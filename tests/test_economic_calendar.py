"""Tests for the Phase 1 economic calendar (FRED) collector.

Same pattern as test_market_data.py and test_sec_edgar.py: `http_get` is
injectable, so these tests use a fake response instead of calling FRED's
real servers.
"""

from stock_scanner.collectors.economic_calendar import (
    COMMON_SERIES,
    fetch_series_observations,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_cpi_payload():
    return {
        "observations": [
            {"date": "2026-07-01", "value": "312.332", "realtime_start": "2026-08-13"},
            {"date": "2026-08-01", "value": "313.049", "realtime_start": "2026-09-10"},
            {"date": "2026-09-01", "value": ".", "realtime_start": "2026-10-10"},  # not released yet
        ]
    }


def test_fetch_series_observations_normalizes_rows_and_skips_missing():
    def fake_http_get(url, params, timeout):
        assert params["series_id"] == "CPIAUCSL"
        assert params["api_key"] == "fake-key"
        return _FakeResponse(_fake_cpi_payload())

    rows = fetch_series_observations("CPIAUCSL", "fake-key", http_get=fake_http_get)

    # the "." (not-yet-released) observation must be dropped, not crash on float(".")
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-07-01"
    assert rows[0]["value"] == 312.332
    assert rows[0]["series_id"] == "CPIAUCSL"
    assert rows[0]["realtime_start"] == "2026-08-13"
    assert "fetched_at" in rows[0]


def test_missing_api_key_raises_clear_error():
    try:
        fetch_series_observations("CPIAUCSL", "", http_get=lambda *a, **k: _FakeResponse(_fake_cpi_payload()))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "FRED_API_KEY" in str(e)


def test_common_series_has_expected_friendly_names():
    assert COMMON_SERIES["CPI"] == "CPIAUCSL"
    assert COMMON_SERIES["FED_FUNDS_RATE"] == "FEDFUNDS"
