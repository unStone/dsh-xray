#!/usr/bin/env python3
"""Generate one crawlable HTML page per plugin, plus sitemap.xml and robots.txt.

The registry renders from data.json in the browser, so none of its ~4000 plugin
entries exist as far as a crawler is concerned. Someone searching for a specific
plugin by name should be able to land on its capability card; that only works if
each card is a real URL with real markup.

Pages are intentionally small and static: title, meta description, JSON-LD, the
evidence table, and a link into the interactive registry.
"""
import datetime
import html
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
OUT = DOCS / 'p'
SITE = 'https://unstone.github.io/dsh-xray'

FLAG_TEXT = {
    'runtime_patch': ('patches the dsh runtime', '给 dsh 运行时打补丁'),
    'prompt_surface': ('can rewrite the system prompt', '能改写系统提示词'),
    'api_intercept': ('can intercept API traffic', '能拦截 API 流量'),
    'subprocess_service': ('can spawn subprocesses', '能起子进程'),
    'tool_gate': ('gates tool execution', '介入工具执行'),
    'exec': ('executes system commands', '执行系统命令'),
    'eval': ('uses eval / new Function', '使用 eval'),
    'base64_decode': ('decodes base64 payloads', '解码 base64'),
    'net_server': ('starts a network server', '启动网络服务'),
    'token_env': ('reads credential-class env vars', '读取凭证类环境变量'),
    'install_script': ('runs code at install time', '安装期执行代码'),
    'no_manifest': ('ships no manifest', '没有 manifest'),
}
LEVEL_DESC = {
    3: 'powerful capability combined with sensitive behavior',
    2: 'one powerful capability or sensitive behavior',
    1: 'ordinary capability surface',
    0: 'no notable capability surface',
}
LEVEL_COLOR = {3: '#dc2626', 2: '#d97706', 1: '#65a30d', 0: '#16a34a'}

# Carrying the topic is not the same as being installable, and the card
# should say which one this is.
TYPE_TEXT = {'plugin': 'Installable plugin — declares a dsh.bundle manifest', 'client-only': 'Not installable — declares only dsh.client, which dsh plugin add cannot install', 'skill': 'A skill, not an installable plugin — ships SKILL.md with no plugin manifest', 'library': 'Not a plugin — depends on dsh packages but declares no plugin manifest', 'code-only': 'Not installable — has plugin code but no manifest to install it by', 'unrelated': 'No dsh integration found — this repository carries the dsh-plugin topic but shows no sign of connecting to dsh'}


def esc(s):
    return html.escape(str(s or ''), quote=True)


def star_bucket(n):
    """Display stars coarsely.

    Exact counts drift daily, which would rewrite every one of ~4000 pages on
    every scan and bloat the repository for no reader benefit. Buckets stay
    stable for weeks.
    """
    if n >= 10000:
        return f'{n // 1000}k+'
    if n >= 1000:
        return f'{n / 1000:.1f}k'
    for edge in (500, 100, 50, 10, 5, 1):
        if n >= edge:
            return f'{edge}+'
    return '0'


def page(p):
    repo = p['repo']
    slug = repo.replace('/', '__')
    lvl = p['level']
    flags = p.get('flags') or []
    name = repo.split('/')[-1]

    if lvl < 0:
        summary = f'{repo} has not been scanned yet.'
    else:
        bits = [FLAG_TEXT.get(f['id'], (f['id'], f['id']))[0] for f in flags[:4]]
        summary = (f'{repo} is a DeepSeek Harness plugin rated C{lvl} — {LEVEL_DESC[lvl]}. '
                   + (f'It {", ".join(bits)}.' if bits else
                      f'Scanning {p.get("files_scanned", 0)} code files turned up none of the '
                      'capabilities we look for: no runtime patch, no prompt or API surface, '
                      'no subprocess use, no credential-class environment reads and no '
                      'install-time scripts.'))

    rows = ''.join(
        f'<tr><td>{esc(FLAG_TEXT.get(f["id"], (f["id"],))[0])}</td>'
        f'<td><code>{esc(f["id"])}</code></td><td>{esc(f.get("evidence"))}</td></tr>'
        for f in flags)
    flags_table = (f'<h2>What it can do</h2><table><thead><tr><th>Capability</th><th>Flag</th>'
                   f'<th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>') if rows else ''

    def chips(items, title):
        if not items:
            return ''
        return (f'<h2>{title}</h2><p class="kv">'
                + ' '.join(f'<span>{esc(i)}</span>' for i in items) + '</p>')

    jsonld = json.dumps({
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        'name': name,
        'identifier': repo,
        'applicationCategory': 'DeveloperApplication',
        'operatingSystem': 'Any',
        'description': summary,
        'codeRepository': f'https://github.com/{repo}',
        'url': f'{SITE}/p/{slug}.html',
    }, ensure_ascii=False)

    lvl_badge = ('unscanned' if lvl < 0 else f'C{lvl}')
    color = LEVEL_COLOR.get(lvl, '#9ca3af')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(repo)} — capability card ({lvl_badge}) · dsh-xray</title>
