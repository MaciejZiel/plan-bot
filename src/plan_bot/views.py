"""Structured answers: what a command found, before it is turned into text.

Plain-text platforms render a view with :func:`render_text`; richer platforms
(Discord embeds) read the fields directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, tzinfo

from plan_bot.domain import Lesson
from plan_bot.formatting import format_day, format_next, format_reminder, format_week
from plan_bot.timetable import NextClass


@dataclass(frozen=True, slots=True)
class DayView:
    title: str
    day: date
    lessons: tuple[Lesson, ...]
    lang: str
    tz: tzinfo
    now: datetime
    warning: str = ""


@dataclass(frozen=True, slots=True)
class WeekView:
    title: str
    days: dict[date, list[Lesson]]
    lang: str
    tz: tzinfo
    now: datetime
    warning: str = ""


@dataclass(frozen=True, slots=True)
class NextView:
    info: NextClass
    lang: str
    tz: tzinfo
    now: datetime
    warning: str = ""


@dataclass(frozen=True, slots=True)
class ReminderView:
    lesson: Lesson
    lang: str
    tz: tzinfo
    now: datetime
    #: ``True`` for the reminder sent when the class starts, not before it.
    at_start: bool = False


View = DayView | WeekView | NextView | ReminderView


def render_text(view: View) -> str:
    text = _render(view)
    warning = getattr(view, "warning", "")
    return f"{text}\n\n{warning}" if warning else text


def _render(view: View) -> str:
    match view:
        case DayView():
            return format_day(view.title, view.day, list(view.lessons), view.tz, view.lang)
        case WeekView():
            return format_week(view.days, view.tz, title=view.title, lang=view.lang)
        case NextView():
            return format_next(view.info, view.now, view.tz, view.lang)
        case ReminderView():
            return format_reminder(
                view.lesson, view.now, view.tz, view.lang, at_start=view.at_start
            )
