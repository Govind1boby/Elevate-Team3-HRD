"""Backend 5xx Circuit Breaker with State Machine & Fast-Fail Queue Evacuation.
Implements CLOSED -> OPEN -> HALF-OPEN state machine, 30s cooldown window,
and <50ms immediate queue evacuation (SDD Section 5.5.3).
"""

from enum import Enum
import time
from typing import Any, Callable, Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenException(Exception):
    """Raised when an operation is rejected because the circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """5xx Circuit Breaker for downstream integration adapters."""

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self.state: CircuitState = CircuitState.CLOSED
        self.consecutive_failures: int = 0
        self.last_failure_time: float = 0.0
        self.last_state_change_time: float = time.time()
        self.half_open_probe_in_flight: bool = False

    def check_state(self) -> None:
        """Evaluates time-based transitions (OPEN -> HALF_OPEN)."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_probe_in_flight = False
                self.last_state_change_time = now

    def record_success(self) -> None:
        """Records a successful operation (HTTP 2xx)."""
        if self.state == CircuitState.HALF_OPEN:
            # Probe succeeded, reset to CLOSED
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0
            self.half_open_probe_in_flight = False
            self.last_state_change_time = time.time()
        elif self.state == CircuitState.CLOSED:
            self.consecutive_failures = 0

    def record_failure(self, error_code: Optional[int] = 500) -> None:
        """Records a 5xx error or connection timeout."""
        now = time.time()
        self.last_failure_time = now
        self.consecutive_failures += 1

        if self.state == CircuitState.HALF_OPEN:
            # Probe failed, trip back to OPEN and restart cooldown
            self.state = CircuitState.OPEN
            self.half_open_probe_in_flight = False
            self.last_state_change_time = now
        elif self.state == CircuitState.CLOSED and self.consecutive_failures >= self.failure_threshold:
            # Trip to OPEN
            self.state = CircuitState.OPEN
            self.last_state_change_time = now

    def acquire(self) -> None:
        """Acquires permission to execute a call.
        Fast-fails in < 50ms with CircuitOpenException if OPEN.
        """
        self.check_state()

        if self.state == CircuitState.OPEN:
            raise CircuitOpenException(
                f"Circuit breaker for service '{self.service_name}' is OPEN "
                f"due to {self.consecutive_failures} consecutive backend failures. "
                f"Fast-failing request immediately."
            )
        elif self.state == CircuitState.HALF_OPEN:
            if self.half_open_probe_in_flight:
                raise CircuitOpenException(
                    f"Circuit breaker for service '{self.service_name}' is HALF_OPEN and test probe is in-flight."
                )
            self.half_open_probe_in_flight = True
