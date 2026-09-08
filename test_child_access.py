"""python3 test_child_access.py: isolated fictional HTTP/SQLite access checks."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

import app
import family_child as child


def check():
    original = app.ROOT, app.DATA, app.DB
    with tempfile.TemporaryDirectory(prefix='synthetic-child-access-') as folder, patch.dict(os.environ, {
            'FAMILY_CHILD_COOKIE_PATH': '/child/', 'FAMILY_CHILD_SECURE': '1',
            'FAMILY_CHILD_PUBLIC_URL': 'https://example.invalid/family/child/'}, clear=False):
        app.ROOT = Path(folder)
        app.DATA = app.ROOT / 'private'
        app.DATA.mkdir()
        app.DB = app.DATA / 'family.sqlite3'
        (app.ROOT / '家庭运行规则.md').write_text('| child-1 | 示例星星 | 男 | 10岁 | 四年级 |\n| child-2 | 示例月亮 | 男 | 13岁 | 初一 |\n')
        for file in ('消息来源.md', '学习与成长.md', '跟踪台账.md'):
            (app.ROOT / file).write_text('PARENT_PRIVATE_CANARY')
        for file in ('child.html', 'child.js', 'child.css'):
            (app.ROOT / file).write_text('synthetic public asset')
        app.connect().close()
        store = app.reading_store()
        count = 0
        def reading(action, task=None, child_id='child-1', **fields):
            nonlocal count
            count += 1
            obj = dict(child_id=child_id, request_key='synthetic-parent-' + str(count))
            if task:
                obj.update(id=task['id'], version=task['version'])
            return store.mutate(action, dict(obj, **fields))['task']
        task = reading('create', book='虚构星光故事', scope='虚构第一章', method='拍照或写字', criteria='说出一个发现', stamps=2)
        other = reading('create', child_id='child-2', book='OTHER_CHILD_PRIVATE_CANARY')
        draft_id = task['id']
        try:
            child.parent_action(app, 'share', dict(child_id='child-1', task_id=draft_id, shared=True))
            assert False, 'draft must not be shareable'
        except child.ChildError as exc:
            assert exc.status == 400
        task = reading('start', task, note='PARENT_NOTE_PRIVATE_CANARY')
        shared_file = app.save_upload(io.BytesIO(b'shared fictional original'), 25, 'shared.txt')
        private_file = app.save_upload(io.BytesIO(b'private fictional original'), 26, 'private.txt')
        task = reading('submit', task, work_text='家长先保存的虚构作品', attachments=[shared_file['id']])
        app.save_record(dict(child='示例星星', day='2026-09-08', category='家长观察', title='PARENT_RECORD_PRIVATE_CANARY',
                             note='PRIVATE_NOTE_CANARY', attachments=[private_file['id']]))
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(path, obj=None, session=None, csrf=True, body=None, headers=None):
            values = dict(headers or {})
            if session:
                values['Cookie'] = session['cookie']
                if csrf:
                    values['X-Child-CSRF'] = session['csrf']
            if obj is not None:
                body = json.dumps(obj, ensure_ascii=False).encode()
                values.setdefault('Content-Type', 'application/json')
            method = 'POST' if body is not None else 'GET'
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            connection.request(method, path, body, values)
            response = connection.getresponse()
            raw = response.read()
            info = dict(response.getheaders())
            status = response.status
            connection.close()
            result = json.loads(raw) if info.get('Content-Type', '').startswith('application/json') else raw
            return status, result, info
        def login(ident):
            invitation = child.parent_action(app, 'invite', {'child_id': ident})
            assert invitation['entry_url'] == 'https://example.invalid/family/child/'
            with app.connect() as c:
                assert not c.execute('SELECT 1 FROM child_invites WHERE hash=?', (invitation['invite'],)).fetchone()
                assert c.execute('SELECT 1 FROM child_invites WHERE hash=?', (child._digest(invitation['invite']),)).fetchone()
            status, state, headers = request('/child/api/login', {'invite': invitation['invite']})
            assert status == 200, state
            cookie = headers['Set-Cookie']
            assert all(value in cookie for value in ('HttpOnly', 'Secure', 'SameSite=Strict', 'Path=/child/', 'Max-Age=604800'))
            assert headers['Cache-Control'] == 'no-store' and headers['Referrer-Policy'] == 'no-referrer'
            assert request('/child/api/login', {'invite': invitation['invite']})[0] == 401
            return {'cookie': cookie.split(';', 1)[0], 'csrf': state['csrf']}, state
        try:
            assert request('/child/api/state')[0] == 401
            assert request('/child/')[0] == 200
            assert request('/child/child.js')[0] == 200
            assert request('/child')[0] == 308
            for path in ('/child/api/record', '/child/api/reading/confirm', '/child/api/print/enqueue',
                         '/child/api/child-access/invite', '/child/../api/state', '/child/%2e%2e/api/state'):
                assert request(path, {})[0] == 404
            assert request('/api/child-access/revoke', {'child_id': 'child-1'})[0] == 403
            first, state = login('child-1')
            assert state['tasks'] == [] and state['child'] == {'id': 'child-1', 'name': '示例星星'}
            assert request('/child/upload/' + shared_file['id'], session=first)[0] == 403
            assert request('/child/api/logout', {}, first, csrf=False)[0] == 403
            for headers in ({'X-Family-Token': app.TOKEN}, {'X-Child-CSRF': 'forged'}):
                headers['Cookie'] = first['cookie']
                assert request('/child/api/logout', {}, headers=headers)[0] == 403
            child.parent_action(app, 'share', dict(child_id='child-1', task_id=task['id'], shared=True))
            status, state, _ = request('/child/api/state', session=first)
            assert status == 200 and len(state['tasks']) == 1
            assert set(state) == {'child', 'csrf', 'tasks', 'asr', 'study_enabled', 'today'}
            assert state['study_enabled'] is False
            assert set(state['tasks'][0]) == set(child.TASK_FIELDS) | {'attachments', 'award'}
            serialized = json.dumps(state)
            for hidden in (app.TOKEN, 'CANARY', 'history', 'source_task_id', 'parent_note', other['id'], 'child-2'):
                assert hidden not in serialized, hidden
            assert request('/child/upload/' + shared_file['id'], session=first)[0] == 200
            assert request('/child/upload/' + private_file['id'], session=first)[0] == 403
            second, second_state = login('child-2')
            assert second_state['tasks'] == []
            assert request('/child/upload/' + shared_file['id'], session=second)[0] == 403
            assert request('/child/api/upload', session=first, body=b'<html>bad</html>', headers={'X-File-Name': 'bad.txt'})[0] == 400
            assert request('/child/api/upload', session=first, body=b'x', headers={'Transfer-Encoding': 'chunked', 'X-File-Name': 'x.txt'})[0] == 400
            assert request('/child/api/upload', session=first, body=b'', headers={'Content-Length': str(app.MAX_UPLOAD + 1), 'X-File-Name': 'big.txt'})[0] == 413
            status, result, _ = request('/child/api/upload', session=first, body=b'own fictional work', headers={'X-File-Name': 'work.txt'})
            assert status == 200, result
            owned = result['attachment']['id']
            with app.connect() as c:
                assert c.execute('SELECT child_id FROM reading_uploads WHERE upload_id=?', (owned,)).fetchone()[0] == 'child-1'
            assert request('/child/upload/' + owned, session=first)[0] == 200
            assert request('/child/upload/' + owned, session=second)[0] == 403
            assert request('/child/api/transcribe', {'attachment': owned}, second)[0] == 403
            assert request('/child/api/transcribe', {'attachment': shared_file['id']}, first)[0] == 403
            with patch.object(app, 'transcribe_material', return_value='虚构转写') as transcribe:
                assert request('/child/api/transcribe', {'attachment': owned}, first)[1] == {'text': '虚构转写'}
                transcribe.assert_called_once_with({'attachment': owned})
            payload = dict(id=task['id'], version=task['version'], request_key='synthetic-child-submit-1', work_text='孩子自己的虚构发现', attachments=[owned, shared_file['id']])
            assert request('/child/api/submit', dict(payload, child_id='child-2'), first)[0] == 403
            assert request('/child/api/submit', dict(payload, action='confirm'), first)[0] == 400
            assert request('/child/api/submit', dict(payload, id=other['id']), first)[0] == 403
            assert request('/child/api/submit', dict(payload, attachments=[private_file['id']]), first)[0] == 403
            assert request('/child/api/submit', dict(payload, version=999), first)[0] == 409
            before_records = app.snapshot()['records']
            first_result = request('/child/api/submit', payload, first)
            repeated = request('/child/api/submit', payload, first)
            assert first_result[0] == repeated[0] == 200, first_result
            assert first_result[1] == repeated[1]
            assert first_result[1]['task']['state'] == '待确认' and first_result[1]['task']['award'] is None
            assert 'history' not in first_result[1]['task'] and 'parent_note' not in first_result[1]['task']
            assert request('/child/api/submit', dict(payload, work_text='另一个请求内容'), first)[0] == 409
            assert app.snapshot()['records'] == before_records
            with app.connect() as c:
                assert c.execute('SELECT count(*) FROM reading_awards').fetchone()[0] == 0
                assert c.execute('SELECT count(*) FROM reading_redemptions').fetchone()[0] == 0
                assert c.execute('SELECT count(*) FROM reading_events WHERE request_key=?', (payload['request_key'],)).fetchone()[0] == 1
                assert c.execute('SELECT reason FROM reading_events WHERE request_key=?', (payload['request_key'],)).fetchone()[0] == '通过孩子独立入口提交，内容待家长核对。'
                previous = json.loads(c.execute('SELECT previous FROM reading_events WHERE request_key=?', (payload['request_key'],)).fetchone()[0])
                assert previous['work_text'] == '家长先保存的虚构作品'
            child.parent_action(app, 'share', dict(child_id='child-1', task_id=task['id'], shared=False))
            assert request('/child/api/state', session=first)[1]['tasks'] == []
            assert request('/child/upload/' + shared_file['id'], session=first)[0] == 403
            assert request('/child/upload/' + owned, session=first)[0] == 200
            assert request('/child/api/submit', payload, first)[0] == 403
            child.parent_action(app, 'revoke', {'child_id': 'child-1'})
            assert request('/child/api/state', session=first)[0] == 401
            assert request('/child/upload/' + owned, session=first)[0] == 401
            assert request('/child/api/state', session=second)[0] == 200
            invitation = child.parent_action(app, 'invite', {'child_id': 'child-1'})
            with app.connect() as c:
                c.execute('UPDATE child_invites SET expires=0')
                c.execute('UPDATE child_sessions SET expires=0')
            assert request('/child/api/login', {'invite': invitation['invite']})[0] == 401
            assert request('/child/api/state', session=second)[0] == 401
            invitation = child.parent_action(app, 'invite', {'child_id': 'child-1'})
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: request('/child/api/login', {'invite': invitation['invite']})[0], range(2)))
            assert sorted(responses) == [200, 401], responses
            with patch.dict(os.environ, {'FAMILY_CHILD_PUBLIC_URL': 'https://user:secret@example.invalid/child/'}):
                try:
                    child.parent_action(app, 'invite', {'child_id': 'child-1'})
                    assert False, 'credential-bearing public URL must fail closed'
                except child.ChildError as exc:
                    assert exc.code == 'configuration_error'
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            app.ROOT, app.DATA, app.DB = original
    print('PASS: child sessions, explicit sharing, upload boundaries, replay/revoke/expiry, no parent or reward mutation')


if __name__ == '__main__':
    check()
