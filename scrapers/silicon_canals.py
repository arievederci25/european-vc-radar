"""
Silicon Canals funding round scraper.
Fetches the RSS feed, extracts new articles, uses Claude to parse deal data,
and upserts into Supabase. Skips articles already in the DB by source_url.
"""

import os, sys, json, re
from datetime import datetime, timezone
import feedparser
import requests
from bs4 import BeautifulSoup
import anthropic

# cloudscraper bypasses Silicon Canals' Cloudflare protection (which blocks
# datacenter IPs like GitHub Actions runners with a 403).
try:
    import cloudscraper
    sc_session = cloudscraper.create_scraper()
except ImportError:
    sc_session = requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

FEED_URL = "https://siliconcanals.com/feed/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def supabase_get(path, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    r.raise_for_status()
    return r.json()


def supabase_upsert(table, rows):
    # on_conflict=company,year,quarter matches the UNIQUE constraint on the deals
    # table so merge-duplicates actually merges instead of returning a 409.
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict=company,year,quarter",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=rows,
    )
    if not r.ok:
        raise requests.exceptions.HTTPError(f"HTTP {r.status_code}: {r.text[:300]}", response=r)


def fetch_article_text(url):
    try:
        r = sc_session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        return article.get_text(" ", strip=True)[:4000] if article else ""
    except Exception as e:
        print(f"  Could not fetch article: {e}")
        return ""


# Stage values the deals table CHECK constraint accepts.
VALID_STAGES = {
    "Seed", "Series A", "Series B", "Series C", "Series D",
    "Series E", "Series F", "Series G", "Series H", "Series I", "Series J",
    "Series E+", "IPO", "Growth",
}
STAGE_REMAP = {
    "Pre-Seed": "Seed", "Pre Seed": "Seed", "Preseed": "Seed",
    "Late Stage": "Growth", "Growth Equity": "Growth", "PE": "Growth", "Private Equity": "Growth",
}


def normalize_stage(stage):
    if not stage:
        return None
    s = stage.strip()
    if s in VALID_STAGES:
        return s
    return STAGE_REMAP.get(s)


def extract_deal(title, text, url, pub_date):
    prompt = f"""You are extracting structured data from a European startup funding article.

Article title: {title}
Article URL: {url}
Article text (first 4000 chars):
{text}

Extract as JSON. Return the literal "null" if NOT a primary funding round (skip M&A/acquisitions, grants, pure debt, product launches, opinion pieces):
{{
  "company": "company name receiving the funding",
  "country": "2-letter ISO country code of company HQ (NL, DE, FR, UK, etc)",
  "flag": "flag emoji",
  "stage": "EXACTLY one of: Seed, Series A, Series B, Series C, Series D, Series E, Series F, Series G, Series H, Series I, Series J, Series E+, IPO, Growth",
  "amount_eur": "deal size in EUR millions as a number, e.g. 12.5 (number or null)",
  "amount_display": "human-readable e.g. '€12.5M' or '€150M' (string or null)",
  "sector": "one of: SaaS, AI, Fintech, Healthtech, Cleantech, Deeptech, E-commerce, Mobility, Proptech, Edtech, Cybersecurity, Logistics, Foodtech, Other",
  "lead_investor": "name of lead investor firm, or 'Undisclosed'",
  "description": "one sentence describing what the company does"
}}

Stage mapping: Pre-Seed -> Seed. Late-stage/private-equity without a series letter -> Growth.
Currency: Convert USD/GBP to EUR (USD*0.92, GBP*1.17).
Company must be European (EU + UK + Switzerland + Norway + Iceland). Return "null" if not European.
For K (thousands) amounts like "€600K", amount_eur should be 0.6 (i.e. millions).

Return ONLY the JSON object or the literal "null". No prose, no markdown.
"""
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        if raw.lower() == "null" or not raw:
            return None
        data = json.loads(raw)
        if not data.get("company") or not data.get("country"):
            return None
        normalized = normalize_stage(data.get("stage"))
        if not normalized:
            return None
        data["stage"] = normalized
        return data
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
    rows = supabase_get("deals", f"source_urls=cs.%5B%22{requests.utils.quote(url)}%22%5D&select=id")
    return len(rows) > 0


def main():
    print("Fetching Silicon Canals RSS feed…")
    feed = feedparser.parse(FEED_URL)
    entries = feed.entries
    print(f"Found {len(entries)} articles in feed")

    new_deals = 0
    skipped = 0

    for entry in entries:
        url = entry.get("link", "")
        title = entry.get("title", "")

        funding_keywords = ["secures", "raises", "funding", "million", "invest", "round", "capital", "seed", "series"]
        if not any(k in title.lower() for k in funding_keywords):
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

        year, quarter, announced_date = parse_date(entry.get("published", ""))

        # Standardise amount_display to a single "€X.YM" format (no K, no B).
        if deal.get("amount_eur") is not None:
            v = round(float(deal["amount_eur"]) * 10) / 10
            deal["amount_display"] = "€" + (str(int(v)) if v == int(v) else str(v)) + "M"
        else:
            deal["amount_display"] = None

        deal.update({
            "year": year,
            "quarter": quarter,
            "announced_date": announced_date,
            "source_urls": [url],
        })

        print(f"  -> {deal.get('company')} | {deal.get('amount_display')} | {deal.get('stage')} | {deal.get('country')}")
        supabase_upsert("deals", [deal])
        new_deals += 1

    print(f"\nDone. New deals added: {new_deals}, skipped: {skipped}")


if __name__ == "__main__":
    main()
