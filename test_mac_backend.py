"""Mac App 后台安装器的只读检查与核对规则。全是临时虚构目录；不安装、不加载任何服务，只读查询测试服务名的状态。"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
import types
import unittest
import zipfile
from contextlib import closing
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / 'packaging/macos'))
import backend  # noqa: E402
import configure_mac  # noqa: E402
import family_backup  # noqa: E402


class Args:
    def __init__(self, **values):
        self.test_profile = self.support = self.port = self.test_fault = None
        self.__dict__.update(values)


def family_db(path, at):
    """完全虚构的 47 张表：登录与邀请、恢复时会挂起的打印/计时、各种存储类型、需加引号的表名和空表。"""
    with closing(sqlite3.connect(path)) as c, c:
        c.execute('CREATE TABLE parent_sessions (hash TEXT PRIMARY KEY, expires INTEGER, config_hash TEXT NOT NULL)')
        c.execute('CREATE TABLE child_sessions (hash TEXT PRIMARY KEY, child_id TEXT, expires)')
        c.execute('CREATE TABLE child_invites (code TEXT PRIMARY KEY, child_id TEXT)')
        c.execute('CREATE TABLE print_jobs (id TEXT PRIMARY KEY, status TEXT, claim_token TEXT, note TEXT, updated TEXT, body BLOB)')
        c.execute('CREATE TABLE study_items (id TEXT PRIMARY KEY, running_since TEXT, status TEXT, time_needs_review INTEGER, '
                  'version INTEGER, last_request_key TEXT, last_request_hash TEXT, title TEXT)')
        c.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, note TEXT, score REAL, photo BLOB, extra)')
        c.execute('CREATE TABLE "odd ""name"" table" (v)')
        for i in range(40):
            c.execute('CREATE TABLE empty_%02d (id INTEGER PRIMARY KEY, value TEXT)' % i)
        c.executemany('INSERT INTO parent_sessions VALUES (?,?,?)', [('near', at + 300, 'c'), ('long', at + 180 * 86400, 'c'),
                                                                    ('old', at - 5, 'c'), ('legacy', None, 'c')])
        c.executemany('INSERT INTO child_sessions VALUES (?,?,?)', [('kid-near', 'kid-1', at + 300),
                                                                   ('kid-legacy', 'kid-1', '2026-11-30T00:00:00'), ('kid-old', 'kid-1', at - 60)])
        c.execute("INSERT INTO child_invites VALUES ('INVITE-1', 'kid-1')")
        c.executemany('INSERT INTO print_jobs VALUES (?,?,?,?,?,?)', [('pj-1', 'queued', 'tok', '', 't0', b'%PDF-fictional'),
                                                                      ('pj-2', 'received', '', 'done', 't1', None)])
        c.executemany('INSERT INTO study_items VALUES (?,?,?,?,?,?,?,?)', [('st-1', 't0', 'running', 0, 3, 'k', 'h', '虚构练习'),
                                                                          ('st-2', None, 'done', 0, 1, '', '', '虚构阅读')])
        c.executemany('INSERT INTO records VALUES (?,?,?,?,?)', [(1, '虚构笔记', 1.5, b'\0\xff', None), (2, '1', 1.0, b'', 1),
                                                                 (3, None, None, None, '1'), (5, 'x', 0.0, b'', 1.0)])
        c.execute("INSERT INTO records VALUES (6, CAST(x'ff41' AS TEXT), 2.0, x'', x'00')")
        c.executemany('INSERT INTO "odd ""name"" table" VALUES (?)', [(b'blob',), ('text',), (None,)])


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'support').mkdir()
        self.port = free_port()
        self.p = backend.profile(Args(test_profile=str(self.root), port=self.port, support=str(self.root / 'support')))

    def tearDown(self):
        self.tmp.cleanup()


class ProfileTest(Base):
    def test_test_profile_is_isolated_and_explicit(self):
        self.assertTrue(self.p['label'].startswith('test.yiqichengzhang.'))
        self.assertEqual((self.p['base'], self.p['agents']), (self.root / 'backend', self.root / 'LaunchAgents'))
        for bad in (Args(test_profile=str(self.root), support=str(self.root / 'support')), Args(test_profile=str(self.root), port=1),
                    Args(port=40123), Args(test_fault='after_start')):
            with self.assertRaises(backend.Refused):
                backend.profile(bad)
        library = self.root / 'Library/inside'
        library.mkdir(parents=True)
        with mock.patch.object(Path, 'home', return_value=self.root), self.assertRaises(backend.Refused):
            backend.profile(Args(test_profile=str(library), port=self.port, support=str(self.root / 'support')))

    def test_production_uses_the_one_family_label_and_port(self):
        production = backend.profile(Args())
        self.assertEqual((production['label'], production['port']), (configure_mac.LABEL, 8765))
        self.assertEqual(production['agents'], Path.home() / 'Library/LaunchAgents')

    def test_bundle_manifest_rejects_paths_outside_the_code(self):
        for bad in ('../x.py', '/etc/x', 'private/family.sqlite3'):
            (self.root / 'BUILD.json').write_text(json.dumps({'format': 1, 'build': 1, 'code': {bad: {}}}))
            with self.assertRaises(backend.Refused):
                backend.build_info(self.root)


class CheckTest(Base):
    def state(self):
        return backend.check(self.p)['state']

    def test_fresh_only_without_any_existing_trace(self):
        self.assertEqual(self.state(), 'fresh')
        (self.p['support'] / 'desktop.json').write_text('{}')
        self.assertEqual(self.state(), 'existing')
        (self.p['support'] / 'desktop.json').unlink()
        self.p['base'].mkdir()
        self.assertEqual(self.state(), 'existing')
        self.p['base'].rmdir()
        self.p['agents'].mkdir()
        other = self.p['agents'] / 'com.example.other-family.plist'
        other.write_bytes(plistlib.dumps({'Label': 'com.example.other-family', 'ProgramArguments': ['/x/python3', '/x/family_agent.py']}))
        self.assertEqual(self.state(), 'existing', 'a family service under another label still counts')
        other.write_bytes(plistlib.dumps({'Label': 'com.example.unrelated', 'ProgramArguments': ['/usr/bin/true']}))
        self.assertEqual(self.state(), 'fresh')
        with socket.socket() as busy:
            busy.bind(('127.0.0.1', self.port))
            busy.listen()
            self.assertEqual(self.state(), 'port_busy')


class OwnershipTest(Base):
    def test_only_a_record_that_verifies_file_by_file_is_owned(self):
        app = self.p['base'] / 'app'
        app.mkdir(parents=True)
        (app / 'app.py').write_text('print(1)\n')
        plist = self.p['agents'] / (self.p['label'] + '.web.plist')
        plist.parent.mkdir()
        plist.write_bytes(b'<plist/>')
        python = self.root / 'python3.11'
        python.write_text('')
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        state = dict(format=1, state='installed', label=self.p['label'], port=self.p['port'], base=str(self.p['base']),
                     code={'app.py': {'sha256': sha(app / 'app.py'), 'mode': 0o644}}, plists={plist.name: sha(plist)}, python=str(python))
        backend.write_state(self.p, state)
        self.assertEqual(oct(backend.state_path(self.p).stat().st_mode & 0o777), '0o600')
        self.assertEqual(backend.owned(self.p)['label'], self.p['label'])
        (app / 'app.py').write_text('print(2)\n')
        with self.assertRaises(backend.Refused) as refused:
            backend.owned(self.p)
        self.assertEqual(refused.exception.state, 'modified')
        (app / 'app.py').write_text('print(1)\n')
        backend.write_state(self.p, dict(state, label='local.family-learning'))
        with self.assertRaises(backend.Refused) as refused:
            backend.owned(self.p)
        self.assertEqual(refused.exception.state, 'unknown_install')
        backend.write_state(self.p, dict(state, state='uninstalled'))
        with self.assertRaises(backend.Refused):
            backend.owned(self.p)
        backend.state_path(self.p).unlink()
        with self.assertRaises(backend.Refused) as refused:
            backend.owned(self.p)
        self.assertEqual(refused.exception.state, 'not_owned')


class DataChecksTest(Base):
    def test_tree_digest_tracks_content_mode_and_links_but_not_bytecode(self):
        tree = self.root / 'runtime/bin'
        tree.mkdir(parents=True)
        (tree / 'python3.11').write_text('x')
        os.symlink('python3.11', tree / 'python3')
        first = backend.tree_digest(self.root / 'runtime')
        (tree / '__pycache__').mkdir()
        (tree / '__pycache__/a.cpython-311.pyc').write_bytes(b'\0')
        self.assertEqual(backend.tree_digest(self.root / 'runtime'), first)
        os.chmod(tree / 'python3.11', 0o755)
        self.assertNotEqual(backend.tree_digest(self.root / 'runtime'), first)


class RowsTest(Base):
    def setUp(self):
        super().setUp()
        self.at = 1_800_000_000
        self.db = self.root / 'family.sqlite3'
        family_db(self.db, self.at)

    def changed(self, statement):
        copy = self.root / 'changed.sqlite3'
        shutil.copyfile(self.db, copy)
        with closing(sqlite3.connect(copy)) as c, c:
            c.execute(statement)
        return backend.rows(copy, verify=True)

    def test_every_table_value_and_storage_type_counts(self):
        first = backend.rows(self.db, verify=True)
        self.assertEqual(len(first), 47)
        self.assertEqual((first['empty_00']['rows'], first['odd "name" table']['rows'], first['records']['rows']), (0, 3, 5))
        self.assertEqual(backend.rows(self.db), first)
        counts = {t: v['rows'] for t, v in first.items()}
        for statement in ("UPDATE records SET note='虚构笔记（改）' WHERE id=1",       # 同样行数，只改一个值
                          "UPDATE records SET extra='1' WHERE id=2",                 # INTEGER 1 → TEXT '1'
                          'UPDATE records SET extra=1 WHERE id=5',                   # REAL 1.0 → INTEGER 1
                          'UPDATE records SET photo=CAST(photo AS TEXT) WHERE id=1', # BLOB → 同字节 TEXT
                          "UPDATE records SET note='' WHERE id=3",                   # NULL → 空文字
                          "UPDATE records SET note=CAST(x'ff42' AS TEXT) WHERE id=6",  # 非 UTF-8 文字
                          'UPDATE "odd ""name"" table" SET v=NULL WHERE v=\'text\'',
                          "UPDATE parent_sessions SET expires=expires+1 WHERE hash='near'",
                          "UPDATE print_jobs SET body=NULL WHERE id='pj-1'"):
            with self.subTest(statement=statement):
                after = self.changed(statement)
                self.assertEqual({t: v['rows'] for t, v in after.items()}, counts)
                self.assertNotEqual(after, first)
        held = self.changed("UPDATE print_jobs SET status='uncertain', claim_token='', note='恢复后待核对', updated='t9' WHERE id='pj-1'")
        self.assertNotEqual(held['print_jobs']['sha256'], first['print_jobs']['sha256'])
        self.assertEqual(held['print_jobs']['kept'], first['print_jobs']['kept'], 'only the restore-held columns may differ')

    def test_sessions_keep_five_minute_and_legacy_expiry_at_one_instant(self):
        valid = backend.sessions(self.db, self.at)
        self.assertEqual([len(valid[t]) for t in backend.SESSION_TABLES], [3, 2])
        self.assertEqual(sorted(e for _, e in valid['parent_sessions'] if e), [self.at + 300, self.at + 180 * 86400])
        self.assertTrue(backend.sessions_kept(valid, valid, self.at))
        dropped = dict(valid, parent_sessions=[r for r in valid['parent_sessions'] if r[1] != self.at + 300])
        self.assertFalse(backend.sessions_kept(valid, dropped, self.at + 299), 'a session valid for five more minutes stays')
        self.assertTrue(backend.sessions_kept(valid, dropped, self.at + 300), 'only a session that has really expired may go')
        legacy = dict(valid, child_sessions=[r for r in valid['child_sessions'] if r[1] is not None])
        self.assertFalse(backend.sessions_kept(valid, legacy, self.at + 10 ** 9), 'a legacy expiry is never treated as expired')

    def test_readonly_helper_never_creates_or_changes_a_file(self):
        missing = self.root / 'missing.sqlite3'
        for read in (lambda: backend.rows(missing), lambda: backend.sessions(missing, self.at)):
            with self.assertRaises(FileNotFoundError):
                read()
        self.assertFalse(missing.exists())
        junk = self.root / 'junk.sqlite3'
        junk.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            backend.rows(junk)
        self.assertEqual(junk.read_bytes(), b'not a database')
        digest = backend.file_sha256(self.db)
        backend.rows(self.db, verify=True), backend.sessions(self.db, self.at)
        self.assertEqual(backend.file_sha256(self.db), digest)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.suffix != '.sqlite3' and 'sqlite3' in p.name), [])


class UpdateTest(Base):
    """update 全流程：launchd 启停与运行时复制换成记录调用，备份与恢复直接用原 family_backup；全是虚构资料。"""
    def setUp(self):
        super().setUp()
        self.app, self.res = self.p['base'] / 'app', self.root / 'resources'
        (self.app / 'private').mkdir(parents=True)
        (self.res / 'app').mkdir(parents=True)
        family_db(self.app / backend.DATABASE, int(time.time()))
        for name, text in (('access.json', '{"fictional": true}'), ('手机访问凭据.json', '{"token": "fictional-token-0000"}'),
                           ('agent.json', '{"enabled": true}'), ('collector.json', '{}')):
            (self.app / 'private' / name).write_text(text)
        (self.app / 'app.py').write_text('build = 1\n')
        (self.app / '家庭运行规则.md').write_text('虚构的家庭规则\n')  # 备份也收的 private/ 以外家庭文档
        (self.res / 'app/app.py').write_text('build = 2\n')
        entry = lambda path: {'sha256': backend.file_sha256(path), 'mode': 0o644}
        self.state = dict(format=1, state='installed', label=self.p['label'], port=self.port, base=str(self.p['base']),
                          build=1, python=sys.executable, code={'app.py': entry(self.app / 'app.py')}, plists={})
        self.info = dict(build=2, version='0.0.2', commit='0' * 40, runtime_id='fictional', code_digest='b2',
                         code={'app.py': entry(self.res / 'app/app.py')})
        self.starts, self.on_switch, self.on_start, self.after_backup, self.after_restore = [], None, None, None, None
        self.original = backend.rows(self.app / backend.DATABASE)

    def run_backup(self, command):
        command = [str(c) for c in command]
        if 'create' in command:
            family_backup.create(Path(command[command.index('--root') + 1]), Path(command[-1]))
            if self.after_backup:
                self.after_backup()
        else:
            family_backup.restore(Path(command[-2]), Path(command[-1]))
            if self.after_restore:
                self.after_restore(Path(command[-1]))

    def update(self, fault=None):
        def switch(*_):
            if self.on_switch:
                self.on_switch()
            return sys.executable

        def start(*_):
            self.starts.append(len(self.starts))
            if self.on_start and len(self.starts) == 1:
                self.on_start()
        plan = lambda *a, **k: {'files': {}, 'collector_enabled': False}
        with mock.patch.multiple(backend, owned=lambda p: self.state, stop=lambda p: None, start=start, run=self.run_backup,
                                 copy_runtime=switch, configure=lambda: types.SimpleNamespace(plan=plan)):
            try:
                reply = backend.update(self.p, self.res, self.info, fault)
            except backend.Refused as refused:
                reply = backend.result(refused.state, str(refused))
                self.cause, self.context = str(refused.__cause__ or ''), str(refused.__context__ or '')
        self.assertNotIn('fictional-token', json.dumps(reply, ensure_ascii=False))
        return reply

    def sql(self, statement, *args, db=None):
        with closing(sqlite3.connect(db or self.app / backend.DATABASE)) as c, c:
            return c.execute(statement, args).fetchall()

    def code(self):
        return (self.app / 'app.py').read_text()

    def test_update_checks_every_row_and_keeps_sessions_and_settings(self):
        # 新服务启动后可以照常清理已过期的会话；停写时还有效的（含五分钟内到期、旧格式）都要在。
        self.on_start = lambda: self.sql('DELETE FROM parent_sessions WHERE expires < ?', int(time.time()))
        reply = self.update()
        self.assertEqual((reply['state'], reply['checked_tables'], self.code(), len(self.starts)), ('updated', 47, 'build = 2\n', 1))
        self.assertEqual({r[0] for r in self.sql('SELECT hash FROM parent_sessions')}, {'near', 'long', 'legacy'})
        self.assertEqual(len(self.sql('SELECT * FROM child_sessions')), 3)
        live = backend.rows(self.app / backend.DATABASE)
        self.assertEqual({t: v for t, v in live.items() if t != 'parent_sessions'},
                         {t: v for t, v in self.original.items() if t != 'parent_sessions'}, 'restore policy never touches the live DB')
        self.assertTrue(json.loads((self.app / 'private/agent.json').read_text())['enabled'])
        archive = next((self.app / 'private/backups').glob('更新前-1-*.zip'))
        with zipfile.ZipFile(archive) as zipped, tempfile.TemporaryDirectory() as tmp:
            zipped.extract(backend.DATABASE, tmp)
            self.assertEqual(backend.rows(Path(tmp) / backend.DATABASE), self.original, 'the archive keeps every row incl. logins')

    def test_same_count_change_while_stopped_rolls_back_code_only(self):
        self.on_switch = lambda: self.sql("UPDATE records SET note='停写期间被改' WHERE id=1")
        reply = self.update()
        self.assertEqual((reply['state'], self.code(), len(self.starts)), ('rolled_back', 'build = 1\n', 1))
        self.assertIn('changed while the services were stopped', self.cause)
        self.assertEqual(self.sql('SELECT note FROM records WHERE id=1'), [('停写期间被改',)], 'never refilled from the backup')

    def test_settings_change_keeps_writers_stopped(self):
        self.on_switch = lambda: (self.app / 'private/手机访问凭据.json').write_text('{"token": "fictional-token-1111"}')
        reply = self.update()
        self.assertEqual((reply['state'], self.code(), self.starts), ('rollback_failed', 'build = 1\n', []))
        self.assertIn('private settings changed', self.context)

    def test_family_document_change_while_stopped_keeps_writers_stopped(self):
        self.on_switch = lambda: (self.app / '家庭运行规则.md').write_text('停写期间被改\n')
        reply = self.update()
        self.assertEqual((reply['state'], self.code(), self.starts), ('rollback_failed', 'build = 1\n', []))
        self.assertEqual((self.app / '家庭运行规则.md').read_text(), '停写期间被改\n')

    def test_failure_after_start_keeps_records_written_by_the_new_services(self):
        self.on_start = lambda: self.sql("INSERT INTO records (id, note) VALUES (99, '新服务写入的虚构记录')")
        reply = self.update('after_start')
        self.assertEqual((reply['state'], self.code(), len(self.starts)), ('rolled_back', 'build = 1\n', 2))
        self.assertIn('declared test fault', self.cause)
        self.assertEqual(self.sql('SELECT note FROM records WHERE id=99'), [('新服务写入的虚构记录',)])

    def test_backup_must_match_the_stopped_rows(self):
        self.after_backup = lambda: self.sql("UPDATE study_items SET title='备份后被改' WHERE id='st-2'")
        reply = self.update()
        self.assertEqual((reply['state'], self.code(), len(self.starts)), ('backup_check_failed', 'build = 1\n', 1))

    def test_isolated_restore_may_differ_only_by_restore_policy(self):
        self.after_restore = lambda restored: self.sql("UPDATE records SET note='恢复副本被改' WHERE id=2", db=restored / backend.DATABASE)
        reply = self.update()
        self.assertEqual((reply['state'], self.code(), len(self.starts)), ('backup_check_failed', 'build = 1\n', 1))


if __name__ == '__main__':
    unittest.main()
