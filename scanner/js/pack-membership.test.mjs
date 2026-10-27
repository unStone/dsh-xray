import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { withPackageTree, packageMembers, unshippedTooling } from './pack-membership.mjs';

const cases = [
  ['lib', 'scripts'], ['lib', 'scripts', '!scripts/private'],
  ['lib', '!scripts/private', 'scripts'],
  ['lib', 'scripts', '!scripts/private', 'scripts/private/a.mjs'],
  ['!scripts/private'], ['lib', '!../outside'], ['lib', '!scripts'],
  ['lib', 'scripts/private/a.mjs', '!scripts/**'],
  ['lib', '!scripts', 'scripts/**/*.mjs'], ['+(lib|scripts)'],
  ['scripts/**/*.{mjs,js}'], ['scripts/gen-[0-9].mjs'],
];

test('membership agrees with real npm, including negation, extglob and forced files', async () => {
  for (const allow of cases) {
    for (const metadata of [{}, { main: 'scripts/private/a.mjs' }, { bin: { demo: 'scripts/check.mjs' } }]) {
      const files = {
        'package.json': JSON.stringify({ name: 'fixture', version: '1.0.0', files: allow, ...metadata }),
        'lib/index.js': '', 'scripts/check.mjs': '', 'scripts/private/a.mjs': '',
        'scripts/gen-1.mjs': '', 'README.md': '',
      };
      await withPackageTree(files, [], async directory => {
        const actual = [...await packageMembers(directory)].sort();
        const report = JSON.parse(execFileSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], {
          cwd: directory, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
        }));
        assert.deepEqual(actual, report[0].files.map(f => f.path).sort(), JSON.stringify({ allow, metadata }));
      });
    }
  }
});

test('nested ignore files, nearest package, and lifecycle protection', async () => {
  const files = {
    'package.json': JSON.stringify({ name: 'root', version: '1.0.0', files: ['scripts'] }),
    'scripts/.npmignore': 'private/\n', 'scripts/private/a.mjs': '', 'scripts/check.mjs': '',
    'packages/p/package.json': JSON.stringify({ name: 'p', version: '1.0.0', files: ['lib', '!docs/private'] }),
    'packages/p/scripts/check.mjs': '',
  };
  assert.deepEqual(await unshippedTooling(files, [], [
    { root: '', paths: ['scripts/private/a.mjs', 'scripts/check.mjs'] },
    { root: 'packages/p', paths: ['packages/p/scripts/check.mjs'] },
  ]), ['packages/p/scripts/check.mjs', 'scripts/private/a.mjs']);
  files['package.json'] = JSON.stringify({ name: 'root', files: ['lib'], scripts: { prepare: 'node scripts/check.mjs' } });
  assert.deepEqual(await unshippedTooling(files, [], [{ root: '', paths: ['scripts/check.mjs'] }]), []);
});

test('case-distinct archive directories are never silently merged by the host filesystem', async () => {
  await withPackageTree({ 'package.json': '{"name":"probe"}' }, [], async directory => {
    await mkdir(join(directory, 'CaseProbe'));
    let insensitive = false;
    try {
      await mkdir(join(directory, 'caseprobe'));
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      insensitive = true;
    }
    const files = { 'package.json': '{"name":"fixture","files":["tools"]}',
      'Tools/a.mjs': '', 'tools/b.mjs': '' };
    const operation = () => withPackageTree(files, [], async root => [...await packageMembers(root)]);
    if (insensitive) await assert.rejects(operation, /collision/i);
    else assert.ok((await operation()).includes('tools/b.mjs'));
  });
});
