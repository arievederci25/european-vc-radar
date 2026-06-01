"""
Silicon Canals funding round scraper.

Discovery strategy (tries each in order until entries are found):
  1. Silicon Canals RSS feed directly
  2. rss2json.com proxy (fetches SC feed via their servers, bypasses IP block)
  3. Feedly public API (another RSS proxy)
  4. Google News RSS search for "silicon canals"
  5. Silicon Canals funding page scrape (last resort)

For each discovered article, tries to fetch article body text.
If the article page is also blocked, falls back to title-only extraction.
Upserts qualifying deals (>= EUR 0.5M, European) into Supabase.
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
RSS2JSON_URL = "https://api.rss2json.com/v1/api.json?rss_url=https%3A%2F%2Fsiliconcanals.com%2Ffeed%2F&count=40"
FEEDLY_URL = "https://cloud.feedly.com/v3/streams/contents?streamId=feed%2Fhttps%3A%2F%2Fsiliconcanals.com%2Ffeed%2F&count=40"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q=%22silicon+canals%22+funding&hl=en&gl=US&ceid=US:en"

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
    """Fetch and clean article body text. Returns empty string if blocked."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 403:
            print(f"  Article page blocked (403) - using title-only extraction")
            return ""
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        return article.get_text(" ", strip=True)[:4000] if article else ""
    except Exception as e:
        print(f"  Could not fetch article: {e}")
        return ""


def try_silicon_canals_rss():
    """Try the Silicon Canals RSS feed directly."""
    try:
        r = requests.get(FEED_URL, headers=HEADERS, timeout=15)
        if r.status_code == 200 and "<rss" in r.text[:500]:
            feed = feedparser.parse(r.text)
            if feed.entries:
                print(f"Silicon Canals RSS OK - {len(feed.entries)} entries")
                return [
                    {"url": e.get("link", ""), "title": e.get("title", ""), "published": e.get("published", "")}
                    for e in feed.entries
                ]
        print(f"Silicon Canals RSS returned {r.status_code}")
    except Exception as e:
        print(f"Silicon Canals RSS failed: {e}")
    return []


def try_rss2json_proxy():
    """Fetch Silicon Canals feed via rss2json.com proxy (bypasses IP block)."""
    try:
        r = requests.get(RSS2JSON_URL, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"rss2json returned {r.status_code}")
            return []
        data = r.json()
        if data.get("status") != "ok":
            print(f"rss2json status: {data.get('status')} - {data.get('message','')}")
            return []
        items = data.get("items", [])
        if not items:
            print("rss2json: no items")
            return []
        print(f"rss2json proxy OK - {len(items)} items")
        return [
            {"url": item.get("link", ""), "title": item.get("title", ""), "published": item.get("pubDate", "")}
            for item in items
        ]
    except Exception as e:
        print(f"rss2json proxy failed: {e}")
    return []


