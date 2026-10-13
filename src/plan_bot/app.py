"""Wiring: build the service graph from settings."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from plan_bot.commands import CommandRouter
from plan_bot.config import Settings
from plan_bot.db import create_engine, migrate, session_factory
from plan_bot.fetch import Fetcher
from plan_bot.ratelimit import RateLimiter
from plan_bot.repository import Repository
from plan_bot.scheduler import Scheduler
from plan_bot.service import BotService, Notifier, utc_now


@dataclass(slots=True)
class App:
    service: BotService
    router: CommandRouter
    scheduler: Scheduler
    engine: AsyncEngine


def shifted_clock(start_at: datetime | None) -> Callable[[], datetime]:
    """Real-time clock, optionally shifted so that "now" starts at ``start_at``."""
    if start_at is None:
        return utc_now
    offset = start_at - utc_now()
    return lambda: utc_now() + offset


@asynccontextmanager
async def build_app(
    settings: Settings,
    notifier: Notifier | None = None,
    *,
    clock: Callable[[], datetime] = utc_now,
    rate_limit: bool = True,
) -> AsyncIterator[App]:
    await migrate(settings.database_url)
    engine = create_engine(settings.database_url)
    fetcher = Fetcher(
        max_bytes=settings.max_ics_bytes,
        timeout_seconds=settings.http_timeout_seconds,
        allow_private=settings.allow_private_urls,
        cache_seconds=settings.fetch_cache_seconds,
    )
    try:
        service = BotService(
            Repository(session_factory(engine)), fetcher, settings, clock=clock, notifier=notifier
        )
        scheduler = Scheduler(service, tick_seconds=settings.tick_seconds, clock=clock)
        limiter = (
            RateLimiter(burst=settings.rate_burst, per_minute=settings.rate_per_minute)
            if rate_limit
            else None
        )
        yield App(service, CommandRouter(service, limiter=limiter), scheduler, engine)
    finally:
        await fetcher.close()
        await engine.dispose()
