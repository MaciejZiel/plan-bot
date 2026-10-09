from __future__ import annotations

import io

import pytest

from plan_bot.__main__ import build_parser, main
from plan_bot.app import shifted_clock
from plan_bot.config import Settings
from plan_bot.console import ConsoleNotifier, run_console
from plan_bot.repository import ChatRef
from plan_bot.service import utc_now
from tests.conftest import warsaw


async def test_console_session(settings: Settings) -> None:
    stdin = io.StringIO("/setfeed demo\n\n/today\nhello\n")
    stdout = io.StringIO()
    await run_console(settings, start_at=warsaw(2026, 10, 12, 7), stdin=stdin, stdout=stdout)
    out = stdout.getvalue()
    assert "Timetable saved" in out
    assert "Today · Monday, 12 Oct" in out
    assert "Commands start with '/'" in out
    assert out.endswith("Bye.\n")


async def test_console_notifier() -> None:
    out = io.StringIO()
    await ConsoleNotifier(out).send(ChatRef("console", "local"), "hi")
    assert "[notification]\nhi" in out.getvalue()


def test_shifted_clock() -> None:
    assert shifted_clock(None) is utc_now
    clock = shifted_clock(warsaw(2030, 1, 1))
    assert abs((clock() - warsaw(2030, 1, 1)).total_seconds()) < 5


def test_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["console", "--at", "2026-10-12T08:00"])
    assert args.at == warsaw(2026, 10, 12, 8)

    seen: dict[str, object] = {}

    async def fake_console(settings: Settings, *, start_at: object = None) -> None:
        seen["start_at"] = start_at

    monkeypatch.setattr("plan_bot.console.run_console", fake_console)
    assert main(["console"]) == 0
    assert main([]) == 0
    assert seen == {"start_at": None}

    monkeypatch.setenv("PLAN_BOT_TIMEZONE", "Nowhere/Land")
    assert main(["console"]) == 2
    assert "configuration error" in capsys.readouterr().out
