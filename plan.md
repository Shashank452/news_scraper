# News Scraper Module Implementation Plan

## Project Overview
Build a modular Python-based news scraper system that collects real-time news from primary sources (BSE announcements, NSE announcements, SEBI filings, company IR pages). This module focuses solely on news scraping and data collection. Sentiment analysis and integration with other systems will be handled by separate projects.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│              News Scraper Module (Python)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐                          │
│  │ BSE          │  │ NSE          │                          │
│  │ Announcements│  │ Announcements│                          │
│  │ Scraper      │  │ Scraper      │                          │
│  └──────┬───────┘  └──────┬───────┘                          │
│         │                 │                                   │
│         └─────────────────┼─────────────────┐                │
│                           ▼                 │                │
│                  ┌──────────────┐          │                │
│                  │  News        │          │                │
│                  │  Aggregator  │          │                │
│                  └──────┬───────┘          │                │
│                         │                 │                │
│                         ▼                 │                │
│                  ┌──────────────┐          │                │
│                  │  Database    │          │                │
│                  │  (PostgreSQL)│          │                │
│                  └──────┬───────┘          │                │
│                         │                 │                │
│                         ▼                 │                │
│                  ┌──────────────┐          │                │
│                  │  API /       │          │                │
│                  │  Export      │          │                │
│                  └──────────────┘          │                │
│                                             │                │
│  ┌──────────────┐  ┌──────────────┐        │                │
│  │ SEBI         │  │ Company IR   │        │                │
│  │ Filings      │  │ Pages        │◄───────┘                │
│  │ (Later)      │  │ (Later)      │                         │
│  └──────────────┘  └──────────────┘                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌──────────────────────────┐
              │  External Integration   │
              │  (Sentiment Analysis,   │
              │   MCP, Trading Systems) │
              └──────────────────────────┘
