import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { createRequire } from 'node:module';

export const traverse = traverseModule.default;
const require = createRequire(import.meta.url);

function javascript(source, filename, startLine = 1, lang = '') {
  return parse(source, {
    sourceFilename: filename,
    sourceType: 'unambiguous',
    startLine,
    allowAwaitOutsideFunction: true,
    allowReturnOutsideFunction: true,
    plugins: [
      'decorators-legacy', 'importAttributes',
      ...(/\.(ts|tsx)$/.test(filename) || ['ts', 'tsx'].includes(lang) ? ['typescript'] : []),
      ...(!filename.endsWith('.ts') && lang !== 'ts' ? ['jsx'] : []),
    ],
  });
}

export function parseSource(source, filename) {
  if (filename.endsWith('.vue')) {
    const { descriptor, errors } = require('@vue/compiler-sfc').parse(source, { filename });
    if (errors.length) throw new Error(errors.map(e => e.message ?? e).join('; '));
    return [descriptor.script, descriptor.scriptSetup].filter(Boolean).map(block =>
      javascript(block.content, filename, block.loc.start.line, block.lang));
  }
  if (filename.endsWith('.svelte')) {
    const component = require('svelte/compiler').parse(source, { modern: true });
    return [component.instance, component.module].filter(Boolean).map(block => {
      const start = block.content.start;
      const end = block.content.end;
      const lang = block.attributes?.find(a => a.name === 'lang')?.value?.[0]?.data ?? '';
      return javascript(source.slice(start, end), filename,
        source.slice(0, start).split('\n').length, lang);
    });
  }
  return [javascript(source, filename)];
}
