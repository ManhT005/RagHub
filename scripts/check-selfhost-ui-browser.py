"""Browser acceptance at desktop widths using state from self-host-ui-smoke.py.

Requires optional Playwright test tooling; writes screenshots only under .backups.
Uses real API responses and existing provisioned credentials, without mock routes.
"""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:18082")
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path(".backups/ui-validation/screenshots")
    )
    args = parser.parse_args()
    state = json.loads(args.state_file.read_text(encoding="utf-8"))
    owner = json.loads(args.owner_file.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    errors = []

    def token(credentials):
        response = httpx.post(
            args.base_url + "/api/v1/auth/login", json=credentials, timeout=20
        )
        assert response.status_code == 200, "Browser test login failed"
        return response.json()["access_token"]

    def initialize(context, access_token):
        context.add_init_script(
            """const data = """
            + json.dumps({"token": access_token, "org": state["organization_id"]})
            + """;
            sessionStorage.setItem('raghub.access-token', data.token);
            sessionStorage.setItem('raghub.organization-id', data.org);
            localStorage.setItem('raghub-theme', 'light');"""
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        initialize(context, token(owner))
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: errors.append(message.text)
            if message.type == "error"
            else None,
        )
        workspace_path = f"/app/workspaces/{state['workspace_id']}"
        pages = [
            ("/system/ai/providers", "AI Providers"),
            ("/system/ai/models", "Model Registry"),
            ("/app/workspaces", "Workspaces"),
            (workspace_path + "/overview", "UI knowledge workspace"),
            (workspace_path + "/documents", "Tài liệu"),
            (workspace_path + "/members", "Thành viên & quyền"),
            (workspace_path + "/ai", "AI & Models"),
            (workspace_path + "/chat", "Chat với tài liệu"),
        ]
        for width in (1024, 1440, 1920):
            page.set_viewport_size({"width": width, "height": 1000})
            for route, heading in pages:
                page.goto(args.base_url + route)
                expect(
                    page.get_by_role("heading", name=heading, exact=True)
                ).to_be_visible(timeout=30000)
                page.wait_for_load_state("networkidle")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth > window.innerWidth + 1"
                )
                assert not overflow, f"Page overflows at {width}: {route}"
                if route.endswith("/documents"):
                    sidebar = page.locator("nz-sider")
                    expect(sidebar.locator('a[href="/app/profile"]')).to_have_count(0)
                    expect(sidebar.locator('a[href^="/system"]')).to_have_count(0)
                    expect(sidebar.locator(".workspace-identity")).to_contain_text(
                        "ui-knowledge"
                    )
                    expect(
                        page.get_by_role("button", name="recovery.txt", exact=True)
                    ).to_be_visible()
                page.screenshot(
                    path=str(
                        args.output
                        / f"{width}-{route.strip('/').replace('/', '_')}.png"
                    ),
                    full_page=True,
                )
            print(f"PASS: 8 screens at {width}px without page overflow", flush=True)

        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 900})
            page.goto(args.base_url + workspace_path + "/documents")
            expect(
                page.get_by_role("heading", name="Tài liệu", exact=True)
            ).to_be_visible()
            assert not page.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth + 1"
            )
            page.screenshot(
                path=str(args.output / f"{width}-workspace-documents.png"),
                full_page=True,
            )
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Chuyển sang nền tối").click()
        page.screenshot(
            path=str(args.output / "dark-workspace-documents.png"), full_page=True
        )
        page.get_by_role("button", name="Chuyển sang nền sáng").click()
        assert page.locator("raghub-provider-logo img").evaluate_all(
            "images => images.every(img => img.complete && img.naturalWidth > 0)"
        )
        print(
            "PASS: mobile/tablet, dark mode, workspace isolation and local logo loading",
            flush=True,
        )

        page.set_viewport_size({"width": 1024, "height": 1000})
        custom_name = "Custom brand regression " + uuid4().hex[:8]
        api_headers = {
            "Authorization": "Bearer " + token(owner),
            "X-Organization-ID": state["organization_id"],
        }
        custom = httpx.post(
            args.base_url
            + f"/api/v1/organizations/{state['organization_id']}/provider-connections",
            headers=api_headers,
            json={
                "name": custom_name,
                "catalog_id": "compatible",
                "provider_type": "OPENAI_COMPATIBLE",
                "base_url": "https://api.openai.com/v1",
            },
            timeout=20,
        )
        assert custom.status_code == 201 and custom.json()["catalog_id"] == "compatible"
        try:
            page.goto(args.base_url + "/system/ai/providers")
            card = page.locator(".provider-card").filter(
                has=page.get_by_role("heading", name=custom_name, exact=True)
            )
            expect(card.locator("raghub-provider-logo img")).to_have_attribute(
                "src", "assets/providers/openai-compatible.svg"
            )
            card.get_by_role("button", name="Quản lý").click()
            expect(
                page.get_by_role("heading", name="OpenAI-compatible", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="Hủy", exact=True).click()
        finally:
            assert (
                httpx.delete(
                    args.base_url
                    + f"/api/v1/provider-connections/{custom.json()['id']}",
                    headers=api_headers,
                    timeout=20,
                ).status_code
                == 204
            )
        print(
            "PASS: custom identity survives create, logo rendering and edit with OpenAI endpoint",
            flush=True,
        )
        page.goto(args.base_url + "/system/ai/providers")
        page.get_by_role("button", name="+ Thêm provider", exact=True).click()
        expect(
            page.get_by_role("button", name="Anthropic Coming soon")
        ).to_be_disabled()
        page.get_by_role(
            "button", name="Sentence Transformer EMBEDDING", exact=True
        ).click()
        page.get_by_label("Tên provider", exact=True).fill(
            "Browser embedding " + uuid4().hex[:8]
        )
        page.get_by_role(
            "button", name="Kiểm tra kết nối & tìm model", exact=True
        ).click()
        expect(page.get_by_role("heading", name="Chọn model để đăng ký")).to_be_visible(
            timeout=30000
        )
        page.get_by_label("Model ID", exact=True).fill(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        page.get_by_role("button", name="Thêm vào lựa chọn").click()
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/models")
            and "/provider-connections/" in response.url
        ) as registration:
            page.get_by_role(
                "button", name="Kiểm tra & đăng ký model", exact=True
            ).click()
        browser_model = registration.value.json()
        assert registration.value.status == 201
        expect(page.locator(".ant-drawer-open")).to_have_count(0, timeout=60000)
        print("PASS: real browser provider -> manual model registration", flush=True)

        page.goto(args.base_url + workspace_path + "/documents")
        page.get_by_role("button", name="+ Tải tài liệu lên", exact=True).click()
        file_name = "browser-" + uuid4().hex[:8] + ".md"
        page.locator("input[type=file]").set_input_files(
            {
                "name": file_name,
                "mimeType": "text/markdown",
                "buffer": b"# Browser acceptance\n\nRagHub browser upload was successful.",
            }
        )
        page.get_by_role("button", name="Đổi", exact=True).click()
        expect(page.get_by_role("dialog").get_by_role("radiogroup")).to_be_visible()
        page.screenshot(
            path=str(args.output / "embedding-model-picker.png"), full_page=True
        )
        page.locator(".embedding-picker").get_by_role(
            "button", name="Hủy", exact=True
        ).click()
        expect(
            page.get_by_role("dialog").filter(has=page.locator(".upload-content"))
        ).to_contain_text(file_name)
        page.screenshot(path=str(args.output / "upload-modal.png"), full_page=True)
        page.get_by_role("button", name="Tải lên & lập chỉ mục", exact=True).click()
        expect(page.locator(".ant-modal")).to_have_count(0, timeout=30000)
        row = page.get_by_role("row").filter(
            has=page.get_by_role("button", name=file_name, exact=True)
        )
        expect(row.get_by_text("Sẵn sàng", exact=True)).to_be_visible(timeout=180000)
        page.get_by_role("button", name=file_name, exact=True).click()
        expect(page.get_by_role("heading", name=file_name, exact=True)).to_be_visible()
        expect(page.get_by_text("450 tokens / overlap 80", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Nội dung", exact=True).click()
        expect(page.locator(".document-text")).to_contain_text("# Browser acceptance")
        page.get_by_role("tab", name="Thông tin", exact=True).click()
        assert page.locator(".ant-drawer-body").evaluate(
            "element => element.scrollWidth <= element.clientWidth + 1"
        ), "Document detail content overflows its drawer"
        page.screenshot(path=str(args.output / "document-detail.png"), full_page=True)
        with page.expect_download() as original:
            page.get_by_role("button", name="Tải bản gốc", exact=True).click()
        assert original.value.suggested_filename == file_name
        assert (
            Path(original.value.path()).read_bytes().startswith(b"# Browser acceptance")
        )
        page.locator(".ant-drawer-close").click()
        page.get_by_role("button", name="Đổi model", exact=True).click()
        page.get_by_role(
            "radio",
            name=f"Chọn {browser_model['model']} từ {browser_model['provider_name']}",
            exact=True,
        ).check()
        page.get_by_role("button", name="Chọn model", exact=True).click()
        expect(
            page.get_by_role("button", name="Đổi model & lập chỉ mục", exact=True)
        ).to_be_disabled(timeout=30000)
        assert page.locator(".ant-modal-body").evaluate(
            "element => element.scrollWidth <= element.clientWidth + 1"
        ), "Embedding impact content overflows its modal"
        page.screenshot(path=str(args.output / "embedding-impact.png"), full_page=True)
        page.get_by_role("checkbox").check()
        page.get_by_role("button", name="Đổi model & lập chỉ mục", exact=True).click()
        expect(page.locator(".ant-modal")).to_have_count(0, timeout=30000)
        expect(
            page.get_by_text(
                "Đang xây dựng index mới. Index hiện tại tiếp tục phục vụ tìm kiếm và chat.",
                exact=True,
            )
        ).to_have_count(0, timeout=180000)
        print(
            "PASS: browser upload -> polling -> detail -> preview -> confirmed migration",
            flush=True,
        )

        page.get_by_role("button", name="Thao tác với " + file_name, exact=True).click()
        page.get_by_role("button", name="Xóa tài liệu", exact=True).click()
        expect(
            page.get_by_text("Xóa tài liệu và dữ liệu tìm kiếm liên quan?", exact=True)
        ).to_be_visible()
        page.locator(".ant-popover-buttons button").first.click()
        expect(page.get_by_role("button", name=file_name, exact=True)).to_be_visible()
        page.get_by_role("button", name="Thao tác với " + file_name, exact=True).click()
        page.get_by_role("button", name="Xóa tài liệu", exact=True).click()
        page.locator(".ant-popover-buttons button").last.click()
        expect(page.get_by_role("button", name=file_name, exact=True)).to_have_count(
            0, timeout=30000
        )
        print(
            "PASS: original download and cancel/confirm document deletion", flush=True
        )

        viewer = browser.new_context(viewport={"width": 1440, "height": 1000})
        initialize(viewer, token(state["member"]))
        member_page = viewer.new_page()
        member_page.on("pageerror", lambda error: errors.append(str(error)))
        member_page.goto(args.base_url + workspace_path + "/documents")
        expect(
            member_page.get_by_role("heading", name="Tài liệu", exact=True)
        ).to_be_visible(timeout=30000)
        expect(
            member_page.get_by_role("button", name="+ Tải tài liệu lên")
        ).to_have_count(0)
        expect(
            member_page.locator("nz-sider").get_by_text("AI & Models", exact=True)
        ).to_have_count(0)
        expect(
            member_page.locator("nz-sider").get_by_text("AI Providers", exact=True)
        ).to_have_count(0)
        member_page.goto(args.base_url + workspace_path + "/ai")
        expect(member_page).to_have_url(
            args.base_url + workspace_path + "/overview?denied=1"
        )
        member_page.goto(args.base_url + "/system/ai/providers")
        expect(member_page).to_have_url(args.base_url + "/app/workspaces")
        print("PASS: delegated navigation/actions and direct URL denial", flush=True)
        browser.close()
    assert not errors, "Browser reported errors: " + "\n".join(errors)
    print("PASS: no browser console errors or unhandled page errors", flush=True)


if __name__ == "__main__":
    main()
