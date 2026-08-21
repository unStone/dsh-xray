#!/usr/bin/env python3
"""Pre-render the markdown docs into standalone HTML pages.

report.html used to fetch its markdown in the browser, so a crawler saw only
"Loading…" on the site's most substantial pages, and every ?doc= variant shared
one canonical and collapsed into a duplicate. Each document now gets its own
URL with the prose already in the HTML; the language switcher still swaps to
another locale client-side for readers who pick one.
"""
import html
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
SITE = 'https://unstone.github.io/dsh-xray'

# slug -> (source stem, output path, meta description)
PAGES = {
    'report': (
        'report/2026-08', 'report.html',
        'A capability survey of the DeepSeek Harness plugin ecosystem: 89% of plugins carry '
        'powerful capability, 76% patch the runtime, and none of it is declared anywhere.'),
    'plugins': (
        'guide/how-dsh-plugins-work', 'guide/plugins.html',
        'How dsh plugins work: the context object, injected services, waterfall hooks, the '
        'append-only session log, and why plugin installation has no permission model.'),
    'changelog': (
        'guide/changelog', 'guide/changelog.html',
        'What changed in dsh-xray and why — method and product changes. Scan results refresh '
        'daily on their own.'),
}


def esc(s):
    return html.escape(s, quote=False)


def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(^|[^*])\*([^*]+)\*', r'\1<em>\2</em>', s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
    return s


def md_to_html(src):
    """Small markdown subset: headings, tables, fences, lists, quotes, rules."""
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)
    blocks = []

    def stash(m):
        blocks.append(f'<pre><code>{esc(m.group(2).rstrip())}</code></pre>')
        return f'\x00{len(blocks) - 1}\x00'

    src = re.sub(r'```(\w*)\n(.*?)```', stash, src, flags=re.S)

    out, lines, i = [], src.split('\n'), 0
    while i < len(lines):
        ln = lines[i]
        if re.fullmatch(r'\x00\d+\x00', ln.strip()):
            out.append(ln.strip())
        elif not ln.strip():
            pass
        elif re.fullmatch(r'-{3,}', ln.strip()):
            out.append('<hr>')
        elif (m := re.match(r'(#{1,4})\s+(.*)', ln)):
            lvl = len(m.group(1))
            out.append(f'<h{lvl}>{inline(m.group(2))}</h{lvl}>')
        elif ln.startswith('> '):
            buf = []
            while i < len(lines) and lines[i].startswith('> '):
                buf.append(lines[i][2:])
                i += 1
            i -= 1
            out.append(f'<blockquote><p>{inline(" ".join(buf))}</p></blockquote>')
        elif ln.strip().startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append(lines[i].strip())
                i += 1
            i -= 1
            body = ''
            for idx, r in enumerate(rows):
                if re.fullmatch(r'\|[\s:|-]+\|', r):
                    continue
                tag = 'th' if idx == 0 else 'td'
                cells = [c.strip() for c in r.strip('|').split('|')]
                body += '<tr>' + ''.join(f'<{tag}>{inline(c)}</{tag}>' for c in cells) + '</tr>'
            out.append(f'<div class="table-wrap"><table>{body}</table></div>')
        elif re.match(r'[-*]\s+', ln):
            items = []
            while i < len(lines) and re.match(r'[-*]\s+', lines[i]):
                items.append(re.sub(r'^[-*]\s+', '', lines[i]))
                i += 1
            i -= 1
            out.append('<ul>' + ''.join(f'<li>{inline(t)}</li>' for t in items) + '</ul>')
        else:
            out.append(f'<p>{inline(ln)}</p>')
        i += 1

    body = '\n'.join(out)
    return re.sub(r'\x00(\d+)\x00', lambda m: blocks[int(m.group(1))], body)


def shell(slug, title, desc, body, depth):
    up = '../' * depth
    home = up or './'                      # depth 0 must not render href=""
    cur = lambda s: ' aria-current="page"' if s == slug else ''
    canonical = f'{SITE}/{PAGES[slug][1]}'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · dsh-xray</title>
