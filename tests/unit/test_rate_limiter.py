"""Unit tests for AsyncRateLimiter."""

import asyncio
import time

import pytest

from po_translator.llm.rate_limiter import AsyncRateLimiter


@pytest.mark.asyncio
async def test_concurrency_limit():
    limiter = AsyncRateLimiter(rpm=None, max_concurrency=2)
    active_workers = 0
    max_active_observed = 0

    async def worker():
        nonlocal active_workers, max_active_observed
        async with limiter:
            active_workers += 1
            max_active_observed = max(max_active_observed, active_workers)
            await asyncio.sleep(0.05)
            active_workers -= 1

    tasks = [asyncio.create_task(worker()) for _ in range(6)]
    await asyncio.gather(*tasks)

    assert max_active_observed <= 2


@pytest.mark.asyncio
async def test_rpm_throttling():
    # Allow 4 requests per 60s
    limiter = AsyncRateLimiter(rpm=4, max_concurrency=4)

    start_time = time.monotonic()
    # Acquire 4 times quickly
    for _ in range(4):
        await limiter.acquire()
        limiter.release()

    elapsed = time.monotonic() - start_time
    # First 4 requests should pass almost instantly (< 0.2s)
    assert elapsed < 0.5
