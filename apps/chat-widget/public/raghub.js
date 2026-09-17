(() => {
    const script = document.currentScript;
    const base = new URL(script.src).origin;
    const key = script.dataset.chatbotKey;
    class RagHubChatbot extends HTMLElement {
        connectedCallback() {
            if (this.shadowRoot) return;
            const root = this.attachShadow({ mode: 'open' });
            root.innerHTML = `<style>:host{position:fixed;bottom:22px;right:22px;z-index:99999;font:14px Arial;color:#234}button{cursor:pointer;background:#187b69;color:white;border:0;padding:13px;border-radius:12px}section{width:min(350px,85vw);background:white;border:1px solid #ddd;border-radius:15px;padding:16px;box-shadow:0 12px 50px #0002;margin-bottom:10px}section[hidden]{display:none}article{height:300px;overflow:auto;white-space:pre-wrap;line-height:1.6}input{padding:12px;width:65%;border:1px solid #ddd;border-radius:7px}p{padding:10px;background:#f1f7f5;border-radius:8px}small{display:block;color:#386}</style><section hidden><h3>RagHub Assistant</h3><article><p>Ask about our documents. Demo: source excerpts, no LLM.</p></article><form><input required maxlength="2000" aria-label="Question" placeholder="Your question..."><button>Send</button></form></section><button class="toggle">Ask RagHub</button>`;
            root.querySelector('.toggle').onclick = () => { const panel = root.querySelector('section'); panel.hidden = !panel.hidden; };
            root.querySelector('form').onsubmit = async e => {
                e.preventDefault(); const input = root.querySelector('input'), button = root.querySelector('form button'), log = root.querySelector('article');
                const message = input.value.trim(); if (!message || button.disabled) return; input.value = ''; button.disabled = true;
                const question = document.createElement('p'); question.textContent = message; log.append(question);
                const answer = document.createElement('p'); log.append(answer);
                try {
                    const response = await fetch(base + '/api/v1/public/chatbots/' + encodeURIComponent(this.getAttribute('chatbot-key')) + '/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) });
                    if (!response.ok) { const error = await response.json(); throw Error(error.error?.message || 'Connection failed'); }
                    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '', citations = [];
                    while (true) { const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); let end; while ((end = buffer.indexOf('\n\n')) >= 0) { const lines = buffer.slice(0, end).split('\n'); buffer = buffer.slice(end + 2); const data = JSON.parse(lines[1].slice(6)); if (lines[0] === 'event: token') answer.append(document.createTextNode(data)); if (lines[0] === 'event: citations') citations = data; log.scrollTop = log.scrollHeight; } }
                    for (const c of citations) { const source = document.createElement('small'); source.textContent = c.source + ' / page ' + c.page; answer.append(source); }
                } catch (error) { answer.textContent = error.message; } finally { button.disabled = false; }
            };
        }
    }
    if (!customElements.get('raghub-chatbot')) customElements.define('raghub-chatbot', RagHubChatbot);
    const el = document.createElement('raghub-chatbot'); el.setAttribute('chatbot-key', key); document.body.append(el);
})();
