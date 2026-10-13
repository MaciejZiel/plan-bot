from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from plan_bot import fetch as fetch_module
from plan_bot.fetch import (
    DEMO_URL,
    Fetcher,
    FetchError,
    PublicOnlyResolver,
    demo_calendar,
    demo_shift,
    ensure_public_host,
    is_public_address,
    normalize_url,
    redact_url,
)
from tests.conftest import fixture_bytes

ICS = fixture_bytes("edits_before.ics")


async def _ok(request: web.Request) -> web.Response:
    return web.Response(body=ICS, content_type="text/calendar")


async def _redirect(request: web.Request) -> web.Response:
    raise web.HTTPFound("/feed.ics")


async def _loop(request: web.Request) -> web.Response:
    raise web.HTTPFound("/loop")


async def _no_location(request: web.Request) -> web.Response:
    return web.Response(status=302)


async def _big(request: web.Request) -> web.Response:
    return web.Response(body=b"x" * 5000)


async def _big_stream(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse()
    await response.prepare(request)
    for _ in range(10):
        await response.write(b"y" * 1000)
    await response.write_eof()
    return response


async def _to_metadata(request: web.Request) -> web.Response:
    raise web.HTTPFound("http://169.254.169.254/latest/meta-data/")


async def _slow_hop(request: web.Request) -> web.Response:
    await asyncio.sleep(0.4)
    hop = int(request.query.get("n", "0"))
    raise web.HTTPFound(f"/slow-hop?n={hop + 1}" if hop < 3 else "/feed.ics")


async def _slow(request: web.Request) -> web.Response:
    await asyncio.sleep(2)
    return web.Response(body=ICS)


@pytest.fixture
async def server() -> AsyncIterator[TestServer]:
    app = web.Application()
    app.router.add_get("/feed.ics", _ok)
    app.router.add_get("/moved", _redirect)
    app.router.add_get("/loop", _loop)
    app.router.add_get("/nowhere", _no_location)
    app.router.add_get("/big", _big)
    app.router.add_get("/stream", _big_stream)
    app.router.add_get("/slow", _slow)
    app.router.add_get("/to-metadata", _to_metadata)
    app.router.add_get("/slow-hop", _slow_hop)
    srv = TestServer(app)
    await srv.start_server()
    yield srv
    await srv.close()


@pytest.fixture
async def fetcher() -> AsyncIterator[Fetcher]:
    async with Fetcher(allow_private=True, max_bytes=4096, timeout_seconds=1) as f:
        yield f


async def test_fetch_ok_and_redirect(server: TestServer, fetcher: Fetcher) -> None:
    assert await fetcher.fetch(str(server.make_url("/feed.ics"))) == ICS
    assert await fetcher.fetch(str(server.make_url("/moved"))) == ICS


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/missing", "HTTP 404"),
        ("/loop", "Too many redirects"),
        ("/nowhere", "Redirect without a target"),
        ("/big", "too large"),
        ("/stream", "too large"),
        ("/slow", "Download failed: TimeoutError"),
    ],
)
async def test_fetch_errors(server: TestServer, fetcher: Fetcher, path: str, message: str) -> None:
    with pytest.raises(FetchError, match=message):
        await fetcher.fetch(str(server.make_url(path)))


async def test_connection_error(fetcher: Fetcher) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(FetchError, match="Download failed"):
        await fetcher.fetch(f"http://127.0.0.1:{port}/feed.ics")


async def test_private_hosts_are_blocked_by_default(server: TestServer) -> None:
    async with Fetcher() as strict:
        with pytest.raises(FetchError, match="private or local"):
            await strict.fetch(str(server.make_url("/feed.ics")))
        assert await strict.fetch(DEMO_URL) == demo_calendar()


async def test_ensure_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    await ensure_public_host("93.184.215.14")
    with pytest.raises(FetchError):
        await ensure_public_host("10.0.0.1")
    with pytest.raises(FetchError):
        await ensure_public_host("::1")

    async def fail(*args: Any, **kwargs: Any) -> Any:
        raise socket.gaierror("no such host")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fail)
    with pytest.raises(FetchError, match="Cannot resolve host"):
        await ensure_public_host("nope.invalid")


def test_normalize_and_redact() -> None:
    assert normalize_url(" webcal://uni.example/x.ics?token=abc ") == (
        "https://uni.example/x.ics?token=abc"
    )
    assert normalize_url("<https://uni.example/a>") == "https://uni.example/a"
    assert normalize_url("DEMO") == DEMO_URL
    with pytest.raises(FetchError):
        normalize_url("javascript:alert(1)")
    with pytest.raises(FetchError, match="no host"):
        normalize_url("https:///path")
    assert redact_url("https://uni.example/x.ics?token=abc") == "https://uni.example/…"
    assert "demo" in redact_url(DEMO_URL)
    assert demo_calendar().startswith(b"BEGIN:VCALENDAR")


async def test_close_is_idempotent() -> None:
    fetcher = Fetcher()
    await fetcher.close()
    fetcher._client()
    await fetcher.close()
    await fetcher.close()


@pytest.mark.parametrize(
    "raw",
    [
        "https://user:secret@uni.example/x.ics",
        "https://uni.example:99999/x.ics",
        "https://uni.example:0/x.ics",
        "ftp://uni.example/x.ics",
        "file:///etc/passwd",
        "https://uni.example/a b.ics",
        "https://uni.example/" + "a" * 2100,
    ],
)
def test_normalize_rejects_unsafe_links(raw: str) -> None:
    with pytest.raises(FetchError):
        normalize_url(raw)


