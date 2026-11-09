"""Issue #17 regressions: a GitHub rename must not become a dead card URL.

The account behind dsh-archived-chats was renamed Ultronen -> Ultroncn; the
pipeline keyed everything on full_name, so the old card path was swept away
and https://unstone.github.io/dsh-xray/p/Ultronen__dsh-archived-chats.html
started returning 404. These tests pin the alias machinery that keeps such
paths alive.
"""
import json
import pathlib
import tempfile
import unittest

import aliases
import render_pages


def catalog(*specs):
    """Entries as discover.py writes them: (node_id, full_name) pairs."""
    return [{'node_id': n, 'full_name': f} for n, f in specs]


class AliasMapTests(unittest.TestCase):
    def test_rename_detected_by_node_id(self):
        previous = catalog(('R_1', 'Old/repo'))
        current = catalog(('R_1', 'New/repo'), ('R_2', 'Old/other'))
        self.assertEqual(aliases.update(current, previous, {}),
                         {'Old__repo': 'New__repo'})

    def test_recreated_under_same_name_is_not_an_alias(self):
        # A deleted-and-recreated repo mints a new node id; the old card is
        # genuinely gone and must be swept, not redirected.
        previous = catalog(('R_1', 'Old/repo'))
        current = catalog(('R_2', 'Old/repo'))
        self.assertEqual(aliases.update(current, previous, {}), {})

    def test_renamed_again_chains_transitively(self):
        # A->B recorded earlier, now B moved to C: resolve() walks A to C.
        previous = catalog(('R_1', 'B/repo'))
        current = catalog(('R_1', 'C/repo'))
        result = aliases.update(current, previous, {'A__repo': 'B__repo'})
        self.assertEqual(result, {'A__repo': 'B__repo', 'B__repo': 'C__repo'})
        self.assertEqual(aliases.resolve(result, 'A__repo'), 'C__repo')

    def test_pathological_cycle_does_not_loop(self):
        self.assertEqual(aliases.resolve({'A__x': 'B__x', 'B__x': 'A__x'}, 'A__x'), 'A__x')

    def test_detect_ignores_entries_without_node_id(self):
        # Catalogs written before node_id was recorded cannot prove a rename.
        previous = [{'full_name': 'Old/repo'}]
        current = catalog(('R_1', 'New/repo'))
        self.assertEqual(list(aliases.detect(current, previous)), [])


class AliasPageTests(unittest.TestCase):
    def setUp(self):
        intermediate = pathlib.Path(__file__).resolve().parent.parent / 'tmp'
        intermediate.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=intermediate)
        self.out = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def kept(self, *slugs):
        for slug in slugs:
            (self.out / f'{slug}.html').write_text('card')
        return {f'{slug}.html' for slug in slugs}

    def test_rename_leaves_a_redirect_stub(self):
        keep = self.kept('New__repo')
        (self.out / 'Old__repo.html').write_text('stale card')
        written = render_pages.write_alias_pages({'Old__repo': 'New__repo'}, keep, self.out)
        self.assertEqual(written, ['Old__repo'])
        stub = (self.out / 'Old__repo.html').read_text()
        self.assertIn('<link rel="canonical" href="https://unstone.github.io/dsh-xray/p/New__repo.html">', stub)
        self.assertIn('<meta http-equiv="refresh" content="0; url=https://unstone.github.io/dsh-xray/p/New__repo.html">', stub)
        self.assertIn('location.replace', stub)

    def test_backfilled_alias_repairs_an_already_deleted_path(self):
        keep = self.kept('New__repo')  # Old__repo.html no longer exists on disk
        written = render_pages.write_alias_pages({'Old__repo': 'New__repo'}, keep, self.out)
        self.assertEqual(written, ['Old__repo'])
        self.assertIn('canonical', (self.out / 'Old__repo.html').read_text())

    def test_chain_and_missing_target_are_handled(self):
        keep = self.kept('C__repo')
        written = render_pages.write_alias_pages(
            {'A__repo': 'B__repo', 'B__repo': 'C__repo', 'D__repo': 'Gone__repo'}, keep, self.out)
        self.assertEqual(sorted(written), ['A__repo', 'B__repo'])
        self.assertFalse((self.out / 'D__repo.html').exists())

    def test_reused_name_keeps_its_live_card(self):
        # GitHub frees the old name, and an unrelated repository can claim it;
        # that live card must win over the historical alias.
        keep = self.kept('New__repo', 'Old__repo')
        (self.out / 'Old__repo.html').write_text('card for the unrelated new repo')
        written = render_pages.write_alias_pages({'Old__repo': 'New__repo'}, keep, self.out)
        self.assertEqual(written, [])
        self.assertEqual((self.out / 'Old__repo.html').read_text(),
                         'card for the unrelated new repo')

    def test_sweep_removes_stale_but_spares_aliases(self):
        keep = self.kept('New__repo')
        (self.out / 'Old__repo.html').write_text('stale card')
        (self.out / 'Gone__repo.html').write_text('left the topic')
        removed = render_pages.sweep_stale(keep, {'Old__repo': 'New__repo'}, self.out)
        self.assertEqual(removed, ['Gone__repo.html'])
        self.assertEqual((self.out / 'Old__repo.html').read_text(), 'stale card')


if __name__ == '__main__':
    unittest.main()
