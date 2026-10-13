"""Discord adapter: slash commands, embeds, buttons, free-text questions and DM delivery.

Design decisions (see README, "Discord"):

* A timetable belongs to the *user*, not to the channel: chats are keyed
  ``user:<id>`` and reminders arrive as direct messages. Older rows keyed by a plain
  channel id keep working and are delivered to that channel.
* Replies to slash commands are ephemeral (only the caller sees them) everywhere except
  in the user's own DM with the bot.
* A mention in a server is answered with a short public note; the answer itself
  (the user's timetable) goes to the author by DM, because a message reply cannot be
  ephemeral.
* Rows from before the per-user model that were keyed by the user's DM channel are
  moved to ``user:<id>`` the first time that user talks to the bot in that DM.
* Only non-privileged intents are used. Messages in DMs and messages that mention
  the bot carry their text without the privileged *message content* intent.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

import discord
from discord import app_commands
from discord.app_commands import locale_str

from plan_bot import intent as intent_rules
from plan_bot.adapters import discord_render as render
from plan_bot.commands import COMMANDS, Button, CommandSpec, Reply, menu_buttons, parse_command
from plan_bot.i18n import DEFAULT_LANG, LANG_NAMES, LANGS, lang_for_locale, tr
from plan_bot.repository import ChatRef
from plan_bot.service import ChatUnavailable, NotificationsBlocked
from plan_bot.views import View

log = logging.getLogger(__name__)

PLATFORM = "discord"
MAX_REMINDER_MINUTES = 24 * 60

#: Discord locale -> language of our catalogue (everything else falls back to English).
LOCALES = {"pl": "pl", "en-US": "en", "en-GB": "en"}

#: Buttons only ever run these commands (the custom id comes from the client).
_BUTTON_COMMAND = re.compile(
    r"(?P<name>next|today|tomorrow|demo|help|forget|week|remind|lang)(?: (?P<arg>[a-z0-9]{1,4}))?"
)
_BUTTON_ARGS: dict[str, frozenset[str | None]] = {
    "week": frozenset({None, "next"}),
    "remind": frozenset({"15", "30", "60", "off"}),
    "lang": frozenset(LANGS),
}

_STYLES = {
    "next": discord.ButtonStyle.primary,
    "demo": discord.ButtonStyle.success,
    "lang": discord.ButtonStyle.success,
    "forget": discord.ButtonStyle.danger,
}

#: Options with a fixed set of values are offered as a pick list.
_CHOICES: dict[str, list[tuple[str | locale_str, str]]] = {
    "week": [
        (locale_str("This week", key="choice.this_week"), "this"),
        (locale_str("Next week", key="choice.next_week"), "next"),
    ],
    "changes": [
        (locale_str("On", key="choice.on"), "on"),
        (locale_str("Off", key="choice.off"), "off"),
    ],
    "summary": [
        (locale_str("On", key="choice.on"), "on"),
        (locale_str("Off", key="choice.off"), "off"),
    ],
    "lang": [(LANG_NAMES[code], code) for code in LANGS],
}

Rows = tuple[tuple[Button, ...], ...]

#: Commands built by hand below instead of from the shared table.
_CUSTOM = frozenset({"start", "subscribe", "remind"})


class Router(Protocol):
    async def reply(
        self, chat: ChatRef, name: str, arg: str | None = None, *, locale: str | None = None
    ) -> Reply: ...

    async def adopt_chat(self, old: ChatRef, new: ChatRef) -> bool: ...


def user_chat(user_id: int) -> ChatRef:
    return ChatRef(PLATFORM, f"user:{user_id}")


def is_private(interaction: discord.Interaction[Any]) -> bool:
    """Whether only the caller may see the answer: everywhere but their DM with the bot.

    A user-installed command can run in a server, a group DM or a DM between two other
    people (Discord's ``private_channel`` context): all of them have other readers.
    """
    context = interaction.context
    if context.guild or context.private_channel:
        return True
    if context.dm_channel:
        return False
    return interaction.guild_id is not None


def parse_target(chat: ChatRef) -> tuple[str, int]:
    """``("user", id)`` or ``("channel", id)``; a bare number is a legacy channel row."""
    kind, sep, ident = chat.chat_id.partition(":")
    if not sep:
        kind, ident = "channel", chat.chat_id
    if kind not in {"user", "channel"} or not ident.isdigit():
        raise ChatUnavailable(f"unusable discord target {chat.chat_id!r}")
    return kind, int(ident)


class PlanTranslator(app_commands.Translator):
    """Serves command, option and choice texts in Polish and English."""

    async def translate(
        self,
        string: locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        lang = LOCALES.get(locale.value)
        key = string.extras.get("key")
        if lang is None or not isinstance(key, str):
            return None
        return tr(lang, key)


class CommandButton(
    discord.ui.DynamicItem[discord.ui.Button[Any]],
    template=r"plan:(?P<command>[a-z0-9 ]{2,20})",
):
    """A button that runs a command. It carries no state, so it survives restarts."""

    def __init__(self, label: str, command: str) -> None:
        name = command.partition(" ")[0]
        super().__init__(
            discord.ui.Button(
                label=label,
                custom_id=f"plan:{command}",
                style=_STYLES.get(name, discord.ButtonStyle.secondary),
            )
        )
        self.command = command

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Any],
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> CommandButton:
        label = item.label if isinstance(item, discord.ui.Button) else None
        return cls(label or "", match["command"])

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        adapter = getattr(interaction.client, "adapter", None)
        if isinstance(adapter, DiscordAdapter):
            await adapter.handle_button(interaction, self.command)


def build_view(rows: tuple[tuple[Button, ...], ...]) -> discord.ui.View | None:
    if not rows:
        return None
    view = discord.ui.View(timeout=None)
    for index, row in enumerate(rows[:5]):
        for button in row[:5]:
            item = CommandButton(button.label, button.command.lstrip("/"))
            item.item.row = index
            view.add_item(item)
    return view


def parse_button(command: str) -> tuple[str, str | None] | None:
    """Validate a button's command line; ``None`` if it is not one we ever send."""
    found = _BUTTON_COMMAND.fullmatch(command)
    if found is None:
        return None
    name, arg = found["name"], found["arg"]
    allowed = _BUTTON_ARGS.get(name, frozenset({None}))
    return (name, arg) if arg in allowed else None


class SubscribeModal(discord.ui.Modal):
    """A private form for the feed link, so it never shows in a server channel."""

    def __init__(self, adapter: DiscordAdapter, lang: str) -> None:
        super().__init__(title=tr(lang, "dc.subscribe_title"))
        self.adapter = adapter
        self.link: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label=tr(lang, "dc.subscribe_label"),
            placeholder="https://… / webcal://…",
            max_length=2000,
        )
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction[Any]) -> None:
        await self.adapter.respond(interaction, "subscribe", self.link.value)


