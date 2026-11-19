"""
Model Context Protocol (MCP) Server for Indian Equities News & Exchange Disclosures.
Allows AI agents (Claude Desktop, Cursor, LangGraph agents, etc.) to query real-time
corporate announcements, regulatory filings, financial news, and market indices.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, or_, select

from core.config import is_market_hours
from core.database import NewsItemRecord, SessionLocal, save_news_items_batch
from scrapers.bse_scraper import BSEScraper
from scrapers.nse_scraper import NSEScraper
from scrapers.media_news_scraper import MediaNewsScraper
from scrapers.regulatory_policy_scraper import RegulatoryPolicyScraper
from aggregators.news_aggregator import NewsAggregator
from core.market_web_tools import (
    browse_web_page as _browse_web_page,
    fetch_google_news as _fetch_google_news,
    get_live_market_quote as _get_live_market_quote,
    search_web_free as _search_web_free,
)
from core.utils import logger

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

mcp = MCPServer("indian-stock-market-news")


@mcp.tool()
def get_latest_announcements(
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get the latest official stock exchange announcements and corporate disclosures from BSE and NSE.

    Args:
        ticker: Optional stock symbol to filter by (e.g. 'RELIANCE', 'TCS', 'INFY', 'POLYPLEX').
        source: Optional source filter ('bse', 'nse', 'economic_times', 'moneycontrol', 'media_news').
        category: Optional category ('financial_results', 'board_meeting', 'dividend', 'acquisition_merger', 'surveillance_asm_gsm', 'circuit_price_band').
        limit: Maximum number of announcements to return (1-50, default 20).
    """
    db = SessionLocal()
    try:
        stmt = select(NewsItemRecord).order_by(desc(NewsItemRecord.published_at))
        if ticker:
            clean_ticker = ticker.strip().upper()
            stmt = stmt.where(
                (NewsItemRecord.ticker == clean_ticker)
                | (NewsItemRecord.title.ilike(f"%{clean_ticker}%"))
            )
        if source:
            stmt = stmt.where(NewsItemRecord.source == source.strip().lower())
        if category:
            stmt = stmt.where(NewsItemRecord.category == category.strip().lower())

        stmt = stmt.limit(min(max(limit, 1), 50))
        records = db.execute(stmt).scalars().all()

        return [
            {
                "id": str(r.id),
                "ticker": r.ticker,
                "title": r.title,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
                "category": r.category,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in records
        ]
    finally:
        db.close()


@mcp.tool()
def search_market_news(
    query: str,
    ticker: Optional[str] = None,
    days_back: Optional[int] = 30,
    live_search: bool = True,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Search both live online financial news and historical database records for specific companies, events, or market themes.

    Args:
        query: Keywords to search for (e.g. 'quarterly results', 'defence contract', 'capex', 'bonus issue').
        ticker: Optional stock ticker symbol (e.g. 'TCS', 'HDFCBANK').
        days_back: Search news published within the last N days (default 30).
        live_search: If True, executes real-time web search across financial media wires and saves new items.
        limit: Maximum number of results to return (default 15).
    """
    db = SessionLocal()
    try:
        if live_search and (query or ticker):
            scraper = MediaNewsScraper()
            live_items = scraper.search_news(
                query=query, ticker=ticker, days_back=days_back, limit=limit
            )
            save_news_items_batch(db, live_items)

        stmt = select(NewsItemRecord).order_by(desc(NewsItemRecord.published_at))
        if ticker:
            clean_ticker = ticker.strip().upper()
            stmt = stmt.where(
                (NewsItemRecord.ticker == clean_ticker)
                | (NewsItemRecord.title.ilike(f"%{clean_ticker}%"))
            )
        if query:
            clean_q = query.strip()
            words = [w for w in clean_q.split() if len(w) > 2]
            if words:
                conditions = []
                for w in words:
                    conditions.append(NewsItemRecord.title.ilike(f"%{w}%"))
                    conditions.append(NewsItemRecord.description.ilike(f"%{w}%"))
                stmt = stmt.where(or_(*conditions))
            else:
                stmt = stmt.where(
                    (NewsItemRecord.title.ilike(f"%{clean_q}%"))
                    | (NewsItemRecord.description.ilike(f"%{clean_q}%"))
                )

        stmt = stmt.limit(min(max(limit, 1), 50))
        records = db.execute(stmt).scalars().all()

        return [
            {
                "ticker": r.ticker,
                "title": r.title,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
                "category": r.category,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in records
        ]
    finally:
        db.close()


@mcp.tool()
def get_live_market_indices() -> Dict[str, Any]:
    """
    Get live benchmark index levels (NIFTY 50, BANK NIFTY, INDIA VIX, NIFTY IT)
    and current Indian market operating status (Open / Closed).
    """
    scraper = NSEScraper()
    indices = scraper.get_market_indices()
    return {
        "is_market_hours": is_market_hours(),
        "indices": indices,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def get_surveillance_and_circuit_notices(limit: int = 15) -> List[Dict[str, Any]]:
    """
    Get latest exchange regulatory surveillance notices, including:
    - Long-Term & Short-Term Additional Surveillance Measure (LT-ASM / ST-ASM)
    - Graded Surveillance Measure (GSM) stages
    - Price band & circuit filter revisions
    """
    db = SessionLocal()
    try:
        stmt = (
            select(NewsItemRecord)
            .where(
                NewsItemRecord.category.in_(["surveillance_asm_gsm", "circuit_price_band", "regulatory"])
            )
            .order_by(desc(NewsItemRecord.published_at))
            .limit(min(max(limit, 1), 50))
        )
        records = db.execute(stmt).scalars().all()
        return [
            {
                "title": r.title,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
                "category": r.category,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in records
        ]
    finally:
        db.close()


@mcp.tool()
def get_government_and_regulatory_policies(
    regulator: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get latest government policy announcements, cabinet decisions, bills,
    and regulatory directives from IRDAI (insurance commission & surrender rules),
    RBI (monetary policy & lending limits), and SEBI with tagged affected stocks.

    Args:
        regulator: Optional filter ('irdai', 'rbi', 'sebi', 'govt_policy').
        limit: Max records to return (1-50, default 20).
    """
    db = SessionLocal()
    try:
        scraper = RegulatoryPolicyScraper()
        live_items = scraper.fetch_latest()
        save_news_items_batch(db, live_items)

        stmt = select(NewsItemRecord).where(
            NewsItemRecord.source.in_(["irdai", "rbi", "sebi", "govt_policy"])
        )
        if regulator:
            stmt = stmt.where(NewsItemRecord.source == regulator.strip().lower())

        stmt = stmt.order_by(desc(NewsItemRecord.published_at)).limit(min(max(limit, 1), 50))
        records = db.execute(stmt).scalars().all()
        return [
            {
                "affected_stocks": r.ticker,
                "title": r.title,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
                "category": r.category,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in records
        ]
    finally:
        db.close()


@mcp.tool()
def get_world_and_macro_news(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get live world business news, US Federal Reserve interest rate announcements,
    crude oil / commodity price shifts, and global macroeconomic trends.

    Args:
        limit: Max articles to return (1-50, default 20).
    """
    db = SessionLocal()
    try:
        scraper = MediaNewsScraper()
        world_items = scraper.fetch_world_and_macro_news(max_items=limit)
        save_news_items_batch(db, world_items)

        stmt = (
            select(NewsItemRecord)
            .where(NewsItemRecord.source == "world_news")
            .order_by(desc(NewsItemRecord.published_at))
            .limit(min(max(limit, 1), 50))
        )
        records = db.execute(stmt).scalars().all()
        return [
            {
                "affected_theme": r.ticker,
                "title": r.title,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
                "category": r.category,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in records
        ]
    finally:
        db.close()


@mcp.tool()
def trigger_live_scrape() -> Dict[str, Any]:
    """
    Trigger an immediate, on-demand real-time scrape across BSE, NSE, and financial media wires.
    Returns the count of total fetched and newly inserted records.
    """
    aggregator = NewsAggregator()
    summary = aggregator.run_cycle()
    return {
        "message": "Scrape cycle completed successfully",
        "summary": summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def get_google_news(
    query: Optional[str] = None,
    topic: str = "BUSINESS",
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Fetch real-time stock, sector, and financial news via Google News RSS (100% free, real-time).

    Args:
        query: Optional search keyword or stock symbol (e.g. 'RELIANCE', 'TCS bonus share', 'RBI repo rate').
        topic: Topic section when query is omitted (default 'BUSINESS', e.g. 'TECHNOLOGY').
        limit: Maximum number of articles to return (1-30, default 15).
    """
    return _fetch_google_news(query=query, topic=topic, limit=limit)


@mcp.tool()
def browse_web_page(url: str, max_chars: int = 4000) -> Dict[str, Any]:
    """
    Browse and extract clean, LLM-ready markdown content from any web article or announcement URL.
    Uses free Jina Reader (https://r.jina.ai/) with HTML parser fallback.

    Args:
        url: Full webpage URL to read (e.g. 'https://www.moneycontrol.com/...').
        max_chars: Maximum character limit for returned content (default 4000).
    """
    return _browse_web_page(url=url, max_chars=max_chars)


@mcp.tool()
def search_web_free(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search the live web for breaking news, disclosures, analyst reports, or websites without an API key.

    Args:
        query: Keywords or question to search the web for.
        limit: Maximum number of search results (1-15, default 10).
    """
    return _search_web_free(query=query, limit=limit)


@mcp.tool()
def get_live_market_quote(
    ticker: str,
    exchange: str = "NSE",
    range_period: str = "1d",
) -> Dict[str, Any]:
    """
    Fetch live market prices, day change, 52-week high/low, volume, and currency for any Indian or global stock/index.

    Args:
        ticker: Stock symbol (e.g. 'RELIANCE', 'TCS', 'HDFCBANK', or indices like '^NSEI' for NIFTY 50, '^BSESN' for SENSEX).
        exchange: 'NSE' (default, appends .NS), 'BSE' (appends .BO), or 'GLOBAL' / 'US'.
        range_period: Historical range window ('1d', '5d', '1mo', '1y').
    """
    return _get_live_market_quote(ticker=ticker, exchange=exchange, range_period=range_period)


def create_mcp_sse_app():
    """
    Returns an SSE Starlette application instance configured for remote clients
    (Claude Web, Claude Desktop, Cursor, etc.). Disables DNS rebinding host checking
    so public domain names (e.g. clawtrade.duckdns.org or custom cloud IPs) connect cleanly.
    """
    try:
        from mcp.server.transport_security import TransportSecuritySettings
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        return mcp.sse_app(transport_security=security)
    except Exception:
        return mcp.sse_app()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Indian Stock Market MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to bind for SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port number to bind for SSE transport (default: 8001)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        logger.info(f"Starting Indian Stock Market MCP Server (SSE transport on http://{args.host}:{args.port}/sse)...")
        mcp.run(transport="sse")
    else:
        logger.info("Starting Indian Stock Market MCP Server (stdio transport)...")
        mcp.run(transport="stdio")