<meta name="description" content="{esc(summary[:300])}">
<link rel="canonical" href="{SITE}/p/{slug}.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(repo)} — dsh plugin capability card">
<meta property="og:description" content="{esc(summary[:300])}">
<meta property="og:url" content="{SITE}/p/{slug}.html">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="../style.css">
<style>
.plugin-head {{ display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin:22px 0 6px; }}
.plugin-head h1 {{ font-size:26px; letter-spacing:-0.5px; }}
.lvl-pill {{ background:{color}; color:#fff; font-weight:700; border-radius:8px; padding:3px 12px; font-size:14px; }}
main {{ max-width:760px; }}
main table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:13.5px; }}
main th, main td {{ border:1px solid var(--border); padding:7px 10px; text-align:left; vertical-align:top; }}
main th {{ background:var(--chip-bg); }}
main h2 {{ font-size:16px; margin:26px 0 6px; }}
.kv span {{ background:var(--chip-bg); border-radius:6px; padding:2px 8px; font-size:12.5px; display:inline-block; margin:2px 2px 2px 0; }}
.lede {{ color:var(--muted); margin:8px 0 4px; }}
</style>
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
<div class="wrap">
<nav class="nav">
  <a class="brand" href="../">dsh-<span>xray</span></a>
  <div class="links">
    <a href="../registry.html">Registry</a>
    <a href="../report.html">Report</a>
    <a href="../levels.html">Levels</a>
    <a href="https://github.com/unStone/dsh-xray">GitHub</a>
  </div>
</nav>
<main>
  <div class="plugin-head">
    <h1>{esc(repo)}</h1>
    <span class="lvl-pill">{lvl_badge}</span>
  </div>
  <p class="lede">{esc(p.get('description'))}</p>
  <p class="lede">★ {star_bucket(p.get('stars', 0))} ·
     <a href="https://github.com/{esc(repo)}" rel="nofollow ugc">{esc(repo)} source on GitHub</a>
     · <a href="../registry.html#{esc(slug)}">this plugin in the registry</a></p>
  <p>{esc(summary)}</p>
  <p class="lede"><b>{esc(TYPE_TEXT.get(p.get('type'), ''))}</b></p>
  {flags_table}
  {chips(p.get('injects') or [], 'Services it injects')}
  {chips(p.get('hooks') or [], 'Hooks it attaches')}
  {chips(p.get('domains') or [], 'Outbound domains')}
  {chips(p.get('env') or [], 'Environment variables it reads')}
  <h2>How to read this</h2>
  <p>Levels measure capability surface and transparency, not maliciousness. A C3 plugin
  can be entirely legitimate — a desktop shell genuinely needs subprocesses. The point is
  that you can see this before installing. See <a href="../levels.html">the levels explained</a>
  and <a href="../report.html?doc=plugins">how dsh plugins work</a>.</p>
  <p>Findings come from static analysis of shipped code; nothing is executed. Think a flag
  is wrong? <a href="https://github.com/unStone/dsh-xray/issues">Open an issue</a> — every
  flag cites the file and line it came from.</p>
