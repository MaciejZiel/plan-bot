from __future__ import annotations

import pytest

from plan_bot.config import DEFAULT_DATABASE_URL, ConfigError, Settings


def test_defaults() -> None:
    settings = Settings.from_env({})
    assert settings.telegram_token is None
    assert settings.discord_token is None
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert str(settings.timezone) == "Europe/Warsaw"
    assert settings.refresh_minutes == 30
    assert not settings.allow_private_urls


def test_overrides() -> None:
    settings = Settings.from_env(
        {
            "TELEGRAM_BOT_TOKEN": " 123:abc ",
            "DISCORD_BOT_TOKEN": "",
            "DATABASE_URL": "sqlite+aiosqlite:///x.db",
            "PLAN_BOT_TIMEZONE": "Europe/London",
            "PLAN_BOT_REFRESH_MINUTES": "15",
            "PLAN_BOT_ALLOW_PRIVATE_URLS": "yes",
            "PLAN_BOT_SUMMARY_WEEKDAY": "4",
            "PLAN_BOT_LOG_LEVEL": "debug",
        }
    )
    assert settings.telegram_token == "123:abc"
    assert settings.discord_token is None
    assert settings.database_url == "sqlite+aiosqlite:///x.db"
    assert str(settings.timezone) == "Europe/London"
    assert settings.refresh_minutes == 15
    assert settings.allow_private_urls
    assert settings.summary_weekday == 4
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    "env",
    [
        {"PLAN_BOT_TIMEZONE": "Mars/Olympus"},
        {"PLAN_BOT_REFRESH_MINUTES": "often"},
        {"PLAN_BOT_REFRESH_MINUTES": "1"},
        {"PLAN_BOT_ALLOW_PRIVATE_URLS": "perhaps"},
        {"PLAN_BOT_SUMMARY_WEEKDAY": "7"},
        {"PLAN_BOT_SUMMARY_HOUR": "24"},
    ],
)
def test_invalid(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_reads_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLAN_BOT_TICK_SECONDS", "5")
    assert Settings.from_env().tick_seconds == 5
