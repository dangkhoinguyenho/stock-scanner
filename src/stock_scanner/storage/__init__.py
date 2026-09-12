"""Roadmap Phase 3 — the event-response database (not started yet).

For every normalized event: price immediately before the event, then
returns at 5m/15m/30m/1h/4h/1d/3d/5d, abnormal return vs. the relevant index
(never raw return alone — ARCHITECTURE.md rule 3), and maximum
favorable/adverse excursion. This is the permanent historical record
everything downstream (Phase 4 onward) is computed from.

This package also currently holds database.py — the Phase 1 raw data
tables collectors write into, AND the Phase 2 `events` table
(events/classifier.py's output). All of this project's SQLite schema
lives in one file by convention, regardless of which phase a table
belongs to — database.py's own module docstring and each table's comment
in init_schema say which phase owns which table.
"""
