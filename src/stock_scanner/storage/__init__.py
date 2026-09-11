"""Roadmap Phase 3 — the event-response database.

For every normalized event: price immediately before the event, then
returns at 5m/15m/30m/1h/4h/1d/3d/5d, abnormal return vs. the relevant index
(never raw return alone — ARCHITECTURE.md rule 3), and maximum
favorable/adverse excursion. This is the permanent historical record
everything downstream (Phase 4 onward) is computed from.

Not started yet — empty on purpose.
"""
