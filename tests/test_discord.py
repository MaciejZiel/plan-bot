from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import discord
import pytest
from discord import app_commands

from plan_bot.adapters import discord_render as render
from plan_bot.adapters.discord import (
    CommandButton,
    DiscordAdapter,
    PlanTranslator,
    SubscribeModal,
    build_view,
    parse_button,
    parse_target,
    user_chat,
)
from plan_bot.commands import COMMANDS, Button, CommandRouter, Reply
from plan_bot.domain import Lesson
from plan_bot.i18n import LANGS, tr
from plan_bot.ratelimit import RateLimiter
from plan_bot.repository import ChatRef, Repository
from plan_bot.service import BotService, ChatUnavailable, NotificationsBlocked
from plan_bot.views import DayView, NextView, ReminderView, WeekView
from tests.conftest import FakeClock, RecordingNotifier, warsaw

USER = 4242
ME = 999


# ------------------------------------------------------------------ test doubles


class FakeResponse:
    def __init__(self) -> None:
        self.deferred: dict[str, Any] | None = None
        self.modal: discord.ui.Modal | None = None
        self.sent: list[dict[str, Any]] = []

    def is_done(self) -> bool:
        return self.deferred is not None or bool(self.sent) or self.modal is not None

    async def defer(self, *, thinking: bool = False, ephemeral: bool = False) -> None:
        self.deferred = {"thinking": thinking, "ephemeral": ephemeral}

    async def send_modal(self, modal: discord.ui.Modal) -> None:
        self.modal = modal

    async def send_message(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


class FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


class FakeInteraction:
    def __init__(
        self,
        *,
        user_id: int = USER,
        guild_id: int | None = 1,
        locale: str = "en-US",
        client: Any = None,
        context: app_commands.AppCommandContext | None = None,
        channel_id: int = 500,
    ) -> None:
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.channel_id = channel_id
        if context is None:
            in_guild = guild_id is not None
            context = app_commands.AppCommandContext(guild=in_guild, dm_channel=not in_guild)
        self.context = context
        self.locale = locale
        self.client = client
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.deleted = False

    async def delete_original_response(self) -> None:
        self.deleted = True


class FakeMessage:
    def __init__(
        self,
        content: str,
        *,
        author_id: int = USER,
        bot: bool = False,
        in_guild: bool = False,
        mentions: tuple[int, ...] = (),
        dms_closed: bool = False,
        channel_id: int = 600,
    ) -> None:
        self.content = content
        self.dms: list[dict[str, Any]] = []
        self.dms_closed = dms_closed
        self.author = SimpleNamespace(id=author_id, bot=bot, send=self._dm)
        self.guild = SimpleNamespace(id=1) if in_guild else None
        self.channel = SimpleNamespace(id=channel_id)
        self.mentions = [SimpleNamespace(id=m) for m in mentions]
        self.replies: list[dict[str, Any]] = []

    async def _dm(self, **kwargs: Any) -> None:
        if self.dms_closed:
            raise forbidden()
        self.dms.append(kwargs)

    async def reply(self, **kwargs: Any) -> None:
        self.replies.append(kwargs)


class FakeRouter:
    def __init__(self, reply: Reply | None = None) -> None:
        self.canned = reply or Reply("ok", lang="en")
        self.calls: list[tuple[ChatRef, str, str | None, str | None]] = []

    async def reply(
        self, chat: ChatRef, name: str, arg: str | None = None, *, locale: str | None = None
    ) -> Reply:
        self.calls.append((chat, name, arg, locale))
        return self.canned

    async def adopt_chat(self, old: ChatRef, new: ChatRef) -> bool:
        return False


class FakeResp:
    def __init__(self, status: int) -> None:
        self.status = status
        self.reason = "x"


def not_found() -> discord.NotFound:
    return discord.NotFound(FakeResp(404), "Unknown Channel")


def forbidden() -> discord.Forbidden:
    return discord.Forbidden(FakeResp(403), "Cannot send messages to this user")


@dataclass
class FakeTarget:
    error: Exception | None = None
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, **kwargs: Any) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(kwargs)


@pytest.fixture
def router(service: BotService) -> CommandRouter:
    return CommandRouter(service)


@pytest.fixture
def adapter(router: CommandRouter) -> DiscordAdapter:
    bot = DiscordAdapter(router, "not-a-real-token")
    bot.client._connection.user = SimpleNamespace(id=ME)  # type: ignore[assignment]
    return bot


def texts(embeds: list[discord.Embed]) -> str:
    parts: list[str] = []
    for e in embeds:
        parts += [e.title or "", e.description or ""]
        parts += [f.name or "" for f in e.fields] + [f.value or "" for f in e.fields]
    return "\n".join(parts)


