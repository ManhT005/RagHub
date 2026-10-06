"""Provider-neutral document embedding renderers, versioned with the index profile."""

from raghub_core.domain.ingestion.chunker import embedding_text

DOCUMENT_PIPELINES = {"legacy", "normalized-v1", "context-v1"}


def build_embedding_text(chunk, *, pipeline="normalized-v1"):
    if pipeline not in DOCUMENT_PIPELINES:
        raise ValueError("Unsupported document embedding pipeline.")
    body = embedding_text(chunk)
    if pipeline != "context-v1":
        return body
    metadata = [f"Source: {chunk.source_name}"]
    path = " > ".join(chunk.heading_path) or chunk.heading
    if path:
        metadata.append(f"Section: {path}")
    if chunk.page_number is not None:
        metadata.append(f"Page: {chunk.page_number}")
    return "\n".join(metadata) + "\n\n" + body
