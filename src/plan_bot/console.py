"""Local console front-end: try the bot without any chat platform or token."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from datetime import datetime
from typing import TextIO

from plan_bot.app import build_app, shifted_clock
from plan_bot.commands import INTRO
from plan_bot.config import Settings
from plan_bot.repository import ChatRef

CONSOLE_CHAT = ChatRef("console", "local")


class ConsoleNotifier:
    def __init__(self, out: TextIO) -> None:
        self.out = out

    async def send(self, chat: ChatRef, text: str) -> None:
        self.out.write(f"\n[notification]\n{text}\n> ")
        self.out.flush()


async def run_console(
    settings: Settings,
    *,
    start_at: datetime | None = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> None:
    clock = shifted_clock(start_at)
    async with build_app(settings, ConsoleNotifier(stdout), clock=clock) as app:
        stop = asyncio.Event()
        scheduler = asyncio.create_task(app.scheduler.run(stop))
        stdout.write(f"{INTRO}\nType /help for commands, Ctrl+D to quit.\n> ")
        stdout.flush()
        try:
            while True:
                line = await asyncio.to_thread(stdin.readline)
                if not line:
                    break
                if not line.strip():
                    stdout.write("> ")
                    continue
                reply = await app.router.handle_text(CONSOLE_CHAT, line)
                stdout.write((reply or "Commands start with '/'. Try /help") + "\n> ")
                stdout.flush()
        finally:
            stop.set()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler
            stdout.write("\nBye.\n")
