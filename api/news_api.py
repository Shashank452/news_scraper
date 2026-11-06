"""
REST API for News Scraper Service.
Provides endpoints for querying, filtering, exporting, and triggering news scraping.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from config import settings
from database import NewsItemRecord, get_db, init_db
from exporters.news_exporter import export_to_csv, export_to_json
from news_model import NewsItemResponse
from aggregators.news_aggregator import NewsAggregator
from utils import logger

app = FastAPI(
    title="Indian Stock Market News Scraper API",
    description="Real-time corporate announcement ingestion and query service for BSE & NSE.",
    version="1.0.0",
)

# Enable CORS for internal dashboards or frontend consumers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Ensure database schema is created on startup."""
    init_db()


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> bool:
    """
    Validates internal API-key header.
    If settings.api_key is set to empty or 'none', authentication is bypassed.
    """
    if not settings.api_key or settings.api_key.lower() in ("none", "disabled"):
        return True

    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
    return True


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint verifying system & database readiness."""
    try:
        # Check DB connection
        db.execute(select(1)).scalar_one()
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


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
        stmt = stmt.where(NewsItemRecord.ticker == ticker.upper())
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
    format: str = Query("json", regex="^(json|csv)$", description="Export format: 'json' or 'csv'"),
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
