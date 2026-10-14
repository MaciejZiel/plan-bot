# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security
- Heavy commands (`/subscribe`, `/refresh`, uploads) also draw from a second per-chat bucket that
  refills one token every 45 s (`PLAN_BOT_HEAVY_INTERVAL`), instead of the 7.5 per minute the
  normal bucket allowed. Identical content is parsed once (SHA-256, ten minutes, failures
  included), and a command that waits more than 15 s for the expansion lock answers "busy".
- Expansion limits: the clock is checked in the loops over single events, overrides and starts,
  `RDATE` and `EXDATE` are capped at 2,000 per event, the 20,000 lesson limit trips while a series
  is expanded, rules are cut off at the end of the window, and rules for non-existent days
  (`BYMONTH=2;BYMONTHDAY=30`, which walked to year 9999) are skipped. `COUNT` is now enforced by
  the bot, because dateutil deprecates it next to `UNTIL`.
- Downloads: one at a time per host, 10 s total deadline (was 20 s; `PLAN_BOT_HTTP_TIMEOUT`), and
  only ports 80, 443, 8080 and 8443 unless private URLs are allowed.
- Parser exception text, host names and URLs are no longer shown in chat replies, stored as
  `last_error` or written to logs; only error keys and exception class names are logged.
- aiohttp floor raised to 3.13.3.

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
  change list once). Bumping `PARSER_VERSION` suppresses change alerts for one refresh by design,
  so a genuine change arriving in that refresh is not announced.
- A chat whose uploaded file was read with an older parser is told once, at the next scheduler
  tick, to upload it again (English or Polish), and `/today`, `/tomorrow`, `/week` and `/next`
  end with a warning line until it does. Schema change (migration `0004`) remembers that the
  notice was sent.
- Manual `/refresh` on a snapshot read with an older parser says the timetable was re-read with
  corrected times instead of "no changes".
- Migration downgrades (`0003` to `0002`, `0002` to `0001`) no longer empty `lessons` and
  `sent_reminders`: with SQLite foreign keys on, Alembic's table copy cascaded. The column is now
  dropped in place.

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
