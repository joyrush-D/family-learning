"""Export reviewed public sources, never family backups or Git history.

python3 export_source.py private/releases/family-learning-source.zip
Only exact !/file entries in .gitignore are read; directories are never walked.
Review the public file contents before publishing: this is not a secret scanner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

from family_backup import copy_hash, no_links, DOCUMENTS


def public_files(root):
    root = no_links(root)
    names = []
    for line in no_links(root / '.gitignore').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#') or line == '/*':
            continue
        if line.startswith('/') and line.endswith('/*'):
            continue  # Child files still need their own explicit allowlist entry.
        if not line.startswith('!/'):
            raise ValueError('Unsupported .gitignore rule; use exact public file entries')
        name = line[2:]
        parts = PurePosixPath(name.rstrip('/')).parts
        if not parts or name.rstrip('/') != '/'.join(parts) or any(p in ('.', '..') for p in parts) or any(c in name for c in '\\*?[]'):
            raise ValueError('Public entries must be canonical literal relative paths')
        if parts[0] == 'private' or name in DOCUMENTS or any(p.startswith('.') for p in parts) and name != '.gitignore':
            raise ValueError('Private data and hidden files cannot be exported')
        if name.endswith('/'):
            continue
        if name not in ('LICENSE', '.gitignore', 'deploy/family-agent.service', 'deploy/family-agent.timer', 'deploy/local.family-learning.collector.plist') and PurePosixPath(name).suffix not in ('.py', '.js', '.cjs', '.html', '.css', '.md', '.txt'):
            raise ValueError('Only reviewed source and documentation file types can be exported')
        path = no_links(root / name)
        if not path.is_file():
            raise ValueError('A listed public source file is missing')
        names.append(name)
    if len(names) != len(set(names)) or not {'.gitignore', 'LICENSE', 'vendor/THREE-LICENSE.txt'} <= set(names):
        raise ValueError('Duplicate entries or missing project/third-party license')
    return sorted(names)


def create(root, output):
    root = no_links(root)
    names = public_files(root)
    output = Path(output)
    output = no_links(output if output.is_absolute() else root / output)
    if output.exists():
        raise ValueError('Output already exists; choose a new filename')
    if output.suffix.lower() != '.zip':
        raise ValueError('Source archive filename must end in .zip')
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.family-source-', dir=output.parent) as temp:
        archive = Path(temp) / 'source.zip'
        manifest = {'format': 1, 'kind': 'public-source', 'files': {}}
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            for name in names:
                path = no_links(root / name)
                with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        raise ValueError('Only regular source files can be exported')
                    with zipped.open(name, 'w') as target:
                        manifest['files'][name] = copy_hash(source, target)
            zipped.writestr('source-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        archive.chmod(0o600)
        os.link(archive, output)  # Atomic publication, refusing a concurrent existing output.
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        result = create(args.root, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Export failed: {error}\n')
    print(f'Source archive: {result}\nSHA-256: {hashlib.sha256(result.read_bytes()).hexdigest()}')
    print('Public contents still require review before publishing. No private paths or Git history were selected.')
