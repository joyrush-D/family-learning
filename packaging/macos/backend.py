"""一起成长.app 的后台安装、更新与卸载：只由 App 在家长明确点击后调用，家长不需要终端、Homebrew 或开发用 Python。

check     只读判断能否全新安装：没有桌面连接设置、安装目录、已知家庭服务，端口空闲。
install   把包内程序与运行时复制到本用户稳定目录，复用 configure_mac.plan/install 装原 web/agent/collector/backup 登录服务。
status    只读查看本 App 安装的后台版本。
update    只处理安装记录可逐文件核对的后台：停写→当前代码一致备份→备份包与新代码隔离恢复逐表逐行核对→换代码→
          写入方仍停着时再核主库逐行与设置文件→启动核对；失败只退回已核对的旧代码与服务设置，
          主库、附件、设置和新资料原样保留，绝不用备份回灌。
uninstall 只停自己的服务、删程序文件与运行时；家庭资料、备份和安装记录保留，不会另装或复制主库。
每次只输出一行 JSON；message 是给家长看的文字，不含路径、命令或进程号。
--test-profile 只用于虚构验收：目录须在本用户 Library 以外，服务名带 test. 前缀，端口由测试声明。
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from contextlib import closing

CODE = Path(__file__).resolve().parents[2]  # 本文件所在程序目录（包内或已安装的稳定目录）
FORMAT = 1
KINDS = ('web', 'agent', 'collector', 'backup')
SAFE_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'  # 不探测或启用本机其他 CLI；消息来源以后在网页另行配置
PRODUCTION_LABEL = 'local.family-learning'  # 与 configure_mac.LABEL 相同：同一用户只能有一套家庭后台
FAMILY_SCRIPTS = ('app.py', 'family_agent.py', 'family_collect.py', 'family_backup.py')
CLEARED_BY_RESTORE = ('child_invites', 'child_sessions', 'parent_sessions')  # family_backup.restore 在隔离副本里有意清空
SESSION_TABLES = ('parent_sessions', 'child_sessions')
DATABASE = 'private/family.sqlite3'
# family_backup.restore 在隔离副本里有意挂起未完成的打印与计时：只有这些列可以与原库不同
RESTORE_HELD = {'print_jobs': ('status', 'claim_token', 'note', 'updated'),
                'study_items': ('running_since', 'status', 'time_needs_review', 'version', 'last_request_key',
                                'last_request_hash')}
NOT_SETTINGS = ('private/backups', 'private/attachments', 'private/uploads', 'private/print', 'private/qq-inbox')


class Refused(Exception):
    """给家长的原因；除非文字说明，否则什么也没改。"""
    def __init__(self, message, state='refused'):
        super().__init__(message)
        self.state = state


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def tree_digest(root):
    """运行时目录摘要：相对路径、内容与可执行位、符号链接目标；忽略运行中生成的 __pycache__/.pyc。"""
    root, digest = Path(root), hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__')
        for name in sorted(filenames + [d for d in dirnames if (here / d).is_symlink()]):
            path = here / name
            if path.is_symlink():
                value = 'link:' + os.readlink(path)
            elif name.endswith('.pyc'):
                continue
            else:
                value = file_sha256(path) + (':x' if os.access(path, os.X_OK) else '')
            digest.update((path.relative_to(root).as_posix() + '\0' + value + '\n').encode())
    return digest.hexdigest()


def result(state, message, ok=False, **extra):
    return dict(extra, ok=ok, state=state, message=message)


def profile(args):
    home = Path.home()
    if args.test_profile:
        test = Path(args.test_profile).expanduser().resolve(strict=True)
        library = (home / 'Library').resolve()
        support = Path(args.support).resolve() if args.support else None
        if test == library or library in test.parents or not args.port or not support or library in support.parents:
            raise Refused('测试配置无效：须是本用户资料库以外的独立目录，并声明端口与桌面入口目录。', 'test_profile_refused')
        label = 'test.yiqichengzhang.' + hashlib.sha256(str(test).encode()).hexdigest()[:12]
        return dict(test=True, base=test / 'backend', agents=test / 'LaunchAgents', label=label, port=args.port, support=support)
    if args.port or args.test_fault:
        raise Refused('只有虚构验收可以指定端口或测试故障。', 'test_profile_refused')
    support = Path(args.support) if args.support else home / 'Library/Application Support/local.yiqichengzhang.desktop'
    return dict(test=False, base=home / 'Library/Application Support/local.yiqichengzhang.backend',
                agents=home / 'Library/LaunchAgents', label=PRODUCTION_LABEL, port=8765, support=support)


def origin(p):
    return 'http://127.0.0.1:%d' % p['port']


def build_info(resources):
    resources = Path(resources).resolve(strict=True)
    try:
        info = json.loads((resources / 'BUILD.json').read_text(encoding='utf-8'))
        assert info.get('format') == FORMAT and isinstance(info.get('build'), int) and isinstance(info.get('code'), dict)
        for rel in info['code']:
            parts = Path(rel).parts
            assert rel and not Path(rel).is_absolute() and '..' not in parts and parts[0] != 'private'
    except (OSError, ValueError, AssertionError):
        raise Refused('安装包信息不完整，不能安装或更新。', 'bundle_invalid') from None
    return resources, info


def launchctl(*args):
    return subprocess.run(['/bin/launchctl', *args], capture_output=True, timeout=20, check=False)


def service(p, kind=None):
    return 'gui/%d/%s' % (os.getuid(), p['label'] + ('.' + kind if kind else ''))


def loaded(p, kind=None):
    code = launchctl('print', service(p, kind)).returncode
    if code in (3, 113):
        return False
    if code == 0:
        return True
    raise Refused('无法确认后台服务状态，未做任何改动。', 'launchd_unknown')


def port_free(port):
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def listening(port):
    """是否仍有程序在本机端口上接受连接；停服务时用它判断，不受已关闭连接的 TIME_WAIT 影响。"""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def known_services(p):
    """服务目录里本服务名的设置，或任何运行家庭程序/指向家庭资料的登录服务（含其他标签的已有家庭部署）。"""
    found, agents = [], p['agents']
    if not agents.is_dir():
        return found
    for path in sorted(agents.glob('*.plist')):
        if path.name.startswith(p['label'] + '.'):
            found.append(path.name)
            continue
        try:
            data = plistlib.loads(path.read_bytes())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        arguments = [str(a) for a in data.get('ProgramArguments') or []]
        env = data.get('EnvironmentVariables')
        if any(Path(a).name in FAMILY_SCRIPTS for a in arguments) or isinstance(env, dict) and 'FAMILY_DATA' in env:
            found.append(path.name)
    return found


def check(p):
    if (p['support'] / 'desktop.json').exists():
        return result('existing', '这个桌面入口已经连接过后台，请连接原来的后台；这里不会另装一套。')
    if p['base'].exists() or p['base'].is_symlink():
        return result('existing', '这台 Mac 上已有一起成长后台的安装或资料，请连接原来的后台；不会另装一套，也不会复制资料。')
    if known_services(p) or any(loaded(p, kind) for kind in (None,) + KINDS):
        return result('existing', '这台 Mac 上已有一起成长后台服务，请连接原来的后台；这里不会另装一套。')
    if not port_free(p['port']):
        return result('port_busy', '这台 Mac 的 %d 端口已被其他程序使用，不能在这里安装后台；不会改用其他端口。' % p['port'])
    return result('fresh', '这台 Mac 上还没有一起成长后台。可以在这里安装：资料只保存在这台 Mac 上，关掉窗口后后台继续运行。',
                  ok=True, origin=origin(p))


def state_path(p):
    return p['base'] / 'install.json'


def atomic_write(path, data, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.new')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode), 'wb') as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def write_state(p, state):
    atomic_write(state_path(p), (json.dumps(state, ensure_ascii=False, indent=1) + '\n').encode())


def read_state(p):
    path = state_path(p)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        return None
    return state if isinstance(state, dict) else None


def copy_code(source, root, manifest):
    """逐文件按记录的 hash 复制；源或目标不符即停止。不碰 private/。"""
    for rel, entry in sorted(manifest.items()):
        src, dst = Path(source) / rel, Path(root) / rel
        if src.is_symlink() or not src.is_file() or file_sha256(src) != entry['sha256']:
            raise Refused('程序文件与记录不一致，未继续。', 'code_mismatch')
        dst.parent.mkdir(parents=True, exist_ok=True)
        temporary = dst.with_name('.' + dst.name + '.new')
        shutil.copyfile(src, temporary)
        os.chmod(temporary, entry['mode'])
        os.replace(temporary, dst)
        if file_sha256(dst) != entry['sha256']:
            raise Refused('程序文件复制不完整，未继续。', 'copy_failed')


def copy_runtime(resources, base, info):
    target = base / 'runtime' / info['runtime_id']
    if not target.exists():
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.runtime-', dir=target.parent))
        try:
            shutil.copytree(resources / 'runtime', stage / 'tree', symlinks=True)
            if tree_digest(stage / 'tree') != info['runtime_digest']:
                raise Refused('运行环境复制不完整，未继续。', 'copy_failed')
            (stage / 'tree').rename(target)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    return str(target / 'bin' / 'python3.11')


def configure():
    sys.path.insert(0, str(CODE))
    import configure_mac
    return configure_mac


def install(p, resources, info):
    first = check(p)
    if first['state'] != 'fresh':
        raise Refused(first['message'], first['state'])
    configure_mac = configure()
    base = p['base']
    base.parent.mkdir(parents=True, exist_ok=True)
    try:
        base.mkdir(mode=0o700)
    except FileExistsError:
        raise Refused('这台 Mac 上已有一起成长后台的安装或资料，未安装。', 'existing') from None
    try:
        python = copy_runtime(resources, base, info)
        root = base / 'app'
        copy_code(resources / 'app', root, info['code'])
        write_state(p, dict(format=FORMAT, state='installing', label=p['label'], port=p['port'], base=str(base)))
        prepared = configure_mac.plan(root, origin(p), label=p['label'], python=python, deeptutor_python=python)
        configure_mac.install(prepared, agents=p['agents'])
        write_state(p, installed(p, info, python, prepared))
    except BaseException:
        # configure_mac.install 已撤销它加载的服务与写入的配置；只有撤销已确认（服务未加载、服务设置已删）时，
        # 才删本次新建、还没有家庭资料的安装目录；撤销未确认就原样保留，之后的检查不会再提供安装。
        if not any(loaded(p, kind) for kind in KINDS) and not any(
                (p['agents'] / ('%s.%s.plist' % (p['label'], kind))).exists() for kind in KINDS):
            shutil.rmtree(base, ignore_errors=True)
        raise
    return result('installed', '后台已安装并在运行。关掉窗口或退出桌面入口后，后台继续工作。', ok=True, origin=origin(p))


def installed(p, info, python, prepared, **extra):
    plists = {Path(name).name: hashlib.sha256(content).hexdigest() for name, content in prepared['files'].items()
              if name.startswith('LaunchAgents/')}
    return dict(extra, format=FORMAT, state='installed', label=p['label'], port=p['port'], base=str(p['base']),
                version=info['version'], build=info['build'], commit=info['commit'], runtime_id=info['runtime_id'],
                code_digest=info['code_digest'], python=python, collector_enabled=prepared['collector_enabled'],
                code=info['code'], plists=plists, updated=time.strftime('%Y-%m-%dT%H:%M:%S%z'))


def owned(p):
    state = read_state(p)
    if not state:
        raise Refused('这台 Mac 上的后台不是由这个桌面入口安装的，或安装记录缺失；不会自动更新或卸载。', 'not_owned')
    if (state.get('format') != FORMAT or state.get('label') != p['label'] or state.get('port') != p['port']
            or state.get('base') != str(p['base'])):
        raise Refused('后台的安装记录与这台 Mac 不符，不会自动更新或卸载。', 'unknown_install')
    if state.get('state') != 'installed':
        raise Refused('后台已卸载或上次安装没有完成；家庭资料保留，不会自动改动。', state.get('state') or 'unknown_install')
    root = p['base'] / 'app'
    for rel, entry in state['code'].items():
        path = root / rel
        if path.is_symlink() or not path.is_file() or file_sha256(path) != entry['sha256']:
            raise Refused('后台程序文件与安装记录不一致（可能被手动改动），不会自动更新或卸载。', 'modified')
    for name, digest in state['plists'].items():
        path = p['agents'] / name
        if path.is_symlink() or not path.is_file() or file_sha256(path) != digest:
            raise Refused('后台服务设置与安装记录不一致，不会自动更新或卸载。', 'modified')
    if not Path(state['python']).is_file():
        raise Refused('后台运行环境缺失，不会自动更新或卸载。', 'modified')
    return state


def status(p, info):
    try:
        state = owned(p)
    except Refused as refused:
        return result(refused.state, str(refused))
    extra = dict(origin=origin(p), installed_build=state['build'], bundle_build=info['build'])
    if info['build'] > state['build']:
        return result('update_available', '这个桌面入口带有较新的后台版本，可以在菜单里更新。', ok=True, **extra)
    if info['build'] == state['build'] and info['code_digest'] == state['code_digest']:
        return result('current', '后台已是这个版本。', ok=True, **extra)
    return result('installed_differs', '已装的后台版本与这个桌面入口不同，不会自动改动。', ok=True, **extra)


def stop(p):
    for kind in ('agent', 'collector', 'backup', 'web'):
        launchctl('bootout', service(p, kind))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not any(loaded(p, kind) for kind in KINDS) and not listening(p['port']):
            return
        time.sleep(0.2)
    raise Refused('后台服务没有按时停下，未做改动；请稍后再试。', 'stop_timeout')


def start(p, configure_mac, root):
    for kind in KINDS:
        path = p['agents'] / ('%s.%s.plist' % (p['label'], kind))
        if not path.is_file() or plistlib.loads(path.read_bytes()).get('Disabled') or loaded(p, kind):
            continue
        if launchctl('bootstrap', 'gui/%d' % os.getuid(), str(path)).returncode:
            raise RuntimeError('service did not load: ' + kind)
        if kind == 'web':
            configure_mac.wait_for_web({'url': origin(p), 'root': root})


class Text(bytes):
    """SQLite TEXT 的原字节：与 BLOB 分开标记，非 UTF-8 的文字也能逐字节核对。"""


def database(path, query):
    """只读打开已有资料库；不存在、不是普通文件或打不开就报错，绝不新建或改写。"""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError('database missing')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        return query(connection)


def quoted(name):
    return '"%s"' % name.replace('"', '""')


def value_bytes(value):
    """一个值的存储类型（NULL/INTEGER/REAL/TEXT/BLOB）与原值；长度前缀让拼接没有歧义。"""
    if value is None:
        kind, data = b'n', b''
    elif isinstance(value, int):
        kind, data = b'i', str(value).encode()
    elif isinstance(value, float):
        kind, data = b'r', value.hex().encode()
    elif isinstance(value, Text):
        kind, data = b't', bytes(value)
    else:
        kind, data = b'b', bytes(value)
    return kind + str(len(data)).encode() + b':' + data


def row_digest(values):
    return hashlib.sha256(b''.join(map(value_bytes, values))).digest()


def multiset(header, digests):
    digest = hashlib.sha256(header)
    for item in sorted(digests):
        digest.update(item)
    return digest.hexdigest()


def rows(path, verify=False):
    """每张表（含空表）的列定义、行数与全部行的多重集摘要：与行的顺序无关，改任何一个值或存储类型都会不同。
    kept 不含恢复规则有意改动的列（RESTORE_HELD），只用于核对隔离恢复；其他表的 kept 就是 sha256。"""
    def read(c):
        if verify and c.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise Refused('更新前的备份核对没有通过，未更新；原后台已恢复运行，资料未改动。', 'backup_check_failed')
        found = {}
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            c.text_factory = str
            header = repr(c.execute('PRAGMA table_xinfo(%s)' % quoted(name)).fetchall()).encode()
            c.text_factory = Text
            cursor = c.execute('SELECT * FROM %s' % quoted(name))
            held = {i for i, column in enumerate(cursor.description) if column[0] in RESTORE_HELD.get(name, ())}
            full, kept = [], []
            for values in cursor:
                full.append(row_digest(values))
                if held:
                    kept.append(row_digest(v for i, v in enumerate(values) if i not in held))
            whole = multiset(header, full)
            found[name] = dict(rows=len(full), sha256=whole, kept=multiset(header, kept) if held else whole)
        return found
    return database(path, read)


def sessions(path, at):
    """在 at 这一刻仍有效的家长/孩子会话：逐行摘要与到期时间。到期时间不是数字（旧格式或空）的一律算有效；
    更新只用停写时取的同一时刻判断，接近到期的也要原样保留。"""
    def read(c):
        found = {}
        for table in SESSION_TABLES:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            c.text_factory = Text
            cursor = c.execute('SELECT * FROM %s' % quoted(table))
            names = [column[0] for column in cursor.description]
            valid = []
            for values in cursor:
                expires = values[names.index('expires')] if 'expires' in names else None
                expires = expires if isinstance(expires, (int, float)) else None
                if expires is None or expires > at:
                    valid.append((row_digest(values), expires))
            found[table] = sorted(valid, key=lambda item: item[0])
            c.text_factory = str
        return found
    return database(path, read)


def sessions_kept(before, after, now):
    """停写时有效的会话更新后都还在；只有到期时间已在 now 之前、确已到期的可以不在（不是更新造成的）。"""
    for table, valid in before.items():
        left = [digest for digest, _ in after.get(table, [])]
        for digest, expires in valid:
            if digest in left:
                left.remove(digest)
            elif expires is None or expires > now:
                return False
    return True


def settings(root, extra=None):
    """private/ 下设置与状态文件（访问与手机凭据、证书、Agent/采集/打印设置等）的内容与权限摘要；
    不含主库及其旁文件、备份与附件类资料。给 extra 时只取这些相对路径（备份也收的 private/ 以外家庭文档）。
    只用于比较，摘要和内容都不输出。"""
    root, found = Path(root), {}
    if extra is not None:
        for rel in extra:
            path = root / rel
            found[rel] = ('link:' + os.readlink(path) if path.is_symlink() else '%s:%o' % (
                file_sha256(path), path.stat().st_mode & 0o7777) if path.is_file() else 'missing')
        return found
    for dirpath, dirnames, filenames in os.walk(root / 'private'):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if (here / d).relative_to(root).as_posix() not in NOT_SETTINGS)
        for name in filenames + [d for d in dirnames if (here / d).is_symlink()]:
            path = here / name
            rel = path.relative_to(root).as_posix()
            if rel.startswith(DATABASE):
                continue
            if path.is_symlink():
                found[rel] = 'link:' + os.readlink(path)
            elif path.is_file():
                found[rel] = '%s:%o' % (file_sha256(path), path.stat().st_mode & 0o7777)
            else:
                found[rel] = 'special'
    return found


def check_backup(before, private, archive, isolated, restore, root):
    """备份包与新代码的隔离恢复都须与停写的原库逐表逐行一致、包里的设置文件与原文件一致，否则不更新。
    只有隔离恢复按恢复规则有意清空登录/邀请表、挂起未完成的打印与计时（只这些列不比）、停用 Agent 设置。"""
    failed = Refused('更新前的备份核对没有通过，未更新；原后台已恢复运行，资料未改动。', 'backup_check_failed')
    copy = isolated / 'archived.sqlite3'
    with zipfile.ZipFile(archive) as zipped:
        packed = {name: entry['sha256'] for name, entry in json.loads(zipped.read('manifest.json'))['files'].items()}
        with zipped.open(DATABASE) as source, open(copy, 'xb') as target:
            shutil.copyfileobj(source, target, 1 << 20)
    names = [n for n in packed if n != DATABASE and not n.startswith(tuple(d + '/' for d in NOT_SETTINGS))]
    outside = [n for n in names if not n.startswith('private/')]  # 备份也收的 private/ 以外家庭文档
    live = {**private, **settings(root, outside)}
    if (file_sha256(copy) != packed[DATABASE] or rows(copy, verify=True) != before
            or any(live.get(n, '').split(':')[0] != packed[n] for n in names)):
        raise failed
    restore(isolated / 'restored')
    again = rows(isolated / 'restored' / DATABASE, verify=True)
    back = {**settings(isolated / 'restored'), **settings(isolated / 'restored', outside)}
    if set(again) != set(before) or any(back.get(n, '').split(':')[0] != packed[n] for n in names if n != 'private/agent.json'):
        raise failed
    for table, old in before.items():
        new = again[table]
        if (new['rows'], new['kept']) != (old['rows'], old['kept']) and not (table in CLEARED_BY_RESTORE and new['rows'] == 0):
            raise failed
    return outside


def run(command):
    done = subprocess.run([str(c) for c in command], capture_output=True, timeout=600, check=False,
                          env={'PATH': SAFE_PATH, 'LANG': 'en_US.UTF-8', 'HOME': str(Path.home())})
    if done.returncode:
        script = next((Path(str(c)).name for c in command if str(c).endswith('.py')), 'command')
        raise RuntimeError('%s exited %d: %s' % (script, done.returncode, done.stderr.decode(errors='replace')[-800:]))


def update(p, resources, info, fault=None):
    state = owned(p)
    if info['build'] <= state['build']:
        raise Refused('后台已是这个版本或更新的版本，不需要更新。', 'not_newer')
    configure_mac = configure()
    root, base = p['base'] / 'app', p['base']
    db = root / DATABASE
    old_plists = {name: (p['agents'] / name).read_bytes() for name in state['plists']}
    keep = base / 'rollback' / str(state['build'])
    switched = resumed = False
    private, outside = None, ()
    try:
        stop(p)  # 停不下来也走下面的恢复：重新启动原服务，不留下停着的后台
        # 写入方都停下后：设置文件摘要与判断会话是否有效的时刻都取这一刻，之后的核对都以它为准。
        private, at = settings(root), int(time.time())
        archive = root / 'private/backups' / ('更新前-%s-%s.zip' % (state['build'], time.strftime('%Y%m%d-%H%M%S')))
        archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        run([state['python'], root / 'family_backup.py', '--root', root, 'create', archive])
        before = rows(db)
        live_sessions = sessions(db, at)
        with tempfile.TemporaryDirectory(prefix='family-update-check-') as isolated:
            isolated = Path(isolated).resolve()  # 系统临时目录经 /var 符号链接；恢复工具按规则拒绝带链接的路径
            outside = check_backup(before, private, archive, isolated, lambda target: run(
                [sys.executable, '-B', resources / 'app/family_backup.py', 'restore', archive, target]), root)
        private.update(settings(root, outside))
        # 先留一份逐文件核对过的旧代码，再换新运行时、代码与服务设置。
        if keep.exists():
            shutil.rmtree(keep)
        copy_code(root, keep, state['code'])
        python = copy_runtime(resources, base, info)
        switched = True
        copy_code(resources / 'app', root, info['code'])
        for rel in set(state['code']) - set(info['code']):
            (root / rel).unlink(missing_ok=True)
        prepared = configure_mac.plan(root, origin(p), label=p['label'], python=python, deeptutor_python=python)
        for name, content in prepared['files'].items():
            if name.startswith('LaunchAgents/'):
                atomic_write(p['agents'] / Path(name).name, content)
        # 写入方仍停着：主库每张表逐行（含全部会话与到期时间）和设置文件都须与停写时完全一致，之后才启动。
        if rows(db) != before or {**settings(root), **settings(root, outside)} != private:
            raise RuntimeError('data or settings changed while the services were stopped')
        resumed = True
        start(p, configure_mac, root)
        if p['test'] and fault == 'after_start':
            raise RuntimeError('declared test fault after the new services started')
        # 新服务已在写：只核旧表都在、停写时有效的会话都在（之后才到期的可以不在）；新写入的资料一律保留。
        present = database(db, lambda c: {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        if set(before) - present or not sessions_kept(live_sessions, sessions(db, at), int(time.time())):
            raise RuntimeError('tables or valid sessions missing after update')
        write_state(p, installed(p, info, python, prepared, previous_build=state['build'], backup=archive.name,
                                 checked_tables=len(before)))
    except BaseException as error:
        try:
            stop(p)
            if switched:
                copy_code(keep, root, state['code'])
                for rel in set(info['code']) - set(state['code']):
                    (root / rel).unlink(missing_ok=True)
                for name, content in old_plists.items():
                    atomic_write(p['agents'] / name, content)
            # 写入方还没恢复过：设置文件须与停写时一致才重新启动原服务，否则保持停止、等人处理。
            if private is not None and not resumed and {**settings(root), **settings(root, outside)} != private:
                raise RuntimeError('private settings changed while the services were stopped')
            start(p, configure_mac, root)
            owned(p)
        except Exception:
            raise Refused('更新没有完成，自动恢复原版本也没有完成；家庭资料都保留，请联系维护的人处理。', 'rollback_failed') from error
        if isinstance(error, Refused):
            raise
        raise Refused('更新没有完成，已恢复原来的后台版本；更新前和更新期间的资料都保留。', 'rolled_back') from error
    return result('updated', '后台已更新到这个版本。更新前已做完整备份并核对，原资料和登录都保留。', ok=True,
                  origin=origin(p), checked_tables=len(before), backup=archive.name)


def uninstall(p):
    state = owned(p)
    stop(p)
    root = p['base'] / 'app'
    for name in state['plists']:
        (p['agents'] / name).unlink(missing_ok=True)
    for rel in state['code']:
        (root / rel).unlink(missing_ok=True)
    for dirpath, dirnames, _ in os.walk(root, topdown=False):
        here = Path(dirpath)
        if here == root or here.relative_to(root).parts[0] == 'private':
            continue
        if here.name == '__pycache__':
            shutil.rmtree(here)
        elif not any(here.iterdir()):
            here.rmdir()
    for cache in [root / '__pycache__']:
        shutil.rmtree(cache, ignore_errors=True)
    shutil.rmtree(p['base'] / 'runtime', ignore_errors=True)
    shutil.rmtree(p['base'] / 'rollback', ignore_errors=True)
    write_state(p, dict(state, state='uninstalled', code={}, plists={}, uninstalled=time.strftime('%Y-%m-%dT%H:%M:%S%z')))
    return result('uninstalled', '后台已停止并卸载程序；家庭资料和备份都保留在这台 Mac 上，没有删除。', ok=True)


FAILED = {'install': '后台安装没有完成，已撤销本次安装；家庭资料未改动，可以再试一次。',
          'update': '后台更新没有完成；家庭资料都保留。', 'uninstall': '卸载没有完成；家庭资料都保留。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('check', 'install', 'status', 'update', 'uninstall'))
    parser.add_argument('--resources', required=True, help='App 包内 Contents/Resources')
    parser.add_argument('--support', help='桌面入口自己的设置目录')
    parser.add_argument('--test-profile')
    parser.add_argument('--port', type=int)
    parser.add_argument('--test-fault', choices=('after_start',))
    args = parser.parse_args(argv)
    os.environ['PATH'] = SAFE_PATH
    try:
        if sys.platform != 'darwin' or os.getuid() == 0:
            raise Refused('只支持已登录的 Mac 普通用户。', 'unsupported')
        p = profile(args)
        resources, info = build_info(args.resources)
        if args.command == 'check':
            reply = check(p)
        elif args.command == 'status':
            reply = status(p, info)
        elif args.command == 'install':
            reply = install(p, resources, info)
        elif args.command == 'update':
            reply = update(p, resources, info, args.test_fault)
        else:
            reply = uninstall(p)
    except Refused as refused:
        traceback.print_exc()
        reply = result(refused.state, str(refused))
    except Exception as error:
        traceback.print_exc()
        reply = result('failed', FAILED.get(args.command, '没有完成；家庭资料未改动。'), detail=type(error).__name__)
    print(json.dumps(reply, ensure_ascii=False))
    return 0 if reply['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
