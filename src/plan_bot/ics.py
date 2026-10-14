"""Turn an iCalendar (RFC 5545) feed into concrete :class:`Lesson` occurrences.

Recurrence is expanded with :mod:`dateutil.rrule` in the event's *local wall
clock*: a class at 08:30 Europe/Warsaw stays at 08:30 after the switch to or
from daylight saving time, exactly as calendar clients render it. ``EXDATE`` and
``RECURRENCE-ID`` values are compared as UTC instants, so it does not matter
which timezone the feed uses to spell them.
"""

from __future__ import annotations

import logging
import re
import time as clock
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any

from dateutil.rrule import rrulestr
from icalendar import Calendar, Component
from icalendar.prop import vRecur

from plan_bot.domain import Lesson

log = logging.getLogger(__name__)

#: Hard cap on generated occurrences per series, as a guard against hostile feeds.
MAX_OCCURRENCES_PER_EVENT = 2000
#: Occurrences a rule may generate in total, including those before the window:
#: a daily class since 1990 needs ~13k, ``FREQ=DAILY;BYMINUTE=...`` since 2000 would
#: need millions.
MAX_RULE_STEPS = 50_000
#: Lessons one feed may produce inside the window (a busy timetable has a few hundred).
MAX_LESSONS = 20_000
#: RDATE and EXDATE values one event may list (a semester has a few dozen).
MAX_DATES_PER_EVENT = 2000
#: Loops over feed contents look at the clock this often.
CHECK_EVERY = 256
#: Wall-clock budget for expanding one feed.
EXPAND_SECONDS = 10.0
#: Classes do not repeat by the hour, minute or second; such rules are hostile or broken.
SUB_DAILY = frozenset({"HOURLY", "MINUTELY", "SECONDLY"})
DEFAULT_DURATION = timedelta(minutes=90)
#: Bumped whenever the same feed can parse to different lessons than before. Stored per
#: subscription, so the first refresh after an upgrade can replace the snapshot silently
#: instead of announcing every shifted class as a change. The price: a genuine timetable
#: change that lands in that same refresh is not announced either. An uploaded file cannot be
#: re-read, so its chat is told once to upload it again and sees a warning until it does.
#: 1: a ``Z`` time is UTC again (version 0 read it as local time for the PJATK export).
PARSER_VERSION = 1
#: ``Subject s. W21``: some exports append the room to the title and leave LOCATION empty.
_TRAILING_ROOM = re.compile(r"^(?P<title>.*\S)\s+s\.\s+(?P<room>\S+)$", re.IGNORECASE)


class IcsError(ValueError):
    """The document is not a usable iCalendar feed."""


class FeedTooComplex(IcsError):
    """The feed is valid but too big or too slow to expand (see the limits above)."""


class _Budget:
    """Aborts the expansion of a feed that is too big or too slow to expand."""

    def __init__(self, seconds: float) -> None:
        self.deadline = clock.monotonic() + seconds

    def check(self) -> None:
        if clock.monotonic() > self.deadline:
            raise FeedTooComplex("the feed is too complex to expand")

    def tick(self, index: int) -> None:
        """Check the clock on every :data:`CHECK_EVERY`-th item of a loop."""
        if index % CHECK_EVERY == 0:
            self.check()


@dataclass(frozen=True, slots=True)
class Window:
    """Half-open interval ``[start, end)`` of aware datetimes."""

    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


def parse_calendar(data: bytes | str) -> Calendar:
    try:
        cal = Calendar.from_ical(data)
    except Exception as exc:  # icalendar raises a variety of exception types
        # The parser's message can quote the feed; keep it out of replies and logs.
        raise IcsError("not a valid iCalendar document") from exc
    if not isinstance(cal, Calendar) or cal.name != "VCALENDAR":
        raise IcsError("document does not contain a VCALENDAR")
    return cal


