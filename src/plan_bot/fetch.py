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
#: Stored in ``ics_url`` for a calendar the user uploaded as a file: there is nothing to
#: refetch. It is not a valid URL, so a user can never set it through ``/subscribe``.
UPLOAD_URL = "upload"
MAX_REDIRECTS = 5
MAX_URL_LENGTH = 2048
#: A timetable is served on a web port; this keeps the bot from probing other services.
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
USER_AGENT = "plan-bot/0.2 (+https://github.com/MaciejZiel/plan-bot)"
#: The bundled demo timetable is written for this Monday and is shifted by whole
#: weeks after ``DEMO_VALID_UNTIL``, so a stranger always sees classes this week
#: and next week. That is the last day before the Christmas break (no classes in
#: the week of 28 Dec) would leave the current or the next week empty.
DEMO_ANCHOR = date(2026, 10, 5)
DEMO_VALID_UNTIL = date(2026, 12, 20)
#: Upper bound on cached feed bytes, so many large feeds cannot exhaust memory.
MAX_CACHE_BYTES = 32_000_000
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_IPV4_COMPATIBLE = ipaddress.ip_network("::/96")
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


def normalize_url(raw: str, *, any_port: bool = False) -> str:
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
    if port is not None and port not in ALLOWED_PORTS and not any_port:
        raise FetchError("url.port")
    return urlunsplit(parts)


def redact_url(url: str) -> str:
    """Hide the path and query, which often contain a personal access token."""
    if url == DEMO_URL:
        return "bundled fictional demo timetable"
    if url == UPLOAD_URL:
        return "uploaded file"
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


def is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for unicast addresses on the public internet.

    Besides :attr:`~ipaddress.IPv4Address.is_global` this rejects multicast and
    IPv6 forms that embed an IPv4 address (IPv4-mapped, IPv4-compatible and the
    NAT64 well-known prefix) unless the embedded address is public itself.
    """
    if not address.is_global or address.is_multicast:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return is_public_address(address.ipv4_mapped)
        if address in _IPV4_COMPATIBLE:
            return False
        if address in _NAT64:
            return is_public_address(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    return True


async def ensure_public_host(host: str) -> None:
    """Reject hosts resolving to loopback, private, link-local or reserved ranges."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError("fetch.resolve") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not is_public_address(address):
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
            raise PublicOnlyError("fetch.resolve") from exc
        for info in infos:
            if not is_public_address(ipaddress.ip_address(info["host"])):
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
        timeout_seconds: float = 10,
        allow_private: bool = False,
        cache_seconds: float = 120,
        max_concurrency: int = 4,
    ) -> None:
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.allow_private = allow_private
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, bytes]] = {}
        self._cache_bytes = 0
        self.max_concurrency = max_concurrency
        self._slots = asyncio.Semaphore(max_concurrency)
        #: One download per host at a time, so one slow server cannot take every slot.
        self._hosts: dict[str, asyncio.Semaphore] = {}
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
        current = normalize_url(url, any_port=self.allow_private)
        cached = self._cache.get(current)
        if cached is not None and time.monotonic() - cached[0] < self.cache_seconds:
            return cached[1]
        async with self._host_slot(current), self._slots:
            try:
                # One deadline for the whole download, redirects included, so a
                # slow server cannot hold a slot for (redirects + 1) timeouts.
                async with asyncio.timeout(self.timeout_seconds):
                    data = await self._download(current)
            except TimeoutError as exc:
                raise FetchError("fetch.failed", kind="TimeoutError") from exc
        if self.cache_seconds > 0:
            self._remember(current, data)
        return data

    def _host_slot(self, url: str) -> asyncio.Semaphore:
        host = (urlsplit(url).hostname or "").lower()
        if len(self._hosts) >= 1024 and host not in self._hosts:
            # Only idle semaphores can be dropped without letting a second download in.
            for name in [n for n, sem in self._hosts.items() if not sem.locked()]:
                del self._hosts[name]
        return self._hosts.setdefault(host, asyncio.Semaphore(1))

    def _remember(self, url: str, data: bytes) -> None:
        """Cache ``data``, dropping expired and then oldest entries to stay within budget."""
        now = time.monotonic()
        self._forget(url)
        for key in [k for k, (at, _) in self._cache.items() if now - at >= self.cache_seconds]:
            self._forget(key)
        while self._cache and (
            len(self._cache) >= 256 or self._cache_bytes + len(data) > MAX_CACHE_BYTES
        ):
            self._forget(next(iter(self._cache)))
        if len(data) <= MAX_CACHE_BYTES:
            self._cache[url] = (now, data)
            self._cache_bytes += len(data)

    def _forget(self, url: str) -> None:
        entry = self._cache.pop(url, None)
        if entry is not None:
            self._cache_bytes -= len(entry[1])

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
                        current = normalize_url(urljoin(current, location), any_port=self.allow_private)
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
