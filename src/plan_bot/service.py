"""The chat-platform-independent core of plan-bot.

Adapters translate platform events into calls on :class:`BotService` and
deliver the returned text; background jobs push messages through a
:class:`Notifier`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from plan_bot.config import Settings
from plan_bot.db import Subscription
from plan_bot.diff import Change, diff
from plan_bot.domain import GroupFilter, Lesson
from plan_bot.fetch import DEMO_URL, FetchError, demo_calendar, normalize_url, redact_url
from plan_bot.formatting import (
    format_changes,
    format_day,
    format_next,
    format_reminder,
    format_week,
    humanize,
)
from plan_bot.ics import IcsError, Window, expand
from plan_bot.repository import ChatRef, Repository
from plan_bot.timetable import (
    group_names,
    lessons_on,
    monday_of,
    next_class,
    starting_between,
    week_of,
)

log = logging.getLogger(__name__)

#: Consecutive refresh failures after which the chat is told about the problem.
ERROR_NOTIFY_THRESHOLD = 3
MAX_REMINDER_MINUTES = 24 * 60


class UserError(Exception):
    """A problem caused by user input; the message is shown verbatim."""


class FeedSource(Protocol):
    async def fetch(self, url: str) -> bytes: ...


class Notifier(Protocol):
    async def send(self, chat: ChatRef, text: str) -> None: ...


class NullNotifier:
    async def send(self, chat: ChatRef, text: str) -> None:
        log.info("no notifier configured, dropping message for %s", chat)


def utc_now() -> datetime:
    return datetime.now(UTC)


NO_FEED = (
    "No timetable yet. Send /setfeed <ICS link> with your university calendar link, "
    "or /setfeed demo to try the fictional sample timetable."
)


def _on_off(raw: str | None, what: str) -> bool:
    value = (raw or "").strip().lower()
    if value in {"on", "yes", "1", "true"}:
        return True
    if value in {"off", "no", "0", "false"}:
        return False
    raise UserError(f"Use /{what} on or /{what} off")


class BotService:
    def __init__(
        self,
        repo: Repository,
        fetcher: FeedSource,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = utc_now,
        notifier: Notifier | None = None,
    ) -> None:
        self.repo = repo
        self.fetcher = fetcher
        self.settings = settings
        self.tz = settings.timezone
        self.clock = clock
        self.notifier: Notifier = notifier or NullNotifier()

    # ------------------------------------------------------------------ commands

    async def set_feed(self, chat: ChatRef, raw_url: str | None) -> str:
        if not raw_url or not raw_url.strip():
            raise UserError("Usage: /setfeed <ICS link>  (or /setfeed demo)")
        try:
            url = normalize_url(raw_url)
        except FetchError as exc:
            raise UserError(str(exc)) from exc
        now = self.clock()
        lessons = await self._download(url, now)
        sub = await self.repo.update(chat, ics_url=url)
        await self._store(sub, lessons, now)
        upcoming = [les for les in lessons if les.start >= now and not les.cancelled]
        groups = group_names(lessons)
        lines = [
            f"Timetable saved ({redact_url(url)}).",
            f"{len(upcoming)} upcoming classes found.",
        ]
        if groups:
            lines.append(f"Groups in this timetable: {', '.join(groups)}")
            lines.append("Show only yours with e.g. /filter " + ",".join(groups[:2]))
        if sub.reminder_minutes:
            lines.append(f"Reminders are on, {sub.reminder_minutes} min before each class.")
        return "\n".join(lines)

    async def today(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        day = self.clock().astimezone(self.tz).date()
        return format_day(
            "Today", day, lessons_on(lessons, day, self.tz, self._filter(sub)), self.tz
        )

    async def tomorrow(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        day = self.clock().astimezone(self.tz).date() + timedelta(days=1)
        selected = lessons_on(lessons, day, self.tz, self._filter(sub))
        return format_day("Tomorrow", day, selected, self.tz)

    async def next(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        now = self.clock()
        return format_next(next_class(lessons, now, self._filter(sub)), now, self.tz)

    async def week(self, chat: ChatRef, which: str | None = None) -> str:
        sub, lessons = await self._load(chat)
        choice = (which or "").strip().lower()
        if choice not in {"", "this", "next"}:
            raise UserError("Use /week or /week next")
        monday = monday_of(self.clock().astimezone(self.tz).date())
        title = "This week"
        if choice == "next":
            monday += timedelta(days=7)
            title = "Next week"
        days = week_of(lessons, monday, self.tz, self._filter(sub))
        return format_week(days, self.tz, title=title)

    async def groups(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        names = group_names(lessons)
        current = self._filter(sub)
        lines = [f"Groups: {', '.join(names)}" if names else "This timetable has no group tags."]
        lines.append(
            f"Current filter: {sub.group_filter}" if current else "No filter: showing everything."
        )
        return "\n".join(lines)

    async def set_filter(self, chat: ChatRef, raw: str | None) -> str:
        value = (raw or "").strip()
        if not value:
            raise UserError("Usage: /filter L1,C2  or  /filter off")
        if value.lower() in {"off", "none", "clear", "all"}:
            await self.repo.update(chat, group_filter="")
            return "Filter removed: showing all classes."
        cleaned = GroupFilter.clean(value)
        parsed = GroupFilter.parse(cleaned)
        sub = await self.repo.update(chat, group_filter=cleaned)
        known = {g.casefold() for g in group_names(await self.repo.lessons(sub.id))}
        unknown = sorted(parsed.tokens - known)
        reply = f"Filter set: {cleaned}. Classes without a group are always shown."
        if known and unknown:
            reply += f"\nNot found in the timetable tags: {', '.join(unknown)}"
        return reply

    async def set_reminder(self, chat: ChatRef, raw: str | None) -> str:
        value = (raw or "").strip().lower()
        if value in {"off", "0", "no"}:
            await self.repo.update(chat, reminder_minutes=0)
            return "Reminders are off."
        try:
            minutes = int(value.removesuffix("min").strip())
        except ValueError as exc:
            raise UserError("Usage: /remind 15  (minutes before class)  or  /remind off") from exc
        if not 1 <= minutes <= MAX_REMINDER_MINUTES:
            raise UserError(f"Pick between 1 and {MAX_REMINDER_MINUTES} minutes.")
        await self.repo.update(chat, reminder_minutes=minutes)
        return f"I will remind you {humanize(timedelta(minutes=minutes))} before each class."

    async def set_changes(self, chat: ChatRef, raw: str | None) -> str:
        enabled = _on_off(raw, "changes")
        await self.repo.update(chat, notify_changes=enabled)
        return "Change alerts are on." if enabled else "Change alerts are off."

    async def set_summary(self, chat: ChatRef, raw: str | None) -> str:
        enabled = _on_off(raw, "summary")
        await self.repo.update(chat, weekly_summary=enabled)
        return "Weekly summary is on." if enabled else "Weekly summary is off."

    async def status(self, chat: ChatRef) -> str:
        sub = await self.repo.get(chat)
        if sub is None or sub.ics_url is None:
            return NO_FEED
        lessons = await self.repo.lessons(sub.id)
        lines = [
            f"Feed: {redact_url(sub.ics_url)}",
            f"Classes stored: {len(lessons)}",
            f"Filter: {sub.group_filter or 'none'}",
            "Reminders: "
            + (f"{sub.reminder_minutes} min before" if sub.reminder_minutes else "off"),
            f"Change alerts: {'on' if sub.notify_changes else 'off'}",
            f"Weekly summary: {'on' if sub.weekly_summary else 'off'}",
        ]
        if sub.last_refresh_at is not None:
            ago = humanize(self.clock() - sub.last_refresh_at)
            lines.append(f"Last refresh: {ago} ago")
        if sub.last_error:
            lines.append(f"Last error: {sub.last_error}")
        return "\n".join(lines)

    async def refresh(self, chat: ChatRef) -> str:
        sub = await self.repo.get(chat)
        if sub is None or sub.ics_url is None:
            return NO_FEED
        changes = await self.refresh_subscription(sub, self.clock(), notify=False)
        relevant = [c for c in changes if c.lesson.matches(self._filter(sub))]
        if not relevant:
            return "Timetable refreshed, no changes."
        return format_changes(relevant, self.tz)

    async def forget(self, chat: ChatRef) -> str:
        if await self.repo.delete(chat):
            return "Done. Your feed link, settings and stored timetable were deleted."
        return "There was nothing stored for this chat."

    # ---------------------------------------------------------- background jobs

    async def refresh_due(self, now: datetime) -> int:
        """Refresh every feed whose refresh interval has elapsed; returns the count."""
        refreshed = 0
        base = timedelta(minutes=self.settings.refresh_minutes)
        for sub in await self.repo.subscriptions_with_feed():
            backoff = base * min(2**sub.error_count, 16)
            if sub.last_refresh_at is not None and now - sub.last_refresh_at < backoff:
                continue
            refreshed += 1
            try:
                await self.refresh_subscription(sub, now, notify=True)
            except UserError as exc:
                count = await self.repo.record_error(sub.id, str(exc), now)
                log.warning("refresh failed for %s:%s: %s", sub.platform, sub.chat_id, exc)
                if count == ERROR_NOTIFY_THRESHOLD:
                    await self._notify(
                        sub,
                        f"I could not refresh your timetable {count} times in a row: {exc}\n"
                        "Check the link with /status or set a new one with /setfeed.",
                    )
        return refreshed

    async def refresh_subscription(
        self, sub: Subscription, now: datetime, *, notify: bool
    ) -> list[Change]:
        assert sub.ics_url is not None
        old = await self.repo.lessons(sub.id)
        new = await self._download(sub.ics_url, now)
        window_end = await self._store(sub, new, now)
        until = min(
            window_end,
            sub.window_end or window_end,
            now + timedelta(days=self.settings.change_horizon_days),
        )
        changes = diff(old, new, since=now, until=until) if old else []
        if notify and changes and sub.notify_changes and sub.ics_url != DEMO_URL:
            relevant = [c for c in changes if c.lesson.matches(self._filter(sub))]
            if relevant:
                await self._notify(sub, format_changes(relevant, self.tz))
        return changes

    async def send_due_reminders(self, now: datetime) -> int:
        sent = 0
        for sub in await self.repo.subscriptions_with_feed():
            if not sub.reminder_minutes:
                continue
            horizon = now + timedelta(minutes=sub.reminder_minutes)
            lessons = await self.repo.lessons(sub.id, start=now, end=horizon)
            for lesson in starting_between(lessons, now, horizon, self._filter(sub)):
                if await self.repo.mark_reminded(sub.id, lesson.key, lesson.start):
                    await self._notify(sub, format_reminder(lesson, now, self.tz))
                    sent += 1
        return sent

    async def send_weekly_summaries(self, now: datetime) -> int:
        local = now.astimezone(self.tz)
        if (
            local.weekday() != self.settings.summary_weekday
            or local.hour < self.settings.summary_hour
        ):
            return 0
        monday = monday_of(local.date()) + timedelta(days=7)
        year, week, _ = monday.isocalendar()
        key = f"{year}-W{week:02d}"
        sent = 0
        for sub in await self.repo.subscriptions_with_feed():
            if not sub.weekly_summary or sub.last_weekly_key == key:
                continue
            lessons = await self.repo.lessons(sub.id)
            days = week_of(lessons, monday, self.tz, self._filter(sub))
            await self._notify(sub, format_week(days, self.tz, title="Coming week"))
            await self.repo.update(ChatRef(sub.platform, sub.chat_id), last_weekly_key=key)
            sent += 1
        return sent

    async def prune(self, now: datetime) -> int:
        return await self.repo.prune_reminders(now - timedelta(days=2))

    # ------------------------------------------------------------------ helpers

    def _window(self, now: datetime) -> Window:
        # Keep the past week too, so "/week" still shows Monday on a Friday.
        return Window(now - timedelta(days=8), now + timedelta(days=self.settings.horizon_days))

    async def _download(self, url: str, now: datetime) -> list[Lesson]:
        try:
            if url == DEMO_URL:
                data = demo_calendar(now.astimezone(self.tz).date())
            else:
                data = await self.fetcher.fetch(url)
            return expand(data, self._window(now), self.tz)
        except FetchError as exc:
            raise UserError(f"Could not download the timetable: {exc}") from exc
        except IcsError as exc:
            raise UserError(f"That link does not return an iCalendar file ({exc}).") from exc

    async def _store(self, sub: Subscription, lessons: list[Lesson], now: datetime) -> datetime:
        window = self._window(now)
        await self.repo.replace_lessons(sub.id, lessons, refreshed_at=now, window_end=window.end)
        return window.end

    async def _load(self, chat: ChatRef) -> tuple[Subscription, list[Lesson]]:
        sub = await self.repo.get(chat)
        if sub is None or sub.ics_url is None:
            raise UserError(NO_FEED)
        return sub, await self.repo.lessons(sub.id)

    @staticmethod
    def _filter(sub: Subscription) -> GroupFilter:
        return GroupFilter.parse(sub.group_filter)

    async def _notify(self, sub: Subscription, text: str) -> None:
        chat = ChatRef(sub.platform, sub.chat_id)
        try:
            await self.notifier.send(chat, text)
        except Exception:  # one broken chat must not stop the job for everybody
            log.exception("failed to deliver a message to %s", chat)


__all__ = ["DEMO_URL", "BotService", "FeedSource", "Notifier", "UserError", "utc_now"]
