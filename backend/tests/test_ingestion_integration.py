"""End-to-end ingestion test; run with RAGHUB_TEST_BASE_URL=http://localhost:8000."""

import os
import time
import uuid

import httpx
import pymupdf
import pytest


@pytest.mark.integration
def test_upload_to_search_and_tenant_scope() -> None:
    base_url = os.getenv("RAGHUB_TEST_BASE_URL")
    if not base_url:
        pytest.skip("Set RAGHUB_TEST_BASE_URL to run the live integration test.")
    unique = uuid.uuid4().hex[:12]
    with httpx.Client(base_url=base_url, timeout=20) as client:
        auth = client.post(
            "/api/v1/auth/register",
            json={
            "email": f"ingestion-{unique}@example.com",
                "password": "integration-password-123",
            },
        )
        assert auth.status_code == 201, auth.text
        headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
        organization = client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Ingestion test", "slug": f"ingestion-{unique}"},
        )
        assert organization.status_code == 201, organization.text
        organization_id = organization.json()["id"]
        headers["X-Organization-ID"] = organization_id
        workspace = client.post(
            "/api/v1/workspaces", headers=headers, json={"name": "Documents", "slug": "documents"}
        )
        assert workspace.status_code == 201, workspace.text
        workspace_id = workspace.json()["id"]
        pdf = pymupdf.open()
        pdf.new_page().insert_text((72, 72), "Unique PDF ingestion citation")
        pdf_data = pdf.tobytes()
        pdf.close()
        samples = [
            ("sample.pdf", "application/pdf", pdf_data),
            ("sample.txt", "text/plain", b"Unique TXT ingestion content"),
            ("sample.md", "text/markdown", b"# Authentication\n\nUnique MD ingestion content"),
        ]
        accepted = []
        for filename, mime, content in samples:
            response = client.post(
                f"/api/v1/workspaces/{workspace_id}/documents",
                headers=headers,
                files={"file": (filename, content, mime)},
            )
            assert response.status_code == 202, response.text
            assert response.json()["status"] == "QUEUED"
            accepted.append(response.json())
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            listing = client.get(f"/api/v1/workspaces/{workspace_id}/documents", headers=headers)
            assert listing.status_code == 200, listing.text
            states = {item["id"]: item for item in listing.json()}
            if all(
                states.get(item["document_id"], {}).get("status") in {"READY", "FAILED"}
                for item in accepted
            ):
                break
            time.sleep(2)
        assert all(states[item["document_id"]]["status"] == "READY" for item in accepted), states
        search = client.get(
            f"/api/v1/workspaces/{workspace_id}/search",
            headers=headers,
            params={"q": "Authentication"},
        )
        assert search.status_code == 200, search.text
        assert any(hit.get("heading") == "Authentication" for hit in search.json()["hits"])
        invalid = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=headers,
            files={"file": ("invalid.pdf", b"%PDF-not-a-real-file", "application/pdf")},
        )
        assert invalid.status_code == 202, invalid.text
        failed_id = invalid.json()["document_id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            listing = client.get(f"/api/v1/workspaces/{workspace_id}/documents", headers=headers)
            failed = next(item for item in listing.json() if item["id"] == failed_id)
            if failed["status"] == "FAILED":
                break
            time.sleep(1)
        assert failed["status"] == "FAILED" and failed["error_code"] == "INVALID_PDF"
        assert failed["attempts"] == 1
        retried = client.post(
            f"/api/v1/workspaces/{workspace_id}/document-versions/"
            f"{invalid.json()['document_version_id']}/retry",
            headers=headers,
        )
        assert retried.status_code == 202, retried.text
        assert retried.json()["document_version_id"] == invalid.json()["document_version_id"]
        assert retried.json()["job_id"] == invalid.json()["job_id"]
        other_org = client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Other test", "slug": f"other-{unique}"},
        )
        assert other_org.status_code == 201, other_org.text
        headers["X-Organization-ID"] = other_org.json()["id"]
        foreign = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=headers,
            files={"file": ("foreign.txt", b"secret", "text/plain")},
        )
        assert foreign.status_code == 404
        assert foreign.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
