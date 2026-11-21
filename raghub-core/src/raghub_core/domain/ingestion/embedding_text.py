"""Provider-neutral document embedding renderers, versioned with the index profile."""

from raghub_core.domain.ingestion.chunker import embedding_text

DOCUMENT_PIPELINES = {"legacy", "normalized-v1", "context-v1", "markdown-v2", "document-v2"}


def build_embedding_text(chunk, *, pipeline="normalized-v1"):
    if pipeline not in DOCUMENT_PIPELINES:
        raise ValueError("Unsupported document embedding pipeline.")
    body = embedding_text(chunk)
    if pipeline not in {"context-v1", "markdown-v2", "document-v2"}:
        return body
    if (
        pipeline in {"markdown-v2", "document-v2"}
        and chunk.metadata.get("document_pipeline") == pipeline
    ):
        return body  # Structured Markdown chunks already carry bounded context.
    metadata = [f"Source: {chunk.source_name}"]
    path = " > ".join(chunk.heading_path) or chunk.heading
    if path:
        metadata.append(f"Section: {path}")
    if chunk.page_number is not None:
        metadata.append(f"Page: {chunk.page_number}")
    return "\n".join(metadata) + "\n\n" + body
