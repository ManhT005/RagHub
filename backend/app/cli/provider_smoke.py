"""Read-only runtime smoke using an explicitly scoped, encrypted connection credential."""

import argparse
import asyncio
import json
from uuid import UUID

from raghub_core.domain.errors import CoreError
from raghub_core.domain.providers.contracts import ChatMessage, ChatOptions
from raghub_core.domain.providers.descriptor import ProviderDescriptor
from raghub_core.domain.providers.errors import ProviderConfigurationError
from raghub_core.domain.providers.rerank import validated_rerank_indices

from app.core.database import SessionFactory, engine
from app.modules.ai_providers.catalog import connection_catalog_id, supported_catalog_by_id
from app.modules.ai_providers.control_service import ProviderControlService
from app.modules.ai_providers.registry import ProviderRegistry
from app.modules.ai_providers.schemas import validate_connection_endpoint


async def probe(session, organization_id, connection_id, model, capability, dimension=None):
    service = ProviderControlService(session)
    connection = await service.get(organization_id, connection_id)
    catalog = supported_catalog_by_id(connection_catalog_id(connection))
    if not connection.enabled or capability not in catalog.capabilities:
        raise ProviderConfigurationError("Choose an enabled connection with this capability.")
    base = validate_connection_endpoint(connection)
    descriptor = ProviderDescriptor(
        provider_type=connection.provider_type,
        capability=capability,
        model=model,
        base_url=base,
        dimension=dimension,
        options={**connection.config_json, "max_attempts": 1, "read_timeout": 30},
    )
    provider = ProviderRegistry().create(descriptor, service.secret(connection))
    result = {"catalog_id": catalog.id, "model": model, "capability": capability, "status": "OK"}
    if capability == "EMBEDDING":
        documents = await provider.embed_documents(["RagHub documentation", "Workspace search"])
        query = await provider.embed_query("RagHub search")
        if len(documents) != 2 or any(len(vector) != len(query) for vector in documents):
            raise ProviderConfigurationError("Document/query embedding dimensions differ.")
        result["dimension"] = len(query)
    elif capability == "RERANK":
        ranked = await provider.rerank(
            query="RagHub", documents=["RagHub documentation", "Another topic"], top_n=2
        )
        validated_rerank_indices(ranked, 2, 2)
    else:
        received = False
        async for delta in provider.stream_chat(
            [ChatMessage("user", "Reply with OK")], ChatOptions(max_tokens=12)
        ):
            received = received or bool(delta.text)
        if not received:
            raise ProviderConfigurationError("Chat stream was empty.")
    return result


async def run(args):
    import app.models  # noqa: F401

    try:
        async with SessionFactory() as session:
            return await probe(
                session,
                args.organization_id,
                args.connection_id,
                args.model,
                args.capability,
                args.dimension,
            )
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True, type=UUID)
    parser.add_argument("--connection-id", required=True, type=UUID)
    parser.add_argument("--model", required=True)
    parser.add_argument("--capability", required=True, choices=["CHAT", "EMBEDDING", "RERANK"])
    parser.add_argument("--dimension", type=int)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except CoreError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code}))
        raise SystemExit(1) from None
    except Exception:
        print(json.dumps({"status": "FAILED", "error_code": "SMOKE_FAILED"}))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
