"""Tests for the Phase 1 SEC EDGAR collector.

Both `resolve_cik` and `fetch_recent_filings` take an injectable `http_get`,
so these tests substitute a fake one instead of calling SEC's real servers —
same reasoning as test_market_data.py: instant, offline, no dependency on a
third-party service being up.
"""

import json

from stock_scanner.collectors.sec_edgar import (
    fetch_recent_filings,
    resolve_cik,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_resolve_cik_finds_matching_ticker_and_zero_pads(tmp_path):
    ticker_map_payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1065280, "ticker": "NFLX", "title": "Netflix Inc."},
    }

    def fake_http_get(url, headers, timeout):
        return _FakeResponse(ticker_map_payload)

    cache_path = tmp_path / "ticker_map.json"
    cik = resolve_cik("nflx", "StockScanner test@example.com", cache_path=cache_path, http_get=fake_http_get)

    assert cik == "0001065280"  # zero-padded to 10 digits
    assert cache_path.exists()  # cached for next time


def test_resolve_cik_uses_cache_without_calling_http_get(tmp_path):
    cache_path = tmp_path / "ticker_map.json"
    cache_path.write_text(json.dumps({"0": {"cik_str": 1065280, "ticker": "NFLX"}}))

    def fake_http_get(*args, **kwargs):
        raise AssertionError("should not hit the network when cache exists")

    cik = resolve_cik("NFLX", "StockScanner test@example.com", cache_path=cache_path, http_get=fake_http_get)
    assert cik == "0001065280"


def test_resolve_cik_raises_for_unknown_ticker(tmp_path):
    cache_path = tmp_path / "ticker_map.json"
    cache_path.write_text(json.dumps({"0": {"cik_str": 1, "ticker": "ZZZZ"}}))

    try:
        resolve_cik("NOPE", "StockScanner test@example.com", cache_path=cache_path, http_get=None)
        assert False, "expected KeyError"
    except KeyError:
        pass


def _fake_submissions_payload():
    return {
        "tickers": ["NFLX"],
        "filings": {
            "recent": {
                "accessionNumber": ["0001065280-26-000042", "0001065280-26-000041"],
                "form": ["8-K", "4"],
                "filingDate": ["2026-09-05", "2026-09-01"],
                "primaryDocument": ["nflx-8k.htm", "nflx-form4.xml"],
            }
        },
    }


def test_fetch_recent_filings_normalizes_rows():
    def fake_http_get(url, headers, timeout):
        return _FakeResponse(_fake_submissions_payload())

    rows = fetch_recent_filings("0001065280", "StockScanner test@example.com", http_get=fake_http_get)

    assert len(rows) == 2
    assert rows[0]["form"] == "8-K"
    assert rows[0]["filing_date"] == "2026-09-05"
    assert rows[0]["ticker"] == "NFLX"
    assert rows[0]["filing_url"].startswith("https://www.sec.gov/Archives/edgar/data/1065280/")
    assert "fetched_at" in rows[0]


def test_fetch_recent_filings_filters_by_form_type():
    def fake_http_get(url, headers, timeout):
        return _FakeResponse(_fake_submissions_payload())

    rows = fetch_recent_filings(
        "0001065280", "StockScanner test@example.com", forms=["8-K"], http_get=fake_http_get
    )

    assert len(rows) == 1
    assert rows[0]["form"] == "8-K"


def test_missing_user_agent_raises_clear_error():
    try:
        fetch_recent_filings("0001065280", "", http_get=lambda *a, **k: _FakeResponse(_fake_submissions_payload()))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "SEC_EDGAR_USER_AGENT" in str(e)
