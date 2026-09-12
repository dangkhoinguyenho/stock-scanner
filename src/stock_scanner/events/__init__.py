"""Roadmap Phase 2 — event normalization.

Converts raw Phase 1 rows (news headlines, SEC filings, economic
observations) into standardized event categories (Earnings, Guidance,
Analyst Revision, Pricing, Advertising, Product, M&A, Regulatory/Legal,
Insider Transaction, Macro, etc.), each with an optional *hypothesized*
direction and — on every row — a plain-language reason explaining why it
got that label. This layer's job stops at "what kind of thing happened,"
never "what will it do to the price" (that's Phase 4/5/6's job, done from
actual price data, not from the event's own text).

Status: classifier.py is built — rule-based (keyword matching), not an LLM.
The original spec envisioned an LLM doing this extraction; see
classifier.py's module docstring for why we're starting simpler first
(rule 6: start simple, justify added complexity with demonstrated need).
"""
