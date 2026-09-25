import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.modules.ai_providers.errors import ProviderConfigurationError


class ProviderSecretCipher:
    def __init__(self, master_key: str) -> None:
        if not master_key or master_key == "change-me-provider-key":
            raise ProviderConfigurationError("PROVIDER_MASTER_KEY must be configured.")
        key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise ProviderConfigurationError(
                "The provider credential cannot be decrypted."
            ) from exc