def expand(
    data: bytes | str, window: Window, default_tz: tzinfo, *, seconds: float = EXPAND_SECONDS
) -> list[Lesson]:
    """Parse ``data`` and return every lesson starting inside ``window``, sorted.

    Raises :class:`IcsError` when the feed yields more than :data:`MAX_LESSONS`
    lessons or takes longer than ``seconds`` to expand.
    """
    budget = _Budget(seconds)
    cal = parse_calendar(data)
    budget.check()
    masters: dict[str, Component] = {}
    overrides: dict[str, list[Component]] = {}
    singles: list[Component] = []
    for event in cal.walk("VEVENT"):
        uid = str(event.get("UID", "")).strip()
        if not uid or "DTSTART" not in event:
            log.debug("skipping VEVENT without UID or DTSTART")
            continue
        if "RECURRENCE-ID" in event:
            overrides.setdefault(uid, []).append(event)
        elif "RRULE" in event or "RDATE" in event:
            masters[uid] = event
        else:
            singles.append(event)

    lessons: list[Lesson] = []

    def add(lesson: Lesson) -> None:
        lessons.append(lesson)
        if len(lessons) > MAX_LESSONS:
            raise FeedTooComplex(f"more than {MAX_LESSONS} classes in the next months")

    for index, event in enumerate(singles):
        budget.tick(index)
        lesson = _lesson_from(event, key=str(event["UID"]), default_tz=default_tz)
        if lesson is not None and window.contains(lesson.start):
            add(lesson)

    for uid, master in masters.items():
        budget.check()
        for lesson in _expand_series(
            uid, master, overrides.pop(uid, []), window, default_tz, budget
        ):
            add(lesson)

    # Overrides whose master is missing (or was not recurring) still describe a class.
    index = 0
    for uid, orphans in overrides.items():
        for event in orphans:
            budget.tick(index)
            index += 1
            rid = _aware(event.decoded("RECURRENCE-ID"), default_tz)
            if rid is None:
                continue
            lesson = _lesson_from(event, key=_occurrence_key(uid, rid), default_tz=default_tz)
            if lesson is not None and window.contains(lesson.start):
                add(lesson)

    lessons.sort(key=lambda les: (les.start, les.summary, les.key))
    return _unique_keys(lessons)


def _split_room(summary: str, location: str) -> tuple[str, str]:
    """Move a trailing `` s. <room>`` out of the summary when there is no location."""
    if location:
        return summary, location
    match = _TRAILING_ROOM.match(summary)
    if match is None:
        return summary, location
    return match["title"], match["room"]


def _unique_keys(lessons: list[Lesson]) -> list[Lesson]:
    """Feeds sometimes reuse a UID for unrelated events; keep keys unique."""
    seen: dict[str, int] = {}
    out: list[Lesson] = []
    for lesson in lessons:
        count = seen.get(lesson.key, 0)
        seen[lesson.key] = count + 1
        out.append(replace(lesson, key=f"{lesson.key}#{count}") if count else lesson)
    return out


def _expand_series(
    uid: str,
    master: Component,
    overrides: list[Component],
    window: Window,
    default_tz: tzinfo,
    budget: _Budget,
) -> Iterator[Lesson]:
    dtstart = _aware(master.decoded("DTSTART"), default_tz)
    if dtstart is None:  # all-day series are not classes
        return
    tz = dtstart.tzinfo
    assert tz is not None
    duration = _duration(master, dtstart, default_tz)

    by_rid: dict[datetime, Component] = {}
    for index, event in enumerate(overrides):
        budget.tick(index)
        rid = _aware(event.decoded("RECURRENCE-ID"), default_tz)
        if rid is not None:
            by_rid[rid.astimezone(UTC)] = event

    excluded = {d.astimezone(UTC) for d in _date_list(master, "EXDATE", tz, budget)}
    starts = set(_rrule_starts(master, dtstart, window, duration, budget))
    starts.update(_date_list(master, "RDATE", tz, budget))
    starts.add(dtstart)

    seen_rids: set[datetime] = set()
    for index, original in enumerate(sorted(starts)):
        budget.tick(index)
        rid_utc = original.astimezone(UTC)
        if rid_utc in excluded:
            continue
        seen_rids.add(rid_utc)
        key = _occurrence_key(uid, original)
        override = by_rid.get(rid_utc)
        if override is not None:
            lesson = _lesson_from(override, key=key, default_tz=default_tz, fallback=master)
        else:
            lesson = _lesson_from(master, key=key, default_tz=default_tz, start=original)
        if lesson is not None and window.contains(lesson.start):
            yield lesson

    # An override may move an occurrence into the window from outside it.
    for index, (rid_utc, override) in enumerate(by_rid.items()):
        budget.tick(index)
        if rid_utc in seen_rids or rid_utc in excluded:
            continue
        lesson = _lesson_from(
            override, key=_occurrence_key(uid, rid_utc), default_tz=default_tz, fallback=master
        )
        if lesson is not None and window.contains(lesson.start):
            yield lesson


