"""ServiceImmediately ITSM Domain Toolkit & Adapter.
Provides incident tracking, automated deduplication, priority validation,
and ticket state machine transitions (SDD Section 5.1.6 - 5.1.8).
"""

from datetime import datetime, timezone
import re
import uuid
from typing import Any, Dict, List, Optional
from src.toolkits.base import BaseTool, ExecutionContext, ToolExecutionError
from src.toolkits.service_immediately.models import (
    AddCommentRequest,
    AddCommentResponse,
    CreateIncidentRequest,
    CreateIncidentResponse,
    IncidentRecord,
    TicketCategory,
    TicketPriority,
    TicketState,
    TimelineItem,
    VALID_STATE_TRANSITIONS,
)

# In-memory ticket database with seeded ticket INC123456 per SDD Section 3.2.4
TICKET_STORE: Dict[str, IncidentRecord] = {
    "INC123456": IncidentRecord(
        ticket_id="INC123456",
        caller_id="EMP-10492",
        category=TicketCategory.IT,
        short_description="VPN connection continuously dropping on home WiFi",
        description="Employee reports VPN tunnel drops every 15 minutes when connecting from residential WiFi.",
        priority=TicketPriority.P2,
        state=TicketState.IN_PROGRESS,
        assignee="Sarah Chen",
        created_at="2026-09-17T08:30:00Z",
        timeline=[
            TimelineItem(timestamp="2026-09-17T09:00:00Z", author="System", note="Assigned to Network Operations"),
            TimelineItem(timestamp="2026-09-18T02:15:00Z", author="Sarah Chen", note="Re-provisioned user cert on gateway")
        ]
    )
}

CRITICAL_OUTAGE_KEYWORDS = [
    r"\benterprise[-\s]wide\b",
    r"\bglobal\s+outage\b",
    r"\bdatacenter\s+down\b",
    r"\bsev[-\s]?1\b",
    r"\bcritical\s+production\s+down\b",
    r"\bcatastrophic\b"
]
CRITICAL_REGEX = re.compile(r"|".join(CRITICAL_OUTAGE_KEYWORDS), re.IGNORECASE)


class ServiceImmediatelyGetTicketTool(BaseTool):
    name = "service_immediately_get_ticket"
    description = (
        "Queries incident status, category, priority, assignee, and timeline work notes "
        "for a given ticket number (e.g. INC123456) in ServiceImmediately ITSM."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {
                "type": "string",
                "description": "Ticket number (e.g. INC123456)."
            }
        },
        "required": ["ticket_id"]
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        ticket_id = kwargs.get("ticket_id", "").strip().upper()
        record = TICKET_STORE.get(ticket_id)

        if not record:
            raise ToolExecutionError(f"Ticket {ticket_id} not found in ServiceImmediately.")

        # Anti-IDOR: Employee can only inspect tickets they own
        if record.caller_id != context.caller_id:
            raise ToolExecutionError(
                f"Security Authorization Violation: Authenticated caller '{context.caller_id}' "
                f"is not authorized to view ticket '{ticket_id}' owned by '{record.caller_id}'."
            )

        return record.model_dump()


