"""
Dump deals from Supabase into data/deals.json as a static asset.

Run after every scraper job. The frontend prefers this CDN-served snapshot
(GitHub Pages, Fastly edge) over hitting Supabase directly, which makes the
page noticeably faster.
"""
import json
import os
import sys
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://swhjffkhhwktrvwiqmoe.supabase.co")
# Use anon key — read-only public deals are accessible via RLS.
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")
if not SUPABASE_KEY:
    print("ERROR: set SUPABASE_KEY or SUPABASE_ANON_KEY", file=sys.stderr)
    sys.exit(1)

COLS = "year,quarter,company,country,flag,stage,amount_eur,amount_display,sector,lead_investor,description"
PAGE = 1000
ORDER = "year.asc,quarter.asc,amount_eur.desc.nullslast"

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "deals.json")
OUT_PATH = os.path.abspath(OUT_PATH)


def fetch_page(offset):
    url = (
        f"{SUPABASE_URL}/rest/v1/deals?select={COLS}"
        f"&order={ORDER}&limit={PAGE}&offset={offset}"
    )
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    all_rows = []
    offset = 0
    while True:
        page = fetch_page(offset)
        all_rows.extend(page)
        print(f"  fetched page offset={offset}: +{len(page)} (total: {len(all_rows)})")
        if len(page) < PAGE:
            break
        offset += PAGE

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, separators=(",", ":"), ensure_ascii=False)

    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\nWrote {len(all_rows)} deals to {OUT_PATH} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
