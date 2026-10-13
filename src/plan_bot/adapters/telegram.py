"""Telegram adapter built directly on the Bot API (long polling over aiohttp).

A thin client is used instead of a framework: python-telegram-bot is LGPL-3.0
and aiogram pulls in certifi (MPL-2.0), neither of which fits this project's
permissive-only dependency policy. The bot needs four API methods.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import aiohttp

from plan_bot.commands import COMMANDS, CommandRouter, Reply, parse_command, split_message
from plan_bot.i18n import LANGS
from plan_bot.repository import ChatRef
from plan_bot.service import ChatUnavailable

log = logging.getLogger(__name__)

PLATFORM = "telegram"
MESSAGE_LIMIT = 4096
API_URL = "https://api.telegram.org"


class TelegramError(Exception):
    def __init__(
        self, description: str, retry_after: float | None = None, error_code: int | None = None
    ) -> None:
        super().__init__(description)
        self.retry_after = retry_after
        self.error_code = error_code

    @property
    def chat_gone(self) -> bool:
        """The user blocked the bot, deleted the chat or kicked the bot from the group."""
        text = str(self).lower()
        return self.error_code == 403 or "chat not found" in text or "deactivated" in text


def keyboard(reply: Reply) -> dict[str, Any] | None:
    if not reply.buttons:
        return None
    return {
        "inline_keyboard": [
            [{"text": b.label, "callback_data": b.command} for b in row] for row in reply.buttons
        ]
    }


class TelegramApi:
    def __init__(
        self, token: str, session: aiohttp.ClientSession, *, base_url: str = API_URL
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/bot{token}/"
        self._session = session

    async def call(self, method: str, *, http_timeout: float = 30, **params: Any) -> Any:
        try:
            async with self._session.post(
                self._url + method,
                json={k: v for k, v in params.items() if v is not None},
                timeout=aiohttp.ClientTimeout(total=http_timeout),
            ) as response:
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            # Never include the exception text: aiohttp puts the URL (with the token) in it.
            raise TelegramError(f"{method} failed: {type(exc).__name__}") from None
        if not isinstance(data, dict) or not data.get("ok"):
            data = data if isinstance(data, dict) else {}
            retry = (data.get("parameters") or {}).get("retry_after")
            raise TelegramError(
                f"{method}: {data.get('description', 'unknown error')}",
                float(retry) if retry is not None else None,
                data.get("error_code"),
            )
        return data["result"]

    async def get_me(self) -> dict[str, Any]:
        result: dict[str, Any] = await self.call("getMe")
        return result

    async def get_updates(self, offset: int | None, poll_seconds: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await self.call(
            "getUpdates",
            http_timeout=poll_seconds + 10,
            offset=offset,
            timeout=poll_seconds,
            allowed_updates=["message", "callback_query"],
        )
        return result

    async def send_message(
        self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None
    ) -> None:
        await self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            link_preview_options={"is_disabled": True},
            reply_markup=reply_markup,
        )

    async def answer_callback(self, callback_id: str) -> None:
        await self.call("answerCallbackQuery", callback_query_id=callback_id)

    async def set_my_commands(self) -> None:
        """Register the command menu: English by default, Polish for Polish clients."""
        for lang in LANGS:
            commands = [{"command": c.name, "description": c.describe(lang)} for c in COMMANDS]
            await self.call(
                "setMyCommands",
                commands=commands,
                language_code=None if lang == "en" else lang,
            )


class TelegramAdapter:
    platform = PLATFORM

    def __init__(
        self,
        api: TelegramApi,
        router: CommandRouter,
        *,
        poll_timeout: int = 30,
        max_concurrency: int = 8,
    ) -> None:
        self.api = api
        self.router = router
        self.poll_timeout = poll_timeout
        self.username: str | None = None
        # A slow feed must not block everybody else, but one chat's commands stay ordered.
        self._slots = asyncio.Semaphore(max_concurrency)
        #: chat id -> (lock, number of updates holding or waiting for it)
        self._chat_locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def send(self, chat: ChatRef, text: str, reply: Reply | None = None) -> None:
        parts = split_message(text, MESSAGE_LIMIT)
        markup = keyboard(reply) if reply is not None else None
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            try:
                await self._send_part(chat, part, markup if last else None)
            except TelegramError as exc:
                if exc.chat_gone:
                    raise ChatUnavailable(str(exc)) from None
                raise

    async def _send_part(self, chat: ChatRef, part: str, markup: dict[str, Any] | None) -> None:
        try:
            await self.api.send_message(chat.chat_id, part, markup)
        except TelegramError as exc:
            if exc.retry_after is None:
                raise
            await asyncio.sleep(min(exc.retry_after, 60))
            await self.api.send_message(chat.chat_id, part, markup)

    def _addressed_elsewhere(self, text: str) -> bool:
        head = text.strip().split(maxsplit=1)[0]
        if "@" not in head or self.username is None:
            return False
        return head.split("@", 1)[1].lower() != self.username.lower()

    async def handle_update(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            await self._handle_callback(callback)
            return
        message = update.get("message")
        if not isinstance(message, dict):
            return
        text = message.get("text")
        chat_id = (message.get("chat") or {}).get("id")
        if not isinstance(text, str) or chat_id is None or parse_command(text) is None:
            return
        if self._addressed_elsewhere(text):
            return
        sender = message.get("from")
        locale = sender.get("language_code") if isinstance(sender, dict) else None
        await self._answer(ChatRef(PLATFORM, str(chat_id)), text, locale)

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        """A tap on an inline button behaves exactly like typing its command."""
        callback_id = callback.get("id")
        if isinstance(callback_id, str):
            with contextlib.suppress(TelegramError):  # stops the button's loading spinner
                await self.api.answer_callback(callback_id)
        data = callback.get("data")
        message = callback.get("message")
        chat_id = (message.get("chat") or {}).get("id") if isinstance(message, dict) else None
        if not isinstance(data, str) or chat_id is None or parse_command(data) is None:
            return
        sender = callback.get("from")
        locale = sender.get("language_code") if isinstance(sender, dict) else None
        await self._answer(ChatRef(PLATFORM, str(chat_id)), data, locale)

    async def _answer(self, chat: ChatRef, text: str, locale: str | None) -> None:
        parsed = parse_command(text)
        assert parsed is not None
        reply = await self.router.reply(chat, *parsed, locale=locale)
        if reply.text:
            try:
                await self.send(chat, reply.text, reply)
            except ChatUnavailable:
                await self.router.service.chat_gone(chat)

    def _dispatch(self, update: dict[str, Any]) -> None:
        task = asyncio.ensure_future(self._guarded(update))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _guarded(self, update: dict[str, Any]) -> None:
        container = update.get("message") or (update.get("callback_query") or {}).get("message")
        chat_id = str(((container or {}).get("chat") or {}).get("id"))
        lock, users = self._chat_locks.get(chat_id, (asyncio.Lock(), 0))
        self._chat_locks[chat_id] = (lock, users + 1)
        try:
            # The chat lock comes first: updates queued behind a slow command of the
            # same chat wait without holding one of the shared slots.
            async with lock, self._slots:
                await self.handle_update(update)
        except Exception:
            log.exception("telegram: failed to handle update %s", update.get("update_id"))
        finally:
            lock, users = self._chat_locks[chat_id]
            if users == 1:
                del self._chat_locks[chat_id]
            else:
                self._chat_locks[chat_id] = (lock, users - 1)

    async def run(self, stop: asyncio.Event) -> None:
        me = await self.api.get_me()
        self.username = me.get("username")
        await self.api.set_my_commands()
        log.info("telegram: polling as @%s", self.username)
        offset: int | None = None
        failures = 0
        while not stop.is_set():
            try:
                updates = await self.api.get_updates(offset, self.poll_timeout)
            except TelegramError as exc:
                failures += 1
                delay = exc.retry_after or min(2**failures, 60)
                log.warning("telegram: polling failed (%s), retrying in %ss", exc, delay)
                await _sleep_or_stop(stop, delay)
                continue
            failures = 0
            for update in updates:
                offset = int(update["update_id"]) + 1
                self._dispatch(update)
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=15)
        log.info("telegram: stopped")


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)
