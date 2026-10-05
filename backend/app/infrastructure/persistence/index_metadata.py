"""Decorate the public builder with host read-model persistence for each index."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.ai_providers.models import EmbeddingIndexVersion
from app.modules.documents.models import DocumentIndexMetadata, DocumentVersion
from app.modules.workspaces.models import Workspace


class MetadataIndexBuilder:
    def __init__(self, builder, session):
        self.builder, self.session = builder, session

    async def execute(self, document, resolve_embedding, make_store, **kwargs):
        runtime = None

        async def resolve():
            nonlocal runtime
            runtime = await resolve_embedding()
            return runtime

        index = await self.builder.execute(document, resolve, make_store, **kwargs)
        version_id = await self.session.scalar(
            select(EmbeddingIndexVersion.id).where(
                EmbeddingIndexVersion.index_name == runtime.index_name,
                EmbeddingIndexVersion.workspace_id == document.scope.workspace_id,
                EmbeddingIndexVersion.organization_id == document.scope.organization_id,
            )
        )
        if version_id is None:
            return index
        metadata = await self.session.get(DocumentIndexMetadata, (document.version_id, version_id))
        if metadata is None:
            metadata = DocumentIndexMetadata(
                document_version_id=document.version_id, embedding_index_version_id=version_id
            )
            self.session.add(metadata)
        metadata.chunk_count, metadata.indexed_at = len(index.chunks), datetime.now(UTC)
        workspace = await self.session.get(Workspace, document.scope.workspace_id)
        if workspace.active_embedding_index_version_id == version_id:
            document_version = await self.session.get(DocumentVersion, document.version_id)
            document_version.chunk_count = metadata.chunk_count
            document_version.indexed_at = metadata.indexed_at
        await self.session.commit()
        return index
