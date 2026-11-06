"""
NSE (National Stock Exchange) Corporate Announcements Scraper.
Uses browser impersonation (curl_cffi) to pass Akamai/WAF defenses,
warm up session cookies, and retrieve live corporate announcements JSON.
"""

from datetime import datetime
import time
from typing import List, Optional
from zoneinfo import ZoneInfo

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as curl_requests
    HAS_CURL_CFFI = False

from config import settings
from news_model import NewsItemCreate, categorize_announcement
from scrapers.base_scraper import BaseScraper
from utils import clean_text, logger, normalize_ticker

IST_TZ = ZoneInfo("Asia/Kolkata")


class NSEScraper(BaseScraper):
    """
    Scrapes real-time corporate announcements from NSE India.
    Implements session warmup and automatic cookie renewal with Chrome impersonation.
    """

    HOME_URL = "https://www.nseindia.com"
    API_URL = "https://www.nseindia.com/api/corporate-announcements?index=equities"
    ARCHIVE_BASE_URL = "https://nsearchives.nseindia.com/corporate"

    def __init__(self, rate_limit_interval: float = 2.0):
        super().__init__(name="nse", rate_limit_interval=rate_limit_interval)
        self.session = curl_requests.Session()
        self._session_initialized = False
        self._session_created_at = 0.0

    def _get_request_kwargs(self) -> dict:
        """Helper to attach browser impersonation kwargs if curl_cffi is available."""
        kwargs = {"timeout": self.timeout}
        if HAS_CURL_CFFI:
            kwargs["impersonate"] = "chrome124"
        return kwargs

    def _ensure_session(self) -> bool:
        """
        Visits the NSE homepage to establish session cookies.
        Renews session if older than 5 minutes.
        """
        now = time.time()
        if self._session_initialized and (now - self._session_created_at) < 300:
            return True

        try:
            logger.info("Initializing NSE session and cookies...")
            self.rate_limiter.wait()
            resp = self.session.get(self.HOME_URL, **self._get_request_kwargs())
            if resp.status_code == 200:
                self._session_initialized = True
                self._session_created_at = now
                logger.info(f"NSE session initialized successfully (cookies: {len(self.session.cookies)}).")
                return True
            else:
                logger.warning(f"Failed to initialize NSE session, HTTP status: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error establishing NSE session: {e}")
            return False

    def _parse_nse_datetime(self, dt_str: Optional[str]) -> datetime:
        """Parses NSE date format like '06-Nov-2026 19:26:06' or '06-11-2026 16:30:15'."""
        if not dt_str:
            return datetime.now(IST_TZ)

        formats = [
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(dt_str.strip(), fmt)
                return dt.replace(tzinfo=IST_TZ)
            except ValueError:
                continue

        return datetime.now(IST_TZ)

    def fetch_latest(self) -> List[NewsItemCreate]:
        """
        Fetches latest corporate announcements from NSE.
        """
        if not self._ensure_session():
            self._last_error = "Could not initialize NSE session"
            return []

        self.rate_limiter.wait()
        items: List[NewsItemCreate] = []

        headers = {
            "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            "Accept": "application/json, text/plain, */*",
        }

        try:
            logger.info("Fetching corporate announcements from NSE...")
            kwargs = self._get_request_kwargs()
            kwargs["headers"] = headers

            resp = self.session.get(self.API_URL, **kwargs)

            # If session expired or unauthorized, reset session once and retry
            if resp.status_code in (401, 403):
                logger.info("NSE session expired (401/403). Renewing session...")
                self._session_initialized = False
                if not self._ensure_session():
                    self._last_error = f"Failed to renew NSE session (HTTP {resp.status_code})"
                    return []
                resp = self.session.get(self.API_URL, **kwargs)

            resp.raise_for_status()
            raw_data = resp.json()

            # Handle either list or {"data": [...]}
            announcements = raw_data if isinstance(raw_data, list) else raw_data.get("data", [])

            for entry in announcements:
                symbol = normalize_ticker(entry.get("symbol") or entry.get("SYMBOL"))
                company_name = entry.get("sm_name") or ""
                desc = clean_text(entry.get("desc") or entry.get("subject") or "")
                att_text = clean_text(entry.get("attchmntText") or "")
                seq_id = str(entry.get("seq_id") or entry.get("an_id") or f"{symbol}_{entry.get('an_dt')}")

                headline = f"{company_name}: {desc}" if company_name and desc else (desc or att_text)
                if not headline:
                    continue

                attachment = entry.get("attchmntFile") or entry.get("attmnt") or entry.get("attachment")
                source_url = None
                if attachment:
                    source_url = attachment if attachment.startswith("http") else f"{self.ARCHIVE_BASE_URL}/{attachment.strip()}"
                else:
                    source_url = f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}"

                published_at = self._parse_nse_datetime(entry.get("an_dt") or entry.get("sort_date"))
                category = categorize_announcement(f"{desc} {att_text}")

                item = NewsItemCreate(
                    ticker=symbol,
                    title=headline,
                    description=att_text if att_text else desc,
                    source="nse",
                    source_url=source_url,
                    source_id=f"nse_{seq_id}",
                    category=category,
                    published_at=published_at,
                )
                items.append(item)

            self._last_error = None
            logger.info(f"NSE Scraper retrieved {len(items)} announcement items.")
            return items

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to fetch NSE announcements: {e}")
            return []
