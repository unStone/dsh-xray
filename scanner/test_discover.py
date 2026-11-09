"""Delta discovery regressions: the daily catalog update must not lose or
duplicate repositories, and must keep rename detection working on delta days.

Full enumeration only runs weekly (it is sleep-paced by the search API's
30 requests/minute cap); the other six days fold a pushed-recently search
into the committed catalog by node id.
"""
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import aliases
import discover


def api_repo(node_id, full_name, stars=1, pushed='2026-11-08T00:00:00Z'):
    """A GitHub search API item, as consumed by discover.fetch_all."""
    return {'node_id': node_id, 'full_name': full_name, 'stargazers_count': stars,
            'description': 'd', 'size': 1, 'pushed_at': pushed,
            'default_branch': 'main'}


def catalog_repo(node_id, full_name, stars=1, pushed='2026-11-08T00:00:00Z'):
    """A catalog entry, as discover.fetch_all emits and discover.merge consumes."""
    return {'node_id': node_id, 'full_name': full_name, 'stars': stars,
            'description': 'd', 'size_kb': 1, 'pushed_at': pushed,
            'default_branch': 'main'}


class MergeTests(unittest.TestCase):
    def test_update_lands_on_the_existing_entry(self):
        catalog = [dict(node_id='R_1', full_name='Old/repo', stars=1,
                        pushed_at='2026-01-01T00:00:00Z')]
        updates = [catalog_repo('R_1', 'Old/repo', stars=5)]
        merged = discover.merge(catalog, updates)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['stars'], 5)
        self.assertEqual(merged[0]['pushed_at'], '2026-11-08T00:00:00Z')

    def test_rename_reuses_the_old_entry(self):
        # The search result carries the new name; the node id carries the identity.
        catalog = [dict(node_id='R_1', full_name='Old/repo', stars=1, pushed_at='x')]
        updates = [catalog_repo('R_1', 'Renamed/repo', stars=2)]
        merged = discover.merge(catalog, updates)
        self.assertEqual([r['full_name'] for r in merged], ['Renamed/repo'])

    def test_new_repos_are_appended(self):
        catalog = [dict(node_id='R_1', full_name='Old/repo', stars=1, pushed_at='x')]
        updates = [catalog_repo('R_2', 'New/repo', stars=9)]
        merged = discover.merge(catalog, updates)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]['full_name'], 'New/repo')  # sorted by stars

    def test_legacy_entry_without_node_id_is_matched_by_name(self):
        # Catalogs written before node ids were recorded must not be duplicated.
        catalog = [dict(full_name='Old/repo', stars=1, pushed_at='x')]
        updates = [catalog_repo('R_1', 'Old/repo', stars=4)]
        merged = discover.merge(catalog, updates)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['node_id'], 'R_1')

    def test_sort_is_by_stars_descending(self):
        merged = discover.merge([], [catalog_repo(f'R_{i}', f'o/r{i}', stars=s)
                                     for i, s in enumerate([3, 9, 1])])
        self.assertEqual([r['stars'] for r in merged], [9, 3, 1])


class WalkFieldTests(unittest.TestCase):
    def test_delta_windows_query_pushed_dates(self):
        queries = []

        def fake_query(q, page=1):
            queries.append((q, page))
            if page == 1:
                return {'total_count': 2, 'items': [
                    api_repo('R_1', 'o/a'), api_repo('R_2', 'o/b')]}
            return {'total_count': 2, 'items': []}

        with patch.object(discover, 'query', fake_query):
            seen, out = set(), []
            discover.walk('topic:dsh-plugin', '2026-11-06', '2026-11-08',
                          seen, out, field='pushed')
        self.assertTrue(all('pushed:2026-11-06..2026-11-08' in q for q, _ in queries))
        self.assertEqual([r['full_name'] for r in out], ['o/a', 'o/b'])


class DeltaModeTests(unittest.TestCase):
    def setUp(self):
        intermediate = pathlib.Path(__file__).resolve().parent.parent / 'tmp'
        intermediate.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=intermediate)
        self.root = pathlib.Path(self.temp.name)
        self.catalog = self.root / 'repos.json'
        self.aliases_file = self.root / 'aliases.json'
        self.catalog.write_text(json.dumps([
            {'node_id': 'R_1', 'full_name': 'Old/repo', 'stars': 1,
             'description': 'old', 'size_kb': 1, 'pushed_at': '2026-10-01T00:00:00Z',
             'default_branch': 'main'}]))
        patches = [patch.object(discover, 'OUT', self.catalog),
                   patch.object(discover, 'ALIASES', self.aliases_file),
                   # keep the committed alias map (the issue #17 backfill) out of the test
                   patch.object(aliases, 'ALIASES', self.aliases_file)]
        for item in patches:
            item.start()
        self.patches = patches

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_delta_merges_renames_and_new_repos(self):
        def fake_query(q, page=1):
            if page == 1:
                return {'total_count': 2, 'items': [
                    # a rename (same node id, new name) and a brand-new repo
                    api_repo('R_1', 'Renamed/repo', stars=2),
                    api_repo('R_2', 'Fresh/repo', stars=7)]}
            return {'total_count': 2, 'items': []}

        with patch.object(discover, 'query', fake_query):
            discover.main(mode='delta')

        result = json.loads(self.catalog.read_text())
        self.assertEqual([r['full_name'] for r in result], ['Fresh/repo', 'Renamed/repo'])
        self.assertEqual(len(result), 2)  # no duplicate of the pre-rename entry
        self.assertEqual(json.loads(self.aliases_file.read_text()),
                         {'Old__repo': 'Renamed__repo'})

    def test_delta_keeps_repos_that_did_not_push(self):
        def fake_query(q, page=1):
            return {'total_count': 0, 'items': []}

        with patch.object(discover, 'query', fake_query):
            discover.main(mode='delta')
        result = json.loads(self.catalog.read_text())
        self.assertEqual([r['full_name'] for r in result], ['Old/repo'])


if __name__ == '__main__':
    unittest.main()