```

### Data Flow

1. **Scrapers** collect raw news from multiple sources
2. **Aggregator** normalizes and deduplicates news items
3. **Database** stores news with metadata (timestamp, source, ticker, URL)
4. **API/Export** provides clean data for external integration

## Implementation Phases

### Phase 1: Foundation
- **Project Setup**
  - Initialize Python project structure
  - Set up virtual environment
  - Create requirements.txt with dependencies
  - Set up PostgreSQL database (run in Docker on Oracle VM)

- **Core Infrastructure**
  - `database.py` - Database connection and models
  - `config.py` - Configuration management
  - `utils.py` - Common utilities (logging, rate limiting, caching)
  - `news_model.py` - Unified data model for news items
  - `scheduler.py` - APScheduler for long-running process

- **Data Model**
  ```python
  NewsItem:
    - id: UUID
    - ticker: str (NSE symbol)
    - title: str
    - description: str (short description, not full content)
    - source: str (bse, nse, sebi, company_ir)
    - source_url: str
    - source_id: str (unique ID from source for deduplication)
    - published_at: datetime
    - scraped_at: datetime
    - category: str (results, board_meeting, acquisition, etc.)
  ```

- **Database Constraints**
  - Unique constraint on (source + source_id or URL) for deduplication
  - Index on ticker, published_at, source for fast queries

- **Data Retention Policy**
  - Keep lightweight records (ticker, title, category, source, URL, timestamps) permanently
  - Purge only text bodies (description) after 3 months
  - Reason: Preserve history for backtesting while saving storage space
  - Cleanup schedule: Every day at night (e.g., 2 AM)
  - Implement scheduled cleanup job

### Phase 2: Scrapers (Priority Order)

#### 2.1 BSE Announcements Scraper (Priority 1)
- **File**: `scrapers/bse_scraper.py`
- **Sources**:
  - BSE corporate announcements
  - BSE circulars
- **Features**:
  - Poll every 1-2 minutes during market hours (9:00-15:30 IST)
  - Back off outside market hours
  - Categorize announcements (results, board meetings, acquisitions, etc.)
  - Extract ticker symbols from announcements
  - Respect rate limits and site terms
  - Cache responses to avoid blocking
- **Dependencies**: `beautifulsoup4`, `requests`

#### 2.2 NSE Announcements Scraper (Priority 2)
- **File**: `scrapers/nse_scraper.py`
- **Sources**:
  - NSE corporate announcements
  - NSE circulars
- **Features**:
  - Poll every 1-2 minutes during market hours (9:00-15:30 IST)
  - Back off outside market hours
  - Handle specific headers/cookies if required
  - Categorize announcements (results, board meetings, acquisitions, etc.)
  - Extract ticker symbols from announcements
  - Respect rate limits (NSE can block aggressive polling)
  - Cache responses to avoid blocking
- **Dependencies**: `beautifulsoup4`, `requests`

#### 2.3 SEBI Filings Scraper (Later Phase)
- **File**: `scrapers/sebi_scraper.py`
- **Sources**:
  - SEBI official website
  - Regulatory orders, circulars, enforcement actions
- **Note**: SEBI mostly carries regulatory content, not ticker-level news
- **Features**:
  - Scrape regulatory filings
  - Filter for material events
  - Extract key information from filings
- **Dependencies**: `beautifulsoup4`, `requests`

#### 2.4 Company IR/Press Release Scraper (Later Phase)
- **File**: `scrapers/press_release_scraper.py`
- **Sources**:
  - Company investor relations pages
  - Official press release sections
- **Note**: Each site needs its own parser and they break often
- **Features**:
  - Parse HTML from IR pages
  - Extract press releases and announcements
  - Identify ticker symbols from company names
- **Dependencies**: `beautifulsoup4`, `requests`

#### 2.5 Twitter/X Scraper (Later Phase, if needed)
- **File**: `scrapers/twitter_scraper.py`
- **Note**: Implement only if BSE/NSE sources are insufficient
- **Approach**: Web scraping (API access not available)
- **Features**:
  - Monitor official company Twitter handles
  - Track hashtags related to companies
  - Extract ticker symbols from tweets
  - Rate limiting and error handling
- **Dependencies**: `selenium` or `playwright`

### Phase 3: Aggregation

#### 3.1 News Aggregator
- **File**: `aggregators/news_aggregator.py`
- **Features**:
  - Collect news from all scrapers
  - Normalize data format
  - Extract and validate ticker symbols
  - Deduplication handled at database level (unique constraint on source + source_id/URL)
  - Prioritize by source reliability

### Phase 4: API/Export Layer

#### 4.1 REST API
- **File**: `api/news_api.py`
- **Endpoints**:
  - `GET /news` - Get all news with filters
  - `GET /news/{ticker}` - Get news for specific ticker
  - `GET /news/sources/{source}` - Get news from specific source
  - `GET /news/export` - Export news in JSON/CSV format
- **Authentication**: Simple API-key header (internal use only)
- **Network**: Bind to localhost or private network, closed in Oracle firewall
- **Dependencies**: `fastapi` or `flask`

#### 4.2 Export Functions
- **File**: `exporters/news_exporter.py`
- **Formats**: JSON, CSV, database dump
- **Use Case**: Easy integration with other projects

### Phase 5: Scheduler & Deployment

#### 5.1 Long-Running Scheduler
- **File**: `scheduler.py`
- **Approach**: Single Python process using asyncio and APScheduler
- **Schedule**:
  - Poll BSE/NSE every 1-2 minutes during market hours (9:00-15:30 IST)
  - Back off outside market hours
  - Keep state in memory (last-seen IDs, rate-limit backoff)
  - Per-source health checks
- **Deployment**: Run under systemd or Docker with restart-on-failure

#### 5.2 Testing
- Unit tests for each scraper
- Integration tests for aggregator
- API endpoint tests
- Performance testing (rate limits, response times)

#### 5.3 Deployment
- Docker containerization for PostgreSQL
- Environment configuration
- Monitoring and logging
- Error handling and alerts

## File Structure

```
news_scraper/
├── plan.md
├── README.md
├── requirements.txt
├── config.py
├── database.py
├── news_model.py
├── utils.py
├── scheduler.py
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py
│   ├── bse_scraper.py
│   ├── nse_scraper.py
│   ├── sebi_scraper.py
│   ├── press_release_scraper.py
│   └── twitter_scraper.py
├── aggregators/
│   ├── __init__.py
│   └── news_aggregator.py
├── api/
│   ├── __init__.py
│   └── news_api.py
├── exporters/
│   ├── __init__.py
│   └── news_exporter.py
├── tests/
│   ├── test_scrapers.py
│   ├── test_aggregator.py
│   └── test_api.py
├── scripts/
│   ├── run_scrapers.py
│   └── init_db.py
└── docker/
    └── docker-compose.yml (PostgreSQL)
