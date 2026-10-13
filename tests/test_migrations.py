from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command

from plan_bot.db import alembic_config


def _counts(path: Path) -> list[int]:
    with closing(sqlite3.connect(path)) as con:
        return [
            con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("subscriptions", "lessons", "sent_reminders")
        ]


def _columns(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as con:
        return {row[1] for row in con.execute("PRAGMA table_info(subscriptions)")}


def _seed(path: Path) -> None:
    with closing(sqlite3.connect(path)) as con:
        con.execute(
            "INSERT INTO subscriptions (id, platform, chat_id, group_filter, reminder_minutes,"
            " notify_changes, weekly_summary, error_count, created_at)"
            " VALUES (1, 'telegram', '1', '', 15, 1, 1, 0, '2026-10-01 00:00:00')"
        )
        con.execute(
            "INSERT INTO lessons (subscription_id, key, uid, start, end, summary, location,"
            " description, groups, cancelled) VALUES"
            " (1, 'k', 'u', '2026-10-12 08:00:00', '2026-10-12 09:30:00', 'Algebra', '', '', '', 0)"
        )
        con.execute(
            "INSERT INTO sent_reminders (subscription_id, key, start) VALUES"
            " (1, 'k', '2026-10-12 08:00:00')"
        )
        con.commit()


@pytest.mark.parametrize(
    ("revision", "target", "dropped"),
    [
        ("0003", "0002", "parser_version"),
        ("0002", "0001", "language"),
    ],
)
def test_downgrade_keeps_lessons_and_reminders(
    tmp_path: Path, revision: str, target: str, dropped: str
) -> None:
    path = tmp_path / "old.db"
    cfg = alembic_config(f"sqlite+aiosqlite:///{path}")
    command.upgrade(cfg, revision)
    assert dropped in _columns(path)
    _seed(path)
    assert _counts(path) == [1, 1, 1]

    command.downgrade(cfg, target)

    assert dropped not in _columns(path)
    assert _counts(path) == [1, 1, 1]
    command.upgrade(cfg, "head")
    assert _counts(path) == [1, 1, 1]
