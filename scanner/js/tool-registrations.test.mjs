import { test } from 'node:test';
import assert from 'node:assert/strict';
import { toolRegistrations } from './tool-registrations.mjs';

function result(source, extension = 'js', extra = {}) {
  return toolRegistrations({ [`index.${extension}`]: source, ...extra });
}

test('context injection, aliases, destructuring, get, bound register and helper arguments', () => {
  const r = result(`
    function mount(host) { const tools = host?.tools; tools.register({name: 'a'}); }
    export function apply(ctx) {
      mount(ctx);
      ctx.inject(['tools'], scoped => {
        const {tools} = scoped;
        scoped.effect(() => tools.register({name: 'b'}));
      });
      const api = ctx.get('tools');
      const register = api.register.bind(api);
      register({name: 'c'});
      ctx['tools']['register']({name: 'd'});
    }
  `);
  assert.equal(r.registrations.length, 4);
});

test('strings, unrelated objects, shadowing and reassignment do not count', () => {
  const r = result(`
    const text = "ctx.tools.register({})";
    // ctx.tools.register({})
    const otherTools = other.tools; otherTools.register({});
    export function apply(ctx) {
      let tools = ctx.tools;
      tools.register({});
      tools = other.tools;
      tools.register({});
      { const ctx = other; ctx.tools.register({}); }
    }
  `);
  assert.equal(r.registrations.length, 1);
});

test('local module helper receives the real context', () => {
  const r = result(`import {mount} from './mount.js'; export function apply(ctx) { mount(ctx); }`, 'ts', {
    'mount.ts': 'export function mount(host) { const registry = host.tools; registry.register({}); }',
  });
  assert.equal(r.registrations.length, 1);
  assert.equal(r.registrations[0].path, 'mount.ts');
});

test('TSX, Vue, Svelte and syntax diagnostics retain original lines', () => {
  assert.equal(result('export function apply(ctx: Context) { ctx.tools.register({view: <p/>}); }', 'tsx').registrations.length, 1);
  const source = `<p>demo</p>\n<script lang="ts">\nexport function apply(ctx: Context) { ctx.tools.register({}); }\n</script>`;
  for (const extension of ['vue', 'svelte']) {
    const r = result(source, extension);
    assert.equal(r.registrations.length, 1, extension);
    assert.equal(r.registrations[0].line, 3, extension);
  }
  assert.equal(result('export function apply( {').diagnostics.length, 1);
});

test('dynamic service lookups are explicitly incomplete', () => {
  const r = result('export function apply(ctx) { ctx.get(service).register({}); }');
  assert.equal(r.registrations.length, 0);
  assert.equal(r.diagnostics.length, 1);
  const alias = result('export function apply(ctx) { const api = ctx.get(service); api.register({}); }');
  assert.equal(alias.registrations.length, 0);
  assert.equal(alias.diagnostics.length, 1);
});

test('unrelated apply properties and mixed helper arguments are not trusted contexts', () => {
  assert.equal(result('object.apply = value => value.tools.register({});').registrations.length, 0);
  const r = result(`function mount(host) { const api = host.tools; api.register({}); }
    export function apply(ctx) { mount(other); mount(ctx); }`);
  assert.equal(r.registrations.length, 0);
  assert.ok(r.diagnostics.length);
});

test('JSX in JavaScript and typed JSX in Vue are parsed', () => {
  assert.equal(result('export function apply(ctx) { ctx.tools.register({view: <p/>}); }').registrations.length, 1);
  assert.equal(result('<script lang="tsx">export function apply(ctx: Context) { ctx.tools.register({view: <p/>}); }</script>', 'vue').registrations.length, 1);
});
