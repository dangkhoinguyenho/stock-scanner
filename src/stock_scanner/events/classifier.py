"""Roadmap Phase 2 — rule-based event classifier.

Turns raw Phase 1 rows (news headlines, SEC filings, economic
observations) into standardized events: a category, an optional
*hypothesized* direction, and — critically — a `classification_reason`
string on every single row explaining exactly why it got that label. That
last field exists specifically to satisfy ARCHITECTURE.md rule 1 (never a
bare verdict) at this layer too: nothing here ever says "this is bullish"
without also saying which words made it think so.

Deliberate scope decisions, worth reading before extending this file:

1. Rule-based (keyword matching), not an LLM. The original project spec
   (project-spec.md section 10) describes an LLM doing this extraction
   step. We're starting with plain keyword rules instead, per rule 6
   (start simple, justify complexity with demonstrated improvement) and
   because an LLM classifier means a real per-article cost — not
   appropriate to add before we know keyword rules are actually
   insufficient. If/when we measure real misclassification or coverage
   problems, upgrading specific categories to an LLM call is a natural,
   justified next step — not a redesign.

2. "Direction" here is a HYPOTHESIS read off the event's own language
   (e.g. a headline saying "beats estimates" is hypothesized bullish),
   never a claim about actual historical price impact. That real
   measurement is Phase 4's job, computed from data. Several categories
   (pricing, M&A, product launches) get NO direction hypothesis at all,
   on purpose — the spec's own Netflix pricing example (section 21) shows
   why: a price increase can be bullish (more revenue) or bearish (churn),
   and guessing wrong here would be exactly the kind of unfounded "good
   news = bullish" heuristic rule 7 forbids. When in doubt, this module
   returns None for direction rather than a guess.

3. No "magnitude" or "novelty" fields yet, even though project-spec.md's
   example event record has them. A text-derived magnitude score with no
   calibration behind it would be a made-up number dressed as data —
   exactly what "numbers over adjectives" (this project's communication
   rule) is supposed to prevent. Real magnitude gets measured from actual
   price reactions in Phase 4. Novelty (how unusual is this event
   compared to past ones) needs a history of past events to compare
   against — meaningful once Phase 3/4 exist, not before.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Ordered on purpose: first matching category wins, so a headline that
# could plausibly fit two categories (e.g. "analyst raises price target
# after strong ad revenue") is resolved deterministically and reproducibly
# rather than ambiguously. Order roughly follows specificity: more
# specific/less ambiguous categories first.
NEWS_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Earnings", [
        "earnings", "quarterly results", "quarterly report", "eps",
        "beats estimates", "misses estimates", "beats expectations",
        "misses expectations", "posts loss", "posts profit",
    ]),
    ("Guidance", [
        "guidance", "outlook", "forecast raised", "forecast cut",
        "raises forecast", "lowers forecast", "raised its outlook",
        "cut its outlook",
    ]),
    ("Analyst Revision", [
        "upgrade", "upgrades", "downgrade", "downgrades", "price target",
        "initiates coverage", "reiterates rating",
    ]),
    ("Advertising", [
        "ad revenue", "advertising revenue", "ad-supported", "cpm",
        "advertiser demand", "ad monetization",
    ]),
    ("Pricing", [
        "price increase", "price hike", "raises prices", "raises its price",
        "subscription price", "price cut", "lowers prices",
    ]),
    ("M&A", [
        # "to buy" was removed 2026-09-12 after real data showed it firing
        # on generic "growth stocks to buy" investment listicles -- "buy
        # the stock" and "buy the company" are unrelated meanings of the
        # same two words, and every real-data match of it was the former.
        "acquires", "acquisition", "merger", "to acquire",
        "divest", "buyout", "takeover",
    ]),
    ("Regulatory/Legal", [
        # bare "fine" was removed 2026-09-12: it matched "Is The Business
        # Fine?" on real data (ordinary-English "fine," not a legal fine).
        # "fined" (past tense) is kept -- it reliably implies an actual
        # penalty was imposed, which bare "fine" does not.
        "lawsuit", "sues", "sued", "investigation", "regulatory",
        "fined", "settlement", "probe", "antitrust",
    ]),
    ("Product", [
        "launches", "unveils", "announces new", "new feature",
        "release date", "rolls out",
    ]),
]

# Per category, keyword -> hypothesized direction. Only categories with a
# genuinely unambiguous textual polarity get an entry here — see reason #2
# in this module's docstring for why pricing/M&A/product are absent.
NEWS_DIRECTION_KEYWORDS: dict[str, list[tuple[str, str]]] = {
    "Earnings": [
        ("beats estimates", "bullish"), ("beats expectations", "bullish"),
        ("tops estimates", "bullish"), ("record revenue", "bullish"),
        ("record profit", "bullish"), ("posts profit", "bullish"),
        ("misses estimates", "bearish"), ("misses expectations", "bearish"),
        ("falls short", "bearish"), ("posts loss", "bearish"),
    ],
    "Guidance": [
        ("raises guidance", "bullish"), ("raised guidance", "bullish"),
        ("raises forecast", "bullish"), ("raised its outlook", "bullish"),
        ("boosts outlook", "bullish"),
        ("cuts guidance", "bearish"), ("lowered guidance", "bearish"),
        ("lowers forecast", "bearish"), ("cut its outlook", "bearish"),
        ("slashes outlook", "bearish"),
    ],
    "Analyst Revision": [
        ("upgrade", "bullish"), ("upgrades", "bullish"),
        ("raises price target", "bullish"),
        ("downgrade", "bearish"), ("downgrades", "bearish"),
        ("cuts price target", "bearish"), ("lowers price target", "bearish"),
    ],
    "Advertising": [
        ("ad revenue growth", "bullish"), ("strong advertiser demand", "bullish"),
        ("ad revenue surges", "bullish"), ("ad revenue jumps", "bullish"),
        ("weak advertiser demand", "bearish"), ("ad revenue declines", "bearish"),
        ("ad revenue falls", "bearish"),
    ],
    "Regulatory/Legal": [
        # Litigation/regulatory action reads as negative-leaning almost by
        # definition of the words themselves (being sued, fined, or probed
        # is bad news about that fact alone) — this is reading the article's
        # own sentiment, not asserting this category always hurts the stock.
        # (bare "fine" removed 2026-09-12 along with the category keyword above)
        ("lawsuit", "bearish"), ("sues", "bearish"), ("sued", "bearish"),
        ("fined", "bearish"), ("investigation", "bearish"),
        ("probe", "bearish"), ("antitrust", "bearish"),
    ],
}


# Tickers we actively watch, mapped to the name(s) a headline genuinely
# about that company will actually contain. Added 2026-09-12 after real
# data showed Finnhub's company-news endpoint returning headlines under
# symbol='NFLX' that had nothing to do with Netflix at all -- e.g. "Take-Two
# Reiterates FY Bookings Outlook" and "How Far Can Amazon Stock Fall When
# The Business Is Fine?" both came back tagged NFLX. A category keyword
# matching text that never mentions the company by name or ticker is not
# trustworthy evidence of an event *for that company* -- same "don't guess"
# philosophy as the direction-hypothesis rules above, applied to company
# attribution instead of sentiment. Known limitation: a ticker with no
# entry here falls back to just the bare ticker string, which is a weaker
# check (works for "(AAPL)" style mentions, not "Apple").
TICKER_ALIASES: dict[str, tuple[str, ...]] = {
    "NFLX": ("Netflix", "NFLX"),
}


def _headline_mentions_company(headline_lower: str, symbol: str | None) -> bool:
    """True if `headline_lower` (already lowercased) actually references
    the company behind `symbol`, per TICKER_ALIASES. No symbol at all
    means there's nothing to check against, so this returns True (nothing
    to reject).
    """
    if not symbol:
        return True
    aliases = TICKER_ALIASES.get(symbol, (symbol,))
    return any(alias.lower() in headline_lower for alias in aliases)


def classify_news_article(article: dict) -> dict:
    """Classify one raw news_articles row (see storage/database.py's
    schema) into a standardized event dict. Always returns a row — even a
    total non-match becomes category="Unclassified" with a reason saying
    so, rather than silently disappearing, so classification coverage is
    itself measurable.
    """
    headline = (article.get("headline") or "").lower()
    symbol = article.get("symbol")

    category = "Unclassified"
    category_reason = "no category keyword matched in headline"
    matched_keyword = None
    for candidate_category, keywords in NEWS_CATEGORY_KEYWORDS:
        matched = next((kw for kw in keywords if kw in headline), None)
        if matched:
            category = candidate_category
            matched_keyword = matched
            category_reason = f"matched category keyword {matched!r}"
            break

    direction = None
    direction_reason = "no direction hypothesis for this category"
    for keyword, hypothesized_direction in NEWS_DIRECTION_KEYWORDS.get(category, []):
        if keyword in headline:
            direction = hypothesized_direction
            direction_reason = f"matched {hypothesized_direction} keyword {keyword!r}"
            break

    reason = f"{category_reason}; {direction_reason}"

    # Relevance check (added 2026-09-12): a category keyword firing on text
    # that never mentions the company itself is more likely to be another
    # company's (or the market's) news returned under this symbol than a
    # real event for it. See TICKER_ALIASES above for the real examples
    # that motivated this.
    if category != "Unclassified" and not _headline_mentions_company(headline, symbol):
        category = "Unclassified"
        direction = None
        reason = (
            f"matched category keyword {matched_keyword!r} but headline does not "
            f"mention {symbol} by name or ticker -- likely a different company's "
            f"news returned under this symbol by the news source, not treated as "
            f"an event for {symbol}"
        )

    return {
        "source_type": "news",
        "source_id": f"{article['symbol']}:{article['article_id']}",
        "symbol": article["symbol"],
        "event_timestamp": article["published_at"],
        "category": category,
        "hypothesized_direction": direction,
        "classification_reason": reason,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# SEC form type -> category. Coarse on purpose: SEC EDGAR's submissions API
# (what collectors/sec_edgar.py reads) only gives the form TYPE, not the
# item codes inside it — e.g. every 8-K lands in one bucket here regardless
# of whether it's an earnings release, a management change, or an M&A
# announcement, because that distinction lives inside the filing document
# itself, which we don't fetch/parse yet. Flagged as a real, known gap, not
# hidden: see this function's docstring.
SEC_FORM_CATEGORY_MAP: dict[str, str] = {
    "10-K": "Earnings/Annual Report",
    "10-K/A": "Earnings/Annual Report",
    "10-Q": "Earnings/Quarterly Report",
    "10-Q/A": "Earnings/Quarterly Report",
    "8-K": "Corporate Event (unspecified)",
    "8-K/A": "Corporate Event (unspecified)",
    "4": "Insider Transaction",
    "3": "Insider Transaction",
    "5": "Insider Transaction",
    "S-1": "Capital Raise",
    "S-3": "Capital Raise",
    "DEF 14A": "Proxy/Governance",
    "SC 13D": "Ownership Change (active, >5%)",
    "SC 13G": "Ownership Change (passive, >5%)",
}


def classify_sec_filing(filing: dict) -> dict:
    """Classify one raw sec_filings row into a standardized event dict.

    Direction is always None here — deliberately. A filing's form type
    alone carries no bullish/bearish information (an 8-K could announce
    almost anything; even "Insider Transaction" doesn't tell us buy vs.
    sell, since that detail is inside the Form 4 document itself, which
    this collector doesn't parse yet — a real gap worth closing later if
    insider buy/sell direction turns out to matter).
    """
    form = filing["form"]
    category = SEC_FORM_CATEGORY_MAP.get(form, "Other Filing")
    if form in SEC_FORM_CATEGORY_MAP:
        reason = f"SEC form {form!r} mapped to category {category!r}"
    else:
        reason = f"SEC form {form!r} not in the known mapping — defaulted to 'Other Filing'"
    if category in ("Corporate Event (unspecified)", "Insider Transaction"):
        reason += " (item code / transaction detail not available from the EDGAR submissions API)"

    return {
        "source_type": "sec_filing",
        "source_id": f"{filing['cik']}:{filing['accession_number']}",
        "symbol": filing.get("ticker"),
        "event_timestamp": filing["filing_date"],
        "category": category,
        "hypothesized_direction": None,
        "classification_reason": reason,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# Friendly names for economic_observations categories, reusing the same
# names collectors/economic_calendar.py's COMMON_SERIES already defines —
# imported lazily inside the function below to avoid a hard import-time
# dependency loop between events/ and collectors/.
def classify_economic_observation(observation: dict, previous_value: float | None = None) -> dict:
    """Classify one raw economic_observations row into a standardized
    event dict.

    Direction is always None here too, on purpose, per rule 7: whether
    rising CPI (say) is "good" or "bad" for a given stock depends entirely
    on the ticker and the broader regime — there is no generic macro
    direction to hypothesize. `previous_value`, if given (the same
    series' immediately preceding observation), is used only to describe
    the magnitude of change in plain terms — not to imply a direction for
    any particular stock.
    """
    from stock_scanner.collectors.economic_calendar import COMMON_SERIES

    series_id = observation["series_id"]
    friendly_name = next((name for name, code in COMMON_SERIES.items() if code == series_id), series_id)
    category = f"Macro: {friendly_name}"

    value = observation["value"]
    if previous_value is None:
        reason = f"{series_id} = {value} — first collected observation for this series, no prior value to compare"
    elif previous_value == 0:
        reason = f"{series_id} changed from {previous_value} to {value} (cannot compute a percent change from zero)"
    else:
        pct_change = (value - previous_value) / abs(previous_value) * 100
        reason = f"{series_id} changed from {previous_value} to {value} ({pct_change:+.2f}%)"

    return {
        "source_type": "economic_observation",
        "source_id": f"{series_id}:{observation['date']}",
        "symbol": None,
        "event_timestamp": observation["date"],
        "category": category,
        "hypothesized_direction": None,
        "classification_reason": reason,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def classify_and_store_all(conn=None) -> dict[str, int]:
    """Classify every raw news article, SEC filing, and economic
    observation currently stored, and upsert the results into `events`.

    Safe to re-run any time: classification is a pure function of each raw
    row, and events are upserted on a natural key back to that row (see
    storage/database.py's init_schema docstring), so re-running this after
    collecting new data just adds the new rows' events and leaves existing
    ones unchanged (unless the classification rules themselves changed,
    in which case re-running intentionally re-labels everything with the
    current rules — also usually what you want).

    Returns a dict of how many events were written per source type, so a
    caller can see classification coverage at a glance.
    """
    from stock_scanner.storage.database import (
        get_all_economic_observations,
        get_all_news_articles,
        get_all_sec_filings,
        get_connection,
        upsert_events,
    )

    owns_conn = conn is None
    if conn is None:
        conn = get_connection()

    try:
        news_events = [classify_news_article(dict(row)) for row in get_all_news_articles(conn)]
        filing_events = [classify_sec_filing(dict(row)) for row in get_all_sec_filings(conn)]

        econ_events = []
        previous_value_by_series: dict[str, float] = {}
        for row in get_all_economic_observations(conn):
            row = dict(row)
            previous_value = previous_value_by_series.get(row["series_id"])
            econ_events.append(classify_economic_observation(row, previous_value=previous_value))
            previous_value_by_series[row["series_id"]] = row["value"]

        written = {
            "news": upsert_events(conn, news_events) if news_events else 0,
            "sec_filing": upsert_events(conn, filing_events) if filing_events else 0,
            "economic_observation": upsert_events(conn, econ_events) if econ_events else 0,
        }
        return written
    finally:
        if owns_conn:
            conn.close()
