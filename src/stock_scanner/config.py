"""Central settings/config loading.

Why this file exists: every collector, analyzer, and script in this project
needs API keys and a handful of settings. Without a single place for that,
every module ends up calling `os.environ.get(...)` directly, which makes it
easy to typo an env var name, hard to see what config the whole app actually
needs at a glance, and hard to test (you can't easily swap in fake settings
for a unit test if a function reads straight from the real environment).

The pattern instead: one `Settings` object, built once from the environment
(with `.env` loaded first), passed into whatever needs it. Tests construct
their own `Settings(...)` with fake values instead of touching real env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Loads variables from a `.env` file (if present) into the process environment.
# Safe to call more than once; does nothing if `.env` doesn't exist (e.g. in CI).
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of this app's configuration.

    `frozen=True` means a Settings instance can't be mutated after creation —
    that's deliberate: config should be read once at startup, not changed
    mid-run, which would make bugs dependent on *when* code happens to read a
    setting.
    """

    sec_edgar_user_agent: str
    alpha_vantage_api_key: str | None
    fred_api_key: str | None
    finnhub_api_key: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        """Build Settings from the current process environment."""
        return cls(
            sec_edgar_user_agent=os.environ.get("SEC_EDGAR_USER_AGENT", ""),
            alpha_vantage_api_key=os.environ.get("ALPHA_VANTAGE_API_KEY") or None,
            fred_api_key=os.environ.get("FRED_API_KEY") or None,
            finnhub_api_key=os.environ.get("FINNHUB_API_KEY") or None,
        )


def get_settings() -> Settings:
    """Convenience accessor for scripts/CLI entry points."""
    return Settings.from_env()
