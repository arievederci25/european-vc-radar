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

Currency conversion when amount is not in EUR:
- USD × 0.92 → EUR
- GBP × 1.17 → EUR
- CHF × 1.025 → EUR
- CZK ÷ 25 → EUR

---

### Step 1 — Research recent deals

Work through the sources below **in tier order**. Tier 1 sources are mandatory — fetch every one. Tier 2 and 3 sources should be fetched where accessible; skip individual pages only if they return a persistent 403/404 after one retry.

For each deal found, collect:

| Field | Description |
|---|---|
| `company` | Name of the startup that received funding |
| `country` | Country where the startup is headquartered |
| `stage` | One of: `Seed`, `Series A`, `Series B`, `Series C`, `Series D`, `Growth`, `IPO` |
| `amount_eur` | Amount in **millions** of euros as decimal. NULL if undisclosed. |
| `sector` | One of: `FinTech`, `HealthTech`, `CleanTech`, `SaaS`, `DeepTech`, `Mobility`, `EdTech`, `PropTech`, `FoodTech`, `AI`, `Other` |
| `lead_investor` | Lead VC firm(s), comma-separated |
| `description` | One-sentence description of what the company does |
| `year` | Calendar year as integer |
| `quarter` | Quarter as integer 1–4 |
| `announced_date` | Date the round was announced/closed, as `YYYY-MM-DD`. Take it from the source article (publication date is a reliable proxy when no explicit date is given). **Mandatory — never leave NULL.** |
| `source_urls` | The URL(s) the deal was confirmed from, as a list. At least one is mandatory. |

---

#### ⚠️ Incomplete deal — enrich before skipping

If a deal found in any source is missing one or more key fields (amount, country, stage, date), **do not skip it**. Instead, enrich it:

1. Run `WebSearch`: `"[company name] funding [year]"` or `"[company name] raises [amount]"`
2. Fetch the most promising result — the company's own press release, tech.eu, sifted.eu, eu-startups.com, or TechCrunch are the best secondary sources.
3. Fill in any fields you can confirm from those sources.
4. Only set `amount_eur = NULL` if the amount is genuinely undisclosed after searching.
5. Only skip a deal entirely if you cannot confirm it is European **and** cannot confirm the stage after searching.

This enrichment step applies to **every tier** of sources.

---

#### Tier 1 — Primary news aggregators (MANDATORY — fetch all)

These are high-yield discovery sources. Fetch each URL, extract all deals from the last 30 days, and enrich any incomplete ones.

