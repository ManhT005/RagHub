from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.infrastructure.ai.rerank_start import main


@pytest.mark.parametrize("invalid_snapshot", [False, True])
def test_api_serves_only_after_verified_model_load(monkeypatch, invalid_snapshot):
    import uvicorn

    from app.composition import retrieval
    from app.core import config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: SimpleNamespace(
            rag_reranker_enabled=True,
            rag_reranker_snapshot_path="/model",
            rag_reranker_expected_sha256="a" * 64,
            rag_reranker_timeout_seconds=10,
        ),
    )
    events = []

    def load():
        events.append("verified-load")
        if invalid_snapshot:
            raise RuntimeError("Snapshot mismatch")

    factory = Mock(return_value=SimpleNamespace(_load=load))
    monkeypatch.setattr(retrieval, "local_reranker", factory)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: events.append("serve"))
    if invalid_snapshot:
        with pytest.raises(RuntimeError, match="Snapshot mismatch"):
            main()
        assert events == ["verified-load"]
    else:
        main()
        assert events == ["verified-load", "serve"]
    factory.assert_called_once_with(
        snapshot_path="/model", expected_sha256="a" * 64, timeout_seconds=10
    )
