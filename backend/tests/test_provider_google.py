from types import SimpleNamespace

from app.infrastructure.provider_credentials import resolve_provider_secret
from app.modules.ai_providers.adapters.google_gemini import (
    GoogleGeminiChatProvider,
    GoogleGeminiEmbeddingProvider,
)


def test_gemini_never_uses_a_global_key_when_connection_has_no_private_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "system-key")
    config = SimpleNamespace(provider_type="GOOGLE_GEMINI", encrypted_secret=None)
    assert resolve_provider_secret(config, None) is None


def test_gemini_adapters_expose_normalized_provider_identity() -> None:
    chat = GoogleGeminiChatProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-chat",
        secret="secret",
    )
    embedding = GoogleGeminiEmbeddingProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-embedding",
        dimension=768,
        secret="secret",
    )

    assert chat.provider_name == "GOOGLE_GEMINI"
    assert embedding.metadata.provider_name == "GOOGLE_GEMINI"
    assert embedding.metadata.dimension == 768


async def test_embedding_2_uses_native_per_chunk_requests_without_task_type(monkeypatch):
    import json
    import httpx

    captured = []

    def handle(request):
        captured.append(request)
        return httpx.Response(200, json={"embedding": {"values": [1.0, 2.0]}})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_type(**{**kwargs, "transport": httpx.MockTransport(handle)}),
    )
    provider = GoogleGeminiEmbeddingProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-embedding-2",
        dimension=2,
        secret="connection-key",
    )
    assert await provider.embed_documents(["first", "second"]) == [[1.0, 2.0], [1.0, 2.0]]
    assert len(captured) == 2
    for request in captured:
        body = json.loads(request.content)
        assert "taskType" not in body and "task_type" not in body
        assert body["outputDimensionality"] == 2
        assert len(body["content"]["parts"]) == 1
        assert request.headers["x-goog-api-key"] == "connection-key"
        assert "authorization" not in request.headers
        assert request.url.path.endswith("/models/gemini-embedding-2:embedContent")
