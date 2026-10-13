"""A tiny rule-based matcher that maps free text ("co mam jutro?") to a command.

No model and no network: the text is normalised (lower case, diacritics and
punctuation removed) and compared with keyword stems in Polish and English.
Stems match as word prefixes, so inflected forms work ("tygodniu" for
"tygodn"), and a stem of five or more letters tolerates one typo
(a substituted, missing, extra or swapped letter).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_URL = re.compile(r"(?:https?|webcal)://\S+", re.IGNORECASE)
_NUMBER = re.compile(r"\d+")
# Letters that Unicode normalisation does not split into base + accent.
_FOLD = str.maketrans({"ł": "l", "Ł": "l", "ø": "o", "đ": "d"})
_POLISH_LETTERS = frozenset("ąćęłńóśźż")

#: Cap so a pasted wall of text cannot make the matcher slow.
MAX_WORDS = 40


@dataclass(frozen=True, slots=True)
class Intent:
    command: str
    arg: str | None = None
    #: "pl" or "en" when the wording (not just a number or link) reveals the language.
    lang: str | None = None


def normalize(text: str) -> list[str]:
    """Lower-case words without diacritics or punctuation."""
    folded = text.lower().translate(_FOLD)
    decomposed = unicodedata.normalize("NFKD", folded)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", plain)[:MAX_WORDS]


def _distance_at_most_one(a: str, b: str) -> bool:
    """Optimal string alignment distance <= 1 (substitution, insertion, deletion, swap)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return (
            len(diff) == 2
            and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]]
            and (a[diff[1]] == b[diff[0]])
        )
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long[i]:
        i += 1
    return short[i:] == long[i + 1 :]


def _is(token: str, stem: str) -> bool:
    """``token`` is ``stem`` followed by anything, give or take one typo in the stem."""
    if token.startswith(stem):
        return True
    if len(stem) < 5:
        return False
    return any(
        _distance_at_most_one(token[:size], stem)
        for size in range(len(stem) - 1, len(stem) + 2)
        if len(token) >= size
    )


def _has(tokens: list[str], *stems: str) -> bool:
    return any(_is(token, stem) for token in tokens for stem in stems)


def _exact(tokens: list[str], *words: str) -> bool:
    return any(token in words for token in tokens)


def _minutes(tokens: list[str]) -> int | None:
    """``30`` or ``30 min`` -> 30; ``2 h`` / ``2 godz`` -> 120."""
    for index, token in enumerate(tokens):
        if not token.isdigit():
            continue
        value = int(token)
        unit = tokens[index + 1] if index + 1 < len(tokens) else ""
        return value * 60 if unit.startswith(("h", "godz")) else value
    return None


_PL = "pl"
_EN = "en"


def _pick(tokens: list[str], raw: str) -> str | None:
    """Language of the wording, from Polish-only letters and stems."""
    if _POLISH_LETTERS & set(raw.lower()):
        return _PL
    if _has(
        tokens, "jutr", "dzis", "tydzie", "tygod", "zajec", "nastepn", "kiedy", "mam", "plan"
    ) or _has(tokens, "przypomn", "przypomin", "godz", "wylacz"):
        return _PL
    if _has(
        tokens, "tomorrow", "tommorow", "today", "week", "next", "class", "what", "when", "remind"
    ):
        return _EN
    return None


def match(text: str) -> Intent | None:
    """Map free text to the command it most likely asks for, or ``None``."""
    tokens = normalize(text)
    if not tokens:
        return None
    lang = _pick(tokens, text)

    url = _URL.search(text)
    if url:
        return Intent("subscribe", url.group(0).rstrip(".,;)>"), lang)

    if _has(tokens, "przypomn", "remind", "powiadom", "notify", "alert"):
        minutes = _minutes(tokens)
        off = _has(tokens, "wylacz", "bez", "nie", "stop", "off", "cancel", "disable")
        if off and minutes is None:
            return Intent("remind", "off", lang)
        if minutes is not None and 1 <= minutes <= 24 * 60:
            return Intent("remind", str(minutes), lang)
        return Intent("remind", "list", lang)

    if _has(tokens, "jezyk", "language", "polski", "polish", "english", "angielsk") or (
        _exact(tokens, "po") and _has(tokens, "polsk", "angielsk")
    ):
        target = "en" if _has(tokens, "english", "angielsk") else "pl"
        return Intent("lang", target, target)

    if _has(tokens, "zapomnij", "forget", "usun", "delete", "wyczysc", "erase"):
        return Intent("forget", None, lang)

    if _has(tokens, "status", "ustawien", "settings"):
        return Intent("status", None, lang)

    if _has(tokens, "demo", "przyklad", "sample", "wyprob", "example"):
        return Intent("demo", None, lang)

    if _has(tokens, "tydzie", "tygod", "tydz", "week", "weekly"):
        later = _has(tokens, "przyszl", "nastepn", "kolejn", "next", "following", "coming")
        return Intent("week", "next" if later else None, lang)

    if _has(tokens, "jutr", "jutro", "tomorrow", "tommorow", "tmrw"):
        return Intent("tomorrow", None, lang)

    if _has(tokens, "dzis", "today", "dzisiaj"):
        return Intent("today", None, lang)

    if _has(
        tokens, "nastepn", "kolejn", "najblizsz", "next", "upcoming", "soon", "teraz"
    ) or _exact(tokens, "now"):
        return Intent("next", None, lang)

    if (
        _has(
            tokens, "help", "pomoc", "pomog", "komend", "command", "hej", "czesc", "siema", "witaj"
        )
        or _exact(tokens, "start", "hi", "hello", "hey", "umiesz")
        or (_has(tokens, "what") and _has(tokens, "can") and _exact(tokens, "do"))
    ):
        return Intent("help", None, lang)

    classes = _has(
        tokens, "zajec", "zajeci", "lekcj", "wyklad", "cwiczen", "class", "lectur", "lesson"
    )
    if _has(tokens, "kiedy", "when") and (classes or _has(tokens, "mam", "have", "is")):
        return Intent("next", None, lang)

    if classes or _has(tokens, "plan", "schedule", "timetable"):
        return Intent("today", None, lang)
    return None
