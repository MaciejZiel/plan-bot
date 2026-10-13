from __future__ import annotations

from plan_bot.ratelimit import RateLimiter


def test_bucket_refills_over_time() -> None:
    now = [0.0]
    limiter = RateLimiter(burst=2, per_minute=30, clock=lambda: now[0])  # 1 token / 2 s
    assert limiter.check("a") == 0
    assert limiter.check("a") == 0
    assert limiter.check("a") == 2
    assert limiter.should_warn("a")
    assert not limiter.should_warn("a")
    now[0] = 2.0
    assert limiter.check("a") == 0
    assert limiter.should_warn("a")  # a new burst may warn again


def test_cost_and_zero_rate() -> None:
    limiter = RateLimiter(burst=4, per_minute=60, clock=lambda: 0.0)
    assert limiter.check("a", cost=4) == 0
    assert limiter.check("a", cost=4) == 4
    assert not limiter.should_warn("unknown")
    frozen = RateLimiter(burst=1, per_minute=0, clock=lambda: 0.0)
    assert frozen.check("a") == 0
    assert frozen.check("a") == 3600


def test_idle_buckets_are_evicted() -> None:
    now = [0.0]
    limiter = RateLimiter(burst=1, per_minute=60, clock=lambda: now[0], max_entries=3)
    for key in "abc":
        limiter.check(key)
    now[0] = 10.0
    limiter.check("d")  # triggers eviction of the three idle buckets
    assert list(limiter._buckets) == ["d"]
    busy = RateLimiter(burst=1, per_minute=0.001, clock=lambda: 0.0, max_entries=10)
    for index in range(10):
        busy.check(str(index))
    busy.check("new")  # nothing is idle: the oldest tenth goes
    assert "0" not in busy._buckets
    assert "new" in busy._buckets


def test_cost_above_the_burst_is_still_possible() -> None:
    now = [0.0]
    limiter = RateLimiter(burst=2, per_minute=60, clock=lambda: now[0])
    assert limiter.check("chat", cost=4) == 0
    assert limiter.check("chat", cost=4) == 2
    now[0] += 2
    assert limiter.check("chat", cost=4) == 0
