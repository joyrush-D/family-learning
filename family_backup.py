"""Private, verified SQLite + family-file backups; Python standard library only.

python3 family_backup.py --root /path/to/app create private/backups/family.zip
python3 family_backup.py restore /path/to/family.zip /path/to/empty-restore
Restore produces data only: copy the application separately before running it.
Restored pending print jobs and active study timers require review; the Agent is disabled.
"""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile

DOCUMENTS = ('家庭运行规则.md', '消息来源.md', '跟踪台账.md', '学习与成长.md')
DATABASE = 'private/family.sqlite3'
DATA_FILES = ('private/采集状态.json', 'private/陪伴建议.json', 'private/陪伴提醒状态.json',
              'private/日历来源.json', 'private/agent.json', 'private/打印机配置.json')
FILE_DIRS = ('private/attachments', 'private/uploads', 'private/print')
# ponytail: one family archive is capped at 10 GiB / 10,000 files; split larger archives.
MAX_BYTES, MAX_FILES = 10 * 1024 ** 3, 10_000


def allowed(name):
    parts = PurePosixPath(name).parts
    if not parts or '\\' in name or name != '/'.join(parts) or any(p in ('.', '..') for p in parts):
        return False
    if any(p.startswith('.') for p in parts):
        return False
    if parts[-1] in ('id_rsa', 'id_ed25519', 'credentials.json') or PurePosixPath(name).suffix.lower() in ('.log', '.pem', '.key', '.p12', '.pfx'):
        return False
    return name in (*DOCUMENTS, DATABASE, *DATA_FILES) or any(name.startswith(d + '/') for d in FILE_DIRS)


def no_links(path):
    """Refuse symbolic links in an input/output path, including its parents."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Symbolic links are not allowed')
    return path


def sources(root):
    for name in (*DOCUMENTS, *DATA_FILES):
        path = no_links(root / name)
        if path.exists():
            yield name, path
    for name in FILE_DIRS:
        base = no_links(root / name)
        if not base.exists():
            continue
        if not base.is_dir():
            raise ValueError('A backed-up file directory is not a directory')
        for directory, dirs, files in os.walk(base, followlinks=False):
            for entry in (*dirs, *files):
                no_links(Path(directory) / entry)
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            for file in sorted(files):
                path = Path(directory) / file
                relative = path.relative_to(root).as_posix()
                if allowed(relative):
                    yield relative, path


def copy_hash(source, target):
    digest, size = hashlib.sha256(), 0
    while chunk := source.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_BYTES:
            raise ValueError('File exceeds the backup size limit')
        digest.update(chunk)
        target.write(chunk)
    return {'size': size, 'sha256': digest.hexdigest()}


def create(root, output):
    root = no_links(root)
    private = no_links(root / 'private')
    output = Path(output)
    output = no_links(output if output.is_absolute() else root / output)
    if private not in output.parents:
        raise ValueError('Backups must be written inside the application private directory')
    if allowed(output.relative_to(root).as_posix()):
        raise ValueError('Keep backups outside the files being backed up, e.g. private/backups')
    if output.exists():
        raise ValueError('Backup already exists; choose a new filename')
    if not private.is_dir():
        raise ValueError('Application private directory does not exist')
    database = no_links(root / DATABASE)
    if not database.is_file():
        raise ValueError('Application database does not exist')
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.family-backup-', dir=output.parent) as tmp:
        tmp = Path(tmp)
        snapshot = tmp / 'family.sqlite3'
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(snapshot)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')  # The archive must not depend on WAL sidecars.
            if dst.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise ValueError('Source SQLite snapshot failed validation')
        manifest = {'format': 1, 'created': dt.datetime.now(dt.timezone.utc).isoformat(), 'files': {}}
        archive = tmp / 'backup.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            total = 0
            for name, path in [(DATABASE, snapshot), *sources(root)]:
                with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        raise ValueError('Only regular files can be backed up')
                    with zipped.open(name, 'w', force_zip64=True) as target:
                        manifest['files'][name] = copy_hash(source, target)
                total += manifest['files'][name]['size']
                if total > MAX_BYTES or len(manifest['files']) > MAX_FILES:
                    raise ValueError('Backup exceeds the size/file count limit')
            zipped.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.chmod(0o600)
        os.link(archive, output)  # Atomic publication; never overwrite an existing backup.
    return output


def hold_restored_print_jobs(db):
    """Keep print history while invalidating unfinished physical side effects."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='print_jobs'").fetchone():
        return  # Backups from before printing support have no print tables.
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    rows = db.execute("SELECT id,status,note,updated FROM print_jobs WHERE status NOT IN ('received','confirmed_received','cancelled','failed','uncertain')").fetchall()
    with db:
        for ident, status, note, updated in rows:
            audit = f'备份恢复后待核对：原状态={status}；原更新时间={updated}；恢复时间={now}。请先核对打印队列和纸张，不自动重印。'
            db.execute("UPDATE print_jobs SET status='uncertain',claim_token='',note=?,updated=? WHERE id=?", ((note + '\n' if note else '') + audit, now, ident))
            # Keep the old claim_key, CUPS id, body and note for deduplication/audit.


