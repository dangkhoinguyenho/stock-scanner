"""Tests for the Phase 1 raw price storage layer.

Uses an in-memory SQLite database (":memory:") so these run instantly,
leave nothing on disk, and need no network — the storage logic itself is
what's under test, not any real data source.
"""

import sqlite3

from stock_scanner.storage.database import (
    get_daily_prices,
    init_schema,
    upsert_daily_prices,
)


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_upsert_and_read_back():
    conn = _fresh_conn()
    rows = [
        {
            "symbol": "NFLX", "date": "2026-09-10", "open": 100.0, "high": 105.0,
            "low": 99.0, "close": 103.0, "volume": 1_000_000,
            "fetched_at": "2026-09-11T00:00:00+00:00",
        },
        {
            "symbol": "NFLX", "date": "2026-09-11", "open": 103.0, "high": 108.0,
            "low": 102.0, "close": 107.0, "volume": 1_200_000,
            "fetched_at": "2026-09-11T00:00:00+00:00",
        },
    ]

    written = upsert_daily_prices(conn, rows)
    assert written == 2

    fetched = get_daily_prices(conn, "NFLX")
    assert len(fetched) == 2
    assert fetched[0]["date"] == "2026-09-10"
    assert fetched[1]["close"] == 107.0


def test_upsert_overwrites_same_symbol_and_date_instead_of_duplicating():
    conn = _fresh_conn()
    row = {
        "symbol": "NFLX", "date": "2026-09-10", "open": 100.0, "high": 105.0,
        "low": 99.0, "close": 103.0, "volume": 1_000_000,
        "fetched_at": "2026-09-11T00:00:00+00:00",
    }
    upsert_daily_prices(conn, [row])

    corrected = dict(row, close=104.5, fetched_at="2026-09-11T12:00:00+00:00")
    upsert_daily_prices(conn, [corrected])

    fetched = get_daily_prices(conn, "NFLX")
    assert len(fetched) == 1
    assert fetched[0]["close"] == 104.5
    assert fetched[0]["fetched_at"] == "2026-09-11T12:00:00+00:00"


def test_date_range_filtering_is_inclusive():
    conn = _fresh_conn()
    rows = [
        {
            "symbol": "NFLX", "date": d, "open": 1.0, "high": 1.0, "low": 1.0,
            "close": 1.0, "volume": 1, "fetched_at": "2026-09-11T00:00:00+00:00",
        }
        for d in ["2026-09-01", "2026-09-05", "2026-09-10"]
    ]
    upsert_daily_prices(conn, rows)

    fetched = get_daily_prices(conn, "NFLX", start="2026-09-05", end="2026-09-05")
    assert [r["date"] for r in fetched] == ["2026-09-05"]


def test_different_symbols_do_not_collide():
    conn = _fresh_conn()
    upsert_daily_prices(conn, [
        {"symbol": "NFLX", "date": "2026-09-10", "open": 1.0, "high": 1.0,
         "low": 1.0, "close": 1.0, "volume": 1, "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"symbol": "QQQ", "date": "2026-09-10", "open": 2.0, "high": 2.0,
         "low": 2.0, "close": 2.0, "volume": 2, "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    assert len(get_daily_prices(conn, "NFLX")) == 1
    assert len(get_daily_prices(conn, "QQQ")) == 1
    assert get_daily_prices(conn, "NFLX")[0]["close"] == 1.0
