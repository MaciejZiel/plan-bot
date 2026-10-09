"""Detect meaningful changes between two snapshots of a timetable."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from plan_bot.domain import Lesson


class ChangeKind(StrEnum):
    ADDED = "added"
    CANCELLED = "cancelled"
    REMOVED = "removed"
    RESCHEDULED = "rescheduled"
    ROOM = "room"
    RESTORED = "restored"


@dataclass(frozen=True, slots=True)
class Change:
    kinds: frozenset[ChangeKind]
    old: Lesson | None
    new: Lesson | None

    @property
    def lesson(self) -> Lesson:
        """The most relevant version of the lesson (new if it exists)."""
        lesson = self.new or self.old
        assert lesson is not None
        return lesson

    @property
    def sort_key(self) -> datetime:
        starts = [les.start for les in (self.old, self.new) if les is not None]
        return min(starts)


def diff(
    old: Iterable[Lesson],
    new: Iterable[Lesson],
    *,
    since: datetime,
    until: datetime,
) -> list[Change]:
    """Compare snapshots, reporting changes that touch ``[since, until)``.

    Lessons are matched by :attr:`Lesson.key`. Some timetable exporters assign a
    fresh UID on every export; unmatched removed/added pairs with the same title
    on the same local day are therefore treated as one rescheduled lesson.
    """

    def relevant(lesson: Lesson) -> bool:
        return since <= lesson.start < until

    old_by_key = {les.key: les for les in old}
    new_by_key = {les.key: les for les in new}
    changes: list[Change] = []

    for key, before in old_by_key.items():
        after = new_by_key.get(key)
        if after is None:
            continue
        if not (relevant(before) or relevant(after)):
            continue
        kinds = _compare(before, after)
        if kinds:
            changes.append(Change(frozenset(kinds), before, after))

    removed = [les for k, les in old_by_key.items() if k not in new_by_key and relevant(les)]
    added = [les for k, les in new_by_key.items() if k not in old_by_key and relevant(les)]

    for before in list(removed):
        match = _find_twin(before, added)
        if match is None:
            continue
        removed.remove(before)
        added.remove(match)
        kinds = _compare(before, match)
        if kinds:
            changes.append(Change(frozenset(kinds), before, match))

    changes.extend(
        Change(frozenset({ChangeKind.REMOVED}), les, None) for les in removed if not les.cancelled
    )
    changes.extend(
        Change(frozenset({ChangeKind.ADDED}), None, les) for les in added if not les.cancelled
    )
    changes.sort(key=lambda c: (c.sort_key, c.lesson.summary))
    return changes


def _compare(before: Lesson, after: Lesson) -> set[ChangeKind]:
    kinds: set[ChangeKind] = set()
    if after.cancelled and not before.cancelled:
        return {ChangeKind.CANCELLED}
    if before.cancelled and not after.cancelled:
        kinds.add(ChangeKind.RESTORED)
    if after.cancelled:
        return kinds
    if before.start != after.start or before.end != after.end:
        kinds.add(ChangeKind.RESCHEDULED)
    if before.location != after.location:
        kinds.add(ChangeKind.ROOM)
    return kinds


def _find_twin(lesson: Lesson, candidates: list[Lesson]) -> Lesson | None:
    tz = lesson.start.tzinfo
    day = lesson.start.date()
    for other in candidates:
        if other.summary == lesson.summary and other.start.astimezone(tz).date() == day:
            return other
    return None
