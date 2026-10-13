from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from plan_bot.config import Settings
from plan_bot.repository import ChatRef
from plan_bot.runner import MultiNotifier, run_bots


class FakeAdapter:
    def __init__(self, platform: str, fail: bool = False) -> None:
        self.platform = platform
        self.sent: list[tuple[ChatRef, str]] = []
        self.fail = fail

    async def send(self, chat: ChatRef, text: str) -> None:
        self.sent.append((chat, text))

    async def run(self, stop: asyncio.Event) -> None:
        if self.fail:
            raise RuntimeError("login failed")
        await stop.wait()


async def test_multi_notifier_routes_by_platform() -> None:
    notifier = MultiNotifier()
    telegram = FakeAdapter("telegram")
    notifier.register(telegram)
    await notifier.send(ChatRef("telegram", "1"), "hi")
    await notifier.send(ChatRef("discord", "2"), "dropped")
    assert telegram.sent == [(ChatRef("telegram", "1"), "hi")]


async def test_requires_a_token(settings: Settings) -> None:
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        await run_bots(settings)


async def test_runs_until_stopped(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    adapters: dict[str, FakeAdapter] = {}

    def fake_telegram(api: object, router: object) -> FakeAdapter:
        adapters["telegram"] = FakeAdapter("telegram")
        return adapters["telegram"]

    def fake_discord(router: object, token: str, guild_id: int | None = None) -> FakeAdapter:
        adapters["discord"] = FakeAdapter("discord")
        return adapters["discord"]

    monkeypatch.setattr("plan_bot.adapters.telegram.TelegramAdapter", fake_telegram)
    monkeypatch.setattr("plan_bot.adapters.discord.DiscordAdapter", fake_discord)
    stop = asyncio.Event()
    configured = replace(settings, telegram_token="1:x", discord_token="y", tick_seconds=1)
    task = asyncio.create_task(run_bots(configured, stop=stop))
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert set(adapters) == {"telegram", "discord"}


async def test_adapter_failure_is_raised(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "plan_bot.adapters.discord.DiscordAdapter",
        lambda router, token, guild_id=None: FakeAdapter("discord", fail=True),
    )
    configured = replace(settings, discord_token="y")
    with pytest.raises(RuntimeError, match="login failed"):
        await asyncio.wait_for(run_bots(configured, install_signal_handlers=True), timeout=5)


async def test_health_endpoint_is_served_while_running(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    import aiohttp

    monkeypatch.setattr(
        "plan_bot.adapters.telegram.TelegramAdapter", lambda api, router: FakeAdapter("telegram")
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    stop = asyncio.Event()
    configured = replace(
        settings, telegram_token="1:x", health_port=port, base_path="/bot", tick_seconds=1
    )
    task = asyncio.create_task(run_bots(configured, stop=stop))
    body: dict[str, object] = {}
    async with aiohttp.ClientSession() as http:
        for _ in range(100):
            try:
                async with http.get(f"http://127.0.0.1:{port}/bot/healthz") as response:
                    body = await response.json()
                    break
            except aiohttp.ClientConnectorError:
                await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert body["status"] == "ok"
    assert body["adapters"] == ["telegram"]


async def test_missing_discord_library_is_explained(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "plan_bot.adapters.discord", None)
    with pytest.raises(RuntimeError, match=r"plan-bot\[discord\]"):
        await run_bots(replace(settings, discord_token="y"), install_signal_handlers=False)
