"""Case identifiers of the HARASS coding system."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from harass.domain.errors import InvalidCaseIdentifierError
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    OwaspCategory,
    RiskCategory,
    SubjectDomain,
)

_SEGMENT_SEPARATOR = "-"
_CASE_NUMBER_PATTERN = re.compile(r"\d{5}")
_OVER_REFUSAL_SEGMENT_COUNT = 5
_ADVERSARIAL_SEGMENT_COUNT = 7


@dataclass(frozen=True)
class CaseIdentifier:
    """Identifier encoding the axis, classification and variety of one evaluation case."""

    axis: Axis
    subject_domain: SubjectDomain
    risk_category: RiskCategory
    variety: ArabicVariety
    case_number: str
    strategy: BypassStrategy | None = None
    owasp_category: OwaspCategory | None = None

    def __post_init__(self) -> None:
        """Enforce the coding-system rules that span several fields."""
        if not _CASE_NUMBER_PATTERN.fullmatch(self.case_number):
            raise InvalidCaseIdentifierError(
                f"Case number '{self.case_number}' must consist of exactly five digits."
            )
        if self.case_number[0] != self.variety.case_number_digit:
            raise InvalidCaseIdentifierError(
                f"Case number '{self.case_number}' must start with "
                f"'{self.variety.case_number_digit}' for variety {self.variety}."
            )
        if self.axis is Axis.OVER_REFUSAL:
            if self.strategy is not None or self.owasp_category is not None:
                raise InvalidCaseIdentifierError(
                    "Over-refusal cases carry neither a bypass strategy nor an OWASP category."
                )
            return
        if self.strategy is None or self.owasp_category is None:
            raise InvalidCaseIdentifierError(
                "Adversarial cases require one bypass strategy and an OWASP category."
            )

    @property
    def base_case_number(self) -> str:
        """Return the four digits shared by all varieties of the same case."""
        return self.case_number[1:]

    @classmethod
    def parse(cls, text: str) -> CaseIdentifier:
        """Parse a textual identifier such as ``AT-SIY-MIS-ROL-LLM07-HIJ-20002``."""
        segments = text.split(_SEGMENT_SEPARATOR)
        axis = _parse_code(Axis, segments[0], text)
        expected_segment_count = (
            _OVER_REFUSAL_SEGMENT_COUNT
            if axis is Axis.OVER_REFUSAL
            else _ADVERSARIAL_SEGMENT_COUNT
        )
        if len(segments) != expected_segment_count:
            raise InvalidCaseIdentifierError(
                f"Identifier '{text}' must have {expected_segment_count} segments "
                f"for axis {axis}, found {len(segments)}."
            )
        if axis is Axis.OVER_REFUSAL:
            _, domain_code, risk_code, variety_code, case_number = segments
            return cls(
                axis=axis,
                subject_domain=_parse_code(SubjectDomain, domain_code, text),
                risk_category=_parse_code(RiskCategory, risk_code, text),
                variety=_parse_code(ArabicVariety, variety_code, text),
                case_number=case_number,
            )
        _, domain_code, risk_code, strategy_code, owasp_code, variety_code, case_number = segments
        return cls(
            axis=axis,
            subject_domain=_parse_code(SubjectDomain, domain_code, text),
            risk_category=_parse_code(RiskCategory, risk_code, text),
            variety=_parse_code(ArabicVariety, variety_code, text),
            case_number=case_number,
            strategy=_parse_code(BypassStrategy, strategy_code, text),
            owasp_category=_parse_code(OwaspCategory, owasp_code, text),
        )

    def __str__(self) -> str:
        """Render the identifier in its canonical textual form."""
        segments: list[str] = [self.axis, self.subject_domain, self.risk_category]
        if self.strategy is not None and self.owasp_category is not None:
            segments.extend([self.strategy, self.owasp_category])
        segments.extend([self.variety, self.case_number])
        return _SEGMENT_SEPARATOR.join(segments)


def _parse_code[CodeT: StrEnum](code_type: type[CodeT], code: str, identifier: str) -> CodeT:
    """Convert one identifier segment into its taxonomy member."""
    try:
        return code_type(code)
    except ValueError as error:
        allowed_codes = ", ".join(member.value for member in code_type)
        raise InvalidCaseIdentifierError(
            f"Segment '{code}' in identifier '{identifier}' is not a valid "
            f"{code_type.__name__}; expected one of: {allowed_codes}."
        ) from error
