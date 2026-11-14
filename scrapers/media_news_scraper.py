"""
Media News Scraper: Collects live financial market news and provides
on-demand search for live and historical news using Google News & top Indian media feeds.
"""

from datetime import datetime, timezone
import hashlib
import re
from typing import List, Optional
import urllib.parse
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
import requests

from core.config import settings
from core.news_model import NewsItemCreate, categorize_announcement
from scrapers.base_scraper import BaseScraper
from core.utils import clean_text, logger, normalize_ticker

IST_TZ = ZoneInfo("Asia/Kolkata")


class MediaNewsScraper(BaseScraper):
    """
    Collects live market headlines and provides queryable news search
    across top Indian financial publications (ET, Moneycontrol, Mint, Reuters, etc.).
    """

    ET_FEED_URL = "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"
    MONEYCONTROL_FEED_URL = "https://www.moneycontrol.com/rss/MCtopnews.xml"
    GOOGLE_NEWS_SEARCH_BASE = "https://news.google.com/rss/search"

    def __init__(self, rate_limit_interval: float = 1.0):
        super().__init__(name="media_news", rate_limit_interval=rate_limit_interval)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
        )

    def _parse_rfc822_date(self, dt_str: Optional[str]) -> datetime:
        """Parses RFC-822 date formats commonly used in RSS feeds."""
        if not dt_str:
            return datetime.now(timezone.utc)
        formats = [
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %Z",
            "%d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
        ]
        # Clean string (e.g. 'GMT', 'IST')
        clean_dt = dt_str.strip()
        for fmt in formats:
            try:
                dt = datetime.strptime(clean_dt, fmt)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        return datetime.now(timezone.utc)

    def fetch_latest(self, max_items_per_source: int = 25) -> List[NewsItemCreate]:
        """
        Fetches latest live market headlines from Economic Times and Moneycontrol feeds.
        """
        items: List[NewsItemCreate] = []

        # 1. Economic Times Markets Feed
        try:
            self.rate_limiter.wait()
            resp = self.session.get(self.ET_FEED_URL, timeout=self.timeout)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                if channel is not None:
                    for entry in channel.findall("item")[:max_items_per_source]:
                        title = clean_text(entry.findtext("title"))
                        link = entry.findtext("link")
                        desc = clean_text(entry.findtext("description"))
                        pub_date = self._parse_rfc822_date(entry.findtext("pubDate"))

                        if not title:
                            continue

                        # Generate stable ID from link
                        source_id = hashlib.sha256((link or title).encode()).hexdigest()[:16]
                        category = categorize_announcement(title, desc)

                        item = NewsItemCreate(
                            ticker=None,
                            title=title,
                            description=desc if desc else None,
                            source="economic_times",
                            source_url=link,
                            source_id=f"et_{source_id}",
                            category=category,
                            published_at=pub_date,
                        )
                        items.append(item)
            logger.info(f"Economic Times scraper fetched {len(items)} headlines.")
        except Exception as e:
            logger.warning(f"Failed to fetch Economic Times feed: {e}")

        # 2. Moneycontrol Top News Feed
        try:
            self.rate_limiter.wait()
            resp = self.session.get(self.MONEYCONTROL_FEED_URL, timeout=self.timeout)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                if channel is not None:
                    count_mc = 0
                    for entry in channel.findall("item")[:max_items_per_source]:
                        title = clean_text(entry.findtext("title"))
                        link = entry.findtext("link")
                        desc = clean_text(entry.findtext("description"))
                        pub_date = self._parse_rfc822_date(entry.findtext("pubDate"))

                        if not title:
                            continue

                        source_id = hashlib.sha256((link or title).encode()).hexdigest()[:16]
                        category = categorize_announcement(title, desc)

                        item = NewsItemCreate(
                            ticker=None,
                            title=title,
                            description=desc if desc else None,
                            source="moneycontrol",
                            source_url=link,
                            source_id=f"mc_{source_id}",
                            category=category,
                            published_at=pub_date,
                        )
                        items.append(item)
                        count_mc += 1
            logger.info(f"Moneycontrol scraper fetched {count_mc} headlines.")
        except Exception as e:
            logger.warning(f"Failed to fetch Moneycontrol feed: {e}")

        # 3. World & Global Macro News Feed
        try:
            world_items = self.fetch_world_and_macro_news(max_items=max_items_per_source)
            items.extend(world_items)
            logger.info(f"World & Macro scraper fetched {len(world_items)} articles.")
        except Exception as e:
            logger.warning(f"Failed to fetch World & Macro news during fetch_latest: {e}")

        return items

    def search_news(
        self,
        query: str,
        ticker: Optional[str] = None,
        days_back: Optional[int] = None,
        limit: int = 30,
    ) -> List[NewsItemCreate]:
        """
        Searches live and historical news using Google News RSS search.
        Supports company names, ticker symbols, topics, and date filtering (e.g. when:7d, when:30d).
        """
        self.rate_limiter.wait()
        items: List[NewsItemCreate] = []

        # Construct search query
        parts = []
        if ticker:
            clean_sym = normalize_ticker(ticker)
            parts.append(f'("{clean_sym}" OR "{ticker}")')
        if query:
            parts.append(query)

        # If no specific query or ticker, default to Indian market search
        if not parts:
            parts.append("Indian stock market NSE BSE")

        if days_back:
            parts.append(f"when:{days_back}d")

        q_str = " ".join(parts)
        params = {
            "q": q_str,
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en",
        }

        url = f"{self.GOOGLE_NEWS_SEARCH_BASE}?{urllib.parse.urlencode(params)}"

        try:
            logger.info(f"Searching news for query: '{q_str}'...")
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                return []

            xml_items = channel.findall("item")[:limit]
            for it in xml_items:
                raw_title = clean_text(it.findtext("title"))
                link = it.findtext("link")
                raw_desc = clean_text(it.findtext("description"))
                pub_date = self._parse_rfc822_date(it.findtext("pubDate"))

                if not raw_title:
                    continue

                # Google News titles are usually in format "Headline - Publisher Name"
                publisher = "Google News"
                headline = raw_title
                if " - " in raw_title:
                    tokens = raw_title.rsplit(" - ", 1)
                    headline = tokens[0].strip()
                    publisher = tokens[1].strip()

                source_id = hashlib.sha256((link or raw_title).encode()).hexdigest()[:16]
                category = categorize_announcement(headline, raw_desc)

                item = NewsItemCreate(
                    ticker=ticker.upper() if ticker else None,
                    title=f"[{publisher}] {headline}",
                    description=raw_desc if raw_desc else f"Published by {publisher}",
                    source="media_news",
                    source_url=link,
                    source_id=f"media_{source_id}",
                    category=category,
                    published_at=pub_date,
                )
                items.append(item)

            logger.info(f"News search returned {len(items)} articles for query: '{q_str}'.")
            return items

        except Exception as e:
            logger.error(f"Error executing news search: {e}")
            return []

    WORLD_NEWS_FEEDS = [
        {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        {"name": "The Guardian World", "url": "https://www.theguardian.com/world/rss"},
        {"name": "DW English", "url": "https://rss.dw.com/xml/rss-en-all"},
        {"name": "Global Macro & Markets", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"},
    ]

    def fetch_world_and_macro_news(self, max_items: int = 30) -> List[NewsItemCreate]:
        """
        Fetches global financial markets, geopolitics, US Federal Reserve, crude oil/commodities,
        and world macroeconomic news affecting Indian equities from top global outlets (BBC, The Guardian, DW, Reuters).
        """
        items: List[NewsItemCreate] = []
        seen_keys = set()
        per_feed_limit = max(5, max_items // len(self.WORLD_NEWS_FEEDS))

        for feed in self.WORLD_NEWS_FEEDS:
            feed_name = feed["name"]
            feed_url = feed["url"]
            try:
                self.rate_limiter.wait()
                logger.info(f"Fetching world news from {feed_name}...")
                resp = self.session.get(feed_url, timeout=self.timeout)
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch {feed_name}: status {resp.status_code}")
                    continue

                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                if channel is None:
                    # In some feeds root is rdf or atom
                    channel = root

                count = 0
                for it in channel.findall(".//item"):
                    if count >= per_feed_limit:
                        break

                    raw_title = clean_text(it.findtext("title"))
                    link = it.findtext("link")
                    raw_desc = clean_text(it.findtext("description"))
                    pub_date = self._parse_rfc822_date(it.findtext("pubDate"))

                    if not raw_title:
                        continue

                    # Clean headline
                    headline = raw_title
                    if " - " in raw_title and feed_name == "Global Macro & Markets":
                        tokens = raw_title.rsplit(" - ", 1)
                        headline = tokens[0].strip()
                        publisher = tokens[1].strip()
                    else:
                        publisher = feed_name

                    key = link or headline
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    # Infer sector/ticker tag based on macro themes
                    text = f"{headline} {raw_desc}".lower()
                    ticker = "GLOBAL_MACRO"
                    if any(k in text for k in ["crude", "oil", "opec", "brent", "petroleum", "energy"]):
                        ticker = "CRUDE_OIL, ONGC, RELIANCE, BPCL, IOC"
                    elif any(k in text for k in ["fed", "federal reserve", "powell", "inflation", "treasury", "interest rate", "wall street", "nasdaq", "dow"]):
                        ticker = "US_FED, IT_SECTOR, TCS, INFY, HCLTECH"
                    elif any(k in text for k in ["gold", "precious metal", "silver", "bullion"]):
                        ticker = "GOLD, TITAN, KALYANKJIL, MUTHOOTFIN"
                    elif any(k in text for k in ["tariff", "trade war", "steel", "aluminum", "metals"]):
                        ticker = "METALS, TATASTEEL, JSWSTEEL, HINDALCO"
                    elif any(k in text for k in ["pharma", "fda", "drug", "healthcare"]):
                        ticker = "PHARMA, SUNPHARMA, DRREDDY, CIPLA"
                    elif any(k in text for k in ["auto", "electric vehicle", "ev", "car"]):
                        ticker = "AUTO, TATAMOTORS, M&M, MARUTI"
                    elif any(k in text for k in ["bank", "central bank", "ecb", "boj", "dollar", "currency"]):
                        ticker = "BANKING_SECTOR, HDFCBANK, ICICIBANK, SBIN"

                    source_id = hashlib.sha256(key.encode()).hexdigest()[:16]

                    item = NewsItemCreate(
                        ticker=ticker[:140],
                        title=f"[{publisher}] {headline}",
                        description=raw_desc if raw_desc else f"World report by {publisher}",
                        source="world_news",
                        source_url=link,
                        source_id=f"world_{source_id}",
                        category="global_macro",
                        published_at=pub_date,
                    )
                    items.append(item)
                    count += 1

                logger.info(f"Retrieved {count} articles from {feed_name}.")

            except Exception as e:
                logger.warning(f"Error fetching {feed_name}: {e}")
                continue

        logger.info(f"Total World & Macro articles fetched: {len(items)}")
        return items