def labels(view: discord.ui.View) -> list[str]:
    return [getattr(getattr(child, "item", child), "label", "") or "" for child in view.children]


async def slash(
    adapter: DiscordAdapter, name: str, *args: Any, sub: str | None = None, **kw: Any
) -> FakeInteraction:
    interaction = FakeInteraction(**kw)
    command = adapter.tree.get_command(name)
    assert command is not None
    if sub is not None:
        assert isinstance(command, app_commands.Group)
        command = command.get_command(sub)
    assert isinstance(command, app_commands.Command)
    await command.callback(interaction, *args)  # type: ignore[arg-type]
    return interaction


# ----------------------------------------------------------------- command tree


async def test_command_tree_has_every_command_with_options(adapter: DiscordAdapter) -> None:
    commands = {c.name: c for c in adapter.tree.get_commands()}
    expected = {spec.name for spec in COMMANDS if spec.name != "start"}
    assert set(commands) == expected
    assert {"help", "demo", "next", "today", "tomorrow", "week", "subscribe", "lang", "forget"} <= (
        set(commands)
    )
    remind = commands["remind"]
    assert isinstance(remind, app_commands.Group)
    assert {c.name for c in remind.commands} == {"set", "list", "off"}
    subscribe = commands["subscribe"]
    assert isinstance(subscribe, app_commands.Command)
    assert [(p.display_name, p.required) for p in subscribe.parameters] == [("url", False)]
    week = commands["week"]
    assert isinstance(week, app_commands.Command)
    assert [c.value for c in week.parameters[0].choices] == ["this", "next"]
    lang = commands["lang"]
    assert isinstance(lang, app_commands.Command)
    assert [c.value for c in lang.parameters[0].choices] == list(LANGS)


async def test_commands_work_in_dms_and_for_user_installs(adapter: DiscordAdapter) -> None:
    for command in adapter.tree.get_commands():
        assert command.allowed_contexts is not None
        assert command.allowed_contexts.dm_channel
        assert command.allowed_installs is not None
        assert command.allowed_installs.user


async def test_texts_fit_discord_limits_in_every_language(adapter: DiscordAdapter) -> None:
    translator = PlanTranslator()

    async def check(string: app_commands.locale_str, key: str) -> None:
        for locale in (discord.Locale.polish, discord.Locale.american_english):
            text = await translator.translate(string, locale, None)  # type: ignore[arg-type]
            assert text is not None
            assert 1 <= len(text) <= 100, key

    for command in adapter.tree.walk_commands():
        key = command._locale_description.extras["key"]  # type: ignore[union-attr]
        await check(command._locale_description, key)  # type: ignore[arg-type]
        if not isinstance(command, app_commands.Command):
            continue
        for param in command.parameters:
            described = param.description
            if isinstance(described, app_commands.locale_str):
                await check(described, described.extras["key"])


async def test_translator_serves_polish_and_english_only() -> None:
    translator = PlanTranslator()
    text = app_commands.locale_str("Classes today", key="cmd.today")
    ctx: Any = None
    assert await translator.translate(text, discord.Locale.polish, ctx) == "Zajęcia dzisiaj"
    assert await translator.translate(text, discord.Locale.british_english, ctx) == "Classes today"
    assert await translator.translate(text, discord.Locale.german, ctx) is None
    assert (
        await translator.translate(app_commands.locale_str("x"), discord.Locale.polish, ctx) is None
    )


