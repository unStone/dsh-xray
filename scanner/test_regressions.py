import json
import unittest

import scan_core


def scan(source, files=None, extra=None):
    package = {'name': 'fixture', 'version': '1.0.0',
               'dsh': {'bundle': {'patch': './cordis.patch.yml'}}}
    if files is not None:
        package['files'] = files
    return scan_core.scan_files({'package.json': json.dumps(package), 'index.js': source,
                                 **(extra or {})})


class IssueRegressions(unittest.TestCase):
    def test_negation_does_not_disable_allowlist(self):
        card = scan('export function apply(ctx) {}', ['lib', '!docs/private'],
                    {'scripts/check.mjs': 'import "node:child_process"; execSync("ls")'})
        self.assertEqual(card['level'], 2)
        self.assertIn('exec_tooling', {f['id'] for f in card['flags']})

    def test_injected_context_and_service_alias(self):
        card = scan('''export function apply(ctx) {
          ctx.inject(['tools'], scoped => {
            const tools = scoped?.tools;
            scoped.effect(() => tools.register({name: 'demo'}));
          });
        }''')
        self.assertEqual(card['tool_regs'], 1)
        self.assertEqual(card['tool_reg_evidence'][0]['line'], 4)

    def test_strings_are_not_registrations(self):
        self.assertEqual(scan('const sample = "ctx.tools.register({})";')['tool_regs'], 0)

    def test_helper_and_optional_chain(self):
        card = scan('''function registerTools(host) {
          const tools = host?.tools;
          tools.register({name: 'a'});
          tools.register({name: 'b'});
        }
        export function apply(context) { registerTools(context); }
        ''')
        self.assertEqual(card['tool_regs'], 2)

    def test_unrelated_service_and_shadowed_binding(self):
        card = scan('''export function apply(ctx) {
          const tools = ctx.tools;
          tools.register({name: 'real'});
          { const tools = other.tools; tools.register({name: 'unrelated'}); }
        }''')
        self.assertEqual(card['tool_regs'], 1)

    def test_finalize_does_not_restamp_old_collection(self):
        card = scan('export function apply(ctx) {}')
        card['collect'] = 2
        self.assertEqual(scan_core.finalize(card)['collect'], 2)

    def test_development_context_does_not_classify_runtime_helper(self):
        card = scan('export function mount(host) { const tools = host.tools; tools.register({}); }', extra={
            'tests/example.js': 'import {mount} from "../index.js"; export function apply(ctx) { mount(ctx); }',
        })
        self.assertEqual(card['tool_regs'], 0)

    def test_development_registrations_remain_visible_separately(self):
        card = scan('export function apply(ctx) {}', extra={
            'tests/example.js': 'export function apply(ctx) { ctx.tools.register({}); }',
        })
        self.assertEqual(card['tool_regs'], 0)
        self.assertEqual(card['dev_tool_regs'], 1)


if __name__ == '__main__':
    unittest.main()
