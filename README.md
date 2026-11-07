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
├── api/
│   ├── __init__.py
│   └── news_api.py            # FastAPI endpoints & authentication
├── aggregators/
│   ├── __init__.py
│   └── news_aggregator.py     # Aggregator coordinating scrapers & DB batching
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py        # Base scraper class with rate-limiting & sessions
│   ├── bse_scraper.py         # BSE Corporate Announcements scraper
│   └── nse_scraper.py         # NSE Corporate Announcements scraper with session warmup
├── exporters/
│   ├── __init__.py
│   └── news_exporter.py       # JSON & CSV export formatters
├── scripts/
│   ├── init_db.py             # Database creation script
│   └── run_scrapers.py        # CLI tool to test scrapers directly
├── tests/
│   ├── test_model_and_utils.py # Tests for normalization, categorization & market hours
│   ├── test_database.py       # Tests for deduplication and 90-day retention purge
│   └── test_api.py            # Tests for API endpoints and auth
├── docker/
│   └── docker-compose.yml     # Production PostgreSQL container
├── config.py                  # Pydantic-based configuration management
├── database.py                # SQLAlchemy ORM models and session factories
├── news_model.py              # Pydantic schemas and auto-categorization
├── utils.py                   # Rate limiting, logger, and ticker sanitization
├── run.py                     # Master runner (starts server, 15m scheduler, cleanup)
├── scheduler.py               # APScheduler background runner
├── requirements.txt           # Project dependencies
├── .env.example               # Environment variables template
└── plan.md                    # Detailed architectural plan
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

## Running Tests

Execute test suite with pytest:
```powershell
pytest -v
```

---

## Production Deployment (Docker + PostgreSQL)

To launch the PostgreSQL container on your server or Oracle VM:
```bash
docker compose -f docker/docker-compose.yml up -d
```
Update `DATABASE_URL` in `.env` to point to the PostgreSQL instance.
