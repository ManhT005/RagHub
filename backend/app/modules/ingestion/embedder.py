import math

from app.modules.ingestion.chunker import TextChunk
from app.modules.ingestion.tokenizer import ENCODING

DIMENSIONS = 384
_ENCODING = ENCODING


def _embed_text(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for token in _ENCODING.encode(text):
        vector[token % DIMENSIONS] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def embed_texts(texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    """Embed texts in bounded batches behind the future provider boundary."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(_embed_text(text) for text in texts[start : start + batch_size])
    return vectors


def embed_chunks(chunks: list[TextChunk], *, batch_size: int = 32) -> dict[str, list[float]]:
    """Development stub: token hashing vectors, pending a semantic retrieval provider."""
    vectors = embed_texts([chunk.content for chunk in chunks], batch_size=batch_size)
    return {str(chunk.chunk_id): vector for chunk, vector in zip(chunks, vectors, strict=True)}
