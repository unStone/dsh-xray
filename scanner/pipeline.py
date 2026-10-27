#!/usr/bin/env python3
"""Batch scan: download repo tarballs (no git clone), run scan_core, emit site data.

Outputs:
  data/scans/<owner>__<repo>.json   full capability card
  docs/data.json                    summary array consumed by the site
  docs/badge/<owner>__<repo>.json   shields.io endpoint JSON
"""
import concurrent.futures as cf
import datetime
import json
import pathlib
import sys

import scan_core
import analysis
from archive_input import fetch_files

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANS = ROOT / 'data' / 'scans'
DOCS = ROOT / 'docs'
LEVEL_COLORS = {0: 'brightgreen', 1: 'green', 2: 'yellow', 3: 'orange'}


def scan_repo(repo, first_seen=None):
    slug = repo['full_name'].replace('/', '__')
    out = {'repo': repo['full_name'], 'stars': repo['stars'], 'description': repo['description'],
           'pushed_at': repo['pushed_at'], 'status': 'ok',
           # Kept from the first card we ever wrote for this repo, so the feed can
           # answer "what showed up in the ecosystem this week".
           'first_seen': first_seen or datetime.date.today().isoformat()}
    try:
        source = fetch_files(repo['full_name'], repo.get('default_branch'))
        card = scan_core.scan_files(source.files, source.entries, source.notes)
        out.update(card)
        out['refresh_status'] = 'current'
    except analysis.AnalysisRuntimeError as error:
        raise analysis.AnalysisRuntimeError(f'{repo["full_name"]}: {error}') from error
    except Exception as e:
        out['status'] = f'skipped: {e}'
        out.update({'type': 'unknown', 'level': -1, 'flags': [], 'injects': [], 'hooks': [],
                    'tool_regs': 0, 'domains': {}, 'env': {}, 'files_scanned': 0,
                    'manifest': None, 'install_scripts': {}, 'behaviors': {}})
    (SCANS / f'{slug}.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=list))
    return out


def top_counted(counts):
    # A card holds {value: count}. An entry recovered from an already published
    # data.json has been through summarize once, so it is a ranked list and the
    # counts are gone -- take it as it stands rather than re-ranking nothing.
    counts = counts or {}
    return (sorted(counts, key=counts.get, reverse=True)
            if isinstance(counts, dict) else list(counts))[:10]


def summarize(card):
    return {k: card.get(k) for k in (
        'repo', 'stars', 'description', 'type', 'level', 'status', 'flags', 'injects', 'hooks',
        'tool_regs', 'files_scanned', 'pushed_at', 'first_seen', 'collect',
        'refresh_status', 'tool_reg_evidence', 'tool_reg_analysis')} | {
        'domains': top_counted(card.get('domains')),
        'env': top_counted(card.get('env')),
        'has_patch': any(f['id'] == 'runtime_patch' for f in card.get('flags', [])),
    }


def write_badge(card):
    slug = card['repo'].replace('/', '__')
    level = card['level']
    msg = f"C{level} · {len(card['flags'])} flags" if level >= 0 else 'unscanned'
    (DOCS / 'badge' / f'{slug}.json').write_text(json.dumps({
        'schemaVersion': 1, 'label': 'dsh-xray',
        'message': msg, 'color': LEVEL_COLORS.get(level, 'lightgrey')}))


def load_cached(slug):
    f = SCANS / f'{slug}.json'
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except Exception:
        return None


def main(limit=None, workers=8, budget=None):
    """Scan repos.json.

    limit  -- only consider the top N repositories by stars (None = all)
    budget -- cap how many repos are actually fetched this run; unchanged repos
              reuse their cached card for free, so a daily run converges toward
              full coverage without re-downloading the whole ecosystem.
    """
    analysis.worker()
    repos = json.loads((ROOT / 'data' / 'repos.json').read_text())
    if limit:
        repos = repos[:limit]
    SCANS.mkdir(parents=True, exist_ok=True)
    (DOCS / 'badge').mkdir(parents=True, exist_ok=True)

    results, todo = [], []
    for r in repos:
        cached = load_cached(r['full_name'].replace('/', '__'))
        # Re-fetch when we have no card, when the repo moved on, when a
        # previous run failed -- a transient failure should not be permanent --
        # or when the card was collected under an older raw-field schema, which
        # a re-derive below could not repair.
        fresh = (cached and cached.get('pushed_at') == r['pushed_at']
                 and cached.get('status') == 'ok'
                 and cached.get('collect') == scan_core.COLLECT_VERSION)
        if fresh:
            cached['stars'] = r['stars']          # stars drift without a push
            cached['description'] = r['description']
            cached['refresh_status'] = 'current'
            # The card caches what was collected, not what it means: re-derive
            # type/flags/level so a rule change reaches unchanged repositories
            # on the next run instead of being trapped inside the cache.
            results.append(scan_core.finalize(cached))
        else:
            todo.append(r)

    dropped = 0
    if budget and len(todo) > budget:
        dropped = len(todo) - budget
        todo.sort(key=lambda r: -r['stars'])
        # Anything deferred keeps whatever we last published, so a cold cache or a
        # tight budget delays a refresh instead of deleting the plugin's page.
        published = {}
        prev = DOCS / 'data.json'
        if prev.exists():
            try:
                published = {p['repo']: p for p in json.loads(prev.read_text())['plugins']}
            except Exception:
                published = {}
        for r in todo[budget:]:
            stale = load_cached(r['full_name'].replace('/', '__')) or published.get(r['full_name'])
            if stale:
                if (stale.get('status') == 'ok' and stale.get('collect') == scan_core.COLLECT_VERSION
                        and 'behaviors' in stale):
                    stale = scan_core.finalize(stale)
                stale['refresh_status'] = 'deferred'
                results.append(stale)
        todo = todo[:budget]
    print(f'{len(results)} cached, {len(todo)} to fetch'
          + (f', {dropped} deferred to a later run (budget {budget})' if dropped else ''))

    with cf.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(scan_repo, r, (load_cached(r['full_name'].replace('/', '__')) or {})
                               .get('first_seen')): r for r in todo}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            try:
                results.append(fut.result())
            except analysis.AnalysisRuntimeError:
                # Executor context cleanup waits for queued work by default.
                # Cancel it so an environment failure cannot start more downloads.
                for pending in futures:
                    pending.cancel()
                raise
            if i % 50 == 0 or i == len(todo):
                print(f'[{i}/{len(todo)}] fetched')

    for card in results:
        write_badge(card)
    results.sort(key=lambda c: -c['stars'])
    ok = [c for c in results if c['status'] == 'ok']
    (DOCS / 'data.json').write_text(json.dumps({
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        # discovered = repositories in the topic; total = repositories we hold a
        # card for; scanned = cards that actually parsed. Publishing all three
        # keeps real coverage visible instead of implying we cover everything.
        'discovered': len(repos), 'total': len(results), 'scanned': len(ok),
        'plugins': [summarize(c) for c in results],
    }, ensure_ascii=False))
    lv = {}
    for c in ok:
        lv[c['level']] = lv.get(c['level'], 0) + 1
    print(f"done: {len(ok)}/{len(results)} scanned, levels={dict(sorted(lv.items()))}")
    if dropped:
        print(f'NOTE: {dropped} repositories were not fetched this run (budget); '
              f'they carry stale or missing cards until a later run picks them up.')


if __name__ == '__main__':
    arg = lambda i, d: (int(sys.argv[i]) if len(sys.argv) > i and sys.argv[i] != 'all' else d)
    main(arg(1, None), arg(2, 8), arg(3, None))
