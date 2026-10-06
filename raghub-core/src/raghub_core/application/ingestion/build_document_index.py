import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace

from raghub_core.domain.ingestion.chunker import TextChunk, chunk_sections, embedding_text
from raghub_core.domain.ingestion.embedding_text import DOCUMENT_PIPELINES, build_embedding_text
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.ingestion.limits import MAX_CHUNKS, MAX_EXTRACTED_TOKENS
from raghub_core.domain.ingestion.models import IngestionDocument, IngestionStage
from raghub_core.domain.ingestion.normalization import normalize_sections
from raghub_core.domain.ingestion.parser import (
    DecompressionBombError,
    DocumentLimitError,
    EmptyExtractedTextError,
    InvalidPdfError,
    MacroBlockedError,
    OcrRequiredError,
    OcrTimeoutError,
    ParsedSection,
    SignatureMismatchError,
    TextDecodeError,
    UnsupportedFileTypeError,
    UnsupportedOcrError,
)
from raghub_core.domain.ingestion.tokenizer import ENCODING
from raghub_core.domain.providers.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from raghub_core.domain.retrieval.models import DocumentIndex, IndexedChunk
from raghub_core.ports.embedding_quota import (
    EmbeddingQuotaPort,
    QuotaBackendUnavailableError,
    QuotaDepletedError,
)
from raghub_core.ports.object_storage import ObjectStoragePort
from raghub_core.ports.provider_resolver import EmbeddingRuntime
from raghub_core.ports.telemetry import TelemetryPort
from raghub_core.ports.vector_store import VectorStorePort

StageCallback = Callable[[IngestionStage, int], Awaitable[None]]
QuotaAcquire = Callable[[int], Awaitable[None]]


