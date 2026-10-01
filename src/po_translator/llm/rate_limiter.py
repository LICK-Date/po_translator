"""Dual rate limiter supporting RPM and concurrency control."""

from __future__ import annotations

import asyncio
import collections
import time
from types import TracebackType
from typing import Self


class AsyncRateLimiter:
    """Controls both requests-per-minute (RPM) and maximum concurrent in-flight requests.

    Thread/asyncio safe for managing asynchronous API traffic.
    """

    def __init__(self, rpm: int | None = None, max_concurrency: int = 5) -> None:
        self.rpm = rpm
        self.max_concurrency = max(1, max_concurrency)
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._timestamps: collections.deque[float] = collections.deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a concurrency slot and satisfy RPM constraints."""
        # 1. Acquire concurrency slot first
        await self._semaphore.acquire()

        # 2. Enforce RPM limit if configured
        if self.rpm is not None and self.rpm > 0:
            while True:
                now = time.monotonic()
                sleep_needed = 0.0

                async with self._lock:
                    # Clean out timestamps older than 60 seconds
                    cutoff = now - 60.0
                    while self._timestamps and self._timestamps[0] <= cutoff:
                        self._timestamps.popleft()

                    if len(self._timestamps) < self.rpm:
                        # Capacity available in current minute window
                        self._timestamps.append(now)
                        break
                    else:
                        # Wait until the oldest request exits the 60s sliding window
                        oldest = self._timestamps[0]
                        sleep_needed = max(0.01, 60.0 - (now - oldest))

                if sleep_needed > 0:
                    await asyncio.sleep(sleep_needed)

    def release(self) -> None:
        """Release the acquired concurrency slot."""
        self._semaphore.release()

    async def __aenter__(self) -> Self:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()
