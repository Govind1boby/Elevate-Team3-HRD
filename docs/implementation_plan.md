# Implementation Plan: Enterprise HR Agentic Virtual Assistant (MVP 1)

## 1. Executive Summary & Objective

Based on the updated **MVP Solution Design Document (`docs/sdd-argon.md`)**, this implementation plan outlines the engineering roadmap to build, validate, and deliver the **Enterprise HR Agentic Virtual Assistant (MVP 1)** for Altostrat.

The objective is to establish a hardened, enterprise-grade agentic system capable of resolving routine HR and IT Tier 1 requests (<10s P95 SLA) with:
- **Autonomous Agent Core (Gemini 3.8 Flash):** Powered by Vertex AI's `gemini-3.8-flash` (GA), specifically tuned for long-horizon tool orchestration and agentic reliability, featuring dynamic thinking level budgets (`low` for sub-second routine queries, `medium` for compound workflows and sagas).
- **Pre-LLM Scope Gating (Gemini 3.5 Flash-Lite):** Ultra-fast (<150ms) and cost-effective ($0.10/1M input) intent and domain classification intercepting out-of-scope queries before invoking the main agent runtime.
- **Vertex AI Context Caching:** Pre-caching static system instructions and 8 OpenAPI tool definitions (>12,000 tokens), slashing prompt token costs by up to 75% and reducing Time to First Token (TTFT).
- **Grounded Policy Retrieval (RAG):** Hybrid vector and keyword search over the *Altostrat Singapore Employee Policy Handbook & Conduct Guidelines* with mathematical citation attribution (score ≥ 0.90) and markdown deep links.
- **Transactional Self-Service:** Deterministic, authenticated operations against **WorkWeek HCM** (profile, contact info, leave balances, leave submission) and **ServiceImmediately ITSM** (ticket query, creation, status transition, comments).
- **Complex Cross-System Orchestration:** Multi-step workflows chaining policy retrieval with multi-system operations (UC-2.1 Equipment Procurement, UC-2.2 Medical Leave & Email Delegation, UC-2.3 International Relocation).
- **Zero-Trust Security & Dual-Layer Guardrails:** Inbound prompt injection / jailbreak protection, Singapore NRIC/FIN and clinical medical note DLP redaction (`LIKELIHOOD_POSSIBLE`), Anti-IDOR middleware locks (`caller == session.user_id`), and RFC 8693 OBO token delegation.
- **Enterprise Resiliency:** Bounded ReAct cognitive loop (max 3 iterations), Redis ephemeral sliding-window session memory, 5xx circuit breakers with fast-fail queue evacuation, and the **Saga Pattern** with Pub/Sub Dead-Letter Queue (DLQ) for multi-system transaction consistency.

---

## 2. Target System Architecture & Component Design

