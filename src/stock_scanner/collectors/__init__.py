"""Roadmap Phase 1 — data pipeline.

Ingests market data (OHLCV, volume), news, SEC filings/EDGAR, the economic
calendar, company events, and options data. Every collector must attach a
precise timestamp to whatever it fetches — that timestamp is what later lets
us tell whether a piece of information was actually available at a given
point in time (see ARCHITECTURE.md rule 4: look-ahead bias).

Status: market_data.py (daily OHLCV via yfinance), sec_edgar.py (SEC EDGAR
filing history), economic_calendar.py (macro data via FRED), and news.py
(company headlines via Finnhub) are built. Only the options data collector
is not started yet — Phase 1's remaining piece.
"""
