#!/usr/bin/env python3
"""Experimental Mac QQ local CLI: scoped, read-only, no QQ login or process attach.

Workflow inspired by qqcli-rs; QQ field references and native dependency licenses
are recorded in THIRD_PARTY.md. A matching database key is supplied separately.
"""
import argparse
import ctypes as C
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from family_qq_llbot import ReadError, check, decimal, private_text

DEFAULT_CONFIG = Path(__file__).with_name('private') / 'qq-local.json'
MAX_BLOB = 262144
COLUMNS = {'40001', '40003', '40010', '40011', '40027', '40033', '40050', '40090', '40093', '40800'}


def config_read(path):
    config = json.loads(private_text(path))
    check(isinstance(config, dict) and set(config) == {
        'database', 'sqlcipher', 'vfs', 'key_file', 'allowed_groups'}, 'invalid_config')
    for name in ('database', 'sqlcipher', 'vfs', 'key_file'):
        check(isinstance(config[name], str) and Path(config[name]).is_absolute()
              and '\x00' not in config[name], 'invalid_path')
    groups = config['allowed_groups']
    check(isinstance(groups, list) and 0 < len(groups) <= 32
          and all(decimal(g) for g in groups) and len(set(groups)) == len(groups), 'invalid_groups')
    return config


def header(config):
    with open(config['database'], 'rb') as source:
        data = source.read(1024)
    check(len(data) == 1024 and data[32:40] == b'QQ_NT DB', 'unsupported_database_header')


def fields(data):
    """Bounded protobuf wire reader; no recursive decoding of quoted conversations."""
    check(isinstance(data, bytes) and len(data) <= MAX_BLOB, 'invalid_payload')
    pos, result = 0, []
    def varint():
        nonlocal pos
        value = 0
        for shift in range(0, 70, 7):
            check(pos < len(data), 'invalid_payload')
            byte = data[pos]; pos += 1
            check(shift < 63 or byte <= 1, 'invalid_payload')
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ReadError('invalid_payload')
    while pos < len(data):
        check(len(result) < 4096, 'invalid_payload')
        tag = varint(); number, wire = tag >> 3, tag & 7
        check(0 < number < 2**29 and wire in (0, 1, 2, 5), 'invalid_payload')
        if wire == 0:
            value = varint()
        else:
            size = varint() if wire == 2 else (8 if wire == 1 else 4)
            check(size <= len(data) - pos, 'invalid_payload')
            value = data[pos:pos + size]; pos += size
        result.append((number, wire, value))
    return result


def content(blob):
    segments, gaps = [], []
    try:
        outer = fields(blob)
        check(bool(outer), 'empty_payload')
        for number, wire, value in outer:
            if number != 40800 or wire != 2:
                gaps.append('unread_outer_field'); continue
            element = fields(value)
            kinds = [v for n, w, v in element if n == 45002 and w == 0]
            texts = [v for n, w, v in element if n == 45101 and w == 2]
            if kinds == [1] and len(texts) == 1:
                text = texts[0].decode('utf-8')
                check(len(text) <= 20000 and '\x00' not in text, 'invalid_text')
                segments.append({'type': 'text', 'text': text})
            else:
                kind = kinds[0] if len(kinds) == 1 else None
                segments.append({'type': 'unread', 'element_type': kind})
                gaps.append('unread_element')
        check(sum(len(s.get('text', '')) for s in segments) <= 20000, 'invalid_text')
    except (ReadError, UnicodeError):
        return [], ['payload_not_decoded']
    return segments, sorted(set(gaps))


