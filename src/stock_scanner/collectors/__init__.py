"""Roadmap Phase 1 — data pipeline.

Ingests market data (OHLCV, volume), news, SEC filings/EDGAR, the economic
calendar, company events, and options data. Every collector must attach a
precise timestamp to whatever it fetches — that timestamp is what later lets
us tell whether a piece of information was actually available at a given
point in time (see ARCHITECTURE.md rule 4: look-ahead bias).

Status: market_data.py (daily OHLCV via yfinance), sec_edgar.py (SEC EDGAR
filing history), economic_calendar.py (macro data via FRED), news.py
(company headlines via Finnhub), and options.py (live options chain via
yfinance) are all built — Phase 1's five collectors are code-complete.

One caveat specific to options.py: unlike the other four sources, it can
only capture the chain as it looks *today* — there is no free historical
options data source, so this collector cannot backfill the past. It has
to run daily, from now on, to accumulate real history over time. See its
own docstring, and stock_scanner.analysis.options_pricing (a Black-Scholes
theoretical reconstruction, not real historical data) for how we're
working around that gap for research purposes in the meantime.
"""
