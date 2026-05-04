# Audi A5 Avant — Demo Petrol Tracker

Streamlit app that automatically scrapes [audi.com.au](https://www.audi.com.au/en/audi-used-car-search/) for **A5 Avant petrol demo listings** near Melbourne, tracks prices over time, and shows a live dashboard.

## How it works

1. Uses **Playwright** (real Chromium browser) to load the Audi AU used car search page — handles JavaScript-rendered content
2. Intercepts the JSON API calls the SPA makes to find listing data
3. Falls back to DOM scraping if the API structure changes
4. Stores every snapshot in **SQLite** so you can track price changes over time
5. Shows a **Streamlit dashboard** with price charts, listing cards, and history

---

## Deploy options

### Option A — Streamlit Cloud (free, easiest)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → "New app"
3. Connect your GitHub repo, set `app.py` as the entry point
4. Streamlit Cloud will auto-run `packages.txt` (system deps) and `requirements.txt`
5. Add this to `.streamlit/config.toml` if not already there:

> **Note:** After first deploy, run `setup.sh` once via the Streamlit Cloud terminal to install Playwright's Chromium binary:
> ```
> playwright install chromium
> ```
> Or add a `postinstall` step — see below.

#### Auto-install Chromium on Streamlit Cloud

Create a file called `setup.sh` in your repo root (already included). Streamlit Cloud runs this automatically if present.

---

### Option B — Railway (free tier, Docker, recommended for reliability)

1. Push repo to GitHub
2. Go to [railway.app](https://railway.app) → "New Project" → "Deploy from GitHub"
3. Railway detects the `Dockerfile` automatically
4. Set env var `PORT=8501` if needed
5. Done — Railway builds the Docker image with Chromium included

---

### Option C — Render (free tier)

1. Push repo to GitHub  
2. Go to [render.com](https://render.com) → "New Web Service"
3. Choose "Docker" environment
4. Render builds from the `Dockerfile`

---

## Run locally

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run
streamlit run app.py
```

---

## Scheduling automatic refreshes

The app currently scrapes on-demand (click "Refresh listings now"). To run on a schedule:

### On Railway / Render
Add a cron job that calls the Streamlit app's `/run-scrape` endpoint, or use Railway's built-in cron to run a separate Python script:

```python
# cron_scrape.py — run separately on a schedule
from scraper import scrape_listings
from database import init_db, save_listings

init_db()
listings = scrape_listings()
save_listings(listings)
print(f"Saved {len(listings)} listings")
```

### With GitHub Actions (free)
Create `.github/workflows/scrape.yml`:

```yaml
name: Daily scrape
on:
  schedule:
    - cron: '0 8 * * *'   # 8am UTC = 6pm AEST
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: playwright install chromium
      - run: playwright install-deps chromium
      - run: python cron_scrape.py
      - uses: actions/upload-artifact@v4
        with:
          name: listings-db
          path: data/listings.db
```

---

## File structure

```
audi_tracker/
├── app.py              # Streamlit dashboard
├── scraper.py          # Playwright scraper for audi.com.au
├── database.py         # SQLite persistence layer
├── requirements.txt    # Python deps
├── packages.txt        # System deps (Streamlit Cloud)
├── setup.sh            # Post-install Playwright browser setup
├── Dockerfile          # For Railway / Render / Docker
├── .streamlit/
│   └── config.toml     # Dark theme config
└── data/
    └── listings.db     # SQLite DB (auto-created, gitignore this)
```

## .gitignore

```
data/
__pycache__/
*.pyc
.env
```
