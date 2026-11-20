"""Optional OpenAI-compatible gateway for one explicitly configured Gradio Space."""

import asyncio
import hmac
import json
import math
import os
import re
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="RagHub Spaces bridge")


def render(value, prompt):
    if value == "$prompt":
        return prompt
    if isinstance(value, list):
        return [render(item, prompt) for item in value]
    if isinstance(value, dict):
        return {key: render(item, prompt) for key, item in value.items()}
    return value


def authorize(request):
    key = os.environ.get("SPACES_BRIDGE_KEY", "")
    if not key:
        raise HTTPException(503, "Configure SPACES_BRIDGE_KEY before use.")
    if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {key}"):
        raise HTTPException(401, "Invalid bridge credential.")


@app.get("/v1/models")
async def models(request: Request):
    authorize(request)
    return {
        "object": "list",
        "data": [
            {
                "id": bridge_model(),
                "object": "model",
                "owned_by": "spaces",
            }
        ],
    }


def bridge_model():
    return os.environ.get("SPACE_MODEL", "space-chat")


async def generate(prompt, *, api=None, data=None, structured=False):
    base = os.environ.get("SPACE_URL", "").rstrip("/")
    api = api or os.environ.get("SPACE_API_NAME", "predict")
    if not re.fullmatch(r"https://[a-zA-Z0-9-]+\.hf\.space", base):
        raise HTTPException(503, "SPACE_URL must be an HTTPS hf.space origin.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", api):
        raise HTTPException(503, "Invalid SPACE_API_NAME.")
    try:
        template = json.loads(os.environ.get("SPACE_INPUT_TEMPLATE", '["$prompt"]'))
        if not isinstance(template, list):
            raise ValueError
        output_index = int(os.environ.get("SPACE_OUTPUT_INDEX", "0"))
    except ValueError as exc:
        raise HTTPException(503, "Invalid Space input/output configuration.") from exc
    token = os.environ.get("HF_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
        response = await client.post(
            f"{base}/gradio_api/call/{api}",
            headers=headers,
            json={"data": data if data is not None else render(template, prompt)},
        )
        if response.status_code != 200:
            raise HTTPException(502, f"Space submission failed (HTTP {response.status_code}).")
        event_id = response.json().get("event_id", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", event_id):
            raise HTTPException(502, "Space returned an invalid event ID.")
        async with client.stream(
            "GET",
            f"{base}/gradio_api/call/{api}/{event_id}",
            headers=headers,
        ) as result:
            if result.status_code != 200:
                raise HTTPException(502, f"Space queue failed (HTTP {result.status_code}).")
            event = ""
            async for line in result.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event == "error":
                    raise HTTPException(
                        502, "Space generation failed; check GPU quota and Space logs."
                    )
                elif line.startswith("data:") and event == "complete":
                    try:
                        output = json.loads(line[5:])[output_index]
                        if not structured and not isinstance(output, str):
                            raise ValueError
                        return output
                    except (ValueError, IndexError, KeyError, TypeError) as exc:
                        raise HTTPException(502, "Expected a text Space output.") from exc
    raise HTTPException(502, "Space queue ended without a result.")


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    authorize(request)
    payload = await request.json()
    if not isinstance(payload, dict) or payload.get("model") != bridge_model():
        raise HTTPException(404, "Unknown bridge model.")
    texts = payload.get("input")
    texts = [texts] if isinstance(texts, str) else texts
    if (
        not isinstance(texts, list)
        or not 1 <= len(texts) <= 32
        or any(not isinstance(text, str) or not text.strip() or len(text) > 8192 for text in texts)
    ):
        raise HTTPException(
            422, "Expected 1–32 nonempty text strings, at most 8192 characters each."
        )
    task = payload.get("input_type")
    if task not in {"query", "passage", "document"}:
        raise HTTPException(
            422, "input_type=query or passage is required to preserve retrieval semantics."
        )
    try:
        dimension = int(os.environ.get("SPACE_EMBEDDING_DIMENSION", "1024"))
    except ValueError as exc:
        raise HTTPException(503, "Invalid configured embedding dimension.") from exc
    if dimension not in {32, 64, 128, 256, 512, 768, 1024}:
        raise HTTPException(503, "Unsupported SICT dimension.")
    if payload.get("dimensions", dimension) != dimension:
        raise HTTPException(422, "Requested dimension differs from registered bridge dimension.")
    if payload.get("encoding_format", "float") != "float":
        raise HTTPException(422, "Only float vectors are supported.")
    try:
        async with asyncio.timeout(180):
            result = await generate(
                "",
                api="embed_batch_text",
                data=[texts, "query" if task == "query" else "document", dimension],
                structured=True,
            )
        if not isinstance(result, dict) or result.get("status") != "success":
            raise ValueError("Space returned an error.")
        from app.modules.ai_providers.adapters.http import validate_vectors

        vectors = validate_vectors(result.get("embeddings"), len(texts), dimension)
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("Nonfinite vector.")
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(504, "Embedding Space timed out.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Space returned invalid embeddings or is unavailable.") from exc
    return {
        "object": "list",
        "model": bridge_model(),
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.post("/v1/chat/completions")
async def chat(request: Request):
    authorize(request)
    payload = await request.json()
    model = os.environ.get("SPACE_MODEL", "space-chat")
    if payload.get("model") != model:
        raise HTTPException(404, "Unknown bridge model.")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(422, "messages must be a nonempty list.")
    parts = []
    for message in messages:
        if (
            not isinstance(message, dict)
            or message.get("role") not in {"system", "user", "assistant"}
            or not isinstance(message.get("content"), str)
        ):
            raise HTTPException(422, "Only text system/user/assistant messages are supported.")
        parts.append(f"{message['role']}: {message['content']}")
    prompt = "\n\n".join(parts) + "\n\nassistant:"
    if len(prompt) > 100_000:
        raise HTTPException(413, "Prompt exceeds bridge limit.")
    try:
        async with asyncio.timeout(180):
            text = await generate(prompt)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(504, "Space queue/generation timed out.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Invalid or unavailable Space response.") from exc
    identifier = f"chatcmpl-{uuid.uuid4().hex}"
    common = {"id": identifier, "created": int(time.time()), "model": model}
    if payload.get("stream"):

        async def stream():
            for delta, finish in (({"role": "assistant", "content": text}, None), ({}, "stop")):
                chunk = {
                    **common,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")
    return {
        **common,
        "object": "chat.completion",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
    }
