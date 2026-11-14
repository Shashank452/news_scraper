"""
Unit tests for NewsAggregator.
Verifies multi-source scraping orchestration, batching, and error containment.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from aggregators.news_aggregator import NewsAggregator
from core.database import NewsItemRecord
from core.news_model import NewsItemCreate
from scrapers.base_scraper import BaseScraper


class DummyScraper(BaseScraper):
    def __init__(self, name: str, items=None, fail: bool = False):
        super().__init__(name=name)
        self.dummy_items = items or []
        self.fail = fail

    def fetch_latest(self, **kwargs):
        if self.fail:
            self._last_error = "Mocked scraper failure"
            return []
        return self.dummy_items


def test_aggregator_cycle_success(in_memory_db):
    now = datetime.now(timezone.utc)
    item1 = NewsItemCreate(
        ticker="TCS",
        title="TCS Signs Strategic Contract",
        source="dummy_1",
        source_id="d1_001",
        published_at=now,
    )
    item2 = NewsItemCreate(
        ticker="INFY",
        title="Infosys Board Meeting Notice",
        source="dummy_2",
        source_id="d2_001",
        published_at=now,
    )

    scraper1 = DummyScraper(name="source_a", items=[item1])
    scraper2 = DummyScraper(name="source_b", items=[item2])

    aggregator = NewsAggregator(scrapers=[scraper1, scraper2])
    summary = aggregator.run_cycle(db=in_memory_db)

    assert "source_a" in summary
    assert summary["source_a"]["total_fetched"] == 1
    assert summary["source_a"]["new_inserted"] == 1
    assert summary["source_a"]["status"] == "ok"

    assert "source_b" in summary
    assert summary["source_b"]["total_fetched"] == 1
    assert summary["source_b"]["new_inserted"] == 1

    total_in_db = in_memory_db.query(NewsItemRecord).count()
    assert total_in_db == 2


def test_aggregator_duplicate_skipping(in_memory_db):
    now = datetime.now(timezone.utc)
    item = NewsItemCreate(
        ticker="RELIANCE",
        title="Reliance Mega Project",
        source="dummy_source",
        source_id="rel_01",
        published_at=now,
    )

    scraper = DummyScraper(name="dummy_source", items=[item])
    aggregator = NewsAggregator(scrapers=[scraper])

    # First cycle
    summary1 = aggregator.run_cycle(db=in_memory_db)
    assert summary1["dummy_source"]["new_inserted"] == 1

    # Second cycle with same items
    summary2 = aggregator.run_cycle(db=in_memory_db)
    assert summary2["dummy_source"]["total_fetched"] == 1
    assert summary2["dummy_source"]["new_inserted"] == 0  # Deduplicated!


def test_aggregator_error_handling(in_memory_db):
    failing_scraper = DummyScraper(name="failing_source", fail=True)
    aggregator = NewsAggregator(scrapers=[failing_scraper])

    summary = aggregator.run_cycle(db=in_memory_db)
    assert summary["failing_source"]["status"] == "error"
    assert "Mocked scraper failure" in summary["failing_source"]["error"]
