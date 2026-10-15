"""Turn plan-bot results into Discord embeds.

Relative times use Discord's own ``<t:unix:R>`` markup: the client renders
"in 25 minutes" in the reader's language and keeps it ticking.
"""

from __future__ import annotations

from datetime import datetime, tzinfo

import discord

from plan_bot.commands import COMMANDS, split_message
from plan_bot.domain import Lesson
from plan_bot.formatting import day_label, short_day, span
from plan_bot.i18n import tr
from plan_bot.views import DayView, NextView, ReminderView, View, WeekView

BLUE = 0x5865F2
GREEN = 0x3BA55D
AMBER = 0xFAA61A
RED = 0xED4245

DESCRIPTION_LIMIT = 4096
TITLE_LIMIT = 256
FIELD_LIMIT = 1024
#: Seven day fields must stay below the 6000 characters Discord allows per message.
WEEK_FIELD_LIMIT = 700


def relative(moment: datetime) -> str:
    """Discord markup that renders as "in 25 minutes" / "5 minutes ago"."""
    return f"<t:{int(moment.timestamp())}:R>"


def _tz_name(tz: tzinfo) -> str:
    return getattr(tz, "key", None) or str(tz)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _footer(embed: discord.Embed, lang: str, tz: tzinfo) -> discord.Embed:
    return embed.set_footer(text=tr(lang, "dc.footer", tz=_tz_name(tz)))


def _details(lesson: Lesson) -> str:
    parts = [p for p in (lesson.location, lesson.teacher, ", ".join(lesson.groups)) if p]
    return " · ".join(parts)


def _lesson_block(lesson: Lesson, tz: tzinfo, lang: str, *, with_relative: bool) -> str:
    title = f"**{span(lesson, tz)}**  {lesson.summary}"
    if lesson.cancelled:
        title = f"~~{title}~~ **{tr(lang, 'ch.cancelled')}**"
    detail = _details(lesson)
    if with_relative and not lesson.cancelled:
        when = relative(lesson.start)
        detail = f"{detail} · {when}" if detail else when
    return f"{title}\n{detail}" if detail else title


def _title(text: str) -> str:
    """Feed texts (subjects) can be long; Discord rejects titles over 256 characters."""
    return _clip(text, TITLE_LIMIT)


def _lesson_fields(embed: discord.Embed, lesson: Lesson, lang: str) -> None:
    fields = [
        ("dc.room", lesson.location),
        ("dc.teacher", lesson.teacher),
        ("dc.groups", ", ".join(lesson.groups)),
    ]
    for key, value in fields:
        if value.strip():
            embed.add_field(name=tr(lang, key), value=_clip(value, FIELD_LIMIT), inline=True)


def day_embed(view: DayView) -> discord.Embed:
    lang = view.lang
    heading = f"{view.title} · {day_label(view.day, lang)}"
    if not view.lessons:
        embed = discord.Embed(title=heading, description=tr(lang, "no_classes_day"), colour=BLUE)
        return _footer(embed, lang, view.tz)
    blocks: list[str] = []
    for index, lesson in enumerate(view.lessons):
        blocks.append(_lesson_block(lesson, view.tz, lang, with_relative=lesson.end > view.now))
        if len("\n\n".join(blocks)) > DESCRIPTION_LIMIT - 60:
            blocks.pop()
            blocks.append(tr(lang, "dc.more", n=len(view.lessons) - index))
            break
    embed = discord.Embed(title=heading, description="\n\n".join(blocks), colour=BLUE)
    return _footer(embed, lang, view.tz)


def week_embed(view: WeekView) -> discord.Embed:
    lang = view.lang
    first, last = min(view.days), max(view.days)
    count = sum(1 for lessons in view.days.values() for les in lessons if not les.cancelled)
    header = tr(
        lang,
        "week_header",
        title=view.title,
        first=short_day(first, lang),
        last=short_day(last, lang),
        count=count,
    )
    embed = discord.Embed(title=view.title, colour=BLUE)
    embed.description = header if count else f"{header}\n{tr(lang, 'no_classes_week')}"
    for day in sorted(view.days):
        lessons = view.days[day]
        if not lessons:
            continue
        lines: list[str] = []
        used = 0
        for index, lesson in enumerate(lessons):
            line = f"`{span(lesson, view.tz)}` {lesson.summary}"
            if lesson.cancelled:
                line = f"~~{line}~~ **{tr(lang, 'ch.cancelled')}**"
            if lesson.location:
                line += f" · {lesson.location}"
            if used + len(line) + 1 > WEEK_FIELD_LIMIT:
                lines.append(tr(lang, "dc.more", n=len(lessons) - index))
                break
            lines.append(line)
            used += len(line) + 1
        embed.add_field(name=day_label(day, lang), value="\n".join(lines), inline=False)
    return _footer(embed, lang, view.tz)


