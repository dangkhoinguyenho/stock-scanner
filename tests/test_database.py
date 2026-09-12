"""Tests for the Phase 1 raw price storage layer.

Uses an in-memory SQLite database (":memory:") so these run instantly,
leave nothing on disk, and need no network — the storage logic itself is
what's under test, not any real data source.
"""

import sqlite3

from stock_scanner.storage.database import (
    get_all_economic_observations,
    get_all_news_articles,
    get_all_sec_filings,
    get_daily_prices,
    get_economic_observations,
    get_events,
    get_news_articles,
    get_options_chain,
    get_sec_filings,
    init_schema,
    upsert_daily_prices,
    upsert_economic_observations,
    upsert_events,
    upsert_news_articles,
    upsert_options_chain,
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


def test_options_chain_upsert_and_read_back():
    conn = _fresh_conn()
    rows = [
        {"symbol": "NFLX", "as_of_date": "2026-09-12", "expiration": "2026-09-18",
         "contract_symbol": "NFLX260918C00700000", "option_type": "call", "strike": 700.0,
         "last_price": 42.5, "bid": 42.0, "ask": 43.0, "volume": 120, "open_interest": 500,
         "implied_volatility": 0.35, "in_the_money": 1, "fetched_at": "2026-09-12T14:00:00+00:00"},
        {"symbol": "NFLX", "as_of_date": "2026-09-12", "expiration": "2026-09-18",
         "contract_symbol": "NFLX260918P00700000", "option_type": "put", "strike": 700.0,
         "last_price": 15.0, "bid": 14.7, "ask": 15.3, "volume": 40, "open_interest": 200,
         "implied_volatility": 0.33, "in_the_money": 0, "fetched_at": "2026-09-12T14:00:00+00:00"},
    ]

    written = upsert_options_chain(conn, rows)
    assert written == 2

    fetched = get_options_chain(conn, "NFLX")
    assert len(fetched) == 2
    assert fetched[0]["strike"] == 700.0


def test_options_chain_same_contract_different_day_accumulates_not_overwrites():
    """This is the whole point of keying on (contract_symbol, as_of_date)
    instead of just contract_symbol: the same option contract snapshotted
    on two different days must produce two rows, building real history.
    """
    conn = _fresh_conn()
    day1 = {"symbol": "NFLX", "as_of_date": "2026-09-12", "expiration": "2026-09-18",
            "contract_symbol": "NFLX260918C00700000", "option_type": "call", "strike": 700.0,
            "last_price": 42.5, "bid": 42.0, "ask": 43.0, "volume": 120, "open_interest": 500,
            "implied_volatility": 0.35, "in_the_money": 1, "fetched_at": "2026-09-12T14:00:00+00:00"}
    day2 = dict(day1, as_of_date="2026-09-13", last_price=45.0, implied_volatility=0.40,
                fetched_at="2026-09-13T14:00:00+00:00")

    upsert_options_chain(conn, [day1])
    upsert_options_chain(conn, [day2])

    fetched = get_options_chain(conn, "NFLX")
    assert len(fetched) == 2
    assert [r["as_of_date"] for r in fetched] == ["2026-09-12", "2026-09-13"]
    assert fetched[1]["last_price"] == 45.0


def test_options_chain_same_day_rerun_overwrites_that_day_only():
    conn = _fresh_conn()
    row = {"symbol": "NFLX", "as_of_date": "2026-09-12", "expiration": "2026-09-18",
           "contract_symbol": "NFLX260918C00700000", "option_type": "call", "strike": 700.0,
           "last_price": 42.5, "bid": 42.0, "ask": 43.0, "volume": 120, "open_interest": 500,
           "implied_volatility": 0.35, "in_the_money": 1, "fetched_at": "2026-09-12T14:00:00+00:00"}
    upsert_options_chain(conn, [row])
    upsert_options_chain(conn, [dict(row, last_price=43.1, fetched_at="2026-09-12T15:30:00+00:00")])

    fetched = get_options_chain(conn, "NFLX", as_of_date="2026-09-12")
    assert len(fetched) == 1
    assert fetched[0]["last_price"] == 43.1


def test_options_chain_filters_by_expiration_and_option_type():
    conn = _fresh_conn()
    upsert_options_chain(conn, [
        {"symbol": "NFLX", "as_of_date": "2026-09-12", "expiration": "2026-09-18",
         "contract_symbol": "A", "option_type": "call", "strike": 700.0, "last_price": 1.0,
         "bid": 1.0, "ask": 1.0, "volume": 1, "open_interest": 1, "implied_volatility": 0.3,
         "in_the_money": 1, "fetched_at": "2026-09-12T14:00:00+00:00"},
        {"symbol": "NFLX", "as_of_date": "2026-09-12", "expiration": "2026-10-16",
         "contract_symbol": "B", "option_type": "put", "strike": 700.0, "last_price": 1.0,
         "bid": 1.0, "ask": 1.0, "volume": 1, "open_interest": 1, "implied_volatility": 0.3,
         "in_the_money": 0, "fetched_at": "2026-09-12T14:00:00+00:00"},
    ])

    sept_only = get_options_chain(conn, "NFLX", expiration="2026-09-18")
    assert len(sept_only) == 1
    assert sept_only[0]["contract_symbol"] == "A"

    puts_only = get_options_chain(conn, "NFLX", option_type="put")
    assert len(puts_only) == 1
    assert puts_only[0]["contract_symbol"] == "B"


def test_get_all_news_articles_spans_every_symbol():
    conn = _fresh_conn()
    upsert_news_articles(conn, [
        {"symbol": "NFLX", "article_id": "1", "headline": "NFLX headline", "source": "R",
         "url": "u1", "published_at": "2026-09-01T00:00:00+00:00", "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"symbol": "AAPL", "article_id": "2", "headline": "AAPL headline", "source": "R",
         "url": "u2", "published_at": "2026-09-02T00:00:00+00:00", "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    all_articles = get_all_news_articles(conn)
    assert len(all_articles) == 2
    assert {a["symbol"] for a in all_articles} == {"NFLX", "AAPL"}


def test_get_all_sec_filings_spans_every_ticker():
    conn = _fresh_conn()
    upsert_sec_filings(conn, [
        {"cik": "1", "accession_number": "A", "ticker": "NFLX", "form": "10-Q",
         "filing_date": "2026-09-01", "primary_document": "x", "filing_url": "u",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"cik": "2", "accession_number": "B", "ticker": "AAPL", "form": "8-K",
         "filing_date": "2026-09-02", "primary_document": "x", "filing_url": "u",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    all_filings = get_all_sec_filings(conn)
    assert len(all_filings) == 2
    assert {f["ticker"] for f in all_filings} == {"NFLX", "AAPL"}


def test_get_all_economic_observations_orders_by_series_then_date():
    conn = _fresh_conn()
    upsert_economic_observations(conn, [
        {"series_id": "UNRATE", "date": "2026-08-01", "value": 4.1,
         "realtime_start": "2026-08-01", "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"series_id": "CPIAUCSL", "date": "2026-07-01", "value": 312.332,
         "realtime_start": "2026-08-13", "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"series_id": "CPIAUCSL", "date": "2026-08-01", "value": 313.049,
         "realtime_start": "2026-09-10", "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    all_obs = get_all_economic_observations(conn)
    assert [(o["series_id"], o["date"]) for o in all_obs] == [
        ("CPIAUCSL", "2026-07-01"),
        ("CPIAUCSL", "2026-08-01"),
        ("UNRATE", "2026-08-01"),
    ]


def test_events_upsert_and_read_back():
    conn = _fresh_conn()
    rows = [
        {"source_type": "news", "source_id": "NFLX:1", "symbol": "NFLX",
         "event_timestamp": "2026-09-01T10:00:00+00:00", "category": "Earnings",
         "hypothesized_direction": "bullish", "classification_reason": "matched 'beats estimates'",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"source_type": "economic_observation", "source_id": "CPIAUCSL:2026-07-01", "symbol": None,
         "event_timestamp": "2026-07-01", "category": "Macro: CPI",
         "hypothesized_direction": None, "classification_reason": "first observation",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
    ]

    written = upsert_events(conn, rows)
    assert written == 2

    events = get_events(conn)
    assert len(events) == 2
    assert events[0]["event_timestamp"] == "2026-07-01"  # ordered by event_timestamp ascending


def test_events_upsert_overwrites_same_source_type_and_id():
    conn = _fresh_conn()
    row = {"source_type": "news", "source_id": "NFLX:1", "symbol": "NFLX",
           "event_timestamp": "2026-09-01T10:00:00+00:00", "category": "Unclassified",
           "hypothesized_direction": None, "classification_reason": "no match",
           "fetched_at": "2026-09-11T00:00:00+00:00"}
    upsert_events(conn, [row])
    upsert_events(conn, [dict(row, category="Earnings", hypothesized_direction="bullish")])

    events = get_events(conn)
    assert len(events) == 1
    assert events[0]["category"] == "Earnings"


def test_events_filters_by_symbol_category_and_source_type():
    conn = _fresh_conn()
    upsert_events(conn, [
        {"source_type": "news", "source_id": "NFLX:1", "symbol": "NFLX",
         "event_timestamp": "2026-09-01T00:00:00+00:00", "category": "Earnings",
         "hypothesized_direction": "bullish", "classification_reason": "r",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"source_type": "sec_filing", "source_id": "1:A", "symbol": "AAPL",
         "event_timestamp": "2026-09-02T00:00:00+00:00", "category": "Insider Transaction",
         "hypothesized_direction": None, "classification_reason": "r",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    nflx_only = get_events(conn, symbol="NFLX")
    assert len(nflx_only) == 1
    assert nflx_only[0]["category"] == "Earnings"

    filings_only = get_events(conn, source_type="sec_filing")
    assert len(filings_only) == 1
    assert filings_only[0]["symbol"] == "AAPL"

    earnings_only = get_events(conn, category="Earnings")
    assert len(earnings_only) == 1
