import { parseSource, traverse } from './source-parser.mjs';
import { Bindings, CONTEXT, TOOLS, REGISTER, FACTORY, UNKNOWN, member, property } from './tool-bindings.mjs';

const extensions = /\.(ts|tsx|js|mjs|cjs|vue|svelte)$/;

function evidence(module, path, reason) {
  return { path: module.filename, line: path.node.loc?.start.line ?? 1,
    column: path.node.loc?.start.column ?? 0, reason };
}

function collect(filename, source, diagnostics) {
  const module = { filename, exports: new Map(), functions: [], calls: [], variables: [], imports: [] };
  let asts;
  try {
    asts = parseSource(source, filename);
  } catch (error) {
    diagnostics.push({ path: filename, line: error.loc?.line ?? 1,
      column: error.loc?.column ?? 0, reason: `Cannot parse source: ${error.message}` });
    return module;
  }
  for (const ast of asts) traverse(ast, {
    Function(path) { module.functions.push(path); },
    'CallExpression|OptionalCallExpression'(path) { module.calls.push(path); },
    VariableDeclarator(path) { module.variables.push(path); },
    ImportDeclaration(path) { module.imports.push(path); },
    ExportNamedDeclaration(path) {
      const declaration = path.get('declaration');
      if (declaration.isFunctionDeclaration()) module.exports.set(declaration.node.id.name, declaration);
      if (declaration.isVariableDeclaration()) {
        for (const entry of declaration.get('declarations')) {
          if (entry.get('id').isIdentifier()) module.exports.set(entry.node.id.name, entry.get('init'));
        }
      }
      for (const specifier of path.get('specifiers')) {
        if (specifier.isExportSpecifier()) module.exports.set(specifier.node.exported.name, specifier.get('local'));
      }
    },
    ExportDefaultDeclaration(path) { module.exports.set('default', path.get('declaration')); },
  });
  return module;
}

function contextEntries(module, bindings) {
  const entries = new Set();
  const exported = module.exports.get('apply');
  const apply = bindings.target(exported, module);
  if (apply) entries.add(apply);
  const defaultValue = module.exports.get('default');
  const fn = bindings.target(defaultValue, module);
  if (fn?.node.id?.name === 'apply') entries.add(fn);
  if (defaultValue?.isObjectExpression()) {
    for (const value of defaultValue.get('properties')) {
      if ((value.node.key?.name ?? value.node.key?.value) !== 'apply') continue;
      const method = value.isObjectMethod() ? value : bindings.target(value.get('value'), module);
      if (method) entries.add(method);
    }
  }
  // CommonJS and bundled modules also expose a top-level named apply function.
  for (const fn of module.functions) {
    if (fn.node.id?.name === 'apply' && !fn.getFunctionParent()) entries.add(fn);
    if (fn.parentPath.isVariableDeclarator() && fn.parentPath.node.id.name === 'apply' &&
        !fn.getFunctionParent()) entries.add(fn);
    if (fn.parentPath.isAssignmentExpression()) {
      const left = fn.parentPath.get('left');
      if (member(left) && property(left) === 'apply') {
        const receiver = left.get('object');
        const exported = receiver.isIdentifier({ name: 'exports' }) && !receiver.scope.getBinding('exports');
        const moduleExported = member(receiver) && property(receiver) === 'exports' &&
          receiver.get('object').isIdentifier({ name: 'module' }) && !receiver.scope.getBinding('module');
        if (exported || moduleExported) entries.add(fn);
      }
    }
  }
  return entries;
}

function maybeTools(path, bindings) {
  if (!member(path) || property(path) !== 'register') return false;
  const receiver = path.get('object');
  if (bindings.role(receiver) === UNKNOWN) return true;
  if (receiver.isIdentifier({ name: 'tools' })) return true;
  if (member(receiver)) return property(receiver) === 'tools' ||
    (!property(receiver) && bindings.role(receiver.get('object')) === CONTEXT);
  if (receiver.isCallExpression()) {
    const callee = receiver.get('callee');
    return member(callee) && property(callee) === 'get' && bindings.role(callee.get('object')) === CONTEXT;
  }
  return false;
}

export function toolRegistrations(files) {
  const diagnostics = [];
  const modules = new Map(Object.entries(files).filter(([path]) => extensions.test(path))
    .sort(([a], [b]) => a.localeCompare(b)).map(([path, source]) => [path, collect(path, source, diagnostics)]));
  const bindings = new Bindings(modules);
  for (const module of modules.values()) {
    for (const entry of contextEntries(module, bindings)) bindings.bind(entry.get('params')[0], CONTEXT);
    for (const imported of module.imports) {
      if (!/^(@deepseek-ai\/|@dsh\/|cordis$)/.test(imported.node.source.value)) continue;
      for (const specifier of imported.get('specifiers')) {
        const name = specifier.node.imported?.name;
        if (['defineTool', 'registerTool'].includes(name)) {
          bindings.add(specifier.scope.getBinding(specifier.node.local.name), FACTORY);
        }
      }
    }
  }
  do {
    bindings.changed = false;
    for (const module of modules.values()) {
      for (const variable of module.variables) bindings.bind(variable.get('id'), bindings.role(variable.get('init')));
      for (const call of module.calls) {
        const callee = call.get('callee');
        const args = call.get('arguments');
        if (member(callee) && property(callee) === 'inject' && bindings.role(callee.get('object')) === CONTEXT) {
          const callback = bindings.target(args.at(-1), module);
          if (callback) bindings.bind(callback.get('params')[0], CONTEXT);
        }
        const target = bindings.target(callee, module);
        if (!target) continue;
        const params = target.get('params');
        args.forEach((argument, i) => bindings.bind(params[i], bindings.role(argument)));
      }
    }
  } while (bindings.changed);

  const registrations = [];
  for (const module of modules.values()) {
    for (const call of module.calls) {
      const callee = call.get('callee');
      const role = bindings.role(callee);
      if (role === REGISTER || role === FACTORY) {
        registrations.push(evidence(module, call, role === REGISTER ? 'tools.register' : 'tool factory'));
      } else if (maybeTools(callee, bindings)) {
        diagnostics.push(evidence(module, call, 'Cannot establish the tools service binding'));
      } else if (callee.isIdentifier() && !bindings.target(callee, module) &&
          call.get('arguments').some(argument => [CONTEXT, TOOLS].includes(bindings.role(argument)))) {
        diagnostics.push(evidence(module, call, 'Context or tools service passed to an unresolved helper'));
      }
    }
  }
  const unique = items => [...new Map(items.map(item => [`${item.path}:${item.line}:${item.column}`, item])).values()]
    .sort((a, b) => a.path.localeCompare(b.path) || a.line - b.line || a.column - b.column);
  return { registrations: unique(registrations), diagnostics: unique(diagnostics) };
}
