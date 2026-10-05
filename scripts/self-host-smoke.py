"""Exercise real local AI through the installed gateway; no direct database inserts."""

import argparse
import json
import secrets
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def compose(args, *command, input_text=None):
    files = ["infrastructure/docker-compose.self-host.yml", *args.compose_override]
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            args.env_file,
            "-p",
            args.project,
            *[item for file in files for item in ("-f", file)],
            "--profile",
            "local-ai",
            *command,
        ],
        cwd=ROOT,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Compose {command[0]} failed (exit {result.returncode}); inspect service logs."
        )
    return result.stdout


def step(message):
    print(message, flush=True)


def wait_ready(client, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if client.get("/health/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("Gateway readiness timed out")


def verify(client, state, owner):
    auth = client.post("/api/v1/auth/login", json=owner)
    assert auth.status_code == 200, "Owner login failed"
    headers = {
        "Authorization": f"Bearer {auth.json()['access_token']}",
        "X-Organization-ID": state["organization_id"],
    }
    workspace = f"/api/v1/workspaces/{state['workspace_id']}"
    search = client.get(
        workspace + "/search", headers=headers, params={"q": "recovery code"}
    )
    assert search.status_code == 200 and search.json()["hits"], "Retrieval failed"
    assert all(
        hit["document_id"] == state["document_id"] for hit in search.json()["hits"]
    )
    for path, request_headers in (
        (f"/api/v1/chatbots/{state['chatbot_id']}/chat", headers),
        (
            f"/api/v1/public/chatbots/{state['embed_key']}/chat",
            {"Origin": state["origin"]},
        ),
    ):
        response = client.post(
            path,
            headers=request_headers,
            json={"message": "What is the recovery code?", "external_user_id": "smoke"},
        )
        assert response.status_code == 200, "Chat request failed"
        events, name = [], ""
        for line in response.text.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            if line.startswith("data: "):
                events.append((name, json.loads(line[6:])))
        assert not any(name == "error" for name, _ in events), (
            "RAG returned an error event"
        )
        assert any(name == "done" for name, _ in events), "Chat did not complete"
        answer = "".join(data["text"] for name, data in events if name == "token")
        assert "729" in answer, "Local model did not answer from the recovery document"
        citations = next(
            data["citations"] for name, data in events if name == "citations"
        )
        assert citations and citations[0]["document_id"] == state["document_id"]
    public = f"/api/v1/public/chatbots/{state['embed_key']}"
    assert (
        client.get(public + "/config", headers={"Origin": state["origin"]}).status_code
        == 200
    )
    assert (
        client.get(
            public + "/config", headers={"Origin": "https://forbidden.example"}
        ).status_code
        == 403
    )
    assert (
        client.options(
            public + "/chat", headers={"Origin": state["origin"]}
        ).status_code
        == 204
    )
    assert client.get("/widget/raghub.js").status_code == 200
    assert client.get("/app/workspaces").status_code == 200
    step(
        "PASS: owner login, retrieval, local Playground/public SSE, citations, origin and widget"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--owner-file", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--compose-override", action="append", default=[])
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--ollama-model", default="gemma3:1b")
    args = parser.parse_args()
    owner = json.loads(Path(args.owner_file).read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.base_url, timeout=360) as client:
        wait_ready(client)
        if args.verify_only:
            verify(
                client,
                json.loads(Path(args.state_file).read_text(encoding="utf-8")),
                owner,
            )
            return
        step("Bootstrap installation owner through CLI")
        initial = json.loads(
            compose(
                args,
                "exec",
                "-T",
                "api",
                "python",
                "-m",
                "app.cli",
                "bootstrap-owner",
                "--stdin-json",
                input_text=json.dumps(owner),
            )
        )
        again = json.loads(
            compose(
                args,
                "exec",
                "-T",
                "api",
                "python",
                "-m",
                "app.cli",
                "bootstrap-owner",
                "--stdin-json",
                input_text=json.dumps({**owner, "password": secrets.token_urlsafe(24)}),
            )
        )
        assert again["result"] == "unchanged" and initial["user_id"] == again["user_id"]
        auth = client.post("/api/v1/auth/login", json=owner)
        assert auth.status_code == 200, (
            "Bootstrap changed the existing owner's password"
        )
        headers = {
            "Authorization": f"Bearer {auth.json()['access_token']}",
            "X-Organization-ID": initial["organization_id"],
        }

        def request(method, path, **kwargs):
            response = client.request(
                method, "/api/v1" + path, headers=headers, **kwargs
            )
            assert response.is_success, (
                f"{method} operation failed ({response.status_code})"
            )
            return response.json()

        workspace = request(
            "POST",
            "/workspaces",
            json={"name": "Local AI smoke", "slug": "smoke-" + uuid4().hex[:12]},
        )
        providers_path = f"/organizations/{initial['organization_id']}/providers"
        embedding = request(
            "POST",
            providers_path,
            json={
                "name": "Local ST smoke",
                "provider_type": "LOCAL_SENTENCE_TRANSFORMER",
                "capability": "EMBEDDING",
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "dimension": 384,
            },
        )
        chat = request(
            "POST",
            providers_path,
            json={
                "name": "Ollama smoke",
                "provider_type": "OLLAMA",
                "capability": "CHAT",
                "model": args.ollama_model,
                "base_url": "http://ollama:11434",
                "config_json": {
                    "read_timeout": 300.0,
                    "max_attempts": 1,
                    "options": {"num_predict": 80, "temperature": 0},
                },
            },
        )
        step("Download/load real Sentence Transformer and Ollama models")
        compose(args, "exec", "-T", "ollama", "ollama", "pull", args.ollama_model)
        for provider in (embedding, chat):
            result = request("POST", f"/providers/{provider['id']}/test")
            assert result["status"].lower() in {"ok", "success"}, (
                "Local provider check failed"
            )
        workspace_path = f"/workspaces/{workspace['id']}"
        request(
            "PATCH",
            workspace_path + "/providers",
            json={
                "embedding_provider_id": embedding["id"],
                "chat_provider_id": chat["id"],
            },
        )
        step("Upload document and wait for real worker ingestion")
        upload = request(
            "POST",
            workspace_path + "/documents",
            files={
                "file": (
                    "recovery.txt",
                    b"The RagHub installation recovery code is ORCHID-729. Use exactly this code for recovery.",
                    "text/plain",
                ),
            },
        )
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            document = next(
                item
                for item in request("GET", workspace_path + "/documents")
                if item["id"] == upload["document_id"]
            )
            assert document["status"] != "FAILED", (
                f"Ingestion failed: {document.get('error_code')}"
            )
            if document["status"] == "READY":
                break
            time.sleep(2)
        else:
            raise RuntimeError("Ingestion did not reach READY")
        bot = request(
            "POST",
            workspace_path + "/chatbots",
            json={
                "name": "Recovery",
                "system_prompt": "Answer briefly using only the provided document context. Include the exact recovery code.",
                "retrieval_limit": 3,
                "published": False,
            },
        )
        published = request(
            "POST",
            f"/chatbots/{bot['id']}/publish",
            json={"allowed_origins": ["https://smoke.example"]},
        )
        state = {
            "organization_id": initial["organization_id"],
            "workspace_id": workspace["id"],
            "document_id": upload["document_id"],
            "chatbot_id": bot["id"],
            "embed_key": published["key"],
            "origin": "https://smoke.example",
        }
        Path(args.state_file).write_text(json.dumps(state), encoding="utf-8")
        Path(args.state_file).chmod(0o600)
        verify(client, state, owner)
        if args.restart:
            step("Restart all persistent runtime services")
            compose(
                args,
                "restart",
                "postgres",
                "redis",
                "elasticsearch",
                "minio",
                "ollama",
                "api",
                "worker",
                "nginx",
            )
            wait_ready(client)
            verify(client, state, owner)
            step(
                "PASS: restart preserves owner, configuration, documents, index, model and embed key"
            )


if __name__ == "__main__":
    main()
