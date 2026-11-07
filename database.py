"""
Database infrastructure: SQLAlchemy models, engine configuration,
session management, and data retention operations.
"""

from datetime import datetime, timedelta, timezone
from typing import Generator, List, Optional
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    desc,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.types import TypeDecorator, CHAR

from config import settings
from news_model import NewsItemCreate
from utils import logger


# Cross-dialect UUID type compatible with both PostgreSQL and SQLite
class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type.
    Uses PostgreSQL's UUID type if available, otherwise CHAR(36).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return str(uuid.UUID(value))
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


Base = declarative_base()


class NewsItemRecord(Base):
    """
    SQLAlchemy table model for news announcements.
    Includes deduplication constraints and optimized query indexes.
    """

    __tablename__ = "news_items"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    ticker = Column(String(150), nullable=True, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)  # Subject to 90-day retention purge
    source = Column(String(50), nullable=False, index=True)  # bse, nse, sebi, etc.
    source_url = Column(Text, nullable=True)
    source_id = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=True, index=True, default="general")
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    scraped_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Ensure identical announcements from same source are never duplicated
        UniqueConstraint("source", "source_id", name="uq_source_source_id"),
        # Composite index for fast ticker history queries
        Index("ix_news_ticker_published", "ticker", "published_at"),
        # Composite index for time-range lookups by source
        Index("ix_news_source_published", "source", "published_at"),
        # Composite index for incremental polling by source
        Index("ix_news_scraped_source", "scraped_at", "source"),
        # Composite index for ticker-specific incremental stream
        Index("ix_news_ticker_scraped", "ticker", "scraped_at"),
        # Composite index for fast deduplication
        Index("ix_news_title_published", "title", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<NewsItemRecord(id={self.id}, ticker='{self.ticker}', source='{self.source}', published_at='{self.published_at}')>"


# Configure Database Engine
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Creates all database tables defined in the models and ensures indexes exist."""
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)

    # Ensure incremental cursor indexes and deduplication indexes exist on existing DBs
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_news_items_scraped_at ON news_items (scraped_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_scraped_source ON news_items (scraped_at, source)",
        "CREATE INDEX IF NOT EXISTS ix_news_ticker_scraped ON news_items (ticker, scraped_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_title_published ON news_items (title, published_at)",
    ]
    with engine.connect() as conn:
        for idx_sql in indexes:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.debug(f"Index creation note: {e}")
        conn.commit()

    logger.info("Database schema and indexes initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """Dependency for yielding database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_duplicate_record(db: Session, item: NewsItemCreate) -> bool:
    """
    Multi-level check to ensure zero duplicate announcements are stored.
    Checks:
    1. Exact (source, source_id)
    2. Exact non-empty source_url
    3. Exact (title, published_at)
    4. Same ticker + identical title published within 24 hours
    """
    # 1. Exact source and source_id
    if (
        db.execute(
            select(NewsItemRecord.id).where(
                NewsItemRecord.source == item.source,
                NewsItemRecord.source_id == item.source_id,
            )
        ).scalar_one_or_none()
        is not None
    ):
        return True

    # 2. Exact source_url (if available)
    if item.source_url:
        clean_url = str(item.source_url).strip()
        if clean_url:
            if (
                db.execute(
                    select(NewsItemRecord.id).where(NewsItemRecord.source_url == clean_url)
                ).scalar_one_or_none()
                is not None
            ):
                return True

    # 3. Exact title and published_at
    if (
        db.execute(
            select(NewsItemRecord.id).where(
                NewsItemRecord.title == item.title,
                NewsItemRecord.published_at == item.published_at,
            )
        ).scalar_one_or_none()
        is not None
    ):
        return True

    # 4. Same ticker and title within 24h window (catches re-submitted disclosures with different attachment IDs)
    if item.ticker and item.title and item.published_at:
        window_start = item.published_at - timedelta(hours=24)
        window_end = item.published_at + timedelta(hours=24)
        if (
            db.execute(
                select(NewsItemRecord.id).where(
                    NewsItemRecord.ticker == item.ticker,
                    NewsItemRecord.title == item.title,
                    NewsItemRecord.published_at >= window_start,
                    NewsItemRecord.published_at <= window_end,
                )
            ).scalar_one_or_none()
            is not None
        ):
            return True

    return False


def save_news_item(db: Session, item: NewsItemCreate) -> Optional[NewsItemRecord]:
    """
    Saves a single news item. Silently ignores duplicates based on multi-level checks.
    Returns the created NewsItemRecord if inserted, or None if already exists.
    """
    if is_duplicate_record(db, item):
        return None

    record = NewsItemRecord(
        id=uuid.uuid4(),
        ticker=item.ticker,
        title=item.title,
        description=item.description,
        source=item.source,
        source_url=str(item.source_url) if item.source_url else None,
        source_id=item.source_id,
        category=item.category,
        published_at=item.published_at,
        scraped_at=datetime.now(timezone.utc),
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    except IntegrityError:
        db.rollback()
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving news item {item.source}:{item.source_id}: {e}")
        return None


def save_news_items_batch(db: Session, items: List[NewsItemCreate]) -> int:
    """
    Saves a batch of news items, deduplicating both in-memory within the batch
    and against existing records in the database.
    Returns the count of newly inserted records.
    """
    if not items:
        return 0

    # In-memory deduplication of the incoming batch first
    seen_keys = set()
    deduped_items: List[NewsItemCreate] = []

    for item in items:
        # Key 1: source + source_id
        k1 = f"src_{item.source}_{item.source_id}"
        # Key 2: source_url
        k2 = f"url_{str(item.source_url).strip()}" if item.source_url else None
        # Key 3: ticker + title + published_at date
        pub_str = item.published_at.strftime("%Y%m%d%H%M") if item.published_at else ""
        k3 = f"meta_{item.ticker or ''}_{item.title.strip().lower()}_{pub_str}"

        if k1 in seen_keys:
            continue
        if k2 and k2 in seen_keys:
            continue
        if k3 in seen_keys:
            continue

        seen_keys.add(k1)
        if k2:
            seen_keys.add(k2)
        seen_keys.add(k3)
        deduped_items.append(item)

    inserted_count = 0
    for item in deduped_items:
        res = save_news_item(db, item)
        if res:
            inserted_count += 1

    return inserted_count


def clean_database_duplicates(db: Session) -> int:
    """
    Scans the database and cleans any existing duplicates, keeping the earliest record.
    Checks for:
    - Same (source, source_id)
    - Same source_url (non-null)
    - Same (title, published_at)
    - Same (ticker, title) on same date
    Returns the total number of duplicate records removed.
    """
    logger.info("Running database deduplication sweep...")
    total_removed = 0

    # 1. Clean duplicates by (title, published_at)
    dup_groups = (
        db.query(
            NewsItemRecord.title,
            NewsItemRecord.published_at,
            func.count(NewsItemRecord.id),
        )
        .group_by(NewsItemRecord.title, NewsItemRecord.published_at)
        .having(func.count(NewsItemRecord.id) > 1)
        .all()
    )

    for title, pub_at, count in dup_groups:
        records = (
            db.query(NewsItemRecord)
            .filter(
                NewsItemRecord.title == title,
                NewsItemRecord.published_at == pub_at,
            )
            .order_by(NewsItemRecord.scraped_at.asc())
            .all()
        )
        # Keep the first, delete the rest
        for r in records[1:]:
            db.delete(r)
            total_removed += 1

    db.commit()

    # 2. Clean duplicates by non-empty source_url
    url_groups = (
        db.query(NewsItemRecord.source_url, func.count(NewsItemRecord.id))
        .filter(NewsItemRecord.source_url.isnot(None), NewsItemRecord.source_url != "")
        .group_by(NewsItemRecord.source_url)
        .having(func.count(NewsItemRecord.id) > 1)
        .all()
    )

    for url, count in url_groups:
        records = (
            db.query(NewsItemRecord)
            .filter(NewsItemRecord.source_url == url)
            .order_by(NewsItemRecord.scraped_at.asc())
            .all()
        )
        for r in records[1:]:
            db.delete(r)
            total_removed += 1

    db.commit()

    # 3. Clean duplicates by identical (title, source) within 24 hours
    title_source_groups = (
        db.query(
            NewsItemRecord.title,
            NewsItemRecord.source,
            func.count(NewsItemRecord.id),
        )
        .group_by(NewsItemRecord.title, NewsItemRecord.source)
        .having(func.count(NewsItemRecord.id) > 1)
        .all()
    )

    for title, source, count in title_source_groups:
        records = (
            db.query(NewsItemRecord)
            .filter(
                NewsItemRecord.title == title,
                NewsItemRecord.source == source,
            )
            .order_by(NewsItemRecord.published_at.asc(), NewsItemRecord.scraped_at.asc())
            .all()
        )
        if len(records) > 1:
            base_rec = records[0]
            for r in records[1:]:
                if base_rec.published_at and r.published_at:
                    diff_sec = abs((r.published_at - base_rec.published_at).total_seconds())
                    if diff_sec <= 86400:  # within 24 hours
                        db.delete(r)
                        total_removed += 1
                        continue
                base_rec = r

    db.commit()

    if total_removed > 0:
        logger.info(f"Deduplication sweep completed: removed {total_removed} redundant records.")
    else:
        logger.info("Deduplication sweep completed: no duplicate records found.")

    return total_removed


def get_latest_checkpoint(db: Session) -> dict:
    """
    Returns the latest checkpoint (scraped_at and id) so downstream applications
    can track where to resume fetching news.
    """
    latest = (
        db.query(NewsItemRecord)
        .order_by(NewsItemRecord.scraped_at.desc(), NewsItemRecord.id.desc())
        .first()
    )
    total_count = db.query(NewsItemRecord).count()
    if latest:
        return {
            "latest_scraped_at": latest.scraped_at.isoformat() if latest.scraped_at else None,
            "last_id": str(latest.id),
            "total_news": total_count,
        }
    return {
        "latest_scraped_at": None,
        "last_id": None,
        "total_news": 0,
    }


def purge_old_descriptions(db: Session, days: int = settings.body_retention_days) -> int:
    """
    Implements the retention policy:
    Keeps metadata (ticker, title, published_at, category, source_url) permanently,
    while clearing the heavy 'description' text bodies older than `days`.
    Returns the number of rows updated.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        update(NewsItemRecord)
        .where(NewsItemRecord.published_at < cutoff, NewsItemRecord.description.isnot(None))
        .values(description=None)
    )
    result = db.execute(stmt)
    db.commit()
    rows_affected = result.rowcount
    if rows_affected > 0:
        logger.info(f"Retention policy: Purged description bodies for {rows_affected} records older than {days} days.")
    return rows_affected
