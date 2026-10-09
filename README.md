# plan-bot

[![CI](https://github.com/MaciejZiel/plan-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/MaciejZiel/plan-bot/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776ab)
![Coverage ≥ 85%](https://img.shields.io/badge/coverage-97%25-brightgreen)
![Ruff + mypy strict](https://img.shields.io/badge/lint-ruff%20%2B%20mypy%20strict-informational)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Your university timetable, answered in the chat you already use.** plan-bot reads any timetable
published as an iCalendar (ICS) link and gives students on **Telegram** and **Discord**:

- **today / tomorrow / this week**: `/today`, `/tomorrow`, `/week`, `/week next`
- **next class**: room, time and how long until it starts (or how long the current one lasts)
- **reminders** N minutes before each class (`/remind 15`)
- **change alerts**: room changes, moved or cancelled classes and new or removed ones, detected by
  diffing the feed on every refresh
- **weekly summary** on Sunday evening
- **group filters** (`/filter L1,C2`) for lab/exercise groups

One platform-independent core does all the work. The Telegram and Discord adapters only turn
chat events into calls to it.

> plan-bot does **not** scrape any university website. It only reads ICS links that users
> provide. The repository ships a clearly **fictional** sample timetable
> ("Northbridge Institute of Imaginary Computing") for demos and tests.

## Screenshots

The images below are **demo mock-ups**. The message texts are real bot output for the
fictional sample timetable, rendered into a static HTML chat frame by
[`scripts/render_demo_chats.py`](scripts/render_demo_chats.py) and captured with Playwright.
They are not screenshots of the real Telegram or Discord apps.

| Telegram (demo) | Discord (demo) |
|---|---|
| <img src="docs/screenshots/telegram.png" alt="Demo mock-up of a Telegram chat with plan-bot" width="380"> | <img src="docs/screenshots/discord.png" alt="Demo mock-up of a Discord channel with plan-bot" width="420"> |

## Architecture

```mermaid
flowchart LR
    subgraph Chat platforms
        TG[Telegram Bot API<br/>long polling]
        DC[Discord gateway<br/>slash commands]
        CLI[Console<br/>plan-bot console]
    end
    subgraph plan_bot
        TA[adapters/telegram.py]
        DA[adapters/discord.py]
        R[commands.py<br/>CommandRouter]
        S[service.py<br/>BotService]
        SCH[scheduler.py<br/>asyncio tick]
        F[fetch.py<br/>size/timeout/SSRF guard]
        I[ics.py<br/>RRULE · EXDATE · RECURRENCE-ID · DST]
        D[diff.py<br/>change detection]
        T[timetable.py + formatting.py]
        REPO[repository.py]
    end
    DB[(SQLite / PostgreSQL<br/>SQLAlchemy 2 + Alembic)]
    ICS[(ICS feed URL<br/>provided by the user)]

    TG <--> TA
    DC <--> DA
    CLI <--> R
    TA --> R
    DA --> R
    R --> S
    SCH --> S
    S --> F --> ICS
    S --> I
    S --> D
    S --> T
    S --> REPO --> DB
    S -. notifications .-> TA
    S -. notifications .-> DA
```

Each refresh downloads the feed, expands it into concrete lesson occurrences for a rolling window
(the past 8 days plus the next 150), compares the result with the stored snapshot, replaces the
snapshot and sends a change alert to the chat when needed. Reminders and summaries are read from
the snapshot, so they keep working while the university server is down.

## Quick start

### 1. Try it locally without any token

```bash
git clone git@github.com:MaciejZiel/plan-bot.git && cd plan-bot
uv sync                                         # Python 3.12 + dependencies
uv run plan-bot console --at 2026-10-12T07:45   # pretend it is a Monday morning
> /setfeed demo
> /today
> /next
```

### 2. Create bot tokens

**Telegram**
1. Open a chat with [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Pick a display name and a username ending in `bot`.
3. Copy the token BotFather replies with (`123456789:AA...`) into `TELEGRAM_BOT_TOKEN` in `.env`.
4. Optional: to use the bot in a group, add it to the group. Commands like `/today@YourBot` work
   with privacy mode on, so no extra settings are needed.

**Discord**
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click
   **New Application**.
2. Open **Bot**, click **Reset Token**, and copy the token into `DISCORD_BOT_TOKEN` in `.env`.
   No privileged gateway intents are needed.
3. Open **OAuth2 → URL Generator**, tick the scopes `bot` and `applications.commands`, then the
   bot permissions *Send Messages* and *View Channels*. Open the generated URL to invite the bot to
   your server.
4. Optional: set `DISCORD_GUILD_ID` to your server's ID (Developer Mode → right-click the server
   → Copy Server ID). Slash commands then appear instantly instead of after the global sync.

Set only one of the tokens to run on just that platform.

### 3. Run it

```bash
cp .env.example .env          # paste the token(s) into .env
set -a; . ./.env; set +a      # export the variables into your shell
uv run plan-bot run
```

or with Docker:

```bash
cp .env.example .env          # paste the token(s) into .env
docker compose up -d --build
docker compose logs -f bot
```

The SQLite database is stored in the `plan-bot-data` volume. For PostgreSQL, run
`docker compose --profile postgres up -d --build` and set
`DATABASE_URL=postgresql+asyncpg://planbot:planbot@postgres:5432/planbot` in `.env`. Outside
Docker, install the extra with `uv sync --extra postgres`. Migrations run automatically on start;
`plan-bot migrate` applies them without starting the bot.

### 4. Getting your ICS link

Look in your university's timetable or student portal for an option called *export to
calendar*, *iCal*, *ICS*, *subscribe* or *add to Google/Outlook calendar*, and copy the **link**
(not a downloaded file). `webcal://` links work too. Then send `/setfeed <link>` to the bot.

- If you already subscribe to the timetable in Google Calendar, open the calendar's
  *Settings → Integrate calendar* page. The *Secret address in iCal format* works, but read the
  privacy notes below first.
- If your university offers no export, plan-bot can't help. It deliberately does not log in to
  portals or scrape pages.

## Commands

| Command | What it does |
|---|---|
| `/setfeed <url>` / `/setfeed demo` | Save the timetable link (or the fictional demo) |
| `/today`, `/tomorrow` | Classes for the day, with rooms and groups |
| `/next` | Current class (if any) and the next one, with time left |
| `/week`, `/week next` | Weekly plan |
| `/groups` | Groups found in the feed (`CATEGORIES`) and the active filter |
| `/filter L1,C2` / `/filter off` | Show only your groups. Classes without a group are always shown |
| `/remind 15` / `/remind off` | Reminder N minutes before each class (default 15) |
| `/changes on\|off` | Change alerts (default on) |
| `/summary on\|off` | Weekly summary on Sunday at 18:00 (default on) |
| `/refresh` | Download the feed now and show what changed |
| `/status` | Settings, last refresh and last error |
| `/forget` | Delete everything stored for this chat |

## Configuration

All settings are environment variables. See [`.env.example`](.env.example) for the full list:
timezone (`Europe/Warsaw` by default), refresh interval, reminder tick, look-ahead window,
change-alert horizon, summary day and hour, download size limit and timeout.

## Privacy notes

- An ICS link is often a **personal secret**: anyone who has it can read your timetable, and
  some links reveal your name or student ID. plan-bot stores the link in its database so it can
  refresh it. Only run the bot on infrastructure you trust, and keep the database private.
- plan-bot never shows the path or query of a link in chat (`/status` shows only
  `https://host/…`). Logs never contain bot tokens.
- Stored data per chat: chat ID, feed link, settings, the lesson snapshot and which reminders
  were sent. `/forget` deletes all of it immediately (cascading delete).
- In a group chat, everybody in the group shares the same feed and settings.
- Message contents are never stored. Only commands are processed. On Discord the bot uses slash
  commands and needs no message-content intent.

## Key decisions

- **One core, thin adapters.** `BotService` returns plain text and pushes notifications through a
  `Notifier` protocol. Adding a platform means writing one adapter, and the console mode is just
  another adapter.
- **Own Telegram client instead of a framework.** python-telegram-bot is LGPL-3.0, and aiogram
  depends on certifi (MPL-2.0). The project only accepts permissive licenses, and the bot needs
  just four Bot API methods, so it uses ~100 lines on top of aiohttp.
- **Recurrence with `python-dateutil`, not `recurring-ical-events`.** The latter is LGPL. Series
  are expanded in the event's local wall-clock time, so a class at 08:30 stays at 08:30 across
  DST switches. Times in the spring-forward gap are shifted the way calendar apps do it, and
  ambiguous autumn times use the first occurrence. `EXDATE` and `RECURRENCE-ID` are matched as
  UTC instants.
- **Stable occurrence keys.** `UID@original-start-UTC` keeps an occurrence's identity when it is
  moved or re-roomed. For exporters that create new UIDs on every export, unmatched
  removed/added pairs with the same title on the same day are treated as one moved class.
- **Own asyncio scheduler instead of APScheduler.** All state (last refresh, sent reminders, last
  weekly summary) lives in the database, so one periodic tick is enough, restarts are harmless,
  and reminders are sent exactly once (enforced by a primary key).
- **Defensive fetching.** The fetcher enforces a size cap and a timeout, follows at most five
  redirects (each one re-validated), and blocks loopback, private and link-local addresses by
  default (SSRF). Feeds that keep failing are retried with exponential back-off, and the chat
  hears about it once, after the third failure.
- **Timezone-correct storage.** All datetimes are aware. The database stores UTC through a
  custom `TypeDecorator`, so SQLite and PostgreSQL behave the same.
- **Dependencies must be at least two weeks old** (`[tool.uv] exclude-newer`), and every
  component is listed with its license in [`3rdparty_licenses.md`](3rdparty_licenses.md).

## Development

```bash
uv sync --all-extras
uv run ruff check . && uv run ruff format --check .
uv run mypy                       # strict
uv run pytest --cov               # fails under 85 % coverage
uv run python scripts/render_demo_chats.py docs/screenshots   # regenerate the demo mock-ups
```

The tests run against fictional fixtures (`tests/fixtures/*.ics` and the bundled sample). They
cover weekly/interval/daily rules, `EXDATE`, `RDATE`, overrides, cancellations, both DST
transitions, UTC and floating times, a feed before and after edits, a fake Telegram Bot API
server, and Discord slash-command callbacks.

## Limitations

- Bot replies are in English only.
- All-day events are ignored, because they are usually holidays rather than classes.
- Group filtering relies on `CATEGORIES` or group names appearing in the title or description.
  Feeds that encode groups some other way may need `/filter off`.
- One feed per chat. To combine several feeds, merge them in a calendar app first.
- Webhook mode for Telegram is not implemented. The bot uses long polling, which needs no
  public URL.
- The SSRF check resolves the host before connecting, but it does not pin the resolved address
  (DNS rebinding is out of scope for a self-hosted bot).
- The scheduler runs inside one process, so run a single instance per database.

## License

[MIT](LICENSE) © 2026 Maciej Zieliński. Third-party components and their licenses are listed in
[`3rdparty_licenses.md`](3rdparty_licenses.md).
