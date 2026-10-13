"""Port for protecting secrets, such as client API keys, while they are stored."""

from abc import ABC, abstractmethod


class SecretCipher(ABC):
    """Encrypts secrets before storage and decrypts them only when they are needed."""

    @abstractmethod
    def encrypt(self, secret: str) -> str:
        """Return an opaque token that reveals nothing about the secret."""

    @abstractmethod
    def decrypt(self, token: str) -> str:
        """Return the secret behind a token produced by ``encrypt``.

        Raises:
            SecretCipherError: If the token was altered or encrypted with another key.
        """
