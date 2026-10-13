from __future__ import annotations

from datetime import timedelta

import pytest

from plan_bot.config import Settings
from plan_bot.ics import IcsError
from plan_bot.repository import ChatRef, Repository
from plan_bot.service import BotService, ChatUnavailable, UserError
from tests.conftest import FakeClock, FakeFeeds, RecordingNotifier, fixture_bytes, warsaw

CHAT = ChatRef("telegram", "100")
OTHER = ChatRef("discord", "200")
URL = "https://timetable.example.org/feed.ics"


async def test_commands_without_feed(service: BotService) -> None:
    for call in (service.today, service.tomorrow, service.next, service.week, service.groups):
        with pytest.raises(UserError, match="No timetable yet"):
            await call(CHAT)
    for call in (service.status, service.refresh):
        with pytest.raises(UserError, match="No timetable yet"):
            await call(CHAT)
    assert await service.forget(CHAT) == "There was nothing stored for this chat."


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (None, "Usage"),
        ("  ", "Usage"),
        ("ftp://example.org/a.ics", "must start with"),
        ("https://missing.example.org/a.ics", "HTTP 404"),
        ("https://bad.example.org/a.ics", "does not return an iCalendar"),
    ],
)
async def test_set_feed_errors(
    service: BotService, feeds: FakeFeeds, raw: str | None, message: str
) -> None:
    feeds.payloads["https://bad.example.org/a.ics"] = IcsError("nope")
    with pytest.raises(UserError, match=message):
        await service.set_feed(CHAT, raw)


async def test_set_feed_and_queries(service: BotService, clock: FakeClock) -> None:
    reply = await service.set_feed(CHAT, "demo")
    assert "Timetable saved (bundled fictional demo timetable)" in reply
    assert "Groups in this timetable: C1, C2, EN-B2, L1, L2" in reply
    assert "Reminders are on, 15 min" in reply

    today = await service.today(CHAT)
    assert today.startswith("Today · Monday, 12 Oct")
    assert "Lab 205 · L2" in today
    assert (await service.tomorrow(CHAT)).startswith("Tomorrow · Tuesday, 13 Oct")
    assert "Starts in 1 h 30 min." in await service.next(CHAT)
    assert (await service.week(CHAT)).startswith("This week Mon 12 Oct – Sun 18 Oct:")
    assert (await service.week(CHAT, "next")).startswith("Next week Mon 19 Oct")
    with pytest.raises(UserError):
        await service.week(CHAT, "later")

    clock.now = warsaw(2026, 10, 16, 18)  # Friday evening: Monday is still in the snapshot
    assert "Algorithms and Data Structures" in await service.week(CHAT)


async def test_filters(service: BotService) -> None:
    await service.set_feed(CHAT, "demo")
    assert "No filter" in await service.groups(CHAT)
    reply = await service.set_filter(CHAT, "L1, c1, xyz")
    assert reply.startswith("Filter set: L1,c1,xyz.")
    assert "Not found in the timetable tags: xyz" in reply
    assert "Current filter: L1,c1,xyz" in await service.groups(CHAT)
    today = await service.today(CHAT)
    assert "Lab 204" in today
    assert "Lab 205" not in today
    assert await service.set_filter(CHAT, "off") == "Filter removed: showing all classes."
    with pytest.raises(UserError, match="Usage"):
        await service.set_filter(CHAT, "")


async def test_settings_commands(service: BotService) -> None:
    assert await service.set_reminder(CHAT, "10") == "I will remind you 10 min before each class."
    assert "1 h" in await service.set_reminder(CHAT, "60min")
    assert await service.set_reminder(CHAT, "off") == "Reminders are off."
    for bad in ("soon", "0x", "100000", "-5"):
        with pytest.raises(UserError):
            await service.set_reminder(CHAT, bad)
    assert await service.set_changes(CHAT, "off") == "Change alerts are off."
    assert await service.set_changes(CHAT, "on") == "Change alerts are on."
    assert await service.set_summary(CHAT, "no") == "Weekly summary is off."
    assert await service.set_summary(CHAT, "yes") == "Weekly summary is on."
    with pytest.raises(UserError, match="/summary on"):
        await service.set_summary(CHAT, "maybe")


