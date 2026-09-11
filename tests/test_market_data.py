"""Tests for the Phase 1 market-data collector.

`normalize_history` is tested directly with a hand-built pandas DataFrame
shaped like what yfinance returns — this verifies the parsing logic
without needing yfinance installed or a network call.

`fetch_daily_ohlcv` is tested by injecting a fake ticker factory (see its
docstring) rather than the real yfinance one, for the same reason: this
suite should run instantly and offline, every time, on any machine. The
real, live yfinance call is verified manually against actual data instead
(see README) — a unit test that depends on a live network call would make
the whole suite slow and occasionally fail for reasons that have nothing
to do with a bug in this code (Yahoo being down, rate limits, etc.).
"""

import pandas as pd

from stock_scanner.collectors.market_data import fetch_daily_ohlcv, normalize_history


def _fake_history_df() -> pd.DataFrame:
    index = pd.to_datetime(["2026-09-10", "2026-09-11"])
    return pd.DataFrame(
        {
            "Open": [100.0, 103.0],
            "High": [105.0, 108.0],
            "Low": [99.0, 102.0],
            "Close": [103.0, 107.0],
            "Volume": [1_000_000, 1_200_000],
        },
        index=index,
    )


def test_normalize_history_shape_and_values():
    rows = normalize_history("NFLX", _fake_history_df())

    assert len(rows) == 2
    assert rows[0]["symbol"] == "NFLX"
    assert rows[0]["date"] == "2026-09-10"
    assert rows[0]["close"] == 103.0
    assert rows[1]["volume"] == 1_200_000
    assert "fetched_at" in rows[0]  # every row records when we learned it


def test_fetch_daily_ohlcv_uses_injected_ticker_factory():
    """Proves fetch_daily_ohlcv is testable without yfinance or a network
    call, by substituting a fake object with the same `.history()` shape
    yfinance's real Ticker has.
    """

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, start, end, interval="1d"):
            assert self.symbol == "NFLX"
            assert start == "2026-09-01"
            assert end == "2026-09-12"
            assert interval == "1d"
            return _fake_history_df()

    rows = fetch_daily_ohlcv("NFLX", "2026-09-01", "2026-09-12", ticker_factory=FakeTicker)

    assert len(rows) == 2
    assert rows[0]["symbol"] == "NFLX"
    assert rows[1]["close"] == 107.0
