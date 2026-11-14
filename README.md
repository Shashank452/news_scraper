# Indian Equities News Scraper & Aggregator

A high-performance, modular Python system designed to scrape real-time corporate announcements and filings from Indian stock exchanges (**BSE** and **NSE**). 

The module aggregates, deduplicates, and structures corporate news, storing disclosures in a database with automatic retention management and exposing clean REST API endpoints for external downstream consumers (such as sentiment analysis engines, MCP servers, and trading strategies).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 News Scraper System (Python)                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌───────────────┐               ┌───────────────┐         │
│   │  BSE Scraper  │               │  NSE Scraper  │         │
│   │(Announcements)│               │(Announcements)│         │
│   └───────┬───────┘               └───────┬───────┘         │
│           │                               │                 │
│           └───────────────┬───────────────┘                 │
│                           ▼                                 │
│                 ┌───────────────────┐                       │
│                 │  News Aggregator  │                       │
│                 │(Deduplication &   │                       │
│                 │ Category Labeler) │                       │
│                 └─────────┬─────────┘                       │
│                           ▼                                 │
│                 ┌───────────────────┐                       │
│                 │ PostgreSQL / DB   │                       │
│                 │(Nightly 90d Purge)│                       │
│                 └─────────┬─────────┘                       │
│                           ▼                                 │
│                 ┌───────────────────┐                       │
│                 │  FastAPI REST API │                       │
│                 │  & Exporter Layer │                       │
│                 └─────────┬─────────┘                       │
└───────────────────────────┼─────────────────────────────────┘
                            ▼
      ┌───────────────────────────────────────────┐
      │  Downstream Integration                   │
      │  (Sentiment Analysis, MCP Servers, etc.)  │
      └───────────────────────────────────────────┘
```

### Core Features

- **Primary Exchange Coverage**:
  - **BSE**: Scrapes corporate announcements and circulars with live attachment links (`bseindia.com`).
  - **NSE**: Scrapes corporate announcements with automated session handshake and cookie refresh (`nseindia.com`).
- **Deduplication Engine**:
  - Composite unique constraint on `(source, source_id)` ensures zero duplicate insertions across polling cycles.
- **Data Retention Policy**:
  - Permanently retains essential metadata: ticker, announcement title, source URL, and publication timestamps for backtesting and historical reference.
  - Automatically purges heavy description text bodies after 90 days (daily cron at 2:00 AM IST).
- **Market Hours Scheduler**:
  - Intelligent APScheduler service that polls every 1–2 minutes during market hours (09:00 – 15:30 IST, Mon–Fri) and backs off outside market hours.
- **FastAPI REST API**:
  - Secure querying by ticker, date, category, and source.
  - JSON and CSV direct data exports.

---

## Directory Structure

```
news_scraper/
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI/CD test runner & merge gate
├── aggregators/
│   ├── __init__.py
│   └── news_aggregator.py     # Aggregator coordinating scrapers & DB batching
├── api/
│   ├── __init__.py
│   └── news_api.py            # FastAPI endpoints, streaming cursors & web UI
├── docker/
│   └── docker-compose.yml     # Production PostgreSQL container
├── docs/
│   ├── architecture_plan.md   # Architectural design specification
│   ├── branch_protection_guide.md # Guide for enforcing tests before merging to main
│   └── roadmap_notes.md       # Trading vision & feature notes
├── exporters/
│   ├── __init__.py
│   └── news_exporter.py       # JSON & CSV export formatters
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py        # Base scraper class with rate-limiting & sessions
│   ├── bse_scraper.py         # BSE Corporate Announcements scraper
│   ├── nse_scraper.py         # NSE Corporate Announcements scraper with session warmup
│   ├── media_news_scraper.py  # Financial media RSS & search scraper
│   └── regulatory_policy_scraper.py # IRDAI, RBI, SEBI, and Ministry policy scraper
├── scripts/
│   ├── init_db.py             # Database creation script
│   ├── run_scrapers.py        # CLI tool to test scrapers directly
│   └── verify_all.py          # Pre-push automated syntax & test suite verifier
├── tests/
│   ├── conftest.py            # Reusable test fixtures & mock DB sessions
│   ├── test_aggregator.py     # Aggregator pipeline & fault tolerance tests
│   ├── test_api.py            # API endpoints & incremental cursor tests
│   ├── test_database.py       # Deduplication & 90-day retention purge tests
│   ├── test_exporter.py       # CSV & JSON export format tests
│   ├── test_model_and_utils.py # Categorization & validation tests
│   ├── test_run.py            # Master runner CLI configuration tests
│   ├── test_scheduler.py      # Background scheduler lifecycle tests
│   └── test_scrapers.py       # BSE, NSE, Media, Policy scraper tests
├── ui/
│   └── index.html             # Real-time Bloomberg-style news terminal UI
├── config.py                  # Pydantic-based configuration management
├── database.py                # SQLAlchemy ORM models, indexes & deduplication
├── news_model.py              # Pydantic schemas and auto-categorization
├── pytest.ini                 # Pytest configuration & warning suppression
├── requirements.txt           # Project dependencies
├── run.py                     # Master runner (starts server, 15m scheduler, cleanup)
├── scheduler.py               # APScheduler background runner
├── utils.py                   # Rate limiting, logger, and ticker sanitization
├── .env.example               # Environment variables template
└── .gitignore                 # Version control exclusions
```

---

## Setup & Installation

### 1. Prerequisites
- Python 3.11+
- Git

### 2. Virtual Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Environment Variables
Copy the `.env.example` file to `.env`:
```powershell
Copy-Item .env.example .env
```
Default configuration uses local SQLite (`sqlite:///./news.db`) for immediate out-of-the-box development.

