"""Tests for the Fernet secret cipher."""

import pytest
from cryptography.fernet import Fernet

from harass.application.errors import SecretCipherError
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher

SECRET = "sk-test-placeholder"


@pytest.fixture
def cipher() -> FernetSecretCipher:
    """Return a cipher with a fresh key."""
    return FernetSecretCipher(Fernet.generate_key().decode("ascii"))


def test_round_trip_restores_the_secret(cipher: FernetSecretCipher) -> None:
    """Decryption returns exactly what was encrypted."""
    assert cipher.decrypt(cipher.encrypt(SECRET)) == SECRET


def test_token_does_not_contain_the_secret(cipher: FernetSecretCipher) -> None:
    """The stored token reveals nothing of the secret."""
    assert SECRET not in cipher.encrypt(SECRET)


def test_altered_token_is_rejected(cipher: FernetSecretCipher) -> None:
    """Fernet authenticates tokens, so any change is detected."""
    token = cipher.encrypt(SECRET)
    altered = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]

    with pytest.raises(SecretCipherError):
        cipher.decrypt(altered)


def test_token_from_another_key_is_rejected(cipher: FernetSecretCipher) -> None:
    """A token is readable only with the key that produced it."""
    other = FernetSecretCipher(Fernet.generate_key().decode("ascii"))

    with pytest.raises(SecretCipherError):
        cipher.decrypt(other.encrypt(SECRET))


def test_invalid_key_is_rejected_at_construction() -> None:
    """A malformed key fails early with a clear error."""
    with pytest.raises(SecretCipherError, match="Fernet key"):
        FernetSecretCipher("not-a-key")
