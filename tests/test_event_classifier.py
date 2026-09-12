"""Tests for the Phase 2 rule-based event classifier.

Each classify_* function is a pure function (no DB, no network) — same
offline-testability philosophy as every collector in this project. The
classification_reason field is checked explicitly in several tests, not
just the category/direction, because that field is the whole mechanism
by which this layer avoids being a bare, unexplained verdict (rule 1).
"""

import sqlite3

from stock_scanner.events.classifier import (
    classify_and_store_all,
    classify_economic_observation,
    classify_news_article,
    classify_sec_filing,
)
from stock_scanner.storage.database import (
    get_events,
    init_schema,
    upsert_economic_observations,
    upsert_news_articles,
    upsert_sec_filings,
)


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _article(headline: str, article_id: str = "1") -> dict:
    return {
        "symbol": "NFLX",
        "article_id": article_id,
        "headline": headline,
        "source": "Reuters",
        "url": "https://example.com",
        "published_at": "2026-09-12T10:00:00+00:00",
        "fetched_at": "2026-09-12T10:05:00+00:00",
    }


def test_classify_news_earnings_bullish():
    event = classify_news_article(_article("Netflix beats estimates in Q2 earnings"))

    assert event["category"] == "Earnings"
    assert event["hypothesized_direction"] == "bullish"
    assert "beats estimates" in event["classification_reason"]
    assert event["source_type"] == "news"
    assert event["source_id"] == "NFLX:1"
    assert event["symbol"] == "NFLX"


def test_classify_news_earnings_bearish():
    event = classify_news_article(_article("Netflix misses estimates, posts loss for the quarter"))

    assert event["category"] == "Earnings"
    assert event["hypothesized_direction"] == "bearish"


def test_classify_news_analyst_revision_bullish():
    event = classify_news_article(_article("Analyst upgrades NFLX, raises price target to $800"))

    assert event["category"] == "Analyst Revision"
    assert event["hypothesized_direction"] == "bullish"


def test_classify_news_regulatory_legal_bearish():
    event = classify_news_article(_article("Netflix sued over data privacy violations"))

    assert event["category"] == "Regulatory/Legal"
    assert event["hypothesized_direction"] == "bearish"


def test_classify_news_pricing_has_no_direction_hypothesis():
    """This is the deliberate case from this module's docstring: a price
    increase headline gets a category but NOT a direction guess, because
    whether it's bullish or bearish depends on subscriber retention, not
    on the headline's own words (project-spec.md section 21's own example).
    """
    event = classify_news_article(_article("Netflix raises prices in several markets"))

    assert event["category"] == "Pricing"
    assert event["hypothesized_direction"] is None
    assert "no direction hypothesis" in event["classification_reason"]


def test_classify_news_ma_has_no_direction_hypothesis():
    event = classify_news_article(_article("Netflix acquires small gaming studio for $50 million"))

    assert event["category"] == "M&A"
    assert event["hypothesized_direction"] is None


def test_classify_news_unclassified_when_no_keyword_matches():
    event = classify_news_article(_article("Netflix stock closes flat in quiet trading session"))

    assert event["category"] == "Unclassified"
    assert event["hypothesized_direction"] is None
    assert "no category keyword matched" in event["classification_reason"]


def test_classify_news_generic_to_buy_listicle_is_unclassified():
    """Real-data finding, 2026-09-12: "to buy" used to match M&A, but every
    real match on Kenny's data was a generic "growth stocks to buy"
    investment listicle, not an acquisition. Removed from the keyword list
    entirely rather than tightened, since "buy the stock" and "buy the
    company" share no distinguishing words to filter on.
    """
    event = classify_news_article(
        _article("3 of the Best Growth Stocks to Buy for Less Than $100 Right Now")
    )

    assert event["category"] == "Unclassified"


def test_classify_news_bare_fine_is_unclassified():
    """Real-data finding, 2026-09-12: bare "fine" matched "Is The Business
    Fine?" (ordinary English, not a legal fine). "fined" (past tense) is
    kept since it reliably implies an actual penalty.
    """
    event = classify_news_article(
        _article("How Far Can Amazon Stock Fall When The Business Is Fine?")
    )

    assert event["category"] == "Unclassified"


def test_classify_news_relevance_check_rejects_other_company_headline():
    """Real-data finding, 2026-09-12: Finnhub's company-news endpoint
    returned this exact headline tagged symbol='NFLX', even though it's
    about Take-Two, not Netflix. A keyword match on text that never
    mentions the company shouldn't be attributed to that company.
    """
    event = classify_news_article(
        _article("Take-Two Reiterates FY Bookings Outlook Despite Pre-Orders")
    )

    assert event["category"] == "Unclassified"
    assert "does not mention NFLX" in event["classification_reason"]


