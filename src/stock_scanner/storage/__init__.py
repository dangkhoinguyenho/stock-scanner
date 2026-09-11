"""Roadmap Phase 3 — the event-response database (not started yet).

For every normalized event: price immediately before the event, then
returns at 5m/15m/30m/1h/4h/1d/3d/5d, abnormal return vs. the relevant index
(never raw return alone — ARCHITECTURE.md rule 3), and maximum
favorable/adverse excursion. This is the permanent historical record
everything downstream (Phase 4 onward) is computed from.

This package also currently holds database.py — the Phase 1 raw price
store collectors write into. That's a different, simpler table (just
"what happened to the price") that the eventual event-response tables here
will read as an input, not the event-response schema itself.
"""
