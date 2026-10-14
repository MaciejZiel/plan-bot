"""Calendars uploaded as a file: limits, storage, no refreshing and change detection."""

from __future__ import annotations

from datetime import timedelta

import pytest

from plan_bot.config import Settings
from plan_bot.ics import PARSER_VERSION
from plan_bot.repository import ChatRef, Repository
from plan_bot.service import BotService, NotificationsBlocked, UserError
from tests.conftest import FakeClock, FakeFeeds, RecordingNotifier, fixture_bytes, warsaw

CHAT = ChatRef("discord", "user:7")
OTHER = ChatRef("discord", "user:8")
BEFORE = fixture_bytes("edits_before.ics")
AFTER = fixture_bytes("edits_after.ics")


async def upload(
    service: BotService,
    data: bytes,
    *,
    name: str = "plan.ics",
    kind: str | None = "text/calendar",
    chat: ChatRef = CHAT,
    size: int | None = None,
) -> str:
    async def read() -> bytes:
        return data

    return await service.upload_feed(chat, name, kind, len(data) if size is None else size, read)


async def test_a_valid_upload_becomes_the_timetable(
    service: BotService, repo: Repository, feeds: FakeFeeds
) -> None:
    reply = await upload(service, BEFORE)
    assert "Timetable saved (uploaded file)." in reply
    assert "upcoming classes found" in reply
    assert "/forget deletes it" in reply
    sub = await repo.get(CHAT)
    assert sub is not None
    assert sub.ics_url == "upload"
    assert await repo.lessons(sub.id)
    assert feeds.calls == []

    # Everything else works unchanged.
    assert "Computer Networks (lecture)" in await service.next(CHAT)
    assert "Computer Networks" in await service.today(CHAT)
    assert "Computer Networks" in await service.week(CHAT)
    assert await service.has_feed(CHAT)


async def test_status_shows_the_upload_date_and_suggests_reuploading(
    service: BotService, clock: FakeClock
) -> None:
    await upload(service, BEFORE)
    clock.now += timedelta(days=3)
    status = await service.status(CHAT)
    assert "Feed: uploaded file, 2026-10-12" in status
    assert "re-upload" in status
    assert "Last refresh" not in status


async def test_status_is_polish_when_the_chat_is(service: BotService, repo: Repository) -> None:
    await repo.update(CHAT, language="pl")
    await upload(service, BEFORE)
    status = await service.status(CHAT)
    assert "Plan: wgrany plik, 2026-10-12" in status
    assert "wgraj" in status


async def test_an_attachment_over_the_limit_is_refused_without_reading_it(
    repo: Repository, feeds: FakeFeeds, db_url: str
) -> None:
    small = BotService(repo, feeds, Settings(database_url=db_url, max_ics_bytes=2048))
    read_calls = 0

    async def read() -> bytes:
        nonlocal read_calls
        read_calls += 1
        return b"x"

    with pytest.raises(UserError, match="too large"):
        await small.upload_feed(CHAT, "plan.ics", "text/calendar", 3000, read)
    assert read_calls == 0
    assert await repo.get(CHAT) is None


async def test_a_file_that_lies_about_its_size_is_refused_after_reading(
    repo: Repository, feeds: FakeFeeds, db_url: str
) -> None:
    small = BotService(repo, feeds, Settings(database_url=db_url, max_ics_bytes=2048))
    with pytest.raises(UserError, match="too large"):
        await upload(small, b"x" * 3000, size=10)
    assert await repo.get(CHAT) is None


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("plan.pdf", "application/pdf"),
        ("plan.png", "image/png"),
        ("plan.txt", "text/plain"),
        ("plan.ics", "image/png"),
        ("plan.ics.exe", None),
        ("plan", "text/calendar"),
    ],
)
async def test_the_wrong_type_is_refused(
    service: BotService, repo: Repository, name: str, kind: str | None
) -> None:
    with pytest.raises(UserError, match="does not look like a calendar"):
        await upload(service, BEFORE, name=name, kind=kind)
    assert await repo.get(CHAT) is None


@pytest.mark.parametrize("kind", [None, "text/calendar; charset=utf-8", "application/octet-stream"])
async def test_usual_content_types_and_upper_case_names_are_accepted(
    service: BotService, kind: str | None
) -> None:
    assert "Timetable saved" in await upload(service, BEFORE, name="PLAN.ICS", kind=kind)


async def test_a_file_that_is_not_a_calendar_is_refused(
    service: BotService, repo: Repository
) -> None:
    with pytest.raises(UserError, match="not an iCalendar file"):
        await upload(service, b"just some text, not a calendar")
    assert await repo.get(CHAT) is None


async def test_a_failed_reupload_keeps_the_previous_file(
    service: BotService, repo: Repository
) -> None:
    await upload(service, BEFORE)
    with pytest.raises(UserError):
        await upload(service, b"garbage")
    sub = await repo.get(CHAT)
    assert sub is not None
    assert await repo.lessons(sub.id)


