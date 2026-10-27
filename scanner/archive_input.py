import dataclasses
import pathlib
import subprocess
import tarfile

CODE_EXT = ('.ts', '.tsx', '.js', '.mjs', '.cjs', '.vue', '.svelte')
METADATA = {'package.json', '.npmignore', '.gitignore'}
MAX_FILES = 600
MAX_FILE_SIZE = 1024 * 1024
MAX_CODE_BYTES = 32 * 1024 * 1024
MAX_BYTES_READ = 400 * 1024 * 1024
MAX_ENTRIES = 100000


@dataclasses.dataclass
class ScanInput:
    files: dict
    entries: list
    notes: list


def read_archive(stream):
    files, entries, notes = {}, [], []
    read = code_bytes = code_count = omitted = 0
    archive_root = None
    with tarfile.open(fileobj=stream, mode='r|gz') as archive:
        for member in archive:
            raw = member.name.rstrip('/')
            parts = raw.split('/')
            if raw.startswith('/') or '\\' in raw or '\0' in raw or '..' in parts:
                raise ValueError(f'Unsafe archive path: {member.name!r}')
            if not parts or not parts[0]:
                raise ValueError('Archive has no repository root')
            if archive_root is None:
                archive_root = parts[0]
            if parts[0] != archive_root:
                raise ValueError(f'Archive has multiple roots: {archive_root!r}, {parts[0]!r}')
            if len(parts) == 1:
                continue
            path = pathlib.PurePosixPath(*parts[1:]).as_posix()
            if any(p in ('.git', 'node_modules') for p in parts[1:]):
                continue
            read += member.size
            if read > MAX_BYTES_READ or len(entries) >= MAX_ENTRIES:
                raise ValueError(f'Archive metadata incomplete: byte/path budget exceeded at {path}')
            if not member.isfile() and not member.isdir():
                if member.islnk():
                    raise ValueError(f'Unsupported hard link in archive: {path}')
                continue
            entries.append({'path': path, 'type': 'directory' if member.isdir() else 'file'})
            if not member.isfile():
                continue
            base = pathlib.PurePosixPath(path).name
            metadata = base in METADATA
            code = path.endswith(CODE_EXT)
            skill = base.upper() == 'SKILL.MD'
            if not (metadata or code or skill):
                continue
            if metadata and member.size > MAX_FILE_SIZE:
                raise ValueError(f'Archive metadata too large: {path} ({member.size} bytes)')
            if not metadata and (member.size > MAX_FILE_SIZE or
                                 (code and (code_count >= MAX_FILES or code_bytes + member.size > MAX_CODE_BYTES))):
                omitted += 1
                continue
            data = archive.extractfile(member).read()
            try:
                files[path] = data.decode('utf-8')
            except UnicodeDecodeError as error:
                if metadata:
                    raise ValueError(f'Archive metadata is not UTF-8: {path}') from error
                omitted += 1
                continue
            if code:
                code_count += 1
                code_bytes += member.size
    if omitted:
        notes.append(f'{omitted} source file(s) omitted by size/count/encoding limits; tool count is incomplete')
    if not any(path.endswith(CODE_EXT) or pathlib.PurePosixPath(path).name == 'package.json' or
               pathlib.PurePosixPath(path).name.upper() == 'SKILL.MD' for path in files):
        raise ValueError('no scannable code')
    return ScanInput(files, entries, notes)


def fetch_files(full_name, branch=None):
    refs = [f'refs/heads/{b}' for b in dict.fromkeys(filter(None, [branch, 'main', 'master']))]
    failures = []
    for ref in refs:
        process = subprocess.Popen(['curl', '-sSL', '--max-time', '120', '--fail',
                                    f'https://codeload.github.com/{full_name}/tar.gz/{ref}'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            try:
                result = read_archive(process.stdout)
            except (tarfile.TarError, EOFError, OSError) as error:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
                detail = process.stderr.read(1000).decode(errors='replace').strip()
                failures.append(f'{ref}: {error}; curl exited {process.returncode}: {detail}')
                continue
            process.stdout.close()
            code = process.wait(timeout=10)
            if code:
                failures.append(f'{ref}: curl exited {code}')
                continue
            return result
        finally:
            if not process.stdout.closed:
                process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            process.stderr.close()
    raise ValueError(f'download failed for {full_name}: {"; ".join(failures)}')
