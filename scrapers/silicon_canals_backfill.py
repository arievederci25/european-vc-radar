"""
Silicon Canals historical backfill scraper (sitemap-based).

Strategy for efficiency:
1. Pull all 137 post sitemaps from Silicon Canals (XML, fast).
2. Filter URLs by funding-related keywords in the slug (no API calls).
3. Bulk-check Supabase to skip URLs already tracked.
4. Fetch article HTML for survivors, parse publication date from meta.
5. Skip articles before 2020.
6. Extract deal data using Claude Haiku 4.5 (cheapest model).
7. Upsert into Supabase.

Designed as a ONE-OFF historic run. Run via GitHub Actions:
  Actions -> "Backfill Silicon Canals (Historical)" -> Run workflow.
"""

import os, sys, json, re, time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET
import requests
from bs4 import BeautifulSoup
import anthropic

# cloudscraper bypasses Silicon Canals' Cloudflare protection.
# Falls back to plain requests for Supabase + Anthropic calls.
try:
    import cloudscraper
    sc_session = cloudscraper.create_scraper()
except ImportError:
    sc_session = requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
}

SITEMAP_INDEX = "https://siliconcanals.com/sitemap_index.xml"

# Keywords that strongly suggest a funding article (in URL slug, lowercase)
FUNDING_SLUG_KEYWORDS = [
    "raises", "secures", "bags", "lands", "scores", "closes",
    "raise-", "secure-", "funding", "seed-round", "series-a", "series-b",
    "series-c", "series-d", "series-e", "pre-seed", "seed-funding",
    "round-of", "investment-of", "invest-in", "to-fuel", "to-scale",
    "to-expand", "to-accelerate", "valuation", "acquires", "acquired-by",
]

# Slug must NOT match these (skip events, partnerships, opinion, etc.)
SKIP_SLUG_KEYWORDS = [
    "press-release-distribution", "sponsored-content", "advertorial",
    "career", "opinion", "interview-", "webinar", "podcast",
]

# Year cutoff (deals before this year are skipped).
MIN_YEAR = 2024

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ----- Supabase helpers -----

def supabase_get(path, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def supabase_upsert(table, rows):
    # The deals table has UNIQUE (company, year, quarter) — Supabase needs that
    # on_conflict target explicitly for merge-duplicates to work.
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict=company,year,quarter",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=rows,
        timeout=30,
    )
    if not r.ok:
        # Surface the actual error from Supabase for easier debugging.
        raise requests.exceptions.HTTPError(
            f"HTTP {r.status_code}: {r.text[:300]}", response=r
        )


def get_all_existing_source_urls():
    """Pull every source_url across all deals (one bulk query, paginated)."""
    all_urls = set()
    page_size = 1000
    offset = 0
    while True:
        rows = supabase_get(
            "deals",
            f"select=source_urls&limit={page_size}&offset={offset}",
        )
        if not rows:
            break
        for row in rows:
            for url in row.get("source_urls") or []:
                all_urls.add(url)
        if len(rows) < page_size:
            break
        offset += page_size
    return all_urls


# ----- Sitemap parsing -----

