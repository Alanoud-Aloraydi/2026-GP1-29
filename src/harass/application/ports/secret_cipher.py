"""Define encryption and decryption of stored secrets."""

from abc import ABC, abstractmethod


class SecretCipher(ABC):
    """Protect stored secrets and decrypt them for authorized use."""

    @abstractmethod
    def encrypt(self, secret: str) -> str:
        """Return an opaque token that reveals nothing about the secret."""

    @abstractmethod
    def decrypt(self, token: str) -> str:
        """Return the secret behind a token produced by ``encrypt``.

        Raises: SecretCipherError: If the token was altered or encrypted with
        another key.
        """
