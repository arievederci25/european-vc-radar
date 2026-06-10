# Data scripts

Utility scripts for the European VC Radar Supabase `deals` table. New deals
are added by the monthly **big scrape** (a Cowork routine — see
`vc-radar-monthly-scrape.md` in the repo root), where Silicon Canals is one
Tier 1 source among many. These scripts only export or enrich existing data.

## Scripts

| Script | What it does | How it runs |
|---|---|---|
| `export_deals_json.py` | Dumps all deals to `data/deals.json`, the static snapshot the site serves for fast loads. | Automated: `.github/workflows/rebuild-deals-snapshot.yml` (monthly, 2nd) + as the final step of the big scrape. Stdlib only — no install. |
| `enrich_descriptions.py` | Fills in missing one-sentence company descriptions by re-reading the source article with Claude. | Manual, local. |
| `enrich_null_amounts.py` | Re-extracts missing `amount_eur` values for deals that landed with a NULL amount. Updates the row if a confirmed amount ≥ €0.5M is found. | Manual, local. |
| `export_null_amount_xlsx.py` | Exports every deal still missing an amount to `data/null_amount_deals.xlsx` for manual review. | Manual, local. |

## Inclusion policy

Deals are kept only when the round size is confirmed and **≥ €0.5M**.
Undisclosed-amount rounds are excluded. The threshold lives in one constant
per script:

```python
MIN_AMOUNT_EUR_M = 0.5  # change here if the policy ever shifts
```

## Running the manual scripts

```bash
pip install -r scrapers/requirements.txt
# set the environment variables below, then e.g.:
python scrapers/enrich_null_amounts.py
```

`export_deals_json.py` needs no install (standard library only).

## Environment variables

- `SUPABASE_URL` — Supabase project URL (defaults to the production project)
- `SUPABASE_KEY` (or `SUPABASE_ANON_KEY`) — Supabase anon key (read-only)
- `ANTHROPIC_API_KEY` — only for the `enrich_*` scripts (they call Claude)
