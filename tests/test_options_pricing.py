"""Tests for the Phase 7 Black-Scholes theoretical option pricing module.

black_scholes_price is checked against a well-known textbook reference
case (S=K=100, T=1yr, r=5%, sigma=20%) and against put-call parity — an
identity that must hold for ANY valid inputs, which catches formula bugs
independent of any single reference value.

realized_volatility is cross-checked against Python's own `statistics`
module computing the same standard deviation a different way, so the test
isn't just repeating the implementation's own arithmetic.

estimate_historical_option_price is tested with an in-memory database
(fake price + FRED rows, no network), the same pattern as every other
Phase 1 collector test in this project.
"""

import math
import sqlite3
import statistics

from stock_scanner.analysis.options_pricing import (
    black_scholes_greeks,
    black_scholes_price,
    estimate_historical_option_price,
    realized_volatility,
)
from stock_scanner.storage.database import init_schema, upsert_daily_prices, upsert_economic_observations


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_black_scholes_price_matches_known_reference_case():
    # Classic textbook example: S=100, K=100, T=1yr, r=5%, sigma=20%.
    call = black_scholes_price(100, 100, 1.0, 0.05, 0.20, "call")
    put = black_scholes_price(100, 100, 1.0, 0.05, 0.20, "put")

    assert call == _approx(10.4506, 0.01)
    assert put == _approx(5.5735, 0.01)


def test_put_call_parity_holds_for_arbitrary_inputs():
    """call - put == S - K*e^(-rT) must hold for ANY valid Black-Scholes
    inputs — this is a model-independent sanity check, not tied to the
    one reference case above.
    """
    S, K, T, r, sigma = 137.0, 150.0, 0.25, 0.03, 0.45
    call = black_scholes_price(S, K, T, r, sigma, "call")
    put = black_scholes_price(S, K, T, r, sigma, "put")

    parity_rhs = S - K * math.exp(-r * T)
    assert (call - put) == _approx(parity_rhs, 1e-6)


def test_black_scholes_rejects_expiration_at_or_before_valuation():
    try:
        black_scholes_price(100, 100, 0, 0.05, 0.20, "call")
        assert False, "expected ValueError for T <= 0"
    except ValueError as e:
        assert "positive" in str(e)


def test_black_scholes_greeks_delta_ranges_are_sane():
    call_greeks = black_scholes_greeks(100, 100, 1.0, 0.05, 0.20, "call")
    put_greeks = black_scholes_greeks(100, 100, 1.0, 0.05, 0.20, "put")

    assert 0.0 < call_greeks["delta"] < 1.0
    assert -1.0 < put_greeks["delta"] < 0.0
    assert call_greeks["gamma"] > 0
    assert call_greeks["theta_per_day"] < 0  # time decay always works against a long option


def test_realized_volatility_matches_independent_stdlib_computation():
    closes = [100.0, 102.0, 101.0, 105.0, 103.0, 107.0, 104.0, 110.0]
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    expected = statistics.stdev(log_returns) * math.sqrt(252)

    actual = realized_volatility(closes)
    assert actual == _approx(expected, 1e-9)


def test_realized_volatility_requires_at_least_three_prices():
    try:
        realized_volatility([100.0, 101.0])
        assert False, "expected ValueError for too few prices"
    except ValueError as e:
        assert "return" in str(e) or "price" in str(e)


def test_estimate_historical_option_price_end_to_end():
    conn = _fresh_conn()
    # 25 days of made-up but plausible price history, ending on the as_of_date.
    prices = [100.0 + (i % 5) - (i % 3) for i in range(25)]
    rows = [
        {"symbol": "NFLX", "date": f"2026-08-{i + 1:02d}",
         "open": p, "high": p + 1, "low": p - 1, "close": p, "volume": 1_000_000,
         "fetched_at": "2026-09-01T00:00:00+00:00"}
        for i, p in enumerate(prices)
    ]
    upsert_daily_prices(conn, rows)
    upsert_economic_observations(conn, [
        {"series_id": "DGS10", "date": "2026-08-25", "value": 4.25,
         "realtime_start": "2026-08-25", "fetched_at": "2026-09-01T00:00:00+00:00"},
    ])

    result = estimate_historical_option_price(
        conn,
        symbol="NFLX",
        as_of_date="2026-08-25",
        expiration_date="2026-09-25",
        strike=100.0,
        option_type="call",
    )

    assert result["estimated_price"] > 0
    assert result["risk_free_rate"] == 0.0425
    assert result["method"] == "black_scholes_with_realized_volatility"
    assert "THEORETICAL ESTIMATE" in result["note"]
    assert result["greeks"]["delta"] > 0


def test_estimate_historical_option_price_rejects_expiration_before_as_of_date():
    conn = _fresh_conn()
    try:
        estimate_historical_option_price(
            conn, "NFLX", as_of_date="2026-09-25", expiration_date="2026-08-25",
            strike=100.0, option_type="call",
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "expiration_date" in str(e)


def test_estimate_historical_option_price_requires_enough_history():
    conn = _fresh_conn()
    upsert_daily_prices(conn, [
        {"symbol": "NFLX", "date": "2026-08-24", "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 1, "fetched_at": "2026-09-01T00:00:00+00:00"},
    ])

    try:
        estimate_historical_option_price(
            conn, "NFLX", as_of_date="2026-08-25", expiration_date="2026-09-25",
            strike=100.0, option_type="call", risk_free_rate=0.04,
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "history" in str(e)


def _approx(expected: float, tolerance: float):
    class _Approx:
        def __eq__(self, other):
            return abs(other - expected) <= tolerance

    return _Approx()