</main>
<footer>Apache-2.0 · <a href="https://github.com/unStone/dsh-xray">dsh-xray</a></footer>
</div>
</body>
</html>
"""


COLLECTIONS = [
    ('runtime-patch', 'dsh plugins that patch the runtime',
     'Plugins declaring manifest.bundle.patch, which modifies dsh core behaviour at load time — the deepest supply-chain surface in the system.',
     lambda p: any(f['id'] == 'runtime_patch' for f in p['flags'])),
    ('prompt-surface', 'dsh plugins that can rewrite the system prompt',
     'Plugins injecting systemPrompt or hooking system-prompt/assemble. They shape what the model is told, without changing what you see on screen.',
     lambda p: any(f['id'] == 'prompt_surface' for f in p['flags'])),
    ('api-intercept', 'dsh plugins that can intercept API traffic',
     'Plugins injecting apiProxy or hooking api/gate, sitting between you and the model.',
     lambda p: any(f['id'] == 'api_intercept' for f in p['flags'])),
    ('subprocess', 'dsh plugins that spawn subprocesses or run commands',
     'Plugins injecting the subprocess service or executing system commands from shipped code.',
     lambda p: any(f['id'] in ('subprocess_service', 'exec') for f in p['flags'])),
    ('credentials', 'dsh plugins that read credential-class environment variables',
     'Plugins reading environment variables whose names contain KEY, TOKEN, SECRET or PASSWORD — often legitimately, since that is how a storage or model plugin authenticates.',
     lambda p: any(f['id'] == 'token_env' for f in p['flags'])),
    ('install-scripts', 'dsh plugins that run code at install time',
     'Plugins with preinstall, install or postinstall scripts: code that runs before you have used the plugin once.',
     lambda p: any(f['id'] == 'install_script' for f in p['flags'])),
    ('not-installable', 'Repositories carrying the dsh-plugin topic that are not installable plugins',
     'Adding a GitHub topic takes a click; being installable takes a dsh.bundle manifest. These repositories carry the topic without one — some are skills or libraries, others show no connection to dsh at all.',
     lambda p: p.get('type') in ('client-only', 'library', 'code-only', 'unrelated')),
    ('minimal-surface', 'dsh plugins with no notable capability surface',
     'Plugins rated C0: no powerful capability and no sensitive behaviour detected in shipped code.',
     lambda p: p['level'] == 0),
]


def collection_page(slug, title, desc, rows, total):
    body = ''.join(
        f'<tr><td><a href="../p/{esc(p["repo"].replace("/", "__"))}.html">{esc(p["repo"])}</a></td>'
        f'<td><span class="lvl-pill" style="background:{LEVEL_COLOR.get(p["level"], "#9ca3af")}">C{p["level"]}</span></td>'
        f'<td>{star_bucket(p.get("stars", 0))}</td>'
        f'<td>{esc((p.get("description") or "")[:110])}</td></tr>' for p in rows)
    shown = f'; the {len(rows)} most-starred are listed' if len(rows) < total else ''
    jsonld = json.dumps({
        '@context': 'https://schema.org', '@type': 'CollectionPage',
        'name': title, 'description': desc, 'url': f'{SITE}/c/{slug}.html',
        'isPartOf': {'@type': 'WebSite', 'name': 'dsh-xray', 'url': f'{SITE}/'},
    }, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} ({total}) · dsh-xray</title>
<meta name="description" content="{esc(desc[:300])}">
<link rel="canonical" href="{SITE}/c/{slug}.html">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc[:300])}">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/atom+xml" href="{SITE}/feed.xml" title="dsh-xray">
<link rel="stylesheet" href="../style.css">
<style>
main {{ max-width: 900px; }}
main table {{ border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 13.5px; }}
main th, main td {{ border: 1px solid var(--border); padding: 7px 10px; text-align: left; }}
main th {{ background: var(--chip-bg); }}
.lvl-pill {{ color: #fff; font-weight: 700; border-radius: 6px; padding: 1px 8px; font-size: 12px; }}
.lede {{ color: var(--muted); max-width: 700px; }}
</style>
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
<div class="wrap">
<nav class="nav">
  <a class="brand" href="../">dsh-<span>xray</span></a>
  <div class="links">
    <a href="../registry.html">Registry</a><a href="../report.html">Report</a>
    <a href="../levels.html">Levels</a><a href="https://github.com/unStone/dsh-xray">GitHub</a>
  </div>
</nav>
<main>
  <h1>{esc(title)}</h1>
  <p class="lede">{esc(desc)}</p>
  <p class="lede"><b>{total}</b> of {{scanned}} scanned plugins qualify{shown}. Levels measure capability
  surface and transparency, <b>not</b> maliciousness — see <a href="../levels.html">how to read them</a>.</p>
  <table><thead><tr><th>Plugin</th><th>Level</th><th>Stars</th><th>Description</th></tr></thead>
  <tbody>{body}</tbody></table>
  <p class="lede">Other views: {{others}}</p>
</main>
<footer>Apache-2.0 · static analysis only · <a href="https://github.com/unStone/dsh-xray/issues">report a false positive</a></footer>
</div>
</body>
</html>
"""


