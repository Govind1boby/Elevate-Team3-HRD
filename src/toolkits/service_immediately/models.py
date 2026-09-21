"""Pydantic data contracts and schemas for ServiceImmediately ITSM/HRSD integrations.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class TicketCategory(str, Enum):
    IT = "IT"
    HRSD = "HRSD"
    FACILITIES = "Facilities"


class TicketPriority(str, Enum):
    P1 = "1 - Critical"
    P2 = "2 - High"
    P3 = "3 - Moderate"
    P4 = "4 - Low"


class TicketState(str, Enum):
    NEW = "New"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


# Valid state transitions
VALID_STATE_TRANSITIONS = {
    TicketState.NEW: [TicketState.IN_PROGRESS, TicketState.NEW],
    TicketState.IN_PROGRESS: [TicketState.RESOLVED, TicketState.IN_PROGRESS],
    TicketState.RESOLVED: [TicketState.CLOSED, TicketState.IN_PROGRESS, TicketState.RESOLVED],
    TicketState.CLOSED: [TicketState.CLOSED],
}


class TimelineItem(BaseModel):
    timestamp: str
    author: str
    note: str


class IncidentRecord(BaseModel):
    ticket_id: str
    caller_id: str
    category: TicketCategory
    short_description: str
    description: Optional[str] = None
    priority: TicketPriority
    state: TicketState
    assignee: Optional[str] = "Service Desk Triage"
    created_at: str
    timeline: List[TimelineItem] = Field(default_factory=list)


class CreateIncidentRequest(BaseModel):
    caller_id: str
    category: TicketCategory
    short_description: str = Field(..., max_length=100)
    description: str
    priority: TicketPriority = TicketPriority.P3

    @field_validator("priority", mode="before")
    @classmethod
    def sanitize_priority(cls, v: str) -> str:
        if isinstance(v, str):
            v_clean = v.strip()
            for p in TicketPriority:
                if v_clean.lower() == p.value.lower() or v_clean.lower() == p.name.lower():
                    return p.value
        return v


class CreateIncidentResponse(BaseModel):
    ticket_id: str
    category: TicketCategory
    short_description: str
    priority: TicketPriority
    state: TicketState
    created_at: str
    duplicate_warning: Optional[str] = None


class AddCommentRequest(BaseModel):
    ticket_id: str
    comment: str = Field(..., min_length=1)
    status: Optional[TicketState] = None


class AddCommentResponse(BaseModel):
    ticket_id: str
    status: TicketState
    comment_added: str
    updated_at: str
