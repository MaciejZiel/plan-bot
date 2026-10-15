from __future__ import annotations

import pytest

from plan_bot.commands import COMMANDS, CommandRouter, help_text, parse_command, split_message
from plan_bot.repository import ChatRef
from plan_bot.service import BotService

CHAT = ChatRef("telegram", "1")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/today", ("today", None)),
        ("/Today@PlanBot", ("today", None)),
        ("  /subscribe   https://x.example/a.ics ", ("subscribe", "https://x.example/a.ics")),
        ("/filter L1, C2", ("filter", "L1, C2")),
        ("hello", None),
        ("/", None),
    ],
)
def test_parse_command(text: str, expected: tuple[str, str | None] | None) -> None:
    assert parse_command(text) == expected


def test_help_lists_every_command() -> None:
    text = help_text()
    for spec in COMMANDS:
        if not spec.telegram_only:
            assert f"/{spec.name}" in text
    assert "/subscribe <url>" in text


async def test_router_dispatch(service: BotService) -> None:
    router = CommandRouter(service)
    assert "Commands:" in await router.handle(CHAT, "help")
    assert "Unknown command /nope" in await router.handle(CHAT, "nope")
    assert "No timetable yet" in await router.handle(CHAT, "today")
    assert await router.handle_text(CHAT, "not a command") is None
    assert "Timetable saved" in (await router.handle_text(CHAT, "/setfeed demo") or "")
    for name in ("today", "tomorrow", "next", "week", "groups", "refresh", "status"):
        reply = await router.handle(CHAT, name)
        assert reply
        assert "went wrong" not in reply
    assert "5 min before each class" in await router.handle(CHAT, "remind", "5")
    assert "Filter set" in await router.handle(CHAT, "filter", "L1")
    assert "on" in await router.handle(CHAT, "changes", "on")
    assert "on" in await router.handle(CHAT, "summary", "on")
    assert "deleted" in await router.handle(CHAT, "forget")


async def test_router_hides_internal_errors(
    service: BotService, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(chat: ChatRef) -> str:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(service, "status", boom)
    reply = await CommandRouter(service).handle(CHAT, "status")
    assert reply == "Something went wrong on my side. Please try again later."


def test_split_message() -> None:
    assert split_message("short", 10) == ["short"]
    assert split_message("", 10) == [""]
    assert split_message("aaaa\nbbbb\ncccc", 9) == ["aaaa\nbbbb", "cccc"]
    assert split_message("x" * 25, 10) == ["x" * 10, "x" * 10, "x" * 5]
    assert split_message("ab\n" + "x" * 12, 10) == ["ab", "x" * 10, "xx"]
