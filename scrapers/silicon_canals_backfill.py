"""
Silicon Canals historical backfill scraper.
Scrapes the Silicon Canals website to find all deals since 2020 that aren't in Supabase.
Uses search/archive pages to discover articles, then extracts deal data with Claude.
"""

import os, sys, json, re, time
from datetime import datetime, timezone
from urllib.parse import urlencode, quote
import requests
from bs4 import BeautifulSoup
import anthropic

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VCRadarBot/1.0)"}
KEYWORDS = ["secures", "raises", "funding", "million", "invest", "round", "capital", "seed", "series"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def supabase_get(path, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
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
    )
    r.raise_for_status()


def fetch_article_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        return article.get_text(" ", strip=True)[:4000] if article else ""
    except Exception as e:
        print(f"  Could not fetch article: {e}")
        return ""


def extract_deal(title, text, url, pub_date):
    prompt = f"""You are extracting structured data from a startup funding article.

Article title: {title}
Article URL: {url}
Article text (first 4000 chars):
{text}

Extract the following fields as JSON. Use null if unknown:
{{
  "company": "company name (string)",
  "country": "2-letter ISO country code of the company HQ (string, e.g. NL, DE, FR)",
  "flag": "flag emoji for that country (string)",
  "stage": "one of: Pre-Seed, Seed, Series A, Series B, Series C, Series D, Growth, Debt, Grant, Acquisition (string)",
  "amount_eur": "deal size in EUR millions as a number, e.g. 12.5 (number or null)",
  "amount_display": "human-readable string e.g. '€12.5M' or '€150M' (string or null)",
  "sector": "one of: SaaS, AI, Fintech, Healthtech, Cleantech, Deeptech, E-commerce, Mobility, Proptech, Edtech, Cybersecurity, Logistics, Foodtech, Other (string)",
  "lead_investor": "name of lead investor firm, or 'Undisclosed' (string)",
  "description": "one sentence describing what the company does (string)"
}}

Only return valid JSON, nothing else. If this article is NOT about a funding round, return null.
"""
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
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
        rows = supabase_get("deals", f"source_urls=cs.%5B%22{quote(url)}%22%5D&select=id")
        return len(rows) > 0
    except:
        return False


def scrape_site_search(years=None):
    """
    Scrape Silicon Canals by searching for funding-related articles.
    Returns list of article URLs found.
    """
    if years is None:
        years = range(2020, 2026)

    articles = []
    for year in years:
        print(f"Searching for articles from {year}…")

        for month in range(1, 13):
            search_date = f"{year}-{month:02d}"
            params = {
                "s": "funding",  # Search keyword
                "post_type": "post",
                "year": year,
                "monthnum": month,
            }

            url = f"https://siliconcanals.com/?{urlencode(params)}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")

                # Find all article links
                for link in soup.find_all("a", href=True):
                    href = link.get("href", "")
                    text = link.get_text(strip=True)

                    # Check if this looks like an article link from Silicon Canals
                    if "siliconcanals.com" in href and any(k in text.lower() for k in KEYWORDS):
                        if href not in articles:
                            articles.append(href)

                time.sleep(0.5)  # Rate limiting
            except Exception as e:
                print(f"  Error searching {search_date}: {e}")
                continue

    return list(set(articles))  # Deduplicate


def scrape_feed_archive():
    """
    Scrape the RSS feed for all historical entries.
    """
    import feedparser

    print("Fetching Silicon Canals RSS feed…")
    feed_url = "https://siliconcanals.com/feed/"
    feed = feedparser.parse(feed_url)

    articles = []
    for entry in feed.entries:
        url = entry.get("link", "")
        title = entry.get("title", "")
        if url and any(k in title.lower() for k in KEYWORDS):
            articles.append({
                "url": url,
                "title": title,
                "published": entry.get("published", ""),
            })

    return articles


def main():
    print("=" * 60)
    print("SILICON CANALS HISTORICAL BACKFILL SCRAPER")
    print("=" * 60)

    # Scrape RSS feed for historical articles
    articles = scrape_feed_archive()
    print(f"\nFound {len(articles)} articles in RSS feed")

    new_deals = 0
    skipped = 0
    processed_urls = set()

    for entry in articles:
        url = entry["url"]
        title = entry["title"]
        pub_date = entry["published"]

        # Skip duplicates
        if url in processed_urls:
            continue
        processed_urls.add(url)

        # Skip if already in database
        if already_tracked(url):
            print(f"  Already tracked: {title[:60]}")
            skipped += 1
            continue

        print(f"Processing: {title[:70]}")
        text = fetch_article_text(url)
        deal = extract_deal(title, text, url, pub_date)

        if not deal:
            print(f"  Not a funding round, skipping")
            skipped += 1
            continue

        year, quarter, announced_date = parse_date(pub_date)

        # Skip deals before 2020
        if year < 2020:
            print(f"  Skipping (before 2020)")
            skipped += 1
            continue

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
            print(f"  Error upserting deal: {e}")
            skipped += 1

        time.sleep(1)  # Rate limit API calls

    print(f"\n{'=' * 60}")
    print(f"Backfill complete. New deals added: {new_deals}, skipped: {skipped}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
