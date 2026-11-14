"""
Tests for database storage, deduplication, and retention policies.
"""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.database import (
    Base,
    NewsItemRecord,
    clean_database_duplicates,
    purge_old_descriptions,
    save_news_item,
    save_news_items_batch,
)
from core.news_model import NewsItemCreate


@pytest.fixture
def test_db():
    """In-memory SQLite database fixture for isolated tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_save_and_deduplicate_news_items(test_db):
    now = datetime.now(timezone.utc)
    item1 = NewsItemCreate(
        ticker="INFY",
        title="Infosys announces strategic collaboration",
        description="Collaboration details",
        source="bse",
        source_url="https://bseindia.com/sample1",
        source_id="bse_99999",
        category="general",
        published_at=now,
    )

    # First insert should succeed
    record1 = save_news_item(test_db, item1)
    assert record1 is not None
    assert record1.ticker == "INFY"

    # Second insert with same (source, source_id) must be skipped (deduplicated)
    record2 = save_news_item(test_db, item1)
    assert record2 is None

    # Verify only one row exists in DB
    count = test_db.query(NewsItemRecord).count()
    assert count == 1


def test_batch_deduplication(test_db):
    now = datetime.now(timezone.utc)
    items = [
        NewsItemCreate(
            ticker="TCS",
            title="TCS Q3 Results",
            source="nse",
            source_id="nse_001",
            published_at=now,
        ),
        NewsItemCreate(
            ticker="WIPRO",
            title="Wipro Appoints New Director",
            source="nse",
            source_id="nse_002",
            published_at=now,
        ),
    ]

    inserted = save_news_items_batch(test_db, items)
    assert inserted == 2

    # Running batch again with one duplicate and one new item
    new_items = [
        items[0],  # Duplicate
        NewsItemCreate(
            ticker="HCLTECH",
            title="HCL Wins Cloud Deal",
            source="nse",
            source_id="nse_003",
            published_at=now,
        ),
    ]

    inserted_second = save_news_items_batch(test_db, new_items)
    assert inserted_second == 1  # Only HCLTECH added

    total = test_db.query(NewsItemRecord).count()
    assert total == 3


def test_data_retention_purge(test_db):
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=120)  # > 90 days ago

    # Create an old record with description
    old_record = NewsItemRecord(
        ticker="SBIN",
        title="Old SBI Announcement",
        description="This detailed body text should be purged after 90 days",
        source="bse",
        source_id="bse_old_1",
        published_at=old_date,
    )
    # Create a fresh record
    fresh_record = NewsItemRecord(
        ticker="HDFCBANK",
        title="Fresh HDFC Announcement",
        description="This fresh body text must be kept",
        source="bse",
        source_id="bse_fresh_1",
        published_at=now,
    )
    test_db.add_all([old_record, fresh_record])
    test_db.commit()

    # Execute purge
    purged_count = purge_old_descriptions(test_db, days=90)
    assert purged_count == 1

    # Verify old record's metadata remains intact but description is None
    test_db.refresh(old_record)
    test_db.refresh(fresh_record)

    assert old_record.title == "Old SBI Announcement"
    assert old_record.description is None  # Body cleared!

    assert fresh_record.title == "Fresh HDFC Announcement"
    assert fresh_record.description == "This fresh body text must be kept"


def test_url_and_title_deduplication(test_db):
    now = datetime.now(timezone.utc)
    item1 = NewsItemCreate(
        ticker="INFY",
        title="Infosys Board Meeting",
        source="bse",
        source_url="https://bseindia.com/pdf1",
        source_id="bse_id_100",
        published_at=now,
    )
    save_news_item(test_db, item1)

    # Attempt to insert same URL with different source_id
    item2 = NewsItemCreate(
        ticker="INFY",
        title="Infosys Outcome",
        source="bse",
        source_url="https://bseindia.com/pdf1",
        source_id="bse_id_101",
        published_at=now + timedelta(minutes=5),
    )
    res2 = save_news_item(test_db, item2)
    assert res2 is None  # Skipped due to identical URL!

    # Attempt to insert identical ticker + title within 24h
    item3 = NewsItemCreate(
        ticker="INFY",
        title="Infosys Board Meeting",
        source="bse",
        source_url="https://bseindia.com/pdf2",
        source_id="bse_id_102",
        published_at=now + timedelta(minutes=10),
    )
    res3 = save_news_item(test_db, item3)
    assert res3 is None  # Skipped due to duplicate title/ticker within 24h!

    assert test_db.query(NewsItemRecord).count() == 1


def test_clean_database_duplicates(test_db):
    now = datetime.now(timezone.utc)
    # Manually insert duplicates into table
    r1 = NewsItemRecord(
        ticker="TCS",
        title="TCS Duplicate Announcement",
        source="bse",
        source_id="bse_dup_1",
        published_at=now,
    )
    r2 = NewsItemRecord(
        ticker="TCS",
        title="TCS Duplicate Announcement",
        source="bse",
        source_id="bse_dup_2",
        published_at=now,
    )
    test_db.add_all([r1, r2])
    test_db.commit()

    assert test_db.query(NewsItemRecord).count() == 2
    removed = clean_database_duplicates(test_db)
    assert removed == 1
    assert test_db.query(NewsItemRecord).count() == 1
