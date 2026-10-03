from collections.abc import Callable
from uuid import UUID

from raghub_core.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from raghub_core.domain.ingestion.reindex import has_all_document_versions, is_transient_failure
from raghub_core.domain.providers.enums import ReindexJobStatus
from raghub_core.ports.provider_resolver import EmbeddingRuntime, ProviderResolverPort
from raghub_core.ports.reindex import ReindexRepositoryPort
from raghub_core.ports.vector_store import VectorStorePort


class ReindexWorkspaceUseCase:
    def __init__(
        self,
        repository: ReindexRepositoryPort,
        builder: BuildDocumentIndexUseCase,
        providers: ProviderResolverPort,
        make_store: Callable[[EmbeddingRuntime], VectorStorePort],
    ) -> None:
        self.repository = repository
        self.builder = builder
        self.providers = providers
        self.make_store = make_store

    async def execute(self, job_id: UUID, *, fail_transient: bool = False) -> None:
        target = await self.repository.load(job_id)
        if target is None or target.status not in {
            ReindexJobStatus.QUEUED,
            ReindexJobStatus.RUNNING,
        }:
            return
        if not target.current:
            await self.repository.mark(job_id, ReindexJobStatus.SUPERSEDED)
            return
        await self.repository.mark(job_id, ReindexJobStatus.RUNNING)
        try:
            runtime = await self.providers.resolve_embedding_version(target.index_version_id)
            documents = await self.repository.latest_documents(target)
            await self.repository.reset_progress(job_id, len(documents))
            store = self.make_store(runtime)

            async def resolved() -> EmbeddingRuntime:
                return runtime

            try:
                store.ensure_index()
                for document in documents:
                    await self.builder.execute(
                        document,
                        resolved,
                        lambda _: store,
                        close_store=False,
                    )
                    await self.repository.processed(job_id)
                await self.repository.mark(job_id, ReindexJobStatus.VALIDATING)
                expected = {document.version_id for document in documents}
                if not has_all_document_versions(
                    expected, store.document_version_ids(target.scope.workspace_id)
                ):
                    raise RuntimeError("Re-index validation found missing documents")
            finally:
                store.close()
            await self.repository.mark(job_id, ReindexJobStatus.SWITCHING)
            await self.repository.activate(target)
        except Exception as exc:
            if is_transient_failure(exc) and not fail_transient:
                await self.repository.rollback()
                raise
            await self.repository.fail(job_id, exc)
            raise
