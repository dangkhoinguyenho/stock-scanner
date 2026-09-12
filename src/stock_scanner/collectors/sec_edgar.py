"""Roadmap Phase 1 — SEC EDGAR filings collector.

Fetches a company's filing history (form type, filing date, accession
number) from SEC EDGAR's public submissions API. No API key required — SEC's
fair-access policy just requires every request to carry a descriptive
User-Agent identifying the requester (see .env.example: SEC_EDGAR_USER_AGENT)
and asks that requests stay under ~10/second, which a single collector call
never approaches.

Same shape as collectors/market_data.py: the function that actually talks to
the network takes a swappable `http_get`, so the parsing logic can be
unit-tested with a fake response object — no real network call, no SEC
server dependency in the test suite.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

# src/stock_scanner/collectors/sec_edgar.py -> repo root is 3 levels up.
TICKER_MAP_CACHE = Path(__file__).resolve().parents[3] / "data" / "sec_ticker_map.json"


def _headers(user_agent: str) -> dict:
    if not user_agent:
        raise ValueError(
            "SEC_EDGAR_USER_AGENT is not set. SEC requires a descriptive "
            "User-Agent (app name + contact email) on every request, or it "
            "will start rejecting them. Set it in .env — see .env.example."
        )
    return {"User-Agent": user_agent}


def resolve_cik(
    ticker: str,
    user_agent: str,
    cache_path: Path = TICKER_MAP_CACHE,
    http_get: Callable[..., Any] | None = None,
) -> str:
    """Look up a ticker's 10-digit, zero-padded CIK — SEC's internal company
    ID, which its filing-history API needs instead of a ticker symbol.

    SEC publishes the full ticker->CIK map as one JSON file. We cache it
    locally (`cache_path`) after the first download instead of re-fetching
    a multi-thousand-entry file every time we look up one ticker — this is
    the same "don't hammer a public API for something that barely changes"
    reasoning as caching in general.
    """
    ticker_map = _load_ticker_map(user_agent, cache_path, http_get=http_get)
    ticker = ticker.upper()
    for entry in ticker_map.values():
        if entry["ticker"].upper() == ticker:
            return str(entry["cik_str"]).zfill(10)
    raise KeyError(f"No CIK found for ticker {ticker!r}")


def _load_ticker_map(
    user_agent: str,
    cache_path: Path,
    http_get: Callable[..., Any] | None = None,
) -> dict:
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    http_get = http_get or requests.get
    response = http_get(TICKER_MAP_URL, headers=_headers(user_agent), timeout=30)
    response.raise_for_status()
    data = response.json()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data))
    return data


def fetch_recent_filings(
    cik: str,
    user_agent: str,
    forms: list[str] | None = None,
    http_get: Callable[..., Any] | None = None,
) -> list[dict]:
    """Fetch a company's recent filings from SEC EDGAR.

    `cik` must already be the 10-digit zero-padded form (get one from
    resolve_cik). `forms`, if given, filters to only those form types —
    e.g. ["8-K"] for material-event disclosures (earnings, management
    changes, M&A, and similar), or ["4"] for insider-transaction filings.
    Every returned row is stamped with `fetched_at` (rule 4: look-ahead
    bias), same as the market-data collector.
    """
    http_get = http_get or requests.get
    url = SUBMISSIONS_URL.format(cik=cik)
    response = http_get(url, headers=_headers(user_agent), timeout=30)
    response.raise_for_status()
    data = response.json()

    ticker = (data.get("tickers") or [None])[0]
    recent = data["filings"]["recent"]
    fetched_at = datetime.now(timezone.utc).isoformat()

    rows = []
    for i in range(len(recent["accessionNumber"])):
        form = recent["form"][i]
        if forms and form not in forms:
            continue
        accession = recent["accessionNumber"][i]
        primary_doc = recent["primaryDocument"][i]
        accession_nodash = accession.replace("-", "")
        rows.append(
            {
                "cik": cik,
                "accession_number": accession,
                "ticker": ticker,
                "form": form,
                "filing_date": recent["filingDate"][i],
                "primary_document": primary_doc,
                "filing_url": (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{accession_nodash}/{primary_doc}"
                ),
                "fetched_at": fetched_at,
            }
        )
    return rows


def collect_and_store(
    ticker: str,
    user_agent: str,
    forms: list[str] | None = None,
    conn=None,
    http_get: Callable[..., Any] | None = None,
) -> int:
    """Resolve `ticker` to a CIK, fetch its recent filings, and persist
    them. Returns the number of rows written.
    """
    from stock_scanner.storage.database import get_connection, upsert_sec_filings

    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        cik = resolve_cik(ticker, user_agent, http_get=http_get)
        rows = fetch_recent_filings(cik, user_agent, forms=forms, http_get=http_get)
        return upsert_sec_filings(conn, rows)
    finally:
        if owns_conn:
            conn.close()
