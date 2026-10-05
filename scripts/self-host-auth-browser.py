"""Real browser setup and session acceptance. Credentials stay in ignored files."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:18082")
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--auth-expiry-seconds", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path(".backups/auth-browser"))
    args = parser.parse_args()
    if urlsplit(args.base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Browser smoke requires an explicit loopback test installation")
    owner = json.loads(args.owner_file.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.set_default_timeout(30000)
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(type(error).__name__))
        if args.initialize:
            status = context.request.get(args.base_url + "/api/v1/setup/status")
            assert status.status == 200
            assert status.json() == {"status": "UNINITIALIZED", "initialized": False}
            page.goto(args.base_url + "/app/workspaces")
            expect(page).to_have_url(args.base_url + "/setup")
            expect(page.get_by_text("Chưa sẵn sàng", exact=True)).to_have_count(0)
            page.screenshot(path=str(args.output / "setup-desktop.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(path=str(args.output / "setup-mobile.png"))
            page.set_viewport_size({"width": 1280, "height": 900})
            page.get_by_role("button", name="Tiếp tục", exact=True).click()
            page.get_by_label("Email Owner", exact=True).fill(owner["email"])
            page.get_by_label("Mật khẩu", exact=True).fill(owner["password"])
            page.get_by_label("Nhập lại mật khẩu", exact=True).fill(owner["password"])
            page.get_by_role("button", name="Tiếp tục", exact=True).click()
            page.get_by_role("button", name="Tiếp tục", exact=True).click()
            page.get_by_role("radio", name="Bỏ qua lúc này").check()
            page.get_by_role("button", name="Tiếp tục", exact=True).click()
            page.get_by_role("button", name="Hoàn tất cài đặt").click()
            expect(
                page.get_by_text("Khởi tạo thành công.", exact=False)
            ).to_be_visible()
            page.get_by_role("link", name="Mở Workspace").click()
        else:
            page.goto(args.base_url + "/auth")
            page.get_by_label("Email", exact=True).fill(owner["email"])
            page.get_by_label("Mật khẩu", exact=True).fill(owner["password"])
            page.get_by_role("button", name="Đăng nhập", exact=True).click()
        expect(page).to_have_url(args.base_url + "/app/workspaces")
        expect(page.locator(".account-trigger")).to_contain_text(owner["email"])
        cookies = context.cookies()
        refresh = next(
            cookie for cookie in cookies if cookie["name"] == "refresh_token"
        )
        assert (
            refresh["httpOnly"]
            and refresh["secure"]
            and refresh["path"] == "/api/v1/auth"
        )
        assert "refresh_token" not in page.evaluate("document.cookie")
        token = page.evaluate("sessionStorage.getItem('raghub.access-token')")
        assert token
        if args.auth_expiry_seconds:
            print(
                "Waiting for real access-token expiry before concurrent UI requests",
                flush=True,
            )
            page.wait_for_timeout(args.auth_expiry_seconds * 1000)
            refresh_requests = []
            page.on(
                "request",
                lambda request: refresh_requests.append(1)
                if request.url.endswith("/auth/refresh")
                else None,
            )
            page.reload()
            expect(page.locator(".account-trigger")).to_contain_text(owner["email"])
            assert (
                page.evaluate("sessionStorage.getItem('raghub.access-token')") != token
            )
            assert len(refresh_requests) == 1, (
                "Concurrent UI 401s did not share one refresh"
            )
        # Reload and a new tab have no access token: only the HttpOnly cookie restores them.
        page.evaluate("sessionStorage.removeItem('raghub.access-token')")
        page.reload()
        expect(page.locator(".account-trigger")).to_contain_text(owner["email"])
        new_tab = context.new_page()
        new_tab.goto(args.base_url + "/app/workspaces")
        expect(new_tab.locator(".account-trigger")).to_contain_text(owner["email"])
        assert new_tab.evaluate("sessionStorage.getItem('raghub.access-token')")
        new_tab.close()
        page.route(
            "**/api/v1/auth/me",
            lambda route: route.fulfill(
                status=503, json={"error": {"code": "DEPENDENCY_UNAVAILABLE"}}
            ),
        )
        saved = page.evaluate("sessionStorage.getItem('raghub.access-token')")
        page.reload()
        expect(page.get_by_role("alert")).to_contain_text("Kết nối tạm thời gián đoạn")
        assert page.evaluate("sessionStorage.getItem('raghub.access-token')") == saved
        page.unroute("**/api/v1/auth/me")
        page.get_by_role("button", name="Thử lại", exact=True).click()
        expect(page.locator(".account-trigger")).to_contain_text(owner["email"])
        page.goto(args.base_url + "/setup")
        expect(page).to_have_url(args.base_url + "/app/workspaces")
        page.locator(".account-trigger").click()
        with page.expect_response("**/api/v1/auth/logout") as logout:
            page.get_by_role("menuitem", name="Đăng xuất", exact=True).click()
        assert logout.value.status == 204
        expect(page).to_have_url(args.base_url + "/auth")
        page.wait_for_function("!sessionStorage.getItem('raghub.access-token')")
        # Wait for asynchronous backend logout to clear the cookie before testing restore.
        page.wait_for_function("!sessionStorage.getItem('raghub.organization-id')")
        page.wait_for_timeout(500)
        assert not any(
            cookie["name"] == "refresh_token" for cookie in context.cookies()
        )
        assert not page_errors, "Browser runtime errors occurred"
        browser.close()
    print(
        "PASS: browser setup, responsive wizard, single-flight expiry, reload/new tab restore, transient outage and logout",
        flush=True,
    )


if __name__ == "__main__":
    main()
