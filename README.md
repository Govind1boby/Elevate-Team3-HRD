# Altostrat Enterprise HR & IT Agentic Virtual Assistant (Argon MVP 1)

Production-grade autonomous enterprise assistant built on Google Cloud and Gemini 3.8 Flash, integrating WorkWeek HCM, ServiceImmediately ITSM, and grounded Altostrat Singapore HR policy RAG.

---

## 1. Architectural Overview

The solution adheres strictly to the Solution Design Document (`docs/sdd-argon.md`), implementing a defense-in-depth, 7-gate execution pipeline:

```
[ Inbound User Request ]
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│ Gate 1 & 2: Pre-LLM Security & DLP (Gemini 3.5 Flash-Lite)│
│ • Adversarial Prompt Injection & DAN Shield             │
│ • Domain Scope Filter (<150ms edge gating)               │
│ • Singapore NRIC/FIN, MC Serial, Clinical Redaction      │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Gate 3: OBO Identity Broker (RFC 8693)                   │
│ • Downstream Token Exchange (Composite Delegation Token) │
│ • Anti-IDOR Caller Locks (caller_id == session.user_id)  │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Gate 4: AI Core ReAct Agent (Gemini 3.8 Flash)           │
│ • Dynamic Thinking Budget (Low: routine, Med: multi-turn)│
│ • Vertex AI Context Caching (>12k tokens, 1h TTL)        │
│ • Sliding Window Session Memory (10 turns, 30m TTL)      │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Gate 5 & 6: Domain Adapters & Resiliency Engine           │
│ • Policy RAG: Singapore Employee Handbook Deep Search    │
│ • WorkWeek HCM: Profile, Balances, Leave Submission      │
│ • ServiceImmediately ITSM: Incidents, 48h Deduplication  │
│ • Circuit Breakers (5xx trip, <50ms queue evacuation)    │
│ • Saga Pattern Coordinator (Compensating Rollbacks, DLQ) │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Gate 7: Post-LLM Output Guardrail                        │
│ • Mathematical Grounding Attribution Check (Score ≥ 0.90)│
│ • Deep Citation Link Verification (intranet domain)      │
│ • Egress DLP Masking & Safe Hallucination Suppression    │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
[ Verified & Grounded Enterprise Response ]
```

---

## 2. Running Locally (Step-by-Step Guide)

Follow these steps to set up and run the application on your local machine or workstation.

### Step 1: Clone and Navigate to the Repository

```bash
git clone https://github.com/Govind1boby/Elevate-Team3-HRD.git
cd Elevate-Team3-HRD
```

### Step 2: Set Up Python Virtual Environment

Make sure you have **Python 3.13+** (or Python 3.11+) installed.

#### Option A: Using `uv` (Recommended — Fast)
```bash
# Create isolated environment
uv venv .venv

# Activate environment
source .venv/bin/activate
```

#### Option B: Using Standard `python3`
```bash
# Create virtual environment
python3 -m venv .venv

# Activate environment
source .venv/bin/activate
```

### Step 3: Install Dependencies

Install the project in editable development mode:

```bash
# Using pip
pip install -e .

# Or using uv
uv pip install -e .
```

### Step 4: Environment Configuration (Optional)

The application includes production-safe defaults for local execution. To override default settings, create a `.env` file or export environment variables:

```bash
export ENVIRONMENT=development
export API_PORT=8000
export API_HOST=0.0.0.0
export GROUNDING_ATTRIBUTION_THRESHOLD=0.90
```

### Step 5: Start the Server

You can start the server using either `uvicorn` or `python`:

#### Method 1: Using Uvicorn (with hot reloading)
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

#### Method 2: Running the Python Module Directly
```bash
python -m src.api.app
```

Once started, the server output will confirm:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 3. Accessing the Application

Once the server is running, access the application through your web browser:

