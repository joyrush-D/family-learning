"""Synthetic real-HTTP Agent integration; no family data, model or message CLI calls."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote, urlencode

import app


class AgentHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-agent-http-')
        root = Path(self.temp.name); private = root / 'private'; private.mkdir()
        (root / '家庭运行规则.md').write_text('| child-1 | 示例星星 | 男 | 10岁 | 四年级 |\n| child-2 | 示例月亮 | 男 | 13岁 | 初一 |\n')
        for name in ('消息来源.md', '学习与成长.md', '跟踪台账.md'):
            (root / name).write_text('SYNTHETIC_PARENT_ONLY')
        (root / 'index.html').write_text('<h1>Synthetic family application</h1>')
        self.paths = patch.multiple(app, ROOT=root, DATA=private, DB=private/'family.sqlite3')
        self.paths.start()
        self.env = patch.dict(app.os.environ, {'FAMILY_HOST':'family.example.invalid',
            'FAMILY_USER':'parent@example.invalid', 'FAMILY_CHILD_COOKIE_PATH':'/child/'})
        self.env.start()
        self.model = patch.object(app.family_llm, '_chat_json', side_effect=AssertionError('HTTP state/action must not call a model'))
        self.model_mock = self.model.start()
        app.connect().close()
        self.source = dict(id='synthetic@chatroom', platform='wechat', child_id='child-1',
                           name='虚构授权班级群', cursor='100', enabled=True)
        self.config = dict(enabled=True, sources=[self.source])
        self.write_config(self.config)
        self.start_server()
        self.parent = {'X-Family-Token':app.TOKEN}

    def start_server(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.model.stop(); self.env.stop(); self.paths.stop(); self.temp.cleanup()

    def write_config(self, config):
        path = app.DATA/'agent.json'
        path.write_text(json.dumps(config, ensure_ascii=False)); path.chmod(0o600)

    def request(self, method, path, obj=None, headers=None):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode() if obj is not None else None
        headers = dict(headers or {})
        if obj is not None: headers.setdefault('Content-Type', 'application/json')
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse(); raw = response.read(); info = dict(response.getheaders())
            result = json.loads(raw) if info.get('Content-Type', '').startswith('application/json') else raw
            return response.status, result, info
        finally:
            connection.close()

    def post(self, path, obj, headers=None):
        return self.request('POST', path, obj, self.parent if headers is None else headers)

    def batch(self, count=1):
        messages = [dict(id=str(101+i), time='2026-02-10T08:00:00+08:00', kind='text',
            sender='虚构老师', text='虚构学校通知。' * 60, unread=False) for i in range(count)]
        return dict(source_id=self.source['id'], expected_cursor='100', cursor=str(100+count),
                    checked_at='2026-02-10T08:05:00+08:00', last_message_time='2026-02-10T08:00:00+08:00',
                    messages=messages, error='')

    def message_keys(self, **changes):
        return dict(child_id='child-1', source_id=self.source['id'], message_id='101') | changes

    def message_get(self, keys=None, headers=None):
        return self.request('GET', '/api/agent/message?' + urlencode(self.message_keys() if keys is None else keys), headers=headers)

    def upload(self, *, headers=None, path='/api/upload'):
        data = '虚构学校原件，仅供隔离测试。'.encode()
        status, result, _ = self.request('POST', path, data,
            (self.parent if headers is None else headers) | {'Content-Type':'text/plain', 'X-File-Name':quote('虚构 中文原件.txt')})
        self.assertEqual(status, 200, result)
        return result['attachment'], data

    def link(self, attachment, action='attach', keys=None):
        return self.post('/api/agent/message/attachment',
            (self.message_keys() if keys is None else keys) | {'attachment_id':attachment['id'], 'action':action})

    def child_headers(self, child_id):
        invitation = app.family_child.parent_action(app, 'invite', {'child_id':child_id})
        status, child, headers = self.post('/child/api/login', {'invite':invitation['invite']}, {})
        self.assertEqual(status, 200, child)
        return {'Cookie':headers['Set-Cookie'].split(';',1)[0], 'X-Child-CSRF':child['csrf']}

    def second_source(self):
        second = dict(self.source, id='synthetic:second@chatroom', child_id='child-2')
        self.config['sources'].append(second); self.write_config(self.config)
        batch = self.batch(); batch['source_id'] = second['id']
        self.assertEqual(self.post('/api/agent/ingest', batch)[0], 200)
        return self.message_keys(child_id='child-2', source_id=second['id'])

    def test_message_attachment_round_trip_and_reopen_preserve_original_facts(self):
        batch = self.batch(); batch['messages'][0].update(kind='image', text='[图片]', unread=True)
        self.assertEqual(self.post('/api/agent/ingest', batch)[0], 200)
        with app.connect() as db:
            before = [tuple(row) for row in db.execute('SELECT * FROM agent_messages')]
            source_before = [tuple(row) for row in db.execute('SELECT * FROM agent_sources')]
        attachment, data = self.upload()
        status, empty, _ = self.message_get()
        self.assertEqual(status, 200, empty); self.assertEqual(empty['attachments'], [])
        self.assertEqual(empty['unavailable_attachment_ids'], [])
        for _ in range(2):
            status, view, _ = self.link(attachment)
            self.assertEqual(status, 200, view); self.assertEqual(view['attachments'], [attachment])
            self.assertEqual(view['message'], batch['messages'][0])
            self.assertEqual(view['source_name'], self.source['name'])
        self.assertEqual(self.request('GET', '/api/agent')[1]['linked_upload_ids'], [attachment['id']])
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.start_server()  # Recreate the HTTP handler/store against the same isolated DB and uploads.
        self.assertEqual(self.message_get()[1], view)
        self.assertEqual(self.request('GET', attachment['url'])[1], data)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_message_attachments').fetchone()[0], 1)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM agent_messages')], before)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM agent_sources')], source_before)
            for table in ('records', 'manual_tasks', 'agent_items', 'agent_jobs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)
        for _ in range(2):
            status, detached, _ = self.link(attachment, 'detach')
            self.assertEqual(status, 200, detached); self.assertEqual(detached['attachments'], [])
        self.assertEqual(self.request('GET', '/api/agent')[1]['linked_upload_ids'], [])
        self.assertEqual(self.request('GET', attachment['url'])[1], data)
        self.assertEqual(self.post('/api/agent/ingest', batch)[1]['replayed'], True)
        self.model_mock.assert_not_called()

    def test_message_arguments_binding_and_disabled_history(self):
        batch = self.batch(); batch['messages'][0]['id'] = 'part:101:source@id'
        self.assertEqual(self.post('/api/agent/ingest', batch)[0], 200)
        keys = self.message_keys(message_id=batch['messages'][0]['id'])
        attachment, _ = self.upload()
        self.assertEqual(self.link(attachment, keys=keys)[0], 200)
        self.config['enabled'] = False; self.source['enabled'] = False; self.write_config(self.config)
        self.assertEqual(self.message_get(keys)[0], 200)
        self.assertEqual(self.request('GET', '/api/agent')[1]['linked_upload_ids'], [attachment['id']])
        self.assertEqual(self.link(attachment, 'detach', keys)[0], 200)
        self.assertEqual(self.link(attachment, keys=keys)[0], 200)
        for changes, expected in [({'child_id':'child-2'}, 403), ({'child_id':'missing'}, 404),
                                  ({'source_id':'missing'}, 403), ({'message_id':'missing'}, 404),
                                  ({'message_id':'../101'}, 400), ({'message_id':''}, 400),
                                  ({'extra':'field'}, 400)]:
            self.assertEqual(self.message_get(keys | changes)[0], expected, changes)
            self.assertEqual(self.link(attachment, keys=keys | changes)[0], expected, changes)
        for key in keys:
            self.assertEqual(self.message_get({k:v for k,v in keys.items() if k!=key})[0], 400)
        duplicate = '/api/agent/message?' + urlencode(keys) + '&child_id=child-1'
        self.assertEqual(self.request('GET', duplicate)[0], 400)
        for changes in ({'action':'delete'}, {'action':[]}, {'attachment_id':'../file'}, {'extra':'field'}):
            body = keys | {'attachment_id':attachment['id'], 'action':'attach'} | changes
            self.assertEqual(self.post('/api/agent/message/attachment', body)[0], 400, changes)
        self.source['child_id'] = 'child-2'; self.write_config(self.config)
        status, error, _ = self.message_get(keys | {'child_id':'child-2'})
        self.assertEqual(status, 409); self.assertEqual(error['code'], 'source_binding_conflict')
        self.assertEqual(self.request('GET', '/api/agent')[1]['linked_upload_ids'], [])
        self.config['sources'] = []; self.write_config(self.config)
        self.assertEqual(self.message_get(keys)[0], 403)

    def test_message_attachment_validates_files_and_can_detach_broken_links(self):
        self.assertEqual(self.post('/api/agent/ingest', self.batch())[0], 200)
        self.assertEqual(self.link({'id':'0'*32})[0], 404)
        for failure in ('missing', 'size', 'symlink', 'metadata'):
            attachment, original = self.upload(); ident = attachment['id']
            self.assertEqual(self.link(attachment)[0], 200)
            path = app.DATA / 'uploads' / ident
            if failure == 'missing': path.unlink()
            elif failure == 'size': path.write_bytes(b'short')
            elif failure == 'symlink':
                path.unlink(); target = app.DATA / 'synthetic-target.txt'; target.write_bytes(original); path.symlink_to(target)
            else:
                with app.connect() as db: db.execute('DELETE FROM uploads WHERE id=?', (ident,))
            unreadable = self.message_get()[1]
            self.assertEqual(unreadable['attachments'], [], failure)
            self.assertEqual(unreadable['unavailable_attachment_ids'], [ident], failure)
            self.assertNotIn(attachment['name'], json.dumps(unreadable))
            self.assertEqual(self.request('GET', '/api/agent')[1]['linked_upload_ids'], [], failure)
            self.assertEqual(self.link(attachment)[0], 404, failure)
            status, detached, _ = self.link(attachment, 'detach')
            self.assertEqual(status, 200, failure)
            self.assertEqual(detached['unavailable_attachment_ids'], [])
            with app.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM agent_message_attachments').fetchone()[0], 0)
            if failure != 'missing': self.assertTrue(path.exists())

    def test_message_attachments_keep_parent_reuse_and_child_ownership_boundaries(self):
        self.assertEqual(self.post('/api/agent/ingest', self.batch())[0], 200)
        second_keys = self.second_source()
        generic, _ = self.upload()
        for keys in (self.message_keys(), second_keys):
            self.assertEqual(self.link(generic, keys=keys)[0], 200)
        child1 = self.child_headers('child-1'); child2 = self.child_headers('child-2')
        for headers in (child1, child2):
            self.assertEqual(self.request('GET', '/child/upload/'+generic['id'], headers=headers)[0], 403)
            state = self.request('GET', '/child/api/state', headers=headers)[1]
            self.assertNotIn(generic['id'], json.dumps(state)); self.assertNotIn('agent', state)
        private, _ = self.upload(headers=child2, path='/child/api/upload')
        self.assertEqual(self.link(private)[0], 403)
        self.assertEqual(self.link(private, keys=second_keys)[0], 200)
        self.assertEqual(self.request('GET', '/child/upload/'+private['id'], headers=child1)[0], 403)
        with app.connect() as db:
            self.assertIsNone(db.execute('SELECT child_id FROM reading_uploads WHERE upload_id=?', (generic['id'],)).fetchone())
        # The existing reading/guided path may later claim generic parent material.
        app.save_record(dict(child='示例月亮', day='2026-02-10', category='学习进展', title='虚构记录', attachments=[generic['id']]))
        with app.connect() as db:
            db.execute('INSERT INTO reading_uploads VALUES (?,?)', (generic['id'], 'child-2'))
        self.assertEqual(self.message_get()[1]['attachments'], [])
        self.assertEqual(self.message_get()[1]['unavailable_attachment_ids'], [generic['id']])
        self.assertEqual(self.link(generic)[0], 403)
        status, detached, _ = self.link(generic, 'detach')
        self.assertEqual(status, 200); self.assertEqual(detached['unavailable_attachment_ids'], [])
        readable = self.message_get(second_keys)[1]['attachments']
        self.assertEqual({row['id'] for row in readable}, {generic['id'], private['id']})
        self.assertEqual(set(self.request('GET', '/api/agent')[1]['linked_upload_ids']), {generic['id'], private['id']})
        self.assertTrue((app.DATA/'uploads'/generic['id']).is_file())
        self.model_mock.assert_not_called()

    def test_message_attachment_endpoints_are_parent_only(self):
        self.assertEqual(self.post('/api/agent/ingest', self.batch())[0], 200)
        attachment, _ = self.upload()
        child = self.child_headers('child-1')
        body = self.message_keys() | {'attachment_id':attachment['id'], 'action':'attach'}
        for headers in ({}, {'X-Family-Token':'wrong'}, child, self.parent | {'Host':'untrusted.invalid'}):
            self.assertEqual(self.post('/api/agent/message/attachment', body, headers)[0], 403)
        untrusted = child | {'Host':'family.example.invalid'}
        self.assertEqual(self.message_get(headers=untrusted)[0], 403)
        trusted = {'Host':'family.example.invalid', 'Tailscale-User-Login':'parent@example.invalid'}
        self.assertEqual(self.message_get(headers=trusted)[0], 200)
        self.assertEqual(self.request('GET', '/child/api/agent/message?'+urlencode(self.message_keys()), headers=child)[0], 404)
        self.assertEqual(self.post('/child/api/agent/message/attachment', body, child | self.parent)[0], 404)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_message_attachments').fetchone()[0], 0)

    def proposal(self, kind='school', child_id='child-1'):
        store = app.agent_store(); now = app.family_agent._now(); key = 'synthetic-'+kind+'-'+child_id
        fingerprint = store._job(key, {'synthetic':key}, now)
        store._save(key, fingerprint, [dict(child_id=child_id, kind=kind, title='虚构待核对通知',
            body='核对虚构活动是否参加', evidence=[dict(ref='synthetic:1', text='虚构活动')], due='2026-02-12')], now)
        return next(item for item in store.snapshot()['items'] if item['child_id']==child_id and item['kind']==kind)

    def test_authorized_large_batch_replay_and_cursor_compare(self):
        status, plan, headers = self.request('GET', '/api/agent/collector')
        self.assertEqual(status, 200); self.assertEqual(plan['sources'][0]['cursor'], '100')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        batch = self.batch(200)
        self.assertGreater(len(json.dumps(batch, ensure_ascii=False).encode()), 20000)
        status, result, _ = self.post('/api/agent/ingest', batch)
        self.assertEqual(status, 200, result); self.assertEqual(result['inserted'], 200)
        status, replay, _ = self.post('/api/agent/ingest', batch)
        self.assertEqual(status, 200); self.assertTrue(replay['replayed']); self.assertEqual(replay['inserted'], 0)
        self.assertEqual(self.request('GET', '/api/agent/collector')[1]['sources'][0]['cursor'], '300')
        status, result, _ = self.post('/api/agent/ingest', self.batch())
        self.assertEqual(status, 409); self.assertEqual(result['code'], 'cursor_conflict')
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_messages').fetchone()[0], 200)
            self.assertEqual(db.execute('SELECT count(*) FROM records').fetchone()[0], 0)
        self.model_mock.assert_not_called()

    def test_authorization_and_body_limits_fail_before_ingest(self):
        batch = self.batch()
        for headers in ({}, {'X-Family-Token':'wrong'}, self.parent | {'Host':'untrusted.invalid'}):
            self.assertEqual(self.post('/api/agent/ingest', batch, headers)[0], 403)
            self.assertEqual(self.post('/api/agent/action', {'action':'retry'}, headers)[0], 403)
        for path in ('/api/agent', '/api/agent/collector', '/api/state'):
            self.assertEqual(self.request('GET', path, headers={'Host':'family.example.invalid'})[0], 403)
            trusted = {'Host':'family.example.invalid', 'Tailscale-User-Login':'parent@example.invalid'}
            self.assertEqual(self.request('GET', path, headers=trusted)[0], 200)
        self.assertEqual(self.post('/api/agent/ingest', batch | {'source_id':'unapproved@chatroom'})[0], 403)
        self.assertEqual(self.post('/api/agent/ingest', batch | {'child_id':'child-2'})[0], 400)
        for payload, headers in (({}, self.parent | {'Content-Length':str(2*1024*1024+1)}),
                                 (batch, self.parent | {'Transfer-Encoding':'chunked'})):
            self.assertEqual(self.post('/api/agent/ingest', payload, headers)[0], 400)
        self.assertEqual(self.post('/api/agent/action', {'action':'retry', 'body':'x'*20000})[0], 400)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_messages').fetchone()[0], 0)

    def test_parent_action_idempotency_child_binding_and_no_fabricated_completion(self):
        item = self.proposal()
        payload = dict(id=item['id'], action='accept', title='家长核对后的虚构事项', due='2026-02-13', action_text='虚构准备内容')
        self.assertEqual(self.post('/api/agent/action', payload | {'child_id':'child-2'})[0], 400)
        status, first, _ = self.post('/api/agent/action', payload)
        self.assertEqual(status, 200, first)
        self.assertEqual(self.post('/api/agent/action', payload)[1], first)
        self.assertEqual(self.post('/api/agent/action', dict(id=item['id'], action='dismiss'))[0], 409)
        state = self.request('GET', '/api/state')[1]
        tasks = [task for task in state['tasks'] if task['id']==first['task_id']]
        self.assertEqual(len(tasks), 1); self.assertEqual(tasks[0]['child'], '示例星星')
        self.assertEqual(tasks[0]['title'], payload['title']); self.assertEqual(tasks[0]['action'], payload['action_text'])
        self.assertIn('synthetic:1', tasks[0]['source']); self.assertIn('虚构活动', tasks[0]['source'])
        self.assertEqual(tasks[0]['original_status'], '待跟进'); self.assertIsNone(tasks[0]['update'])
        learning = self.proposal('learning', 'child-2')
        self.assertEqual(self.post('/api/agent/action', dict(id=learning['id'], action='accept'))[0], 400)
        action = dict(id=learning['id'], action='dismiss')
        self.assertEqual(self.post('/api/agent/action', action)[0], 200)
        self.assertEqual(self.post('/api/agent/action', action)[0], 200)
        self.assertEqual(state['records'], []); self.model_mock.assert_not_called()

    def test_child_session_cannot_read_or_modify_agent(self):
        self.proposal(child_id='child-2')
        invitation = app.family_child.parent_action(app, 'invite', {'child_id':'child-1'})
        status, child, headers = self.post('/child/api/login', {'invite':invitation['invite']}, {})
        self.assertEqual(status, 200, child)
        child_headers = {'Cookie':headers['Set-Cookie'].split(';',1)[0], 'X-Child-CSRF':child['csrf']}
        status, state, _ = self.request('GET', '/child/api/state', headers=child_headers)
        self.assertEqual(status, 200); self.assertNotIn('agent', state)
        self.assertNotIn('SYNTHETIC_PARENT_ONLY', json.dumps(state)); self.assertNotIn('child-2', json.dumps(state))
        for path in ('/child/api/agent', '/child/api/agent/collector', '/child/../api/agent'):
            self.assertEqual(self.request('GET', path, headers=child_headers)[0], 404)
        for path in ('/child/api/agent/ingest', '/child/api/agent/action'):
            self.assertEqual(self.post(path, self.batch(), child_headers | self.parent)[0], 404)
        self.assertEqual(self.post('/api/agent/action', {'action':'retry'}, child_headers)[0], 403)
        self.assertEqual(self.post('/api/agent/ingest', self.batch(), child_headers)[0], 403)

    def test_bad_config_isolated_and_state_does_not_run_agent(self):
        app.save_record(dict(child='示例星星', day='2026-02-10', category='学习进展', title='虚构已保存记录'))
        before = self.request('GET', '/api/state')[1]
        for raw in ('{broken', '[]', '{"enabled":true,"sources":[{}]}'):
            (app.DATA/'agent.json').write_text(raw)
            status, state, _ = self.request('GET', '/api/state')
            self.assertEqual(status, 200); self.assertEqual(state['records'], before['records'])
            self.assertEqual(state['agent']['state'], 'error'); self.assertFalse(state['agent']['enabled'])
            self.assertTrue(state['agent']['last_error']); self.assertEqual(self.request('GET', '/')[0], 200)
            self.assertEqual(self.request('GET', '/api/agent/collector')[0], 409)
        self.write_config(self.config)
        self.assertEqual(self.request('GET', '/api/state')[1]['agent']['state'], 'waiting')
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_runtime').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM agent_jobs').fetchone()[0], 0)
        self.model_mock.assert_not_called()


if __name__=='__main__': unittest.main()