async def test_resolver_pins_only_public_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = PublicOnlyResolver()
    answers: list[list[str]] = [["93.184.215.14"], ["93.184.215.14", "169.254.169.254"]]

    async def fake(host: str, port: int = 0, family: int = 0) -> list[dict[str, Any]]:
        return [{"host": ip, "port": port, "hostname": host} for ip in answers.pop(0)]

    monkeypatch.setattr(resolver._inner, "resolve", fake)
    assert (await resolver.resolve("good.example", 443))[0]["host"] == "93.184.215.14"
    with pytest.raises(OSError, match=r"fetch\.private"):
        await resolver.resolve("rebind.example", 443)  # one private answer poisons the host
    await resolver.close()


async def test_strict_fetcher_blocks_loopback_at_connect_time(
    server: TestServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bypass the pre-check to prove the connector itself refuses private addresses.
    # (aiohttp does not resolve IP literals, so a host name is needed; literals
    # cannot be rebound and are covered by the pre-check on every hop.)
    async def skip(host: str) -> None:
        return None

    monkeypatch.setattr(fetch_module, "ensure_public_host", skip)
    async with Fetcher(timeout_seconds=2) as strict:
        with pytest.raises(FetchError, match="not allowed"):
            await strict._download(f"http://localhost:{server.port}/feed.ics")


async def test_cache_shares_downloads(server: TestServer) -> None:
    url = str(server.make_url("/feed.ics"))
    async with Fetcher(allow_private=True, cache_seconds=60) as cached:
        assert await cached.fetch(url) == ICS
        await server.close()  # a second request would now fail
        assert await cached.fetch(url) == ICS
    async with Fetcher(allow_private=True, cache_seconds=0, timeout_seconds=1) as uncached:
        with pytest.raises(FetchError):
            await uncached.fetch(url)


def test_demo_calendar_rolls_forward() -> None:
    assert demo_calendar(date(2026, 10, 13)) == demo_calendar()
    assert demo_shift(date(2026, 12, 20)) == timedelta(0)
    assert demo_shift(date(2026, 12, 21)) == timedelta(weeks=7)
    moved = demo_calendar(date(2027, 6, 2))  # a Wednesday
    shift = demo_shift(date(2027, 6, 2))
    assert shift.days % 7 == 0
    assert b"DTSTART:19700329T020000" in moved
    first = (date(2026, 10, 5) + shift).strftime("%Y%m%d").encode()
    assert b"DTSTART;TZID=Europe/Warsaw:" + first + b"T083000" in moved


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.215.14", True),
        ("2001:4860:4860::8888", True),
        ("::ffff:8.8.8.8", True),
        ("64:ff9b::808:808", True),
        ("127.0.0.1", False),
        ("0.0.0.0", False),
        ("10.1.2.3", False),
        ("100.64.0.1", False),
        ("169.254.169.254", False),
        ("192.168.1.1", False),
        ("224.0.0.1", False),
        ("255.255.255.255", False),
        ("::", False),
        ("::1", False),
        ("::ffff:127.0.0.1", False),
        ("::ffff:169.254.169.254", False),
        ("::127.0.0.1", False),
        ("64:ff9b::7f00:1", False),
        ("64:ff9b::a9fe:a9fe", False),
        ("2002:7f00:1::", False),
        ("fe80::1", False),
        ("fd00::1", False),
        ("ff02::1", False),
    ],
)
def test_is_public_address(address: str, public: bool) -> None:
    assert is_public_address(ipaddress.ip_address(address)) is public


async def test_every_redirect_hop_is_checked(
    server: TestServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Treat the loopback test server as public; its redirect to the cloud metadata
    # address must still be refused (before and while connecting).
    real = fetch_module.is_public_address

    def loopback_is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return address == ipaddress.ip_address("127.0.0.1") or real(address)

    monkeypatch.setattr(fetch_module, "is_public_address", loopback_is_public)
    async with Fetcher(timeout_seconds=2) as strict:
        assert await strict.fetch(str(server.make_url("/feed.ics"))) == ICS
        with pytest.raises(FetchError) as caught:
            await strict.fetch(str(server.make_url("/to-metadata")))
        assert caught.value.key == "fetch.private"


async def test_one_deadline_covers_all_redirects(server: TestServer) -> None:
    # Every hop is faster than the timeout, the whole chain is not.
    async with Fetcher(allow_private=True, timeout_seconds=1) as f:
        with pytest.raises(FetchError, match="TimeoutError"):
            await f.fetch(str(server.make_url("/slow-hop")))


async def test_cache_stays_within_its_byte_budget(
    server: TestServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_module, "MAX_CACHE_BYTES", len(ICS) + 10)
    async with Fetcher(allow_private=True, cache_seconds=60) as f:
        first = str(server.make_url("/feed.ics"))
        second = str(server.make_url("/moved"))
        await f.fetch(first)
        await f.fetch(first)  # refreshing an entry does not count it twice
        assert f._cache_bytes == len(ICS)
        await f.fetch(second)
        assert list(f._cache) == [second]
        assert f._cache_bytes == len(ICS)


def test_demo_has_classes_this_week_and_next_week_every_day() -> None:
    from zoneinfo import ZoneInfo

    from plan_bot.ics import Window, expand

    tz = ZoneInfo("Europe/Warsaw")
    day = date(2026, 10, 5)
    while day < date(2028, 1, 1):
        monday = day - timedelta(days=day.weekday())
        start = datetime.combine(monday, time(0), tz)
        lessons = expand(demo_calendar(day), Window(start, start + timedelta(days=14)), tz)
        weeks = {(les.start.date() - monday).days // 7 for les in lessons if not les.cancelled}
        assert weeks == {0, 1}, day
        day += timedelta(days=3)
