"""Message catalogue for the bot's replies (English and Polish).

Every user-visible string lives here, keyed by a short id, so the core and the
adapters never build sentences themselves. Placeholders use ``str.format``.
"""

from __future__ import annotations

from typing import Final

LANGS: Final = ("en", "pl")
DEFAULT_LANG: Final = "en"
LANG_NAMES: Final = {"en": "English", "pl": "Polski"}

DAYS: Final = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "pl": ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"),
}
SHORT_DAYS: Final = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "pl": ("pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."),
}
MONTHS: Final = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "pl": ("sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"),
}

# key -> {lang: text}
_M: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------- onboarding
    "start": {
        "en": (
            "Hi! I show your university timetable right in this chat: the next class, "
            "today, the week, reminders before each class and alerts when something changes.\n"
            'No timetable at hand? Tap "Try the demo" to see it with a fictional sample.\n'
            "Your own: /subscribe <ICS link>. All commands: /help"
        ),
        "pl": (
            "Cześć! Pokazuję plan zajęć z uczelni prosto w tym czacie: następne zajęcia, "
            "dzisiaj, tydzień, przypomnienia przed zajęciami i alerty o zmianach.\n"
            'Nie masz pod ręką planu? Kliknij "Wypróbuj demo", żeby zobaczyć przykład.\n'
            "Własny plan: /subscribe <link ICS>. Wszystkie komendy: /help"
        ),
    },
    "help_intro": {
        "en": (
            "1. Copy the ICS/iCal export link of your timetable.\n"
            "2. Send /subscribe <link>  (or /demo to try a fictional sample).\n"
            "3. Optionally /filter your groups and set /remind 15."
        ),
        "pl": (
            "1. Skopiuj link eksportu ICS/iCal swojego planu.\n"
            "2. Wyślij /subscribe <link>  (albo /demo, żeby zobaczyć przykład).\n"
            "3. Opcjonalnie ustaw grupy przez /filter i przypomnienie przez /remind 15."
        ),
    },
    "help_commands": {"en": "Commands:", "pl": "Komendy:"},
    "unknown_command": {
        "en": "Unknown command /{name}. Send /help for the list.",
        "pl": "Nieznana komenda /{name}. Wyślij /help, żeby zobaczyć listę.",
    },
    "internal_error": {
        "en": "Something went wrong on my side. Please try again later.",
        "pl": "Coś poszło nie tak po mojej stronie. Spróbuj ponownie później.",
    },
    "rate_limited": {
        "en": "Slow down a little. Try again in {seconds} s.",
        "pl": "Troszkę wolniej. Spróbuj ponownie za {seconds} s.",
    },
    "lang_set": {"en": "Language: English.", "pl": "Język: polski."},
    "lang_usage": {"en": "Use /lang en or /lang pl", "pl": "Użyj /lang en albo /lang pl"},
    # ----------------------------------------------------------------- buttons
    "btn.demo": {"en": "Try the demo", "pl": "Wypróbuj demo"},
    "btn.next": {"en": "Next class", "pl": "Następne"},
    "btn.today": {"en": "Today", "pl": "Dzisiaj"},
    "btn.tomorrow": {"en": "Tomorrow", "pl": "Jutro"},
    "btn.week": {"en": "Week", "pl": "Tydzień"},
    "btn.next_week": {"en": "Next week", "pl": "Przyszły tydzień"},
    "btn.remind": {"en": "Remind {n} min", "pl": "Przypomnij {n} min"},
    "btn.remind_off": {"en": "No reminders", "pl": "Bez przypomnień"},
    "btn.help": {"en": "Help", "pl": "Pomoc"},
    # ------------------------------------------------------- command catalogue
    "cmd.start": {"en": "What this bot does", "pl": "Co robi ten bot"},
    "cmd.today": {"en": "Classes today", "pl": "Zajęcia dzisiaj"},
    "cmd.tomorrow": {"en": "Classes tomorrow", "pl": "Zajęcia jutro"},
    "cmd.next": {
        "en": "Next class with room and time left",
        "pl": "Następne zajęcia: sala i czas do startu",
    },
    "cmd.week": {"en": "This week's plan", "pl": "Plan na tydzień"},
    "cmd.subscribe": {"en": "Set your timetable ICS link", "pl": "Ustaw link ICS z planem"},
    "cmd.demo": {"en": "Try a fictional sample timetable", "pl": "Wypróbuj przykładowy plan"},
    "cmd.groups": {"en": "Groups found in the timetable", "pl": "Grupy znalezione w planie"},
    "cmd.filter": {"en": "Show only your groups", "pl": "Pokaż tylko swoje grupy"},
    "cmd.remind": {"en": "Reminder before classes", "pl": "Przypomnienie przed zajęciami"},
    "cmd.changes": {"en": "Alerts about timetable changes", "pl": "Alerty o zmianach w planie"},
    "cmd.summary": {
        "en": "Weekly summary on Sunday evening",
        "pl": "Podsumowanie tygodnia w niedzielę wieczorem",
    },
    "cmd.refresh": {"en": "Download the timetable now", "pl": "Pobierz plan teraz"},
    "cmd.status": {"en": "Current settings and feed status", "pl": "Ustawienia i stan planu"},
    "cmd.lang": {"en": "Language: en or pl", "pl": "Język: en lub pl"},
    "cmd.forget": {
        "en": "Delete everything stored for this chat",
        "pl": "Usuń wszystko, co zapisano dla tego czatu",
    },
    "cmd.help": {"en": "How to use the bot", "pl": "Jak używać bota"},
    "arg.week": {"en": "Leave empty or type 'next'", "pl": "Zostaw puste albo wpisz 'next'"},
    "arg.subscribe": {
        "en": "https://... or webcal://... link to the .ics feed",
        "pl": "link https://... lub webcal://... do pliku .ics",
    },
    "arg.filter": {"en": "e.g. L1,C2 or 'off'", "pl": "np. L1,C2 albo 'off'"},
    "arg.remind": {"en": "e.g. 15 or 'off'", "pl": "np. 15 albo 'off'"},
    "arg.changes": {"en": "'on' or 'off'", "pl": "'on' albo 'off'"},
    "arg.summary": {"en": "'on' or 'off'", "pl": "'on' albo 'off'"},
    "arg.lang": {"en": "'en' or 'pl'", "pl": "'en' albo 'pl'"},
    # ----------------------------------------------------------------- service
    "no_feed": {
        "en": (
            "No timetable yet. Send /subscribe <ICS link> with your university calendar link, "
            "or /demo to try a fictional sample timetable."
        ),
        "pl": (
            "Nie ma jeszcze planu. Wyślij /subscribe <link ICS> z linkiem do kalendarza "
            "uczelni albo /demo, żeby wypróbować przykładowy plan."
        ),
    },
    "subscribe_usage": {
        "en": "Usage: /subscribe <ICS link>  (or /demo)",
        "pl": "Użycie: /subscribe <link ICS>  (albo /demo)",
    },
    "saved": {"en": "Timetable saved ({where}).", "pl": "Plan zapisany ({where})."},
    "saved_demo": {
        "en": (
            "This is a fictional demo timetable. Try /next, /today and /week, "
            "then use your own with /subscribe <ICS link>."
        ),
        "pl": (
            "To fikcyjny plan demonstracyjny. Wypróbuj /next, /today i /week, "
            "a potem podepnij własny przez /subscribe <link ICS>."
        ),
    },
    "upcoming": {
        "en": "{n} upcoming classes found.",
        "pl": "Znalezione nadchodzące zajęcia: {n}.",
    },
    "groups_found": {
        "en": "Groups in this timetable: {groups}",
        "pl": "Grupy w tym planie: {groups}",
    },
    "filter_hint": {
        "en": "Show only yours with e.g. /filter {example}",
        "pl": "Pokaż tylko swoje, np. /filter {example}",
    },
    "reminders_on": {
        "en": "Reminders are on, {n} min before each class.",
        "pl": "Przypomnienia włączone, {n} min przed każdymi zajęciami.",
    },
    "feed_demo": {
        "en": "bundled fictional demo timetable",
        "pl": "wbudowany fikcyjny plan demonstracyjny",
    },
    "week_usage": {"en": "Use /week or /week next", "pl": "Użyj /week albo /week next"},
    "groups_list": {"en": "Groups: {groups}", "pl": "Grupy: {groups}"},
    "groups_none": {
        "en": "This timetable has no group tags.",
        "pl": "Ten plan nie ma oznaczeń grup.",
    },
    "filter_current": {"en": "Current filter: {f}", "pl": "Aktualny filtr: {f}"},
    "filter_none": {
        "en": "No filter: showing everything.",
        "pl": "Brak filtra: pokazuję wszystko.",
    },
    "filter_usage": {
        "en": "Usage: /filter L1,C2  or  /filter off",
        "pl": "Użycie: /filter L1,C2  albo  /filter off",
    },
    "filter_removed": {
        "en": "Filter removed: showing all classes.",
        "pl": "Filtr usunięty: pokazuję wszystkie zajęcia.",
    },
    "filter_set": {
        "en": "Filter set: {f}. Classes without a group are always shown.",
        "pl": "Filtr ustawiony: {f}. Zajęcia bez grupy są zawsze pokazywane.",
    },
    "filter_unknown": {
        "en": "Not found in the timetable tags: {x}",
        "pl": "Nie znaleziono w oznaczeniach planu: {x}",
    },
    "remind_off": {"en": "Reminders are off.", "pl": "Przypomnienia wyłączone."},
    "remind_usage": {
        "en": "Usage: /remind 15  (minutes before class)  or  /remind off",
        "pl": "Użycie: /remind 15  (minuty przed zajęciami)  albo  /remind off",
    },
    "remind_range": {
        "en": "Pick between 1 and {max} minutes.",
        "pl": "Wybierz od 1 do {max} minut.",
    },
    "remind_set": {
        "en": "I will remind you {delta} before each class.",
        "pl": "Przypomnę Ci {delta} przed każdymi zajęciami.",
    },
    "on_off_usage": {
        "en": "Use /{what} on or /{what} off",
        "pl": "Użyj /{what} on albo /{what} off",
    },
    "changes_on": {"en": "Change alerts are on.", "pl": "Alerty o zmianach włączone."},
    "changes_off": {"en": "Change alerts are off.", "pl": "Alerty o zmianach wyłączone."},
    "summary_on": {"en": "Weekly summary is on.", "pl": "Podsumowanie tygodnia włączone."},
    "summary_off": {"en": "Weekly summary is off.", "pl": "Podsumowanie tygodnia wyłączone."},
    "status_feed": {"en": "Feed: {where}", "pl": "Plan: {where}"},
    "status_classes": {"en": "Classes stored: {n}", "pl": "Zapisane zajęcia: {n}"},
    "status_filter": {"en": "Filter: {f}", "pl": "Filtr: {f}"},
    "status_none": {"en": "none", "pl": "brak"},
    "status_remind": {"en": "Reminders: {v}", "pl": "Przypomnienia: {v}"},
    "status_remind_min": {"en": "{n} min before", "pl": "{n} min przed"},
    "status_changes": {"en": "Change alerts: {v}", "pl": "Alerty o zmianach: {v}"},
    "status_summary": {"en": "Weekly summary: {v}", "pl": "Podsumowanie tygodnia: {v}"},
    "status_lang": {"en": "Language: {v}", "pl": "Język: {v}"},
    "on": {"en": "on", "pl": "włączone"},
    "off": {"en": "off", "pl": "wyłączone"},
    "status_refresh": {"en": "Last refresh: {ago} ago", "pl": "Ostatnie odświeżenie: {ago} temu"},
    "status_error": {"en": "Last error: {e}", "pl": "Ostatni błąd: {e}"},
    "refreshed_same": {
        "en": "Timetable refreshed, no changes.",
        "pl": "Plan odświeżony, bez zmian.",
    },
    "forgotten": {
        "en": "Done. Your feed link, settings and stored timetable were deleted.",
        "pl": "Gotowe. Link do planu, ustawienia i zapisany plan zostały usunięte.",
    },
    "nothing_stored": {
        "en": "There was nothing stored for this chat.",
        "pl": "Dla tego czatu nic nie było zapisane.",
    },
    "refresh_failing": {
        "en": (
            "I could not refresh your timetable {count} times in a row: {error}\n"
            "Check the link with /status or set a new one with /subscribe."
        ),
        "pl": (
            "Nie udało mi się odświeżyć planu {count} razy z rzędu: {error}\n"
            "Sprawdź link przez /status albo ustaw nowy przez /subscribe."
        ),
    },
    "download_failed": {
        "en": "Could not download the timetable: {error}",
        "pl": "Nie udało się pobrać planu: {error}",
    },
    "too_complex": {
        "en": "That timetable is too large or too complex for this bot.",
        "pl": "Ten plan jest zbyt duży lub zbyt skomplikowany dla tego bota.",
    },
    "not_ics": {
        "en": "That link does not return an iCalendar file ({error}).",
        "pl": "Ten link nie zwraca pliku iCalendar ({error}).",
    },
    # ------------------------------------------------------------- fetch errors
    "url.too_long": {"en": "The link is too long", "pl": "Link jest za długi"},
    "url.chars": {
        "en": "The link contains spaces or control characters",
        "pl": "Link zawiera spacje lub znaki sterujące",
    },
    "url.invalid": {"en": "The link is not a valid URL", "pl": "To nie jest poprawny link"},
    "url.scheme": {
        "en": "The link must start with https://, http:// or webcal://",
        "pl": "Link musi zaczynać się od https://, http:// lub webcal://",
    },
    "url.no_host": {"en": "The link has no host name", "pl": "W linku brakuje nazwy hosta"},
    "url.credentials": {
        "en": "Links with a user name or password are not supported",
        "pl": "Linki z nazwą użytkownika lub hasłem nie są obsługiwane",
    },
    "fetch.private": {
        "en": "Links to private or local network addresses are not allowed",
        "pl": "Linki do adresów prywatnych lub lokalnych nie są dozwolone",
    },
    "fetch.resolve": {"en": "Cannot resolve host {host}", "pl": "Nie można znaleźć hosta {host}"},
    "fetch.http": {
        "en": "The server answered HTTP {status}",
        "pl": "Serwer odpowiedział HTTP {status}",
    },
    "fetch.redirect": {"en": "Redirect without a target", "pl": "Przekierowanie bez celu"},
    "fetch.redirects": {"en": "Too many redirects", "pl": "Za dużo przekierowań"},
    "fetch.too_large": {
        "en": "The calendar file is too large",
        "pl": "Plik kalendarza jest za duży",
    },
    "fetch.failed": {"en": "Download failed: {kind}", "pl": "Pobieranie nie powiodło się: {kind}"},
    # --------------------------------------------------------------- formatting
    "unit.d": {"en": "d", "pl": "d"},
    "unit.h": {"en": "h", "pl": "godz."},
    "unit.min": {"en": "min", "pl": "min"},
    "title.today": {"en": "Today", "pl": "Dzisiaj"},
    "title.tomorrow": {"en": "Tomorrow", "pl": "Jutro"},
    "title.week": {"en": "This week", "pl": "Ten tydzień"},
    "title.next_week": {"en": "Next week", "pl": "Przyszły tydzień"},
    "title.coming_week": {"en": "Coming week", "pl": "Nadchodzący tydzień"},
    "no_classes_day": {
        "en": "No classes. Enjoy the free time.",
        "pl": "Brak zajęć. Ciesz się wolnym.",
    },
    "week_header": {
        "en": "{title} {first} – {last}: {count} classes",
        "pl": "{title} {first} – {last}: zajęć: {count}",
    },
    "no_classes_week": {"en": "No classes this week.", "pl": "W tym tygodniu brak zajęć."},
    "now": {
        "en": "Now: {summary}{room}, ends in {delta}.",
        "pl": "Teraz: {summary}{room}, koniec za {delta}.",
    },
    "in_room": {"en": " in {room}", "pl": ", sala {room}"},
    "no_upcoming": {
        "en": "No upcoming classes in the timetable.",
        "pl": "Brak nadchodzących zajęć w planie.",
    },
    "next_label": {"en": "Next: {summary}", "pl": "Następne: {summary}"},
    "starts_in": {"en": "Starts in {delta}.", "pl": "Start za {delta}."},
    "reminder": {
        "en": "Reminder: {summary} starts in {delta}",
        "pl": "Przypomnienie: {summary} zaczyna się za {delta}",
    },
    "cancelled_tag": {"en": "[CANCELLED] ", "pl": "[ODWOŁANE] "},
    "changed_header": {"en": "Timetable changed:", "pl": "Zmiany w planie:"},
    "ch.cancelled": {"en": "CANCELLED", "pl": "ODWOŁANE"},
    "ch.removed": {"en": "removed from the timetable", "pl": "usunięte z planu"},
    "ch.added": {"en": "new class, {span}{where}", "pl": "nowe zajęcia, {span}{where}"},
    "ch.restored": {
        "en": "back on (no longer cancelled)",
        "pl": "znowu się odbędą (już nie odwołane)",
    },
    "ch.moved": {"en": "moved to {day}{span}", "pl": "przeniesione na {day}{span}"},
    "ch.room": {"en": "room {old} → {new}", "pl": "sala {old} → {new}"},
}


def tr(lang: str, key: str, **params: object) -> str:
    """Translate ``key``; unknown languages fall back to English."""
    entry = _M[key]
    text = entry.get(lang) or entry[DEFAULT_LANG]
    return text.format(**params) if params else text


def normalize_lang(code: str | None) -> str | None:
    """Map a platform locale such as ``pl-PL`` or ``en_GB`` to a supported language."""
    if not code:
        return None
    base = code.replace("_", "-").split("-", 1)[0].lower()
    return base if base in LANGS else None


def lang_for_locale(code: str | None) -> str:
    return normalize_lang(code) or DEFAULT_LANG
