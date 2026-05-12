"""
Re-extract missing amount_eur (and optionally description) values for deals
that originally landed with NULL amounts.

These deals were already extracted once and Claude returned null for the
amount — usually because the LLM missed a number buried in the article
body, or because the article truly doesn't disclose the round size.

Strategy: fetch the same source URL again, run a tightly focused prompt
asking specifically for the amount. Updates the DB row if a number >= 0.5M
is found.

Also enriches up to MAX_DESCRIPTIONS missing descriptions along the way
(so the user gets a sample of description enrichment for free).
"""

import os
import sys
import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
import anthropic

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
}

# Same min as the rest of the pipeline.
MIN_AMOUNT_EUR_M = 0.5

# Cap the number of NULL-description rows we backfill with a description.
# User asked for 3.
MAX_DESCRIPTIONS = 3

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """You are extracting a single funding amount from a startup funding article.

You will be given the article text. Extract:

{
  "amount_eur": number in EUR millions (e.g. 12.5), or null if the article does NOT state a concrete deal size,
  "description": one-sentence description of what the company does, or null if not derivable from the article
}

How to interpret amounts:
  - "raises EUR X million"  -> amount_eur = X
  - "raises $X million"     -> amount_eur = X * 0.92
  - "secures GBP X million" -> amount_eur = X * 1.17
  - "EUR X.YK" / "EUR XK"   -> amount_eur = X/1000 (or X.Y/1000)
  - "valued at EUR X billion" -> this is VALUATION, NOT amount. Return null for amount_eur in this case unless a separate round size is also stated.
  - Range like "between EUR 5-10 million" -> use the midpoint, 7.5
  - "Series A funding" / "secures funding" with NO number anywhere -> null

Be thorough: scan the entire text. Look for digits with M, m, million, mn, mln, K, B, b, billion suffixes.

Return ONLY the JSON object. No prose, no markdown."""


def fetch_article_text(url):
    try:
        r = sc_session.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "footer", "aside", "script", "style", "form"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        return article.get_text(" ", strip=True)[:4000] if article else ""
    except Exception as e:
        print(f"    fetch failed: {e}")
        return ""


def get_null_amount_deals():
    rows = []
    offset = 0
    page = 1000
    while True:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/deals"
            f"?amount_eur=is.null&select=id,company,year,quarter,source_urls,description"
            f"&limit={page}&offset={offset}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def update_deal(deal_id, amount_eur, description=None):
    fields = {}
    if amount_eur is not None:
        fields["amount_eur"] = float(amount_eur)
        v = round(float(amount_eur) * 10) / 10
        fields["amount_display"] = "€" + (str(int(v)) if v == int(v) else str(v)) + "M"
    if description:
        fields["description"] = description
    if not fields:
        return
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/deals?id=eq.{deal_id}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=fields,
        timeout=30,
    )
    r.raise_for_status()


def extract(text, url, company):
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Company: {company}\nURL: {url}\n\nArticle text:\n{text}"}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"    extraction failed: {e}")
        return None


def main():
    deals = get_null_amount_deals()
    print(f"Found {len(deals)} deals with NULL amount.\n")

    found_amount = 0
    found_amount_below_min = 0
    found_description = 0
    skipped_no_url = 0
    skipped_no_amount = 0
    failed = 0

    for i, deal in enumerate(deals, 1):
        company = deal.get("company") or "?"
        urls = deal.get("source_urls") or []
        if not urls:
            skipped_no_url += 1
            continue

        url = urls[0]
        if i % 10 == 1 or i == len(deals):
            print(f"[{i}/{len(deals)}] processing... (found amounts so far: {found_amount}, "
                  f"below-min: {found_amount_below_min}, descriptions: {found_description}, "
                  f"failed: {failed}, no-url: {skipped_no_url})")

        text = fetch_article_text(url)
        if not text:
            failed += 1
            continue

        data = extract(text, url, company)
        if data is None:
            failed += 1
            continue

        amount = data.get("amount_eur")
        desc = data.get("description")

        update_amount = None
        update_desc = None

        if amount is not None:
            try:
                a = float(amount)
                if a >= MIN_AMOUNT_EUR_M:
                    update_amount = a
                    found_amount += 1
                else:
                    found_amount_below_min += 1
            except (TypeError, ValueError):
                pass
        else:
            skipped_no_amount += 1

        if desc and not deal.get("description") and found_description < MAX_DESCRIPTIONS:
            update_desc = desc
            found_description += 1

        if update_amount is not None or update_desc:
            try:
                update_deal(deal["id"], update_amount, update_desc)
                if update_amount is not None:
                    print(f"  [+] {company} {deal.get('year')}Q{deal.get('quarter')}: €{update_amount}M"
                          + (" + desc" if update_desc else ""))
                elif update_desc:
                    print(f"  [d] {company}: desc only")
            except Exception as e:
                print(f"  [!] {company}: db update failed: {e}")
                failed += 1

        time.sleep(0.15)

    print(f"\nDone.")
    print(f"  Found amounts (>= EUR {MIN_AMOUNT_EUR_M}M): {found_amount}")
    print(f"  Found amounts but below threshold:        {found_amount_below_min}")
    print(f"  Descriptions enriched:                    {found_description}")
    print(f"  No source URL on row:                     {skipped_no_url}")
    print(f"  Article said amount is undisclosed:       {skipped_no_amount}")
    print(f"  Fetch/extract failures:                   {failed}")


if __name__ == "__main__":
    main()
