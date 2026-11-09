import json
import os
import pathlib
import selectors
import subprocess
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIMEOUT = 90
RECYCLE_AFTER = 300      # analyses per node process; caps RSS growth over a day
LOCAL = threading.local()


class AnalysisRuntimeError(RuntimeError):
    pass


class RepositoryAnalysisError(ValueError):
    pass


class Worker:
    """One persistent node analysis process, driven one request at a time.

    The one-shot design paid a node start plus the babel/pack-membership
    imports for every repository; a day's ~2000 analyses re-paid that ~2000
    times per pool thread. The process here answers line-delimited requests
    sequentially, so exactly one request is ever in flight on its pipes --
    which is why a Worker must not be shared across threads (worker() hands
    out one per thread).
    """

    def __init__(self):
        self.process = None
        self.buffer = bytearray()
        self.served = 0

    def _spawn(self):
        # Unbuffered stdout: responses are read straight off the fd under a
        # deadline; the write side is line-framed so a large request drains
        # fully before the worker answers, and the pipes cannot cross.
        try:
            self.process = subprocess.Popen(
                ['node', '--max-old-space-size=512', '--expose-gc', str(ROOT / 'scanner/js/worker.mjs')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0)
        except OSError as error:
            raise AnalysisRuntimeError(f'Scanner analysis failed: {error}') from error
        result = self.request({'version': 1, 'operation': 'ping'}, deadline=60, count=False)
        version = tuple(int(part) for part in result['node'].split('.'))
        if version < (24, 17, 0) or version[0] != 24:
            self.close()
            raise AnalysisRuntimeError(f'Scanner needs Node 24.17+ (24.x), got {result["node"]}; run fnm use')
        # Reset the recycle budget for the new process: after a recycle the
        # counter still holds the retired process's total, and without this
        # every request would pay a fresh spawn.
        self.served = 0

    def close(self):
        process, self.process, self.buffer = self.process, None, bytearray()
        if process is None:
            return
        try:
            process.stdin.close()
        except OSError:
            pass
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass

    def _readline(self, limit):
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            while True:
                index = self.buffer.find(b'\n')
                if index != -1:
                    line = bytes(self.buffer[:index])
                    del self.buffer[:index + 1]
                    return line
                remaining = limit - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired('node analysis response', TIMEOUT)
                if not selector.select(timeout=remaining):
                    raise subprocess.TimeoutExpired('node analysis response', TIMEOUT)
                chunk = os.read(self.process.stdout.fileno(), 1 << 16)
                if not chunk:
                    detail = self._stderr_detail()
                    raise EOFError(f'analysis worker exited{": " + detail if detail else ""}')
                self.buffer += chunk
        finally:
            selector.close()

    def _stderr_detail(self):
        # Only safe once the process is confirmed dead; reading a live
        # process's stderr would block on a pipe nobody is writing to.
        process = self.process
        if process is None or process.poll() is None:
            return ''
        try:
            return (process.stderr.read(2000) or b'').decode(errors='replace')[:500]
        except (OSError, ValueError):
            return ''

    def request(self, payload, deadline=None, count=True):
        if self.process is None:
            self._spawn()
        request_id = uuid.uuid4().hex
        # ensure_ascii (the default) keeps the wire pure ASCII: the worker
        # frames on 0x0A and JSON guarantees no raw newline inside a string,
        # so one request is always exactly one frame.
        message = json.dumps({**payload, 'requestId': request_id}).encode() + b'\n'
        limit = time.monotonic() + (deadline if deadline is not None else TIMEOUT)
        try:
            self.process.stdin.write(message)
            self.process.stdin.flush()
            line = self._readline(limit)
        except (OSError, ValueError, EOFError, subprocess.TimeoutExpired) as error:
            # A wedged or dead worker must not poison later requests: drop the
            # process and let the next call spawn a fresh one.
            self.close()
            raise AnalysisRuntimeError(f'Scanner analysis failed: {error}') from error
        if len(line) > 32 * 1024 * 1024:
            self.close()
            raise AnalysisRuntimeError('Node analysis response exceeded 32 MiB')
        try:
            envelope = json.loads(line)
        except (ValueError, UnicodeDecodeError) as error:
            self.close()
            raise AnalysisRuntimeError(f'Invalid Node analysis JSON: {error}') from error
        if envelope.get('requestId') != request_id:
            self.close()
            raise AnalysisRuntimeError(f'Node analysis response request ID does not match {request_id}')
        if 'error' in envelope:
            # Per-repository failure; the worker itself stays healthy.
            raise RepositoryAnalysisError(envelope['error'])
        result = envelope.get('result')
        if not isinstance(result, dict) or result.get('version') != 1:
            self.close()
            raise AnalysisRuntimeError('Invalid scanner analysis response: expected protocol version 1')
        # The spawn ping passes count=False: the budget counts analyses on one
        # process, and a recycle must never fire for the request that warmed it.
        if count:
            self.served += 1
            if self.served >= RECYCLE_AFTER:
                self.close()
        return result


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
