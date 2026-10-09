from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from plan_bot.repository import ChatRef
from plan_bot.scheduler import Scheduler
from plan_bot.service import BotService
from tests.conftest import FakeClock, RecordingNotifier, warsaw


async def test_tick_runs_jobs(
    service: BotService, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    await service.set_feed(ChatRef("telegram", "sched"), "demo")
    clock.now = warsaw(2026, 10, 12, 8, 20)
    scheduler = Scheduler(service, tick_seconds=0.01, clock=clock)
    await scheduler.tick()
    assert any(text.startswith("Reminder:") for text in notifier.texts())


async def test_failing_job_does_not_stop_others(
    service: BotService,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[str] = []

    async def broken(now: datetime) -> int:
        raise RuntimeError("db down")

    async def weekly(now: datetime) -> int:
        calls.append("weekly")
        return 0

    monkeypatch.setattr(service, "send_due_reminders", broken)
    monkeypatch.setattr(service, "send_weekly_summaries", weekly)
    await Scheduler(service, clock=clock).tick()
    assert calls == ["weekly"]
    assert "scheduled job reminders failed" in caplog.text


async def test_run_stops_on_event(service: BotService, clock: FakeClock) -> None:
    scheduler = Scheduler(service, tick_seconds=0.01, clock=clock)
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler.run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert scheduler._ticks >= 2
