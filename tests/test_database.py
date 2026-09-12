"""Tests for the Phase 1 raw price storage layer.

Uses an in-memory SQLite database (":memory:") so these run instantly,
leave nothing on disk, and need no network — the storage logic itself is
what's under test, not any real data source.
"""

import sqlite3

from stock_scanner.storage.database import (
    get_daily_prices,
    get_economic_observations,
    get_news_articles,
    get_sec_filings,
    init_schema,
    upsert_daily_prices,
    upsert_economic_observations,
    upsert_news_articles,
    upsert_sec_filings,
)


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_upsert_and_read_back():
    conn = _fresh_conn()
    rows = [
        {
            "symbol": "NFLX", "date": "2026-09-10", "open": 100.0, "high": 105.0,
            "low": 99.0, "close": 103.0, "volume": 1_000_000,
            "fetched_at": "2026-09-11T00:00:00+00:00",
        },
        {
            "symbol": "NFLX", "date": "2026-09-11", "open": 103.0, "high": 108.0,
            "low": 102.0, "close": 107.0, "volume": 1_200_000,
            "fetched_at": "2026-09-11T00:00:00+00:00",
        },
    ]

    written = upsert_daily_prices(conn, rows)
    assert written == 2

    fetched = get_daily_prices(conn, "NFLX")
    assert len(fetched) == 2
    assert fetched[0]["date"] == "2026-09-10"
    assert fetched[1]["close"] == 107.0


def test_upsert_overwrites_same_symbol_and_date_instead_of_duplicating():
    conn = _fresh_conn()
    row = {
        "symbol": "NFLX", "date": "2026-09-10", "open": 100.0, "high": 105.0,
        "low": 99.0, "close": 103.0, "volume": 1_000_000,
        "fetched_at": "2026-09-11T00:00:00+00:00",
    }
    upsert_daily_prices(conn, [row])

    corrected = dict(row, close=104.5, fetched_at="2026-09-11T12:00:00+00:00")
    upsert_daily_prices(conn, [corrected])

    fetched = get_daily_prices(conn, "NFLX")
    assert len(fetched) == 1
    assert fetched[0]["close"] == 104.5
    assert fetched[0]["fetched_at"] == "2026-09-11T12:00:00+00:00"


def test_date_range_filtering_is_inclusive():
    conn = _fresh_conn()
    rows = [
        {
            "symbol": "NFLX", "date": d, "open": 1.0, "high": 1.0, "low": 1.0,
            "close": 1.0, "volume": 1, "fetched_at": "2026-09-11T00:00:00+00:00",
        }
        for d in ["2026-09-01", "2026-09-05", "2026-09-10"]
    ]
    upsert_daily_prices(conn, rows)

    fetched = get_daily_prices(conn, "NFLX", start="2026-09-05", end="2026-09-05")
    assert [r["date"] for r in fetched] == ["2026-09-05"]