def _rrule_starts(
    master: Component, dtstart: datetime, window: Window, duration: timedelta, budget: _Budget
) -> Iterator[datetime]:
    rules = master.get("RRULE")
    if rules is None:
        return
    if not isinstance(rules, list):
        rules = [rules]
    tz = dtstart.tzinfo
    assert tz is not None
    naive_start = dtstart.replace(tzinfo=None)
    # Search a little before the window so occurrences shifted by an override are seen.
    lo = (window.start - duration - timedelta(days=1)).astimezone(tz).replace(tzinfo=None)
    hi = window.end.astimezone(tz).replace(tzinfo=None)
    for rule in rules:
        try:
            sub_daily = SUB_DAILY.intersection(str(f).upper() for f in rule.get("FREQ", []))
            text, max_count = _naive_rule(rule, tz, hi)
            rset = rrulestr(text, dtstart=naive_start, forceset=True)
        except Exception as exc:  # broken RRULE values surface as various exception types
            log.warning("ignoring unparsable RRULE (%s)", type(exc).__name__)
            continue
        if sub_daily:
            log.warning("ignoring sub-daily RRULE")
            continue
        if _never_matches(rule):
            log.warning("ignoring RRULE that never matches")
            continue
        produced = 0
        # Iterate from DTSTART (``xafter`` would do the same internally) so that the
        # occurrences before the window count against the step budget too.
        for step, occurrence in enumerate(rset):
            if occurrence >= hi or produced >= MAX_OCCURRENCES_PER_EVENT:
                break
            if max_count is not None and step >= max_count:
                break
            if step >= MAX_RULE_STEPS:
                log.warning("RRULE generates too many occurrences")
                break
            if step % 1000 == 999:
                budget.check()
            if occurrence >= lo:
                produced += 1
                yield _localize(occurrence, tz)


_MONTH_DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _never_matches(rule: vRecur) -> bool:
    """True for ``BYMONTH`` / ``BYMONTHDAY`` pairs no date satisfies (30 February).

    dateutil checks ``UNTIL`` only when it produces an occurrence, so a rule that matches
    nothing walks to the year 9999 (about 2.5 s) and neither ``UNTIL`` nor the budget can
    stop it. This catches the cheap way to ask for that; the budget still bounds the rest.
    """
    days = [int(d) for d in rule.get("BYMONTHDAY", [])]
    if not days or any(d <= 0 for d in days):
        return False
    months = [int(m) for m in rule.get("BYMONTH", [])] or list(range(1, 13))
    return not any(d <= _MONTH_DAYS[m - 1] for d in days for m in months if 1 <= m <= 12)


def _naive_rule(rule: vRecur, tz: tzinfo, end: datetime) -> tuple[str, int | None]:
    """Render ``rule`` with ``UNTIL`` in naive local time capped at ``end``, plus its ``COUNT``.

    ``COUNT`` is taken out of the rule (dateutil deprecates it next to ``UNTIL``) and
    returned, so the caller enforces it.

    Expanding in naive local time keeps the wall-clock time stable across DST. The cap
    matters for rules that never match (``BYMONTH=2;BYMONTHDAY=30``): without an end,
    the iterator walks to the year 9999 inside a single step and no budget can stop it.
    """
    data: dict[str, Any] = {k: list(v) for k, v in rule.items()}
    until = data.get("UNTIL")
    if until:
        value = until[0]
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(tz)
            data["UNTIL"] = [value.replace(tzinfo=None)]
        elif isinstance(value, date):
            data["UNTIL"] = [datetime.combine(value, time(23, 59, 59))]
    count_values = data.pop("COUNT", None)
    count = int(count_values[0]) if count_values else None
    capped = data.get("UNTIL")
    if not capped or capped[0] > end:
        data["UNTIL"] = [end]
    rendered: bytes = vRecur(data).to_ical()  # type: ignore[no-untyped-call]
    return rendered.decode(), count


