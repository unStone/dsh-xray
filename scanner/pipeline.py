#!/usr/bin/env python3
"""Batch scan: download repo tarballs (no git clone), run scan_core, emit site data.

Outputs:
  data/scans/<owner>__<repo>.json   full capability card
  docs/data.json                    summary array consumed by the site
  docs/badge/<owner>__<repo>.json   shields.io endpoint JSON
"""
import concurrent.futures as cf
import datetime
import io
import json
import pathlib
import subprocess
import sys
import tarfile

import scan_core

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANS = ROOT / 'data' / 'scans'
DOCS = ROOT / 'docs'
MAX_FILES = 600
MAX_FILE_SIZE = 1024 * 1024
MAX_BYTES_READ = 400 * 1024 * 1024  # decompressed budget, not repo size
LEVEL_COLORS = {0: 'brightgreen', 1: 'green', 2: 'yellow', 3: 'orange'}


def wanted(path):
    if 'node_modules/' in path or path.startswith('.git/'):
        return False
    base = path.rsplit('/', 1)[-1]
    return path.endswith(scan_core.CODE_EXT) or base == 'package.json' or base.upper() == 'SKILL.MD'


def fetch_files(full_name, branch=None):
    """Stream a repo tarball and pull out code files as they pass.

    Downloads from codeload rather than the REST API: public tarballs need no
    auth there and do not consume the hourly API quota, which matters when a
    full sweep touches thousands of repositories. Streaming (mode 'r|gz') means
    repository size barely matters -- we stop once MAX_FILES code files are
    collected instead of buffering the whole archive.
    """
    refs = [f'refs/heads/{b}' for b in dict.fromkeys(filter(None, [branch, 'main', 'master']))]
    downloaded = False
    for ref in refs:
        url = f'https://codeload.github.com/{full_name}/tar.gz/{ref}'
        proc = subprocess.Popen(['curl', '-sL', '--max-time', '120', '--fail', url],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        files, read = {}, 0
        try:
            with tarfile.open(fileobj=proc.stdout, mode='r|gz') as tf:
                for m in tf:
                    if read > MAX_BYTES_READ:
                        break
                    read += m.size
                    if not m.isfile() or m.size > MAX_FILE_SIZE:
                        continue
                    path = m.name.split('/', 1)[-1]  # strip the tarball root dir
                    if not wanted(path):
                        continue
                    # package.json files are small and carry the manifest -- never
                    # let the code-file cap truncate them, or which manifest we
                    # report would depend on tar ordering.
                    if path.rsplit('/', 1)[-1] != 'package.json' and len(files) >= MAX_FILES:
                        continue
                    try:
                        files[path] = tf.extractfile(m).read().decode('utf-8', errors='ignore')
                    except Exception:
                        continue
            downloaded = True
        except Exception:
            pass  # ref missing or archive unreadable; try the next ref
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            proc.terminate()
            proc.wait(timeout=10)
        if files:
            return files
    # Distinguish "we read the repo and it has no code" from "we never got the
    # repo": the site reports these differently and conflating them would
    # overstate coverage.
    raise ValueError('no scannable code' if downloaded else 'download failed')


def scan_repo(repo, first_seen=None):
    slug = repo['full_name'].replace('/', '__')
    out = {'repo': repo['full_name'], 'stars': repo['stars'], 'description': repo['description'],
           'pushed_at': repo['pushed_at'], 'status': 'ok',
           # Kept from the first card we ever wrote for this repo, so the feed can
           # answer "what showed up in the ecosystem this week".
           'first_seen': first_seen or datetime.date.today().isoformat()}
    try:
        card = scan_core.scan_files(fetch_files(repo['full_name'], repo.get('default_branch')))
        out.update(card)
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
        'tool_regs', 'files_scanned', 'pushed_at', 'first_seen')} | {
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
                if stale.get('status') == 'ok' and stale.get('collect') == scan_core.COLLECT_VERSION:
                    stale = scan_core.finalize(stale)
                results.append(stale)
        todo = todo[:budget]
    print(f'{len(results)} cached, {len(todo)} to fetch'
          + (f', {dropped} deferred to a later run (budget {budget})' if dropped else ''))

    with cf.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(scan_repo, r, (load_cached(r['full_name'].replace('/', '__')) or {})
                               .get('first_seen')): r for r in todo}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            results.append(fut.result())
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
