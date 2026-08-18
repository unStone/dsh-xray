#!/usr/bin/env python3
"""Enumerate the whole `dsh-plugin` topic, working around GitHub's 1000-result cap.

GitHub search returns at most 1000 results per query, and the topic holds ~7k
repositories. We partition by star bucket and, when a bucket still exceeds the
cap, recursively halve its creation-date window until every slice fits.

Writes data/repos.json sorted by stars. Requires `gh` CLI auth (or GH_TOKEN).
"""
import datetime
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'repos.json'
TOPIC = 'topic:dsh-plugin'
STAR_BUCKETS = ['>=100', '10..99', '5..9', '2..4', '1', '0']
EPOCH = datetime.date(2008, 1, 1)
PAGE_SLEEP = 2.2          # search API allows 30 req/min authenticated
CAP = 1000


def gh_json(path):
    for attempt in range(4):
        r = subprocess.run(['gh', 'api', path], capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
        if 'rate limit' in r.stderr.lower() or 'API rate' in r.stderr:
            time.sleep(20 * (attempt + 1))
            continue
        if attempt == 3:
            raise RuntimeError(r.stderr.strip()[:200])
        time.sleep(3)
    return {}


def query(q, page=1):
    from urllib.parse import quote
    time.sleep(PAGE_SLEEP)
    return gh_json(f'search/repositories?q={quote(q)}&sort=stars&order=desc&per_page=100&page={page}')


def fetch_all(q, seen, out):
    """Pull every page of a query known to be under the result cap."""
    for page in range(1, 11):
        data = query(q, page)
        items = data.get('items', [])
        for r in items:
            if r['full_name'] in seen or r.get('fork') or r.get('archived'):
                continue
            seen.add(r['full_name'])
            out.append({
                'full_name': r['full_name'],
                'stars': r['stargazers_count'],
                'description': (r.get('description') or '')[:200],
                'size_kb': r.get('size', 0),
                'pushed_at': r.get('pushed_at'),
                'default_branch': r.get('default_branch'),
            })
        if len(items) < 100:
            return


def walk(base_q, lo, hi, seen, out, depth=0):
    """Enumerate base_q within [lo, hi], halving the window while over the cap."""
    q = f'{base_q} created:{lo}..{hi}'
    total = query(q).get('total_count', 0)
    if total == 0:
        return
    if total <= CAP or lo == hi or depth > 12:
        if total > CAP:
            print(f'  ! {q} has {total} (>cap) and cannot split further; taking first {CAP}')
        fetch_all(q, seen, out)
        return
    mid = lo + (hi - lo) / 2
    walk(base_q, lo, mid, seen, out, depth + 1)
    walk(base_q, mid + datetime.timedelta(days=1), hi, seen, out, depth + 1)


def main(limit=None):
    today = datetime.date.today()
    seen, out = set(), []
    for bucket in STAR_BUCKETS:
        base = f'{TOPIC} stars:{bucket}'
        total = query(base).get('total_count', 0)
        before = len(out)
        if total <= CAP:
            fetch_all(base, seen, out)
        else:
            walk(base, EPOCH, today, seen, out)
        print(f'stars:{bucket:8} reported={total:5} collected={len(out) - before:5} running={len(out)}')
    out.sort(key=lambda r: -r['stars'])
    if limit:
        out = out[:limit]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f'discovered {len(out)} repos -> {OUT}')


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != 'all' else None)