For production with PostgreSQL:
```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres_password@localhost:5432/news_scraper
API_KEY=your_production_secret_key
```

### 4. Initialize Database
```powershell
python scripts/init_db.py
```

---

## Running the System

### 1. Recommended: Master Unified Runner (`run.py`)
Run all tasks simultaneously with a single command — starts the API server, schedules scrapers every 15 minutes, stores deduplicated announcements, and schedules daily retention cleanup:
```powershell
python run.py
```

CLI Options:
```powershell
python run.py --scrape-interval 15   # Change scrape interval in minutes (default 15)
python run.py --port 8000            # Specify custom port
python run.py --cleanup-now          # Execute duplicate sweep and retention purge on start
python run.py --no-server            # Run scheduler daemon only (worker mode)
python run.py --no-scheduler         # Run FastAPI REST server only
```

---

## Running Individual Components

### 1. Run Scrapers CLI (Ad-Hoc / Test Run)
Test fetching and deduplicating announcements without starting the background daemon:
```powershell
# Run all scrapers
python scripts/run_scrapers.py --source all

# Or run a specific exchange
python scripts/run_scrapers.py --source bse
python scripts/run_scrapers.py --source nse
```

### 2. Run the Background Scheduler
Starts APScheduler to continuously poll exchanges and run the nightly retention cleanup:
```powershell
python scheduler.py
```

### 3. Run the REST API Server
Start the FastAPI server:
```powershell
uvicorn api.news_api:app --host 127.0.0.1 --port 8000 --reload
```
If that command fails try the below one.
```powershell
.\.venv\Scripts\uvicorn api.news_api:app --host 127.0.0.1 --port 8000 --reload
```
Interactive Swagger documentation is available at: `http://127.0.0.1:8000/docs`

---

## REST API Reference

All protected endpoints require the `X-API-Key` header (defined in `.env`).

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Healthcheck for server & database (no auth required) |
| `GET` | `/news` | Query news with filters (`ticker`, `source`, `category`, `since`, `since_scraped`, `limit`, `offset`) |
| `GET` | `/news/incremental` | **Cursor-based incremental polling**: fetch news ingested strictly after `since_scraped` cursor for downstream applications |
| `GET` | `/news/checkpoint` | Get latest database watermark (`latest_scraped_at`, `last_id`, `total_news`) for starting sync |
| `GET` | `/news/{ticker}` | Retrieve latest announcements for a specific ticker (e.g. `/news/RELIANCE`) |
| `GET` | `/news/sources/{source}` | Retrieve announcements by source (`/news/sources/bse`, `/news/sources/nse`) |
| `GET` | `/news/export/file` | Download announcements as CSV or JSON (`?format=csv` or `?format=json`) |
| `POST` | `/news/trigger-scrape` | Trigger an on-demand scraping & deduplication cycle |

### Downstream Application Integration Example (Python)
Fetch news from where you left off:
```python
import requests

API_URL = "http://127.0.0.1:8000"
HEADERS = {"X-API-Key": "dev_secret_api_key_change_in_production"}

# 1. Get current checkpoint to start from right now (or pass None to fetch all)
checkpoint = requests.get(f"{API_URL}/news/checkpoint", headers=HEADERS).json()
cursor_time = checkpoint["latest_scraped_at"]
cursor_id = checkpoint["last_id"]

# 2. In your worker loop, fetch latest updates from where you left off:
params = {"since_scraped": cursor_time, "last_id": cursor_id, "limit": 100}
resp = requests.get(f"{API_URL}/news/incremental", headers=HEADERS, params=params).json()

for item in resp["items"]:
    print(f"[{item['ticker']}] {item['title']}")

# Update your local cursor with the new watermark returned
cursor_time = resp["cursor"]["since_scraped"]
cursor_id = resp["cursor"]["last_id"]
```

---

## Running Tests & CI/CD Verification

### 1. Run Complete Test Suite
Execute all 38 unit and integration tests with pytest:
```powershell
pytest
```

### 2. Pre-Push Verification Tool
Run full syntax compilation, index checks, and test runner before pushing to GitHub:
```powershell
python scripts/verify_all.py
```

### 3. GitHub Actions CI/CD & Merge Protection
This repository includes a GitHub Actions workflow in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) that automatically runs all test cases across Python 3.10, 3.11, and 3.12 on every push and pull request.

To ensure code is only merged into `main` when all tests pass:
1. Open GitHub repo > **Settings** > **Branches**.
2. Add branch protection rule for `main`.
3. Enable **Require status checks to pass before merging** and select `Merge Protection Gate`.
4. Detailed setup steps are documented in [docs/branch_protection_guide.md](docs/branch_protection_guide.md).

---

## Production Deployment (Docker + PostgreSQL)

To launch the PostgreSQL container on your server or Oracle VM:
```bash
docker compose -f docker/docker-compose.yml up -d
```
Update `DATABASE_URL` in `.env` to point to the PostgreSQL instance.
