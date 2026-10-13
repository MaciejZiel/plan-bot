"""Runtime configuration read from environment variables (see ``.env.example``)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/plan-bot.db"


class ConfigError(ValueError):
    pass


def _int(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str | None = None
    discord_token: str | None = None
    #: Override to use a self-hosted Bot API server (or a test double).
    telegram_api_url: str = "https://api.telegram.org"
    #: Optional dev server: sync slash commands there only (instant) instead of globally.
    discord_guild_id: int | None = None
    database_url: str = DEFAULT_DATABASE_URL
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Warsaw"))
    #: How often each feed is downloaded again.
    refresh_minutes: int = 30
    #: Scheduler resolution (reminders are at most this late).
    tick_seconds: int = 30
    #: How far ahead the stored snapshot reaches.
    horizon_days: int = 150
    #: Only changes to classes in the next N days are announced.
    change_horizon_days: int = 28
    #: Weekly summary: 0 = Monday ... 6 = Sunday, hour in local time.
    summary_weekday: int = 6
    summary_hour: int = 18
    max_ics_bytes: int = 5_000_000
    http_timeout_seconds: int = 20
    #: Identical feed URLs requested within this many seconds share one download.
    fetch_cache_seconds: int = 120
    #: Allow feeds on private/loopback addresses (off by default to prevent SSRF).
    allow_private_urls: bool = False
    log_level: str = "INFO"
    #: "text" for humans, "json" (one object per line) for log shippers.
    log_format: str = "text"
    #: Per-chat rate limit: a burst of N commands, then this many per minute.
    rate_burst: int = 10
    rate_per_minute: int = 30
    #: Health endpoint (``GET <base path>/healthz``); port 0 disables it.
    health_host: str = "127.0.0.1"
    health_port: int = 0
    base_path: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        tz_name = env.get("PLAN_BOT_TIMEZONE", "Europe/Warsaw").strip() or "Europe/Warsaw"
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(f"unknown timezone {tz_name!r}") from exc
        weekday = _int(env, "PLAN_BOT_SUMMARY_WEEKDAY", 6)
        hour = _int(env, "PLAN_BOT_SUMMARY_HOUR", 18)
        if weekday > 6 or hour > 23:
            raise ConfigError("PLAN_BOT_SUMMARY_WEEKDAY must be 0-6 and PLAN_BOT_SUMMARY_HOUR 0-23")
        log_format = env.get("PLAN_BOT_LOG_FORMAT", "text").strip().lower() or "text"
        if log_format not in {"text", "json"}:
            raise ConfigError("PLAN_BOT_LOG_FORMAT must be 'text' or 'json'")
        base_path = "/" + env.get("PLAN_BOT_BASE_PATH", "").strip().strip("/")
        base_path = "" if base_path == "/" else base_path
        port = _int(env, "PLAN_BOT_HEALTH_PORT", 0)
        if port > 65535:
            raise ConfigError("PLAN_BOT_HEALTH_PORT must be 0-65535")
        return cls(
            telegram_token=env.get("TELEGRAM_BOT_TOKEN", "").strip() or None,
            telegram_api_url=env.get("TELEGRAM_API_URL", "").strip() or "https://api.telegram.org",
            discord_token=env.get("DISCORD_BOT_TOKEN", "").strip() or None,
            discord_guild_id=(
                _int(env, "DISCORD_DEV_GUILD_ID", 0) or _int(env, "DISCORD_GUILD_ID", 0) or None
            ),
            database_url=env.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
            timezone=tz,
            refresh_minutes=_int(env, "PLAN_BOT_REFRESH_MINUTES", 30, minimum=5),
            tick_seconds=_int(env, "PLAN_BOT_TICK_SECONDS", 30, minimum=1),
            horizon_days=_int(env, "PLAN_BOT_HORIZON_DAYS", 150, minimum=7),
            change_horizon_days=_int(env, "PLAN_BOT_CHANGE_HORIZON_DAYS", 28, minimum=1),
            summary_weekday=weekday,
            summary_hour=hour,
            max_ics_bytes=_int(env, "PLAN_BOT_MAX_ICS_BYTES", 5_000_000, minimum=1024),
            http_timeout_seconds=_int(env, "PLAN_BOT_HTTP_TIMEOUT", 20, minimum=1),
            fetch_cache_seconds=_int(env, "PLAN_BOT_FETCH_CACHE_SECONDS", 120),
            allow_private_urls=_bool(env, "PLAN_BOT_ALLOW_PRIVATE_URLS", False),
            log_level=env.get("PLAN_BOT_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            log_format=log_format,
            rate_burst=_int(env, "PLAN_BOT_RATE_BURST", 10, minimum=1),
            rate_per_minute=_int(env, "PLAN_BOT_RATE_PER_MINUTE", 30, minimum=1),
            health_host=env.get("PLAN_BOT_HEALTH_HOST", "127.0.0.1").strip() or "127.0.0.1",
            health_port=_int(env, "PLAN_BOT_HEALTH_PORT", 0),
            base_path=base_path,
        )