```

## Dependencies

### Core
- `python>=3.9`
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `sqlalchemy` - Database ORM
- `psycopg2-binary` - PostgreSQL adapter
- `pydantic` - Data validation

### Scraping
- `aiohttp` - Async HTTP requests
- `selenium` or `playwright` - Web scraping (for Twitter, if needed later)

### Scheduler
- `apscheduler` - Task scheduling
- `asyncio` - Async I/O

### API
- `fastapi` - REST API
- `uvicorn` - ASGI server
- `python-multipart` - For form data (if needed)

### Database
- `docker` and `docker-compose` - For PostgreSQL container

## Key Considerations

### Rate Limiting
- Respect API rate limits (BSE, NSE, SEBI)
- Implement exponential backoff
- Cache responses to avoid duplicate requests
- Poll BSE/NSE every 1-2 minutes during market hours only
- Back off outside market hours to avoid blocking

### Data Quality
- Validate ticker symbols against NSE/BSE
- Deduplication at database level (unique constraint on source + source_id/URL)
- Filter out spam/irrelevant content
- Maintain source reliability scores

### Performance
- Use async I/O for concurrent scraping
- Implement caching strategies
- Database indexing for fast queries
- Efficient data storage and retrieval
- PostgreSQL handles concurrent writes better than SQLite

### Security
- Secure API keys in environment variables
- Use HTTPS for all requests
- Sanitize user inputs
- Simple API-key authentication for internal use
- Bind API to localhost or private network
- Close ports in Oracle firewall

### Legal/Compliance
- Respect robots.txt
- Comply with site terms of service (BSE, NSE)
- Don't scrape copyrighted content excessively
- Read and follow exchange site terms

## Integration with External Systems

This module provides clean data exports for integration with other projects:

### API Integration
- REST API endpoints for real-time data access
- JSON/CSV export for batch processing
- Database access for direct integration

### Use Cases
- **Sentiment Analysis Projects**: Can consume news data via API or export
- **MCP Servers**: Can integrate via REST API or direct database access
- **Trading Systems**: Can use API for real-time news feeds
- **Analytics Platforms**: Can use CSV/JSON exports for analysis

## Success Metrics

- **Coverage**: News from 80% of NSE top 500 stocks
- **Latency**: News scraped within 5 minutes of publication
- **Data Quality**: >95% ticker symbol accuracy
- **Uptime**: >99% scraper availability
- **Performance**: API response time <500ms

## Build Order

1. **Foundation**
   - Set up project structure and dependencies
   - Set up PostgreSQL database (Docker on Oracle VM)
   - Implement database schema with unique constraints
   - Implement base scraper module

2. **Primary Scrapers**
   - Implement BSE announcements scraper
   - Implement NSE announcements scraper

3. **API Layer**
   - Implement REST API with simple API-key authentication
   - Test API endpoints

4. **Aggregation**
   - Implement news aggregator
   - Implement deduplication (database-level)

5. **Scheduler**
   - Implement long-running scheduler with APScheduler
   - Configure market hours polling (9:00-15:30 IST)
   - Deploy under systemd or Docker with restart-on-failure

6. **Later Phase Scrapers**
   - Implement SEBI filings scraper (for regulatory content)
   - Implement company IR scraper (if needed)
   - Implement Twitter scraper (only if BSE/NSE insufficient)

7. **Cleanup**
   - Implement scheduled cleanup for text bodies (keep records permanent)
   - Configure daily cleanup at night (2 AM)
