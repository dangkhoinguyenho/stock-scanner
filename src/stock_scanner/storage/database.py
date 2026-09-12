"""Roadmap Phase 1 — raw market data storage.

A thin SQLite wrapper the collectors write into. This is deliberately NOT
the Phase 3 event-response database (event -> price reaction at 5m/15m/
30m/1h/4h/1d/3d/5d, abnormal return, max favorable/adverse excursion) —
that comes later and will read the price history stored here as one of
its inputs. This module only owns "what actually happened to the price,"
nothing derived yet.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# src/stock_scanner/storage/database.py -> repo root is 3 levels up.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "stock_scanner.sqlite3"


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection to the local SQLite file, creating the schema if
    this is the first time. `row_factory = sqlite3.Row` lets callers read
    columns by name (row["close"]) instead of positional index (row[3]),
    which is what keeps queries readable as more columns get added later.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create every collector's table if it doesn't exist yet.

    `PRIMARY KEY (symbol, date)` on daily_prices means one row per symbol
    per trading day — re-collecting a day you already have overwrites it
    (see upsert_daily_prices) instead of creating a duplicate. Same idea
    for sec_filings, keyed on (cik, accession_number) — SEC's own unique
    ID for a filing, so re-collecting never duplicates a filing either.

    options_chain is keyed on (contract_symbol, as_of_date) instead of just
    contract_symbol, because unlike a filing, an option contract's bid/ask/
    open interest/implied volatility genuinely change day to day while the
    contract itself (same strike, same expiration) still exists. Running
    the collector daily is supposed to accumulate one row per contract per
    day — a real, growing history — not overwrite yesterday's snapshot.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_prices (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (symbol, date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sec_filings (
            cik TEXT NOT NULL,
            accession_number TEXT NOT NULL,
            ticker TEXT,
            form TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            primary_document TEXT,
            filing_url TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (cik, accession_number)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS economic_observations (
            series_id TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL NOT NULL,
            realtime_start TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (series_id, date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_articles (
            symbol TEXT NOT NULL,
            article_id TEXT NOT NULL,
            headline TEXT NOT NULL,
            source TEXT,
            url TEXT,
            published_at TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (symbol, article_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS options_chain (
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            expiration TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            option_type TEXT NOT NULL,
            strike REAL NOT NULL,
            last_price REAL,
            bid REAL,
            ask REAL,
            volume INTEGER,
            open_interest INTEGER,
            implied_volatility REAL,
            in_the_money INTEGER,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (contract_symbol, as_of_date)
        )
        """
    )
    conn.commit()


