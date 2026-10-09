"""Platform-independent domain types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class Lesson:
    """A single, concrete occurrence of a class taken from a timetable.

    ``key`` identifies the occurrence across feed refreshes: it is the event UID
    for one-off events and ``UID@<original start in UTC>`` for occurrences of a
    recurring series, so a moved or re-roomed occurrence keeps its identity.
    ``start``/``end`` are timezone-aware.
    """

    key: str
    uid: str
    start: datetime
    end: datetime
    summary: str
    location: str = ""
    description: str = ""
    groups: tuple[str, ...] = ()
    cancelled: bool = False

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Lesson start/end must be timezone-aware")

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def matches(self, group_filter: GroupFilter) -> bool:
        return group_filter.matches(self)


_SPLIT = re.compile(r"[,;\s]+")


@dataclass(frozen=True, slots=True)
class GroupFilter:
    """Case-insensitive filter on groups.

    A lesson matches when it has no group information at all (e.g. a lecture for
    everyone), when one of its ``groups`` (ICS ``CATEGORIES``) equals a filter
    token, or when a token appears as a whole word in the summary/description.
    An empty filter matches everything.
    """

    tokens: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def parse(cls, raw: str | None) -> GroupFilter:
        if not raw:
            return cls()
        return cls(frozenset(t.casefold() for t in _SPLIT.split(raw) if t))

    @staticmethod
    def clean(raw: str) -> str:
        """Normalise user input to ``A,B`` keeping the original spelling."""
        seen: dict[str, str] = {}
        for token in _SPLIT.split(raw):
            if token:
                seen.setdefault(token.casefold(), token)
        return ",".join(seen.values())

    def serialize(self) -> str:
        return ",".join(sorted(self.tokens))

    def __bool__(self) -> bool:
        return bool(self.tokens)

    def matches(self, lesson: Lesson) -> bool:
        if not self.tokens:
            return True
        groups = {g.casefold() for g in lesson.groups}
        if groups & self.tokens:
            return True
        text = f"{lesson.summary} {lesson.description}".casefold()
        words = set(re.findall(r"[\w-]+", text))
        if words & self.tokens:
            return True
        # Lessons without any group information are shared by everyone.
        return not lesson.groups
