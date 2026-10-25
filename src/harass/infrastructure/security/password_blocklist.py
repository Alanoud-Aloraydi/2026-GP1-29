"""Screen password hashes locally against configured blocklists."""

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
    """Load built-in and optional external SHA-256 password hashes."""
    hashes = {
        hashlib.sha256(password.encode()).hexdigest()
        for password in COMMON_PASSWORDS
    }
    sources = [Path(__file__).with_name("common_passwords.sha256")]
    if path:
        sources.append(Path(path))
    for source in sources:
        for line in source.read_text(encoding="utf-8").splitlines():
            value = line.strip().lower()
            if not value or value.startswith("#"):
                continue
            if len(value) != 64 or any(
                c not in "0123456789abcdef" for c in value
            ):
                raise ValueError(
                    "Password blocklist must contain one SHA-256 "
                    "digest per line."
                )
            hashes.add(value)
    return frozenset(hashes)
