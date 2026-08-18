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
import urllib.request

import scan_core

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANS = ROOT / 'data' / 'scans'
DOCS = ROOT / 'docs'
MAX_TARBALL = 40 * 1024 * 1024
MAX_FILES = 600
MAX_FILE_SIZE = 1024 * 1024
LEVEL_COLORS = {0: 'brightgreen', 1: 'green', 2: 'yellow', 3: 'orange'}


def gh_token():
    return subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True).stdout.strip()


TOKEN = gh_token()


def fetch_tarball(full_name):
    req = urllib.request.Request(
        f'https://api.github.com/repos/{full_name}/tarball',
        headers={'Authorization': f'Bearer {TOKEN}', 'User-Agent': 'dsh-xray'})
    buf = io.BytesIO()
    with urllib.request.urlopen(req, timeout=60) as resp:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            buf.write(chunk)
            if buf.tell() > MAX_TARBALL:
                raise ValueError('tarball too large')
    buf.seek(0)
    return buf


def extract_files(buf):
    files, count = {}, 0
    with tarfile.open(fileobj=buf, mode='r:gz') as tf:
        for m in tf:
            if not m.isfile() or m.size > MAX_FILE_SIZE or count >= MAX_FILES:
                continue
            path = m.name.split('/', 1)[-1]  # strip the tarball root dir
            if 'node_modules/' in path or path.startswith('.git/'):
                continue
            base = path.rsplit('/', 1)[-1]
            if not (path.endswith(scan_core.CODE_EXT) or base == 'package.json' or base.upper() == 'SKILL.MD'):
                continue
            try:
                files[path] = tf.extractfile(m).read().decode('utf-8', errors='ignore')
                count += 1
            except Exception:
                continue
    return files


def scan_repo(repo):
    slug = repo['full_name'].replace('/', '__')
    out = {'repo': repo['full_name'], 'stars': repo['stars'], 'description': repo['description'],
           'pushed_at': repo['pushed_at'], 'status': 'ok'}
    try:
        if repo.get('size_kb', 0) > 200_000:
            raise ValueError('repo too large')
        files = extract_files(fetch_tarball(repo['full_name']))
        if not files:
            raise ValueError('no scannable files')
        card = scan_core.scan_files(files)
        out.update(card)
    except Exception as e:
        out['status'] = f'skipped: {e}'
        out.update({'type': 'unknown', 'level': -1, 'flags': [], 'injects': [], 'hooks': [],
                    'tool_regs': 0, 'domains': {}, 'env': {}, 'files_scanned': 0,
                    'manifest': None, 'install_scripts': {}, 'behaviors': {}})
    (SCANS / f'{slug}.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=list))
    return out


def summarize(card):
    return {k: card.get(k) for k in (
        'repo', 'stars', 'description', 'type', 'level', 'status', 'flags', 'injects', 'hooks',
        'tool_regs', 'files_scanned', 'pushed_at')} | {
        'domains': sorted(card.get('domains', {}), key=card.get('domains', {}).get, reverse=True)[:10],
        'env': sorted(card.get('env', {}), key=card.get('env', {}).get, reverse=True)[:10],
        'has_patch': any(f['id'] == 'runtime_patch' for f in card.get('flags', [])),
    }


def write_badge(card):
    slug = card['repo'].replace('/', '__')
    level = card['level']
    msg = f"C{level} · {len(card['flags'])} flags" if level >= 0 else 'unscanned'
    (DOCS / 'badge' / f'{slug}.json').write_text(json.dumps({
        'schemaVersion': 1, 'label': 'dsh-xray',
        'message': msg, 'color': LEVEL_COLORS.get(level, 'lightgrey')}))


def main(limit=100, workers=8):
    repos = json.loads((ROOT / 'data' / 'repos.json').read_text())[:limit]
    SCANS.mkdir(parents=True, exist_ok=True)
    (DOCS / 'badge').mkdir(parents=True, exist_ok=True)
    results = []
    with cf.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(scan_repo, r): r for r in repos}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            card = fut.result()
            results.append(card)
            write_badge(card)
            if i % 10 == 0 or i == len(repos):
                print(f'[{i}/{len(repos)}] scanned')
    results.sort(key=lambda c: -c['stars'])
    ok = [c for c in results if c['status'] == 'ok']
    (DOCS / 'data.json').write_text(json.dumps({
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'total': len(results), 'scanned': len(ok),
        'plugins': [summarize(c) for c in results],
    }, ensure_ascii=False))
    lv = {}
    for c in ok:
        lv[c['level']] = lv.get(c['level'], 0) + 1
    print(f"done: {len(ok)}/{len(results)} scanned, levels={dict(sorted(lv.items()))}")


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100,
         int(sys.argv[2]) if len(sys.argv) > 2 else 8)
