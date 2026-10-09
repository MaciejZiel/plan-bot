from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from plan_bot.fetch import (
    DEMO_URL,
    Fetcher,
    FetchError,
    demo_calendar,
    ensure_public_host,
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