def _localize(naive: datetime, tz: tzinfo) -> datetime:
    """Attach ``tz``; wall times that do not exist (spring-forward gap) are shifted.

    Normalising through UTC turns 02:30 on the day clocks jump from 02:00 to
    03:00 into 03:30, which is what calendar applications show as well.
    """
    return naive.replace(tzinfo=tz).astimezone(UTC).astimezone(tz)


def _lesson_from(
    event: Component,
    *,
    key: str,
    default_tz: tzinfo,
    start: datetime | None = None,
    fallback: Component | None = None,
) -> Lesson | None:
    """Build a lesson from ``event``; properties missing on overrides come from ``fallback``."""

    def prop(name: str) -> Any:
        if name in event:
            return event.get(name)
        if fallback is not None:
            return fallback.get(name)
        return None

    if start is None:
        start = _aware(event.decoded("DTSTART"), default_tz)
        if start is None:
            return None
        end = _end(event, start, default_tz, fallback)
    else:
        base = _aware(event.decoded("DTSTART"), default_tz)
        assert base is not None
        assert start.tzinfo is not None
        wall_end = start.replace(tzinfo=None) + _duration(event, base, default_tz)
        end = _localize(wall_end, start.tzinfo)

    status = str(prop("STATUS") or "").upper()
    summary, location = _split_room(_text(prop("SUMMARY")) or "(untitled)", _text(prop("LOCATION")))
    return Lesson(
        key=key,
        uid=str(event.get("UID", "") or (fallback.get("UID", "") if fallback else "")),
        start=start,
        end=end,
        summary=summary,
        location=location,
        description=_text(prop("DESCRIPTION")),
        groups=tuple(_categories(prop("CATEGORIES"))),
        cancelled=status == "CANCELLED",
    )


def _end(
    event: Component, start: datetime, default_tz: tzinfo, fallback: Component | None
) -> datetime:
    if "DTEND" in event:
        end = _aware(event.decoded("DTEND"), default_tz)
        if end is not None and end >= start:
            return end
    if "DURATION" in event:
        value = event.decoded("DURATION")
        if isinstance(value, timedelta):
            return start + value
    if fallback is not None:
        base = _aware(fallback.decoded("DTSTART"), default_tz)
        if base is not None:
            return start + _duration(fallback, base, default_tz)
    return start + DEFAULT_DURATION


def _duration(event: Component, start: datetime, default_tz: tzinfo) -> timedelta:
    if "DTEND" in event:
        end = _aware(event.decoded("DTEND"), default_tz)
        if end is not None and end >= start:
            # Duration in wall-clock terms, so DST does not stretch a class.
            return end.replace(tzinfo=None) - start.astimezone(end.tzinfo).replace(tzinfo=None)
    if "DURATION" in event:
        value = event.decoded("DURATION")
        if isinstance(value, timedelta):
            return value
    return DEFAULT_DURATION


def _aware(value: object, default_tz: tzinfo) -> datetime | None:
    """Return an aware datetime, or ``None`` for all-day (date-only) values."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=default_tz)
    return None


def _date_list(event: Component, name: str, tz: tzinfo, budget: _Budget) -> Iterator[datetime]:
    values = event.get(name)
    if values is None:
        return
    if not isinstance(values, list):
        values = [values]
    count = 0
    for group in values:
        for item in getattr(group, "dts", []):
            count += 1
            if count > MAX_DATES_PER_EVENT:
                raise FeedTooComplex(f"more than {MAX_DATES_PER_EVENT} {name} dates in one event")
            budget.tick(count)
            moment = _aware(item.dt, tz)
            if moment is not None:
                yield moment


def _categories(value: object) -> Iterable[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        for cat in getattr(item, "cats", [item]):
            text = str(cat).strip()
            if text and text not in out:
                out.append(text)
    return out


def _text(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _occurrence_key(uid: str, original_start: datetime) -> str:
    return f"{uid}@{original_start.astimezone(UTC):%Y%m%dT%H%M%SZ}"
