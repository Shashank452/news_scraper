"""
Core infrastructure for News Scraper:
Configuration, Database models & operations, Pydantic schemas,
Rate limiting, Utilities, and Scheduler service.
"""

from core.config import settings, is_market_hours, IST_TIMEZONE
from core.database import (
    Base,
    NewsItemRecord,
    SessionLocal,
    clean_database_duplicates,
    get_db,
    get_latest_checkpoint,
    init_db,
    purge_old_descriptions,
    save_news_item,
    save_news_items_batch,
)
from core.news_model import (
    NewsItemBase,
    NewsItemCreate,
    NewsItemResponse,
    categorize_announcement,
)
from core.scheduler import NewsSchedulerService
from core.utils import RateLimiter, clean_text, logger, normalize_ticker

__all__ = [
    "settings",
    "is_market_hours",
    "IST_TIMEZONE",
    "Base",
    "NewsItemRecord",
    "SessionLocal",
    "clean_database_duplicates",
    "get_db",
    "get_latest_checkpoint",
    "init_db",
    "purge_old_descriptions",
    "save_news_item",
    "save_news_items_batch",
    "NewsItemBase",
    "NewsItemCreate",
    "NewsItemResponse",
    "categorize_announcement",
    "NewsSchedulerService",
    "RateLimiter",
    "clean_text",
    "logger",
    "normalize_ticker",
]
