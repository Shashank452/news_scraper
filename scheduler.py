"""
Background Scheduler for News Scraper.
Runs adaptive polling (fast during Indian market hours, backoff during off-hours),
and scheduled nightly retention cleanup jobs.
"""

import signal
import sys
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from aggregators.news_aggregator import NewsAggregator
from config import IST_TIMEZONE, is_market_hours, settings
from database import SessionLocal, init_db, purge_old_descriptions
from utils import logger


class NewsSchedulerService:
    """
    Manages periodic news scraping and scheduled database maintenance.
    """

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=IST_TIMEZONE)
        self.aggregator = NewsAggregator()
        self._running = False

    def scheduled_scrape_job(self) -> None:
        """Executes a scraping cycle, adapting logic according to market schedule."""
        market_open = is_market_hours()
        logger.info(
            f"Scheduler trigger: Market is {'OPEN' if market_open else 'CLOSED'} (IST)."
        )

        db = SessionLocal()
        try:
            summary = self.aggregator.run_cycle(db=db)
            logger.info(f"Scheduled cycle completed: {summary}")
        except Exception as e:
            logger.error(f"Error during scheduled scraping cycle: {e}")
        finally:
            db.close()

    def scheduled_cleanup_job(self) -> None:
        """Purges news text bodies older than configured retention days (2:00 AM IST daily)."""
        logger.info("Executing scheduled retention policy cleanup...")
        db = SessionLocal()
        try:
            purged = purge_old_descriptions(db, days=settings.body_retention_days)
            logger.info(f"Retention cleanup finished. Rows cleared: {purged}")
        except Exception as e:
            logger.error(f"Error during retention cleanup: {e}")
        finally:
            db.close()

    def start(self) -> None:
        """Configures job intervals and starts the background scheduler."""
        init_db()

        # Job 1: Ingestion cycle (every 120s by default)
        self.scheduler.add_job(
            self.scheduled_scrape_job,
            trigger=IntervalTrigger(seconds=settings.scrape_interval_market_seconds),
            id="market_news_ingestion",
            name="Market News Ingestion",
            replace_existing=True,
        )

        # Job 2: Nightly retention cleanup at 02:00 AM IST
        self.scheduler.add_job(
            self.scheduled_cleanup_job,
            trigger=CronTrigger(hour=2, minute=0, timezone=IST_TIMEZONE),
            id="retention_cleanup",
            name="Daily Retention Cleanup",
            replace_existing=True,
        )

        self.scheduler.start()
        self._running = True
        logger.info("NewsSchedulerService started successfully.")

        # Run an initial cycle immediately on startup
        self.scheduled_scrape_job()

    def stop(self) -> None:
        """Gracefully shuts down scheduler."""
        if self._running:
            logger.info("Stopping NewsSchedulerService...")
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("NewsSchedulerService stopped.")


def run_scheduler_daemon():
    """CLI entrypoint to run scheduler continuously with signal handlers."""
    service = NewsSchedulerService()

    def handle_shutdown(signum, frame):
        logger.info(f"Received termination signal ({signum}). Exiting...")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    service.start()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        service.stop()


if __name__ == "__main__":
    run_scheduler_daemon()
