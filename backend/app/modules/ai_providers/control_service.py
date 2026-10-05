import math
import time
from datetime import UTC, datetime
from uuid import UUID

from raghub_core.domain.errors import CoreError
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.infrastructure.provider_credentials import resolve_provider_secret
from app.modules.ai_providers.catalog import connection_catalog_id, supported_catalog_by_id
from app.modules.ai_providers.control_schemas import (
    ConnectionInput,
    ConnectionPatch,
    ConnectionResponse,
    ConnectionTestResponse,
    ModelInput,
    ModelResponse,
)
from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.ai_providers.discovery import discover_models
from app.modules.ai_providers.models import OllamaModelPull, ProviderConfig, ProviderConnection
from app.modules.ai_providers.schemas import ProviderConfigInput
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.workspaces.models import Workspace


def connection_response(connection, model_count=0):
    return ConnectionResponse(
        **{
            key: getattr(connection, key)
            for key in ConnectionResponse.model_fields
            if key not in {"has_secret", "model_count", "catalog_id"}
        },
        catalog_id=connection_catalog_id(connection),
        has_secret=bool(connection.encrypted_secret),
        model_count=model_count,
    )


def model_response(config, used=0):
    connection = config.connection
    return ModelResponse(
        id=config.id,
        connection_id=config.connection_id,
        model=config.model,
        display_name=config.display_name or config.name,
        provider_name=connection.name if connection else config.name,
        provider_type=config.provider_type,
        provider_catalog_id=connection_catalog_id(connection) if connection else None,
        capability=config.capability,
        dimension=config.dimension,
        availability_status=config.availability_status,
        enabled=config.enabled,
        connection_status=connection.status if connection else "UNTESTED",
        connection_enabled=connection.enabled if connection else config.enabled,
        used_by_workspaces=used,
        last_health_check_at=config.last_health_check_at,
    )


def health_error(exc: CoreError) -> str:
    return {
        "PROVIDER_AUTH_FAILED": "PROVIDER_AUTH_FAILED",
        "PROVIDER_UNAVAILABLE": "PROVIDER_UNREACHABLE",
        "PROVIDER_TIMEOUT": "PROVIDER_UNREACHABLE",
        "PROVIDER_INVALID_RESPONSE": "MODEL_DIMENSION_MISMATCH",
        "PROVIDER_NOT_CONFIGURED": "MODEL_DIMENSION_MISMATCH",
    }.get(exc.code, "PROVIDER_UNREACHABLE")


