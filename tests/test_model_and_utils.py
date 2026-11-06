"""
Unit tests for data models, classification heuristics, and utilities.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

from config import is_market_hours
from news_model import NewsItemCreate, categorize_announcement
from utils import clean_text, normalize_ticker

IST_TZ = ZoneInfo("Asia/Kolkata")


def test_clean_text():
    raw_html = "<p>Reliance Industries <b>Announces</b> &amp; discloses Q4 results.&nbsp;</p>"
    cleaned = clean_text(raw_html)
    assert cleaned == "Reliance Industries Announces & discloses Q4 results."


def test_normalize_ticker():
    assert normalize_ticker("RELIANCE.NS") == "RELIANCE"
    assert normalize_ticker("infy.bo") == "INFY"
    assert normalize_ticker("TCS") == "TCS"
    assert normalize_ticker("M&M") == "M&M"
    assert normalize_ticker("  TATAMOTORS  ") == "TATAMOTORS"
    assert normalize_ticker("") is None
    assert normalize_ticker(None) is None


def test_categorize_announcement():
    assert categorize_announcement("Financial Results for Q3 FY24") == "financial_results"
    assert categorize_announcement("Outcome of Board Meeting held today") == "board_meeting"
    assert categorize_announcement("Declaration of Interim Dividend") == "dividend"
    assert categorize_announcement("Acquisition of 51% stake in XYZ Ltd") == "acquisition_merger"
    assert categorize_announcement("Resignation of Chief Financial Officer") == "management_change"
    assert categorize_announcement("Company bagged new order worth 500 Cr") == "order_contract"
    assert categorize_announcement("SEBI circular compliance note") == "regulatory"
    assert categorize_announcement("Routine newspaper publication") == "general"


def test_is_market_hours():
    # Tuesday 11:30 AM IST (market open)
    market_time = datetime(2026, 11, 10, 11, 30, tzinfo=IST_TZ)
    assert is_market_hours(market_time) is True

    # Tuesday 08:30 AM IST (pre-market, closed)
    pre_market = datetime(2026, 11, 10, 8, 30, tzinfo=IST_TZ)
    assert is_market_hours(pre_market) is False

    # Tuesday 16:30 PM IST (post-market, closed)
    post_market = datetime(2026, 11, 10, 16, 30, tzinfo=IST_TZ)
    assert is_market_hours(post_market) is False

    # Sunday 12:00 PM IST (weekend, closed)
    sunday = datetime(2026, 11, 8, 12, 0, tzinfo=IST_TZ)
    assert is_market_hours(sunday) is False


def test_news_item_create_validation():
    now = datetime.now(IST_TZ)
    item = NewsItemCreate(
        ticker="TCS",
        title="Board approves dividend of Rs 28/share",
        description="Detailed notes on dividend declaration.",
        source="nse",
        source_url="https://nseindia.com/sample",
        source_id="nse_12345",
        category="dividend",
        published_at=now,
    )
    assert item.ticker == "TCS"
    assert item.source == "nse"
    assert item.category == "dividend"
