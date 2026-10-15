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
    "cmd.subscribe": {
        "en": "Set your timetable from an ICS link or file",
        "pl": "Ustaw plan z linku lub pliku ICS",
    },
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
    "arg.subscribe_file": {
        "en": "or attach the .ics file you exported from your university",
        "pl": "albo załącz plik .ics wyeksportowany z uczelni",
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
    "feed_demo": {
        "en": "bundled fictional demo timetable",
        "pl": "wbudowany fikcyjny plan demonstracyjny",
    },
    "feed_upload": {"en": "uploaded file", "pl": "wgrany plik"},
    "feed_upload_on": {"en": "uploaded file, {date}", "pl": "wgrany plik, {date}"},
    "upload_status_hint": {
        "en": "It is not refreshed automatically. When the plan changes, export it again and "
        "re-upload it with /subscribe file:<.ics file>.",
        "pl": "Nie jest odświeżany automatycznie. Gdy plan się zmieni, wyeksportuj go ponownie "
        "i wgraj przez /subscribe file:<plik .ics>.",
    },
    "refresh_uploaded": {
        "en": "This timetable came from an uploaded file, so there is nothing to refresh. "
        "Export it again and re-upload it with /subscribe file:<.ics file>.",
        "pl": "Ten plan pochodzi z wgranego pliku, więc nie ma czego odświeżać. "
        "Wyeksportuj go ponownie i wgraj przez /subscribe file:<plik .ics>.",
    },
    "upload_both": {
        "en": "Give either a link or a file, not both.",
        "pl": "Podaj link albo plik, nie jedno i drugie.",
    },
    "upload_too_large": {
        "en": "That file is too large (the limit is {mb} MB).",
        "pl": "Ten plik jest za duży (limit to {mb} MB).",
    },
    "upload_bad_type": {
        "en": "That does not look like a calendar. Upload the .ics file exported from your "
        "university's timetable.",
        "pl": "To nie wygląda na kalendarz. Wgraj plik .ics wyeksportowany z planu uczelni.",
    },
    "upload_read_failed": {
        "en": "Could not read the attached file. Try uploading it again.",
        "pl": "Nie udało się odczytać załączonego pliku. Spróbuj wgrać go ponownie.",
    },
    "upload_not_ics": {
        "en": "That file is not an iCalendar file ({error}).",
        "pl": "Ten plik nie jest plikiem iCalendar ({error}).",
    },
    "upload_reparsed": {
        "en": "The previous upload was replaced. Class times were read differently before, so "
        "no list of changes is shown this time.",
        "pl": "Poprzedni wgrany plik został zastąpiony. Godziny zajęć były wcześniej czytane "
        "inaczej, więc tym razem nie pokazuję listy zmian.",
    },
    "upload_stale_notice": {
        "en": "Class times in your uploaded timetable were read incorrectly before an update "
        "(they could be shifted by an hour or two). Please upload the .ics file again with "
        "/subscribe to get the corrected times.",
        "pl": "Godziny zajęć w Twoim wgranym planie były wcześniej czytane błędnie (mogły być "
        "przesunięte o godzinę lub dwie). Wgraj plik .ics ponownie przez /subscribe, żeby "
        "dostać poprawione godziny.",
    },
    "upload_stale_warning": {
        "en": "Warning: these times may be shifted. Upload your .ics file again with /subscribe.",
        "pl": "Uwaga: te godziny mogą być przesunięte. Wgraj plik .ics ponownie przez /subscribe.",
    },
    "refreshed_reparsed": {
        "en": "Timetable re-read with corrected class times. Earlier times could be shifted, so "
        "no list of changes is shown.",
        "pl": "Plan wczytany ponownie z poprawionymi godzinami zajęć. Wcześniejsze godziny mogły "
        "być przesunięte, więc nie pokazuję listy zmian.",
    },
    "upload_same": {
        "en": "The previous upload was replaced; no changes in upcoming classes.",
        "pl": "Poprzedni wgrany plik został zastąpiony; bez zmian w nadchodzących zajęciach.",
    },
    "saved_upload_hint": {
        "en": "The file is stored for this chat only; /forget deletes it.",
        "pl": "Plik jest zapisany tylko dla tego czatu; /forget go usuwa.",
    },
    "week_usage": {"en": "Use /week or /week next", "pl": "Użyj /week albo /week next"},
    "groups_list": {"en": "Groups: {groups}", "pl": "Grupy: {groups}"},
    "groups_single": {
        "en": "This timetable has only one group tag ({group}), so filtering will not help.",
        "pl": "Ten plan ma tylko jedno oznaczenie grupy ({group}), więc filtr nic nie da.",
    },
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
        "en": "Usage: /remind 15 (minutes before class), /remind start on|off (when it starts) "
        "or /remind off (everything)",
        "pl": "Użycie: /remind 15 (minuty przed zajęciami), /remind start on|off (w chwili "
        "startu) albo /remind off (wszystko)",
    },
    "remind_range": {
        "en": "Pick between 1 and {max} minutes.",
        "pl": "Wybierz od 1 do {max} minut.",
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
    "status_remind_start": {"en": "at the start", "pl": "w chwili startu"},
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
    "busy": {
        "en": "The bot is busy reading other timetables. Try again in a minute.",
        "pl": "Bot czyta teraz inne plany. Spróbuj ponownie za minutę.",
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
    "url.port": {
        "en": "The link must use port 80, 443, 8080 or 8443",
        "pl": "Link musi używać portu 80, 443, 8080 lub 8443",
    },
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
    "fetch.resolve": {"en": "Cannot resolve the host", "pl": "Nie można znaleźć hosta"},
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
    "reminder_start": {
        "en": "Starting now: {summary}",
        "pl": "Zaczyna się: {summary}",
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
    "remind_current": {
        "en": "Reminders are on, {delta} before each class. Change it with /remind 30 or "
        "add one when the class starts with /remind start on.",
        "pl": "Przypomnienia włączone, {delta} przed każdymi zajęciami. Zmienisz to przez "
        "/remind 30, a przypomnienie w chwili startu dodasz przez /remind start on.",
    },
    "remind_both": {
        "en": "Reminders are on: {delta} before each class and again when it starts "
        "(/remind 30 changes the first, /remind start off drops the second).",
        "pl": "Przypomnienia włączone: {delta} przed każdymi zajęciami i jeszcze raz w chwili "
        "startu (/remind 30 zmienia pierwsze, /remind start off wyłącza drugie).",
    },
    "remind_start_only": {
        "en": "I will remind you when each class starts. Add one before it with /remind 15.",
        "pl": "Przypomnę Ci w chwili startu każdych zajęć. Dodatkowe przed nimi ustawisz "
        "przez /remind 15.",
    },
    # ------------------------------------------------------------------ Discord
    "dc.room": {"en": "Room", "pl": "Sala"},
    "dc.teacher": {"en": "Teacher", "pl": "Prowadzący"},
    "dc.groups": {"en": "Groups", "pl": "Grupy"},
    "dc.when": {"en": "When", "pl": "Kiedy"},
    "dc.next": {"en": "Next class", "pl": "Następne zajęcia"},
    "dc.in_progress": {"en": "In progress now", "pl": "Trwa teraz"},
    "dc.reminder": {"en": "Reminder", "pl": "Przypomnienie"},
    "dc.cancelled": {"en": "Cancelled", "pl": "Odwołane"},
    "dc.ends": {"en": "ends", "pl": "koniec"},
    "dc.starts": {"en": "starts", "pl": "start"},
    "dc.started": {"en": "Starting now", "pl": "Zaczyna się"},
    "dc.more": {"en": "... and {n} more", "pl": "... i jeszcze {n}"},
    "dc.footer": {
        "en": "Times in {tz} · /help for all commands",
        "pl": "Czas: {tz} · /help pokazuje wszystkie komendy",
    },
    "dc.dm_hint": {
        "en": (
            "Reminders arrive as direct messages. Allow DMs from this server's members "
            "(Privacy Settings), otherwise I cannot reach you."
        ),
        "pl": (
            "Przypomnienia przychodzą w wiadomościach prywatnych. Zezwól na DM od członków "
            "serwera (Ustawienia prywatności), inaczej nie dotrę do Ciebie."
        ),
    },
    "dc.help_title": {"en": "plan-bot: your timetable", "pl": "plan-bot: Twój plan zajęć"},
    "dc.help_ask": {
        "en": (
            "You can also just write to me in a DM: "
            '"what\'s next?", "today", "tomorrow", "week", "remind me 30 min before". '
            "Mention me in a server and the answer comes by DM."
        ),
        "pl": (
            "Możesz też po prostu napisać do mnie w DM: "
            '"kiedy mam następne zajęcia?", "co mam jutro", "plan na tydzień", '
            '"przypomnij 30 min przed". Gdy wspomnisz mnie na serwerze, odpowiem w DM.'
        ),
    },
    "dc.privacy": {
        "en": "Your timetable belongs to you, not to the channel: answers are visible only to you.",
        "pl": "Plan należy do Ciebie, nie do kanału: odpowiedzi widzisz tylko Ty.",
    },
    "dc.answer_in_dm": {
        "en": "I sent you the answer in a direct message, so your timetable stays private.",
        "pl": "Odpowiedź wysłałem Ci w wiadomości prywatnej, żeby Twój plan nie był publiczny.",
    },
    "dc.dm_closed": {
        "en": (
            "I cannot send you a direct message. Use a slash command such as /next or /today "
            "here: only you will see the answer. Or allow DMs from this server's members."
        ),
        "pl": (
            "Nie mogę wysłać Ci wiadomości prywatnej. Użyj tutaj komendy, np. /next albo "
            "/today: odpowiedź zobaczysz tylko Ty. Albo zezwól na DM od członków serwera."
        ),
    },
    "nl.unknown": {
        "en": (
            "I did not get that. I can show your timetable: ask for the next class, today, "
            "tomorrow or the week, or use the buttons below. /help lists all commands."
        ),
        "pl": (
            "Nie rozumiem. Mogę pokazać Twój plan: zapytaj o następne zajęcia, dzisiaj, jutro "
            "albo tydzień, albo użyj przycisków. /help pokazuje wszystkie komendy."
        ),
    },
    "dc.subscribe_title": {"en": "Your timetable link", "pl": "Link do Twojego planu"},
    "dc.subscribe_label": {"en": "ICS / iCal link", "pl": "Link ICS / iCal"},
    "dc.link_warning": {
        "en": (
            "Everybody in this channel can see the link you posted; consider deleting your "
            "message. Next time send it in a DM or use /subscribe: only you see that."
        ),
        "pl": (
            "Wszyscy na tym kanale widzą wysłany link; rozważ usunięcie wiadomości. "
            "Następnym razem wyślij go w DM albo użyj /subscribe: to widzisz tylko Ty."
        ),
    },
    "dc.forget_confirm": {
        "en": "This deletes your timetable link, settings and stored classes. Confirm?",
        "pl": "To usunie link do planu, ustawienia i zapisane zajęcia. Potwierdzasz?",
    },
    "dc.forget_yes": {"en": "Yes, delete everything", "pl": "Tak, usuń wszystko"},
    "choice.this_week": {"en": "This week", "pl": "Ten tydzień"},
    "choice.next_week": {"en": "Next week", "pl": "Przyszły tydzień"},
    "choice.on": {"en": "On", "pl": "Włączone"},
    "choice.off": {"en": "Off", "pl": "Wyłączone"},
    "cmd.remind_set": {
        "en": "Remind me N minutes before each class",
        "pl": "Przypomnij mi N minut przed każdymi zajęciami",
    },
    "cmd.remind_start": {
        "en": "Remind me when a class starts (on or off)",
        "pl": "Przypomnij mi w chwili startu zajęć (włącz lub wyłącz)",
    },
    "arg.remind_start": {"en": "On or off", "pl": "Włącz lub wyłącz"},
    "cmd.remind_list": {"en": "Show the current reminder", "pl": "Pokaż obecne przypomnienie"},
    "cmd.remind_off": {"en": "Turn reminders off", "pl": "Wyłącz przypomnienia"},
    "arg.remind_minutes": {
        "en": "Minutes before class (1-1440)",
        "pl": "Minuty przed zajęciami (1-1440)",
    },
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
