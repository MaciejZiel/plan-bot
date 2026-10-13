"""Database schema, engine setup and migrations (SQLAlchemy 2 + Alembic)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    event,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MIGRATIONS = Path(__file__).parent / "migrations"


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware datetimes as naive UTC; always hand back aware UTC values.

    SQLite has no timezone support, so normalising at the boundary keeps the
    rest of the code free of naive datetimes on every backend.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to the database layer")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    """One chat (Telegram chat, Discord channel, console) following one ICS feed."""

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("platform", "chat_id", name="uq_subscription_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(16))
    chat_id: Mapped[str] = mapped_column(String(64))
    ics_url: Mapped[str | None] = mapped_column(Text, default=None)
    language: Mapped[str] = mapped_column(String(8), default="en", server_default="en")
    group_filter: Mapped[str] = mapped_column(String(255), default="")
    reminder_minutes: Mapped[int] = mapped_column(Integer, default=15)
    notify_changes: Mapped[bool] = mapped_column(Boolean, default=True)
    weekly_summary: Mapped[bool] = mapped_column(Boolean, default=True)
    last_weekly_key: Mapped[str | None] = mapped_column(String(16), default=None)
    last_refresh_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    window_end: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    #: ``ics.PARSER_VERSION`` the stored lessons were parsed with (0 = before it existed).
    parser_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Parser version for which the chat was already told to re-upload its file (0 = never told).
    reupload_notified: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))

    lessons: Mapped[list[LessonRow]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", passive_deletes=True
    )


class LessonRow(Base):
    """Last known snapshot of the feed, used for queries, reminders and diffing."""

    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("subscription_id", "key", name="uq_lesson_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(512))
    uid: Mapped[str] = mapped_column(String(512))
    start: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    summary: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    groups: Mapped[str] = mapped_column(Text, default="")
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)

    subscription: Mapped[Subscription] = relationship(back_populates="lessons")


class SentReminder(Base):
    """Makes reminders idempotent across ticks and restarts."""

    __tablename__ = "sent_reminders"

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    start: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)


def create_engine(url: str, **kwargs: Any) -> AsyncEngine:
    engine = create_async_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def session_factory(engine: AsyncEngine) -> async_sessionmaker[Any]:
    return async_sessionmaker(engine, expire_on_commit=False)


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(url: str) -> None:
    """Upgrade the database at ``url`` to the latest revision (blocking)."""
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if path and path != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(url), "head")


async def migrate(url: str) -> None:
    """Async wrapper around :func:`upgrade`.

    Alembic's async env runs its own event loop, so it is executed in a worker
    thread to stay out of the caller's loop.
    """
    await asyncio.to_thread(upgrade, url)
