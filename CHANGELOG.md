# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