class Database:
    """Only instantiated in the disposable CLI worker, never in the family DB process."""
    def __init__(self, config):
        header(config)
        for name in ('sqlcipher', 'vfs', 'key_file'):
            check(Path(config[name]).is_file(), 'key_required' if name == 'key_file' else name + '_required')
        key = private_text(config['key_file']).encode()
        check(0 < len(key) <= 512 and b'\x00' not in key, 'invalid_key')
        self.api = a = C.CDLL(config['sqlcipher'])
        ptr, integer, string = C.c_void_p, C.c_int, C.c_char_p
        declarations = {
            'open_v2': (integer, [string, C.POINTER(ptr), integer, string]),
            'close': (integer, [ptr]), 'key': (integer, [ptr, ptr, integer]),
            'prepare_v2': (integer, [ptr, string, integer, C.POINTER(ptr), C.POINTER(string)]),
            'bind_text': (integer, [ptr, integer, string, integer, ptr]),
            'step': (integer, [ptr]), 'finalize': (integer, [ptr]),
            'column_count': (integer, [ptr]), 'column_type': (integer, [ptr, integer]),
            'column_int64': (C.c_int64, [ptr, integer]),
            'column_blob': (ptr, [ptr, integer]), 'column_bytes': (integer, [ptr, integer]),
            'enable_load_extension': (integer, [ptr, integer]),
            'load_extension': (integer, [ptr, string, string, C.POINTER(string)]),
            'free': (None, [ptr]), 'busy_timeout': (integer, [ptr, integer]),
        }
        for name, (returns, arguments) in declarations.items():
            fn = getattr(a, 'sqlite3_' + name); fn.restype = returns; fn.argtypes = arguments
        self.db = ptr()
        self.check(a.sqlite3_open_v2(b':memory:', C.byref(self.db), 6, None))
        try:
            self.check(a.sqlite3_enable_load_extension(self.db, 1))
            error = string()
            rc = a.sqlite3_load_extension(self.db, config['vfs'].encode(), None, C.byref(error))
            if error: a.sqlite3_free(error)
            self.check(rc)
        finally:
            a.sqlite3_close(self.db)
        self.db = ptr()
        uri = Path(config['database']).resolve().as_uri() + '?mode=ro&vfs=offset_vfs'
        # SQLITE_OPEN_READONLY | SQLITE_OPEN_URI. Never immutable: QQ may have a live WAL.
        rc = a.sqlite3_open_v2(uri.encode(), C.byref(self.db), 0x41, None)
        try:
            self.check(rc)
            self.check(a.sqlite3_key(self.db, key, len(key)))
            for sql in ('PRAGMA cipher_page_size=4096', 'PRAGMA kdf_iter=4000',
                        'PRAGMA cipher_hmac_algorithm=HMAC_SHA1',
                        'PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512',
                        'PRAGMA query_only=ON', 'PRAGMA trusted_schema=OFF'):
                self.query(sql)
            self.check(a.sqlite3_enable_load_extension(self.db, 0))
            a.sqlite3_busy_timeout(self.db, 1000)
            deadline = time.monotonic() + 10
            callback = C.CFUNCTYPE(integer, ptr)
            self.progress = callback(lambda _: int(time.monotonic() > deadline))
            a.sqlite3_progress_handler.argtypes = [ptr, integer, callback, ptr]
            a.sqlite3_progress_handler(self.db, 1000, self.progress, None)
            check(bool(self.query('PRAGMA cipher_version')), 'sqlcipher_required')
            columns = {row[1] for row in self.query('PRAGMA table_info(group_msg_table)')}
            check(COLUMNS <= columns, 'unsupported_schema')
        except BaseException:
            self.close(); raise

    @staticmethod
    def check(code):
        if code:
            raise ReadError({5: 'database_busy', 8: 'readonly', 9: 'query_timeout',
                             26: 'key_or_database_invalid'}.get(code, 'database_read_failed'))

    def query(self, sql, params=()):
        a, stmt = self.api, C.c_void_p()
        self.check(a.sqlite3_prepare_v2(self.db, sql.encode(), -1, C.byref(stmt), None))
        rows = []
        try:
            for i, value in enumerate(params, 1):
                self.check(a.sqlite3_bind_text(stmt, i, str(value).encode(), -1, C.c_void_p(-1)))
            while True:
                rc = a.sqlite3_step(stmt)
                if rc == 101: break
                if rc != 100: self.check(rc)
                row = []
                for i in range(a.sqlite3_column_count(stmt)):
                    kind = a.sqlite3_column_type(stmt, i)
                    if kind == 5: value = None
                    elif kind == 1: value = a.sqlite3_column_int64(stmt, i)
                    else:
                        size = a.sqlite3_column_bytes(stmt, i)
                        check(size <= MAX_BLOB, 'database_value_too_large')
                        value = C.string_at(a.sqlite3_column_blob(stmt, i), size)
                        if kind != 4: value = value.decode('utf-8')
                    row.append(value)
                rows.append(row)
                check(len(rows) <= 1024, 'result_too_large')
            return rows
        finally:
            a.sqlite3_finalize(stmt)

    def close(self):
        self.api.sqlite3_close(self.db)