def fetch_sitemap_index():
    """Return list of post-sitemap URLs from the sitemap index."""
    r = sc_session.get(SITEMAP_INDEX, headers=HEADERS, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [
        loc.text for loc in root.findall(".//s:sitemap/s:loc", ns)
        if "post-sitemap" in (loc.text or "")
    ]


def fetch_sitemap_urls(sitemap_url):
    """Return list of (url, lastmod) tuples from a single sitemap."""
    try:
        r = sc_session.get(sitemap_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        out = []
        for entry in root.findall(".//s:url", ns):
            loc = entry.find("s:loc", ns)
            mod = entry.find("s:lastmod", ns)
            if loc is not None and loc.text:
                out.append((loc.text, mod.text if mod is not None else ""))
        return out
    except Exception as e:
        print(f"  Failed to parse {sitemap_url}: {e}")
        return []


# Auto-generated SEO-spam URL pattern: slug starts with a short letter prefix
# like /sc-n-..., /sc-d-..., /k-t-..., /r-t-..., /z-t-..., /k-bt-..., /r-tns-...
# These pages 404 in practice (~30% of URLs match a funding keyword by coincidence).
SEO_SPAM_PREFIX_RE = re.compile(r"^/[a-z]{1,3}-[a-z]{1,4}-")


def looks_like_funding(url):
    """Cheap URL-slug filter for funding articles."""
    slug = urlparse(url).path.lower()
    if SEO_SPAM_PREFIX_RE.match(slug):
        return False
    if any(skip in slug for skip in SKIP_SLUG_KEYWORDS):
        return False
    if any(kw in slug for kw in FUNDING_SLUG_KEYWORDS):
        return True
    # Catch amount patterns like "raises-50m", "secures-e10m", etc.
    if re.search(r"-\d+(?:\.\d+)?-?(?:m|million|b|billion)\b", slug):
        return True
    return False


# ----- Article fetching & extraction -----

def fetch_article(url):
    """Fetch article HTML and return (text, published_date_iso, title)."""
    try:
        r = sc_session.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  Fetch failed: {e}")
        return None, None, None

    soup = BeautifulSoup(r.text, "html.parser")

    # Title
    title_tag = soup.find("meta", {"property": "og:title"}) or soup.find("title")
    title = title_tag.get("content") if title_tag and title_tag.get("content") else (
        title_tag.get_text(strip=True) if title_tag else ""
    )

    # Published date from meta
    pub = None
    for prop in ("article:published_time", "og:article:published_time"):
        m = soup.find("meta", {"property": prop})
        if m and m.get("content"):
            pub = m.get("content")
            break

    # Clean body text
    for tag in soup(["nav", "footer", "aside", "script", "style", "form"]):
        tag.decompose()
    article = soup.find("article") or soup.find("main") or soup.body
    text = article.get_text(" ", strip=True)[:2500] if article else ""

    return text, pub, title


def parse_iso_date(pub):
    """Return (year, quarter, YYYY-MM-DD) or None."""
    if not pub:
        return None
    try:
        # Handle "2023-10-04T07:06:03+00:00"
        t = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        return t.year, (t.month - 1) // 3 + 1, t.strftime("%Y-%m-%d")
    except Exception:
        return None


# Cacheable system prompt - reused across all extractions
SYSTEM_PROMPT = """You extract structured data from European startup funding articles.

Output ONLY valid JSON matching this schema, or the literal string "null" if the article is NOT a primary funding round (skip pure M&A/acquisitions, grants, debt-only news, product launches, opinion pieces, events, listicles).

Schema:
{
  "company": "company name receiving the funding",
  "country": "2-letter ISO country code of company HQ (e.g. NL, DE, FR, UK)",
  "flag": "flag emoji for that country",
  "stage": "one of EXACTLY these values: Seed, Series A, Series B, Series C, Series D, Series E, Series F, Series G, Series H, Series I, Series J, Series E+, IPO, Growth",
  "amount_eur": "deal size in EUR millions as a number (e.g. 12.5), or null if undisclosed",
  "amount_display": "human-readable e.g. '€12.5M' or '€150M' or null",
  "sector": "one of: SaaS, AI, Fintech, Healthtech, Cleantech, Deeptech, E-commerce, Mobility, Proptech, Edtech, Cybersecurity, Logistics, Foodtech, Other",
  "lead_investor": "name of lead investor firm, or 'Undisclosed'",
  "description": "one-sentence description of what the company does"
}

Stage mapping rules:
- Pre-Seed funding rounds -> use "Seed"
- Late-stage / pre-IPO / private equity rounds without a series letter -> use "Growth"
- Debt facilities, grants, or acquisitions -> return "null" (not a primary funding round)

Other rules:
- The company must be European (EU + UK + Switzerland + Norway + Iceland). Return "null" if it's not European.
- Convert USD/GBP amounts to EUR roughly (USD*0.92, GBP*1.17).
- Return ONLY the JSON object or the literal "null". No prose, no markdown fences.
"""

# Defensive: if the model returns a stage outside the allowed set, normalize or drop.
VALID_STAGES = {
    "Seed", "Series A", "Series B", "Series C", "Series D",
    "Series E", "Series F", "Series G", "Series H", "Series I", "Series J",
    "Series E+", "IPO", "Growth",
}

STAGE_REMAP = {
    "Pre-Seed": "Seed",
    "Pre Seed": "Seed",
    "Preseed": "Seed",
    "Late Stage": "Growth",
    "Growth Equity": "Growth",
    "PE": "Growth",
    "Private Equity": "Growth",
}


def normalize_stage(stage):
    """Return a stage value the DB will accept, or None to drop the deal."""
    if not stage:
        return None
    s = stage.strip()
    if s in VALID_STAGES:
        return s
    if s in STAGE_REMAP:
        return STAGE_REMAP[s]
    return None  # Drop deals that don't map cleanly (debt, grant, acquisition, etc.)


def extract_deal(title, text, url):
    """Call Claude Haiku to extract structured deal data. Returns dict or None."""
    user_content = f"Title: {title}\nURL: {url}\n\nArticle text:\n{text}"
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown fences if any
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        if raw.lower() == "null" or not raw:
            return None
        data = json.loads(raw)
        # Sanity check
        if not data.get("company") or not data.get("country"):
            return None
        return data
    except Exception as e:
        print(f"  Extraction failed: {e}")
        return None


# ----- Main pipeline -----

def main():
    print("=" * 70)
    print("SILICON CANALS HISTORIC BACKFILL (sitemap-based)")
    print("=" * 70)

    # Step 1: pull existing URLs from Supabase
    print("\n[1/5] Loading existing source URLs from Supabase…")
    existing_urls = get_all_existing_source_urls()
    print(f"      {len(existing_urls)} URLs already tracked.")

    # Step 2: enumerate sitemaps
    print("\n[2/5] Fetching sitemap index…")
    sitemaps = fetch_sitemap_index()
    print(f"      Found {len(sitemaps)} post sitemaps.")

    # Step 3: pull all URLs, filter by funding slug + lastmod >= MIN_YEAR, skip existing
    print(f"\n[3/5] Walking sitemaps; keeping funding-slug URLs with lastmod >= {MIN_YEAR}…")
    candidates = []
    min_date_str = f"{MIN_YEAR}-01-01"
    for i, sm in enumerate(sitemaps, 1):
        urls = fetch_sitemap_urls(sm)
        kept_before = len(candidates)
        for url, lastmod in urls:
            if url in existing_urls:
                continue
            if not looks_like_funding(url):
                continue
            # Skip if lastmod indicates pre-MIN_YEAR. lastmod can only go forward
            # in time, so lastmod < cutoff guarantees publish < cutoff.
            if lastmod and lastmod[:10] < min_date_str:
                continue
            candidates.append(url)
        print(f"      [{i}/{len(sitemaps)}] {sm.rsplit('/', 1)[-1]}: {len(urls)} urls, "
              f"+{len(candidates) - kept_before} candidates (total: {len(candidates)})")

    print(f"\n      {len(candidates)} candidate funding URLs to process.")

    if not candidates:
        print("Nothing to do.")
        return

    # Step 4 & 5: fetch articles, filter by date, extract, upsert
    print(f"\n[4/5] Fetching articles and extracting deals…")
    new_deals = 0
    skipped_old = 0
    skipped_not_funding = 0
    fetch_failed = 0
    batch = []

    for i, url in enumerate(candidates, 1):
        if i % 25 == 0 or i == 1:
            print(f"      [{i}/{len(candidates)}] processed | "
                  f"new: {new_deals} | old (<2020): {skipped_old} | "
                  f"not funding: {skipped_not_funding} | fetch fail: {fetch_failed}")

        text, pub, title = fetch_article(url)
        if not text:
            fetch_failed += 1
            continue

        # Parse date
        date_parts = parse_iso_date(pub)
        if not date_parts:
            # Couldn't parse date - skip rather than guess
            skipped_not_funding += 1
            continue

        year, quarter, announced_date = date_parts
        if year < MIN_YEAR:
            skipped_old += 1
            continue

        deal = extract_deal(title, text, url)
        if not deal:
            skipped_not_funding += 1
            continue

        # Normalize stage to one of the values the DB CHECK constraint allows.
        normalized_stage = normalize_stage(deal.get("stage"))
        if not normalized_stage:
            skipped_not_funding += 1
            continue
        deal["stage"] = normalized_stage

        # Standardise amount_display to a single format: "€X.YM" with trailing .0
        # stripped (no K, no B). Whatever Claude returned is overridden so the
        # whole table stays consistent.
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

        batch.append(deal)
        new_deals += 1

        # Flush every 25 deals
        if len(batch) >= 25:
            try:
                supabase_upsert("deals", batch)
                print(f"      >>> Flushed batch of {len(batch)} deals.")
                batch = []
            except Exception as e:
                print(f"      !!! Batch upsert failed: {e}")
                # Try one-by-one so a single bad row doesn't kill the whole batch
                for row in batch:
                    try:
                        supabase_upsert("deals", [row])
                    except Exception as inner:
                        print(f"          row failed: {row.get('company')} y{row.get('year')}q{row.get('quarter')}: {str(inner)[:120]}")
                batch = []

        # Light rate limit (Silicon Canals tolerates fast scraping; keep small.)
        time.sleep(0.05)

    # Final flush
    if batch:
        try:
            supabase_upsert("deals", batch)
            print(f"      >>> Flushed final batch of {len(batch)} deals.")
        except Exception as e:
            print(f"      !!! Final batch upsert failed: {e}")
            for row in batch:
                try:
                    supabase_upsert("deals", [row])
                except Exception as inner:
                    print(f"          row failed: {row.get('company')} y{row.get('year')}q{row.get('quarter')}: {str(inner)[:120]}")

    print(f"\n[5/5] Done.")
    print(f"      New deals added: {new_deals}")
    print(f"      Skipped (pre-2020): {skipped_old}")
    print(f"      Skipped (not funding / non-EU): {skipped_not_funding}")
    print(f"      Fetch failures: {fetch_failed}")
    print("=" * 70)


if __name__ == "__main__":
    main()
