/* Swap a pre-rendered document to another locale, client-side.
   The English prose is already in the HTML so crawlers and no-JS readers get
   the full text; this only runs when a reader has chosen another language. */
window.mdview = (function () {
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

  function render(src) {
    src = src.replace(/<!--[\s\S]*?-->/g, '');
    const blocks = [];
    src = src.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      blocks.push('<pre><code>' + esc(code.replace(/\n$/, '')) + '</code></pre>');
      return ' BLOCK' + (blocks.length - 1) + ' ';
    });

    const inline = (s) => esc(s)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

    const out = [];
    const lines = src.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i];
      let m;
      if (/^ BLOCK\d+ $/.test(ln.trim())) { out.push(ln.trim()); continue; }
      if (/^\s*$/.test(ln)) continue;
      if (/^---+$/.test(ln.trim())) { out.push('<hr>'); continue; }
      if ((m = ln.match(/^(#{1,4})\s+(.*)$/))) {
        const lvl = m[1].length;
        out.push('<h' + lvl + '>' + inline(m[2]) + '</h' + lvl + '>');
        continue;
      }
      if (ln.startsWith('> ')) {
        const buf = [];
        while (i < lines.length && lines[i].startsWith('> ')) buf.push(lines[i++].slice(2));
        i--;
        out.push('<blockquote><p>' + inline(buf.join(' ')) + '</p></blockquote>');
        continue;
      }
      if (ln.trim().startsWith('|')) {
        const rows = [];
        while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++].trim());
        i--;
        const cells = (r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        let html = '<div class="table-wrap"><table>';
        rows.forEach((r, idx) => {
          if (/^\|[\s:|-]+\|$/.test(r)) return;
          const tag = idx === 0 ? 'th' : 'td';
          html += '<tr>' + cells(r).map((c) => '<' + tag + '>' + inline(c) + '</' + tag + '>').join('') + '</tr>';
        });
        out.push(html + '</table></div>');
        continue;
      }
      if (/^[-*]\s+/.test(ln)) {
        const items = [];
        while (i < lines.length && /^[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^[-*]\s+/, ''));
        i--;
        out.push('<ul>' + items.map((t) => '<li>' + inline(t) + '</li>').join('') + '</ul>');
        continue;
      }
      out.push('<p>' + inline(ln) + '</p>');
    }
    return out.join('\n').replace(/ BLOCK(\d+) /g, (_, n) => blocks[+n]);
  }

  /** base: path prefix back to the site root; stem: doc path without extension. */
  function swapLocale(base, stem) {
    if (xray.lang === 'en') return;   // already in the HTML
    fetch(base + stem + '.' + xray.lang + '.md')
      .then((r) => (r.ok ? r.text() : Promise.reject(r.status)))
      .then((text) => {
        document.getElementById('md').innerHTML = render(text);
        const h1 = document.querySelector('.md h1');
        if (h1) document.title = h1.textContent + ' · dsh-xray';
      })
      .catch(() => { /* no translation for this locale; English stays */ });
  }

  return { render, swapLocale };
})();
