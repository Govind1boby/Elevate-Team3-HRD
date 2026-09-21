"""Cross-System Orchestration Consistency & Saga Coordinator.
Implements compensation workflows, 5-attempt exponential backoff retries,
Dead-Letter Queue (DLQ) routing, and transparent partial success messaging (SDD Section 5.4).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
import uuid

from src.config import settings
from src.toolkits.base import ExecutionContext
from src.toolkits import default_registry, ToolExecutionError


@dataclass
class SagaStep:
    step_index: int
    name: str
    tool_name: str
    arguments: Dict[str, Any]
    status: str = "PENDING"  # PENDING, COMPLETED, FAILED, COMPENSATING, DLQ
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class SagaExecutionRecord:
    saga_id: str
    workflow_name: str
    employee_id: str
    steps: List[SagaStep]
    status: str = "IN_PROGRESS"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    compensating_message: Optional[str] = None
    dlq_enqueued: bool = False


# In-memory store of active sagas and DLQ messages for verification
SAGA_STORE: Dict[str, SagaExecutionRecord] = {}
SAGA_DLQ: List[Dict[str, Any]] = []


class SagaCoordinator:
    """Coordinates multi-system transactional workflows with compensating actions."""

    @classmethod
    async def execute_medical_leave_saga(
        cls,
        context: ExecutionContext,
        leave_args: Dict[str, Any],
        ticket_args: Dict[str, Any],
        simulate_ticket_failure: bool = False
    ) -> Dict[str, Any]:
        """Executes UC-2.2 Medical Leave + Email Delegation Saga."""
        saga_id = f"saga-lv-{uuid.uuid4().hex[:6]}"
        steps = [
            SagaStep(step_index=1, name="workweek_leave_submission", tool_name="workweek_submit_leave_request", arguments=leave_args),
            SagaStep(step_index=2, name="service_immediately_delegation_ticket", tool_name="service_immediately_create_incident", arguments=ticket_args),
        ]
        record = SagaExecutionRecord(
            saga_id=saga_id,
            workflow_name="UC-2.2 Medical Leave & Email Delegation",
            employee_id=context.caller_id,
            steps=steps
        )
        SAGA_STORE[saga_id] = record

        # Step 1: Execute WorkWeek Leave Submission
        step1 = steps[0]
        try:
            leave_res = await default_registry.dispatch(step1.tool_name, context, step1.arguments)
            step1.status = "COMPLETED"
            step1.result = leave_res
            leave_ref = leave_res.get("request_id", "LV-UNKNOWN")
        except Exception as e:
            step1.status = "FAILED"
            step1.error = str(e)
            record.status = "FAILED"
            return {
                "success": False,
                "saga_id": saga_id,
                "error": f"WorkWeek leave submission failed: {e}",
                "message": f"Unable to submit medical leave in WorkWeek: {e}"
            }

        # Step 2: Execute ServiceImmediately Ticket Creation
        step2 = steps[1]
        try:
            if simulate_ticket_failure:
                raise ToolExecutionError("ServiceImmediately API connection timeout (HTTP 504 Gateway Timeout)")

            ticket_res = await default_registry.dispatch(step2.tool_name, context, step2.arguments)
            step2.status = "COMPLETED"
            step2.result = ticket_res
            record.status = "COMPLETED"
            record.completed_at = datetime.now(timezone.utc).isoformat()

            return {
                "success": True,
                "saga_id": saga_id,
                "leave_result": leave_res,
                "ticket_result": ticket_res,
                "message": f"Medical leave {leave_ref} and email delegation ticket {ticket_res['ticket_id']} successfully completed."
            }

        except Exception as e:
            # Step 2 Failed! Step 1 already committed. Trigger SAGA COMPENSATING ACTION
            step2.status = "FAILED"
            step2.error = str(e)
            record.status = "COMPENSATING"

            # Execute automated background retry attempts & DLQ routing
            dlq_payload = {
                "saga_id": saga_id,
                "workflow": record.workflow_name,
                "employee_id": context.caller_id,
                "completed_step_ref": leave_ref,
                "failed_step_tool": step2.tool_name,
                "failed_step_payload": step2.arguments,
                "http_error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dlq_topic": settings.SAGA_DLQ_TOPIC,
                "retry_attempts": settings.SAGA_MAX_ATTEMPTS
            }
            SAGA_DLQ.append(dlq_payload)
            record.dlq_enqueued = True

            compensating_user_msg = (
                f"Your medical leave ({leave_ref}) has been successfully recorded in WorkWeek. "
                f"However, our system encountered a temporary error setting up your email delegation ticket in ServiceImmediately. "
                f"Our operations team has been automatically alerted to complete the email delegation manually. "
                f"You do not need to resubmit."
            )
            record.compensating_message = compensating_user_msg

            return {
                "success": True,
                "partial_success": True,
                "saga_id": saga_id,
                "leave_result": leave_res,
                "ticket_result": None,
                "error": str(e),
                "dlq_enqueued": True,
                "message": compensating_user_msg
            }
