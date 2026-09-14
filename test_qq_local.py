"""Native Mac CLI acceptance using only synthetic encrypted QQ-shaped records.

python3 test_qq_local.py --sqlcipher /path/libsqlite3.dylib --vfs /path/extension.dylib
Without native arguments, run the portable payload checks only.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from family_qq_local import Database, ReadError, content, fields, isolated


def varint(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128); number >>= 7
    return bytes(result + bytes([number]))


def field(number, value):
    return varint(number * 8 + (2 if isinstance(value, bytes) else 0)) + (
        varint(len(value)) + value if isinstance(value, bytes) else varint(value))


def payload(text, image=False):
    text_element = field(45002, 1) + field(45101, text.encode())
    return field(40800, text_element) + (field(40800, field(45002, 2)) if image else b'')


def run(library=None, extension=None):
    assert content(payload('虚构作业')) == ([{'type': 'text', 'text': '虚构作业'}], [])
    assert content(payload('文字和图片', True))[1] == ['unread_element']
    for bad in (None, b'', b'\x80', b'\xff' * 20, b'\x00', b'\x0a\xff\x7f', b'x' * 262145,
                field(40800, field(45002, 1) + field(45101, b'\xff'))):
        assert content(bad)[1]
    for seed in range(100):
        sample = hashlib.sha256(str(seed).encode()).digest()
        try: fields(sample)
        except ReadError: pass
    if not library:
        return {'portable_payload_checks': True, 'native_checks': 'not_run'}
    library, extension = library.resolve(), extension.resolve()
    with tempfile.TemporaryDirectory(prefix='family-qq-local-test-') as directory:
        root = Path(directory); key = root / 'key'; key.write_text("synthetic'key"); key.chmod(0o600)
        plain = root / 'encrypted.db'; wrapped = root / 'nt_msg.db'; config_path = root / 'config.json'
        config = dict(database=str(wrapped), sqlcipher=str(library), vfs=str(extension),
                      key_file=str(key), allowed_groups=['10002'])
        config_path.write_text(json.dumps(config)); config_path.chmod(0o600)
        a = C.CDLL(str(library)); p = C.c_void_p()
        a.sqlite3_open_v2.argtypes = [C.c_char_p, C.POINTER(C.c_void_p), C.c_int, C.c_char_p]
        a.sqlite3_exec.argtypes = [C.c_void_p, C.c_char_p, C.c_void_p, C.c_void_p, C.c_void_p]
        a.sqlite3_close.argtypes = [C.c_void_p]
        def execute(sql):
            assert a.sqlite3_exec(p, sql.encode(), None, None, None) == 0
        setup = ("PRAGMA key='synthetic''key'; PRAGMA cipher_page_size=4096; PRAGMA kdf_iter=4000;"
                 'PRAGMA cipher_hmac_algorithm=HMAC_SHA1; PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512;')
        def insert(ident, seq, group, text, image=False, when=1700000000):
            return (f"INSERT INTO group_msg_table VALUES({ident},{seq},2,2,{group},80001,{when},"
                    f"'示例老师','fixture',X'{payload(text, image).hex()}');")
        assert a.sqlite3_open_v2(str(plain).encode(), C.byref(p), 6, None) == 0
        execute(setup + 'CREATE TABLE group_msg_table([40001] INTEGER PRIMARY KEY,[40003] INTEGER,'
                '[40010] INTEGER,[40011] INTEGER,[40027] INTEGER,[40033] INTEGER,[40050] INTEGER,'
                '[40090] TEXT,[40093] TEXT,[40800] BLOB);'
                + insert(-20, 1, 10002, '第一条虚构作业')
                + insert(90000000000000003, 2, 10002, '英语听写', True)
                + insert(90000000000000004, 3, 10003, 'UNAUTHORIZED_ROOM_CANARY')
                + 'CREATE TABLE c2c_msg_table(secret TEXT);'
                + "INSERT INTO c2c_msg_table VALUES('PRIVATE_CHAT_CANARY');")
        assert a.sqlite3_close(p) == 0
        head = bytearray(1024); head[32:40] = b'QQ_NT DB'
        wrapped.write_bytes(head + plain.read_bytes())
        def call(command, **extra):
            return isolated(config_path, dict(command=command, **extra))
        before = hashlib.sha256(wrapped.read_bytes()).hexdigest()
        diagnosis = call('doctor')
        assert diagnosis.get('data', {}).get('database_readable'), diagnosis
        sessions = call('sessions')['data']['sessions']
        assert sessions == [dict(group_id='10002', local_message_count=2, latest_time=1700000000)]
        page = call('history', group='10002', limit=1)['data']
        assert page['messages'][0]['id'] == '-20' and page['has_more']
        second = call('history', group='10002', after=page['next_cursor'], limit=1)['data']
        assert second['messages'][0]['id'] == '90000000000000003' and not second['has_more']
        assert second['messages'][0]['unread'] == ['unread_element']
        assert call('history', group='10003')['error'] == 'group_not_authorized'
        assert call('history', group='10002', after='wrong:1700000000:1')['error'] == 'cursor_scope_mismatch'
        assert call('history', group='10002', since=1700000001)['data']['messages'] == []
        search = call('search', group='10002', keyword='听写', limit=1)['data']
        assert search['messages'] == [] and search['has_more'] and search['next_cursor']
        assert call('search', group='10002', keyword='听写', after=search['next_cursor'])['data']['messages'][0]['text'] == '英语听写'
        assert call('search', group='10002', keyword="' OR 1=1 --")['data']['messages'] == []
        assert 'CANARY' not in json.dumps(call('history', group='10002'))
        assert hashlib.sha256(wrapped.read_bytes()).hexdigest() == before
        db = Database(config)  # isolated synthetic test process; never opens the family store
        try:
            try: db.query("DELETE FROM group_msg_table")
            except ReadError as error: assert str(error) == 'readonly'
            else: raise AssertionError('write accepted')
        finally: db.close()
        p = C.c_void_p()
        assert a.sqlite3_open_v2((wrapped.as_uri() + '?vfs=offset_vfs').encode(), C.byref(p), 0x46, None) == 0
        try:
            execute(setup + 'PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0; BEGIN IMMEDIATE;'
                    + insert(90000000000000005, 4, 10002, '之后的虚构通知', when=1700000001))
            assert call('history', group='10002', after=second['next_cursor'])['data']['messages'] == []
            execute('COMMIT;')
            files = [wrapped, Path(str(wrapped) + '-wal')]
            hashes = [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]
            added = call('history', group='10002', after=second['next_cursor'])['data']
            assert added['messages'][0]['text'] == '之后的虚构通知'
            assert [hashlib.sha256(f.read_bytes()).hexdigest() for f in files] == hashes
            execute('ALTER TABLE group_msg_table RENAME COLUMN [40027] TO [999];')
            assert call('doctor')['error'] == 'unsupported_schema'
            execute('ALTER TABLE group_msg_table RENAME COLUMN [999] TO [40027];')
        finally: assert a.sqlite3_close(p) == 0
        assert call('history', group='10002', after=second['next_cursor'])['data']['messages'] == added['messages']
        key.write_text('WRONG_SECRET_CANARY')
        wrong = call('doctor')
        assert wrong['error'] == 'key_or_database_invalid' and 'CANARY' not in json.dumps(wrong)
        key.unlink()
        assert call('doctor')['error'] == 'key_required'
        # Scope validation precedes key access, including when setup is incomplete.
        assert call('history', group='10003')['error'] == 'group_not_authorized'
        config_path.chmod(0o644)
        assert call('doctor')['error'] == 'private_file_required'
        config_path.chmod(0o600)
        cli = Path(__file__).with_name('family_qq_local.py')
        init_path = root / 'new.json'
        argv = [sys.executable, str(cli), '--config', str(init_path), '--json', 'init',
                '--database', str(wrapped), '--sqlcipher', str(library), '--vfs', str(extension),
                '--key-file', str(key), '--group', '10002']
        initialized = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        assert initialized.returncode == 0 and json.loads(initialized.stdout)['data']['configured']
        saved = init_path.read_bytes()
        assert os.stat(init_path).st_mode & 0o777 == 0o600
        assert subprocess.run(argv, capture_output=True, timeout=5).returncode == 3
        assert init_path.read_bytes() == saved
        wrapped.unlink()
        assert call('doctor')['error'] == 'setup_file_missing' and not wrapped.exists()
    return dict(portable_payload_checks=True, native_encrypted_qq_schema_checks=True,
                source_scope=True, exact_int64_ids=True, pagination=True, bounded_search=True,
                explicit_readonly=True, committed_wal=True, main_and_wal_unchanged=True,
                init_no_overwrite=True, secret_errors_redacted=True, real_qq_messages_read=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlcipher', type=Path); parser.add_argument('--vfs', type=Path)
    args = parser.parse_args()
    assert bool(args.sqlcipher) == bool(args.vfs), 'provide both native libraries or neither'
    print(json.dumps(run(args.sqlcipher, args.vfs), ensure_ascii=False))
