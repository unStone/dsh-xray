import { posix } from 'node:path';

export const CONTEXT = 1;
export const TOOLS = 2;
export const REGISTER = 4;
export const FACTORY = 8;
export const UNKNOWN = 16;

function moduleFor(filename, specifier, modules) {
  if (!specifier.startsWith('.')) return null;
  const base = posix.normalize(posix.join(posix.dirname(filename), specifier));
  const candidates = [base, ...['.js', '.mjs', '.cjs', '.ts', '.tsx', '.vue', '.svelte'].map(e => `${base}${e}`),
    ...['index.js', 'index.mjs', 'index.ts', 'index.tsx'].map(e => `${base}/${e}`)];
  if (/\.[mc]?js$/.test(base)) candidates.push(base.replace(/\.[mc]?js$/, '.ts'));
  return candidates.map(p => modules.get(p)).find(Boolean);
}

export class Bindings {
  constructor(graph) {
    this.graph = graph;
    this.roles = new Map();
    this.changed = false;
  }

  bind(pattern, role) {
    if (!pattern) return;
    if (pattern.type === 'binding' && pattern.id != null) {
      const value = role || (this.roles.has(pattern.id) ? UNKNOWN : 0);
      const merged = (this.roles.get(pattern.id) ?? 0) | value;
      if (merged && merged !== this.roles.get(pattern.id)) {
        this.roles.set(pattern.id, merged);
        this.changed = true;
      }
    }
    if (pattern.type === 'object') for (const entry of pattern.properties) {
      const value = entry.key === 'tools' && role === CONTEXT ? TOOLS
        : entry.key === 'register' && role === TOOLS ? REGISTER
          : entry.key == null && [CONTEXT, TOOLS].includes(role) ? UNKNOWN : 0;
      this.bind(entry.value, value);
    }
  }

  role(value, seen = new Set(), position = value?.position) {
    if (!value) return 0;
    if (value.type === 'identifier') {
      if (value.id == null || seen.has(value.id)) return 0;
      const binding = this.graph.bindings[value.id];
      if (binding.violations.some(v => v.position <= position || v.fn !== value.fn)) return UNKNOWN;
      const assigned = this.roles.get(value.id);
      if (assigned) return [CONTEXT, TOOLS, REGISTER, FACTORY].includes(assigned) ? assigned : UNKNOWN;
      if (binding.imported && /^(@deepseek-ai\/|@dsh\/|cordis$)/.test(binding.imported.source) &&
          ['defineTool', 'registerTool'].includes(binding.imported.name)) return FACTORY;
      return this.role(binding.init, new Set(seen).add(value.id), position);
    }
    if (value.type === 'member') {
      const parent = this.role(value.object, seen, position);
      if (parent === UNKNOWN || (parent === CONTEXT && !value.key)) return UNKNOWN;
      if (parent === CONTEXT && value.key === 'tools') return TOOLS;
      if (parent === TOOLS && value.key === 'register') return REGISTER;
    }
    if (value.type === 'unknown-projection') return this.role(value.object, seen, position) ? UNKNOWN : 0;
    if (value.type === 'call') {
      const callee = value.callee;
      if (callee?.type === 'member' && callee.key === 'get' && this.role(callee.object, seen, position) === CONTEXT) {
        if (value.args[0]?.type === 'string' && value.args[0].value === 'tools') return TOOLS;
        if (value.args[0]?.type !== 'string') return UNKNOWN;
      }
      if (callee?.type === 'member' && callee.key === 'bind' &&
          this.role(callee.object, seen, position) === REGISTER &&
          this.role(value.args[0], seen, position) === TOOLS) return REGISTER;
    }
    if (value.type === 'choice') {
      const left = this.role(value.left, seen, position);
      const right = this.role(value.right, seen, position);
      return left === right ? left : left || right ? UNKNOWN : 0;
    }
    return 0;
  }

  importedTarget(binding, name, seen) {
    const source = moduleFor(binding.imported.owner, binding.imported.source, this.graph.modules);
    return this.target(source?.exports.get(name), seen);
  }

  target(value, seen = new Set()) {
    if (!value) return null;
    if (value.type === 'function') return value.id;
    if (value.type === 'identifier') {
      if (value.id == null || seen.has(value.id)) return null;
      const binding = this.graph.bindings[value.id];
      if (!binding.constant) return null;
      seen = new Set(seen).add(value.id);
      if (binding.imported && !binding.imported.namespace) return this.importedTarget(binding, binding.imported.name, seen);
      return this.target(binding.init, seen);
    }
    if (value.type === 'member' && value.object?.type === 'identifier' && value.object.id != null) {
      const binding = this.graph.bindings[value.object.id];
      if (binding.imported?.namespace) return this.importedTarget(binding, value.key, seen);
    }
    return null;
  }
}