async def test_setup_registers_translator_and_syncs(
    adapter: DiscordAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[object] = []

    async def sync(*, guild: object = None) -> list[int]:
        synced.append(guild)
        return [1, 2]

    monkeypatch.setattr(adapter.tree, "sync", sync)
    await adapter.client.setup_hook()
    assert synced == [None]
    assert isinstance(adapter.tree.translator, PlanTranslator)


async def test_dev_guild_gets_the_commands(router: CommandRouter) -> None:
    bot = DiscordAdapter(router, "not-a-real-token", guild_id=42)
    assert bot.guild is not None
    assert not bot.tree.get_commands()
    assert len(bot.tree.get_commands(guild=bot.guild)) > 10


# ----------------------------------------------------------------- slash replies


async def test_demo_then_next_answers_with_embeds(
    adapter: DiscordAdapter, clock: FakeClock
) -> None:
    demo = await slash(adapter, "demo")
    assert demo.response.deferred == {"thinking": True, "ephemeral": True}
    (saved,) = demo.followup.sent
    assert saved["ephemeral"] is True
    assert "fictional demo timetable" in texts(saved["embeds"])
    assert "Next class" in labels(saved["view"])

    nxt = await slash(adapter, "next")
    (sent,) = nxt.followup.sent
    (embed,) = sent["embeds"]
    assert embed.title == "Next class: Algorithms and Data Structures (lecture)"
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Room"] == "A-101"
    assert fields["Teacher"] == "Prof. Alan Placeholder (fictional)"
    start = int(warsaw(2026, 10, 12, 8, 30).timestamp())
    assert f"<t:{start}:R>" in embed.description
    assert "08:30–10:00" in embed.description
    assert embed.footer.text == "Times in Europe/Warsaw · /help for all commands"
    # the buttons mirror the Telegram keyboard
    assert labels(sent["view"]) == ["Next class", "Today", "Tomorrow", "Week", "Next week"]


async def test_replies_are_public_only_in_dms(adapter: DiscordAdapter) -> None:
    dm = await slash(adapter, "demo", guild_id=None)
    assert dm.response.deferred == {"thinking": True, "ephemeral": False}
    assert dm.followup.sent[0]["ephemeral"] is False


async def test_timetables_belong_to_the_user_not_the_channel(
    adapter: DiscordAdapter, repo: Repository
) -> None:
    await slash(adapter, "demo", user_id=1)
    await slash(adapter, "demo", user_id=2, guild_id=77)
    assert await repo.get(ChatRef("discord", "user:1")) is not None
    assert await repo.get(ChatRef("discord", "user:2")) is not None
    other = await slash(adapter, "today", user_id=3)
    assert "No timetable yet" in texts(other.followup.sent[0]["embeds"])


async def test_locale_picks_the_language_and_lang_overrides_it(
    adapter: DiscordAdapter,
) -> None:
    demo = await slash(adapter, "demo", locale="pl")
    assert "fikcyjny plan" in texts(demo.followup.sent[0]["embeds"])
    today = await slash(adapter, "today", locale="pl")
    assert "Dzisiaj · Poniedziałek, 12 paź" in texts(today.followup.sent[0]["embeds"])
    english = await slash(adapter, "lang", "en", locale="pl")
    assert "Language: English." in texts(english.followup.sent[0]["embeds"])
    again = await slash(adapter, "today", locale="pl")
    assert "Today · Monday, 12 Oct" in texts(again.followup.sent[0]["embeds"])


async def test_day_and_week_embeds(adapter: DiscordAdapter) -> None:
    await slash(adapter, "demo")
    today = (await slash(adapter, "today")).followup.sent[0]["embeds"][0]
    assert today.title == "Today · Monday, 12 Oct"
    assert "**08:30–10:00**  Algorithms and Data Structures (lecture)" in today.description
    assert "A-101 · Prof. Alan Placeholder (fictional)" in today.description
    week = (await slash(adapter, "week", "next")).followup.sent[0]["embeds"][0]
    assert week.title == "Next week"
    assert week.fields[0].name == "Monday, 19 Oct"
    assert "`08:30–10:00` Algorithms and Data Structures (lecture) · A-101" in week.fields[0].value
    assert sum(len(f.value) for f in week.fields) < 5000


async def test_help_embed_lists_commands_and_free_text(adapter: DiscordAdapter) -> None:
    (embed,) = (await slash(adapter, "help")).followup.sent[0]["embeds"]
    assert embed.title == "plan-bot: your timetable"
    assert "`/subscribe <url>`" in embed.fields[0].value
    assert "what's next?" in embed.fields[1].value
    assert len(embed.fields[0].value) <= 1024


async def test_reminder_commands(adapter: DiscordAdapter) -> None:
    await slash(adapter, "demo")
    listed = await slash(adapter, "remind", sub="list")
    assert "15 min before each class" in texts(listed.followup.sent[0]["embeds"])
    await slash(adapter, "remind", 30, sub="set")
    listed = await slash(adapter, "remind", sub="list")
    assert "30 min before" in texts(listed.followup.sent[0]["embeds"])
    await slash(adapter, "remind", sub="off")
    listed = await slash(adapter, "remind", sub="list")
    assert "Reminders are off." in texts(listed.followup.sent[0]["embeds"])


async def test_subscribe_without_a_link_opens_a_private_form(adapter: DiscordAdapter) -> None:
    interaction = await slash(adapter, "subscribe", locale="pl")
    modal = interaction.response.modal
    assert isinstance(modal, SubscribeModal)
    assert modal.title == "Link do Twojego planu"
    assert interaction.response.deferred is None

    modal.link._value = "demo"  # what the user typed into the form
    submit = FakeInteraction()
    await modal.on_submit(submit)  # type: ignore[arg-type]
    assert "Timetable saved" in texts(submit.followup.sent[0]["embeds"])
    assert submit.followup.sent[0]["ephemeral"] is True


async def test_subscribe_with_a_link_in_a_server_warns_that_it_was_visible(
    adapter: DiscordAdapter,
) -> None:
    server = await slash(adapter, "subscribe", "demo")
    first, last = server.followup.sent
    assert "Timetable saved" in texts(first["embeds"])
    assert "visible in the channel" in texts(last["embeds"])
    dm = await slash(adapter, "subscribe", "demo", guild_id=None, user_id=5)
    assert len(dm.followup.sent) == 1


async def test_rate_limited_users_get_one_warning_then_silence(
    service: BotService,
) -> None:
    limited = DiscordAdapter(
        CommandRouter(service, limiter=RateLimiter(burst=1, per_minute=1)), "x"
    )
    first = await slash(limited, "help")
    assert first.followup.sent
    warned = await slash(limited, "help")
    assert "Slow down" in texts(warned.followup.sent[0]["embeds"])
    silent = await slash(limited, "help")
    assert silent.deleted
    assert not silent.followup.sent


async def test_discard_survives_an_already_deleted_response(adapter: DiscordAdapter) -> None:
    class Gone(FakeInteraction):
        async def delete_original_response(self) -> None:
            raise not_found()

    await adapter._discard(Gone())  # type: ignore[arg-type]


async def test_command_errors_answer_politely(adapter: DiscordAdapter) -> None:
    interaction = FakeInteraction(locale="pl")
    await adapter._on_tree_error(interaction, app_commands.AppCommandError("boom"))  # type: ignore[arg-type]
    assert "Coś poszło nie tak" in texts(interaction.response.sent[0]["embeds"])
    after_defer = FakeInteraction()
    await after_defer.response.defer()
    await adapter._on_tree_error(after_defer, app_commands.AppCommandError("boom"))  # type: ignore[arg-type]
    assert "Something went wrong" in texts(after_defer.followup.sent[0]["embeds"])


# ---------------------------------------------------------------------- buttons


@pytest.mark.parametrize(
    ("command", "parsed"),
    [
        ("next", ("next", None)),
        ("week", ("week", None)),
        ("week next", ("week", "next")),
        ("remind 15", ("remind", "15")),
        ("remind off", ("remind", "off")),
        ("lang pl", ("lang", "pl")),
        ("forget", ("forget", None)),
        ("demo", ("demo", None)),
    ],
)
def test_known_buttons_parse(command: str, parsed: tuple[str, str | None]) -> None:
    assert parse_button(command) == parsed


@pytest.mark.parametrize(
    "command",
    ["subscribe http://x", "remind 99999", "lang de", "week later", "next now", "", "status"],
)
def test_unknown_buttons_are_rejected(command: str) -> None:
    assert parse_button(command) is None


async def test_button_layout_follows_the_rows() -> None:
    rows = (
        (Button("A", "/next"), Button("B", "/week next")),
        (Button("C", "/forget"),),
    )
    view = build_view(rows)
    assert view is not None
    assert view.timeout is None
    assert [(c.item.row, c.item.custom_id) for c in view.children] == [  # type: ignore[attr-defined]
        (0, "plan:next"),
        (0, "plan:week next"),
        (1, "plan:forget"),
    ]
    assert build_view(()) is None


async def test_buttons_survive_restarts_through_their_custom_id(adapter: DiscordAdapter) -> None:
    template = CommandButton.__discord_ui_compiled_template__
    found = template.fullmatch("plan:week next")
    assert found is not None
    restored = await CommandButton.from_custom_id(
        FakeInteraction(),  # type: ignore[arg-type]
        discord.ui.Button(label="Next week", custom_id="plan:week next"),
        found,
    )
    assert restored.command == "week next"
    assert restored.item.label == "Next week"
    assert template.fullmatch("plan:Next?") is None


async def test_pressing_a_button_answers_the_presser(adapter: DiscordAdapter) -> None:
    await slash(adapter, "demo", user_id=7)
    button = CommandButton("Next class", "next")
    press = FakeInteraction(user_id=7, client=adapter.client)
    await button.callback(press)  # type: ignore[arg-type]
    assert press.response.deferred == {"thinking": True, "ephemeral": True}
    assert "Next class: " in texts(press.followup.sent[0]["embeds"])

    ignored = FakeInteraction(user_id=7, client=adapter.client)
    await adapter.handle_button(ignored, "subscribe http://evil")  # type: ignore[arg-type]
    assert ignored.response.deferred is None
    stray = FakeInteraction(client=object())
    await button.callback(stray)  # type: ignore[arg-type]
    assert stray.response.deferred is None


# --------------------------------------------------------------- DMs / mentions


async def test_dm_question_gets_an_embed_reply(adapter: DiscordAdapter) -> None:
    await slash(adapter, "demo", guild_id=None)
    message = FakeMessage("kiedy mam następne zajęcia?")
    await adapter.handle_message(message)  # type: ignore[arg-type]
    (reply,) = message.replies
    assert reply["mention_author"] is False
    assert "Następne zajęcia" not in texts(reply["embeds"])  # the stored language is English
    assert "Next class: Algorithms and Data Structures (lecture)" in texts(reply["embeds"])
    assert "Tomorrow" in labels(reply["view"])


async def test_polish_wording_sets_the_language_of_a_new_user(
    adapter: DiscordAdapter,
) -> None:
    await adapter.handle_message(FakeMessage("pokaż demo", author_id=11))  # type: ignore[arg-type]
    message = FakeMessage("co mam jutro", author_id=11)
    await adapter.handle_message(message)  # type: ignore[arg-type]
    assert "Jutro · Wtorek, 13 paź" in texts(message.replies[0]["embeds"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("co mam dzisiaj", "Today · Monday, 12 Oct"),
        ("what do I have tomorrow", "Tomorrow · Tuesday, 13 Oct"),
        ("plan na tydzień", "This week"),
        ("plan na przyszły tydzień", "Next week"),
        ("what's next", "Next class: "),
        ("remind me 30 min before class", "I will remind you 30 min before each class."),
        ("/today", "Today · Monday, 12 Oct"),
        ("status", "Feed: bundled fictional demo timetable"),
    ],
)
async def test_free_text_is_mapped_to_commands(
    adapter: DiscordAdapter, text: str, expected: str
) -> None:
    await slash(adapter, "demo", guild_id=None)
    message = FakeMessage(text)
    await adapter.handle_message(message)  # type: ignore[arg-type]
    assert expected in texts(message.replies[0]["embeds"])


async def test_mentions_work_in_servers_without_the_message_content_intent(
    adapter: DiscordAdapter,
) -> None:
    await slash(adapter, "demo")
    message = FakeMessage(f"<@{ME}> co mam jutro?", in_guild=True, mentions=(ME,))
    await adapter.handle_message(message)  # type: ignore[arg-type]
    assert "Tomorrow" in texts(message.dms[0]["embeds"])
    bare = FakeMessage(f"<@!{ME}>", in_guild=True, mentions=(ME,))
    await adapter.handle_message(bare)  # type: ignore[arg-type]
    assert bare.replies[0]["embeds"][0].title == "plan-bot: your timetable"


async def test_mentions_in_servers_never_show_the_timetable_publicly(
    adapter: DiscordAdapter,
) -> None:
    await slash(adapter, "demo")
    for text in ("what's next", "co mam dzisiaj", "plan na tydzień", "status", "przypomnienia"):
        message = FakeMessage(f"<@{ME}> {text}", in_guild=True, mentions=(ME,))
        await adapter.handle_message(message)  # type: ignore[arg-type]
        (note,) = message.replies
        public = texts(note["embeds"])
        assert "direct message" in public
        assert "Algorithms" not in public
        assert "A-101" not in public
        assert "view" not in note
        assert message.dms, text


async def test_mentions_with_closed_dms_point_to_slash_commands(
    adapter: DiscordAdapter,
) -> None:
    await slash(adapter, "demo")
    message = FakeMessage(f"<@{ME}> what's next", in_guild=True, mentions=(ME,), dms_closed=True)
    await adapter.handle_message(message)  # type: ignore[arg-type]
    (note,) = message.replies
    public = texts(note["embeds"])
    assert "/next" in public
    assert "Algorithms" not in public
    forget = FakeMessage(f"<@{ME}> delete my data", in_guild=True, mentions=(ME,))
    await adapter.handle_message(forget)  # type: ignore[arg-type]
    assert "Confirm?" in texts(forget.dms[0]["embeds"])
    assert "Confirm?" not in texts(forget.replies[0]["embeds"])


async def test_answers_are_private_outside_the_bots_own_dm(adapter: DiscordAdapter) -> None:
    group_dm = await slash(
        adapter,
        "demo",
        guild_id=None,
        context=app_commands.AppCommandContext(private_channel=True),
    )
    assert group_dm.response.deferred == {"thinking": True, "ephemeral": True}
    assert group_dm.followup.sent[0]["ephemeral"] is True
    unknown = await slash(adapter, "help", context=app_commands.AppCommandContext())
    assert unknown.response.deferred == {"thinking": True, "ephemeral": True}


async def test_rows_keyed_by_a_dm_channel_move_to_the_user(
    adapter: DiscordAdapter, repo: Repository
) -> None:
    await repo.update(ChatRef("discord", "777"), ics_url="demo", reminder_minutes=30)
    await slash(adapter, "status", guild_id=None, channel_id=777)
    assert await repo.get(ChatRef("discord", "777")) is None
    moved = await repo.get(user_chat(USER))
    assert moved is not None
    assert moved.reminder_minutes == 30
    # a channel row in a server is shared and stays where it is
    await repo.update(ChatRef("discord", "888"), ics_url="demo")
    await slash(adapter, "status", guild_id=5, channel_id=888)
    assert await repo.get(ChatRef("discord", "888")) is not None
    # free text in a DM moves it too; an existing user row wins over the old one
    await repo.update(ChatRef("discord", "999"), ics_url="demo")
    await adapter.handle_message(FakeMessage("status", channel_id=999))  # type: ignore[arg-type]
    assert await repo.get(ChatRef("discord", "999")) is None
    assert (await repo.get(user_chat(USER))) is not None


async def test_chatter_in_servers_and_from_bots_is_ignored(adapter: DiscordAdapter) -> None:
    for message in (
        FakeMessage("what's next", in_guild=True),
        FakeMessage("what's next", in_guild=True, mentions=(5,)),
        FakeMessage("what's next", bot=True),
    ):
        await adapter.handle_message(message)  # type: ignore[arg-type]
        assert not message.replies
    assert "guild_messages" in str([n for n, v in adapter.client.intents if v])
    assert not adapter.client.intents.message_content
    assert not adapter.client.intents.members


async def test_unknown_text_lists_what_the_bot_can_do(adapter: DiscordAdapter) -> None:
    message = FakeMessage("asdf qwerty")
    await adapter.handle_message(message)  # type: ignore[arg-type]
    (reply,) = message.replies
    assert "ask for the next class, today, tomorrow or the week" in texts(reply["embeds"])
    assert "Next class" in labels(reply["view"])


async def test_deleting_data_from_free_text_needs_a_confirmation(
    adapter: DiscordAdapter, repo: Repository
) -> None:
    await slash(adapter, "demo", guild_id=None)
    message = FakeMessage("usuń moje dane")
    await adapter.handle_message(message)  # type: ignore[arg-type]
    (reply,) = message.replies
    assert "Confirm?" in texts(reply["embeds"])
    assert await repo.get(user_chat(USER)) is not None
    assert reply["view"].children[0].item.custom_id == "plan:forget"
    press = FakeInteraction(client=adapter.client, guild_id=None)
    await adapter.handle_button(press, "forget")  # type: ignore[arg-type]
    assert await repo.get(user_chat(USER)) is None


async def test_a_link_in_a_message_subscribes_and_warns_in_servers(
    adapter: DiscordAdapter,
) -> None:
    message = FakeMessage(f"<@{ME}> demo", in_guild=True, mentions=(ME,))
    await adapter.handle_message(message)  # type: ignore[arg-type]
    assert "Timetable saved" in texts(message.dms[0]["embeds"])
    (note,) = message.replies
    assert "visible" not in texts(note["embeds"])  # "demo" is not a link: no warning

    router = FakeRouter(Reply("Timetable saved.", lang="en"))
    other = DiscordAdapter(router, "x")
    other.client._connection.user = SimpleNamespace(id=ME)  # type: ignore[assignment]
    linked = FakeMessage(f"<@{ME}> https://uni.example/a.ics", in_guild=True, mentions=(ME,))
    await other.handle_message(linked)  # type: ignore[arg-type]
    assert router.calls[0][1:3] == ("subscribe", "https://uni.example/a.ics")
    assert "Timetable saved" in texts(linked.dms[0]["embeds"])
    (note,) = linked.replies
    assert "visible in the channel" in texts(note["embeds"])


async def test_silent_replies_send_nothing(service: BotService) -> None:
    router = FakeRouter(Reply(""))
    bot = DiscordAdapter(router, "x")
    for text in ("what's next", "asdf", "forget me"):
        message = FakeMessage(text)
        await bot.handle_message(message)  # type: ignore[arg-type]
        assert not message.replies


# ---------------------------------------------------------------- notifications


async def test_reminders_are_sent_as_embeds_by_dm(
    adapter: DiscordAdapter,
    service: BotService,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dm = FakeTarget()
    users = {USER: dm}

    async def fetch_user(user_id: int) -> FakeTarget:
        return users[user_id]

    monkeypatch.setattr(adapter.client, "fetch_user", fetch_user)
    service.notifier = adapter
    await service.set_feed(user_chat(USER), "demo")
    clock.now = warsaw(2026, 10, 12, 8, 20)
    assert await service.send_due_reminders(clock.now) == 1
    (sent,) = dm.sent
    (embed,) = sent["embeds"]
    assert embed.title == "Reminder: Algorithms and Data Structures (lecture)"
    assert {f.name: f.value for f in embed.fields}["Room"] == "A-101"
    assert "Today" in labels(sent["view"])


async def test_plain_notifications_are_embeds_too(
    adapter: DiscordAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = FakeTarget()
    monkeypatch.setattr(adapter.client, "get_user", lambda _id: target)
    await adapter.send(user_chat(5), "Timetable changed:\n- something")
    assert target.sent[0]["embeds"][0].description.startswith("Timetable changed")
    assert "view" not in target.sent[0]
    await adapter.send(user_chat(5), "x" * 9000)
    assert len(target.sent) == 4  # 1 + three chunks of at most 4096


async def test_legacy_channel_rows_still_receive_messages(
    adapter: DiscordAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = FakeTarget()
    monkeypatch.setattr(adapter.client, "get_channel", lambda cid: channel if cid == 3 else None)
    await adapter.send(ChatRef("discord", "3"), "hello")
    await adapter.send(ChatRef("discord", "channel:3"), "again")
    assert len(channel.sent) == 2


@pytest.mark.parametrize(
    ("chat_id", "expected"),
    [("user:5", ("user", 5)), ("channel:6", ("channel", 6)), ("7", ("channel", 7))],
)
def test_parse_target(chat_id: str, expected: tuple[str, int]) -> None:
    assert parse_target(ChatRef("discord", chat_id)) == expected


@pytest.mark.parametrize("chat_id", ["abc", "user:x", "guild:1", "user:", ":1"])
def test_parse_target_rejects_garbage(chat_id: str) -> None:
    with pytest.raises(ChatUnavailable):
        parse_target(ChatRef("discord", chat_id))


async def test_closed_dms_block_notifications_but_deleted_targets_are_gone(
    adapter: DiscordAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = FakeTarget(error=forbidden())
    monkeypatch.setattr(adapter.client, "get_user", lambda _id: closed)
    with pytest.raises(NotificationsBlocked):
        await adapter.send(user_chat(1), "hi")

    muted = FakeTarget(error=forbidden())
    monkeypatch.setattr(adapter.client, "get_channel", lambda _id: muted)
    with pytest.raises(ChatUnavailable):
        await adapter.send(ChatRef("discord", "9"), "hi")

    deleted = FakeTarget(error=not_found())
    monkeypatch.setattr(adapter.client, "get_channel", lambda _id: deleted)
    with pytest.raises(ChatUnavailable):
        await adapter.send(ChatRef("discord", "9"), "hi")

    async def missing(_id: int) -> object:
        raise not_found()

    monkeypatch.setattr(adapter.client, "get_user", lambda _id: None)
    monkeypatch.setattr(adapter.client, "fetch_user", missing)
    with pytest.raises(ChatUnavailable):
        await adapter.send(user_chat(2), "hi")

    async def hidden(_id: int) -> object:
        raise forbidden()

    monkeypatch.setattr(adapter.client, "get_channel", lambda _id: None)
    monkeypatch.setattr(adapter.client, "fetch_channel", hidden)
    with pytest.raises(ChatUnavailable):
        await adapter.send(ChatRef("discord", "9"), "hi")

    async def category(_id: int) -> object:
        return object()

    monkeypatch.setattr(adapter.client, "fetch_channel", category)
    with pytest.raises(ChatUnavailable, match="cannot receive"):
        await adapter.send(ChatRef("discord", "9"), "hi")


async def test_a_deleted_channel_is_cleaned_up_instead_of_retried_forever(
    adapter: DiscordAdapter,
    service: BotService,
    repo: Repository,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ChatRef("discord", "555")  # a row from before timetables were per user
    await service.set_feed(chat, "demo")
    service.notifier = adapter

    async def missing(_id: int) -> object:
        raise not_found()

    monkeypatch.setattr(adapter.client, "get_channel", lambda _id: None)
    monkeypatch.setattr(adapter.client, "fetch_channel", missing)
    clock.now = warsaw(2026, 10, 12, 8, 20)
    await service.send_due_reminders(clock.now)
    assert await repo.get(chat) is None


async def test_a_user_with_closed_dms_keeps_the_timetable_but_loses_pushes(
    adapter: DiscordAdapter,
    service: BotService,
    repo: Repository,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = user_chat(USER)
    await service.set_feed(chat, "demo")
    service.notifier = adapter
    monkeypatch.setattr(adapter.client, "get_user", lambda _id: FakeTarget(error=forbidden()))
    clock.now = warsaw(2026, 10, 12, 8, 20)
    await service.send_due_reminders(clock.now)
    sub = await repo.get(chat)
    assert sub is not None
    assert sub.reminder_minutes == 0
    assert not sub.weekly_summary
    today = await slash(adapter, "today")  # slash commands keep working
    assert "08:30" in texts(today.followup.sent[0]["embeds"])


# --------------------------------------------------------------------- rendering


def lesson(hour: int, summary: str = "Maths", **kw: Any) -> Lesson:
    base: dict[str, Any] = {
        "key": f"k{hour}{summary}",
        "uid": "u",
        "start": warsaw(2026, 10, 12, hour),
        "end": warsaw(2026, 10, 12, hour + 1),
        "summary": summary,
    }
    return Lesson(**{**base, **kw})


def test_empty_day_and_cancelled_lessons() -> None:
    now = warsaw(2026, 10, 12, 7)
    empty = DayView("Today", now.date(), (), "pl", now.tzinfo, now)  # type: ignore[arg-type]
    assert "Brak zajęć" in render.day_embed(empty).description  # type: ignore[operator]
    busy = DayView(
        "Today",
        now.date(),
        (lesson(8, cancelled=True, location="B2"), lesson(9, groups=("L1", "L2"))),
        "en",
        now.tzinfo,  # type: ignore[arg-type]
        now,
    )
    body = render.day_embed(busy).description or ""
    assert "~~**08:00–09:00**  Maths~~ **CANCELLED**" in body
    assert "<t:" in body.split("\n\n")[1]
    assert "L1, L2" in body
    assert "<t:" not in body.split("\n\n")[0]  # cancelled classes show no countdown


def test_a_very_long_day_is_cut_with_a_count() -> None:
    now = warsaw(2026, 10, 12, 7)
    many = tuple(
        replace(lesson(8), key=f"k{i}", summary="Long subject " * 8 + str(i)) for i in range(80)
    )
    embed = render.day_embed(DayView("Today", now.date(), many, "en", now.tzinfo, now))  # type: ignore[arg-type]
    assert len(embed.description or "") <= 4096
    assert (embed.description or "").endswith("more")


def test_a_packed_week_stays_below_the_message_limit() -> None:
    now = warsaw(2026, 10, 12, 7)
    days = {
        now.date() + timedelta(days=i): [
            replace(lesson(8), key=f"{i}-{n}", summary="A fairly long subject name " * 3)
            for n in range(40)
        ]
        for i in range(7)
    }
    embed = render.week_embed(WeekView("This week", days, "en", now.tzinfo, now))  # type: ignore[arg-type]
    assert len(embed) <= 6000
    assert all(len(f.value or "") <= 1024 for f in embed.fields)
    assert "more" in (embed.fields[0].value or "")


def test_empty_week_says_so() -> None:
    now = warsaw(2026, 10, 12, 7)
    days: dict[date, list[Lesson]] = {now.date() + timedelta(days=i): [] for i in range(7)}
    embed = render.week_embed(WeekView("This week", days, "en", now.tzinfo, now))  # type: ignore[arg-type]
    assert "No classes this week." in (embed.description or "")
    assert not embed.fields


def test_next_with_a_running_class_and_without_any() -> None:
    from plan_bot.timetable import NextClass

    now = warsaw(2026, 10, 12, 8, 30)
    tz: Any = now.tzinfo
    running = NextView(NextClass(lesson(8, location="A1"), lesson(10)), "en", tz, now)
    current, upcoming = render.next_embeds(running)
    assert current.title == "In progress now: Maths"
    assert "ends <t:" in (current.description or "")
    assert upcoming.title == "Next class: Maths"
    assert upcoming.footer.text
    none = render.next_embeds(NextView(NextClass(None, None), "pl", tz, now))
    assert none[0].description == tr("pl", "no_upcoming")


def test_reminder_embed() -> None:
    now = warsaw(2026, 10, 12, 7, 45)
    embed = render.reminder_embed(ReminderView(lesson(8, location="C3"), "pl", now.tzinfo, now))  # type: ignore[arg-type]
    assert embed.title == "Przypomnienie: Maths"
    assert embed.fields[0].name == "Sala"
    assert render.view_embeds(ReminderView(lesson(8), "en", now.tzinfo, now))  # type: ignore[arg-type]


def test_text_embeds_split_long_text() -> None:
    parts = render.text_embeds("line\n" * 2000)
    assert len(parts) == 3
    assert all(len(p.description or "") <= 4096 for p in parts)


# -------------------------------------------------------------------- lifecycle


async def test_run_stops_and_propagates_errors(
    adapter: DiscordAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
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


async def test_client_forwards_messages_to_the_adapter(
    adapter: DiscordAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[object] = []

    async def handle(message: object) -> None:
        seen.append(message)

    monkeypatch.setattr(adapter, "handle_message", handle)
    marker = FakeMessage("hi")
    await adapter.client.on_message(marker)  # type: ignore[arg-type]
    assert seen == [marker]


async def test_notifier_protocol_is_satisfied(adapter: DiscordAdapter) -> None:
    sink = RecordingNotifier()
    assert adapter.supports_views
    assert hasattr(sink, "send")