def read(config, request):
    command = request['command']
    check(command in ('doctor', 'sessions', 'history', 'search'), 'invalid_command')
    group = request.get('group')
    after = request.get('after')
    limit = request.get('limit', 50)
    check(type(limit) is int and 1 <= limit <= 200, 'invalid_limit')
    start = request.get('since', 0)
    check(type(start) is int and 0 <= start < 253402300800, 'invalid_date')
    scope = hashlib.sha256((str(Path(config['database']).resolve()) + ':' + str(group)).encode()).hexdigest()[:20]
    cursor_time, cursor_id = 0, -(2**63)
    if command in ('history', 'search'):
        check(group in config['allowed_groups'], 'group_not_authorized')
        if after:
            parts = after.split(':')
            check(len(parts) == 3 and parts[0] == scope, 'cursor_scope_mismatch')
            cursor_time, cursor_id = int(parts[1]), int(parts[2])
            check(0 <= cursor_time < 253402300800 and -(2**63) <= cursor_id < 2**63, 'invalid_cursor')
    else:
        check(not group and not after, 'invalid_arguments')
    keyword = request.get('keyword')
    if command == 'search':
        check(isinstance(keyword, str) and 0 < len(keyword) <= 200, 'invalid_keyword')
    db = Database(config)
    try:
        if command == 'doctor':
            return {'schema': 'nt_group_numeric_v1', 'database_readable': True, 'collector_compatible': False}
        if command == 'sessions':
            groups = config['allowed_groups']
            rows = db.query('SELECT CAST([40027] AS TEXT),COUNT(*),MAX([40050]) FROM group_msg_table '
                            'WHERE [40010]=2 AND [40027] IN (' + ','.join('?' for _ in groups) +
                            ') GROUP BY [40027] ORDER BY MAX([40050]) DESC', groups)
            return {'sessions': [dict(group_id=str(g), local_message_count=n, latest_time=t) for g, n, t in rows],
                    'scope': 'configured_groups_only', 'names_resolved': False}
        # ponytail: scan one bounded local page; add an index only after real-volume measurements.
        rows = db.query('SELECT [40001],[40003],[40027],[40033],[40050],[40090],[40093],[40011],'
                        f'CASE WHEN length([40800]) <= {MAX_BLOB} THEN [40800] END '
                        'FROM group_msg_table WHERE [40010]=2 AND [40027]=? AND [40050]>=? '
                        'AND ([40050]>? OR ([40050]=? AND [40001]>?)) '
                        'ORDER BY [40050],[40001] LIMIT ?',
                        (group, start, cursor_time, cursor_time, cursor_id, limit + 1))
        messages = []
        page = rows[:limit]
        for ident, seq, peer, sender, when, card, nick, kind, blob in page:
            check(str(peer) == group and type(ident) is int and type(when) is int
                  and 0 <= when < 253402300800 and type(seq) is int, 'invalid_message_row')
            check(isinstance(card, (str, type(None))) and isinstance(nick, (str, type(None))), 'invalid_sender')
            segments, gaps = content(blob)
            if kind != 2: gaps = sorted(set(gaps + ['message_kind_not_fully_decoded']))
            text = ''.join(s.get('text', '') for s in segments)
            if command == 'search' and keyword.casefold() not in text.casefold(): continue
            messages.append(dict(id=str(ident), sequence=str(seq), group_id=group, time=when,
                                 sender=dict(id=str(sender), card=card or '', nickname=nick or ''),
                                 text=text, segments=segments, unread=gaps,
                                 content_complete=bool(segments) and not gaps, recall_state='not_verified'))
        return dict(messages=messages, scanned=len(page), has_more=len(rows) > limit,
                    next_cursor=f'{scope}:{page[-1][4]}:{page[-1][0]}' if page else after,
                    coverage='local_database_page_only', complete_history=False,
                    attachments_read=False, collector_compatible=False)
    finally:
        db.close()


