"""Isolated synthetic checks for the standalone Agent; no external model or collectors."""
from contextlib import contextmanager, redirect_stdout
import datetime as dt
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
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
        self.assertEqual(value['as_of'], self.now.astimezone(agent.TZ).date().isoformat())
        if name == 'family_agent_plan':
            quote = value['evidence'][0]['text'][:40]
            return {'proposal': dict(title='回看这次阅读', goal='能说出一次实际想法', action='一起说一说这次阅读中最想保留的一点。',
                why_now='这条记录保留了本次实际表达。', estimated_minutes=10, review_on=value['as_of'],
                evidence=[{'ref': value['evidence'][0]['ref'], 'quote': quote}])}
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
            if item['kind'] == 'school': self.assertIn(item['body'], agent.FOCUS.values())

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

    def test_retry_limit_stops_same_fingerprint_until_manual_or_new_input(self):
        self.record()
        bad = {'proposal': {'title': '提高20分', 'goal': 'x', 'action': 'x', 'why_now': 'x',
                            'estimated_minutes': 10, 'review_on': '2026-02-10',
                            'evidence': [{'ref': 'record:1', 'quote': '提高20分'}]}}
        with patch.object(agent.family_llm, '_chat_json', return_value=bad) as model:
            for minutes in [0, 6, 17]: agent.run_once(self.app, self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(model.call_count, 3)
            # Each tick creates a fresh Store; a reopened process must still honor the cap.
            reopened = agent.Store(self.app.connect, self.app.profiles, self.data)
            self.assertEqual(reopened.snapshot()['failed_jobs'], 1)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=41))
            self.assertEqual(model.call_count, 3)
            self.assertIn('自动尝试上限', reopened.snapshot()['last_error'])
        with self.app.connect() as c:
            job = dict(c.execute('SELECT * FROM agent_jobs').fetchone())
            self.assertEqual(job['attempts'], agent.MAX_ATTEMPTS)
            self.assertIn('达到自动重试上限', job['error'])
            self.assertIn('人工重试', job['error'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT note FROM records WHERE id=1').fetchone()[0], '孩子自述：愿意谈谈阅读。')
        self.assertEqual(self.store.snapshot()['failed_jobs'], 1)
        self.assertEqual(self.store.snapshot()['pending_count'], 0)
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model):
            self.store.act({'action': 'retry'})
            # A failure finishing after the parent's retry must not consume the restored budget.
            self.store._fail('record:1', self.now + dt.timedelta(minutes=41), fingerprint=job['fingerprint'])
            with self.app.connect() as c:
                self.assertEqual(dict(c.execute('SELECT attempts,error FROM agent_jobs WHERE id=?', ('record:1',)).fetchone()),
                                 {'attempts': 0, 'error': ''})
            # Manual retry is the explicit recovery path for the same fingerprint.
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=41))['created'], 1)
        self.store._fail('record:1', self.now + dt.timedelta(minutes=41), fingerprint=job['fingerprint'])
        self.store.act({'action': 'retry'})
        with self.app.connect() as c:
            self.assertEqual(dict(c.execute('SELECT attempts,done,error FROM agent_jobs WHERE id=?', ('record:1',)).fetchone()),
                             {'attempts': 1, 'done': 1, 'error': ''})
        with self.app.connect() as c:
            c.execute('UPDATE records SET note=? WHERE id=1', ('更正后的虚构观察。',))
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model) as model:
            # A changed source fingerprint gets a fresh automatic attempt budget.
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=42))['created'], 1)
            self.assertEqual(model.call_count, 1)

    def test_retry_limit_survives_process_exit_after_model_starts(self):
        self.record()
        marker = self.data / 'synthetic-model-calls'
        script = '''
import datetime as dt
import os
from pathlib import Path
import sys
import family_agent
import family_review

root, data, marker = map(Path, sys.argv[1:])
app = family_review.load_app(root, data)
def exit_during_model(*args, **kwargs):
    with marker.open('a') as stream:
        stream.write('call\\n')
        stream.flush()
        os.fsync(stream.fileno())
    os._exit(17)
family_agent._plan_learning = exit_during_model
family_agent.run_once(app, dt.datetime(2026, 2, 10, 8, tzinfo=family_agent.TZ))
'''
        commands = [[sys.executable, '-c', script, str(self.root), str(self.data), str(marker)] for _ in range(4)]
        results = [subprocess.run(command, cwd=Path(__file__).resolve().parent, timeout=10) for command in commands]
        self.assertEqual([result.returncode for result in results], [17, 17, 17, 0])
        self.assertEqual(marker.read_text().splitlines(), ['call'] * agent.MAX_ATTEMPTS)
        with self.app.connect() as c:
            job = dict(c.execute('SELECT attempts,done FROM agent_jobs WHERE id=?', ('record:1',)).fetchone())
        self.assertEqual(job, {'attempts': agent.MAX_ATTEMPTS, 'done': 0})

    def test_due_review_offline_declined_deferred_and_feedback_correction(self):
        care = dict(id='synthetic-care', child='示例甲', topic='阅读', title='讨论一次阅读', evidence='虚构记录，仅为回看依据。',
                    action='一起谈谈孩子想讨论的内容。', review_on='2026-02-10', expires_on='2026-02-20')
        (self.data / '陪伴建议.json').write_text(json.dumps([care]))
        state = self.data / '陪伴提醒状态.json'; state.write_text('{}')
        with patch.object(agent.family_llm, '_chat_json', side_effect=AssertionError('due checks do not need a model')):
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 0)
            with self.app.connect() as c:
                self.assertEqual(c.execute("SELECT attempts FROM agent_jobs WHERE id LIKE 'review:%'").fetchone()[0], 0)
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

    def test_school_collector_placeholder_requires_explicit_task_details(self):
        for title in ('[图片]', '待核对：[文件]', '[语音]', '[视频]', '[file：内容未读取，仅保留消息说明]'):
            self.assertTrue(agent._needs_task_details(title))
        self.assertFalse(agent._needs_task_details('请核对图片里的要求'))
        fp = self.store._job('placeholder-school', 'placeholder', self.now)
        evidence = [dict(ref='message:synthetic-group:20', text='图片内容尚未读取')]
        placeholder = dict(child_id='child-1', kind='school',
                           title='待核对：[image：内容未读取，仅保留消息说明]',
                           body=agent.FOCUS['school'], evidence=evidence, due='')
        self.store._save('placeholder-school', fp, [placeholder], self.now)
        item = self.store.snapshot()['items'][0]
        self.assertTrue(item['needs_task_details'])
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept'))
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept', title='带齐资料', body=agent.FOCUS['school']))
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept', title='核对资料', body='[图片]'))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
        accepted = self.store.act(dict(id=item['id'], action='accept', title='找老师核对作业要求',
                                       body='先向老师确认图片里的作业要求，再按确认内容安排。'))
        replay = self.store.act(dict(id=item['id'], action='accept', title='另一标题', body='另一动作'))
        self.assertEqual(accepted, replay)
        with self.app.connect() as c:
            task = dict(c.execute('SELECT * FROM manual_tasks').fetchone())
            self.assertEqual(task['title'], '找老师核对作业要求')
            self.assertIn('message:synthetic-group:20', task['source'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 1)

        normal = dict(child_id='child-1', kind='school', title='明天带阅读材料',
                      body=agent.FOCUS['school'], evidence=[dict(ref='message:synthetic-group:21', text='请带阅读材料')], due='')
        fp = self.store._job('normal-school', 'normal', self.now)
        self.store._save('normal-school', fp, [normal], self.now)
        normal_item = next(row for row in self.store.snapshot()['items'] if row['title'] == normal['title'])
        self.assertFalse(normal_item['needs_task_details'])
        self.store.act(dict(id=normal_item['id'], action='accept'))

    def test_qq_placeholders_stay_unknown_until_parent_writes_specific_action(self):
        cases = [
            '[包含未读取的非文字内容]',
            '[已撤回，正文未读取]',
            '[包含未读取的非文字内容]\n[已撤回，正文未读取]',
            '[图片][包含未读取的非文字内容] [已撤回，正文未读取]',
            '[image：内容未读取，仅保留消息说明]',
        ]
        for index, source_text in enumerate(cases):
            self.assertTrue(agent._needs_task_details(source_text), source_text)
        self.assertFalse(agent._needs_task_details('请打印材料\n[包含未读取的非文字内容]'))
        self.assertFalse(agent._needs_task_details('请核对图片里的要求 [已撤回，正文未读取]'))

        # The model may quote a harmless-looking substring, but the complete cited
        # source is still only an unread/recalled placeholder.
        selected = None
        for index, source_text in enumerate(cases):
            ref = 'message:synthetic-group:qq-placeholder-' + str(index)
            quote = '说明' if '说明' in source_text else '未读取'
            result = {'proposals': [dict(title_quote=quote, focus='school', due='',
                                         evidence=[dict(ref=ref, quote=quote)])]}
            with patch.object(agent.family_llm, '_chat_json', return_value=result):
                selected = agent._select('school', [dict(ref=ref, text=source_text)], as_of='2026-02-10')
            self.assertEqual(selected[0]['title'], '待核对：[资料]')
            self.assertEqual(selected[0]['body'], agent.FOCUS['school'])

        fp = self.store._job('qq-placeholder', 'qq-placeholder', self.now)
        self.store._save('qq-placeholder', fp, [dict(child_id='child-1', kind='school',
                           title=selected[0]['title'], body=selected[0]['body'],
                           evidence=selected[0]['evidence'], due='')], self.now)
        item = next(row for row in self.store.snapshot()['items'] if row['title'] == '待核对：[资料]')
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept'))
        accepted = self.store.act(dict(id=item['id'], action='accept',
                                       title='先向老师核对原件',
                                       body='先向老师核对原件，再按确认后的具体要求安排。'))
        self.assertEqual(accepted['state'], 'accepted')
        with self.app.connect() as c:
            task = dict(c.execute('SELECT * FROM manual_tasks').fetchone())
        self.assertEqual(task['title'], '先向老师核对原件')

        normal_text = '请打印材料\n[包含未读取的非文字内容]'
        normal_ref = 'message:synthetic-group:qq-normal'
        normal_result = {'proposals': [dict(title_quote='请打印材料', focus='school', due='',
                                             evidence=[dict(ref=normal_ref, quote='请打印材料')])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=normal_result):
            normal = agent._select('school', [dict(ref=normal_ref, text=normal_text)], as_of='2026-02-10')
        self.assertEqual(normal[0]['title'], '待核对：请打印材料')

    def test_school_history_uses_beijing_date_and_preserves_current_or_uncertain_requirements(self):
        # The caller's UTC date is still September 8; this run is September 9 in China.
        self.now = dt.datetime(2026, 9, 8, 16, 15, tzinfo=dt.timezone.utc)
        old_time = '2026-03-09T09:00:00+08:00'
        cases = [('11', '一次性准备截止2026-03-10', '2026-03-10', old_time),
                 ('12', '未来活动截止2026-09-10', '2026-09-10', old_time),
                 ('13', '今天活动截止2026-09-09', '2026-09-09', old_time),
                 ('14', '长期阅读约定，请持续保留阅读记录。', '', old_time),
                 ('15', '时间仍待核对，请带阅读材料。', '', '')]
        payload = self.payload(cursor='15')
        payload['messages'] = [dict(id=ident, time=stamp, kind='text', sender='示例老师', text=text, unread=False)
                               for ident, text, due, stamp in cases]
        self.store.ingest(payload)
        # Existing parent decisions and their task must survive analysis of old messages.
        fp = self.store._job('prior-school', 'prior', self.now)
        item = dict(child_id='child-1', kind='school', title='已由家长核对的要求', body=agent.FOCUS['school'],
                    evidence=[dict(ref='message:synthetic-prior:1', text='虚构的早期依据')], due='2026-03-10')
        self.store._save('prior-school', fp, [item, {**item, 'title': '家长已忽略的要求'}], self.now)
        prior = self.store.snapshot()['items']
        self.store.act(dict(id=prior[0]['id'], action='accept'))
        self.store.act(dict(id=prior[1]['id'], action='dismiss'))
        with self.app.connect() as c:
            before_items = [dict(row) for row in c.execute('SELECT * FROM agent_items ORDER BY id')]
            before_tasks = [dict(row) for row in c.execute('SELECT * FROM manual_tasks ORDER BY id')]

        with patch.object(agent.family_llm, '_chat_json', side_effect=agent.family_llm.LLMUnavailable('offline')):
            self.assertEqual(agent.run_once(self.app, self.now)['failed'], 1)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0], '15')

        def school_model(messages, schema, name, timeout, *, data_path=None):
            request = json.loads(messages[-1]['content'])
            self.assertEqual(request['as_of'], '2026-09-09')
            self.assertEqual([row['time'] for row in request['evidence']], [row[3] for row in cases])
            self.assertIn('按各条消息的发送日期理解', messages[0]['content'])
            return {'proposals': [dict(title_quote=text, focus='school', due=due,
                evidence=[dict(ref='message:' + self.source['id'] + ':' + ident, quote=text)])
                for ident, text, due, stamp in cases]}

        with patch.object(agent.family_llm, '_chat_json', side_effect=school_model) as model:
            result = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
            self.assertEqual((result['created'], result['processed']), (4, 5))
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=7))['created'], 0)
            self.assertEqual(model.call_count, 1)
        with self.app.connect() as c:
            stored = [dict(row) for row in c.execute('SELECT * FROM agent_messages ORDER BY id')]
            self.assertEqual([json.loads(row['payload'])['text'] for row in stored], [row[1] for row in cases])
            self.assertTrue(all(row['processed'] == 1 for row in stored))
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0], '15')
            self.assertEqual([dict(row) for row in c.execute("SELECT * FROM agent_items WHERE job_id='prior-school' ORDER BY id")], before_items)
            self.assertEqual([dict(row) for row in c.execute('SELECT * FROM manual_tasks ORDER BY id')], before_tasks)
        pending = self.store.snapshot()['items']
        titles = [row['title'] for row in pending if row['state'] == 'pending']
        self.assertEqual(set(titles), {'待核对：' + row[1] for row in cases[1:]})

    def test_old_learning_evidence_is_not_filtered_by_school_expiry_rule(self):
        evidence = [dict(ref='record:synthetic-old', text='2026-03-10 阅读观察')]
        output = {'proposals': [dict(title_quote='阅读观察', focus='listen', due='2026-03-10',
                                    evidence=[dict(ref=evidence[0]['ref'], quote=evidence[0]['text'])])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=output):
            self.assertEqual(len(agent._select('learning', evidence, as_of='2026-09-09')), 1)

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
        bad = {'proposal': {'oops': 'invalid'}}
        with patch.object(agent.family_llm, '_chat_json', return_value=bad):
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=1))['state'], 'needs_attention')

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

    def test_learning_plan_accept_feedback_due_deferral_dismiss_and_restart(self):
        self.now = dt.datetime.now(agent.TZ).replace(microsecond=0)
        first = self.record(note='孩子自述：分数题想再说一遍。')
        calls = []

        def planner(evidence, profile, *, as_of, data_path):
            calls.append(evidence)
            return dict(title='再说一次分数题', goal='能说出一步理由', action='一起说一说这次分数题最关键的一步。',
                        why_now='记录中保留了孩子自己的表达。', estimated_minutes=8,
                        review_on=(dt.date.fromisoformat(as_of) + dt.timedelta(days=2)).isoformat(),
                        evidence=[dict(ref=evidence[0]['ref'], quote=evidence[0]['text'][:30])])

        with patch.object(agent, '_plan_learning', side_effect=planner) as model:
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            care = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'care')
            with self.assertRaises(agent.AgentError):
                self.store.act(dict(id=care['id'], action='accept', title='确认小尝试', body='一起说一说关键一步。',
                                     review_on='2026-02-31', estimated_minutes=8))
            accepted = self.store.act(dict(id=care['id'], action='accept', title='家长确认的一小步', body='一起说一说关键一步。',
                                            review_on=(self.now.date() + dt.timedelta(days=2)).isoformat(), estimated_minutes=8))
            self.assertEqual(self.store.act(dict(id=care['id'], action='accept', title='迟到标题')), accepted)
            task_id = accepted['task_id']
            with self.app.connect() as c:
                c.execute('INSERT INTO records(child,day,category,subject,title,note,source,created,related_record_id,followup_kind,assistance,practice_relation,comparison_note) '
                          'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          ('示例甲', (self.now.date() + dt.timedelta(days=1)).isoformat(), '学习进展', '语文', '分数题回看',
                           '孩子说：这次先想每份一样大。', '家长记录', self.now.isoformat(), first, '订正', '', '', ''))
                feedback_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=1))['created'], 1)
            self.assertEqual(model.call_count, 2)
            self.assertTrue(any(evidence['ref'].startswith('plan:') for evidence in calls[1]))
            with self.app.connect() as c:
                c.execute('UPDATE records SET note=? WHERE id=?', ('更正：这次实际先画图再说。', first))
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=1, minutes=1))['created'], 1)
            self.assertEqual(model.call_count, 3)
            self.app.save_task(dict(id=task_id, status='已完成', note='虚构反馈：完成一次约定尝试。'))
            due_day = self.now.date() + dt.timedelta(days=2)
            self.assertGreaterEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(8), tzinfo=agent.TZ))['created'], 1)
            model_calls_before_defer = model.call_count
            review = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'review' and item['state'] == 'pending')
            self.assertIn('补充实际用时、结果和帮助', review['body'])
            care = next(item for item in self.store.snapshot()['items'] if item['id'] == care['id'])
            deferred = self.store.act(dict(id=care['id'], action='defer', review_on=(self.now.date() + dt.timedelta(days=5)).isoformat(),
                                            expected_updated=care['updated']))
            self.assertFalse(deferred.get('replayed'))
            self.assertTrue(self.store.act(dict(id=care['id'], action='defer', review_on=(self.now.date() + dt.timedelta(days=5)).isoformat(),
                                                expected_updated=care['updated'])).get('replayed'))
            with self.app.connect() as c:
                self.assertEqual(c.execute("SELECT state FROM agent_items WHERE id=?", (review['id'],)).fetchone()[0], 'superseded')
            due_day = self.now.date() + dt.timedelta(days=5)
            self.assertGreaterEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(8), tzinfo=agent.TZ))['created'], 1)
            self.assertEqual(model.call_count, model_calls_before_defer)
            review = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'review' and item['state'] == 'pending')
            self.store.act(dict(id=review['id'], action='dismiss'))
            self.assertEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(9), tzinfo=agent.TZ))['created'], 0)
        reopened = agent.Store(self.app.connect, self.app.profiles, self.data)
        self.assertEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(9), tzinfo=agent.TZ))['created'], 0)

    def test_planned_review_respects_focus_without_date_and_update_order(self):
        self.now = dt.datetime.now(agent.TZ).replace(microsecond=0)
        self.record()
        review_dates = {}

        def planner(evidence, profile, *, as_of, data_path):
            review_dates['base'] = dt.date.fromisoformat(as_of) + dt.timedelta(days=2)
            return dict(title='一次小尝试', goal='说出一步理由', action='一起说出这次尝试的一步理由。',
                        why_now='记录保留了这次尝试。', estimated_minutes=5,
                        review_on=review_dates['base'].isoformat(),
                        evidence=[dict(ref=evidence[0]['ref'], quote=evidence[0]['text'][:20])])

        with patch.object(agent, '_plan_learning', side_effect=planner):
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
        care = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'care')
        accepted = self.store.act(dict(id=care['id'], action='accept', review_on=review_dates['base'].isoformat(),
                                       estimated_minutes=5, title='确认小尝试', body='一起说出这次尝试的一步理由。'))
        task_id = accepted['task_id']
        with self.app.connect() as c:
            plan_changed = json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (care['id'],)).fetchone()[0])['approved_changed_at']
        def set_focus(mode, review_on, updated):
            with self.app.connect() as c:
                c.execute('''CREATE TABLE IF NOT EXISTS task_focus (
                    task_id TEXT PRIMARY KEY, mode TEXT NOT NULL, next_action TEXT NOT NULL,
                    waiting_for TEXT NOT NULL, review_on TEXT NOT NULL, version INTEGER NOT NULL, updated TEXT NOT NULL)''')
                c.execute('''INSERT INTO task_focus VALUES (?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                    mode=excluded.mode,next_action=excluded.next_action,waiting_for=excluded.waiting_for,
                    review_on=excluded.review_on,version=excluded.version,updated=excluded.updated''',
                          (task_id, mode, '', '等回复' if mode == 'waiting' else '', review_on, 1, updated))
        changed = (dt.datetime.fromisoformat(plan_changed) + dt.timedelta(microseconds=1)).isoformat()
        set_focus('waiting', '', changed)
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(review_dates['base'], dt.time(8), tzinfo=agent.TZ)), [])
        focus_date = review_dates['base'] + dt.timedelta(days=1)
        set_focus('later', focus_date.isoformat(), changed)
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(focus_date, dt.time(8), tzinfo=agent.TZ))[0]['review_on'], focus_date.isoformat())
        care = next(item for item in self.store.snapshot()['items'] if item['id'] == care['id'])
        defer_date = review_dates['base'] + dt.timedelta(days=2)
        self.store.act(dict(id=care['id'], action='defer', review_on=defer_date.isoformat(), expected_updated=care['updated']))
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(defer_date, dt.time(8), tzinfo=agent.TZ))[0]['review_on'], defer_date.isoformat())
        with self.app.connect() as c:
            approved_changed = json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (care['id'],)).fetchone()[0])['approved_changed_at']
        latest_focus = (dt.datetime.fromisoformat(approved_changed) + dt.timedelta(microseconds=1)).isoformat()
        later_date = defer_date + dt.timedelta(days=1)
        set_focus('waiting', later_date.isoformat(), latest_focus)
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(later_date, dt.time(8), tzinfo=agent.TZ))[0]['review_on'], later_date.isoformat())


if __name__ == '__main__':
    unittest.main()