def upsert_daily_prices(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace rows, keyed on (symbol, date). Returns row count.

    "Upsert" = update-if-exists-else-insert. Re-running the collector for a
    day we already have just refreshes that row (and its fetched_at) rather
    than erroring on a duplicate key or silently piling up copies.
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO daily_prices
            (symbol, date, open, high, low, close, volume, fetched_at)
        VALUES
            (:symbol, :date, :open, :high, :low, :close, :volume, :fetched_at)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_daily_prices(
    conn: sqlite3.Connection,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
) -> list[sqlite3.Row]:
    """Read back stored rows for a symbol, oldest first, optionally
    bounded by an inclusive [start, end] date range (YYYY-MM-DD strings).
    """
    query = "SELECT * FROM daily_prices WHERE symbol = ?"
    params: list = [symbol]
    if start:
        query += " AND date >= ?"
        params.append(start)
    if end:
        query += " AND date <= ?"
        params.append(end)
    query += " ORDER BY date ASC"
    return conn.execute(query, params).fetchall()


def upsert_news_articles(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace news article rows, keyed on (symbol, article_id).
    Same upsert reasoning as the other tables.
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO news_articles
            (symbol, article_id, headline, source, url, published_at, fetched_at)
        VALUES
            (:symbol, :article_id, :headline, :source, :url, :published_at, :fetched_at)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_news_articles(
    conn: sqlite3.Connection,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
) -> list[sqlite3.Row]:
    """Read back stored articles for a symbol, oldest first, optionally
    bounded by an inclusive [start, end] range on `published_at` (ISO date
    or datetime strings — ISO format sorts and compares correctly as plain
    text, which is why every timestamp in this project is stored that way).
    """
    query = "SELECT * FROM news_articles WHERE symbol = ?"
    params: list = [symbol]
    if start:
        query += " AND published_at >= ?"
        params.append(start)
    if end:
        query += " AND published_at <= ?"
        params.append(end)
    query += " ORDER BY published_at ASC"
    return conn.execute(query, params).fetchall()


def upsert_sec_filings(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace SEC filing rows, keyed on (cik, accession_number).
    Same upsert reasoning as upsert_daily_prices: safe to re-run.
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO sec_filings
            (cik, accession_number, ticker, form, filing_date,
             primary_document, filing_url, fetched_at)
        VALUES
            (:cik, :accession_number, :ticker, :form, :filing_date,
             :primary_document, :filing_url, :fetched_at)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_sec_filings(
    conn: sqlite3.Connection,
    cik: str | None = None,
    form: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[sqlite3.Row]:
    """Read back stored filings, newest first, with optional filters."""
    query = "SELECT * FROM sec_filings WHERE 1=1"
    params: list = []
    if cik:
        query += " AND cik = ?"
        params.append(cik)
    if form:
        query += " AND form = ?"
        params.append(form)
    if start:
        query += " AND filing_date >= ?"
        params.append(start)
    if end:
        query += " AND filing_date <= ?"
        params.append(end)
    query += " ORDER BY filing_date DESC"
    return conn.execute(query, params).fetchall()


def upsert_economic_observations(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace economic observation rows, keyed on
    (series_id, date). Same upsert reasoning as the other tables — safe to
    re-run, and a later re-fetch (e.g. after FRED revises a figure) just
    overwrites the stored value rather than duplicating.
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO economic_observations
            (series_id, date, value, realtime_start, fetched_at)
        VALUES
            (:series_id, :date, :value, :realtime_start, :fetched_at)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_economic_observations(
    conn: sqlite3.Connection,
    series_id: str,
    start: str | None = None,
    end: str | None = None,
) -> list[sqlite3.Row]:
    """Read back stored observations for one series, oldest first."""
    query = "SELECT * FROM economic_observations WHERE series_id = ?"
    params: list = [series_id]
    if start:
        query += " AND date >= ?"
        params.append(start)
    if end:
        query += " AND date <= ?"
        params.append(end)
    query += " ORDER BY date ASC"
    return conn.execute(query, params).fetchall()


def upsert_options_chain(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace options-chain snapshot rows, keyed on
    (contract_symbol, as_of_date). Re-running the collector later the same
    day just refreshes that day's snapshot; running it again tomorrow adds
    a new row per contract instead of overwriting today's — see
    init_schema's docstring for why that distinction matters here.
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO options_chain
            (symbol, as_of_date, expiration, contract_symbol, option_type,
             strike, last_price, bid, ask, volume, open_interest,
             implied_volatility, in_the_money, fetched_at)
        VALUES
            (:symbol, :as_of_date, :expiration, :contract_symbol, :option_type,
             :strike, :last_price, :bid, :ask, :volume, :open_interest,
             :implied_volatility, :in_the_money, :fetched_at)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_options_chain(
    conn: sqlite3.Connection,
    symbol: str,
    expiration: str | None = None,
    as_of_date: str | None = None,
    option_type: str | None = None,
) -> list[sqlite3.Row]:
    """Read back stored option contract snapshots for a symbol, optionally
    filtered to one expiration, one as_of_date (the day we captured the
    chain), and/or one option_type ("call" or "put").
    """
    query = "SELECT * FROM options_chain WHERE symbol = ?"
    params: list = [symbol]
    if expiration:
        query += " AND expiration = ?"
        params.append(expiration)
    if as_of_date:
        query += " AND as_of_date = ?"
        params.append(as_of_date)
    if option_type:
        query += " AND option_type = ?"
        params.append(option_type)
    query += " ORDER BY as_of_date ASC, expiration ASC, strike ASC"
    return conn.execute(query, params).fetchall()