def isolated(config_path, request):
    # The VFS registers a process-wide default. No native library loads in the caller.
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'],
                            input=json.dumps({'config': str(config_path), 'request': request}),
                            capture_output=True, text=True, timeout=15)
    check(result.returncode in (0, 3) and len(result.stdout) <= 16 * 1024 * 1024, 'reader_failed')
    return json.loads(result.stdout)


def error_result(error):
    code = str(error) if isinstance(error, ReadError) else (
        'setup_file_missing' if isinstance(error, FileNotFoundError) else
        'file_access_denied' if isinstance(error, PermissionError) else
        'reader_timeout' if isinstance(error, subprocess.TimeoutExpired) else 'local_read_failed')
    steps = {'key_required': 'Supply the matching local database key in the configured private file; no automatic key extraction.',
             'sqlcipher_required': 'Configure a compatible SQLCipher dynamic library.',
             'vfs_required': 'Configure the separately built NTQQ offset VFS.',
             'unsupported_schema': 'Verify this QQ version against the supported group message columns.',
             'key_or_database_invalid': 'Verify the key matches this database and check database integrity.'}
    return {'ok': False, 'error': code, 'next_command': 'doctor',
            'next_step': steps.get(code, 'Check local configuration and file access.'), 'collector_compatible': False}


def main():
    if sys.argv[1:] == ['--worker']:
        try:
            obj = json.load(sys.stdin)
            result = {'ok': True, 'data': read(config_read(obj['config']), obj['request'])}
        except (ReadError, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            result = error_result(error)
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
        parser.add_argument('--json', action='store_true', help='JSON is also the default output')
        commands = parser.add_subparsers(dest='command', required=True)
        init = commands.add_parser('init', help='save explicit local paths and group allowlist; no key extraction')
        for name in ('database', 'sqlcipher', 'vfs', 'key-file'):
            init.add_argument('--' + name, type=Path, required=True)
        init.add_argument('--group', action='append', required=True)
        for name in ('doctor', 'sessions'):
            commands.add_parser(name)
        for name in ('history', 'search'):
            p = commands.add_parser(name); p.add_argument('group')
            if name == 'search': p.add_argument('keyword')
            p.add_argument('--since', help='YYYY-MM-DD, Asia/Shanghai')
            p.add_argument('--after'); p.add_argument('--limit', type=int, default=50)
        args = parser.parse_args()
        try:
            if args.command == 'init':
                config = {name: str(getattr(args, name).expanduser().resolve())
                          for name in ('database', 'sqlcipher', 'vfs', 'key_file')}
                config['allowed_groups'] = args.group
                check(0 < len(args.group) <= 32 and all(decimal(g) for g in args.group)
                      and len(set(args.group)) == len(args.group), 'invalid_groups')
                check(len(json.dumps(config).encode()) <= 4096, 'config_too_large')
                header(config)
                args.config.parent.mkdir(parents=True, exist_ok=True)
                with os.fdopen(os.open(args.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
                    json.dump(config, out, ensure_ascii=False); out.flush(); os.fsync(out.fileno())
                result = {'ok': True, 'data': {'configured': True, 'database_readable': False,
                                             'next_command': 'doctor', 'collector_compatible': False}}
            else:
                request = vars(args).copy(); request.pop('config'); request.pop('json')
                if request.get('since'):
                    request['since'] = int(datetime.strptime(request['since'], '%Y-%m-%d')
                                           .replace(tzinfo=timezone(timedelta(hours=8))).timestamp())
                else: request['since'] = 0
                result = isolated(args.config, request)
        except (ReadError, OSError, ValueError, TypeError, subprocess.TimeoutExpired) as error:
            result = error_result(error)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result['ok'] else 3


if __name__ == '__main__':
    sys.exit(main())
