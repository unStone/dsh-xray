# dsh-xray — capability cards for DeepSeek Harness plugins

**What a dsh plugin declares vs. what its code actually does — with file:line evidence.**

给每个 dsh 插件拍一张 X 光片:声明了什么,代码实际在做什么。

[![scan](https://github.com/unStone/dsh-xray/actions/workflows/scan.yml/badge.svg)](https://github.com/unStone/dsh-xray/actions/workflows/scan.yml)
[![plugins scanned](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Funstone.github.io%2Fdsh-xray%2Fdata.json&query=%24.scanned&label=plugins%20scanned&color=blue)](https://unstone.github.io/dsh-xray/registry.html)
[![license](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

**[🔍 Registry](https://unstone.github.io/dsh-xray/registry.html)** ·
**[📊 Report](https://unstone.github.io/dsh-xray/report.html)** ·
**[📈 Levels explained](https://unstone.github.io/dsh-xray/levels.html)** ·
**[📖 How dsh plugins work](https://unstone.github.io/dsh-xray/report.html?doc=plugins)**

English / 简体中文 / 日本語

> **91%** of scanned plugins carry a powerful capability surface · **77%** patch the dsh runtime itself · **4,000+** plugins scanned, refreshed daily

## Why

The `dsh-plugin` ecosystem went from ~200 to **7,000+ repos in 30 days**. Plugins run arbitrary code inside your agent runtime: they can rewrite your system prompt (`system-prompt/assemble`), intercept every API call (`api/gate`), spawn subprocesses, read `GITHUB_TOKEN` from your env, and even **patch the runtime itself** (`manifest.bundle.patch`). Today nothing surfaces any of that before you install.

dsh-xray statically scans every plugin in the ecosystem and publishes a **capability card**:

| Dimension | Examples |
|---|---|
| Declared surface | `manifest`, injected services, registered tools, hooks |
| Powerful capabilities | `systemPrompt` / `apiProxy` / `subprocess` injection, `tools/pre-execute` gate, runtime patches |
| Sensitive behavior | `exec` / `eval` / base64 decode in shipped code, install-time scripts, outbound domains, credential-like env reads |
| Transparency gaps | capability used in code but absent from the manifest |

Every flag carries **file:line evidence**. Levels **C0–C3** measure capability surface and transparency — *not* maliciousness. A C3 plugin can be perfectly legitimate; you just deserve to know before it touches your agent.

## Capability levels

[![capability levels](https://unstone.github.io/dsh-xray/og.png)](https://unstone.github.io/dsh-xray/levels.html)

**C0** no notable surface · **C1** ordinary (tools, services, outbound domains) ·
**C2** powerful: prompt surface, API interception, subprocess, exec, credential reads or
install scripts · **C3** powerful capability combined with sensitive behavior.

Levels measure **capability surface and transparency, not maliciousness**. A C3 plugin can
be entirely legitimate — a desktop shell genuinely needs subprocesses.
[See the levels explained visually](https://unstone.github.io/dsh-xray/levels.html).

## Badge

Plugin authors: show users your capability card.

```markdown
[![dsh-xray](https://img.shields.io/endpoint?url=https%3A%2F%2Funstone.github.io%2Fdsh-xray%2Fbadge%2F<owner>__<repo>.json)](https://unstone.github.io/dsh-xray/registry.html#<owner>__<repo>)
```

## Run it yourself

```bash
python scanner/discover.py 3        # top repos via topic:dsh-plugin (needs gh auth)
cd scanner && python pipeline.py 200 8   # tarball-download + scan, no git clone
```

Outputs: `data/scans/*.json` (full cards), `docs/data.json` (site data), `docs/badge/*.json` (shields endpoints).

A daily GitHub Action (`.github/workflows/scan.yml`) refreshes everything. Pushing that file needs the `workflow` OAuth scope:

```bash
gh auth refresh -s workflow && git -C . add .github/workflows/scan.yml && git commit -m "ci: daily scan" && git push
```

## Methodology & fair play

- Static analysis only; nothing is executed.
- Shipped code and test/dev code are classified separately; risk flags fire on shipped code only.
- False positive? [Open an issue](https://github.com/unStone/dsh-xray/issues) — cards link evidence so disputes are checkable, and rules get fixed in public.

## Roadmap

- [ ] Full-ecosystem coverage (6.9k repos) + daily diff feed ("what changed in plugins you use")
- [ ] `cordis.patch.yml` runtime-patch audit view
- [ ] Install-gate companion plugin: block/ask on C2+ installs from inside dsh
- [ ] Multi-harness: Abu-Cowork & Claude Code plugin formats
- [ ] Private registry / org policy engine (enterprise)

Apache-2.0
