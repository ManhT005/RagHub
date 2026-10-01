from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.auth.email import send_password_reset_email


@pytest.mark.asyncio
async def test_password_reset_email_uses_sender() -> None:
    sender = AsyncMock()

    await send_password_reset_email(
        sender,
        "user@example.com",
        "https://app.example/reset?token=secret-token",
    )

    subject, text = sender.send.call_args.args[1:]
    assert "secret-token" in text and "mật khẩu" in subject.lower()


def test_production_requires_gmail_smtp_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            app_secret_key="production-secret",
            provider_master_key="production-provider-key",
        )
