"""Roadmap Phase 1 — data pipeline.

Ingests market data (OHLCV, volume), news, SEC filings/EDGAR, the economic
calendar, company events, and options data. Every collector must attach a
precise timestamp to whatever it fetches — that timestamp is what later lets
us tell whether a piece of information was actually available at a given
point in time (see ARCHITECTURE.md rule 4: look-ahead bias).

Not started yet — empty on purpose.
"""
