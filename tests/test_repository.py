from __future__ import annotations

from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from plan_bot.db import Base, UTCDateTime, alembic_config, migrate
from plan_bot.ics import Window, expand
from plan_bot.repository import ChatRef, Repository
from tests.conftest import WARSAW, fixture_bytes, warsaw

CHAT = ChatRef("telegram", "42")
NOW = datetime(2026, 10, 12, 6, tzinfo=UTC)


async def test_migrations_match_models(engine: AsyncEngine) -> None:
    def compare(conn: Connection) -> list[object]:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return list(compare_metadata(ctx, Base.metadata))

    async with engine.connect() as conn:
        assert await conn.run_sync(compare) == []


async def test_migrate_is_idempotent(db_url: str, engine: AsyncEngine) -> None:
    await migrate(db_url)
    assert alembic_config("sqlite:///100%").get_main_option("sqlalchemy.url") == "sqlite:///100%"


async def test_subscription_lifecycle(repo: Repository) -> None:
    assert await repo.get(CHAT) is None
    sub = await repo.get_or_create(CHAT)
    again = await repo.get_or_create(CHAT)
    assert sub.id == again.id
    assert sub.reminder_minutes == 15
    assert sub.created_at.tzinfo is not None
    updated = await repo.update(CHAT, ics_url="https://example.org/a.ics", group_filter="l1")
    assert updated.ics_url == "https://example.org/a.ics"
    with pytest.raises(AttributeError):
        await repo.update(CHAT, nonsense=1)
    assert [s.id for s in await repo.subscriptions_with_feed()] == [sub.id]
    created = await repo.update(ChatRef("discord", "7"), reminder_minutes=5)
    assert created.reminder_minutes == 5
    assert await repo.delete(CHAT)
    assert not await repo.delete(CHAT)
    assert str(CHAT) == "telegram:42"


async def test_lessons_roundtrip_and_cascade(repo: Repository) -> None:
    sub = await repo.get_or_create(CHAT)
    lessons = expand(
        fixture_bytes("sample.ics"), Window(warsaw(2026, 10, 12), warsaw(2026, 10, 19)), WARSAW
    )
    end = warsaw(2026, 10, 19)
    await repo.replace_lessons(sub.id, lessons, refreshed_at=NOW, window_end=end)
    loaded = await repo.lessons(sub.id)
    assert [les.key for les in loaded] == [les.key for les in lessons]
    assert loaded[1].groups == lessons[1].groups
    assert loaded[0].start == lessons[0].start
    assert loaded[0].start.tzinfo is UTC
    refreshed = await repo.get(CHAT)
    assert refreshed is not None
    assert refreshed.window_end == end
    await repo.replace_lessons(sub.id, lessons[:2], refreshed_at=NOW, window_end=end)
    assert len(await repo.lessons(sub.id)) == 2
    await repo.delete(CHAT)
    assert await repo.lessons(sub.id) == []


async def test_errors_and_reminders(repo: Repository) -> None:
    sub = await repo.get_or_create(CHAT)
    assert await repo.record_error(sub.id, "boom" * 500, NOW) == 1
    assert await repo.record_error(sub.id, "boom", NOW) == 2
    stored = await repo.get(CHAT)
    assert stored is not None
    assert stored.last_error == "boom"
    assert await repo.record_error(9999, "x", NOW) == 0
    assert await repo.mark_reminded(sub.id, "k", NOW)
    assert not await repo.mark_reminded(sub.id, "k", NOW)
    assert await repo.prune_reminders(datetime(2027, 1, 1, tzinfo=UTC)) == 1
    assert await repo.mark_reminded(sub.id, "k", NOW)


def test_utc_type_rejects_naive_values() -> None:
    col = UTCDateTime()
    with pytest.raises(ValueError, match="naive"):
        col.process_bind_param(datetime(2026, 1, 1), None)  # type: ignore[arg-type]
    assert col.process_bind_param(None, None) is None  # type: ignore[arg-type]
    assert col.process_result_value(None, None) is None  # type: ignore[arg-type]
    aware = datetime(2026, 1, 1, 12, tzinfo=WARSAW)
    assert col.process_result_value(aware, None) == aware  # type: ignore[arg-type]