def next_embeds(view: NextView) -> list[discord.Embed]:
    lang, tz = view.lang, view.tz
    embeds: list[discord.Embed] = []
    current = view.info.current
    if current is not None:
        now_embed = discord.Embed(
            title=_title(f"{tr(lang, 'dc.in_progress')}: {current.summary}"),
            description=f"**{span(current, tz)}** · {tr(lang, 'dc.ends')} {relative(current.end)}",
            colour=GREEN,
        )
        _lesson_fields(now_embed, current, lang)
        embeds.append(now_embed)
    upcoming = view.info.upcoming
    if upcoming is None:
        embed = discord.Embed(
            title=tr(lang, "dc.next"), description=tr(lang, "no_upcoming"), colour=BLUE
        )
        embeds.append(embed)
    else:
        when = upcoming.start.astimezone(tz)
        embed = discord.Embed(
            title=_title(f"{tr(lang, 'dc.next')}: {upcoming.summary}"),
            description=(
                f"{short_day(when.date(), lang)}, **{span(upcoming, tz)}**\n"
                f"{tr(lang, 'dc.starts')} {relative(upcoming.start)}"
            ),
            colour=BLUE,
        )
        _lesson_fields(embed, upcoming, lang)
        embeds.append(embed)
    _footer(embeds[-1], lang, tz)
    return embeds


def reminder_embed(view: ReminderView) -> discord.Embed:
    lesson, lang = view.lesson, view.lang
    if view.at_start:
        title = f"{tr(lang, 'dc.started')}: {lesson.summary}"
        description = f"**{span(lesson, view.tz)}**"
    else:
        title = f"{tr(lang, 'dc.reminder')}: {lesson.summary}"
        description = (
            f"**{span(lesson, view.tz)}** · {tr(lang, 'dc.starts')} {relative(lesson.start)}"
        )
    embed = discord.Embed(title=_title(title), description=description, colour=AMBER)
    _lesson_fields(embed, lesson, lang)
    return _footer(embed, lang, view.tz)


def view_embeds(view: View) -> list[discord.Embed]:
    embeds = _view_embeds(view)
    warning = getattr(view, "warning", "")
    if warning:
        embeds.append(discord.Embed(description=warning, colour=AMBER))
    return embeds


def _view_embeds(view: View) -> list[discord.Embed]:
    match view:
        case DayView():
            return [day_embed(view)]
        case WeekView():
            return [week_embed(view)]
        case NextView():
            return next_embeds(view)
        case ReminderView():
            return [reminder_embed(view)]


def text_embeds(text: str, *, colour: int = BLUE) -> list[discord.Embed]:
    """A plain text answer as embeds (a description holds 4096 characters)."""
    return [
        discord.Embed(description=part, colour=colour)
        for part in split_message(text, DESCRIPTION_LIMIT)
    ]


def help_embed(lang: str) -> discord.Embed:
    embed = discord.Embed(
        title=tr(lang, "dc.help_title"),
        description=f"{tr(lang, 'start')}\n\n{tr(lang, 'help_intro')}",
        colour=BLUE,
    )
    lines = []
    for spec in COMMANDS:
        if spec.name == "start":
            continue
        usage = f"/{spec.name}" + (f" <{spec.arg}>" if spec.arg else "")
        lines.append(f"`{usage}` {spec.describe(lang)}")
    embed.add_field(name=tr(lang, "help_commands"), value=_clip("\n".join(lines), FIELD_LIMIT))
    embed.add_field(name="\u200b", value=tr(lang, "dc.help_ask"), inline=False)
    embed.set_footer(text=tr(lang, "dc.privacy"))
    return embed


def unknown_embed(lang: str) -> discord.Embed:
    return discord.Embed(description=tr(lang, "nl.unknown"), colour=BLUE)
