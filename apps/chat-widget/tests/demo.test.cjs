const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const source = readFileSync(`${__dirname}/../demo/index.html`, 'utf8')
  .match(/<script>([\s\S]+?)<\/script>/)[1];

for (const [name, origin, pathname, query, expected] of [
  ['gateway domain', 'https://raghub.example.com', '/demo/', '', 'https://raghub.example.com'],
  ['local demo', 'http://localhost:8081', '/', '', 'http://localhost:8080'],
  ['custom gateway', 'http://localhost:18081', '/', '&api=http://localhost:18080', 'http://localhost:18080'],
]) {
  test(`demo loads the widget from ${name}`, () => {
    const nodes = { '#key': {}, '#status': {}, '#load': {} };
    let script;
    let historyUrl;
    vm.runInNewContext(source, {
      URL, URLSearchParams, Date,
      location: { origin, pathname, search: `?key=rgh_test${query}` },
      document: {
        querySelector: selector => nodes[selector] || null,
        createElement: () => ({ dataset: {} }),
        body: { append: element => { script = element; } },
      },
      history: { replaceState: (_, __, url) => { historyUrl = url; } },
    });
    nodes['#load'].onclick();
    assert.equal(new URL(script.src).origin, expected);
    assert.equal(new URL(script.src).pathname, '/widget/raghub.js');
    assert.equal(script.dataset.chatbotKey, 'rgh_test');
    assert.equal(script.charset, 'utf-8');
    assert.equal(new URLSearchParams(historyUrl).has('key'), false);
    if (query) assert.equal(new URLSearchParams(historyUrl).get('api'), expected);
  });
}

test('demo reads show-once keys from the fragment and clears them after loading', () => {
  const nodes = { '#key': {}, '#status': {}, '#load': {} };
  let script, historyUrl;
  vm.runInNewContext(source, {
    URL, URLSearchParams, Date,
    location: { origin: 'https://raghub.example.com', pathname: '/demo/', search: '', hash: '#key=rgh_once&api=https%3A%2F%2Fraghub.example.com' },
    document: {
      querySelector: selector => nodes[selector] || null,
      createElement: () => ({ dataset: {} }), body: { append: value => { script = value; } },
    },
    history: { replaceState: (_, __, value) => { historyUrl = value; } },
  });
  nodes['#load'].onclick();
  assert.equal(script.dataset.chatbotKey, 'rgh_once');
  assert.equal(historyUrl.includes('rgh_once'), false);
});
