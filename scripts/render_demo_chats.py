"""Render mock chat transcripts for the README screenshots.

The replies are produced by the real BotService (bundled fictional timetable,
fixed clock); only the chat "window" around them is a static HTML mock-up.

    uv run python scripts/render_demo_chats.py docs/screenshots
    # then screenshot docs/screenshots/*.html with Playwright
"""

from __future__ import annotations

import asyncio
import html
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from plan_bot.commands import CommandRouter
from plan_bot.config import Settings
from plan_bot.db import create_engine, migrate, session_factory
from plan_bot.fetch import demo_calendar
from plan_bot.repository import ChatRef, Repository
from plan_bot.service import BotService

TZ = ZoneInfo("Europe/Warsaw")
FEED = "https://timetable.example.edu/ical/your-personal-token.ics"

# Edits applied to the fictional feed to demonstrate change alerts.
EDITS = """BEGIN:VEVENT
UID:os-lab-l1@northbridge.example
RECURRENCE-ID;TZID=Europe/Warsaw:20261014T104500
DTSTART;TZID=Europe/Warsaw:20261014T104500
DTEND;TZID=Europe/Warsaw:20261014T121500
SUMMARY:Operating Systems (lab)
LOCATION:Lab 312
CATEGORIES:L1
END:VEVENT
BEGIN:VEVENT
UID:dm-ex-c1@northbridge.example
RECURRENCE-ID;TZID=Europe/Warsaw:20261015T160000
DTSTART;TZID=Europe/Warsaw:20261015T160000
DTEND;TZID=Europe/Warsaw:20261015T173000
SUMMARY:Discrete Mathematics (exercises)
CATEGORIES:C1
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""


@dataclass
class Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


class Feeds:
    def __init__(self) -> None:
        self.edited = False

    async def fetch(self, url: str) -> bytes:
        data = demo_calendar().decode()
        if self.edited:
            data = data.replace("END:VCALENDAR", EDITS.replace("\n", "\r\n"), 1)
        return data.encode()


@dataclass
class Bubble:
    sender: str  # "user" | "bot"
    text: str
    time: datetime


class Recorder:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.bubbles: list[Bubble] = []
        self.platform = "telegram"

    async def send(self, chat: ChatRef, text: str) -> None:
        if chat.platform == self.platform:
            self.bubbles.append(Bubble("bot", text, self.clock.now))


async def transcripts(workdir: Path) -> tuple[list[Bubble], list[Bubble]]:
    url = f"sqlite+aiosqlite:///{workdir / 'demo.db'}"
    await migrate(url)
    engine = create_engine(url)
    clock = Clock(datetime(2026, 10, 12, 7, 41, tzinfo=TZ))
    feeds = Feeds()
    recorder = Recorder(clock)
    service = BotService(
        Repository(session_factory(engine)),
        feeds,
        Settings(database_url=url, timezone=TZ),
        clock=clock,
        notifier=recorder,
    )
    router = CommandRouter(service)
    tg = ChatRef("telegram", "1")

    async def say(chat: ChatRef, text: str) -> None:
        recorder.bubbles.append(Bubble("user", text, clock.now))
        reply = await router.handle_text(chat, text)
        recorder.bubbles.append(Bubble("bot", reply or "", clock.now))
        clock.now += timedelta(seconds=40)

    await say(tg, f"/setfeed {FEED}")
    await say(tg, "/filter L1,C1")
    await say(tg, "/today")
    await say(tg, "/next")
    clock.now = datetime(2026, 10, 12, 8, 15, tzinfo=TZ)
    await service.send_due_reminders(clock.now)
    clock.now = datetime(2026, 10, 12, 13, 2, tzinfo=TZ)
    feeds.edited = True
    await service.refresh_due(clock.now)
    telegram = recorder.bubbles
    recorder.bubbles = []
    recorder.platform = "discord"

    dc = ChatRef("discord", "2")
    clock.now = datetime(2026, 10, 13, 9, 5, tzinfo=TZ)
    await say(dc, "/setfeed demo")
    await say(dc, "/filter L2,C2")
    await say(dc, "/tomorrow")
    clock.now = datetime(2026, 10, 18, 18, 0, tzinfo=TZ)
    await service.send_weekly_summaries(clock.now)
    discord = recorder.bubbles
    await engine.dispose()
    return telegram, discord


BANNER = (
    '<div class="banner">DEMO · mock-up rendered from real bot output · '
    "fictional timetable (no real university data)</div>"
)


def telegram_html(bubbles: list[Bubble]) -> str:
    rows = []
    for b in bubbles:
        rows.append(
            f'<div class="msg {b.sender}"><pre>{html.escape(b.text)}</pre>'
            f'<span class="time">{b.time:%H:%M}</span></div>'
        )
    return f"""<!doctype html><meta charset="utf-8"><title>Telegram demo</title>
