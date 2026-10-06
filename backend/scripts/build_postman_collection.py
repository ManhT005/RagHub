"""Generate the Postman Collection v3 from the static OpenAPI artifact.

No Postman Cloud: the collection and the local example environment live in
the repo; CI regenerates into a temp dir and diffs. Variables are
placeholders only; runs inject real values via environment, and the run
never persists tokens.

Usage (from backend/):
    python scripts/build_postman_collection.py \\
        --openapi ../docs/api/openapi.json \\
        --out ../postman/collections/raghub-api.postman_collection.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COLLECTION_NAME = "RagHub API"

# Curated expectations for contract-critical routes.
EXPECTATIONS = {
    ("post", "/api/v1/workspaces/{workspace_id}/documents"): {
        "status": 202,
        "tests": [
            "pm.test('upload returns 202', () => pm.response.to.have.status(202));",
            "pm.test('upload receipt shape', () => { const j = pm.response.json();"
            " pm.expect(j).to.have.keys("
            "['document_id','document_version_id','job_id','status']); });",
        ],
    },
    ("get", "/api/v1/workspaces/{workspace_id}/search"): {
        "status": 200,
        "tests": [
            "pm.test('search returns 200', () => pm.response.to.have.status(200));",
            "pm.test('search shape', () => { const j = pm.response.json();"
            " pm.expect(j).to.have.keys(['query','hits','context']); });",
        ],
    },
    ("post", "/api/v1/chatbots/{chatbot_id}/chat"): {
        "status": 200,
        "tests": [
            "pm.test('chat streams SSE', () => pm.response.to.have.status(200));",
            "pm.test('SSE order conversation->citations->token->usage->done', () => {"
            " const t = pm.response.text(); const order = ["
            "'event: conversation','event: citations',"
            "'event: token','event: usage','event: done'];"
            " let last = -1; for (const e of order) { const i = t.indexOf(e);"
            " pm.expect(i).to.be.above(last, e); last = i; } });",
        ],
    },
    ("post", "/api/v1/public/chatbots/{embed_key}/chat"): {
        "status": 200,
        "tests": [
            "pm.test('public chat streams SSE', () => pm.response.to.have.status(200));",
        ],
    },
}


def _fill_path(path: str) -> str:
    replacements = {
        "{workspace_id}": "{{workspace_id}}",
        "{chatbot_id}": "{{chatbot_id}}",
        "{document_id}": "{{document_id}}",
        "{organization_id}": "{{organization_id}}",
        "{provider_id}": "{{provider_id}}",
        "{user_id}": "{{user_id}}",
        "{version_id}": "{{version_id}}",
        "{job_id}": "{{job_id}}",
        "{embed_key}": "{{embed_key}}",
    }
    for token, value in replacements.items():
        path = path.replace(token, value)
    return "{{base_url}}" + path


def _request_body(operation: dict) -> dict:
    content = (operation.get("requestBody") or {}).get("content", {})
    if "multipart/form-data" in content:
        return {"mode": "formdata", "formdata": [{"key": "file", "type": "file", "src": []}]}
    if "application/json" in content:
        schema = content["application/json"].get("schema", {})
        example = {k: f"{{{{{k}}}}}" for k in (schema.get("properties") or {})}
        return {"mode": "raw", "raw": json.dumps(example or {}, indent=2),
                "options": {"raw": {"language": "json"}}}
    return {}


def build(openapi: dict) -> dict:
    items = []
    for path in sorted(openapi.get("paths", {})):
        for method in sorted(openapi["paths"][path]):
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            operation = openapi["paths"][path][method] or {}
            key = (method, path)
            curated = EXPECTATIONS.get(key, {})
            query = []
            for param in operation.get("parameters", []):
                if param.get("in") == "query":
                    query.append({"key": param["name"], "value": f"{{{{{param['name']}}}}}"})
            if path.endswith("/search") and not any(p["key"] == "q" for p in query):
                query.append({"key": "q", "value": "{{search_query}}"})
                query.append({"key": "limit", "value": "5"})
            url = {"raw": _fill_path(path), "host": ["{{base_url}}"]}
            tests = list(curated.get("tests", [])) or [
                "pm.test('responds', () => pm.expect(pm.response.code).to.be.below(500));"
            ]
            items.append({
                "name": f"{method.upper()} {path}",
                "request": {
                    "method": method.upper(),
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{admin_token}}"},
                        {"key": "X-Organization-ID", "value": "{{organization_id}}"},
                        {"key": "Accept", "value": "application/json"},
                    ],
                    "url": {**url, "query": query},
                    "body": _request_body(operation),
                },
                "event": [{"listen": "test",
                           "script": {"type": "text/javascript",
                                      "exec": tests}}],
            })
    return {
        "info": {
            "name": COLLECTION_NAME,
            "_postman_id": "raghub-local-contract",
            "schema": "https://schema.getpostman.com/json/collection/v3/collection.json",
        },
        "variable": [
            {"key": "base_url", "value": "http://localhost:8000"},
            {"key": "search_query", "value": "tuyen sinh"},
        ],
        "item": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    openapi = json.loads(Path(args.openapi).read_text(encoding="utf-8"))
    collection = build(openapi)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"items={len(collection['item'])} -> {out}")


if __name__ == "__main__":
    main()
