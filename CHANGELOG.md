# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
- `deploy/termux/` for self-hosting on Android; Python 3.14 support.

### Changed
- SSRF protection now happens in the connector, on the address that is actually used; links with
  credentials, control characters or more than 2048 characters are rejected.
- Telegram updates are processed concurrently (ordered per chat), so one slow feed cannot block
  other users.
- `discord.py` is an optional extra (`pip install 'plan-bot[discord]'`).
- Chats that blocked the bot are deleted instead of being retried forever.

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