```
+----------------------------------------------------------------------------------------------------+
|                                    CLIENT & INGRESS TIER                                           |
|  [Enterprise Web Chat Client / Portal]                                                             |
|           │ (HTTPS / WSS, TLS 1.3, RS256 JWT, HSTS)                                                |
|           ▼                                                                                        |
|  [API Gateway & Session Context Broker] ──► Extracts caller (EMP-10492), verifies OBO scopes       |
+----------------------------------------------------------------------------------------------------+
                                           │
                                           ▼
+----------------------------------------------------------------------------------------------------+
|                                  DUAL-LAYER GUARDRAIL PIPELINE                                     |
|  [Input Guardrail Interceptor]                                                                     |
|    ├── 1. Adversarial & Jailbreak Filter (Regex overrides, prompt injection, system leaks)        |
|    ├── 2. Pre-LLM Scope Gating: Gemini 3.5 Flash-Lite (<150ms edge classification, HR/IT domain)  |
|    └── 3. Sensitive Data DLP (Cloud DLP / Regex at LIKELIHOOD_POSSIBLE: NRIC, Medical terms)      |
+----------------------------------------------------------------------------------------------------+
                                           │ (Sanitized Prompt + Verified Session Context)
                                           ▼
+----------------------------------------------------------------------------------------------------+
|                             AUTONOMOUS AGENT ORCHESTRATION RUNTIME                                 |
|  [Bounded ReAct Orchestrator (LangGraph / Native ReAct Graph)]                                    |
|    ├── Foundation Model: Gemini 3.8 Flash (Vertex AI - GA)                                         |
|    │     • Dynamic Thinking Level: 'low' (~512-1024 tokens) for single-turn routine lookups        |
|    │     • Dynamic Thinking Level: 'medium' (~2048-4096 tokens) for multi-step sagas (UC-2.x)      |
|    ├── Vertex AI Context Caching: Pre-caches static system prompt & 8 OpenAPI tool declarations   |
|    ├── Ephemeral Session Store (Redis): Sliding 10-turn window, 2-sentence summary, 30m TTL   |
|    └── Deterministic Tool Dispatcher & Gate 3 Parameter Validation                                 |
+----------------------------------------------------------------------------------------------------+
                                           │
                                           ▼
+----------------------------------------------------------------------------------------------------+
|                           DOMAIN TOOLKITS & DETERMINISTIC ADAPTERS                                 |
|  [PolicyToolkit]                   [WorkWeekToolkit]                 [ServiceImmediatelyToolkit]  |
|    • policy_search_knowledge_base   • workweek_get_employee_profile    • service_immediately_get_   |
|      (Hybrid search, deep links)    • workweek_update_contact_info       ticket                    |
|                                     • workweek_get_leave_balances     • service_immediately_      |
|                                     • workweek_submit_leave_request      create_incident           |
|                                                                       • service_immediately_add_   |
|                                                                          comment                   |
|  ────────────────────────────────────────────────────────────────────────────────────────────────  |
|  [Gate 3 Middleware Interceptors]:                                                                 |
|    • Anti-IDOR Enforcement: caller_id == session.user_id programmatically injected                 |
|    • Pydantic v2 strict schema validation & type coercion                                          |
|    • Temporal & Balance Checks (start >= today, start <= end, days <= remaining balance)         |
|    • 48-Hour Incident Deduplication Scan                                                           |
+----------------------------------------------------------------------------------------------------+
                                           │
                                           ▼
+----------------------------------------------------------------------------------------------------+
|                            RESILIENCY & TRANSACTIONAL SAGA TIER                                    |
|  ├── 5xx Circuit Breaker (5 consecutive failures -> OPEN, 30s cooldown, fast queue evacuation)     |
|  ├── Distributed Token Bucket Limiter (100 req/min WorkWeek, 60 req/min ServiceImmediately)        |
|  └── Saga Coordinator (Compensating rollback / Pub/Sub DLQ replay / partial success transparency)  |
+----------------------------------------------------------------------------------------------------+
                                           │
                                           ▼
+----------------------------------------------------------------------------------------------------+
|                                 OUTPUT GUARDRAIL & AUDIT TIER                                      |
|  [Output Guardrail Interceptor]                                                                    |
|    ├── Grounding Attribution Check (Score ≥ 0.90, suppresses hallucinated policy advice)          |
|    ├── Citation URL & Markdown Deep Link Validator                                                 |
|    └── Cloud DLP Output Redaction & Tone Filter                                                    |
|  [Immutable Audit Logger]                                                                          |
|    └── Structured BigQuery logging: HMAC-SHA256(employee_id), tool payloads, latency, traces       |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. Project Directory Structure

```
Elevate-Team3-HRD/
├── docs/                                  # SDD and architecture assets (existing)
│   ├── sdd-argon.md
│   └── assets/
├── src/                                   # Production source code
│   ├── __init__.py
│   ├── config.py                          # Config: GEMINI_MODEL="gemini-3.8-flash", GATE_MODEL="gemini-3.5-flash-lite", caching & thinking levels
│   ├── agent/                             # Cognitive ReAct Orchestration
│   │   ├── __init__.py
│   │   ├── core.py                        # ReAct agent loop (bounded max 3 iterations, dynamic thinking level)
│   │   ├── prompts.py                     # System prompt, guardrail directives, tool schemas
│   │   ├── context_cache.py               # Vertex AI Context Caching manager for static prompt & tools
│   │   ├── state.py                       # Conversation turn model & state representations
│   │   └── memory.py                      # Redis sliding window session memory & summarizer
│   ├── guardrails/                        # Dual-layer safety & DLP pipeline
│   │   ├── __init__.py
│   │   ├── input_guard.py                 # Jailbreak/prompt injection filter + Gemini 3.5 Flash-Lite scope gating
│   │   ├── output_guard.py                # Grounding attribution evaluator (>=0.90), citation validator & tone check
│   │   └── dlp.py                         # Singapore NRIC & medical term masking engine (LIKELIHOOD_POSSIBLE)
│   ├── toolkits/                          # Modular domain toolkits & adapters
│   │   ├── __init__.py
│   │   ├── base.py                        # BaseTool, Anti-IDOR middleware, execution context
│   │   ├── policy/                        # Policy Knowledge Search (RAG)
│   │   │   ├── __init__.py
│   │   │   └── adapter.py                 # Hybrid vector/keyword search + citation formatting
│   │   ├── workweek/                      # WorkWeek HCM Integrations
│   │   │   ├── __init__.py
│   │   │   ├── client.py                  # WorkWeek REST API client with OBO headers
│   │   │   ├── models.py                  # Pydantic models for Profile, Balances, Leave
│   │   │   └── adapter.py                 # Tool implementations with balance & date constraints
│   │   └── service_immediately/          # ServiceImmediately ITSM Integrations
│   │       ├── __init__.py
│   │       ├── client.py                  # ServiceImmediately REST API client with mTLS/X-Origin
│   │       ├── models.py                  # Pydantic models for Incidents, Comments, Timeline
│   │       └── adapter.py                 # Tool implementations with deduplication & state logic
│   ├── resiliency/                        # Enterprise reliability & fault tolerance
│   │   ├── __init__.py
│   │   ├── circuit_breaker.py             # 5xx circuit breaker with state machine & fast-fail
│   │   ├── rate_limiter.py                # Distributed token bucket rate limiter
│   │   └── saga.py                        # Cross-system Saga coordinator & DLQ handler
│   ├── audit/                             # Observability, compliance & audit logging
│   │   ├── __init__.py
│   │   ├── logger.py                      # Structured audit logger with HMAC pseudonymization
│   │   └── models.py                      # Audit event schema (BigQuery compatible)
│   └── api/                               # Ingress Gateway & REST/WebSocket API
│       ├── __init__.py
│       ├── app.py                         # FastAPI application entrypoint
│       ├── auth.py                        # RFC 8693 OBO token validation & session extractor
│       └── routes.py                      # Chat endpoint (/v1/chat/message), health checks (/healthz)
├── tests/                                 # Test suite & verification harness
│   ├── conftest.py                        # Test fixtures, mock servers & environments
│   ├── unit/                              # Isolated unit tests
│   │   ├── test_guardrails.py             # Jailbreak, Flash-Lite scope gating & DLP masking tests
│   │   ├── test_thinking_levels.py        # Verification of dynamic thinking levels ('low' vs 'medium')
│   │   ├── test_workweek_adapter.py       # Leave balance constraints, E.164 phone, profile locks
│   │   ├── test_service_immediately.py    # Deduplication, priority rules, ticket lifecycle
│   │   ├── test_policy_rag.py             # Citation deep links, grounding checks
│   │   ├── test_circuit_breaker.py        # 5xx trip, half-open probe, queue evacuation
│   │   └── test_saga_orchestrator.py      # Partial failure recovery, compensating rollback
│   ├── integration/                       # End-to-end use case validation
│   │   ├── test_uc_1_1_policy_qa.py       # UC-1.1 Grounded Policy Q&A
│   │   ├── test_uc_1_2_leave_submit.py    # UC-1.2 WorkWeek Leave Submission
│   │   ├── test_uc_1_3_ticket_ops.py      # UC-1.3 ServiceImmediately Ticket Management
│   │   ├── test_uc_2_1_equipment.py       # UC-2.1 Equipment Procurement Orchestration
│   │   ├── test_uc_2_2_medical_leave.py   # UC-2.2 Medical Leave & Email Delegation Orchestration
│   │   └── test_uc_2_3_relocation.py      # UC-2.3 Relocation & Building Access Orchestration
│   └── evaluation/                        # Continuous quality & adversarial evaluation
│       ├── evalset.json                   # 200 Golden benchmark evaluation dataset
│       └── test_benchmark_eval.py         # Ragas / DeepEval quality gate execution
├── pyproject.toml                         # Project metadata, dependencies and build configuration
└── README.md                              # Repository overview and execution guide
```

---

## 4. Detailed Implementation Phases

### Phase 1: Foundation, Configuration & Model Layer
1. **Dependency & Environment Setup:**
   - Configure `pyproject.toml` with `google-genai>=1.0.0`, `vertexai`, `fastapi`, `uvicorn`, `pydantic>=2.7`, `redis`, `httpx`, `pytest`, `pytest-asyncio`.
   - Setup configuration management (`src/config.py`) defining:
     - `AGENT_MODEL = "gemini-3.8-flash"` (Primary ReAct reasoning & tool execution)
     - `GATE_MODEL = "gemini-3.5-flash-lite"` (Pre-LLM scope gating & domain filter)
     - Thinking level profiles: `THINKING_LEVEL_ROUTINE = "low"`, `THINKING_LEVEL_COMPLEX = "medium"`
     - Context cache TTL and configuration.
2. **Pydantic Schemas & Domain Models:**
   - Define strict models for WorkWeek entities (`EmployeeProfile`, `ContactInfo`, `LeaveBalance`, `LeaveRequest`).
   - Define ServiceImmediately entities (`IncidentRecord`, `CreateIncidentRequest`, `AddCommentRequest`, `TicketStateEnum`).
   - Define Policy RAG models (`PolicyChunk`, `PolicySearchQuery`, `PolicySearchResult`).
   - Define Chat contracts (`ChatRequest`, `ChatResponse`, `CitationMetadata`).

### Phase 2: Dual-Layer Guardrails & Sensitive Data DLP
1. **Input Guardrail Interceptor (`src/guardrails/input_guard.py`):**
   - Adversarial prompt injection & jailbreak detection (regex heuristics + instruction override patterns).
   - Pre-LLM Scope Gating via **Gemini 3.5 Flash-Lite**: ultra-fast (<150ms) classification ensuring query pertains to Altostrat HR/IT; rejects out-of-scope requests with the standard boundary notice.
2. **Cloud DLP / Clinical & NRIC Redaction (`src/guardrails/dlp.py`):**
   - Implement synchronous masking matching SDD Section 4.4:
     - Free-text medical notes and diagnoses: regex + clinical dictionary -> `[REDACTED_MEDICAL_INFO]`.
     - Singapore National ID (NRIC/FIN): regex `[STFGM][0-9]{7}[A-Z]` -> `[REDACTED_NRIC]`.
     - MC Identifiers: regex `MC-[0-9]{6,10}` -> `[REDACTED_MC_ID]`.
     - International passports: regex -> `[REDACTED_PASSPORT]`.
3. **Output Guardrail Interceptor (`src/guardrails/output_guard.py`):**
   - Grounding attribution validator: verify that generated policy statements are grounded in retrieved chunks (score ≥ 0.90 threshold).
   - Citation validator: ensure citations strictly match approved handbook URLs (`https://intranet.altostrat.com/policies/singapore#...`).
   - Egress DLP scrub and enterprise professional tone check.

