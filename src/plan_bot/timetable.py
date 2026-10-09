"""Queries over a list of lessons: a day, a week, the next class."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from plan_bot.domain import GroupFilter, Lesson


@dataclass(frozen=True, slots=True)
class NextClass:
    current: Lesson | None
    upcoming: Lesson | None


def _visible(lessons: Iterable[Lesson], group_filter: GroupFilter) -> list[Lesson]:
    return sorted(
        (les for les in lessons if group_filter.matches(les)),
        key=lambda les: (les.start, les.summary),
    )


def lessons_on(
    lessons: Iterable[Lesson], day: date, tz: tzinfo, group_filter: GroupFilter
) -> list[Lesson]:
    """Lessons starting on local ``day``; cancelled ones are kept (they are news)."""
    return [
        les for les in _visible(lessons, group_filter) if les.start.astimezone(tz).date() == day
    ]


def week_of(
    lessons: Iterable[Lesson], monday: date, tz: tzinfo, group_filter: GroupFilter
) -> dict[date, list[Lesson]]:
    days: dict[date, list[Lesson]] = {monday + timedelta(days=i): [] for i in range(7)}
    for les in _visible(lessons, group_filter):
        local = les.start.astimezone(tz).date()
        if local in days:
            days[local].append(les)
    return days


def next_class(lessons: Iterable[Lesson], now: datetime, group_filter: GroupFilter) -> NextClass:
    current: Lesson | None = None
    upcoming: Lesson | None = None
    for les in _visible(lessons, group_filter):
        if les.cancelled or les.end <= now:
            continue
        if les.start <= now:
            current = current or les
        elif upcoming is None:
            upcoming = les
            break
    return NextClass(current, upcoming)


def starting_between(
    lessons: Iterable[Lesson], start: datetime, end: datetime, group_filter: GroupFilter
) -> list[Lesson]:
    """Non-cancelled lessons with ``start < lesson.start <= end``."""
    return [
        les
        for les in _visible(lessons, group_filter)
        if not les.cancelled and start < les.start <= end
    ]


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def group_names(lessons: Iterable[Lesson]) -> list[str]:
    seen: dict[str, str] = {}
    for les in lessons:
        for group in les.groups:
            seen.setdefault(group.casefold(), group)
    return sorted(seen.values(), key=str.casefold)
