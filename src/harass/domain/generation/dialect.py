"""Check an Arabic prompt against the variety it claims.

Two checks, both cheap and deterministic: a word listed for some varieties
is foreign in every other variety and in MSA, and a dialect prompt that
still carries strongly formal words was never really localized.
"""

import re
from collections.abc import Callable

DIACRITICS = re.compile(r"[ً-ْٰـ]")
UNIFY = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
WORD = re.compile(r"[ء-ي]+")
# Clitics that may attach to a marker; "ال" is tried first so "وال" resolves.
PREFIXES = ("ال", "و", "ف", "ب", "ل")
MAX_PREFIX_STRIPS = 2
# A two-letter marker reached only by stripping is nearly always a
# coincidence: MSA "لدي" and "بلدي" both reduce to "دي", and Levantine
# "بده" reduces to Egyptian "ده". Measured on the team's 377 prompts,
# this rule cuts false flags from 1.9% to 0.3% and costs one point of
# mislabel detection.
MIN_STRIPPED_LENGTH = 3

EGY, HIJ, LEV, NAJ = "EGY", "HIJ", "LEV", "NAJ"

# Each entry maps a word to the varieties where it is native.
MARKERS: dict[str, frozenset[str]] = {}


def normalize(text: str) -> str:
    """Drop diacritics and tatweel and unify alef, ta-marbuta and ya."""
    return DIACRITICS.sub("", text).translate(UNIFY)


def _add(words: str, *varieties: str) -> None:
    """Record every comma-separated word as native to these varieties."""
    native = frozenset(varieties)
    for word in words.replace("،", ",").split(","):
        token = normalize(word.strip())
        if token:
            MARKERS[token] = native


_add(
    "وشلون، تبي، يبي، حنا، مب، موب، هالحين، مير، تسان، تهقى، هقوتي، فيذا،"
    " فيذاك، تسذا، تسذب، عيّا، حَزّة، زهّبي، مفهي، ناه، سدح، أفحز، قراشيع، شلون، وش",
    NAJ,
)
_add(
    "دحين، أشبك، أشبنا، بزورة، أهرج، قوامن، بلكن، جغمة، دحلسة، مصرفدة، سيتي،"
    " استيتة، دحديرة، مزبرقة، اتلبخت، إيش",
    HIJ,
)
_add(
    "عايز، عاوز، عايزة، إزاي، دلوقتي، كده، أوي، بتاع، مفيش، ده،"
    " النهارده، امبارح، بص، ماعرفش، إزيّك، هروح، هنعمل، ترابيزة، الحقني، بإيه",
    EGY,
)
_add(
    "شو، بدي، بدك، بدنا، بدو، بده، هلأ، هلق، هيك، منيح، هون، هنيك، قديش،"
    " مشان، منشان، رح، هاد، هيدي، هداك، مصاري، شغلة، عنجد، نحنا، بكرا،"
    " بقدر، فيني، حدا، لحتى، إنو، متل",
    LEV,
)
_add("مش", EGY, LEV)
_add("الحين", NAJ, HIJ)
_add("أبغى، تبغى", NAJ, HIJ)
_add("فين، كدا، إيوه، يا واد، دي، برضه", HIJ, EGY)
_add("التاني", HIJ, EGY, LEV)
_add("هادا، هادي، هدول، دغري", HIJ, LEV)
_add("شوية", EGY, HIJ, LEV)
_add("بتعمل", EGY, LEV)
_add("إيه", EGY, NAJ, HIJ)
_add("لسه، لسا، معلش", EGY, HIJ, LEV)
_add("كتير", LEV, EGY, HIJ)
_add("ليش، كيفك، يسلمو، تكرم", LEV, NAJ, HIJ)

PHRASES = {word: native for word, native in MARKERS.items() if " " in word}
WORDS = {word: native for word, native in MARKERS.items() if " " not in word}

# Formal words no localized dialect prompt should keep. Words every variety
# also uses (الذي، كيف، حيث، الآن) are deliberately absent.
FORMAL = frozenset(
    normalize(word)
    for word in ["سوف", "لماذا", "ماذا", "أريد", "ليس", "ليست", "هؤلاء", "هذان", "اللاتي", "ينبغي"]
)


def stems(token: str) -> list[str]:
    """Return the token and the forms left by stripping up to two clitics."""
    found = [token]
    frontier = [token]
    for _ in range(MAX_PREFIX_STRIPS):
        nxt: list[str] = []
        for form in frontier:
            for prefix in PREFIXES:
                if form.startswith(prefix) and len(form) > len(prefix) + 1:
                    stem = form[len(prefix) :]
                    if len(stem) >= MIN_STRIPPED_LENGTH and stem not in found:
                        found.append(stem)
                        nxt.append(stem)
        frontier = nxt
    return found


def _hits(text: str, keep: Callable[[frozenset[str]], bool]) -> list[str]:
    """Collect marker words in a text whose native set satisfies ``keep``.

    O(n) in tokens: a bounded number of dict lookups per token.
    """
    body = normalize(text)
    found = [phrase for phrase, native in PHRASES.items() if keep(native) and phrase in body]
    for token in WORD.findall(body):
        for form in stems(token):
            native = WORDS.get(form)
            if native is not None:
                if keep(native):
                    found.append(form)
                break
    return found


def foreign_markers(text: str, variety: str) -> list[str]:
    """Return the markers in a text that are not native to its variety."""
    return _hits(text, lambda native: variety not in native)


def native_markers(text: str, variety: str) -> list[str]:
    """Return the markers in a text that are native to its own variety."""
    return _hits(text, lambda native: variety in native)


def formal_leakage(text: str) -> list[str]:
    """Return formal words that show a dialect prompt was not localized."""
    body = normalize(text)
    return sorted({token for token in WORD.findall(body) if token in FORMAL})
