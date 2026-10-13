# plan-bot

**Your university timetable, answered in the chat you already use.**

**[Add the bot to Discord](https://discord.com/oauth2/authorize?client_id=1559599102084521994&scope=bot+applications.commands&permissions=84992)** · [Status](https://status.maciejzielinski.dev) · [Portfolio](https://maciejzielinski.dev)

Try it now: run `/demo` for a fictional sample timetable, or `/subscribe` with an `.ics` file or a link to your own.

[![CI](https://github.com/MaciejZiel/plan-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/MaciejZiel/plan-bot/actions/workflows/ci.yml)
![Python 3.12 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.14-3776ab)
![Coverage 98%](https://img.shields.io/badge/coverage-98%25-brightgreen)
![Ruff + mypy strict](https://img.shields.io/badge/lint-ruff%20%2B%20mypy%20strict-informational)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

plan-bot reads any timetable
published as an iCalendar (ICS) link or exported as an `.ics` file and gives students on
**Discord** (slash commands, embeds, buttons, plain questions) and **Telegram**:

- **English and Polish**: the language follows your Discord or Telegram app on first contact,
  `/lang en|pl` overrides it
- **plain questions**: DM the bot or mention it ("kiedy mam następne zajęcia?", "what's next")
  and a small keyword matcher (no AI model, no paid API) picks the right command
- **a demo that needs nothing**: `/demo` loads a fictional sample timetable so anyone can try
  every feature in seconds, no university link required
- **today / tomorrow / this week**: `/today`, `/tomorrow`, `/week`, `/week next`
- **next class**: room, time and how long until it starts (or how long the current one lasts)
- **reminders** N minutes before each class (`/remind 15`)
- **change alerts**: room changes, moved or cancelled classes and new or removed ones, detected by
  diffing the feed on every refresh
- **weekly summary** on Sunday evening
- **group filters** (`/filter L1,C2`) for lab/exercise groups

One platform-independent core does all the work. The Discord and Telegram adapters only turn
chat events into calls to it and render the answers (embeds on Discord, text on Telegram).

> plan-bot does **not** scrape any university website. It only reads ICS links that users
> provide. The repository ships a clearly **fictional** sample timetable
> ("Northbridge Institute of Imaginary Computing") for demos and tests.

## Try it in 30 seconds

**Discord** (the public demo runs here)

1. Open the invite link: **[Add plan-bot to Discord](https://discord.com/oauth2/authorize?client_id=1559599102084521994&scope=bot+applications.commands&permissions=84992)**
   (details in [Invite URL](#invite-url-and-permissions)). Add it to a server, or to your own
   account to use it in every DM and server.
2. In any channel or in a DM with the bot, type `/demo`. Nobody else sees the answers: outside
   your DM with the bot they are ephemeral.
3. Try `/next`, `/today`, `/week`, or just write to the bot: `co mam jutro?`

You cannot embed a Discord screenshot here, so this is a transcript of the real embeds
(generated against the fictional sample timetable with the clock set to Monday 12 Oct, 07:45;
`<t:…:R>` is Discord's relative-time markup and renders as "in 45 minutes").

```text
you > /demo
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
bot > ┃ Next class: Algorithms and Data Structures (lecture)
      ┃ Mon 12 Oct, 08:30–10:00
      ┃ starts in 45 minutes
      ┃ Room                 Teacher
      ┃ A-101                Prof. Alan Placeholder (fictional)
      ┃ Times in Europe/Warsaw · /help for all commands
      [ Next class ] [ Today ] [ Tomorrow ] [ Week ] [ Next week ]

you > co mam jutro?                      (a plain message in a DM; after a mention in a server
                                         the answer arrives by DM)
bot > ┃ Tomorrow · Tuesday, 13 Oct
      ┃ 12:00–13:30  Databases (lecture)
      ┃ Aula B · Dr. Ada Example (fictional) · in 1 day
      ┃ 14:00–15:30  Databases (exercises)
      ┃ C-12 · C1 · in 1 day
      ┃ 15:45–17:15  Databases (exercises)
      ┃ C-12 · C2 · in 1 day
      [ Next class ] [ Today ] [ Tomorrow ] [ Week ] [ Next week ]

you > /remind set minutes:30
bot > I will remind you 30 min before each class.

you > asdf
bot > I did not get that. I can show your timetable: ask for the next class, today, tomorrow or
      the week, or use the buttons below. /help lists all commands.
```

At the time a class is 30 minutes away, the bot sends the same style of embed as a direct
message ("Reminder: Algorithms and Data Structures (lecture)", with room, teacher and the
countdown).

Your own timetable: `/subscribe` without a link opens a private form for it (so the link does not
show in the channel), or send `/subscribe https://…/plan.ics`.

**Telegram** works the same way with plain-text replies and inline buttons. The transcript is real
output (generated with `plan-bot console --at 2026-10-12T07:45`):

```text
you > /start
bot > Hi! I show your university timetable right in this chat: the next class, today, the
      week, reminders before each class and alerts when something changes.
      No timetable at hand? Tap "Try the demo" to see it with a fictional sample.
      Your own: /subscribe <ICS link>. All commands: /help
      [ Try the demo ]  [ English | Polski ]

you > (taps "Try the demo")
bot > Timetable saved (bundled fictional demo timetable).
      ...

you > /next
bot > Next: Algorithms and Data Structures (lecture)
      Mon 12 Oct, 08:30–10:00 · A-101
      Starts in 45 min.

you > /subscribe http://169.254.169.254/latest/meta-data
bot > Could not download the timetable: Links to private or local network addresses are not
      allowed
```

## Screenshots

The images below are a **demo mock-up**, not a screenshot of a real Discord server or of anyone's
plan. The message texts are real bot output for the fictional sample timetable (`/demo`, `/next`),
laid out in a static HTML chat frame ([`docs/screenshots/discord-demo.html`](docs/screenshots/discord-demo.html))
and captured with Playwright at a desktop and a mobile width.

<img src="docs/screenshots/discord-demo.png" alt="Demo mock-up of Discord replies from plan-bot to /demo and /next on a fictional timetable, desktop width" width="460">
<img src="docs/screenshots/discord-demo-mobile.png" alt="The same mock-up at mobile width" width="220">

## Self-hosted

The public bot runs on a home server, not on a cloud platform. Its uptime is on the
[status page](https://status.maciejzielinski.dev). You can run your own copy; see
[Quick start](#quick-start) and [Self-hosting on Termux](#self-hosting-on-termux).

## Architecture

```mermaid
flowchart LR
    subgraph Chat platforms
        TG[Telegram Bot API<br/>long polling]
        DC[Discord gateway<br/>slash commands · DMs · mentions]
        CLI[Console<br/>plan-bot console]
    end
    subgraph plan_bot
        TA[adapters/telegram.py]
        DA[adapters/discord.py<br/>discord_render.py embeds]
        R[commands.py<br/>CommandRouter]
        S[service.py<br/>BotService]
        SCH[scheduler.py<br/>asyncio tick]
        F[fetch.py<br/>size/timeout/SSRF guard]
        I[ics.py<br/>RRULE · EXDATE · RECURRENCE-ID · DST]
        D[diff.py<br/>change detection]
        T[timetable.py + formatting.py<br/>views.py · intent.py]
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

### 2. Create the bot

**Discord**
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click
   **New Application**.
2. Open **Bot**, click **Reset Token**, and copy the token into `DISCORD_BOT_TOKEN` in `.env`.
   Leave all three **Privileged Gateway Intents** switched off (see [Discord](#discord)).
3. Optional, to use the bot in DMs and every server without inviting it to each one: open
   **Installation** and tick **User Install** next to **Guild Install**.
4. Build the invite link from [Invite URL and permissions](#invite-url-and-permissions) and open
   it.
5. While testing, set `DISCORD_DEV_GUILD_ID` to your test server's ID (Developer Mode → right-click
   the server → Copy Server ID). The slash commands then appear there instantly. Leave it empty in
   production: global commands can take up to an hour to show up the first time.

**Telegram**
1. Open a chat with [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Pick a display name and a username ending in `bot`.
3. Copy the token BotFather replies with (`123456789:AA...`) into `TELEGRAM_BOT_TOKEN` in `.env`.
4. Optional: to use the bot in a group, add it to the group. Commands like `/today@YourBot` work
   with privacy mode on, so no extra settings are needed.

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

### 4. Getting your ICS link or file

Look in your university's timetable or student portal for an option called *export to
calendar*, *iCal*, *ICS*, *subscribe* or *add to Google/Outlook calendar*. If it gives you a
**link**, copy it (`webcal://` links work too) and send `/subscribe <link>` to the bot.

If the portal only lets you **download a file** (for example PJATK's *Eksportuj do iCalendar*,
which saves one `.ics` file for the whole semester), upload that file instead. On Discord, run
`/subscribe` and attach it in the `file` option.

- The answer is ephemeral, and the file's contents are stored only for your chat as the parsed
  timetable. `/forget` deletes them. The file itself is not kept.
- The file must be an `.ics` calendar within the size limit (`PLAN_BOT_MAX_ICS_BYTES`, 5 MB by
  default). Reminders, `/today`, `/next`, `/week` and the other commands work as with a link.
- An uploaded calendar has no address to refetch, so it is never refreshed automatically and
  `/refresh` has nothing to do. `/status` shows `uploaded file, <date>`. When the plan changes,
  export it again and re-upload it: the new file replaces the old one and the reply lists what
  changed (new, moved, re-roomed and cancelled classes), the same way a link refresh does.
- Only classes from about a week ago to `PLAN_BOT_HORIZON_DAYS` (150) ahead are kept, so re-upload
  after a long break.
- The PJATK export writes local times with a `Z` suffix and puts the room into the title
  (`ZPR wykład s. W21`). plan-bot reads those times as Warsaw wall-clock time (only for files
  whose `PRODID` says `PJWSTK PLAN`) and shows the room as the location.
- If you already subscribe to the timetable in Google Calendar, open the calendar's
  *Settings → Integrate calendar* page. The *Secret address in iCal format* works, but read the
  privacy notes below first.
- If your university offers no export, plan-bot can't help. It deliberately does not log in to
  portals or scrape pages.

## Discord

### What you get

- **Slash commands** with Polish and English descriptions (`pl`, `en-US`, `en-GB`; other
  locales see English): `/help`, `/demo`, `/subscribe`, `/next`, `/today`, `/tomorrow`, `/week`,
  `/remind set|list|off`, `/lang`, `/forget`, plus `/groups`, `/filter`, `/changes`, `/summary`,
  `/refresh` and `/status`. They work in servers and in DMs.
- **Embeds** with the subject, time range, room, teacher and a live countdown ("starts in 25
  minutes", Discord renders it in the reader's language), a green card for a class in progress,
  strike-through for cancelled classes.
- **Buttons** under every answer (Next class, Today, Tomorrow, Week, Next week; reminder presets
  after `/demo` and `/subscribe`) that mirror the Telegram keyboard. They carry no state, so they
  keep working after a restart.
- **Plain questions** in a DM, or after mentioning the bot in a server: "kiedy mam następne
  zajęcia?", "co mam jutro", "plan na tydzień", "what's next", "remind me 30 min before",
  "po polsku". Matching is a keyword table (Polish and English, diacritics ignored, one typo
  tolerated), not a model. Text it does not understand gets a short list of what the bot can do.
  Deleting your data by free text asks for a button confirmation first.
- **Language** follows `interaction.locale` on first contact (Polish clients get Polish);
  `/lang en|pl` overrides it.

### Whose timetable? (a design decision)

A timetable belongs to the **user**, not to the channel: every Discord user has their own feed,
filter and reminders, and the answer to a slash command is **ephemeral** (only the person who
asked sees it) everywhere except the user's own DM with the bot, including group DMs and other
people's DMs where a user-installed command runs. A shared channel timetable (one feed for the whole group) is not
supported on purpose: it would need permission rules (who may change it?), and the common use
case, "my plan", works per user.

Rows created by an earlier version were keyed by channel id. A row keyed by a user's DM channel
is moved to that user the first time they talk to the bot in that DM (if the user already set
things up again, the old row is dropped so nothing arrives twice). A row keyed by a server
channel is shared, so it stays: it is still delivered to that channel and is removed
automatically once the bot can no longer post there (channel deleted, bot removed or its
permission revoked).

Consequences:

- Reminders, change alerts and the weekly summary arrive as **direct messages**. If a user closed
  their DMs (or the bot can no longer reach them), the bot **switches that user's pushes off**
  (reminders, change alerts, summary) and keeps the timetable, so slash commands keep working.
  `/remind set` turns reminders on again after the user allows DMs.
- If the target no longer exists (a deleted legacy channel, a deleted account, an uninvited bot),
  its data is deleted instead of being retried forever.
- A **mention in a server** cannot get an ephemeral answer (Discord only has those for
  interactions), so the channel sees a short note and the answer, which is personal, goes to the
  author **by DM**. If their DMs are closed, the note points to the slash commands instead.
  Help and the "I did not get that" hint are not personal and are answered in the channel.
- `/subscribe` without a link opens a form; with a link the answer is ephemeral, and so is the
  "used /subscribe" line that shows the option, so nobody else sees the link either way. A link
  **posted as a message** after a mention is public, so the bot suggests deleting it.

### Intents

Only non-privileged intents are requested: `guilds`, `guild_messages` and `dm_messages`. Slash
commands, buttons and forms need no intent at all. The privileged **Message Content** intent is
**not** required: per the [discord.py documentation][intents] (and Discord's), message content is
delivered without it for messages sent in DMs to the bot and for messages that mention the bot,
which are exactly the two cases the bot reads. Ordinary server chatter has an empty body, and the
bot ignores it. Leave all three privileged intents (Presence, Server Members, Message Content)
switched off in the Developer Portal.

[intents]: https://discordpy.readthedocs.io/en/stable/api.html#discord.Intents.message_content

### Invite URL and permissions

The public demo's application ID is `1559599102084521994`. To run your own copy, replace it with
the *Application ID* from your Developer Portal (General Information):

```text
Server install (slash commands + mentions):
https://discord.com/oauth2/authorize?client_id=1559599102084521994&scope=bot+applications.commands&permissions=84992

User install (DMs and every server, no invite per server; needs "User Install" enabled):
https://discord.com/oauth2/authorize?client_id=1559599102084521994&integration_type=1&scope=applications.commands
```

`permissions=84992` is the sum of the four bits the bot needs for mentions: **View Channels**
(1024), **Send Messages** (2048), **Embed Links** (16384) and **Read Message History** (65536;
needed to reply to a message). Slash commands, buttons and DM reminders need no channel
permission at all, so a server admin can also invite the bot with `permissions=0` and use only
slash commands. The bot never asks for Administrator, Manage \* or Read Message Content.

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
| `/remind 15` / `/remind off` | Reminder N minutes before each class (default 15). On Discord: `/remind set`, `/remind list`, `/remind off` |
| `/changes on\|off` | Change alerts (default on) |
| `/summary on\|off` | Weekly summary on Sunday at 18:00 (default on) |
| `/refresh` | Download the feed now and show what changed |
| `/status` | Settings, last refresh and last error |
| `/forget` | Delete everything stored for this chat |

Telegram shows these as a command menu (in Polish for Polish clients) and as inline buttons
under replies, Discord as localised slash commands with embeds and buttons, so most of the bot
can be used without typing. `/start` exists on Telegram only; on Discord use `/help`.

## Configuration

All settings are environment variables (`DISCORD_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`,
`DISCORD_DEV_GUILD_ID` for instant slash command sync while testing; the older name
`DISCORD_GUILD_ID` still works). See [`.env.example`](.env.example) and
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
  links share one download for two minutes (at most 32 MB cached), and at most four downloads
  run at once. Feeds are refreshed in the background, so slow servers do not delay reminders.
- **Restarts.** Chats, settings, snapshots and the "reminder already sent" markers are in the
  database, so a restart neither forgets nor repeats a reminder. Reminders are matched against UTC
  instants while class times are expanded in the feed's local wall-clock time, so they stay right
  across DST switches.
- **Blocked bot.** When Telegram reports that a user blocked the bot, that chat's data is deleted.
  On Discord a user who closed their DMs keeps the timetable but loses pushes; a deleted channel
  or account has its data deleted (see [Discord](#discord)).
- **Logs.** `PLAN_BOT_LOG_FORMAT=json` writes one JSON object per line. Chat ids are logged as a
  short keyed hash (HMAC with a key derived from the bot token, so it cannot be reversed by
  hashing every possible id) and anything that looks like a bot token is redacted.
- **Health.** With `PLAN_BOT_HEALTH_PORT` set, `GET <base path>/healthz` returns 200 with
  `{"status": "ok", ...}` while the database answers and the scheduler ticks, and 503 otherwise.
  It listens on `127.0.0.1` and exposes no user data.

## Self-hosting on Termux

[`deploy/termux/`](deploy/termux) runs the bot as a plain process on a self-hosted server running
Termux (no Docker).
Everything is configured through environment variables; the bot only makes outgoing connections
(the Discord gateway, Telegram long polling), so no port has to be opened.

```bash
pkg install git
git clone https://github.com/MaciejZiel/plan-bot.git && cd plan-bot
bash deploy/termux/install.sh         # installs with Discord support (WITH_DISCORD=0 to skip)
nano ~/.config/plan-bot/env           # paste DISCORD_BOT_TOKEN (and/or TELEGRAM_BOT_TOKEN)
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
  under Termux, so SQLite is the easier choice for one small bot.
- Python 3.12 to 3.14 is supported (CI runs 3.12 and 3.14); Termux ships 3.14.

> The scripts were checked with `bash -n` and the full start path (migrate, run, health check,
> graceful stop) was exercised on Linux against a local fake Telegram API, but they have not yet
> been run on a real Termux device.

## Privacy notes

The public Discord bot has a short [privacy policy](PRIVACY.md) and [terms](TERMS.md).

- An ICS link is often a **personal secret**: anyone who has it can read your timetable, and
  some links reveal your name or student ID. plan-bot stores the link in its database so it can
  refresh it. Only run the bot on infrastructure you trust, and keep the database private.
- plan-bot never shows the path or query of a link in chat (`/status` shows only
  `https://host/…`). Logs never contain bot tokens.
- Stored data per chat: chat ID, language, feed link, settings, the lesson snapshot and which reminders
  were sent. `/forget` deletes all of it immediately (cascading delete).
- On Telegram, in a group chat everybody in the group shares the same feed and settings. On
  Discord every user has their own, answers to slash commands are only visible to the asker, and
  answers to a mention in a server are sent by DM.
- Message contents are never stored. Only commands and, on Discord, DMs and mentions addressed to
  the bot are processed, and the text is used only to pick a command. The bot needs no
  message-content intent.
- A feed link posted as a normal message in a server is visible to the channel: use `/subscribe`
  (private answer) or a DM with the bot.

## Key decisions

- **One core, thin adapters.** `BotService` returns structured views (rendered to plain text by
  default, to embeds by the Discord adapter) and pushes notifications through a `Notifier`
  protocol. Adding a platform means writing one adapter, and the console mode is just another
  adapter.
- **Free text without a model.** `intent.py` normalises a message (lower case, no diacritics) and
  matches keyword stems with a one-typo tolerance. It is deterministic, free, runs offline and is
  covered by a PL/EN table test.
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
  fetcher enforces a size cap and one timeout for the whole download (redirects included),
  follows at most five redirects (each hop re-validated), and refuses loopback, private,
  link-local, CGNAT, multicast and reserved addresses, including IPv6 forms that embed one
  (IPv4-mapped, NAT64). Host names are checked inside the connector's resolver, so the validated
  address is the one that is connected to and DNS rebinding does not help. Feeds that keep
  failing are retried with exponential back-off, and the chat hears about it once, after the
  third failure.
- **Bounded expansion.** Recurrence rules repeating hourly or faster are ignored, a rule may
  generate at most 50,000 occurrences (counting those before the window), a feed at most 20,000
  lessons in the window, and expanding one feed may take at most 10 s. Expansion runs in a worker
  thread, one feed at a time, so a hostile feed cannot stall the other chats.
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

The suite has **427 tests** with **98% line coverage** (CI fails below 85%) and runs in about
ten seconds. All tests use fictional fixtures (`tests/fixtures/*.ics` and the bundled sample).
They cover:

- weekly, interval and daily rules, `EXDATE` (also written in UTC) and `RDATE`-only series
- overrides with inherited or their own durations, and cancellations
- both DST transitions (the repeated hour and the spring-forward gap), date-only `UNTIL`, and
  UTC and floating times
- a feed before and after edits
- a fake Telegram Bot API server (commands, inline-button callbacks, concurrent chats, blocked
  users)
- the Discord adapter against fakes of interactions, messages and channels (slash commands and
  their localisation, embeds, buttons, DMs and mentions, closed DMs, deleted channels) and a
  Polish/English table test of the free-text matcher
- races: per-chat ordering under random delays, one busy chat versus the shared slots, and
  background jobs meeting `/forget` or a feed switch half-way
- hostile feeds (sub-daily and impossible rules, too many lessons) and SSRF address forms
- the English/Polish catalogue (every key in both languages), onboarding, rate limiting, the
  health endpoint, JSON logging and token redaction, SSRF checks and the rolling demo timetable

## Limitations

- Replies exist in English and Polish only. Discord slash commands are described in Polish and
  English; clients in other languages see English.
- Discord timetables are per user (no shared channel feed), and DMs from the bot must be allowed
  for reminders to arrive.
- Free-text understanding is a keyword table for Polish and English, not a language model: it
  handles the common phrasings and a typo, and falls back to a help message otherwise.
- The Discord adapter has been tested against fakes of the discord.py objects, not yet against the
  live Discord API.
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
