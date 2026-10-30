"""构建时把已核对的运行时、离线依赖与当前提交的程序装进 一起成长.app/Contents/Resources（不联网）。

CPython 压缩包、5 个 wheel 均按 runtime.lock.json 的 sha256 核对，上游许可证按材料清单核对后随包附带；
程序只取 git HEAD 已提交的公开文件（不含测试与构建源码），逐文件记 hash 写入 BUILD.json，安装与更新据此核对。
"""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from backend import FORMAT, file_sha256, tree_digest  # noqa: E402

EXCLUDED = ('.gitignore', 'packaging/macos/Sources/', 'packaging/macos/build.sh', 'packaging/macos/Info.plist')


def safe(name):
    parts = PurePosixPath(name).parts
    return bool(parts) and not PurePosixPath(name).is_absolute() and '..' not in parts


def verified(path, sha256):
    if file_sha256(path) != sha256:
        raise SystemExit('hash mismatch: ' + path.name)
    return path


def runtime(resources, materials, lock):
    archive = verified(materials / lock['python']['archive'], lock['python']['sha256'])
    target = resources / 'runtime'
    with tarfile.open(archive) as tar:
        members = []
        for member in tar.getmembers():
            if not safe(member.name) or PurePosixPath(member.name).parts[0] != 'python' or not (member.isfile() or member.isdir() or member.issym()):
                raise SystemExit('unexpected runtime member: ' + member.name)
            if member.issym() and (member.linkname.startswith('/') or not safe(str(PurePosixPath(member.name).parent / member.linkname))):
                raise SystemExit('unexpected runtime link: ' + member.name)
            members.append(member)
        tar.extractall(resources / '.runtime-stage', members=members)
    (resources / '.runtime-stage/python').rename(target)
    (resources / '.runtime-stage').rmdir()
    manifest = json.loads((materials / 'MATERIAL-MANIFEST.json').read_text())
    notices = resources / 'licenses/runtime'
    notices.mkdir(parents=True)
    for entry in manifest['notices']:
        shutil.copyfile(verified(materials / 'runtime-notices' / entry['path'], entry['sha256']), notices / entry['path'])
    return target


def wheels(resources, folder, lock, site):
    for entry in lock['wheels']:
        wheel = verified(folder / entry['filename'], entry['sha256'])
        with zipfile.ZipFile(wheel) as zipped:
            for name in zipped.namelist():
                if not safe(name):
                    raise SystemExit('unexpected wheel member: ' + name)
            zipped.extractall(site)
            licenses = [n for n in zipped.namelist() if '.dist-info/' in n and ('LICENSE' in n.upper() or '/licenses/' in n) and not n.endswith('/')]
            target = resources / 'licenses/wheels' / entry['name']
            target.mkdir(parents=True)
            for name in licenses:
                (target / PurePosixPath(name).name).write_bytes(zipped.read(name))
            info = next(n for n in zipped.namelist() if n.endswith('.dist-info/WHEEL'))
            (site / PurePosixPath(info).parent / 'INSTALLER').write_text('yiqichengzhang-mac-build\n')


def code(resources, repo):
    commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    data = subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar', commit], capture_output=True, check=True).stdout
    target, manifest = resources / 'app', {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            name = member.name
            if member.isdir() or name.startswith(EXCLUDED) or PurePosixPath(name).name.startswith('test_') and '/' not in name:
                continue
            if not member.isfile() or not safe(name) or PurePosixPath(name).parts[0] == 'private':
                raise SystemExit('unexpected tracked file: ' + name)
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(tar.extractfile(member).read())
            mode = 0o755 if member.mode & 0o111 else 0o644
            os.chmod(path, mode)
            manifest[name] = {'sha256': file_sha256(path), 'mode': mode}
    return commit, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--materials', type=Path, required=True)
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--build', type=int, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    lock = json.loads((HERE / 'runtime.lock.json').read_text())
    resources = args.resources.resolve()
    target = runtime(resources, args.materials.resolve(), lock)
    site = target / 'lib/python3.11/site-packages'
    wheels(resources, args.wheels.resolve(), lock, site)
    probe = subprocess.run([str(target / 'bin/python3.11'), '-I', '-B', '-c',
                            'import sys, sqlite3, ssl, pydantic, pydantic_core; print(sys.version.split()[0], pydantic.VERSION, pydantic_core.__version__)'],
                           capture_output=True, text=True, check=True).stdout.split()
    if probe != [lock['python']['version']] + [w['version'] for w in lock['wheels'][:2]]:
        raise SystemExit('runtime self-check failed: ' + ' '.join(probe))
    commit, manifest = code(resources, args.repo.resolve())
    digest = tree_digest(target)
    code_digest = __import__('hashlib').sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    build = dict(format=FORMAT, version=args.version, build=args.build, commit=commit, python=lock['python']['version'],
                 runtime_id='cpython-%s-%s' % (lock['python']['version'], digest[:12]), runtime_digest=digest,
                 code_digest=code_digest, code=manifest, materials=lock)
    (resources / 'BUILD.json').write_text(json.dumps(build, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    print(json.dumps(dict(commit=commit, build=args.build, files=len(manifest), runtime_id=build['runtime_id'], self_check=probe)))


if __name__ == '__main__':
    main()
