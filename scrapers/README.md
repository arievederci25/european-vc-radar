# Silicon Canals Scrapers

This directory contains scrapers for extracting funding deal data from Silicon Canals.

## Inclusion policy

Both scrapers enforce the rules published in the site footer:

1. **Round size confirmed and ≥ €0.5M.** Deals with `amount_eur < 0.5` are skipped.
2. **Undisclosed-amount rounds excluded.** Deals where the article doesn't state
   a concrete amount (so the LLM returns `amount_eur: null`) are skipped.
3. **EUR conversion.** USD/GBP amounts are converted to euros at the
   approximate time-of-deal exchange rate by the extraction prompt.
4. **Europe only.** The extraction prompt asks the LLM to return `null` if the
   company isn't headquartered in the EU + UK + CH + NO + IS.

The minimum amount threshold lives in one constant in each scraper:

```python
MIN_AMOUNT_EUR_M = 0.5  # change here if the policy ever shifts
```

## Scrapers

### `silicon_canals.py` - Regular Updates (RSS Feed)
- **Purpose**: Fetch new funding articles from Silicon Canals RSS feed
- **Schedule**: Monthly (1st of month at 07:00 UTC)
- **Workflow**: `.github/workflows/scrape-silicon-canals.yml`
- **Behavior**: 
  - Fetches latest articles from the RSS feed
  - Skips articles already in the database
  - Extracts deal data using Claude
  - Only processes articles with funding keywords

### `silicon_canals_backfill.py` - Historical Data (One-Time or Manual)
- **Purpose**: Backfill historical deals from Silicon Canals since 2020
- **Schedule**: Manual trigger only (not automated)
- **Workflow**: `.github/workflows/backfill-silicon-canals.yml`
- **Behavior**:
  - Scrapes the RSS feed for all available articles
  - Filters articles from 2020 onwards
  - Skips articles already in the database
  - Extracts deal data using Claude

## How to Run

### Monthly Automatic Scraping
The regular scraper runs automatically on the 1st of every month at 07:00 UTC.

To trigger manually:
1. Go to GitHub → Actions → "Scrape Silicon Canals"
2. Click "Run workflow"

### Historical Backfill
To run the historical backfill (adds deals from 2020-present not yet in database):
1. Go to GitHub → Actions → "Backfill Silicon Canals (Historical)"
2. Click "Run workflow"

This will process all articles from 2020 onwards and add any new deals to Supabase.

## Environment Variables

Both scrapers require:
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_KEY` - Your Supabase API key
- `ANTHROPIC_API_KEY` - Your Anthropic API key

These must be set as GitHub Secrets in your repository.

## Dependencies

See `requirements.txt` for required Python packages.

## How It Works

1. **Scraper Discovery**: Identifies articles with funding-related keywords
2. **Duplicate Check**: Queries Supabase to skip articles already processed
3. **Content Extraction**: Fetches article HTML and extracts text
4. **AI Parsing**: Uses Claude to extract structured deal data (company, amount, stage, etc.)
5. **Database Upsert**: Adds or updates deals in Supabase with deduplication

## Error Handling

- Articles that fail to fetch are skipped with a message
- Articles that Claude cannot parse as funding rounds are skipped
- Articles before 2020 are skipped by the backfill scraper
- Duplicates are detected and skipped (based on source URL)