### Phase 3: Domain Toolkits & Deterministic Adapters
1. **Base Toolkit & Anti-IDOR Middleware (`src/toolkits/base.py`):**
   - Enforce programmatic injection of `caller_id` from the verified session context (`caller == session.user_id`).
   - Enforce strict parameter type checking, bounds checking, and structured exception handling.
2. **PolicyToolkit (`src/toolkits/policy/adapter.py`):**
   - Implement `policy_search_knowledge_base(query, category=None, max_chunks=3)`.
   - Supports indexed policy store (Altostrat Singapore Employee Policy Handbook) with vector/keyword hybrid search and metadata extraction.
3. **WorkWeekToolkit (`src/toolkits/workweek/adapter.py`):**
   - `workweek_get_employee_profile(employee_id)`: Read-only profile attributes; Anti-IDOR lock.
   - `workweek_update_contact_info(home_address, phone_number)`: Disallows modifying legal name, salary, role, or manager. Validates E.164 phone format.
   - `workweek_get_leave_balances(employee_id)`: Fetches accrued, used, and remaining balances.
   - `workweek_submit_leave_request(employee_id, leave_type, start_date, end_date, work_days)`: Validates `start_date >= today`, `start_date <= end_date`, and `work_days <= remaining_balance`.
4. **ServiceImmediatelyToolkit (`src/toolkits/service_immediately/adapter.py`):**
   - `service_immediately_get_ticket(ticket_id)`: Verifies ticket caller ownership, returns timeline.
   - `service_immediately_create_incident(caller_id, category, short_description, description, priority)`: Validates priority rules, executes 48-hour deduplication check.
   - `service_immediately_add_comment(ticket_id, comment, status=None)`: Enforces valid status lifecycle (`New` -> `In Progress` -> `Resolved` -> `Closed`).

