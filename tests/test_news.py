"""Tests for the Phase 1 news collector (Finnhub).

Same pattern as the other Phase 1 collector tests: `http_get` is
injectable, so these use a fake response instead of calling Finnhub's real
servers.
"""

from stock_scanner.collectors.news import fetch_company_news


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_articles_payload():
    return [
        {
            "id": 7001,
            "headline": "Netflix announces price changes in several markets",
            "source": "Reuters",
            "url": "https://example.com/a",
            "datetime": 1757000000,  # a fixed Unix timestamp
        },
        {
            "id": 7002,
            "headline": "Netflix advertising revenue accelerates",
            "source": "Bloomberg",
            "url": "https://example.com/b",
            "datetime": 1757100000,
        },
    ]


def test_fetch_company_news_normalizes_rows():
    def fake_http_get(url, params, timeout):
        assert params["symbol"] == "NFLX"
        assert params["from"] == "2026-08-01"
        assert params["to"] == "2026-09-01"
        assert params["token"] == "fake-key"
        return _FakeResponse(_fake_articles_payload())

    rows = fetch_company_news("NFLX", "fake-key", "2026-08-01", "2026-09-01", http_get=fake_http_get)

    assert len(rows) == 2
    assert rows[0]["symbol"] == "NFLX"
    assert rows[0]["article_id"] == "7001"
    assert rows[0]["headline"] == "Netflix announces price changes in several markets"
    assert rows[0]["source"] == "Reuters"
    # Unix timestamp converted to an ISO string, not left as a raw int
    assert rows[0]["published_at"].startswith("2025-") or rows[0]["published_at"].startswith("2026-")
    assert "fetched_at" in rows[0]


def test_missing_api_key_raises_clear_error():
    try:
        fetch_company_news(
            "NFLX", "", "2026-08-01", "2026-09-01",
            http_get=lambda *a, **k: _FakeResponse(_fake_articles_payload()),
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "FINNHUB_API_KEY" in str(e)


def test_fetch_company_news_handles_empty_results():
    def fake_http_get(url, params, timeout):
        return _FakeResponse([])

    rows = fetch_company_news("NFLX", "fake-key", "2026-08-01", "2026-09-01", http_get=fake_http_get)
    assert rows == []
