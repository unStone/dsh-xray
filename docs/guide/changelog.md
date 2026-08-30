# Changelog

*[中文版](changelog.html?lang=zh) · Scan results refresh daily; this page records changes to method and product*

---

## 2026-08-30 · A pack-check script is not a plugin executing commands

[Issue #4](https://github.com/unStone/dsh-xray/issues/4) reported a plugin rated C3 for `exec` in `scripts/check-pack.mjs` — a script its own `package.json` `files` allowlist keeps out of the published tarball. Installing that plugin never puts the file on disk, so the command it runs is a developer's, not a user's.

The reporter also did the work to show why the obvious fix is wrong, and they were right. Ignoring `scripts/` by name would have hidden [`LBXC-666/dsh-voice-input`](https://github.com/LBXC-666/dsh-voice-input), which explicitly ships `scripts/**/*.mjs` — including a proxy that opens a socket and reads `DASHSCOPE_API_KEY`.

**Two proofs, not one.** A file counts as unshipped tooling only when both hold: it sits at a tooling root (`scripts/`, `tools/`, `bench/`, a root-level `build.mjs`-shaped config), *and* an explicit `files` allowlist proves the package does not contain it. Either signal alone is wrong. The directory name alone hides the `scripts/**/*.mjs` some plugins genuinely ship. Package membership alone is worse: a TypeScript plugin's `src/` is excluded from `files` in favour of the `lib/` it compiles into, and `lib/` is already discounted as build output — demoting both would make the plugin's real behaviour invisible in either place.

**npm's glob semantics, not `fnmatch`'s.** Under minimatch, `**` spans zero or more path segments, so `scripts/**/*.mjs` matches the direct child `scripts/proxy.mjs`. Python's `fnmatch` does not, and that single difference is what turns a fix into a cover-up. The translation — globstar, `*` stopping at `/`, character classes, brace expansion, `main`/`bin`/`directories.bin` force-includes — is checked against `npm pack --dry-run --json` on npm 11, and the resulting table is pinned as a test so CI holds it without needing npm.

**Fail closed.** No `files` allowlist, one pattern we do not model (`!` negations, extglob, `{a..z}` ranges), or an install-time lifecycle script — installing from a git ref runs the checkout, not the tarball — and nothing is demoted.

**Still on the card.** Nothing is hidden: findings report as `exec_tooling`, `eval_tooling`, `base64_decode_tooling`, `net_server_tooling` and `token_env_tooling`, with the same `file:line` evidence, and simply do not count toward the level. A finding that sits in both build output and tooling now reports both, instead of one masking the other.

**What it cost.** 13.6% of scanned cards cite risky behavior at a tooling root. On a 391-plugin sample scanned under both rule sets — same fetched files, so upstream changes cannot be mistaken for a rule change — **22 plugins (5.6%) moved down a level and none moved up**: C3 29%→24%. Within a 248-plugin sample drawn from the affected population, 26% moved down. Env reads and outbound domains found only in unshipped tooling stop counting too, which is why a few plugins drop two levels.

### Also in this release

- **Flag chips had no labels.** 1,381 published cards rendered a raw i18n key — `reg.f.exec_bundled` — where the chip text should be. Every non-counting flag is now labelled in English, Chinese and Japanese.

---

## 2026-08-19 · We audited our own flags, and two rules were wrong

The whole project rests on findings being checkable, so we checked them: a random sample of flags, with the cited source line fetched and read by hand. Two rules were crediting plugins with code they had not written.

**Comments matched.** A plugin whose doc comment read *"this gates the tool-call surface, NOT plugin-internal code (child_process/fetch/eval inside the plugin body)"* scored an `exec` flag — for a sentence explaining that it does not do that. Comments are now blanked before matching, with newlines preserved so cited line numbers still point at the right place.

**Build output was read as authored code.** This was the larger error. 32% of all line-cited flags sat in `lib/` or `dist/` — bundler output containing inlined dependencies. For `eval` it was 44%, for base64 45%. Four of six sampled `eval` flags pointed at the same upstream library, schemastery, which ships with dsh itself: we were marking plugins down for using an official dependency.

Findings in build output now report as `*_bundled` — stated, because it is true that the code is there, but not counted toward the level, because it is not the author's code.

**What it cost.** On a 327-plugin sample, 49 plugins moved down a level: C3 51%→43%, C0 7%→14%, C2+ 90%→81%. Our published figures were overstated by roughly eight points. The report now carries a correction saying so.

### Also in this release

- **Rule tests.** The scanner had none, while a scheduled run re-rated thousands of plugins daily. Ten test groups now pin the rules that decide a level, and CI runs them before scanning.
- **Failure reporting.** A broken scan used to leave the site quietly serving stale data; it now opens an issue.
- **Capability-change feed.** The Atom feed reports plugins whose level moved or that gained a powerful capability, not only newly scanned ones — the case that matters if you already installed something.
- **Scan cards out of git.** 35MB of per-repo cards were rewritten on every run. They live in the CI cache now; a cache miss costs one slower sweep.

---

## 2026-08-18 · First release

### Full ecosystem coverage

GitHub search returns at most 1000 results per query, and the `dsh-plugin` topic holds 7,000+ repositories. Discovery now partitions adaptively — **by star bucket, then by recursively halved creation-date windows** — and enumerates 6,942 repositories (forks and archives excluded).

Downloads moved from the REST API to codeload. Public tarballs need no auth there and do not consume the hourly quota, which a 7,000-repository sweep would otherwise exhaust against CI's 1,000/hour limit.

Scanning is incremental: a repository whose `pushed_at` is unchanged and whose last scan succeeded reuses its cached card, and each run has a fetch budget. After the first full sweep, routine rescans are cheap.

### Two fixes that affected the findings

**Streaming extraction.** A repository-size cap was dropping whole repositories — including a 249MB one containing 555 code files. Switching to streaming extraction (`mode='r|gz'`) with a decompressed-byte budget took skips from 43 down to 19, and the remainder are genuinely code-free repositories.

**Deterministic manifest selection.** A 600-file cap could truncate `package.json` files, so which manifest we reported from a monorepo depended on tar ordering — two scans of the same repository could disagree. `package.json` files are now exempt from the cap, and the shallowest path wins.

That bug briefly invalidated a key example in the report: we had written "declares empty vs. uses 17 services", where the "empty" came from a truncated read of a sub-package manifest. The passage has been rewritten to a checkable version.

### Honesty of reporting

- Download failures and "repository contains no scannable code" shared one error message, which recorded unreached repositories as code-free and overstated coverage. They are now distinct.
- `data.json` publishes a `discovered` count, so the site reports "M scanned of N repositories in the ecosystem" rather than treating "however many cards we hold" as the denominator.

### Content

- The report, *The dsh Plugin Ecosystem Has No Permission Model* (English and Chinese). Figures are injected from scan data by `render_report.py`, so the text tracks the daily scan instead of going stale.
- [Capability levels C0–C3, explained visually](../levels.html)
- [How dsh plugins actually work](plugins.html)
- Landing page, registry and report in English, Chinese and Japanese
- Embeddable capability badges for plugin authors

---

## Planned

- Remaining coverage of the zero-star tail (the daily run converges on its own)
- A `cordis.patch.yml` runtime-patch audit view
- A daily diff feed: what changed in the capability surface of plugins you use
- An install-gate plugin: block or ask on C2+ installs
- Multi-harness support (Abu-Cowork, Claude Code plugin formats)

---

*False positives and corrections: [open an issue](https://github.com/unStone/dsh-xray/issues). Rules are fixed in public and rescans run daily.*
