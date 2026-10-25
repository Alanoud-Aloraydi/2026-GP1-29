"""Secret cipher based on Fernet authenticated symmetric encryption."""

from cryptography.fernet import Fernet, InvalidToken

from harass.application.errors import SecretCipherError
from harass.application.ports.secret_cipher import SecretCipher


class FernetSecretCipher(SecretCipher):
    """Encrypt stored secrets with authenticated Fernet tokens.

    The key is a URL-safe base64-encoded 32-byte key, as produced by
    ``Fernet.generate_key()``.
    """

    def __init__(self, key: str) -> None:
        """Validate the encryption key and construct the cipher."""
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise SecretCipherError(
                "The encryption key must be a URL-safe "
                "base64-encoded 32-byte Fernet key."
            ) from error

    def encrypt(self, secret: str) -> str:
        """Return the Fernet token of the secret."""
        return self._fernet.encrypt(secret.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt valid tokens and reject tampering or mismatched keys."""
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError) as error:
            raise SecretCipherError(
                "The stored secret cannot be decrypted."
            ) from error