def write_collections(plugins, out_dir):
    ok = [p for p in plugins if p['level'] >= 0]
    links = ' · '.join(f'<a href="{s}.html">{t.replace("dsh plugins ", "")}</a>'
                       for s, t, _, _ in COLLECTIONS)
    for slug, title, desc, pred in COLLECTIONS:
        matching = sorted([p for p in ok if pred(p)], key=lambda p: -p['stars'])
        rows = matching[:300]
        html = collection_page(slug, title, desc, rows, len(matching))
        html = html.replace('{scanned}', str(len(ok))).replace('{others}', links)
        (out_dir / f'{slug}.html').write_text(html)
    return [s for s, _, _, _ in COLLECTIONS]


def diff_against(plugins, previous):
    """What changed since the last published scan.

    A registry you check once is a directory; a registry that tells you what
    moved is worth coming back to. Levels changing on a plugin you already
    installed is the case that actually matters.
    """
    before = {p['repo']: p for p in previous}
    added, changed = [], []
    for p in plugins:
        old = before.get(p['repo'])
        if old is None:
            if p['level'] >= 0:
                added.append(p)
            continue
        if old.get('level') != p.get('level') and p['level'] >= 0 and old.get('level', -1) >= 0:
            changed.append((p, old['level']))
        else:
            oldf = {f['id'] for f in old.get('flags') or []}
            newf = {f['id'] for f in p.get('flags') or []}
            gained = newf - oldf
            if gained & {'runtime_patch', 'prompt_surface', 'api_intercept',
                         'subprocess_service', 'token_env', 'install_script'}:
                changed.append((p, None))
    added.sort(key=lambda p: -p['stars'])
    changed.sort(key=lambda t: -t[0]['stars'])
    return added, changed


def write_feed(plugins, path, today, previous=None):
    """Atom feed: newly scanned plugins, and capability changes on existing ones."""
    entries = ''
    if previous:
        added, changed = diff_against(plugins, previous)
        if changed:
            rows = ''.join(
                f'&lt;li&gt;{esc(p["repo"])}: '
                + (f'C{old} → C{p["level"]}' if old is not None else 'gained capability flags')
                + '&lt;/li&gt;' for p, old in changed[:40])
            entries += (
                f'<entry><title>{len(changed)} plugin(s) changed capability on {today}</title>'
                f'<link href="{SITE}/registry.html"/>'
                f'<id>{SITE}/changes/{today}</id><updated>{today}T00:00:00Z</updated>'
                f'<summary type="html">&lt;ul&gt;{rows}&lt;/ul&gt;</summary></entry>')
        if added:
            rows = ''.join(f'&lt;li&gt;{esc(p["repo"])} — C{p["level"]}&lt;/li&gt;' for p in added[:40])
            entries += (
                f'<entry><title>{len(added)} plugin(s) newly scanned on {today}</title>'
                f'<link href="{SITE}/registry.html"/>'
                f'<id>{SITE}/added/{today}</id><updated>{today}T00:00:00Z</updated>'
                f'<summary type="html">&lt;ul&gt;{rows}&lt;/ul&gt;</summary></entry>')

    fresh = sorted([p for p in plugins if p.get('first_seen')],
                   key=lambda p: (p['first_seen'], p['stars']), reverse=True)[:40]
    entries += ''.join(
        f'<entry><title>{esc(p["repo"])} — C{p["level"]}</title>'
        f'<link href="{SITE}/p/{p["repo"].replace("/", "__")}.html"/>'
        f'<id>{SITE}/p/{p["repo"].replace("/", "__")}.html</id>'
        f'<updated>{p["first_seen"]}T00:00:00Z</updated>'
        f'<summary>{esc((p.get("description") or "")[:280])}</summary></entry>' for p in fresh)
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        '<title>dsh-xray — newly scanned plugins</title>'
        f'<link href="{SITE}/feed.xml" rel="self"/><link href="{SITE}/"/>'
        f'<id>{SITE}/</id><updated>{today}T00:00:00Z</updated>'
        f'{entries}</feed>')


