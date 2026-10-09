"""Command-line entry point: ``plan-bot console``."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime

from plan_bot.config import ConfigError, Settings


def _moment(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=Settings.from_env().timezone)
    return moment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plan-bot", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    console = sub.add_parser("console", help="chat with the bot in this terminal")
    console.add_argument(
        "--at",
        type=_moment,
        default=None,
        help="pretend the current time is this ISO timestamp, e.g. 2026-10-12T08:00",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}")
        return 2
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("alembic").setLevel(logging.WARNING)
    command = args.command or "console"
    if command == "console":
        from plan_bot.console import run_console

        logging.getLogger().setLevel(logging.WARNING)
        asyncio.run(run_console(settings, start_at=getattr(args, "at", None)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
