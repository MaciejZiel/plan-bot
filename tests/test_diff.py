from __future__ import annotations

from dataclasses import replace

from plan_bot.diff import ChangeKind, diff
from plan_bot.domain import Lesson
from plan_bot.ics import Window, expand
from tests.conftest import WARSAW, fixture_bytes, warsaw

WINDOW = Window(warsaw(2026, 10, 1), warsaw(2027, 1, 1))


def snapshots() -> tuple[list[Lesson], list[Lesson]]:
    return (
        expand(fixture_bytes("edits_before.ics"), WINDOW, WARSAW),
        expand(fixture_bytes("edits_after.ics"), WINDOW, WARSAW),
    )


def test_detects_all_edits() -> None:
    before, after = snapshots()
    changes = diff(before, after, since=warsaw(2026, 10, 12), until=warsaw(2026, 12, 1))
    summary = [(c.lesson.summary, c.sort_key.astimezone(WARSAW).day, set(c.kinds)) for c in changes]
    assert summary == [
        ("Statistics (exercises)", 15, {ChangeKind.RESCHEDULED, ChangeKind.ROOM}),
        ("Seminar", 16, {ChangeKind.REMOVED}),
        ("Computer Networks (lecture)", 19, {ChangeKind.ROOM}),
        ("Computer Networks (lab)", 20, {ChangeKind.RESCHEDULED}),
        ("Extra make-up class", 22, {ChangeKind.ADDED}),
        ("Computer Networks (lecture)", 26, {ChangeKind.REMOVED}),
        ("Computer Networks (lab)", 27, {ChangeKind.CANCELLED}),
    ]
    lab = changes[3]
    assert lab.old is not None
    assert lab.new is not None
    assert (lab.old.start.hour, lab.new.start.hour) == (10, 12)


def test_past_changes_are_ignored() -> None:
    before, after = snapshots()
    changes = diff(before, after, since=warsaw(2026, 10, 21), until=warsaw(2026, 12, 1))
    assert [c.sort_key.astimezone(WARSAW).day for c in changes] == [22, 26, 27]


def test_identical_snapshots_have_no_changes() -> None:
    before, _ = snapshots()
    assert diff(before, before, since=warsaw(2026, 10, 1), until=warsaw(2027, 1, 1)) == []


def test_restored_and_already_cancelled() -> None:
    before, _ = snapshots()
    first = before[0]
    cancelled = replace(first, cancelled=True)
    restored = diff([cancelled], [first], since=warsaw(2026, 10, 1), until=warsaw(2027, 1, 1))
    assert restored[0].kinds == {ChangeKind.RESTORED}
    # still cancelled, but the room changed: not interesting
    moved = replace(cancelled, location="elsewhere")
    assert diff([cancelled], [moved], since=warsaw(2026, 10, 1), until=warsaw(2027, 1, 1)) == []
    # removing or adding an already-cancelled lesson is not news either
    assert diff([cancelled], [], since=warsaw(2026, 10, 1), until=warsaw(2027, 1, 1)) == []
    assert diff([], [cancelled], since=warsaw(2026, 10, 1), until=warsaw(2027, 1, 1)) == []


def test_twin_without_real_change_is_silent() -> None:
    before, _ = snapshots()
    first = before[0]
    twin = replace(first, key="other-key", uid="other")
    assert diff([first], [twin], since=warsaw(2026, 10, 1), until=warsaw(2027, 1, 1)) == []
