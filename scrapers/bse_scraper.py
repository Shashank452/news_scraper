"""
BSE (Bombay Stock Exchange) Announcements Scraper.
Fetches real-time corporate announcements from BSE's official feeds.
"""

from datetime import datetime
import re
from typing import List, Optional
import xml.etree.ElementTree as ET
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
    Uses the real-time XML/RSS disclosure feed with JSON API fallback.
    """

    RSS_FEED_URL = "https://www.bseindia.com/data/xml/announcements.aspx"
    API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
    ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"

    def __init__(self, rate_limit_interval: float = 2.0):
        super().__init__(name="bse", rate_limit_interval=rate_limit_interval)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def _parse_bse_datetime(self, dt_str: Optional[str]) -> datetime:
        """Parses BSE date strings like '06-Nov-2026 19:23:28' or '2024-05-10T15:30:00'."""
        if not dt_str:
            return datetime.now(IST_TZ)

        formats = [
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(dt_str.strip(), fmt)
                return dt.replace(tzinfo=IST_TZ)
            except ValueError:
                continue

        return datetime.now(IST_TZ)

    def fetch_latest(self, max_items: int = 100) -> List[NewsItemCreate]:
        """
        Fetches latest corporate announcements from BSE RSS feed.
        """
        self.rate_limiter.wait()
        items: List[NewsItemCreate] = []

        try:
            logger.info("Fetching corporate announcements feed from BSE...")
            resp = self.session.get(self.RSS_FEED_URL, timeout=self.timeout)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                logger.warning("BSE RSS response missing channel element.")
                return []

            xml_items = channel.findall("item")[:max_items]

            for entry in xml_items:
                raw_title = clean_text(entry.findtext("title"))
                link = entry.findtext("link")
                raw_desc = clean_text(entry.findtext("description"))
                pub_date_str = entry.findtext("pubDate")

                if not raw_title:
                    continue

                # Extract scrip code if present in format: "Company Name Ltd (500325)"
                scrip_match = re.search(r"\((\d{4,6})\)", raw_title)
                scrip_code = scrip_match.group(1) if scrip_match else None
                company_name = re.sub(r"\(\d{4,6}\)", "", raw_title).strip()

                published_at = self._parse_bse_datetime(pub_date_str)
                category = categorize_announcement(raw_desc or raw_title)

                # Extract unique ID from attachment URL or generate unique key
                source_id = None
                if link and "/AttachLive/" in link:
                    source_id = link.split("/AttachLive/")[-1].replace(".pdf", "")
                if not source_id:
                    source_id = f"{scrip_code or 'bse'}_{published_at.strftime('%Y%m%d%H%M%S')}"

                ticker = scrip_code if scrip_code else normalize_ticker(company_name)

                item = NewsItemCreate(
                    ticker=ticker,
                    title=f"{company_name}: {raw_desc[:120]}" if raw_desc else raw_title,
                    description=raw_desc if raw_desc else None,
                    source="bse",
                    source_url=link,
                    source_id=f"bse_{source_id}",
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
