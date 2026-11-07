"""
REST API for News Scraper Service.
Provides endpoints for querying, filtering, exporting, triggering news scraping,
and serving the interactive testing web UI.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from config import is_market_hours, settings
from database import NewsItemRecord, get_db, init_db, save_news_items_batch
from exporters.news_exporter import export_to_csv, export_to_json
from news_model import NewsItemResponse
from aggregators.news_aggregator import NewsAggregator
from scrapers.nse_scraper import NSEScraper
from scrapers.media_news_scraper import MediaNewsScraper
from scrapers.regulatory_policy_scraper import RegulatoryPolicyScraper
from utils import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database schema is created on application startup."""
    init_db()
    yield


app = FastAPI(
    title="Indian Stock Market News Scraper API",
    description="Real-time corporate announcement ingestion and query service for BSE & NSE.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for internal dashboards or frontend consumers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UI_HTML_PATH = Path(__file__).parent.parent / "ui" / "index.html"


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key_query: Optional[str] = Query(None, alias="api_key"),
) -> bool:
    """
    Validates internal API-key.
    Bypasses authentication if key is not configured or explicitly disabled.
    """
    provided_key = x_api_key or api_key_query
    if not settings.api_key or settings.api_key.lower() in ("none", "disabled"):
        return True

    if not provided_key or provided_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key header (X-API-Key)",
        )
    return True


