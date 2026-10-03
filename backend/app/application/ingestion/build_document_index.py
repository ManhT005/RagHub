import math
from collections.abc import Awaitable, Callable

from app.core_domain.ingestion.chunker import TextChunk, chunk_sections
from app.core_domain.ingestion.errors import IngestionError
from app.core_domain.ingestion.models import IngestionDocument, IngestionStage
from app.core_domain.ingestion.parser import (
    EmptyExtractedTextError,
    InvalidPdfError,
    ParsedSection,
    TextDecodeError,
    UnsupportedFileTypeError,
    UnsupportedOcrError,
)
from app.core_domain.providers.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.core_domain.retrieval.models import DocumentIndex, IndexedChunk
from app.ports.object_storage import ObjectStoragePort
from app.ports.provider_resolver import EmbeddingRuntime
from app.ports.vector_store import VectorStorePort

StageCallback = Callable[[IngestionStage, int], Awaitable[None]]


class BuildDocumentIndexUseCase:
    """One parse/chunk/embed/index path for ingestion and workspace rebuilds."""

    def __init__(
        self,
        storage: ObjectStoragePort,
        parser: Callable[[bytes, str], list[ParsedSection]],
        *,
        chunker: Callable[..., list[TextChunk]] = chunk_sections,
    ) -> None:
        self.storage = storage
        self.parser = parser
        self.chunker = chunker

    async def execute(
        self,
        document: IngestionDocument,
        resolve_embedding: Callable[[], Awaitable[EmbeddingRuntime]],
        make_store: Callable[[EmbeddingRuntime], VectorStorePort],
        *,
        stage: StageCallback | None = None,
        before_index: Callable[[], Awaitable[None]] | None = None,
        close_store: bool = True,
    ) -> DocumentIndex:
        try:
            content = self.storage.get(document.storage_key)
        except Exception as exc:
            raise IngestionError("STORAGE_UNAVAILABLE", str(exc), retryable=True) from exc
        try:
            sections = self.parser(content, document.source_name)
        except (
            InvalidPdfError,
            UnsupportedOcrError,
            TextDecodeError,
            EmptyExtractedTextError,
            UnsupportedFileTypeError,
        ) as exc:
            codes = {
                InvalidPdfError: "INVALID_PDF",
                UnsupportedOcrError: "FAILED_UNSUPPORTED_OCR",
                TextDecodeError: "TEXT_DECODE_FAILED",
                EmptyExtractedTextError: "EMPTY_EXTRACTED_TEXT",
                UnsupportedFileTypeError: "UNSUPPORTED_FILE_TYPE",
            }
            raise IngestionError(codes[type(exc)], str(exc), retryable=False) from exc
        except Exception as exc:
            raise IngestionError("PARSE_FAILED", str(exc), retryable=False) from exc
        if stage:
            await stage(IngestionStage.CHUNKING, 45)
        try:
            chunks = self.chunker(sections, document.version_id)
            if not chunks:
                raise EmptyExtractedTextError("No chunks were extracted.")
        except EmptyExtractedTextError as exc:
            raise IngestionError("EMPTY_EXTRACTED_TEXT", str(exc), retryable=False) from exc
        except Exception as exc:
            raise IngestionError("CHUNKING_FAILED", str(exc), retryable=False) from exc
        if stage:
            await stage(IngestionStage.EMBEDDING, 65)
        try:
            runtime = await resolve_embedding()
            vectors = await runtime.provider.embed_documents([chunk.content for chunk in chunks])
            if len(vectors) != len(chunks):
                raise ValueError("Embedding response count does not match chunks")
            if any(
                len(v) != runtime.dimension or not all(math.isfinite(x) for x in v) for v in vectors
            ):
                raise ValueError(
                    "Embedding vectors do not match the index dimension or are invalid"
                )
            index = DocumentIndex(
                document.scope,
                document.document_id,
                document.version_id,
                document.source_name,
                tuple(
                    IndexedChunk(chunk, tuple(vector))
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ),
            )
        except (ProviderTimeoutError, ProviderUnavailableError, ProviderRateLimitError) as exc:
            raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=True) from exc
        except Exception as exc:
            raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=False) from exc
        if stage:
            await stage(IngestionStage.INDEXING, 85)
        if before_index:
            await before_index()
        store = make_store(runtime)
        try:
            store.replace(index)
        except Exception as exc:
            try:
                store.delete_document_version(document.version_id)
            except Exception:
                # Preserve the indexing error; readiness filtering hides partial data.
                pass
            raise IngestionError("INDEX_UNAVAILABLE", str(exc), retryable=True) from exc
        finally:
            if close_store:
                store.close()
        return index
