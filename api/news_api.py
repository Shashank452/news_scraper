"""
REST API for News Scraper Service.
Provides endpoints for querying, filtering, exporting, triggering news scraping,
and serving the interactive testing web UI.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from config import is_market_hours, settings
from database import NewsItemRecord, get_db, init_db
from exporters.news_exporter import export_to_csv, export_to_json
from news_model import NewsItemResponse
from aggregators.news_aggregator import NewsAggregator
from scrapers.nse_scraper import NSEScraper
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
