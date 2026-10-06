from uuid import uuid4

import httpx
import pytest

from app.cli.provider_smoke import probe
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.modules.ai_providers.catalog import supported_catalog_by_id
from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.ai_providers.models import ProviderConnection
from app.modules.organizations.models import Organization


@pytest.mark.parametrize(
    "module,marker",
    [
        ("app.cli", "bootstrap-owner"),
        ("app.cli.providers", "import-env"),
        ("app.cli.provider_smoke", "--connection-id"),
    ],
)
def test_cli_entry_points_are_importable_packages(module, marker):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", module, "--help"], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0 and marker in result.stdout


async def test_smoke_uses_each_account_credential_and_rejects_wrong_organization(
    isolated_sessions, monkeypatch
):
    captured = []

    def handle(request):
        captured.append(request)
        return httpx.Response(
            200, text='data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n\n'
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**{**kwargs, "transport": httpx.MockTransport(handle)}),
    )
    cipher = ProviderSecretCipher(get_settings().provider_master_key)
    async with isolated_sessions() as session:
        org = Organization(name="Smoke", slug=uuid4().hex)
        session.add(org)
        await session.flush()
        connections = []
        for i, brand in enumerate(["groq", "openrouter", "openrouter"]):
            item = supported_catalog_by_id(brand)
            connection = ProviderConnection(
                organization_id=org.id,
                catalog_id=brand,
                provider_type=item.provider_type,
                name=brand,
                enabled=True,
                base_url=item.default_base_url,
                config_json={"request_profile": item.request_profile},
                encrypted_secret=cipher.encrypt(f"account-key-{i}"),
            )
            session.add(connection)
            connections.append(connection)
        await session.commit()
        for connection in connections:
            result = await probe(session, org.id, connection.id, "served-model", "CHAT")
            assert result["status"] == "OK" and "account-key" not in str(result)
        assert [request.headers["authorization"] for request in captured] == [
            "Bearer account-key-0",
            "Bearer account-key-1",
            "Bearer account-key-2",
        ]
        with pytest.raises(AppError) as error:
            await probe(session, uuid4(), connections[0].id, "served-model", "CHAT")
        assert error.value.code == "PROVIDER_NOT_FOUND" and len(captured) == 3
