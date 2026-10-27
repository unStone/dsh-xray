import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./worker.mjs', import.meta.url));

test('one-shot worker rejects multiple request documents', () => {
  const input = ['first', 'second'].map(requestId =>
    JSON.stringify({version: 1, operation: 'ping', requestId})).join('\n');
  const run = spawnSync(process.execPath, [script], {input, encoding: 'utf8'});
  assert.equal(run.status, 0, run.stderr);
  const response = JSON.parse(run.stdout);
  assert.equal(typeof response.error, 'string');
  assert.equal(response.result, undefined);
});

test('one JSON request preserves Unicode line separators inside source', () => {
  const run = spawnSync(process.execPath, [script], {encoding: 'utf8', input: JSON.stringify({
    version: 1, requestId: 'unicode-source', entries: [], candidates: [], nonRuntimePaths: [],
    files: {'index.js': '// \u2028 \u2029\nexport function apply(ctx) { ctx.tools.register({}); }'},
  })});
  assert.equal(run.status, 0, run.stderr);
  const response = JSON.parse(run.stdout);
  assert.equal(response.requestId, 'unicode-source');
  assert.equal(response.result.registrations.length, 1);
});
