"""Arabic labels under which verdicts and metrics are presented to readers.

Codes remain the machine-readable identifiers; the labels follow the naming agreed for
reports: attack outcomes on the adversarial axis and XSTest response categories on both axes.
"""

from harass.domain.taxonomy import ResponseCategory

RESPONSE_CATEGORY_LABELS = {
    ResponseCategory.FULL_COMPLIANCE: "امتثال كامل",
    ResponseCategory.PARTIAL_REFUSAL: "رفض جزئي",
    ResponseCategory.FULL_REFUSAL: "رفض كامل",
    ResponseCategory.UNCLEAR: "غير واضح",
}
ATTACK_OUTCOME_LABELS = {True: "هجوم ناجح", False: "هجوم فاشل"}
METRIC_LABELS = {
    "attack_success": "معدل نجاح الهجوم (ASR)",
    "refusal": "معدل الرفض",
    "over_refusal": "معدل الرفض المفرط",
    "full_refusal": "معدل الرفض الكامل",
    "unclear": "معدل الردود غير الواضحة",
}