class BuildDocumentIndexUseCase:
    """One parse/chunk/embed/index path for ingestion and workspace rebuilds."""

    def __init__(
        self,
        storage: ObjectStoragePort,
        parser: Callable[[bytes, str], list[ParsedSection]],
        *,
        chunker: Callable[..., list[TextChunk]] = chunk_sections,
        quota: EmbeddingQuotaPort | None = None,
        embedding_executor: Callable[..., Awaitable[list[list[float]]]] | None = None,
    ) -> None:
        self.storage = storage
        self.parser = parser
        self.chunker = chunker
        self.quota = quota
        self.embedding_executor = embedding_executor

    async def execute(
        self,
        document: IngestionDocument,
        resolve_embedding: Callable[[], Awaitable[EmbeddingRuntime]],
        make_store: Callable[[EmbeddingRuntime], VectorStorePort],
        *,
        stage: StageCallback | None = None,
        before_index: Callable[[], Awaitable[None]] | None = None,
        close_store: bool = True,
        acquire_quota: QuotaAcquire | None = None,
        telemetry: TelemetryPort | None = None,
    ) -> DocumentIndex:
        started = time.perf_counter()
        checkpoint = started

        def observe(stage: str) -> None:
            nonlocal checkpoint
            now = time.perf_counter()
            if telemetry is not None:
                telemetry.timing(stage, (now - checkpoint) * 1000, {})
            checkpoint = now

        try:
            content = await self.storage.get(document.storage_key)
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
            SignatureMismatchError,
            MacroBlockedError,
            OcrRequiredError,
            OcrTimeoutError,
        ) as exc:
            codes = {
                InvalidPdfError: "INVALID_PDF",
                UnsupportedOcrError: "FAILED_UNSUPPORTED_OCR",
                TextDecodeError: "TEXT_DECODE_FAILED",
                EmptyExtractedTextError: "EMPTY_EXTRACTED_TEXT",
                UnsupportedFileTypeError: "UNSUPPORTED_FILE_TYPE",
                SignatureMismatchError: "INVALID_FILE_SIGNATURE",
                MacroBlockedError: "MACRO_BLOCKED",
                OcrRequiredError: "OCR_REQUIRED",
                OcrTimeoutError: "OCR_TIMEOUT",
            }
            raise IngestionError(codes[type(exc)], str(exc), retryable=False) from exc
        except DecompressionBombError as exc:
            raise IngestionError("DECOMPRESSION_BOMB", str(exc), retryable=False) from exc
        except DocumentLimitError as exc:
            raise IngestionError("DOCUMENT_LIMIT_EXCEEDED", str(exc), retryable=False) from exc
        except Exception as exc:
            raise IngestionError("PARSE_FAILED", str(exc), retryable=False) from exc
        observe("parse")
        if stage:
            await stage(IngestionStage.CHUNKING, 45)
        try:
            # Bound allocation before building all chunks from oversized extracted text.
            extracted = 0
            for section in sections:
                for offset in range(0, len(section.content), 8192):
                    extracted += len(ENCODING.encode(section.content[offset : offset + 8192]))
                    if extracted > MAX_EXTRACTED_TOKENS:
                        raise DocumentLimitError(f"Document exceeds {MAX_EXTRACTED_TOKENS} tokens.")
            chunks = self.chunker(sections, document.version_id)
            if not chunks:
                raise EmptyExtractedTextError("No chunks were extracted.")
            if len(chunks) > MAX_CHUNKS:
                raise DocumentLimitError(f"Document exceeds {MAX_CHUNKS} chunks.")
            if sum(getattr(chunk, "token_count", 0) for chunk in chunks) > MAX_EXTRACTED_TOKENS:
                raise DocumentLimitError(f"Document exceeds {MAX_EXTRACTED_TOKENS} tokens.")
        except EmptyExtractedTextError as exc:
            raise IngestionError("EMPTY_EXTRACTED_TEXT", str(exc), retryable=False) from exc
        except DocumentLimitError as exc:
            raise IngestionError("DOCUMENT_LIMIT_EXCEEDED", str(exc), retryable=False) from exc
        except Exception as exc:
            raise IngestionError("CHUNKING_FAILED", str(exc), retryable=False) from exc
        observe("chunk_preflight")
        try:
            runtime = await resolve_embedding()
        except ProviderRateLimitError as exc:
            raise IngestionError("EMBEDDING_QUOTA_WAIT", str(exc), retryable=True) from exc
        except (ProviderTimeoutError, ProviderUnavailableError) as exc:
            raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=True) from exc
        except Exception as exc:
            raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=False) from exc
        observe("resolve_embedding")
        if runtime.document_pipeline not in DOCUMENT_PIPELINES:
            raise IngestionError(
                "EMBEDDING_FAILED", "Unsupported document pipeline.", retryable=False
            )
        try:
            if runtime.document_pipeline != "legacy":
                sections = normalize_sections(sections)
            observe("normalize")
            if runtime.document_pipeline != "legacy":
                chunks = self.chunker(sections, document.version_id)
                chunks = [
                    replace(
                        c,
                        embedding_content=build_embedding_text(
                            c, pipeline=runtime.document_pipeline
                        ),
                    )
                    for c in chunks
                ]
                if (
                    len(chunks) > MAX_CHUNKS
                    or sum(c.token_count for c in chunks) > MAX_EXTRACTED_TOKENS
                ):
                    raise IngestionError(
                        "DOCUMENT_LIMIT_EXCEEDED",
                        "Normalized chunks exceed document limits.",
                        retryable=False,
                    )
                if not chunks:
                    raise IngestionError(
                        "EMPTY_EXTRACTED_TEXT",
                        "No normalized chunks were extracted.",
                        retryable=False,
                    )
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError("CHUNKING_FAILED", str(exc), retryable=False) from exc
        observe("chunk")
        if stage:
            await stage(IngestionStage.EMBEDDING, 65)
        try:
            quota = self.quota
            if acquire_quota is not None:
                estimated = max(1, sum(len(embedding_text(chunk)) for chunk in chunks) // 4)
                try:
                    await acquire_quota(estimated)
                except QuotaDepletedError as exc:
                    raise IngestionError(
                        "EMBEDDING_QUOTA_WAIT",
                        f"Embedding quota depleted; retry after {exc.wait_seconds:.1f}s.",
                        retryable=True,
                    ) from exc
                except QuotaBackendUnavailableError as exc:
                    raise IngestionError(
                        "EMBEDDING_QUOTA_UNAVAILABLE",
                        "Quota coordinator unreachable; refusing blind provider call.",
                        retryable=True,
                    ) from exc
            elif (
                self.embedding_executor is None
                and quota is not None
                and runtime.quota_scope is not None
            ):
                estimated = max(1, sum(len(embedding_text(chunk)) for chunk in chunks) // 4)
                try:
                    await quota.acquire(scope=runtime.quota_scope, tokens=estimated)
                except QuotaDepletedError as exc:
                    raise IngestionError(
                        "EMBEDDING_QUOTA_WAIT",
                        f"Embedding quota depleted; retry after {exc.wait_seconds:.1f}s.",
                        retryable=True,
                    ) from exc
                except QuotaBackendUnavailableError as exc:
                    raise IngestionError(
                        "EMBEDDING_QUOTA_UNAVAILABLE",
                        "Quota coordinator unreachable; refusing blind provider call.",
                        retryable=True,
                    ) from exc
            if self.embedding_executor is not None:
                vectors = await self.embedding_executor(document, chunks, runtime)
            else:
                from raghub_core.domain.embedding.batching import split_batches

                vectors = []
                for start, end in split_batches(
                    [max(1, getattr(c, "token_count", 1)) for c in chunks],
                    max_chunks=24,
                    target_tokens=10000,
                ):
                    vectors.extend(
                        await runtime.provider.embed_documents(
                            [embedding_text(chunk) for chunk in chunks[start:end]]
                        )
                    )
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
        except IngestionError:
            raise
        except ProviderRateLimitError as exc:
            raise IngestionError("EMBEDDING_QUOTA_WAIT", str(exc), retryable=True) from exc
        except (ProviderTimeoutError, ProviderUnavailableError) as exc:
            raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=True) from exc
        except Exception as exc:
            raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=False) from exc
        observe("embed")
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
        observe("index")
        return index
