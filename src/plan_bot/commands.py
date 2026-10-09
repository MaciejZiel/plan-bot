"""Command table and dispatcher shared by all chat adapters."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from plan_bot.repository import ChatRef
from plan_bot.service import BotService, UserError

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str
    arg: str | None = None
    arg_help: str | None = None
    arg_required: bool = False


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("today", "Classes today"),
    CommandSpec("tomorrow", "Classes tomorrow"),
    CommandSpec("next", "Next class with room and time left"),
    CommandSpec("week", "This week's plan", "which", "Leave empty or type 'next'"),
    CommandSpec(
        "setfeed",
        "Set your timetable ICS link",
        "url",
        "https://... or webcal://... link to the .ics feed, or 'demo'",
        arg_required=True,
    ),
    CommandSpec("groups", "Groups found in the timetable"),
    CommandSpec("filter", "Show only your groups", "groups", "e.g. L1,C2 or 'off'", True),
    CommandSpec("remind", "Reminder before classes", "minutes", "e.g. 15 or 'off'", True),
    CommandSpec("changes", "Alerts about timetable changes", "state", "'on' or 'off'", True),
    CommandSpec("summary", "Weekly summary on Sunday evening", "state", "'on' or 'off'", True),
    CommandSpec("refresh", "Download the timetable now"),
    CommandSpec("status", "Current settings and feed status"),
    CommandSpec("forget", "Delete everything stored for this chat"),
    CommandSpec("help", "How to use the bot"),
)

INTRO = (
    "Hi! I turn your university timetable (an iCalendar/ICS link) into quick answers, "
    "reminders and change alerts.\n"
    "1. Copy the ICS/iCal export link of your timetable.\n"
    "2. Send /setfeed <link>  (or /setfeed demo to try a fictional sample).\n"
    "3. Optionally /filter your groups and set /remind 15."
)


def help_text() -> str:
    lines = [INTRO, "", "Commands:"]
    for spec in COMMANDS:
        usage = f"/{spec.name}" + (f" <{spec.arg}>" if spec.arg else "")
        lines.append(f"{usage} - {spec.description}")
    return "\n".join(lines)


def parse_command(text: str) -> tuple[str, str | None] | None:
    """Split ``/name@BotName args`` into ``("name", "args")``."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    head, _, rest = text[1:].partition(" ")
    name = head.split("@", 1)[0].lower()
    if not name:
        return None
    return name, rest.strip() or None


class CommandRouter:
    def __init__(self, service: BotService) -> None:
        self.service = service
        s = service
        self._handlers: dict[str, Callable[[ChatRef, str | None], Awaitable[str]]] = {
            "today": lambda chat, _: s.today(chat),
            "tomorrow": lambda chat, _: s.tomorrow(chat),
            "next": lambda chat, _: s.next(chat),
            "week": s.week,
            "setfeed": s.set_feed,
            "groups": lambda chat, _: s.groups(chat),
            "filter": s.set_filter,
            "remind": s.set_reminder,
            "changes": s.set_changes,
            "summary": s.set_summary,
            "refresh": lambda chat, _: s.refresh(chat),
            "status": lambda chat, _: s.status(chat),
            "forget": lambda chat, _: s.forget(chat),
        }

    async def handle(self, chat: ChatRef, name: str, arg: str | None = None) -> str:
        name = name.lower()
        if name in {"start", "help"}:
            return help_text()
        handler = self._handlers.get(name)
        if handler is None:
            return f"Unknown command /{name}. Send /help for the list."
        try:
            return await handler(chat, arg)
        except UserError as exc:
            return str(exc)
        except Exception:
            log.exception("command /%s failed for %s", name, chat)
            return "Something went wrong on my side. Please try again later."

    async def handle_text(self, chat: ChatRef, text: str) -> str | None:
        parsed = parse_command(text)
        if parsed is None:
            return None
        return await self.handle(chat, *parsed)


def split_message(text: str, limit: int) -> list[str]:
    """Split on line boundaries so each part fits the platform's size limit."""
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate
    if current or not parts:
        parts.append(current)
    return parts
