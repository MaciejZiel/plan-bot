from __future__ import annotations

import string

import pytest

from plan_bot.commands import COMMANDS, CommandRouter, help_text
from plan_bot.i18n import _M, DAYS, LANGS, MONTHS, SHORT_DAYS, normalize_lang, tr
from plan_bot.repository import ChatRef
from plan_bot.service import BotService
from tests.conftest import FakeClock, RecordingNotifier, warsaw

CHAT = ChatRef("telegram", "pl-user")


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_message_exists_in_every_language_with_the_same_placeholders() -> None:
    for key, texts in _M.items():
        assert set(texts) == set(LANGS), key
        assert _fields(texts["en"]) == _fields(texts["pl"]), key


def test_calendar_names_are_complete() -> None:
    for lang in LANGS:
        assert len(DAYS[lang]) == len(SHORT_DAYS[lang]) == 7
        assert len(MONTHS[lang]) == 12


def test_every_command_is_described_in_every_language() -> None:
    for spec in COMMANDS:
        for lang in LANGS:
            assert spec.describe(lang)
            if spec.arg:
                assert tr(lang, f"arg.{spec.name}")
    assert "Komendy:" in help_text("pl")


def test_tr_falls_back_to_english_and_normalizes_locales() -> None:
    assert tr("de", "lang_set") == "Language: English."
    assert normalize_lang("pl-PL") == "pl"
    assert normalize_lang("EN_gb") == "en"
    assert normalize_lang("de") is None
    assert normalize_lang(None) is None
    assert normalize_lang("") is None


async def test_polish_replies_end_to_end(service: BotService) -> None:
    router = CommandRouter(service)
    assert "Język: polski" in await router.handle(CHAT, "lang", "pl")
    assert "Plan zapisany" in await router.handle(CHAT, "demo")
    assert "Następne: Algorithms" in await router.handle(CHAT, "next")
    assert "Start za 1 godz. 30 min." in await router.handle(CHAT, "next")
    today = await router.handle(CHAT, "today")
    assert today.startswith("Dzisiaj · Poniedziałek, 12 paź")
    week = await router.handle(CHAT, "week")
    assert week.startswith("Ten tydzień pon. 12 paź – niedz. 18 paź: zajęć:")
    assert "Przypomnę Ci 10 min przed każdymi zajęciami." in await router.handle(
        CHAT, "remind", "10"
    )
    assert "Użyj /changes on albo /changes off" in await router.handle(CHAT, "changes", "x")
    assert "Link musi zaczynać się" in await router.handle(CHAT, "subscribe", "ftp://x.example/a")
    status = await router.handle(CHAT, "status")
    assert "Przypomnienia: 10 min przed" in status
    assert "Język: pl" in status


async def test_polish_reminders_and_summary(
    service: BotService, clock: FakeClock, notifier: RecordingNotifier
) -> None:
    await service.set_language(CHAT, "pl")
    await service.set_feed(CHAT, "demo")
    clock.now = warsaw(2026, 10, 12, 8, 20)
    assert await service.send_due_reminders(clock.now) == 1
    texts = notifier.texts()
    assert texts[0].startswith(
        "Przypomnienie: Algorithms and Data Structures (lecture) zaczyna się za"
    )
    clock.now = warsaw(2026, 10, 18, 18, 5)
    assert await service.send_weekly_summaries(clock.now) == 1
    assert notifier.texts()[-1].startswith("Nadchodzący tydzień")


@pytest.mark.parametrize("bad", ["", "de", "english"])
async def test_lang_usage(service: BotService, bad: str) -> None:
    router = CommandRouter(service)
    assert "Use /lang en or /lang pl" in await router.handle(CHAT, "lang", bad)
