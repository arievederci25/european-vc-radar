"""
Enrich up to MAX_DESCRIPTIONS NULL-description deals by re-reading their
source article and asking Claude for a one-sentence company description.
"""

import os
import sys
import json
import re
import time

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

MAX_DESCRIPTIONS = int(os.environ.get("MAX_DESCRIPTIONS", "3"))

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


PROMPT = """You will be given a startup funding article. Return ONE concise sentence describing what the company actually does (its product/service/market). No marketing fluff, no investor names, no funding details — just what the company does.

If the article does not contain enough info to describe the company, return the string "null".

Return only the sentence (or "null"). No JSON, no quotes."""


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


def get_null_description_deals():
    # Only rows that have a source URL and that pass the visibility policy
    # (amount_eur not null and >= 0.5), so we don't enrich invisible rows.
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/deals"
        f"?description=is.null&amount_eur=gte.0.5"
        f"&select=id,company,source_urls"
        f"&order=year.desc,quarter.desc"
        f"&limit=50",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    return [d for d in r.json() if d.get("source_urls") and d["source_urls"][0]]


def update_description(deal_id, description):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/deals?id=eq.{deal_id}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"description": description},
        timeout=30,
    )
    r.raise_for_status()


def main():
    candidates = get_null_description_deals()
    print(f"Found {len(candidates)} visible deals with NULL description.\n"
          f"Aiming to enrich {MAX_DESCRIPTIONS}.\n")

    enriched = 0
    for deal in candidates:
        if enriched >= MAX_DESCRIPTIONS:
            break
        company = deal.get("company") or "?"
        url = deal["source_urls"][0]
        text = fetch_article_text(url)
        if not text:
            continue
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": f"{PROMPT}\n\nCompany: {company}\nArticle:\n{text}"}],
            )
            desc = msg.content[0].text.strip()
            # Strip surrounding quotes if Claude added them.
            desc = re.sub(r'^["\']|["\']$', '', desc).strip()
            if not desc or desc.lower() == "null":
                print(f"  [-] {company}: no usable description")
                continue
            update_description(deal["id"], desc)
            enriched += 1
            print(f"  [+] {company}: {desc}")
        except Exception as e:
            print(f"  [!] {company}: failed: {e}")
        time.sleep(0.15)

    print(f"\nDone. Enriched {enriched} descriptions.")


if __name__ == "__main__":
    main()
