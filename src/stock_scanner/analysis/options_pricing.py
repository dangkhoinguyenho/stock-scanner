"""Roadmap Phase 7 — options layer: theoretical option valuation.

This module answers "what would an option like this one have been worth
on some past date" using the Black-Scholes formula, a standard options
pricing model. It exists specifically to work around the gap flagged in
collectors/options.py: there is no free source of real historical options
data (no historical implied volatility, open interest, or bid/ask), so we
cannot look up what an option actually traded at in the past. What we CAN
do is reconstruct a theoretical price from things we do have for free:
stock price history (collectors/market_data.py) and the risk-free interest
rate (collectors/economic_calendar.py, FRED series DGS10).

Read this before trusting any number this module produces:

Black-Scholes needs five inputs: the stock price (S), the strike (K), the
time to expiration (T), the risk-free rate (r), and volatility (sigma). We
have real values for S, K, T, and r. For sigma, this module uses REALIZED
volatility — the standard deviation of the stock's own past returns,
annualized — because that's the only volatility number computable purely
from price history.

Realized volatility is NOT the same thing as implied volatility, and this
is not a rounding-error difference — it's a real, structural limitation:

- Implied volatility is backed out from real option prices people actually
  paid. It reflects the market's forward-looking uncertainty, and it can
  move well before the stock does (e.g. IV often rises heading into an
  earnings date on no price movement at all, purely because uncertainty
  is priced in, then collapses right after the event resolves — "IV
  crush" — even when the stock moved in the "right" direction). Realized
  volatility, computed only from past price history, cannot see any of
  that anticipatory pricing or the crush afterward.
- Every value this module returns is therefore a theoretical estimate, not
  a record of a real historical price. Every function here labels its
  output accordingly. Never present a number from this module as "what the
  option was worth" without that caveat — that would violate the project's
  core rule against overstating confidence (ARCHITECTURE.md rule 1).

This module also has no opinion on direction, magnitude, or speed
(ARCHITECTURE.md rule 2) — it prices a single, fully-specified contract
(strike + expiration + option type) that the CALLER chooses.
"""

from __future__ import annotations

