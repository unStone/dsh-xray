import { sourceModel } from './source-model.mjs';
import { Bindings, CONTEXT, TOOLS, REGISTER, FACTORY, UNKNOWN } from './tool-bindings.mjs';

function maybeTools(value, bindings) {
  if (value?.type !== 'member' || value.key !== 'register') return false;
  const receiver = value.object;
  if (bindings.role(receiver) === UNKNOWN || (receiver?.type === 'identifier' && receiver.name === 'tools')) return true;
  if (receiver?.type === 'member') return receiver.key === 'tools' ||
    (!receiver.key && bindings.role(receiver.object) === CONTEXT);
  return receiver?.type === 'call' && receiver.callee?.type === 'member' &&
    receiver.callee.key === 'get' && bindings.role(receiver.callee.object) === CONTEXT;
}

export function toolRegistrations(files) {
  const graph = sourceModel(files);
  const bindings = new Bindings(graph);
  for (const model of graph.modules.values()) for (const entry of model.entries) {
    const target = bindings.target(entry);
    if (target != null) bindings.bind(graph.functions[target].params[0], CONTEXT);
  }
  do {
    bindings.changed = false;
    for (const model of graph.modules.values()) for (const call of model.calls) {
      const callee = call.callee;
      if (callee.type === 'member' && callee.key === 'inject' && bindings.role(callee.object) === CONTEXT) {
        const callback = bindings.target(call.args.at(-1));
        if (callback != null) bindings.bind(graph.functions[callback].params[0], CONTEXT);
      }
      const target = bindings.target(callee);
      if (target != null) call.args.forEach((argument, i) =>
        bindings.bind(graph.functions[target].params[i], bindings.role(argument)));
    }
  } while (bindings.changed);

  const registrations = [];
  const diagnostics = graph.diagnostics;
  for (const model of graph.modules.values()) for (const call of model.calls) {
    const role = bindings.role(call.callee);
    if (role === REGISTER || role === FACTORY) {
      registrations.push({ ...call.point, reason: role === REGISTER ? 'tools.register' : 'tool factory' });
    } else if (maybeTools(call.callee, bindings)) {
      diagnostics.push({ ...call.point, reason: 'Cannot establish the tools service binding' });
    } else if (call.callee.type === 'identifier' && bindings.target(call.callee) == null &&
        call.args.some(argument => [CONTEXT, TOOLS].includes(bindings.role(argument)))) {
      diagnostics.push({ ...call.point, reason: 'Context or tools service passed to an unresolved helper' });
    }
  }
  const unique = items => [...new Map(items.map(item => [`${item.path}:${item.line}:${item.column}`, item])).values()]
    .sort((a, b) => a.path.localeCompare(b.path) || a.line - b.line || a.column - b.column);
  return { registrations: unique(registrations), diagnostics: unique(diagnostics) };
}
