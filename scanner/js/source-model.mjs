import { parseSource, traverse } from './source-parser.mjs';

function property(path) {
  if (!path?.node) return null;
  if (!path.node.computed && path.node.property?.type === 'Identifier') return path.node.property.name;
  return path.node.property?.type === 'StringLiteral' ? path.node.property.value : null;
}

function objectKey(node) {
  if (node.computed) return node.key.type === 'StringLiteral' ? node.key.value : null;
  return node.key.name ?? node.key.value;
}

function projection(pattern, name, keys = []) {
  if (pattern.isIdentifier({ name })) return keys;
  if (pattern.isAssignmentPattern()) return projection(pattern.get('left'), name, keys);
  if (pattern.isObjectPattern()) {
    for (const entry of pattern.get('properties')) {
      if (!entry.isObjectProperty()) continue;
      const key = objectKey(entry.node);
      const result = projection(entry.get('value'), name, [...keys, key]);
      if (result) return result;
    }
  }
  return null;
}

function compile(filename, source, graph) {
  const model = { filename, exports: new Map(), entries: [], calls: [] };
  const bindingIds = new WeakMap();
  const functionIds = new WeakMap();

  function fn(path) {
    if (!path?.node) return null;
    if (functionIds.has(path.node)) return functionIds.get(path.node);
    const id = graph.functions.length;
    const record = { params: [], name: path.node.id?.name ?? null };
    graph.functions.push(record);
    functionIds.set(path.node, id);
    record.params = path.get('params').map(pattern);
    return id;
  }

  function binding(path) {
    const value = path.scope.getBinding(path.node.name);
    if (!value) return null;
    if (bindingIds.has(value)) return bindingIds.get(value);
    const id = graph.bindings.length;
    const record = { constant: value.constant, init: null, violations: [], imported: null };
    graph.bindings.push(record);
    bindingIds.set(value, id);
    record.violations = value.constantViolations.map(p => ({ position: p.node.start, fn: fn(p.getFunctionParent()) }));
    if (value.path.isFunction()) record.init = { type: 'function', id: fn(value.path) };
    if (value.path.isVariableDeclarator()) {
      record.init = expression(value.path.get('init'));
      const keys = projection(value.path.get('id'), path.node.name);
      if (keys) for (const key of keys) record.init = { type: 'member', object: record.init, key };
      else record.init = { type: 'unknown-projection', object: record.init };
    }
    if (value.path.isImportSpecifier() || value.path.isImportDefaultSpecifier() || value.path.isImportNamespaceSpecifier()) {
      record.imported = { owner: filename, source: value.path.parentPath.node.source.value,
        name: value.path.isImportDefaultSpecifier() ? 'default'
          : value.path.node.imported?.name ?? value.path.node.imported?.value,
        namespace: value.path.isImportNamespaceSpecifier() };
    }
    return id;
  }

  function pattern(path) {
    if (path.isAssignmentPattern()) return pattern(path.get('left'));
    if (path.isIdentifier()) return { type: 'binding', id: binding(path) };
    if (path.isObjectPattern()) return { type: 'object', properties: path.get('properties')
      .filter(p => p.isObjectProperty()).map(p => ({ key: objectKey(p.node), value: pattern(p.get('value')) })) };
    return null;
  }

  function expression(path) {
    if (!path?.node) return null;
    if (['TSAsExpression', 'TSTypeAssertion', 'TSNonNullExpression', 'ParenthesizedExpression', 'TypeCastExpression'].includes(path.node.type)) {
      return expression(path.get('expression'));
    }
    if (path.isIdentifier()) return { type: 'identifier', id: binding(path), name: path.node.name,
      position: path.node.start, fn: fn(path.getFunctionParent()) };
    if (path.isFunction()) return { type: 'function', id: fn(path) };
    if (path.isStringLiteral()) return { type: 'string', value: path.node.value };
    if (path.isMemberExpression() || path.isOptionalMemberExpression()) return {
      type: 'member', object: expression(path.get('object')), key: property(path) };
    if (path.isCallExpression() || path.isOptionalCallExpression()) {
      const callee = path.get('callee');
      // Only these call results can carry a service in the supported analysis.
      if (!['get', 'bind'].includes(property(callee))) return null;
      return { type: 'call', callee: expression(callee), args: path.get('arguments').map(expression) };
    }
    if (path.isLogicalExpression() || path.isConditionalExpression()) return { type: 'choice',
      left: expression(path.get(path.isLogicalExpression() ? 'left' : 'consequent')),
      right: expression(path.get(path.isLogicalExpression() ? 'right' : 'alternate')) };
    return null;
  }

  let asts;
  try {
    asts = parseSource(source, filename);
  } catch (error) {
    graph.diagnostics.push({ path: filename, line: error.loc?.line ?? 1,
      column: error.loc?.column ?? 0, reason: `Cannot parse source: ${error.message}` });
    return model;
  }
  for (const ast of asts) traverse(ast, {
    Function(path) {
      const id = fn(path);
      if ((path.node.id?.name === 'apply' ||
          (path.parentPath.isVariableDeclarator() && path.parentPath.node.id.name === 'apply')) && !path.getFunctionParent()) {
        model.entries.push({ type: 'function', id });
      }
      if (path.parentPath.isAssignmentExpression()) {
        const left = path.parentPath.get('left');
        const receiver = left.get('object');
        if (property(left) === 'apply' && receiver?.node) {
          const exported = receiver.isIdentifier({ name: 'exports' }) && !receiver.scope.getBinding('exports');
          const moduleExported = property(receiver) === 'exports' && receiver.get('object').isIdentifier({ name: 'module' }) &&
            !receiver.scope.getBinding('module');
          if (exported || moduleExported) model.entries.push({ type: 'function', id });
        }
      }
    },
    'CallExpression|OptionalCallExpression'(path) {
      const raw = path.get('callee');
      if ((raw.isMemberExpression() || raw.isOptionalMemberExpression()) && !['register', 'inject'].includes(property(raw))) {
        const object = raw.get('object');
        const imported = object.isIdentifier() && object.scope.getBinding(object.node.name);
        if (!imported?.path?.isImportNamespaceSpecifier()) return;
      }
      const callee = expression(raw);
      if (!callee) return;
      const args = path.get('arguments').map(expression);
      if (callee.type === 'identifier' && callee.id == null &&
          args.every(arg => !arg || ['string', 'function'].includes(arg.type))) return;
      model.calls.push({ callee, args,
        point: { path: filename, line: path.node.loc.start.line, column: path.node.loc.start.column } });
    },
    ExportNamedDeclaration(path) {
      const declaration = path.get('declaration');
      if (declaration.isFunctionDeclaration()) model.exports.set(declaration.node.id.name, expression(declaration));
      if (declaration.isVariableDeclaration()) for (const entry of declaration.get('declarations')) {
        const value = expression(entry.get('init'));
        if (value && entry.get('id').isIdentifier()) model.exports.set(entry.node.id.name, value);
      }
      for (const specifier of path.get('specifiers')) {
        if (specifier.isExportSpecifier()) model.exports.set(specifier.node.exported.name ?? specifier.node.exported.value, expression(specifier.get('local')));
      }
    },
    ExportDefaultDeclaration(path) {
      const value = path.get('declaration');
      model.exports.set('default', expression(value));
      if (value.isFunction() && value.node.id?.name === 'apply') model.entries.push(expression(value));
      if (value.isObjectExpression()) for (const entry of value.get('properties')) {
        if (entry.node.key && objectKey(entry.node) === 'apply') {
          model.entries.push(expression(entry.isObjectMethod() ? entry : entry.get('value')));
        }
      }
    },
  });
  const exported = model.exports.get('apply');
  if (exported) model.entries.push(exported);
  return model;
}

export function sourceModel(files) {
  const graph = { modules: new Map(), bindings: [], functions: [], diagnostics: [] };
  for (const [filename, source] of Object.entries(files).filter(([path]) => /\.(ts|tsx|js|mjs|cjs|vue|svelte)$/.test(path))
    .sort(([a], [b]) => a.localeCompare(b))) {
    graph.modules.set(filename, compile(filename, source, graph));
    // No Babel objects escape compile(). Drop traversal caches before the next file.
    traverse.cache.clear();
    if (globalThis.gc && process.memoryUsage().heapUsed > 256 * 1024 * 1024) globalThis.gc();
  }
  return graph;
}
