"""Discord adapter: slash commands generated from the shared command table."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

import discord
from discord import app_commands

from plan_bot.commands import COMMANDS, CommandSpec, split_message
from plan_bot.repository import ChatRef

log = logging.getLogger(__name__)

PLATFORM = "discord"
MESSAGE_LIMIT = 2000


class Router(Protocol):
    async def handle(self, chat: ChatRef, name: str, arg: str | None = None) -> str: ...


class Messageable(Protocol):
    async def send(self, content: str) -> Any: ...


class DiscordAdapter:
    platform = PLATFORM

    def __init__(self, router: Router, token: str, *, guild_id: int | None = None) -> None:
        self.router = router
        self._token = token
        self.guild = discord.Object(id=guild_id) if guild_id else None
        # Slash commands need no privileged intents; "guilds" keeps the channel cache.
        intents = discord.Intents.none()
        intents.guilds = True
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        for spec in COMMANDS:
            self.tree.add_command(self._command(spec), guild=self.guild)
        self.client.setup_hook = self._setup_hook  # type: ignore[method-assign]

    async def _setup_hook(self) -> None:
        synced = await self.tree.sync(guild=self.guild)
        log.info("discord: synced %d slash commands", len(synced))

    def _command(self, spec: CommandSpec) -> app_commands.Command[Any, ..., None]:
        respond = self.respond
        callback: Callable[..., Coroutine[Any, Any, None]]
        if spec.arg is None:

            async def no_arg(interaction: discord.Interaction) -> None:
                await respond(interaction, spec.name, None)

            callback = no_arg
        elif spec.arg_required:

            async def required(interaction: discord.Interaction, value: str) -> None:
                await respond(interaction, spec.name, value)

            callback = required
        else:

            async def optional(interaction: discord.Interaction, value: str | None = None) -> None:
                await respond(interaction, spec.name, value)

            callback = optional

        if spec.arg is not None:
            callback = app_commands.rename(value=spec.arg)(callback)
            callback = app_commands.describe(value=spec.arg_help or spec.arg)(callback)
        return app_commands.Command(name=spec.name, description=spec.description, callback=callback)

    async def respond(self, interaction: discord.Interaction, name: str, arg: str | None) -> None:
        # Downloading a feed can take longer than Discord's 3 s answer deadline.
        await interaction.response.defer(thinking=True)
        chat = ChatRef(PLATFORM, str(interaction.channel_id))
        reply = await self.router.handle(chat, name, arg)
        for part in split_message(reply, MESSAGE_LIMIT):
            await interaction.followup.send(part)

    async def _channel(self, chat_id: int) -> Messageable:
        channel = self.client.get_channel(chat_id)
        if channel is None:
            channel = await self.client.fetch_channel(chat_id)
        if not hasattr(channel, "send"):
            raise TypeError(f"channel {chat_id} cannot receive messages")
        return channel  # type: ignore[return-value]

    async def send(self, chat: ChatRef, text: str) -> None:
        channel = await self._channel(int(chat.chat_id))
        for part in split_message(text, MESSAGE_LIMIT):
            await channel.send(part)

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
