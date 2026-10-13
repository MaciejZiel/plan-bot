"""Tiny HTTP health endpoint for process supervisors and reverse proxies.

``GET <base path>/healthz`` answers 200 while the database responds and the
scheduler is ticking, 503 otherwise. It exposes no user data.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime

from aiohttp import web
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from plan_bot import __version__
from plan_bot.service import utc_now

log = logging.getLogger(__name__)


class HealthServer:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        host: str,
        port: int,
        base_path: str = "",
        tick_seconds: float = 30,
        scheduler_last_tick: Callable[[], datetime | None],
        adapters: Callable[[], list[str]],
    ) -> None:
        self.engine = engine
        self.host = host
        self.port = port
        self.base_path = base_path
        self.tick_seconds = tick_seconds
        self.scheduler_last_tick = scheduler_last_tick
        self.adapters = adapters
        self.started = time.monotonic()
        self.started_at = utc_now()

    async def report(self) -> tuple[int, dict[str, object]]:
        db_ok = True
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            log.exception("health check: database unreachable")
            db_ok = False
        last = self.scheduler_last_tick()
        stale_after = max(self.tick_seconds * 4, 120)
        reference = last or self.started_at
        age = (utc_now() - reference).total_seconds()
        scheduler_ok = age <= stale_after
        healthy = db_ok and scheduler_ok
        body: dict[str, object] = {
            "status": "ok" if healthy else "degraded",
            "version": __version__,
            "uptime_seconds": round(time.monotonic() - self.started),
            "database": "ok" if db_ok else "error",
            "scheduler": "ok" if scheduler_ok else "stalled",
            "last_tick_age_seconds": None if last is None else round(age),
            "adapters": self.adapters(),
        }
        return (200 if healthy else 503), body

    async def _handle(self, request: web.Request) -> web.Response:
        status, body = await self.report()
        return web.json_response(body, status=status)

    def application(self) -> web.Application:
        app = web.Application()
        app.router.add_get(f"{self.base_path}/healthz", self._handle)
        return app

    async def run(self, stop: asyncio.Event) -> None:
        runner = web.AppRunner(self.application(), access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        log.info("health endpoint listening", extra={"host": self.host, "port": self.port})
        try:
            await stop.wait()
        finally:
            await runner.cleanup()
