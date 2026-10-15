"""Add the reminder sent when a class starts (on by default).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from plan_bot.migrations.util import drop_column

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch:
        batch.add_column(
            sa.Column("remind_on_start", sa.Boolean(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    drop_column("subscriptions", "remind_on_start")
