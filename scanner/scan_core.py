"""dsh-xray core: static capability analysis for dsh plugins.

Input: a file map {relative_path: text} for one repository.
Output: a capability card (dict) — what the plugin declares vs what its code does.

This is transparency tooling, not a malice detector. Every flag carries evidence
(file:line) so authors and users can verify or dispute it.
"""
import json
import re

CODE_EXT = ('.ts', '.tsx', '.js', '.mjs', '.cjs', '.vue', '.svelte')

DEV_DIR_RE = re.compile(
    r"(^|/)(tests?|__tests__|e2e|spec|specs|fixtures?|mocks?|examples?|docs?|website|\.github)(/|$)")
DEV_FILE_RE = re.compile(r"\.(test|spec|stories)\.[a-z]+$|\.d\.ts$")
# Build output and vendored trees carry inlined dependencies. Flagging a plugin
# for eval() that its bundler pulled in from schemastery — an official dsh
# package — attributes someone else's code to its author.
VENDOR_DIR_RE = re.compile(r"(^|/)(lib|dist|build|vendor|bundle|out|_output)(/|$)")

LINE_COMMENT_RE = re.compile(r"(?<![:\w])//[^\n]*")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def strip_comments(text):
    """Blank out comments, preserving newlines so reported line numbers hold.

    A mention of child_process in a doc comment is not a call to it.
    """
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return LINE_COMMENT_RE.sub(blank, BLOCK_COMMENT_RE.sub(blank, text))

URL_RE = re.compile(r"https?://([a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})")
INJECT_RE = re.compile(r"(?:export\s+const\s+inject|['\"]?inject['\"]?)\s*[:=]\s*(\[[^\]]{0,400}\])", re.S)
HOOK_RE = re.compile(r"ctx\.on\s*\(\s*['\"]([^'\"]+)['\"]")
TOOL_RE = re.compile(r"ctx\.tools\.register|defineTool\s*\(|registerTool\b")
ENV_RE = re.compile(r"process\.env\.([A-Za-z_][A-Za-z_0-9]*)")
APPLY_RE = re.compile(r"export\s+(?:function|const)\s+apply\b|\bapply\s*\(\s*ctx\b")

# Raw-field schema version. finalize() stamps it on every card; the pipeline
# refuses to reuse a cached card collected under a different version, because
# fields added or split since then cannot be reconstructed without a rescan.
COLLECT_VERSION = 2

# A diagnostic may carry the literal `node:internal/child_process` in a string
# or regex without ever importing the module. Execution needs an import-shaped
# reference or a call; a bare mention is reported separately as `exec_ref`.
CP_IMPORT = (
    r"(?:\bfrom\s*['\"](?:node:)?child_process['\"]"
    r"|\b(?:import|require)\s*\(\s*['\"](?:node:)?child_process['\"]\s*\)"
    r"|\bimport\s*['\"](?:node:)?child_process['\"])"
)
CP_REF_RE = re.compile(r"child_process")

BEHAVIOR_RES = {
    'exec': re.compile(CP_IMPORT + r"|execSync|spawnSync|execFileSync|\bexeca\b|\bspawn\s*\("),
    'eval': re.compile(r"\beval\s*\(|new\s+Function\s*\("),
    'base64_decode': re.compile(r"\batob\s*\(|Buffer\.from\s*\([^)]{1,120}['\"]base64['\"]"),
    'net_server': re.compile(r"createServer\s*\(|\.listen\s*\(\s*\d"),
    'fs_write': re.compile(r"writeFileSync|writeFile\s*\(|appendFile|createWriteStream|\brmSync\b|\bunlinkSync\b"),
    'dyn_import': re.compile(r"await\s+import\s*\(\s*[^'\")]"),
}

