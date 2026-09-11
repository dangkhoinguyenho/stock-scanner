"""Roadmap Phase 1 — market data collector.

Fetches daily OHLCV (open/high/low/close/volume) candles via yfinance and
normalizes them into plain dicts the storage layer understands, so nothing
else in this codebase needs to know yfinance's (or any future vendor's)
particular DataFrame shape.

The fetch step and the normalize step are deliberately two separate
functions. That split is what lets `normalize_history` be unit-tested with
a hand-built DataFrame — no yfinance install, no network call, no
flakiness — while `fetch_daily_ohlcv` (the part that actually talks to
Yahoo Finance) gets verified for real, once, against live data. See
tests/test_market_data.py and the README for how each is checked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def normalize_history(symbol: str, history_df: Any) -> list[dict]:
    """Turn a yfinance-shaped DataFrame (columns Open/High/Low/Close/
    Volume, indexed by date) into our own plain-dict row format.

    Every row is stamped with a `fetched_at` UTC timestamp. This is not
    decorative — ARCHITECTURE.md rule 4 (look-ahead bias) requires being
    able to tell "we learned this candle existed at time X" separately
    from "the candle itself is dated Y." Nothing downstream should ever
    assume data was known before its fetched_at time.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for index, row in history_df.iterrows():
        date_str = index.strftime("%Y-%m-%d") if hasattr(index, "strftime") else str(index)
        rows.append(
            {
                "symbol": symbol,
                "date": date_str,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
                "fetched_at": fetched_at,
            }
        )
    return rows


def fetch_daily_ohlcv(
    symbol: str,
    start: str,
    end: str,
    ticker_factory: Callable[[str], Any] | None = None,
) -> list[dict]:
    """Fetch daily OHLCV for `symbol` between `start` and `end`
    (YYYY-MM-DD strings, end exclusive per yfinance's convention).

    `ticker_factory`, if given, must be callable(symbol) -> an object with
    a `.history(start=, end=, interval=)` method — that's the "shape"
    yfinance's own `Ticker` class has. Tests pass a fake one; real callers
    leave this as None and get the real yfinance Ticker. yfinance is only
    imported inside this function (not at module load time) specifically
    so importing this module — and running its tests — never requires
    yfinance to be installed.
    """
    if ticker_factory is None:
        import yfinance as yf

        ticker_factory = yf.Ticker

    ticker = ticker_factory(symbol)
    history_df = ticker.history(start=start, end=end, interval="1d")
    return normalize_history(symbol, history_df)


def collect_and_store(
    symbol: str,
    start: str,
    end: str,
    conn=None,
    ticker_factory: Callable[[str], Any] | None = None,
) -> int:
    """Fetch OHLCV for `symbol` and persist it to the price database.
    Returns the number of rows written.

    Opens (and closes) its own database connection if none is passed in —
    pass one explicitly if you're collecting several symbols in a row and
    want to reuse a single connection instead of opening one per call.
    """
    from stock_scanner.storage.database import get_connection, upsert_daily_prices

    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        rows = fetch_daily_ohlcv(symbol, start, end, ticker_factory=ticker_factory)
        return upsert_daily_prices(conn, rows)
    finally:
        if owns_conn:
            conn.close()