class PlanClient(discord.Client):
    def __init__(self, adapter: DiscordAdapter, *, intents: discord.Intents) -> None:
        super().__init__(intents=intents)
        self.adapter = adapter

    async def setup_hook(self) -> None:
        await self.adapter.setup()

    async def on_message(self, message: discord.Message) -> None:
        await self.adapter.handle_message(message)


class DiscordAdapter:
    platform = PLATFORM
    #: Notifications may carry a structured view, rendered as an embed.
    supports_views = True

    def __init__(self, router: Router, token: str, *, guild_id: int | None = None) -> None:
        self.router = router
        self._token = token
        self.guild = discord.Object(id=guild_id) if guild_id else None
        # Slash commands need no intents. Messages (DMs and mentions) are non-privileged;
        # their text is delivered without the message content intent in exactly those cases.
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.dm_messages = True
        self.client = PlanClient(self, intents=intents)
        #: DM channels already checked for a row from before per-user timetables.
        self._dm_checked: set[int] = set()
        self.tree = app_commands.CommandTree(self.client)
        self.tree.on_error = self._on_tree_error  # type: ignore[method-assign]
        self.client.add_dynamic_items(CommandButton)
        for command in self._commands():
            command.allowed_contexts = app_commands.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            )
            command.allowed_installs = app_commands.AppInstallationType(guild=True, user=True)
            self.tree.add_command(command, guild=self.guild)

    # ------------------------------------------------------------------ setup

    async def setup(self) -> None:
        await self.tree.set_translator(PlanTranslator())
        synced = await self.tree.sync(guild=self.guild)
        log.info("discord: synced %d slash commands", len(synced))

    def _commands(self) -> list[app_commands.Command[Any, ..., Any] | app_commands.Group]:
        commands: list[app_commands.Command[Any, ..., Any] | app_commands.Group] = [
            self._subscribe_command(),
            self._remind_group(),
        ]
        commands.extend(self._command(spec) for spec in COMMANDS if spec.name not in _CUSTOM)
        return commands

    @staticmethod
    def _description(key: str) -> locale_str:
        return locale_str(tr(DEFAULT_LANG, key), key=key)

    def _command(self, spec: CommandSpec) -> app_commands.Command[Any, ..., None]:
        respond = self.respond
        callback: Callable[..., Coroutine[Any, Any, None]]
        if spec.arg is None:

            async def no_arg(interaction: discord.Interaction[Any]) -> None:
                await respond(interaction, spec.name, None)

            callback = no_arg
        elif spec.arg_required:

            async def required(interaction: discord.Interaction[Any], value: str) -> None:
                await respond(interaction, spec.name, value)

            callback = required
        else:

            async def optional(
                interaction: discord.Interaction[Any], value: str | None = None
            ) -> None:
                await respond(interaction, spec.name, value)

            callback = optional

        if spec.arg is not None:
            callback = app_commands.rename(value=spec.arg)(callback)
            callback = app_commands.describe(value=self._description(f"arg.{spec.name}"))(callback)
            if spec.name in _CHOICES:
                choices = [app_commands.Choice(name=n, value=v) for n, v in _CHOICES[spec.name]]
                callback = app_commands.choices(value=choices)(callback)
        return app_commands.Command(
            name=spec.name,
            description=self._description(f"cmd.{spec.name}"),
            callback=callback,
        )

    def _subscribe_command(self) -> app_commands.Command[Any, ..., None]:
        async def subscribe(interaction: discord.Interaction[Any], url: str | None = None) -> None:
            if url is None or not url.strip():
                lang = lang_for_locale(str(interaction.locale))
                await interaction.response.send_modal(SubscribeModal(self, lang))
                return
            await self.respond(interaction, "subscribe", url, link_in_channel=True)

        callback: Callable[..., Coroutine[Any, Any, None]] = app_commands.describe(
            url=self._description("arg.subscribe")
        )(subscribe)
        return app_commands.Command(
            name="subscribe", description=self._description("cmd.subscribe"), callback=callback
        )

    def _remind_group(self) -> app_commands.Group:
        group = app_commands.Group(name="remind", description=self._description("cmd.remind"))
        respond = self.respond

        async def set_(
            interaction: discord.Interaction[Any],
            minutes: app_commands.Range[int, 1, MAX_REMINDER_MINUTES],
        ) -> None:
            await respond(interaction, "remind", str(minutes))

        async def list_(interaction: discord.Interaction[Any]) -> None:
            await respond(interaction, "remind", "list")

        async def off(interaction: discord.Interaction[Any]) -> None:
            await respond(interaction, "remind", "off")

        described = app_commands.describe(minutes=self._description("arg.remind_minutes"))(set_)
        callbacks: list[tuple[str, str, Callable[..., Coroutine[Any, Any, None]]]] = [
            ("set", "cmd.remind_set", described),
            ("list", "cmd.remind_list", list_),
            ("off", "cmd.remind_off", off),
        ]
        for name, key, callback in callbacks:
            group.add_command(
                app_commands.Command(
                    name=name, description=self._description(key), callback=callback
                )
            )
        return group

    async def _on_tree_error(
        self, interaction: discord.Interaction[Any], error: app_commands.AppCommandError
    ) -> None:
        log.error("discord: command failed", exc_info=error)
        lang = lang_for_locale(str(interaction.locale))
        try:
            await self._say(interaction, [discord.Embed(description=tr(lang, "internal_error"))])
        except discord.HTTPException:  # the interaction expired or was already answered
            log.debug("discord: could not report the error to the user")

    # ------------------------------------------------------- answering users

    @staticmethod
    def _present(reply: Reply) -> list[list[discord.Embed]]:
        """Message payloads (each a list of embeds) for a reply."""
        if reply.view is not None:
            return [render.view_embeds(reply.view)]
        if reply.intro:
            return [[render.help_embed(reply.lang)]]
        return [[e] for e in render.text_embeds(reply.text)]

    async def respond(
        self,
        interaction: discord.Interaction[Any],
        name: str,
        arg: str | None,
        *,
        link_in_channel: bool = False,
    ) -> None:
        """Answer a slash command or button press from the caller's own timetable."""
        in_server = interaction.guild_id is not None
        # Downloading a feed can take longer than Discord's 3 s answer deadline.
        await interaction.response.defer(thinking=True, ephemeral=is_private(interaction))
        chat = user_chat(interaction.user.id)
        if interaction.context.dm_channel and interaction.channel_id is not None:
            await self._adopt_dm_row(interaction.channel_id, chat)
        reply = await self.router.reply(chat, name, arg, locale=str(interaction.locale))
        if not reply.text:  # rate limited and already warned
            await self._discard(interaction)
            return
        messages = self._present(reply)
        if link_in_channel and in_server and name == "subscribe":
            messages.append([discord.Embed(description=tr(reply.lang, "dc.link_warning"))])
        await self._say(interaction, messages[-1], extra=messages[:-1], rows=reply.buttons)

    @staticmethod
    async def _discard(interaction: discord.Interaction[Any]) -> None:
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            log.debug("discord: nothing to delete")

    @staticmethod
    async def _say(
        interaction: discord.Interaction[Any],
        embeds: list[discord.Embed],
        *,
        extra: list[list[discord.Embed]] | None = None,
        rows: tuple[tuple[Button, ...], ...] = (),
    ) -> None:
        ephemeral = is_private(interaction)
        for earlier in extra or []:
            await interaction.followup.send(embeds=earlier, ephemeral=ephemeral)
        kwargs: dict[str, Any] = {"embeds": embeds, "ephemeral": ephemeral}
        view = build_view(rows)
        if view is not None:
            kwargs["view"] = view
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)

    async def handle_button(self, interaction: discord.Interaction[Any], command: str) -> None:
        parsed = parse_button(command)
        if parsed is None:
            log.warning("discord: ignoring unknown button %r", command)
            return
        await self.respond(interaction, *parsed)

    # ------------------------------------------------- DMs and mentions (text)

    def _strip_mentions(self, content: str) -> str:
        me = self.client.user
        if me is not None:
            content = re.sub(rf"<@[!&]?{me.id}>", " ", content)
        return content.strip()

    async def _adopt_dm_row(self, channel_id: int, chat: ChatRef) -> None:
        """Move a row keyed by this DM channel (before per-user timetables) to the user."""
        if channel_id in self._dm_checked:
            return
        await self.router.adopt_chat(ChatRef(PLATFORM, str(channel_id)), chat)
        self._dm_checked.add(channel_id)

    async def handle_message(self, message: discord.Message) -> None:
        """Answer free text sent in a DM or addressed to the bot with a mention.

        In a server a message reply cannot be ephemeral, so the channel only sees a
        short note: the answer goes to the author by DM. If their DMs are closed the
        note points to the slash commands, whose answers only the caller sees.
        """
        if message.author.bot:
            return
        me = self.client.user
        mentioned = me is not None and any(u.id == me.id for u in message.mentions)
        in_server = message.guild is not None
        if in_server and not mentioned:
            return
        text = self._strip_mentions(message.content) or "help"
        parsed = parse_command(text)
        intent = intent_rules.Intent(*parsed) if parsed else intent_rules.match(text)
        chat = user_chat(message.author.id)
        if not in_server:
            await self._adopt_dm_row(message.channel.id, chat)

        async def public(embeds: list[discord.Embed], rows: Rows = ()) -> None:
            kwargs: dict[str, Any] = {"embeds": embeds, "mention_author": False}
            view = build_view(rows)
            if view is not None:
                kwargs["view"] = view
            await message.reply(**kwargs)

        async def deliver(messages: list[tuple[list[discord.Embed], Rows]], lang: str) -> None:
            if not in_server:
                for embeds, rows in messages:
                    await public(embeds, rows)
                return
            try:
                for embeds, rows in messages:
                    kwargs: dict[str, Any] = {"embeds": embeds}
                    view = build_view(rows)
                    if view is not None:
                        kwargs["view"] = view
                    await message.author.send(**kwargs)
            except discord.Forbidden:
                await public([discord.Embed(description=tr(lang, "dc.dm_closed"))])
                return
            note = tr(lang, "dc.answer_in_dm")
            if intent is not None and intent.command == "subscribe":
                note = f"{note}\n\n{tr(lang, 'dc.link_warning')}"
            await public([discord.Embed(description=note)])

        if intent is None:
            # Not personal: the same short list of what the bot can do for everybody.
            reply = await self.router.reply(chat, "help")
            if reply.text:
                await public([render.unknown_embed(reply.lang)], menu_buttons(reply.lang))
            return
        if intent.command == "help" and in_server:
            reply = await self.router.reply(chat, "help", locale=intent.lang)
            if reply.text:
                await public([render.help_embed(reply.lang)], reply.buttons)
            return
        if intent.command == "forget" and not parsed:
            # Deleting data from a loosely worded sentence needs an explicit confirmation.
            reply = await self.router.reply(chat, "help", locale=intent.lang)
            if reply.text:
                embed = discord.Embed(description=tr(reply.lang, "dc.forget_confirm"))
                confirm: Rows = ((Button(tr(reply.lang, "dc.forget_yes"), "/forget"),),)
                await deliver([([embed], confirm)], reply.lang)
            return
        reply = await self.router.reply(chat, intent.command, intent.arg, locale=intent.lang)
        if not reply.text:
            return
        payloads = self._present(reply)
        messages: list[tuple[list[discord.Embed], Rows]] = [(e, ()) for e in payloads[:-1]]
        messages.append((payloads[-1], reply.buttons))
        await deliver(messages, reply.lang)

    # ----------------------------------------------------------- notifications

    async def _target(self, kind: str, ident: int) -> Any:
        found: Any
        try:
            if kind == "user":
                found = self.client.get_user(ident) or await self.client.fetch_user(ident)
            else:
                found = self.client.get_channel(ident) or await self.client.fetch_channel(ident)
        except discord.NotFound:
            raise ChatUnavailable(f"{kind} {ident} no longer exists") from None
        except discord.Forbidden:
            raise ChatUnavailable(f"no access to {kind} {ident}") from None
        if not hasattr(found, "send"):
            raise ChatUnavailable(f"{kind} {ident} cannot receive messages")
        return found

    async def send(self, chat: ChatRef, text: str, view: View | None = None) -> None:
        """Push a notification (reminder, change alert, weekly summary).

        Raises :class:`ChatUnavailable` when the channel or user is gone and
        :class:`NotificationsBlocked` when a user does not accept DMs from the bot.
        """
        kind, ident = parse_target(chat)
        target = await self._target(kind, ident)
        if view is not None:
            messages = [render.view_embeds(view)]
            rows = menu_buttons(view.lang)
        else:
            messages = [[e] for e in render.text_embeds(text)]
            rows = ()
        try:
            for index, embeds in enumerate(messages):
                kwargs: dict[str, Any] = {"embeds": embeds}
                last_view = build_view(rows) if index == len(messages) - 1 else None
                if last_view is not None:
                    kwargs["view"] = last_view
                await target.send(**kwargs)
        except discord.NotFound:
            raise ChatUnavailable(f"{kind} {ident} no longer exists") from None
        except discord.Forbidden:
            if kind == "user":
                raise NotificationsBlocked(f"user {ident} does not accept DMs") from None
            raise ChatUnavailable(f"no permission to post in channel {ident}") from None

    # --------------------------------------------------------------- lifecycle

    async def run(self, stop: asyncio.Event) -> None:
        async with self.client:
            runner = asyncio.create_task(self.client.start(self._token))
            stopper = asyncio.create_task(stop.wait())
            done, _ = await asyncio.wait({runner, stopper}, return_when=asyncio.FIRST_COMPLETED)
            stopper.cancel()
            if runner in done:
                runner.result()  # re-raise login/connection errors
            else:
                await self.client.close()
                runner.cancel()
        log.info("discord: stopped")
