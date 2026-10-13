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


def test_serving_and_logging_settings() -> None:
    settings = Settings.from_env(
        {
            "PLAN_BOT_HEALTH_PORT": "8091",
            "PLAN_BOT_BASE_PATH": "plan-bot/",
            "PLAN_BOT_LOG_FORMAT": "JSON",
            "PLAN_BOT_RATE_BURST": "3",
        }
    )
    assert (settings.health_port, settings.base_path) == (8091, "/plan-bot")
    assert settings.log_format == "json"
    assert settings.rate_burst == 3
    assert Settings.from_env({"PLAN_BOT_BASE_PATH": "/"}).base_path == ""
    assert Settings.from_env({}).health_port == 0  # disabled unless asked for
    assert Settings.from_env({}).telegram_api_url == "https://api.telegram.org"
    local = Settings.from_env({"TELEGRAM_API_URL": "http://127.0.0.1:8081"})
    assert local.telegram_api_url == "http://127.0.0.1:8081"


@pytest.mark.parametrize(
    "env",
    [
        {"PLAN_BOT_LOG_FORMAT": "xml"},
        {"PLAN_BOT_HEALTH_PORT": "70000"},
        {"PLAN_BOT_RATE_BURST": "0"},
    ],
)
def test_serving_and_logging_validation(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_discord_dev_guild_prefers_the_new_name() -> None:
    assert Settings.from_env({"DISCORD_GUILD_ID": "5"}).discord_guild_id == 5
    both = {"DISCORD_GUILD_ID": "5", "DISCORD_DEV_GUILD_ID": "7"}
    assert Settings.from_env(both).discord_guild_id == 7
    assert Settings.from_env({}).discord_guild_id is None
