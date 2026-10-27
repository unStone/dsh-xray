import { mkdir, mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { resolve, posix } from 'node:path';
import { fileURLToPath } from 'node:url';
import Arborist from '@npmcli/arborist';
import packlist from 'npm-packlist';
import { validatePath } from './paths.mjs';
export { validatePath } from './paths.mjs';

const scratch = fileURLToPath(new URL('../../tmp/analysis/', import.meta.url));

export async function withPackageTree(files, entries, callback) {
  await mkdir(scratch, { recursive: true });
  const directory = await mkdtemp(resolve(scratch, 'package-'));
  try {
    const directories = new Set(['.', '']);
    async function ensureDirectory(relative) {
      if (directories.has(relative)) return;
      await ensureDirectory(posix.dirname(relative));
      try {
        await mkdir(resolve(directory, relative));
      } catch (error) {
        if (error.code === 'EEXIST') throw new Error(`Archive path collision on this filesystem: ${relative}`);
        throw error;
      }
      directories.add(relative);
    }
    const paths = new Map(entries.map(entry => [entry.path, entry.type]));
    for (const path of Object.keys(files)) paths.set(path, 'file');
    for (const [path, type] of [...paths].sort(([a], [b]) => a.localeCompare(b))) {
      validatePath(path);
      const target = resolve(directory, path);
      if (type === 'directory') {
        await ensureDirectory(path);
      } else if (type === 'file') {
        await ensureDirectory(posix.dirname(path));
        // npm decides membership from paths, stats, manifests and ignore files.
        // No plugin source is evaluated or installed in this tree.
        const metadata = ['package.json', '.npmignore', '.gitignore'].includes(posix.basename(path));
        try {
          await writeFile(target, metadata ? files[path] ?? '' : '', { flag: 'wx' });
        } catch (error) {
          if (error.code === 'EEXIST') throw new Error(`Archive path collision on this filesystem: ${path}`);
          throw error;
        }
      } else {
        throw new Error(`Unsupported archive entry type for ${path}: ${type}`);
      }
    }
    return await callback(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

export async function packageMembers(directory, root = '') {
  const path = resolve(directory, root);
  const pkg = JSON.parse(await readFile(resolve(path, 'package.json'), 'utf8'));
  const workspaces = Array.isArray(pkg.workspaces) ? pkg.workspaces : pkg.workspaces?.packages ?? [];
  for (const workspace of workspaces) {
    if (typeof workspace !== 'string' || posix.isAbsolute(workspace) ||
        workspace.includes('\\') || workspace.split('/').includes('..')) {
      throw new Error(`${root}/package.json: workspace must stay inside the package: ${workspace}`);
    }
  }
  const tree = await new Arborist({ path, workspacesEnabled: false }).loadActual();
  return new Set(await packlist(tree));
}

function declaredEntrypoints(pkg) {
  const values = [];
  const collect = value => {
    if (typeof value === 'string') values.push(value.replace(/^(\.\/)+/, '').replace(/\/$/, ''));
    else if (Array.isArray(value)) value.forEach(collect);
    else if (value && typeof value === 'object') Object.values(value).forEach(collect);
  };
  for (const key of ['main', 'module', 'types', 'typings', 'browser', 'bin', 'exports', 'unpkg', 'directories']) {
    collect(pkg[key]);
  }
  return values.filter(Boolean);
}

export async function unshippedTooling(files, entries, candidates) {
  if (!candidates.length) return [];
  return withPackageTree(files, entries, async directory => {
    const excluded = [];
    for (const { root, paths } of candidates) {
      const manifestPath = root ? `${root}/package.json` : 'package.json';
      const pkg = JSON.parse(files[manifestPath]);
      if (!pkg || typeof pkg !== 'object' || Array.isArray(pkg)) {
        throw new Error(`${manifestPath}: expected a package object`);
      }
      if (!Array.isArray(pkg.files) || !pkg.files.length) continue;
      if (!pkg.files.every(p => typeof p === 'string')) {
        throw new Error(`${manifestPath}: files must contain strings`);
      }
      if (['prepare', 'preinstall', 'install', 'postinstall'].some(k => k in (pkg.scripts ?? {}))) continue;
      const packed = await packageMembers(directory, root);
      const forced = declaredEntrypoints(pkg);
      for (const path of paths) {
        const relative = root ? path.slice(root.length + 1) : path;
        // Preserve the existing conservative treatment of misconfigured entrypoints.
        if (!packed.has(relative) && !forced.some(p => relative === p || relative.startsWith(`${p}/`))) {
          excluded.push(path);
        }
      }
    }
    return excluded.sort();
  });
}
