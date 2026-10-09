"""Plain-text rendering shared by every chat platform.

Messages avoid platform-specific markup so the same text works in Telegram,
Discord and the local console.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from plan_bot.diff import Change, ChangeKind
from plan_bot.domain import Lesson
from plan_bot.timetable import NextClass

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip


def day_label(day: date) -> str:
    return f"{DAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"


def short_day(day: date) -> str:
    return f"{DAYS[day.weekday()][:3]} {day.day} {MONTHS[day.month - 1]}"


def hm(moment: datetime, tz: tzinfo) -> str:
    return f"{moment.astimezone(tz):%H:%M}"


def span(lesson: Lesson, tz: tzinfo) -> str:
    return f"{hm(lesson.start, tz)}–{hm(lesson.end, tz)}"


def humanize(delta: timedelta) -> str:
    minutes = max(0, int(delta.total_seconds() // 60))
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days} d {hours} h" if hours else f"{days} d"
    if hours:
        return f"{hours} h {mins} min" if mins else f"{hours} h"
    return f"{mins} min"


def lesson_line(lesson: Lesson, tz: tzinfo) -> str:
    details = [d for d in (lesson.location, ", ".join(lesson.groups)) if d]
    suffix = f"  ({' · '.join(details)})" if details else ""
    prefix = "[CANCELLED] " if lesson.cancelled else ""
    return f"{span(lesson, tz)}  {prefix}{lesson.summary}{suffix}"


def format_day(title: str, day: date, lessons: list[Lesson], tz: tzinfo) -> str:
    header = f"{title} · {day_label(day)}"
    if not lessons:
        return f"{header}\nNo classes. Enjoy the free time."
    return "\n".join([header, *(lesson_line(les, tz) for les in lessons)])


def format_week(days: dict[date, list[Lesson]], tz: tzinfo, *, title: str = "Week") -> str:
    first, last = min(days), max(days)
    count = sum(1 for lessons in days.values() for les in lessons if not les.cancelled)
    lines = [f"{title} {short_day(first)} – {short_day(last)}: {count} classes"]
    for day in sorted(days):
        lessons = days[day]
        if not lessons:
            continue
        lines.append("")
        lines.append(day_label(day))
        lines.extend(lesson_line(les, tz) for les in lessons)
    if count == 0:
        lines.append("No classes this week.")
    return "\n".join(lines)


def format_next(info: NextClass, now: datetime, tz: tzinfo) -> str:
    lines: list[str] = []
    if info.current is not None:
        cur = info.current
        room = f" in {cur.location}" if cur.location else ""
        lines.append(f"Now: {cur.summary}{room}, ends in {humanize(cur.end - now)}.")
    if info.upcoming is None:
        lines.append("No upcoming classes in the timetable.")
        return "\n".join(lines)
    nxt = info.upcoming
    when = nxt.start.astimezone(tz)
    lines.append(f"Next: {nxt.summary}")
    where = f" · {nxt.location}" if nxt.location else ""
    lines.append(f"{short_day(when.date())}, {span(nxt, tz)}{where}")
    lines.append(f"Starts in {humanize(nxt.start - now)}.")
    return "\n".join(lines)


def format_reminder(lesson: Lesson, now: datetime, tz: tzinfo) -> str:
    where = f" · {lesson.location}" if lesson.location else ""
    return (
        f"Reminder: {lesson.summary} starts in {humanize(lesson.start - now)}\n"
        f"{span(lesson, tz)}{where}"
    )


def describe_change(change: Change, tz: tzinfo) -> str:
    old, new = change.old, change.new
    base = old or new
    assert base is not None
    start = base.start.astimezone(tz)
    head = f"{short_day(start.date())} {hm(base.start, tz)} {base.summary}"
    kinds = change.kinds
    if ChangeKind.CANCELLED in kinds:
        return f"{head}: CANCELLED"
    if ChangeKind.REMOVED in kinds:
        return f"{head}: removed from the timetable"
    if ChangeKind.ADDED in kinds:
        assert new is not None
        where = f" in {new.location}" if new.location else ""
        return f"{head}: new class, {span(new, tz)}{where}"
    assert old is not None
    assert new is not None
    parts: list[str] = []
    if ChangeKind.RESTORED in kinds:
        parts.append("back on (no longer cancelled)")
    if ChangeKind.RESCHEDULED in kinds:
        new_day = new.start.astimezone(tz).date()
        on_day = "" if new_day == start.date() else f"{short_day(new_day)} "
        parts.append(f"moved to {on_day}{span(new, tz)}")
    if ChangeKind.ROOM in kinds:
        parts.append(f"room {old.location or '?'} → {new.location or '?'}")
    return f"{head}: {', '.join(parts)}"


def format_changes(changes: Iterable[Change], tz: tzinfo) -> str:
    lines = [f"- {describe_change(c, tz)}" for c in changes]
    return "\n".join(["Timetable changed:", *lines])
