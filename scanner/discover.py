#!/usr/bin/env python3
"""Enumerate the `dsh-plugin` topic, working around GitHub's 1000-result cap.

GitHub search returns at most 1000 results per query and answers at most 30
requests per minute, so a full enumeration (mode `all`) costs hundreds of
sleep-paced requests. That is why it only runs weekly: on the other days,
mode `delta` searches just the repos pushed since a couple of days back --
a handful of pages -- and merges them into the committed catalog. Deltas
cannot see topic departures, old repositories that only now gained the
topic, or quiet renames; the weekly full sweep is what keeps those honest.

Writes data/repos.json sorted by stars. Requires `gh` CLI auth (or GH_TOKEN).
"""
import datetime
import json
import pathlib
import subprocess
import sys
import time

import aliases

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'repos.json'
ALIASES = aliases.ALIASES
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
                # The one identifier that survives account and repository
                # renames; full_name does not. This is what lets the next run
                # tell a rename apart from a delete-plus-new-repo and keep the
                # old card path alive as an alias (issue #17).
                'node_id': r.get('node_id'),
                'stars': r['stargazers_count'],
                'description': (r.get('description') or '')[:200],
                'size_kb': r.get('size', 0),
                'pushed_at': r.get('pushed_at'),
                'default_branch': r.get('default_branch'),
            })
        if len(items) < 100:
            return


def walk(base_q, lo, hi, seen, out, depth=0, field='created'):
    """Enumerate base_q within [lo, hi] on a date field, halving while over the cap."""
    q = f'{base_q} {field}:{lo}..{hi}'
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


def merge(catalog, updates):
    """Fold freshly discovered entries into the catalog, matching by node id.

    Search results carry the current full_name, so a renamed repository that
    was pushed recently arrives here under its new name and lands on the old
    entry -- which is exactly what makes rename aliases work on delta days.
    Entries recorded before node ids were kept match by name instead, so a
    delta run cannot duplicate them.
    """
    by_node, by_name = {}, {}
    for r in catalog:
        if r.get('node_id'):
            by_node[r['node_id']] = r
        by_name[r['full_name']] = r
    for u in updates:
        target = by_node.get(u.get('node_id')) or by_name.get(u['full_name'])
        if target is None:
            catalog.append(u)
            target = u
        target.update(u)
        if u.get('node_id'):
            by_node[u['node_id']] = target
        by_name[u['full_name']] = target
    catalog.sort(key=lambda r: -r['stars'])
    return catalog


def main(limit=None, mode='all'):
    today = datetime.date.today()
    # The catalog on disk is the previous run's view; the node-id diff against
    # it is what records renames while they are still fresh.
    try:
        previous = json.loads(OUT.read_text())
    except Exception:
        previous = []
    if mode == 'delta':
        # A repo that merely changed name without pushing is invisible here;
        # the weekly full sweep picks those renames up. The catalog is re-read
        # (rather than reusing `previous`) because merge() mutates its entries
        # in place, and `previous` must stay the untouched pre-merge view for
        # the node-id rename diff below.
        try:
            catalog = json.loads(OUT.read_text())
        except Exception:
            catalog = []
        updates = []
        walk(TOPIC, today - datetime.timedelta(days=2), today, set(), updates, field='pushed')
        out = merge(catalog, updates)
        print(f'delta: {len(updates)} pushed repo(s) merged into {len(out)}')
    else:
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
    previous_aliases = aliases.load()
    added = aliases.update(out, previous)
    if len(added) > len(previous_aliases):
        print(f'aliased {len(added) - len(previous_aliases)} renamed repos -> {ALIASES}')
    ALIASES.parent.mkdir(parents=True, exist_ok=True)
    ALIASES.write_text(json.dumps(added, ensure_ascii=False, indent=1, sort_keys=True))
    print(f'discovered {len(out)} repos ({mode}) -> {OUT}')


if __name__ == '__main__':
    args = list(sys.argv[1:])
    mode = 'all'
    if args and args[0] in ('all', 'delta'):
        mode = args.pop(0)
    limit = int(args[0]) if args and args[0] != 'all' else None
    main(limit, mode)
