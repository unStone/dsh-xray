import json
import pathlib
import subprocess
import threading
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIMEOUT = 90
LOCAL = threading.local()


class AnalysisRuntimeError(RuntimeError):
    pass


class RepositoryAnalysisError(ValueError):
    pass


class Worker:
    def __init__(self):
        result = self.request({'version': 1, 'operation': 'ping'})
        version = tuple(int(part) for part in result['node'].split('.'))
        if version < (24, 17, 0) or version[0] != 24:
            raise AnalysisRuntimeError(f'Scanner needs Node 24.17+ (24.x), got {result["node"]}; run fnm use')

    def request(self, payload):
        request_id = uuid.uuid4().hex
        message = {**payload, 'requestId': request_id}
        try:
            # communicate() owns both pipes for this request; no shared reader
            # can attach another repository's response to the current card.
            completed = subprocess.run(
                ['node', '--max-old-space-size=512', '--expose-gc', str(ROOT / 'scanner/js/worker.mjs')],
                input=json.dumps(message, ensure_ascii=False).encode() + b'\n',
                capture_output=True, timeout=TIMEOUT, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AnalysisRuntimeError(f'Scanner analysis failed: {error}') from error
        if completed.returncode:
            detail = completed.stderr.decode(errors='replace')[:2000]
            raise AnalysisRuntimeError(f'Node analysis exited {completed.returncode}: {detail}')
        if len(completed.stdout) > 32 * 1024 * 1024:
            raise AnalysisRuntimeError('Node analysis response exceeded 32 MiB')
        try:
            envelope = json.loads(completed.stdout)
        except (ValueError, UnicodeDecodeError) as error:
            raise AnalysisRuntimeError(f'Invalid Node analysis JSON: {error}') from error
        if envelope.get('requestId') != request_id:
            raise AnalysisRuntimeError(f'Node analysis response request ID does not match {request_id}')
        if 'error' in envelope:
            raise RepositoryAnalysisError(envelope['error'])
        result = envelope.get('result')
        if not isinstance(result, dict) or result.get('version') != 1:
            raise AnalysisRuntimeError('Invalid scanner analysis response: expected protocol version 1')
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
