"""Plain-text rendering shared by every chat platform.

Messages avoid platform-specific markup so the same text works in Telegram,
Discord and the local console. Every function takes the chat's language.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from plan_bot.diff import Change, ChangeKind
from plan_bot.domain import Lesson
from plan_bot.i18n import DAYS, DEFAULT_LANG, MONTHS, SHORT_DAYS, tr
from plan_bot.timetable import NextClass


def day_label(day: date, lang: str = DEFAULT_LANG) -> str:
    return f"{DAYS[lang][day.weekday()].capitalize()}, {day.day} {MONTHS[lang][day.month - 1]}"


def short_day(day: date, lang: str = DEFAULT_LANG) -> str:
    return f"{SHORT_DAYS[lang][day.weekday()]} {day.day} {MONTHS[lang][day.month - 1]}"


def hm(moment: datetime, tz: tzinfo) -> str:
    return f"{moment.astimezone(tz):%H:%M}"


def span(lesson: Lesson, tz: tzinfo) -> str:
    return f"{hm(lesson.start, tz)}–{hm(lesson.end, tz)}"


def humanize(delta: timedelta, lang: str = DEFAULT_LANG) -> str:
    minutes = max(0, math.ceil(delta.total_seconds() / 60))
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    d, h, m = tr(lang, "unit.d"), tr(lang, "unit.h"), tr(lang, "unit.min")
    if days:
        return f"{days} {d} {hours} {h}" if hours else f"{days} {d}"
    if hours:
        return f"{hours} {h} {mins} {m}" if mins else f"{hours} {h}"
    return f"{mins} {m}"


def lesson_line(lesson: Lesson, tz: tzinfo, lang: str = DEFAULT_LANG) -> str:
    details = [d for d in (lesson.location, ", ".join(lesson.groups)) if d]
    suffix = f"  ({' · '.join(details)})" if details else ""
    prefix = tr(lang, "cancelled_tag") if lesson.cancelled else ""
    return f"{span(lesson, tz)}  {prefix}{lesson.summary}{suffix}"


def format_day(
    title: str, day: date, lessons: list[Lesson], tz: tzinfo, lang: str = DEFAULT_LANG
) -> str:
    header = f"{title} · {day_label(day, lang)}"
    if not lessons:
        return f"{header}\n{tr(lang, 'no_classes_day')}"
    return "\n".join([header, *(lesson_line(les, tz, lang) for les in lessons)])


def format_week(
    days: dict[date, list[Lesson]], tz: tzinfo, *, title: str = "Week", lang: str = DEFAULT_LANG
) -> str:
    first, last = min(days), max(days)
    count = sum(1 for lessons in days.values() for les in lessons if not les.cancelled)
    lines = [
        tr(
            lang,
            "week_header",
            title=title,
            first=short_day(first, lang),
            last=short_day(last, lang),
            count=count,
        )
    ]
    for day in sorted(days):
        lessons = days[day]
        if not lessons:
            continue
        lines.append("")
        lines.append(day_label(day, lang))
        lines.extend(lesson_line(les, tz, lang) for les in lessons)
    if count == 0:
        lines.append(tr(lang, "no_classes_week"))
    return "\n".join(lines)


def format_next(info: NextClass, now: datetime, tz: tzinfo, lang: str = DEFAULT_LANG) -> str:
    lines: list[str] = []
    if info.current is not None:
        cur = info.current
        room = tr(lang, "in_room", room=cur.location) if cur.location else ""
        lines.append(
            tr(lang, "now", summary=cur.summary, room=room, delta=humanize(cur.end - now, lang))
        )
    if info.upcoming is None:
        lines.append(tr(lang, "no_upcoming"))
        return "\n".join(lines)
    nxt = info.upcoming
    when = nxt.start.astimezone(tz)
    lines.append(tr(lang, "next_label", summary=nxt.summary))
    where = f" · {nxt.location}" if nxt.location else ""
    lines.append(f"{short_day(when.date(), lang)}, {span(nxt, tz)}{where}")
    lines.append(tr(lang, "starts_in", delta=humanize(nxt.start - now, lang)))
    return "\n".join(lines)


def format_reminder(lesson: Lesson, now: datetime, tz: tzinfo, lang: str = DEFAULT_LANG) -> str:
    where = f" · {lesson.location}" if lesson.location else ""
    head = tr(lang, "reminder", summary=lesson.summary, delta=humanize(lesson.start - now, lang))
    return f"{head}\n{span(lesson, tz)}{where}"


def describe_change(change: Change, tz: tzinfo, lang: str = DEFAULT_LANG) -> str:
    old, new = change.old, change.new
    base = old or new
    assert base is not None
    start = base.start.astimezone(tz)
    head = f"{short_day(start.date(), lang)} {hm(base.start, tz)} {base.summary}"
    kinds = change.kinds
    if ChangeKind.CANCELLED in kinds:
        return f"{head}: {tr(lang, 'ch.cancelled')}"
    if ChangeKind.REMOVED in kinds:
        return f"{head}: {tr(lang, 'ch.removed')}"
    if ChangeKind.ADDED in kinds:
        assert new is not None
        where = tr(lang, "in_room", room=new.location) if new.location else ""
        return f"{head}: {tr(lang, 'ch.added', span=span(new, tz), where=where)}"
    assert old is not None
    assert new is not None
    parts: list[str] = []
    if ChangeKind.RESTORED in kinds:
        parts.append(tr(lang, "ch.restored"))
    if ChangeKind.RESCHEDULED in kinds:
        new_day = new.start.astimezone(tz).date()
        on_day = "" if new_day == start.date() else f"{short_day(new_day, lang)} "
        parts.append(tr(lang, "ch.moved", day=on_day, span=span(new, tz)))
    if ChangeKind.ROOM in kinds:
        parts.append(tr(lang, "ch.room", old=old.location or "?", new=new.location or "?"))
    return f"{head}: {', '.join(parts)}"


def format_changes(changes: Iterable[Change], tz: tzinfo, lang: str = DEFAULT_LANG) -> str:
    lines = [f"- {describe_change(c, tz, lang)}" for c in changes]
    return "\n".join([tr(lang, "changed_header"), *lines])
