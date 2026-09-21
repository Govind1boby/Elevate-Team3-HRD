"""API request/response contracts for chat and session ingress.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CitationMetadata(BaseModel):
    document_title: str
    section_title: str
    url: str
    attribution_score: float = 1.0


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None
    employee_id: Optional[str] = None  # In production, extracted from verified JWT


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    turn_id: int
    tool_calls_executed: List[str] = Field(default_factory=list)
    citations: List[CitationMetadata] = Field(default_factory=list)
    latency_ms: float = 0.0
    blocked: bool = False
    block_reason: Optional[str] = None