<style>
body{{margin:0;background:#cfdcc4;font:15px/1.35 -apple-system,"Segoe UI",Roboto,sans-serif}}
.window{{width:560px;margin:0 auto;background:#a8c49a;min-height:100vh}}
.head{{background:#fff;padding:10px 16px;border-bottom:1px solid #ddd;display:flex;gap:12px;align-items:center}}
.avatar{{width:40px;height:40px;border-radius:50%;background:#3d9be9;color:#fff;display:grid;place-items:center;font-weight:700}}
.name{{font-weight:600}} .sub{{color:#7a8a99;font-size:13px}}
.banner{{background:#fff3cd;color:#6b5200;font-size:12px;text-align:center;padding:6px}}
.chat{{padding:12px 14px;display:flex;flex-direction:column;gap:6px}}
.msg{{max-width:82%;padding:7px 10px 18px;border-radius:12px;position:relative;box-shadow:0 1px 1px rgba(0,0,0,.12)}}
.msg.bot{{background:#fff;align-self:flex-start;border-bottom-left-radius:4px}}
.msg.user{{background:#e1ffc7;align-self:flex-end;border-bottom-right-radius:4px}}
pre{{margin:0;white-space:pre-wrap;font:inherit}}
.time{{position:absolute;right:9px;bottom:3px;font-size:11px;color:#8a9a8a}}
</style>
<div class="window"><div class="head"><div class="avatar">P</div>
<div><div class="name">plan-bot</div><div class="sub">bot</div></div></div>
{BANNER}<div class="chat">{"".join(rows)}</div></div>"""


def discord_html(bubbles: list[Bubble]) -> str:
    rows = []
    for b in bubbles:
        who = "plan-bot" if b.sender == "bot" else "student"
        tag = '<span class="tag">APP</span>' if b.sender == "bot" else ""
        color = "#5865f2" if b.sender == "bot" else "#3ba55c"
        rows.append(
            f'<div class="row"><div class="av" style="background:{color}">{who[0].upper()}</div>'
            f'<div><div class="who">{who}{tag}<span class="ts">{b.time:%d.%m.%Y %H:%M}</span>'
            f"</div><pre>{html.escape(b.text)}</pre></div></div>"
        )
    return f"""<!doctype html><meta charset="utf-8"><title>Discord demo</title>
<style>
body{{margin:0;background:#313338;color:#dbdee1;font:15px/1.4 "gg sans","Segoe UI",Roboto,sans-serif}}
.window{{width:640px;margin:0 auto}}
.head{{padding:12px 16px;border-bottom:1px solid #1f2023;font-weight:600;color:#f2f3f5}}
.head span{{color:#80848e;font-weight:400}}
.banner{{background:#4e3d00;color:#ffd666;font-size:12px;text-align:center;padding:6px}}
.row{{display:flex;gap:14px;padding:8px 16px}}
.av{{flex:0 0 40px;height:40px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:700}}
.who{{font-weight:600;color:#f2f3f5}} .ts{{color:#949ba4;font-size:12px;font-weight:400;margin-left:8px}}
.tag{{background:#5865f2;color:#fff;font-size:10px;padding:1px 4px;border-radius:3px;margin-left:6px}}
pre{{margin:2px 0 0;white-space:pre-wrap;font:inherit}}
</style>
<div class="window"><div class="head"># timetable <span>· study group server</span></div>
{BANNER}{"".join(rows)}</div>"""


async def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        telegram, discord = await transcripts(Path(tmp))
    (out / "telegram.html").write_text(telegram_html(telegram), encoding="utf-8")
    (out / "discord.html").write_text(discord_html(discord), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")))
