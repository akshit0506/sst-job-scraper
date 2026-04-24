# SST Job Scraper

Scrapes tech jobs (internships + full-time) from Indian-relevant sources, enriches
them with Claude to infer compensation, filters by your thresholds, and appends
the survivors to a Google Sheet. Runs on a schedule via GitHub Actions.

## What it scrapes

| Source     | Type       | How                                                  |
|------------|------------|------------------------------------------------------|
| Greenhouse | ATS feed   | `boards-api.greenhouse.io/v1/boards/<slug>/jobs`     |
| Lever      | ATS feed   | `api.lever.co/v0/postings/<slug>`                    |
| Ashby      | ATS feed   | `api.ashbyhq.com/posting-api/job-board/<slug>`       |
| Workable   | ATS feed   | `apply.workable.com/api/v1/widget/accounts/<slug>`   |
| HN Who's Hiring | Aggregator | Algolia HN search + Firebase item API           |
| RemoteOK   | JSON feed  | `remoteok.com/api`                                   |
| Naukri     | Search API | `naukri.com/jobapi/v3/search` (fragile, may 429)     |
| Instahyre  | Search API | `instahyre.com/api/v1/job_search`                    |

Slack sink is stubbed — we'll wire it up next session.

## Filters (defined in `config/thresholds.yaml`)

- Internship stipend > ₹75,000/month
- Full-time CTC > ₹20,00,000/year
- India location (or remote roles that don't exclude India)
- Tech role (keyword-matched)

For jobs where comp isn't stated on the posting (most of them), Claude Haiku
estimates a band based on company tier, title, location, and description.

## Setup

### 1. Push to GitHub

```bash
cd sst-job-scraper
git init && git add . && git commit -m "initial scrape scaffold"
gh repo create sst-job-scraper --private --source=. --push
```

### 2. Create Google Sheet

1. New blank sheet → copy the ID from the URL
   (`docs.google.com/spreadsheets/d/THIS_PART/edit`)
2. Go to Google Cloud Console → create a project → enable **Sheets API** and **Drive API**
3. Create a service account → download JSON key
4. Share the sheet with the service account email (`...@...iam.gserviceaccount.com`),
   give it **Editor** access

### 3. Get Claude API key

Go to [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
and create a key. Expected cost: ~$0.50–$2/day at 6-hour run cadence with
current volume (Haiku is cheap).

### 4. Add GitHub secrets

In the repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret                          | Value                                      |
|---------------------------------|--------------------------------------------|
| `ANTHROPIC_API_KEY`             | Your Claude API key                        |
| `GSHEET_ID`                     | The sheet ID from step 2                   |
| `GOOGLE_SERVICE_ACCOUNT_JSON`   | Full contents of the JSON key file         |

### 5. Trigger the first run

GitHub → Actions tab → "Scrape jobs" → "Run workflow". Check the sheet after
~3 minutes.

## Local dev

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in your keys
python -m src.main --dry-run --no-enrich --sources greenhouse --limit 20
```

Recommended first run without enrichment to verify scraping works, then enable
enrichment.

## Adding a new company

Edit `config/companies.yaml`. For Greenhouse/Lever/Ashby/Workable, you need the
company's ATS slug. Heuristic: go to the company's "Careers" page, click a
listing, look at the URL —

- `boards.greenhouse.io/<slug>/jobs/123`
- `jobs.lever.co/<slug>/...`
- `jobs.ashbyhq.com/<slug>/...`
- `apply.workable.com/<slug>/...`

Then run `python scripts/verify_slugs.py` to confirm the slug resolves.

## Adding a new source

1. Drop `src/sources/mynewsite.py` implementing `fetch() -> Iterable[Job]`
2. Register it in `src/main.py` under `build_sources`
3. Add its key to the `--sources` default

Each source's `safe_fetch()` swallows exceptions, so a broken new adapter
won't kill the pipeline.

## Known limitations (honest list)

- **LinkedIn is NOT included.** Their ToS forbids scraping, they block aggressively,
  and for an institution scraping from their infrastructure is a legal liability.
- **Naukri is fragile.** When they rotate anti-bot measures, the adapter will 
  return 0 rows for a while. It won't crash — but you'll see a gap.
- **Comp inference is a best-effort estimate.** Filter with confidence ≥ `medium`
  by default. For any job about to be shared with students, a human should verify
  the comp band (your CRM workflow already does this).
- **HFT firms don't use public ATS feeds.** Coverage comes from Naukri + HN +
  adding their careers pages as individual scrapers later.
