#!/usr/bin/env python3
"""Write the English text of every data-i18n element into the HTML.

The i18n pass fills these elements in the browser, which means a first-pass
crawler — which does not run scripts — sees the headings, paragraphs and FAQ
answers as empty tags. The landing page carried 66 of them and read as about a
hundred words to a crawler while showing far more to a reader.

Filling them at build time makes English the served text; the switcher still
swaps to another locale for readers who pick one. Run after editing i18n.js or
any page that uses data-i18n.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
PAGES = ['index.html', 'registry.html', 'levels.html']


def english_strings(js):
    """Quoted entries from the `en:` block. Arrow-function values are skipped."""
    block = js[js.index('en: {'):js.index('zh: {')]
    out = {}
    for m in re.finditer(r"'([\w.-]+)':\s*'((?:[^'\\]|\\.)*)'", block):
        out[m.group(1)] = m.group(2).replace("\\'", "'")
    return out


def fill(page_text, strings):
    filled = [0]

    def one(m):
        key, tag = m.group('key'), m.group('tag')
        value = strings.get(key)
        if not value:
            return m.group(0)
        filled[0] += 1
        return f'{m.group("open")}{value}</{tag}>'

    pattern = re.compile(
        r'(?P<open><(?P<tag>[a-z][\w-]*)\b[^>]*\bdata-i18n="(?P<key>[\w.-]+)"[^>]*>)\s*</(?P=tag)>')
    return pattern.sub(one, page_text), filled[0]


def main():
    strings = english_strings((DOCS / 'i18n.js').read_text())
    total = 0
    for name in PAGES:
        p = DOCS / name
        if not p.exists():
            continue
        text, n = fill(p.read_text(), strings)
        p.write_text(text)
        total += n
        print(f'{name}: filled {n}')
    if total == 0:
        print('nothing to fill')
    return 0


if __name__ == '__main__':
    sys.exit(main())
