"""
BSE (Bombay Stock Exchange) Announcements Scraper.
Fetches real-time corporate announcements from BSE API endpoints.
"""

from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
import requests

from config import settings
from news_model import NewsItemCreate, categorize_announcement
from scrapers.base_scraper import BaseScraper
from utils import clean_text, logger, normalize_ticker

IST_TZ = ZoneInfo("Asia/Kolkata")


class BSEScraper(BaseScraper):
    """
    Scrapes real-time corporate announcements from BSE India.
    """

    API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
    ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"

    def __init__(self, rate_limit_interval: float = 2.0):
        super().__init__(name="bse", rate_limit_interval=rate_limit_interval)
        self.session.headers.update(
            {
                "Origin": "https://www.bseindia.com",
                "Referer": "https://www.bseindia.com/",
                "Accept": "application/json, text/plain, */*",
            }
        )

    def _parse_bse_datetime(self, dt_str: Optional[str]) -> datetime:
        """Parses BSE date strings like '2024-05-10T15:30:00' or '10/05/2024 15:30:00'."""
        if not dt_str:
            return datetime.now(IST_TZ)

        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(dt_str.strip(), fmt)
                return dt.replace(tzinfo=IST_TZ)
            except ValueError:
                continue

        return datetime.now(IST_TZ)

    def fetch_latest(self, page_no: int = 1) -> List[NewsItemCreate]:
        """
        Fetches latest corporate announcements from BSE.
        """
        self.rate_limiter.wait()
        items: List[NewsItemCreate] = []

        params = {
            "pageno": str(page_no),
            "strCat": "-1",
            "strPrevDate": "",
            "strScrip": "",
            "strSearch": "P",
            "strToDate": "",
            "strType": "C",
        }

        try:
            logger.info("Fetching latest corporate announcements from BSE...")
            resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            table_data = data.get("Table", [])
            if not table_data and isinstance(data, list):
                table_data = data

            for entry in table_data:
                news_id = str(entry.get("NEWS_ID") or entry.get("SCRIP_CD", "") + "_" + str(entry.get("NEWS_DT", "")))
                if not news_id:
                    continue

                scrip_cd = str(entry.get("SCRIP_CD") or "").strip()
                company_name = entry.get("SLONGNAME") or entry.get("NEWSSUB", "")
                headline = entry.get("HEADLINE") or entry.get("NEWSSUB") or "Corporate Announcement"
                headline = clean_text(headline)
                more_desc = clean_text(entry.get("MORE") or entry.get("CATEGORYNAME") or "")

                attachment = entry.get("ATTACHMENTNAME")
                source_url = None
                if attachment:
                    source_url = f"{self.ATTACHMENT_BASE_URL}/{attachment.strip()}"
                else:
                    source_url = f"https://www.bseindia.com/corporates/ann.html?scrip={scrip_cd}"

                published_at = self._parse_bse_datetime(entry.get("NEWS_DT") or entry.get("DT_TM"))
                category = categorize_announcement(headline, more_desc)

                # Prefer Scrip Code or company ticker
                ticker = scrip_cd if scrip_cd else normalize_ticker(company_name)

                item = NewsItemCreate(
                    ticker=ticker,
                    title=headline,
                    description=more_desc if more_desc else None,
                    source="bse",
                    source_url=source_url,
                    source_id=f"bse_{news_id}",
                    category=category,
                    published_at=published_at,
                )
                items.append(item)

            self._last_error = None
            logger.info(f"BSE Scraper retrieved {len(items)} announcement items.")
            return items

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to fetch BSE announcements: {e}")
            return []
