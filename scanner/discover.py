#!/usr/bin/env python3
"""Discover dsh plugin repositories via the GitHub topic `dsh-plugin`.

Writes data/repos.json sorted by stars. Requires `gh` CLI auth (or GH_TOKEN).
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'repos.json'


def gh_json(url):
    return json.loads(subprocess.run(['gh', 'api', url], capture_output=True, text=True, check=True).stdout)


def main(pages=3):
    repos = []
    for page in range(1, pages + 1):
        data = gh_json(f'search/repositories?q=topic:dsh-plugin&sort=stars&order=desc&per_page=100&page={page}')
        items = data.get('items', [])
        for r in items:
            if r.get('fork') or r.get('archived'):
                continue
            repos.append({
                'full_name': r['full_name'],
                'stars': r['stargazers_count'],
                'description': (r.get('description') or '')[:200],
                'size_kb': r.get('size', 0),
                'pushed_at': r.get('pushed_at'),
                'default_branch': r.get('default_branch'),
            })
        if len(items) < 100:
            break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(repos, ensure_ascii=False, indent=1))
    print(f'discovered {len(repos)} repos -> {OUT}')


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
