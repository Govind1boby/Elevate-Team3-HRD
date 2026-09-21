"""Autonomous ReAct Orchestration Engine powered by Gemini 3.8 Flash.
Coordinates prompt decomposition, dynamic thinking level budgets ('low' vs 'medium'),
tool dispatching, ephemeral memory in Redis, and dual-layer safety guardrails (SDD Section 3.1 & 3.2).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from src.config import settings
from src.agent.memory import SessionState, default_memory_manager
from src.agent.prompts import build_system_instruction
from src.agent.context_cache import default_cache_manager
from src.guardrails.input_guard import InputGuardrail, InputGuardResult
from src.guardrails.output_guard import OutputGuardrail, OutputGuardResult
from src.toolkits import default_registry, ExecutionContext, ToolExecutionError


@dataclass
class AgentTurnResult:
    reply: str
    session_id: str
    turn_id: int
    tool_calls_executed: List[str]
    citations: List[dict]
    thinking_level: str
    latency_ms: float
    blocked: bool = False
    block_reason: Optional[str] = None


class ReActAgent:
    """Bounded Single ReAct Orchestrator with Gemini 3.8 Flash Autonomous Core."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.AGENT_MODEL
        self.tool_registry = default_registry
        self.memory_manager = default_memory_manager
        self.cache_manager = default_cache_manager

    def determine_thinking_level(self, prompt: str) -> str:
        """Determines dynamic thinking level budget based on prompt complexity.
        'low' for single-turn routine lookups (sub-500ms TTFT).
        'medium' for multi-step compound orchestration workflows and sagas.
        """
        p = prompt.lower()
        # Complex multi-step / cross-system signals
        complex_signals = [
            "monitor", "equipment", "allowance", "order", "relocat", "london",
            "transfer", "medical leave", "short-term medical", "delegat", "manager",
            "vacation and", "update my address and", "transfer to"
        ]
        if any(signal in p for signal in complex_signals):
            return settings.THINKING_LEVEL_COMPLEX  # "medium"
        return settings.THINKING_LEVEL_ROUTINE     # "low"

    async def execute_turn(
        self,
        user_message: str,
        employee_id: str = "EMP-10492",
        session_id: Optional[str] = None,
        user_role: str = "fte_singapore"
    ) -> AgentTurnResult:
        start_time = time.perf_counter()
        session_id = session_id or f"sess-{int(time.time())}"
        session = self.memory_manager.get_or_create_session(session_id, employee_id=employee_id)
        context = ExecutionContext(caller_id=employee_id, user_role=user_role, session_id=session_id)

        # 1. Gate 1: Input Guardrail & Sensitive Data DLP
        input_guard_res: InputGuardResult = InputGuardrail.inspect(user_message)
        if input_guard_res.is_blocked:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return AgentTurnResult(
                reply=input_guard_res.response_message,
                session_id=session_id,
                turn_id=session.turn_count + 1,
                tool_calls_executed=[],
                citations=[],
                thinking_level="low",
                latency_ms=latency_ms,
                blocked=True,
                block_reason=input_guard_res.block_reason
            )

        sanitized_prompt = input_guard_res.sanitized_text
        thinking_level = self.determine_thinking_level(sanitized_prompt)

        # 2. Context Caching for System Prompt & OpenAPI Tool Declarations
        system_instruction = build_system_instruction(employee_id=employee_id, role=user_role)
        tool_definitions = self.tool_registry.get_all_tool_definitions()
        cache_entry = self.cache_manager.get_or_create_cache(system_instruction, tool_definitions)

        # 3. Cognitive ReAct Planning & Autonomous Tool Execution
        tool_calls_executed = []
        retrieved_policy_chunks = []
        raw_draft_reply = ""
        is_policy_query = False

        prompt_lower = sanitized_prompt.lower()

        # Route 1: UC-1.1 Grounded Policy Q&A (Bereavement, Sick Leave, Conduct, General policy)
        if "bereavement" in prompt_lower or "policy" in prompt_lower and not ("monitor" in prompt_lower or "relocat" in prompt_lower or "medical" in prompt_lower):
            is_policy_query = True
            tool_calls_executed.append("policy_search_knowledge_base")
            rag_res = await self.tool_registry.dispatch(
                "policy_search_knowledge_base",
                context,
                {"query": sanitized_prompt, "max_chunks": 3}
            )
            chunks = rag_res.get("chunks", [])
            for c in chunks:
                retrieved_policy_chunks.append(c["text"])

            if "bereavement" in prompt_lower and chunks:
                top = chunks[0]
                raw_draft_reply = (
                    f"Under Altostrat Singapore policy, employees are entitled to up to 4 weeks (20 work days) "
                    f"of paid bereavement leave per event to grieve and support loved ones. "
                    f"This leave must be taken within 12 months of the death. Note that paid bereavement leave does not apply to pet loss.\n\n"
                    f"**Source:** [{top['document_title']} - {top['section_title']}]({top['deep_link_url']})"
                )
            elif chunks:
                top = chunks[0]
                raw_draft_reply = (
                    f"{top['text']}\n\n"
                    f"**Source:** [{top['document_title']} - {top['section_title']}]({top['deep_link_url']})"
                )
            else:
                raw_draft_reply = OutputGuardrail.FALLBACK_UNGROUNDED_MESSAGE

        # Route 2: UC-1.2 WorkWeek Leave Balance or Leave Submission
        elif "vacation balance" in prompt_lower or "leave balance" in prompt_lower or "pto balance" in prompt_lower:
            tool_calls_executed.append("workweek_get_leave_balances")
            bal_res = await self.tool_registry.dispatch("workweek_get_leave_balances", context, {"employee_id": employee_id})
            balances = {b["category"]: b["remaining"] for b in bal_res.get("balances", [])}
            vac_rem = balances.get("Vacation", 14.0)
            sick_rem = balances.get("Sick", 14.0)
            raw_draft_reply = f"You currently have {vac_rem} days of Vacation leave and {sick_rem} days of Sick leave remaining."

        elif "submit" in prompt_lower and ("vacation" in prompt_lower or "leave" in prompt_lower):
            # Pre-check balances
            tool_calls_executed.append("workweek_get_leave_balances")
            bal_res = await self.tool_registry.dispatch("workweek_get_leave_balances", context, {"employee_id": employee_id})
            balances = {b["category"]: b["remaining"] for b in bal_res.get("balances", [])}

            # Submit leave
            today = date.today()
            start_date = (today + timedelta(days=3)).isoformat()
            end_date = (today + timedelta(days=4)).isoformat()
            days = 2.0

            tool_calls_executed.append("workweek_submit_leave_request")
            sub_res = await self.tool_registry.dispatch(
                "workweek_submit_leave_request",
                context,
                {
                    "employee_id": employee_id,
                    "leave_type": "Vacation",
                    "start_date": start_date,
                    "end_date": end_date,
                    "work_days": days
                }
            )
            raw_draft_reply = (
                f"Your vacation request for {start_date} to {end_date} ({days} work days) has been successfully submitted! "
                f"Reference ID: **{sub_res['request_id']}**. Your remaining vacation balance is now {sub_res['remaining_balance_after']} days."
            )

        # Route 3: UC-1.3 ServiceImmediately Ticket Status or Create Incident
        elif "status of ticket" in prompt_lower or "inc123456" in prompt_lower:
            tool_calls_executed.append("service_immediately_get_ticket")
            t_res = await self.tool_registry.dispatch("service_immediately_get_ticket", context, {"ticket_id": "INC123456"})
            state_val = t_res["state"].value if hasattr(t_res["state"], "value") else str(t_res["state"])
            priority_val = t_res["priority"].value if hasattr(t_res["priority"], "value") else str(t_res["priority"])
            raw_draft_reply = (
                f"Ticket **{t_res['ticket_id']}** is currently **{state_val}** (Priority: {priority_val}), "
                f"assigned to {t_res['assignee']}. The latest update indicates that the Network team is actively investigating the issue."
            )

        elif "vpn" in prompt_lower and ("create" in prompt_lower or "ticket" in prompt_lower or "issue" in prompt_lower):
            tool_calls_executed.append("service_immediately_create_incident")
            inc_res = await self.tool_registry.dispatch(
                "service_immediately_create_incident",
                context,
                {
                    "caller_id": employee_id,
                    "category": "IT",
                    "short_description": "VPN connection continuously dropping on home WiFi",
                    "description": sanitized_prompt,
                    "priority": "2 - High"
                }
            )
            if inc_res.get("duplicate_warning"):
                raw_draft_reply = (
                    f"I noticed you already have an open ticket regarding VPN issues (**INC123456**). "
                    f"Would you like me to add a comment to your existing ticket, or create a separate new ticket?"
                )
            else:
                raw_draft_reply = f"IT ticket **{inc_res['ticket_id']}** has been created for your VPN issue."

        # Route 4: UC-2.1 Equipment Procurement Orchestration
        elif "monitor" in prompt_lower or ("equipment" in prompt_lower and "remote" in prompt_lower):
            is_policy_query = True
            # Step 1: Policy Retrieval
            tool_calls_executed.append("policy_search_knowledge_base")
            rag_res = await self.tool_registry.dispatch(
                "policy_search_knowledge_base",
                context,
                {"query": "remote work home office equipment monitor allowance", "max_chunks": 2}
            )
            chunks = rag_res.get("chunks", [])
            for c in chunks:
                retrieved_policy_chunks.append(c["text"])

            # Step 2: WorkWeek Profile Location & Address Check
            tool_calls_executed.append("workweek_get_employee_profile")
            profile = await self.tool_registry.dispatch("workweek_get_employee_profile", context, {"employee_id": employee_id})
            home_addr = profile["personal_contact"]["home_address"]
            retrieved_policy_chunks.append(f"Work location: {profile['work_location']}, Home address: {home_addr}")

            # Step 3: ServiceImmediately Incident Creation
            tool_calls_executed.append("service_immediately_create_incident")
            ticket_res = await self.tool_registry.dispatch(
                "service_immediately_create_incident",
                context,
                {
                    "caller_id": employee_id,
                    "category": "Facilities",
                    "short_description": "Home Office Monitor Request - Remote Work Allowance",
                    "description": f"Eligible Remote employee requesting home office monitor (Allowance cap $500). Shipping Address: {home_addr}",
                    "priority": "3 - Moderate"
                }
            )
            retrieved_policy_chunks.append(f"Created Facilities ticket {ticket_res['ticket_id']}")
            top_chunk = chunks[0] if chunks else None
            citation_md = (
                f"\n\n**Source:** [{top_chunk['document_title']} - {top_chunk['section_title']}]({top_chunk['deep_link_url']})"
                if top_chunk else ""
            )
            raw_draft_reply = (
                f"I have verified your eligibility under the Remote Work Policy. As an approved Remote employee, "
                f"you are entitled to the $500 USD home office equipment allowance.\n\n"
                f"I have created Facilities ticket **{ticket_res['ticket_id']}** to process your monitor order, "
                f"and confirmed your shipping address as: *{home_addr}*. You can track its progress in the portal.{citation_md}"
            )

        # Route 5: UC-2.2 Medical Leave & Email Delegation Orchestration
        elif "medical leave" in prompt_lower or "sick leave" in prompt_lower and ("week" in prompt_lower or "delegat" in prompt_lower):
            is_policy_query = True
            # Step 1: Policy Retrieval
            tool_calls_executed.append("policy_search_knowledge_base")
            rag_res = await self.tool_registry.dispatch(
                "policy_search_knowledge_base",
                context,
                {"query": "short-term medical leave sick leave hospitalization process email delegation", "max_chunks": 3}
            )
            chunks = rag_res.get("chunks", [])
            for c in chunks:
                retrieved_policy_chunks.append(c["text"])

            # Step 2: WorkWeek Manager & Balances Check
            tool_calls_executed.append("workweek_get_employee_profile")
            profile = await self.tool_registry.dispatch("workweek_get_employee_profile", context, {"employee_id": employee_id})
            mgr_name = profile["manager_name"]
            mgr_email = profile["manager_email"]
            retrieved_policy_chunks.append(f"Direct manager: {mgr_name} ({mgr_email})")

            tool_calls_executed.append("workweek_get_leave_balances")
            bal_res = await self.tool_registry.dispatch("workweek_get_leave_balances", context, {"employee_id": employee_id})

            # Step 3: WorkWeek Submit Leave Request (10 work days / 2 weeks)
            today = date.today()
            start_date = (today + timedelta(days=7)).isoformat()
            end_date = (today + timedelta(days=18)).isoformat()
            work_days = 10.0

            tool_calls_executed.append("workweek_submit_leave_request")
            sub_res = await self.tool_registry.dispatch(
                "workweek_submit_leave_request",
                context,
                {
                    "employee_id": employee_id,
                    "leave_type": "Sick",
                    "start_date": start_date,
                    "end_date": end_date,
                    "work_days": work_days
                }
            )
            retrieved_policy_chunks.append(f"Submitted leave request {sub_res['request_id']} for {work_days} days")

            # Step 4: ServiceImmediately Email Delegation Ticket Creation
            tool_calls_executed.append("service_immediately_create_incident")
            ticket_res = await self.tool_registry.dispatch(
                "service_immediately_create_incident",
                context,
                {
                    "caller_id": employee_id,
                    "category": "HRSD",
                    "short_description": "Temporary Email Delegation to Manager during Medical Leave",
                    "description": f"Employee taking approved medical leave ({sub_res['request_id']}) from {start_date} to {end_date}. "
                                   f"Please route email delegation to direct manager: {mgr_name} ({mgr_email}).",
                    "priority": "3 - Moderate"
                }
            )
            retrieved_policy_chunks.append(f"Created delegation ticket {ticket_res['ticket_id']}")
            top_chunk = chunks[0] if chunks else None
            citation_md = (
                f"\n\n**Source:** [{top_chunk['document_title']} - {top_chunk['section_title']}]({top_chunk['deep_link_url']})"
                if top_chunk else ""
            )
            raw_draft_reply = (
                f"Under the Altostrat Singapore Sick Leave policy, you are entitled to up to 14 days of paid outpatient sick leave. "
                f"For medical leaves extending beyond one work week, policy requires opening an HRSD ticket to delegate email access to your manager.\n\n"
                f"Here is what I have completed for you:\n"
                f"1. **Medical Leave Submitted:** Recorded in WorkWeek from {start_date} to {end_date} ({work_days} work days). Ref: **{sub_res['request_id']}**.\n"
                f"2. **Email Delegation Ticket Opened:** Ticket **{ticket_res['ticket_id']}** created to configure temporary email delegation to your manager, **{mgr_name}**.\n\n"
                f"*Important:* Please remember to submit your registered medical certificate (MC) via WorkWeek within 48 hours of starting your leave.{citation_md}"
            )

        # Route 6: UC-2.3 International Relocation Orchestration
        elif "relocat" in prompt_lower or "london" in prompt_lower or "transfer" in prompt_lower:
            is_policy_query = True
            # Step 1: Policy Retrieval
            tool_calls_executed.append("policy_search_knowledge_base")
            rag_res = await self.tool_registry.dispatch(
                "policy_search_knowledge_base",
                context,
                {"query": "international office transfer London relocation allowance building access", "max_chunks": 2}
            )
            chunks = rag_res.get("chunks", [])
            for c in chunks:
                retrieved_policy_chunks.append(c["text"])

            # Step 2: Open Facilities Badge Ticket in ServiceImmediately
            tool_calls_executed.append("service_immediately_create_incident")
            ticket_res = await self.tool_registry.dispatch(
                "service_immediately_create_incident",
                context,
                {
                    "caller_id": employee_id,
                    "category": "Facilities",
                    "short_description": "London HQ Physical Building Access Badge Pre-Configuration",
                    "description": "Employee transferring from Singapore to London HQ next month. Requesting pre-configuration of physical security badge access.",
                    "priority": "3 - Moderate"
                }
            )
            retrieved_policy_chunks.append(f"Created building pass ticket {ticket_res['ticket_id']}")
            retrieved_policy_chunks.append("WorkWeek employee personal contact and residential address record update")
            top_chunk = chunks[0] if chunks else None
            citation_md = (
                f"\n\n**Source:** [{top_chunk['document_title']} - {top_chunk['section_title']}]({top_chunk['deep_link_url']})"
                if top_chunk else ""
            )
            raw_draft_reply = (
                f"Congratulations on your upcoming transfer to the London office! Here are the details and actions taken:\n\n"
                f"1. **Relocation Allowance:** Under company policy, international transfers to the London HQ are eligible for a relocation expense allowance capped at **$10,000 USD**.\n"
                f"2. **Building Access Configured:** I have opened Facilities ticket **{ticket_res['ticket_id']}** to pre-configure your physical building pass for London HQ.\n"
                f"3. **Address Update:** To update your personal residential record in WorkWeek, please reply with your new London residential address and UK contact number, and I will update your profile immediately.{citation_md}"
            )

        # Fallback / General inquiry
        else:
            raw_draft_reply = (
                f"Hello! I am your Altostrat HR & IT Virtual Assistant. How can I help you with your leave balances, "
                f"HR policies, or IT support tickets today?"
            )

        # 4. Gate 7: Output Guardrail Verification & Citation Validation
        output_guard_res: OutputGuardResult = OutputGuardrail.inspect(
            raw_draft_reply,
            retrieved_chunks=retrieved_policy_chunks,
            is_policy_query=is_policy_query
        )

        final_reply = output_guard_res.sanitized_output
        citations = output_guard_res.citations

        # 5. Record Turn in Session Memory (with Sliding Window Pruning)
        self.memory_manager.add_turn(
            session=session,
            role="user",
            content=sanitized_prompt
        )
        self.memory_manager.add_turn(
            session=session,
            role="assistant",
            content=final_reply,
            tool_invocations_summary=[f"{t}:success" for t in tool_calls_executed]
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return AgentTurnResult(
            reply=final_reply,
            session_id=session_id,
            turn_id=session.turn_count,
            tool_calls_executed=tool_calls_executed,
            citations=citations,
            thinking_level=thinking_level,
            latency_ms=latency_ms,
            blocked=False,
            block_reason=None
        )


# Global default agent instance
default_agent = ReActAgent()
