from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from plan_bot.repository import ChatRef, Repository
from plan_bot.scheduler import Scheduler
from plan_bot.service import BotService
from tests.conftest import FakeClock, RecordingNotifier, fixture_bytes, warsaw


async def test_tick_runs_jobs(
    service: BotService, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    await service.set_feed(ChatRef("telegram", "sched"), "demo")
    clock.now = warsaw(2026, 10, 12, 8, 20)
    scheduler = Scheduler(service, tick_seconds=0.01, clock=clock)
    await scheduler.tick()
    # tick() starts the feed refresh in the background; let it finish before the
    # engine is disposed, or its pooled connection is garbage collected unclosed.
    await scheduler.wait_for_refresh()
    assert any(text.startswith("Reminder:") for text in notifier.texts())


async def test_tick_tells_a_stale_upload_to_upload_again_once(
    service: BotService, repo: Repository, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    chat = ChatRef("discord", "user:9")
    data = fixture_bytes("edits_before.ics")

    async def read() -> bytes:
        return data

    await service.upload_feed(chat, "plan.ics", "text/calendar", len(data), read)
    await repo.update(chat, parser_version=0, reminder_minutes=0)
    scheduler = Scheduler(service, tick_seconds=0.01, clock=clock)
    for _ in range(3):
        await scheduler.tick()
        await scheduler.wait_for_refresh()
        clock.now += timedelta(minutes=1)
    assert [c for c, _ in notifier.sent] == [chat]
    assert "upload the .ics file again" in notifier.texts()[0]


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
    scheduler = Scheduler(service, clock=clock)
    await scheduler.tick()
    await scheduler.wait_for_refresh()
    assert calls == ["weekly"]
    assert "scheduled job reminders failed" in caplog.text


async def test_run_stops_on_event(service: BotService, clock: FakeClock) -> None:
    scheduler = Scheduler(service, tick_seconds=0.01, clock=clock)
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler.run(stop))
    for _ in range(200):  # a slow machine may need more than a few milliseconds per tick
        if scheduler._ticks >= 2:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert scheduler._ticks >= 2


async def test_slow_refresh_does_not_delay_reminders(
    service: BotService,
    clock: FakeClock,
    notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await service.set_feed(ChatRef("telegram", "sched"), "demo")
    gate = asyncio.Event()
    refreshes: list[datetime] = []

    async def slow_refresh(now: datetime) -> int:
        refreshes.append(now)
        await gate.wait()
        return 1

    monkeypatch.setattr(service, "refresh_due", slow_refresh)
    scheduler = Scheduler(service, clock=clock)
    clock.now = warsaw(2026, 10, 12, 8, 0)
    await asyncio.wait_for(scheduler.tick(), timeout=1)
    clock.now = warsaw(2026, 10, 12, 8, 20)
    await asyncio.wait_for(scheduler.tick(), timeout=1)  # the refresh is still running
    assert any(text.startswith("Reminder:") for text in notifier.texts())
    assert len(refreshes) == 1  # no second refresh while one is in flight
    gate.set()
    await scheduler.wait_for_refresh()
    await scheduler.tick()
    await scheduler.wait_for_refresh()
    assert len(refreshes) == 2


async def test_cancelling_run_cancels_the_refresh(
    service: BotService, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()

    async def endless(now: datetime) -> int:
        started.set()
        await asyncio.Event().wait()
        return 0

    monkeypatch.setattr(service, "refresh_due", endless)
    scheduler = Scheduler(service, tick_seconds=60, clock=clock)
    task = asyncio.create_task(scheduler.run(asyncio.Event()))
    await asyncio.wait_for(started.wait(), timeout=1)
    for _ in range(100):  # cancel between ticks, not in the middle of a database call
        if scheduler.last_tick_at is not None:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert scheduler._refreshing is not None
    assert scheduler._refreshing.cancelled()
