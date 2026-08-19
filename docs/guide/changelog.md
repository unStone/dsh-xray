# Changelog

*[中文版](changelog.html?lang=zh) · Scan results refresh daily; this page records changes to method and product*

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
