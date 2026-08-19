#!/usr/bin/env python3
"""Sample flags and fetch the exact source line each one cites.

The whole product rests on findings being checkable, so they have to actually
be checked. This pulls a deterministic random sample of flags, retrieves the
cited line from the repository, and prints it for review.

Usage: python audit_sample.py [n_per_flag] [seed]
"""
import json
import pathlib
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / 'docs' / 'data.json').read_text())
REPOS = {r['full_name']: r for r in json.loads((ROOT / 'data' / 'repos.json').read_text())}

# Only these carry file:line evidence; the rest derive from manifest/injects.
LINE_FLAGS = ('exec', 'eval', 'base64_decode', 'net_server')
EVIDENCE_RE = re.compile(r'([\w./-]+):(\d+)')


def fetch_line(repo, path, lineno):
    branch = (REPOS.get(repo) or {}).get('default_branch') or 'main'
    for ref in dict.fromkeys([branch, 'main', 'master']):
        url = f'https://raw.githubusercontent.com/{repo}/{ref}/{path}'
        r = subprocess.run(['curl', '-sL', '--max-time', '25', '--fail', url],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout:
            lines = r.stdout.split('\n')
            if lineno <= len(lines):
                start = max(0, lineno - 2)
                return [(i + 1, lines[i]) for i in range(start, min(len(lines), lineno + 1))]
            return [(0, f'(file has {len(lines)} lines, cited {lineno})')]
    return None


def main(n=6, seed=7):
    rng = random.Random(seed)
    ok = [p for p in DATA['plugins'] if p['level'] >= 0]
    jobs = []
    for fid in LINE_FLAGS:
        holders = [p for p in ok if any(f['id'] == fid for f in p['flags'])]
        for p in rng.sample(holders, min(n, len(holders))):
            ev = next(f['evidence'] for f in p['flags'] if f['id'] == fid)
            m = EVIDENCE_RE.search(ev)
            if m:
                jobs.append((fid, p['repo'], m.group(1), int(m.group(2))))

    print(f'sampling {len(jobs)} flags across {len(LINE_FLAGS)} rule types\n')
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda j: (j, fetch_line(j[1], j[2], j[3])), jobs))

    for (fid, repo, path, lineno), lines in results:
        print(f'--- [{fid}] {repo}  {path}:{lineno}')
        if lines is None:
            print('    (could not fetch)')
        else:
            for i, text in lines:
                mark = '>>' if i == lineno else '  '
                print(f'    {mark} {i}: {text.strip()[:150]}')
        print()


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6,
         int(sys.argv[2]) if len(sys.argv) > 2 else 7)