### Phase 4: Autonomous ReAct Orchestration & Context Caching
1. **ReAct Engine (`src/agent/core.py`):**
   - Implement single ReAct agent graph with max 3 cognitive loop iterations powered by **Gemini 3.8 Flash**.
   - Dynamic Thinking Level selection:
     - Automatically routes single-intent / routine requests (PTO balance, policy lookup, ticket query) to `thinking_level: "low"`.
     - Routes multi-step compound workflows (UC-2.x) to `thinking_level: "medium"`.
   - Compound intent decomposition (e.g., update profile first before policy search).
2. **Vertex AI Context Caching (`src/agent/context_cache.py`):**
   - Manages creation and reuse of cached prompt contexts containing system instructions and 8 OpenAPI tool definitions.
3. **Ephemeral Session Memory (`src/agent/memory.py`):**
   - Redis session management with sliding 10-turn window.
   - Progressive 2-sentence summary condensation for turns > 10.
   - 30-minute sliding inactivity TTL and 2-hour hard session ceiling.
   - Zero raw PII caching policy.

### Phase 5: Enterprise Resiliency, Circuit Breakers & Saga Pattern
1. **5xx Circuit Breaker (`src/resiliency/circuit_breaker.py`):**
   - State machine: `CLOSED`, `OPEN`, `HALF-OPEN`.
   - Trips on 5 consecutive 5xx / timeout errors; 30s cooldown; fast-fail queue evacuation (<50ms).
