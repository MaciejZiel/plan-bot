from __future__ import annotations

import asyncio
from typing import Any

import pytest
from discord import app_commands

from plan_bot.adapters.discord import DiscordAdapter
from plan_bot.commands import COMMANDS
from plan_bot.repository import ChatRef


class FakeRouter:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: list[tuple[ChatRef, str, str | None]] = []

    async def handle(self, chat: ChatRef, name: str, arg: str | None = None) -> str:
        self.calls.append((chat, name, arg))
        return self.reply


class FakeResponse:
    def __init__(self) -> None:
        self.deferred = False

    async def defer(self, *, thinking: bool = False) -> None:
        self.deferred = thinking


class FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str) -> None:
        self.sent.append(content)


class FakeInteraction:
    def __init__(self, channel_id: int = 777) -> None:
        self.channel_id = channel_id
        self.response = FakeResponse()
        self.followup = FakeFollowup()


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str) -> None:
        self.sent.append(content)


async def test_slash_commands_mirror_command_table() -> None:
    adapter = DiscordAdapter(FakeRouter(), "not-a-real-token")
    commands = {c.name: c for c in adapter.tree.get_commands()}
    assert set(commands) == {spec.name for spec in COMMANDS}
    setfeed = commands["setfeed"]
    assert isinstance(setfeed, app_commands.Command)
    (param,) = setfeed.parameters
    assert param.display_name == "url"
    assert param.required
    week = commands["week"]
    assert isinstance(week, app_commands.Command)
    assert not week.parameters[0].required
    today = commands["today"]
    assert isinstance(today, app_commands.Command)
    assert today.parameters == []


async def test_callbacks_defer_and_reply_in_chunks() -> None:
    router = FakeRouter("x" * 2500)
    adapter = DiscordAdapter(router, "not-a-real-token", guild_id=42)
    commands = {c.name: c for c in adapter.tree.get_commands(guild=adapter.guild)}
    interaction = FakeInteraction()
    setfeed = commands["setfeed"]
    assert isinstance(setfeed, app_commands.Command)
    await setfeed.callback(interaction, "demo")  # type: ignore[arg-type]
    assert interaction.response.deferred
    assert [len(p) for p in interaction.followup.sent] == [2000, 500]
    assert router.calls == [(ChatRef("discord", "777"), "setfeed", "demo")]

    for name, args in (("today", ()), ("week", ()), ("week", ("next",))):
        command = commands[name]
        assert isinstance(command, app_commands.Command)
        await command.callback(FakeInteraction(), *args)  # type: ignore[arg-type]
    assert [c[1:] for c in router.calls[1:]] == [("today", None), ("week", None), ("week", "next")]


async def test_send_uses_cache_or_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DiscordAdapter(FakeRouter(), "not-a-real-token")
    cached = FakeChannel()
    fetched = FakeChannel()

    async def fetch_channel(channel_id: int) -> Any:
        return fetched if channel_id == 2 else object()

    monkeypatch.setattr(adapter.client, "get_channel", lambda cid: cached if cid == 1 else None)
    monkeypatch.setattr(adapter.client, "fetch_channel", fetch_channel)
    await adapter.send(ChatRef("discord", "1"), "hello")
    await adapter.send(ChatRef("discord", "2"), "world")
    assert cached.sent == ["hello"]
    assert fetched.sent == ["world"]
    with pytest.raises(TypeError):
        await adapter.send(ChatRef("discord", "3"), "nobody")


async def test_setup_hook_syncs(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DiscordAdapter(FakeRouter(), "not-a-real-token")
    synced: list[object] = []

    async def sync(*, guild: object = None) -> list[int]:
        synced.append(guild)
        return [1, 2]

    monkeypatch.setattr(adapter.tree, "sync", sync)
    await adapter.client.setup_hook()
    assert synced == [None]


async def test_run_stops_and_propagates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DiscordAdapter(FakeRouter(), "not-a-real-token")
    closed: list[bool] = []

    async def start_forever(token: str) -> None:
        await asyncio.sleep(3600)

    async def close() -> None:
        closed.append(True)

    monkeypatch.setattr(adapter.client, "start", start_forever)
    monkeypatch.setattr(adapter.client, "close", close)
    stop = asyncio.Event()
    task = asyncio.create_task(adapter.run(stop))
    await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert closed

    async def bad_login(token: str) -> None:
        raise RuntimeError("Improper token has been passed.")

    monkeypatch.setattr(adapter.client, "start", bad_login)
    with pytest.raises(RuntimeError, match="Improper token"):
        await adapter.run(asyncio.Event())