async def test_status_and_forget(
    service: BotService, repo: Repository, clock: FakeClock, feeds: FakeFeeds
) -> None:
    feeds.payloads[URL] = fixture_bytes("sample.ics")
    await service.set_feed(CHAT, URL)
    await service.set_reminder(CHAT, "off")
    clock.now += timedelta(minutes=42)
    status = await service.status(CHAT)
    assert "Feed: https://timetable.example.org/…" in status
    assert "feed.ics" not in status  # the private part of the link is never echoed
    assert "Reminders: off" in status
    assert "Last refresh: 42 min ago" in status
    sub = await repo.get(CHAT)
    assert sub is not None
    await repo.record_error(sub.id, "HTTP 500", clock.now)
    assert "Last error: HTTP 500" in await service.status(CHAT)
    assert "deleted" in await service.forget(CHAT)
    assert await repo.get(CHAT) is None


async def test_refresh_detects_changes_and_notifies(
    service: BotService, feeds: FakeFeeds, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    feeds.payloads[URL] = fixture_bytes("edits_before.ics")
    await service.set_feed(CHAT, URL)
    assert await service.refresh(CHAT) == "Timetable refreshed, no changes."

    feeds.payloads[URL] = fixture_bytes("edits_after.ics")
    clock.now += timedelta(minutes=31)
    assert await service.refresh_due(clock.now) == 1
    (message,) = notifier.texts()
    assert message.startswith("Timetable changed:")
    assert "Computer Networks (lab): CANCELLED" in message
    assert "room A-1 → Aula Magna" in message

    # Nothing new on the next refresh, and not due again yet.
    assert await service.refresh_due(clock.now + timedelta(minutes=5)) == 0
    clock.now += timedelta(minutes=31)
    assert await service.refresh_due(clock.now) == 1
    assert len(notifier.sent) == 1


async def test_change_alerts_respect_filter_and_switch(
    service: BotService, feeds: FakeFeeds, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    feeds.payloads[URL] = fixture_bytes("edits_before.ics")
    await service.set_feed(CHAT, URL)
    await service.set_filter(CHAT, "L2")  # hides the L1 lab
    feeds.payloads[URL] = fixture_bytes("edits_after.ics")
    reply = await service.refresh(CHAT)
    assert "Computer Networks (lab)" not in reply
    assert "Aula Magna" in reply

    feeds.payloads[URL] = fixture_bytes("edits_before.ics")
    await service.set_changes(CHAT, "off")
    clock.now += timedelta(hours=1)
    await service.refresh_due(clock.now)
    assert notifier.sent == []


async def test_repeated_errors_back_off_and_notify_once(
    service: BotService,
    feeds: FakeFeeds,
    clock: FakeClock,
    notifier: RecordingNotifier,
    repo: Repository,
) -> None:
    feeds.payloads[URL] = fixture_bytes("sample.ics")
    await service.set_feed(CHAT, URL)
    del feeds.payloads[URL]
    for _ in range(5):
        clock.now += timedelta(days=1)
        await service.refresh_due(clock.now)
    sub = await repo.get(CHAT)
    assert sub is not None
    assert sub.error_count == 5
    (message,) = notifier.texts()
    assert "could not refresh your timetable 3 times" in message
    # Back-off: right after a failure the feed is not retried.
    calls = len(feeds.calls)
    await service.refresh_due(clock.now + timedelta(minutes=31))
    assert len(feeds.calls) == calls
    # Old lessons are kept while the feed is broken.
    clock.now = warsaw(2026, 10, 19, 7)
    assert "Algorithms" in await service.today(CHAT)


async def test_reminders(
    service: BotService, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    await service.set_feed(CHAT, "demo")
    await service.set_feed(OTHER, "demo")
    await service.set_reminder(OTHER, "off")
    await service.set_filter(CHAT, "L1")
    now = warsaw(2026, 10, 12, 8, 16)
    assert await service.send_due_reminders(now) == 1
    assert notifier.sent[0][0] == CHAT
    assert notifier.texts()[0].startswith(
        "Reminder: Algorithms and Data Structures (lecture) starts in 14 min"
    )
    assert await service.send_due_reminders(now + timedelta(seconds=30)) == 0
    # The L1 lab at 10:15; the L2 lab at the same time is filtered out.
    assert await service.send_due_reminders(warsaw(2026, 10, 12, 10, 1)) == 1
    assert "Lab 204" in notifier.texts()[1]
    assert await service.prune(warsaw(2026, 10, 20)) == 2


async def test_weekly_summary(service: BotService, notifier: RecordingNotifier) -> None:
    await service.set_feed(CHAT, "demo")
    await service.set_feed(OTHER, "demo")
    await service.set_summary(OTHER, "off")
    assert await service.send_weekly_summaries(warsaw(2026, 10, 17, 18)) == 0  # Saturday
    assert await service.send_weekly_summaries(warsaw(2026, 10, 18, 17)) == 0  # too early
    assert await service.send_weekly_summaries(warsaw(2026, 10, 18, 18, 5)) == 1
    assert notifier.texts()[0].startswith("Coming week Mon 19 Oct – Sun 25 Oct:")
    assert await service.send_weekly_summaries(warsaw(2026, 10, 18, 20)) == 0


async def test_notifier_failures_are_contained(
    service: BotService, notifier: RecordingNotifier
) -> None:
    await service.set_feed(CHAT, "demo")
    notifier.fail = True
    assert await service.send_due_reminders(warsaw(2026, 10, 12, 8, 20)) == 1


async def test_default_notifier_drops_messages(repo: Repository, settings: object) -> None:
    from plan_bot.config import Settings

    assert isinstance(settings, Settings)
    service = BotService(repo, FakeFeeds(), settings, clock=FakeClock(warsaw(2026, 10, 12, 8)))
    await service.set_feed(CHAT, "demo")
    assert await service.send_due_reminders(warsaw(2026, 10, 12, 8, 20)) == 1


async def test_blocked_chats_are_forgotten(
    service: BotService, repo: Repository, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    await service.set_feed(CHAT, "demo")

    async def gone(chat: ChatRef, text: str) -> None:
        raise ChatUnavailable("bot was blocked")

    service.notifier.send = gone  # type: ignore[method-assign]
    clock.now = warsaw(2026, 10, 12, 8, 20)
    await service.send_due_reminders(clock.now)
    assert await repo.get(CHAT) is None  # no point refreshing for a user who left


async def test_reminders_survive_a_restart(
    service: BotService,
    repo: Repository,
    feeds: FakeFeeds,
    settings: Settings,
    clock: FakeClock,
    notifier: RecordingNotifier,
) -> None:
    await service.set_feed(CHAT, "demo")
    clock.now = warsaw(2026, 10, 12, 8, 20)
    assert await service.send_due_reminders(clock.now) == 1
    # A new process: fresh service objects on the same database.
    restarted = BotService(repo, feeds, settings, clock=clock, notifier=notifier)
    clock.now = warsaw(2026, 10, 12, 8, 25)
    assert await restarted.send_due_reminders(clock.now) == 0
    assert len(notifier.sent) == 1
    clock.now = warsaw(2026, 10, 12, 10, 5)  # the next lab block still gets its own reminder
    assert await restarted.send_due_reminders(clock.now) >= 1


async def test_reminders_follow_wall_clock_across_dst(
    service: BotService, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    # Europe/Warsaw returns to standard time on Sunday 25 Oct 2026. A class at 08:30 on
    # Monday the 26th is 07:30 UTC, one hour later in UTC than the week before.
    await service.set_feed(CHAT, "demo")
    clock.now = warsaw(2026, 10, 26, 8, 20)
    assert clock.now.utcoffset() == timedelta(hours=1)
    assert await service.send_due_reminders(clock.now) == 1
    assert "08:30" in notifier.texts()[-1]
    clock.now = warsaw(2026, 10, 19, 8, 20)
    assert clock.now.utcoffset() == timedelta(hours=2)
    assert await service.send_due_reminders(clock.now) == 1


async def test_demo_timetable_never_runs_out(
    service: BotService, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    clock.now = warsaw(2027, 6, 2, 7, 0)  # months after the bundled semester ended
    reply = await service.set_feed(CHAT, "demo")
    assert "0 upcoming" not in reply
    assert "Today · Wednesday, 2 Jun" in await service.today(CHAT)
    assert "Starts in" in await service.next(CHAT)
    # The demo shifts by whole weeks over time; that must never produce change alerts.
    clock.now = warsaw(2027, 6, 9, 7, 0)
    await service.refresh_due(clock.now)
    assert notifier.sent == []


async def test_feed_errors_are_localized(service: BotService, feeds: FakeFeeds) -> None:
    await service.set_language(CHAT, "pl")
    with pytest.raises(UserError, match="Serwer odpowiedział HTTP 404"):
        await service.set_feed(CHAT, "https://missing.example.org/a.ics")
