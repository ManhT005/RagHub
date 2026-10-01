type EventPayload = Record<string, unknown>;
(() => {
const loaderScript = document.currentScript as HTMLScriptElement | null;

class RaghubChatbot extends HTMLElement {
  private readonly root = this.attachShadow({ mode: 'open' });
  private key = '';
  private readonly api = new URL('/api/v1/public/chatbots/', loaderScript?.src || location.href).toString();
  private conversationId: string | null = null;
  private visitorId = sessionStorage.getItem('raghub-visitor') || crypto.randomUUID();
  private controller: AbortController | null = null;

  connectedCallback() {
    this.key = this.getAttribute('chatbot-key') || '';
    sessionStorage.setItem('raghub-visitor', this.visitorId);
    void this.start();
  }

  private async start() {
    try {
      const response = await fetch(`${this.api}${encodeURIComponent(this.key)}/config`);
      if (!response.ok) throw new Error('CONFIG');
      const config = await response.json() as { primary_color: string; title: string; greeting: string };
      this.render(config);
    } catch { this.render({ primary_color: '#1463ff', title: 'RagHub Assistant', greeting: 'Không thể tải chatbot cho website này.' }, true); }
  }

  private render(config: { primary_color: string; title: string; greeting: string }, unavailable = false) {
    this.root.innerHTML = `<style>
      :host{--rgh:${config.primary_color};font-family:Inter,system-ui,sans-serif;color:#122545;position:fixed;z-index:2147483647;right:20px;bottom:20px;font-size:14px;line-height:1.45}
      *{box-sizing:border-box}.fab{width:58px;height:58px;border:0;border-radius:50%;background:var(--rgh);color:#fff;box-shadow:0 12px 30px #0e3b884d;font-size:24px;cursor:pointer;float:right}.panel{display:none;width:360px;height:min(560px,calc(100vh - 110px));margin-bottom:14px;background:#fff;border:1px solid #dce8fb;border-radius:18px;overflow:hidden;box-shadow:0 22px 60px #12315a2e;flex-direction:column}.panel.open{display:flex}.head{padding:16px 18px;background:var(--rgh);color:white;display:flex;align-items:center;justify-content:space-between}.head b{font-size:15px}.head button{background:none;border:0;color:#fff;font-size:22px;cursor:pointer}.history{flex:1;overflow:auto;padding:16px;background:#f7faff}.msg{max-width:88%;padding:10px 12px;margin:0 0 10px;border-radius:13px;white-space:pre-wrap}.user{margin-left:auto;background:var(--rgh);color:#fff;border-bottom-right-radius:3px}.assistant{background:#fff;border:1px solid #e0e9f6;border-bottom-left-radius:3px}.citations{font-size:12px;margin:-4px 0 12px 0}.citation{display:block;color:#235cc0;text-decoration:none;padding:4px 0}.status{padding:0 16px;color:#607492;font-size:12px}.composer{display:flex;gap:8px;padding:12px;border-top:1px solid #e3edf9}.composer input{min-width:0;flex:1;border:1px solid #c9d9ef;border-radius:10px;padding:10px;color:#122545;font:inherit}.composer button{border:0;border-radius:10px;padding:0 13px;background:var(--rgh);color:#fff;font-weight:700;cursor:pointer}.composer button[disabled]{opacity:.55;cursor:not-allowed}@media(max-width:480px){:host{right:12px;bottom:12px}.panel{width:calc(100vw - 24px);height:calc(100vh - 92px);border-radius:16px}}
    </style><section class="panel"><header class="head"><b>${this.escape(config.title)}</b><button aria-label="Đóng chat">×</button></header><div class="history"><div class="msg assistant">${this.escape(config.greeting)}</div></div><p class="status" aria-live="polite"></p><form class="composer"><input aria-label="Câu hỏi" placeholder="Nhập câu hỏi..." ${unavailable ? 'disabled' : ''}/><button ${unavailable ? 'disabled' : ''}>Gửi</button></form></section><button class="fab" aria-label="Mở chat">◌</button>`;
    const panel = this.root.querySelector('.panel')!;
    this.root.querySelector('.fab')!.addEventListener('click', () => panel.classList.toggle('open'));
    this.root.querySelector('.head button')!.addEventListener('click', () => panel.classList.remove('open'));
    this.root.querySelector('form')!.addEventListener('submit', (event) => { event.preventDefault(); void this.send(); });
  }

  private async send() {
    const input = this.root.querySelector('input')!;
    const message = input.value.trim(); if (!message || this.controller) return;
    this.add('user', message); input.value = ''; input.disabled = true;
    const send = this.root.querySelector('.composer button') as HTMLButtonElement;
    send.textContent = 'Dừng'; send.type = 'button'; send.onclick = () => this.controller?.abort();
    const answer = this.add('assistant', ''); const status = this.root.querySelector('.status')!;
    status.textContent = 'Đang trả lời…'; this.controller = new AbortController(); let citations: EventPayload[] = [];
    try {
      const response = await fetch(`${this.api}${encodeURIComponent(this.key)}/chat`, { method:'POST', headers:{'Content-Type':'application/json',Accept:'text/event-stream'}, body:JSON.stringify({message,conversation_id:this.conversationId,external_user_id:this.visitorId}), signal:this.controller.signal });
      if (!response.ok || !response.body) throw new Error(response.status === 429 ? 'RATE_LIMIT' : 'CONNECTION');
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
      while (true) { const {value,done}=await reader.read(); buffer += decoder.decode(value || new Uint8Array(), {stream:!done}); const frames=buffer.split(/\r?\n\r?\n/); buffer=frames.pop() || ''; for (const frame of frames) { const event=frame.match(/^event:\s*(.+)$/m)?.[1], raw=frame.match(/^data:\s*(.+)$/m)?.[1]; if (!event || !raw) continue; const data=JSON.parse(raw) as EventPayload; if(event==='token') answer.textContent += String(data.text || ''); if(event==='conversation') this.conversationId=String(data.conversation_id); if(event==='citations') citations=Array.isArray(data.citations) ? data.citations as EventPayload[] : []; if(event==='error') throw new Error(String(data.code || 'CONNECTION')); } if(done) break; }
      if (citations.length) this.addCitations(citations);
      status.textContent = '';
    } catch (error) { if ((error as Error).name === 'AbortError') { status.textContent='Đã dừng câu trả lời.'; } else { answer.textContent = this.messageFor((error as Error).message); status.textContent='Bạn có thể thử lại.'; } }
    finally { this.controller=null; input.disabled=false; send.textContent='Gửi'; send.type='submit'; send.onclick=null; input.focus(); }
  }

  private add(kind: 'user'|'assistant', text: string) { const node=document.createElement('div'); node.className=`msg ${kind}`; node.textContent=text; this.root.querySelector('.history')!.append(node); node.scrollIntoView({block:'end'}); return node; }
  private addCitations(citations: EventPayload[]) { const box=document.createElement('div'); box.className='citations'; box.innerHTML='<b>Nguồn tham khảo</b>'; citations.forEach((citation) => { const item=document.createElement('span'); item.className='citation'; item.textContent=`${String(citation.citation_id || 'Nguồn')}: ${String(citation.document_name || '')}${citation.page ? `, trang ${citation.page}` : ''}`; box.append(item); }); this.root.querySelector('.history')!.append(box); }
  private messageFor(code:string) { return code.includes('TIMEOUT') ? 'Hệ thống trả lời quá lâu. Hãy thử lại.' : code.includes('RATE_LIMIT') ? 'Bạn đang gửi câu hỏi quá nhanh. Hãy đợi một lát.' : 'Không thể kết nối đến chatbot.'; }
  private escape(value:string) { const node=document.createElement('span'); node.textContent=value; return node.innerHTML; }
}

customElements.get('raghub-chatbot') || customElements.define('raghub-chatbot', RaghubChatbot);

const key = loaderScript?.dataset.chatbotKey;
if (key && !document.querySelector('raghub-chatbot')) { const element=document.createElement('raghub-chatbot'); element.setAttribute('chatbot-key',key); document.body.append(element); }
})();
