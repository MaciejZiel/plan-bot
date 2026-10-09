from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from plan_bot.domain import Lesson
from plan_bot.ics import IcsError, Window, expand, parse_calendar
from tests.conftest import WARSAW, fixture_bytes, warsaw

WIDE = Window(warsaw(2026, 1, 1), warsaw(2028, 1, 1))


def by_uid(lessons: list[Lesson], uid: str) -> list[Lesson]:
    return [les for les in lessons if les.uid.startswith(uid)]


def test_sample_weekly_series_expands_and_skips_exdates() -> None:
    lessons = expand(fixture_bytes("sample.ics"), WIDE, WARSAW)
    os_lec = by_uid(lessons, "os-lec")
    dates = [les.start.date().isoformat() for les in os_lec]
    assert dates[0] == "2026-10-07"
    assert "2026-11-11" not in dates  # national holiday EXDATE
    assert "2026-12-23" not in dates
    assert "2026-12-30" not in dates
    assert all(les.start.hour == 9 and les.start.minute == 0 for les in os_lec)
    assert len(os_lec) == 17 - 3


def test_sample_interval_two() -> None:
    lessons = expand(fixture_bytes("sample.ics"), WIDE, WARSAW)
    eng = by_uid(lessons, "eng-b2")
    gaps = {(b.start - a.start).days for a, b in pairwise(eng)}
    assert gaps <= {14, 28}
    assert eng[0].groups == ("EN-B2",)


def test_override_changes_room_and_keeps_key() -> None:
    lessons = expand(fixture_bytes("sample.ics"), WIDE, WARSAW)
    db = {les.start.date().isoformat(): les for les in by_uid(lessons, "db-lec")}
    assert db["2026-10-20"].location == "Aula C"
    assert db["2026-10-27"].location == "Aula B"
    assert db["2026-10-20"].key == "db-lec@northbridge.example@20261020T100000Z"
    assert db["2026-10-20"].description.startswith("Lecturer")  # inherited from master


def test_cancelled_override_is_flagged() -> None:
    lessons = expand(fixture_bytes("sample.ics"), WIDE, WARSAW)
    dm = {les.start.date().isoformat(): les for les in by_uid(lessons, "dm-ex-c1")}
    assert dm["2026-11-05"].cancelled
    assert not dm["2026-11-12"].cancelled


def test_window_filters_and_sorts() -> None:
    window = Window(warsaw(2026, 10, 12), warsaw(2026, 10, 13))
    lessons = expand(fixture_bytes("sample.ics"), window, WARSAW)
    assert [les.start.hour for les in lessons] == [8, 10, 10]
    assert {les.location for les in lessons} == {"A-101", "Lab 204", "Lab 205"}
    single = expand(
        fixture_bytes("sample.ics"), Window(warsaw(2026, 10, 16), warsaw(2026, 10, 17)), WARSAW
    )
    assert "Project consultations" in [les.summary for les in single]


def test_autumn_dst_keeps_wall_clock_time() -> None:
    lessons = by_uid(expand(fixture_bytes("dst.ics"), WIDE, WARSAW), "monday-0800")
    assert [les.start.hour for les in lessons] == [8, 8, 8]
    utc_hours = [les.start.astimezone(UTC).hour for les in lessons]
    assert utc_hours == [6, 7, 7]  # CEST (+2) before 25 Oct, CET (+1) after
    assert all(les.duration == timedelta(minutes=90) for les in lessons)


def test_ambiguous_time_uses_first_occurrence() -> None:
    (lesson,) = by_uid(expand(fixture_bytes("dst.ics"), WIDE, WARSAW), "ambiguous")
    assert lesson.start.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_spring_forward_gap_is_shifted() -> None:
    lessons = by_uid(expand(fixture_bytes("dst.ics"), WIDE, WARSAW), "sunday-0230")
    starts = [les.start for les in lessons]
    assert [s.date().isoformat() for s in starts] == ["2027-03-21", "2027-03-28", "2027-04-04"]
    assert starts[0].hour == 2
    assert (starts[1].hour, starts[1].minute) == (3, 30)  # 02:30 does not exist that day
    assert starts[2].hour == 2
    assert starts[1].astimezone(UTC) == datetime(2027, 3, 28, 1, 30, tzinfo=UTC)


