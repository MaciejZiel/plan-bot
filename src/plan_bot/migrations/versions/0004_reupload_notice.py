"""Remember which parser version a chat was told to re-upload its file for.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from plan_bot.migrations.util import drop_column

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch:
        batch.add_column(
            sa.Column("reupload_notified", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    drop_column("subscriptions", "reupload_notified")
