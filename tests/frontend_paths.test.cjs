const { test } = require('node:test');
const assert = require('node:assert/strict');
const { runInNewContext } = require('node:vm');
const { readFileSync } = require('node:fs');
const { webcrypto } = require('node:crypto');
const code = readFileSync('frontend/paths.js', 'utf8');

for (const prefix of ['', '/harness']) {
  test(`URLs and UUID fallback at ${prefix || 'root'}`, () => {
    const context = {
      URL, Uint8Array,
      document: { currentScript: { src: `http://public.example${prefix}/static/paths.js` } },
      location: { origin: 'http://public.example', pathname: `${prefix}/connectors/baidu-netdisk` },
      crypto: { getRandomValues: a => webcrypto.getRandomValues(a) }, window: {},
    };
    runInNewContext(code, context);
    const helper = context.window.HarnessURLs;
    for (const path of ['/api/v1/health', '/api/local/agent-runtime/sessions/id/messages', '/api/v1/artifacts/id/content?download=true', '/docs', '/']) {
      assert.equal(helper.url(path), prefix + path);
    }
    for (const path of ['https://other.example/', '//other.example/', '/\\other.example/', 'relative']) {
      assert.throws(() => helper.url(path));
    }
    if (prefix) assert.throws(() => helper.url('/../api'));
    const ids = new Set(Array.from({ length: 100 }, () => helper.requestId()));
    assert.equal(ids.size, 100);
    for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
}