async def test_refresh_skips_uploaded_calendars(
    service: BotService, feeds: FakeFeeds, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    await upload(service, BEFORE)
    await service.set_reminder(CHAT, "off")
    clock.now += timedelta(days=2)
    assert await service.refresh_due(clock.now) == 0
    assert feeds.calls == []
    assert notifier.sent == []
    with pytest.raises(UserError, match="uploaded file"):
        await service.refresh(CHAT)


async def test_refresh_still_serves_other_chats_next_to_uploaded_ones(
    service: BotService, feeds: FakeFeeds, clock: FakeClock
) -> None:
    url = "https://timetable.example.org/feed.ics"
    feeds.payloads[url] = BEFORE
    await upload(service, BEFORE)
    await service.set_feed(OTHER, url)
    clock.now += timedelta(hours=2)
    assert await service.refresh_due(clock.now) == 1
    assert feeds.calls == [url, url]


async def test_reuploading_replaces_the_file_and_reports_the_changes(
    service: BotService, repo: Repository, clock: FakeClock
) -> None:
    await upload(service, BEFORE)
    clock.now += timedelta(hours=1)
    reply = await upload(service, AFTER)
    assert "Timetable changed:" in reply
    assert "Computer Networks (lab): CANCELLED" in reply
    assert "room A-1 → Aula Magna" in reply
    sub = await repo.get(CHAT)
    assert sub is not None
    lessons = await repo.lessons(sub.id)
    assert any(les.location == "Aula Magna" for les in lessons)
    assert sub.ics_url == "upload"

    again = await upload(service, AFTER)
    assert "Timetable changed:" not in again
    assert "no changes" in again


async def test_reupload_changes_respect_the_group_filter(service: BotService) -> None:
    await upload(service, BEFORE)
    await service.set_filter(CHAT, "L2")  # hides the L1 lab
    reply = await upload(service, AFTER)
    assert "Computer Networks (lab)" not in reply
    assert "Aula Magna" in reply


async def test_switching_from_a_link_to_a_file_is_not_diffed(
    service: BotService, feeds: FakeFeeds
) -> None:
    feeds.payloads["https://timetable.example.org/feed.ics"] = BEFORE
    await service.set_feed(CHAT, "https://timetable.example.org/feed.ics")
    reply = await upload(service, AFTER)
    assert "Timetable changed:" not in reply
    assert "no changes" not in reply


async def test_reminders_work_for_uploaded_calendars(
    service: BotService, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    await upload(service, BEFORE)
    clock.now = warsaw(2026, 10, 12, 7, 50)  # the 08:00 lecture is within 15 minutes
    assert await service.send_due_reminders(clock.now) == 1
    assert "Computer Networks" in notifier.texts()[0]


async def test_forget_deletes_the_uploaded_data_for_that_chat_only(
    service: BotService, repo: Repository
) -> None:
    await upload(service, BEFORE)
    await upload(service, AFTER, chat=OTHER)
    sub = await repo.get(CHAT)
    other = await repo.get(OTHER)
    assert sub is not None
    assert other is not None
    assert "deleted" in await service.forget(CHAT)
    assert await repo.get(CHAT) is None
    assert await repo.lessons(sub.id) == []
    assert await repo.lessons(other.id)


async def test_the_pjatk_style_export_shows_local_times_rooms_and_one_group(
    service: BotService, clock: FakeClock
) -> None:
    clock.now = warsaw(2026, 10, 20, 7, 0)
    reply = await upload(service, fixture_bytes("gakko_export.ics"))
    assert "Groups in this timetable" not in reply  # one tag cannot split anything
    assert "only one group tag (PLAN-FICTIONAL)" in await service.groups(CHAT)
    assert "only one group tag" in await service.set_filter(CHAT, "PLAN-FICTIONAL")
    text = await service.next(CHAT)
    assert "Imaginary Algebra lecture" in text
    assert "12:00" in text
    assert "W21" in text


async def test_reupload_after_a_parser_change_does_not_list_every_class_as_changed(
    service: BotService, repo: Repository
) -> None:
    await upload(service, BEFORE)
    await repo.update(CHAT, parser_version=0)
    reply = await upload(service, AFTER)
    assert "read differently before" in reply
    assert "Timetable changed" not in reply
    sub = await repo.get(CHAT)
    assert sub is not None
    assert sub.parser_version == PARSER_VERSION
    # The next upload is compared as usual.
    assert "read differently" not in await upload(service, BEFORE)


async def test_an_upload_stays_stale_until_it_is_uploaded_again(
    service: BotService,
    repo: Repository,
    feeds: FakeFeeds,
    clock: FakeClock,
    notifier: RecordingNotifier,
) -> None:
    await upload(service, BEFORE)
    await repo.update(CHAT, parser_version=0)  # stored before the parser fix

    # Refreshing never touches an upload, however many ticks and days go by.
    for _ in range(3):
        clock.now += timedelta(days=1)
        assert await service.refresh_due(clock.now) == 0
    sub = await repo.get(CHAT)
    assert sub is not None
    assert sub.parser_version == 0
    assert feeds.calls == []
    with pytest.raises(UserError, match="uploaded"):
        await service.refresh(CHAT)
    assert (await repo.get(CHAT)).parser_version == 0  # type: ignore[union-attr]

    # Re-uploading is the only thing that brings it up to date.
    await upload(service, AFTER)
    sub = await repo.get(CHAT)
    assert sub is not None
    assert sub.parser_version == PARSER_VERSION


async def test_a_stale_upload_gets_one_notice_and_a_warning_on_every_view(
    service: BotService,
    repo: Repository,
    clock: FakeClock,
    notifier: RecordingNotifier,
) -> None:
    await upload(service, BEFORE)
    assert await service.send_reupload_notices(clock.now) == 0  # current: nothing to say
    assert "Warning" not in await service.today(CHAT)

    await repo.update(CHAT, parser_version=0)
    assert await service.send_reupload_notices(clock.now) == 1
    assert len(notifier.sent) == 1
    chat, text = notifier.sent[0]
    assert chat == CHAT
    assert "upload the .ics file again" in text

    # Once only, also across later ticks.
    clock.now += timedelta(minutes=30)
    assert await service.send_reupload_notices(clock.now) == 0
    assert len(notifier.sent) == 1

    # The warning stays on every view while the upload is stale.
    for call in (service.today, service.tomorrow, service.next, service.week):
        assert "Warning: these times may be shifted" in await call(CHAT)

    # A fresh upload clears the warning.
    await upload(service, AFTER)
    for call in (service.today, service.next, service.week):
        assert "Warning" not in await call(CHAT)


async def test_the_stale_notice_is_polish_when_the_chat_is_and_retried_if_undelivered(
    service: BotService,
    repo: Repository,
    clock: FakeClock,
    notifier: RecordingNotifier,
) -> None:
    await repo.update(CHAT, language="pl")
    await upload(service, BEFORE)
    await repo.update(CHAT, parser_version=0)

    # A closed DM disables pushes and sends nothing, so nothing is marked as told.
    class Blocked:
        async def send(self, *_: object, **__: object) -> None:
            raise NotificationsBlocked

    service.notifier = Blocked()
    assert await service.send_reupload_notices(clock.now) == 0
    sub = await repo.get(CHAT)
    assert sub is not None
    assert sub.reupload_notified == 0
    assert "Uwaga: te godziny" in await service.today(CHAT)

    service.notifier = notifier
    assert await service.send_reupload_notices(clock.now) == 1
    assert "Wgraj plik .ics ponownie" in notifier.texts()[0]


async def test_link_subscriptions_never_get_the_upload_notice(
    service: BotService,
    repo: Repository,
    feeds: FakeFeeds,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    feeds.payloads["https://timetable.example.org/feed.ics"] = BEFORE
    await service.set_feed(CHAT, "https://timetable.example.org/feed.ics")
    await repo.update(CHAT, parser_version=0)
    assert await service.send_reupload_notices(clock.now) == 0
    assert notifier.sent == []
    assert "Warning" not in await service.today(CHAT)

async def test_identical_content_is_parsed_once(
    service: BotService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from plan_bot.ics import expand as real

    calls = 0

    def counting(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("plan_bot.service.expand", counting)
    await upload(service, BEFORE)
    await upload(service, BEFORE, chat=OTHER)
    assert calls == 1
    await upload(service, AFTER)
    assert calls == 2


async def test_a_failed_parse_is_remembered_too(
    service: BotService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from plan_bot.ics import expand as real

    calls = 0

    def counting(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("plan_bot.service.expand", counting)
    for _ in range(3):
        with pytest.raises(UserError, match="not an iCalendar"):
            await upload(service, b"BEGIN:VCALENDAR\r\nnonsense\r\n")
    assert calls == 1


async def test_a_queued_upload_gets_busy_instead_of_hanging(service: BotService) -> None:
    service.expand_queue_seconds = 0.05
    async with service._expanding:
        with pytest.raises(UserError, match="busy"):
            await upload(service, BEFORE)
    assert "Timetable saved" in await upload(service, BEFORE)


async def test_a_busy_queue_does_not_count_as_a_feed_error(
    service: BotService, repo: Repository, feeds: FakeFeeds, clock: FakeClock
) -> None:
    feeds.payloads["https://uni.example/a.ics"] = BEFORE
    await service.set_feed(CHAT, "https://uni.example/a.ics")
    service.expand_queue_seconds = 0.05
    clock.now += timedelta(days=1)
    feeds.payloads["https://uni.example/a.ics"] = AFTER
    async with service._expanding:
        await service.refresh_due(clock.now)
    sub = await repo.get(CHAT)
    assert sub is not None
    assert sub.error_count == 0
    assert sub.last_error is None
