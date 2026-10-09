from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = Path(__file__).parents[1] / "src" / "plan_bot" / "data" / "sample.ics"
WARSAW = ZoneInfo("Europe/Warsaw")


def warsaw(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=WARSAW)


def fixture_bytes(name: str) -> bytes:
    if name == "sample.ics":
        return SAMPLE.read_bytes()
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def sample_ics() -> bytes:
    return SAMPLE.read_bytes()
