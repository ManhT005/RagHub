"""Live extraction regression: change embedding snapshot and rebuild existing documents."""

import json
import os
import time
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.integration


def wait_for(read, complete, *, seconds=90):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        last = read()
        if complete(last):
            return last
        time.sleep(0.5)
    pytest.fail(f"Timed out waiting for ingestion/reindex: {last}")


def test_embedding_rebuild_switches_snapshot_and_keeps_existing_document_searchable():
    base_url = os.getenv("RAGHUB_TEST_BASE_URL")
    if not base_url:
        pytest.skip("Set RAGHUB_TEST_BASE_URL to run the live integration test.")
    unique = uuid4().hex[:12]
    with httpx.Client(base_url=base_url, timeout=20) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            assert response.is_success, response.text
            return response.json()

        auth = request(
            "POST",
            "/api/v1/auth/register",
            json={
                "email": f"core-reindex-{unique}@example.com",
                "password": "integration-password-123",
            },
        )
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        organization = request(
            "POST",
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Core rebuild", "slug": f"core-rebuild-{unique}"},
        )
        headers["X-Organization-ID"] = organization["id"]
        workspace = request(
            "POST", "/api/v1/workspaces", headers=headers, json={"name": "Core", "slug": "core"}
        )
        workspace_path = f"/api/v1/workspaces/{workspace['id']}"

        def provider(dimension):
            return request(
                "POST",
                f"/api/v1/organizations/{organization['id']}/providers",
                headers=headers,
                json={
                    "name": f"Test {dimension}",
                    "provider_type": "LOCAL_TOKEN_HASH",
                    "capability": "EMBEDDING",
                    "model": f"hash-{dimension}",
                    "dimension": dimension,
                },
            )

        first = provider(384)
        binding = request(
            "PATCH",
            workspace_path + "/providers",
            headers=headers,
            json={"embedding_provider_id": first["id"]},
        )
        previous_index = binding["active_embedding_index_version_id"]
        accepted = request(
            "POST",
            workspace_path + "/documents",
            headers=headers,
            files={
                "file": ("guide.md", b"# Core\n\nRebuild preserves knowledge.", "text/markdown")
            },
        )

        def document():
            listing = request("GET", workspace_path + "/documents", headers=headers)
            return next(item for item in listing if item["id"] == accepted["document_id"])

        initial = wait_for(document, lambda item: item["status"] in {"READY", "FAILED"})
        assert initial["status"] == "READY", initial
        replacement = provider(128)
        changed = request(
            "PATCH",
            workspace_path + "/providers",
            headers=headers,
            json={"embedding_provider_id": replacement["id"]},
        )
        assert changed["active_embedding_index_version_id"] == previous_index
        assert changed["reindex_job_id"]
        job_path = workspace_path + f"/embedding-reindex-jobs/{changed['reindex_job_id']}"
        job = wait_for(
            lambda: request("GET", job_path, headers=headers),
            lambda item: item["status"] in {"COMPLETED", "FAILED", "SUPERSEDED"},
        )
        assert job["status"] == "COMPLETED", job
        assert job["processed_documents"] == job["total_documents"] == 1
        assert job["failed_documents"] == 0
        active = request(
            "PATCH",
            workspace_path + "/providers",
            headers=headers,
            json={"embedding_provider_id": replacement["id"]},
        )
        assert active["active_embedding_index_version_id"] == job["target_index_version_id"]
        assert active["active_embedding_index_version_id"] != previous_index
        assert active["reindex_job_id"] is None
        search = request(
            "GET",
            workspace_path + "/search",
            headers=headers,
            params={"q": "Rebuild preserves knowledge"},
        )
        assert any(hit["document_id"] == accepted["document_id"] for hit in search["hits"])
        assert document()["document_version_id"] == accepted["document_version_id"]


def test_authenticated_chatbot_management_and_empty_context_without_chat_provider():
    base_url = os.getenv("RAGHUB_TEST_BASE_URL")
    if not base_url:
        pytest.skip("Set RAGHUB_TEST_BASE_URL to run the live integration test.")
    unique = uuid4().hex[:12]
    with httpx.Client(base_url=base_url, timeout=20) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            assert response.is_success, response.text
            return response.json()

        auth = request(
            "POST",
            "/api/v1/auth/register",
            json={
                "email": f"core-chat-{unique}@example.com",
                "password": "integration-password-123",
            },
        )
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        organization = request(
            "POST",
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Core chat", "slug": f"core-chat-{unique}"},
        )
        headers["X-Organization-ID"] = organization["id"]
        workspace = request(
            "POST", "/api/v1/workspaces", headers=headers, json={"name": "Core", "slug": "core"}
        )
        workspace_path = f"/api/v1/workspaces/{workspace['id']}"
        provider = request(
            "POST",
            f"/api/v1/organizations/{organization['id']}/providers",
            headers=headers,
            json={
                "name": "Local embedding",
                "provider_type": "LOCAL_TOKEN_HASH",
                "capability": "EMBEDDING",
                "model": "hash",
                "dimension": 128,
            },
        )
        request(
            "PATCH",
            workspace_path + "/providers",
            headers=headers,
            json={"embedding_provider_id": provider["id"]},
        )
        chatbot = request(
            "POST",
            workspace_path + "/chatbots",
            headers=headers,
            json={"name": " Bot ", "system_prompt": " Prompt ", "published": True},
        )
        chatbot_path = f"/api/v1/chatbots/{chatbot['id']}"
        assert chatbot["name"] == "Bot" and chatbot["system_prompt"] == "Prompt"
        assert request("GET", chatbot_path, headers=headers)["id"] == chatbot["id"]
        updated = request(
            "PATCH", chatbot_path, headers=headers, json={"name": "Renamed", "retrieval_limit": 3}
        )
        assert (
            updated["name"] == "Renamed"
            and updated["published"]
            and updated["retrieval_limit"] == 3
        )
        response = client.post(
            chatbot_path + "/chat", headers=headers, json={"message": "question"}
        )
        assert response.status_code == 200, response.text
        events = [
            line.removeprefix("event: ")
            for line in response.text.splitlines()
            if line.startswith("event: ")
        ]
        assert events == ["conversation", "citations", "token", "usage", "done"], response.text
        data = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert data[1] == {"citations": []}
        assert data[3]["source"] == "none" and data[3]["total_tokens"] == 0
        assert data[4]["first_token_ms"] is None and data[4]["latency_ms"] == 0
        deleted = client.delete(chatbot_path, headers=headers)
        assert deleted.status_code == 204
        assert client.get(chatbot_path, headers=headers).status_code == 404
