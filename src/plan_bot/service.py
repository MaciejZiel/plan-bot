"""The chat-platform-independent core of plan-bot.

Adapters translate platform events into calls on :class:`BotService` and
deliver the returned text; background jobs push messages through a
:class:`Notifier`.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
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
from plan_bot.i18n import DEFAULT_LANG, LANGS, normalize_lang, tr
from plan_bot.ics import FeedTooComplex, IcsError, Window, expand
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


class NoFeedError(UserError):
    """The chat has not set a timetable yet."""


class ChatUnavailable(Exception):
    """Raised by a notifier when the chat is gone (the user blocked the bot, left, ...)."""


class FeedSource(Protocol):
    async def fetch(self, url: str) -> bytes: ...


class Notifier(Protocol):
    async def send(self, chat: ChatRef, text: str) -> None: ...


class NullNotifier:
    async def send(self, chat: ChatRef, text: str) -> None:
        log.info("no notifier configured, dropping message for %s", chat)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _on_off(raw: str | None, what: str, lang: str) -> bool:
    value = (raw or "").strip().lower()
    if value in {"on", "yes", "1", "true"}:
        return True
    if value in {"off", "no", "0", "false"}:
        return False
    raise UserError(tr(lang, "on_off_usage", what=what))


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
        # Expanding a feed is CPU-bound: do it in a worker thread so the event loop
        # keeps answering other chats, and one at a time so feeds cannot pile up.
        self._expanding = asyncio.Lock()
        # Chat ids are numbers from a small space: a plain hash of one is easy to
        # reverse, so log pseudonyms are keyed with a secret only this bot knows.
        secret = f"{settings.telegram_token or ''}:{settings.discord_token or ''}"
        self._log_key = hashlib.sha256(b"plan-bot log pseudonym:" + secret.encode()).digest()

    # ----------------------------------------------------------------- language

    async def language(self, chat: ChatRef) -> str:
        sub = await self.repo.get(chat)
        return sub.language if sub is not None else DEFAULT_LANG

    async def adopt_language(self, chat: ChatRef, hint: str | None) -> None:
        """On first contact, start in the language of the user's app (if supported).

        Only a non-default language is stored, so a chat that merely says hello in
        English leaves nothing behind in the database.
        """
        lang = normalize_lang(hint)
        if lang not in {None, DEFAULT_LANG} and await self.repo.get(chat) is None:
            await self.repo.update(chat, language=lang)

    async def set_language(self, chat: ChatRef, raw: str | None) -> str:
        lang = (raw or "").strip().lower()
        if lang not in LANGS:
            raise UserError(tr(await self.language(chat), "lang_usage"))
        await self.repo.update(chat, language=lang)
        return tr(lang, "lang_set")

    async def has_feed(self, chat: ChatRef) -> bool:
        sub = await self.repo.get(chat)
        return sub is not None and sub.ics_url is not None

    # ------------------------------------------------------------------ commands

    async def set_feed(self, chat: ChatRef, raw_url: str | None) -> str:
        lang = await self.language(chat)
        if not raw_url or not raw_url.strip():
            raise UserError(tr(lang, "subscribe_usage"))
        try:
            url = normalize_url(raw_url)
        except FetchError as exc:
            raise UserError(exc.localized(lang)) from exc
        now = self.clock()
        lessons = await self._download(url, now, lang)
        sub = await self.repo.update(chat, ics_url=url)
        await self._store(sub, lessons, now)
        upcoming = [les for les in lessons if les.start >= now and not les.cancelled]
        groups = group_names(lessons)
        lines = [
            tr(lang, "saved", where=self._where(url, lang)),
            tr(lang, "upcoming", n=len(upcoming)),
        ]
        if groups:
            lines.append(tr(lang, "groups_found", groups=", ".join(groups)))
            lines.append(tr(lang, "filter_hint", example=",".join(groups[:2])))
        if sub.reminder_minutes:
            lines.append(tr(lang, "reminders_on", n=sub.reminder_minutes))
        if url == DEMO_URL:
            lines.append(tr(lang, "saved_demo"))
        return "\n".join(lines)

    async def today(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        day = self.clock().astimezone(self.tz).date()
        selected = lessons_on(lessons, day, self.tz, self._filter(sub))
        return format_day(tr(sub.language, "title.today"), day, selected, self.tz, sub.language)

    async def tomorrow(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        day = self.clock().astimezone(self.tz).date() + timedelta(days=1)
        selected = lessons_on(lessons, day, self.tz, self._filter(sub))
        title = tr(sub.language, "title.tomorrow")
        return format_day(title, day, selected, self.tz, sub.language)

    async def next(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        now = self.clock()
        info = next_class(lessons, now, self._filter(sub))
        return format_next(info, now, self.tz, sub.language)

    async def week(self, chat: ChatRef, which: str | None = None) -> str:
        sub, lessons = await self._load(chat)
        lang = sub.language
        choice = (which or "").strip().lower()
        if choice not in {"", "this", "next"}:
            raise UserError(tr(lang, "week_usage"))
        monday = monday_of(self.clock().astimezone(self.tz).date())
        title = tr(lang, "title.week")
        if choice == "next":
            monday += timedelta(days=7)
            title = tr(lang, "title.next_week")
        days = week_of(lessons, monday, self.tz, self._filter(sub))
        return format_week(days, self.tz, title=title, lang=lang)

    async def groups(self, chat: ChatRef) -> str:
        sub, lessons = await self._load(chat)
        lang = sub.language
        names = group_names(lessons)
        current = self._filter(sub)
        lines = [
            tr(lang, "groups_list", groups=", ".join(names)) if names else tr(lang, "groups_none")
        ]
        lines.append(
            tr(lang, "filter_current", f=sub.group_filter) if current else tr(lang, "filter_none")
        )
        return "\n".join(lines)

    async def set_filter(self, chat: ChatRef, raw: str | None) -> str:
        lang = await self.language(chat)
        value = (raw or "").strip()
        if not value:
            raise UserError(tr(lang, "filter_usage"))
        if value.lower() in {"off", "none", "clear", "all"}:
            await self.repo.update(chat, group_filter="")
            return tr(lang, "filter_removed")
        cleaned = GroupFilter.clean(value)
        parsed = GroupFilter.parse(cleaned)
        sub = await self.repo.update(chat, group_filter=cleaned)
        known = {g.casefold() for g in group_names(await self.repo.lessons(sub.id))}
        unknown = sorted(parsed.tokens - known)
        reply = tr(lang, "filter_set", f=cleaned)
        if known and unknown:
            reply += "\n" + tr(lang, "filter_unknown", x=", ".join(unknown))
        return reply

    async def set_reminder(self, chat: ChatRef, raw: str | None) -> str:
        lang = await self.language(chat)
        value = (raw or "").strip().lower()
        if value in {"off", "0", "no"}:
            await self.repo.update(chat, reminder_minutes=0)
            return tr(lang, "remind_off")
        try:
            minutes = int(value.removesuffix("min").strip())
        except ValueError as exc:
            raise UserError(tr(lang, "remind_usage")) from exc
        if not 1 <= minutes <= MAX_REMINDER_MINUTES:
            raise UserError(tr(lang, "remind_range", max=MAX_REMINDER_MINUTES))
        await self.repo.update(chat, reminder_minutes=minutes)
        return tr(lang, "remind_set", delta=humanize(timedelta(minutes=minutes), lang))

    async def set_changes(self, chat: ChatRef, raw: str | None) -> str:
        lang = await self.language(chat)
        enabled = _on_off(raw, "changes", lang)
        await self.repo.update(chat, notify_changes=enabled)
        return tr(lang, "changes_on" if enabled else "changes_off")

    async def set_summary(self, chat: ChatRef, raw: str | None) -> str:
        lang = await self.language(chat)
        enabled = _on_off(raw, "summary", lang)
        await self.repo.update(chat, weekly_summary=enabled)
        return tr(lang, "summary_on" if enabled else "summary_off")

    async def status(self, chat: ChatRef) -> str:
        sub = await self.repo.get(chat)
        lang = sub.language if sub is not None else DEFAULT_LANG
        if sub is None or sub.ics_url is None:
            raise NoFeedError(tr(lang, "no_feed"))
        lessons = await self.repo.lessons(sub.id)
        remind = (
            tr(lang, "status_remind_min", n=sub.reminder_minutes)
            if sub.reminder_minutes
            else tr(lang, "off")
        )
        lines = [
            tr(lang, "status_feed", where=self._where(sub.ics_url, lang)),
            tr(lang, "status_classes", n=len(lessons)),
            tr(lang, "status_filter", f=sub.group_filter or tr(lang, "status_none")),
            tr(lang, "status_remind", v=remind),
            tr(lang, "status_changes", v=tr(lang, "on" if sub.notify_changes else "off")),
            tr(lang, "status_summary", v=tr(lang, "on" if sub.weekly_summary else "off")),
            tr(lang, "status_lang", v=sub.language),
        ]
        if sub.last_refresh_at is not None:
            ago = humanize(self.clock() - sub.last_refresh_at, lang)
            lines.append(tr(lang, "status_refresh", ago=ago))
        if sub.last_error:
            lines.append(tr(lang, "status_error", e=sub.last_error))
        return "\n".join(lines)

    async def refresh(self, chat: ChatRef) -> str:
        sub = await self.repo.get(chat)
        lang = sub.language if sub is not None else DEFAULT_LANG
        if sub is None or sub.ics_url is None:
            raise NoFeedError(tr(lang, "no_feed"))
        changes = await self.refresh_subscription(sub, self.clock(), notify=False)
        relevant = [c for c in changes if c.lesson.matches(self._filter(sub))]
        if not relevant:
            return tr(lang, "refreshed_same")
        return format_changes(relevant, self.tz, lang)

    async def forget(self, chat: ChatRef) -> str:
        lang = await self.language(chat)
        if await self.repo.delete(chat):
            return tr(lang, "forgotten")
        return tr(lang, "nothing_stored")

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
                log.warning(
                    "feed refresh failed",
                    extra={
                        "platform": sub.platform,
                        "chat": self._chat_tag(sub),
                        "error": str(exc),
                    },
                )
                if count == ERROR_NOTIFY_THRESHOLD:
                    await self._notify(
                        sub, tr(sub.language, "refresh_failing", count=count, error=exc)
                    )
            except Exception:  # one broken feed or chat must not stop the others
                log.exception("feed refresh crashed", extra={"chat": self._chat_tag(sub)})
        return refreshed

    async def refresh_subscription(
        self, sub: Subscription, now: datetime, *, notify: bool
    ) -> list[Change]:
        assert sub.ics_url is not None
        old = await self.repo.lessons(sub.id)
        new = await self._download(sub.ics_url, now, sub.language)
        window_end = await self._store(sub, new, now)
        if window_end is None:  # forgotten or switched to another feed meanwhile
            return []
        until = min(
            window_end,
            sub.window_end or window_end,
            now + timedelta(days=self.settings.change_horizon_days),
        )
        changes = diff(old, new, since=now, until=until) if old else []
        if notify and changes and sub.notify_changes and sub.ics_url != DEMO_URL:
            relevant = [c for c in changes if c.lesson.matches(self._filter(sub))]
            if relevant:
                await self._notify(sub, format_changes(relevant, self.tz, sub.language))
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
                    await self._notify(sub, format_reminder(lesson, now, self.tz, sub.language))
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
            title = tr(sub.language, "title.coming_week")
            text = format_week(days, self.tz, title=title, lang=sub.language)
            if await self._notify(sub, text):
                await self.repo.update(ChatRef(sub.platform, sub.chat_id), last_weekly_key=key)
                sent += 1
        return sent

    async def prune(self, now: datetime) -> int:
        return await self.repo.prune_reminders(now - timedelta(days=2))

    # ------------------------------------------------------------------ helpers

    def _window(self, now: datetime) -> Window:
        # Keep the past week too, so "/week" still shows Monday on a Friday.
        return Window(now - timedelta(days=8), now + timedelta(days=self.settings.horizon_days))

    @staticmethod
    def _where(url: str, lang: str) -> str:
        return tr(lang, "feed_demo") if url == DEMO_URL else redact_url(url)

    async def _download(self, url: str, now: datetime, lang: str) -> list[Lesson]:
        try:
            if url == DEMO_URL:
                data = demo_calendar(now.astimezone(self.tz).date())
            else:
                data = await self.fetcher.fetch(url)
            async with self._expanding:
                return await asyncio.to_thread(expand, data, self._window(now), self.tz)
        except FetchError as exc:
            raise UserError(tr(lang, "download_failed", error=exc.localized(lang))) from exc
        except FeedTooComplex as exc:
            raise UserError(tr(lang, "too_complex")) from exc
        except IcsError as exc:
            raise UserError(tr(lang, "not_ics", error=exc)) from exc

    async def _store(
        self, sub: Subscription, lessons: list[Lesson], now: datetime
    ) -> datetime | None:
        """Save the snapshot; ``None`` if the chat changed its feed or was deleted meanwhile."""
        window = self._window(now)
        stored = await self.repo.replace_lessons(
            sub.id, lessons, refreshed_at=now, window_end=window.end, feed_url=sub.ics_url
        )
        return window.end if stored else None

    async def _load(self, chat: ChatRef) -> tuple[Subscription, list[Lesson]]:
        sub = await self.repo.get(chat)
        if sub is None or sub.ics_url is None:
            lang = sub.language if sub is not None else DEFAULT_LANG
            raise NoFeedError(tr(lang, "no_feed"))
        return sub, await self.repo.lessons(sub.id)

    @staticmethod
    def _filter(sub: Subscription) -> GroupFilter:
        return GroupFilter.parse(sub.group_filter)

    async def chat_gone(self, chat: ChatRef) -> None:
        """The user blocked the bot or left: stop working for nobody and drop their data."""
        log.info("chat unavailable, deleting its data", extra={"chat": self._chat_tag(chat)})
        await self.repo.delete(chat)

    def _chat_tag(self, sub: Subscription | ChatRef) -> str:
        """Short stable pseudonym for logs, so chat ids are not written to disk."""
        message = f"{sub.platform}:{sub.chat_id}".encode()
        return hmac.new(self._log_key, message, hashlib.sha256).hexdigest()[:12]

    async def _notify(self, sub: Subscription, text: str) -> bool:
        """Send ``text``; ``False`` if the chat is gone (and its data was deleted)."""
        chat = ChatRef(sub.platform, sub.chat_id)
        try:
            await self.notifier.send(chat, text)
        except ChatUnavailable:
            await self.chat_gone(chat)
            return False
        except Exception:  # one broken chat must not stop the job for everybody
            log.exception("failed to deliver a message", extra={"chat": self._chat_tag(sub)})
        return True


__all__ = [
    "DEMO_URL",
    "BotService",
    "ChatUnavailable",
    "FeedSource",
    "NoFeedError",
    "Notifier",
    "UserError",
    "utc_now",
]
