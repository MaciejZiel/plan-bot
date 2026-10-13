# plan-bot

[![CI](https://github.com/MaciejZiel/plan-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/MaciejZiel/plan-bot/actions/workflows/ci.yml)
![Python 3.12 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.14-3776ab)
![Coverage 98%](https://img.shields.io/badge/coverage-98%25-brightgreen)
![Ruff + mypy strict](https://img.shields.io/badge/lint-ruff%20%2B%20mypy%20strict-informational)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Your university timetable, answered in the chat you already use.** plan-bot reads any timetable
published as an iCalendar (ICS) link and gives students on **Telegram** and **Discord**:

- **English and Polish**: the language follows the Telegram app on first contact, `/lang en|pl`
- **a demo that needs nothing**: `/demo` loads a fictional sample timetable so anyone can try
  every feature in seconds, no university link required
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

## Try it in 30 seconds

Open the bot in Telegram (the owner publishes the `@username` after deploying it), then:

```text
you > /start
bot > Hi! I show your university timetable right in this chat: the next class, today, the
      week, reminders before each class and alerts when something changes.
      No timetable at hand? Tap "Try the demo" to see it with a fictional sample.
      Your own: /subscribe <ICS link>. All commands: /help
      [ Try the demo ]  [ English | Polski ]

you > (taps "Try the demo")
bot > Timetable saved (bundled fictional demo timetable).
      164 upcoming classes found.
      Groups in this timetable: C1, C2, EN-B2, L1, L2
      Show only yours with e.g. /filter C1,C2
      Reminders are on, 15 min before each class.
      This is a fictional demo timetable. Try /next, /today and /week, then use your own with
      /subscribe <ICS link>.
      [ Next class ] [ Today ] [ Tomorrow ] [ Week ] [ Next week ]
      [ Remind 15 min ] [ Remind 60 min ] [ No reminders ]

you > /next
bot > Next: Algorithms and Data Structures (lecture)
      Mon 12 Oct, 08:30–10:00 · A-101
      Starts in 45 min.

you > /lang pl
bot > Język: polski.

you > /next
bot > Następne: Algorithms and Data Structures (lecture)
      pon. 12 paź, 08:30–10:00 · A-101
      Start za 45 min.

you > /subscribe http://169.254.169.254/latest/meta-data
bot > Nie udało się pobrać planu: Linki do adresów prywatnych lub lokalnych nie są dozwolone
```

This transcript is real output (generated with `plan-bot console --at 2026-10-12T07:45`; in
Telegram the same replies come with the inline buttons shown in brackets). A private chat is
enough to try it; the bot does not have to be added to a group.

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
> /demo
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

Set only one of the tokens to run on just that platform. Discord needs the optional extra
(`uv sync --extra discord`, or `pip install 'plan-bot[discord]'`).

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
(not a downloaded file). `webcal://` links work too. Then send `/subscribe <link>` to the bot.

- If you already subscribe to the timetable in Google Calendar, open the calendar's
  *Settings → Integrate calendar* page. The *Secret address in iCal format* works, but read the
  privacy notes below first.
- If your university offers no export, plan-bot can't help. It deliberately does not log in to
  portals or scrape pages.

## Commands

| Command | What it does |
|---|---|
| `/start`, `/help` | What the bot does, and all commands |
| `/demo` | Load the fictional sample timetable (no link needed) |
| `/subscribe <url>` | Save your timetable link (`/setfeed` still works) |
| `/lang en\|pl` | Switch the language of this chat |
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

Telegram shows these as a command menu (in Polish for Polish clients) and as inline buttons
under replies, so most of the bot can be used without typing.

## Configuration

All settings are environment variables. See [`.env.example`](.env.example) and
[`deploy/termux/env.example`](deploy/termux/env.example) for the full list: timezone
(`Europe/Warsaw` by default), refresh interval, reminder tick, look-ahead window, change-alert
horizon, summary day and hour, download size limit and timeout, feed cache, per-chat rate limit,
log format (`text` or `json`) and the health endpoint (`PLAN_BOT_HEALTH_PORT`,
`PLAN_BOT_BASE_PATH`).

## Operating it

- **Rate limiting.** Every chat has a token bucket (default: a burst of 10 commands, then 30 per
  minute). Commands that download a feed cost 4 tokens. A throttled chat is warned once, then
  ignored until it has tokens again.
- **Feed errors.** A failing feed is retried with exponential back-off, the stored snapshot keeps
  answering `/next` and reminders, and the chat is told once after the third failure. Identical
  links share one download for two minutes, and at most four downloads run at once.
- **Restarts.** Chats, settings, snapshots and the "reminder already sent" markers are in the
  database, so a restart neither forgets nor repeats a reminder. Reminders are matched against UTC
  instants while class times are expanded in the feed's local wall-clock time, so they stay right
  across DST switches.
- **Blocked bot.** When Telegram reports that a user blocked the bot, that chat's data is deleted.
- **Logs.** `PLAN_BOT_LOG_FORMAT=json` writes one JSON object per line. Chat ids are logged as a
  short keyed hash (HMAC with a key derived from the bot token, so it cannot be reversed by
  hashing every possible id) and anything that looks like a bot token is redacted.
- **Health.** With `PLAN_BOT_HEALTH_PORT` set, `GET <base path>/healthz` returns 200 with
  `{"status": "ok", ...}` while the database answers and the scheduler ticks, and 503 otherwise.
  It listens on `127.0.0.1` and exposes no user data.

## Self-hosting on Termux

[`deploy/termux/`](deploy/termux) runs the bot as a plain process on an Android phone (no Docker).
Everything is configured through environment variables; the bot only makes outgoing connections
(Telegram long polling), so no port has to be opened.

```bash
pkg install git
git clone https://github.com/MaciejZiel/plan-bot.git && cd plan-bot
bash deploy/termux/install.sh         # WITH_DISCORD=1 to add Discord support
nano ~/.config/plan-bot/env           # paste TELEGRAM_BOT_TOKEN (from @BotFather)
~/plan-bot/start.sh                   # runs in the foreground; Ctrl+C stops it
```

- `install.sh` creates a virtualenv in `~/plan-bot`, builds the dependencies (pure-Python
  fallbacks for aiohttp's C helpers, `greenlet` is compiled with clang), copies `env.example` to
  `~/.config/plan-bot/env` (mode 600) and installs the Termux:Boot hook.
- `start.sh` loads that file, applies migrations, refuses to start a second instance and shuts
  down cleanly on `SIGTERM`.
- With the **Termux:Boot** app installed, `~/.termux/boot/plan-bot` starts the bot after a reboot
  (holding a wake lock) and restarts it 15 seconds after any exit. Logs go to
  `~/plan-bot/logs/plan-bot.log` (rotated at 5 MB).
- `nginx-plan-bot.conf` is a location snippet exposing only `/plan-bot/healthz` through the
  reverse proxy. Pair it with a Cloudflare Tunnel or Tailscale Funnel if you want a public health
  URL; the bot works without it.
- SQLite is the default (`~/plan-bot/data/plan-bot.db`). For PostgreSQL create a dedicated
  database and role and set `DATABASE_URL=postgresql+asyncpg://...`; `asyncpg` has to be compiled
  on Android, so SQLite is the easier choice for one small bot.
- Python 3.12 to 3.14 is supported (CI runs 3.12 and 3.14); Termux ships 3.14.

> The scripts were checked with `bash -n` and the full start path (migrate, run, health check,
> graceful stop) was exercised on Linux against a local fake Telegram API, but they have not yet
> been run on a real Termux device.

## Privacy notes

- An ICS link is often a **personal secret**: anyone who has it can read your timetable, and
  some links reveal your name or student ID. plan-bot stores the link in its database so it can
  refresh it. Only run the bot on infrastructure you trust, and keep the database private.
- plan-bot never shows the path or query of a link in chat (`/status` shows only
  `https://host/…`). Logs never contain bot tokens.
- Stored data per chat: chat ID, language, feed link, settings, the lesson snapshot and which reminders
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
  just four Bot API methods, so it uses a small client (about 150 lines including the
  adapter) on top of aiohttp.
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
- **Defensive fetching.** Only `http(s)`/`webcal` links without credentials are accepted. The
  fetcher enforces a size cap and a timeout, follows at most five redirects (each one
  re-validated), and the connector itself refuses loopback, private and link-local addresses (the
  validated address is the one that is connected to, so DNS rebinding does not help). Feeds that keep failing are retried with exponential back-off, and the chat
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

The suite has **172 tests** with **98% line coverage** (CI fails below 85%) and runs in a few
seconds. All tests use fictional fixtures (`tests/fixtures/*.ics` and the bundled sample).
They cover:

- weekly, interval and daily rules, `EXDATE` (also written in UTC) and `RDATE`-only series
- overrides with inherited or their own durations, and cancellations
- both DST transitions (the repeated hour and the spring-forward gap), date-only `UNTIL`, and
  UTC and floating times
- a feed before and after edits
- a fake Telegram Bot API server (commands, inline-button callbacks, concurrent chats, blocked
  users) and the Discord slash-command callbacks
- the English/Polish catalogue (every key in both languages), onboarding, rate limiting, the
  health endpoint, JSON logging and token redaction, SSRF checks and the rolling demo timetable

## Limitations

- Replies exist in English and Polish only. Discord commands are described in English and have
  no inline buttons (only Telegram does).
- All-day events are ignored, because they are usually holidays rather than classes.
- Group filtering relies on `CATEGORIES` or group names appearing in the title or description.
  Feeds that encode groups some other way may need `/filter off`.
- One feed per chat. To combine several feeds, merge them in a calendar app first.
- Webhook mode for Telegram is not implemented. The bot uses long polling, which needs no
  public URL.
- The scheduler runs inside one process, so run a single instance per database.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE) © 2026 Maciej Zieliński. Third-party components and their licenses are listed in
[`3rdparty_licenses.md`](3rdparty_licenses.md).
