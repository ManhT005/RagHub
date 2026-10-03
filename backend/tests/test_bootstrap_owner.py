from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.infrastructure.persistence.bootstrap import BootstrapOwnerInput
from app.modules.auth.email import build_email_sender


def test_bootstrap_validates_credentials_without_disclosing_password():
    with pytest.raises(ValidationError):
        BootstrapOwnerInput(email="owner@example.com", password="short")
    payload = BootstrapOwnerInput(email="owner@example.com", password="strong-test-password")
    assert "strong-test-password" not in repr(payload)


async def test_selfhost_without_smtp_cannot_log_reset_tokens(monkeypatch):
    settings = Settings(_env_file=None, app_env="selfhost", provider_master_key="test-master-key")
    warning = AsyncMock()
    monkeypatch.setattr("app.modules.auth.email.logger.warning", warning)
    with pytest.raises(AppError, match="Configure SMTP"):
        await build_email_sender(settings).send("owner@example.com", "Reset", "secret-token")
    warning.assert_not_called()
