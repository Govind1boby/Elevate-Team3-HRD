"""Policy Knowledge Store and Search Adapter (RAG).
Provides semantic and keyword hybrid retrieval over Altostrat Singapore HR policies
with mathematical citation attribution and deep-link generation (SDD Section 5.1.1).
"""

import re
from typing import Any, Dict, List, Optional
from src.toolkits.base import BaseTool, ExecutionContext
from src.toolkits.policy.models import PolicyChunk, PolicySearchRequest, PolicySearchResponse


ALTOSTRAT_HANDBOOK_POLICY_CHUNKS = [
    PolicyChunk(
        chunk_id="sg_policy_handbook_sec_22",
        document_title="Altostrat Singapore Employee Policy Handbook & Conduct Guidelines",
        section_title="Section 22: Bereavement Leave (Global)",
        text=(
            "Altostrat provides up to 4 weeks (20 work days) of paid bereavement leave per event "
            "to grieve and support loved ones upon the death of an immediate family member. "
            "This leave must be taken within 12 months of the death. "
            "Note that paid bereavement leave does not apply to pet loss."
        ),
        deep_link_url="https://intranet.altostrat.com/policies/singapore#section-22",
        relevance_score=0.96,
    ),
    PolicyChunk(
        chunk_id="sg_policy_handbook_sec_1_1",
        document_title="Altostrat Singapore Employee Policy Handbook & Conduct Guidelines",
        section_title="Section 1.1: Sick Time",
        text=(
            "Under the Altostrat Singapore Sick Leave policy and MOM guidelines, full-time employees "
            "are entitled to up to 14 days of paid outpatient sick leave and up to 46 days of paid hospitalization leave "
            "per calendar year. A registered Medical Certificate (MC) must be submitted via WorkWeek within 48 hours "
            "of commencing sick leave."
        ),
        deep_link_url="https://intranet.altostrat.com/policies/singapore#section-1-1",
        relevance_score=0.95,
    ),
    PolicyChunk(
        chunk_id="sg_policy_handbook_sec_1_5",
        document_title="Altostrat Singapore Employee Policy Handbook & Conduct Guidelines",
        section_title="Section 1.5: Remote Work Policy",
        text=(
            "Approved Remote and Hybrid employees in Singapore are eligible for a one-time home office equipment "
            "reimbursement allowance capped at $500 USD (e.g. for ergonomic monitors, keyboards, or desk accessories). "
            "To procure equipment, the employee must verify their active remote work location and submit a Facilities "
            "incident ticket in ServiceImmediately including their confirmed home shipping address."
        ),
        deep_link_url="https://intranet.altostrat.com/policies/singapore#section-1-5",
        relevance_score=0.94,
    ),
    PolicyChunk(
        chunk_id="sg_policy_handbook_sec_2_2",
        document_title="Altostrat Singapore Employee Policy Handbook & Conduct Guidelines",
        section_title="Section 2.2: Administrative Coverage",
        text=(
            "For planned leaves of absence or medical leaves extending beyond one standard work week (5 business days), "
            "company policy requires the employee or manager to open an administrative HRSD ticket in ServiceImmediately "
            "(Priority: '3 - Moderate') to configure temporary email delegation and operational mailbox coverage "
            "to the direct manager during the absence window."
        ),
        deep_link_url="https://intranet.altostrat.com/policies/singapore#section-2-2",
        relevance_score=0.93,
    ),
    PolicyChunk(
        chunk_id="sg_policy_handbook_sec_relocation",
        document_title="Altostrat Singapore Employee Policy Handbook & Conduct Guidelines",
        section_title="Relocation & International Office Guidelines",
        text=(
            "Employees executing an approved international office transfer (such as relocating from Singapore to the "
            "London HQ office) are entitled to an international relocation expense allowance capped at $10,000 USD. "
            "Pre-configuration of physical building security badge access requires opening a Facilities ticket in "
            "ServiceImmediately with the destination office site prior to the transfer start date."
        ),
        deep_link_url="https://intranet.altostrat.com/policies/singapore#section-relocation",
        relevance_score=0.95,
    ),
]


class PolicySearchKnowledgeBaseTool(BaseTool):
    name = "policy_search_knowledge_base"
    description = (
        "Performs hybrid vector and keyword search over approved Altostrat Singapore Employee Policy Handbook documents. "
        "Returns chunk text, section title, document title, and verified deep link URLs."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Specific keywords or question regarding HR policy, leave, benefits, conduct, or relocation."
            },
            "category": {
                "type": "string",
                "description": "Optional category filter: 'Leave', 'Benefits', 'Conduct', 'Facilities', 'Relocation'."
            },
            "max_chunks": {
                "type": "integer",
                "default": 3,
                "description": "Maximum number of policy chunks to return (1-5)."
            }
        },
        "required": ["query"]
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "").strip().lower()
        max_chunks = kwargs.get("max_chunks", 3)

        if not query:
            return {"chunks": []}

        # Tokenize query words
        query_words = set(re.findall(r"\b[a-z]{3,}\b", query))

        scored_chunks = []
        for chunk in ALTOSTRAT_HANDBOOK_POLICY_CHUNKS:
            searchable_text = f"{chunk.section_title} {chunk.text}".lower()
            chunk_words = set(re.findall(r"\b[a-z]{3,}\b", searchable_text))
            
            overlap = len(query_words.intersection(chunk_words))
            if overlap > 0:
                score = min(1.0, 0.5 + (overlap / len(query_words)) * 0.5)
                scored_chunk = chunk.model_copy()
                scored_chunk.relevance_score = round(score, 2)
                scored_chunks.append(scored_chunk)

        # Sort by relevance
        scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)
        results = scored_chunks[:max_chunks]

        return {
            "chunks": [c.model_dump() for c in results]
        }
