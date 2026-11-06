"""
News Aggregator: Orchestrates scrapers, normalizes formats,
and coordinates batch deduplication into the database.
"""

from typing import Dict, List
from sqlalchemy.orm import Session

from database import SessionLocal, save_news_items_batch
from news_model import NewsItemCreate
from scrapers.base_scraper import BaseScraper
from scrapers.bse_scraper import BSEScraper
from scrapers.nse_scraper import NSEScraper
from utils import logger


class NewsAggregator:
    """
    Coordinates multi-source scraping (BSE, NSE, etc.), collects announcements,
    and inserts new records into the database while skipping duplicates.
    """

    def __init__(self, scrapers: List[BaseScraper] = None):
        if scrapers is None:
            self.scrapers: List[BaseScraper] = [
                BSEScraper(),
                NSEScraper(),
            ]
        else:
            self.scrapers = scrapers

    def run_cycle(self, db: Session = None) -> Dict[str, dict]:
        """
        Runs one ingestion cycle across all registered scrapers.
        Returns a summary dictionary of results per source.
        """
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True

        cycle_summary: Dict[str, dict] = {}

        try:
            for scraper in self.scrapers:
                logger.info(f"Running aggregation for source: {scraper.name}")
                items = scraper.fetch_latest()
                new_items_count = save_news_items_batch(db, items)

                cycle_summary[scraper.name] = {
                    "total_fetched": len(items),
                    "new_inserted": new_items_count,
                    "status": "ok" if scraper.is_healthy() else "error",
                    "error": scraper.get_last_error(),
                }
                logger.info(
                    f"Source {scraper.name}: fetched {len(items)}, newly inserted {new_items_count}."
                )

            return cycle_summary

        finally:
            if should_close_db:
                db.close()
