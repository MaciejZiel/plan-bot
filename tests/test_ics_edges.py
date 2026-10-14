"""Recurrence edge cases: RDATE-only series, DURATION across DST, overrides, UNTIL dates."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from plan_bot.domain import Lesson
from plan_bot.ics import DEFAULT_DURATION, FeedTooComplex, Window, expand
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


def _calendar_body(body: str) -> bytes:
    return (
        f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\n{body}END:VCALENDAR\r\n".encode()
    )


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
    with pytest.raises(FeedTooComplex, match="more than"):
        expand(_calendar("FREQ=DAILY", "20261005T080000", events=200), HOSTILE_WINDOW, WARSAW)


def test_expansion_has_a_time_budget() -> None:
    # Impossible rules make dateutil scan up to the year 9999 without yielding.
    data = _calendar("FREQ=DAILY;BYYEARDAY=366;BYMONTH=2", "20260105T080000", events=5)
    with pytest.raises(FeedTooComplex, match="too complex"):
        expand(data, HOSTILE_WINDOW, WARSAW, seconds=0.1)


# ------------------------------------------------------- the PJATK (Gakko) file export
# It labels real UTC instants with Z and does the summer/winter shift itself.

WALLCLOCK = expand(
    fixture_bytes("gakko_export.ics"), Window(warsaw(2026, 1, 1), warsaw(2028, 1, 1)), WARSAW
)


def test_z_times_are_utc_and_shown_in_warsaw_time() -> None:
    before, after, _ = WALLCLOCK
    # 10:00Z is 12:00 in summer time (22 Oct) and 11:00Z is 12:00 in winter time (27 Oct).
    assert before.start == datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    assert after.start == datetime(2026, 10, 27, 11, 0, tzinfo=UTC)
    for lesson, offset in ((before, 2), (after, 1)):
        local = lesson.start.astimezone(WARSAW)
        assert (local.hour, local.utcoffset()) == (12, timedelta(hours=offset))


def _one_event(start: str, end: str, prodid: str = "-//PJWSTK PLAN//EN") -> bytes:
    return (
        f"BEGIN:VCALENDAR\nPRODID:{prodid}\nBEGIN:VEVENT\nUID:z\nDTSTART:{start}\n"
        f"DTEND:{end}\nSUMMARY:Class\nEND:VEVENT\nEND:VCALENDAR\n"
    ).encode()


WIDE_WINDOW = Window(warsaw(2026, 1, 1), warsaw(2028, 1, 1))


def local_days_hours(lessons: list[Lesson]) -> list[tuple[int, int]]:
    return [
        (les.start.astimezone(WARSAW).day, les.start.astimezone(WARSAW).hour) for les in lessons
    ]


def hm(lesson: Lesson) -> tuple[int, int, int]:
    """Local start hour, end hour and end minute."""
    start, end = lesson.start.astimezone(WARSAW), lesson.end.astimezone(WARSAW)
    return start.hour, end.hour, end.minute


@pytest.mark.parametrize("prodid", ["-//PJWSTK PLAN//EN", "SOMEONE ELSE"])
def test_a_noon_utc_class_is_14_in_summer_and_13_in_winter(prodid: str) -> None:
    (summer,) = expand(
        _one_event("20260928T120000Z", "20260928T133000Z", prodid), WIDE_WINDOW, WARSAW
    )
    (winter,) = expand(
        _one_event("20261102T120000Z", "20261102T133000Z", prodid), WIDE_WINDOW, WARSAW
    )
    assert hm(summer) == (14, 15, 30)
    assert hm(winter) == (13, 14, 30)


def test_a_utc_series_keeps_its_utc_time_across_the_october_change() -> None:
    # Without TZID an RRULE repeats at the same UTC time: 14:00 before the change, 13:00 after.
    data = (
        b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:s\nDTSTART:20261019T120000Z\n"
        b"DTEND:20261019T133000Z\nRRULE:FREQ=WEEKLY;COUNT=3\nSUMMARY:Class\n"
        b"END:VEVENT\nEND:VCALENDAR\n"
    )
    lessons = expand(data, WIDE_WINDOW, WARSAW)
    assert local_days_hours(lessons) == [(19, 14), (26, 13), (2, 13)]
    assert all(les.duration == timedelta(minutes=90) for les in lessons)


def test_a_tzid_series_keeps_its_local_time_across_the_october_change() -> None:
    data = (
        b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:s\nDTSTART;TZID=Europe/Warsaw:20261019T140000\n"
        b"DTEND;TZID=Europe/Warsaw:20261019T153000\nRRULE:FREQ=WEEKLY;COUNT=3\nSUMMARY:Class\n"
        b"END:VEVENT\nEND:VCALENDAR\n"
    )
    lessons = expand(data, WIDE_WINDOW, WARSAW)
    assert local_days_hours(lessons) == [(19, 14), (26, 14), (2, 14)]


def test_a_trailing_room_moves_from_the_title_to_the_location() -> None:
    first, second, third = WALLCLOCK
    assert (first.summary, first.location) == ("Imaginary Algebra lecture", "W21")
    assert (second.summary, second.location) == ("Imaginary Algebra exercises", "B/03")
    # An explicit LOCATION wins and the title is left alone.
    assert (third.summary, third.location) == ("Fictional Physics s. B212", "Aula Magna")


@pytest.mark.parametrize("title", ["Seminar", "Class s. 5 and more", "Physics s.", "s. W21"])
def test_titles_without_a_trailing_room_are_untouched(title: str) -> None:
    data = (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:t\nDTSTART:20261022T101500\n"
        f"SUMMARY:{title}\nEND:VEVENT\nEND:VCALENDAR\n"
    ).encode()
    (lesson,) = expand(data, Window(warsaw(2026, 1, 1), warsaw(2028, 1, 1)), WARSAW)
    assert (lesson.summary, lesson.location) == (title, "")


def test_a_rule_for_a_day_that_does_not_exist_is_skipped_at_once() -> None:
    # 30 February used to walk to the year 9999 (about 2.5 s per series).
    data = _calendar("FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30", "00010101T080000", events=200)
    started = time.monotonic()
    assert expand(data, HOSTILE_WINDOW, WARSAW) == []
    assert time.monotonic() - started < 2


def test_rules_that_can_match_are_not_mistaken_for_impossible_ones() -> None:
    leap = expand(
        _calendar("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29", "20240229T080000"),
        Window(warsaw(2027, 1, 1), warsaw(2029, 1, 1)),
        WARSAW,
    )
    assert [(les.start.year, les.start.day) for les in leap] == [(2028, 29)]
    last = expand(
        _calendar("FREQ=MONTHLY;BYMONTHDAY=-1;BYMONTH=2", "20260228T080000"),
        Window(warsaw(2026, 1, 1), warsaw(2027, 12, 31)),
        WARSAW,
    )
    assert len(last) == 2


def test_count_is_still_honoured_without_until() -> None:
    lessons = expand(_calendar("FREQ=WEEKLY;COUNT=3", "20261005T080000"), HOSTILE_WINDOW, WARSAW)
    assert len(lessons) == 3


def test_an_open_rule_never_runs_past_the_window() -> None:
    lessons = expand(_calendar("FREQ=WEEKLY", "20261005T080000"), HOSTILE_WINDOW, WARSAW)
    assert max(les.start for les in lessons) < HOSTILE_WINDOW.end


def _dates(prop: str, count: int) -> str:
    base = datetime(2026, 1, 1, 8, tzinfo=UTC)
    return "".join(f"{prop}:{(base + timedelta(days=i)):%Y%m%dT%H%M%SZ}\r\n" for i in range(count))


@pytest.mark.parametrize("prop", ["RDATE", "EXDATE"])
def test_too_many_rdates_or_exdates_in_one_event_are_refused(prop: str) -> None:
    body = (
        "BEGIN:VEVENT\r\nUID:big\r\nDTSTART:20261005T080000Z\r\nRRULE:FREQ=WEEKLY\r\n"
        + _dates(prop, 2001)
        + "END:VEVENT\r\n"
    )
    with pytest.raises(FeedTooComplex, match=prop):
        expand(_calendar_body(body), HOSTILE_WINDOW, WARSAW)


def test_the_lesson_limit_trips_inside_one_big_series(monkeypatch: pytest.MonkeyPatch) -> None:
    from plan_bot import ics

    monkeypatch.setattr(ics, "MAX_LESSONS", 5)
    produced = 0
    real = ics._lesson_from

    def counting(*args: object, **kwargs: object) -> object:
        nonlocal produced
        produced += 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ics, "_lesson_from", counting)
    with pytest.raises(FeedTooComplex, match="more than"):
        expand(_calendar("FREQ=DAILY", "20261005T080000"), HOSTILE_WINDOW, WARSAW)
    assert produced <= 6  # stopped at once, not after all 147 days


def test_loops_over_feed_contents_watch_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    # Many single events, each cheap: only a check inside that loop can stop the feed.
    from plan_bot import ics

    now = [0.0]

    def slow_clock() -> float:
        now[0] += 0.1
        return now[0]

    monkeypatch.setattr(ics.clock, "monotonic", slow_clock)
    events = "".join(
        f"BEGIN:VEVENT\r\nUID:s{i}\r\nDTSTART:2026110{1 + i % 9}T080000Z\r\nEND:VEVENT\r\n"
        for i in range(5000)
    )
    with pytest.raises(FeedTooComplex, match="too complex"):
        expand(_calendar_body(events), HOSTILE_WINDOW, WARSAW, seconds=1.0)
    assert now[0] < 3  # stopped after about ten clock reads, not after 5000 events
