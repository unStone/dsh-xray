import atexit
import contextlib
import json
import os
import pathlib
import selectors
import subprocess
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIMEOUT = 90
LOCAL = threading.local()
WORKERS = set()
LOCK = threading.Lock()


class AnalysisRuntimeError(RuntimeError):
    pass


class RepositoryAnalysisError(ValueError):
    pass


class Worker:
    def __init__(self):
        scratch = ROOT / 'tmp' / 'analysis'
        scratch.mkdir(parents=True, exist_ok=True)
        self.errors = tempfile.TemporaryFile(dir=scratch)
        try:
            self.process = subprocess.Popen(
                ['node', '--max-old-space-size=512', '--expose-gc', str(ROOT / 'scanner/js/worker.mjs')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors)
        except OSError as error:
            self.errors.close()
            raise AnalysisRuntimeError('Cannot start scanner Node worker; run fnm use and npm ci --prefix scanner') from error
        self.closed = False
        with LOCK:
            WORKERS.add(self)
        result = self.request({'version': 1, 'operation': 'ping'})
        version = tuple(int(part) for part in result['node'].split('.'))
        if version < (24, 17, 0) or version[0] != 24:
            self.close()
            raise AnalysisRuntimeError(f'Scanner needs Node 24.17+ (24.x), got {result["node"]}; run fnm use')

    def request(self, payload):
        if self.closed:
            raise AnalysisRuntimeError('Scanner Node worker was closed after a previous failure')
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False).encode() + b'\n')
            self.process.stdin.flush()
            response = bytearray()
            deadline = time.monotonic() + TIMEOUT
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while not response.endswith(b'\n'):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise TimeoutError(f'Node analysis did not finish within {TIMEOUT}s')
                    chunk = os.read(self.process.stdout.fileno(), 65536)
                    if not chunk:
                        self.errors.seek(0)
                        detail = self.errors.read(2000).decode(errors='replace')
                        raise RuntimeError(f'Node analysis exited unexpectedly: {detail}')
                    response.extend(chunk)
                    if len(response) > 32 * 1024 * 1024:
                        raise RuntimeError('Node analysis response exceeded 32 MiB')
            envelope = json.loads(response)
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            self.close()
            raise AnalysisRuntimeError(f'Scanner analysis failed: {error}') from error
        if 'error' in envelope:
            raise RepositoryAnalysisError(envelope['error'])
        result = envelope.get('result')
        if not isinstance(result, dict) or result.get('version') != 1:
            self.close()
            raise AnalysisRuntimeError('Invalid scanner analysis response: expected protocol version 1')
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        with contextlib.suppress(OSError):
            self.process.stdin.close()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()
        self.errors.close()
        with LOCK:
            WORKERS.discard(self)


def worker():
    if not hasattr(LOCAL, 'worker'):
        LOCAL.worker = Worker()
    return LOCAL.worker


def analyze(files, candidates, entries=None, non_runtime=None):
    result = worker().request({'version': 1, 'files': files, 'entries': entries or [],
                               'candidates': candidates, 'nonRuntimePaths': non_runtime or []})
    if any(not isinstance(result.get(key), list) for key in ('tooling', 'registrations', 'diagnostics')):
        raise AnalysisRuntimeError('Invalid analysis response: expected tooling, registrations and diagnostics arrays')
    for item in result['registrations'] + result['diagnostics']:
        if (not isinstance(item, dict) or item.get('path') not in files or
                not isinstance(item.get('line'), int) or item['line'] < 1 or
                not isinstance(item.get('reason'), str)):
            raise AnalysisRuntimeError(f'Invalid analysis response: malformed file:line evidence: {item!r}')
    if any(path not in files for path in result['tooling']):
        raise AnalysisRuntimeError('Invalid analysis response: unknown tooling path')
    return result


def package_members(files, root=''):
    return set(worker().request({'version': 1, 'operation': 'membership',
                                 'files': files, 'root': root})['members'])


@atexit.register
def close_workers():
    for instance in list(WORKERS):
        instance.close()
