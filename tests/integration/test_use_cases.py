"""End-to-End Integration Tests for all core Use Cases (UC-1.1 to UC-2.3).
Validates end-to-end orchestration, tool chaining, citation verification, and guardrails (SDD Section 3.2).
"""

import pytest
from src.agent.core import default_agent
from src.api.auth import OBOIdentityBroker


@pytest.mark.asyncio
async def test_uc_1_1_grounded_policy_qa():
    """UC-1.1: Grounded Policy Q&A with Citation Verification."""
    agent = default_agent
    res = await agent.execute_turn(
        user_message="What is the company's bereavement leave policy?",
        employee_id="EMP-10492"
    )
    assert res.blocked is False
    assert "policy_search_knowledge_base" in res.tool_calls_executed
    assert "20 work days" in res.reply or "4 weeks" in res.reply
    assert "pet loss" in res.reply
    assert len(res.citations) > 0
    assert "https://intranet.altostrat.com/policies/singapore#section-22" in res.citations[0]["url"]


@pytest.mark.asyncio
async def test_uc_1_2_hr_self_service_leave_submission():
    """UC-1.2: HR Self-Service Transaction (WorkWeek Leave Submission)."""
    agent = default_agent
    res = await agent.execute_turn(
        user_message="Please submit a vacation request for next week.",
        employee_id="EMP-10492"
    )
    assert res.blocked is False
    assert "workweek_get_leave_balances" in res.tool_calls_executed
    assert "workweek_submit_leave_request" in res.tool_calls_executed
    assert "LV-" in res.reply
    assert "successfully submitted" in res.reply


@pytest.mark.asyncio
async def test_uc_1_3_it_incident_status_and_duplicate_handling():
    """UC-1.3: IT Incident Management (ServiceImmediately Ticket Query & Duplicate Detection)."""
    agent = default_agent

    # 1. Query Status of ticket INC123456
    status_res = await agent.execute_turn(
        user_message="What is the status of ticket INC123456?",
        employee_id="EMP-10492"
    )
    assert status_res.blocked is False
    assert "service_immediately_get_ticket" in status_res.tool_calls_executed
    assert "INC123456" in status_res.reply
    assert "In Progress" in status_res.reply
    assert "Sarah Chen" in status_res.reply

    # 2. Inquire about creating a duplicate VPN ticket
    dup_res = await agent.execute_turn(
        user_message="Create an IT ticket because my VPN connection keeps dropping.",
        employee_id="EMP-10492"
    )
    assert dup_res.blocked is False
    assert "service_immediately_create_incident" in dup_res.tool_calls_executed
    assert "INC123456" in dup_res.reply
    assert "add a comment to your existing ticket" in dup_res.reply


@pytest.mark.asyncio
async def test_uc_2_1_equipment_procurement_orchestration():
    """UC-2.1: Cross-System Orchestration — Equipment Procurement."""
    agent = default_agent
    res = await agent.execute_turn(
        user_message="I just read the remote work policy and saw I'm eligible for a home office monitor. Can you verify my remote status and order one for me?",
        employee_id="EMP-10492"
    )
    assert res.blocked is False
    assert "policy_search_knowledge_base" in res.tool_calls_executed
    assert "workweek_get_employee_profile" in res.tool_calls_executed
    assert "service_immediately_create_incident" in res.tool_calls_executed
    assert res.thinking_level == "medium"

    # Verifies policy allowance, confirmed shipping address, and Facilities ticket
    assert "$500 USD" in res.reply
    assert "12 Marina Boulevard" in res.reply
    assert "INC" in res.reply
    assert len(res.citations) > 0


@pytest.mark.asyncio
async def test_uc_2_2_medical_leave_and_email_delegation():
    """UC-2.2: Cross-System Orchestration — Medical Leave & Email Delegation."""
    agent = default_agent
    res = await agent.execute_turn(
        user_message="I need to take short-term medical leave starting next Monday for 2 weeks. What is the process, and can you set it up for me?",
        employee_id="EMP-10492"
    )
    assert res.blocked is False
    assert "policy_search_knowledge_base" in res.tool_calls_executed
    assert "workweek_get_employee_profile" in res.tool_calls_executed
    assert "workweek_get_leave_balances" in res.tool_calls_executed
    assert "workweek_submit_leave_request" in res.tool_calls_executed
    assert "service_immediately_create_incident" in res.tool_calls_executed
    assert res.thinking_level == "medium"

    # Verifies leave submitted, delegation ticket created for David Tan, and 48h MC reminder
    assert "LV-" in res.reply
    assert "INC" in res.reply
    assert "David Tan" in res.reply
    assert "48 hours" in res.reply
    assert len(res.citations) > 0


@pytest.mark.asyncio
async def test_uc_2_3_international_relocation_orchestration():
    """UC-2.3: Cross-System Orchestration — International Relocation."""
    agent = default_agent
    res = await agent.execute_turn(
        user_message="I'm transferring to the London office next month. Can you tell me the relocation allowance, update my record, and get my building access sorted?",
        employee_id="EMP-10492"
    )
    assert res.blocked is False
    assert "policy_search_knowledge_base" in res.tool_calls_executed
    assert "service_immediately_create_incident" in res.tool_calls_executed
    assert res.thinking_level == "medium"

    # Verifies $10,000 USD allowance, Facilities building pass ticket, and address update prompt
    assert "$10,000 USD" in res.reply
    assert "INC" in res.reply
    assert "London" in res.reply
    assert "residential address" in res.reply
    assert len(res.citations) > 0
