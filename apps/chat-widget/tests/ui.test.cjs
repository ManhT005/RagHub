const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { stripTypeScriptTypes, createRequire } = require('node:module');
const adminRequire = createRequire(`${__dirname}/../../admin-web/package.json`);
const { JSDOM } = adminRequire('jsdom');
const source = stripTypeScriptTypes(readFileSync(`${__dirname}/../src/raghub.ts`, 'utf8'));
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const tick = () => new Promise(resolve => setImmediate(resolve));
async function setup(chat, overrides = {}) {
  const dom = new JSDOM('<body></body>', { url: 'http://host.example/', runScripts: 'outside-only' });
  const { window } = dom;
  Object.assign(window, { TextDecoder, AbortController, ReadableStream });
  Object.defineProperty(window.document, 'currentScript', { value: {
    src: 'http://192.168.1.50:8080/widget/raghub.js', dataset: { chatbotKey: 'rgh_test' },
  }});
  const requests = [];
  window.fetch = async (url, options) => {
    requests.push({ url, options });
    return options ? chat(options) : { ok: true, json: async () => ({
      primary_color: '#8faaf6', title: 'Trợ lý tài liệu', greeting: 'Xin chào!', ...overrides,
    }) };
  };
  window.eval(source);
  await tick();
  const widget = window.document.querySelector('raghub-chatbot');
  const root = widget.shadowRoot;
  root.querySelector('.fab').click();
  return { dom, window, widget, root, requests };
}
function response(text) {
  return { ok: true, body: new ReadableStream({ start(controller) {
    const bytes = new TextEncoder().encode(text);
    // Split within Vietnamese UTF-8 to exercise the incremental decoder.
    for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7));
    controller.close();
  } }) };
}
function ask(root, window) {
  const input = root.querySelector('textarea');
  input.value = 'Câu hỏi\nnhiều dòng';
  input.dispatchEvent(new window.Event('input'));
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
}
test('SSE text is rendered without exposing source details in the public widget', async () => {
  const citations = Array.from({ length: 7 }, (_, i) => ({
    citation_id: `C${i + 1}`, document_name: '<img src=x onerror=alert(1)> Tài liệu rất dài',
    page: i + 1, excerpt: 'Trích đoạn an toàn', score: 0.8, chunk_id: 'private-uuid',
  }));
  const { dom, root, window, requests } = await setup(() => response(
    frame('conversation', { conversation_id: 'conversation-1' }) +
    frame('citations', { citations }) + frame('token', { text: 'Câu trả lời tiếng Việt.' }) + frame('done', {})
  ));
  ask(root, window);
  await tick(); await tick();
  assert.equal(root.querySelectorAll('.typing').length, 0);
  assert.match(root.textContent, /Câu trả lời tiếng Việt/);
  assert.equal(root.querySelector('details'), null);
  assert.doesNotMatch(root.textContent, /Tài liệu rất dài|Trang 1|private-uuid|0\.8/);
  assert.equal(requests[1].url, 'http://192.168.1.50:8080/api/v1/public/chatbots/rgh_test/chat');
  root.querySelector('.reset').click();
  assert.equal(root.querySelectorAll('.message').length, 1);
  ask(root, window); await tick(); await tick();
  assert.equal(JSON.parse(requests[2].options.body).conversation_id, null);
  dom.window.close();
});
test('composer preserves Shift+Enter and IME, exposes stop and reset cancels old streams', async () => {
  const { dom, root, window, widget } = await setup(options => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new window.DOMException('Stopped', 'AbortError')));
  }));
  const input = root.querySelector('textarea');
  input.value = 'Xin chào';
  input.dispatchEvent(new window.Event('input'));
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true }));
  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }));
  assert.equal(widget.controller, null);
  ask(root, window);
  assert.equal(root.querySelector('.composer button').getAttribute('aria-label'), 'Dừng câu trả lời');
  root.querySelector('.reset').click();
  await tick();
  assert.equal(root.querySelectorAll('.message').length, 1);
  assert.equal(root.querySelector('.status').textContent, '');
  assert.equal(input.disabled, false);
  assert.equal(root.querySelector('.composer button').getAttribute('aria-label'), 'Gửi câu hỏi');
  dom.window.close();
});
for (const [code, text] of [
  ['PUBLIC_CHAT_CONCURRENCY_LIMITED', 'Chatbot đang bận'],
  ['PROVIDER_TIMEOUT', 'phản hồi quá lâu'],
  ['PROVIDER_RATE_LIMITED', 'Dịch vụ AI đang giới hạn'],
  ['EMBED_ORIGIN_NOT_ALLOWED', 'Website này chưa được phép'],
]) test(`friendly error for ${code} without upstream details`, async () => {
  const { dom, root, window } = await setup(() => response(frame('error', { code, message: 'upstream-secret' })));
  ask(root, window); await tick(); await tick();
  assert.match(root.textContent, new RegExp(text));
  assert.doesNotMatch(root.textContent, /upstream-secret/);
  assert.equal(root.querySelector('textarea').disabled, false);
  dom.window.close();
});
test('safe theme fallback and accessible light foreground', async () => {
  const light = await setup(() => response(''), { primary_color: '#ffffff' });
  assert.equal(light.widget.style.getPropertyValue('--rgh-fg'), '#000000');
  light.dom.window.close();
  const unsafe = await setup(() => response(''), { primary_color: '#fff;}button{display:none}' });
  assert.equal(unsafe.widget.style.getPropertyValue('--rgh'), '#1463ff');
  assert.equal(unsafe.root.querySelector('.fab').getAttribute('aria-expanded'), 'true');
  unsafe.root.querySelector('.close').click();
  assert.equal(unsafe.root.querySelector('.fab').getAttribute('aria-expanded'), 'false');
  unsafe.dom.window.close();
});