def test_different_symbols_do_not_collide():
    conn = _fresh_conn()
    upsert_daily_prices(conn, [
        {"symbol": "NFLX", "date": "2026-09-10", "open": 1.0, "high": 1.0,
         "low": 1.0, "close": 1.0, "volume": 1, "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"symbol": "QQQ", "date": "2026-09-10", "open": 2.0, "high": 2.0,
         "low": 2.0, "close": 2.0, "volume": 2, "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    assert len(get_daily_prices(conn, "NFLX")) == 1
    assert len(get_daily_prices(conn, "QQQ")) == 1
    assert get_daily_prices(conn, "NFLX")[0]["close"] == 1.0


def test_sec_filings_upsert_and_read_back():
    conn = _fresh_conn()
    rows = [
        {"cik": "0001065280", "accession_number": "0001065280-26-000042", "ticker": "NFLX",
         "form": "8-K", "filing_date": "2026-09-05", "primary_document": "nflx-8k.htm",
         "filing_url": "https://example.com/1", "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"cik": "0001065280", "accession_number": "0001065280-26-000041", "ticker": "NFLX",
         "form": "4", "filing_date": "2026-09-01", "primary_document": "nflx-form4.xml",
         "filing_url": "https://example.com/2", "fetched_at": "2026-09-11T00:00:00+00:00"},
    ]

    written = upsert_sec_filings(conn, rows)
    assert written == 2

    fetched = get_sec_filings(conn, cik="0001065280")
    assert len(fetched) == 2
    assert fetched[0]["filing_date"] == "2026-09-05"  # newest first


def test_sec_filings_upsert_overwrites_same_accession_number():
    conn = _fresh_conn()
    row = {"cik": "0001065280", "accession_number": "0001065280-26-000042", "ticker": "NFLX",
           "form": "8-K", "filing_date": "2026-09-05", "primary_document": "nflx-8k.htm",
           "filing_url": "https://example.com/1", "fetched_at": "2026-09-11T00:00:00+00:00"}
    upsert_sec_filings(conn, [row])
    upsert_sec_filings(conn, [dict(row, fetched_at="2026-09-12T00:00:00+00:00")])

    fetched = get_sec_filings(conn, cik="0001065280")
    assert len(fetched) == 1
    assert fetched[0]["fetched_at"] == "2026-09-12T00:00:00+00:00"


def test_sec_filings_filter_by_form():
    conn = _fresh_conn()
    upsert_sec_filings(conn, [
        {"cik": "0001065280", "accession_number": "A", "ticker": "NFLX", "form": "8-K",
         "filing_date": "2026-09-05", "primary_document": "a.htm", "filing_url": "u1",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"cik": "0001065280", "accession_number": "B", "ticker": "NFLX", "form": "4",
         "filing_date": "2026-09-01", "primary_document": "b.xml", "filing_url": "u2",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    eight_ks = get_sec_filings(conn, form="8-K")
    assert len(eight_ks) == 1
    assert eight_ks[0]["accession_number"] == "A"


def test_economic_observations_upsert_and_read_back():
    conn = _fresh_conn()
    rows = [
        {"series_id": "CPIAUCSL", "date": "2026-07-01", "value": 312.332,
         "realtime_start": "2026-08-13", "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"series_id": "CPIAUCSL", "date": "2026-08-01", "value": 313.049,
         "realtime_start": "2026-09-10", "fetched_at": "2026-09-11T00:00:00+00:00"},
    ]

    written = upsert_economic_observations(conn, rows)
    assert written == 2

    fetched = get_economic_observations(conn, "CPIAUCSL")
    assert len(fetched) == 2
    assert fetched[0]["date"] == "2026-07-01"
    assert fetched[1]["value"] == 313.049


def test_economic_observations_upsert_overwrites_same_series_and_date():
    conn = _fresh_conn()
    row = {"series_id": "CPIAUCSL", "date": "2026-07-01", "value": 312.332,
           "realtime_start": "2026-08-13", "fetched_at": "2026-09-11T00:00:00+00:00"}
    upsert_economic_observations(conn, [row])

    revised = dict(row, value=312.5, fetched_at="2026-09-12T00:00:00+00:00")
    upsert_economic_observations(conn, [revised])

    fetched = get_economic_observations(conn, "CPIAUCSL")
    assert len(fetched) == 1
    assert fetched[0]["value"] == 312.5


def test_news_articles_upsert_and_read_back():
    conn = _fresh_conn()
    rows = [
        {"symbol": "NFLX", "article_id": "7001", "headline": "Netflix news A",
         "source": "Reuters", "url": "https://example.com/a",
         "published_at": "2026-09-01T10:00:00+00:00", "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"symbol": "NFLX", "article_id": "7002", "headline": "Netflix news B",
         "source": "Bloomberg", "url": "https://example.com/b",
         "published_at": "2026-09-02T10:00:00+00:00", "fetched_at": "2026-09-11T00:00:00+00:00"},
    ]

    written = upsert_news_articles(conn, rows)
    assert written == 2

    fetched = get_news_articles(conn, "NFLX")
    assert len(fetched) == 2
    assert fetched[0]["headline"] == "Netflix news A"


def test_news_articles_upsert_overwrites_same_symbol_and_article_id():
    conn = _fresh_conn()
    row = {"symbol": "NFLX", "article_id": "7001", "headline": "Original headline",
           "source": "Reuters", "url": "https://example.com/a",
           "published_at": "2026-09-01T10:00:00+00:00", "fetched_at": "2026-09-11T00:00:00+00:00"}
    upsert_news_articles(conn, [row])
    upsert_news_articles(conn, [dict(row, headline="Corrected headline")])

    fetched = get_news_articles(conn, "NFLX")
    assert len(fetched) == 1
    assert fetched[0]["headline"] == "Corrected headline"
