# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- Classes from the PJATK (Gakko) export were shown two hours early in summer (14:00 as 12:00). The
  export labels real UTC times with `Z`; an earlier change read them as local time when `PRODID`
  contained `PJWSTK PLAN`. That special case is removed: `Z` means UTC everywhere, so a `12:00Z`
  class is 14:00 in summer and 13:00 in winter. Analysing a real export confirmed it: read as UTC
  every start falls on the PJATK slot grid, read as local time it did not.
- Schema change (migration `0003`): subscriptions remember the parser version their stored
  timetable was read with. After this upgrade the first refresh of each link subscription replaces
  the snapshot without a change alert, so shifted times are not announced as changes. A file that
  was uploaded is not stored, so it cannot be re-read: upload it again (the reply then skips the
  change list once).

### Added
- `/subscribe` accepts an `.ics` file attachment (`file` option) for universities that only offer a
  download. The parsed timetable is stored for that chat only, answers are ephemeral and
  `/forget` deletes it. Uploads obey the download size limit, are never refreshed automatically,
  show as `uploaded file, <date>` in `/status`, and re-uploading replaces the file and reports
  what changed. No schema change.
- A trailing ` s. <room>` in the title (PJATK export) becomes the location when the event has none.
- `/groups` and `/filter` say that filtering is pointless when a timetable has a single group tag.
- Discord is first-class: localised slash commands (`pl`, `en-US`, `en-GB`) including
  `/remind set|list|off`, embeds with room, teacher and a live countdown, buttons that mirror the
  Telegram keyboard, ephemeral answers outside the user's DM with the bot and a private form for
  `/subscribe`.
- Plain questions in DMs and after a mention ("kiedy mam następne zajęcia?", "what's next") are
  mapped to commands by a rule-based Polish/English matcher; no model, no network, no privileged
  intent. Answers to a mention in a server are sent by DM, so a timetable never shows in a
  channel.
- Discord reminders, change alerts and weekly summaries arrive as embeds by DM.
- `DISCORD_DEV_GUILD_ID` syncs slash commands to one server instantly while testing
  (`DISCORD_GUILD_ID` still works).
- Teachers are read from `Lecturer:` / `Prowadzący:` lines in the event description.

### Changed
- Discord timetables are per user instead of per channel. Rows keyed by a DM channel move to the
  user on their next DM; rows keyed by a server channel keep working.
- A Discord user who closed their DMs keeps the timetable but loses pushes; a deleted channel or
  account has its data removed.
- The Termux installer adds the Discord extra by default.

### Fixed
- Reminders and summaries for a deleted Discord channel were retried forever.

## [0.2.0] - 2026-10-13

### Added
- Polish and English replies, chosen per chat (follows the Telegram app language on first contact,
  `/lang en|pl` to change).
- `/start` onboarding, `/demo` and `/subscribe` (the old `/setfeed` keeps working), inline
  keyboards on Telegram, a per-language command menu.
- The demo timetable rolls forward by whole weeks before the bundled semester reaches its
  Christmas break, so it always has classes this week and next week; it never raises change
  alerts.
- Per-chat rate limiting, a shared feed cache and a download concurrency cap.
- Structured JSON logging, token redaction, a `/healthz` endpoint and graceful shutdown.
- `deploy/termux/` for self-hosting under Termux; Python 3.14 support.

### Changed
- SSRF protection now happens in the connector, on the address that is actually used; links with
  credentials, control characters or more than 2048 characters are rejected.
- Telegram updates are processed concurrently (ordered per chat), so one slow feed cannot block
  other users.
- `discord.py` is an optional extra (`pip install 'plan-bot[discord]'`).
- Chats that blocked the bot are deleted instead of being retried forever.
- Recurrence expansion is bounded (no sub-daily rules, a step budget, a lesson cap and a time
  limit) and runs in a worker thread; feeds are refreshed in the background so reminders are
  never held up by a slow server.
- Log pseudonyms for chat ids are keyed with a secret; only a non-default first-contact language
  is stored for chats without a feed.

## [0.1.0] - 2026-10-10

First release.

### Added
- ICS import from any user-provided link (`https://`, `http://`, `webcal://`) or the bundled
  fictional demo timetable (`/setfeed demo`).
- Recurrence expansion with `RRULE`, `RDATE`, `EXDATE`, `RECURRENCE-ID` overrides and
  `STATUS:CANCELLED`. Wall-clock times stay correct across DST switches in `Europe/Warsaw`
  (or any configured timezone).
- Commands: `/today`, `/tomorrow`, `/next` (room and time left), `/week`, `/week next`,
  `/groups`, `/filter`, `/remind`, `/changes`, `/summary`, `/refresh`, `/status`, `/forget`,
  `/help`.
- Change detection between refreshes: room changes, rescheduled, cancelled, restored, added and
  removed classes, including feeds that create new UIDs on every export.
- Reminders N minutes before each class (sent exactly once), a weekly summary on Sunday evening,
  and periodic feed refresh with exponential back-off.
- Telegram adapter (long polling on a minimal Bot API client) and Discord adapter (slash
  commands), both sharing one platform-independent core.
- `plan-bot console` for trying the bot without tokens, with `--at` to pick the simulated time.
- SQLite (aiosqlite) by default and optional PostgreSQL (asyncpg) via SQLAlchemy 2. Alembic
  migrations run on start-up.
- Feed downloads limited by size and timeout, with redirect re-validation and private-address
  (SSRF) blocking.
- Docker image, compose file with an optional PostgreSQL profile, and GitHub Actions CI (ruff,
  mypy strict, pytest with a coverage gate, Docker build and smoke test).

[0.1.0]: https://github.com/MaciejZiel/plan-bot/releases/tag/v0.1.0
