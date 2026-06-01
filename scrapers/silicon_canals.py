"""
Silicon Canals funding round scraper.
Fetches the RSS feed, extracts new articles, uses Claude to parse deal data,
and upserts into Supabase. Skips articles already in the DB by source_url.

Fallback: if RSS feed is blocked (403/timeout), scrapes the news page directly.
"""

import os, sys, json, re
from datetime import datetime, timezone
import feedparser
import requests
from bs4 import BeautifulSoup
import anthropic

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

FEED_URL = "https://siliconcanals.com/feed/"
FALLBACK_URL = "https://siliconcanals.com/news/startups/funding/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def supabase_get(path, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def supabase_upsert(table, rows):
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=rows,
        timeout=15,
    )
    r.raise_for_status()


def fetch_article_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        return article.get_text(" ", strip=True)[:4000] if article else ""
    except Exception as e:
        print(f"  Could not fetch article: {e}")
        return ""


def get_feed_entries():
    """Try RSS feed first, fall back to scraping the news page."""
    # Try RSS
    try:
        r = requests.get(FEED_URL, headers=HEADERS, timeout=15)
        if r.status_code == 200 and "<rss" in r.text[:500]:
            feed = feedparser.parse(r.text)
            if feed.entries:
                print(f"RSS feed OK â {len(feed.entries)} entries")
                return [
                    {"url": e.get("link", ""), "title": e.get("title", ""), "published": e.get("published", "")}
                    for e in feed.entries
                ]
        print(f"RSS returned {r.status_code}, trying fallback page scrapeâ¦")
    except Exception as e:
        print(f"RSS fetch failed ({e}), trying fallback page scrapeâ¦")

    # Fallback: scrape the funding news page for article links
    try:
        r = requests.get(FALLBACK_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        entries = []
        for a in soup.select("a[href*='siliconcanals.com']"):
            href = a["href"]
            title = a.get_text(strip=True)
            if len(title) > 20 and href not in [e["url"] for e in entries]:
                entries.append({"url": href, "title": title, "published": ""})
        # Also look for article cards
        for card in soup.select("article, .post, .entry"):
            link = card.find("a", href=True)
            heading = card.find(["h2", "h3", "h4"])
            if link and heading:
                href = link["href"]
                if not href.startswith("http"):
                    href = "https://siliconcanals.com" + href
                title = heading.get_text(strip=True)
                if href not in [e["url"] for e in entries]:
                    entries.append({"url": href, "title": title, "published": ""})
        print(f"Fallback scrape: found {len(entries)} article links")
        return entries[:40]  # cap at 40 to avoid rate limits
    except Exception as e:
        print(f"Fallback scrape also failed: {e}")
        return []


def extract_deal(title, text, url, pub_date):
    prompt = f"""You are extracting structured data from a startup funding article.

Article title: {title}
Article URL: {url}
Article text (first 4000 chars):
{text}

Extract the following fields as JSON. Use null if unknown:
{{
  "company": "company name (string)",
  "country": "full country name of company HQ (string, e.g. Netherlands, Germany, France, United Kingdom)",
  "flag": "flag emoji for that country (string)",
  "stage": "one of: Pre-Seed, Seed, Series A, Series B, Series C, Series D, Growth, Debt, Grant, Acquisition (string)",
  "amount_eur": "deal size in EUR millions as a number, e.g. 12.5 (number or null)",
  "amount_display": "human-readable string e.g. 'â¬12.5M' or 'â¬150M' (string or null)",
  "sector": "one of: SaaS, AI, FinTech, HealthTech, CleanTech, DeepTech, E-commerce, Mobility, PropTech, EdTech, Cybersecurity, Logistics, FoodTech, Other (string)",
  "lead_investor": "name of lead investor firm, or 'Undisclosed' (string)",
  "description": "one sentence describing what the company does (string)"
}}

Only return valid JSON, nothing else. If this article is NOT about a European funding round, return null.
"""
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        if raw.lower() == "null":
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"  Claude extraction failed: {e}")
        return None


def parse_date(pub_date_str):
    try:
        import email.utils
        t = email.utils.parsedate_to_datetime(pub_date_str)
        year = t.year
        month = t.month
        quarter = (month - 1) // 3 + 1
        announced_date = t.strftime("%Y-%m-%d")
        return year, quarter, announced_date
    except Exception:
        now = datetime.now(timezone.utc)
        return now.year, (now.month - 1) // 3 + 1, now.strftime("%Y-%m-%d")


def already_tracked(url):
    try:
        rows = supabase_get(
            "deals",
            f"source_urls=cs.%5B%22{requests.utils.quote(url)}%22%5D&select=id"
        )
        return len(rows) > 0
    except Exception:
        return False


FUNDING_KEYWORDS = [
    "secures", "raises", "funding", "million", "invest",
    "round", "capital", "seed", "series", "backed", "closes"
]


def main():
    print("Fetching Silicon Canals articlesâ¦")
    entries = get_feed_entries()

    if not entries:
        print("No articles found â exiting.")
        sys.exit(0)

    new_deals = 0
    skipped = 0

    for entry in entries:
        url = entry["url"]
        title = entry["title"]

        if not any(k in title.lower() for k in FUNDING_KEYWORDS):
            skipped += 1
            continue

        if already_tracked(url):
            print(f"  Already tracked: {title[:60]}")
            skipped += 1
            continue

        print(f"Processing: {title[:70]}")
        text = fetch_article_text(url)
        deal = extract_deal(title, text, url, entry.get("published", ""))

        if not deal:
            print(f"  Not a funding round, skipping")
            skipped += 1
            continue

        # Skip non-European or below threshold
        if deal.get("amount_eur") is not None and deal["amount_eur"] < 0.5:
            print(f"  Below â¬500k threshold, skipping")
            skipped += 1
            continue

        year, quarter, announced_date = parse_date(entry.get("published", ""))
        deal.update({
            "year": year,
            "quarter": quarter,
            "announced_date": announced_date,
            "source_urls": [url],
        })

        print(f"  -> {deal.get('company')} | {deal.get('amount_display')} | {deal.get('stage')} | {deal.get('country')}")
        try:
            supabase_upsert("deals", [deal])
            new_deals += 1
        except Exception as e:
            print(f"  Supabase upsert failed: {e}")

    print(f"\nDone. New deals added: {new_deals}, skipped: {skipped}")


if __name__ == "__main__":
    main()
