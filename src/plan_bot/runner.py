"""Run the configured chat adapters and the scheduler together."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable
from typing import Protocol

import aiohttp

from plan_bot.app import build_app
from plan_bot.config import Settings
from plan_bot.repository import ChatRef
from plan_bot.views import View

log = logging.getLogger(__name__)

SHUTDOWN_GRACE_SECONDS = 10


class Adapter(Protocol):
    platform: str

    async def send(self, chat: ChatRef, text: str) -> None: ...

    async def run(self, stop: asyncio.Event) -> None: ...


class MultiNotifier:
    """Routes outgoing notifications to the adapter of the chat's platform."""

    def __init__(self) -> None:
        self.adapters: dict[str, Adapter] = {}

    def register(self, adapter: Adapter) -> None:
        self.adapters[adapter.platform] = adapter

    async def send(self, chat: ChatRef, text: str, view: View | None = None) -> None:
        adapter = self.adapters.get(chat.platform)
        if adapter is None:
            log.warning("no adapter running for %s, message dropped", chat.platform)
            return
        if view is not None and getattr(adapter, "supports_views", False):
            await adapter.send(chat, text, view)  # type: ignore[call-arg]
        else:
            await adapter.send(chat, text)


async def run_bots(
    settings: Settings,
    *,
    stop: asyncio.Event | None = None,
    install_signal_handlers: bool = True,
    session_factory: Callable[[], aiohttp.ClientSession] = aiohttp.ClientSession,
) -> None:
    if not settings.telegram_token and not settings.discord_token:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN and/or DISCORD_BOT_TOKEN (see .env.example), "
            "or try `plan-bot console`."
        )
    stop = stop or asyncio.Event()
    if install_signal_handlers:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):  # Windows
                loop.add_signal_handler(sig, stop.set)

    notifier = MultiNotifier()
    async with build_app(settings, notifier) as app, session_factory() as http:
        runners: list[Callable[[], Awaitable[None]]] = []
        if settings.telegram_token:
            from plan_bot.adapters.telegram import TelegramAdapter, TelegramApi

            telegram = TelegramAdapter(
                TelegramApi(settings.telegram_token, http, base_url=settings.telegram_api_url),
                app.router,
            )
            notifier.register(telegram)
            runners.append(lambda: telegram.run(stop))
        if settings.discord_token:
            try:
                from plan_bot.adapters.discord import DiscordAdapter
            except ImportError as exc:
                raise RuntimeError(
                    "DISCORD_BOT_TOKEN is set but discord.py is not installed "
                    "(install it with `pip install 'plan-bot[discord]'`)."
                ) from exc

            discord_bot = DiscordAdapter(
                app.router, settings.discord_token, guild_id=settings.discord_guild_id
            )
            notifier.register(discord_bot)
            runners.append(lambda: discord_bot.run(stop))
        if settings.health_port:
            from plan_bot.health import HealthServer

            health = HealthServer(
                app.engine,
                host=settings.health_host,
                port=settings.health_port,
                base_path=settings.base_path,
                tick_seconds=settings.tick_seconds,
                scheduler_last_tick=lambda: app.scheduler.last_tick_at,
                adapters=lambda: sorted(notifier.adapters),
            )
            runners.append(lambda: health.run(stop))
        runners.insert(0, lambda: app.scheduler.run(stop))
        log.info("plan-bot running", extra={"adapters": ",".join(notifier.adapters)})
        # Coroutines are only created now, so an error while wiring leaks none of them.
        tasks = [asyncio.ensure_future(start()) for start in runners]
        stopper = asyncio.ensure_future(stop.wait())
        try:
            done, _ = await asyncio.wait([*tasks, stopper], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not stopper and task.exception() is not None:
                    raise task.exception()  # type: ignore[misc]
        finally:
            stop.set()
            # Let the scheduler and adapters finish the job in flight (a cancelled
            # database call would leave a connection to be garbage collected).
            await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE_SECONDS)
            for task in [*tasks, stopper]:
                task.cancel()
            await asyncio.gather(*tasks, stopper, return_exceptions=True)
