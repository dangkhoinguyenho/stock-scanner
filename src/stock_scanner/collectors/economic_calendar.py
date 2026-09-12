"""Roadmap Phase 1 — economic calendar / macro data collector.

Fetches macro/economic time series (CPI, PPI, unemployment, nonfarm
payrolls, GDP, the Fed funds rate, 10-year Treasury yield) from FRED
(Federal Reserve Economic Data) — the free public API run by the St. Louis
Fed. No cost, and no rate-limit concern at the scale this project runs at.
Needs a free API key: sign up at
https://fred.stlouisfed.org/docs/api/api_key.html and set FRED_API_KEY
in .env.

Known gap, flagged rather than hidden: FRED tracks *revisions* to each
data point (an initial jobs report vs. a later-corrected figure) via
`realtime_start`/`realtime_end` fields on each observation — this is
exactly what ARCHITECTURE.md rule 4 (look-ahead bias) cares about. This
first version stores each observation's *current* value as FRED serves it
today, not the value as it was first published. Getting that right (using
FRED's vintage/ALFRED data properly) is a real follow-up task before this
feeds Phase 3/4 analysis, not something silently glossed over.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import requests

OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

# A handful of the macro series the project spec names explicitly (section 7).
# Not exhaustive — add more FRED series IDs here as needed.
COMMON_SERIES = {
    "CPI": "CPIAUCSL",
    "PPI": "PPIACO",
    "UNEMPLOYMENT_RATE": "UNRATE",
    "NONFARM_PAYROLLS": "PAYEMS",
    "GDP": "GDP",
    "FED_FUNDS_RATE": "FEDFUNDS",
    "TREASURY_10Y": "DGS10",
}


def fetch_series_observations(
    series_id: str,
    api_key: str,
    start: str | None = None,
    end: str | None = None,
    http_get: Callable[..., Any] | None = None,
) -> list[dict]:
    """Fetch observations for one FRED series (e.g. "CPIAUCSL" for CPI).

    `start`/`end` are optional YYYY-MM-DD bounds on the observation date.
    Same injectable-`http_get` pattern as the other Phase 1 collectors —
    real callers leave it as None and get `requests.get`; tests pass a fake
    one so this never needs a real network call to verify.
    """
    if not api_key:
        raise ValueError(
            "FRED_API_KEY is not set. Sign up for a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html and set it in .env."
        )

    http_get = http_get or requests.get
    params = {"series_id": series_id, "api_key": api_key, "file_type": "json"}
    if start:
        params["observation_start"] = start
    if end:
        params["observation_end"] = end

    response = http_get(OBSERVATIONS_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for obs in data["observations"]:
        if obs["value"] == ".":
            # FRED's own convention for "no data at this date" — skip it
            # rather than storing a fake zero or crashing on float(".").
            continue
        rows.append(
            {
                "series_id": series_id,
                "date": obs["date"],
                "value": float(obs["value"]),
                "realtime_start": obs.get("realtime_start"),
                "fetched_at": fetched_at,
            }
        )
    return rows


def collect_and_store(
    series_id: str,
    api_key: str,
    start: str | None = None,
    end: str | None = None,
    conn=None,
    http_get: Callable[..., Any] | None = None,
) -> int:
    """Fetch observations for `series_id` and persist them. Returns the
    number of rows written. `series_id` can be a raw FRED code ("CPIAUCSL")
    or one of the friendly names in COMMON_SERIES ("CPI").
    """
    from stock_scanner.storage.database import (
        get_connection,
        upsert_economic_observations,
    )

    series_id = COMMON_SERIES.get(series_id.upper(), series_id)

    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        rows = fetch_series_observations(series_id, api_key, start=start, end=end, http_get=http_get)
        return upsert_economic_observations(conn, rows)
    finally:
        if owns_conn:
            conn.close()
