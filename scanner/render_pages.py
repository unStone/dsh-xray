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
                   + (f'It {", ".join(bits)}.' if bits else 'No notable capability flags were found.'))

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
  <p class="lede">★ {star_bucket(p.get('stars', 0))} · <a href="https://github.com/{esc(repo)}">source on GitHub</a>
     · <a href="../registry.html#{esc(slug)}">open in the registry</a></p>
  <p>{esc(summary)}</p>
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


def main():
    data = json.loads((DOCS / 'data.json').read_text())
    plugins = data['plugins']
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
    urls = ['', 'registry.html', 'report.html', 'levels.html',
            'report.html?doc=plugins', 'report.html?doc=changelog']
    entries = ''.join(
        f'<url><loc>{SITE}/{u}</loc><lastmod>{today}</lastmod>'
        f'<changefreq>daily</changefreq><priority>1.0</priority></url>' for u in urls)
    entries += ''.join(
        f'<url><loc>{SITE}/p/{p["repo"].replace("/", "__")}.html</loc>'
        f'<lastmod>{today}</lastmod><changefreq>weekly</changefreq>'
        f'<priority>0.6</priority></url>' for p in plugins)
    (DOCS / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'{entries}</urlset>')
    (DOCS / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')
    print(f'{len(plugins)} plugin pages + sitemap ({len(urls) + len(plugins)} urls)')


if __name__ == '__main__':
    main()
