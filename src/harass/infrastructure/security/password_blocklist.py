"""Local compromised-password screening without sending passwords to a service."""

import hashlib
from pathlib import Path

COMMON_PASSWORDS = (
    "123456789012345",
    "1234567890123456",
    "12345678901234567890",
    "passwordpassword",
    "password123456789",
    "qwertyuiopasdfgh",
    "qwertyuiop123456",
    "iloveyouiloveyou",
    "adminadminadminadmin",
)


def password_hashes(path: str | None = None) -> frozenset[str]:
    """Combine built-in examples with an optional maintained SHA-256 blocklist."""
    hashes = {hashlib.sha256(password.encode()).hexdigest() for password in COMMON_PASSWORDS}
    if path:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            value = line.strip().lower()
            if not value or value.startswith("#"):
                continue
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("Password blocklist must contain one SHA-256 digest per line.")
            hashes.add(value)
    return frozenset(hashes)
