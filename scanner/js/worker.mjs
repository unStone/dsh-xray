import { createInterface } from 'node:readline';
import { unshippedTooling, validatePath, withPackageTree, packageMembers } from './pack-membership.mjs';
import { toolRegistrations } from './tool-registrations.mjs';

async function analyze(request) {
  if (request.version !== 1) throw new Error(`Unsupported analysis protocol ${request.version}`);
  if (request.operation === 'ping') return { version: 1, node: process.versions.node };
  if (!request.files || Array.isArray(request.files) || typeof request.files !== 'object') throw new Error('files must be an object');
  for (const [path, text] of Object.entries(request.files)) {
    validatePath(path);
    if (typeof text !== 'string') throw new Error(`${path}: source must be text`);
  }
  for (const entry of request.entries ?? []) validatePath(entry.path);
  if (request.operation === 'membership') {
    if (request.root) validatePath(request.root);
    const members = await withPackageTree(request.files, request.entries ?? [],
      async directory => [...await packageMembers(directory, request.root ?? '')].sort());
    return { version: 1, members };
  }
  for (const candidate of request.candidates) {
    if (candidate.root) validatePath(candidate.root);
    candidate.paths.forEach(validatePath);
  }
  const tooling = await unshippedTooling(request.files, request.entries, request.candidates);
  const nonRuntime = new Set([...(request.nonRuntimePaths ?? []), ...tooling]);
  const runtime = toolRegistrations(Object.fromEntries(Object.entries(request.files).filter(([path]) => !nonRuntime.has(path))));
  const development = toolRegistrations(Object.fromEntries(Object.entries(request.files).filter(([path]) => nonRuntime.has(path))));
  return { version: 1, tooling,
    registrations: [...runtime.registrations, ...development.registrations.map(e => ({ ...e, origin: 'dev' }))],
    diagnostics: [...runtime.diagnostics, ...development.diagnostics.map(e => ({ ...e, origin: 'dev' }))] };
}

for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  try {
    const result = await analyze(JSON.parse(line));
    process.stdout.write(`${JSON.stringify({ result })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ error: error.message })}\n`);
  }
}
