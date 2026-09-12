"""Roadmap Phase 1 — news collector.

Fetches company-specific news headlines from Finnhub's free API
(https://finnhub.io) — 60 requests/minute on the free tier, no credit card,
a real documented `company-news` endpoint that takes a date range per
ticker, rather than something scraped.

This collector only fetches and stores raw headlines with their real
publish timestamps (plus source and URL). It does NOT classify them —
no bullish/bearish, no event type, no importance. That's Phase 2's job
(events/), deliberately kept separate: this module's only responsibility
is "what was published, and when," so Phase 2's classification logic can
be built, tested, and improved independently of how headlines get in.

Known gap, flagged rather than hidden: this only covers company-specific
news. The project spec (section 6) also wants industry-level news that
moves a stock even when the company itself isn't mentioned (e.g. Disney
news affecting NFLX) — that needs a different source and isn't solved here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import requests

COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"


def fetch_company_news(
    symbol: str,
    api_key: str,
    start: str,
    end: str,
    http_get: Callable[..., Any] | None = None,
) -> list[dict]:
    """Fetch news headlines for `symbol` between `start` and `end`
    (YYYY-MM-DD strings). Same injectable-`http_get` pattern as the other
    Phase 1 collectors, for the same reason: testable without a real
    network call to Finnhub.
    """
    if not api_key:
        raise ValueError(
            "FINNHUB_API_KEY is not set. Sign up for a free key at "
            "https://finnhub.io/register and set it in .env."
        )

    http_get = http_get or requests.get
    params = {"symbol": symbol, "from": start, "to": end, "token": api_key}
    response = http_get(COMPANY_NEWS_URL, params=params, timeout=30)
    response.raise_for_status()
    articles = response.json()

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for article in articles:
        # Finnhub gives publish time as a Unix timestamp (seconds); we store
        # it as an ISO string like every other timestamp in this project.
        published_at = datetime.fromtimestamp(article["datetime"], tz=timezone.utc).isoformat()
        rows.append(
            {
                "symbol": symbol,
                "article_id": str(article["id"]),
                "headline": article["headline"],
                "source": article.get("source"),
                "url": article.get("url"),
                "published_at": published_at,
                "fetched_at": fetched_at,
            }
        )
    return rows


def collect_and_store(
    symbol: str,
    api_key: str,
    start: str,
    end: str,
    conn=None,
    http_get: Callable[..., Any] | None = None,
) -> int:
    """Fetch news for `symbol` between `start` and `end` and persist it.
    Returns the number of rows written.
    """
    from stock_scanner.storage.database import get_connection, upsert_news_articles

    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        rows = fetch_company_news(symbol, api_key, start, end, http_get=http_get)
        return upsert_news_articles(conn, rows)
    finally:
        if owns_conn:
            conn.close()