2. **Distributed Rate Limiting (`src/resiliency/rate_limiter.py`):**
   - Token bucket limiters (100 req/min WorkWeek, 60 req/min ServiceImmediately) with 3-second priority queueing and backpressure notification.
3. **Saga Coordinator (`src/resiliency/saga.py`):**
   - Handles multi-step transactions (especially UC-2.2 Medical Leave).
   - If Step 2 (ServiceImmediately) fails after Step 1 (WorkWeek) succeeds, schedules 5 background retries with exponential backoff (2s to 60s).
   - Enqueues to Dead-Letter Queue (DLQ) if retries exhaust and notifies user with partial success transparency.

### Phase 6: API Layer, Auth & Session Broker
1. **Auth & Identity Broker (`src/api/auth.py`):**
   - Inbound RS256 JWT validation, extraction of `sub` (`EMP-10492`) and `role` (`fte_singapore`).
   - Mock/Test OIDC realm support conforming to RFC 8693 OBO specifications.
2. **FastAPI Application (`src/api/app.py` & `routes.py`):**
   - `POST /v1/chat/message`: Main conversational endpoint.
   - `GET /healthz`: Deep health probe testing database and backend connectivity.

### Phase 7: Verification, Golden Evaluation & Red-Teaming
1. **Unit & Component Testing:**
   - 100% test coverage across Guardrails, Toolkits, DLP, Dynamic Thinking Levels, Circuit Breakers, and Saga coordinator.
2. **End-to-End Use Case Integration Testing:**
   - UC-1.1: Grounded policy Q&A with bereavement leave citation verification.
   - UC-1.2: WorkWeek vacation leave submission with balance check.
   - UC-1.3: IT ticket status check and 48-hour duplicate detection.
   - UC-2.1: Remote monitor procurement orchestration.
   - UC-2.2: Medical leave submission + manager email delegation ticket.
   - UC-2.3: International relocation allowance + building pass ticket.
3. **Adversarial & Safety Evaluation:**
   - 30 adversarial probes (DAN jailbreaks, instruction overrides, system extraction).
   - False positive verification (<1.0%).
   - Grounding attribution threshold test (>= 0.90).

---

## 5. Deliverables & Acceptance Criteria

| Workstream | Deliverable | Acceptance Criteria |
| :--- | :--- | :--- |
| **Model & Orchestration** | `src/agent/` | **Gemini 3.8 Flash** active; dynamic thinking levels (`low`/`medium`) verified; Vertex AI context cache active; sub-10s P95 turn latency. |
| **Pre-LLM & Safety** | `src/guardrails/` | **Gemini 3.5 Flash-Lite** pre-LLM scope gating (<150ms); 100% prompt injection interception; synchronous NRIC and medical DLP redaction. |
| **Integration Adapters** | `src/toolkits/` | All 8 tools operational; Anti-IDOR enforced; Pydantic schema validation; E.164 phone regex verified; duplicate ticket detection active. |
| **Resilience & Saga** | `src/resiliency/` | 5xx circuit breaker trips on 5 failures; Saga executes compensating actions and transparent user messaging on partial failures. |
| **API & Gateway** | `src/api/` | Secure FastAPI server with OIDC/OBO token extraction and deep `/healthz` probe. |
| **Test & Eval Harness** | `tests/` | Comprehensive test suite covering all use cases, edge cases, thinking levels, and adversarial probes with zero test failures. |

---

## 6. Review & Approval Gate

In accordance with the **System-Wide & General Execution Rules (Mandatory Human-in-the-Loop Approvals)**, this updated implementation plan is presented to the user for interactive review. Upon receiving user confirmation, we will proceed to execution.
