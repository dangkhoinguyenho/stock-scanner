# Stock Scanner

An event-driven, continuously learning market scanner that ingests real-time financial news, SEC filings, economic events, market/volume data, and options data; converts information into structured events; measures the historical price reaction to similar events at multiple time horizons; learns which event/market-condition combinations produce significant and fast abnormal movements for each ticker; and ranks current opportunities by probability, magnitude, speed, and options-specific payoff potential — while avoiding look-ahead and survivorship bias.

This is a research/ranking tool, not financial advice. It never outputs a bare "buy" or "bullish" — every score comes with the evidence behind it: comparable historical events, base rate, average/median return, and confidence.

## Project status

This repo is at **Stage 0 (repo scaffolding)**. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full 10-phase roadmap and what's actually built vs. still conceptual.

The full project spec (goals, data requirements, model design, domain rules) lives in the attached Claude project, not duplicated here — see `claude/project-spec.md` there. This README and ARCHITECTURE.md are the repo's own source of truth for what's *actually implemented*.

## Repo layout

```
src/stock_scanner/
    config.py       # central place all code reads settings/API keys from
    collectors/     # Phase 1 — market data, news, SEC filings, macro, options data ingestion
    events/         # Phase 2 — turning raw collected data into normalized structured events
    storage/        # Phase 3 — the event-response database (event -> price reaction at multiple horizons)
    analysis/       # Phase 4-5 — historical stats, abnormal/relative returns, similarity search
    scanner/        # Phase 8 — ranking the live universe into an opportunity score
tests/              # one test file per module, written alongside the code (not after)
data/               # local data cache (gitignored — never commit data files or API keys)
```

Each subpackage's `__init__.py` names which roadmap phase it belongs to, so it's always clear what stage a piece of code is part of.

## Environment setup

Requires Python 3.11+.

```bash
# from inside the Stock Scanner folder
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell/cmd
# source .venv/bin/activate   # macOS/Linux, if you ever work from one

pip install -e ".[dev]"
cp .env.example .env          # then fill in real API keys — .env is gitignored, never commit it
```

## Running tests

```bash
pytest
```

## Why a virtual environment, and why `-e`

A virtual environment (`.venv`) keeps this project's Python packages isolated from every other Python project on your machine — without it, two projects that need different versions of the same library will eventually break each other. `pip install -e ".[dev]"` installs this package in "editable" mode: Python imports `stock_scanner` straight from `src/` instead of copying it somewhere else, so code edits take effect immediately without reinstalling, and it also pulls in the `dev` extra (currently just `pytest`) defined in `pyproject.toml`.
