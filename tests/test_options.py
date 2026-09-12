"""Tests for the Phase 1 options chain collector.

Same shape as test_market_data.py: `normalize_option_chain` is tested
directly with hand-built pandas DataFrames shaped like what yfinance's
`option_chain()` returns, and `fetch_option_chain` is tested by injecting a
fake ticker factory — no yfinance install or network call needed to verify
the parsing/normalization logic.
"""

import math

import pandas as pd

from stock_scanner.collectors.options import fetch_option_chain, normalize_option_chain


def _fake_calls_df():
    return pd.DataFrame(
        {
            "contractSymbol": ["NFLX260918C00700000", "NFLX260918C00750000"],
            "strike": [700.0, 750.0],
            "lastPrice": [42.5, 20.1],
            "bid": [42.0, 19.8],
            "ask": [43.0, 20.4],
            "volume": [120, float("nan")],  # illiquid contract: no trades today
            "openInterest": [500, 80],
            "impliedVolatility": [0.35, 0.38],
            "inTheMoney": [True, False],
        }
    )


def _fake_puts_df():
    return pd.DataFrame(
        {
            "contractSymbol": ["NFLX260918P00700000"],
            "strike": [700.0],
            "lastPrice": [15.0],
            "bid": [14.7],
            "ask": [15.3],
            "volume": [40],
            "openInterest": [200],
            "impliedVolatility": [0.33],
            "inTheMoney": [False],
        }
    )


def test_normalize_option_chain_shape_and_values():
    rows = normalize_option_chain(
        "NFLX", "2026-09-18", _fake_calls_df(), _fake_puts_df(), as_of_date="2026-09-12"
    )

    assert len(rows) == 3  # 2 calls + 1 put
    calls = [r for r in rows if r["option_type"] == "call"]
    puts = [r for r in rows if r["option_type"] == "put"]
    assert len(calls) == 2
    assert len(puts) == 1

    itm_call = next(r for r in calls if r["strike"] == 700.0)
    assert itm_call["symbol"] == "NFLX"
    assert itm_call["as_of_date"] == "2026-09-12"
    assert itm_call["expiration"] == "2026-09-18"
    assert itm_call["contract_symbol"] == "NFLX260918C00700000"
    assert itm_call["last_price"] == 42.5
    assert itm_call["implied_volatility"] == 0.35
    assert itm_call["in_the_money"] == 1
    assert "fetched_at" in itm_call

    otm_call = next(r for r in calls if r["strike"] == 750.0)
    assert otm_call["volume"] is None  # NaN converted to None, not left as NaN
    assert otm_call["in_the_money"] == 0


def test_fetch_option_chain_uses_injected_ticker_factory():
    """Proves fetch_option_chain is testable without yfinance or a network
    call, by substituting a fake object with the same `.options` /
    `.option_chain()` shape yfinance's real Ticker has.
    """

    class FakeChain:
        def __init__(self, calls, puts):
            self.calls = calls
            self.puts = puts

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
            self.options = ("2026-09-18", "2026-10-16")

        def option_chain(self, expiration):
            assert self.symbol == "NFLX"
            assert expiration in self.options
            return FakeChain(_fake_calls_df(), _fake_puts_df())

    rows = fetch_option_chain("NFLX", ticker_factory=FakeTicker)

    # 3 contracts per expiration x 2 expirations
    assert len(rows) == 6
    expirations_seen = {r["expiration"] for r in rows}
    assert expirations_seen == {"2026-09-18", "2026-10-16"}


def test_fetch_option_chain_respects_max_expirations():
    class FakeChain:
        def __init__(self, calls, puts):
            self.calls = calls
            self.puts = puts

    class FakeTicker:
        def __init__(self, symbol):
            self.options = ("2026-09-18", "2026-10-16", "2026-11-20")

        def option_chain(self, expiration):
            return FakeChain(_fake_calls_df(), _fake_puts_df())

    rows = fetch_option_chain("NFLX", ticker_factory=FakeTicker, max_expirations=1)

    assert {r["expiration"] for r in rows} == {"2026-09-18"}
