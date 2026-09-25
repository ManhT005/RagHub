from app.modules.ingestion.chunker import TextChunk


def embed_chunks(chunks: list[TextChunk], *, batch_size: int = 32) -> dict[str, list[float]]:
    """Removed compatibility entry point; production embedding requires a configured provider."""
    raise RuntimeError("Use EmbeddingProvider.embed_documents through ProviderResolver")
