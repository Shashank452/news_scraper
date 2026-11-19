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
├── core/
│   ├── __init__.py            # Core package exports
│   ├── config.py              # Pydantic-based configuration management
│   ├── database.py            # SQLAlchemy ORM models, indexes & deduplication
│   ├── mcp_server.py          # Model Context Protocol (MCP) server
│   ├── news_model.py          # Pydantic schemas and auto-categorization
│   ├── scheduler.py           # APScheduler background runner
│   └── utils.py               # Rate limiting, logger, and ticker sanitization
├── ui/
│   └── index.html             # Real-time Bloomberg-style news terminal UI
├── run.py                     # Master runner (only python file in root)
├── pytest.ini                 # Pytest configuration & warning suppression
├── requirements.txt           # Project dependencies
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
| `GET` | `/mcp/sse` | **Model Context Protocol (MCP) SSE endpoint** for Claude, Cursor, and AI agents |
| `GET` | `/news` | Query news with filters (`ticker`, `source`, `category`, `since`, `since_scraped`, `limit`, `offset`) |
| `GET` | `/news/google` | **Google News RSS**: Real-time ticker/query financial headlines without API key |
| `GET` | `/news/browse` | **Web Page Reader**: Clean markdown conversion of any URL via Jina Reader |
| `GET` | `/news/search-web` | **Free Web Search**: Live search queries without an API key |
| `GET` | `/market/quote/{ticker}` | **Live Stock Quote**: Real-time price, day change, 52-week high/low, and volume |
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

## Model Context Protocol (MCP) Server for Claude & AI Agents

The service embeds an **MCP Server** (`indian-stock-market-news`) allowing AI assistants like **Claude (Web & Desktop)**, Cursor, and custom agentic workflows to query real-time Indian stock market disclosures directly.

### Available MCP Tools (11 Tools):
1. `get_latest_announcements(ticker, source, category, limit)`: Fetch official corporate disclosures and exchange announcements (BSE & NSE).
2. `search_market_news(query, ticker, days_back, live_search, limit)`: Search live web feeds and historical database records for keywords or themes.
3. `get_live_market_indices()`: Live levels for benchmark indices (NIFTY 50, BANK NIFTY, INDIA VIX, NIFTY IT).
4. `get_surveillance_and_circuit_notices(limit)`: Check BSE/NSE surveillance notices (ASM, GSM, price bands, graded surveillance).
5. `get_government_and_regulatory_policies(regulator, limit)`: Track regulatory updates from SEBI, RBI, IRDAI, and Government policy press releases.
6. `get_world_and_macro_news(limit)`: Retrieve global macroeconomic themes, crude oil trends, and foreign policy news.
7. `get_google_news(query, topic, limit)`: **Free Google News RSS**: Query breaking headlines by stock ticker, company name, or topic without rate limits or API keys.
8. `browse_web_page(url, max_chars)`: **Free Web Page Reader**: Extract clean markdown text of any article or report via Jina Reader.
9. `search_web_free(query, limit)`: **Free Web Search**: Search the live web for breaking announcements, analyst articles, and website info without an API key.
10. `get_live_market_quote(ticker, exchange, range_period)`: **Free Live Stock Quotes & Metrics**: Real-time prices, day changes, 52-week high/low, day high/low, and volume for NSE/BSE stocks.
11. `trigger_live_scrape()`: Trigger an on-demand real-time scrape cycle across all feeds.

---

### Connecting Claude Web (`claude.ai`)

When running in cloud hosting (e.g., **Oracle Cloud** at `clawtrade.duckdns.org`), Claude Web connects directly over the internet from Anthropic's cloud backend to your hosted MCP SSE endpoint.

#### 1. Requirements for Claude Web & Oracle Cloud:
* **HTTPS Requirement**: Anthropic's servers require an SSL/TLS certificate. Use Nginx with Let's Encrypt / Certbot on port 443, or route through a Cloudflare Tunnel:
  ```
  https://clawtrade.duckdns.org/mcp/sse
  ```
* **Oracle Cloud Ingress**: Ensure your Oracle Cloud VCN Security List and OS firewall (`iptables` / `ufw`) permit inbound traffic on your external port (e.g., 443 / 8000).

#### 2. Adding to Claude Web:
1. Log in to [claude.ai](https://claude.ai).
2. Go to **Settings** > **Connectors** (or **Integrations**).
3. Click **Add custom connector** and enter your public HTTPS endpoint:
   `https://clawtrade.duckdns.org/mcp/sse`

---

### Connecting Claude Desktop

#### Option A: Remote SSE Connection (Hosted Server)
To connect your local Claude Desktop app to your hosted remote instance, add this to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "indian-stock-market-news": {
      "url": "http://clawtrade.duckdns.org:8000/mcp/sse"
    }
  }
}
```

#### Option B: Local `stdio` Transport (Running on Local Machine)
If running locally on your development machine, configure Claude Desktop to launch the server as a subprocess:
```json
{
  "mcpServers": {
    "indian-stock-market-news": {
      "command": "python",
      "args": ["-m", "core.mcp_server"],
      "cwd": "C:\\path\\to\\news_scraper"
    }
  }
}
```

#### Option C: Standalone CLI Runner
You can also run the MCP server standalone in either `stdio` or `sse` mode:
```powershell
# Run in default stdio transport:
python -m core.mcp_server

# Run in SSE transport on custom port:
python -m core.mcp_server --transport sse --host 0.0.0.0 --port 8001
```

---

## Running Tests & CI/CD Verification

### 1. Run Complete Test Suite
Execute all 40 unit and integration tests with pytest:
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

## Production Deployment (All-in-One Docker Image)

The project includes an **all-in-one, fully self-contained Docker image** containing Python 3.11, all required packages, the embedded database (PostgreSQL 17 / SQLite), background scrapers, and the FastAPI REST API server + Web Dashboard.

### 1. Build the Docker Image
```bash
docker build -f docker/Dockerfile -t news_scraper:latest .
```

### 2. Run with Docker CLI

**Option A: Running with Embedded PostgreSQL (Default)**
```bash
docker run -d \
  --name news_scraper_app \
  -p 8000:8000 \
  -p 5432:5432 \
  -v news_scraper_pg:/var/lib/postgresql/data \
  news_scraper:latest
```

**Option B: Running with Lightweight SQLite**
```bash
docker run -d \
  --name news_scraper_app \
  -p 8000:8000 \
  -e DATABASE_TYPE=sqlite \
  -v news_scraper_data:/app/data \
  news_scraper:latest
```

### 3. Run with Docker Compose
```bash
# Start all-in-one service with persistence from project root:
docker compose -f docker/docker-compose.yml up -d

# View real-time logs
docker compose -f docker/docker-compose.yml logs -f

# Stop container
docker compose -f docker/docker-compose.yml down
```

### 4. Verify Service Health
Check the container health and API availability:
```bash
curl http://localhost:8000/health
```
Access the interactive Web UI and Swagger Docs:
- **Web Dashboard**: `http://localhost:8000/`
- **Swagger Documentation**: `http://localhost:8000/docs`
