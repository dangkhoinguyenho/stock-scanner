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
    """Create the daily_prices table if it doesn't exist yet.

    `PRIMARY KEY (symbol, date)` means one row per symbol per trading day —
    re-collecting a day you already have overwrites it (see
    upsert_daily_prices) instead of creating a duplicate.
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
