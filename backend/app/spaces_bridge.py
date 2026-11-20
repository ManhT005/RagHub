"""Optional OpenAI-compatible gateway for one explicitly configured Gradio Space."""

import asyncio
import hmac
import json
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
                "id": os.environ.get("SPACE_MODEL", "space-chat"),
                "object": "model",
                "owned_by": "spaces",
            }
        ],
    }


async def generate(prompt):
    base = os.environ.get("SPACE_URL", "").rstrip("/")
    api = os.environ.get("SPACE_API_NAME", "predict")
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
            json={"data": render(template, prompt)},
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
                        if not isinstance(output, str):
                            raise ValueError
                        return output
                    except (ValueError, IndexError, KeyError, TypeError) as exc:
                        raise HTTPException(502, "Expected a text Space output.") from exc
    raise HTTPException(502, "Space queue ended without a result.")


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