def disable_restored_agent(stage):
    """Retain source bindings while requiring explicit activation after recovery."""
    path = stage / 'private/agent.json'
    if not path.exists():
        return  # Missing configuration already means disabled, including old backups.
    if path.stat().st_size > 32768:
        raise ValueError('Restored Agent configuration is too large')
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Restored Agent configuration must be an object')
    config['enabled'] = False
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def hold_restored_study_timers(db):
    """An archived running clock cannot prove any work after its saved checkpoint."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='study_items'").fetchone():
        return
    with db:
        db.execute("""UPDATE study_items SET running_since=NULL,status='paused',time_needs_review=1,
            version=version+1,last_request_key='',last_request_hash='' WHERE running_since IS NOT NULL""")


def restore(archive, destination):
    archive, destination = no_links(archive), no_links(destination)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Restore destination must not exist or must be an empty directory')
    if not destination.parent.is_dir():
        raise ValueError('Restore destination parent must exist')
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1 or 'manifest.json' not in names:
            raise ValueError('Invalid backup file list')
        if zipped.getinfo('manifest.json').file_size > 2 * 1024 ** 2:
            raise ValueError('Backup manifest is too large')
        manifest = json.loads(zipped.read('manifest.json'))
        if not isinstance(manifest, dict) or manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
            raise ValueError('Invalid backup manifest')
        files = manifest['files']
        if DATABASE not in files or set(names) != set(files) | {'manifest.json'}:
            raise ValueError('Backup files do not match the manifest')
        total = 0
        for entry in entries:
            mode = entry.external_attr >> 16
            if entry.is_dir() or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError('Archive contains a link or special file')
            if entry.filename == 'manifest.json':
                continue
            expected = files[entry.filename]
            if not allowed(entry.filename) or not isinstance(expected, dict):
                raise ValueError('Archive contains an unapproved file')
            if type(expected.get('size')) is not int or expected['size'] != entry.file_size or not re.fullmatch('[0-9a-f]{64}', str(expected.get('sha256', ''))):
                raise ValueError('Invalid file checksum/size metadata')
            total += entry.file_size
            if total > MAX_BYTES:
                raise ValueError('Backup exceeds the size limit')
        stage = Path(tempfile.mkdtemp(prefix='.family-restore-', dir=destination.parent))
        try:
            for name, expected in files.items():
                path = stage / name
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with zipped.open(name) as source, path.open('xb') as target:
                    actual = copy_hash(source, target)
                path.chmod(0o600)
                if actual != expected:
                    raise ValueError('Backup checksum does not match')
            with closing(sqlite3.connect((stage / DATABASE).as_uri() + '?mode=rw', uri=True)) as db:
                if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise ValueError('Restored SQLite database failed validation')
                # Verify archive hashes first, then change only the isolated restore.
                # Its database intentionally differs from the archived print queue.
                hold_restored_print_jobs(db)
                # Ordinary restarts resume timers; restoring old data must not.
                hold_restored_study_timers(db)
                # Old backups must not revive a child login or invitation that a
                # parent revoked after the backup. Shared works remain intact.
                with db:
                    for table in ('child_invites', 'child_sessions'):
                        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                            db.execute('DELETE FROM ' + table)
            # Verification above covers the original bytes. Only the isolated
            # restored config changes; cursors, messages and Agent results stay intact.
            disable_restored_agent(stage)
            no_links(destination)
            if destination.exists():
                destination.rmdir()  # Fails if anything was added since the first check.
            stage.rename(destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('create').add_argument('output', type=Path)
    recovery = commands.add_parser('restore')
    recovery.add_argument('archive', type=Path)
    recovery.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        result = create(args.root, args.output) if args.command == 'create' else restore(args.archive, args.destination)
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as error:
        parser.exit(1, f'Backup/restore failed: {error}\n')
    print(result)
