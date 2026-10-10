"""Recurrence edge cases: RDATE-only series, DURATION across DST, overrides, UNTIL dates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from plan_bot.domain import Lesson
from plan_bot.ics import DEFAULT_DURATION, Window, expand
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
