import io
import json
import pathlib
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import analysis
import archive_input
import pipeline
import render_pages
import scan_core


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as output:
        for path, content in files.items():
            member = tarfile.TarInfo('repo/' + path)
            data = content.encode()
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    buffer.seek(0)
    return buffer


class ArchiveTests(unittest.TestCase):
    def test_collects_paths_and_nested_ignore_metadata(self):
        source = archive_input.read_archive(archive({
            'package.json': '{"name":"p","files":["scripts"]}',
            'scripts/.npmignore': 'private/\n', 'scripts/private/a.mjs': 'execSync("ls")',
            'assets/photo.png': 'not-code',
        }))
        self.assertIn('scripts/.npmignore', source.files)
        self.assertIn({'path': 'assets/photo.png', 'type': 'file'}, source.entries)
        card = scan_core.scan_files(source.files, source.entries, source.notes)
        self.assertIn('exec_tooling', {f['id'] for f in card['flags']})

    def test_code_cap_never_truncates_metadata_or_hides_incomplete_count(self):
        with patch.object(archive_input, 'MAX_FILES', 1):
            source = archive_input.read_archive(archive({
                'a.js': 'const a = 1', 'b.js': 'const b = 2',
                'package.json': '{"name":"p"}', 'scripts/.npmignore': 'private/',
            }))
        self.assertIn('package.json', source.files)
        self.assertIn('scripts/.npmignore', source.files)
        self.assertTrue(source.notes)
        self.assertEqual(scan_core.scan_files(source.files, source.entries, source.notes)
                         ['tool_reg_analysis']['status'], 'partial')

    def test_incomplete_metadata_fails_instead_of_claiming_files_are_absent(self):
        with patch.object(archive_input, 'MAX_ENTRIES', 1):
            with self.assertRaisesRegex(ValueError, 'metadata incomplete'):
                archive_input.read_archive(archive({'package.json': '{}', 'index.js': ''}))

    def test_rejects_archive_path_traversal(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            archive_input.read_archive(archive({'../outside.js': 'danger'}))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=analysis.ROOT / 'tmp')
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'data').mkdir()
        (self.root / 'docs').mkdir()
        self.patches = [patch.object(pipeline, 'ROOT', self.root),
                        patch.object(pipeline, 'SCANS', self.root / 'data/scans'),
                        patch.object(pipeline, 'DOCS', self.root / 'docs')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_old_schema_is_refetched_even_when_push_time_is_unchanged(self):
        repo = {'full_name': 'owner/plugin', 'stars': 1, 'description': 'current', 'pushed_at': 'same'}
        (self.root / 'data/repos.json').write_text(json.dumps([repo]))
        (self.root / 'data/scans').mkdir()
        old = {'repo': repo['full_name'], 'pushed_at': 'same', 'collect': 3,
               'status': 'ok', 'first_seen': '2026-01-01'}
        (self.root / 'data/scans/owner__plugin.json').write_text(json.dumps(old))
        source = archive_input.ScanInput({'package.json': '{"name":"p"}',
                                        'index.js': 'export function apply(ctx) { ctx.tools.register({}); }'}, [], [])
        with patch.object(pipeline, 'fetch_files', return_value=source) as download:
            pipeline.main(workers=1)
        self.assertEqual(download.call_count, 1)
        card = json.loads((self.root / 'docs/data.json').read_text())['plugins'][0]
        self.assertEqual(card['collect'], scan_core.COLLECT_VERSION)
        self.assertEqual(card['tool_regs'], 1)
        self.assertEqual(card['first_seen'], '2026-01-01')
        with patch.object(pipeline, 'fetch_files', side_effect=AssertionError('fresh cache was refetched')):
            pipeline.main(workers=1)

    def test_budget_retains_old_version_and_marks_deferred_summary(self):
        repos = [{'full_name': f'owner/p{i}', 'stars': 2 - i, 'description': 'new', 'pushed_at': 'same'} for i in range(2)]
        (self.root / 'data/repos.json').write_text(json.dumps(repos))
        published = {'repo': 'owner/p1', 'stars': 1, 'level': 2, 'flags': [], 'status': 'ok',
                     'tool_regs': 0, 'files_scanned': 1}
        (self.root / 'docs/data.json').write_text(json.dumps({'plugins': [published]}))
        source = archive_input.ScanInput({'package.json': '{"name":"p"}'}, [], [])
        with patch.object(pipeline, 'fetch_files', return_value=source):
            pipeline.main(workers=1, budget=1)
        deferred = json.loads((self.root / 'docs/data.json').read_text())['plugins'][1]
        self.assertIsNone(deferred['collect'])
        self.assertEqual(deferred['refresh_status'], 'deferred')

    def test_environment_failure_is_not_written_as_a_successful_card(self):
        (self.root / 'data/scans').mkdir()
        repo = {'full_name': 'owner/plugin', 'stars': 1, 'description': '', 'pushed_at': 'same'}
        with patch.object(pipeline, 'fetch_files', side_effect=analysis.AnalysisRuntimeError('worker stopped')):
            with self.assertRaises(analysis.AnalysisRuntimeError):
                pipeline.scan_repo(repo)
        self.assertFalse((self.root / 'data/scans/owner__plugin.json').exists())

    def test_batch_worker_failure_does_not_publish_partial_dataset(self):
        repos = [{'full_name': f'owner/p{i}', 'stars': i, 'description': '', 'pushed_at': 'same'} for i in range(3)]
        (self.root / 'data/repos.json').write_text(json.dumps(repos))
        published = '{"plugins":[],"generated_at":"previous"}'
        (self.root / 'docs/data.json').write_text(published)
        with patch.object(pipeline, 'fetch_files', side_effect=analysis.AnalysisRuntimeError('worker stopped')):
            with self.assertRaisesRegex(analysis.AnalysisRuntimeError, 'worker stopped'):
                pipeline.main(workers=1)
        self.assertEqual((self.root / 'docs/data.json').read_text(), published)


class PresentationTests(unittest.TestCase):
    def test_partial_and_deferred_are_visible_and_evidence_is_escaped(self):
        page = render_pages.page({'repo': 'owner/plugin', 'level': 2, 'type': 'plugin',
                                  'flags': [], 'tool_regs': 0, 'refresh_status': 'deferred',
                                  'tool_reg_analysis': {'status': 'partial', 'diagnostics': [
                                      {'path': '<index>.js', 'line': 7, 'reason': '<script>alert(1)</script>'}]}})
        self.assertIn('analysis is incomplete', page)
        self.assertIn('Refresh pending', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert(1)</script>', page)


if __name__ == '__main__':
    unittest.main()
