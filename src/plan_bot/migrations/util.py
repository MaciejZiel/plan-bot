"""Helpers shared by migration scripts."""

from __future__ import annotations

from alembic import op


def drop_column(table: str, column: str) -> None:
    """Drop a column without touching the rows of other tables.

    SQLite cannot drop a column in place, so Alembic's batch mode copies the table and
    drops the original. The connection has ``PRAGMA foreign_keys=ON``, so dropping the
    original ``subscriptions`` table cascades and empties ``lessons`` and
    ``sent_reminders``. A plain ``ALTER TABLE ... DROP COLUMN`` (SQLite 3.35+) edits the
    table in place and keeps everything.
    """
    if op.get_bind().dialect.name == "sqlite":
        op.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
    else:
        op.drop_column(table, column)
