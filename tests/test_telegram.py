from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from plan_bot.adapters.telegram import TelegramAdapter, TelegramApi, TelegramError
from plan_bot.commands import CommandRouter
from plan_bot.repository import ChatRef
from plan_bot.service import BotService

TOKEN = "123456:TEST-TOKEN-NOT-REAL"


class FakeBotApi:
    """Just enough of the Telegram Bot API to exercise the adapter."""

    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.calls: list[str] = []
        self.fail_next: dict[str, dict[str, Any]] = {}
        self.got_message = asyncio.Event()

    async def handler(self, request: web.Request) -> web.Response:
        assert request.match_info["token"] == TOKEN
        method = request.match_info["method"]
        self.calls.append(method)
        body = await request.json()
        if method in self.fail_next:
            return web.json_response(self.fail_next.pop(method))
        if method == "getMe":
            return web.json_response({"ok": True, "result": {"id": 1, "username": "PlanBot"}})
        if method == "getUpdates":
            offset = body.get("offset") or 0
            pending = [u for u in self.updates if u["update_id"] >= offset]
            if not pending:
                await asyncio.sleep(0.01)
            return web.json_response({"ok": True, "result": pending})
        if method == "sendMessage":
            self.sent.append(body)
            self.got_message.set()
            return web.json_response({"ok": True, "result": {}})
        return web.json_response({"ok": True, "result": True})


@pytest.fixture
async def bot_api() -> AsyncIterator[tuple[FakeBotApi, TelegramApi]]:
    fake = FakeBotApi()
    app = web.Application()
    app.router.add_post("/bot{token}/{method}", fake.handler)
    server = TestServer(app)
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        yield fake, TelegramApi(TOKEN, session, base_url=str(server.make_url("/")))
    await server.close()


def message(update_id: int, text: str, chat_id: int = 555) -> dict[str, Any]:
    return {"update_id": update_id, "message": {"text": text, "chat": {"id": chat_id}}}


async def test_polling_answers_commands(
    bot_api: tuple[FakeBotApi, TelegramApi], service: BotService
) -> None:
    fake, api = bot_api
    adapter = TelegramAdapter(api, CommandRouter(service), poll_timeout=0)
    fake.updates = [
        {"update_id": 1, "edited_message": {}},
        message(2, "hello there"),
        message(3, "/today@SomeOtherBot"),
        message(4, "/setfeed@PlanBot demo"),
    ]
    stop = asyncio.Event()
    task = asyncio.create_task(adapter.run(stop))
    await asyncio.wait_for(fake.got_message.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert fake.calls[:2] == ["getMe", "setMyCommands"]
    (sent,) = fake.sent
    assert sent["chat_id"] == "555"
    assert sent["text"].startswith("Timetable saved")


async def test_polling_survives_errors(
    bot_api: tuple[FakeBotApi, TelegramApi], service: BotService, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, api = bot_api
    adapter = TelegramAdapter(api, CommandRouter(service), poll_timeout=0)
    fake.fail_next["getUpdates"] = {
        "ok": False,
        "description": "Too Many Requests",
        "parameters": {"retry_after": 0.01},
    }
    fake.updates = [message(10, "/help")]

    async def broken(update: dict[str, Any]) -> None:
        monkeypatch.undo()
        raise RuntimeError("bad update")

    monkeypatch.setattr(adapter, "handle_update", broken)
    stop = asyncio.Event()
    task = asyncio.create_task(adapter.run(stop))
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert fake.calls.count("getUpdates") >= 2


async def test_send_splits_and_retries(bot_api: tuple[FakeBotApi, TelegramApi]) -> None:
    fake, api = bot_api
    adapter = TelegramAdapter(api, router=None)  # type: ignore[arg-type]
    fake.fail_next["sendMessage"] = {
        "ok": False,
        "description": "slow down",
        "parameters": {"retry_after": 0},
    }
    await adapter.send(ChatRef("telegram", "9"), "line\n" * 1000)
    assert len(fake.sent) == 2
    assert all(len(m["text"]) <= 4096 for m in fake.sent)
    fake.fail_next["sendMessage"] = {"ok": False, "description": "Forbidden: bot was blocked"}
    with pytest.raises(TelegramError, match="blocked"):
        await adapter.send(ChatRef("telegram", "9"), "hi")


async def test_api_errors_do_not_leak_token() -> None:
    async with aiohttp.ClientSession() as session:
        api = TelegramApi(TOKEN, session, base_url="http://127.0.0.1:9")
        with pytest.raises(TelegramError) as info:
            await api.get_me()
    assert TOKEN not in str(info.value)
    assert info.value.retry_after is None


class EchoRouter:
    def __init__(self) -> None:
        self.seen: list[tuple[ChatRef, str]] = []

    async def handle_text(self, chat: ChatRef, text: str) -> str | None:
        self.seen.append((chat, text))
        return "" if text.startswith("/quiet") else f"echo {text}"


async def test_handle_update_filters_noise(bot_api: tuple[FakeBotApi, TelegramApi]) -> None:
    fake, api = bot_api
    router = EchoRouter()
    adapter = TelegramAdapter(api, router)  # type: ignore[arg-type]
    await adapter.handle_update({"update_id": 1, "message": {"chat": {"id": 1}}})  # no text
    await adapter.handle_update({"update_id": 2, "message": {"text": "/today"}})  # no chat
    await adapter.handle_update({"update_id": 3, "message": "garbage"})
    # Before getMe the username is unknown, so a mention cannot be checked: answer it.
    await adapter.handle_update(message(4, "/today@AnyBot", chat_id=-100))
    await adapter.handle_update(message(5, "/quiet"))
    assert [text for _, text in router.seen] == ["/today@AnyBot", "/quiet"]
    assert router.seen[0][0] == ChatRef("telegram", "-100")
    assert [m["text"] for m in fake.sent] == ["echo /today@AnyBot"]
