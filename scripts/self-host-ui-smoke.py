"""Exercise the v1 UI contracts using real local AI in an isolated test organization.

Credentials are read/written only through ignored local files; never print them.
--queue-outage briefly stops Redis in the explicitly selected *test* project,
restores it in finally, and proves that failed enqueue preserves the active index.
"""

import argparse
import json
import secrets
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"COMPLETED", "FAILED", "QUEUE_FAILED", "SUPERSEDED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:18082")
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--project")
    parser.add_argument("--queue-outage", action="store_true")
    args = parser.parse_args()
    if args.queue_outage and (
        not args.env_file or not args.project or "test" not in args.project
    ):
        parser.error("Queue outage requires an explicit test project and env file")

    def compose(*command):
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                args.env_file,
                "-p",
                args.project,
                "-f",
                "infrastructure/docker-compose.self-host.yml",
                "-f",
                "infrastructure/docker-compose.self-host.build.yml",
                "--profile",
                "local-ai",
                *command,
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"Compose {command[0]} failed"

    owner = json.loads(args.owner_file.read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.base_url, timeout=300) as client:
        response = client.post("/api/v1/auth/login", json=owner)
        assert response.status_code == 200, "Owner login failed"
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        def request(method, path, *, expected=None, delegated=False, **kwargs):
            result = client.request(
                method,
                "/api/v1" + path,
                headers=member_headers if delegated else headers,
                **kwargs,
            )
            if expected is not None:
                assert result.status_code == expected, (
                    f"{method} {path}: {result.status_code}"
                )
            else:
                assert result.is_success, f"{method} {path}: {result.status_code}"
            return result.json() if result.content else None

        org = request(
            "POST",
            "/organizations",
            json={"name": "Self-host UI acceptance", "slug": "ui-" + uuid4().hex[:12]},
        )
        org_id = org["id"]
        headers["X-Organization-ID"] = org_id
        workspace = request(
            "POST",
            "/workspaces",
            json={"name": "UI knowledge workspace", "slug": "ui-knowledge"},
        )
        workspace_id = workspace["id"]
        path = f"/workspaces/{workspace_id}"
        other = request(
            "POST",
            "/workspaces",
            json={"name": "Unassigned workspace", "slug": "unassigned"},
        )
        catalog = request("GET", "/ai/provider-catalog")
        assert (
            next(item for item in catalog if item["id"] == "anthropic")["status"]
            == "COMING_SOON"
        )
        print(
            "Verify connection credentials stay private and unsupported models stay unselectable",
            flush=True,
        )
        sentinel = secrets.token_urlsafe(24)
        secret_connection = request(
            "POST",
            f"/organizations/{org_id}/provider-connections",
            json={
                "name": "Credential contract probe",
                "provider_type": "OPENAI_COMPATIBLE",
                "catalog_id": "openai",
                "base_url": "https://api.openai.com/v1",
                "secret": sentinel,
            },
        )
        assert secret_connection["has_secret"] and sentinel not in json.dumps(
            secret_connection
        )
        assert sentinel not in json.dumps(
            request("GET", f"/organizations/{org_id}/provider-connections")
        )
        request("DELETE", f"/provider-connections/{secret_connection['id']}")

        def embedding_connection(name, dimension=None):
            connection = request(
                "POST",
                f"/organizations/{org_id}/provider-connections",
                json={
                    "name": name,
                    "provider_type": "LOCAL_SENTENCE_TRANSFORMER",
                    "catalog_id": "sentence-transformer",
                },
            )
            checked = request("POST", f"/provider-connections/{connection['id']}/test")
            assert checked["discovery_supported"] is False
            payload = {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "capability": "EMBEDDING",
            }
            if dimension is not None:
                payload["dimension"] = dimension
                mismatch = request(
                    "POST",
                    f"/provider-connections/{connection['id']}/models",
                    expected=422,
                    json={**payload, "dimension": 768},
                )
                assert mismatch["error"]["code"] == "MODEL_DIMENSION_MISMATCH"
            model = request(
                "POST", f"/provider-connections/{connection['id']}/models", json=payload
            )
            assert (
                model["availability_status"] == "AVAILABLE"
                and model["dimension"] == 384
            )
            return connection, model

        print(
            "Register a real Sentence Transformer model and bind the workspace",
            flush=True,
        )
        connection, model = embedding_connection("Local embedding A", 384)
        binding = request(
            "PUT", path + "/embedding-model", json={"model_id": model["id"]}
        )
        active_before = binding["active_embedding_index_version_id"]
        assert active_before and binding["reindex_job_id"] is None
        invalid = request(
            "POST",
            f"/provider-connections/{connection['id']}/models",
            expected=409,
            json={
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "capability": "EMBEDDING",
                "dimension": 768,
            },
        )
        # Duplicate IDs are rejected before the runtime dimension probe.
        assert invalid["error"]["code"] in {
            "MODEL_ALREADY_REGISTERED",
            "MODEL_DIMENSION_MISMATCH",
        }
        print(
            "Upload, index, read aggregate metadata, download and retrieve the document",
            flush=True,
        )
        content = b"The RagHub UI acceptance recovery code is ORCHID-729. Use exactly this code for recovery."
        uploaded = request(
            "POST",
            path + "/documents",
            files={"file": ("recovery.txt", content, "text/plain")},
        )
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            document = next(
                item
                for item in request("GET", path + "/documents")
                if item["id"] == uploaded["document_id"]
            )
            assert document["status"] != "FAILED", "Real local ingestion failed"
            if document["status"] == "READY":
                break
            time.sleep(2)
        else:
            raise AssertionError("Ingestion timed out")
        assert document["chunk_count"] > 0 and document["indexed_at"]
        detail = request("GET", path + f"/documents/{document['id']}")
        assert detail["embedding_dimension"] == 384 and "storage_key" not in detail
        download = client.get(
            "/api/v1" + path + f"/documents/{document['id']}/download", headers=headers
        )
        assert download.status_code == 200 and download.content == content
        summary = request("GET", path)
        assert (
            summary["document_count"] == 1
            and summary["chunk_count"] == document["chunk_count"]
        )

        def retrieved():
            hits = request("GET", path + "/search", params={"q": "recovery code"})[
                "hits"
            ]
            assert hits and hits[0]["document_id"] == document["id"], (
                "Active retrieval was lost"
            )

        retrieved()
        print(
            "Verify delegated direct API requests, assignment scope and normalized dependencies",
            flush=True,
        )
        member_credentials = {
            "email": "ui-member-" + uuid4().hex[:12] + "@example.com",
            "password": secrets.token_urlsafe(24),
        }
        member = request("POST", "/admin/users", json=member_credentials)
        request(
            "POST",
            path + "/members",
            json={"user_id": member["id"], "permissions": ["document.view"]},
        )
        auth = client.post("/api/v1/auth/login", json=member_credentials)
        assert auth.status_code == 200
        member_headers = {
            "Authorization": f"Bearer {auth.json()['access_token']}",
            "X-Organization-ID": org_id,
        }
        assert [
            item["id"] for item in request("GET", "/workspaces", delegated=True)
        ] == [workspace_id]
        request("GET", path + "/documents", delegated=True)
        request("GET", path + f"/documents/{document['id']}", delegated=True)
        for method, url, body in (
            ("GET", f"/workspaces/{other['id']}/documents", None),
            ("GET", f"/organizations/{org_id}/provider-connections", None),
            ("GET", f"/organizations/{org_id}/models", None),
            ("PUT", path + "/embedding-model", {"model_id": model["id"]}),
            ("PUT", path + "/chat-model", {"model_id": model["id"]}),
            ("DELETE", path + f"/documents/{document['id']}", None),
            (
                "POST",
                path + "/members",
                {"user_id": member["id"], "permissions": ["system.admin"]},
            ),
        ):
            request(method, url, expected=403, delegated=True, json=body)
        request(
            "POST",
            path + "/documents",
            expected=403,
            delegated=True,
            files={"file": ("blocked.txt", b"blocked", "text/plain")},
        )
        grants = request(
            "PATCH",
            path + f"/members/{member['id']}",
            json={"permissions": ["ai.change_embedding", "document.upload"]},
        )
        assert {"workspace.view", "ai.view", "document.view"}.issubset(
            grants["permissions"]
        )
        request("GET", path + "/models", delegated=True)
        request("GET", f"/organizations/{org_id}/models", expected=403, delegated=True)
        request(
            "PATCH",
            path + f"/members/{member['id']}",
            json={"permissions": ["document.view"]},
        )

        print(
            "Preview and execute a real full reindex; verify active index survives queue failure",
            flush=True,
        )
        target_connection, target = embedding_connection("Local embedding B")
        impact = request(
            "POST", path + "/embedding-model/preview", json={"model_id": target["id"]}
        )
        assert (
            impact["requires_reindex"]
            and impact["documents_affected"] == 1
            and impact["chunks_affected"] > 0
        )
        if args.queue_outage:
            compose("stop", "redis")
            try:
                changed = request(
                    "PUT", path + "/embedding-model", json={"model_id": target["id"]}
                )
                assert changed["active_embedding_index_version_id"] == active_before
                job_id = changed["reindex_job_id"]
                job = request("GET", path + f"/embedding-reindex-jobs/{job_id}")
                assert job["status"] == "QUEUE_FAILED", (
                    "Enqueue failure was not recorded"
                )
                assert request("GET", path)["embedding_model"]["id"] == model["id"]
                retrieved()
            finally:
                compose("start", "redis")
                compose("restart", "worker")
            request("POST", f"/embedding-reindex-jobs/{job_id}/retry")
        else:
            changed = request(
                "PUT", path + "/embedding-model", json={"model_id": target["id"]}
            )
            job_id = changed["reindex_job_id"]
        assert job_id
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            job = request("GET", path + f"/embedding-reindex-jobs/{job_id}")
            if job["status"] in TERMINAL:
                break
            time.sleep(2)
        assert job["status"] == "COMPLETED", f"Reindex ended with {job['status']}"
        final = request("GET", path)
        assert (
            final["embedding_model"]["id"] == target["id"] and final["chunk_count"] > 0
        )
        assert final["reindex_job_id"] is None
        retrieved()
        request(
            "PATCH", f"/models/{target['id']}", expected=409, json={"enabled": False}
        )
        request(
            "PATCH",
            f"/provider-connections/{target_connection['id']}",
            expected=409,
            json={"enabled": False},
        )

        print("Discover and register a real Ollama chat model", flush=True)
        chat_connection = request(
            "POST",
            f"/organizations/{org_id}/provider-connections",
            json={
                "name": "Local Ollama",
                "provider_type": "OLLAMA",
                "base_url": "http://ollama:11434",
                "config_json": {
                    "read_timeout": 300.0,
                    "max_attempts": 1,
                    "options": {"num_predict": 80, "temperature": 0},
                },
            },
        )
        tested = request("POST", f"/provider-connections/{chat_connection['id']}/test")
        assert tested["status"] == "CONNECTED"
        discovered = request(
            "POST", f"/provider-connections/{chat_connection['id']}/models/discover"
        )
        if (
            not any(item["model"] == "gemma3:1b" for item in discovered)
            and args.project
        ):
            compose("exec", "-T", "ollama", "ollama", "pull", "gemma3:1b")
            discovered = request(
                "POST", f"/provider-connections/{chat_connection['id']}/models/discover"
            )
        assert any(item["model"] == "gemma3:1b" for item in discovered)
        chat = request(
            "POST",
            f"/provider-connections/{chat_connection['id']}/models",
            json={"model": "gemma3:1b", "capability": "CHAT"},
        )
        request("PUT", path + "/chat-model", json={"model_id": chat["id"]})
        bot = request(
            "POST",
            path + "/chatbots",
            json={
                "name": "UI Recovery",
                "system_prompt": "Answer briefly using only the document context. Include the exact recovery code.",
                "retrieval_limit": 3,
                "published": False,
            },
        )
        published = request(
            "POST",
            f"/chatbots/{bot['id']}/publish",
            json={"allowed_origins": ["https://ui-smoke.example"]},
        )
        for chat_path, chat_headers in (
            (f"/chatbots/{bot['id']}/chat", headers),
            (
                f"/public/chatbots/{published['key']}/chat",
                {"Origin": "https://ui-smoke.example"},
            ),
        ):
            result = client.post(
                "/api/v1" + chat_path,
                headers=chat_headers,
                json={"message": "What is the recovery code?"},
            )
            assert result.status_code == 200 and "event: error" not in result.text
            assert (
                "event: done" in result.text
                and "729" in result.text
                and document["id"] in result.text
            )
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        args.state_file.write_text(
            json.dumps(
                {
                    "organization_id": org_id,
                    "workspace_id": workspace_id,
                    "document_id": document["id"],
                    "chatbot_id": bot["id"],
                    "member": member_credentials,
                    "model_id": target["id"],
                    "connection_id": target_connection["id"],
                }
            ),
            encoding="utf-8",
        )
        print(
            "PASS: connection -> registry -> workspace -> permissions -> document -> reindex -> private/public chat",
            flush=True,
        )


if __name__ == "__main__":
    main()
