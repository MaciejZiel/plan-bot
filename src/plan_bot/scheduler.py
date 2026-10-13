"""A small asyncio scheduler driving refreshes, reminders and weekly summaries.

All state (what was refreshed, which reminder went out) lives in the database,
so a single periodic tick is enough and restarts are harmless.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from plan_bot.service import BotService, utc_now

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        service: BotService,
        *,
        tick_seconds: float = 30,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.service = service
        self.tick_seconds = tick_seconds
        self.clock = clock
        self._ticks = 0
        #: Set after every completed tick; the health endpoint watches it.
        self.last_tick_at: datetime | None = None
        self.last_tick_ok = True
        self._refreshing: asyncio.Future[bool] | None = None

    async def tick(self) -> None:
        """Send due reminders and summaries; start a feed refresh unless one is running.

        Refreshing downloads every due feed and can take long when servers are
        slow, so it runs in the background: reminders keep going out on time.
        """
        now = self.clock()
        jobs: list[tuple[str, Callable[[datetime], Awaitable[int]]]] = [
            ("reminders", self.service.send_due_reminders),
            ("weekly", self.service.send_weekly_summaries),
        ]
        if self._ticks % 120 == 0:
            jobs.append(("prune", self.service.prune))
        self._ticks += 1
        if self._refreshing is None or self._refreshing.done():
            self._refreshing = asyncio.ensure_future(
                self._run_jobs(
                    now,
                    [
                        ("refresh", self.service.refresh_due),
                        ("reminders-after-refresh", self.service.send_due_reminders),
                    ],
                )
            )
        self.last_tick_ok = await self._run_jobs(now, jobs)
        self.last_tick_at = utc_now()

    async def wait_for_refresh(self) -> None:
        """Wait until the background refresh started by the last tick (if any) is done."""
        if self._refreshing is not None:
            await self._refreshing

    @staticmethod
    async def _run_jobs(
        now: datetime, jobs: list[tuple[str, Callable[[datetime], Awaitable[int]]]]
    ) -> bool:
        ok = True
        for name, job in jobs:
            try:
                count = await job(now)
            except Exception:
                ok = False
                log.exception("scheduled job %s failed", name, extra={"job": name})
            else:
                if count:
                    log.info("scheduled job done", extra={"job": name, "items": count})
        return ok

    async def run(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        log.info("scheduler started, tick every %ss", self.tick_seconds)
        try:
            while not stop.is_set():
                await self.tick()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.tick_seconds)
        except asyncio.CancelledError:
            if self._refreshing is not None:
                self._refreshing.cancel()
            raise
        # Let the refresh in flight finish; cancelling this task cancels it too.
        await self.wait_for_refresh()
