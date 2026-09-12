"""Roadmap Phase 1 — daily options snapshot job.

Runs the options collector (collectors/options.py) once for every symbol in
the configured watchlist (see config.py's WATCHLIST setting). Meant to be
invoked once a day by an OS-level scheduler — see run_daily_options.bat and
the README for how this is wired into Windows Task Scheduler.

Why this has to run daily, unattended, indefinitely: collectors/options.py
can only ever capture *today's* options chain — no free source exposes a
historical one. The only way this project ever accumulates real options
history is by this job actually running every single day without gaps.
Missing a day is a permanent, unrecoverable gap in that history (unlike
market data or SEC filings, which can be backfilled for any past date).

Two design choices here exist specifically because this runs unattended,
which none of the other Phase 1 collectors had to worry about (Kenny ran
those interactively and could see failures immediately):

1. One symbol failing (bad ticker, a rate limit, a network blip) must not
   stop the rest of the watchlist from being collected — each symbol is
   wrapped in its own try/except, and the run continues past a failure.
2. Every symbol's result (success + row count, or failure + error) is
   printed with a timestamp. Nothing is written to a project-managed log
   file from inside Python — run_daily_options.bat redirects this
   process's output to logs/daily_options.log, so there's exactly one
   place responsible for "where do logs live" (the batch script), not two.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Callable

from stock_scanner.collectors.options import collect_and_store
from stock_scanner.config import get_settings
from stock_scanner.storage.database import get_connection


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(
    watchlist: list[str] | None = None,
    collect_fn: Callable[..., int] | None = None,
    conn=None,
) -> int:
    """Collect today's options chain for every symbol in the watchlist.

    `watchlist` defaults to config.py's Settings.watchlist (from the
    WATCHLIST env var) if not given. `collect_fn` and `conn` are injectable
    for the same testability reason every other collector in this project
    is structured this way — see tests/test_daily_options_snapshot.py.

    Returns how many symbols succeeded, so a caller (or this file's own
    `__main__` block) can turn that into a process exit code.
    """
    watchlist = list(watchlist) if watchlist is not None else list(get_settings().watchlist)
    collect_fn = collect_fn or collect_and_store

    if not watchlist:
        print(f"{_timestamp()} ERROR no watchlist configured (set WATCHLIST in .env) — nothing to collect")
        return 0

    owns_conn = conn is None
    if conn is None:
        conn = get_connection()

    succeeded = 0
    try:
        for symbol in watchlist:
            try:
                # Capped to the 6 nearest expirations rather than every expiration
                # yfinance lists (some names have 15-20) — this project is focused
                # on short-term catalysts, so near-dated contracts matter most, and
                # this keeps a daily run to a handful of network calls per symbol
                # instead of dozens. Raise this later if a use case needs further-
                # dated contracts too.
                rows_written = collect_fn(symbol, conn=conn, max_expirations=6)
                print(f"{_timestamp()} OK {symbol}: {rows_written} option contract rows written")
                succeeded += 1
            except Exception as e:  # one bad symbol must not kill the whole run
                print(f"{_timestamp()} FAILED {symbol}: {e!r}")
    finally:
        if owns_conn:
            conn.close()

    print(f"{_timestamp()} run complete: {succeeded}/{len(watchlist)} symbols succeeded")
    return succeeded


if __name__ == "__main__":
    succeeded_count = run()
    # Exit code 0 only if at least one symbol succeeded — lets Task Scheduler's
    # own "last run result" column reflect whether the job actually did anything.
    sys.exit(0 if succeeded_count > 0 else 1)