def write_llms_txt(path, plugins, collections, today):
    """An llms.txt for assistants answering "is <plugin> safe".

    Google states it does not use llms.txt, and this is not written expecting it
    to. Other assistants do read it, and a wrong answer about a plugin's rating
    is worth the few lines it costs to prevent.
    """
    ok = [p for p in plugins if p['level'] >= 0]
    lines = [
        '# dsh-xray',
        '',
        '> Capability cards for DeepSeek Harness (dsh) plugins: what a plugin declares versus '
        'what its shipped code actually does, each finding carrying file:line evidence. '
        'Static analysis only — nothing is executed, and levels measure capability surface and '
        'transparency, not maliciousness.',
        '',
        f'Data as of {today}: {len(ok)} plugins scanned out of {len(plugins)} known repositories.',
        '',
        '## Key pages',
        f'- [Registry]({SITE}/registry.html): searchable capability cards for every scanned plugin.',
        f'- [Ecosystem report]({SITE}/report.html): why the ecosystem has no plugin permission model.',
        f'- [Capability levels]({SITE}/levels.html): what C0-C3 mean, and what they do not mean.',
        f'- [How dsh plugins work]({SITE}/report.html?doc=plugins): the plugin model background.',
        f'- [Machine-readable data]({SITE}/data.json): every card as JSON.',
        '',
        '## Per-plugin pages',
        f'- `{SITE}/p/<owner>__<repo>.html` — the capability card for one plugin.',
        '',
        '## Collections',
    ] + [f'- [{s}]({SITE}/c/{s}.html)' for s in collections] + [
        '',
        '## Answering questions about a plugin',
        '- A C3 rating does NOT mean a plugin is malicious or should not be installed. It means '
        'the plugin has broad capability and sensitive behaviour, which many legitimate tools '
        'genuinely require.',
        '- Cite the plugin page URL so the reader can check the evidence themselves.',
        '- This project cannot detect malware or establish intent, and says so.',
    ]
    path.write_text('\n'.join(lines) + '\n')


def main():
    data = json.loads((DOCS / 'data.json').read_text())
    plugins = data['plugins']
    # The committed copy from the previous run is what "changed" is measured against.
    try:
        previous = json.loads(subprocess.run(
            ['git', 'show', 'HEAD:docs/data.json'], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout)['plugins']
    except Exception:
        previous = None
    OUT.mkdir(parents=True, exist_ok=True)

    keep = set()
    for p in plugins:
        slug = p['repo'].replace('/', '__')
        keep.add(f'{slug}.html')
        (OUT / f'{slug}.html').write_text(page(p))

    for stale in OUT.glob('*.html'):       # repos that left the topic
        if stale.name not in keep:
            stale.unlink()

    today = datetime.date.today().isoformat()
    coll_dir = DOCS / 'c'
    coll_dir.mkdir(parents=True, exist_ok=True)
    collections = write_collections(plugins, coll_dir)
    write_feed(plugins, DOCS / 'feed.xml', today, previous)
    write_llms_txt(DOCS / 'llms.txt', plugins, collections, today)

    # A sitemap index with per-section children: 7k URLs in one file is past the
    # point where that is good practice, and fresh filenames also get re-fetched
    # rather than inheriting a stuck status on the old one.
    pages = ['', 'registry.html', 'report.html', 'levels.html', 'levels-diagram.html',
             'guide/plugins.html', 'guide/changelog.html'] + [f'c/{c}.html' for c in collections]

    def urlset(entries, freq, prio):
        body = ''.join(
            f'<url><loc>{SITE}/{u}</loc><lastmod>{today}</lastmod>'
            f'<changefreq>{freq}</changefreq><priority>{prio}</priority></url>' for u in entries)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f'{body}</urlset>')

    (DOCS / 'sitemap-pages.xml').write_text(urlset(pages, 'daily', '1.0'))
    (DOCS / 'sitemap-plugins.xml').write_text(urlset(
        [f'p/{p["repo"].replace("/", "__")}.html' for p in plugins], 'weekly', '0.6'))
    (DOCS / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'<sitemap><loc>{SITE}/sitemap-pages.xml</loc><lastmod>{today}</lastmod></sitemap>'
        f'<sitemap><loc>{SITE}/sitemap-plugins.xml</loc><lastmod>{today}</lastmod></sitemap>'
        '</sitemapindex>')
    urls = pages + [1] * len(plugins)
    (DOCS / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')
    print(f'{len(plugins)} plugin pages, {len(collections)} collections, feed + llms.txt, '
          f'sitemap index ({len(pages)} pages + {len(plugins)} plugins)')


if __name__ == '__main__':
    main()