import math
from datetime import date


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function, via math.erf —
    no scipy dependency needed for something this standard.
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    if T <= 0:
        raise ValueError("time_to_expiration_years (T) must be positive — expiration must be after the valuation date")
    if sigma <= 0:
        raise ValueError("sigma (volatility) must be positive")
    if S <= 0 or K <= 0:
        raise ValueError("stock price and strike must both be positive")

    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def black_scholes_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Theoretical Black-Scholes price of a European option.

    S = current/underlying stock price
    K = strike price
    T = time to expiration, in years (e.g. 30 calendar days = 30/365)
    r = risk-free interest rate, as a decimal (0.04, not 4)
    sigma = annualized volatility, as a decimal (0.30, not 30)
    option_type = "call" or "put"

    Black-Scholes technically assumes European-style exercise (only
    exercisable at expiration); most US equity options are American-style
    (exercisable any time). For anything this project uses purely for
    relative comparison and backtesting exploration, that gap is a known,
    minor simplification — not something to treat as exact.
    """
    option_type = option_type.lower()
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    discounted_K = K * math.exp(-r * T)

    if option_type == "call":
        return S * _norm_cdf(d1) - discounted_K * _norm_cdf(d2)
    return discounted_K * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def black_scholes_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> dict:
    """Delta, gamma, theta, vega for the same contract as
    black_scholes_price. Greeks describe how the theoretical price moves
    as one input changes — delta per $1 the stock moves, gamma per $1 of
    delta change, vega per 1 percentage point of volatility, theta per day
    of time decay (always negative: time passing works against a long
    option, all else equal — this is the mechanism behind IV crush).
    """
    option_type = option_type.lower()
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    pdf_d1 = _norm_pdf(d1)
    discounted_K = K * math.exp(-r * T)

    gamma = pdf_d1 / (S * sigma * math.sqrt(T))
    vega = S * pdf_d1 * math.sqrt(T) / 100.0  # per 1 vol point (0.01), not per 1.0

    if option_type == "call":
        delta = _norm_cdf(d1)
        theta_per_year = (
            -(S * pdf_d1 * sigma) / (2 * math.sqrt(T)) - r * discounted_K * _norm_cdf(d2)
        )
    else:
        delta = _norm_cdf(d1) - 1.0
        theta_per_year = (
            -(S * pdf_d1 * sigma) / (2 * math.sqrt(T)) + r * discounted_K * _norm_cdf(-d2)
        )

    return {
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta_per_day": theta_per_year / 365.0,
    }


def realized_volatility(closes: list[float]) -> float:
    """Annualized realized volatility from a trailing series of daily
    closing prices (oldest first), computed as the sample standard
    deviation of daily log returns, annualized by sqrt(252) (the standard
    count of US trading days in a year).

    This is NOT implied volatility — see this module's docstring for the
    real distinction. It is the best volatility estimate computable purely
    from price history.
    """
    if len(closes) < 2:
        raise ValueError("need at least 2 closing prices to compute a return")

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean_return = sum(log_returns) / len(log_returns)

    if len(log_returns) < 2:
        raise ValueError("need at least 2 returns (3 prices) to compute a sample standard deviation")

    variance = sum((r - mean_return) ** 2 for r in log_returns) / (len(log_returns) - 1)
    daily_vol = math.sqrt(variance)
    return daily_vol * math.sqrt(252)


def estimate_historical_option_price(
    conn,
    symbol: str,
    as_of_date: str,
    expiration_date: str,
    strike: float,
    option_type: str,
    risk_free_rate: float | None = None,
    volatility_window_days: int = 60,
    risk_free_series_id: str = "DGS10",
) -> dict:
    """Reconstruct a theoretical option price/greeks as of a past date,
    using only data this project already collects for free: stock price
    history (for the underlying price and realized volatility) and the
    risk-free rate (from FRED, if already collected via
    collectors/economic_calendar.py — pass risk_free_rate directly to skip
    that lookup).

    as_of_date / expiration_date: "YYYY-MM-DD" strings. Enforces
    ARCHITECTURE.md rule 5 (expiration-awareness): raises if
    expiration_date is not strictly after as_of_date, since a catalyst (or
    a valuation) after an option's expiration isn't relevant to it.

    Look-ahead-bias note (rule 4): volatility and price are computed only
    from prices dated on or before as_of_date — never from data that would
    not have existed yet at that point in time.

    Returns a dict of every input used plus the estimate, so the estimate
    is always traceable back to what produced it — never a bare number.
    """
    from stock_scanner.storage.database import get_daily_prices, get_economic_observations

    as_of = date.fromisoformat(as_of_date)
    expiration = date.fromisoformat(expiration_date)
    if expiration <= as_of:
        raise ValueError(
            f"expiration_date ({expiration_date}) must be after as_of_date ({as_of_date}) — "
            "this function values an option BEFORE it expires, not after"
        )

    price_rows = get_daily_prices(conn, symbol, end=as_of_date)
    if len(price_rows) < 21:
        raise ValueError(
            f"only {len(price_rows)} days of price history for {symbol} on or before {as_of_date} — "
            "need at least 21 (20 returns) to estimate volatility reliably. Collect more price "
            "history first (collectors/market_data.py)."
        )

    window_rows = price_rows[-(volatility_window_days + 1):]
    closes = [row["close"] for row in window_rows]
    underlying_price = closes[-1]
    sigma = realized_volatility(closes)

    if risk_free_rate is None:
        rate_rows = get_economic_observations(conn, risk_free_series_id, end=as_of_date)
        if not rate_rows:
            raise ValueError(
                f"no {risk_free_series_id} observations on or before {as_of_date} — collect economic "
                "calendar data first (collectors/economic_calendar.py), or pass risk_free_rate explicitly"
            )
        # FRED's Treasury yield series (e.g. DGS10) is quoted in percent (4.25 means 4.25%).
        risk_free_rate = rate_rows[-1]["value"] / 100.0

    time_to_expiration_years = (expiration - as_of).days / 365.0

    price = black_scholes_price(
        underlying_price, strike, time_to_expiration_years, risk_free_rate, sigma, option_type
    )
    greeks = black_scholes_greeks(
        underlying_price, strike, time_to_expiration_years, risk_free_rate, sigma, option_type
    )

    return {
        "symbol": symbol,
        "as_of_date": as_of_date,
        "expiration_date": expiration_date,
        "strike": strike,
        "option_type": option_type,
        "underlying_price": underlying_price,
        "risk_free_rate": risk_free_rate,
        "realized_volatility": sigma,
        "volatility_window_days_used": len(window_rows) - 1,
        "time_to_expiration_years": time_to_expiration_years,
        "estimated_price": price,
        "greeks": greeks,
        "method": "black_scholes_with_realized_volatility",
        "note": (
            "THEORETICAL ESTIMATE, not a real historical option price. Uses realized "
            "(historical) volatility as a substitute for implied volatility, which this "
            "reconstruction cannot recover — see options_pricing.py's module docstring."
        ),
    }
