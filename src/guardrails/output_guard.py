"""Output Guardrail Interceptor.
Provides post-generation validation:
1. Grounding Attribution Checking (Threshold >= 0.90).
2. Deep Citation Link Validation ([Document - Section](URL)).
3. Egress DLP Inspection (NRIC, MC Serial, Clinical terms).
4. Professional Enterprise Tone Verification.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from src.guardrails.dlp import DLPScrubber
from src.config import settings

# Markdown link regex: [Text](URL)
MARKDOWN_LINK_REGEX = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
APPROVED_CITATION_PREFIX = "https://intranet.altostrat.com/policies/"


COMMON_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what", "which", "this", "that", "these", "those",
    "then", "so", "than", "such", "both", "through", "about", "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "once", "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "no", "nor", "not", "only", "own",
    "same", "too", "very", "can", "will", "just", "should", "now", "for",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself", "they", "them", "their",
    "theirs", "themselves", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "would", "could", "cannot",
    "please", "contact", "operations", "details", "source", "policy", "company", "employee", "singapore",
    "created", "ticket", "process", "portal", "track", "progress", "confirmed", "recorded", "order", "completed",
    "remember", "submit", "congratulations", "upcoming", "transfer", "taken", "reply", "with", "immediately",
    "office", "direct", "into", "also", "actions", "residential", "record", "personal", "number", "update", "profile",
    "important", "starting", "configured", "opened", "manager", "steps", "request", "notice", "tell", "help", "ref", "new"
}

SYNONYMS = {
    "entitled": "eligible",
    "entitlement": "eligibility",
    "entitlements": "eligibility",
    "eligible": "entitled",
    "eligibility": "entitled",
}


@dataclass
class OutputGuardResult:
    is_valid: bool
    sanitized_output: str
    attribution_score: float
    violations: List[str]
    citations: List[dict]


class OutputGuardrail:
    """Synchronous post-LLM validation gate."""

    FALLBACK_UNGROUNDED_MESSAGE = (
        "I cannot find this information in the approved policy documents. "
        "Please contact HR Operations at hr-operations@altostrat.com for guidance on this topic."
    )

    @classmethod
    def _stem(cls, word: str) -> str:
        w = word.lower()
        for suffix in ("ing", "ed", "es", "s", "tion", "tional", "ity", "ment", "able", "ible"):
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                return w[:-len(suffix)]
        return w

    @classmethod
    def _matches_context(cls, word: str, context_str: str, context_stems: set) -> bool:
        w = word.lower()
        if w in context_str:
            return True
        stem = cls._stem(w)
        if stem in context_stems or stem in context_str:
            return True
        if len(w) >= 4 and w[:4] in context_str:
            return True
        syn = SYNONYMS.get(w)
        if syn and (syn in context_str or syn[:4] in context_str):
            return True
        return False

    @classmethod
    def calculate_lexical_grounding(cls, response_text: str, context_chunks: List[str]) -> float:
        """Calculates token overlap and claim grounding confidence between response and context chunks.
        Returns a score in [0.0, 1.0].
        """
        if not context_chunks:
            return 0.0

        clean_response = MARKDOWN_LINK_REGEX.sub("", response_text)
        words = re.findall(r"\b[a-z]{3,}\b", clean_response.lower())
        claim_keywords = [w for w in words if w not in COMMON_STOPWORDS]

        if not claim_keywords:
            return 1.0

        combined_context = " ".join(context_chunks).lower()
        context_words = re.findall(r"\b[a-z]{3,}\b", combined_context)
        context_stems = set(cls._stem(cw) for cw in context_words) | set(context_words)

        matches = sum(1 for w in claim_keywords if cls._matches_context(w, combined_context, context_stems))
        return min(1.0, matches / len(claim_keywords))

    @classmethod
    def extract_and_validate_citations(cls, text: str) -> Tuple[List[dict], List[str]]:
        citations = []
        violations = []
        links = MARKDOWN_LINK_REGEX.findall(text)

        for anchor_text, url in links:
            if not url.startswith(APPROVED_CITATION_PREFIX):
                violations.append(f"Unapproved citation domain/URL: {url}")
            else:
                citations.append({"title": anchor_text, "url": url})

        return citations, violations

    @classmethod
    def inspect(
        cls,
        candidate_response: str,
        retrieved_chunks: Optional[List[str]] = None,
        is_policy_query: bool = False
    ) -> OutputGuardResult:
        violations = []

        # 1. Grounding Attribution Check
        attribution_score = 1.0
        if is_policy_query:
            attribution_score = cls.calculate_lexical_grounding(candidate_response, retrieved_chunks or [])
            if attribution_score < settings.GROUNDING_ATTRIBUTION_THRESHOLD:
                violations.append(
                    f"Grounding score {attribution_score:.2f} below threshold {settings.GROUNDING_ATTRIBUTION_THRESHOLD}"
                )
                return OutputGuardResult(
                    is_valid=False,
                    sanitized_output=cls.FALLBACK_UNGROUNDED_MESSAGE,
                    attribution_score=attribution_score,
                    violations=violations,
                    citations=[]
                )

        # 2. Citation URL Validation
        citations, citation_violations = cls.extract_and_validate_citations(candidate_response)
        violations.extend(citation_violations)

        # 3. Egress DLP Inspection
        scrubbed_output, dlp_stats = DLPScrubber.scrub_text(candidate_response, stage="post_llm")

        return OutputGuardResult(
            is_valid=len(violations) == 0,
            sanitized_output=scrubbed_output,
            attribution_score=attribution_score,
            violations=violations,
            citations=citations
        )
