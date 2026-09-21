"""Unit tests for Phase 5: Enterprise Resiliency, Circuit Breakers & Saga Pattern.
"""

from datetime import date, timedelta
import time
import pytest
from src.resiliency.circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenException
from src.resiliency.rate_limiter import BackendRateLimiter
from src.resiliency.saga import SagaCoordinator, SAGA_DLQ
from src.toolkits.base import ExecutionContext


def test_circuit_breaker_trip_and_evacuate():
    cb = CircuitBreaker("test-service", failure_threshold=5, cooldown_seconds=0.1)

    assert cb.state == CircuitState.CLOSED

    # 4 failures - still closed
    for _ in range(4):
        cb.record_failure(500)
    assert cb.state == CircuitState.CLOSED

    # 5th failure - trips to OPEN
    cb.record_failure(500)
    assert cb.state == CircuitState.OPEN

    # Fast-fail while OPEN
    t0 = time.perf_counter()
    with pytest.raises(CircuitOpenException):
        cb.acquire()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 50.0  # Under 50ms fast-fail

    # Wait for cooldown to test HALF-OPEN
    time.sleep(0.12)
    cb.acquire()  # Allowed probe
    assert cb.state == CircuitState.HALF_OPEN

    # Probe success resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_rate_limiter_acquire_and_release():
    limiter = BackendRateLimiter()
    # Acquire slot
    await limiter.acquire("workweek", timeout=1.0)
    limiter.release("workweek")


@pytest.mark.asyncio
async def test_saga_medical_leave_full_success():
    ctx = ExecutionContext(caller_id="EMP-10492")
    today = date.today()
    start = (today + timedelta(days=10)).isoformat()
    end = (today + timedelta(days=12)).isoformat()

    leave_args = {
        "employee_id": "EMP-10492",
        "leave_type": "Sick",
        "start_date": start,
        "end_date": end,
        "work_days": 2.0
    }
    ticket_args = {
        "caller_id": "EMP-10492",
        "category": "HRSD",
        "short_description": "Email delegation during medical leave",
        "description": "Please route email delegation to manager David Tan."
    }

    res = await SagaCoordinator.execute_medical_leave_saga(ctx, leave_args, ticket_args, simulate_ticket_failure=False)
    assert res["success"] is True
    assert res.get("partial_success") is None
    assert "LV-" in res["leave_result"]["request_id"]
    assert "INC" in res["ticket_result"]["ticket_id"]


@pytest.mark.asyncio
async def test_saga_medical_leave_partial_failure_compensating_action():
    ctx = ExecutionContext(caller_id="EMP-10492")
    today = date.today()
    start = (today + timedelta(days=14)).isoformat()
    end = (today + timedelta(days=16)).isoformat()

    initial_dlq_count = len(SAGA_DLQ)

    leave_args = {
        "employee_id": "EMP-10492",
        "leave_type": "Sick",
        "start_date": start,
        "end_date": end,
        "work_days": 2.0
    }
    ticket_args = {
        "caller_id": "EMP-10492",
        "category": "HRSD",
        "short_description": "Email delegation during medical leave",
        "description": "Please route email delegation to manager David Tan."
    }

    # Simulate ServiceImmediately 504 timeout on Step 2
    res = await SagaCoordinator.execute_medical_leave_saga(ctx, leave_args, ticket_args, simulate_ticket_failure=True)
    assert res["success"] is True
    assert res["partial_success"] is True
    assert res["dlq_enqueued"] is True

    # User transparent compensating message
    assert "successfully recorded in WorkWeek" in res["message"]
    assert "temporary error setting up your email delegation ticket" in res["message"]
    assert "You do not need to resubmit" in res["message"]

    # DLQ enqueued
    assert len(SAGA_DLQ) == initial_dlq_count + 1
    dlq_item = SAGA_DLQ[-1]
    assert dlq_item["employee_id"] == "EMP-10492"
    assert "LV-" in dlq_item["completed_step_ref"]
    assert "saga-compensation-dlq" in dlq_item["dlq_topic"]
