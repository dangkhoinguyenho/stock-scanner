"""Tests for the Phase 1 daily options snapshot job.

Verifies the one thing that matters for an unattended, scheduled job that
the other Phase 1 collectors didn't need to worry about: one symbol
failing must not stop the rest of the watchlist from being collected.
Uses an in-memory database and a fake `collect_fn` — no network, no
yfinance, no real filesystem log — same offline-testability pattern as
every other collector in this project.
"""

import sqlite3

from stock_scanner.jobs.daily_options_snapshot import run
from stock_scanner.storage.database import init_schema


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_run_collects_every_symbol_in_watchlist():
    calls = []

    def fake_collect(symbol, conn, max_expirations):
        calls.append(symbol)
        return 42

    succeeded = run(watchlist=["NFLX", "AAPL"], collect_fn=fake_collect, conn=_fresh_conn())

    assert succeeded == 2
    assert calls == ["NFLX", "AAPL"]


def test_run_continues_past_a_failing_symbol():
    calls = []

    def fake_collect(symbol, conn, max_expirations):
        calls.append(symbol)
        if symbol == "BADTICKER":
            raise ValueError("no data for symbol")
        return 10

    succeeded = run(
        watchlist=["NFLX", "BADTICKER", "AAPL"], collect_fn=fake_collect, conn=_fresh_conn()
    )

    # Both good symbols still ran despite the failure sandwiched between them —
    # this is the whole point of wrapping each symbol in its own try/except.
    assert succeeded == 2
    assert calls == ["NFLX", "BADTICKER", "AAPL"]


def test_run_with_empty_watchlist_does_nothing():
    def fake_collect(symbol, conn, max_expirations):
        raise AssertionError("collect_fn should never be called for an empty watchlist")

    succeeded = run(watchlist=[], collect_fn=fake_collect, conn=_fresh_conn())

    assert succeeded == 0


def test_run_passes_max_expirations_cap_to_collect_fn():
    seen_max_expirations = []

    def fake_collect(symbol, conn, max_expirations):
        seen_max_expirations.append(max_expirations)
        return 1

    run(watchlist=["NFLX"], collect_fn=fake_collect, conn=_fresh_conn())

    assert seen_max_expirations == [6]
