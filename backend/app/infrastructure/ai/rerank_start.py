"""Validate and warm local reranking before exposing API readiness."""


def main():
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.rag_reranker_enabled:
        raise RuntimeError("Reranking startup requires RAG_RERANKER_ENABLED=true.")
    from app.composition.retrieval import local_reranker

    adapter = local_reranker(
        snapshot_path=settings.rag_reranker_snapshot_path,
        expected_sha256=settings.rag_reranker_expected_sha256,
        timeout_seconds=settings.rag_reranker_timeout_seconds,
    )
    adapter._load()
    # Same process/cache is reused by retrieval; first query does not load weights.
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
