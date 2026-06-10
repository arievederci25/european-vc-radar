## European VC Radar — Monthly Data Refresh + Infographic

**Objective:** Research European VC funding deals closed in the last 30 days, insert them into Supabase, and generate a monthly infographic HTML file.

---

### Supabase connection
- **URL:** `https://swhjffkhhwktrvwiqmoe.supabase.co`
- **Anon key:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN3aGpmZmtoaHdrdHJ2d2lxbW9lIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyMTY5NDYsImV4cCI6MjA5MDc5Mjk0Nn0.XjNLCy3Fahc9AlitTpLWMQFRFC8HXh3OVT5iaIeFrNE`
- **Table:** `deals`
- **Project ID:** `swhjffkhhwktrvwiqmoe`

Use the Supabase MCP tool (`execute_sql`) with project_id `swhjffkhhwktrvwiqmoe` for ALL database operations. Do NOT use the REST API — it is blocked.

---

### ⚠️ Critical: amount_eur unit convention
`amount_eur` is stored in **millions of euros** as a decimal — NOT in raw euros.
- €5M → store as `5.0`
- €65.5M → store as `65.5`
- €1.1B → store as `1100.0`
- NULL if undisclosed

Do NOT store raw euro amounts (e.g. do NOT store 5000000 for €5M).

---

### Step 1 — Research recent deals

Search ALL of the following sources for European VC funding rounds announced in the last 30 days:
- https://eu-startups.com
- https://tech.eu
- https://sifted.eu
- https://vestbee.com
- TechCrunch (Europe tag)
- Crunchbase (filter: Europe, last 30 days)
- https://www.gpbullhound.com/deals/
- https://www.ingenhousz.com/projects
- https://www.akd.eu/cases
- https://mena.nl/
- https://www.goldfish.global/news
- https://improvedcf.com/deals/
- https://www.vriman.nl/
- https://peak.capital/
- https://newion.com/news/
- https://venturelawyers.nl/deals/
- https://www.taylorwessing.com/en/insights-and-events/news/media-centre
- https://vectrix.nl/venture-capital/venture-capital-deals/
- https://mtsprout.nl/groei/financiering
- https://siliconcanals.com/
- X (Filter: Funding, Seed, Series A, Series B, Europe, last 30 days)
- https://www.armapartners.com/deals/
- https://www.raiserspartners.com/transactions
- https://www.seedtable.com/recently-funded-startups
- https://www.orrick.com/en/News
- https://www.goodwinlaw.com/en/news-and-events
- https://www.eversheds-sutherland.com/en/italy/about/news
- https://www.cooley.com/news/search-media
- https://www.drakestar.com/our-work
- https://www.mountsideventures.com/deals
- https://www.silverpeakib.com/track-record/
- https://www.firstcapital.co.uk/deals/
- https://www.techfundingnews.com

For each deal, extract:

| Field | Description |
|---|---|
| `company` | Name of the startup that received funding |
| `country` | Country where the startup is headquartered |
| `stage` | One of: `Seed`, `Series A`, `Series B`, `Series C`, `Series D`, `Growth` |
| `amount_eur` | Amount in **millions** of euros as decimal (e.g. `5.0` for €5M). NULL if undisclosed. |
| `amount_display` | Human-readable e.g. "€5M", "£12M", "$8M" |
| `sector` | One of: `FinTech`, `HealthTech`, `CleanTech`, `SaaS`, `DeepTech`, `Mobility`, `EdTech`, `PropTech`, `FoodTech`, `AI`, `Other` |
| `lead_investor` | Lead VC firm(s), comma-separated |
| `description` | One-sentence description |
| `year` | Calendar year as integer |
| `quarter` | Quarter as integer 1–4 |

---

### Step 2 — Check for duplicates

```sql
SELECT company, year, quarter FROM deals WHERE year = {year} AND quarter = {quarter};
```
Skip companies already present for the same year+quarter.

---

### Step 3 — Insert new deals

```sql
INSERT INTO deals (company, country, stage, amount_eur, amount_display, sector, lead_investor, description, year, quarter)
VALUES (...);
```
`amount_eur` must be in millions. Insert in batches. Log count.

---

### Step 4 — Report

- How many deals found, skipped (duplicates), inserted
- List inserted companies with amount and country

---

### Step 5 — Generate monthly infographic

Run these SQL queries for the current year+quarter:

**Totals:**
```sql
SELECT COUNT(*) as total_deals, ROUND(SUM(amount_eur)::numeric,1) as total_capital_eur, COUNT(DISTINCT country) as countries_count FROM deals WHERE year = {year} AND quarter = {quarter};
```

**Top 5 sectors by deal count:**
```sql
SELECT sector, COUNT(*) as deal_count, ROUND(SUM(amount_eur)::numeric,1) as total_eur FROM deals WHERE year = {year} AND quarter = {quarter} GROUP BY sector ORDER BY deal_count DESC LIMIT 5;
```

**Top 5 countries:**
```sql
SELECT country, COUNT(*) as deal_count FROM deals WHERE year = {year} AND quarter = {quarter} GROUP BY country ORDER BY deal_count DESC LIMIT 5;
```

**Stage breakdown:**
```sql
SELECT stage, COUNT(*) as deal_count FROM deals WHERE year = {year} AND quarter = {quarter} GROUP BY stage ORDER BY CASE stage WHEN 'Seed' THEN 1 WHEN 'Series A' THEN 2 WHEN 'Series B' THEN 3 WHEN 'Series C' THEN 4 WHEN 'Series D' THEN 5 ELSE 6 END;
```

**Top 5 biggest deals:**
```sql
SELECT company, country, sector, stage, amount_eur, amount_display FROM deals WHERE year = {year} AND quarter = {quarter} ORDER BY amount_eur DESC NULLS LAST LIMIT 5;
```

Compute:
- `TOTAL_CAPITAL`: format total_capital_eur → "€3.9B" (B if ≥1000, else M)
- `AVG_ROUND`: total_capital_eur / total_deals formatted as "€61.8M"
- `QUARTER_LABEL`: e.g. "Q2 · April 2026"
- `MONTH_YEAR`: e.g. "April 2026"
- Sector bar widths: top sector = 100%, others relative
- Stage bar widths: largest stage = 100%, others relative
- Stage pill/bar CSS classes: Seed→pill-seed/bar-seed, Series A→pill-a/bar-a, Series B→pill-b/bar-b, Series C→pill-c/bar-c, Series D→pill-c/bar-c, Growth→pill-growth/bar-growth

Write 4 data-driven observations. Wrap key facts in `<strong>` tags. Examples:
- Most notable deal (biggest, or unusual stage/size)
- Which sector dominated capital and its % of total
- What % of deals were early-stage (Seed)
- Which country led and its % of total deals

Then write the complete HTML file to:
`C:\Users\ab\Desktop\.claude\european-vc-radar\infographic-q{quarter}-{year}.html`

Use this exact template, replacing all {{PLACEHOLDER}} values:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1200">
<title>European VC Radar — Q{{QUARTER}} {{YEAR}}</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { width: 1200px; min-height: 1200px; background: #faf8f4; font-family: 'Plus Jakarta Sans', sans-serif; color: #1a1805; display: flex; flex-direction: column; align-items: center; padding: 32px 0 48px; }
  .download-btn { display: flex; align-items: center; gap: 8px; background: #1a1805; color: #faf8f4; border: none; border-radius: 100px; font-family: 'Plus Jakarta Sans', sans-serif; font-size: 14px; font-weight: 700; padding: 12px 24px; cursor: pointer; margin-bottom: 24px; transition: background 0.15s; }
  .download-btn:hover { background: #e87461; }
  .download-btn.loading { opacity: 0.6; cursor: wait; }
  .canvas { width: 1200px; background: #faf8f4; display: flex; flex-direction: column; padding: 56px 60px 44px; border-radius: 24px; box-shadow: 0 8px 48px rgba(0,0,0,0.12); }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 36px; }
  .brand { display: flex; align-items: center; gap: 12px; }
  .brand svg { width: 38px; height: 37px; flex-shrink: 0; }
  .brand-text { display: flex; flex-direction: column; line-height: 1.1; }
  .brand-name { font-size: 17px; font-weight: 700; color: #1a1805; letter-spacing: -0.3px; }
  .brand-sub { font-size: 12px; font-weight: 500; color: #888070; letter-spacing: 0.5px; text-transform: uppercase; }
  .period-pill { background: #e87461; color: #fff; font-size: 13px; font-weight: 700; padding: 6px 16px; border-radius: 100px; }
  .headline { margin-bottom: 20px; }
  .headline h1 { font-size: 52px; font-weight: 800; color: #1a1805; line-height: 1.0; letter-spacing: -1.8px; }
  .headline h1 span { color: #e87461; }
  .headline p { font-size: 16px; font-weight: 500; color: #888070; margin-top: 10px; }
  .observations { background: #1a1805; border-radius: 20px; padding: 22px 28px; margin-bottom: 20px; }
  .observations .panel-label { color: rgba(250,248,244,0.45); margin-bottom: 12px; }
  .obs-list { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 32px; }
  .obs-item { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; font-weight: 500; color: rgba(250,248,244,0.8); line-height: 1.5; }
  .obs-dot { width: 7px; height: 7px; background: #e87461; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
  .obs-item strong { color: #faf8f4; font-weight: 700; }
  .hero-stats { display: flex; gap: 16px; margin-bottom: 20px; }
  .stat-card { flex: 1; background: #1a1805; border-radius: 20px; padding: 22px 28px; color: #faf8f4; }
  .stat-card.coral { background: #e87461; }
  .stat-value { font-size: 38px; font-weight: 800; letter-spacing: -1.5px; line-height: 1; margin-bottom: 6px; }
  .stat-label { font-size: 12px; font-weight: 600; opacity: 0.7; letter-spacing: 0.5px; text-transform: uppercase; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .panel { background: #fff; border-radius: 20px; padding: 22px; border: 1px solid rgba(26,24,5,0.07); }
  .panel.span2 { grid-column: span 2; }
  .panel-label { font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: #aaa090; margin-bottom: 14px; }
  .sector-row { display: flex; align-items: center; gap: 10px; margin-bottom: 11px; }
  .sector-row:last-child { margin-bottom: 0; }
  .sector-name { font-size: 13px; font-weight: 600; color: #1a1805; width: 80px; flex-shrink: 0; }
  .sector-bar-wrap { flex: 1; height: 8px; background: rgba(26,24,5,0.08); border-radius: 99px; overflow: hidden; }
  .sector-bar { height: 100%; background: #e87461; border-radius: 99px; }
  .sector-count { font-size: 12px; font-weight: 700; color: #1a1805; width: 28px; text-align: right; flex-shrink: 0; }
  .country-row { display: flex; align-items: center; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid rgba(26,24,5,0.06); }
  .country-row:last-child { border-bottom: none; }
  .country-name { font-size: 13px; font-weight: 600; color: #1a1805; }
  .country-badge { background: #faf8f4; border-radius: 100px; padding: 3px 10px; font-size: 12px; font-weight: 700; color: #888070; }
  .stage-grid { display: flex; flex-direction: column; gap: 9px; }
  .stage-row { display: flex; align-items: center; gap: 10px; }
  .stage-pill { font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 100px; width: 82px; text-align: center; flex-shrink: 0; }
  .pill-seed { background: #e8f5e9; color: #2e7d32; } .pill-a { background: #e3f2fd; color: #1565c0; } .pill-b { background: #fff3e0; color: #e65100; } .pill-c { background: #fce4ec; color: #c62828; } .pill-growth { background: #f3e5f5; color: #6a1b9a; }
  .stage-bar-wrap { flex: 1; height: 8px; background: rgba(26,24,5,0.08); border-radius: 99px; overflow: hidden; }
  .stage-bar { height: 100%; border-radius: 99px; }
  .bar-seed { background: #4caf50; } .bar-a { background: #2196f3; } .bar-b { background: #ff9800; } .bar-c { background: #f44336; } .bar-growth { background: #9c27b0; }
  .stage-num { font-size: 13px; font-weight: 700; color: #1a1805; width: 22px; text-align: right; flex-shrink: 0; }
  .deal-row { display: flex; align-items: flex-start; gap: 12px; padding: 9px 0; border-bottom: 1px solid rgba(26,24,5,0.06); }
  .deal-row:last-child { border-bottom: none; }
  .deal-rank { font-size: 11px; font-weight: 800; color: #e87461; width: 18px; flex-shrink: 0; margin-top: 2px; }
  .deal-info { flex: 1; }
  .deal-company { font-size: 13px; font-weight: 700; color: #1a1805; }
  .deal-meta { font-size: 11px; color: #aaa090; font-weight: 500; margin-top: 2px; }
  .deal-amount { font-size: 14px; font-weight: 800; color: #1a1805; flex-shrink: 0; }
  .footer { display: flex; align-items: center; justify-content: space-between; padding-top: 16px; border-top: 1px solid rgba(26,24,5,0.08); margin-top: 4px; gap: 24px; }
  .footer-disclaimer { font-size: 11px; font-weight: 500; color: #aaa090; line-height: 1.5; flex: 1; }
  .footer-logo { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .footer-logo svg { width: 22px; height: 21px; }
  .footer-logo span { font-size: 12px; font-weight: 700; color: #888070; }
</style>
</head>
<body>
<button class="download-btn" id="pdfBtn" onclick="generatePDF()">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
  Download als PDF
</button>
<div class="canvas" id="infographic">
  <div class="header">
    <div class="brand">
      <svg viewBox="0 0 51 49" fill="#1a1805" xmlns="http://www.w3.org/2000/svg"><path d="m30.388 34.796-9.8-9.8-9.8 9.8L1 25v19.592l9.8-9.8 9.8 9.8Z"/><path d="m49.981 15.204-9.8-9.8-9.8 9.8-9.8-9.8V25l9.8-9.8 9.8 9.8Z"/></svg>
      <div class="brand-text"><div class="brand-name">Goldfish</div><div class="brand-sub">VC Radar</div></div>
    </div>
    <div class="period-pill">{{QUARTER_LABEL}}</div>
  </div>
  <div class="headline">
    <h1>European VC <span>in numbers.</span></h1>
    <p>{{TOTAL_DEALS}} deals tracked across {{COUNTRIES_COUNT}} countries — {{MONTH_YEAR}} update</p>
  </div>
  <div class="observations">
    <div class="panel-label">Key observations</div>
    <div class="obs-list">
      <div class="obs-item"><div class="obs-dot"></div><div>{{OBS_1}}</div></div>
      <div class="obs-item"><div class="obs-dot"></div><div>{{OBS_2}}</div></div>
      <div class="obs-item"><div class="obs-dot"></div><div>{{OBS_3}}</div></div>
      <div class="obs-item"><div class="obs-dot"></div><div>{{OBS_4}}</div></div>
    </div>
  </div>
  <div class="hero-stats">
    <div class="stat-card coral"><div class="stat-value">{{TOTAL_CAPITAL}}</div><div class="stat-label">Capital deployed</div></div>
    <div class="stat-card"><div class="stat-value">{{TOTAL_DEALS}}</div><div class="stat-label">Deals tracked</div></div>
    <div class="stat-card"><div class="stat-value">{{COUNTRIES_COUNT}}</div><div class="stat-label">Countries</div></div>
    <div class="stat-card"><div class="stat-value">{{AVG_ROUND}}</div><div class="stat-label">Avg. round size</div></div>
  </div>
  <div class="grid">
    <div class="panel"><div class="panel-label">Top sectors · by deals</div>{{SECTOR_ROWS}}</div>
    <div class="panel"><div class="panel-label">Top countries · by deals</div>{{COUNTRY_ROWS}}</div>
    <div class="panel"><div class="panel-label">Stage breakdown</div><div class="stage-grid">{{STAGE_ROWS}}</div></div>
    <div class="panel span2"><div class="panel-label">Biggest deals this quarter</div>{{DEAL_ROWS}}</div>
  </div>
  <div class="footer">
    <div class="footer-disclaimer">Information sourced from publicly available sources and is not complete. Only deals above €500K are listed. Powered by Supabase. Built for Goldfish.</div>
    <div class="footer-logo">
      <svg viewBox="0 0 51 49" fill="#aaa090" xmlns="http://www.w3.org/2000/svg"><path d="m30.388 34.796-9.8-9.8-9.8 9.8L1 25v19.592l9.8-9.8 9.8 9.8Z"/><path d="m49.981 15.204-9.8-9.8-9.8 9.8-9.8-9.8V25l9.8-9.8 9.8 9.8Z"/></svg>
      <span>goldfish.global</span>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<script>
async function generatePDF() {
  const btn = document.getElementById('pdfBtn');
  btn.textContent = 'Bezig met genereren…';
  btn.classList.add('loading');
  btn.disabled = true;
  await new Promise(r => setTimeout(r, 100));
  const el = document.getElementById('infographic');
  const canvas = await html2canvas(el, { scale: 2, useCORS: true, backgroundColor: '#faf8f4', logging: false });
  const imgData = canvas.toDataURL('image/png');
  const { jsPDF } = window.jspdf;
  const pxW = canvas.width, pxH = canvas.height;
  const mmW = 297, mmH = Math.round((pxH / pxW) * mmW);
  const pdf = new jsPDF({ orientation: mmW >= mmH ? 'landscape' : 'portrait', unit: 'mm', format: [mmW, mmH] });
  pdf.addImage(imgData, 'PNG', 0, 0, mmW, mmH);
  pdf.save('vc-radar-q{{QUARTER}}-{{YEAR}}.pdf');
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download als PDF';
  btn.classList.remove('loading');
  btn.disabled = false;
}
</script>
</body>
</html>
```

---

### Step 6 — Refresh the website snapshot (deals.json)

After all inserts are done, rebuild the static snapshot the site serves so the new deals appear immediately on www.vcradar.nl. This runs in the same job as the scrape, so the data and the snapshot stay in sync. (This replaces the old standalone Silicon Canals scraper.)

From the repo root `C:\Users\ab\Desktop\.claude\european-vc-radar`:

1. Run the export script with the anon key in the environment:
   - PowerShell: `$env:SUPABASE_KEY="<anon key above>"; python scrapers/export_deals_json.py`
   - REST **reads** work fine — the read-only export uses the public anon key. (DB writes/inserts still go via the Supabase MCP.)
2. Commit and push the refreshed file:
   ```
   git add data/deals.json
   git commit -m "Auto: refresh data/deals.json after monthly scrape"
   git push
   ```
3. If there is nothing to commit, or the push fails, do not block on it — the GitHub Actions workflow **Rebuild deals.json snapshot** runs on the 2nd of the month as a cloud safety net.

---

### Constraints
- Only European companies (EU + UK + Norway + Switzerland etc.)
- Exclude deals below €500k (amount_eur < 0.5)
- If stage is unclear, use `n/a`
- Only include verifiable deals from named sources
- Search ALL listed sources
