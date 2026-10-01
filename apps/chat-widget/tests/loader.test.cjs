const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { stripTypeScriptTypes } = require('node:module');
const vm = require('node:vm');

test('loading the script again uses the new key without global redeclarations', async () => {
  const source = stripTypeScriptTypes(readFileSync(`${__dirname}/../src/raghub.ts`, 'utf8'));
  const definitions = new Map();
  const requests = [];
  let widget = null;
  const context = vm.createContext({
    URL, crypto: require('node:crypto').webcrypto,
    location: { href: 'http://localhost:8081/' },
    sessionStorage: { getItem: () => null, setItem() {} },
    HTMLElement: class {
      attributes = {};
      attachShadow() { return {}; }
      setAttribute(name, value) { this.attributes[name] = value; }
      getAttribute(name) { return this.attributes[name]; }
    },
    customElements: {
      get: name => definitions.get(name),
      define(name, type) { type.prototype.render = () => {}; definitions.set(name, type); },
    },
    document: {
      currentScript: { src: 'http://localhost:8080/widget/raghub.js', dataset: { chatbotKey: 'rgh_old' } },
      querySelector: () => widget,
      createElement: name => new (definitions.get(name))(),
      body: { append(element) { widget = element; element.connectedCallback(); } },
    },
    fetch: async url => { requests.push(url); return { ok: true, json: async () => ({}) }; },
  });
  vm.runInContext(source, context);
  widget = null;
  context.document.currentScript.dataset.chatbotKey = 'rgh_new';
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(requests, [
    'http://localhost:8080/api/v1/public/chatbots/rgh_old/config',
    'http://localhost:8080/api/v1/public/chatbots/rgh_new/config',
  ]);
});
