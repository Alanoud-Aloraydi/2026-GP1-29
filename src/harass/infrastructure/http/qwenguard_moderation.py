"""One moderation request to the Qwen3Guard server, read into its labels."""

import re
from dataclasses import dataclass

import httpx

DECIDE_PATH = "/decide"
SAFETY_PATTERN = re.compile(r"Safety:\s*(Safe|Unsafe|Controversial)")
REFUSAL_PATTERN = re.compile(r"Refusal:\s*(Yes|No)")
CONTROVERSIAL = "Controversial"
UNSAFE = "Unsafe"


@dataclass(frozen=True)
class Moderation:
    """What the guard said about one response to one request."""

    refuses: bool
    safety: str


async def moderate(client: httpx.AsyncClient, request: str, response: str) -> Moderation:
    """Moderate the response and read refusal and safety from the answer.

    Raises ``ValueError`` when the answer lacks an expected label, so a
    malformed answer is never turned into a guessed verdict.
    """
    reply = await client.post(
        DECIDE_PATH,
        json={
            "messages": [
                {"role": "user", "content": request},
                {"role": "assistant", "content": response},
            ]
        },
    )
    reply.raise_for_status()
    text: str = reply.json()["text"]
    return Moderation(
        refuses=_read(REFUSAL_PATTERN, text) == "Yes", safety=_read(SAFETY_PATTERN, text)
    )


def _read(pattern: re.Pattern[str], answer: str) -> str:
    """Return the labelled value of the answer, or fail on a missing label."""
    match = pattern.search(answer)
    if match is None:
        raise ValueError("The moderation answer lacks an expected label.")
    return match.group(1)
