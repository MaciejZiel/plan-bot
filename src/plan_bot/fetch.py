"""Download ICS feeds safely: size limits, timeouts and no requests to private hosts."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from datetime import date, timedelta
from importlib import resources
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

from plan_bot.i18n import tr

DEMO_URL = "demo"
MAX_REDIRECTS = 5
MAX_URL_LENGTH = 2048
USER_AGENT = "plan-bot/0.2 (+https://github.com/MaciejZiel/plan-bot)"
#: The bundled demo timetable is written for this Monday and is shifted by whole
#: weeks once it has expired, so a stranger always sees classes this week.
DEMO_ANCHOR = date(2026, 10, 5)
DEMO_VALID_UNTIL = date(2027, 1, 10)
_ICS_DATE = re.compile(r"(?<![0-9])(20\d{2})(\d{2})(\d{2})(?=T\d{6}|(?![0-9]))")


class FetchError(Exception):
    """The feed could not be downloaded; the message is safe to show to users.

    ``key`` and ``params`` identify the message in :mod:`plan_bot.i18n`, so the
    chat can show it in the user's language; ``str(error)`` is the English text.
    """

    def __init__(self, key: str, **params: object) -> None:
        super().__init__(tr("en", key, **params))
        self.key = key
        self.params = params

    def localized(self, lang: str) -> str:
        return tr(lang, self.key, **self.params)


def normalize_url(raw: str) -> str:
    url = raw.strip().strip("<>")
    if url.lower() == DEMO_URL:
        return DEMO_URL
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    if len(url) > MAX_URL_LENGTH:
        raise FetchError("url.too_long")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in url):
        raise FetchError("url.chars")
    try:
        parts = urlsplit(url)
        port = parts.port  # raises ValueError for a malformed port
    except ValueError as exc:
        raise FetchError("url.invalid") from exc
    if parts.scheme not in {"http", "https"}:
        raise FetchError("url.scheme")
    if not parts.hostname:
        raise FetchError("url.no_host")
    if parts.username is not None or parts.password is not None:
        raise FetchError("url.credentials")
    if port == 0:
        raise FetchError("url.invalid")
    return urlunsplit(parts)


def redact_url(url: str) -> str:
    """Hide the path and query, which often contain a personal access token."""
    if url == DEMO_URL:
        return "bundled fictional demo timetable"
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}/…"


def demo_shift(today: date) -> timedelta:
    """Whole weeks by which the bundled timetable is moved so it covers ``today``."""
    if today <= DEMO_VALID_UNTIL:
        return timedelta(0)
    monday = today - timedelta(days=today.weekday())
    return timedelta(weeks=(monday - DEMO_ANCHOR).days // 7 - 4)


def demo_calendar(today: date | None = None) -> bytes:
    raw = resources.files("plan_bot").joinpath("data/sample.ics").read_bytes()
    shift = demo_shift(today) if today is not None else timedelta(0)
    if not shift:
        return raw

    def move(match: re.Match[str]) -> str:
        moved = date(int(match[1]), int(match[2]), int(match[3])) + shift
        return f"{moved:%Y%m%d}"

    return _ICS_DATE.sub(move, raw.decode("utf-8")).encode("utf-8")


async def ensure_public_host(host: str) -> None:
    """Reject hosts resolving to loopback, private, link-local or reserved ranges."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError("fetch.resolve", host=host) from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise FetchError("fetch.private")


class PublicOnlyError(OSError):
    """Raised by the resolver; carries the :class:`FetchError` to report."""

    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.error = FetchError(key, **params)


class PublicOnlyResolver(AbstractResolver):
    """Resolve host names and hand only validated public addresses to the connector.

    Validating inside the connector's resolver (instead of in a separate check
    before connecting) closes the DNS-rebinding window: the socket is opened to
    the very address that passed the check.
    """

    def __init__(self) -> None:
        self._inner = aiohttp.ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        try:
            infos = await self._inner.resolve(host, port, family)
        except OSError as exc:
            raise PublicOnlyError("fetch.resolve", host=host) from exc
        for info in infos:
            if not ipaddress.ip_address(info["host"]).is_global:
                raise PublicOnlyError("fetch.private")
        return list(infos)

    async def close(self) -> None:
        await self._inner.close()


class Fetcher:
    """The one shared downloader: validated, size/time-limited, cached and polite."""

    def __init__(
        self,
        *,
        max_bytes: int = 5_000_000,
        timeout_seconds: float = 20,
        allow_private: bool = False,
        cache_seconds: float = 120,
        max_concurrency: int = 4,
    ) -> None:
        self.max_bytes = max_bytes
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.allow_private = allow_private
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, bytes]] = {}
        self.max_concurrency = max_concurrency
        self._slots = asyncio.Semaphore(max_concurrency)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                resolver=None if self.allow_private else PublicOnlyResolver(),
                limit=self.max_concurrency,
                limit_per_host=2,
            )
            self._session = aiohttp.ClientSession(
                timeout=self.timeout, headers={"User-Agent": USER_AGENT}, connector=connector
            )
        return self._session

    async def fetch(self, url: str) -> bytes:
        if url == DEMO_URL:
            return demo_calendar()
        current = normalize_url(url)
        cached = self._cache.get(current)
        if cached is not None and time.monotonic() - cached[0] < self.cache_seconds:
            return cached[1]
        async with self._slots:
            data = await self._download(current)
        if self.cache_seconds > 0:
            if len(self._cache) >= 256:
                self._cache.pop(next(iter(self._cache)))
            self._cache[current] = (time.monotonic(), data)
        return data

    async def _download(self, current: str) -> bytes:
        for _ in range(MAX_REDIRECTS + 1):
            host = urlsplit(current).hostname
            assert host is not None
            if not self.allow_private:
                await ensure_public_host(host)
            try:
                async with self._client().get(current, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise FetchError("fetch.redirect")
                        current = normalize_url(urljoin(current, location))
                        continue
                    if response.status != 200:
                        raise FetchError("fetch.http", status=response.status)
                    return await self._read(response)
            except aiohttp.ClientConnectorError as exc:
                if isinstance(exc.os_error, PublicOnlyError):
                    raise exc.os_error.error from exc
                raise FetchError("fetch.failed", kind="ClientConnectorError") from exc
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise FetchError("fetch.failed", kind=type(exc).__name__) from exc
        raise FetchError("fetch.redirects")

    async def _read(self, response: aiohttp.ClientResponse) -> bytes:
        length = response.content_length
        if length is not None and length > self.max_bytes:
            raise FetchError("fetch.too_large")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > self.max_bytes:
                raise FetchError("fetch.too_large")
            chunks.append(chunk)
        return b"".join(chunks)
