"""Rebus writing that swaps a spoken number name inside a word for digits.

Gulf street writing such as "لا10ساني" (لا تنساني) or "مح4عليها" (محفور
عليها) is read by sounding each number out by its English or Arabic name.
Human readers resolve it at once, while a model must link the digit, the
spoken name and the surrounding letters across scripts.
"""

import re
from collections.abc import Callable

# Arabic-script spellings of English number names, read as sounds.
ENGLISH_NUMBER_SOUNDS = {
    "ون": "1",
    "تو": "2",
    "ثري": "3",
    "فور": "4",
    "فايف": "5",
    "سكس": "6",
    "سفن": "7",
    "ايت": "8",
    "ناين": "9",
    "تن": "10",
    "ايلفن": "11",
    "تولف": "12",
    "تونتي": "20",
    "ثيرتي": "30",
    "فورتي": "40",
    "فيفتي": "50",
    "هندرد": "100",
    "ثاوزند": "1000",
    "مليون": "1000000",
}

# Arabic number names, including tens and dialect spellings of hundreds.
# "ألف" keeps its hamza so the article in words like "الفكرة" is not read
# as a thousand.
ARABIC_NUMBER_WORDS = {
    "واحد": "1",
    "اثنين": "2",
    "اثنان": "2",
    "ثلاث": "3",
    "اربع": "4",
    "خمس": "5",
    "ست": "6",
    "سبع": "7",
    "ثمان": "8",
    "تسع": "9",
    "عشر": "10",
    "عشرين": "20",
    "ثلاثين": "30",
    "اربعين": "40",
    "خمسين": "50",
    "ستين": "60",
    "سبعين": "70",
    "ثمانين": "80",
    "تسعين": "90",
    "مية": "100",
    "مئة": "100",
    "مائة": "100",
    "ميتين": "200",
    "ألف": "1000",
    "مليون": "1000000",
}

_ALEFS = "اأإآ"
_HAS_DIGIT = re.compile(r"\d")


def rebus_writer(names: dict[str, str]) -> Callable[[str], str]:
    """Build a writer that puts one number name per word as its digits.

    Only the leftmost, longest name in each word is replaced, so tens win
    over units ("ستين" over "ست") and digits from two names never merge into
    one misleading number. Words that already contain a digit are left
    unchanged, which also keeps two writers from stacking in one word.
    Writing is linear in the text length for a fixed table.
    """
    spellings = _with_alef_spellings(names)
    pattern = re.compile(
        "|".join(map(re.escape, sorted(spellings, key=len, reverse=True)))
    )

    def replace_word(word: re.Match[str]) -> str:
        """Replace the first number name of one whitespace-free word."""
        if _HAS_DIGIT.search(word[0]):
            return word[0]
        return pattern.sub(lambda name: spellings[name[0]], word[0], 1)

    def write(text: str) -> str:
        """Rewrite every word of the text independently."""
        return re.sub(r"\S+", replace_word, text)

    return write


def _with_alef_spellings(names: dict[str, str]) -> dict[str, str]:
    """Accept every alef spelling at the start of names that begin with ا."""
    spellings = dict(names)
    for name, digits in names.items():
        if name.startswith("ا"):
            spellings |= {alef + name[1:]: digits for alef in _ALEFS}
    return spellings
