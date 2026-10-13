from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from plan_bot.adapters.telegram import TelegramAdapter, TelegramApi, TelegramError
from plan_bot.commands import CommandRouter, Reply
from plan_bot.repository import ChatRef
from plan_bot.service import BotService, ChatUnavailable

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
        message(4, "/subscribe@PlanBot demo"),
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

    async def reply(
        self, chat: ChatRef, name: str, arg: str | None = None, *, locale: str | None = None
    ) -> Reply:
        text = f"/{name}" + (f" {arg}" if arg else "")
        self.seen.append((chat, text))
        return Reply("" if name == "quiet" else f"echo {text}")


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
    assert [text for _, text in router.seen] == ["/today", "/quiet"]
    assert router.seen[0][0] == ChatRef("telegram", "-100")
    assert [m["text"] for m in fake.sent] == ["echo /today"]


def callback(
    update_id: int, data: str, chat_id: int = 555, lang: str | None = "pl"
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "data": data,
            "from": {"id": chat_id, "language_code": lang},
            "message": {"chat": {"id": chat_id}},
        },
    }


async def test_start_demo_flow_with_inline_buttons(
    bot_api: tuple[FakeBotApi, TelegramApi], service: BotService
) -> None:
    fake, api = bot_api
    adapter = TelegramAdapter(api, CommandRouter(service))
    start = message(1, "/start")
    start["message"]["from"] = {"language_code": "pl"}
    await adapter.handle_update(start)
    (greeting,) = fake.sent
    assert greeting["text"].startswith("Cześć!")
    keyboard = greeting["reply_markup"]["inline_keyboard"]
    assert keyboard[0] == [{"text": "Wypróbuj demo", "callback_data": "/demo"}]

    await adapter.handle_update(callback(2, "/demo"))  # the tap
    assert "answerCallbackQuery" in fake.calls
    demo = fake.sent[-1]
    assert demo["text"].startswith("Plan zapisany")
    buttons = [b["callback_data"] for row in demo["reply_markup"]["inline_keyboard"] for b in row]
    assert buttons[:3] == ["/next", "/today", "/tomorrow"]

    await adapter.handle_update(callback(3, "/next"))
    assert fake.sent[-1]["text"].startswith("Następne:")
    await adapter.handle_update(callback(4, "not a command"))
    await adapter.handle_update({"update_id": 5, "callback_query": {"id": "x", "data": "/next"}})
    assert len(fake.sent) == 3  # malformed callbacks are ignored


async def test_commands_are_registered_per_language(
    bot_api: tuple[FakeBotApi, TelegramApi],
) -> None:
    _, api = bot_api
    registered: list[dict[str, Any]] = []
    original = api.call

    async def spy(method: str, *, http_timeout: float = 30, **params: Any) -> Any:
        if method == "setMyCommands":
            registered.append(params)
        return await original(method, http_timeout=http_timeout, **params)

    api.call = spy  # type: ignore[method-assign]
    await api.set_my_commands()
    assert [p.get("language_code") for p in registered] == [None, "pl"]
    start_pl = registered[1]["commands"][0]
    assert start_pl == {"command": "start", "description": "Co robi ten bot"}


async def test_blocked_bot_raises_chat_unavailable(
    bot_api: tuple[FakeBotApi, TelegramApi],
) -> None:
    fake, api = bot_api
    adapter = TelegramAdapter(api, router=None)  # type: ignore[arg-type]
    fake.fail_next["sendMessage"] = {
        "ok": False,
        "error_code": 403,
        "description": "Forbidden: bot was blocked by the user",
    }
    with pytest.raises(ChatUnavailable):
        await adapter.send(ChatRef("telegram", "9"), "hi")


async def test_slow_command_does_not_block_other_chats(
    bot_api: tuple[FakeBotApi, TelegramApi],
) -> None:
    fake, api = bot_api
    gate = asyncio.Event()
    order: list[str] = []

    class SlowRouter:
        async def reply(
            self, chat: ChatRef, name: str, arg: str | None = None, *, locale: str | None = None
        ) -> Reply:
            if chat.chat_id == "1":
                await gate.wait()
            order.append(f"{chat.chat_id}:{arg}")
            return Reply(f"done {chat.chat_id} {arg}")

    adapter = TelegramAdapter(api, SlowRouter(), poll_timeout=0)  # type: ignore[arg-type]
    fake.updates = [
        message(1, "/x first", chat_id=1),
        message(2, "/x second", chat_id=1),
        message(3, "/x other", chat_id=2),
    ]
    stop = asyncio.Event()
    task = asyncio.create_task(adapter.run(stop))
    for _ in range(100):
        if order:
            break
        await asyncio.sleep(0.02)
    assert order == ["2:other"]  # chat 2 was answered while chat 1 is still busy
    gate.set()
    for _ in range(100):
        if len(order) == 3:
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert order == ["2:other", "1:first", "1:second"]  # per-chat order is preserved


async def test_one_busy_chat_cannot_take_every_slot(
    bot_api: tuple[FakeBotApi, TelegramApi],
) -> None:
    _, api = bot_api
    gate = asyncio.Event()
    answered: list[str] = []

    class SlowRouter:
        async def reply(
            self, chat: ChatRef, name: str, arg: str | None = None, *, locale: str | None = None
        ) -> Reply:
            if chat.chat_id == "1":
                await gate.wait()
            answered.append(f"{chat.chat_id}:{arg}")
            return Reply("")

    adapter = TelegramAdapter(api, SlowRouter(), max_concurrency=2)  # type: ignore[arg-type]
    # Chat 1 queues more commands than there are slots, all stuck behind a slow feed.
    for n in range(5):
        adapter._dispatch(message(n, f"/x {n}", chat_id=1))
    adapter._dispatch(message(99, "/x other", chat_id=2))
    for _ in range(100):
        if answered:
            break
        await asyncio.sleep(0.01)
    assert answered == ["2:other"]
    gate.set()
    await asyncio.wait(adapter._tasks, timeout=5)
    assert answered == ["2:other", *(f"1:{n}" for n in range(5))]
    assert adapter._chat_locks == {}  # idle chats leave no lock behind


async def test_per_chat_order_holds_under_random_delays(
    bot_api: tuple[FakeBotApi, TelegramApi],
) -> None:
    _, api = bot_api
    rng = random.Random(1234)
    seen: dict[str, list[int]] = {}

    class JitterRouter:
        async def reply(
            self, chat: ChatRef, name: str, arg: str | None = None, *, locale: str | None = None
        ) -> Reply:
            await asyncio.sleep(rng.random() / 200)
            seen.setdefault(chat.chat_id, []).append(int(arg or 0))
            return Reply("")

    adapter = TelegramAdapter(api, JitterRouter(), max_concurrency=3)  # type: ignore[arg-type]
    for n in range(300):
        adapter._dispatch(message(n, f"/x {n}", chat_id=rng.randrange(7)))
    await asyncio.wait(adapter._tasks, timeout=10)
    assert sum(len(v) for v in seen.values()) == 300
    for numbers in seen.values():
        assert numbers == sorted(numbers)
    assert adapter._chat_locks == {}