TOKEN_ENV_RE = re.compile(r"KEY|TOKEN|SECRET|PASS|CRED|AUTH|COOKIE", re.I)
POWERFUL_SERVICES = {'subprocess', 'apiProxy', 'systemPrompt', 'sandbox', 'webServer', 'approval'}
POWERFUL_HOOKS = {'system-prompt/assemble', 'api/gate', 'tools/pre-execute', 'llm/request'}
BENIGN_DOMAINS = {
    'www.w3.org', 'schemas.xmlsoap.org', 'json-schema.org', 'registry.npmjs.org',
    'github.com', 'raw.githubusercontent.com', 'img.shields.io', 'shields.io',
    'example.com', 'example.org', 'localhost', 'nodejs.org', 'developer.mozilla.org',
}
BENIGN_ENV = {'NODE_ENV', 'HOME', 'PATH', 'TZ', 'USER', 'SHELL', 'TERM', 'CI', 'PWD', 'TMPDIR', 'LANG'}


def zone_of(path):
    if DEV_DIR_RE.search(path) or DEV_FILE_RE.search(path):
        return 'dev'
    if VENDOR_DIR_RE.search(path):
        return 'vendor'
    return 'src'


def _line(text, pos):
    return text.count('\n', 0, pos) + 1


def scan_files(files):
    """files: {path: text}. Returns the capability card."""
    card = {
        'manifest': None, 'pkg_name': None, 'deps': [], 'install_scripts': {},
        'injects': set(), 'hooks': set(), 'tool_regs': 0,
        'domains': {}, 'env': {},
        'behaviors': {k: {'src': 0, 'dev': 0, 'vendor': 0, 'evidence': [],
                          'vendor_evidence': []} for k in BEHAVIOR_RES},
        'has_apply': False, 'files_scanned': 0, 'has_skill_md': False,
        'has_bundle': False, 'has_client': False,
        'cp_refs': 0, 'cp_ref_evidence': [],
        # Capability surface found in test/example/docs trees. Tracked apart
        # from the runtime surface: it never classifies the repo or raises the
        # level, but hiding real code in a directory named examples/ must stay
        # visible on the card, so it is reported instead of skipped.
        'dev_injects': set(), 'dev_hooks': set(), 'dev_tool_regs': 0,
        'dev_has_apply': False, 'dev_manifests': [],
    }

    # Shallowest paths first: in a monorepo the plugin's own root package.json
    # wins, so the reported manifest is deterministic rather than tar-order luck.
    for path, text in sorted(files.items(), key=lambda kv: (kv[0].count('/'), kv[0])):
        base = path.rsplit('/', 1)[-1]
        if base == 'package.json':
            try:
                data = json.loads(text)
            except Exception:
                continue
            if zone_of(path) == 'dev':
                # A fixture or example manifest is evidence about development,
                # not the installable surface: it must not classify the repo,
                # feed deps, or flag install scripts. Recorded so the card can
                # still say "an installable-looking manifest sits in test/".
                m = next((data.get(k) for k in ('manifest', 'dsh')
                          if isinstance(data.get(k), dict)), None)
                if m is not None and len(card['dev_manifests']) < 5:
                    card['dev_manifests'].append(
                        {'path': path, 'bundle': isinstance(m.get('bundle'), dict)})
                continue
            if card['pkg_name'] is None:
                card['pkg_name'] = data.get('name')
            card['deps'].extend((data.get('dependencies') or {}).keys())
            card['deps'].extend((data.get('peerDependencies') or {}).keys())
            for k, v in (data.get('scripts') or {}).items():
                if k in ('preinstall', 'postinstall', 'install', 'prepare'):
                    card['install_scripts'][k] = str(v)[:200]
            for key in ('manifest', 'dsh'):
                m = data.get(key)
                if not isinstance(m, dict):
                    continue
                if card['manifest'] is None:
                    card['manifest'] = m
                if isinstance(m.get('bundle'), dict):
                    card['has_bundle'] = True
                if isinstance(m.get('client'), dict):
                    card['has_client'] = True
            continue
        if base.upper() == 'SKILL.MD':
            card['has_skill_md'] = True
        if not path.endswith(CODE_EXT):
            continue

        card['files_scanned'] += 1
        zone = zone_of(path)
        text = strip_comments(text)
        if zone == 'dev':
            if APPLY_RE.search(text):
                card['dev_has_apply'] = True
            for m in INJECT_RE.finditer(text):
                for name in re.findall(r"['\"]([a-zA-Z][a-zA-Z0-9_-]{1,40})['\"]", m.group(1)):
                    card['dev_injects'].add(name)
            for m in HOOK_RE.finditer(text):
                card['dev_hooks'].add(m.group(1))
            card['dev_tool_regs'] += len(TOOL_RE.findall(text))
        else:
            if APPLY_RE.search(text):
                card['has_apply'] = True
            for m in INJECT_RE.finditer(text):
                for name in re.findall(r"['\"]([a-zA-Z][a-zA-Z0-9_-]{1,40})['\"]", m.group(1)):
                    card['injects'].add(name)
            for m in HOOK_RE.finditer(text):
                card['hooks'].add(m.group(1))
            card['tool_regs'] += len(TOOL_RE.findall(text))
        if zone == 'src' and CP_REF_RE.search(text):
            # Mentions of child_process that the exec pattern did not claim:
            # string constants, regexes over stack traces — or an indirect
            # `require(name)` where only the string sits in the file.
            spans = [m.span() for m in BEHAVIOR_RES['exec'].finditer(text)]
            for m in CP_REF_RE.finditer(text):
                if not any(s <= m.start() < e for s, e in spans):
                    card['cp_refs'] += 1
                    if len(card['cp_ref_evidence']) < 3:
                        card['cp_ref_evidence'].append(f"{path}:{_line(text, m.start())}")
        if zone != 'dev':
            for m in URL_RE.finditer(text):
                d = m.group(1).lower()
                if d not in BENIGN_DOMAINS and not d.endswith(('.example', '.test', '.local', '.internal', '.invalid')):
                    card['domains'][d] = card['domains'].get(d, 0) + 1
            for m in ENV_RE.finditer(text):
                v = m.group(1)
                if v not in BENIGN_ENV:
                    card['env'][v] = card['env'].get(v, 0) + 1
        for key, pat in BEHAVIOR_RES.items():
            b = card['behaviors'][key]
            for m in pat.finditer(text):
                b[zone] += 1
                if zone == 'src' and len(b['evidence']) < 5:
                    b['evidence'].append(f"{path}:{_line(text, m.start())}")
                elif zone == 'vendor' and len(b['vendor_evidence']) < 3:
                    b['vendor_evidence'].append(f"{path}:{_line(text, m.start())}")

    return finalize(card)


