"""
Shared pytest fixtures and test configuration.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, NewsItemRecord
from news_model import NewsItemCreate


@pytest.fixture
def in_memory_db():
    """Provides an isolated in-memory SQLite database session for unit tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_news_create():
    """Returns a valid NewsItemCreate instance for testing."""
    return NewsItemCreate(
        ticker="TCS",
        title="TCS announces multi-year strategic AI partnership",
        description="Partnership details and contract value.",
        source="bse",
        source_url="https://www.bseindia.com/pdf/test_tcs.pdf",
        source_id="bse_tcs_001",
        category="order_contract",
        published_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_records(in_memory_db):
    """Populates and returns a set of news records in the in-memory database."""
    now = datetime.now(timezone.utc)
    records = [
        NewsItemRecord(
            ticker="RELIANCE",
            title="Reliance Retail expands store network",
            description="New retail format launches.",
            source="bse",
            source_url="https://bseindia.com/pdf/rel1.pdf",
            source_id="bse_rel_01",
            category="general",
            published_at=now,
        ),
        NewsItemRecord(
            ticker="INFY",
            title="Infosys Q3 net profit increases 8%",
            description="Audited quarterly financials.",
            source="nse",
            source_url="https://nseindia.com/corp/infy1.pdf",
            source_id="nse_infy_01",
            category="financial_results",
            published_at=now,
        ),
        NewsItemRecord(
            ticker="HDFCBANK",
            title="HDFC Bank Board approves interim dividend",
            description="Dividend of Rs 15 per share.",
            source="bse",
            source_url="https://bseindia.com/pdf/hdfc1.pdf",
            source_id="bse_hdfc_01",
            category="dividend",
            published_at=now,
        ),
    ]
    in_memory_db.add_all(records)
    in_memory_db.commit()
    return records