- https://siliconcanals.com/
- **tech.eu** — *do NOT rely on `https://tech.eu/category/news/` or clicking "More" on it.* That page has a known caching bug and can serve stale content from years ago even after paginating. Instead:
  1. `WebSearch` for `tech.eu "European tech weekly recap" [month] [year]` to find that month's weekly recap articles (published most Mondays, URL pattern `tech.eu/YYYY/MM/DD/european-tech-weekly-recap-...`). There are ~4-5 per month, each covering the prior Mon-Sun week.
  2. `WebFetch` each recap URL with a prompt like *"List every individual funding deal mentioned (company, country, amount, stage, lead investors, description, date). Include ALL companies, not just top ones. List exits/M&A separately."* — each recap lists 50-75+ deals in one fetch, far more efficient than paging the news feed article-by-article.
  3. If a recap URL 404s from search results (e.g. published too recently to be indexed), get the exact slug from the tech.eu homepage: `find` the article link by its title, then `read_page` with that `ref_id` to read its `href` (don't just click it — clicking has been unreliable for navigating to fresh homepage links).
  4. tech.eu also publishes a monthly summary article ("[X] deals, [trend]: European startup funding in [month] [year]") — it's aggregate stats only (total deals, biggest deal, top sector/country), not a per-company list, so it's useful only as a sanity check on total deal count, not for extraction.
  5. Watch for: pure debt/credit facilities (exclude per the debt-only rule below), and strategic minority-stake purchases into already-mature companies (e.g. a state fund buying a small stake in an existing unicorn) — these aren't startup fundraises and should be excluded even if tech.eu covers them.
- https://sifted.eu
- https://eu-startups.com
- https://vestbee.com/insights/articles/ *(fetch the most recent monthly CEE article, e.g. `top-european-funding-rounds-closed-in-[month]-[year]`)*
- https://www.techfundingnews.com
- https://mtsprout.nl/groei/financiering
- https://www.seedtable.com/recently-funded-startups
- TechCrunch Europe tag: `https://techcrunch.com/tag/europe/`

---

#### Tier 2 — Advisor & law firm deal pages (fetch all — scan for last 30 days)

These pages list transactions the firm advised on. Fetch each and extract any European VC deals from the last 30 days. If a deal is missing fields, enrich via WebSearch.

- https://www.gpbullhound.com/deals/
- https://www.ingenhousz.com/projects
- https://www.akd.eu/cases
- https://improvedcf.com/deals/
- https://venturelawyers.nl/deals/
- https://vectrix.nl/venture-capital/venture-capital-deals/
- https://www.taylorwessing.com/en/insights-and-events/news/media-centre
- https://www.armapartners.com/deals/
- https://www.raiserspartners.com/transactions
- https://www.orrick.com/en/News
- https://www.goodwinlaw.com/en/news-and-events
- https://www.eversheds-sutherland.com/en/italy/about/news
- https://www.cooley.com/news/search-media
- https://www.drakestar.com/our-work
- https://www.mountsideventures.com/deals
- https://www.silverpeakib.com/track-record/
- https://www.firstcapital.co.uk/deals/
- https://www.loyensloeff.com/
- https://viottalaw.com/en/our-cases/
- https://finnius.com/
- https://www.vandoorne.com/
- https://www.ypog.law/
- https://www.pplaw.com/en
- https://www.dlapiper.com/
- https://www.pavia-ansaldo.it/en/
- https://www.cuatrecasas.com/
- https://lexcrea.com/
- https://www.vriman.nl/
- https://mena.nl/
- https://www.goldfish.global/news
- https://peak.capital/
- https://newion.com/news/

---

#### Tier 3 — VC firm portfolio & news pages (fetch all — scan for recent portfolio announcements)

These pages typically list portfolio companies or press releases. Fetch each and check for funding announcements from the last 30 days. If a deal is listed but incomplete, enrich via WebSearch before deciding to include or skip.

**Pan-European generalist funds:**
- https://www.indexventures.com/
- https://www.balderton.com/
- https://atomico.com/
- https://seedcamp.com/
- https://www.speedinvest.com/
- https://www.phoenixcourt.vc/localglobe
- https://cherry.vc/
- https://eightroads.com/en/
- https://creandum.com/
- https://northzone.com/
- https://earlybird.com/
- https://dawncapital.com/
- https://lakestar.com/
- https://www.accel.com/
- https://lsvp.com/global-presence/lightspeed-europe/
- https://www.generalcatalyst.com/
- https://www.battery.com/
- https://psgequity.com/
- https://eqtgroup.com/
- https://partechpartners.com/
- https://www.elaia.com/
- https://www.notioncapital.com/
- https://www.ventechvc.com/
- https://www.moltenventures.com/
- https://www.forward.one/
- https://rubio.vc/
- https://octopusventures.com/
- https://www.83north.com/
- https://augmentum.vc/
- https://felixcap.com/
- https://omersventures.com/
- https://rtp.vc/
- https://blossomcap.com/
- https://www.fuel.ventures/
- https://www.ascension.vc/
- https://mangrove.vc/
- https://anthemis.com/
- http://runacap.com/
- https://flashpointvc.com/

**Impact & CleanTech funds:**
- https://www.energyimpactpartners.com/
- https://setventures.com/
- https://moveenergy.vc/
- https://2150.vc/
- https://climentum.com/
- https://systemiq.earth/
- https://astanor.com/
- https://forbion.com/
- https://paleblue.vc/
- https://katapult.vc/
- https://repair-impact-fund.com/
- https://www.mirova.com/en/
- https://blueimpact.io/

**Netherlands & Belgium:**
- https://www.bom.nl/
- https://oostnl.nl/
- https://horizonflevoland.nl/
- https://www.innovationquarter.nl/
- https://rominwest.nl/
- https://www.invest-nl.nl/nl
- https://www.4impact.vc/
- https://www.pitchdrive.com/
- https://shapingimpact.vc/
- https://www.pmv.eu/
- https://gimv.com/
- https://eitfood.eu/
- https://blackfin-tech.com/
- https://ninepointfive.vc/
- https://solvay-ventures.com/
- https://nomainvest.eu/
- https://imecxpand.com/en/
- https://finindus.be/
- https://telosimpact.com/
- https://freshmenfund.com/
- https://keenventurepartners.com/
- https://henq.vc/
- https://revo.vc/
- https://proptech1.ventures/
- https://inkef.com/
- https://innoenergy.com/
- https://www.volta.ventures/
- https://www.curiosityvc.com/
- http://www.deeptechxl.com/
- https://www.innovationindustries.com/
- https://lumolabs.io/
- https://rockstart.com/
- https://volve.capital/
- https://arches.capital/
- https://borskifund.com/

**France:**
- https://www.bpifrance.com/
- https://heartcore.com/
- https://alven.co/
- https://kimaventures.com/
- https://eurazeo.com/
- https://daphni.com/
- https://hiinov.com/
- https://revaia.com/
- https://sofinnovapartners.com/
- https://caphorn.vc/
- https://breega.com/
- https://oneragtime.com/
- https://impact-partenaires.fr/
- https://rive-investment.com/
- https://fomcap.com/

**Germany & DACH:**
- https://www.htgf.de/
- https://lafamiglia.vc/
- https://10x.group/
- https://uniqaventures.com/
- https://calmstorm.vc/
- https://push.ventures/
- https://breeze-invest.at/
- https://dvhventures.de/
- https://xista.vc/
- https://gateway.ventures/
- https://nextechinvest.com/
- https://fly.vc/
- https://climbventures.com/
- https://forestay.vc/
- https://mountain.partners/
- https://www.redalpine.com/
- https://www.b2venture.vc/
- https://alstin.capital/
- https://www.project-a.vc/
- https://www.astutia.de/
- https://nap.vc/
- https://esg.de/
- https://baybg-vc.de/
- https://mig.ag/
- https://actoncapital.com/
- https://twip.de/
- https://senovo.vc/
- https://rocket.capital/
- https://www.riverside.ac/

**Nordics:**
- https://lifelineventures.com/
- https://openocean.vc/
- https://finnvera.fi/
- https://playventures.vc/
- https://maki.vc/
- https://sisu.vc/
- https://superherocapital.com/
- https://voimaventures.com/
- https://allianceventure.com/
- https://nordicmakers.vc/
- https://sno.vc/
- https://arcternventures.com/
- https://statkraftventures.com/
- https://nfrontventures.com/
- https://investinor.no/
- https://norselab.com/
- https://skyfall.vc/
- https://momentumpartners.no/
- https://linkcapital.no/
- https://concentric.vc/
- https://northcap.vc/
- https://north-eastventure.com/
- https://kompas.vc/
- https://seedcapital.dk/
- https://byfounders.vc/
- https://preseedventures.dk/
- https://soundbioventures.com/
- https://bii.dk/
- https://egp.fi/
- https://sparkmind.vc/
- https://nexitventures.com/
- https://pauliggroup.com/
- https://vnv.global/
- https://vef.vc/
- https://healthcap.eu/
- https://industrifonden.com/
- https://kinnevik.com/

**Spain & Portugal:**
- https://www.kiboventures.com/
- https://kfund.vc/
- https://jme.vc/
- https://creas.es/
- https://bonsaipartners.eu/
- https://invivoventures.es/
- https://samaipata.vc/
- https://myelin.vc/
- https://seayaventures.com/
- https://idcventures.com/
- https://aldea.ventures/
- https://mundiventures.com/
- https://nina.capital/
- https://primamateria.com/
- https://hcapital.pt/
- https://bigstart.vc/
- https://bynd.vc/
- https://armilar.com/
- https://portugalventures.pt/
- https://brpx.com/
- https://bionovacapital.com/
- https://risingventures.pt/

**Italy:**
- https://unicreditgroup.eu/
- https://proximitycapital.it/
- https://fondoitaliano.it/
- https://panakes.it/
- https://indacosgr.com/
- https://nevasgr.com/
- https://dpixel.it/
- https://360cap.vc/
- https://p101.it/
- https://unitedventures.com/
- https://e-novia.it/
- https://growthengine.it/
- https://fabric.vc/
- https://aicapital.ai/

**CEE (Central & Eastern Europe):**
- https://innovationnest.co/
- https://inovo.vc/
- https://blackpearls.vc/
- https://4growthvc.pl/
- https://pracuj.vc/
- https://kh.vc/
- https://shape.vc/
- https://movenscapital.com/
- https://eecventures.com/
- https://kogito-ventures.com/
- https://nextroad.vc/
- https://fundingbox.vc/
- https://33nventures.com/
- https://explorerinvestments.com/
- https://msm.vc/
- https://indicocapital.com/
- https://bluecrowcapital.com/
- https://targetglobal.vc/
- https://corvus.vc/
- https://ariafund.com/
- https://simpact.vc/
- https://flashpointvc.com/
- https://expeditionsfund.com/
- https://ffvc.com/

**Other European & global with European focus:**
- https://www.hvcapital.com/
- https://www.smedvig.com/
- https://www.fortino.capital/
- https://www.bluewirecapital.com/
- https://www.nautacapital.com/
- https://connyandco.com/
- https://www.dcvc.com/
- https://www.ringcp.com/
- https://prosus.com/
- https://finchcapital.com/
- https://pitoncap.com/
- https://fomcap.com/
- https://redline-capital.com/
- https://cogitocapital.com/
- https://middlegamevc.com/
- https://satgana.com/
- https://droiaventures.com/
- https://altervp.com/
- https://adara.vc/
- https://futureindustry.vc/
- https://hiro.capital/
- https://agritechhub.com/
- https://signatureventures.com/
- https://hitachi-ventures.com/
- https://sannocapital.com/
- https://praeturaventures.com/
- https://lightstonevc.com/
- https://seroba-lifesciences.com/
- https://actventure.capital/
- https://elkstonepartners.com/
- https://dbicventures.ie/
- https://deltapartners.com/
- http://www.giant.vc/
- https://identity.vc/
- https://futuristic.vc/
- https://scalecapital.com/
- https://latitudeventures.vc/
- https://taliscapital.com/
- https://www.hummingbird.vc/
- https://innovationfund.eu/
- https://mediahuis.com/
- https://joinef.com/
- https://public.io/
- https://finleap.com/
- https://visionfund.com/
- https://gv.com/
- http://bvp.com/
- https://www.nea.com/
- http://sequoiacap.com/
- https://indipartners.com/
- https://active-vp.com/
- https://rventures.co/
- https://nordicninja.vc/
- https://flatcapital.com/
- https://universitybridge fund.com/
- https://edenventures.co.uk/
- https://clarisventures.com/
- https://alchimiainvestments.com/
- https://alfabeat.com/
- https://adepa.com/
- https://basinghallpartners.com/
- https://digital.space/
- https://sghcapital.com/
- https://hthvc.com/

---

### Step 2 — Check for duplicates

```sql
SELECT company, year, quarter, amount_eur FROM deals WHERE year = {year} AND quarter = {quarter};
```

Skip companies already present for the same year+quarter.

**Fuzzy name rule:** If a similar name exists (e.g. "Aikido" vs "Aikido Security") with matching amount and country, treat as duplicate — keep the fuller name.

**Cross-quarter rule:** If a company appears in the previous quarter with an amount within ~20%, treat it as the same deal (announced vs closed timing). Keep the earlier entry — **unless** the earlier entry has `source_urls IS NULL` or its description reads like a rumor/target ("seeking", "in talks", "targeting a valuation of") while the newer one is a properly sourced close. In that case the earlier row is a rumor artifact, not a real duplicate to preserve: delete it and keep the sourced one, even if the amounts differ by more than 20% (rumored targets vs. actual close size often diverge a lot — e.g. NEURA Robotics was logged in Q1 as "seeking €4B valuation" at €1000M with no source, then actually closed in Q2 at €1288M/$1.4B with a full investor list; the Q1 row was deleted).

```sql
SELECT id, company, year, quarter, amount_eur, source_urls, description FROM deals
WHERE company ILIKE '%{first_word}%'
  AND ((year = {year} AND quarter IN ({quarter}, {quarter}-1))
    OR (year = {year}-1 AND quarter = 4 AND {quarter} = 1));
```

---

### Step 3 — Insert new deals

```sql
INSERT INTO deals (company, country, stage, amount_eur, sector, lead_investor, description, year, quarter, announced_date, source_urls, amount_display)
VALUES (..., '2026-05-19', ARRAY['https://tech.eu/...'], '€65.5M');
```

`amount_eur` must be in millions. `announced_date` is a `YYYY-MM-DD` date and `source_urls` is a Postgres text array (`ARRAY['url1','url2']`) — **both are required on every row, never insert without them.**

**`amount_display` — always set this explicitly, on every row, it does not auto-generate:**
- Below €1000M: `'€' + amount_eur rounded to 1 decimal + 'M'`, trailing `.0` stripped (e.g. `65.5` → `'€65.5M'`, `120.0` → `'€120M'`).
- €1000M and above: convert to billions, 1 decimal, trailing `.0` stripped, unit `'B'` (e.g. `1288` → `'€1.3B'`, `1000` → `'€1B'`, `2000` → `'€2B'`). Never leave a ≥€1000M deal displaying as `'€XXXXM'` — the site shows `amount_display` verbatim if set, so a missing or wrong value here is what caused deals like NEURA Robotics to render as "1288M" instead of "1.3B".

Use `ON CONFLICT (company, year, quarter) DO NOTHING`. Insert in batches. Log count inserted.

---

### Step 4 — Report

- How many deals found, skipped (duplicates), inserted
- List inserted companies with amount and country

**Post-insert integrity check** — run this and confirm it returns `0`. If not, backfill the offending rows before continuing:
```sql
SELECT count(*) FROM deals WHERE year = {year} AND quarter = {quarter} AND (announced_date IS NULL OR source_urls IS NULL);
```

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
SELECT company, country, sector, stage, amount_eur FROM deals WHERE year = {year} AND quarter = {quarter} ORDER BY amount_eur DESC NULLS LAST LIMIT 5;
```

Compute:
- `TOTAL_CAPITAL`: format total_capital_eur → "€3.9B" (B if ≥1000, else "€61.8M")
- `AVG_ROUND`: total_capital_eur / total_deals formatted same way
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

### Step 5b — Auto-export infographic to PDF (best-effort via Chrome)

The HTML file already has a built-in "Download als PDF" button (html2canvas + jsPDF) that renders a pixel-perfect PDF the moment a human clicks it in a real browser — that stays the reliable fallback if the automated export below doesn't work this run.

To also produce an actual `.pdf` file automatically, without waiting for a click:

1. Load the Chrome tools if not already available: `ToolSearch` with `select:mcp__claude-in-chrome__list_connected_browsers,mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool`.
2. Call `list_connected_browsers`. If none is connected, **skip this step entirely** — note "PDF auto-export skipped (no Chrome connected this run)" in the Step 4 report and move on to Step 6. Do not block or retry.
3. If connected: `tabs_context_mcp` (createIfEmpty: true) → `tabs_create_mcp` a new tab → `navigate` to `file:///C:/Users/ab/Desktop/.claude/european-vc-radar/infographic-q{quarter}-{year}.html`.
4. Wait ~2s for the Google Font and scripts to load, then call `javascript_tool` to run `generatePDF()` directly on the page (more reliable than pixel-clicking the button). Poll every second for up to 15s until the button's text reverts to "Download als PDF" — that means the export finished and the browser started the download.
5. The browser saves `vc-radar-q{quarter}-{year}.pdf` to the default Downloads folder (typically `C:\Users\ab\Downloads\`). Locate that file and copy it into the project folder as `C:\Users\ab\Desktop\.claude\european-vc-radar\infographic-q{quarter}-{year}.pdf`.
6. If any part of this fails (browser error, download not found within ~20s, etc.), don't block the task — note the failure in the Step 4 report and rely on the in-page button as fallback. Close the tab either way when done.

---

### Step 6 — Refresh the website snapshot (deals.json)

After all inserts are done, rebuild the static snapshot the site serves so the new deals appear immediately on www.vcradar.nl. This runs in the same job as the scrape, so the data and the snapshot stay in sync. (This replaces the old standalone Silicon Canals scraper.)

From the repo root `C:\Users\ab\Desktop\.claude\european-vc-radar`:

1. Run the export script with the anon key in the environment:
   - PowerShell: `$env:SUPABASE_KEY="<anon key above>"; python scrapers/export_deals_json.py`
   - REST **reads** work fine here — the "REST API is blocked" note above only applies to the DB writes (inserts), which go via the Supabase MCP. The read-only export uses the public anon key.
2. Commit and push the refreshed file:
   ```
   git add data/deals.json
   git commit -m "Auto: refresh data/deals.json after monthly scrape"
   git push
   ```
3. If there is nothing to commit, or the push fails, do not block on it — the GitHub Actions workflow **Rebuild deals.json snapshot** runs on the 2nd of the month as a cloud safety net.

---

### Constraints
- Only European companies (EU + UK + Norway + Switzerland + Israel etc.)
- Exclude deals below €500K (amount_eur < 0.5) — skip immediately, do not spend time researching them
- Only include verifiable deals from named sources
- Debt-only rounds (no equity component) should not be included
- If stage is unclear after WebSearch enrichment, use `Growth` for large rounds (>€50M) or `Seed` for early undetermined rounds