class ServiceImmediatelyCreateIncidentTool(BaseTool):
    name = "service_immediately_create_incident"
    description = (
        "Creates a new IT, HRSD, or Facilities incident ticket in ServiceImmediately ITSM. "
        "Automatically checks for duplicates within the last 48 hours."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "caller_id": {
                "type": "string",
                "description": "Employee ID of requestor (e.g. EMP-10492). Must match authenticated caller."
            },
            "category": {
                "type": "string",
                "enum": ["IT", "HRSD", "Facilities"],
                "description": "Service category."
            },
            "short_description": {
                "type": "string",
                "description": "Concise summary of issue or request (max 100 characters)."
            },
            "description": {
                "type": "string",
                "description": "Detailed background information, shipping address, or operational context."
            },
            "priority": {
                "type": "string",
                "enum": ["1 - Critical", "2 - High", "3 - Moderate", "4 - Low"],
                "default": "3 - Moderate",
                "description": "Ticket urgency priority."
            }
        },
        "required": ["caller_id", "category", "short_description", "description"]
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        target_caller = kwargs.get("caller_id")
        verified_caller = self.enforce_anti_idor(context, target_caller)
        kwargs["caller_id"] = verified_caller

        req = CreateIncidentRequest(**kwargs)

        # Priority Guardrail (FR-4.3): Priority 1 requires enterprise outage keywords
        if req.priority == TicketPriority.P1:
            combined = f"{req.short_description} {req.description}"
            if not CRITICAL_REGEX.search(combined):
                req.priority = TicketPriority.P3

        # Deduplication Check (FR-4.3): Look for active tickets by caller with matching keywords
        duplicate_warning = None
        req_words = set(re.findall(r"\b[a-z]{3,}\b", req.short_description.lower()))
        for existing in TICKET_STORE.values():
            if existing.caller_id == verified_caller and existing.state in (TicketState.NEW, TicketState.IN_PROGRESS):
                existing_words = set(re.findall(r"\b[a-z]{3,}\b", existing.short_description.lower()))
                common = req_words.intersection(existing_words)
                if len(common) >= 2:
                    duplicate_warning = (
                        f"Potential duplicate detected: Ticket {existing.ticket_id} is already open "
                        f"('{existing.short_description}') with state {existing.state.value}."
                    )
                    break

        new_id = f"INC{uuid.uuid4().int % 900000 + 100000}"
        now_iso = datetime.now(timezone.utc).isoformat()

        record = IncidentRecord(
            ticket_id=new_id,
            caller_id=verified_caller,
            category=req.category,
            short_description=req.short_description,
            description=req.description,
            priority=req.priority,
            state=TicketState.NEW,
            assignee="Service Desk Triage",
            created_at=now_iso,
            timeline=[
                TimelineItem(
                    timestamp=now_iso,
                    author=f"Altostrat-HRAgent [{verified_caller}]",
                    note=f"[Automated by HR Virtual Assistant on behalf of {verified_caller}] Created incident."
                )
            ]
        )
        TICKET_STORE[new_id] = record

        resp = CreateIncidentResponse(
            ticket_id=new_id,
            category=req.category,
            short_description=req.short_description,
            priority=req.priority,
            state=TicketState.NEW,
            created_at=now_iso,
            duplicate_warning=duplicate_warning
        )
        return resp.model_dump()


class ServiceImmediatelyAddCommentTool(BaseTool):
    name = "service_immediately_add_comment"
    description = (
        "Appends a comment or work note to an existing ServiceImmediately incident and optionally advances state."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {
                "type": "string",
                "description": "Ticket identifier (e.g. INC123456)."
            },
            "comment": {
                "type": "string",
                "description": "Work note or comment to append."
            },
            "status": {
                "type": "string",
                "enum": ["New", "In Progress", "Resolved", "Closed"],
                "description": "Optional target lifecycle status."
            }
        },
        "required": ["ticket_id", "comment"]
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        req = AddCommentRequest(**kwargs)
        ticket_id = req.ticket_id.strip().upper()

        record = TICKET_STORE.get(ticket_id)
        if not record:
            raise ToolExecutionError(f"Ticket {ticket_id} not found.")

        # Anti-IDOR verification
        if record.caller_id != context.caller_id:
            raise ToolExecutionError(
                f"Security Authorization Violation: Authenticated caller '{context.caller_id}' "
                f"is not authorized to comment on ticket '{ticket_id}' owned by '{record.caller_id}'."
            )

        # State transition constraint (FR-4.3): Block New -> Closed
        if req.status:
            allowed_targets = VALID_STATE_TRANSITIONS.get(record.state, [])
            if req.status not in allowed_targets:
                raise ToolExecutionError(
                    f"Illegal ticket state transition from '{record.state.value}' to '{req.status.value}'. "
                    f"Direct closure without resolution is blocked."
                )
            record.state = req.status

        now_iso = datetime.now(timezone.utc).isoformat()
        prefixed_comment = f"[Automated by HR Virtual Assistant on behalf of {context.caller_id}] {req.comment}"

        record.timeline.append(TimelineItem(
            timestamp=now_iso,
            author=f"Altostrat-HRAgent [{context.caller_id}]",
            note=prefixed_comment
        ))

        resp = AddCommentResponse(
            ticket_id=ticket_id,
            status=record.state,
            comment_added=prefixed_comment,
            updated_at=now_iso
        )
        return resp.model_dump()
