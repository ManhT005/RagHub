import httpx
import pytest
from fastapi.testclient import TestClient

from app import spaces_bridge


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
