"""
News Exporter: Exports scraped news announcements into JSON and CSV formats.
"""

import csv
import io
import json
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import NewsItemRecord


def get_records_query(
    db: Session,
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 1000,
) -> List[NewsItemRecord]:
    """Helper query to fetch filtered news records."""
    stmt = select(NewsItemRecord).order_by(NewsItemRecord.published_at.desc())

    if ticker:
        stmt = stmt.where(NewsItemRecord.ticker == ticker.upper())
    if source:
        stmt = stmt.where(NewsItemRecord.source == source.lower())
    if category:
        stmt = stmt.where(NewsItemRecord.category == category.lower())

    stmt = stmt.limit(limit)
    return db.execute(stmt).scalars().all()


def export_to_json(
    db: Session,
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 1000,
) -> str:
    """Exports filtered announcements as a formatted JSON string."""
    records = get_records_query(db, ticker=ticker, source=source, category=category, limit=limit)
    items = []
    for r in records:
        items.append(
            {
                "id": str(r.id),
                "ticker": r.ticker,
                "title": r.title,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
                "source_id": r.source_id,
                "category": r.category,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
            }
        )
    return json.dumps(items, indent=2)


def export_to_csv(
    db: Session,
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 1000,
) -> str:
    """Exports filtered announcements as a CSV formatted string."""
    records = get_records_query(db, ticker=ticker, source=source, category=category, limit=limit)
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "id",
            "ticker",
            "title",
            "description",
            "source",
            "source_url",
            "source_id",
            "category",
            "published_at",
            "scraped_at",
        ]
    )

    for r in records:
        writer.writerow(
            [
                str(r.id),
                r.ticker or "",
                r.title or "",
                r.description or "",
                r.source or "",
                r.source_url or "",
                r.source_id or "",
                r.category or "",
                r.published_at.isoformat() if r.published_at else "",
                r.scraped_at.isoformat() if r.scraped_at else "",
            ]
        )

    return output.getvalue()
