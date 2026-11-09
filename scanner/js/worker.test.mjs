import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./worker.mjs', import.meta.url));

// The worker is a resident process: one JSON request per line in, one JSON
// response per line out. Python drives it strictly sequentially, but the
// protocol tests below go through the same wire format.
function startWorker() {
  const child = spawn(process.execPath, [script]);
  const queued = [];
  const waiters = [];
  createInterface({ input: child.stdout }).on('line', line => {
    const envelope = JSON.parse(line);
    const waiter = waiters.shift();
    if (waiter) waiter(envelope); else queued.push(envelope);
  });
  return {
    child,
    send(line) { child.stdin.write(line + '\n'); },
    next() { return queued.length ? Promise.resolve(queued.shift())
      : new Promise(resolve => waiters.push(resolve)); },
    stop() { child.stdin.end(); return new Promise(resolve => child.on('exit', resolve)); },
  };
}

test('one worker answers sequential requests with correlated ids', async () => {
  const worker = startWorker();
  try {
    worker.send(JSON.stringify({ version: 1, operation: 'ping', requestId: 'first' }));
    worker.send(JSON.stringify({ version: 1, operation: 'ping', requestId: 'second' }));
    const first = await worker.next();
    const second = await worker.next();
    assert.equal(first.requestId, 'first');
    assert.equal(second.requestId, 'second');
    assert.equal(typeof first.result.node, 'string');
  } finally {
    await worker.stop();
  }
});

test('a malformed line answers with an error envelope and the worker survives it', async () => {
  const worker = startWorker();
  try {
    worker.send('not json');
    worker.send(JSON.stringify({ version: 1, operation: 'ping', requestId: 'after-bad' }));
    const failed = await worker.next();
    const healthy = await worker.next();
    assert.equal(typeof failed.error, 'string');
    assert.equal(failed.requestId, null);
    assert.equal(healthy.requestId, 'after-bad');
    assert.ok(healthy.result);
  } finally {
    await worker.stop();
  }
});

test('a failing request envelope carries the error without ending the process', async () => {
  const worker = startWorker();
  try {
    worker.send(JSON.stringify({ version: 2, requestId: 'bad-version' }));
    worker.send(JSON.stringify({ version: 1, operation: 'ping', requestId: 'recovered' }));
    const failed = await worker.next();
    const healthy = await worker.next();
    assert.match(failed.error, /Unsupported analysis protocol/);
    assert.equal(healthy.requestId, 'recovered');
  } finally {
    await worker.stop();
  }
});

test('one JSON request preserves Unicode line separators inside source', () => {
  const run = spawnSync(process.execPath, [script], {encoding: 'utf8', input: JSON.stringify({
    version: 1, requestId: 'unicode-source', entries: [], candidates: [], nonRuntimePaths: [],
    files: {'index.js': '// \u2028 \u2029\nexport function apply(ctx) { ctx.tools.register({}); }'},
  }) + '\n'});
  assert.equal(run.status, 0, run.stderr);
  const response = JSON.parse(run.stdout);
  assert.equal(response.requestId, 'unicode-source');
  assert.equal(response.result.registrations.length, 1);
});
