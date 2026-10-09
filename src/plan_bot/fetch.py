"""Download ICS feeds safely: size limits, timeouts and no requests to private hosts."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from importlib import resources
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp

DEMO_URL = "demo"
MAX_REDIRECTS = 5
USER_AGENT = "plan-bot/0.1 (+https://github.com/MaciejZiel/plan-bot)"


class FetchError(Exception):
    """The feed could not be downloaded; the message is safe to show to users."""


def normalize_url(raw: str) -> str:
    url = raw.strip().strip("<>")
    if url.lower() == DEMO_URL:
        return DEMO_URL
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise FetchError("The link must start with https://, http:// or webcal://")
    if not parts.hostname:
        raise FetchError("The link has no host name")
    return urlunsplit(parts)


def redact_url(url: str) -> str:
    """Hide the path and query, which often contain a personal access token."""
    if url == DEMO_URL:
        return "bundled fictional demo timetable"
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}/…"


def demo_calendar() -> bytes:
    return resources.files("plan_bot").joinpath("data/sample.ics").read_bytes()


async def ensure_public_host(host: str) -> None:
    """Reject hosts resolving to loopback, private, link-local or reserved ranges."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError(f"Cannot resolve host {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise FetchError("Links to private or local network addresses are not allowed")


class Fetcher:
    def __init__(
        self,
        *,
        max_bytes: int = 5_000_000,
        timeout_seconds: float = 20,
        allow_private: bool = False,
    ) -> None:
        self.max_bytes = max_bytes
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.allow_private = allow_private
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
            self._session = aiohttp.ClientSession(
                timeout=self.timeout, headers={"User-Agent": USER_AGENT}
            )
        return self._session

    async def fetch(self, url: str) -> bytes:
        if url == DEMO_URL:
            return demo_calendar()
        current = normalize_url(url)
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
                            raise FetchError("Redirect without a target")
                        current = normalize_url(urljoin(current, location))
                        continue
                    if response.status != 200:
                        raise FetchError(f"The server answered HTTP {response.status}")
                    return await self._read(response)
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise FetchError(f"Download failed: {type(exc).__name__}") from exc
        raise FetchError("Too many redirects")

    async def _read(self, response: aiohttp.ClientResponse) -> bytes:
        length = response.content_length
        if length is not None and length > self.max_bytes:
            raise FetchError("The calendar file is too large")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > self.max_bytes:
                raise FetchError("The calendar file is too large")
            chunks.append(chunk)
        return b"".join(chunks)
