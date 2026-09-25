import hashlib
import json
import math
import time
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.modules.ai_providers.contracts import ChatMessage, ChatOptions
from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.ai_providers.enums import (
    IndexVersionStatus,
    ProviderCapability,
    ProviderType,
    ReindexJobStatus,
)
from app.modules.ai_providers.errors import ProviderConfigurationError
from app.modules.ai_providers.models import (
    EmbeddingIndexVersion,
    EmbeddingReindexJob,
    ProviderConfig,
)
from app.modules.ai_providers.registry import ProviderRegistry
from app.modules.ai_providers.repository import ProviderConfigRepository
from app.modules.ai_providers.schemas import ProviderConfigInput, ProviderConfigPatch
from app.modules.documents.models import Document, DocumentStatus
from app.modules.workspaces.models import Workspace


def embedding_fingerprint(config: ProviderConfig) -> str:
    identity = "\0".join(
        (
            str(config.id),
            str(config.provider_type),
            config.base_url or "",
            config.model,
            str(config.dimension),
            json.dumps(config.config_json or {}, sort_keys=True, separators=(",", ":")),
        )
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def workspace_index_name(workspace_id: UUID, version_id: UUID) -> str:
    return f"raghub_chunks_{workspace_id.hex}_v{version_id.hex[:12]}"


class ProviderConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProviderConfigRepository(session)
        self.registry = ProviderRegistry()
        self.cipher = ProviderSecretCipher(get_settings().provider_master_key)

    async def list(self, organization_id: UUID) -> list[ProviderConfig]:
        return await self.repository.list_for_organization(organization_id)

    async def get(self, organization_id: UUID, provider_id: UUID) -> ProviderConfig:
        config = await self.repository.get_scoped(organization_id, provider_id)
        if config is None:
            raise AppError("PROVIDER_NOT_FOUND", "Provider was not found.", status_code=404)
        return config

    async def create(self, organization_id: UUID, payload: ProviderConfigInput) -> ProviderConfig:
        config = ProviderConfig(
            organization_id=organization_id,
            name=payload.name.strip(),
            provider_type=payload.provider_type,
            capability=payload.capability,
            base_url=payload.base_url.rstrip("/") if payload.base_url else None,
            model=payload.model.strip(),
            dimension=payload.dimension,
            encrypted_secret=self.cipher.encrypt(payload.secret) if payload.secret else None,
            config_json=payload.config_json,
            enabled=payload.enabled,
        )
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def update(
        self, organization_id: UUID, provider_id: UUID, payload: ProviderConfigPatch
    ) -> ProviderConfig:
        config = await self.get(organization_id, provider_id)
        if payload.enabled is False and config.enabled and await self._is_bound(
            organization_id, provider_id
        ):
            raise AppError(
                "PROVIDER_IN_USE",
                "An active workspace provider cannot be disabled.",
                status_code=409,
            )
        if (
            payload.clear_secret
            and config.provider_type
            in {ProviderType.OPENAI_COMPATIBLE, ProviderType.GOOGLE_GEMINI}
            and await self._is_bound(organization_id, provider_id)
        ):
            raise AppError(
                "PROVIDER_CREDENTIAL_IN_USE",
                "Credentials cannot be cleared while the provider is bound.",
                status_code=409,
            )
        old_fingerprint = embedding_fingerprint(config) if config.dimension else None
        reindex_jobs: list[EmbeddingReindexJob] = []
        values = payload.model_dump(exclude_unset=True, exclude={"secret", "clear_secret"})
        for field, value in values.items():
            if field == "base_url" and value:
                value = value.rstrip("/")
            if isinstance(value, str):
                value = value.strip()
            setattr(config, field, value)
        if payload.secret is not None:
            config.encrypted_secret = self.cipher.encrypt(payload.secret)
        elif payload.clear_secret:
            config.encrypted_secret = None
        if config.capability == ProviderCapability.EMBEDDING and not config.dimension:
            raise ProviderConfigurationError("Embedding providers require dimension.")
        await self.session.flush()
        if old_fingerprint and old_fingerprint != embedding_fingerprint(config):
            workspaces = await self.session.scalars(
                select(Workspace).where(
                    Workspace.organization_id == organization_id,
                    Workspace.embedding_provider_id == provider_id,
                    Workspace.deleted_at.is_(None),
                )
            )
            for workspace in workspaces:
                job = await self._stage_embedding_version(workspace, config)
                if job:
                    reindex_jobs.append(job)
        await self.session.commit()
        for job in reindex_jobs:
            await self._enqueue_reindex(job)
        await self.session.refresh(config)
        return config

    async def _is_bound(self, organization_id: UUID, provider_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(Workspace.id).where(
                    Workspace.organization_id == organization_id,
                    Workspace.deleted_at.is_(None),
                    (Workspace.embedding_provider_id == provider_id)
                    | (Workspace.chat_provider_id == provider_id),
                )
            )
        )

    async def delete(self, organization_id: UUID, provider_id: UUID) -> None:
        config = await self.get(organization_id, provider_id)
        bound = await self.session.scalar(
            select(Workspace.id).where(
                Workspace.organization_id == organization_id,
                (Workspace.embedding_provider_id == provider_id)
                | (Workspace.chat_provider_id == provider_id),
            )
        )
        if bound:
            raise AppError("PROVIDER_IN_USE", "Provider is bound to a workspace.", status_code=409)
        has_history = await self.session.scalar(
            select(EmbeddingIndexVersion.id).where(
                EmbeddingIndexVersion.provider_config_id == provider_id
            )
        )
        if has_history:
            config.enabled = False
            config.encrypted_secret = None
            await self.session.commit()
            return
        await self.session.delete(config)
        await self.session.commit()

    async def test(self, organization_id: UUID, provider_id: UUID) -> dict[str, object]:
        config = await self.get(organization_id, provider_id)
        if not config.enabled:
            raise AppError("PROVIDER_DISABLED", "Provider is disabled.", status_code=409)
        secret = self.cipher.decrypt(config.encrypted_secret) if config.encrypted_secret else None
        provider = self.registry.create(config, secret)
        started = time.monotonic()
        dimension: int | None = None
        if config.capability == ProviderCapability.EMBEDDING:
            vector = await provider.embed_query("RagHub provider connectivity test")  # type: ignore[attr-defined]
            if not vector or not all(math.isfinite(value) for value in vector):
                raise ProviderConfigurationError("Provider returned an invalid embedding.")
            dimension = len(vector)
            if dimension != config.dimension:
                raise ProviderConfigurationError(
                    "Provider embedding dimension does not match config."
                )
        else:
            received = False
            async for token in provider.stream_chat(  # type: ignore[attr-defined]
                [ChatMessage("user", "Reply with OK")], ChatOptions(max_tokens=8)
            ):
                if token:
                    received = True
                    break
            if not received:
                raise ProviderConfigurationError("Provider returned an empty chat stream.")
        return {
            "status": "OK",
            "capability": config.capability,
            "provider": config.provider_type,
            "model": config.model,
            "dimension": dimension,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    async def bind_workspace(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        *,
        embedding_provider_id: UUID | None,
        chat_provider_id: UUID | None,
    ) -> tuple[Workspace, EmbeddingReindexJob | None]:
        workspace = await self.session.scalar(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.organization_id == organization_id,
                Workspace.deleted_at.is_(None),
            )
        )
        if workspace is None:
            raise AppError("WORKSPACE_NOT_FOUND", "Workspace was not found.", status_code=404)
        reindex_job = None
        if chat_provider_id is not None:
            chat = await self.get(organization_id, chat_provider_id)
            if chat.capability != ProviderCapability.CHAT:
                raise ProviderConfigurationError("Selected chat provider has wrong capability.")
            workspace.chat_provider_id = chat.id
        if embedding_provider_id is not None:
            embedding = await self.get(organization_id, embedding_provider_id)
            if embedding.capability != ProviderCapability.EMBEDDING:
                raise ProviderConfigurationError(
                    "Selected embedding provider has wrong capability."
                )
            active = (
                await self.session.get(
                    EmbeddingIndexVersion, workspace.active_embedding_index_version_id
                )
                if workspace.active_embedding_index_version_id
                else None
            )
            if active is None or active.embedding_fingerprint != embedding_fingerprint(embedding):
                reindex_job = await self._stage_embedding_version(workspace, embedding)
            else:
                workspace.embedding_provider_id = embedding.id
        await self.session.commit()
        if reindex_job:
            await self._enqueue_reindex(reindex_job)
        return workspace, reindex_job

    async def _enqueue_reindex(self, job: EmbeddingReindexJob) -> None:
        try:
            from app.workers.reindex_tasks import reindex_workspace

            reindex_workspace.delay(str(job.id))
        except Exception:
            job.status = ReindexJobStatus.QUEUE_FAILED
            job.error_code = "REINDEX_QUEUE_UNAVAILABLE"
            job.error_message = (
                "The re-index job could not be queued. Retry when the broker recovers."
            )
            await self.session.commit()

    async def retry_reindex(self, organization_id: UUID, job_id: UUID) -> EmbeddingReindexJob:
        job = await self.session.scalar(
            select(EmbeddingReindexJob).where(
                EmbeddingReindexJob.id == job_id,
                EmbeddingReindexJob.organization_id == organization_id,
            )
        )
        if job is None:
            raise AppError("REINDEX_JOB_NOT_FOUND", "Re-index job was not found.", status_code=404)
        if job.status not in {ReindexJobStatus.QUEUE_FAILED, ReindexJobStatus.FAILED}:
            raise AppError(
                "REINDEX_JOB_NOT_RETRYABLE", "Re-index job is not retryable.", status_code=409
            )
        job.status = ReindexJobStatus.QUEUED
        job.error_code = job.error_message = None
        job.completed_at = None
        await self.session.commit()
        await self._enqueue_reindex(job)
        return job

    async def _stage_embedding_version(
        self, workspace: Workspace, config: ProviderConfig
    ) -> EmbeddingReindexJob | None:
        version_id = uuid.uuid4()
        version = EmbeddingIndexVersion(
            id=version_id,
            organization_id=workspace.organization_id,
            workspace_id=workspace.id,
            provider_config_id=config.id,
            provider_type=config.provider_type,
            base_url=config.base_url,
            model=config.model,
            dimension=config.dimension,
            config_json=config.config_json or {},
            embedding_fingerprint=embedding_fingerprint(config),
            index_name=workspace_index_name(workspace.id, version_id),
            status=IndexVersionStatus.BUILDING,
        )
        self.session.add(version)
        if workspace.pending_embedding_index_version_id:
            previous_job = await self.session.scalar(
                select(EmbeddingReindexJob).where(
                    EmbeddingReindexJob.target_index_version_id
                    == workspace.pending_embedding_index_version_id,
                    EmbeddingReindexJob.status.not_in(
                        (ReindexJobStatus.COMPLETED, ReindexJobStatus.FAILED)
                    ),
                )
            )
            if previous_job:
                previous_job.status = ReindexJobStatus.SUPERSEDED
                previous_job.completed_at = datetime.now(UTC)
        workspace.pending_embedding_index_version_id = version.id
        ready_count = int(
            await self.session.scalar(
                select(func.count(Document.id)).where(
                    Document.workspace_id == workspace.id,
                    Document.organization_id == workspace.organization_id,
                    Document.status == DocumentStatus.READY,
                    Document.deleted_at.is_(None),
                )
            )
            or 0
        )
        if ready_count == 0:
            old = (
                await self.session.get(
                    EmbeddingIndexVersion, workspace.active_embedding_index_version_id
                )
                if workspace.active_embedding_index_version_id
                else None
            )
            if old:
                old.status = IndexVersionStatus.RETIRED
            version.status = IndexVersionStatus.ACTIVE
            version.activated_at = datetime.now(UTC)
            workspace.active_embedding_index_version_id = version.id
            workspace.embedding_provider_id = config.id
            workspace.pending_embedding_index_version_id = None
            return None
        job = EmbeddingReindexJob(
            organization_id=workspace.organization_id,
            workspace_id=workspace.id,
            target_index_version_id=version.id,
            status=ReindexJobStatus.QUEUED,
            total_documents=ready_count,
        )
        self.session.add(job)
        await self.session.flush()
        return job
