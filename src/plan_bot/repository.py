"""Persistence operations used by the service layer."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plan_bot.db import LessonRow, SentReminder, Subscription
from plan_bot.domain import Lesson

_GROUP_SEP = "\x1f"


@dataclass(frozen=True, slots=True)
class ChatRef:
    """Platform-neutral address of a conversation."""

    platform: str
    chat_id: str

    def __str__(self) -> str:
        return f"{self.platform}:{self.chat_id}"


def _to_row(subscription_id: int, lesson: Lesson) -> LessonRow:
    return LessonRow(
        subscription_id=subscription_id,
        key=lesson.key,
        uid=lesson.uid,
        start=lesson.start,
        end=lesson.end,
        summary=lesson.summary,
        location=lesson.location,
        description=lesson.description,
        groups=_GROUP_SEP.join(lesson.groups),
        cancelled=lesson.cancelled,
    )


def _to_lesson(row: LessonRow) -> Lesson:
    return Lesson(
        key=row.key,
        uid=row.uid,
        start=row.start,
        end=row.end,
        summary=row.summary,
        location=row.location,
        description=row.description,
        groups=tuple(g for g in row.groups.split(_GROUP_SEP) if g),
        cancelled=row.cancelled,
    )


class Repository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, chat: ChatRef) -> Subscription | None:
        async with self._sessions() as session:
            return await self._find(session, chat)

    async def get_or_create(self, chat: ChatRef) -> Subscription:
        async with self._sessions() as session:
            found = await self._find(session, chat)
            if found is not None:
                return found
            sub = Subscription(platform=chat.platform, chat_id=chat.chat_id)
            session.add(sub)
            try:
                await session.commit()
            except IntegrityError:  # created concurrently
                await session.rollback()
                found = await self._find(session, chat)
                assert found is not None
                return found
            return sub

    async def update(self, chat: ChatRef, **fields: Any) -> Subscription:
        async with self._sessions() as session:
            sub = await self._find(session, chat)
            if sub is None:
                sub = Subscription(platform=chat.platform, chat_id=chat.chat_id)
                session.add(sub)
            for name, value in fields.items():
                if not hasattr(Subscription, name):
                    raise AttributeError(name)
                setattr(sub, name, value)
            await session.commit()
            return sub

    async def delete(self, chat: ChatRef) -> bool:
        async with self._sessions() as session:
            sub = await self._find(session, chat)
            if sub is None:
                return False
            await session.delete(sub)
            await session.commit()
            return True

    async def subscriptions_with_feed(self) -> list[Subscription]:
        async with self._sessions() as session:
            stmt = select(Subscription).where(Subscription.ics_url.is_not(None))
            return list((await session.scalars(stmt.order_by(Subscription.id))).all())

    async def lessons(
        self,
        subscription_id: int,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Lesson]:
        """Stored lessons, optionally only those starting in ``[start, end]``."""
        async with self._sessions() as session:
            stmt = select(LessonRow).where(LessonRow.subscription_id == subscription_id)
            if start is not None:
                stmt = stmt.where(LessonRow.start >= start)
            if end is not None:
                stmt = stmt.where(LessonRow.start <= end)
            stmt = stmt.order_by(LessonRow.start, LessonRow.summary)
            return [_to_lesson(row) for row in (await session.scalars(stmt)).all()]

    async def replace_lessons(
        self,
        subscription_id: int,
        lessons: Iterable[Lesson],
        *,
        refreshed_at: datetime,
        window_end: datetime,
    ) -> None:
        async with self._sessions() as session:
            await session.execute(
                delete(LessonRow).where(LessonRow.subscription_id == subscription_id)
            )
            session.add_all(_to_row(subscription_id, les) for les in lessons)
            sub = await session.get(Subscription, subscription_id)
            if sub is not None:
                sub.last_refresh_at = refreshed_at
                sub.window_end = window_end
                sub.last_error = None
                sub.error_count = 0
            await session.commit()

    async def record_error(self, subscription_id: int, message: str, at: datetime) -> int:
        async with self._sessions() as session:
            sub = await session.get(Subscription, subscription_id)
            if sub is None:
                return 0
            sub.last_error = message[:500]
            sub.error_count += 1
            sub.last_refresh_at = at
            await session.commit()
            return sub.error_count

    async def mark_reminded(self, subscription_id: int, key: str, start: datetime) -> bool:
        """Record a reminder; ``False`` if it had already been sent."""
        async with self._sessions() as session:
            session.add(SentReminder(subscription_id=subscription_id, key=key, start=start))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    async def prune_reminders(self, before: datetime) -> int:
        async with self._sessions() as session:
            result = await session.execute(delete(SentReminder).where(SentReminder.start < before))
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def _find(session: AsyncSession, chat: ChatRef) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.platform == chat.platform, Subscription.chat_id == chat.chat_id
        )
        return (await session.scalars(stmt)).first()
