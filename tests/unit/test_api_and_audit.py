"""Unit tests for Phase 6: API Layer, OBO Auth & Immutable Audit Logging.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from src.api.app import app
from src.api.auth import OBOIdentityBroker
from src.audit.logger import AuditLogger, default_audit_logger


@pytest.mark.asyncio
async def test_healthz_deep_probe():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UP"
        assert data["region"] == "asia-southeast1"
        assert data["checks"]["model_core"] == "gemini-3.8-flash"
        assert data["checks"]["guardrail_scope_gate"] == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_chat_message_endpoint_with_obo_jwt():
    transport = ASGITransport(app=app)
    token = OBOIdentityBroker.create_test_token(employee_id="EMP-10492")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "message": "What is the bereavement leave policy?",
            "session_id": "api-test-session-1"
        }
        resp = await client.post(
            "/v1/chat/message",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is False
        assert "bereavement" in data["reply"].lower()
        assert len(data["citations"]) > 0
        assert data["citations"][0]["url"].startswith("https://intranet.altostrat.com/policies/")

        # Verify audit log was recorded
        logs = default_audit_logger.get_logs()
        assert len(logs) > 0
        last_log = logs[-1]
        assert last_log["tools_executed"] == ["policy_search_knowledge_base"]
        assert len(last_log["prompt_hash"]) == 64  # SHA-256


def test_audit_hmac_pseudonymization_and_rtbf():
    logger1 = AuditLogger(secret_salt="secret-salt-2026")
    pseudonym1 = logger1.pseudonymize("EMP-10492")
    assert len(pseudonym1) == 64  # SHA-256 HMAC

    # Same salt yields consistent pseudonym
    assert logger1.pseudonymize("EMP-10492") == pseudonym1

    # Cryptographic shredding (RTBF): rotating or destroying the salt renders past records mathematically unlinkable
    logger2 = AuditLogger(secret_salt="rotated-or-deleted-salt")
    pseudonym2 = logger2.pseudonymize("EMP-10492")
    assert pseudonym1 != pseudonym2
