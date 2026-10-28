(() => {
  'use strict';
  const t = xray.t;
  const boot = JSON.parse(document.getElementById('registryBootstrap').textContent);
  if (boot.version !== 1) throw new Error(`Unsupported registry version: ${boot.version}`);
  const HOT = new Set(['runtime_patch', 'prompt_surface', 'api_intercept', 'exec', 'eval', 'token_env', 'install_script']);
  const POWERFUL = new Set(['subprocess', 'apiProxy', 'systemPrompt', 'sandbox', 'webServer', 'approval']);
  const SITE = 'https://unstone.github.io/dsh-xray';
  const tbl = document.getElementById('tbl');
  const status = document.getElementById('loadStatus');
  const search = document.getElementById('q');
  const shardRequests = new Map();
  let index = null, indexRequest = null, page = 0, lv = 'all', pluginOnly = false, query = '';
  let navigation = 0;
  const esc = value => String(value ?? '').replace(/[&<>"']/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const flagChip = id => `<span class="flag ${HOT.has(id) ? 'hot' : ''}">${esc(t('reg.f.' + id))}</span>`;

  async function fetchJSON(path) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, {signal: controller.signal});
      if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  function loadIndex() {
    if (index) return Promise.resolve(index);
    if (!indexRequest) {
      indexRequest = fetchJSON(boot.index).then(entries => {
        if (!Array.isArray(entries) || entries.length !== boot.total) {
          throw new Error(`Invalid registry index: expected ${boot.total} entries`);
        }
        index = entries;
        return index;
      }).catch(error => { indexRequest = null; throw error; });
    }
    return indexRequest;
  }

  function setStatus(message, retry) {
    status.replaceChildren();
    status.append(document.createTextNode(message));
    if (retry) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = t('reg.retry');
      button.addEventListener('click', retry);
      status.append(' ', button);
    }
  }

  function filtered() {
    let rows = index || boot.initial;
    if (pluginOnly) rows = rows.filter(p => p.type === 'plugin');
    if (lv !== 'all') rows = rows.filter(p => String(p.level) === lv);
    if (query) {
      const key = query.toLowerCase();
      rows = rows.filter(p => `${p.repo} ${p.description || ''} ${(p.injects || []).join(' ')}`.toLowerCase().includes(key));
    }
    return rows;
  }

  function render() {
    const rows = filtered();
    const total = index ? rows.length : boot.total;
    page = Math.max(0, Math.min(page, Math.ceil(total / boot.page_size) - 1));
    const start = page * boot.page_size;
    const visible = rows.slice(start, start + boot.page_size);
    tbl.innerHTML = visible.map((p, i) => `<div class="row" data-repo="${esc(p.repo)}">
      <div class="row-head" role="button" tabindex="0" aria-expanded="false" aria-controls="detail-${i}">
        <div><div class="name"><a href="https://github.com/${esc(p.repo)}" target="_blank" rel="nofollow ugc noopener">${esc(p.repo)}</a></div>
        <div class="desc">${esc(p.description)}</div>
        ${p.type && p.type !== 'plugin' ? `<div class="notplug">${esc(t('reg.type.' + p.type))}</div>` : ''}</div>
        <div class="stars">★ ${p.stars >= 1000 ? (p.stars / 1000).toFixed(1) + 'k' : p.stars}</div>
        <div class="lvl ${p.level < 0 ? 'lvx' : 'lv' + p.level}">${p.level < 0 ? '—' : 'C' + p.level}</div>
        <div class="flags">${p.flags.map(flagChip).join('')}</div>
      </div><div class="detail" id="detail-${i}"></div></div>`).join('') || `<div class="empty">${esc(t('reg.empty'))}</div>`;
    document.getElementById('pageSummary').textContent = t('reg.range', total ? start + 1 : 0, Math.min(start + visible.length, total), total);
    document.getElementById('prevPage').disabled = page === 0;
    document.getElementById('nextPage').disabled = start + visible.length >= total;
  }

  async function update() {
    const current = ++navigation;
    tbl.setAttribute('aria-busy', 'true');
    setStatus(t('reg.indexLoading'));
    try {
      await loadIndex();
      if (current !== navigation) return;
      render();
      setStatus('');
    } catch (error) {
      if (current === navigation) setStatus(t('reg.indexError'), update);
      console.error('Registry search index failed', error);
    } finally {
      if (current === navigation) tbl.setAttribute('aria-busy', 'false');
    }
  }

  async function loadCard(repo) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(repo));
    const key = (new Uint8Array(digest)[0] % 64).toString(16).padStart(2, '0');
    const path = boot.details[key];
    if (!path) throw new Error(`Missing detail shard for ${repo}`);
    if (!shardRequests.has(path)) {
      const request = fetchJSON(path).catch(error => { shardRequests.delete(path); throw error; });
      shardRequests.set(path, request);
    }
    const shard = await shardRequests.get(path);
    if (shard[repo]?.repo !== repo) throw new Error(`Missing capability card: ${repo}`);
    return shard[repo];
  }

  function detail(p) {
    if (p.level < 0) return `<p class="evid">${esc(p.status)}</p>`;
    let h = p.refresh_status === 'deferred' ? `<p class="evid">${esc(t('reg.deferred'))}</p>` : '';
    if (p.flags?.length) h += `<h4>${esc(t('reg.flags'))}</h4>` + p.flags.map(f =>
      `<div>${flagChip(f.id)} <span class="evid">${esc(f.evidence)}</span></div>`).join('');
    for (const [key, label] of [['injects', 'services'], ['hooks', 'hooks'], ['domains', 'domains'], ['env', 'env']]) {
      if (p[key]?.length) h += `<h4>${esc(t('reg.' + label))} (${p[key].length})</h4><div class="kv">` +
        p[key].map(s => `<span class="${key === 'injects' && POWERFUL.has(s) ? 'pw' : ''}">${esc(s)}</span>`).join('') + '</div>';
    }
    const partial = p.tool_reg_analysis?.status === 'partial';
    h += `<h4>·</h4>${esc(partial ? t('reg.toolsPartial', p.tool_regs) : t('reg.tools', p.tool_regs, p.files_scanned))}`;
    if (p.tool_reg_evidence?.length) h += `<h4>${esc(t('reg.toolEvidence'))}</h4>` + p.tool_reg_evidence.map(e =>
      `<div class="evid">${esc(e.path)}:${e.line} · ${esc(e.reason)}</div>`).join('');
    if (partial) {
      h += (p.tool_reg_analysis.diagnostics || []).map(e =>
        `<div class="evid">${esc(e.path)}:${e.line} · ${esc(e.reason)}</div>`).join('');
      h += (p.tool_reg_analysis.notes || []).map(n => `<p class="evid">${esc(n)}</p>`).join('');
    }
    return h;
  }

  async function expand(row) {
    row.classList.add('open');
    row.querySelector('.row-head').setAttribute('aria-expanded', 'true');
    const box = row.querySelector('.detail');
    if (box.dataset.loaded || box.dataset.loading) return;
    box.dataset.loading = 'true';
    box.textContent = t('reg.loading');
    try {
      const card = await loadCard(row.dataset.repo);
      if (!row.isConnected) return;
      box.innerHTML = detail(card);
      if (card.level >= 0) {
        const slug = card.repo.replace('/', '__');
        const badgeUrl = `https://img.shields.io/endpoint?url=${encodeURIComponent(SITE + '/badge/' + slug + '.json')}`;
        const markdown = `[![dsh-xray](${badgeUrl})](${SITE}/registry.html#${slug})`;
        const badge = document.createElement('div');
        badge.className = 'badge-line';
        const image = document.createElement('img');
        image.src = badgeUrl;
        image.alt = 'badge';
        image.loading = 'lazy';
        const text = document.createElement('span');
        text.className = 'mono';
        text.textContent = markdown;
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.textContent = t('reg.copy');
        copy.addEventListener('click', async () => {
          try { await navigator.clipboard.writeText(markdown); copy.textContent = t('reg.copied'); }
          catch (error) { copy.textContent = t('reg.copyError'); console.error('Badge copy failed', error); }
        });
        badge.append(image, text, copy);
        box.append(badge);
      }
      box.dataset.loaded = 'true';
    } catch (error) {
      if (!row.isConnected) return;
      box.textContent = t('reg.detailError') + ' ';
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = t('reg.retry');
      retry.addEventListener('click', () => expand(row));
      box.append(retry);
      console.error(`Registry detail failed: ${row.dataset.repo}`, error);
    } finally {
      delete box.dataset.loading;
    }
  }

  function toggle(head) {
    const row = head.closest('.row');
    if (row.classList.contains('open')) {
      row.classList.remove('open');
      head.setAttribute('aria-expanded', 'false');
    } else expand(row);
  }
  tbl.addEventListener('click', event => {
    if (event.target.closest('a, button')) return;
    const head = event.target.closest('.row-head');
    if (head) toggle(head);
  });
  tbl.addEventListener('keydown', event => {
    if (event.target.matches('.row-head') && ['Enter', ' '].includes(event.key)) {
      event.preventDefault(); toggle(event.target);
    }
  });

  async function openHash() {
    const slug = location.hash.slice(1);
    if (!slug) return;
    let repo;
    try { repo = decodeURIComponent(slug).replace('__', '/'); }
    catch { setStatus(t('reg.notFound')); return; }
    const current = ++navigation;
    try {
      let rows = index || boot.initial;
      if (!rows.some(p => p.repo === repo)) {
        setStatus(t('reg.indexLoading'));
        rows = await loadIndex();
      }
      if (current !== navigation) return;
      const position = rows.findIndex(p => p.repo === repo);
      if (position < 0) { setStatus(t('reg.notFound')); return; }
      query = ''; search.value = ''; lv = 'all'; pluginOnly = false;
      document.querySelectorAll('#lvlChips .chip').forEach(c => c.classList.toggle('on', c.dataset.lv === 'all'));
      document.getElementById('pluginOnly').classList.remove('on');
      page = Math.floor(position / boot.page_size);
      render(); setStatus('');
      const row = [...tbl.querySelectorAll('.row')].find(el => el.dataset.repo === repo);
      await expand(row);
      if (row.isConnected) row.scrollIntoView({block: 'start'});
    } catch (error) {
      if (current === navigation) setStatus(t('reg.indexError'), openHash);
      console.error('Registry deep link failed', error);
    } finally {
      if (current === navigation) tbl.setAttribute('aria-busy', 'false');
    }
  }

  xray.applyStatic();
  xray.mountSwitcher(document.getElementById('langSwitch'));
  document.title = 'dsh-xray · ' + t('reg.title');
  document.getElementById('stats').innerHTML = t('reg.stats', {
    ...boot, c3: boot.levels['3'], c2: boot.levels['2'], date: boot.generated_at.slice(0, 16).replace('T', ' ')
  });
  render();
  openHash();
  window.addEventListener('hashchange', openHash);
  search.addEventListener('input', () => { query = search.value.trim(); page = 0; update(); });
  document.getElementById('lvlChips').addEventListener('click', event => {
    if (!event.target.dataset.lv) return;
    lv = event.target.dataset.lv; page = 0;
    document.querySelectorAll('#lvlChips .chip').forEach(c => c.classList.toggle('on', c === event.target));
    update();
  });
  document.getElementById('pluginOnly').addEventListener('click', event => {
    pluginOnly = !pluginOnly; page = 0; event.target.classList.toggle('on', pluginOnly); update();
  });
  for (const [id, step] of [['prevPage', -1], ['nextPage', 1]]) {
    document.getElementById(id).addEventListener('click', async () => {
      page += step;
      await update();
      tbl.scrollIntoView({block: 'start'});
    });
  }
})();
