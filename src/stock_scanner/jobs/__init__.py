"""Scheduled/unattended entry points — scripts meant to be invoked by an OS
scheduler (Windows Task Scheduler, cron, etc.), not run interactively.

This is a separate concept from collectors/: a collector is "how to fetch
and store one kind of data"; a job is "what to actually run, on what
inputs, on a schedule, without a human watching it." A job typically calls
one or more collectors.

Status: daily_options_snapshot.py (Phase 1) is built.
"""
