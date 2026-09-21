"""Distributed Rate Limiting & Concurrency Throttling.
Enforces 100 req/min for WorkWeek, 60 req/min for ServiceImmediately,
concurrency semaphores, and 3.0-second priority queueing (SDD Section 5.5.2).
"""

import asyncio
import time
from typing import Dict, Optional
from aiolimiter import AsyncLimiter
from src.config import settings


class BackpressureException(Exception):
    """Raised when priority queue wait time exceeds 3.0 seconds."""
    pass


class BackendRateLimiter:
    """Manages token bucket rate limits and concurrency semaphores."""

    BACKPRESSURE_MESSAGE = (
        "Our HR and IT backend systems are currently experiencing high request volumes. "
        "Your request has been safely queued—please give me a few seconds, or try asking again momentarily."
    )

    def __init__(self):
        # Token bucket limiters (requests per minute)
        self.limiters: Dict[str, AsyncLimiter] = {
            "workweek": AsyncLimiter(max_rate=settings.WORKWEEK_RATE_LIMIT_RPM, time_period=60.0),
            "service_immediately": AsyncLimiter(max_rate=settings.SERVICE_IMMEDIATELY_RATE_LIMIT_RPM, time_period=60.0)
        }
        # Concurrency semaphores (35 WorkWeek, 20 ServiceImmediately)
        self.semaphores: Dict[str, asyncio.Semaphore] = {
            "workweek": asyncio.Semaphore(35),
            "service_immediately": asyncio.Semaphore(20)
        }

    async def acquire(self, service_name: str, timeout: float = 3.0) -> None:
        """Acquires a token and concurrency slot within the specified timeout."""
        limiter = self.limiters.get(service_name)
        semaphore = self.semaphores.get(service_name)

        if not limiter or not semaphore:
            return

        try:
            # Wait for rate limiter and concurrency semaphore within timeout
            await asyncio.wait_for(limiter.acquire(), timeout=timeout)
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise BackpressureException(self.BACKPRESSURE_MESSAGE)

    def release(self, service_name: str) -> None:
        """Releases the concurrency semaphore slot."""
        semaphore = self.semaphores.get(service_name)
        if semaphore:
            try:
                semaphore.release()
            except ValueError:
                pass


default_rate_limiter = BackendRateLimiter()
