# How dsh Plugins Actually Work

**The background you need to read a capability card**

*[中文版](plugins.html?lang=zh) · Written for people new to DeepSeek Harness*

---

## The one-sentence version

dsh is built on the principle that everything is a plugin. It sits on the Cordis framework: plugins register services and listen for events on a shared **context object, `ctx`** — and dsh's own core features (sessions, tools, LLM adapters) are written as plugins through that same mechanism.

Which means: **there is no privilege gap between a plugin and the core**. A third-party plugin you install uses exactly the interfaces the official modules use.

---

## What a plugin looks like

The smallest plugin is a module exporting `apply`:

```ts
export const name = 'my-plugin'
export const inject = ['tools', 'sessions']   // services I depend on

export function apply(ctx: Context) {
  ctx.tools.register(/* ... */)
  ctx.on('session/event', (e) => { /* ... */ })
}
```

Three things worth noting:

| Element | What it does | Commonly mistaken for |
|---|---|---|
| `inject` | Declares service dependencies, drives load order | ❌ a permission request |
| `ctx.xxx` | Retrieves a service by key, no import needed | — |
| `ctx.on(...)` | Attaches a hook — to observe, or to rewrite | — |

`inject` is the most important point here: it resolves *what loads first*, **not *what you may do***. Once loaded, a plugin holds every service it declared, with no runtime boundary enforcing anything.

---

## What lives on `ctx`

Services occupy stable namespace keys, and plugins discover each other by key. Some common ones:

| Service | Capability |
|---|---|
| `ctx.tools` | Register tools, intervene in the execution pipeline |
| `ctx.llm` | Model adapters, streaming |
| `ctx.sessions` | The session log |
| `ctx.systemPrompt` | System prompt assembly |
| `ctx.apiProxy` | The API request proxy layer |
| `ctx.subprocess` | Spawning subprocesses |
| `ctx.approval` | Asking the user to confirm |
| `ctx.sandbox` | Sandbox backends (e.g. `dsh-bash-sandbox`) |

The last four are why we mark certain plugins as carrying "powerful capability": they correspond to rewriting what the model sees, sitting between you and the model, and running system commands.

---

## What happens during one exchange

```
turn/start → agent/pre-step → step/start → llm/stream → tool/call* → step/end → turn/end
```

A **step** is one model request plus the tools it calls; a **turn** contains zero or more steps.

Events dispatch in four modes, and the difference matters:

| Mode | Behaviour | What a plugin can do |
|---|---|---|
| `emit` | Fire-and-forget | Observe only |
| `parallel` | Concurrent, awaited | Observe + async side effects |
| `serial` | Sequential, returns values | Influence the result |
| `waterfall` | Middleware chain, wraps values | **Rewrite the data itself** |

`waterfall` is why a plugin can rewrite rather than merely watch. A plugin hooked onto `system-prompt/assemble` can rewrite the prompt before it reaches the model — and nothing in the conversation you see on screen changes.

---

## The session log: everything the model sees

dsh holds one hard invariant: **what the model sees is logged**.

The session log is append-only, and `deriveMessages()` projects the model's history from it. To feed the model anything extra, you must append a record — there is no path around it.

It is a clean design: it keeps "what did the model actually see" permanently auditable. And it is exactly why hooks like `system-prompt/assemble` deserve attention — they are among the few places that shape model input outside that projection.

---

## Permissions: where things actually stand

dsh **does** have a runtime approval mechanism at the tool level:

```ts
ctx.on('tools/pre-execute', () => ({ kind: 'ask', reason: '...' }))
// or { kind: 'deny', reason: '...' }
```

A plugin can hold up a tool call for user confirmation, or refuse it outright. Together with `ctx.approval` and `ctx.sandbox`, the guardrails around tool execution are real.

**Plugin installation has no equivalent.**

When you install a plugin:

- no manifest field describes the capabilities it will use
- there is no permission prompt at install time
- there is no runtime enforcement of a capability boundary
- `manifest.bundle.patch` even lets it patch dsh itself (`cordis.patch.yml`)

So "the plugin exceeded its permissions" does not apply — there are none to exceed. Tool calls are carefully gated, while the step that grants a plugin all of this happens silently.

---

## What a capability card does about it

dsh-xray statically scans each plugin's shipped code and lists the above: which services it takes, which hooks it attaches, whether it patches the runtime, which environment variables it reads, whether it runs anything at install time — each with a file and line number.

That is not a substitute for a permission model. It just puts the information on the table until there is one.

- [Capability levels C0–C3, explained visually](../levels.html)
- [The report: the dsh plugin ecosystem has no permission model](../report.html)
- [Plugin registry](../registry.html)

*Written from dsh's own documentation (architecture, cordis-primer, capability-seams, extension-cookbook) and from scan results. Spotted an error? [Open an issue](https://github.com/unStone/dsh-xray/issues).*
