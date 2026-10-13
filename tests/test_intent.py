from __future__ import annotations

import pytest

from plan_bot.intent import Intent, match, normalize

CASES: list[tuple[str, str, str | None, str | None]] = [
    # text, command, arg, language
    ("kiedy mam następne zajęcia?", "next", None, "pl"),
    ("Kiedy mam nastepne zajecia", "next", None, "pl"),
    ("jakie mam kolejne zajęcia", "next", None, "pl"),
    ("najbliższe zajęcia", "next", None, "pl"),
    ("co teraz mam?", "next", None, "pl"),
    ("what's next", "next", None, "en"),
    ("whats next?", "next", None, "en"),
    ("when is my next class", "next", None, "en"),
    ("when do I have class", "next", None, "en"),
    ("co mam jutro", "tomorrow", None, "pl"),
    ("a co jutro?", "tomorrow", None, "pl"),
    ("plan na jutro", "tomorrow", None, "pl"),
    ("jturo", "tomorrow", None, None),
    ("what do I have tomorrow", "tomorrow", None, "en"),
    ("tomorow?", "tomorrow", None, "en"),
    ("classes tommorow", "tomorrow", None, "en"),
    ("co mam dzisiaj", "today", None, "pl"),
    ("dziś", "today", None, "pl"),
    ("dzis jakie zajecia", "today", None, "pl"),
    ("what's on today", "today", None, "en"),
    ("my schedule", "today", None, None),
    ("plan", "today", None, "pl"),
    ("plan na tydzień", "week", None, "pl"),
    ("plan na tydzien", "week", None, "pl"),
    ("co mam w tym tygodniu", "week", None, "pl"),
    ("plan na przyszły tydzień", "week", "next", "pl"),
    ("następny tydzień", "week", "next", "pl"),
    ("show me the week", "week", None, "en"),
    ("next week please", "week", "next", "en"),
    ("tydizen", "week", None, "pl"),
    ("przypomnij 30 min przed", "remind", "30", "pl"),
    ("przypomnij mi 15 minut przed zajęciami", "remind", "15", "pl"),
    ("przypominaj za 2 godziny", "remind", "120", "pl"),
    ("remind me 45 minutes before", "remind", "45", "en"),
    ("remind me 1 hour before class", "remind", "60", "en"),
    ("wyłącz przypomnienia", "remind", "off", "pl"),
    ("nie przypominaj", "remind", "off", "pl"),
    ("turn off reminders", "remind", "off", "en"),
    ("przypomnienia", "remind", "list", "pl"),
    ("what are my reminders", "remind", "list", "en"),
    ("po polsku", "lang", "pl", "pl"),
    ("język polski", "lang", "pl", "pl"),
    ("switch to english", "lang", "en", "en"),
    ("po angielsku", "lang", "en", "en"),
    ("pomoc", "help", None, None),
    ("help", "help", None, None),
    ("what can you do?", "help", None, "en"),
    ("cześć", "help", None, "pl"),
    ("hi", "help", None, None),
    ("jakie komendy", "help", None, None),
    ("demo", "demo", None, None),
    ("pokaż przykład", "demo", None, "pl"),
    ("try the demo", "demo", None, None),
    ("usuń moje dane", "forget", None, "pl"),
    ("forget me", "forget", None, None),
    ("status", "status", None, None),
    ("ustawienia", "status", None, None),
    # added after a review against unseen phrasings
    ("co dalej", "next", None, None),
    ("co mam po tym", "next", None, "pl"),
    ("przypomnij mi pol godziny przed", "remind", "30", "pl"),
    ("przypomnienie 1h przed", "remind", "60", "pl"),
    ("remind me 15min before", "remind", "15", "en"),
    ("remind me half an hour before", "remind", "30", "en"),
    ("no more reminders", "remind", "off", "en"),
    ("co mam za tydzien", "week", "next", "pl"),
    ("upcoming week", "week", "next", "en"),
    ("co potrafisz", "help", None, None),
    ("jak tego uzywac", "help", None, None),
    ("jak to działa", "help", None, "pl"),
    ("how do i use this", "help", None, None),
]


@pytest.mark.parametrize(("text", "command", "arg", "lang"), CASES)
def test_matches(text: str, command: str, arg: str | None, lang: str | None) -> None:
    assert match(text) == Intent(command, arg, lang)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "???", "asdf qwerty", "ok", "dzięki!", "thanks a lot", "lorem ipsum dolor sit"],
)
def test_unknown_text_matches_nothing(text: str) -> None:
    assert match(text) is None


def test_link_becomes_subscribe() -> None:
    found = match("proszę, oto mój plan: https://uni.example/plan.ics.")
    assert found == Intent("subscribe", "https://uni.example/plan.ics", "pl")
    assert match("webcal://uni.example/p.ics") == Intent("subscribe", "webcal://uni.example/p.ics")


def test_remind_number_out_of_range_is_a_status_question() -> None:
    assert match("remind me 99999 minutes before") == Intent("remind", "list", "en")


def test_normalize_strips_diacritics_and_punctuation() -> None:
    assert normalize("Zażółć gęślą jaźń, 15 min!") == ["zazolc", "gesla", "jazn", "15", "min"]
    assert normalize("Łódź") == ["lodz"]
    assert len(normalize("a " * 500)) == 40


def test_short_stems_do_not_match_typos() -> None:
    # "text" is one letter from "next"; short stems must match exactly.
    assert match("text") is None
    assert match("nest") is None
