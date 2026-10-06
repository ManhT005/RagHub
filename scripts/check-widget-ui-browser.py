"""Deterministic Chromium acceptance for built Admin/widget assets with mocked APIs.

No real accounts, providers or external services are modified. Requires Playwright
and a production Admin build plus a compiled widget. Outputs stay under .backups.
"""

import argparse
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8078"
HOST = "http://127.0.0.1:5500"
BOT = {
    "id": "bot-1",
    "workspace_id": "ws-1",
    "name": "Trợ lý tài liệu",
    "system_prompt": "",
    "model": None,
    "retrieval_limit": 5,
    "published": True,
    "allowed_origins": [HOST, BASE],
    "embed_primary_color": "#8faaf6",
    "embed_title": "Trợ lý tuyển sinh",
    "embed_greeting": "Xin chào! Tôi có thể giúp gì cho bạn?",
    "created_at": "2026-10-05T00:00:00Z",
    "updated_at": None,
}
METADATA = {
    "code": None,
    "key": None,
    "has_embed_key": True,
    "public_base_url": BASE,
    "script_src": BASE + "/widget/raghub.js",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-dist", type=Path, default=Path("apps/admin-web/dist/admin-web/browser")
    )
    parser.add_argument(
        "--widget-js", type=Path, default=Path(".backups/widget-ui-v2/widget/raghub.js")
    )
    parser.add_argument(
        "--output", type=Path, default=Path(".backups/widget-ui-v2/browser")
    )
    parser.add_argument("--widget-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    assert (args.admin_dist / "index.html").exists(), "Build Admin first"
    assert args.widget_js.exists(), "Compile the widget first"
    state = {"widget_error": None, "config_error": None, "initialized": True}
    errors, unknown_api, checks = [], [], []

    def api(route):
        path = urlsplit(route.request.url).path
        origin = route.request.headers.get("origin", BASE)
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Headers": "Content-Type, Accept",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=headers)
            return
        if "/public/chatbots/" in path:
            if path.endswith("/config"):
                if state["config_error"]:
                    route.fulfill(
                        status=403,
                        headers=headers,
                        json={
                            "error": {
                                "code": state["config_error"],
                                "message": "upstream-secret",
                            }
                        },
                    )
                else:
                    route.fulfill(
                        headers=headers,
                        json={
                            "primary_color": "#8faaf6",
                            "title": BOT["embed_title"],
                            "greeting": BOT["embed_greeting"],
                        },
                    )
                return
            if state["widget_error"]:
                route.fulfill(
                    status=429,
                    headers=headers,
                    json={
                        "error": {
                            "code": state["widget_error"],
                            "message": "upstream-secret",
                        }
                    },
                )
                return
            citations = [
                {
                    "citation_id": f"C{i + 1}",
                    "document_name": "Hướng dẫn tuyển sinh đại học chính quy năm 2026 – tên tài liệu rất dài.pdf",
                    "page": i + 1,
                    "excerpt": "Nội dung trích đoạn liên quan. " * 30,
                    "score": 0.83,
                    "chunk_id": "hidden-uuid",
                }
                for i in range(5)
            ]
            events = [
                ("conversation", {"conversation_id": "conversation-1"}),
                ("citations", {"citations": citations}),
                (
                    "token",
                    {
                        "text": "Theo tài liệu tuyển sinh, bạn có thể tham khảo quy định và thời gian đăng ký. "
                        * 12
                    },
                ),
                ("done", {}),
            ]
            body = "".join(
                f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                for event, data in events
            )
            route.fulfill(headers=headers, content_type="text/event-stream", body=body)
            return
        data = None
        if path.endswith("/setup/status"):
            data = {
                "status": "INITIALIZED" if state["initialized"] else "UNINITIALIZED",
                "initialized": state["initialized"],
            }
        elif path.endswith("/auth/me"):
            data = {"id": "user-1", "email": "test@example.com", "email_verified": True}
        elif path.endswith("/organizations"):
            data = [
                {"id": "org-1", "name": "RagHub", "slug": "raghub", "role": "ADMIN"}
            ]
        elif path.endswith("/me/permissions"):
            data = {
                "workspace_id": "ws-1",
                "permissions": ["workspace.edit", "chat.use"],
                "is_system_admin": True,
            }
        elif path.endswith("/embed-code"):
            data = METADATA
        elif path.endswith("/embed-key/rotate"):
            data = {
                **METADATA,
                "key": "rgh_browser_test",
                "code": f'<script src="{BASE}/widget/raghub.js" data-chatbot-key="rgh_browser_test" async></script>',
            }
        elif path.endswith("/publish"):
            data = METADATA
        elif path.endswith("/chatbots/bot-1"):
            data = BOT
        elif path == "/health/ready":
            data = {"status": "ready"}
        else:
            unknown_api.append(path)
        route.fulfill(
            status=200 if data is not None else 404, headers=headers, json=data or {}
        )

    def serve(route):
        path = urlsplit(route.request.url).path
        if path.startswith("/api/") or path.startswith("/health/"):
            api(route)
            return
        if path == "/widget/raghub.js":
            route.fulfill(
                path=str(args.widget_js),
                content_type="application/javascript; charset=utf-8",
            )
            return
        candidate = (args.admin_dist / path.lstrip("/")).resolve()
        if not candidate.is_relative_to(args.admin_dist.resolve()):
            route.fulfill(status=404)
        elif candidate.is_file():
            route.fulfill(
                path=str(candidate),
                content_type=mimetypes.guess_type(candidate)[0]
                or "application/octet-stream",
            )
        else:
            route.fulfill(
                path=str(args.admin_dist / "index.html"), content_type="text/html"
            )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        if not args.widget_only:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
            )
            context.route(BASE + "/**", serve)
            context.add_init_script(
                "sessionStorage.setItem('raghub.access-token','test-only');sessionStorage.setItem('raghub.organization-id','org-1');localStorage.setItem('raghub-theme','light');"
            )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE + "/app/chatbots/bot-1/settings")
            expect(
                page.get_by_role("heading", name="Nhúng chatbot", exact=True)
            ).to_be_visible()
            expect(
                page.get_by_role("button", name="Sao chép mã", exact=True)
            ).to_be_disabled()
            expect(page.locator(".key-empty")).to_contain_text(
                "key cũ không được hiển thị lại"
            )
            page.locator(".color-hex").fill("#ffffff")
            expect(page.locator(".color-swatch")).to_have_value("#ffffff")
            assert (
                page.locator(".preview-head").evaluate(
                    "node => getComputedStyle(node).color"
                )
                == "rgb(0, 0, 0)"
            )
            page.locator("#widget-title").fill("Trợ lý thử nghiệm")
            expect(page.locator(".preview-head strong")).to_have_text(
                "Trợ lý thử nghiệm"
            )
            page.locator(".color-hex").fill("#xyz")
            expect(
                page.get_by_role("button", name="Lưu thay đổi", exact=True)
            ).to_be_disabled()
            page.locator(".color-hex").fill("#8faaf6")
            page.get_by_role("button", name="Mobile", exact=True).click()
            expect(page.locator(".preview-stage")).to_have_class("preview-stage mobile")
            for width in [1440, 375, 320]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.screenshot(
                    path=str(args.output / f"settings-{width}.png"), full_page=True
                )
                overflow = page.evaluate(
                    """() => [...document.querySelectorAll('main, section, aside, form, .card, .color-control, .color-hex, .origin-chip, .ant-layout-content')].filter(n => n.getBoundingClientRect().right > innerWidth + 1).map(n => ({tag:n.tagName, cls:n.className, width:n.getBoundingClientRect().width, right:n.getBoundingClientRect().right}))"""
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), f"Admin overflow at {width}: {overflow}"
                swatch = page.locator(".color-swatch").bounding_box()
                assert swatch and swatch["width"] >= 48 and swatch["height"] >= 48
                page.screenshot(
                    path=str(args.output / f"settings-{width}.png"), full_page=True
                )
                checks.append(f"Admin layout/color/preview at {width}px")
            page.set_viewport_size({"width": 1440, "height": 1000})
            expect(page.locator(".console-main")).to_have_css("margin-left", "232px")
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            expect(page.locator(".preview-head strong")).to_have_css("color", "rgb(0, 0, 0)")
            page.screenshot(path=str(args.output / "settings-dark.png"), full_page=True)
            assert (
                page.locator(".configuration").evaluate(
                    "node => getComputedStyle(node).backgroundColor"
                )
                != "rgb(255, 255, 255)"
            )
            checks.append("Settings respects dark theme tokens")
            page.get_by_role("button", name="Tạo key mới", exact=True).click()
            page.get_by_role("button", name="Tạo key mới", exact=True).last.click()
            expect(page.locator("pre")).to_contain_text(BASE + "/widget/raghub.js")
            assert "#key=" in page.get_by_role(
                "link", name="Mở trang thử widget"
            ).get_attribute("href")
            checks.append("Show-once script and demo after confirmed key rotation")
            for route_name, count in [
                ("/auth", 1),
                ("/auth/reset-password?token=test", 2),
                ("/app/security", 3),
            ]:
                page.goto(BASE + route_name)
                expect(page.locator(".rh-password-toggle")).to_have_count(count)
                field = page.locator(".rh-password-control input").first
                field.fill("test-password-123")
                toggle = page.locator(".rh-password-toggle").first
                expect(field).to_have_attribute("type", "password")
                toggle.focus()
                page.keyboard.press("Enter")
                expect(field).to_have_attribute("type", "text")
                expect(field).to_have_value("test-password-123")
                toggle.click()
                expect(field).to_have_attribute("type", "password")
                checks.append(f"Password visibility/keyboard on {route_name}")
            state["initialized"] = False
            page.goto(BASE + "/setup")
            page.get_by_role("button", name="Tiếp tục", exact=True).click()
            expect(page.locator(".rh-password-toggle")).to_have_count(2)
            checks.append("Both owner setup password fields have visibility controls")

        widget_context = browser.new_context(
            viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
        )
        widget_context.route(BASE + "/**", serve)
        html = f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{{background:#fcf2e8;margin:0}}button,input,textarea{{background:red!important;border:8px dotted red!important;font-size:50px!important}}</style></head><body><h1>Website test</h1><script src="{BASE}/widget/raghub.js" data-chatbot-key="rgh_browser_test" async></script></body></html>'''
        widget_context.route(
            HOST + "/**",
            lambda route: route.fulfill(
                content_type="text/html",
                headers={
                    "Content-Security-Policy": f"default-src 'none'; script-src {BASE}; connect-src {BASE}; style-src 'unsafe-inline'"
                },
                body=html,
            ),
        )
        widget_page = widget_context.new_page()
        widget_page.on("pageerror", lambda error: errors.append(str(error)))
        widget_page.on(
            "console",
            lambda message: print(message.text) if message.type == "error" else None,
        )
        widget_page.goto(HOST + "/")
        expect(widget_page.locator("raghub-chatbot")).to_have_count(1)
        widget_page.get_by_role("button", name="Mở chat", exact=True).click()
        expect(widget_page.locator("raghub-chatbot .subtitle")).to_contain_text(
            "Sẵn sàng"
        )
        widget_page.get_by_role("textbox", name="Câu hỏi").fill("Hỏi về tuyển sinh")
        widget_page.get_by_role("textbox", name="Câu hỏi").press("Enter")
        sources = widget_page.locator("raghub-chatbot details")
        expect(sources).to_have_count(1)
        assert sources.get_attribute("open") is None
        expect(sources.locator("summary")).to_contain_text("· 5")
        summary_height = sources.bounding_box()["height"]
        sources.locator("summary").click()
        expect(sources.locator(".citation-page").first).to_have_text("Trang 1")
        assert sources.bounding_box()["height"] > summary_height
        sources.locator("summary").click()
        assert sources.bounding_box()["height"] == summary_height
        for width in [1440, 375, 320]:
            widget_page.set_viewport_size({"width": width, "height": 800})
            panel = widget_page.locator("raghub-chatbot .panel").bounding_box()
            assert panel and panel["x"] >= 0 and panel["x"] + panel["width"] <= width
            assert panel["y"] >= 0 and panel["y"] + panel["height"] <= 800
            assert (
                widget_page.locator("raghub-chatbot .fab").evaluate(
                    "node => getComputedStyle(node).borderTopWidth"
                )
                == "0px"
            )
            widget_page.screenshot(path=str(args.output / f"widget-{width}.png"))
            checks.append(
                f"Widget viewport, long answer, 5 collapsed sources, host CSS/CSP at {width}px"
            )
        widget_page.get_by_role("button", name="Hội thoại mới", exact=True).click()
        expect(widget_page.locator("raghub-chatbot .message")).to_have_count(1)
        state["widget_error"] = "PUBLIC_CHAT_CONCURRENCY_LIMITED"
        widget_page.get_by_role("textbox", name="Câu hỏi").fill("Hỏi lại")
        widget_page.get_by_role("textbox", name="Câu hỏi").press("Enter")
        expect(widget_page.locator("raghub-chatbot .history")).to_contain_text(
            "Chatbot đang bận"
        )
        checks.append("New conversation and safe HTTP concurrency feedback")
        state["config_error"] = "EMBED_ORIGIN_NOT_ALLOWED"
        widget_page.reload()
        widget_page.get_by_role("button", name="Mở chat", exact=True).click()
        expect(widget_page.locator("raghub-chatbot .history")).to_contain_text(
            "Website này chưa được phép"
        )
        expect(widget_page.get_by_role("textbox", name="Câu hỏi")).to_be_disabled()
        checks.append("Origin denial disables the widget composer")
        browser.close()
    assert not errors, errors
    assert not unknown_api, unknown_api
    report = {
        "checks": checks,
        "page_errors": errors,
        "unknown_api": unknown_api,
        "scope": "Built assets with mocked APIs; real provider/LAN deployment requires environment acceptance.",
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Passed {len(checks)} browser checks. Artifacts: {args.output}")


if __name__ == "__main__":
    main()
