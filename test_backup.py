"""Run with python3 test_backup.py. Uses only synthetic data in a temporary directory."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import tempfile
from unittest.mock import patch
import zipfile
import zlib

import family_backup as backup
import family_print as printing
import family_reading as reading
import family_calendar as calendar


def rejected(call):
    try:
        call()
    except (ValueError, OSError):
        return
    raise AssertionError('Unsafe operation was accepted')


def print_fixture(root):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\x00')) + chunk(b'IEND', b'')
    pdf = printing.image_pdf(png)
    (root / 'private/attachments/synthetic-print.pdf').write_bytes(pdf)
    store = printing.PrintStore(root / 'private', lambda: sqlite3.connect(root / backup.DATABASE))
    with patch.object(store, '_page_count', return_value=1):
        prep = store.prepare({'type': 'attachment', 'name': 'synthetic-print.pdf'}, 'synthetic_prepare')
    jobs = {}
    for status in ('queued', 'claimed', 'submitted', 'spooler_completed', 'uncertain', 'received', 'confirmed_received', 'cancelled', 'failed'):
        job = store.enqueue(dict(preparation_id=prep['id'], pdf_sha256=prep['pdf_sha256'], confirmed=True, idempotency_key='synthetic_' + status, printer='Synthetic_Printer'))
        with store._db() as db:
            db.execute('UPDATE print_jobs SET status=?,bridge_id=?,claim_key=?,claim_token=?,cups_job_id=?,note=?,updated=? WHERE id=?',
                       (status, 'synthetic-bridge', None if status == 'queued' else 'synthetic-bridge:claim_' + status,
                        '' if status == 'queued' else 'synthetic-token-' + status, '' if status in ('queued', 'claimed') else 'Synthetic_Printer-7',
                        'Synthetic original note: ' + status, '2026-01-02T03:04:05+00:00', job['id']))
            jobs[status] = dict(db.execute('SELECT * FROM print_jobs WHERE id=?', (job['id'],)).fetchone())
    return prep, pdf, jobs


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary).resolve() / 'example'
    (root / 'private/uploads').mkdir(parents=True)
    (root / 'private/attachments').mkdir()
    for name in backup.DOCUMENTS:
        (root / name).write_text('虚构示例：甲同学的学习记录。', encoding='utf-8')
    data = b'Example attachment content\x00\x01'
    (root / 'private/uploads/example.bin').write_bytes(data)
    (root / 'private/attachments/example.txt').write_text('Synthetic file', encoding='utf-8')
    (root / 'private/陪伴建议.json').write_text('[]')
    (root / 'private/采集状态.json').write_text('{}')
    printer_config = {'printers': [{'name': 'Synthetic_Printer', 'label': '虚构打印机', 'color': False, 'duplex': True}]}
    (root / 'private/打印机配置.json').write_text(json.dumps(printer_config, ensure_ascii=False))
    reminder_state = {'example-care': {'notified_on': '2026-01-01', 'review_on': '2026-01-04'}}
    (root / 'private/陪伴提醒状态.json').write_text(json.dumps(reminder_state))
    (root / 'private/.env').write_text('DO_NOT_BACK_UP=yes')
    (root / 'private/server.log').write_text('DO_NOT_BACK_UP')
    (root / 'private/uploads/.env').write_text('DO_NOT_BACK_UP=yes')
    (root / 'private/uploads/debug.log').write_text('DO_NOT_BACK_UP')
    learning_context = dict(assistance='少量提示', practice_relation='相近的新题或新片段', comparison_note='虚构同一知识点；难度是否相近待核对')
    legacy_revision = dict(id=1, name='示例甲', score=70)
    learning_revision = dict(legacy_revision, assistance='看过讲解或答案', practice_relation='同一道题或同一片段', comparison_note='虚构先看过讲解，不据此认定独立')
    with sqlite3.connect(root / backup.DATABASE) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, name TEXT, score INTEGER, assistance TEXT NOT NULL DEFAULT '', practice_relation TEXT NOT NULL DEFAULT '', comparison_note TEXT NOT NULL DEFAULT '')")
        db.execute('INSERT INTO records VALUES (1, ?, 85, ?, ?, ?)', ('示例甲', *learning_context.values()))
        db.execute('CREATE TABLE revisions (id INTEGER PRIMARY KEY, record_id INTEGER, previous TEXT, changed TEXT)')
        for version, previous in enumerate((legacy_revision, learning_revision), 1):
            db.execute('INSERT INTO revisions VALUES (?,1,?,?)', (version, json.dumps(previous, ensure_ascii=False), '2026-01-0' + str(version)))
        db.commit()
        legacy_archive = backup.create(root, 'private/backups/without-printing.zip')
        prep, pdf, print_jobs = print_fixture(root)
        for table in ('child_invites', 'child_sessions'):
            db.execute('CREATE TABLE ' + table + ' (token_hash TEXT PRIMARY KEY)')
            db.execute('INSERT INTO ' + table + ' VALUES (?)', ('synthetic-old-hash',))
        db.commit()
        archive = backup.create(root, 'private/backups/example.zip')
        # The live DB moves on; restoration must still recover the committed backup state.
        db.execute("UPDATE records SET score=91, assistance='独立尝试', comparison_note='虚构备份之后的更新'")
        db.commit()
    restored = backup.restore(archive, root.parent / 'restored')
    with sqlite3.connect(restored / backup.DATABASE) as db:
        assert db.execute('SELECT name, score FROM records').fetchall() == [('示例甲', 85)]
        assert db.execute('SELECT assistance,practice_relation,comparison_note FROM records').fetchone() == tuple(learning_context.values())
        restored_revisions = [json.loads(row[0]) for row in db.execute('SELECT previous FROM revisions ORDER BY id')]
        assert restored_revisions == [legacy_revision, learning_revision]
        assert all(key not in restored_revisions[0] for key in learning_context)  # Missing historical facts stay unknown.
        assert db.execute('SELECT changed FROM revisions ORDER BY id').fetchall() == [('2026-01-01',), ('2026-01-02',)]
        for table in ('child_invites', 'child_sessions'):
            assert db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
        db.row_factory = sqlite3.Row
        for status, old in print_jobs.items():
            current = dict(db.execute('SELECT * FROM print_jobs WHERE id=?', (old['id'],)).fetchone())
            if status in ('received', 'confirmed_received', 'cancelled', 'failed', 'uncertain'):
                assert current == old
            else:
                assert current['status'] == 'uncertain' and current['claim_token'] == ''
                assert current['note'].startswith(old['note'] + '\n')
                assert '原状态=' + status in current['note'] and old['updated'] in current['note']
                assert current['updated'] != old['updated'] and '恢复时间=' + current['updated'] in current['note']
                for field in ('id', 'idem', 'fingerprint', 'preparation_id', 'body', 'bridge_id', 'claim_key', 'cups_job_id'):
                    assert current[field] == old[field]
        assert db.execute("SELECT COUNT(*) FROM print_jobs WHERE status IN ('queued','claimed','submitted')").fetchone()[0] == 0
    store = printing.PrintStore(restored / 'private', lambda: sqlite3.connect(restored / backup.DATABASE))
    assert store.preview(prep['id'])[0] == pdf
    assert store.claim('synthetic-bridge', 'Synthetic_Printer', 'new_claim_after_restore') is None
    for status in ('claimed', 'submitted', 'spooler_completed'):
        old = print_jobs[status]
        assert store.claim('synthetic-bridge', 'Synthetic_Printer', 'claim_' + status)['status'] == 'uncertain'
        rejected(lambda: store.claimed_pdf(old['id'], old['claim_token']))
        rejected(lambda: store.report(old['id'], old['claim_token'], 'submitted', 'Synthetic_Printer-7'))
    # Re-restoring a backup of this protected queue keeps the audit and terminal facts.
    restored_again = backup.restore(backup.create(restored, 'private/backups/protected.zip'), root.parent / 'restored-again')
    with sqlite3.connect(restored / backup.DATABASE) as db, sqlite3.connect(restored_again / backup.DATABASE) as again:
        assert db.execute('SELECT * FROM print_jobs ORDER BY id').fetchall() == again.execute('SELECT * FROM print_jobs ORDER BY id').fetchall()
    with sqlite3.connect(root / backup.DATABASE) as db:
        assert db.execute('SELECT score,assistance,comparison_note FROM records').fetchone() == (91, '独立尝试', '虚构备份之后的更新')
        for table in ('child_invites', 'child_sessions'):
            assert db.execute('SELECT token_hash FROM ' + table).fetchall() == [('synthetic-old-hash',)]
        db.row_factory = sqlite3.Row
        assert {r['status']: dict(r) for r in db.execute('SELECT * FROM print_jobs')} == print_jobs
    legacy = backup.restore(legacy_archive, root.parent / 'legacy-restored')
    with sqlite3.connect(legacy / backup.DATABASE) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='print_jobs'").fetchone() is None
    assert (restored / 'private/uploads/example.bin').read_bytes() == data
    assert json.loads((restored / 'private/打印机配置.json').read_text()) == printer_config
    assert json.loads((restored / 'private/陪伴提醒状态.json').read_text()) == reminder_state
    with zipfile.ZipFile(archive) as zipped:
        manifest = json.loads(zipped.read('manifest.json'))
        assert manifest['files']['private/uploads/example.bin']['sha256'] == hashlib.sha256(data).hexdigest()
        assert manifest['files']['private/print/' + prep['id'] + '.pdf']['sha256'] == hashlib.sha256(pdf).hexdigest()
        assert len(manifest['files']) == 13
        assert all('.env' not in p and not p.endswith('.log') for p in zipped.namelist())
        members = {name: zipped.read(name) for name in zipped.namelist()}
    assert restored.stat().st_mode & 0o777 == 0o700
    assert (archive.stat().st_mode & 0o777) == 0o600
    rejected(lambda: backup.create(root, 'public.zip'))
    rejected(lambda: backup.create(root, archive))
    rejected(lambda: backup.restore(archive, restored))
    assert (restored / 'private/uploads/example.bin').read_bytes() == data

    empty = root.parent / 'empty'
    empty.mkdir()
    backup.restore(archive, empty)
    assert (empty / backup.DATABASE).is_file()

    for variant in ('checksum', 'traversal', 'symlink', 'duplicate'):
        bad = root.parent / (variant + '.zip')
        bad_members = dict(members)
        if variant in ('traversal', 'symlink'):
            name = '../escape.txt' if variant == 'traversal' else 'private/uploads/link'
            content = b'../../outside'
            changed_manifest = json.loads(members['manifest.json'])
            changed_manifest['files'][name] = {'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
            bad_members['manifest.json'] = json.dumps(changed_manifest).encode()
        with zipfile.ZipFile(bad, 'w') as zipped:
            for name, content in bad_members.items():
                zipped.writestr(name, b'x' * len(content) if variant == 'checksum' and name == 'private/uploads/example.bin' else content)
            if variant == 'traversal':
                zipped.writestr('../escape.txt', b'../../outside')
            elif variant == 'symlink':
                link = zipfile.ZipInfo('private/uploads/link')
                link.create_system = 3
                link.external_attr = 0o120777 << 16
                zipped.writestr(link, b'../../outside')
            elif variant == 'duplicate':
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    zipped.writestr('manifest.json', members['manifest.json'])
        destination = root.parent / ('restore-' + variant)
        rejected(lambda: backup.restore(bad, destination))
        assert not destination.exists()

    link = root / 'private/uploads/link'
    link.symlink_to(root / '家庭运行规则.md')
    rejected(lambda: backup.create(root, 'private/backups/no-links.zip'))
    assert not (root / 'private/backups/no-links.zip').exists()
    link.unlink()
    os.mkfifo(root / 'private/uploads/pipe')
    rejected(lambda: backup.create(root, 'private/backups/no-special-files.zip'))
    assert not (root / 'private/backups/no-special-files.zip').exists()
    symlink_dir = root.parent / 'linked'
    symlink_dir.symlink_to(empty, target_is_directory=True)
    rejected(lambda: backup.restore(archive, symlink_dir / 'new'))

def reading_restore_check():
    """One real Store agreement covers restored uploads, ledger and retry keys."""
    with tempfile.TemporaryDirectory(prefix='synthetic-reading-backup-') as temporary:
        root = Path(temporary).resolve() / 'family'
        (root / 'private/uploads').mkdir(parents=True)
        ident = 'a' * 32
        original = b'Synthetic reading work: one small observation.'
        (root / 'private/uploads' / ident).write_bytes(original)
        for name in backup.DOCUMENTS:
            (root / name).write_text('Synthetic family documents only.')
        profiles = lambda: [dict(id='child-alpha', name='示例甲'), dict(id='child-beta', name='示例乙')]
        tasks = lambda: [dict(id='T01', child='示例甲', title='虚构阅读通知')]

        def connect(base):
            return sqlite3.connect(base / backup.DATABASE)

        def tables(base):
            with connect(base) as db:
                names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                return {name: db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall() for name in names}

        with connect(root) as db:
            db.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, child TEXT, title TEXT, attachments TEXT)')
            db.execute('INSERT INTO records VALUES (1,?,?,?)', ('示例甲', '虚构原记录', json.dumps([ident])))
            db.execute('CREATE TABLE uploads (id TEXT PRIMARY KEY, name TEXT, size INTEGER, mime TEXT, created TEXT)')
            db.execute('INSERT INTO uploads VALUES (?,?,?,?,?)', (ident, 'synthetic-work.txt', len(original), 'text/plain', '2026-01-01'))
            db.execute('CREATE TABLE task_updates (id TEXT PRIMARY KEY, status TEXT, note TEXT, updated TEXT)')
            db.execute('INSERT INTO task_updates VALUES (?,?,?,?)', ('T01', '已完成', '虚构确认依据', '2026-01-01'))
        old_tables = tables(root)
        legacy_archive = backup.create(root, 'private/backups/before-reading.zip')
        store = reading.Store(lambda: connect(root), profiles, tasks)
        requests = []

        def mutate(action, **values):
            obj = dict(child_id='child-alpha', request_key='synthetic_backup_' + str(len(requests)), **values)
            result = store.mutate(action, obj)
            requests.append((action, obj, result))
            return result.get('task', result.get('redemption'))

        task = mutate('create', book='虚构观察故事', scope='第一小节', method='语音或文字',
                      criteria='说出一处自己的发现', source_task_id='T01', stamps=5)
        task = mutate('start', id=task['id'], version=task['version'], note='虚构孩子选择开始')
        task = mutate('submit', id=task['id'], version=task['version'], work_text='虚构观察与解释', attachments=[ident])
        task = mutate('confirm', id=task['id'], version=task['version'], note='虚构家长核对作品')
        mutate('reserve', reward='虚构待兑现活动', cost=1, note='虚构共同约定')
        redeemed = mutate('reserve', reward='虚构已兑现活动', cost=1, note='虚构共同约定')
        redeemed = mutate('fulfill', id=redeemed['id'], version=redeemed['version'], note='虚构实际兑现依据')
        mutate('correct_redemption', id=redeemed['id'], version=redeemed['version'], reason='虚构补充兑现说明')
        cancelled = mutate('reserve', reward='虚构取消活动', cost=1, note='虚构共同约定')
        mutate('cancel_redemption', id=cancelled['id'], version=cancelled['version'], reason='虚构取消原因')
        mutate('revoke', id=task['id'], version=task['version'], reason='虚构更正：已有兑现，交家长核对')
        expected = store.snapshot()
        balance = expected['balances'][0]
        assert {k: balance[k] for k in ('earned', 'reserved', 'spent', 'available')} == dict(earned=5, reserved=1, spent=1, available=3)
        assert expected['tasks'][0]['attachments'] == [ident]
        assert expected['tasks'][0]['source_task_id'] == 'T01'
        assert expected['tasks'][0]['award']['status'] == '需家长处理'
        assert {r['state'] for r in expected['redemptions']} == {'待兑现', '已兑现', '已取消'}
        assert next(r for r in expected['redemptions'] if r['state'] == '已兑现')['correction_note']
        original_tables = tables(root)
        for name, rows in old_tables.items():
            assert original_tables[name] == rows
        archive = backup.create(root, 'private/backups/reading.zip')
        restored = backup.restore(archive, root.parent / 'restored-reading')
        assert tables(restored) == original_tables
        restored_store = reading.Store(lambda: connect(restored), profiles, tasks)
        assert restored_store.snapshot() == expected
        assert tables(restored) == original_tables
        restored_file = restored / 'private/uploads' / ident
        assert restored_file.read_bytes() == original
        digest = hashlib.sha256(original).hexdigest()
        with zipfile.ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read('manifest.json'))
            assert manifest['files']['private/uploads/' + ident]['sha256'] == digest
        # Persisted events must deduplicate old requests before checking old versions.
        for action, obj, result in requests:
            if action in ('confirm', 'reserve', 'fulfill'):
                assert restored_store.mutate(action, obj) == result
        assert restored_store.snapshot() == expected
        assert tables(restored) == original_tables
        with connect(restored) as db:
            rejected(lambda: reading.validate_record_attachments(db, 'child-beta', [ident]))
        assert tables(root) == original_tables

        legacy = backup.restore(legacy_archive, root.parent / 'legacy-reading')
        assert tables(legacy) == old_tables
        legacy_store = reading.Store(lambda: connect(legacy), profiles, tasks)
        empty = legacy_store.snapshot()
        assert empty['tasks'] == empty['redemptions'] == []
        assert all(b[k] == 0 for b in empty['balances'] for k in ('earned', 'reserved', 'spent', 'available'))
        for name, rows in old_tables.items():
            assert tables(legacy)[name] == rows
        assert (legacy / 'private/uploads' / ident).read_bytes() == original
        result = dict(tasks=1, awards=1, redemptions=3, events=len(requests),
                      earned=5, reserved=1, spent=1, available=3, upload_sha256=digest,
                      new_tables_restored=True, ownership_preserved=True, idempotent_retries=5,
                      legacy_initialization_preserved_existing_data=True, source_unchanged=True)
    result['temporary_data_removed'] = not Path(temporary).exists()
    assert result['temporary_data_removed']
    return result


def calendar_restore_check():
    """Preserve a shared series, its retry version and read-only school sources."""
    with tempfile.TemporaryDirectory(prefix='synthetic-calendar-backup-') as temporary:
        root = Path(temporary).resolve() / 'family'
        (root / 'private/attachments').mkdir(parents=True)
        profiles = lambda: [dict(id='child-alpha', name='示例甲'), dict(id='child-beta', name='示例乙')]

        def connect(base):
            return sqlite3.connect(base / backup.DATABASE)

        def calendar_rows(base):
            with connect(base) as db:
                return db.execute('SELECT * FROM calendar_events ORDER BY id').fetchall()

        with connect(root) as db:
            db.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, title TEXT)')
            db.execute('INSERT INTO records VALUES (1,?)', ('虚构原记录',))
        legacy_archive = backup.create(root, 'private/backups/before-calendar.zip')
        original = b'Synthetic timetable original: Monday, first lesson, no clock time.'
        original_path = 'private/attachments/synthetic-timetable.txt'
        (root / original_path).write_bytes(original)
        source = dict(events=[dict(id='synthetic-school-event', child_ids=['child-beta'],
            title='虚构学校活动', category='school', day='2026-09-12', status='confirmed',
            source='虚构学校通知', task_id='T-SYNTHETIC')], timetables=[dict(
            id='synthetic-timetable', child_id='child-alpha', effective_from='2026-09-07',
            title='虚构学校课表', source='虚构课表来源', attachment='synthetic-timetable.txt',
            week=[dict(weekday=1, sessions=[dict(slot='第一节', title='虚构课程')])])])
        source_path = 'private/日历来源.json'
        source_bytes = json.dumps(source, ensure_ascii=False).encode('utf-8')
        (root / source_path).write_bytes(source_bytes)
        store = calendar.Store(lambda: connect(root), profiles, root / 'private')
        request = dict(id='b' * 32, version=0, child_ids=['child-alpha', 'child-beta'],
            title='虚构家庭活动', category='family', day='2026-09-12', start_time='09:00',
            end_time='10:00', status='tentative', repeat='weekly', until='2026-09-19')
        saved = store.save(request)
        expected = store.snapshot('2026-09-07', '2026-09-20')
        assert expected['source_error'] == '' and len(expected['events']) == 3
        assert len(expected['timetables']) == 2
        assert all(item['sessions'] == [dict(slot='第一节', title='虚构课程')]
                   and 'start_time' not in item for item in expected['timetables'])
        original_rows = calendar_rows(root)
        archive = backup.create(root, 'private/backups/calendar.zip')
        restored = backup.restore(archive, root.parent / 'restored-calendar')
        with zipfile.ZipFile(archive) as zipped:
            assert zipped.testzip() is None
            manifest = json.loads(zipped.read('manifest.json'))
            for path, content in ((source_path, source_bytes), (original_path, original)):
                assert manifest['files'][path]['sha256'] == hashlib.sha256(content).hexdigest()
                assert (restored / path).read_bytes() == content
                assert (restored / path).stat().st_mode & 0o777 == 0o600
        assert calendar_rows(restored) == original_rows
        restored_store = calendar.Store(lambda: connect(restored), profiles, restored / 'private')
        assert restored_store.snapshot('2026-09-07', '2026-09-20') == expected
        # A lost pre-backup response is safe to retry after restoration.
        assert restored_store.save(request) == saved
        assert calendar_rows(restored) == original_rows
        assert calendar_rows(root) == original_rows
        with connect(restored) as db:
            assert db.execute('SELECT * FROM records').fetchall() == [(1, '虚构原记录')]
        legacy = backup.restore(legacy_archive, root.parent / 'legacy-calendar')
        assert not (legacy / source_path).exists()
        with connect(legacy) as db:
            assert db.execute("SELECT name FROM sqlite_master WHERE name='calendar_events'").fetchone() is None
        legacy_store = calendar.Store(lambda: connect(legacy), profiles, legacy / 'private')
        assert legacy_store.snapshot('2026-09-07', '2026-09-20') == dict(events=[], timetables=[], source_error='')
        with connect(legacy) as db:
            assert db.execute('SELECT * FROM records').fetchall() == [(1, '虚构原记录')]


def care_choice_restore_check():
    """Restore real record fields, revisions, original uploads, and retry receipts."""
    import datetime as dt
    import io
    import app
    original_paths=app.ROOT,app.DATA,app.DB
    with tempfile.TemporaryDirectory(prefix='synthetic-care-backup-') as temporary:
        root=Path(temporary).resolve()/'family'
        (root/'private').mkdir(parents=True)
        for name in backup.DOCUMENTS:
            (root/name).write_text('仅为隔离测试的虚构资料。')
        (root/'家庭运行规则.md').write_text('| child-example | 示例甲 | 男 | 10岁 | 四年级 |\n')
        today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
        next_day=(today+dt.timedelta(days=1)).isoformat()
        (root/'private/陪伴建议.json').write_text(json.dumps([dict(id='synthetic-care',child='示例甲',topic='阅读',
            title='虚构建议',evidence='虚构来源',action='交流一个发现',review_on=today.isoformat(),
            expires_on=(today+dt.timedelta(days=7)).isoformat())],ensure_ascii=False))
        reminder={'synthetic-care':dict(status='awaiting_parent_feedback',last_notified=None)}
        (root/'private/陪伴提醒状态.json').write_text(json.dumps(reminder))
        try:
            app.ROOT,app.DATA,app.DB=root,root/'private',root/'private/family.sqlite3'
            app.connect().close()
            original=b'Synthetic feedback original. No real child information.'
            upload=app.save_upload(io.BytesIO(original),len(original),'synthetic-feedback.txt')
            request=dict(child='示例甲',day=today.isoformat(),category='家长观察',subject='阅读',title='虚构反馈',
                         note='这段虚构观察仍需核对。',source='陪伴建议:synthetic-care',attachments=[upload['id']],
                         care_choice='改天回看',care_review_on=next_day,request_key='synthetic_backup_care_request')
            first=app.save_record(request,care_only=True)
            edit={key:value for key,value in request.items() if key not in ['care_choice','care_review_on','request_key']}
            app.save_record(edit | dict(id=first['record_id'],title='虚构文字更正'))
            with app.connect() as connection:
                expected_records=[dict(row) for row in connection.execute('SELECT * FROM records ORDER BY id')]
                expected_revisions=[dict(row) for row in connection.execute('SELECT * FROM revisions ORDER BY id')]
            archive=backup.create(root,'private/backups/care.zip')
            restored=backup.restore(archive,root.parent/'restored')
            app.ROOT,app.DATA,app.DB=restored,restored/'private',restored/'private/family.sqlite3'
            replay=app.save_record(request,care_only=True)
            assert replay['replayed'] and replay['record_id']==first['record_id']
            assert replay['care']['review_status']=='deferred' and replay['care']['review_on']==next_day
            assert (app.DATA/'uploads'/upload['id']).read_bytes()==original
            with app.connect() as connection:
                assert [dict(row) for row in connection.execute('SELECT * FROM records ORDER BY id')]==expected_records
                assert [dict(row) for row in connection.execute('SELECT * FROM revisions ORDER BY id')]==expected_revisions
                assert connection.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='record_request_key'").fetchone()
                try:
                    connection.execute('INSERT INTO records (request_key) VALUES (?)',(request['request_key'],))
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError('restored retry key must remain unique')
            history=app.record_history(first['record_id'])
            assert history['history'][0]['previous']['care_choice']=='改天回看'
            assert history['history'][0]['previous']['care_review_on']==next_day
            assert json.loads((app.DATA/'陪伴提醒状态.json').read_text())==reminder
        finally:
            app.ROOT,app.DATA,app.DB=original_paths


def agent_restore_check():
    """Keep acknowledged messages/results, but do not resume collection on restore."""
    import app
    import family_agent as agent
    with tempfile.TemporaryDirectory(prefix='synthetic-agent-backup-') as temporary:
        root=Path(temporary).resolve()/'family'; data=root/'private'; data.mkdir(parents=True)
        for name in backup.DOCUMENTS:
            (root/name).write_text('仅为隔离测试的虚构资料。')
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        source=dict(id='synthetic@chatroom',platform='wechat',child_id='child-1',name='虚构班级群',cursor='10',enabled=True)
        config=dict(enabled=True,sources=[source]); config_path=data/'agent.json'
        original_config=(json.dumps(config,ensure_ascii=False)+'\n').encode()
        config_path.write_bytes(original_config); config_path.chmod(0o600)
        (data/'collector.json').write_text('{"private_fixture":"DO_NOT_BACK_UP"}')
        (data/'model.env').write_text('SYNTHETIC_PRIVATE_CONFIGURATION=DO_NOT_BACK_UP')
        with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
            app.connect().close(); store=app.agent_store(); now=agent._now()
            request=dict(source_id=source['id'],expected_cursor='10',cursor='11',checked_at=now.isoformat(),
                last_message_time=now.isoformat(),messages=[dict(id='11',time=now.isoformat(),kind='text',
                sender='虚构老师',text='虚构通知',unread=False)],error='')
            store.ingest(request)
            fingerprint=store._job('synthetic-notice',request,now)
            store._save('synthetic-notice',fingerprint,[dict(child_id='child-1',kind='school',title='虚构学校安排',
                body='虚构核对动作',due='',evidence=[dict(ref='message:synthetic:11',text='虚构通知')])],now,
                [(source['id'],'11')])
            item=store.snapshot()['items'][0]
            accepted=store.act(dict(id=item['id'],action='accept'))
            with app.connect() as db:
                evidence=db.execute('SELECT source FROM manual_tasks WHERE id=?',(accepted['task_id'],)).fetchone()[0]
                assert 'message:synthetic:11' in evidence and '虚构通知' in evidence
            store._job('synthetic-retry',dict(record='synthetic'),now)
            store._fail('synthetic-retry',now)
            store._runtime('idle',now)
            # Parent browser sessions are device credentials and must not survive restore.
            with app.connect() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS parent_sessions
                    (hash TEXT PRIMARY KEY, expires REAL NOT NULL, config_hash TEXT NOT NULL)''')
                db.execute('INSERT OR REPLACE INTO parent_sessions VALUES (?,?,?)',
                           ('s' * 64, 4102444800, 'c' * 64))
            table_names=['agent_sources','agent_messages','agent_jobs','agent_items','agent_runtime','manual_tasks',
                         'parent_sessions']
            def rows(base):
                with sqlite3.connect(base/'private/family.sqlite3') as db:
                    return {name:db.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in table_names}
            expected=rows(root)
            archive=backup.create(root,'private/backups/agent.zip')
            archived_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
            restored=backup.restore(archive,root.parent/'restored-agent')
            restored_rows=rows(restored)
            assert rows(root)==expected
            assert restored_rows==dict(expected,parent_sessions=[])
            recovered_config=restored/'private/agent.json'
            assert json.loads(recovered_config.read_text())==dict(config,enabled=False)
            assert recovered_config.stat().st_mode & 0o777 == 0o600
            assert config_path.read_bytes()==original_config
            assert hashlib.sha256(archive.read_bytes()).hexdigest()==archived_hash
            with zipfile.ZipFile(archive) as zipped:
                assert zipped.read('private/agent.json')==original_config
                assert json.loads(zipped.read('manifest.json'))['files']['private/agent.json']['sha256']==hashlib.sha256(original_config).hexdigest()
                assert 'private/collector.json' not in zipped.namelist() and 'private/model.env' not in zipped.namelist()
            with patch.multiple(app,ROOT=restored,DATA=restored/'private',DB=restored/'private/family.sqlite3'):
                recovered=app.agent_store()
                assert recovered.snapshot()['state']=='disabled'
                assert recovered.collector_plan()['sources'][0]['cursor']=='11'
                try:
                    recovered.ingest(request)
                except agent.AgentError as error:
                    assert error.code=='source_disabled'
                else:
                    raise AssertionError('restore must not reactivate message collection')
                # Parent decisions and their stable task IDs survive; no new task is created.
                assert recovered.act(dict(id=item['id'],action='accept'))==accepted
            assert rows(restored)==restored_rows
            # Malformed saved config stops isolated restore instead of enabling it or dropping bindings.
            config_path.write_text('[]')
            bad_archive=backup.create(root,'private/backups/bad-agent-config.zip')
            rejected(lambda:backup.restore(bad_archive,root.parent/'bad-agent-restore'))
            assert not (root.parent/'bad-agent-restore').exists()
            assert not list(root.parent.glob('.family-restore-*'))


def study_restore_check():
    """Recovery pauses archived timers, without resuming old requests or losing checkpoints."""
    import datetime as dt
    import app
    import family_study as study
    with tempfile.TemporaryDirectory(prefix='synthetic-study-backup-') as temporary:
        root=Path(temporary).resolve()/'family'; data=root/'private'; data.mkdir(parents=True)
        for name in backup.DOCUMENTS: (root/name).write_text('仅为隔离测试的虚构资料。')
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        now=dt.datetime(2026,9,8,18,0,tzinfo=study.TZ)
        with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
            store=study.Store(app); store._now=lambda:now
            base=dict(child_id='child-1',day='2026-09-08')
            first=store.save_item(dict(base,title='虚构待继续功课',planned_minutes=20,
                request_key='synthetic-backup-study-add-1'))['items'][0]
            store.action(dict(base,id=first['id'],version=1,action='manual',actual_minutes=12,
                request_key='synthetic-backup-study-manual-1'))
            start=dict(base,id=first['id'],version=2,action='start',request_key='synthetic-backup-study-start-1')
            store.action(start)
            second=store.save_item(dict(base,title='虚构已结束功课',planned_minutes=10,
                request_key='synthetic-backup-study-add-2'))['items'][-1]
            store.action(dict(base,id=second['id'],version=1,action='finish',result='完成',actual_minutes=8,
                request_key='synthetic-backup-study-finish-2'))
            def rows(base):
                with sqlite3.connect(base/backup.DATABASE) as db:
                    db.row_factory=sqlite3.Row
                    return {r['id']:dict(r) for r in db.execute('SELECT * FROM study_items')}
            expected=rows(root); archive=backup.create(root,'private/backups/study.zip')
            archived_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
            restored=backup.restore(archive,root.parent/'restored-study')
            actual=rows(restored)
            assert rows(root)==expected and hashlib.sha256(archive.read_bytes()).hexdigest()==archived_hash
            assert actual[second['id']]==expected[second['id']]
            held=dict(expected[first['id']],running_since=None,status='paused',time_needs_review=1,
                version=expected[first['id']]['version']+1,last_request_key='',last_request_hash='')
            assert actual[first['id']]==held and held['elapsed_seconds']==720
            again=backup.restore(backup.create(restored,'private/backups/study-again.zip'),root.parent/'restored-study-again')
            assert rows(again)==actual
            with patch.multiple(app,ROOT=restored,DATA=restored/'private',DB=restored/'private/family.sqlite3'):
                recovered=study.Store(app); recovered._now=lambda:now+dt.timedelta(hours=1)
                snapshot=recovered.snapshot('child-1','2026-09-08')
                first_item=next(r for r in snapshot['items'] if r['id']==first['id'])
                assert snapshot['active_item'] is None
                assert first_item['actual_minutes'] is None and first_item['elapsed_seconds']==720 and first_item['time_needs_review']
                assert '核对实际分钟' in snapshot['summary']['warning']
                for payload in (start,dict(base,id=first['id'],version=held['version'],action='start',
                    request_key='synthetic-backup-study-start-new')):
                    try: recovered.action(payload)
                    except study.StudyError: pass
                    else: raise AssertionError('A restored timer must not resume until its duration is reconciled')
                reconciled=recovered.action(dict(base,id=first['id'],version=held['version'],action='manual',actual_minutes=15,
                    request_key='synthetic-backup-study-reconcile'))
                current=next(r for r in reconciled['items'] if r['id']==first['id'])
                assert current['actual_minutes']==15 and not current['time_needs_review']
                assert current['time_source']=='manual' and current['status']=='paused'
                with app.connect() as db:
                    assert db.execute('SELECT count(*) FROM records').fetchone()[0]==1
                    assert db.execute('SELECT id FROM records').fetchone()[0]==expected[second['id']]['record_id']


reading_backup_result = reading_restore_check()
calendar_restore_check()
care_choice_restore_check()
agent_restore_check()
study_restore_check()
print('Backup/restore checks passed: SQLite snapshot, Agent sources/cursors/results retained with Agent disabled, calendar/readings/retry keys, original uploads, print no-replay audit, study timers held for review, hashes and unsafe paths.')
