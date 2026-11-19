"""
Utility module for free external financial endpoints, Google News RSS,
live stock quotes, and web browsing/search.
Zero API-key required integrations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

from core.utils import logger

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch_google_news(
    query: Optional[str] = None,
    topic: str = "BUSINESS",
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Fetches real-time market and company news via Google News RSS feed (100% free, no key).

    Args:
        query: Optional search keyword or ticker (e.g. 'RELIANCE', 'TCS quarterly results').
        topic: Section topic when query is not specified (default: 'BUSINESS').
        limit: Max news items to return (1-30, default 15).
    """
    limit = min(max(limit, 1), 30)
    if query and query.strip():
        encoded_query = quote_plus(query.strip())
        feed_url = (
            f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        )
    else:
        topic_name = topic.strip().upper() if topic else "BUSINESS"
        feed_url = (
            f"https://news.google.com/rss/headlines/section/topic/{topic_name}?hl=en-IN&gl=IN&ceid=IN:en"
        )

    items: List[Dict[str, Any]] = []
    try:
        resp = requests.get(feed_url, headers=DEFAULT_HEADERS, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Google News RSS returned status {resp.status_code}")
            return items

        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            return items

        for item_node in channel.findall("item")[:limit]:
            title_node = item_node.find("title")
            link_node = item_node.find("link")
            pub_date_node = item_node.find("pubDate")
            source_node = item_node.find("source")

            title = title_node.text if title_node is not None and title_node.text else "No title"
            link = link_node.text if link_node is not None and link_node.text else ""
            pub_date = pub_date_node.text if pub_date_node is not None and pub_date_node.text else ""
            source = source_node.text if source_node is not None and source_node.text else "Google News"

            items.append({
                "title": title,
                "source": source,
                "link": link,
                "published_at": pub_date,
            })
    except Exception as e:
        logger.error(f"Error fetching Google News RSS: {e}")

    return items


def browse_web_page(url: str, max_chars: int = 4000) -> Dict[str, Any]:
    """
    Reads and extracts clean, LLM-friendly markdown content of any webpage.
    Uses the free Jina Reader endpoint (https://r.jina.ai/<url>) with fallback to BeautifulSoup.

    Args:
        url: Full web address to browse (e.g. 'https://www.moneycontrol.com/...').
        max_chars: Maximum characters of markdown/text content to return (default 4000).
    """
    if not url or not url.startswith("http"):
        return {"error": "Invalid URL provided. URL must start with http:// or https://"}

    # Attempt via Jina Reader
    jina_url = f"https://r.jina.ai/{url.strip()}"
    try:
        resp = requests.get(jina_url, headers=DEFAULT_HEADERS, timeout=12)
        if resp.status_code == 200 and resp.text:
            content = resp.text.strip()
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n\n...[Truncated: exceeded {max_chars} chars]"
            return {
                "url": url,
                "engine": "jina_reader",
                "status": "success",
                "content": content,
            }
    except Exception as e:
        logger.debug(f"Jina Reader fetch failed ({e}), falling back to direct parse")

    # Fallback: direct HTTP fetch and BeautifulSoup extraction
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        if resp.status_code != 200:
            return {"url": url, "status": "error", "message": f"HTTP status {resp.status_code}"}

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()

        page_title = soup.title.get_text(strip=True) if soup.title else url
        body_text = soup.get_text(separator="\n", strip=True)

        if len(body_text) > max_chars:
            body_text = body_text[:max_chars] + f"\n\n...[Truncated: exceeded {max_chars} chars]"

        return {
            "url": url,
            "title": page_title,
            "engine": "direct_scrape_fallback",
            "status": "success",
            "content": body_text,
        }
    except Exception as e:
        return {"url": url, "status": "error", "message": str(e)}


def search_web_free(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Searches the live web using free HTML search without requiring an API key.

    Args:
        query: Search keywords or phrases.
        limit: Max search results (1-15, default 10).
    """
    limit = min(max(limit, 1), 15)
    results: List[Dict[str, Any]] = []

    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query.strip()},
            headers=DEFAULT_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        for r in soup.select(".result")[:limit]:
            title_tag = r.select_one(".result__title")
            snippet_tag = r.select_one(".result__snippet")
            url_tag = r.select_one(".result__url")

            if title_tag:
                title = title_tag.get_text(strip=True)
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                url = url_tag.get_text(strip=True) if url_tag else ""
                if not url.startswith("http") and url:
                    url = "https://" + url

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })
    except Exception as e:
        logger.error(f"Error executing free web search: {e}")

    return results


def get_live_market_quote(
    ticker: str,
    exchange: str = "NSE",
    range_period: str = "1d",
) -> Dict[str, Any]:
    """
    Fetches real-time price quotes, changes, 52-week high/low, and market metrics
    for any Indian or global stock/index (100% free via Yahoo Finance chart engine).

    Args:
        ticker: Symbol (e.g. 'RELIANCE', 'TCS', 'INFY', or index '^NSEI' / '^BSESN').
        exchange: 'NSE' (default, appends .NS), 'BSE' (appends .BO), or 'US' / 'GLOBAL' (raw ticker).
        range_period: Period range (e.g. '1d', '5d', '1mo', '1y').
    """
    clean_ticker = ticker.strip().upper()
    if clean_ticker.startswith("^") or "." in clean_ticker:
        symbol = clean_ticker
    elif exchange.upper() == "NSE":
        symbol = f"{clean_ticker}.NS"
    elif exchange.upper() == "BSE":
        symbol = f"{clean_ticker}.BO"
    else:
        symbol = clean_ticker

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_period}"
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        if resp.status_code != 200:
            return {
                "symbol": symbol,
                "status": "not_found",
                "message": f"Unable to fetch quote (HTTP {resp.status_code})",
            }

        data = resp.json().get("chart", {}).get("result", [])
        if not data:
            return {"symbol": symbol, "status": "not_found", "message": "No quote data returned"}

        meta = data[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")

        change = None
        change_pct = None
        if price is not None and prev_close is not None and prev_close > 0:
            change = round(price - prev_close, 2)
            change_pct = round((change / prev_close) * 100, 2)

        return {
            "symbol": meta.get("symbol", symbol),
            "price": price,
            "previous_close": prev_close,
            "change": change,
            "change_percent": change_pct,
            "currency": meta.get("currency", "INR"),
            "exchange": meta.get("exchangeName"),
            "day_high": meta.get("regularMarketDayHigh"),
            "day_low": meta.get("regularMarketDayLow"),
            "high_52w": meta.get("fiftyTwoWeekHigh"),
            "low_52w": meta.get("fiftyTwoWeekLow"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success",
        }
    except Exception as e:
        logger.error(f"Error fetching quote for {symbol}: {e}")
        return {"symbol": symbol, "status": "error", "message": str(e)}
