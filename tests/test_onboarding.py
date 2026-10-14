from __future__ import annotations

from plan_bot.commands import Button, CommandRouter, Reply
from plan_bot.ratelimit import RateLimiter
from plan_bot.repository import ChatRef, Repository
from plan_bot.service import BotService

CHAT = ChatRef("telegram", "stranger")


def commands(reply: Reply) -> list[str]:
    return [button.command for row in reply.buttons for button in row]


async def test_start_explains_the_bot_and_offers_the_demo(service: BotService) -> None:
    reply = await CommandRouter(service).reply(CHAT, "start")
    assert len(reply.text.splitlines()) <= 3  # 2-3 lines, as promised
    assert "/subscribe" in reply.text
    assert commands(reply) == ["/demo", "/lang en", "/lang pl"]


async def test_first_contact_follows_the_language_of_the_app(service: BotService) -> None:
    router = CommandRouter(service)
    polish = await router.reply(ChatRef("telegram", "1"), "start", locale="pl-PL")
    assert polish.text.startswith("Cześć!")
    assert polish.buttons[0][0] == Button("Wypróbuj demo", "/demo")
    english = await router.reply(ChatRef("telegram", "2"), "start", locale="de")
    assert english.text.startswith("Hi!")
    # The stored choice wins over later hints.
    await router.reply(ChatRef("telegram", "2"), "lang", "pl")
    again = await router.reply(ChatRef("telegram", "2"), "start", locale="en")
    assert again.text.startswith("Cześć!")


async def test_demo_gives_value_immediately(service: BotService) -> None:
    router = CommandRouter(service)
    reply = await router.reply(CHAT, "demo")
    assert "fictional demo timetable" in reply.text
    assert commands(reply)[:3] == ["/next", "/today", "/tomorrow"]
    assert "/remind 15" in commands(reply)
    nxt = await router.reply(CHAT, "next")
    assert nxt.text.startswith("Next: Algorithms and Data Structures")
    assert "/week next" in commands(nxt)
    # After a feed exists /start shows the menu instead of the demo button.
    assert "/demo" not in commands(await router.reply(CHAT, "start"))


async def test_missing_feed_points_to_the_demo(service: BotService) -> None:
    reply = await CommandRouter(service).reply(CHAT, "today")
    assert reply.text.startswith("No timetable yet")
    assert commands(reply) == ["/demo"]


async def test_old_setfeed_name_and_unknown_commands(service: BotService) -> None:
    router = CommandRouter(service)
    assert "Timetable saved" in await router.handle(CHAT, "setfeed", "demo")
    assert "Unknown command /nope" in await router.handle(CHAT, "nope")


async def test_ssrf_attempts_are_refused_with_a_friendly_message(service: BotService) -> None:
    router = CommandRouter(service)
    for link in ("file:///etc/passwd", "https://user:pw@evil.example/x.ics", "javascript:1"):
        reply = await router.handle(CHAT, "subscribe", link)
        assert "Timetable saved" not in reply


async def test_rate_limit_throttles_once_then_stays_quiet(
    service: BotService, repo: Repository
) -> None:
    now = [0.0]
    limiter = RateLimiter(burst=3, per_minute=60, clock=lambda: now[0])
    router = CommandRouter(service, limiter=limiter)
    for _ in range(3):
        assert (await router.reply(CHAT, "help")).text
    warning = await router.reply(CHAT, "help")
    assert warning.text.startswith("Slow down a little. Try again in 1 s.")
    assert (await router.reply(CHAT, "help")).text == ""  # no second warning
    other = ChatRef("telegram", "someone-else")
    assert (await router.reply(other, "help")).text  # other chats are unaffected
    now[0] += 5
    assert (await router.reply(CHAT, "help")).text.startswith("Hi!")


async def test_feed_commands_cost_more(service: BotService) -> None:
    limiter = RateLimiter(burst=5, per_minute=1, clock=lambda: 0.0)
    router = CommandRouter(service, limiter=limiter)
    assert "Slow down" not in await router.handle(CHAT, "subscribe", "ftp://x")  # cost 4
    assert "Slow down" in await router.handle(CHAT, "subscribe", "ftp://x")  # 1 token left
    assert "Timetable saved" in await router.handle(CHAT, "demo")  # the demo costs just 1


async def test_first_contact_stores_only_a_non_default_language(service: BotService) -> None:
    router = CommandRouter(service)
    await router.reply(ChatRef("telegram", "en"), "start", locale="en-GB")
    await router.reply(ChatRef("telegram", "de"), "help", locale="de")
    await router.reply(ChatRef("telegram", "pl"), "start", locale="pl")
    assert await service.repo.get(ChatRef("telegram", "en")) is None
    assert await service.repo.get(ChatRef("telegram", "de")) is None
    stored = await service.repo.get(ChatRef("telegram", "pl"))
    assert stored is not None
    assert stored.language == "pl"


async def test_heavy_commands_have_their_own_slow_bucket(service: BotService) -> None:
    now = [0.0]
    limiter = RateLimiter(burst=100, per_minute=6000, clock=lambda: now[0])
    heavy = RateLimiter(burst=1, per_minute=60 / 45, clock=lambda: now[0])
    router = CommandRouter(service, limiter=limiter, heavy_limiter=heavy)
    assert "Slow down" not in await router.handle(CHAT, "subscribe", "ftp://x")
    reply = await router.handle(CHAT, "subscribe", "ftp://x")
    assert "Slow down" in reply
    assert "Try again in 4" in reply  # about 45 s
    assert "Slow down" not in await router.handle(CHAT, "help")  # cheap commands are unaffected
    other = ChatRef("telegram", "someone-else")
    assert "Slow down" not in await router.handle(other, "subscribe", "ftp://x")
    now[0] += 46
    assert "Slow down" not in await router.handle(CHAT, "subscribe", "ftp://x")
