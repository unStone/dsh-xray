#!/usr/bin/env python3
"""Tests for the scanning rules.

A regex tweak here silently re-rates thousands of plugins on the next scheduled
run, so the rules that decide a level are pinned by example.

Run: python test_scan_core.py
"""
import sys

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
