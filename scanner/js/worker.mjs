import { createInterface } from 'node:readline';
import { createRequire } from 'node:module';
import { validatePath } from './paths.mjs';

const require = createRequire(import.meta.url);

async function analyze(request) {
  if (request.version !== 1) throw new Error(`Unsupported analysis protocol ${request.version}`);
  if (request.operation === 'ping') {
    for (const name of ['@babel/parser', '@babel/traverse', '@npmcli/arborist',
      'npm-packlist', '@vue/compiler-sfc', 'svelte/compiler']) require.resolve(name);
    return { version: 1, node: process.versions.node };
  }
  if (!request.files || Array.isArray(request.files) || typeof request.files !== 'object') throw new Error('files must be an object');
  for (const [path, text] of Object.entries(request.files)) {
    validatePath(path);
    if (typeof text !== 'string') throw new Error(`${path}: source must be text`);
  }
  for (const entry of request.entries ?? []) validatePath(entry.path);
  if (request.operation === 'membership') {
    const { withPackageTree, packageMembers } = await import('./pack-membership.mjs');
    if (request.root) validatePath(request.root);
    const members = await withPackageTree(request.files, request.entries ?? [],
      async directory => [...await packageMembers(directory, request.root ?? '')].sort());
    return { version: 1, members };
  }
  for (const candidate of request.candidates) {
    if (candidate.root) validatePath(candidate.root);
    candidate.paths.forEach(validatePath);
  }
  const tooling = request.candidates.length
    ? await (await import('./pack-membership.mjs')).unshippedTooling(request.files, request.entries, request.candidates) : [];
  if (!Object.keys(request.files).some(path => /\.(ts|tsx|js|mjs|cjs|vue|svelte)$/.test(path))) {
    return { version: 1, tooling, registrations: [], diagnostics: [] };
  }
  const { toolRegistrations } = await import('./tool-registrations.mjs');
  const nonRuntime = new Set([...(request.nonRuntimePaths ?? []), ...tooling]);
  const runtime = toolRegistrations(Object.fromEntries(Object.entries(request.files).filter(([path]) => !nonRuntime.has(path))));
  const development = toolRegistrations(Object.fromEntries(Object.entries(request.files).filter(([path]) => nonRuntime.has(path))));
  return { version: 1, tooling,
    registrations: [...runtime.registrations, ...development.registrations.map(e => ({ ...e, origin: 'dev' }))],
    diagnostics: [...runtime.diagnostics, ...development.diagnostics.map(e => ({ ...e, origin: 'dev' }))] };
}

for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  let requestId = null;
  try {
    const request = JSON.parse(line);
    requestId = request.requestId;
    const result = await analyze(request);
    process.stdout.write(`${JSON.stringify({ requestId, result })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ requestId, error: error.message })}\n`);
  }
  if (globalThis.gc) globalThis.gc();
}
