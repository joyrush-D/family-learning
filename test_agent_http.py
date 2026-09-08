"""Synthetic real-HTTP Agent integration; no family data, model or message CLI calls."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

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
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.parent = {'X-Family-Token':app.TOKEN}

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.model.stop(); self.env.stop(); self.paths.stop(); self.temp.cleanup()

    def write_config(self, config):
        path = app.DATA/'agent.json'
        path.write_text(json.dumps(config, ensure_ascii=False)); path.chmod(0o600)

    def request(self, method, path, obj=None, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode() if obj is not None else None
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
