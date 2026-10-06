"""Run inside the API container: real LOCAL setup/providers in a disposable schema."""

import asyncio
import secrets
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.auth.email import build_email_sender
from app.modules.auth.service import AuthService
from app.modules.installation.models import InstallationState
from app.modules.installation.schemas import InitializeInstallationInput
from app.modules.installation.service import InitializeInstallationService


async def main():
    settings = get_settings()
    schema = "setup_smoke_" + uuid4().hex
    admin = create_async_engine(settings.database_url, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add(InstallationState(id=1, status="UNINITIALIZED"))
            await session.commit()
            auth = AuthService(
                session=session,
                settings=settings,
                email_sender=build_email_sender(settings),
            )
            result = await InitializeInstallationService(session).initialize(
                InitializeInstallationInput(
                    owner_email="local-setup-smoke@example.com",
                    owner_password=secrets.token_urlsafe(24),
                    ai_mode="LOCAL",
                ),
                auth_service=auth,
            )
            assert result.auth and len(result.provider_ids) == 2
            providers = ProviderConfigService(session)
            from uuid import UUID

            for provider_id in result.provider_ids:
                tested = await providers.test(
                    UUID(result.organization_id), UUID(provider_id)
                )
                assert tested["status"] == "OK"
            await auth.refresh(result.auth.refresh_token)
            assert (await session.get(InstallationState, 1)).status == "INITIALIZED"
        print(
            "PASS: atomic LOCAL setup, multilingual embedding, Ollama chat and setup refresh session",
            flush=True,
        )
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


if __name__ == "__main__":
    asyncio.run(main())