<meta name="description" content="{html.escape(desc, quote=True)}">
<link rel="canonical" href="{canonical}">
<link rel="alternate" hreflang="en" href="{canonical}?lang=en">
<link rel="alternate" hreflang="zh" href="{canonical}?lang=zh">
<link rel="alternate" hreflang="x-default" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(desc, quote=True)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/atom+xml" href="{SITE}/feed.xml" title="dsh-xray">
<link rel="stylesheet" href="{up}style.css">
<style>
.md {{ max-width: 760px; margin: 0 auto; }}
.md h1 {{ font-size: 32px; letter-spacing: -0.8px; margin: 28px 0 8px; line-height: 1.2; }}
.md h2 {{ font-size: 22px; letter-spacing: -0.4px; margin: 38px 0 10px; padding-top: 18px; border-top: 1px solid var(--border); }}
.md h3 {{ font-size: 17px; margin: 24px 0 6px; }}
.md p {{ margin: 12px 0; }}
.md ul {{ margin: 12px 0; padding-left: 22px; }}
.md li {{ margin: 5px 0; }}
.md blockquote {{ margin: 20px 0; padding: 14px 18px; border-left: 3px solid var(--accent); background: var(--accent-soft); border-radius: 0 8px 8px 0; }}
.md blockquote p {{ margin: 0; font-size: 16.5px; font-weight: 600; }}
.md table {{ border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 14px; }}
.md th, .md td {{ border: 1px solid var(--border); padding: 7px 11px; text-align: left; vertical-align: top; }}
.md th {{ background: var(--chip-bg); font-weight: 600; }}
.md pre {{ background: var(--code-bg); border-radius: 8px; padding: 12px 14px; overflow-x: auto; margin: 14px 0; }}
.md pre code {{ background: none; padding: 0; font-size: 12.5px; line-height: 1.5; }}
.md hr {{ border: none; border-top: 1px solid var(--border); margin: 32px 0; }}
.md em {{ color: var(--muted); }}
.md .table-wrap {{ overflow-x: auto; }}
</style>
</head>
<body>
<div class="wrap">
<nav class="nav">
  <a class="brand" href="{home}">dsh-<span>xray</span></a>
  <div class="links">
    <a href="{up}registry.html" data-i18n="nav.registry">Registry</a>
    <a href="{up}report.html"{cur('report')} data-i18n="nav.report">Report</a>
    <a href="{up}levels.html" data-i18n="nav.levels">Levels</a>
    <a href="{up}guide/plugins.html"{cur('plugins')} data-i18n="nav.guide">How it works</a>
    <a href="{up}guide/changelog.html"{cur('changelog')} data-i18n="nav.changelog">Changelog</a>
    <a href="https://github.com/unStone/dsh-xray" data-i18n="nav.github">GitHub</a>
  </div>
  <div class="chips" id="langSwitch"></div>
</nav>
<article class="md" id="md">
{body}
</article>
<footer>
  <span data-i18n="foot.oss"></span> <a href="https://github.com/unStone/dsh-xray/issues" data-i18n="foot.issue"></a>
</footer>
</div>

<script src="{up}i18n.js"></script>
<script src="{up}mdview.js"></script>
<script>
xray.applyStatic();
xray.mountSwitcher(document.getElementById('langSwitch'));
// English prose ships in the HTML for crawlers; other locales load on demand.
mdview.swapLocale('{up}', '{PAGES[slug][0]}');
</script>
</body>
</html>
"""


def main():
    for slug, (stem, out_rel, desc) in PAGES.items():
        src = DOCS / f'{stem}.md'
        if not src.exists():
            continue
        text = src.read_text()
        title = re.search(r'^#\s+(.*)', text, re.M).group(1)
        body = md_to_html(text)
        out = DOCS / out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(shell(slug, title, desc, body, out_rel.count('/')))
        print(f'{out_rel}  ({len(body)} bytes of prose)')


if __name__ == '__main__':
    main()
