#!/usr/bin/env python3
"""
================================================================================
Indian Equities News Scraper & Aggregator Service - Master Runner
================================================================================

This module orchestrates all news scraper operations into a single coordinated process:
  1. Initializes the database schema and verifies all performance/cursor indexes.
  2. Executes initial deduplication and retention sweep.
  3. Configures and starts the background scheduler:
     - Scrapes news every 15 minutes (BSE, NSE, Media, Regulatory feeds).
     - Multi-level deduplication prevents identical announcements and duplicate URLs.
     - Scheduled nightly retention cleanup (purging old text bodies).
  4. Starts the FastAPI REST API server (with interactive UI at http://<host>:<port>/)
     featuring cursor-based streaming endpoints (/news/incremental and /news/checkpoint)
     so downstream applications can resume exactly where they left off.
  5. Provides clean signal handling (SIGINT / SIGTERM) for graceful shutdown.

Usage:
  python run.py                         # Runs both API server and 15-min background scraper
  python run.py --scrape-interval 15    # Explicitly set 15-minute scrape interval
  python run.py --port 8000             # Specify API port
  python run.py --no-server             # Run background scheduler daemon only
  python run.py --no-scheduler          # Run FastAPI REST server only
  python run.py --cleanup-now           # Run database duplicate cleanup and retention purge on start
================================================================================
"""

import argparse
import os
import signal
import sys
import time
try:
    import pysqlite3
    sys.modules['sqlite3'] = pysqlite3
except ImportError:
    pass

import uvicorn

from core.config import settings
from core.database import (
    SessionLocal,
    clean_database_duplicates,
    get_latest_checkpoint,
    init_db,
    purge_old_descriptions,
)
from core.scheduler import NewsSchedulerService
from core.utils import logger


def parse_arguments() -> argparse.Namespace:
    """Parses command-line configuration arguments."""
    parser = argparse.ArgumentParser(
        description="Indian Equities News Scraper & Aggregator Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        type=str,
        default=getattr(settings, "api_host", "127.0.0.1"),
        help="Host address to bind the API server to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=getattr(settings, "api_port", 8000),
        help="Port number to bind the API server to.",
    )
    parser.add_argument(
        "--scrape-interval",
        type=int,
        default=15,
        help="Scraping interval in minutes (default: 15 min).",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        default=False,
        help="Run only the background scheduler daemon (no HTTP server).",
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        default=False,
        help="Run only the HTTP server (no background scraping).",
    )
    parser.add_argument(
        "--no-initial-scrape",
        action="store_true",
        default=False,
        help="Skip the immediate scrape cycle on startup.",
    )
    parser.add_argument(
        "--cleanup-now",
        action="store_true",
        default=False,
        help="Execute database deduplication and retention purge immediately on startup.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable uvicorn auto-reload (for development).",
    )
    return parser.parse_args()


def print_banner(args: argparse.Namespace) -> None:
    """Displays startup banner with service details and endpoints."""
    banner = f"""
================================================================================
       INDIAN EQUITIES NEWS SCRAPER & AGGREGATOR SERVICE
================================================================================
  Database URL    : {settings.database_url}
  API Host        : {args.host}:{args.port}
  Scrape Interval : Every {args.scrape_interval} minutes
  Retention Purge : Description bodies older than {settings.body_retention_days} days
  UI Dashboard    : http://{args.host}:{args.port}/
  API Docs        : http://{args.host}:{args.port}/docs
  MCP Server (SSE): http://{args.host}:{args.port}/mcp/sse
  Incremental API : http://{args.host}:{args.port}/news/incremental
  Checkpoint API  : http://{args.host}:{args.port}/news/checkpoint
================================================================================
"""
    print(banner, flush=True)


def main() -> None:
    """Main orchestration entrypoint."""
    args = parse_arguments()
    print_banner(args)

    # 1. Initialize Database Schema & Performance/Cursor Indexes
    logger.info("Step 1/3: Initializing database schema and performance indexes...")
    init_db()

    # 2. Database Deduplication & Maintenance
    db = SessionLocal()
    try:
        if args.cleanup_now:
            logger.info("Executing immediate retention cleanup and duplicate purge...")
            purged = purge_old_descriptions(db, days=settings.body_retention_days)
            logger.info(f"Purged description text for {purged} old records.")

        # Always run a deduplication sweep to ensure existing data is 100% unique
        cleaned = clean_database_duplicates(db)
        if cleaned > 0:
            logger.info(f"Database sanitized: removed {cleaned} redundant duplicate entries.")

        # Log current database cursor state for downstream consumers
        checkpoint = get_latest_checkpoint(db)
        logger.info(
            f"Current database checkpoint: total={checkpoint['total_news']}, "
            f"latest_scraped_at={checkpoint['latest_scraped_at']}, "
            f"last_id={checkpoint['last_id']}"
        )
    finally:
        db.close()

    # 3. Configure & Start Scheduler Service
    scheduler_service = None
    if not args.no_scheduler:
        logger.info(
            f"Step 2/3: Starting background scheduler (interval: {args.scrape_interval} min)..."
        )
        scheduler_service = NewsSchedulerService(
            interval_minutes=args.scrape_interval,
            run_initial_scrape=not args.no_initial_scrape,
        )
        scheduler_service.start()
    else:
        logger.info("Step 2/3: Background scheduler skipped (--no-scheduler).")

    # Setup Graceful Shutdown Handler
    def shutdown_handler(signum, frame):
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else signum
        logger.info(f"Received shutdown signal ({sig_name}). Cleaning up...")
        if scheduler_service:
            scheduler_service.stop()
        logger.info("Shutdown completed cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # 4. Start Server or Run in Scheduler-Only Loop
    if not args.no_server:
        logger.info(f"Step 3/3: Starting Uvicorn API server on {args.host}:{args.port}...")
        try:
            # Using uvicorn.run directly
            uvicorn.run(
                "api.news_api:app",
                host=args.host,
                port=args.port,
                reload=args.reload,
                log_level=settings.log_level.lower(),
            )
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            if scheduler_service:
                scheduler_service.stop()
            logger.info("News Scraper service stopped.")
    else:
        logger.info("Running in scheduler-only mode (--no-server). Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            if scheduler_service:
                scheduler_service.stop()
            logger.info("News Scraper scheduler stopped.")


if __name__ == "__main__":
    main()
