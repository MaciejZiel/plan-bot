from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from plan_bot.diff import diff
from plan_bot.domain import GroupFilter
from plan_bot.formatting import (
    format_changes,
    format_day,
    format_next,
    format_reminder,
    format_week,
    humanize,
    lesson_line,
)
from plan_bot.ics import Window, expand
from plan_bot.timetable import (
    group_names,
    lessons_on,
    monday_of,
    next_class,
    starting_between,
    week_of,
)
from tests.conftest import WARSAW, fixture_bytes, warsaw

LESSONS = expand(
    fixture_bytes("sample.ics"), Window(warsaw(2026, 10, 1), warsaw(2027, 2, 1)), WARSAW
)
L1 = GroupFilter.parse("L1")


def test_lessons_on_with_filter() -> None:
    monday = lessons_on(LESSONS, date(2026, 10, 12), WARSAW, L1)
    assert [les.location for les in monday] == ["A-101", "Lab 204"]
    everything = lessons_on(LESSONS, date(2026, 10, 12), WARSAW, GroupFilter())
    assert len(everything) == 3


def test_next_class_before_during_and_after() -> None:
    before = next_class(LESSONS, warsaw(2026, 10, 12, 7, 0), L1)
    assert before.current is None
    assert before.upcoming is not None
    assert before.upcoming.location == "A-101"
    during = next_class(LESSONS, warsaw(2026, 10, 12, 9, 0), L1)
    assert during.current is not None
    assert during.current.location == "A-101"
    assert during.upcoming is not None
    assert during.upcoming.location == "Lab 204"
    after = next_class(LESSONS, warsaw(2027, 3, 1), L1)
    assert after == type(after)(None, None)


def test_next_class_skips_cancelled() -> None:
    c1 = GroupFilter.parse("C1")
    info = next_class(LESSONS, warsaw(2026, 11, 5, 15, 0), c1)
    assert info.upcoming is not None
    assert info.upcoming.start.date() != date(2026, 11, 5) or info.upcoming.start.hour != 16


def test_week_and_groups() -> None:
    week = week_of(LESSONS, monday_of(date(2026, 10, 14)), WARSAW, GroupFilter.parse("L2,C2"))
    assert next(iter(week)) == date(2026, 10, 12)
    assert len(week) == 7
    assert sum(len(v) for v in week.values()) == 8
    assert group_names(LESSONS) == ["C1", "C2", "EN-B2", "L1", "L2"]


def test_starting_between() -> None:
    found = starting_between(LESSONS, warsaw(2026, 10, 12, 8, 30), warsaw(2026, 10, 12, 10, 15), L1)
    assert [les.location for les in found] == ["Lab 204"]


def test_humanize() -> None:
    assert humanize(timedelta(minutes=5)) == "5 min"
    assert humanize(timedelta(hours=2)) == "2 h"
    assert humanize(timedelta(hours=1, minutes=25)) == "1 h 25 min"
    assert humanize(timedelta(days=2)) == "2 d"
    assert humanize(timedelta(days=2, hours=3)) == "2 d 3 h"
    assert humanize(timedelta(seconds=-5)) == "0 min"


def test_format_day_and_week() -> None:
    day = date(2026, 10, 12)
    text = format_day("Today", day, lessons_on(LESSONS, day, WARSAW, L1), WARSAW)
    assert text.splitlines()[0] == "Today · Monday, 12 Oct"
    assert "08:30–10:00  Algorithms and Data Structures (lecture)  (A-101)" in text
    assert "Lab 204 · L1" in text
    empty = format_day("Tomorrow", date(2026, 10, 11), [], WARSAW)
    assert "No classes" in empty
    week = format_week(week_of(LESSONS, day, WARSAW, L1), WARSAW)
    assert week.startswith("Week Mon 12 Oct – Sun 18 Oct:")
    quiet = format_week(week_of(LESSONS, date(2026, 12, 28), WARSAW, L1), WARSAW)
    assert "No classes this week." in quiet


def test_format_next_and_reminder() -> None:
    now = warsaw(2026, 10, 12, 9, 0)
    text = format_next(next_class(LESSONS, now, L1), now, WARSAW)
    assert "Now: Algorithms and Data Structures (lecture) in A-101, ends in 1 h." in text
    assert "Starts in 1 h 15 min." in text
    later = warsaw(2027, 3, 1)
    assert "No upcoming" in format_next(next_class(LESSONS, later, L1), later, WARSAW)
    lab = lessons_on(LESSONS, date(2026, 10, 12), WARSAW, L1)[1]
    reminder = format_reminder(lab, warsaw(2026, 10, 12, 10, 0), WARSAW)
    assert reminder.startswith("Reminder: Algorithms and Data Structures (lab) starts in 15 min")
    bare = replace(lab, location="", groups=(), cancelled=True)
    assert lesson_line(bare, WARSAW).endswith("[CANCELLED] Algorithms and Data Structures (lab)")
    assert "·" not in format_reminder(bare, warsaw(2026, 10, 12, 10, 0), WARSAW)


def test_format_changes() -> None:
    window = Window(warsaw(2026, 10, 1), warsaw(2027, 1, 1))
    before = expand(fixture_bytes("edits_before.ics"), window, WARSAW)
    after = expand(fixture_bytes("edits_after.ics"), window, WARSAW)
    changes = diff(before, after, since=warsaw(2026, 10, 12), until=warsaw(2026, 12, 1))
    lab = next(c for c in changes if c.lesson.uid == "net-lab@fixture.example")
    moved_day = replace(lab, new=replace(lab.lesson, start=warsaw(2026, 10, 21, 12)))
    lines = format_changes([*changes, moved_day], WARSAW).splitlines()
    assert lines == [
        "Timetable changed:",
        "- Thu 15 Oct 14:00 Statistics (exercises): moved to 16:00–17:30, room C-3 → C-4",
        "- Fri 16 Oct 12:00 Seminar: removed from the timetable",
        "- Mon 19 Oct 08:00 Computer Networks (lecture): room A-1 → Aula Magna",
        "- Tue 20 Oct 10:00 Computer Networks (lab): moved to 12:00–13:30",
        "- Thu 22 Oct 09:00 Extra make-up class: new class, 09:00–10:30 in B-2",
        "- Mon 26 Oct 08:00 Computer Networks (lecture): removed from the timetable",
        "- Tue 27 Oct 10:00 Computer Networks (lab): CANCELLED",
        "- Tue 20 Oct 10:00 Computer Networks (lab): moved to Wed 21 Oct 12:00–13:30",
    ]
    restored = diff(
        [replace(before[0], cancelled=True)],
        [replace(before[0], location="")],
        since=warsaw(2026, 10, 1),
        until=warsaw(2027, 1, 1),
    )
    assert "back on (no longer cancelled), room A-1 → ?" in format_changes(restored, WARSAW)
