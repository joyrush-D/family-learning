"""Isolated synthetic checks for the standalone Agent; no external model or collectors."""
from contextlib import contextmanager, redirect_stdout
import datetime as dt
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import family_agent as agent
import family_review


class AgentTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-agent-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name); self.data = self.root / 'private'; self.data.mkdir()
        (self.root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.app = family_review.load_app(self.root, self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data)
        self.now = dt.datetime(2026, 2, 10, 8, tzinfo=agent.TZ)
        self.source = dict(id='synthetic-group', platform='wechat', child_id='child-1', name='虚构班级', cursor='10', enabled=True)
        self.config()

    def config(self, enabled=True):
        (self.data / 'agent.json').write_text(json.dumps({'enabled': enabled, 'sources': [self.source]}))

    def payload(self, expected='10', cursor='11', message='11', offset=0):
        stamp = (self.now + dt.timedelta(minutes=offset)).isoformat()
        return dict(source_id=self.source['id'], expected_cursor=expected, cursor=cursor,
                    checked_at=stamp, last_message_time=stamp, error='',
                    messages=[dict(id=message, time=stamp, kind='text', sender='示例老师', text='待核对原文：明天带阅读材料。', unread=False)])

    def record(self, note='孩子自述：愿意谈谈阅读。', source='家长记录', care_choice='', care_review_on=''):
        with self.app.connect() as c:
            return c.execute('INSERT INTO records(child,day,category,subject,title,note,source,created,care_choice,care_review_on) VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('示例甲', '2026-02-10', '学习进展', '语文', '待核对原文', note, source, self.now.isoformat(), care_choice, care_review_on)).lastrowid

    def model(self, messages, schema, name, timeout, *, data_path=None):
        self.assertEqual(data_path,self.app.DATA)
        # A model call must not hold a write transaction or make basic operations wait.
        with sqlite3.connect(self.app.DB, timeout=0.1) as c:
            c.execute('BEGIN IMMEDIATE'); c.rollback()
        value = json.loads(messages[-1]['content'])
        return {'proposals': [dict(title_quote='待核对原文', focus='school' if value['mode'] == 'school' else 'listen', due='',
            evidence=[{'ref': value['evidence'][0]['ref'], 'quote': '待核对原文'}])]}

    def test_ingest_allowlist_cas_retry_immutability_and_failure_cursor(self):
        payload = self.payload()
        self.assertEqual(self.store.ingest(payload)['inserted'], 1)
        self.assertTrue(self.store.ingest(payload)['replayed'])
        with self.assertRaises(agent.AgentError) as raised: self.store.ingest(self.payload(cursor='12', message='12'))
        self.assertEqual(raised.exception.code, 'cursor_conflict')
        stale = self.payload(expected='11', offset=1); stale['messages'][0]['text'] = '改写原文'
        with self.assertRaises(agent.AgentError) as raised: self.store.ingest(stale)
        self.assertEqual(raised.exception.code, 'message_conflict')
        unknown = self.payload(expected='11', cursor='12', message='12', offset=1); unknown['source_id'] = 'not-authorized'
        with self.assertRaises(agent.AgentError): self.store.ingest(unknown)
        failure = self.payload(expected='11', offset=1); failure.update(messages=[], error='token=PRIVATE-SECRET /Users/private/path')
        self.store.ingest(failure)
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot['sources'][0]['cursor'], '11')
        self.assertEqual(snapshot['sources'][0]['last_success'], payload['checked_at'])
        self.assertNotIn('PRIVATE-SECRET', json.dumps(snapshot))
        self.assertNotIn('/Users/private/path', json.dumps(snapshot))
        empty = self.payload(expected='11', cursor='12', offset=2); empty['messages'] = []
        with self.assertRaises(agent.AgentError): self.store.ingest(empty)
        self.source['child_id'] = 'child-2'; self.config()
        with self.assertRaises(agent.AgentError) as raised: self.store.collector_plan()
        self.assertEqual(raised.exception.code, 'source_binding_conflict')

    def test_worker_model_failure_backoff_dedup_corrected_input_and_idempotent_accept(self):
        self.store.ingest(self.payload()); ident = self.record()
        with patch.object(agent.family_llm, '_chat_json', side_effect=agent.family_llm.LLMUnavailable('offline')) as model:
            failed = agent.run_once(self.app, self.now)
            self.assertEqual(failed['failed'], 2)
            self.assertEqual(model.call_count, 2)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
            self.assertEqual(model.call_count, 2)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model) as model:
            done = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
            self.assertEqual(done['created'], 2)
            self.assertEqual(model.call_count, 2)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
            self.assertEqual(model.call_count, 2)
            items = self.store.snapshot()['items']; school = next(row for row in items if row['kind'] == 'school')
            accepted = self.store.act(dict(id=school['id'], action='accept', title='家长核对后的准备', due='2026-02-12', body='按核对后的材料准备'))
            replay = self.store.act(dict(id=school['id'], action='accept', title='迟到的不同内容'))
            self.assertEqual(accepted, replay)
            with self.app.connect() as c:
                task = dict(c.execute('SELECT * FROM manual_tasks').fetchone())
                self.assertEqual(task['title'], '家长核对后的准备')
                self.assertLessEqual(len(task['id']), 30)
                self.assertIn('message:synthetic-group:11', task['source'])
                self.assertIn('待核对原文', task['source'])
                c.execute('UPDATE records SET note=? WHERE id=?', ('更正：当时是家长观察，孩子的意愿未询问。', ident))
            changed = agent.run_once(self.app, self.now + dt.timedelta(minutes=8))
            self.assertEqual(changed['created'], 1)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=9))
            self.assertEqual(model.call_count, 3)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        for item in self.store.snapshot()['items']:
            self.assertNotIn('score', item); self.assertNotIn('已完成', item['body'])
            self.assertIn(item['body'], agent.FOCUS.values())

    def test_revocation_before_ingest_write_rejects_inflight_batch(self):
        self.source['id'] = '100000001@chatroom'
        settings = self.app.settings_store()
        original_db = self.store._db
        for disable_agent in (True, False):
            self.config()

            @contextmanager
            def revoked_before_write():
                state = settings.snapshot()
                rows = [{key: source[key] for key in ['id', 'platform', 'child_id', 'name', 'enabled']}
                        for source in state['sources']]
                if not disable_agent: rows[0]['enabled'] = False
                settings.save_sources(dict(revision=state['revision'], enabled=not disable_agent, sources=rows))
                with original_db() as connection:
                    yield connection

            with patch.object(self.store, '_db', revoked_before_write):
                with self.assertRaises(agent.AgentError) as raised:
                    self.store.ingest(self.payload())
            self.assertEqual(raised.exception.code, 'source_disabled')
            with self.app.connect() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM agent_messages').fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT cursor FROM agent_sources').fetchone()[0], '10')

    def test_retry_limit_and_forged_evidence_never_create_a_fact(self):
        self.record()
        bad = {'proposals': [dict(title_quote='提高20分', focus='compare', due='', evidence=[{'ref': 'record:1', 'quote': '提高20分'}])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=bad) as model:
            for minutes in [0, 6, 17, 30]: agent.run_once(self.app, self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(model.call_count, 3)
        self.assertEqual(self.store.snapshot()['failed_jobs'], 1)
        self.assertEqual(self.store.snapshot()['pending_count'], 0)
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model):
            # Recovery proceeds without a parent or Codex retry request.
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=41))['created'], 1)
        self.store.act({'action': 'retry'})

    def test_due_review_offline_declined_deferred_and_feedback_correction(self):
        care = dict(id='synthetic-care', child='示例甲', topic='阅读', title='讨论一次阅读', evidence='虚构记录，仅为回看依据。',
                    action='一起谈谈孩子想讨论的内容。', review_on='2026-02-10', expires_on='2026-02-20')
        (self.data / '陪伴建议.json').write_text(json.dumps([care]))
        state = self.data / '陪伴提醒状态.json'; state.write_text('{}')
        with patch.object(agent.family_llm, '_chat_json', side_effect=AssertionError('due checks do not need a model')):
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 0)
            self.assertEqual(self.store.snapshot()['items'][0]['care_id'], care['id'])
            state.write_text(json.dumps({care['id']: {'status': 'declined'}}))
            agent.run_once(self.app, self.now)
            self.assertEqual(self.store.snapshot()['pending_count'], 0)
            feedback = self.record(note='只补充一次观察，不恢复原计划。', source='陪伴建议:' + care['id'], care_choice='暂不考虑')
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            item = self.store.snapshot()['items'][0]
            self.assertIn('不恢复原建议', item['body'])
            self.assertEqual(item['record_id'], feedback)
            self.store.act(dict(id=item['id'], action='dismiss'))
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 0)
            with self.app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?', ('更正当时观察的情境。', feedback))
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 0)
            # A newer explicit deferral hides the due prompt; textual feedback may still be checked.
            self.record(note='', source='陪伴建议:' + care['id'], care_choice='改天回看', care_review_on='2026-02-15')
            agent.run_once(self.app, self.now)
            self.assertIn('不恢复原建议', self.store.snapshot()['items'][0]['body'])
            with self.app.connect() as c: c.execute('UPDATE records SET note=?', ('',))
            agent.run_once(self.app, self.now)
            self.assertEqual(self.store.snapshot()['pending_count'], 0)
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=5))['created'], 1)

    def test_backed_off_batch_does_not_block_new_messages_and_quotes_keep_newlines(self):
        payload = self.payload(cursor='23')
        payload['messages'] = [{**payload['messages'][0], 'id': str(ident)} for ident in range(11, 24)]
        self.store.ingest(payload)
        with patch.object(agent.family_llm, '_chat_json', side_effect=agent.family_llm.LLMUnavailable('offline')):
            agent.run_once(self.app, self.now)
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model):
            result = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual(result['processed'], 1)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages WHERE processed=0').fetchone()[0], 12)
        excerpt = '学校通知\n请带“阅读材料”'
        output = {'proposals': [dict(title_quote='请带“阅读材料”', focus='school', due='', evidence=[{'ref': 'message:synthetic:1', 'quote': excerpt}])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=output):
            items = agent._select('school', [{'ref': 'message:synthetic:1', 'text': excerpt}])
        self.assertEqual(items[0]['evidence'][0]['text'], excerpt)

    def test_unread_media_remains_visible_after_processing_and_replay(self):
        payload = self.payload(); payload['messages'][0].update(kind='image', text='图片原件未读', unread=True)
        self.store.ingest(payload); self.store.ingest(payload)
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': []}):
            self.assertEqual(agent.run_once(self.app, self.now)['processed'], 1)
        self.assertEqual(self.store.snapshot()['sources'][0]['unread_count'], 1)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0], 1)

    def test_older_record_correction_and_invalid_model_type(self):
        old_id = self.record()
        # More recent care feedback must not permanently hide the older learning record.
        for _ in range(201): self.record(note='', source='陪伴建议:synthetic-other')
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model):
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            with self.app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?', ('更正旧观察。', old_id))
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
        self.record()
        bad = {'proposals': [dict(title_quote='待核对原文', focus=[], due='', evidence=[])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=bad):
            self.assertEqual(agent.run_once(self.app, self.now)['state'], 'needs_attention')

    def test_title_uses_cited_record_or_verified_excerpt_not_model_claim(self):
        evidence = [{'ref': 'record:1', 'text': 'title: 一次虚构阅读\nnote: 孩子说这段不太明白。'}]
        proposal = dict(title_quote='一次虚构阅读', focus='clarify', due='',
                        evidence=[{'ref': 'record:1', 'quote': '孩子说这段不太明白。'}])
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [proposal]}):
            self.assertEqual(agent._select('learning', evidence)[0]['title'], '待核对：一次虚构阅读')
        proposal['title_quote'] = '已经完全掌握并提高20分'
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [proposal]}):
            item = agent._select('learning', evidence)[0]
        self.assertEqual(item['title'], '待核对：孩子说这段不太明白。')
        self.assertNotIn('提高20分', json.dumps(item, ensure_ascii=False))
        proposal['evidence'][0]['ref'] = 'record:unprovided'
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [proposal]}):
            with self.assertRaises(agent.AgentError): agent._select('learning', evidence)

    def test_nonoverlap_crash_release_and_disabled_cli(self):
        with agent._lock(self.data / '.agent.lock') as locked:
            self.assertTrue(locked)
            self.assertEqual(agent.run_once(self.app, self.now)['state'], 'already_running')
        self.assertEqual(agent.run_once(self.app, self.now)['state'], 'ready')
        self.config(False); output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(agent.main(['--once', '--root', str(self.root), '--data', str(self.data)]), 0)
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
