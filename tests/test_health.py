from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from plan_bot.health import HealthServer
from plan_bot.service import utc_now


def make(engine: AsyncEngine, last_tick: datetime | None, base_path: str = "") -> HealthServer:
    return HealthServer(
        engine,
        host="127.0.0.1",
        port=0,
        base_path=base_path,
        tick_seconds=30,
        scheduler_last_tick=lambda: last_tick,
        adapters=lambda: ["telegram"],
    )


@pytest.fixture
async def client_for(engine: AsyncEngine) -> AsyncIterator[TestClient]:  # type: ignore[type-arg]
    server = TestServer(make(engine, utc_now(), "/plan-bot").application())
    async with TestClient(server) as client:
        yield client


async def test_healthy(client_for: TestClient) -> None:  # type: ignore[type-arg]
    response = await client_for.get("/plan-bot/healthz")
    body = await response.json()
    assert response.status == 200
    assert body["status"] == "ok"
    assert body["adapters"] == ["telegram"]
    assert body["database"] == "ok"
    assert (await client_for.get("/healthz")).status == 404  # only under the base path


async def test_stalled_scheduler_is_unhealthy(engine: AsyncEngine) -> None:
    status, body = await make(engine, utc_now() - timedelta(minutes=10)).report()
    assert status == 503
    assert body["scheduler"] == "stalled"
    fresh, body = await make(engine, None).report()  # just started, no tick yet
    assert fresh == 200
    assert body["last_tick_age_seconds"] is None


async def test_unreachable_database_is_unhealthy() -> None:
    broken = create_async_engine("sqlite+aiosqlite:////nonexistent-dir/x.db")
    try:
        status, body = await make(broken, utc_now()).report()
    finally:
        await broken.dispose()
    assert status == 503
    assert body["database"] == "error"


async def test_serves_over_a_real_socket(engine: AsyncEngine) -> None:
    server = make(engine, utc_now())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        server.port = port = sock.getsockname()[1]
    stop = asyncio.Event()
    task = asyncio.create_task(server.run(stop))
    try:
        async with aiohttp.ClientSession() as session:
            for _ in range(50):
                try:
                    async with session.get(f"http://127.0.0.1:{port}/healthz") as response:
                        assert response.status == 200
                        break
                except aiohttp.ClientConnectorError:
                    await asyncio.sleep(0.05)
            else:  # pragma: no cover
                pytest.fail("health server did not start")
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)
