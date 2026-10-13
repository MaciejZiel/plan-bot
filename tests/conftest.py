from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from plan_bot.config import Settings
from plan_bot.db import create_engine, migrate, session_factory
from plan_bot.fetch import FetchError
from plan_bot.repository import ChatRef, Repository
from plan_bot.service import BotService
from plan_bot.views import View

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


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeFeeds:
    """In-memory replacement for :class:`plan_bot.fetch.Fetcher`."""

    def __init__(self, **payloads: bytes | Exception) -> None:
        self.payloads: dict[str, bytes | Exception] = dict(payloads)
        self.calls: list[str] = []

    async def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        if url == "demo":
            return fixture_bytes("sample.ics")
        payload = self.payloads.get(url)
        if payload is None:
            raise FetchError("fetch.http", status=404)
        if isinstance(payload, Exception):
            raise payload
        return payload


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[ChatRef, str]] = []
        self.views: list[View | None] = []
        self.fail = False

    async def send(self, chat: ChatRef, text: str, view: View | None = None) -> None:
        if self.fail:
            raise RuntimeError("platform down")
        self.sent.append((chat, text))
        self.views.append(view)

    def texts(self) -> list[str]:
        return [text for _, text in self.sent]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(warsaw(2026, 10, 12, 7, 0))


@pytest.fixture
def feeds() -> FakeFeeds:
    return FakeFeeds()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def settings(db_url: str) -> Settings:
    return Settings(database_url=db_url, timezone=WARSAW)


@pytest.fixture
def service(
    repo: Repository,
    feeds: FakeFeeds,
    settings: Settings,
    clock: FakeClock,
    notifier: RecordingNotifier,
) -> BotService:
    return BotService(repo, feeds, settings, clock=clock, notifier=notifier)
