import httpx
import pytest
from fastapi.testclient import TestClient

from app import spaces_bridge


@pytest.mark.parametrize("input_type,task", [("query", "query"), ("passage", "document")])
def test_sict_embedding_routing(monkeypatch, input_type, task):
    monkeypatch.setenv("SPACES_BRIDGE_KEY", "test-key")
    monkeypatch.setenv("SPACE_MODEL", "jinaai/jina-clip-v2")
    monkeypatch.setenv("SPACE_EMBEDDING_DIMENSION", "32")

    async def generate(prompt, **kwargs):
        assert kwargs == {
            "api": "embed_batch_text",
            "data": [["hello"], task, 32],
            "structured": True,
        }
        return {"status": "success", "embeddings": [[0.1] * 32]}

    monkeypatch.setattr(spaces_bridge, "generate", generate)
    with TestClient(spaces_bridge.app) as client:
        response = client.post(
            "/v1/embeddings",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "jinaai/jina-clip-v2", "input": ["hello"], "input_type": input_type},
        )
    assert response.status_code == 200
    assert len(response.json()["data"][0]["embedding"]) == 32


def test_embedding_requires_query_document_semantics(monkeypatch):
    monkeypatch.setenv("SPACES_BRIDGE_KEY", "test-key")
    with TestClient(spaces_bridge.app) as client:
        response = client.post(
            "/v1/embeddings",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "space-chat", "input": "hello"},
        )
    assert response.status_code == 422


def test_sict_rejects_wrong_dimension(monkeypatch):
    monkeypatch.setenv("SPACES_BRIDGE_KEY", "test-key")

    async def generate(*args, **kwargs):
        return {"status": "success", "embeddings": [[0.1, 0.2]]}

    monkeypatch.setattr(spaces_bridge, "generate", generate)
    with TestClient(spaces_bridge.app) as client:
        response = client.post(
            "/v1/embeddings",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "space-chat", "input": "hello", "input_type": "query"},
        )
    assert response.status_code == 502


def test_space_template_keeps_prompt_as_data():
    prompt = 'Vietnamese text: "quoted" $prompt'
    assert spaces_bridge.render(["$prompt", [], {"temperature": 0.3}], prompt) == [
        prompt,
        [],
        {"temperature": 0.3},
    ]


def test_bridge_auth_and_model(monkeypatch):
    monkeypatch.setenv("SPACES_BRIDGE_KEY", "test-key")
    with TestClient(spaces_bridge.app) as client:
        assert client.get("/v1/models").status_code == 401
        assert (
            client.get("/v1/models", headers={"Authorization": "Bearer test-key"}).status_code
            == 200
        )


@pytest.mark.asyncio
async def test_queue_protocol(monkeypatch):
    monkeypatch.setenv("SPACE_URL", "https://test-space.hf.space")
    monkeypatch.setenv("HF_TOKEN", "private-token")
    real_client = httpx.AsyncClient
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer private-token"
        if request.method == "POST":
            return httpx.Response(200, json={"event_id": "abc"})
        return httpx.Response(200, text='event: complete\ndata: ["answer"]\n\n')

    monkeypatch.setattr(
        spaces_bridge.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    assert await spaces_bridge.generate("question") == "answer"
    assert str(calls[1].url).endswith("/gradio_api/call/predict/abc")