def try_feedly_proxy():
    """Fetch Silicon Canals feed via Feedly public API (bypasses IP block)."""
    try:
        r = requests.get(FEEDLY_URL, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"Feedly returned {r.status_code}")
            return []
        data = r.json()
        items = data.get("items", [])
        if not items:
            print("Feedly: no items")
            return []
        print(f"Feedly proxy OK - {len(items)} items")
        entries = []
        for item in items:
            url = item.get("originId", "") or item.get("canonical", [{}])[0].get("href", "")
            title = item.get("title", "")
            pub_ms = item.get("published", 0)
            pub_str = datetime.fromtimestamp(pub_ms / 1000, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000") if pub_ms else ""
            entries.append({"url": url, "title": title, "published": pub_str})
        return entries
    except Exception as e:
        print(f"Feedly proxy failed: {e}")
    return []


def try_google_news_rss():
    """Search Google News for Silicon Canals funding articles."""
    try:
        r = requests.get(GOOGLE_NEWS_URL, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"Google News RSS returned {r.status_code}")
            return []
        feed = feedparser.parse(r.text)
        if not feed.entries:
            print("Google News RSS: no entries")
            return []
        entries = []
        seen = set()
        for e in feed.entries:
            raw_title = e.get("title", "")
            link = e.get("link", "")
            pub = e.get("published", "")
            # Strip source name suffix (e.g. " - Silicon Canals")
            title = re.sub(r"\s*[-|]\s*[\w\s]+$", "", raw_title).strip() or raw_title
            if link not in seen:
                seen.add(link)
                entries.append({"url": link, "title": title, "published": pub})
        print(f"Google News: {len(entries)} entries")
        return entries[:40]
    except Exception as e:
        print(f"Google News RSS failed: {e}")
    return []


def try_direct_page_scrape():
    """Scrape the Silicon Canals funding page directly (likely blocked)."""
    try:
        r = requests.get(FALLBACK_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        entries = []
        seen = set()
        for a in soup.select("a[href*='siliconcanals.com']"):
            href = a["href"]
            title = a.get_text(strip=True)
            if len(title) > 20 and href not in seen:
                seen.add(href)
                entries.append({"url": href, "title": title, "published": ""})
        for card in soup.select("article, .post, .entry"):
            link = card.find("a", href=True)
            heading = card.find(["h2", "h3", "h4"])
            if link and heading:
                href = link["href"]
                if not href.startswith("http"):
                    href = "https://siliconcanals.com" + href
                title = heading.get_text(strip=True)
                if href not in seen:
                    seen.add(href)
                    entries.append({"url": href, "title": title, "published": ""})
        print(f"Direct page scrape: {len(entries)} articles")
        return entries[:40]
    except Exception as e:
        print(f"Direct page scrape failed: {e}")
    return []


def get_feed_entries():
    """Try each discovery method in order until entries are found."""
    entries = try_silicon_canals_rss()
    if entries:
        return entries

    print("Trying rss2json proxy...")
    entries = try_rss2json_proxy()
    if entries:
        return entries

    print("Trying Feedly proxy...")
    entries = try_feedly_proxy()
    if entries:
        return entries

    print("Trying Google News RSS...")
    entries = try_google_news_rss()
    if entries:
        return entries

    print("Trying direct page scrape...")
    return try_direct_page_scrape()


def extract_deal(title, text, url, pub_date):
    text_section = (
        f"Article text (first 4000 chars):\n{text}"
        if text
        else "(Article body unavailable - extract from title only)"
    )
    prompt = f"""You are extracting structured data from a startup funding article.

Article title: {title}
Article URL: {url}
{text_section}

Extract the following fields as JSON. Use null if unknown:
{{
  "company": "company name (string)",
  "country": "full country name of company HQ (string, e.g. Netherlands, Germany, France, United Kingdom)",
  "flag": "flag emoji for that country (string)",
  "stage": "one of: Pre-Seed, Seed, Series A, Series B, Series C, Series D, Growth, Debt, Grant, Acquisition (string)",
  "amount_eur": "deal size in EUR millions as a number, e.g. 12.5 (number or null)",
  "amount_display": "human-readable string e.g. '12.5M' or '150M' (string or null)",
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
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        if raw.lower() == "null":
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"  Claude extraction failed: {e}")
        return None


def parse_date(pub_date_str):
    if not pub_date_str:
        now = datetime.now(timezone.utc)
        return now.year, (now.month - 1) // 3 + 1, now.strftime("%Y-%m-%d")
    # Try RFC 2822 format (RSS feeds)
    try:
        import email.utils
        t = email.utils.parsedate_to_datetime(pub_date_str)
        return t.year, (t.month - 1) // 3 + 1, t.strftime("%Y-%m-%d")
    except Exception:
        pass
    # Try ISO format (rss2json, Feedly)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            t = datetime.strptime(pub_date_str[:19], fmt[:len(pub_date_str[:19])])
            return t.year, (t.month - 1) // 3 + 1, t.strftime("%Y-%m-%d")
        except Exception:
            pass
    now = datetime.now(timezone.utc)
    return now.year, (now.month - 1) // 3 + 1, now.strftime("%Y-%m-%d")


def already_tracked(url):
    try:
        rows = supabase_get(
            "deals",
            f"source_urls=cs.%5B%22{requests.utils.quote(url)}%22%5D&select=id",
        )
        return len(rows) > 0
        except Exception:
            return False


FUNDING_KEYWORDS = [
    "secures", "raises", "funding", "million", "invest",
    "round", "capital", "seed", "series", "backed", "closes",
]


def main():
    print("Fetching Silicon Canals articles...")
    entries = get_feed_entries()

    if not entries:
        print("No articles found from any source - exiting.")
        sys.exit(0)

    new_deals = 0
    skipped = 0

    for entry in entries:
        url = entry["url"]
        title = entry["title"]

        if not title or not any(k in title.lower() for k in FUNDING_KEYWORDS):
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

        if deal.get("amount_eur") is not None and deal["amount_eur"] < 0.5:
            print(f"  Below 500k threshold, skipping")
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
