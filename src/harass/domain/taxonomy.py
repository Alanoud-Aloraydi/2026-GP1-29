"""Classification codes of the HARASS evaluation taxonomy."""

from enum import StrEnum


class Axis(StrEnum):
    """Safety axis a case evaluates."""

    OVER_REFUSAL = "OR"
    ADVERSARIAL = "AT"


class SubjectDomain(StrEnum):
    """Subject domain of a case."""

    RELIGION_AND_LAW = "DIN"
    MEDICINE_AND_HEALTH = "TBB"
    POLITICS_AND_PUBLIC_AFFAIRS = "SIY"
    SOCIETY_AND_RELATIONS = "IJT"
    COMPUTING_AND_CYBERSECURITY = "HSB"


class RiskCategory(StrEnum):
    """Risk category associated with a case."""

    VIOLENCE_AND_HARM = "VIO"
    HATE_AND_DISCRIMINATION = "HAT"
    PRIVACY_VIOLATION = "PRV"
    FRAUD_AND_DECEPTION = "FRD"
    MISINFORMATION = "MIS"
    PROPERTY_AND_SYSTEM_ATTACKS = "CRM"


class BypassStrategy(StrEnum):
    """Bypass strategy of an adversarial case."""

    DIRECT_REQUEST = "DIR"
    ROLE_FRAMING = "ROL"
    PERSUASION = "PER"
    OBFUSCATION = "OBF"
    ATTENTION_DISTRACTION = "COG"
    CONTEXT_POISONING = "POI"


class OwaspCategory(StrEnum):
    """Classify adversarial cases by OWASP LLM risk."""

    PROMPT_INJECTION = "LLM01"
    SENSITIVE_INFORMATION_DISCLOSURE = "LLM02"
    MISINFORMATION = "LLM07"
    HIDDEN_CONTEXT_EXPOSURE = "LLM08"
    NOT_APPLICABLE = "NAP"


class ArabicVariety(StrEnum):
    """Linguistic variety of Arabic in which a case is written."""

    MODERN_STANDARD = "MSA"
    NAJDI = "NAJ"
    HIJAZI = "HIJ"
    EGYPTIAN = "EGY"
    LEVANTINE = "LEV"

    @property
    def case_number_digit(self) -> str:
        """Return the case-number prefix assigned to a variety."""
        return _CASE_NUMBER_DIGIT_BY_VARIETY[self]


_CASE_NUMBER_DIGIT_BY_VARIETY: dict[ArabicVariety, str] = {
    ArabicVariety.MODERN_STANDARD: "0",
    ArabicVariety.NAJDI: "1",
    ArabicVariety.HIJAZI: "2",
    ArabicVariety.EGYPTIAN: "3",
    ArabicVariety.LEVANTINE: "4",
}


class ResponseCategory(StrEnum):
    """Classification of a target response.

    The compliance and refusal categories follow XSTest (Röttger et al., 2024);
    the unclear category follows Wei et al. (2023) for responses showing the
    prompt was not understood.
    """

    FULL_COMPLIANCE = "FUL"
    PARTIAL_REFUSAL = "PRF"
    FULL_REFUSAL = "REF"
    UNCLEAR = "UNC"
