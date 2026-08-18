/* dsh-xray i18n — zero-build, shared by index.html (landing) and registry.html */
window.XRAY_I18N = {
en: {
  _name: 'English',
  'report.banner': 'New — <b>The dsh Plugin Ecosystem Has No Permission Model</b>: a capability survey of the most-installed plugins.', 'report.read': 'Read the report →',
  'nav.registry': 'Registry', 'nav.report': 'Report', 'nav.github': 'GitHub',
  'hero.title': 'X-ray for agent plugins',
  'hero.sub': 'Every DeepSeek Harness plugin gets a capability card: what it declares vs. what its code actually does — with file:line evidence.',
  'hero.cta1': 'Browse the registry', 'hero.cta2': 'Get your badge',
  'hero.stat': (s) => `${s.scanned} repos scanned · ${s.c3} × C3 · ${s.c2} × C2 · updated ${s.date} UTC`,
  'why.title': 'Plugins run inside your agent. Know what they can do.',
  'why.p': 'The dsh-plugin ecosystem grew from ~200 to 7,000+ repositories in 30 days. A plugin is arbitrary code inside your agent runtime — and today nothing surfaces its real capability surface before you install it.',
  'card1.t': 'Rewrite your system prompt',
  'card1.b': 'A plugin hooking system-prompt/assemble silently shapes every instruction your model sees.',
  'card2.t': 'Intercept APIs, read credentials',
  'card2.b': 'apiProxy and api/gate sit between you and the model; some plugins read GITHUB_TOKEN-class environment variables.',
  'card3.t': 'Patch the runtime itself',
  'card3.b': 'manifest.bundle.patch lets a plugin modify dsh core behavior — the deepest supply-chain surface there is.',
  'how.title': 'How it works',
  'how.s1t': 'Discover', 'how.s1b': 'Every repo under the dsh-plugin topic, rescanned daily.',
  'how.s2t': 'Scan', 'how.s2b': 'Static analysis of shipped code: injected services, hooks, runtime patches, exec/eval, outbound domains, credential-like env reads. Nothing is executed.',
  'how.s3t': 'Publish', 'how.s3b': 'A capability card per plugin with file:line evidence, a C0–C3 level, and an embeddable badge.',
  'levels.title': 'Capability levels',
  'levels.l0': 'No notable capability surface.',
  'levels.l1': 'Ordinary: registers tools/services, calls external domains.',
  'levels.l2': 'Powerful: prompt surface, API interception, subprocess, exec, credential reads or install scripts.',
  'levels.l3': 'Powerful capabilities combined with sensitive behavior.',
  'levels.note': 'Levels measure capability surface and transparency — not maliciousness. A C3 plugin can be perfectly legitimate; you just deserve to know before it touches your agent.',
  'badge.title': 'Nothing to hide? Show it.',
  'badge.b': 'Plugin authors: embed your capability badge. Users click through to the full evidence card.',
  'teams.title': 'For teams',
  'teams.b': 'Coming next: full-ecosystem coverage with daily diffs, a runtime-patch audit view, an install-gate plugin that blocks or asks on C2+ installs, multi-harness support (Abu-Cowork, Claude Code), and a private registry with org policy for enterprises.',
  'teams.cta': 'Follow the roadmap',
  'foot.oss': 'Apache-2.0 · static analysis only · false positives:',
  'foot.issue': 'open an issue',
  // registry page
  'reg.title': 'dsh plugin registry',
  'reg.search': 'Search name / description / service…',
  'reg.all': 'All', 'reg.pluginOnly': 'Plugins only',
  'reg.stats': (s) => `<b>${s.scanned}</b> of top ${s.total} repos scanned · <b>${s.c3}</b> × C3, <b>${s.c2}</b> × C2 · updated ${s.date} UTC`,
  'reg.empty': 'No matching plugins', 'reg.loading': 'Loading…', 'reg.unscanned': 'not scanned',
  'reg.flags': 'Flags & evidence', 'reg.services': 'Injected services', 'reg.hooks': 'Hooks',
  'reg.domains': 'Outbound domains', 'reg.env': 'Environment variables',
  'reg.tools': (n, f) => `${n} tool registration(s) · ${f} files scanned`,
  'reg.copy': 'Copy badge', 'reg.copied': 'Copied',
  'reg.f.runtime_patch': 'runtime patch', 'reg.f.prompt_surface': 'prompt surface', 'reg.f.api_intercept': 'API intercept',
  'reg.f.subprocess_service': 'subprocess', 'reg.f.tool_gate': 'tool gate', 'reg.f.exec': 'exec', 'reg.f.eval': 'eval',
  'reg.f.base64_decode': 'base64', 'reg.f.net_server': 'net server', 'reg.f.token_env': 'reads credentials',
  'reg.f.install_script': 'install script', 'reg.f.no_manifest': 'no manifest',
},
zh: {
  _name: '简体中文',
  'report.banner': '新发布 —— <b>dsh 插件生态还没有权限模型</b>:对装机量最大的一批插件做的能力普查。', 'report.read': '阅读报告 →',
  'nav.registry': '插件注册表', 'nav.report': '生态报告', 'nav.github': 'GitHub',
  'hero.title': '给 Agent 插件拍 X 光片',
  'hero.sub': '每个 DeepSeek Harness 插件一张能力卡片:它声明了什么,代码实际在做什么——每条结论都附 file:line 证据。',
  'hero.cta1': '浏览注册表', 'hero.cta2': '获取徽章',
  'hero.stat': (s) => `已扫描 ${s.scanned} 个仓库 · C3 × ${s.c3} · C2 × ${s.c2} · 更新于 ${s.date} UTC`,
  'why.title': '插件运行在你的 Agent 体内,你有权知道它能做什么。',
  'why.p': 'dsh-plugin 生态 30 天内从约 200 个仓库涨到 7,000+。插件就是跑在你 Agent 运行时里的任意代码——而今天,安装前没有任何东西告诉你它真实的能力面。',
  'card1.t': '改写你的系统提示词',
  'card1.b': '挂上 system-prompt/assemble 钩子的插件,可以悄悄塑造模型看到的每一条指令。',
  'card2.t': '拦截 API、读取凭证',
  'card2.b': 'apiProxy 和 api/gate 坐在你与模型之间;有的插件还会读取 GITHUB_TOKEN 这类环境变量。',
  'card3.t': '给运行时本体打补丁',
  'card3.b': 'manifest.bundle.patch 允许插件修改 dsh 核心行为——这是最深的供应链攻击面。',
  'how.title': '工作原理',
  'how.s1t': '发现', 'how.s1b': 'dsh-plugin 标签下的全部仓库,每日重扫。',
  'how.s2t': '扫描', 'how.s2b': '对发布代码做静态分析:注入的服务、钩子、runtime 补丁、exec/eval、外联域名、凭证类环境变量读取。全程不执行任何代码。',
  'how.s3t': '发布', 'how.s3b': '每个插件一张能力卡片:file:line 证据、C0–C3 等级、可嵌入的徽章。',
  'levels.title': '能力等级',
  'levels.l0': '无显著能力面。',
  'levels.l1': '常规:注册工具/服务、外联域名。',
  'levels.l2': '强能力:提示词面、API 拦截、子进程、exec、凭证读取或安装脚本。',
  'levels.l3': '强能力与敏感行为并存。',
  'levels.note': '等级衡量的是能力面大小与透明度,不是恶意判定。C3 插件完全可能是正当的——只是它碰你的 Agent 之前,你应当知情。',
  'badge.title': '没什么可藏的?亮出来。',
  'badge.b': '插件作者:在 README 嵌入能力徽章,用户点击即可查看完整证据卡片。',
  'teams.title': '面向团队',
  'teams.b': '路线图:全生态覆盖与每日差异推送、runtime 补丁审计视图、安装闸门插件(C2+ 安装时阻断或询问)、多 harness 支持(Abu-Cowork、Claude Code),以及面向企业的私有注册表与组织策略引擎。',
  'teams.cta': '关注路线图',
  'foot.oss': 'Apache-2.0 · 仅静态分析 · 误报请',
  'foot.issue': '提 issue',
  'reg.title': 'dsh 插件注册表',
  'reg.search': '搜索插件名 / 描述 / 服务名…',
  'reg.all': '全部', 'reg.pluginOnly': '只看插件',
  'reg.stats': (s) => `已扫描 top ${s.total} 中的 <b>${s.scanned}</b> 个 · <b>${s.c3}</b> 个 C3、<b>${s.c2}</b> 个 C2 · 更新于 ${s.date} UTC`,
  'reg.empty': '没有匹配的插件', 'reg.loading': '加载中…', 'reg.unscanned': '未扫描',
  'reg.flags': '标志与证据', 'reg.services': '注入服务', 'reg.hooks': '监听钩子',
  'reg.domains': '外联域名', 'reg.env': '环境变量',
  'reg.tools': (n, f) => `工具注册点 ${n} 处 · 扫描 ${f} 个代码文件`,
  'reg.copy': '复制徽章', 'reg.copied': '已复制',
  'reg.f.runtime_patch': '改runtime', 'reg.f.prompt_surface': '改提示词', 'reg.f.api_intercept': '拦API',
  'reg.f.subprocess_service': '子进程', 'reg.f.tool_gate': '工具闸门', 'reg.f.exec': 'exec', 'reg.f.eval': 'eval',
  'reg.f.base64_decode': 'base64', 'reg.f.net_server': '起服务', 'reg.f.token_env': '读凭证',
  'reg.f.install_script': '安装脚本', 'reg.f.no_manifest': '无manifest',
},
ja: {
  _name: '日本語',
  'report.banner': '新着 —— <b>dsh プラグインエコシステムに権限モデルは存在しない</b>:最も使われているプラグインの能力調査。', 'report.read': 'レポートを読む →',
  'nav.registry': 'レジストリ', 'nav.report': 'レポート', 'nav.github': 'GitHub',
  'hero.title': 'エージェントプラグインのX線検査',
  'hero.sub': 'DeepSeek Harness の各プラグインに「能力カード」を発行:宣言された権限と、コードが実際に行うこと——すべて file:line の証拠つき。',
  'hero.cta1': 'レジストリを見る', 'hero.cta2': 'バッジを取得',
  'hero.stat': (s) => `${s.scanned} リポジトリをスキャン · C3 × ${s.c3} · C2 × ${s.c2} · 更新 ${s.date} UTC`,
  'why.title': 'プラグインはあなたのエージェント内部で動く。その能力を知る権利がある。',
  'why.p': 'dsh-plugin エコシステムは 30 日間で約 200 から 7,000+ リポジトリに急増。プラグインはランタイム内で動く任意のコードだが、インストール前にその実際の能力面を示すものは今のところ存在しない。',
  'card1.t': 'システムプロンプトの書き換え',
  'card1.b': 'system-prompt/assemble にフックするプラグインは、モデルが見るすべての指示を静かに変えられる。',
  'card2.t': 'API 傍受・認証情報の読み取り',
  'card2.b': 'apiProxy や api/gate はあなたとモデルの間に位置する。GITHub_TOKEN 級の環境変数を読むプラグインもある。',
  'card3.t': 'ランタイム本体へのパッチ',
  'card3.b': 'manifest.bundle.patch により dsh コアの挙動を変更できる——最も深いサプライチェーン面だ。',
  'how.title': '仕組み',
  'how.s1t': '発見', 'how.s1b': 'dsh-plugin トピック配下の全リポジトリを毎日再スキャン。',
  'how.s2t': 'スキャン', 'how.s2b': '出荷コードの静的解析:注入サービス、フック、ランタイムパッチ、exec/eval、外部ドメイン、認証情報系の環境変数読み取り。コードは一切実行しない。',
  'how.s3t': '公開', 'how.s3b': 'プラグインごとに能力カードを発行:file:line 証拠、C0–C3 レベル、埋め込み可能なバッジ。',
  'levels.title': '能力レベル',
  'levels.l0': '顕著な能力面なし。',
  'levels.l1': '通常:ツール/サービス登録、外部ドメインへのアクセス。',
  'levels.l2': '強力:プロンプト面、API 傍受、サブプロセス、exec、認証情報読み取り、インストールスクリプトのいずれか。',
  'levels.l3': '強力な能力と機微な挙動の併存。',
  'levels.note': 'レベルは能力面の大きさと透明性の指標であり、悪意の判定ではない。C3 でも正当なプラグインは普通にある——ただ、知った上で使うべきだ。',
  'badge.title': '隠すものがない?見せよう。',
  'badge.b': 'プラグイン作者へ:能力バッジを README に埋め込めば、ユーザーはクリックひとつで証拠カードに到達できる。',
  'teams.title': 'チーム向け',
  'teams.b': '今後の予定:エコシステム全量カバレッジと日次差分、ランタイムパッチ監査ビュー、C2+ インストールをブロック/確認するゲートプラグイン、マルチハーネス対応(Abu-Cowork、Claude Code)、企業向けプライベートレジストリと組織ポリシー。',
  'teams.cta': 'ロードマップを見る',
  'foot.oss': 'Apache-2.0 · 静的解析のみ · 誤検知は',
  'foot.issue': 'issue へ',
  'reg.title': 'dsh プラグインレジストリ',
  'reg.search': '名前 / 説明 / サービス名で検索…',
  'reg.all': 'すべて', 'reg.pluginOnly': 'プラグインのみ',
  'reg.stats': (s) => `top ${s.total} 中 <b>${s.scanned}</b> をスキャン · C3 <b>${s.c3}</b>、C2 <b>${s.c2}</b> · 更新 ${s.date} UTC`,
  'reg.empty': '該当なし', 'reg.loading': '読み込み中…', 'reg.unscanned': '未スキャン',
  'reg.flags': 'フラグと証拠', 'reg.services': '注入サービス', 'reg.hooks': 'フック',
  'reg.domains': '外部ドメイン', 'reg.env': '環境変数',
  'reg.tools': (n, f) => `ツール登録 ${n} 箇所 · ${f} ファイルをスキャン`,
  'reg.copy': 'バッジをコピー', 'reg.copied': 'コピー済み',
  'reg.f.runtime_patch': 'ランタイムパッチ', 'reg.f.prompt_surface': 'プロンプト面', 'reg.f.api_intercept': 'API傍受',
  'reg.f.subprocess_service': 'サブプロセス', 'reg.f.tool_gate': 'ツールゲート', 'reg.f.exec': 'exec', 'reg.f.eval': 'eval',
  'reg.f.base64_decode': 'base64', 'reg.f.net_server': 'サーバ起動', 'reg.f.token_env': '認証情報読取',
  'reg.f.install_script': 'インストールスクリプト', 'reg.f.no_manifest': 'manifest無し',
},
};

