"""
One-off execution script to test and run scrapers directly from the command line.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aggregators.news_aggregator import NewsAggregator
from database import init_db
from scrapers.bse_scraper import BSEScraper
from scrapers.nse_scraper import NSEScraper
from scrapers.media_news_scraper import MediaNewsScraper
from scrapers.regulatory_policy_scraper import RegulatoryPolicyScraper
from utils import logger


def main():
    parser = argparse.ArgumentParser(description="Run News Scraper CLI")
    parser.add_argument(
        "--source",
        choices=["all", "bse", "nse", "media", "policy"],
        default="all",
        help="Specify which news source to scrape (default: all)",
    )
    args = parser.parse_args()

    init_db()

    scrapers = []
    if args.source in ("all", "bse"):
        scrapers.append(BSEScraper())
    if args.source in ("all", "nse"):
        scrapers.append(NSEScraper())
    if args.source in ("all", "media"):
        scrapers.append(MediaNewsScraper())
    if args.source in ("all", "policy"):
        scrapers.append(RegulatoryPolicyScraper())

    aggregator = NewsAggregator(scrapers=scrapers)
    logger.info(f"Starting scraping cycle for sources: {[s.name for s in scrapers]}")

    summary = aggregator.run_cycle()
    print("\n--- Cycle Execution Summary ---")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
