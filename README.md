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
    analysis/       # Phase 4-5, and Phase 7's Black-Scholes reconstruction — historical stats, abnormal/relative returns, similarity search, options valuation
    scanner/        # Phase 8 — ranking the live universe into an opportunity score
    jobs/           # scheduled/unattended entry points, e.g. the daily options snapshot job
tests/              # one test file per module, written alongside the code (not after)
data/               # local data cache (gitignored — never commit data files or API keys)
logs/               # job run logs (gitignored — see "Running the daily options job" below)
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

## Running the daily options job

There is no free source of *historical* options data — every provider we found (yfinance included) only exposes the current chain. `jobs/daily_options_snapshot.py` is how this project gets around that: run it once a day and it records a real, permanent snapshot; skip a day and that day's history is gone for good, not something that can be backfilled later. So it needs to run every day, indefinitely, whether or not anyone is watching — which means it belongs to the operating system's own scheduler, not something triggered from inside a chat session.

One-time setup on Windows — paste this whole block into PowerShell once:

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\dangk\OneDrive\Máy tính\Stock Scanner\run_daily_options.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At 5:00PM
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable
Register-ScheduledTask -TaskName "StockScannerDailyOptions" -Action $action -Trigger $trigger -Settings $settings -Description "Daily options chain snapshot for Stock Scanner (Phase 1)"
```

What each piece does:
- `-At 5:00PM` — runs daily at 5:00 PM Pacific (adjust if you move time zones): the US market closes at 4:00 PM Eastern = 1:00 PM Pacific, so this gives a 4-hour buffer for the day's data to fully settle.
- `-WakeToRun` — if your laptop is *asleep* (lid closed, screen off, but not shut down) at 5:00 PM, Windows wakes it just long enough to run the job, then it can go back to sleep. This does NOT work if the laptop is fully powered off — no software can wake a machine that isn't running at all, that's a hardware limitation, not a settings gap.
- `-StartWhenAvailable` — if 5:00 PM was missed entirely (laptop was off, or asleep without waking), the job fires automatically the next time you turn the laptop on — instead of silently being skipped. Note this is *not* a downgrade for that day's data: since the market is closed after 4:00 PM ET anyway, the options chain doesn't change again until the next trading day opens, so a catch-up run at 9 PM (or whenever you next log in) still captures the same end-of-day snapshot as a run at 5:00 PM would have.

Honest limit, not a bug: if the laptop stays fully powered off for a stretch of days (not just asleep), those specific days are genuinely never collected — there's no catching that up later, per the whole reason this job exists. If reliable day-to-day coverage ever becomes important enough to justify it, the real fix is running this on a machine that's always on (a small always-on cloud server, a few dollars a month) — not worth setting up now, but worth knowing the option exists later.

To check it's actually running: open Task Scheduler, find "StockScannerDailyOptions" — the "Last Run Result" column should read `The operation completed successfully. (0x0)` once it's fired — or just check `logs/daily_options.log` for a new line each day. To remove it later: `Unregister-ScheduledTask -TaskName "StockScannerDailyOptions" -Confirm:$false`.

## Why a virtual environment, and why `-e`

A virtual environment (`.venv`) keeps this project's Python packages isolated from every other Python project on your machine — without it, two projects that need different versions of the same library will eventually break each other. `pip install -e ".[dev]"` installs this package in "editable" mode: Python imports `stock_scanner` straight from `src/` instead of copying it somewhere else, so code edits take effect immediately without reinstalling, and it also pulls in the `dev` extra (currently just `pytest`) defined in `pyproject.toml`.
