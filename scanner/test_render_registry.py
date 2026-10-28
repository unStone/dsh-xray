import gzip
import json
import pathlib
import tempfile
import unittest

import render_registry


def dataset(count=123):
    return {
        'generated_at': '2026-10-28T00:00:00+00:00',
        'total': count, 'scanned': count - 1, 'discovered': count + 2,
        'plugins': [{
            'repo': f'owner/plugin-{i}', 'stars': count - i,
            'description': '</script><script>alert(1)</script>' if i == 0 else f'Plugin {i}',
            'level': -1 if i == count - 1 else i % 4,
            'type': 'plugin' if i % 2 else 'skill', 'injects': ['tools', f'service-{i}'],
            'flags': [{'id': 'exec', 'evidence': f'index.js:{i + 1}'}],
            'tool_regs': 1, 'tool_reg_evidence': [{'path': 'index.js', 'line': i + 1}],
            'tool_reg_analysis': {'status': 'partial', 'diagnostics': [{'reason': 'unresolved'}]},
            'refresh_status': 'deferred', 'status': 'ok',
        } for i in range(count)],
    }


class RegistryBuildTests(unittest.TestCase):
    def setUp(self):
        intermediate = pathlib.Path(__file__).resolve().parent.parent / 'tmp'
        intermediate.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=intermediate)
        self.docs = pathlib.Path(self.temp.name)
        (self.docs / 'registry.html').write_text(
            '<head><!--REGISTRY_STYLE_START--><!--REGISTRY_STYLE_END--></head>'
            '<body><!--REGISTRY_BOOTSTRAP_START--><!--REGISTRY_BOOTSTRAP_END--></body>')
        (self.docs / 'registry.js').write_text('window.registryReady = true;')
        (self.docs / 'i18n.js').write_text('window.xray = {};')
        (self.docs / 'style.css').write_text('body { margin: 0; }')

    def tearDown(self):
        self.temp.cleanup()

    def build(self, data):
        (self.docs / 'data.json').write_text(json.dumps(data))
        return render_registry.build(self.docs)

    def test_index_and_shards_preserve_every_repo_and_evidence(self):
        data = dataset()
        manifest = self.build(data)
        index = [p for path in manifest['indexes'] for p in json.loads((self.docs / path).read_text())]
        self.assertEqual([p['repo'] for p in index], [p['repo'] for p in data['plugins']])
        self.assertEqual(index[-1]['injects'], data['plugins'][-1]['injects'])
        self.assertNotIn('tool_reg_evidence', index[0])
        self.assertEqual(index[0]['flags'], ['exec'])
        restored = {}
        for path in manifest['details'].values():
            restored.update(json.loads((self.docs / path).read_text()))
        self.assertEqual(restored, {p['repo']: p for p in data['plugins']})
        for repo in restored:
            path = manifest['details'][render_registry.bucket(repo)]
            self.assertIn(repo, json.loads((self.docs / path).read_text()))
        stats = json.loads((self.docs / 'stats.json').read_text())
        self.assertEqual(stats['levels']['3'], 30)
        self.assertEqual(stats['scanned'], 122)
        self.assertEqual(stats['total'], 123)

    def test_bootstrap_is_bounded_safe_and_contains_snapshot_references(self):
        manifest = self.build(dataset())
        page = (self.docs / 'registry.html').read_text()
        self.assertNotIn('</script><script>alert', page)
        self.assertIn('\\u003c/script>', page)
        content = page.split('<script type="application/json" id="registryBootstrap">')[1].split('</script>')[0]
        boot = json.loads(content)
        self.assertEqual(len(boot['initial']), 50)
        self.assertEqual(boot['index'], manifest['index'])
        self.assertEqual(boot['details'], manifest['details'])
        self.assertIn(f'<script src="{manifest["app"]}">', page)
        self.assertIn(f'<script src="{manifest["i18n"]}">', page)
        self.assertIn(f'<link rel="stylesheet" href="{manifest["style"]}">', page)
        self.assertLess(len(gzip.compress(content.encode())), 12000)

    def test_deterministic_outputs_and_one_previous_generation_survives(self):
        data = dataset()
        first = self.build(data)
        self.assertEqual(first, self.build(data))
        data['plugins'][0]['description'] = 'updated'
        second = self.build(data)
        self.assertNotEqual(first['index'], second['index'])
        self.assertTrue((self.docs / first['index']).exists())
        data['plugins'][0]['description'] = 'updated again'
        third = self.build(data)
        self.assertFalse((self.docs / first['index']).exists())
        self.assertTrue((self.docs / second['index']).exists())
        self.assertTrue((self.docs / third['index']).exists())

    def test_invalid_snapshot_cannot_overwrite_bootstrap(self):
        self.build(dataset())
        before = (self.docs / 'registry.html').read_bytes()
        data = dataset()
        data['plugins'].append(data['plugins'][0])
        with self.assertRaisesRegex(ValueError, 'total|duplicate'):
            self.build(data)
        self.assertEqual((self.docs / 'registry.html').read_bytes(), before)

    def test_missing_bootstrap_marker_fails_explicitly(self):
        (self.docs / 'registry.html').write_text('<html></html>')
        with self.assertRaisesRegex(ValueError, 'marker'):
            self.build(dataset())

    def test_search_chunks_are_bounded_and_client_code_is_content_addressed(self):
        first = self.build(dataset(1234))
        self.assertEqual(len(first['indexes']), 3)
        for path in first['indexes']:
            self.assertLessEqual(len(json.loads((self.docs / path).read_text())), 500)
        (self.docs / 'registry.js').write_text('window.registryReady = 2;')
        second = self.build(dataset(1234))
        self.assertNotEqual(first['app'], second['app'])
        self.assertTrue((self.docs / first['app']).exists())
        self.assertEqual((self.docs / second['app']).read_text(), 'window.registryReady = 2;')


if __name__ == '__main__':
    unittest.main()
