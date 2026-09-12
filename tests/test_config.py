"""Smoke test for config.py — proves the test harness itself works before
any real logic exists, and shows the pattern every future test should
follow: build a Settings object directly with fake values rather than
mutating real environment variables.
"""

from stock_scanner.config import Settings


def test_settings_holds_the_values_it_was_given():
    settings = Settings(
        sec_edgar_user_agent="StockScanner test@example.com",
        alpha_vantage_api_key="fake-key-123",
        fred_api_key="fake-fred-key",
        finnhub_api_key="fake-finnhub-key",
    )

    assert settings.sec_edgar_user_agent == "StockScanner test@example.com"
    assert settings.alpha_vantage_api_key == "fake-key-123"
    assert settings.fred_api_key == "fake-fred-key"
    assert settings.finnhub_api_key == "fake-finnhub-key"


def test_from_env_reads_process_environment(monkeypatch):
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "StockScanner env@example.com")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "env-key-456")
    monkeypatch.setenv("FRED_API_KEY", "env-fred-key")
    monkeypatch.setenv("FINNHUB_API_KEY", "env-finnhub-key")

    settings = Settings.from_env()

    assert settings.sec_edgar_user_agent == "StockScanner env@example.com"
    assert settings.alpha_vantage_api_key == "env-key-456"
    assert settings.fred_api_key == "env-fred-key"
    assert settings.finnhub_api_key == "env-finnhub-key"


def test_from_env_defaults_missing_keys_to_none(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    settings = Settings.from_env()

    assert settings.alpha_vantage_api_key is None
    assert settings.fred_api_key is None
    assert settings.finnhub_api_key is None
