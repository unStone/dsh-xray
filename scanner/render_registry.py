import hashlib
import json
import pathlib

DOCS = pathlib.Path(__file__).resolve().parent.parent / 'docs'
START = '<!--REGISTRY_BOOTSTRAP_START-->'
END = '<!--REGISTRY_BOOTSTRAP_END-->'
PAGE_SIZE = 50


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def bucket(repo):
    return f'{hashlib.sha256(repo.encode()).digest()[0] % 64:02x}'


def assets(manifest):
    return {manifest['index'], *manifest['details'].values()} if manifest else set()


def build(docs=DOCS):
    data = json.loads((docs / 'data.json').read_text())
    plugins = data['plugins']
    if data['total'] != len(plugins):
        raise ValueError(f"Snapshot total {data['total']} does not match {len(plugins)} cards")
    names = [p['repo'] for p in plugins]
    if len(set(names)) != len(names):
        raise ValueError('Snapshot contains duplicate repository names')
    page = (docs / 'registry.html').read_text()
    if page.count(START) != 1 or page.count(END) != 1 or page.index(START) >= page.index(END):
        raise ValueError('registry.html requires exactly one ordered bootstrap marker pair')

    stats = {k: data[k] for k in ('generated_at', 'total', 'scanned', 'discovered')}
    stats['levels'] = {str(level): sum(p['level'] == level for p in plugins) for level in range(4)}
    index = [{k: p.get(k) for k in ('repo', 'stars', 'description', 'type', 'level', 'injects')}
             | {'flags': [f['id'] for f in p.get('flags', [])]} for p in plugins]
    shards = {f'{i:02x}': {} for i in range(64)}
    for p in plugins:
        shards[bucket(p['repo'])][p['repo']] = p

    previous_file = docs / 'registry-manifest.json'
    old = json.loads(previous_file.read_text()) if previous_file.exists() else {}
    output = docs / 'registry'
    output.mkdir(exist_ok=True)

    def write_asset(stem, value):
        content = encoded(value).encode()
        digest = hashlib.sha256(content).hexdigest()[:20]
        path = f'registry/{stem}-{digest}.json'
        (docs / path).write_bytes(content)
        return path

    manifest = {'version': 1, **stats, 'index': write_asset('index', index),
                'details': {key: write_asset(f'detail-{key}', value) for key, value in shards.items()}}
    # Repeated builds keep the same previous generation, rather than expiring it.
    previous = old.get('previous') if old.get('current') == manifest else old.get('current')
    bootstrap = encoded({**manifest, 'page_size': PAGE_SIZE, 'initial': index[:PAGE_SIZE]})
    bootstrap = bootstrap.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    script = f'<script type="application/json" id="registryBootstrap">{bootstrap}</script>'
    before, rest = page.split(START)
    _, after = rest.split(END)
    (docs / 'registry.html').write_text(f'{before}{START}\n{script}\n{END}{after}')
    (docs / 'stats.json').write_text(encoded(stats))
    previous_file.write_text(encoded({'current': manifest, 'previous': previous}))
    keep = assets(manifest) | assets(previous)
    for path in output.glob('*.json'):
        if f'registry/{path.name}' not in keep:
            path.unlink()
    print(f'Registry: {len(index)} entries, {min(len(index), PAGE_SIZE)} inline, 64 detail shards')
    return manifest


if __name__ == '__main__':
    build()
