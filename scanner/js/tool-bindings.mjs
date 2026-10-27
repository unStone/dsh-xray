import { posix } from 'node:path';

export const CONTEXT = 1;
export const TOOLS = 2;
export const REGISTER = 4;
export const FACTORY = 8;
export const UNKNOWN = 16;

export function property(path) {
  const node = path?.node;
  if (!node) return null;
  if (!node.computed && node.property?.type === 'Identifier') return node.property.name;
  return node.property?.type === 'StringLiteral' ? node.property.value : null;
}

export function member(path) {
  return path?.isMemberExpression() || path?.isOptionalMemberExpression();
}

function unwrap(path) {
  while (path?.node && ['TSAsExpression', 'TSTypeAssertion', 'TSNonNullExpression',
    'ParenthesizedExpression', 'TypeCastExpression'].includes(path.node.type)) path = path.get('expression');
  return path;
}

export function moduleFor(filename, specifier, modules) {
  if (!specifier.startsWith('.')) return null;
  const base = posix.normalize(posix.join(posix.dirname(filename), specifier));
  const candidates = [base, ...['.js', '.mjs', '.cjs', '.ts', '.tsx', '.vue', '.svelte'].map(e => `${base}${e}`),
    ...['index.js', 'index.mjs', 'index.ts', 'index.tsx'].map(e => `${base}/${e}`)];
  if (/\.[mc]?js$/.test(base)) candidates.push(base.replace(/\.[mc]?js$/, '.ts'));
  return candidates.map(p => modules.get(p)).find(Boolean);
}

export class Bindings {
  constructor(modules) {
    this.modules = modules;
    this.roles = new Map();
    this.changed = false;
  }

  add(binding, role) {
    if (!binding || !role) return;
    const value = (this.roles.get(binding) ?? 0) | role;
    if (value !== this.roles.get(binding)) {
      this.roles.set(binding, value);
      this.changed = true;
    }
  }

  bind(pattern, role) {
    if (pattern?.isAssignmentPattern()) return this.bind(pattern.get('left'), role);
    if (pattern?.isIdentifier()) {
      const binding = pattern.scope.getBinding(pattern.node.name);
      this.add(binding, role || (this.roles.has(binding) ? UNKNOWN : 0));
    }
    if (pattern?.isObjectPattern()) {
      for (const entry of pattern.get('properties')) {
        if (!entry.isObjectProperty()) continue;
        const name = entry.node.computed ? entry.node.key.value : entry.node.key.name ?? entry.node.key.value;
        const value = name === 'tools' && role === CONTEXT ? TOOLS
          : name === 'register' && role === TOOLS ? REGISTER : 0;
        this.bind(entry.get('value'), value);
      }
    }
  }

  role(path, seen = new Set(), position = path?.node?.start) {
    path = unwrap(path);
    if (!path?.node) return 0;
    if (path.isIdentifier()) {
      const binding = path.scope.getBinding(path.node.name);
      if (!binding || seen.has(binding)) return 0;
      if (binding.constantViolations.some(p => p.node.start <= position || p.getFunctionParent() !== path.getFunctionParent())) return UNKNOWN;
      seen = new Set(seen).add(binding);
      const assigned = this.roles.get(binding);
      if (assigned) return [CONTEXT, TOOLS, REGISTER, FACTORY].includes(assigned) ? assigned : UNKNOWN;
      if (binding.path.isVariableDeclarator() && binding.path.get('id').isIdentifier()) {
        return this.role(binding.path.get('init'), seen, position);
      }
      return 0;
    }
    if (member(path)) {
      const parent = this.role(path.get('object'), seen, position);
      if (parent === UNKNOWN) return UNKNOWN;
      if (parent === CONTEXT && !property(path)) return UNKNOWN;
      if (parent === CONTEXT && property(path) === 'tools') return TOOLS;
      if (parent === TOOLS && property(path) === 'register') return REGISTER;
      return 0;
    }
    if (path.isCallExpression() || path.isOptionalCallExpression()) {
      const callee = path.get('callee');
      const args = path.get('arguments');
      if (member(callee) && property(callee) === 'get' &&
          this.role(callee.get('object'), seen, position) === CONTEXT) {
        if (args[0]?.isStringLiteral({ value: 'tools' })) return TOOLS;
        if (!args[0]?.isStringLiteral()) return UNKNOWN;
      }
      if (member(callee) && property(callee) === 'bind' &&
          this.role(callee.get('object'), seen, position) === REGISTER &&
          this.role(args[0], seen, position) === TOOLS) return REGISTER;
    }
    if (path.isLogicalExpression() || path.isConditionalExpression()) {
      const left = this.role(path.get(path.isLogicalExpression() ? 'left' : 'consequent'), seen, position);
      const right = this.role(path.get(path.isLogicalExpression() ? 'right' : 'alternate'), seen, position);
      return left === right ? left : left || right ? UNKNOWN : 0;
    }
    return 0;
  }

  target(path, module, seen = new Set()) {
    path = unwrap(path);
    if (!path?.node) return null;
    if (path.isFunction()) return path;
    if (path.isIdentifier()) {
      const binding = path.scope.getBinding(path.node.name);
      if (!binding || seen.has(binding) || !binding.constant) return null;
      seen = new Set(seen).add(binding);
      if (binding.path.isFunction()) return binding.path;
      if (binding.path.isVariableDeclarator()) return this.target(binding.path.get('init'), module, seen);
      if (binding.path.isImportSpecifier() || binding.path.isImportDefaultSpecifier()) {
        const declaration = binding.path.parentPath;
        const imported = moduleFor(module.filename, declaration.node.source.value, this.modules);
        const name = binding.path.isImportDefaultSpecifier() ? 'default'
          : binding.path.node.imported.name ?? binding.path.node.imported.value;
        const exported = imported?.exports.get(name);
        return exported ? this.target(exported, imported, seen) : null;
      }
    }
    if (member(path) && path.get('object').isIdentifier()) {
      const binding = path.scope.getBinding(path.node.object.name);
      if (binding?.path.isImportNamespaceSpecifier()) {
        const imported = moduleFor(module.filename, binding.path.parentPath.node.source.value, this.modules);
        const exported = imported?.exports.get(property(path));
        return exported ? this.target(exported, imported, seen) : null;
      }
    }
    return null;
  }
}
