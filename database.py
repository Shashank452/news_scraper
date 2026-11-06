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
    select,
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
    ticker = Column(String(50), nullable=True, index=True)
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
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Ensure identical announcements from same source are never duplicated
        UniqueConstraint("source", "source_id", name="uq_source_source_id"),
        # Composite index for fast ticker history queries
        Index("ix_news_ticker_published", "ticker", "published_at"),
        # Composite index for time-range lookups by source
        Index("ix_news_source_published", "source", "published_at"),
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
    """Creates all database tables defined in the models."""
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """Dependency for yielding database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_news_item(db: Session, item: NewsItemCreate) -> Optional[NewsItemRecord]:
    """
    Saves a single news item. Silently ignores duplicates based on (source, source_id).
    Returns the created NewsItemRecord if inserted, or None if already exists.
    """
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
    Saves a batch of news items, deduplicating each against the database.
    Returns the count of newly inserted records.
    """
    if not items:
        return 0

    inserted_count = 0
    for item in items:
        # Check if record already exists to avoid throwing rollbacks
        exists = (
            db.execute(
                select(NewsItemRecord.id).where(
                    NewsItemRecord.source == item.source,
                    NewsItemRecord.source_id == item.source_id,
                )
            ).scalar_one_or_none()
            is not None
        )
        if exists:
            continue

        res = save_news_item(db, item)
        if res:
            inserted_count += 1

    return inserted_count


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
