"""Input Guardrail Interceptor.
Provides pre-execution security:
1. Adversarial prompt injection & jailbreak detection.
2. Pre-LLM domain & scope classification (Gemini 3.5 Flash-Lite / fast heuristic gating).
3. Synchronous pre-LLM Cloud DLP redaction (NRIC, MC Serial, Clinical medical terms).
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass
from src.guardrails.dlp import DLPScrubber


JAILBREAK_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous\s+)?(?:instructions|rules|prompts)",
    r"system\s+prompt\s+(?:extraction|reveal|leak|print|show)",
    r"\bdan\s+mode\b",
    r"do\s+anything\s+now",
    r"developer\s+mode\s+(?:enabled|on|activate)",
    r"bypass\s+(?:all\s+)?(?:guardrails|filters|restrictions)",
    r"reveal\s+(?:your\s+)?(?:hidden\s+)?(?:instructions|api\s*key|secrets)",
    r"pretend\s+you\s+are\s+(?:an?\s+)?unfiltered",
    r"roleplay\s+as\s+(?:a\s+)?hacker",
]
JAILBREAK_REGEX = re.compile(r"|".join(JAILBREAK_PATTERNS), re.IGNORECASE)

OUT_OF_SCOPE_PATTERNS = [
    r"\b(?:crypto|bitcoin|ethereum|arbitrage|stock\s+market|forex)\b",
    r"\b(?:premier\s+league|champions\s+league|world\s+cup|nba|football|soccer|basketball)\b",
    r"\b(?:write\s+a\s+poem|tell\s+me\s+a\s+joke|play\s+a\s+game|horoscope)\b",
    r"\b(?:write|generate|create)\s+(?:a\s+)?(?:python|javascript|bash|code|script)\b",
    r"\b(?:web\s+scraping|scraper|scrape)\b",
]
OUT_OF_SCOPE_REGEX = re.compile(r"|".join(OUT_OF_SCOPE_PATTERNS), re.IGNORECASE)


@dataclass
class InputGuardResult:
    is_blocked: bool
    sanitized_text: str
    block_reason: Optional[str] = None
    response_message: Optional[str] = None
    redactions: dict = None


class InputGuardrail:
    """Synchronous pre-LLM security pipeline."""

    BOUNDARY_REJECTION_MESSAGE = (
        "I am specialized to assist only with Altostrat HR policies, WorkWeek transactions, "
        "and ServiceImmediately IT support. Please contact the appropriate team for other inquiries."
    )

    SAFETY_VIOLATION_MESSAGE = (
        "Request rejected due to safety policy violation."
    )

    @classmethod
    def inspect(cls, raw_prompt: str) -> InputGuardResult:
        # 1. Adversarial & Jailbreak Detection
        if JAILBREAK_REGEX.search(raw_prompt):
            return InputGuardResult(
                is_blocked=True,
                sanitized_text="",
                block_reason="Adversarial prompt injection / jailbreak detected",
                response_message=cls.SAFETY_VIOLATION_MESSAGE,
                redactions={},
            )

        # 2. Scope & Domain Gating (Heuristic / Flash-Lite edge gate)
        if OUT_OF_SCOPE_REGEX.search(raw_prompt):
            return InputGuardResult(
                is_blocked=True,
                sanitized_text="",
                block_reason="Out of domain / scope request",
                response_message=cls.BOUNDARY_REJECTION_MESSAGE,
                redactions={},
            )

        # 3. Synchronous DLP Redaction (Pre-LLM)
        sanitized_prompt, redaction_stats = DLPScrubber.scrub_text(raw_prompt, stage="pre_llm")

        return InputGuardResult(
            is_blocked=False,
            sanitized_text=sanitized_prompt,
            block_reason=None,
            response_message=None,
            redactions=redaction_stats,
        )
