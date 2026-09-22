import math

from app.modules.ingestion.chunker import TextChunk
from app.modules.ingestion.tokenizer import ENCODING

DIMENSIONS = 384
_ENCODING = ENCODING


def embed_chunks(chunks: list[TextChunk]) -> dict[str, list[float]]:
    """Deterministic local token hashing vectors; replaceable by a model later."""
    vectors: dict[str, list[float]] = {}
    for chunk in chunks:
        vector = [0.0] * DIMENSIONS
        for token in _ENCODING.encode(chunk.content):
            vector[token % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        vectors[str(chunk.chunk_id)] = vector
    return vectors