class ProviderControlService:
    def __init__(self, session):
        self.session = session
        self.cipher = ProviderSecretCipher(get_settings().provider_master_key)

    async def get(self, organization_id, connection_id):
        connection = await self.session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.id == connection_id,
                ProviderConnection.organization_id == organization_id,
            )
        )
        if connection is None:
            raise AppError("PROVIDER_NOT_FOUND", "Connection not found.", status_code=404)
        return connection

    async def list(self, organization_id):
        counts = (
            select(ProviderConfig.connection_id, func.count().label("count"))
            .group_by(ProviderConfig.connection_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(ProviderConnection, counts.c.count)
            .outerjoin(
                counts,
                counts.c.connection_id == ProviderConnection.id,
            )
            .where(ProviderConnection.organization_id == organization_id)
            .order_by(ProviderConnection.name)
        )
        return [connection_response(connection, count or 0) for connection, count in rows]

    async def create(self, organization_id, payload: ConnectionInput):
        connection = ProviderConnection(
            organization_id=organization_id,
            name=payload.name,
            provider_type=payload.provider_type,
            catalog_id=payload.catalog_id,
            base_url=payload.base_url,
            config_json=payload.config_json,
            enabled=payload.enabled,
            encrypted_secret=self.cipher.encrypt(payload.secret) if payload.secret else None,
        )
        self.session.add(connection)
        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def update(self, organization_id, connection_id, payload: ConnectionPatch):
        connection = await self.get(organization_id, connection_id)
        if payload.catalog_id and payload.catalog_id != connection_catalog_id(connection):
            raise AppError(
                "PROVIDER_IDENTITY_IMMUTABLE",
                "Create a new connection to switch providers.",
                status_code=422,
            )
        catalog_id = payload.catalog_id or connection_catalog_id(connection)
        if supported_catalog_by_id(catalog_id).provider_type != connection.provider_type:
            raise AppError(
                "UNSUPPORTED_PROVIDER",
                "Catalog identity must match the runtime adapter.",
                status_code=422,
            )
        models = list(
            await self.session.scalars(
                select(ProviderConfig).where(ProviderConfig.connection_id == connection_id)
            )
        )
        changes = payload.model_dump(exclude_unset=True, exclude={"secret", "clear_secret"})
        proposed = ConnectionInput(
            name=changes.get("name", connection.name),
            provider_type=connection.provider_type,
            catalog_id=catalog_id,
            base_url=changes.get("base_url", connection.base_url),
            config_json=changes.get("config_json", connection.config_json),
            enabled=changes.get("enabled", connection.enabled),
            secret=payload.secret,
        )
        current_catalog = supported_catalog_by_id(connection_catalog_id(connection))
        current_options = dict(connection.config_json or {})
        current_options.setdefault("endpoint_scope", current_catalog.endpoint_scope)
        current_options.setdefault("request_profile", current_catalog.request_profile)
        runtime_changed = (
            proposed.base_url != connection.base_url or proposed.config_json != current_options
        )
        if runtime_changed or not proposed.enabled or payload.secret or payload.clear_secret:
            await self._require_no_active_pull(connection_id)
        if (runtime_changed or not proposed.enabled or payload.clear_secret) and models:
            for model in models:
                if await ProviderConfigService(self.session)._is_bound(organization_id, model.id):
                    raise AppError(
                        "PROVIDER_IN_USE", "Connection is used by a workspace.", status_code=409
                    )
        connection.name, connection.enabled = proposed.name, proposed.enabled
        connection.catalog_id = proposed.catalog_id
        connection.base_url, connection.config_json = proposed.base_url, proposed.config_json
        if payload.secret:
            connection.encrypted_secret = self.cipher.encrypt(payload.secret)
        elif payload.clear_secret:
            connection.encrypted_secret = None
        if runtime_changed or payload.secret or payload.clear_secret:
            connection.status = "UNTESTED"
            connection.last_error_code = None
            for model in models:
                model.base_url, model.config_json = proposed.base_url, proposed.config_json
                model.availability_status = "UNTESTED"
        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def delete(self, organization_id, connection_id):
        connection = await self.get(organization_id, connection_id)
        await self._require_no_active_pull(connection_id)
        if await self.session.scalar(
            select(ProviderConfig.id).where(ProviderConfig.connection_id == connection_id).limit(1)
        ):
            raise AppError(
                "PROVIDER_IN_USE",
                "Remove registered models before this connection.",
                status_code=409,
            )
        await self.session.delete(connection)
        await self.session.commit()

    async def _require_no_active_pull(self, connection_id):
        if await self.session.scalar(
            select(OllamaModelPull.id)
            .where(
                OllamaModelPull.connection_id == connection_id,
                OllamaModelPull.status.in_({"QUEUED", "PULLING", "VERIFYING"}),
            )
            .limit(1)
        ):
            raise AppError(
                "MODEL_PULL_IN_PROGRESS", "Wait for the active download.", status_code=409
            )

    def secret(self, connection):
        return resolve_provider_secret(connection, self.cipher)

    async def discover(self, organization_id, connection_id):
        connection = await self.get(organization_id, connection_id)
        if not connection.enabled:
            raise AppError("PROVIDER_DISABLED", "Connection is disabled.", status_code=409)
        return await discover_models(connection, self.secret(connection))

    async def test(self, organization_id, connection_id):
        connection = await self.get(organization_id, connection_id)
        if not connection.enabled:
            raise AppError("PROVIDER_DISABLED", "Connection is disabled.", status_code=409)
        item = supported_catalog_by_id(connection_catalog_id(connection))
        start = time.monotonic()
        error_code = None
        try:
            if item.supports_model_discovery:
                await discover_models(connection, self.secret(connection))
            else:
                import importlib.util

                if importlib.util.find_spec("sentence_transformers") is None:
                    raise AppError(
                        "PROVIDER_UNREACHABLE", "Local AI dependency unavailable.", status_code=422
                    )
            connection.status = "CONNECTED"
        except AppError as exc:
            if exc.code == "MODEL_DISCOVERY_UNSUPPORTED":
                # Manual mode still needs a successful runtime model probe before selection.
                connection.status = "UNTESTED"
            else:
                connection.status = "ERROR"
            error_code = exc.code
        connection.last_error_code = error_code
        connection.last_tested_at = datetime.now(UTC)
        connection.last_latency_ms = int((time.monotonic() - start) * 1000)
        await self.session.commit()
        return ConnectionTestResponse(
            status=connection.status,
            latency_ms=connection.last_latency_ms,
            capabilities=item.capabilities,
            discovery_supported=item.supports_model_discovery,
            error_code=error_code,
        )

    async def register(self, organization_id, connection_id, payload: ModelInput):
        connection = await self.get(organization_id, connection_id)
        item = supported_catalog_by_id(connection_catalog_id(connection))
        if payload.capability not in item.capabilities:
            raise AppError("UNSUPPORTED_CAPABILITY", "Capability unavailable.", status_code=422)
        if not connection.enabled:
            raise AppError("PROVIDER_DISABLED", "Connection is disabled.", status_code=409)
        if not payload.model.strip():
            raise AppError("INVALID_MODEL", "Model ID required.", status_code=422)
        existing = await self.session.scalar(
            select(ProviderConfig).where(
                ProviderConfig.connection_id == connection_id,
                ProviderConfig.model == payload.model.strip(),
                ProviderConfig.capability == payload.capability,
            )
        )
        if existing:
            raise AppError(
                "MODEL_ALREADY_REGISTERED", "Model is already registered.", status_code=409
            )
        validated = ProviderConfigInput(
            name=payload.display_name or payload.model,
            provider_type=connection.provider_type,
            capability=payload.capability,
            model=payload.model.strip(),
            base_url=connection.base_url,
            dimension=(payload.dimension or 1) if payload.capability == "EMBEDDING" else None,
            config_json=connection.config_json,
        )
        config = ProviderConfig(
            organization_id=organization_id,
            connection=connection,
            name=validated.name,
            display_name=validated.name,
            provider_type=validated.provider_type,
            capability=validated.capability,
            model=validated.model,
            dimension=validated.dimension,
            base_url=validated.base_url,
            config_json=validated.config_json,
            enabled=True,
        )
        if payload.capability == "EMBEDDING" and payload.dimension is None:
            config.dimension = await infer_dimension(
                connection, validated.model, self.secret(connection)
            )
        self.session.add(config)
        await self.session.flush()
        # Models become selectable only after an actual embedding/chat runtime request succeeds.
        try:
            await ProviderConfigService(self.session).test(organization_id, config.id)
        except CoreError as exc:
            await self.session.rollback()
            raise AppError(
                health_error(exc), "Model health probe failed.", status_code=422
            ) from exc
        await self.session.commit()
        return config

    async def models(
        self, organization_id: UUID, *, capability=None, availability=None, provider_type=None
    ):
        counts = (
            select(ProviderConfig.id.label("model_id"), func.count(Workspace.id).label("count"))
            .outerjoin(
                Workspace,
                (
                    (Workspace.embedding_provider_id == ProviderConfig.id)
                    | (Workspace.chat_provider_id == ProviderConfig.id)
                )
                & Workspace.deleted_at.is_(None),
            )
            .group_by(ProviderConfig.id)
            .subquery()
        )
        statement = (
            select(ProviderConfig, counts.c.count)
            .join(counts, counts.c.model_id == ProviderConfig.id)
            .where(ProviderConfig.organization_id == organization_id)
        )
        if capability:
            statement = statement.where(ProviderConfig.capability == capability)
        if availability:
            statement = statement.where(ProviderConfig.availability_status == availability)
        if provider_type:
            statement = statement.where(ProviderConfig.provider_type == provider_type)
        rows = await self.session.execute(statement.order_by(ProviderConfig.model))
        return [model_response(config, count or 0) for config, count in rows]


async def infer_dimension(connection, model: str, secret: str | None) -> int:
    """Probe outside the engine, then let its regular adapter verify the registration."""
    if connection.provider_type == "LOCAL_SENTENCE_TRANSFORMER":
        import asyncio

        from app.modules.ai_providers.adapters.sentence_transformer import (
            SentenceTransformerModelRegistry,
        )

        try:
            loaded = await asyncio.to_thread(SentenceTransformerModelRegistry.get, model)
            dimension = loaded.get_sentence_embedding_dimension()
        except Exception as exc:
            raise AppError(
                "PROVIDER_UNREACHABLE", "Local model probe failed.", status_code=422
            ) from exc
    else:
        import httpx

        from app.modules.ai_providers.request_profiles import embedding_payload
        from app.modules.ai_providers.schemas import validate_connection_endpoint

        try:
            base = validate_connection_endpoint(connection).rstrip("/")
        except ValueError as exc:
            raise AppError(
                "PROVIDER_ENDPOINT_REJECTED", "Provider endpoint is not allowed.", status_code=422
            ) from exc
        profile = supported_catalog_by_id(connection_catalog_id(connection)).request_profile
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.post(
                    f"{base}/embeddings",
                    headers={"Authorization": f"Bearer {secret}"} if secret else {},
                    json=embedding_payload(profile, model, ["RagHub dimension probe"], "query"),
                )
                if response.status_code in {401, 403}:
                    raise AppError(
                        "PROVIDER_AUTH_FAILED", "Authentication failed.", status_code=422
                    )
                if response.status_code != 200:
                    raise AppError("PROVIDER_UNREACHABLE", "Model probe failed.", status_code=422)
                vector = response.json()["data"][0]["embedding"]
                if not all(math.isfinite(value) for value in vector):
                    raise ValueError("Invalid vector")
                dimension = len(vector)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise AppError(
                "MODEL_DIMENSION_MISMATCH", "Enter embedding dimension manually.", status_code=422
            ) from exc
    if not isinstance(dimension, int) or not 0 < dimension <= 65536:
        raise AppError(
            "MODEL_DIMENSION_MISMATCH", "Enter embedding dimension manually.", status_code=422
        )
    return dimension
