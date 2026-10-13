"""Recurrence edge cases: RDATE-only series, DURATION across DST, overrides, UNTIL dates."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from plan_bot.domain import Lesson
from plan_bot.ics import DEFAULT_DURATION, IcsError, Window, expand
from tests.conftest import WARSAW, fixture_bytes, warsaw

LESSONS = expand(
    fixture_bytes("rrule_edges.ics"), Window(warsaw(2026, 1, 1), warsaw(2028, 1, 1)), WARSAW
)


def series(uid: str) -> list[Lesson]:
    return [les for les in LESSONS if les.uid.startswith(uid)]


def test_all_day_series_and_orphans_are_skipped() -> None:
    assert series("allday-series") == []
    assert series("orphan-allday") == []


def test_rdate_only_series() -> None:
    starts = [(les.start.day, les.start.hour) for les in series("rdate-only")]
    assert starts == [(3, 10), (10, 10), (17, 12)]
    assert all(les.duration == timedelta(minutes=90) for les in series("rdate-only"))


def test_duration_series_across_spring_dst_with_utc_exdate() -> None:
    lessons = series("duration-series")
    # 29 Mar is excluded by an EXDATE written in UTC (15:30Z == 17:30 CEST).
    assert [les.start.date().isoformat() for les in lessons] == ["2027-03-22", "2027-04-05"]
    first, moved = lessons
    assert first.start.astimezone(UTC).hour == 16  # CET
    assert first.duration == timedelta(minutes=90)
    assert (moved.start.hour, moved.start.minute) == (18, 0)
    assert moved.location == "Moved room"
    assert moved.duration == timedelta(minutes=90)  # inherited from the master's DURATION
    assert moved.key == "duration-series@fixture.example@20270405T153000Z"


def test_override_with_own_duration() -> None:
    first, second = series("override-duration")
    assert first.duration == timedelta(minutes=90)
    assert second.start == warsaw(2026, 11, 11, 9)
    assert second.duration == timedelta(minutes=45)


def test_until_date_is_inclusive_and_keeps_wall_clock() -> None:
    lessons = series("until-date")
    assert [les.start.day for les in lessons] == [19, 26, 2]
    assert {les.start.hour for les in lessons} == {14}
    assert [les.start.utcoffset() for les in lessons] == [
        timedelta(hours=2),
        timedelta(hours=1),
        timedelta(hours=1),
    ]


def test_end_before_start_uses_default_length() -> None:
    (lesson,) = series("backwards")
    assert lesson.duration == DEFAULT_DURATION


def test_window_edges_in_other_timezones() -> None:
    window = Window(
        datetime(2026, 11, 10, 8, 59, tzinfo=UTC), datetime(2026, 11, 10, 9, 1, tzinfo=UTC)
    )
    (lesson,) = expand(fixture_bytes("rrule_edges.ics"), window, WARSAW)
    assert lesson.start == warsaw(2026, 11, 10, 10)


def _calendar(rule: str, start: str, events: int = 1) -> bytes:
    body = "".join(
        f"BEGIN:VEVENT\r\nUID:hostile-{i}\r\nDTSTART;TZID=Europe/Warsaw:{start}\r\n"
        f"DURATION:PT1H\r\nRRULE:{rule}\r\nSUMMARY:x\r\nEND:VEVENT\r\n"
        for i in range(events)
    )
    return (
        f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\n{body}END:VCALENDAR\r\n".encode()
    )


HOSTILE_WINDOW = Window(warsaw(2026, 10, 5), warsaw(2027, 3, 1))


@pytest.mark.parametrize("freq", ["HOURLY", "MINUTELY", "SECONDLY"])
def test_sub_daily_rules_are_ignored(freq: str) -> None:
    # FREQ=MINUTELY since 2000 used to block the event loop for tens of seconds.
    lessons = expand(_calendar(f"FREQ={freq}", "20000103T080000"), HOSTILE_WINDOW, WARSAW)
    assert lessons == []


def test_rule_steps_before_the_window_are_bounded() -> None:
    minutes = ",".join(str(m) for m in range(60))
    hours = ",".join(str(h) for h in range(24))
    rule = f"FREQ=DAILY;BYHOUR={hours};BYMINUTE={minutes}"
    started = time.monotonic()
    assert expand(_calendar(rule, "20000103T080000"), HOSTILE_WINDOW, WARSAW) == []
    assert time.monotonic() - started < 5


def test_long_running_daily_series_still_expands() -> None:
    lessons = expand(_calendar("FREQ=DAILY", "19900101T080000"), HOSTILE_WINDOW, WARSAW)
    assert len(lessons) == (HOSTILE_WINDOW.end - HOSTILE_WINDOW.start).days


def test_too_many_lessons_are_refused() -> None:
    with pytest.raises(IcsError, match="more than"):
        expand(_calendar("FREQ=DAILY", "20261005T080000", events=200), HOSTILE_WINDOW, WARSAW)


def test_expansion_has_a_time_budget() -> None:
    # Impossible rules make dateutil scan up to the year 9999 without yielding.
    data = _calendar("FREQ=DAILY;BYMONTH=2;BYMONTHDAY=31", "20260105T080000", events=5)
    with pytest.raises(IcsError, match="too complex"):
        expand(data, HOSTILE_WINDOW, WARSAW, seconds=0.5)
