import pytest

from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.ai_providers.errors import ProviderConfigurationError


def test_provider_secret_round_trip_and_ciphertext_is_opaque() -> None:
    cipher = ProviderSecretCipher("dedicated-test-master-key")
    encrypted = cipher.encrypt("sk-super-secret")

    assert encrypted != "sk-super-secret"
    assert "sk-super-secret" not in encrypted
    assert cipher.decrypt(encrypted) == "sk-super-secret"


def test_wrong_master_key_returns_sanitized_configuration_error() -> None:
    encrypted = ProviderSecretCipher("first-key").encrypt("secret-that-must-not-leak")

    with pytest.raises(ProviderConfigurationError) as error:
        ProviderSecretCipher("second-key").decrypt(encrypted)

    assert "secret-that-must-not-leak" not in str(error.value)