| Interface | URL | Description |
| :--- | :--- | :--- |
| **Interactive Web Chat Portal** | [http://localhost:8000](http://localhost:8000) | Full web UI with pre-configured SDD scenario chips, real-time message rendering, citation badges, and thinking telemetry. |
| **OpenAPI / Swagger UI** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive API exploration and direct schema inspection. |
| **Deep Health Probe** | [http://localhost:8000/healthz](http://localhost:8000/healthz) | Live dependency health check (Orchestrator, Model Core, Scope Gate, Knowledge Base, Session Memory). |

> [!NOTE]
> **Cloudtop / Remote Workstation Note:** If running on a Google Cloudtop, you can connect from your local machine using your cloudtop hostname proxy URL:  
> `http://kan-glinux-0226.c.googlers.com:8000` (or `http://kan-glinux-0226.c.googlers.com:8000/docs`).

---

## 4. Trying Out Core Scenarios

### Option A: Using the Web UI
Open [http://localhost:8000](http://localhost:8000) in your browser and click on any of the pre-set scenario buttons in the left sidebar:
1. **📄 Bereavement Leave Policy (UC-1.1):** Grounded RAG retrieval with citation deep link (`#section-22`).
2. **🌴 Vacation Leave Request (UC-1.2):** WorkWeek balance check and vacation submission (`LV-...`).
3. **🎫 IT Incident Status (UC-1.3):** ServiceImmediately status check on ticket `INC123456`.
4. **⚠️ Duplicate Incident Handling (UC-1.3):** 48-hour deduplication window interception for recurring VPN issues.
5. **🖥️ Equipment Procurement (UC-2.1):** Remote Work allowance ($500 USD cap) + WorkWeek address confirmation + Facilities ticket creation.
6. **🏥 Medical Leave & Delegation (UC-2.2):** Sick leave submission + Manager email delegation ticket + 48h MC reminder.
7. **✈️ International Relocation (UC-2.3):** $10k transfer allowance + London HQ building security pass + WorkWeek address update prompt.
8. **🛡️ Adversarial DAN / Jailbreak Shield:** Pre-LLM edge security classifier intercepts and blocks malicious injection attempts.

---

### Option B: Using cURL from the Terminal

#### 1. Policy Q&A with Citation Attribution (UC-1.1)
```bash
curl -X POST http://localhost:8000/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the company bereavement leave policy?",
    "employee_id": "EMP-10492"
  }'
```

#### 2. Vacation Leave Submission (UC-1.2)
```bash
curl -X POST http://localhost:8000/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Please submit a vacation request for next week.",
    "employee_id": "EMP-10492"
  }'
```

#### 3. Equipment Procurement Orchestration (UC-2.1)
```bash
curl -X POST http://localhost:8000/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I read the remote work policy and saw I am eligible for a home office monitor. Can you verify my status and order one?",
    "employee_id": "EMP-10492"
  }'
```

#### 4. Deep Health Check
```bash
curl http://localhost:8000/healthz
```

---

## 5. Running the Test Suite

The repository includes a comprehensive, zero-mocking test suite covering 100% of the use cases and architectural components:

```bash
# Run all unit and integration tests (41 tests)
pytest tests/ -v

# Run only the end-to-end integration use cases (UC-1.1 to UC-2.3)
pytest tests/integration/test_use_cases.py -v

# Run specific unit test modules
pytest tests/unit/test_guardrails.py -v       # Pre-LLM & Post-LLM security gates, DLP, NRIC masking
pytest tests/unit/test_toolkits.py -v         # WorkWeek, ServiceImmediately, Anti-IDOR middleware
pytest tests/unit/test_agent.py -v            # ReAct engine, dynamic thinking budgets, session memory
pytest tests/unit/test_resiliency.py -v       # Circuit breakers, rate limiters, 2-phase Saga rollbacks
pytest tests/unit/test_api_and_audit.py -v    # OBO Identity broker, BigQuery HMAC audit logging
```

Expected test execution output:
```
============================== 41 passed in 0.98s ==============================
```

---

## 6. Directory Structure

```
├── docs/
│   └── sdd-argon.md              # Official Solution Design Document (SDD v1.0)
├── src/
│   ├── agent/                    # Autonomous ReAct core, memory & context caching
│   │   ├── context_cache.py      # Vertex AI Context Caching manager (>12k tokens, 1h TTL)
│   │   ├── core.py               # Gemini 3.8 Flash ReAct engine (low/med dynamic thinking)
│   │   ├── memory.py             # Sliding-window session memory manager (10 turns, 30m TTL)
│   │   └── prompts.py            # Boundary-enforcing system instructions
│   ├── api/                      # Enterprise API layer
│   │   ├── app.py                # FastAPI application & CORS configuration
│   │   ├── auth.py               # RFC 8693 OBO Identity Broker (delegation tokens)
│   │   ├── models.py             # Pydantic v2 API request/response contracts
│   │   └── routes.py             # /v1/chat/message, /healthz, and interactive Web UI (/)
│   ├── audit/                    # Compliance & Telemetry
│   │   └── logger.py             # HMAC-SHA256 pseudonymized BigQuery audit logging & RTBF
│   ├── guardrails/               # Security & compliance interceptors
│   │   ├── dlp.py                # Cloud DLP sensitive data scrubber (NRIC, MC, medical info)
│   │   ├── input_guard.py        # Pre-LLM jailbreak & scope classifier (<150ms edge gate)
│   │   └── output_guard.py       # Grounding attribution (score ≥ 0.90) & deep citation validator
│   ├── resiliency/               # Fault tolerance & distributed coordination
│   │   ├── circuit_breaker.py    # 5xx circuit breaker with <50ms queue evacuation
│   │   ├── rate_limiter.py       # Token bucket rate limiters & async semaphores
│   │   └── saga.py               # 2-Phase Saga transaction coordinator & Pub/Sub DLQ
│   ├── toolkits/                 # Domain toolkits & adapters
│   │   ├── base.py               # BaseTool with Anti-IDOR middleware locks
│   │   ├── policy/               # Grounded Singapore HR Handbook RAG adapter
│   │   ├── service_immediately/  # ServiceImmediately ITSM adapter (incidents, 48h dedup)
│   │   └── workweek/             # WorkWeek HCM adapter (profile, balances, leave submission)
│   ├── config.py                 # Central environment & settings configuration
│   └── __init__.py
├── tests/
│   ├── integration/              # End-to-end multi-system use cases (UC-1.1 - UC-2.3)
│   │   └── test_use_cases.py
│   └── unit/                     # Unit test suites across all architectural layers
│       ├── test_agent.py
│       ├── test_api_and_audit.py
│       ├── test_guardrails.py
│       ├── test_models.py
│       ├── test_resiliency.py
│       └── test_toolkits.py
├── pyproject.toml                # Project metadata, dependencies & pytest configuration
└── README.md                     # Local runbook and documentation
```

---

## 7. Troubleshooting & FAQ

### 1. `Address already in use` error on port 8000
If port 8000 is occupied by another process, run on a different port:
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8080 --reload
```
Or terminate the process using port 8000:
```bash
lsof -ti :8000 | xargs kill -9
```

### 2. ModuleNotFoundError when running scripts
Ensure your virtual environment is active and the package is installed in editable mode:
```bash
source .venv/bin/activate
pip install -e .
```

### 3. How do identity and authorization work locally?
The application features an RFC 8693 On-Behalf-Of (OBO) identity broker (`src/api/auth.py`). In local test mode:
* If no `Authorization: Bearer <token>` header is passed, the system defaults safely to test persona **`EMP-10492`** (`Alex Chen, Software Engineer (Singapore FTE)`).
* The Anti-IDOR middleware ensures that users can only view or mutate records belonging to their authenticated caller identity.
