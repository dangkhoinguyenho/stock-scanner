"""Roadmap Phase 1 — options data collector.

Fetches a live options chain snapshot via yfinance: for a given symbol,
every available expiration date, and every call/put contract at every
strike within each expiration, we record price (last/bid/ask), volume,
open interest, and implied volatility.

Read this collector's limitation before using it for anything: yfinance
(like every free source we found) only exposes the CURRENT chain, not a
historical one. There is no free way to ask "what did NFLX's options chain
look like on 2024-03-15." So this collector cannot backfill the past — it
can only start recording real snapshots from today onward, one column-
complete day at a time. Every row is stamped with `as_of_date` (the day we
captured it) specifically so that a year from now, we have a real year of
history — not because we invented a way around the missing-history gap.

For estimating what a *past* option might have been worth, see
`stock_scanner.analysis.options_pricing` — a Black-Scholes reconstruction
built from stock price history and the risk-free rate, clearly labeled as
a theoretical estimate rather than a record of a real historical price
(see that module's docstring for exactly what it can and can't reconstruct
about implied volatility, and ARCHITECTURE.md's decisions log).

This collector belongs to Phase 1 (raw data collection) and is what Phase 7
(the options layer) will eventually read live data from, once the model
translates a stock-movement prediction into an option-specific one. It
does not itself do any of that translation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def normalize_option_chain(
    symbol: str,
    expiration: str,
    calls_df: Any,
    puts_df: Any,
    as_of_date: str | None = None,
) -> list[dict]:
    """Turn yfinance's per-expiration calls/puts DataFrames (columns
    contractSymbol/strike/lastPrice/bid/ask/volume/openInterest/
    impliedVolatility/inTheMoney) into our own plain-dict row format.

    `as_of_date` defaults to today (UTC) if not given — it's the date we
    captured this snapshot, which is what accumulates into real history
    over time as this collector runs daily. It is deliberately a separate
    concept from `expiration` (the contract's own expiration date): one
    contract shows up under many different as_of_dates as it approaches
    its one fixed expiration.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    as_of_date = as_of_date or fetched_at[:10]

    rows = []
    for option_type, df in (("call", calls_df), ("put", puts_df)):
        for _, contract in df.iterrows():
            rows.append(
                {
                    "symbol": symbol,
                    "as_of_date": as_of_date,
                    "expiration": expiration,
                    "contract_symbol": contract["contractSymbol"],
                    "option_type": option_type,
                    "strike": float(contract["strike"]),
                    "last_price": _to_float_or_none(contract.get("lastPrice")),
                    "bid": _to_float_or_none(contract.get("bid")),
                    "ask": _to_float_or_none(contract.get("ask")),
                    "volume": _to_int_or_none(contract.get("volume")),
                    "open_interest": _to_int_or_none(contract.get("openInterest")),
                    "implied_volatility": _to_float_or_none(contract.get("impliedVolatility")),
                    "in_the_money": 1 if bool(contract.get("inTheMoney")) else 0,
                    "fetched_at": fetched_at,
                }
            )
    return rows


def _to_float_or_none(value: Any) -> float | None:
    # yfinance sometimes returns NaN (pandas' "missing number" marker) for
    # illiquid contracts that haven't traded — NaN != NaN is how you detect
    # it in plain Python, no pandas import needed here.
    if value is None:
        return None
    value = float(value)
    return None if value != value else value


def _to_int_or_none(value: Any) -> int | None:
    value = _to_float_or_none(value)
    return None if value is None else int(value)


def fetch_option_chain(
    symbol: str,
    ticker_factory: Callable[[str], Any] | None = None,
    expirations: list[str] | None = None,
    max_expirations: int | None = None,
) -> list[dict]:
    """Fetch a full live options chain snapshot for `symbol` across every
    expiration yfinance currently lists (or a caller-supplied subset).

    `ticker_factory`, if given, must be callable(symbol) -> an object with
    an `.options` property (tuple of expiration date strings) and an
    `.option_chain(expiration)` method returning an object with `.calls`
    and `.puts` DataFrames — that's the shape yfinance's real `Ticker` has.
    Same injectable-client pattern as every other Phase 1 collector, and
    for the same reason: testable offline, without yfinance installed.

    `max_expirations`, if set, caps how many expiration dates get fetched
    (nearest-dated first) — a liquid name can have 15-20 expirations, each
    a separate network call, so this is a knob to keep a single run cheap
    while testing rather than a correctness concern.
    """
    if ticker_factory is None:
        import yfinance as yf

        ticker_factory = yf.Ticker

    ticker = ticker_factory(symbol)
    available_expirations = list(expirations) if expirations is not None else list(ticker.options)
    if max_expirations is not None:
        available_expirations = available_expirations[:max_expirations]

    as_of_date = datetime.now(timezone.utc).date().isoformat()
    rows: list[dict] = []
    for expiration in available_expirations:
        chain = ticker.option_chain(expiration)
        rows.extend(
            normalize_option_chain(symbol, expiration, chain.calls, chain.puts, as_of_date=as_of_date)
        )
    return rows


def collect_and_store(
    symbol: str,
    conn=None,
    ticker_factory: Callable[[str], Any] | None = None,
    max_expirations: int | None = None,
) -> int:
    """Fetch today's live options chain for `symbol` and persist it.
    Returns the number of rows (individual contracts) written.
    """
    from stock_scanner.storage.database import get_connection, upsert_options_chain

    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        rows = fetch_option_chain(symbol, ticker_factory=ticker_factory, max_expirations=max_expirations)
        return upsert_options_chain(conn, rows)
    finally:
        if owns_conn:
            conn.close()
