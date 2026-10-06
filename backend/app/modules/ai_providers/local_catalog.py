"""Curated public repositories, pinned to revisions reviewed on 2026-10-05."""

from dataclasses import dataclass

from app.core.exceptions import AppError


@dataclass(frozen=True)
class LocalModelSpec:
    id: str
    repo: str
    revision: str
    dimension: int
    languages: str
    approximate_bytes: int
    max_bytes: int = 1_000_000_000


LOCAL_MODELS = (
    LocalModelSpec(
        "minilm-l6",
        "sentence-transformers/all-MiniLM-L6-v2",
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        384,
        "English",
        91_000_000,
    ),
    LocalModelSpec(
        "multilingual-minilm",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        384,
        "Multilingual",
        471_000_000,
    ),
    LocalModelSpec(
        "multilingual-e5-small",
        "intfloat/multilingual-e5-small",
        "614241f622f53c4eeff9890bdc4f31cfecc418b3",
        384,
        "Multilingual",
        471_000_000,
    ),
)
ALLOWED_FILES = frozenset(
    {
        "config.json",
        "config_sentence_transformers.json",
        "sentence_bert_config.json",
        "modules.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.txt",
        "sentencepiece.bpe.model",
        "model.safetensors",
        "1_Pooling/config.json",
        "2_Normalize/config.json",
    }
)


def local_spec(model_id):
    for spec in LOCAL_MODELS:
        if spec.id == model_id:
            return spec
    raise AppError(
        "LOCAL_MODEL_NOT_ALLOWED", "Choose a model from the local catalog.", status_code=422
    )
