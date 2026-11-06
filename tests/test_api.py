"""
Integration tests for FastAPI endpoints.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.news_api import app
from config import settings
from database import Base, NewsItemRecord, get_db

# Setup test SQLite database using StaticPool to share in-memory state across connections
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def populate_sample_data():
    """Populates test announcements into test database before each test."""
    db = TestingSessionLocal()
    db.query(NewsItemRecord).delete()
    db.commit()

    now = datetime.now(timezone.utc)
    items = [
        NewsItemRecord(
            ticker="RELIANCE",
            title="Reliance Retail enters new market segment",
            description="Expansion details and capital outlay.",
            source="bse",
            source_id="bse_test_101",
            category="general",
            published_at=now,
        ),
        NewsItemRecord(
            ticker="TCS",
            title="TCS announces Q4 audited results",
            description="Net profit jumps 9% YoY.",
            source="nse",
            source_id="nse_test_202",
            category="financial_results",
            published_at=now,
        ),
    ]
    db.add_all(items)
    db.commit()
    db.close()


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_auth_unauthorized():
    # If API key is enabled in settings, requesting without header should yield 401
    resp = client.get("/news")
    assert resp.status_code == 401


def test_get_news_authorized():
    headers = {"X-API-Key": settings.api_key}
    resp = client.get("/news", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_filter_by_ticker():
    headers = {"X-API-Key": settings.api_key}
    resp = client.get("/news?ticker=RELIANCE", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "RELIANCE"


def test_export_file():
    headers = {"X-API-Key": settings.api_key}
    # JSON export
    resp_json = client.get("/news/export/file?format=json", headers=headers)
    assert resp_json.status_code == 200
    assert len(resp_json.json()) == 2

    # CSV export
    resp_csv = client.get("/news/export/file?format=csv", headers=headers)
    assert resp_csv.status_code == 200
    assert "RELIANCE" in resp_csv.text
    assert "TCS" in resp_csv.text


def test_ui_and_stats():
    # Test UI HTML page serving
    resp_ui = client.get("/ui")
    assert resp_ui.status_code == 200
    assert "Indian Equities News Terminal" in resp_ui.text

    # Test stats endpoint
    resp_stats = client.get("/stats")
    assert resp_stats.status_code == 200
    data = resp_stats.json()
    assert data["total_news"] == 2
    assert "bse_count" in data
    assert "nse_count" in data
    assert "is_market_hours" in data
