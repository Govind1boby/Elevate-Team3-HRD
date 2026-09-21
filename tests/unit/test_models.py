"""Unit tests for Pydantic data schemas across WorkWeek, ServiceImmediately, and Policy RAG.
"""

from datetime import date, timedelta
import pytest
from pydantic import ValidationError

from src.toolkits.workweek.models import (
    ContactInfo,
    UpdateContactInfoRequest,
    SubmitLeaveRequest,
)
from src.toolkits.service_immediately.models import (
    CreateIncidentRequest,
    TicketCategory,
    TicketPriority,
    TicketState,
)


def test_contact_info_valid_e164():
    contact = ContactInfo(
        home_address="12 Marina Boulevard, Singapore 018982",
        phone_number="+65 9123 4567"
    )
    assert contact.home_address == "12 Marina Boulevard, Singapore 018982"
    assert contact.phone_number == "+65 9123 4567"


def test_contact_info_invalid_phone():
    with pytest.raises(ValidationError):
        ContactInfo(
            home_address="12 Marina Boulevard, Singapore 018982",
            phone_number="not-a-number"
        )


def test_update_contact_info_validation():
    req = UpdateContactInfoRequest(phone_number="+6591234567")
    assert req.phone_number == "+6591234567"

    # Must have at least one field
    with pytest.raises(ValidationError):
        UpdateContactInfoRequest()


def test_submit_leave_request_dates():
    today = date.today()
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)

    # Valid request
    req = SubmitLeaveRequest(
        employee_id="EMP-10492",
        leave_type="Vacation",
        start_date=tomorrow.isoformat(),
        end_date=next_week.isoformat(),
        work_days=5.0
    )
    assert req.work_days == 5.0

    # Start date in past should fail
    past_date = today - timedelta(days=2)
    with pytest.raises(ValidationError):
        SubmitLeaveRequest(
            employee_id="EMP-10492",
            leave_type="Vacation",
            start_date=past_date.isoformat(),
            end_date=tomorrow.isoformat(),
            work_days=3.0
        )

    # Start date > end date should fail
    with pytest.raises(ValidationError):
        SubmitLeaveRequest(
            employee_id="EMP-10492",
            leave_type="Sick",
            start_date=next_week.isoformat(),
            end_date=tomorrow.isoformat(),
            work_days=2.0
        )


def test_service_immediately_incident_priority():
    req = CreateIncidentRequest(
        caller_id="EMP-10492",
        category=TicketCategory.IT,
        short_description="VPN keeps disconnecting",
        description="Detailed description here",
        priority="2 - High"
    )
    assert req.priority == TicketPriority.P2
