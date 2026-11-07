"""
Regulatory & Government Policy Scraper:
Tracks government announcements, union cabinet decisions, bills, amendments,
and regulatory policies from IRDAI, RBI, SEBI, and Central Ministries.
"""

from datetime import datetime, timezone
import hashlib
import re
from typing import List, Optional
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
import requests

from config import settings
from news_model import NewsItemCreate, categorize_announcement
from scrapers.base_scraper import BaseScraper
from utils import clean_text, logger

IST_TZ = ZoneInfo("Asia/Kolkata")


class RegulatoryPolicyScraper(BaseScraper):
    """
    Scrapes policy changes, regulatory circulars, and government decisions from:
    1. IRDAI (Insurance Regulatory & Development Authority)
    2. RBI (Reserve Bank of India)
    3. SEBI (Securities & Exchange Board of India)
    4. Government of India Cabinet / PIB Policy announcements
    """

    IRDAI_CIRCULARS_URL = "https://irdai.gov.in/circulars"
    RBI_PRESS_URL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"
    SEBI_RSS_URL = "https://www.sebi.gov.in/sebirss.xml"
    GOOGLE_POLICY_SEARCH = (
        "https://news.google.com/rss/search?q="
        "(IRDAI+OR+\"GST+Council\"+OR+\"Union+Cabinet\"+OR+\"Ministry+of+Finance\"+OR+\"RBI+circular\"+OR+\"Parliament+bill\"+OR+\"SEBI+circular\")+when:7d"
        "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    def __init__(self, rate_limit_interval: float = 1.5):
        super().__init__(name="regulatory_policy", rate_limit_interval=rate_limit_interval)
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

    def _tag_affected_stocks(self, title: str, desc: str = "") -> str:
        """
        Maps regulatory/policy events to the specific stocks and sectors affected.
        For example: IRDAI commission cut -> POLICYBZR, HDFCLIFE, SBILIFE.
        """
        text = f"{title} {desc}".lower()

        # Insurance regulations (IRDAI)
        if any(k in text for k in ["irdai", "insurance", "motor insurance", "commission on insurance", "surrender value"]):
            return "POLICYBZR, HDFCLIFE, SBILIFE, ICICIPRU, MAXFIN"

        # Banking & NBFC policy (RBI)
        if any(k in text for k in ["rbi", "repo rate", "unsecured loan", "nbfc", "priority sector", "capital adequacy"]):
            return "BANKING_SECTOR, BAJFINANCE, HDFCBANK, SBIN, ICICIBANK"

        # Market & Brokerage regulations (SEBI)
        if any(k in text for k in ["sebi", "f&o", "futures and options", "lot size", "algorithmic trading", "sub-broker"]):
            return "ANGELONE, BSE, MCX, MOTILALOFS"

        # Defence procurement / Ministry of Defence
        if any(k in text for k in ["defence", "defense", "ministry of defence", "procurement", "dac approval"]):
            return "HAL, BEL, BDL, MAZDOCK, COCHINSHIP"

        # Energy & Power / RE / Windfall tax
        if any(k in text for k in ["crude oil", "windfall tax", "opec", "petroleum", "power tariff"]):
            return "ONGC, OIL, BPCL, IOC, RELIANCE"

        # Sugar / Ethanol policy
        if any(k in text for k in ["sugar export", "ethanol blending", "cane price"]):
            return "BALRAMCHIN, SHREERAMA, PRAJIND"

        # Telecom
        if any(k in text for k in ["telecom", "dot", "spectrum", "trai", "agr dues"]):
            return "BHARTIARTL, IDEA"

        # Metals & Mining
        if any(k in text for k in ["steel export", "iron ore", "anti-dumping duty", "import duty on metal"]):
            return "TATASTEEL, JSWSTEEL, JINDALSTEL, HINDALCO"

        return "POLICY_REGULATORY"

    def fetch_irdai_circulars(self, max_items: int = 15) -> List[NewsItemCreate]:
        """Scrapes official circulars and regulatory notifications from IRDAI."""
        items: List[NewsItemCreate] = []
        try:
            self.rate_limiter.wait()
            resp = self.session.get(self.IRDAI_CIRCULARS_URL, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                return []

            for row in table.find_all("tr")[1:max_items + 1]:
                cols = row.find_all(["td", "th"])
                if len(cols) < 3:
                    continue

                # Clean cell text
                cell_texts = [clean_text(td.get_text()) for td in cols]
                # Extract link and title
                link_tag = row.find("a")
                subject = ""
                if link_tag:
                    link_txt = clean_text(link_tag.get_text())
                    if link_txt and len(link_txt) > 5 and link_txt.lower() not in ["view", "download", "click here", "non-archived", "archived"]:
                        subject = link_txt

                if not subject:
                    for t in cell_texts:
                        lower_t = t.lower()
                        if (
                            len(t) > 10
                            and not t.startswith("0")
                            and not t.startswith("1")
                            and not t.startswith("2")
                            and "non-archived" not in lower_t
                            and "archived" not in lower_t
                        ):
                            subject = t
                            break

                if not subject:
                    continue

                link = link_tag.get("href") if link_tag else ""
                if link and not link.startswith("http"):
                    link = f"https://irdai.gov.in{link}"

                date_match = re.search(r"\d{2}-\d{2}-\d{4}", " ".join(cell_texts))
                pub_date = datetime.now(timezone.utc)
                if date_match:
                    try:
                        pub_date = datetime.strptime(date_match.group(0), "%d-%m-%Y").replace(tzinfo=IST_TZ)
                    except ValueError:
                        pass

                source_id = hashlib.sha256((link or subject).encode()).hexdigest()[:16]
                affected_stocks = self._tag_affected_stocks(subject)

                item = NewsItemCreate(
                    ticker=affected_stocks,
                    title=f"[IRDAI Notification] {subject}",
                    description=f"IRDAI Insurance Regulatory Circular. Impacted stocks/sectors: {affected_stocks}",
                    source="irdai",
                    source_url=link or self.IRDAI_CIRCULARS_URL,
                    source_id=f"irdai_{source_id}",
                    category="regulatory_policy",
                    published_at=pub_date,
                )
                items.append(item)

            logger.info(f"IRDAI scraper retrieved {len(items)} regulatory circulars.")
            return items
        except Exception as e:
            logger.warning(f"Failed to fetch IRDAI circulars: {e}")
            return []

    def fetch_rbi_press_releases(self, max_items: int = 25) -> List[NewsItemCreate]:
        """Scrapes official RBI press releases, monetary policies, and banking regulations."""
        items: List[NewsItemCreate] = []
        try:
            self.rate_limiter.wait()
            resp = self.session.get(self.RBI_PRESS_URL, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            for a_tag in soup.find_all("a"):
                href = a_tag.get("href", "")
                if "prid=" not in href:
                    continue

                headline = clean_text(a_tag.get_text())
                if not headline or len(headline) < 10:
                    continue

                link = f"https://www.rbi.org.in/Scripts/{href}" if not href.startswith("http") else href

                # Extract PR ID if available
                pr_id_match = re.search(r"prid=(\d+)", href)
                source_id = pr_id_match.group(1) if pr_id_match else hashlib.sha256(headline.encode()).hexdigest()[:16]

                affected_stocks = self._tag_affected_stocks(headline)[:140]
                category = "regulatory_policy"
                if "rate" in headline.lower() or "repo" in headline.lower() or "monetary" in headline.lower():
                    category = "monetary_policy"

                item = NewsItemCreate(
                    ticker=affected_stocks,
                    title=f"[RBI Notification] {headline}",
                    description=f"Reserve Bank of India notification. Relevant for: {affected_stocks}",
                    source="rbi",
                    source_url=link,
                    source_id=f"rbi_{source_id}",
                    category=category,
                    published_at=datetime.now(timezone.utc),
                )
                items.append(item)
                if len(items) >= max_items:
                    break

            logger.info(f"RBI scraper retrieved {len(items)} press releases & notifications.")
            return items
        except Exception as e:
            logger.warning(f"Failed to fetch RBI releases: {e}")
            return []

    def fetch_sebi_regulations(self, max_items: int = 25) -> List[NewsItemCreate]:
        """Scrapes official SEBI regulatory orders, circulars, and press releases."""
        items: List[NewsItemCreate] = []
        try:
            self.rate_limiter.wait()
            resp = self.session.get(self.SEBI_RSS_URL, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                return []

            for entry in channel.findall("item")[:max_items]:
                raw_title = clean_text(entry.findtext("title"))
                link = entry.findtext("link")
                raw_desc = clean_text(entry.findtext("description"))

                if not raw_title:
                    continue

                source_id = hashlib.sha256((link or raw_title).encode()).hexdigest()[:16]
                affected_stocks = self._tag_affected_stocks(raw_title, raw_desc)

                item = NewsItemCreate(
                    ticker=affected_stocks,
                    title=f"[SEBI Order] {raw_title}",
                    description=raw_desc if raw_desc else f"SEBI Regulatory Circular. Sector: {affected_stocks}",
                    source="sebi",
                    source_url=link,
                    source_id=f"sebi_{source_id}",
                    category="regulatory_policy",
                    published_at=datetime.now(timezone.utc),
                )
                items.append(item)

            logger.info(f"SEBI scraper retrieved {len(items)} circulars/orders.")
            return items
        except Exception as e:
            logger.warning(f"Failed to fetch SEBI RSS: {e}")
            return []

    def fetch_government_policies_and_bills(self, max_items: int = 30) -> List[NewsItemCreate]:
        """
        Scrapes Union Cabinet decisions, Parliament bills, GST Council,
        and Central Ministry policy decisions impacting industries.
        """
        items: List[NewsItemCreate] = []
        try:
            self.rate_limiter.wait()
            resp = self.session.get(self.GOOGLE_POLICY_SEARCH, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                return []

            for entry in channel.findall("item")[:max_items]:
                raw_title = clean_text(entry.findtext("title"))
                link = entry.findtext("link")
                raw_desc = clean_text(entry.findtext("description"))

                if not raw_title:
                    continue

                headline = raw_title
                source_pub = "Govt Wire"
                if " - " in raw_title:
                    parts = raw_title.rsplit(" - ", 1)
                    headline = parts[0].strip()
                    source_pub = parts[1].strip()

                affected_stocks = self._tag_affected_stocks(headline, raw_desc)[:140]
                source_id = hashlib.sha256((link or headline).encode()).hexdigest()[:16]

                item = NewsItemCreate(
                    ticker=affected_stocks,
                    title=f"[Policy & Bills] {headline}",
                    description=f"{raw_desc} (Reported by {source_pub}). Relevant stocks/sectors: {affected_stocks}",
                    source="govt_policy",
                    source_url=link,
                    source_id=f"gov_{source_id}",
                    category="government_policy",
                    published_at=datetime.now(timezone.utc),
                )
                items.append(item)

            logger.info(f"Government policy scraper retrieved {len(items)} policy news items.")
            return items
        except Exception as e:
            logger.warning(f"Failed to fetch Government policy search: {e}")
            return []

    def fetch_latest(self) -> List[NewsItemCreate]:
        """Fetches all regulatory notifications (IRDAI, RBI, SEBI, Government policies)."""
        all_items: List[NewsItemCreate] = []
        all_items.extend(self.fetch_irdai_circulars(max_items=15))
        all_items.extend(self.fetch_rbi_press_releases(max_items=20))
        all_items.extend(self.fetch_sebi_regulations(max_items=20))
        all_items.extend(self.fetch_government_policies_and_bills(max_items=25))

        self._last_error = None
        logger.info(f"Total regulatory & government policy items scraped: {len(all_items)}.")
        return all_items
