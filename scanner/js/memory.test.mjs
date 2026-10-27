import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

test('large repositories retain compact summaries rather than all syntax trees', { timeout: 120000 }, () => {
  const padding = Array.from({ length: 450 }, (_, i) =>
    `export const value${i} = {label: "padding", values: [1,2,3,4,5,6], meta: {enabled: true}};`).join('\n');
  const files = Object.fromEntries(Array.from({ length: 597 }, (_, i) => [`data/file${i}.js`, padding]));
  files['large.js'] = Array.from({ length: 10000 }, (_, i) =>
    `export const large${i} = {label:"padding",values:[1,2,3,4,5,6],meta:{enabled:true}};`).join('\n');
  files['index.js'] = 'import {mount} from "./helper.js"; export function apply(ctx) { mount(ctx); }';
  files['helper.js'] = 'export function mount(host) { const tools = host.tools; tools.register({name:"real"}); }';
  const run = spawnSync(process.execPath, ['--max-old-space-size=512', '--expose-gc',
    fileURLToPath(new URL('./worker.mjs', import.meta.url))], {
    input: JSON.stringify({ version: 1, requestId: 'memory-regression', files, entries: [], candidates: [], nonRuntimePaths: [] }) + '\n',
    encoding: 'utf8', timeout: 110000, maxBuffer: 1024 * 1024,
  });
  assert.equal(run.status, 0, run.stderr.slice(-2000));
  const response = JSON.parse(run.stdout);
  assert.equal(response.requestId, 'memory-regression');
  assert.equal(response.error, undefined);
  assert.equal(response.result.registrations.length, 1);
  assert.equal(response.result.registrations[0].path, 'helper.js');
  assert.deepEqual(response.result.diagnostics, []);
});
