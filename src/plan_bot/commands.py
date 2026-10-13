"""Command table and dispatcher shared by all chat adapters."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from plan_bot.i18n import DEFAULT_LANG, LANG_NAMES, LANGS, tr
from plan_bot.ratelimit import RateLimiter
from plan_bot.repository import ChatRef
from plan_bot.service import BotService, NoFeedError, UserError
from plan_bot.views import View, render_text

log = logging.getLogger(__name__)

#: Commands that download a feed cost extra rate-limit tokens.
#: The bundled demo never touches the network, so it costs a normal command.
HEAVY_COMMANDS = frozenset({"subscribe", "refresh"})
HEAVY_COST = 4


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    arg: str | None = None
    arg_required: bool = False
    #: Only offered on Telegram (``/start`` has no meaning on Discord).
    telegram_only: bool = False

    @property
    def description(self) -> str:
        return self.describe(DEFAULT_LANG)

    @property
    def arg_help(self) -> str | None:
        return tr(DEFAULT_LANG, f"arg.{self.name}") if self.arg else None

    def describe(self, lang: str) -> str:
        return tr(lang, f"cmd.{self.name}")


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("start", telegram_only=True),
    CommandSpec("next"),
    CommandSpec("today"),
    CommandSpec("tomorrow"),
    CommandSpec("week", "which"),
    CommandSpec("demo"),
    CommandSpec("subscribe", "url", arg_required=True),
    CommandSpec("groups"),
    CommandSpec("filter", "groups", True),
    CommandSpec("remind", "minutes", True),
    CommandSpec("changes", "state", True),
    CommandSpec("summary", "state", True),
    CommandSpec("refresh"),
    CommandSpec("status"),
    CommandSpec("lang", "language", True),
    CommandSpec("forget"),
    CommandSpec("help"),
)

#: Old names that still work but are not advertised.
ALIASES = {"setfeed": "subscribe"}


@dataclass(frozen=True, slots=True)
class Button:
    label: str
    #: A command line, e.g. ``/next`` or ``/lang pl``; pressing it equals typing it.
    command: str


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    buttons: tuple[tuple[Button, ...], ...] = ()
    #: Structured result for platforms that can render more than text (Discord embeds).
    view: View | None = None
    #: Language the reply is written in.
    lang: str = DEFAULT_LANG
    #: The welcome/help answer (Discord renders it as a richer embed).
    intro: bool = False


def intro_text(lang: str = DEFAULT_LANG) -> str:
    return tr(lang, "start")


def help_text(lang: str = DEFAULT_LANG) -> str:
    lines = [tr(lang, "start"), "", tr(lang, "help_intro"), "", tr(lang, "help_commands")]
    for spec in COMMANDS:
        if spec.name == "start":
            continue
        usage = f"/{spec.name}" + (f" <{spec.arg}>" if spec.arg else "")
        lines.append(f"{usage} - {spec.describe(lang)}")
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


def language_row() -> tuple[Button, ...]:
    return tuple(Button(LANG_NAMES[code], f"/lang {code}") for code in LANGS)


def menu_buttons(lang: str, *, extra: str | None = None) -> tuple[tuple[Button, ...], ...]:
    rows = [
        (
            Button(tr(lang, "btn.next"), "/next"),
            Button(tr(lang, "btn.today"), "/today"),
            Button(tr(lang, "btn.tomorrow"), "/tomorrow"),
        ),
        (
            Button(tr(lang, "btn.week"), "/week"),
            Button(tr(lang, "btn.next_week"), "/week next"),
        ),
    ]
    if extra == "reminders":
        rows.append(
            (
                Button(tr(lang, "btn.remind", n=15), "/remind 15"),
                Button(tr(lang, "btn.remind", n=60), "/remind 60"),
                Button(tr(lang, "btn.remind_off"), "/remind off"),
            )
        )
    return tuple(rows)


class CommandRouter:
    def __init__(self, service: BotService, *, limiter: RateLimiter | None = None) -> None:
        self.service = service
        self.limiter = limiter
        s = service
        self._views: dict[str, Callable[[ChatRef, str | None], Awaitable[View]]] = {
            "today": lambda chat, _: s.today_view(chat),
            "tomorrow": lambda chat, _: s.tomorrow_view(chat),
            "next": lambda chat, _: s.next_view(chat),
            "week": s.week_view,
        }
        self._handlers: dict[str, Callable[[ChatRef, str | None], Awaitable[str]]] = {
            "today": lambda chat, _: s.today(chat),
            "tomorrow": lambda chat, _: s.tomorrow(chat),
            "next": lambda chat, _: s.next(chat),
            "week": s.week,
            "subscribe": s.set_feed,
            "demo": lambda chat, _: s.set_feed(chat, "demo"),
            "groups": lambda chat, _: s.groups(chat),
            "filter": s.set_filter,
            "remind": s.set_reminder,
            "changes": s.set_changes,
            "summary": s.set_summary,
            "refresh": lambda chat, _: s.refresh(chat),
            "status": lambda chat, _: s.status(chat),
            "lang": s.set_language,
            "forget": lambda chat, _: s.forget(chat),
        }

    async def adopt_chat(self, old: ChatRef, new: ChatRef) -> bool:
        return await self.service.adopt_chat(old, new)

    async def handle(self, chat: ChatRef, name: str, arg: str | None = None) -> str:
        return (await self.reply(chat, name, arg)).text

    async def reply(
        self, chat: ChatRef, name: str, arg: str | None = None, *, locale: str | None = None
    ) -> Reply:
        """Run a command and return its text plus optional quick-reply buttons.

        ``locale`` is the language code reported by the chat platform; it picks the
        language of a brand-new chat.
        """
        name = ALIASES.get(name.lower(), name.lower())
        key = str(chat)
        if self.limiter is not None:
            wait = self.limiter.check(key, HEAVY_COST if name in HEAVY_COMMANDS else 1)
            if wait:
                if not self.limiter.should_warn(key):
                    return Reply("")
                lang = await self.service.language(chat)
                return Reply(tr(lang, "rate_limited", seconds=wait))
        try:
            await self.service.adopt_language(chat, locale)
            reply = await self._run(chat, name, arg)
            return replace(reply, lang=await self.service.language(chat))
        except Exception:
            log.exception("command failed", extra={"command": name, "platform": chat.platform})
            lang = await self.service.language(chat)
            return Reply(tr(lang, "internal_error"), lang=lang)

    async def _run(self, chat: ChatRef, name: str, arg: str | None) -> Reply:
        lang = await self.service.language(chat)
        if name in {"start", "help"}:
            return await self._intro(chat, name, lang)
        handler = self._handlers.get(name)
        if handler is None:
            return Reply(tr(lang, "unknown_command", name=name))
        view: View | None = None
        try:
            if name in self._views:
                view = await self._views[name](chat, arg)
                text = render_text(view)
            else:
                text = await handler(chat, arg)
        except NoFeedError as exc:
            return Reply(str(exc), ((Button(tr(lang, "btn.demo"), "/demo"),),))
        except UserError as exc:
            return Reply(str(exc))
        # The language may just have been changed by the command itself.
        lang = await self.service.language(chat)
        log.info("command", extra={"command": name, "platform": chat.platform})
        return Reply(text, await self._buttons_after(chat, name, lang), view)

    async def _intro(self, chat: ChatRef, name: str, lang: str) -> Reply:
        text = intro_text(lang) if name == "start" else help_text(lang)
        if await self.service.has_feed(chat):
            rows = (*menu_buttons(lang), language_row())
        else:
            rows = ((Button(tr(lang, "btn.demo"), "/demo"),), language_row())
        return Reply(text, rows, intro=True)

    async def _buttons_after(
        self, chat: ChatRef, name: str, lang: str
    ) -> tuple[tuple[Button, ...], ...]:
        if name in {"subscribe", "demo"}:
            return menu_buttons(lang, extra="reminders")
        if name == "lang":
            return ((Button(tr(lang, "btn.help"), "/help"),),)
        if name in {"next", "today", "tomorrow", "week", "refresh"}:
            return menu_buttons(lang)
        return ()

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
