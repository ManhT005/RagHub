from collections.abc import Awaitable, Callable
from uuid import UUID

from raghub_core.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.ingestion.models import IngestionDocument, IngestionResult, IngestionStage
from raghub_core.ports.ingestion import IngestionRepositoryPort
from raghub_core.ports.provider_resolver import EmbeddingRuntime, ProviderResolverPort
from raghub_core.ports.vector_store import VectorStorePort


class RunIngestionUseCase:
    def __init__(
        self,
        repository: IngestionRepositoryPort,
        builder: BuildDocumentIndexUseCase,
        providers: ProviderResolverPort,
        make_store: Callable[[EmbeddingRuntime], VectorStorePort],
        *,
        pipeline: Callable[[IngestionDocument], Awaitable[None]] | None = None,
        retry_limits: dict[str, int] | None = None,
    ) -> None:
        self.repository = repository
        self.builder = builder
        self.providers = providers
        self.make_store = make_store
        self.pipeline = pipeline
        self.retry_limits = retry_limits or {}

    async def execute(
        self, version_id: UUID, *, retries: int = 0, max_retries: int = 3
    ) -> IngestionResult:
        attempt = await self.repository.load(version_id)
        if attempt is None:
            return IngestionResult(version_id, "SKIPPED", False, reason="MISSING_ATTEMPT")
        if attempt.status == IngestionStage.FAILED:
            return IngestionResult(version_id, attempt.status, False, reason="ALREADY_FAILED")
        if attempt.status == IngestionStage.READY and attempt.progress >= 100:
            return IngestionResult(version_id, attempt.status, False, reason="TERMINAL_REDELIVERY")
        if attempt.document is None:
            raise ValueError("A nonterminal ingestion attempt must contain document metadata.")
        await self.repository.begin(version_id)
        try:
            if self.pipeline:
                await self.pipeline(attempt.document)
            else:
                await self.build(attempt.document)
        except IngestionError as exc:
            await self.repository.record_failure(
                version_id,
                exc,
                failed=not exc.retryable or retries >= self.retry_limits.get(exc.code, max_retries),
            )
            raise
        except Exception as exc:
            error = IngestionError("INGESTION_FAILED", str(exc), retryable=False)
            await self.repository.record_failure(version_id, error, failed=True)
            raise error from exc
        return IngestionResult(version_id, IngestionStage.READY, True)

    async def build(self, document: IngestionDocument) -> None:
        async def stage(value: IngestionStage, progress: int) -> None:
            await self.repository.set_stage(document.version_id, value, progress)

        await self.builder.execute(
            document,
            lambda: self.providers.resolve_embedding(document.scope),
            self.make_store,
            stage=stage,
            before_index=lambda: self.repository.expose_version(document.version_id),
        )
        await self.repository.complete(document.version_id)
