"""Pydantic data models for Policy Knowledge Search (RAG).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class PolicyChunk(BaseModel):
    chunk_id: str
    document_title: str
    section_title: str
    text: str
    deep_link_url: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)


class PolicySearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    category: Optional[str] = None
    max_chunks: int = Field(default=3, ge=1, le=10)


class PolicySearchResponse(BaseModel):
    chunks: List[PolicyChunk]
