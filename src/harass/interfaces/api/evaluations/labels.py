"""Arabic catalogue labels shared by HTTP metadata and report presentation."""

DIALECTS = {
    "MSA": "الفصحى",
    "NAJ": "النجدية",
    "HIJ": "الحجازية",
    "EGY": "المصرية",
    "LEV": "الشامية",
}

AXES = {"AT": "مقاومة الاختراق", "OR": "الرفض المفرط"}

LABELS = {
    "DIN": "الدين والشريعة",
    "TBB": "الطب والصحة",
    "SIY": "السياسة والشؤون العامة",
    "IJT": "المجتمع والعلاقات",
    "HSB": "الحوسبة والأمن السيبراني",
    "VIO": "العنف والإيذاء",
    "HAT": "خطاب الكراهية والتمييز والتنمر",
    "PRV": "انتهاك الخصوصية والسرّية",
    "FRD": "الاحتيال والخداع",
    "MIS": "التضليل واختلاق الوقائع",
    "CRM": "الاعتداء على الممتلكات والأنظمة",
    "DIR": "طلب مباشر",
    "ROL": "التأطير بدور أو سياق متخيَّل",
    "PER": "الإقناع",
    "OBF": "التعمية وتغيير التمثيل",
    "COG": "تشتيت الانتباه أو تفكيك المحتوى",
    "POI": "تسميم السياق داخل الرسالة",
    "LLM01": "حقن التعليمات",
    "LLM02": "كشف معلومات حساسة",
    "LLM07": "معلومات مضللة",
    "LLM08": "كشف سياق مخفي",
    "NAP": "لا ينطبق",
}

# Short names for the over-refusal mechanisms; the domain keeps the writer's
# longer instructions, which are too long to show as a pattern's name.
MECHANISM_LABELS = {
    "homonym": "كلمة بمعنيين، والمقصود بريء",
    "figurative": "تعبير مجازي بلفظ مخيف",
    "harmless_object": "فعل مخيف يقع على شيء لا يتأذى",
    "own_property": "الهدف ملك السائل نفسه",
    "fictional_entity": "الهدف شخصية أو جهة خيالية",
    "public_info": "معلومة منشورة علنًا",
    "nonsense_group": "جماعة لا وجود لها",
}

# The adapter's transforms, in the order the setup page offers them.
TRANSFORM_LABELS = {
    "tatweel": "إدراج التطويل بين الحروف",
    "zero_width": "إدراج محارف صفرية العرض",
    "presentation_forms": "أشكال العرض العربية",
    "base64": "ترميز Base64 مع طلب فكّه",
    "unicode_escape": "ترميز يونيكود مع طلب فكّه",
    "arabizi": "العربيزي (حروف لاتينية وأرقام)",
    "english_number_sounds": "استبدال المقاطع بأرقام إنجليزية",
    "arabic_number_words": "استبدال المقاطع بأسماء الأعداد",
}
