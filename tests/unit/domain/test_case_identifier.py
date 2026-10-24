"""Tests for the case identifier coding rules."""

import pytest

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.errors import InvalidCaseIdentifierError
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    OwaspCategory,
    RiskCategory,
    SubjectDomain,
)


def test_parses_over_refusal_identifier() -> None:
    """Verify parses over refusal identifier."""
    identifier = CaseIdentifier.parse("OR-DIN-VIO-MSA-00001")

    assert identifier.axis is Axis.OVER_REFUSAL
    assert identifier.subject_domain is SubjectDomain.RELIGION_AND_LAW
    assert identifier.risk_category is RiskCategory.VIOLENCE_AND_HARM
    assert identifier.variety is ArabicVariety.MODERN_STANDARD
    assert identifier.strategy is None
    assert identifier.owasp_category is None


def test_parses_adversarial_identifier() -> None:
    """Verify parses adversarial identifier."""
    identifier = CaseIdentifier.parse("AT-SIY-MIS-ROL-LLM07-HIJ-20002")

    assert identifier.axis is Axis.ADVERSARIAL
    assert identifier.strategy is BypassStrategy.ROLE_FRAMING
    assert identifier.owasp_category is OwaspCategory.MISINFORMATION
    assert identifier.variety is ArabicVariety.HIJAZI


@pytest.mark.parametrize(
    "text", ["OR-DIN-VIO-MSA-00001", "AT-SIY-MIS-ROL-LLM07-HIJ-20002"]
)
def test_rendering_reproduces_the_canonical_text(text: str) -> None:
    """Parsing then rendering is lossless."""
    assert str(CaseIdentifier.parse(text)) == text


def test_base_case_number_is_shared_across_varieties() -> None:
    """The last four digits identify the case independently of its variety."""
    standard = CaseIdentifier.parse("OR-HSB-VIO-MSA-00001")
    najdi = CaseIdentifier.parse("OR-HSB-VIO-NAJ-10001")

    assert standard.base_case_number == najdi.base_case_number == "0001"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("OR-DIN-VIO-NAJ-00001", "first digit does not encode the variety"),
        ("OR-DIN-VIO-MSA-0001", "case number has four digits"),
        ("OR-DIN-VIO-MSA-0000A", "case number is not numeric"),
        ("AT-SIY-MIS-PER+ROL-LLM07-HIJ-20002", "strategies are combined"),
        ("AT-SIY-MIS-NAJ-LLM07-HIJ-20002", "a variety is used as a strategy"),
        (
            "AT-SIY-MIS-ROL-LLM05-HIJ-20002",
            "OWASP code is outside the taxonomy",
        ),
        ("XX-DIN-VIO-MSA-00001", "axis is unknown"),
        ("OR-DIN-VIO-MSA", "segment is missing"),
        (
            "AT-DIN-VIO-MSA-00001",
            "adversarial identifier lacks strategy and OWASP segments",
        ),
    ],
)
def test_rejects_identifiers_that_violate_the_coding_system(
    text: str, reason: str
) -> None:
    """Malformed identifiers are rejected with a domain error."""
    with pytest.raises(InvalidCaseIdentifierError):
        CaseIdentifier.parse(text)
