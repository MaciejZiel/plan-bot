from __future__ import annotations

from datetime import datetime

import pytest

from plan_bot.domain import GroupFilter, Lesson
from tests.conftest import warsaw


def lesson(**kw: object) -> Lesson:
    base: dict[str, object] = {
        "key": "k",
        "uid": "u",
        "start": warsaw(2026, 10, 12, 8),
        "end": warsaw(2026, 10, 12, 9),
        "summary": "Algorithms (lab) group L1",
        "groups": ("L1",),
    }
    base.update(kw)
    return Lesson(**base)  # type: ignore[arg-type]


def test_lesson_requires_aware_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        lesson(start=datetime(2026, 1, 1))


def test_group_filter_parse_and_serialize() -> None:
    f = GroupFilter.parse(" L1, c2;;W3 ")
    assert f.tokens == {"l1", "c2", "w3"}
    assert f.serialize() == "c2,l1,w3"
    assert not GroupFilter.parse(None)
    assert not GroupFilter.parse("")


def test_group_filter_matching() -> None:
    assert lesson().matches(GroupFilter())
    assert lesson().matches(GroupFilter.parse("l1"))
    assert not lesson().matches(GroupFilter.parse("l2"))
    assert lesson(groups=("X",)).matches(GroupFilter.parse("group"))  # word in summary
    assert lesson(groups=()).matches(GroupFilter.parse("l2"))  # shared lecture
    assert lesson().duration.total_seconds() == 3600
