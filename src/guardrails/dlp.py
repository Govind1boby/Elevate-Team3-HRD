"""Cloud DLP & Sensitive Data Redaction Engine.
Enforces synchronous redaction of Singapore NRIC/FIN, medical diagnosis/clinical terms,
MC serial numbers, and passport numbers at LIKELIHOOD_POSSIBLE threshold (SDD Section 4.4).
"""

import re
from typing import Tuple

# Singapore NRIC / FIN Regex: S, T, F, G, M followed by 7 digits and an alpha check letter
NRIC_REGEX = re.compile(r"\b[STFGMstfgm]\d{7}[A-Za-z]\b")

# Medical Certificate (MC) serial number regex: MC-123456
MC_SERIAL_REGEX = re.compile(r"\bMC-\d{6,10}\b", re.IGNORECASE)

# International Passport regex (alphanumeric 8-9 chars preceded by keyword or formatted)
PASSPORT_REGEX = re.compile(r"\b(?:passport\s*(?:no|number|#)?\s*[:=]?\s*)([A-Z0-9]{8,9})\b", re.IGNORECASE)

# Clinical diagnoses and sensitive medical terms (ICD-10, surgical, clinical terms)
# Matches free-text health details per SDD Section 4.4
CLINICAL_TERMS = [
    r"\bspinal\s+fusion\b",
    r"\bsurgery\b",
    r"\bhospital(?:ized|ization)?\b",
    r"\bchemotherapy\b",
    r"\bradiation\s+therapy\b",
    r"\bcardi(?:ac|ology)\b",
    r"\bdepressi(?:on|ve)\b",
    r"\banxiety\s+disorder\b",
    r"\bbiopsy\b",
    r"\btumor\b",
    r"\bcancer\b",
    r"\bicu\b",
    r"\bintensive\s+care\b",
    r"\bdiagnostic\s+report\b",
    r"\bprescription\s+drug\b",
    r"\bmedical\s+condition\b",
    r"\bclinical\s+diagnosis\b",
    r"\borthopedic\b",
    r"\bchronic\s+illness\b",
    r"\bpathology\b",
]
CLINICAL_REGEX = re.compile(r"|".join(CLINICAL_TERMS), re.IGNORECASE)


class DLPScrubber:
    """Synchronous DLP Inspection and Masking Pipeline."""

    @classmethod
    def redact_nric(cls, text: str) -> Tuple[str, int]:
        matches = len(NRIC_REGEX.findall(text))
        redacted = NRIC_REGEX.sub("[REDACTED_NRIC]", text)
        return redacted, matches

    @classmethod
    def redact_mc_serial(cls, text: str) -> Tuple[str, int]:
        matches = len(MC_SERIAL_REGEX.findall(text))
        redacted = MC_SERIAL_REGEX.sub("[REDACTED_MC_ID]", text)
        return redacted, matches

    @classmethod
    def redact_passport(cls, text: str) -> Tuple[str, int]:
        matches = len(PASSPORT_REGEX.findall(text))
        redacted = PASSPORT_REGEX.sub("passport: [REDACTED_PASSPORT]", text)
        return redacted, matches

    @classmethod
    def redact_medical_info(cls, text: str) -> Tuple[str, int]:
        """Redacts sensitive clinical terms to [REDACTED_MEDICAL_INFO].
        Prevents medical details from entering LLM context or ITSM ticket payloads.
        """
        matches = len(CLINICAL_REGEX.findall(text))
        redacted = CLINICAL_REGEX.sub("[REDACTED_MEDICAL_INFO]", text)
        return redacted, matches

    @classmethod
    def scrub_text(cls, text: str, stage: str = "pre_llm") -> Tuple[str, dict]:
        """Runs the full DLP inspection matrix."""
        redactions = {}
        scrubbed = text

        scrubbed, nric_count = cls.redact_nric(scrubbed)
        if nric_count > 0:
            redactions["nric"] = nric_count

        scrubbed, mc_count = cls.redact_mc_serial(scrubbed)
        if mc_count > 0:
            redactions["mc_serial"] = mc_count

        scrubbed, pass_count = cls.redact_passport(scrubbed)
        if pass_count > 0:
            redactions["passport"] = pass_count

        scrubbed, med_count = cls.redact_medical_info(scrubbed)
        if med_count > 0:
            redactions["medical_info"] = med_count

        return scrubbed, redactions
