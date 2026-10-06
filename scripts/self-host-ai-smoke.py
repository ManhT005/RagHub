"""AI configuration acceptance on an explicit disposable loopback installation.

Credentials/state/screenshots stay in ignored local files. Uses actual providers;
the pull smoke reuses an installed gemma3:1b and refuses a new model download.
"""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".backups/ai-smoke"))
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--browser-only", action="store_true")
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--skip-local-embedding", action="store_true")
    args = parser.parse_args()
    if urlsplit(args.base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Use an explicit loopback test installation")
    owner = json.loads(args.owner_file.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.base_url, timeout=150) as client:

        def request(method, path, **kwargs):
            result = client.request(method, "/api/v1" + path, **kwargs)
            assert result.is_success, f"{method} {path} failed ({result.status_code})"
            return result.json() if result.content else None

        if args.initialize:
            assert request("GET", "/setup/status")["status"] == "UNINITIALIZED"
            auth = request(
                "POST",
                "/setup/initialize",
                json={
                    "owner_email": owner["email"],
                    "owner_password": owner["password"],
                    "ai_mode": "LOCAL",
                },
            )
        else:
            auth = request("POST", "/auth/login", json=owner)
        client.headers["Authorization"] = "Bearer " + auth["access_token"]
        if args.browser_only or args.verify_existing:
            state = json.loads((args.output / "state.json").read_text(encoding="utf-8"))
            client.headers["X-Organization-Id"] = state["organization_id"]
            connection = state["ollama_connection_id"]
            job = request(
                "GET",
                f"/provider-connections/{connection}/ollama/model-pulls/{state['pull_job_id']}",
            )
            assert job["status"] == "READY" and job["registered_model_id"]
            workspace = request("GET", f"/workspaces/{state['workspace_id']}")
            assert (
                workspace["ai_status"] == "PARTIAL"
                and workspace["chat_model"]["model"] == "gemma3:1b"
            )
            defaults = request("GET", "/workspaces/ai-defaults")
            assert (
                defaults["default_chat_model_id"]
                and defaults["default_embedding_model_id"]
            )
            installed = request(
                "POST", f"/provider-connections/{connection}/models/discover"
            )
            assert any(item["model"] == "gemma3:1b" for item in installed)
            if args.browser_only or args.browser:
                browser_smoke(args, auth["access_token"], state)
            print(
                "PASS: persisted pull job, organization defaults and workspace bindings"
            )
            return
        organizations = request("GET", "/organizations")
        org = organizations[0]["id"]
        client.headers["X-Organization-Id"] = org
        connections = request("GET", f"/organizations/{org}/provider-connections")
        assert {item["catalog_id"] for item in connections} >= {
            "sentence-transformer",
            "ollama",
        }
        ollama = next(item for item in connections if item["catalog_id"] == "ollama")[
            "id"
        ]
        installed = request("POST", f"/provider-connections/{ollama}/models/discover")
        assert any(item["model"] == "gemma3:1b" for item in installed), (
            "Install gemma3:1b explicitly before running smoke"
        )
        if args.skip_local_embedding:
            models = request("GET", f"/organizations/{org}/models")
            chat = next(item for item in models if item["capability"] == "CHAT")
            if chat["availability_status"] != "AVAILABLE":
                request("POST", f"/models/{chat['id']}/test")
        deadline = time.monotonic() + 240
        while True:
            models = request("GET", f"/organizations/{org}/models")
            checked_models = [
                item
                for item in models
                if not args.skip_local_embedding or item["capability"] == "CHAT"
            ]
            if (
                len(models) >= 2
                and checked_models
                and all(
                    item["availability_status"] == "AVAILABLE"
                    for item in checked_models
                )
            ):
                break
            assert time.monotonic() < deadline, "Local AI health jobs did not finish"
            time.sleep(2)
        defaults = request("GET", "/workspaces/ai-defaults")
        assert (
            defaults["default_embedding_model_id"] and defaults["default_chat_model_id"]
        )
        existing_workspaces = request("GET", "/workspaces")

        def ensure_workspace(payload):
            existing = next(
                (
                    item
                    for item in existing_workspaces
                    if item["slug"] == payload["slug"]
                ),
                None,
            )
            return existing or request("POST", "/workspaces", json=payload)

        chat_only = ensure_workspace(
            {
                "name": "Chat Only",
                "slug": "ai-smoke-chat",
                "embedding_model_id": None,
                "chat_model_id": defaults["default_chat_model_id"],
            },
        )
        assert (
            chat_only["ai_status"] == "PARTIAL"
            and chat_only["chat_model"]["model"] == "gemma3:1b"
        )
        ready = None
        if not args.skip_local_embedding:
            ready = ensure_workspace({"name": "Ready AI", "slug": "ai-smoke-ready"})
            assert ready["ai_status"] == "READY"
        empty = ensure_workspace(
            {
                "name": "Empty AI",
                "slug": "ai-smoke-empty",
                "embedding_model_id": None,
                "chat_model_id": None,
            },
        )
        request(
            "PUT",
            f"/workspaces/{empty['id']}/chat-model",
            json={"model_id": defaults["default_chat_model_id"]},
        )
        updated = request("GET", f"/workspaces/{empty['id']}")
        assert (
            updated["ai_status"] == "PARTIAL"
            and updated["chat_model"]["model"] == "gemma3:1b"
        )
        job = request(
            "POST",
            f"/provider-connections/{ollama}/ollama/models/pull",
            json={"model": "gemma3:1b", "register_after_pull": True},
        )
        deadline = time.monotonic() + 360
        while job["status"] in {"QUEUED", "PULLING", "VERIFYING"}:
            assert time.monotonic() < deadline, "Ollama pull did not finish"
            time.sleep(1)
            job = request(
                "GET", f"/provider-connections/{ollama}/ollama/model-pulls/{job['id']}"
            )
        assert job["status"] == "READY" and job["registered_model_id"], (
            "Ollama pull/register failed"
        )
        state = {
            "organization_id": org,
            "workspace_id": chat_only["id"],
            "ready_workspace_id": ready["id"] if ready else None,
            "local_embedding_skipped": args.skip_local_embedding,
            "ollama_connection_id": ollama,
            "pull_job_id": job["id"],
        }
        (args.output / "state.json").write_text(json.dumps(state), encoding="utf-8")
        if args.browser:
            browser_smoke(args, auth["access_token"], state)
    print(
        "PASS: LOCAL registry/defaults, chat-only PARTIAL, save/read/list, real Ollama pull/probe/register; "
        + (
            "local embedding runtime skipped"
            if args.skip_local_embedding
            else "both READY"
        )
    )


def browser_smoke(args, token, state):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(
            "const data = "
            + json.dumps({"token": token, "org": state["organization_id"]})
            + ";"
            "sessionStorage.setItem('raghub.access-token', data.token);"
            "sessionStorage.setItem('raghub.organization-id', data.org);"
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(type(error).__name__))
        page.goto(args.base_url + f"/app/workspaces/{state['workspace_id']}/ai")
        chat = page.locator("section").filter(
            has=page.get_by_role("heading", name="Chat model", exact=True)
        )
        expect(chat.get_by_text("gemma3:1b", exact=True)).to_be_visible()
        save = chat.get_by_role("button", name="Lưu chat model", exact=True)
        expect(save).to_be_enabled()
        save.click()
        expect(chat.get_by_text("Đã cập nhật chat model.", exact=True)).to_be_visible()
        page.screenshot(path=str(args.output / "workspace-ai-saved.png"))
        page.goto(args.base_url + "/app/workspaces")
        expect(page.get_by_text("AI Models", exact=True)).to_be_visible()
        expect(page.get_by_text("Thiếu embedding", exact=True).first).to_be_visible()
        expect(page.get_by_text("gemma3:1b", exact=True).first).to_be_visible()
        page.screenshot(path=str(args.output / "workspace-list.png"))
        page.goto(args.base_url + f"/app/workspaces/{state['workspace_id']}/overview")
        expect(page.get_by_text("Chat model của workspace", exact=True)).to_be_visible()
        expect(page.get_by_text("Thiếu embedding", exact=True)).to_be_visible()
        page.screenshot(path=str(args.output / "workspace-overview.png"))
        page.goto(args.base_url + "/system/ai/providers")
        page.locator(".provider-card").filter(has_text="Local Chat").get_by_role(
            "button", name="Quản lý →", exact=True
        ).click()
        # Existing connection starts on Connection so its endpoint can be checked again.
        page.get_by_role(
            "button", name="Kiểm tra kết nối & tìm model", exact=True
        ).click()
        try:
            expect(
                page.get_by_role("button", name="Recommended", exact=True)
            ).to_be_visible(timeout=30_000)
        except AssertionError:
            page.screenshot(path=str(args.output / "provider-failure.png"))
            raise AssertionError(
                page.locator(".ant-drawer-body").inner_text()
            ) from None
        page.get_by_role("button", name="Recommended", exact=True).click()
        expect(page.get_by_text("Qwen3 4B", exact=True)).to_be_visible()
        page.screenshot(path=str(args.output / "ollama-recommended-desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("""() => {
            const drawer = document.querySelector('.ant-drawer-content-wrapper').getBoundingClientRect();
            return drawer.x >= -1 && drawer.right <= innerWidth + 1 && drawer.width <= innerWidth + 1;
        }""")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(args.output / "ollama-recommended-mobile.png"))
        assert not errors, "Browser runtime errors occurred"
        browser.close()
    print("PASS: browser Workspace AI summaries and responsive Ollama recommendations")


if __name__ == "__main__":
    main()
