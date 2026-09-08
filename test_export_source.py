"""python3 test_export_source.py — synthetic data, clean install and demo, no Git/LLM required."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from export_source import create, public_files


def rejected(call):
    try:
        call()
    except (ValueError, OSError):
        return
    raise AssertionError('Unsafe export accepted')


@contextmanager
def running(root, demo=False):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith('FAMILY_')}
    env['PORT'] = str(port)
    command = [sys.executable, 'demo.py', '--port', str(port)] if demo else [sys.executable, 'app.py']
    process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path, data=None, headers=None, response_headers=None):
        request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data, headers=headers or {})
        with opener.open(request, timeout=2) as response:
            assert response.status == 200
            if response_headers is not None:
                response_headers.update(response.headers)
            return response.read()
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError('Exported application failed to start')
            try:
                state = json.loads(get('/api/state'))
                break
            except OSError:
                time.sleep(.05)
        else:
            raise AssertionError('Exported application startup timeout')
        yield get, state
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


with tempfile.TemporaryDirectory(prefix='family-source-check-') as temp:
    temp = Path(temp).resolve()
    source = temp / 'source'
    source.mkdir()
    real_root = Path(__file__).resolve().parent
    names = public_files(real_root)
    for name in names:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real_root / name, target)
    # Unlisted private material must stay untouched, including symlinks and history.
    sentinel = b'FICTIONAL-PRIVATE-' + b'CREDENTIAL-ONLY-FOR-EXPORT-CHECK'
    for name in ('private/credentials.json', 'private/family.sqlite3', '.env', '.git/config', '家庭运行规则.md'):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(sentinel)
    (source / 'private/link').symlink_to(source / '.env')
    archive = create(source, 'private/releases/source.zip')
    rejected(lambda: create(source, archive))
    clean = temp / 'clean'
    with zipfile.ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == set(names) | {'source-manifest.json'}
        manifest = json.loads(zipped.read('source-manifest.json'))
        assert manifest['kind'] == 'public-source'
        for name in names:
            raw = zipped.read(name)
            assert sentinel not in raw
            assert manifest['files'][name] == {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        zipped.extractall(clean)
    assert not (clean / 'private').exists() and not (clean / '.git').exists()
    env = {key: value for key, value in os.environ.items() if not key.startswith('FAMILY_')}
    subprocess.run([sys.executable, 'init_family.py', '--child', '示例独立甲', '四年级', '--child', '示例独立乙', '初一'], cwd=clean, env=env, check=True, capture_output=True)
    subprocess.run([sys.executable, 'export_source.py', 'private/repacked.zip'], cwd=clean, env=env, check=True, capture_output=True)
    with zipfile.ZipFile(clean / 'private/repacked.zip') as repacked:
        assert json.loads(repacked.read('source-manifest.json')) == manifest
    with running(clean) as (get, state):
        assert [child['name'] for child in state['children']] == ['示例独立甲', '示例独立乙']
        assert not state['records'] and not state['tasks'] and not state['uploads']
        assert not state['llm']['configured'] and not state['asr']['configured']
        assert b'app.bundle.js' in get('/')
        assert get('/app.bundle.js').startswith(b'(()=>{\n')
        assert get('/startup.js') and get('/vendor/three.module.min.js') and get('/vendor/three.core.min.js')
        assert json.loads(get('/api/calendar?start=2026-01-05&end=2026-01-11'))
        # Exercise the documented data restore + same-version source assembly,
        # rather than treating a new empty install as recovery evidence.
        headers = {'Content-Type': 'application/json', 'X-Family-Token': state['token']}
        original = b'Synthetic saved learning work, independent of the old installation.'
        uploaded = json.loads(get('/api/upload', original, {
            'X-Family-Token': state['token'], 'X-File-Name': 'synthetic-recovered-work.txt',
            'Content-Type': 'application/octet-stream'}))['attachment']
        record = dict(child='示例独立甲', day='2026-01-05', category='学习进展',
                      title='虚构恢复后的学习记录', note='保留自己的观察与原件。', source='家长观察',
                      attachments=[uploaded['id']])
        get('/api/record', json.dumps(record).encode(), headers)
        invite = json.loads(get('/api/child-access/invite', json.dumps({'child_id': 'child-1'}).encode(), headers))
        response_headers = {}
        get('/child/api/login', json.dumps({'invite': invite['invite']}).encode(),
            {'Content-Type': 'application/json'}, response_headers)
        old_cookie = response_headers['Set-Cookie'].split(';')[0]
        assert json.loads(get('/child/api/state', headers={'Cookie': old_cookie}))['child']['id'] == 'child-1'
        unused_invite = json.loads(get('/api/child-access/invite', json.dumps({'child_id': 'child-1'}).encode(), headers))['invite']
        expected_state = json.loads(get('/api/state'))
    # All writers are stopped before archiving the database and family files.
    for name in ('model.env', '打印机配置.json', '网页访问凭据.json'):
        (clean / 'private' / name).write_text('SYNTHETIC_DEPLOYMENT_CONFIG_NOT_IN_DATA_BACKUP')
    subprocess.run([sys.executable, 'family_backup.py', 'create', 'private/backups/recovery.zip'], cwd=clean, env=env, check=True, capture_output=True)
    data_archive = temp / 'recovery.zip'
    shutil.copyfile(clean / 'private/backups/recovery.zip', data_archive)
    with zipfile.ZipFile(data_archive) as zipped:
        assert not any(name in zipped.namelist() for name in (
            'app.py', 'private/model.env', 'private/打印机配置.json', 'private/网页访问凭据.json'))
    recovered = temp / 'recovered'
    subprocess.run([sys.executable, str(clean / 'family_backup.py'), 'restore', str(data_archive), str(recovered)], env=env, check=True, capture_output=True)
    assert not (recovered / 'app.py').exists()
    with zipfile.ZipFile(archive) as zipped:
        for name in names:
            assert not (recovered / name).exists()
        zipped.extractall(recovered)
    shutil.rmtree(clean)  # The old synthetic installation cannot supply missing files.
    with running(recovered) as (get, state):
        assert state['children'] == expected_state['children']
        assert state['records'] == expected_state['records'] and state['uploads'] == expected_state['uploads']
        assert not state['llm']['configured'] and not state['asr']['configured']
        assert state['token'] != expected_state['token']
        assert b'app.bundle.js' in get('/') and get('/app.bundle.js').startswith(b'(()=>{\n')
        assert get('/upload/' + uploaded['id']) == original
        assert b'child.js' in get('/child/')
        access = json.loads(get('/api/child-access'))
        assert all(not child['has_access'] for child in access['children'])
        for path, body, request_headers in (
            ('/child/api/state', None, {'Cookie': old_cookie}),
            ('/child/api/login', json.dumps({'invite': unused_invite}).encode(), {'Content-Type': 'application/json'}),
        ):
            try:
                get(path, body, request_headers)
            except urllib.error.HTTPError as error:
                assert error.code == 401
            else:
                raise AssertionError('Restoration revived old child access')
    demo = temp / 'demo'
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(demo)
    with running(demo, demo=True) as (get, state):
        assert [child['name'] for child in state['children']] == ['示例星星', '示例小宇']
        assert state['records'] and state['tasks']
        assert not state['llm']['configured'] and not state['asr']['configured']
        assert get('/') and get('/app.bundle.js')
    assert not (demo / 'private/family.sqlite3').exists()
    original_ignore = (source / '.gitignore').read_text()
    for bad in ('!/private/credentials.json', '!/.env', '!/家庭运行规则.md', '!/../escape.py', '!/secrets.json', '!/source/*.py'):
        (source / '.gitignore').write_text(original_ignore + '\n' + bad + '\n')
        rejected(lambda: create(source, 'invalid.zip'))
        assert not (source / 'invalid.zip').exists()
    (source / '.gitignore').write_text(original_ignore)
    (source / 'app.py').unlink()
    (source / 'app.py').symlink_to(source / '.env')
    rejected(lambda: create(source, 'linked.zip'))
    (source / 'app.py').unlink()
    rejected(lambda: create(source, 'missing.zip'))
    shutil.copyfile(real_root / 'app.py', source / 'app.py')
    (source / 'vendor').rename(source / 'vendor-real')
    (source / 'vendor').symlink_to(source / 'vendor-real', target_is_directory=True)
    rejected(lambda: create(source, 'linked-parent.zip'))

print('Source export passed: whitelist/hashes/licenses, clean initialization/demo, and same-version source + data recovery HTTP readback with original file and old child access rejected.')