@app.get("/", response_class=HTMLResponse, tags=["UI"])
@app.get("/ui", response_class=HTMLResponse, tags=["UI"])
def serve_ui():
    """Serves the interactive web UI for testing and viewing live announcements."""
    if UI_HTML_PATH.exists():
        html_content = UI_HTML_PATH.read_text(encoding="utf-8")
        # Inject API key so browser requests are automatically authorized
        html_content = html_content.replace("{{API_KEY}}", settings.api_key or "")
        return HTMLResponse(content=html_content)
    return HTMLResponse("<h3>UI template not found</h3>", status_code=404)


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint verifying system & database readiness."""
    try:
        db.execute(select(1)).scalar_one()
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "is_market_hours": is_market_hours(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/stats", tags=["Stats"])
def get_stats(db: Session = Depends(get_db)):
    """Provides high-level announcement counts and market status for the UI dashboard."""
    total = db.query(NewsItemRecord).count()
    bse = db.query(NewsItemRecord).filter(NewsItemRecord.source == "bse").count()
    nse = db.query(NewsItemRecord).filter(NewsItemRecord.source == "nse").count()
    categories_raw = (
        db.query(NewsItemRecord.category, func.count(NewsItemRecord.id))
        .group_by(NewsItemRecord.category)
        .all()
    )
    categories = {cat or "general": count for cat, count in categories_raw}

    return {
        "total_news": total,
        "bse_count": bse,
        "nse_count": nse,
        "categories": categories,
        "is_market_hours": is_market_hours(),
    }


@app.get("/market/indices", tags=["Market"])
def get_market_indices():
    """Returns live snapshot of major benchmark indices (NIFTY 50, BANK NIFTY, INDIA VIX)."""
    scraper = NSEScraper()
    indices = scraper.get_market_indices()
    return indices


@app.get(
    "/news",
    response_model=List[NewsItemResponse],
    dependencies=[Depends(verify_api_key)],
    tags=["News"],
)
def get_news(
    ticker: Optional[str] = Query(None, description="Filter by NSE/BSE ticker symbol (e.g. RELIANCE)"),
    source: Optional[str] = Query(None, description="Filter by source: 'bse', 'nse'"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. 'financial_results')"),
    since: Optional[datetime] = Query(None, description="Filter published after this timestamp"),
    limit: int = Query(50, ge=1, le=500, description="Number of items to retrieve"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
):
    """Retrieves news announcements with flexible filtering and pagination."""
    stmt = select(NewsItemRecord).order_by(desc(NewsItemRecord.published_at))

    if ticker:
        # Match either exact ticker or contains ticker substring (supports scrip codes)
        stmt = stmt.where(
            (NewsItemRecord.ticker == ticker.upper())
            | (NewsItemRecord.title.ilike(f"%{ticker}%"))
        )
    if source:
        stmt = stmt.where(NewsItemRecord.source == source.lower())
    if category:
        stmt = stmt.where(NewsItemRecord.category == category.lower())
    if since:
        stmt = stmt.where(NewsItemRecord.published_at >= since)

    stmt = stmt.offset(offset).limit(limit)
    records = db.execute(stmt).scalars().all()
    return records


@app.get(
    "/news/live",
    response_model=List[NewsItemResponse],
    dependencies=[Depends(verify_api_key)],
    tags=["News"],
)
def get_live_media_news(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Fetches real-time live market news from major financial media feeds (ET, Moneycontrol) and persists them."""
    scraper = MediaNewsScraper()
    items = scraper.fetch_latest(max_items_per_source=limit // 2)
    save_news_items_batch(db, items)

    stmt = (
        select(NewsItemRecord)
        .where(NewsItemRecord.source.in_(["economic_times", "moneycontrol", "media_news"]))
        .order_by(desc(NewsItemRecord.published_at))
        .limit(limit)
    )
    return db.execute(stmt).scalars().all()


@app.get(
    "/news/search",
    response_model=List[NewsItemResponse],
    dependencies=[Depends(verify_api_key)],
    tags=["News"],
)
def search_market_news_api(
    q: Optional[str] = Query(None, description="Keywords or topic (e.g. 'results', 'defence', 'capex')"),
    ticker: Optional[str] = Query(None, description="Stock ticker symbol (e.g. 'RELIANCE', 'TATA MOTORS')"),
    days_back: Optional[int] = Query(None, ge=1, le=365, description="Filter news published within last N days"),
    live_search: bool = Query(True, description="Query live web feeds if True, or search historical DB only"),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Unified search across live and historical news.
    Searches both stored database records and live online media feeds,
    deduplicating and returning chronologically sorted articles.
    """
    if live_search and (q or ticker):
        scraper = MediaNewsScraper()
        live_items = scraper.search_news(query=q or "", ticker=ticker, days_back=days_back, limit=limit)
        save_news_items_batch(db, live_items)

    stmt = select(NewsItemRecord).order_by(desc(NewsItemRecord.published_at))
    if ticker:
        clean_ticker = ticker.strip().upper()
        stmt = stmt.where(
            (NewsItemRecord.ticker == clean_ticker)
            | (NewsItemRecord.title.ilike(f"%{clean_ticker}%"))
        )
    if q:
        clean_q = q.strip()
        words = [w for w in clean_q.split() if len(w) > 2]
        if words:
            conditions = []
            for w in words:
                conditions.append(NewsItemRecord.title.ilike(f"%{w}%"))
                conditions.append(NewsItemRecord.description.ilike(f"%{w}%"))
            stmt = stmt.where(or_(*conditions))
        else:
            stmt = stmt.where(
                (NewsItemRecord.title.ilike(f"%{clean_q}%"))
                | (NewsItemRecord.description.ilike(f"%{clean_q}%"))
            )
    if days_back:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        stmt = stmt.where(NewsItemRecord.published_at >= cutoff)

    stmt = stmt.limit(limit)
    records = db.execute(stmt).scalars().all()
    return records


@app.get(
    "/news/policy",
    response_model=List[NewsItemResponse],
    dependencies=[Depends(verify_api_key)],
    tags=["Policy & Regulators"],
)
def get_regulatory_policy_news(
    regulator: Optional[str] = Query(None, description="Filter by regulator: 'irdai', 'rbi', 'sebi', 'govt_policy'"),
    limit: int = Query(30, ge=1, le=100),
    live_fetch: bool = Query(True, description="Fetch live regulatory updates on-demand"),
    db: Session = Depends(get_db),
):
    """
    Retrieves government announcements, bills, amendments, and regulatory notifications
    from IRDAI, RBI, SEBI, and Central Ministries with tagged affected stocks.
    """
    if live_fetch:
        scraper = RegulatoryPolicyScraper()
        items = scraper.fetch_latest()
        save_news_items_batch(db, items)

    stmt = select(NewsItemRecord).where(
        NewsItemRecord.source.in_(["irdai", "rbi", "sebi", "govt_policy"])
    )
    if regulator:
        stmt = stmt.where(NewsItemRecord.source == regulator.lower())

    stmt = stmt.order_by(desc(NewsItemRecord.published_at)).limit(limit)
    return db.execute(stmt).scalars().all()


@app.get(
    "/news/world",
    response_model=List[NewsItemResponse],
    dependencies=[Depends(verify_api_key)],
    tags=["World News"],
)
def get_world_and_macro_news(
    limit: int = Query(30, ge=1, le=100),
    live_fetch: bool = Query(True, description="Fetch live world business news on-demand"),
    db: Session = Depends(get_db),
):
    """
    Retrieves global macroeconomic news, US Federal Reserve decisions,
    crude oil developments, and world markets affecting Indian equities.
    """
    if live_fetch:
        scraper = MediaNewsScraper()
        items = scraper.fetch_world_and_macro_news(max_items=limit)
        save_news_items_batch(db, items)

    stmt = select(NewsItemRecord).where(
        NewsItemRecord.source == "world_news"
    ).order_by(desc(NewsItemRecord.published_at)).limit(limit)
    return db.execute(stmt).scalars().all()


@app.get(
    "/news/{ticker}",
    response_model=List[NewsItemResponse],
    dependencies=[Depends(verify_api_key)],
    tags=["News"],
)
def get_news_by_ticker(
    ticker: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieves news for a specific stock ticker symbol."""
    stmt = (
        select(NewsItemRecord)
        .where(NewsItemRecord.ticker == ticker.upper())
        .order_by(desc(NewsItemRecord.published_at))
        .offset(offset)
        .limit(limit)
    )
    records = db.execute(stmt).scalars().all()
    return records


@app.get(
    "/news/sources/{source}",
    response_model=List[NewsItemResponse],
    dependencies=[Depends(verify_api_key)],
    tags=["News"],
)
def get_news_by_source(
    source: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieves news announcements originating from a specific source."""
    stmt = (
        select(NewsItemRecord)
        .where(NewsItemRecord.source == source.lower())
        .order_by(desc(NewsItemRecord.published_at))
        .offset(offset)
        .limit(limit)
    )
    records = db.execute(stmt).scalars().all()
    return records


@app.get(
    "/news/export/file",
    dependencies=[Depends(verify_api_key)],
    tags=["Export"],
)
def export_news(
    format: str = Query("json", pattern="^(json|csv)$", description="Export format: 'json' or 'csv'"),
    ticker: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """Exports news records as downloadable CSV or JSON file."""
    if format == "csv":
        csv_data = export_to_csv(db, ticker=ticker, source=source, category=category, limit=limit)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=news_export.csv"},
        )
    else:
        json_data = export_to_json(db, ticker=ticker, source=source, category=category, limit=limit)
        return Response(
            content=json_data,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=news_export.json"},
        )


@app.post(
    "/news/trigger-scrape",
    dependencies=[Depends(verify_api_key)],
    tags=["Scraper"],
)
def trigger_scrape(db: Session = Depends(get_db)):
    """Manually triggers one complete scraping & deduplication cycle."""
    aggregator = NewsAggregator()
    summary = aggregator.run_cycle(db=db)
    return {"message": "Scrape cycle completed", "summary": summary}
