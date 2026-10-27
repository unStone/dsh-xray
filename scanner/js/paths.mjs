import { posix } from 'node:path';

export function validatePath(path) {
  if (typeof path !== 'string' || !path || path.includes('\\') || path.includes('\0') ||
      posix.isAbsolute(path) || /^[A-Za-z]:/.test(path) ||
      path.split('/').some(p => !p || p === '.' || p === '..')) {
    throw new Error(`Invalid repository path: ${JSON.stringify(path)}`);
  }
}
