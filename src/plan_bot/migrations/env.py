"""Alembic environment: async engine, URL taken from the Alembic config."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from plan_bot.db import Base, create_engine

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    url = config.get_main_option("sqlalchemy.url")
    assert url is not None
    engine = create_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_async())
