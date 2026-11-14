"""
Base class interface for all exchange and news source scrapers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import requests

from core.config import settings
from core.news_model import NewsItemCreate
from core.utils import RateLimiter, logger


class BaseScraper(ABC):
    """
    Abstract Base Scraper that every source scraper inherits from.
    Encapsulates common HTTP session management, rate-limiting, and error handling.
    """

    def __init__(
        self,
        name: str,
        rate_limit_interval: float = 1.0,
        timeout: int = settings.request_timeout_seconds,
    ):
        self.name = name
        self.rate_limiter = RateLimiter(min_interval_seconds=rate_limit_interval)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_error: Optional[str] = None

    @abstractmethod
    def fetch_latest(self) -> List[NewsItemCreate]:
        """
        Fetches the latest announcements from the source.
        Returns a list of validated NewsItemCreate instances.
        """
        pass

    def is_healthy(self) -> bool:
        """Returns True if the scraper's last fetch was healthy."""
        return self._last_error is None

    def get_last_error(self) -> Optional[str]:
        return self._last_error
