"""Unit tests for Phase 3: Domain Toolkits & Deterministic Adapters.
"""

from datetime import date, timedelta
import pytest
from src.toolkits import default_registry, ExecutionContext, ToolExecutionError, AntiIDORViolationError
from src.toolkits.service_immediately.models import TicketState


@pytest.mark.asyncio
async def test_policy_search_knowledge_base():
    ctx = ExecutionContext(caller_id="EMP-10492")
    res = await default_registry.dispatch("policy_search_knowledge_base", ctx, {"query": "bereavement leave policy"})
    chunks = res["chunks"]
    assert len(chunks) > 0
    assert "Bereavement Leave" in chunks[0]["section_title"]
    assert "https://intranet.altostrat.com/policies/singapore#section-22" in chunks[0]["deep_link_url"]


@pytest.mark.asyncio
async def test_workweek_profile_anti_idor():
    ctx = ExecutionContext(caller_id="EMP-10492")
    # Valid caller
    profile = await default_registry.dispatch("workweek_get_employee_profile", ctx, {"employee_id": "EMP-10492"})
    assert profile["employee_id"] == "EMP-10492"
    assert profile["first_name"] == "Alexander"

    # IDOR attempt: trying to query another employee's profile
    with pytest.raises(AntiIDORViolationError):
        await default_registry.dispatch("workweek_get_employee_profile", ctx, {"employee_id": "EMP-99999"})


@pytest.mark.asyncio
async def test_workweek_update_contact_info():
    ctx = ExecutionContext(caller_id="EMP-10492")
    res = await default_registry.dispatch(
        "workweek_update_contact_info",
        ctx,
        {"home_address": "88 Shenton Way, Singapore 068811", "phone_number": "+6598765432"}
    )
    assert res["status"] == "SUCCESS"
    assert res["updated_contact"]["phone_number"] == "+6598765432"
    assert res["updated_contact"]["home_address"] == "88 Shenton Way, Singapore 068811"


@pytest.mark.asyncio
async def test_workweek_leave_balances():
    ctx = ExecutionContext(caller_id="EMP-10492")
    res = await default_registry.dispatch("workweek_get_leave_balances", ctx, {"employee_id": "EMP-10492"})
    assert res["employee_id"] == "EMP-10492"
    balances = {b["category"]: b["remaining"] for b in res["balances"]}
    assert "Vacation" in balances
    assert "Sick" in balances


@pytest.mark.asyncio
async def test_workweek_submit_leave_and_balance_check():
    ctx = ExecutionContext(caller_id="EMP-10492")
    today = date.today()
    start = (today + timedelta(days=5)).isoformat()
    end = (today + timedelta(days=6)).isoformat()

    # Valid submission (2 days)
    res = await default_registry.dispatch(
        "workweek_submit_leave_request",
        ctx,
        {
            "employee_id": "EMP-10492",
            "leave_type": "Vacation",
            "start_date": start,
            "end_date": end,
            "work_days": 2.0
        }
    )
    assert res["status"] == "SUBMITTED"
    assert "LV-" in res["request_id"]

    # Insufficient balance check (trying to submit 99 days)
    with pytest.raises(ToolExecutionError) as exc_info:
        await default_registry.dispatch(
            "workweek_submit_leave_request",
            ctx,
            {
                "employee_id": "EMP-10492",
                "leave_type": "Vacation",
                "start_date": start,
                "end_date": end,
                "work_days": 99.0
            }
        )
    assert "Insufficient leave balance" in str(exc_info.value)


@pytest.mark.asyncio
async def test_service_immediately_get_ticket():
    ctx = ExecutionContext(caller_id="EMP-10492")
    ticket = await default_registry.dispatch("service_immediately_get_ticket", ctx, {"ticket_id": "INC123456"})
    assert ticket["ticket_id"] == "INC123456"
    assert ticket["category"] == "IT"
    assert ticket["state"] == "In Progress"

    # IDOR attempt: employee with another ID cannot view this ticket
    ctx_other = ExecutionContext(caller_id="EMP-99999")
    with pytest.raises(ToolExecutionError) as exc_info:
        await default_registry.dispatch("service_immediately_get_ticket", ctx_other, {"ticket_id": "INC123456"})
    assert "not authorized" in str(exc_info.value)


@pytest.mark.asyncio
async def test_service_immediately_create_incident_and_duplicate_scan():
    ctx = ExecutionContext(caller_id="EMP-10492")

    # Creating ticket with matching keywords of INC123456 (VPN connection dropping)
    res = await default_registry.dispatch(
        "service_immediately_create_incident",
        ctx,
        {
            "caller_id": "EMP-10492",
            "category": "IT",
            "short_description": "VPN connection drops repeatedly",
            "description": "Home office VPN disconnects every few minutes."
        }
    )
    assert res["ticket_id"].startswith("INC")
    assert res["duplicate_warning"] is not None
    assert "INC123456" in res["duplicate_warning"]


@pytest.mark.asyncio
async def test_service_immediately_add_comment_and_state_machine():
    ctx = ExecutionContext(caller_id="EMP-10492")

    # Valid comment on INC123456
    res = await default_registry.dispatch(
        "service_immediately_add_comment",
        ctx,
        {
            "ticket_id": "INC123456",
            "comment": "Issue re-occurred after router reboot.",
            "status": "In Progress"
        }
    )
    assert res["status"] == "In Progress"
    assert "Automated by HR Virtual Assistant" in res["comment_added"]

    # Create new ticket to test illegal transition (New -> Closed)
    new_ticket = await default_registry.dispatch(
        "service_immediately_create_incident",
        ctx,
        {
            "caller_id": "EMP-10492",
            "category": "Facilities",
            "short_description": "Desk lamp bulb replacement",
            "description": "Bulb is flickering on 2nd floor desk."
        }
    )
    new_id = new_ticket["ticket_id"]

    # Attempt illegal transition: New -> Closed
    with pytest.raises(ToolExecutionError) as exc_info:
        await default_registry.dispatch(
            "service_immediately_add_comment",
            ctx,
            {
                "ticket_id": new_id,
                "comment": "Closing directly",
                "status": "Closed"
            }
        )
    assert "Illegal ticket state transition" in str(exc_info.value)
