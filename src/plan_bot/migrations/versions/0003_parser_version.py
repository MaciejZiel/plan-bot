"""Remember which parser version produced each stored snapshot.

Existing subscriptions get 0, so their next refresh is treated as a silent re-import
(no change alert) when the parser has changed since.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from plan_bot.migrations.util import drop_column

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch:
        batch.add_column(
            sa.Column("parser_version", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    drop_column("subscriptions", "parser_version")
