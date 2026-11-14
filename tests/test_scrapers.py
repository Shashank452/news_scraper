"""
Unit tests for scrapers (BSE, NSE, Media News, Regulatory Policies).
Tests parsing, error handling, date formatting, and stock tagging using mocks.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from scrapers.bse_scraper import BSEScraper
from scrapers.media_news_scraper import MediaNewsScraper
from scrapers.nse_scraper import NSEScraper
from scrapers.regulatory_policy_scraper import RegulatoryPolicyScraper


SAMPLE_BSE_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>BSE Corporate Announcements</title>
    <item>
      <title>Infosys Ltd (500209)</title>
      <link>https://www.bseindia.com/xml-data/corpfiling/AttachLive/sample-uuid-1234.pdf</link>
      <description>Outcome of Board Meeting for financial results</description>
      <pubDate>06-Nov-2026 19:23:28</pubDate>
    </item>
    <item>
      <title>Tata Motors Limited (500570)</title>
      <link>https://www.bseindia.com/xml-data/corpfiling/AttachLive/sample-uuid-5678.pdf</link>
      <description>Production and Sales performance update</description>
      <pubDate>06-Nov-2026 18:10:00</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_NSE_JSON = [
    {
        "symbol": "RELIANCE",
        "companyName": "Reliance Industries Limited",
        "desc": "Outcome of Board Meeting - Financial Results",
        "an_dt": "06-Nov-2026 18:30:00",
        "attchmntText": "Financial results disclosure",
        "attchmntFile": "https://nsearchives.nseindia.com/corporate/rel_res.pdf",
    },
    {
        "symbol": "TCS",
        "companyName": "Tata Consultancy Services Limited",
        "desc": "Press Release on Cloud Partnership",
        "an_dt": "06-Nov-2026 17:00:00",
        "attchmntText": "Strategic expansion in Europe",
        "attchmntFile": "https://nsearchives.nseindia.com/corporate/tcs_pr.pdf",
    },
]

SAMPLE_MEDIA_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>ET Markets</title>
    <item>
      <title>Sensex surges 500 points led by banking stocks</title>
      <link>https://economictimes.indiatimes.com/markets/sensex-rally-101.cms</link>
      <description>Bulls charge D-Street as Nifty touches fresh high</description>
      <pubDate>Fri, 06 Nov 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_bse_scraper_parsing():
    scraper = BSEScraper(rate_limit_interval=0.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = SAMPLE_BSE_RSS.encode("utf-8")

    with patch.object(scraper.session, "get", return_value=mock_resp):
        items = scraper.fetch_latest(max_items=10)
        # 2 announcements + 2 circular notices from the mocked RSS
        assert len(items) == 4
        assert items[0].ticker == "500209"
        assert "sample-uuid-1234" in items[0].source_id
        assert items[0].source == "bse"
        assert items[0].category == "financial_results"
        assert items[1].ticker == "500570"


def test_bse_scraper_date_parsing():
    scraper = BSEScraper(rate_limit_interval=0.0)
    dt = scraper._parse_bse_datetime("06-Nov-2026 19:23:28")
    assert dt.year == 2026
    assert dt.month == 11
    assert dt.day == 6
    assert dt.hour == 19

    # Fallback on invalid date
    fallback_dt = scraper._parse_bse_datetime("invalid-date-string")
    assert fallback_dt is not None


def test_nse_scraper_parsing():
    scraper = NSEScraper(rate_limit_interval=0.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_NSE_JSON

    with patch.object(scraper, "_ensure_session", return_value=True), \
         patch.object(scraper.session, "get", return_value=mock_resp):
        items = scraper.fetch_latest()
        # Fetches announcements
        assert len(items) >= 2
        assert items[0].ticker == "RELIANCE"
        assert items[0].source == "nse"
        assert items[0].category == "financial_results"
        assert items[1].ticker == "TCS"


def test_nse_market_indices():
    scraper = NSEScraper(rate_limit_interval=0.0)

    indices_payload = {
        "data": [
            {
                "index": "NIFTY 50",
                "last": 25420.50,
                "variation": 140.25,
                "percentChange": 0.55,
                "open": 25300.00,
                "high": 25450.00,
                "low": 25280.00,
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = indices_payload

    with patch.object(scraper, "_ensure_session", return_value=True), \
         patch.object(scraper.session, "get", return_value=mock_resp):
        indices = scraper.get_market_indices()
        assert len(indices) == 1
        assert indices[0]["name"] == "NIFTY 50"
        assert indices[0]["last"] == 25420.50
        assert indices[0]["percent_change"] == 0.55


def test_media_news_scraper():
    scraper = MediaNewsScraper(rate_limit_interval=0.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = SAMPLE_MEDIA_RSS.encode("utf-8")

    with patch.object(scraper.session, "get", return_value=mock_resp):
        items = scraper.fetch_latest(max_items_per_source=5)
        # Should have fetched from mocked Economic Times and Moneycontrol
        assert len(items) >= 1
        assert "Sensex" in items[0].title
        assert items[0].source in ("economic_times", "moneycontrol")


def test_regulatory_policy_tagging():
    scraper = RegulatoryPolicyScraper(rate_limit_interval=0.0)

    # IRDAI insurance regulations tagging
    tagged_irdai = scraper._tag_affected_stocks("IRDAI issues new master circular on life insurance commission")
    assert "POLICYBZR" in tagged_irdai or "HDFCLIFE" in tagged_irdai

    # Banking policy tagging
    tagged_rbi = scraper._tag_affected_stocks("RBI increases risk weights on unsecured bank loans")
    assert "BANKING_SECTOR" in tagged_rbi or "SBIN" in tagged_rbi

    # Defence procurement tagging
    tagged_defence = scraper._tag_affected_stocks("Ministry of Defence approves procurement of fighter jet engines")
    assert "HAL" in tagged_defence or "BEL" in tagged_defence


def test_scraper_error_resilience():
    scraper = BSEScraper(rate_limit_interval=0.0)

    # Simulate network timeout
    with patch.object(scraper.session, "get", side_effect=Exception("Connection refused")):
        items = scraper.fetch_latest(max_items=10)
        assert items == []  # Gracefully returns empty list without crashing
        assert not scraper.is_healthy()
        assert "Connection refused" in scraper.get_last_error()