def classify(card):
    """How a repository actually connects to dsh.

    Carrying the `dsh-plugin` topic says nothing on its own — anyone can add a
    topic. What makes a repository installable via `dsh plugin add` is a
    `dsh.bundle` manifest; declaring only `dsh.client` does not.
    """
    if card.get('has_bundle'):
        return 'plugin'
    if card.get('has_client'):
        return 'client-only'
    if card.get('has_skill_md'):
        return 'skill'
    if any(str(d).startswith('@deepseek-ai/') or d == 'cordis' for d in (card.get('deps') or [])):
        return 'library'
    if card.get('has_apply') and (card.get('hooks') or card.get('tool_regs')):
        return 'code-only'
    return 'unrelated'


def finalize(card):
    """Derive type, flags and level from the collected raw fields.

    Idempotent over a JSON round-trip: the pipeline re-runs it on cached cards
    so a rule change reaches unchanged repositories on the next scan instead of
    being trapped inside the cache.
    """
    card['injects'] = sorted(card['injects'])
    card['hooks'] = sorted(card['hooks'])
    card['dev_injects'] = sorted(card.get('dev_injects', []))
    card['dev_hooks'] = sorted(card.get('dev_hooks', []))
    card['type'] = classify(card)

    flags = []

    def flag(fid, evidence):
        flags.append({'id': fid, 'evidence': evidence})

    manifest = card['manifest'] or {}
    if isinstance(manifest.get('bundle'), dict) and manifest['bundle'].get('patch'):
        flag('runtime_patch', str(manifest['bundle']['patch']))
    hard_install = {k: v for k, v in card['install_scripts'].items() if k != 'prepare'}
    if hard_install:
        flag('install_script', '; '.join(f"{k}: {v}" for k, v in hard_install.items())[:200])
    pw_srv = sorted(set(card['injects']) & POWERFUL_SERVICES)
    pw_hook = sorted(set(card['hooks']) & POWERFUL_HOOKS)
    if 'systemPrompt' in pw_srv or 'system-prompt/assemble' in pw_hook:
        flag('prompt_surface', ', '.join(pw_srv + pw_hook))
    if 'apiProxy' in pw_srv or 'api/gate' in pw_hook or 'llm/request' in pw_hook:
        flag('api_intercept', ', '.join(pw_srv + pw_hook))
    if 'subprocess' in pw_srv:
        flag('subprocess_service', 'inject: subprocess')
    if 'tools/pre-execute' in pw_hook:
        flag('tool_gate', 'hook: tools/pre-execute')
    bundled_only = []
    for key in ('exec', 'eval', 'base64_decode', 'net_server'):
        b = card['behaviors'][key]
        if b['src']:
            flag(key, f"×{b['src']} in authored code, e.g. {', '.join(b['evidence'][:2])}")
        elif b['vendor']:
            # Present, but in bundled output — reported without counting toward
            # the level, since it is not the author's code.
            bundled_only.append(key)
            flag(f'{key}_bundled',
                 f"×{b['vendor']} in build output only, e.g. {', '.join(b['vendor_evidence'][:2])}")
    if card.get('cp_refs') and not card['behaviors']['exec']['src']:
        # Transparency for what the tightened exec pattern no longer counts:
        # the string is in the file, the import is not. Not in the risky set.
        flag('exec_ref',
             f"mentions child_process ×{card['cp_refs']} without importing it, "
             f"e.g. {', '.join(card['cp_ref_evidence'][:2])}")
    token_env = sorted(v for v in card['env'] if TOKEN_ENV_RE.search(v))
    if token_env:
        flag('token_env', ', '.join(token_env[:6]))
    if card['type'] in ('code-only', 'library') and (card['injects'] or card['tool_regs']):
        flag('no_manifest', f"uses {len(card['injects'])} services, {card['tool_regs']} tool regs, no manifest")
    # Dev-zone findings never count toward the level, but they stay on the
    # card: a powerful service wired up only under examples/ is exactly the
    # kind of thing a reader should get to see and dispute.
    src_pw = set(pw_srv) | set(pw_hook)
    dev_pw = sorted(((set(card.get('dev_injects', [])) & POWERFUL_SERVICES)
                     | (set(card.get('dev_hooks', [])) & POWERFUL_HOOKS)) - src_pw)
    if dev_pw:
        flag('dev_surface', 'in test/example code only: ' + ', '.join(dev_pw))
    fixture_bundles = [d['path'] for d in card.get('dev_manifests', []) if d.get('bundle')]
    if fixture_bundles and card['type'] != 'plugin':
        flag('dev_manifest',
             'installable-looking manifest in fixtures only: ' + ', '.join(fixture_bundles[:3]))

    ids = {f['id'] for f in flags}
    powerful = ids & {'runtime_patch', 'prompt_surface', 'api_intercept', 'subprocess_service'}
    risky = ids & {'exec', 'eval', 'base64_decode', 'token_env', 'install_script', 'net_server'}
    if powerful and risky:
        level = 3
    elif powerful or risky:
        level = 2
    elif card['tool_regs'] or card['injects'] or card['domains']:
        level = 1
    else:
        level = 0

    card['flags'] = flags
    card['level'] = level
    card['collect'] = COLLECT_VERSION
    return card