def test_utc_floating_allday_duration_rdate() -> None:
    lessons = expand(fixture_bytes("dst.ics"), WIDE, WARSAW)
    (utc,) = by_uid(lessons, "utc@")
    assert utc.start.astimezone(WARSAW).hour == 8
    (floating,) = by_uid(lessons, "floating")
    assert floating.start == warsaw(2026, 10, 27, 10)
    assert by_uid(lessons, "allday") == []
    (dur,) = by_uid(lessons, "duration")
    assert dur.duration == timedelta(minutes=45)
    daily = by_uid(lessons, "daily-until-date")
    assert [d.start.day for d in daily] == [30, 31, 1, 5]


def test_untitled_and_missing_end_defaults() -> None:
    data = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:x\nBEGIN:VEVENT\nUID:u1\n"
        "DTSTART:20261012T080000Z\nEND:VEVENT\n"
        "BEGIN:VEVENT\nSUMMARY:no uid\nDTSTART:20261012T080000Z\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )
    (lesson,) = expand(data, WIDE, WARSAW)
    assert lesson.summary == "(untitled)"
    assert lesson.duration == timedelta(minutes=90)


def test_orphan_override_and_override_moved_into_window() -> None:
    data = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:x\n"
        "BEGIN:VEVENT\nUID:orphan\nRECURRENCE-ID:20261012T080000Z\n"
        "DTSTART:20261012T090000Z\nDTEND:20261012T100000Z\nSUMMARY:Orphan\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:s\nDTSTART:20261001T080000Z\nDTEND:20261001T090000Z\n"
        "RRULE:FREQ=DAILY;COUNT=3\nSUMMARY:Series\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:s\nRECURRENCE-ID:20261003T080000Z\n"
        "DTSTART:20261020T080000Z\nDTEND:20261020T090000Z\nSUMMARY:Series moved\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )
    window = Window(datetime(2026, 10, 10, tzinfo=UTC), datetime(2026, 10, 30, tzinfo=UTC))
    lessons = expand(data, window, WARSAW)
    assert [les.summary for les in lessons] == ["Orphan", "Series moved"]
    assert lessons[0].key == "orphan@20261012T080000Z"
    assert lessons[1].key == "s@20261003T080000Z"


def test_bad_rrule_is_ignored() -> None:
    data = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:x\nBEGIN:VEVENT\nUID:b\n"
        "DTSTART:20261012T080000Z\nRRULE:FREQ=WEEKLY;BYDAY=XX\nSUMMARY:Bad\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )
    lessons = expand(data, WIDE, WARSAW)
    assert [les.summary for les in lessons] == ["Bad"]  # DTSTART itself still counts


def test_infinite_rule_is_capped_by_window() -> None:
    data = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:x\nBEGIN:VEVENT\nUID:inf\n"
        "DTSTART:20261012T080000Z\nRRULE:FREQ=MINUTELY\nSUMMARY:Spam\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )
    lessons = expand(data, WIDE, WARSAW)
    assert len(lessons) <= 2001


@pytest.mark.parametrize("payload", [b"not a calendar", b"BEGIN:VEVENT\nEND:VEVENT\n", b""])
def test_invalid_documents(payload: bytes) -> None:
    with pytest.raises(IcsError):
        parse_calendar(payload)


def test_window_contains_is_half_open() -> None:
    w = Window(warsaw(2026, 1, 1), warsaw(2026, 1, 2))
    assert w.contains(warsaw(2026, 1, 1))
    assert not w.contains(warsaw(2026, 1, 2))


def test_duplicate_uids_get_unique_keys() -> None:
    data = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:x\n"
        "BEGIN:VEVENT\nUID:dup\nDTSTART:20261012T080000Z\nSUMMARY:A\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:dup\nDTSTART:20261013T080000Z\nSUMMARY:B\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )
    assert [les.key for les in expand(data, WIDE, WARSAW)] == ["dup", "dup#1"]