def test_classify_news_relevance_check_allows_real_company_mention():
    event = classify_news_article(_article("Netflix (NFLX) Shares Pressured by Weak Q2 Outlook"))

    assert event["category"] == "Guidance"


def test_classify_news_relevance_check_matches_company_name_not_just_ticker():
    event = classify_news_article(_article("Netflix's Acquisition Wishlist: Which Target Has the Best Odds?"))

    assert event["category"] == "M&A"


def test_classify_sec_filing_quarterly_report():
    filing = {"cik": "0001065280", "accession_number": "A1", "ticker": "NFLX",
              "form": "10-Q", "filing_date": "2026-09-05", "primary_document": "x",
              "filing_url": "u", "fetched_at": "2026-09-11T00:00:00+00:00"}

    event = classify_sec_filing(filing)

    assert event["category"] == "Earnings/Quarterly Report"
    assert event["hypothesized_direction"] is None
    assert event["source_type"] == "sec_filing"
    assert event["source_id"] == "0001065280:A1"


def test_classify_sec_filing_insider_transaction_flags_missing_direction_detail():
    filing = {"cik": "0001065280", "accession_number": "A2", "ticker": "NFLX",
              "form": "4", "filing_date": "2026-09-05", "primary_document": "x",
              "filing_url": "u", "fetched_at": "2026-09-11T00:00:00+00:00"}

    event = classify_sec_filing(filing)

    assert event["category"] == "Insider Transaction"
    assert "transaction detail not available" in event["classification_reason"]


def test_classify_sec_filing_unknown_form_defaults_to_other():
    filing = {"cik": "0001065280", "accession_number": "A3", "ticker": "NFLX",
              "form": "NT 10-K", "filing_date": "2026-09-05", "primary_document": "x",
              "filing_url": "u", "fetched_at": "2026-09-11T00:00:00+00:00"}

    event = classify_sec_filing(filing)

    assert event["category"] == "Other Filing"
    assert "not in the known mapping" in event["classification_reason"]


def test_classify_economic_observation_first_observation_has_no_comparison():
    obs = {"series_id": "CPIAUCSL", "date": "2026-07-01", "value": 312.332,
           "realtime_start": "2026-08-13", "fetched_at": "2026-09-11T00:00:00+00:00"}

    event = classify_economic_observation(obs, previous_value=None)

    assert event["category"] == "Macro: CPI"  # friendly name from COMMON_SERIES
    assert event["hypothesized_direction"] is None
    assert "no prior value to compare" in event["classification_reason"]


def test_classify_economic_observation_computes_percent_change():
    obs = {"series_id": "CPIAUCSL", "date": "2026-08-01", "value": 313.049,
           "realtime_start": "2026-09-10", "fetched_at": "2026-09-11T00:00:00+00:00"}

    event = classify_economic_observation(obs, previous_value=312.332)

    expected_pct = (313.049 - 312.332) / 312.332 * 100
    assert f"{expected_pct:+.2f}%" in event["classification_reason"]
    assert event["hypothesized_direction"] is None  # macro direction is never generic (rule 7)


def test_classify_economic_observation_unknown_series_falls_back_to_series_id():
    obs = {"series_id": "SOMENEWSERIES", "date": "2026-08-01", "value": 1.0,
           "realtime_start": "2026-08-01", "fetched_at": "2026-09-11T00:00:00+00:00"}

    event = classify_economic_observation(obs)

    assert event["category"] == "Macro: SOMENEWSERIES"


def test_classify_and_store_all_end_to_end_and_is_idempotent():
    conn = _fresh_conn()
    upsert_news_articles(conn, [_article("Netflix beats estimates in Q2 earnings")])
    upsert_sec_filings(conn, [
        {"cik": "0001065280", "accession_number": "A1", "ticker": "NFLX", "form": "10-Q",
         "filing_date": "2026-09-05", "primary_document": "x", "filing_url": "u",
         "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])
    upsert_economic_observations(conn, [
        {"series_id": "CPIAUCSL", "date": "2026-07-01", "value": 312.332,
         "realtime_start": "2026-08-13", "fetched_at": "2026-09-11T00:00:00+00:00"},
        {"series_id": "CPIAUCSL", "date": "2026-08-01", "value": 313.049,
         "realtime_start": "2026-09-10", "fetched_at": "2026-09-11T00:00:00+00:00"},
    ])

    written = classify_and_store_all(conn=conn)
    assert written == {"news": 1, "sec_filing": 1, "economic_observation": 2}

    events = get_events(conn)
    assert len(events) == 4
    categories = {e["category"] for e in events}
    assert "Earnings" in categories
    assert "Earnings/Quarterly Report" in categories
    assert "Macro: CPI" in categories

    # Re-running must not duplicate rows — upserted on the same natural keys.
    classify_and_store_all(conn=conn)
    assert len(get_events(conn)) == 4
