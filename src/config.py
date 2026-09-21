"""Application configuration and runtime settings for the Enterprise HR Virtual Assistant.
"""

from dataclasses import dataclass, field
import os
from typing import Optional


@dataclass
class Settings:
    # Model Configurations (SDD-Argon v1.0 updated)
    AGENT_MODEL: str = os.getenv("AGENT_MODEL", "gemini-3.8-flash")
    GATE_MODEL: str = os.getenv("GATE_MODEL", "gemini-3.5-flash-lite")
    THINKING_LEVEL_ROUTINE: str = "low"
    THINKING_LEVEL_COMPLEX: str = "medium"
    MAX_REACT_ITERATIONS: int = 3
    GROUNDING_ATTRIBUTION_THRESHOLD: float = 0.90

    # Project and Region
    GCP_PROJECT: str = os.getenv("GCP_PROJECT", "altostrat-hr-agent-prod")
    GCP_REGION: str = os.getenv("GCP_REGION", "asia-southeast1")

    # API Base URLs
    WORKWEEK_BASE_URL: str = os.getenv("WORKWEEK_BASE_URL", "http://127.0.0.1:8001")
    SERVICE_IMMEDIATELY_BASE_URL: str = os.getenv("SERVICE_IMMEDIATELY_BASE_URL", "http://127.0.0.1:8002")
    OIDC_ISSUER_URI: str = os.getenv("OIDC_ISSUER_URI", "https://idp-sandbox.altostrat.com")

    # Resiliency and Circuit Breakers
    CIRCUIT_BREAKER_FAIL_THRESHOLD: int = 5
    CIRCUIT_BREAKER_COOLDOWN_SECONDS: float = 30.0
    CIRCUIT_BREAKER_FAST_FAIL_QUEUE_TIMEOUT: float = 3.0

    # Distributed Rate Limiting (requests per minute)
    WORKWEEK_RATE_LIMIT_RPM: int = 100
    SERVICE_IMMEDIATELY_RATE_LIMIT_RPM: int = 60

    # Saga Pattern & Dead-Letter Queue
    SAGA_MAX_ATTEMPTS: int = 5
    SAGA_MIN_BACKOFF: float = 2.0
    SAGA_MAX_BACKOFF: float = 60.0
    SAGA_DLQ_TOPIC: str = os.getenv("SAGA_DLQ_TOPIC", "projects/altostrat-hr-agent-prod/topics/saga-compensation-dlq")

    # Ephemeral Session & Context Window Management (Redis)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    SESSION_INACTIVITY_TTL_SECONDS: int = 1800  # 30 minutes
    SESSION_MAX_LIFETIME_SECONDS: int = 7200    # 2 hours
    SESSION_MAX_TURNS_WINDOW: int = 10          # Sliding window turn limit

    # Policy Store Knowledge Base
    POLICY_DOCS_DIR: str = os.getenv("POLICY_DOCS_DIR", os.path.abspath("docs"))
    DEFAULT_TENANT_ID: str = "altostrat-sg"


settings = Settings()
