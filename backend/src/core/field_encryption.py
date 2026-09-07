"""Authenticated encryption for secrets stored by server-side adapters."""

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from core.errors import AppError


class DecryptionError(AppError):
    """Raised when protected stored material cannot be authenticated."""


class FieldCipher:
    """Encrypt and authenticate opaque server-side values with Fernet."""

    def __init__(
        self,
        key: str,
    ) -> None:
        if not key:
            message = "An explicit encryption key is required"
            raise ValueError(message)
        self._fernet = Fernet(key.encode("ascii"))

    def encrypt(
        self,
        plaintext: str,
    ) -> str:
        """Encrypt a string for persistence without exposing its contents."""

        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(
        self,
        ciphertext: str,
    ) -> str:
        """Authenticate and decrypt a stored string or fail closed."""

        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("ascii"))
        except (InvalidToken, ValueError) as exc:
            raise DecryptionError("Protected material could not be decrypted") from exc
        return plaintext.decode("utf-8")


__all__ = ["DecryptionError", "FieldCipher"]