window.xray = (function () {
  const langs = Object.keys(XRAY_I18N);
  const q = new URLSearchParams(location.search).get('lang');
  const saved = localStorage.getItem('xray-lang');
  const nav = (navigator.language || 'en').toLowerCase();
  let lang = q || saved || (nav.startsWith('zh') ? 'zh' : nav.startsWith('ja') ? 'ja' : 'en');
  if (!langs.includes(lang)) lang = 'en';

  const t = (key, ...args) => {
    const v = XRAY_I18N[lang][key] ?? XRAY_I18N.en[key] ?? key;
    return typeof v === 'function' ? v(...args) : v;
  };

  function applyStatic() {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang;
    document.querySelectorAll('[data-i18n]').forEach(el => { el.innerHTML = t(el.dataset.i18n); });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  }

  function mountSwitcher(el) {
    el.innerHTML = langs.map(l =>
      `<span class="chip lang ${l === lang ? 'on' : ''}" data-lang="${l}">${XRAY_I18N[l]._name}</span>`).join('');
    el.addEventListener('click', e => {
      const l = e.target.dataset.lang;
      if (!l) return;
      localStorage.setItem('xray-lang', l);
      const url = new URL(location);
      url.searchParams.delete('lang');
      history.replaceState(null, '', url);
      location.reload();
    });
  }

  return { lang, t, applyStatic, mountSwitcher };
})();
