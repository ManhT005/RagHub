type EventPayload = Record<string, unknown>;
type WidgetConfig = { primary_color: string; title: string; greeting: string };

(() => {
  const loaderScript = document.currentScript as HTMLScriptElement | null;
  const defaults: WidgetConfig = { primary_color: "#1463ff", title: "RagHub Assistant", greeting: "Xin chào! Tôi có thể giúp gì cho bạn?" };
  const paths = {
    chat: '<path d="M5 5.75h14A2.25 2.25 0 0 1 21.25 8v7A2.25 2.25 0 0 1 19 17.25H10l-4.75 3v-3.48A2.25 2.25 0 0 1 2.75 15V8A2.25 2.25 0 0 1 5 5.75Z"/><path d="M12 8.3c.35 1.55 1.05 2.25 2.6 2.6-1.55.35-2.25 1.05-2.6 2.6-.35-1.55-1.05-2.25-2.6-2.6 1.55-.35 2.25-1.05 2.6-2.6Z" fill="currentColor" stroke="none"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    reset: '<path d="M3 10a9 9 0 1 1 2.6 8.4M3 4v6h6"/>',
    send: '<path d="m21 3-7 18-4-7-7-4 18-7ZM10 14 21 3"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
  };
  const icon = (name: keyof typeof paths) => `<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]}</svg>`;
  function foregroundFor(hex: string) {
    const rgb = [1, 3, 5].map((start) => {
      const v = parseInt(hex.slice(start, start + 2), 16) / 255;
      return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
    });
    const l = rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
    return (l + .05) / .05 > 1.05 / (l + .05) ? "#000000" : "#ffffff";
  }

  class RaghubChatbot extends HTMLElement {
    private readonly root = this.attachShadow({ mode: "open" });
    private key = "";
    private readonly api = new URL("/api/v1/public/chatbots/", loaderScript?.src || location.href).toString();
    private conversationId: string | null = null;
    private visitorId: string = crypto.randomUUID();
    private controller: AbortController | null = null;
    private config = defaults;
    private open = false;
    private unavailable = false;
    private loading = false;

    connectedCallback() {
      this.key = this.getAttribute("chatbot-key") || "";
      try {
        this.visitorId = sessionStorage.getItem("raghub-visitor") || this.visitorId;
        sessionStorage.setItem("raghub-visitor", this.visitorId);
      } catch { /* Storage may be denied by the embedding website. */ }
      void this.start();
    }
    disconnectedCallback() { this.controller?.abort(); }
    private async start() {
      this.render(defaults, false, true);
      try {
        const response = await fetch(`${this.api}${encodeURIComponent(this.key)}/config`);
        if (!response.ok) throw new Error(await this.responseCode(response));
        this.render(await response.json() as WidgetConfig);
      } catch (error) {
        this.render({ ...defaults, greeting: this.messageFor((error as Error).message) }, true);
      }
    }

    private render(config: WidgetConfig, unavailable = false, loading = false) {
      this.config = config;
      this.unavailable = unavailable;
      this.loading = loading;
      this.root.innerHTML = `<style>
        :host{all:initial;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#182b49;position:fixed;z-index:2147483647;right:20px;bottom:20px;font-size:14px;line-height:1.5;color-scheme:light;text-align:left}
        *,*::before,*::after{box-sizing:border-box}button,textarea{font:inherit}button{cursor:pointer;touch-action:manipulation;display:inline-flex;align-items:center;justify-content:center}button:disabled{cursor:not-allowed;opacity:.5}button:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #5177bf;outline-offset:3px}svg{display:block;flex-shrink:0}
        .fab{position:relative;width:56px;height:56px;border:0;border-radius:50%;background:var(--rgh);color:var(--rgh-fg);box-shadow:0 8px 24px #16396440;float:right;transition:box-shadow .18s}.fab:hover{box-shadow:0 10px 30px #16396460}.fab svg{width:26px;height:26px}.warning-dot{position:absolute;right:2px;top:2px;width:12px;height:12px;border:2px solid #fff;border-radius:50%;background:#b45309}.spinner{width:22px;height:22px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spin 1s linear infinite}
        .panel{display:none;width:380px;height:min(620px,calc(100vh - 100px));height:min(620px,calc(100dvh - 100px));margin-bottom:14px;background:#fff;border:1px solid #dce5f1;border-radius:20px;overflow:hidden;box-shadow:0 20px 64px #12315a2e;flex-direction:column}.panel.open{display:flex}
        .head{padding:14px 12px;flex-shrink:0;background:var(--rgh);color:var(--rgh-fg);display:flex;align-items:center;gap:10px}.brand-avatar{display:flex;align-items:center;justify-content:center;border-radius:12px;background:color-mix(in srgb,currentColor 12%,transparent);width:36px;height:36px;flex-shrink:0}.heading{flex:1;min-width:0}.heading h2{font-size:15px;line-height:1.3;margin:0;font-weight:650;overflow-wrap:anywhere}.subtitle{display:flex;align-items:center;gap:5px;font-size:12px;margin-top:4px}.ready-dot{width:6px;height:6px;border-radius:50%;background:currentColor}.head button{background:transparent;border:0;color:inherit;border-radius:8px;width:32px;height:36px;flex-shrink:0}.head button:hover{background:color-mix(in srgb,currentColor 12%,transparent)}.head button svg{width:18px;height:18px}
        .history{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:18px 14px;background:#f6f8fc;scrollbar-width:thin;scrollbar-color:#8b9bb780 transparent}.history::-webkit-scrollbar{width:7px}.history::-webkit-scrollbar-track{background:transparent}.history::-webkit-scrollbar-thumb{background:#8b9bb748;border-radius:999px}.history::-webkit-scrollbar-button{display:none;width:0;height:0}
        .message{display:flex;align-items:flex-start;gap:8px;margin-bottom:16px;max-width:92%}.message.user{margin-left:auto;max-width:82%;justify-content:flex-end}.avatar{display:flex;align-items:center;justify-content:center;width:24px;height:24px;flex-shrink:0;margin-top:5px;color:#324d7a}.avatar svg{width:22px;height:22px}.msg{min-width:0;padding:11px 13px;border-radius:4px 14px 14px 14px;background:#fff;border:1px solid #e0e7f1;overflow-wrap:anywhere}.user .msg{border:0;border-radius:14px 14px 4px 14px;background:var(--rgh);color:var(--rgh-fg)}.message-text{white-space:pre-wrap}.typing{display:flex;gap:4px;padding:8px 0}.typing i{width:5px;height:5px;border-radius:50%;background:#647695;animation:pulse 1.2s ease-in-out infinite}.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}
        .citations{border-top:1px solid #e6ecf4;margin-top:10px;padding-top:6px;font-size:12px}.citations summary{display:flex;align-items:center;justify-content:space-between;gap:8px;cursor:pointer;list-style:none;min-height:32px;color:#344f79;font-weight:600}.citations summary::-webkit-details-marker{display:none}.citations summary svg{width:16px;height:16px;transition:transform .15s}.citations[open] summary svg{transform:rotate(180deg)}.citation{padding:8px 0;border-top:1px solid #edf1f6;overflow-wrap:anywhere}.citation-title{display:flex;gap:6px;align-items:baseline}.citation-title b{color:#3c5682;flex-shrink:0}.citation-title span{font-weight:600}.citation-page{display:block;color:#586980;margin:3px 0}.excerpt{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;margin:4px 0 0;color:#586980;white-space:pre-wrap}
        .status{flex-shrink:0;padding:0 16px;color:#4f6483;font-size:12px;margin:0}.status:not(:empty){padding-top:6px;padding-bottom:8px}.composer{display:flex;align-items:flex-end;gap:8px;margin:10px 12px 12px;padding:4px;border:1px solid #d5dfed;border-radius:14px;background:#fff;flex-shrink:0}.composer:focus-within{border-color:#5177bf;box-shadow:0 0 0 2px #5177bf20}.composer textarea{resize:none;min-width:0;flex:1;min-height:44px;max-height:120px;border:0;background:transparent;border-radius:10px;padding:11px 8px;color:#182b49;line-height:22px;scrollbar-width:thin}.composer textarea:focus-visible{outline-offset:-3px}.composer textarea::placeholder{color:#62748f}.composer button{width:40px;height:40px;flex-shrink:0;margin-bottom:2px;border:0;border-radius:10px;background:var(--rgh);color:var(--rgh-fg)}.composer button svg{width:20px;height:20px}
        @keyframes spin{to{transform:rotate(360deg)}}@keyframes pulse{50%{opacity:.35}}
        @media(max-width:480px){:host{right:12px;bottom:max(12px,env(safe-area-inset-bottom))}.panel{width:calc(100vw - 24px);height:calc(100vh - 100px);height:calc(100dvh - 100px - env(safe-area-inset-bottom));border-radius:16px}.head button{width:36px;height:44px}.composer textarea{font-size:16px}}
        @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
      </style>
      <section id="rgh-panel" class="panel${this.open ? " open" : ""}" role="region" aria-label="Chat với trợ lý">
        <header class="head"><span class="brand-avatar">${icon("chat")}</span><div class="heading"><h2>${this.escape(config.title)}</h2><div class="subtitle"><span class="ready-dot" aria-hidden="true"></span>Trợ lý tài liệu · ${loading ? "Đang kết nối" : unavailable ? "Chưa kết nối" : "Sẵn sàng"}</div></div><button class="reset" type="button" title="Hội thoại mới" aria-label="Hội thoại mới" ${unavailable || loading ? "disabled" : ""}>${icon("reset")}</button><button class="close" type="button" aria-label="Đóng chat">${icon("close")}</button></header>
        <div class="history" role="log" aria-label="Hội thoại" aria-live="polite" aria-relevant="additions"></div><p class="status" role="status" aria-live="polite" aria-atomic="true"></p>
        <form class="composer"><textarea aria-label="Câu hỏi" placeholder="Nhập câu hỏi…" maxlength="4000" rows="1" ${unavailable || loading ? "disabled" : ""}></textarea><button type="submit" aria-label="Gửi câu hỏi" disabled>${icon("send")}</button></form>
      </section><button class="fab" type="button" aria-label="${this.open ? "Đóng chat" : "Mở chat"}" aria-expanded="${this.open}" aria-controls="rgh-panel">${loading ? '<span class="spinner" aria-hidden="true"></span>' : icon(this.open ? "close" : "chat")}${unavailable ? '<span class="warning-dot" aria-hidden="true"></span>' : ""}</button>`;
      const color = /^#[0-9a-f]{6}$/i.test(config.primary_color) ? config.primary_color : defaults.primary_color;
      this.style.setProperty("--rgh", color);
      this.style.setProperty("--rgh-fg", foregroundFor(color));
      this.add("assistant", loading ? "Đang kết nối với trợ lý…" : config.greeting);
      this.root.querySelector(".fab")!.addEventListener("click", () => this.setOpen(!this.open));
      this.root.querySelector(".close")!.addEventListener("click", () => this.setOpen(false));
      this.root.querySelector(".reset")!.addEventListener("click", () => this.reset());
      this.root.querySelector("form")!.addEventListener("submit", (event) => { event.preventDefault(); void this.send(); });
      const input = this.root.querySelector("textarea")!;
      input.addEventListener("input", () => this.updateComposer());
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); void this.send(); }
      });
      this.root.querySelector(".panel")!.addEventListener("keydown", (event) => {
        if ((event as KeyboardEvent).key === "Escape") this.setOpen(false);
      });
    }

    private setOpen(open: boolean) {
      this.open = open;
      this.root.querySelector(".panel")!.classList.toggle("open", open);
      const fab = this.root.querySelector(".fab") as HTMLButtonElement;
      fab.setAttribute("aria-expanded", String(open));
      fab.setAttribute("aria-label", open ? "Đóng chat" : "Mở chat");
      fab.innerHTML = this.loading ? '<span class="spinner" aria-hidden="true"></span>' : icon(open ? "close" : "chat");
      if (this.unavailable) fab.innerHTML += '<span class="warning-dot" aria-hidden="true"></span>';
      if (open) this.root.querySelector("textarea")?.focus();
      else fab.focus();
    }
    private reset() {
      this.controller?.abort();
      this.controller = null;
      this.conversationId = null;
      this.root.querySelector(".history")!.replaceChildren();
      this.add("assistant", this.config.greeting);
      this.root.querySelector(".status")!.textContent = "";
      this.root.querySelector("textarea")!.disabled = this.unavailable;
      this.updateComposer();
      this.root.querySelector("textarea")!.focus();
    }
    private updateComposer() {
      const input = this.root.querySelector("textarea")!;
      input.style.height = "auto";
      input.style.height = `${Math.min(120, Math.max(44, input.scrollHeight))}px`;
      const button = this.root.querySelector(".composer button") as HTMLButtonElement;
      button.disabled = this.controller ? false : input.disabled || !input.value.trim();
      button.type = this.controller ? "button" : "submit";
      button.setAttribute("aria-label", this.controller ? "Dừng câu trả lời" : "Gửi câu hỏi");
      button.innerHTML = icon(this.controller ? "stop" : "send");
      button.onclick = this.controller ? () => this.controller?.abort() : null;
    }

    private async send() {
      const input = this.root.querySelector("textarea")!;
      const message = input.value.trim();
      if (!message || input.disabled || this.controller) return;
      this.add("user", message);
      input.value = "";
      input.disabled = true;
      const controller = new AbortController();
      this.controller = controller;
      this.updateComposer();
      const answer = this.add("assistant", "");
      answer.innerHTML = '<span class="typing" aria-label="Đang tạo câu trả lời"><i></i><i></i><i></i></span>';
      const status = this.root.querySelector(".status")!;
      status.textContent = "Đang tìm trong tài liệu…";
      let citations: EventPayload[] = [], text = "", complete = false;
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
      try {
        const response = await fetch(`${this.api}${encodeURIComponent(this.key)}/chat`, {
          method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ message, conversation_id: this.conversationId, external_user_id: this.visitorId }), signal: controller.signal,
        });
        if (!response.ok) throw new Error(await this.responseCode(response));
        if (!response.body) throw new Error("CONNECTION");
        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!complete) {
          const { value, done } = await reader.read();
          if (controller.signal.aborted) throw new DOMException("Stopped", "AbortError");
          if (this.controller !== controller) return;
          buffer += decoder.decode(value, { stream: !done });
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() || "";
          if (done && buffer.trim()) frames.push(buffer);
          for (const frame of frames) {
            const event = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim();
            const raw = frame.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
            if (!event || !raw) continue;
            const data = JSON.parse(raw) as EventPayload;
            if (event === "token" && typeof data.text === "string") {
              const history = this.root.querySelector(".history")!;
              const follow = history.scrollHeight - history.scrollTop - history.clientHeight < 100;
              text += data.text;
              answer.textContent = text;
              status.textContent = "";
              if (follow) history.scrollTop = history.scrollHeight;
            }
            if (event === "conversation" && typeof data.conversation_id === "string") this.conversationId = data.conversation_id;
            if (event === "citations") {
              citations = Array.isArray(data.citations) ? data.citations as EventPayload[] : [];
              if (!text) status.textContent = "Đang tạo câu trả lời…";
            }
            if (event === "error") throw new Error(String(data.code || "CONNECTION"));
            if (event === "done") { complete = true; break; }
          }
          if (done) break;
        }
        if (!complete) throw new Error("CHAT_STREAM_INTERRUPTED");
        if (!text) answer.textContent = "Trợ lý chưa trả lời. Vui lòng thử lại.";
        if (citations.length) this.addCitations(answer.parentElement!, citations);
        status.textContent = "";
      } catch (error) {
        if (this.controller !== controller) return;
        if (controller.signal.aborted || (error as Error).name === "AbortError") {
          if (!text) answer.textContent = "Đã dừng.";
          status.textContent = "Đã dừng câu trả lời.";
        } else {
          const friendly = this.messageFor((error as Error).message);
          if (!text) answer.textContent = friendly;
          status.textContent = text ? friendly : "Bạn có thể thử lại.";
        }
      } finally {
        await reader?.cancel().catch(() => {});
        reader?.releaseLock();
        if (this.controller === controller) {
          this.controller = null;
          input.disabled = false;
          this.updateComposer();
          if (this.open) input.focus();
        }
      }
    }

    private add(kind: "user" | "assistant", text: string) {
      const row = document.createElement("div");
      row.className = `message ${kind}`;
      if (kind === "assistant") row.innerHTML = `<span class="avatar">${icon("chat")}</span>`;
      const bubble = document.createElement("div");
      bubble.className = "msg";
      const body = document.createElement("div");
      body.className = "message-text";
      body.textContent = text;
      bubble.append(body); row.append(bubble);
      const history = this.root.querySelector(".history")!;
      history.append(row); history.scrollTop = history.scrollHeight;
      return body;
    }
    private addCitations(bubble: HTMLElement, citations: EventPayload[]) {
      const sources = citations.slice(0, 5);
      const box = document.createElement("details");
      box.className = "citations";
      box.innerHTML = `<summary>Nguồn tham khảo · ${sources.length}${icon("chevron")}</summary>`;
      sources.forEach((citation, index) => {
        const item = document.createElement("div");
        item.className = "citation";
        item.innerHTML = `<div class="citation-title"><b>${this.escape(String(citation.citation_id || `C${index + 1}`))}</b><span>${this.escape(String(citation.document_name || "Tài liệu"))}</span></div>${typeof citation.page === "number" ? `<span class="citation-page">Trang ${citation.page}</span>` : ""}<p class="excerpt">${this.escape(String(citation.excerpt || ""))}</p>`;
        box.append(item);
      });
      bubble.append(box);
    }
    private async responseCode(response: Response) {
      const body = await response.json().catch(() => null);
      return String(body?.error?.code || (response.status === 429 ? "PUBLIC_CHAT_RATE_LIMITED" : "CONNECTION"));
    }
    private messageFor(code: string) {
      const messages: Record<string, string> = {
        EMBED_ORIGIN_NOT_ALLOWED: "Website này chưa được phép sử dụng chatbot.",
        EMBED_CHATBOT_NOT_FOUND: "Chatbot hiện chưa được xuất bản hoặc mã nhúng đã thay đổi.",
        PUBLIC_CHAT_CONCURRENCY_LIMITED: "Chatbot đang bận. Hãy thử lại sau một lát.",
        PUBLIC_CHAT_RATE_LIMITED: "Bạn đang gửi câu hỏi quá nhanh. Hãy thử lại sau.",
        PROVIDER_RATE_LIMITED: "Dịch vụ AI đang giới hạn tốc độ. Hãy thử lại sau.",
        PROVIDER_TIMEOUT: "Trợ lý phản hồi quá lâu. Vui lòng thử lại.",
        PUBLIC_CHAT_TIMEOUT: "Trợ lý phản hồi quá lâu. Vui lòng thử lại.",
        CHAT_STREAM_INTERRUPTED: "Kết nối bị gián đoạn trước khi trả lời xong. Hãy thử lại.",
      };
      return messages[code] || "Hiện chưa thể kết nối tới trợ lý. Vui lòng thử lại.";
    }
    private escape(value: string) {
      const node = document.createElement("span"); node.textContent = value; return node.innerHTML;
    }
  }
  customElements.get("raghub-chatbot") || customElements.define("raghub-chatbot", RaghubChatbot);
  const key = loaderScript?.dataset.chatbotKey;
  if (key && !document.querySelector("raghub-chatbot")) {
    const element = document.createElement("raghub-chatbot");
    element.setAttribute("chatbot-key", key); document.body.append(element);
  }
})();
