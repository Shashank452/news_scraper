"""
Common utilities: Logging, text sanitization, rate limiting, and ticker normalization.
"""

import html
import logging
import re
import sys
import time
from typing import Optional
from core.config import settings

# Setup unified logger
logger = logging.getLogger("news_scraper")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))


def clean_text(raw_text: Optional[str]) -> str:
    """
    Cleans raw text by unescaping HTML entities, stripping HTML tags,
    and collapsing multiple spaces and newlines.
    """
    if not raw_text:
        return ""
    # Unescape HTML entities
    unescaped = html.unescape(raw_text)
    # Strip HTML tags
    no_html = re.sub(r"<[^>]+>", " ", unescaped)
    # Normalize whitespaces
    cleaned = re.sub(r"\s+", " ", no_html).strip()
    return cleaned


def normalize_ticker(symbol: Optional[str]) -> Optional[str]:
    """
    Normalizes a ticker symbol to uppercase, stripping exchange suffixes like .NS / .BO.
    Returns None if symbol is invalid or empty.
    """
    if not symbol:
        return None
    cleaned = symbol.strip().upper()
    # Strip common exchange suffixes
    cleaned = re.sub(r"\.(NS|BO|BSE|NSE)$", "", cleaned)
    # Basic validation: alphanumeric with optional hyphens/underscores (e.g., M&M -> MM or keep alphanumeric)
    cleaned = re.sub(r"[^\w\-&]", "", cleaned)
    return cleaned if cleaned else None


class RateLimiter:
    """Simple rate limiter ensuring a minimum delay between consecutive calls."""

    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval = min_interval_seconds
        self.last_call_time = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call_time = time.time()
