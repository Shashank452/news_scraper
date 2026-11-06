"""
Configuration management for the News Scraper system.
Loads settings from environment variables or .env file with sensible defaults.
"""

from datetime import datetime, time
import os
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )

        database_url: str = Field(
            default="sqlite:///./news.db",
            description="Database connection URL (PostgreSQL or SQLite fallback)",
        )
        api_host: str = Field(default="127.0.0.1", description="API host to bind")
        api_port: int = Field(default=8000, description="API port")
        api_key: str = Field(
            default="dev_secret_api_key_change_in_production",
            description="Secret key required for API header authentication",
        )
        log_level: str = Field(default="INFO", description="Logging level")
        
        # Scraper polling intervals (seconds)
        scrape_interval_market_seconds: int = Field(
            default=120,
            description="Polling interval during market hours (9:00-15:30 IST)",
        )
        scrape_interval_off_hours_seconds: int = Field(
            default=900,
            description="Polling interval outside market hours",
        )
        request_timeout_seconds: int = Field(
            default=15,
            description="HTTP request timeout in seconds",
        )
        user_agent: str = Field(
            default=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            description="Default HTTP User-Agent header",
        )
        body_retention_days: int = Field(
            default=90,
            description="Days to retain news body text before nightly purge",
        )

    settings = Settings()

except ImportError:
    # Lightweight fallback if pydantic-settings is not yet installed
    from dotenv import load_dotenv

    load_dotenv()

    class FallbackSettings:
        database_url: str = os.getenv("DATABASE_URL", "sqlite:///./news.db")
        api_host: str = os.getenv("API_HOST", "127.0.0.1")
        api_port: int = int(os.getenv("API_PORT", "8000"))
        api_key: str = os.getenv("API_KEY", "dev_secret_api_key_change_in_production")
        log_level: str = os.getenv("LOG_LEVEL", "INFO")
        scrape_interval_market_seconds: int = int(
            os.getenv("SCRAPE_INTERVAL_MARKET_SECONDS", "120")
        )
        scrape_interval_off_hours_seconds: int = int(
            os.getenv("SCRAPE_INTERVAL_OFF_HOURS_SECONDS", "900")
        )
        request_timeout_seconds: int = int(
            os.getenv("REQUEST_TIMEOUT_SECONDS", "15")
        )
        user_agent: str = os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        body_retention_days: int = int(os.getenv("BODY_RETENTION_DAYS", "90"))

    settings = FallbackSettings()


IST_TIMEZONE = ZoneInfo("Asia/Kolkata")
MARKET_OPEN_TIME = time(9, 0)
MARKET_CLOSE_TIME = time(15, 30)


def get_current_ist_time() -> datetime:
    """Returns current datetime in IST (Indian Standard Time)."""
    return datetime.now(IST_TIMEZONE)


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """
    Checks if given datetime (or current time if omitted) falls
    within Indian Equities trading hours: Monday - Friday, 09:00 to 15:30 IST.
    """
    if dt is None:
        dt = get_current_ist_time()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST_TIMEZONE)
    else:
        dt = dt.astimezone(IST_TIMEZONE)

    # Monday is 0, Sunday is 6
    if dt.weekday() >= 5:
        return False

    current_time = dt.time()
    return MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME
