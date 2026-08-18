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


def fetch_files(full_name):
    """Stream the tarball through `gh api` and pull out code files as they pass.

    Streaming (mode 'r|gz') means repository size barely matters: we stop once
    MAX_FILES code files are collected instead of buffering the whole archive,
    so asset-heavy repos stay scannable.
    """
    proc = subprocess.Popen(['gh', 'api', f'repos/{full_name}/tarball'],
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
                # package.json files are small and carry the manifest — never let
                # the code-file cap truncate them, or which manifest we report
                # would depend on tar ordering.
                if path.rsplit('/', 1)[-1] != 'package.json' and len(files) >= MAX_FILES:
                    continue
                try:
                    files[path] = tf.extractfile(m).read().decode('utf-8', errors='ignore')
                except Exception:
                    continue
    except Exception as e:
        if not files:
            raise ValueError(f'download failed: {type(e).__name__}')
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.terminate()
        proc.wait(timeout=10)
    if not files:
        raise ValueError('no scannable files')
    return files


def scan_repo(repo):
    slug = repo['full_name'].replace('/', '__')
    out = {'repo': repo['full_name'], 'stars': repo['stars'], 'description': repo['description'],
           'pushed_at': repo['pushed_at'], 'status': 'ok'}
    try:
        card = scan_core.scan_files(fetch_files(repo['full_name']))
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
