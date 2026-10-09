from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from plan_bot.db import create_engine, migrate, session_factory
from plan_bot.repository import Repository

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


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'plan-bot.db'}"


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    await migrate(db_url)
    eng = create_engine(db_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def repo(engine: AsyncEngine) -> Repository:
    return Repository(session_factory(engine))
