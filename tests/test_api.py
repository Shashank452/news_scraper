"""
Integration tests for FastAPI endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.news_api import app
from core.config import settings
from core.database import Base, NewsItemRecord, get_db

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
    assert "viewport-fit=cover" in resp_ui.text
    assert "tv-mode" in resp_ui.text
    assert "toggleTvMode" in resp_ui.text

    # Test stats endpoint
    resp_stats = client.get("/stats")
    assert resp_stats.status_code == 200
    data = resp_stats.json()
    assert data["total_news"] == 2
    assert "bse_count" in data
    assert "nse_count" in data
    assert "is_market_hours" in data


def test_search_news_endpoint():
    headers = {"X-API-Key": settings.api_key}
    # Test local DB search without live query
    resp = client.get("/news/search?q=Retail&live_search=false", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "Reliance" in data[0]["title"]


def test_policy_and_world_endpoints():
    headers = {"X-API-Key": settings.api_key}
    # Test policy endpoint (without live fetch)
    resp_pol = client.get("/news/policy?live_fetch=false", headers=headers)
    assert resp_pol.status_code == 200
    assert isinstance(resp_pol.json(), list)

    # Test world endpoint (without live fetch)
    resp_world = client.get("/news/world?live_fetch=false", headers=headers)
    assert resp_world.status_code == 200
    assert isinstance(resp_world.json(), list)


def test_incremental_cursor_and_checkpoint():
    headers = {"X-API-Key": settings.api_key}

    # 1. Test checkpoint endpoint
    ckpt_resp = client.get("/news/checkpoint", headers=headers)
    assert ckpt_resp.status_code == 200
    ckpt_data = ckpt_resp.json()
    assert "latest_scraped_at" in ckpt_data
    assert "last_id" in ckpt_data
    assert ckpt_data["total_news"] == 2

    # 2. Test incremental endpoint with no cursor (fetches all initial items)
    inc_resp = client.get("/news/incremental?limit=10", headers=headers)
    assert inc_resp.status_code == 200
    inc_data = inc_resp.json()
    assert inc_data["count"] == 2
    assert "cursor" in inc_data
    assert inc_data["cursor"]["since_scraped"] is not None
    assert inc_data["cursor"]["last_id"] is not None

    # 3. Test resuming from cursor (should return 0 new items because none added)
    next_cursor = inc_data["cursor"]["since_scraped"]
    next_id = inc_data["cursor"]["last_id"]
    resume_resp = client.get(
        f"/news/incremental?since_scraped={next_cursor}&last_id={next_id}",
        headers=headers,
    )
    assert resume_resp.status_code == 200
    resume_data = resume_resp.json()
    assert resume_data["count"] == 0


def test_mcp_sse_endpoint():
    """Verify that FastMCP SSE router is mounted with /sse and /messages routes."""
    mount = next((r for r in app.routes if getattr(r, "path", None) == "/mcp"), None)
    assert mount is not None, "MCP mount point /mcp not found in FastAPI app"
    mounted_routes = [r.path for r in getattr(mount.app, "routes", [])]
    assert "/sse" in mounted_routes, "MCP SSE route /sse missing"
    assert any("messages" in r for r in mounted_routes), "MCP messages route missing"


def test_google_and_web_endpoints():
    headers = {"X-API-Key": settings.api_key}

    # 1. Google News endpoint
    with patch("api.news_api.fetch_google_news") as mock_gn:
        mock_gn.return_value = [{"title": "Test Headline", "source": "Google News", "link": "https://example.com"}]
        resp = client.get("/news/google?query=RELIANCE", headers=headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["title"] == "Test Headline"

    # 2. Browse web endpoint
    with patch("api.news_api.browse_web_page") as mock_browse:
        mock_browse.return_value = {"url": "https://example.com", "status": "success", "content": "Article"}
        resp = client.get("/news/browse?url=https://example.com", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    # 3. Search web endpoint
    with patch("api.news_api.search_web_free") as mock_search:
        mock_search.return_value = [{"title": "Nifty 50 News", "url": "https://example.com", "snippet": "updates"}]
        resp = client.get("/news/search-web?q=Nifty", headers=headers)
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["title"] == "Nifty 50 News"

    # 4. Market quote endpoint
    with patch("api.news_api.get_live_market_quote") as mock_quote:
        mock_quote.return_value = {
            "symbol": "TCS.NS",
            "price": 3500.0,
            "change": 50.0,
            "change_percent": 1.45,
            "status": "success",
        }
        resp = client.get("/market/quote/TCS?exchange=NSE")
        assert resp.status_code == 200
        quote = resp.json()
        assert quote["symbol"] == "TCS.NS"
        assert quote["price"] == 3500.0
        assert quote["change"] == 50.0
