"""Arabic labels under which verdicts and metrics are presented to readers.

Codes remain the machine-readable identifiers; the labels follow the naming
agreed for reports: attack outcomes on the adversarial axis and XSTest response
categories on both axes.
"""

from harass.domain.taxonomy import ResponseCategory

RESPONSE_CATEGORY_LABELS = {
    ResponseCategory.FULL_COMPLIANCE: "أجاب عن الطلب",
    ResponseCategory.PARTIAL_REFUSAL: "أجاب جزئيًا",
    ResponseCategory.FULL_REFUSAL: "رفض الطلب",
    ResponseCategory.UNCLEAR: "رد غير واضح",
}
ATTACK_OUTCOME_LABELS = {True: "اختراق ناجح", False: "اختراق فاشل"}
METRIC_LABELS = {
    "attack_success": "معدل نجاح الاختراق",
    "refusal": "معدل الرفض (كلي أو جزئي)",
    "over_refusal": "معدل الرفض المفرط",
    "full_refusal": "معدل رفض الطلب كاملًا",
    "unclear": "معدل الردود غير الواضحة",
}
