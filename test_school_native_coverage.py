"""Synthetic native school-action coverage; no real model, collectors or devices.

The incomplete receipt is structurally valid and cites both original messages,
but omits the exercise and all its supplemental standards. It must not finish
the intake batch. This regression uses run_once's real _select/_save route;
the saved replies are fixtures, not a measurement of model extraction accuracy.
"""
import copy
import datetime as dt
import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import family_agent as agent
import family_media
import test_agent as fixtures


class SchoolNativeCoverageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AgentTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.now = dt.datetime(2026, 10, 5, 8, tzinfo=agent.TZ)
        self.app, self.store, self.now = self.fixture.app, self.fixture.store, self.fixture.now
        self.source = self.fixture.source
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        self.model = self.stack.enter_context(patch.object(
            agent.family_llm, '_chat_json', side_effect=AssertionError('no real model transport')))

    def _ingest(self, texts, publishers=None):
        publishers = publishers or ['synthetic-teacher-1'] * len(texts)
        payload = self.fixture.payload(cursor=str(10 + len(texts)))
        common = dict(time=self.now.isoformat(), kind='text', sender='虚构英语老师',
                      unread=False)
        payload['messages'] = [dict(common, id=str(11 + index), message_order=str(11 + index),
                                    sender_id=publisher, text=text)
                               for index, (text, publisher) in enumerate(zip(texts, publishers))]
        self.assertEqual(len(payload['messages']), len(texts))
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        return payload, refs

    def _two_actions(self, extra_supplement=None):
        texts = ['英语，明天完成两项要求：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题。',
                 '补充英语练习卷：单面打印；完成后自查并请家长签字；第4题选做。']
        publishers = ['synthetic-teacher-1', 'synthetic-teacher-1']
        if extra_supplement:
            texts.append(extra_supplement)
            publishers.append('synthetic-teacher-2')
        payload, refs = self._ingest(texts, publishers)
        reading = fixtures.school_proposal(
            title_quote='朗读Unit 2课文两遍', due='2026-10-06', evidence=[dict(ref=refs[0])],
            learning_subject='英语', task_title='英语：朗读Unit 2课文',
            task_goal='朗读Unit 2课文两遍。', task_state='ready',
            task_reason='原文第一项朗读要求明确。', task_purpose='learning')
        exercise = fixtures.school_proposal(
            title_quote='完成练习卷第1–3题', due='2026-10-06', evidence=[dict(ref=ref) for ref in refs[:2]],
            learning_subject='英语', task_title='英语：完成练习卷',
            task_goal='完成练习卷第1–3题；单面打印；完成后自查并请家长签字；第4题选做。',
            task_state='ready', task_reason='原文第二项及同一份练习的补充标准明确。',
            task_purpose='learning')
        return payload, refs, reading, exercise

    def _use_replies(self, payload, replies):
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        calls = []

        def saved_reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual(name, 'family_agent_selection', 'only the school selection is allowed')
            self.assertEqual(data_path, self.app.DATA, 'the model seam must use only the synthetic family')
            context = json.loads(messages[-1]['content'])
            self.assertEqual([(e['ref'], e['text']) for e in context['evidence']],
                             list(zip(refs, [m['text'] for m in payload['messages']])))
            self.assertTrue(all(e['kind'] == 'text' and not e['content_incomplete']
                                and not e['attachments'] for e in context['evidence']))
            calls.append(name)
            self.assertLessEqual(len(calls), len(replies), 'retry/replay must not request another model receipt')
            return copy.deepcopy(replies[len(calls) - 1])

        self.model.side_effect = saved_reply

    def _assert_rejected_batch(self, payload, result, *, model_calls=1):
        self.assertEqual((result['failed'], result['processed'], result['created']), (1, 0, 0),
                         'invalid action allocation must not finish or partially save the batch')
        self.assertEqual(self.model.call_count, model_calls)
        with self.store._db() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')],
                             [0] * len(payload['messages']))
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')],
                             payload['messages'], 'failure must preserve the complete originals')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            job = c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
            self.assertEqual((job['attempts'], job['done']), (1, 0))
            self.assertTrue(job['error'])
            self.assertEqual(job['next_try'], (self.now + dt.timedelta(minutes=5)).isoformat())
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0], payload['cursor'])

    def _excerpt_batch(self, due, correction_publisher='synthetic-teacher-1'):
        texts = ['语文：2026年10月18日20:00前完成《河岸随记》的阅读摘记，摘录两句并各写一句选择理由；摘记本2026年10月19日早读交给语文课代表；2026年10月19日早读默写《山行》全文。',
                 '更正：摘记本改为2026年10月20日早读交给语文课代表；摘记仍须2026年10月18日20:00前完成；《山行》默写安排不变。',
                 '家长问：摘记本是不是只交一本？活动回执有没有电子版？']
        payload, refs = self._ingest(texts, ['synthetic-teacher-1', correction_publisher, 'synthetic-parent-1'])
        excerpt = fixtures.school_proposal(
            title_quote='语文：2026年10月18日20:00前完成《河岸随记》的阅读摘记，摘录两句并各写一句选择理由；摘记本2026年10月19日早读交给语文课代表；',
            due=due, evidence=[dict(ref=refs[0]), dict(ref=refs[1])], learning_subject='语文', task_title='语文：完成《河岸随记》阅读摘记',
            task_goal='2026年10月18日20:00前完成《河岸随记》的阅读摘记。\n摘录两句，并各写一句选择理由。\n摘记本于2026年10月20日早读交给语文课代表（原为10月19日早读，已更正）。',
            task_state='ready', task_reason='虚构回执：完成时间与更正后的交回时间。', task_purpose='learning',
            task_submission='摘记本于2026年10月20日早读交给语文课代表。')
        dictation = fixtures.school_proposal(
            title_quote='2026年10月19日早读默写《山行》全文。', due='2026-10-19', evidence=[dict(ref=refs[0]), dict(ref=refs[1])],
            learning_subject='语文', task_title='语文：早读默写《山行》全文', task_goal='2026年10月19日早读默写《山行》全文。\n《山行》默写安排不变。',
            task_state='ready', task_reason='虚构回执。', task_purpose='learning')
        question = fixtures.school_proposal(
            title_quote=texts[2], evidence=[dict(ref=refs[2])], task_state='reference', task_purpose='optional',
            task_reason='虚构回执：家长个人询问，不是老师要求。')
        return payload, refs, [excerpt, dictation, question]

    def test_corrected_handback_day_saves_one_excerpt_task_with_its_completion_time(self):
        payload, refs, replies = self._excerpt_batch('2026-10-20')
        self._use_replies(payload, [dict(proposals=replies)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 3))
        with self.store._db() as c:
            saved = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            excerpt, = [r for r in saved if '河岸随记' in r['title']]
            self.assertEqual((excerpt['due'], excerpt['state']), ('2026-10-20', 'accepted'))
            for words in ('2026年10月18日20:00前完成', '摘录两句', '各写一句选择理由', '2026年10月20日早读交给语文课代表'):
                self.assertIn(words, excerpt['body'])
            self.assertEqual([e['ref'] for e in json.loads(excerpt['evidence'])], refs[:2])
            dictation, = [r for r in saved if '山行' in r['title']]
            self.assertEqual(dictation['due'], '2026-10-19', 'the dictation never borrows the corrected handback day')
            question = [r for r in saved if r['evidence'] and refs[2] in r['evidence']]
            self.assertTrue(question and all(json.loads(r['plan'])['school_task']['state'] == 'reference' and not r['task_id']
                                             for r in question), 'the parent question stays reference, never a todo')
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
            self.assertEqual(sorted(t['due'] for t in tasks), ['2026-10-19', '2026-10-20'])
            self.assertFalse(any('只交一本' in t['action'] for t in tasks))
            rows = [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        with self.store._db() as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')], rows, 'no second excerpt task')

    def test_old_completion_day_or_another_teachers_correction_keeps_the_excerpt_unconfirmed(self):
        payload, refs, original = self._excerpt_batch('')
        for due, publisher in (('2026-10-18', 't1'), ('2026-10-19', 't1'), ('2026-10-20', 't2')):
            with self.subTest(due=due, publisher=publisher):
                replies = copy.deepcopy(original);replies[0]['due'] = due
                with patch.object(agent.family_llm, '_chat_json', return_value=dict(proposals=replies)):
                    evidence = [dict(ref=r, text=m['text'], time=m['time'], kind='text', publisher='publisher:' + p,
                                     content_incomplete=False, attachments=[], unread=False)
                                for r, m, p in zip(refs, payload['messages'], ['t1', publisher, 'p1'])]
                    items = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-05')
                excerpt, = [i for i in items if '河岸随记' in i['title']]
                self.assertEqual((excerpt['due'], excerpt['plan']['school_task']['state']), ('', 'review'),
                                 'a wrong or unowned day is neither kept nor rewritten to the corrected day')
                question, = [i for i in items if i['evidence'][0]['ref'] == refs[2]]
                self.assertEqual(question['plan']['school_task']['state'], 'reference')

    def test_a_title_naming_another_day_or_a_change_word_never_corrects_the_old_material(self):
        for old, new in (('《10月18日课堂摘记》', '更正：《10月20日课堂摘记》改为'), ('《实操指南》', '《改为实操指南》')):
            with self.subTest(old=old):
                self.setUp()
                payload, refs = self._ingest([old + '2026年10月19日交回', new + '2026年10月21日交回'])
                named = new.split('《')[1].split('》')[0]
                first = fixtures.school_proposal(
                    title_quote=old + '2026年10月19日交回', due='2026-10-21', evidence=[dict(ref=r) for r in refs],
                    learning_subject='语文', task_title='交回' + old, task_goal=old + '2026年10月21日交回。',
                    task_state='ready', task_reason='虚构对抗回执。', task_purpose='admin')
                second = fixtures.school_proposal(
                    title_quote=new + '2026年10月21日交回', due='2026-10-21', evidence=[dict(ref=refs[1])],
                    learning_subject='语文', task_title='交回《' + named + '》', task_goal='《' + named + '》2026年10月21日交回。',
                    task_state='ready', task_reason='虚构独立新材料。', task_purpose='admin')
                self._use_replies(payload, [dict(proposals=[first, second])])
                self.assertEqual(agent.run_once(self.app, self.now)['failed'], 0)
                with self.store._db() as c:
                    rows = {r['title']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
                    tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
                self.assertEqual((rows['交回' + old]['due'], json.loads(rows['交回' + old]['plan'])['school_task']['state']), ('', 'review'))
                self.assertIn(old + '2026年10月19日交回', json.loads(rows['交回' + old]['evidence'])[0]['text'])
                self.assertEqual((rows['交回《' + named + '》']['due'], rows['交回《' + named + '》']['state']), ('2026-10-21', 'accepted'))
                self.assertEqual([(t['title'], t['due']) for t in tasks], [('交回《' + named + '》', '2026-10-21')])
                self.doCleanups()

    def test_only_a_positive_same_publisher_corrects_the_excerpt_handback(self):
        payload, refs, original = self._excerpt_batch('2026-10-20')
        for publisher, expected in (('t1', ('2026-10-20', 'ready')), ('', ('', 'review')), (None, ('', 'review'))):
            with self.subTest(publisher=publisher), patch.object(agent.family_llm, '_chat_json',
                                                                 return_value=dict(proposals=copy.deepcopy(original))):
                evidence = [dict(ref=r, text=m['text'], time=m['time'], kind='text', content_incomplete=False, attachments=[],
                                 unread=False, **({} if publisher is None and n < 2 else
                                                  dict(publisher='publisher:p1' if n == 2 else publisher and 'publisher:' + publisher)))
                            for n, (r, m) in enumerate(zip(refs, payload['messages']))]
                items = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-05')
                excerpt, = [i for i in items if '河岸随记' in i['title']]
                self.assertEqual((excerpt['due'], excerpt['plan']['school_task']['state']), expected)
                for words in ('2026年10月18日20:00前完成', '摘录两句', '各写一句选择理由'):
                    self.assertIn(words, excerpt['plan']['school_task']['goal'])
                self.assertEqual([q['ref'] for q in excerpt['evidence']], refs[:2])

    def test_missing_second_action_and_supplement_keeps_batch_retryable(self):
        payload, refs, reading, exercise = self._two_actions()
        # Both message refs are present, so the old ref-only coverage guard
        # accepts this receipt despite losing the second independent outcome.
        incomplete = dict(reading, evidence=[dict(ref=ref) for ref in refs])
        self._use_replies(payload, [dict(proposals=[incomplete]), dict(proposals=[reading, exercise])])
        first = agent.run_once(self.app, self.now)
        self._assert_rejected_batch(payload, first)
        source = self.store.snapshot()['sources'][0]
        self.assertEqual(source['pending_message_count'], 2, 'received messages are still awaiting successful processing')
        self.assertEqual((source['error'], source['last_success']), ('', payload['checked_at']),
                         'successful collection does not mean the school list is complete')
        agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 2)
        with self.store._db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
        self.assertEqual(self.model.call_count, 1, 'respect the existing retry delay')

        recovered = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((recovered['failed'], recovered['processed']), (0, 2))
        self.assertEqual(self.model.call_count, 2)
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 0)
        with self.store._db() as c:
            # route_school legitimately creates a care root for the subject;
            # count school outcomes without deleting that unrelated workflow.
            saved = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual(len(saved), 2, 'reading and exercise are two independent outcomes')
            reading_rows = [r for r in saved if '朗读Unit 2课文两遍' in r['body']]
            exercise_rows = [r for r in saved if '完成练习卷第1–3题' in r['body']]
            self.assertEqual((len(reading_rows), len(exercise_rows)), (1, 1))
            reading_row, exercise_row = reading_rows[0], exercise_rows[0]
            self.assertNotEqual(reading_row['id'], exercise_row['id'], 'do not merge independent actions')
            for clause in ('完成练习卷第1–3题', '单面打印', '完成后自查并请家长签字', '第4题选做'):
                self.assertIn(clause, exercise_row['body'], 'keep every literal exercise standard')
                self.assertNotIn(clause, reading_row['body'], 'exercise standards must not move to reading')
            self.assertNotIn('朗读Unit 2课文两遍', exercise_row['body'])
            for row, expected_refs in ((reading_row, [refs[0]]), (exercise_row, refs)):
                self.assertTrue(row['title'].startswith('英语：'))
                self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
                self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], expected_refs)
                self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')
                scope=json.loads(row['plan'])['school_original_action']
                self.assertEqual(scope['identity'],agent._hash([row['child_id'],sorted(
                    agent._json([a['ref'],a['upload_ids'],a['quote']]) for a in scope['anchors'])]))
                self.assertTrue(all(a['upload_ids']==[] and a['pages']==[] for a in scope['anchors']))
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
            self.assertEqual(set(tasks), {r['task_id'] for r in saved})
            for row in saved:
                task = tasks[row['task_id']]
                self.assertEqual(task['title'], row['title'])
                self.assertEqual((task['child'], task['action'], task['due'], task['original_status']),
                                 ('示例甲', row['body'], '2026-10-06', '待跟进'))
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')], [1, 1])
            self.assertEqual(tuple(c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()),
                             (2, 1, '', ''))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            item_rows = [tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')]
            task_rows = [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]

        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 2)
        with self.store._db() as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')], item_rows)
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')], task_rows)

    def test_pending_message_counts_are_source_scoped_and_reject_stale_bindings(self):
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 0)
        self._two_actions()
        second = dict(self.source, id='synthetic-second-group', child_id='child-2', name='虚构另一班级')
        empty = dict(self.source, id='synthetic-empty-group', name='虚构未读取班级')
        path = self.app.DATA / 'agent.json'
        config = json.loads(path.read_text())
        config['sources'] = [self.source, second, empty]
        path.write_text(json.dumps(config, ensure_ascii=False))
        self.store.ingest(dict(self.fixture.payload(), source_id=second['id']))
        with self.store._db() as c:
            before = [tuple(r) for r in c.execute('SELECT * FROM agent_messages ORDER BY source_id,id')]
        sources = {s['id']: s for s in self.store.snapshot()['sources']}
        self.assertEqual({key: row['pending_message_count'] for key, row in sources.items()},
                         {self.source['id']: 2, second['id']: 1, empty['id']: 0})
        for changes in ({'child_id': 'child-2'}, {'platform': 'qq'}):
            with self.subTest(changes=changes):
                config['sources'][0] = dict(self.source, **changes)
                path.write_text(json.dumps(config, ensure_ascii=False))
                sources = {s['id']: s for s in self.store.snapshot()['sources']}
                self.assertTrue(sources[self.source['id']]['error'])
                self.assertEqual(sources[self.source['id']]['pending_message_count'], 0,
                                 'an invalid binding must not expose another ownership context')
                self.assertEqual(sources[second['id']]['pending_message_count'], 1)
                self.assertEqual(sources[empty['id']]['pending_message_count'], 0)
        config['sources'] = [second, empty]
        path.write_text(json.dumps(config, ensure_ascii=False))
        self.assertEqual({s['id'] for s in self.store.snapshot()['sources']}, {second['id'], empty['id']})
        with self.store._db() as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM agent_messages ORDER BY source_id,id')], before)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
        self.model.assert_not_called()

    def test_two_independent_actions_cannot_be_merged_into_one_receipt(self):
        payload, refs, reading, exercise = self._two_actions()
        merged = dict(reading, evidence=[dict(ref=ref) for ref in refs],
                      task_title='英语：朗读并完成练习卷',
                      task_goal=reading['task_goal'] + '\n' + exercise['task_goal'])
        self._use_replies(payload, [dict(proposals=[merged])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_malformed_native_title_keeps_the_existing_batch_retry(self):
        payload, refs, reading, exercise = self._two_actions()
        self._use_replies(payload, [dict(proposals=[dict(reading, title_quote=None), exercise])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_one_actions_date_is_not_borrowed_by_its_sibling(self):
        payload, refs = self._ingest(['英语，完成两项要求：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题，明天完成。'])
        proposals=[fixtures.school_proposal(title_quote=quote, due='2026-10-06', evidence=[dict(ref=refs[0])],
            learning_subject='英语', task_title=quote, task_goal=quote, task_state='ready',
            task_reason='虚构回执错误地把第二项截止借给第一项。', task_purpose='learning')
            for quote in ['朗读Unit 2课文两遍','完成练习卷第1–3题']]
        self._use_replies(payload,[dict(proposals=proposals)])
        result=agent.run_once(self.app,self.now)
        self.assertEqual(result['failed'],0)
        with self.store._db() as c:
            rows=[dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            reading=next(r for r in rows if '朗读' in r['body'])
            exercise=next(r for r in rows if '练习卷' in r['body'])
            self.assertEqual((reading['due'],reading['state']),('','pending'))
            self.assertEqual((exercise['due'],exercise['state']),('2026-10-06','accepted'))

    def test_named_supplement_uses_its_own_sending_day_across_midnight(self):
        payload=self.fixture.payload(cursor='12')
        texts=['英语，完成两项要求：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题。',
               '补充英语练习卷：明天完成并自查。']
        payload['messages']=[dict(id=str(11+i),time=stamp,kind='text',sender='虚构英语老师',
            sender_id='synthetic-teacher-1',unread=False,text=text,message_order=str(11+i))
            for i,(stamp,text) in enumerate(zip(['2026-10-04T23:59:30+08:00','2026-10-05T00:00:30+08:00'],texts))]
        self.store.ingest(payload)
        refs=['message:'+self.source['id']+':'+m['id'] for m in payload['messages']]
        reading=fixtures.school_proposal(title_quote='朗读Unit 2课文两遍',evidence=[dict(ref=refs[0])],
            learning_subject='英语',task_title='英语：朗读课文',task_goal='朗读Unit 2课文两遍',task_state='ready',task_purpose='learning')
        exercise=fixtures.school_proposal(title_quote='完成练习卷第1–3题',due='2026-10-06',evidence=[dict(ref=r) for r in refs],
            learning_subject='英语',task_title='英语：完成练习卷',task_goal='完成练习卷第1–3题；明天完成并自查。',task_state='ready',task_purpose='learning')
        self._use_replies(payload,[dict(proposals=[reading,exercise])])
        result=agent.run_once(self.app,self.now)
        self.assertEqual(result['failed'],0)
        with self.store._db() as c:
            row=dict(c.execute("SELECT * FROM agent_items WHERE kind='school' AND body LIKE '%练习卷%'").fetchone())
            self.assertEqual((row['due'],row['state']),('2026-10-06','accepted'))
            self.assertIn('明天完成并自查',row['body'])

    def test_mixed_header_keeps_the_subject_named_by_its_own_action(self):
        payload,refs=self._ingest(['英语和数学，明天完成两项要求：1. 朗读Unit 2课文两遍；2. 完成数学练习卷第1–3题。'])
        proposals=[fixtures.school_proposal(title_quote=quote,due='2026-10-06',evidence=[dict(ref=refs[0])],
            learning_subject=subject,task_title=subject+'：'+quote,task_goal=quote,
            task_state='ready',task_purpose='learning')
            for subject,quote in [('英语','朗读Unit 2课文两遍'),('数学','完成数学练习卷第1–3题')]]
        self._use_replies(payload,[dict(proposals=proposals)])
        result=agent.run_once(self.app,self.now)
        self.assertEqual(result['failed'],0)
        with self.store._db() as c:
            row=dict(c.execute("SELECT * FROM agent_items WHERE kind='school' AND body LIKE '%数学练习卷%'").fetchone())
            self.assertTrue(row['title'].startswith('数学：'))
            self.assertFalse(row['title'].startswith('英语：'))

    def test_repeated_native_action_cannot_create_an_extra_copy(self):
        payload, refs, reading, exercise = self._two_actions()
        duplicate = dict(reading, task_title='英语：再次朗读Unit 2课文')
        self._use_replies(payload, [dict(proposals=[reading, exercise, duplicate])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_extra_copy_without_action_anchor_cannot_bypass_allocation(self):
        payload, refs, reading, exercise = self._two_actions()
        # The header quote is literal but does not identify either outcome.
        # A third receipt cannot evade ownership by choosing this broad quote.
        extra = dict(exercise, title_quote='英语', task_title='英语：再做练习卷')
        self._use_replies(payload, [dict(proposals=[reading, exercise, extra])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_supplement_reference_elsewhere_does_not_cover_the_exercise(self):
        payload, refs, reading, exercise = self._two_actions()
        missing_link = dict(exercise, evidence=[dict(ref=refs[0])])
        # All message refs are still accounted for. The second message must be
        # assigned to the exercise, not hidden in a separate reference receipt.
        misplaced = fixtures.school_proposal(
            title_quote='补充英语练习卷', evidence=[dict(ref=refs[1])],
            task_title='练习卷补充说明', task_goal=payload['messages'][1]['text'],
            task_state='reference', task_reason='虚构错误回执将必需补充当成参考。',
            task_purpose='admin')
        self._use_replies(payload, [dict(proposals=[reading, missing_link, misplaced])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_supplements_from_different_publishers_cannot_bind_by_same_nickname(self):
        payload, refs, reading, exercise = self._two_actions(
            extra_supplement='补充英语练习卷：第1–3题均用红笔作答。')
        self.assertEqual(payload['messages'][1]['sender'], payload['messages'][2]['sender'])
        self.assertNotEqual(payload['messages'][1]['sender_id'], payload['messages'][2]['sender_id'])
        foreign_link = dict(exercise, evidence=[dict(ref=ref) for ref in refs],
                            task_goal=exercise['task_goal'] + '\n第1–3题均用红笔作答。')
        self._use_replies(payload, [dict(proposals=[reading, foreign_link])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_two_notices_cannot_compete_for_the_same_ambiguous_supplement(self):
        payload,refs=self._ingest([
            '英语，明天完成两项要求：1. 朗读Unit 1课文两遍；2. 完成甲练习卷第1–3题。',
            '英语，明天完成两项要求：1. 朗读Unit 2课文两遍；2. 完成乙练习卷第1–3题。',
            '补充英语练习卷：第4题选做。'])
        result=agent.run_once(self.app,self.now)
        self.assertEqual((result['failed'],result['processed'],result['created']),(1,0,0))
        self.model.assert_not_called()
        with self.store._db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')],[0,0,0])
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],payload['messages'])
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0],payload['cursor'])
            job=c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
            self.assertEqual((job['attempts'],job['done']),(1,0))
            self.assertIn('同时对应多项',job['error'])
            self.assertEqual(job['next_try'],(self.now+dt.timedelta(minutes=5)).isoformat())

    SHARED_LIST = '英语，明天完成两项要求：1. 朗读Unit 8课文两遍；2. 完成练习卷第2–4题。'
    SHARED_STANDARD = '以上两项均请家长核对并在记录本签字。'
    SHARED_ACTIONS = ('朗读Unit 8课文两遍', '完成练习卷第2–4题')

    def _shared_messages(self, texts, *, stamps=('2026-10-15T07:58:00+08:00', '2026-10-15T07:59:00+08:00'),
                         publishers=None, cited=None, unread_last=False):
        """A wholly synthetic list and its same-teacher shared standard; the receipt is a fixed complete reply."""
        self.now = self.fixture.now = dt.datetime(2026, 10, 15, 8, tzinfo=agent.TZ)
        publishers = publishers or ['synthetic-teacher-1'] * len(texts)
        payload = self.fixture.payload(cursor=str(10 + len(texts)))
        payload['messages'] = [dict(id=str(11 + i), message_order=str(11 + i), time=stamp, kind='text',
                                    sender='虚构英语老师', sender_id=publisher, text=text,
                                    unread=unread_last and i == len(texts) - 1)
                               for i, (text, stamp, publisher) in enumerate(zip(texts, stamps, publishers))]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        proposals = [fixtures.school_proposal(
            title_quote=quote, due='2026-10-16', evidence=[dict(ref=ref) for ref in (cited or refs)],
            learning_subject='英语', task_title='英语：' + quote,
            task_goal=quote + '；以上两项均请家长核对并在记录本签字。', task_state='ready',
            task_reason='虚构回执：本项行动与共同核对签字标准明确。', task_purpose='learning')
            for quote in self.SHARED_ACTIONS]
        return payload, refs, proposals

    def _assert_shared_saved(self, payload, refs, proposals):
        self._use_replies(payload, [dict(proposals=proposals)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, len(refs)))
        self.assertEqual(self.model.call_count, 1)
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), 2, 'the shared standard is no third task and the two actions stay separate')
            for quote, other in (self.SHARED_ACTIONS, self.SHARED_ACTIONS[::-1]):
                row = next(r for r in rows if quote in r['body'])
                self.assertNotIn(other, row['body'])
                self.assertIn('以上两项均请家长核对并在记录本签字', row['body'])
                self.assertEqual((row['due'], row['state']), ('2026-10-16', 'accepted'))
                self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)
                scope = json.loads(row['plan'])['school_original_action']
                self.assertEqual({a['ref'] for a in scope['anchors']}, set(refs))
                self.assertTrue(all(payload['messages'][refs.index(a['ref'])]['text'].count(a['quote']) == 1
                                    for a in scope['anchors']), 'every anchor stays a literal original quote')
                self.assertEqual(scope['identity'], agent._hash([row['child_id'], sorted(
                    agent._json([a['ref'], a['upload_ids'], a['quote']]) for a in scope['anchors'])]))
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
            self.assertEqual(set(tasks), {r['task_id'] for r in rows})
            for row in rows:
                self.assertEqual((tasks[row['task_id']]['action'], tasks[row['task_id']]['due']), (row['body'], '2026-10-16'))
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')], [1] * len(refs))
            before = ([tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')],
                      [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')])
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1, 'a saved batch is not sent again')
        with self.store._db() as c:
            self.assertEqual(([tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')],
                              [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]), before)
        return sorted((r['title'], r['body'], r['due'], r['state']) for r in rows)

    SHARED_SAVED = [('英语：完成练习卷第2–4题', '明天\n完成练习卷第2–4题\n以上两项均请家长核对并在记录本签字', '2026-10-16', 'accepted'),
                    ('英语：朗读Unit 8课文两遍', '明天\n朗读Unit 8课文两遍\n以上两项均请家长核对并在记录本签字', '2026-10-16', 'accepted')]

    def test_list_and_its_next_shared_standard_message_save_like_one_message(self):
        saved = self._assert_shared_saved(*self._shared_messages([self.SHARED_LIST, self.SHARED_STANDARD]))
        self.assertEqual(saved, self.SHARED_SAVED)

    def test_one_message_list_with_its_shared_standard_saves_the_same_two_tasks(self):
        saved = self._assert_shared_saved(*self._shared_messages([self.SHARED_LIST + self.SHARED_STANDARD]))
        self.assertEqual(saved, self.SHARED_SAVED)

    def _assert_shared_rejected(self, texts, *, model_calls=1, **values):
        payload, refs, proposals = self._shared_messages(texts, **values)
        if values.get('unread_last'):
            # The unread original reaches the model as its own gap; the fixed complete receipt still cites it.
            self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(dict(proposals=proposals))
        else:
            self._use_replies(payload, [dict(proposals=proposals)])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now), model_calls=model_calls)
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], len(texts))

    def test_shared_standard_from_another_teacher_binds_nothing(self):
        self._assert_shared_rejected([self.SHARED_LIST, self.SHARED_STANDARD],
                                     publishers=['synthetic-teacher-1', 'synthetic-teacher-2'])

    def test_shared_standard_outside_the_supplement_window_binds_nothing(self):
        self._assert_shared_rejected([self.SHARED_LIST, self.SHARED_STANDARD],
                                     stamps=('2026-10-15T07:50:00+08:00', '2026-10-15T07:59:00+08:00'))

    def test_shared_standard_after_another_message_binds_nothing(self):
        self._assert_shared_rejected([self.SHARED_LIST, '明天带跳绳。', self.SHARED_STANDARD],
                                     stamps=('2026-10-15T07:58:00+08:00', '2026-10-15T07:58:30+08:00', '2026-10-15T07:59:00+08:00'),
                                     publishers=['synthetic-teacher-1', 'synthetic-teacher-2', 'synthetic-teacher-1'],
                                     cited=['message:' + self.source['id'] + ':' + i for i in ('11', '13')])

    def test_shared_standard_naming_another_count_keeps_the_batch_before_any_model_call(self):
        self._assert_shared_rejected([self.SHARED_LIST, '以上三项均请家长核对并在记录本签字。'], model_calls=0)

    def test_shared_standard_with_a_second_clause_binds_nothing(self):
        self._assert_shared_rejected([self.SHARED_LIST, '以上两项均请家长核对，朗读另外录音上传。'])

    def _p11_payload(self, standard_sender='synthetic-teacher-1'):
        """P11: five independent notices, then the list and its standard 60 seconds later; orders are not consecutive."""
        self.now = self.fixture.now = dt.datetime(2026, 10, 15, 8, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='17')
        texts = ['独立的虚构通知 ' + str(i) for i in range(1, 6)] + [self.SHARED_LIST, self.SHARED_STANDARD]
        stamps = ['2026-10-15T07:5%d:00+08:00' % i for i in range(5)] + ['2026-10-15T07:58:00+08:00', '2026-10-15T07:59:00+08:00']
        orders = ['101', '103', '104', '108', '109', '113', '116']
        senders = ['synthetic-teacher-1'] * 6 + [standard_sender]
        payload['messages'] = [dict(id=str(11 + i), message_order=order, time=stamp, kind='text', sender='虚构英语老师',
                                    sender_id=sender, unread=False, text=text)
                               for i, (text, stamp, order, sender) in enumerate(zip(texts, stamps, orders, senders))]
        return payload, ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]

    def test_p11_list_and_its_next_shared_standard_stay_one_reading_after_five_notices(self):
        payload, refs = self._p11_payload()
        self.store.ingest(payload)
        proposals = [fixtures.school_proposal(
            title_quote=quote, due='2026-10-16', evidence=[dict(ref=ref) for ref in refs[5:]],
            learning_subject='英语', task_title='英语：' + quote, task_goal=quote + '；以上两项均请家长核对并在记录本签字。',
            task_state='ready', task_reason='虚构回执：本项行动与共同核对签字标准明确。', task_purpose='learning')
            for quote in self.SHARED_ACTIONS]
        batches = []

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual((name, data_path), ('family_agent_selection', self.app.DATA))
            evidence = json.loads(messages[-1]['content'])['evidence']
            self.assertTrue(all(e['text'] == payload['messages'][refs.index(e['ref'])]['text'] for e in evidence))
            batches.append([e['ref'] for e in evidence])
            if batches[-1] == refs[5:]:return copy.deepcopy(dict(proposals=proposals))
            return dict(proposals=[fixtures.school_proposal(title_quote=e['text'], evidence=[dict(ref=e['ref'])],
                task_state='reference', task_purpose='unknown', task_reason='虚构通知按原文保留。') for e in evidence])

        self.model.side_effect = reply
        rounds = [agent.run_once(self.app, self.now), agent.run_once(self.app, self.now + dt.timedelta(minutes=1))]
        self.assertEqual([r['failed'] for r in rounds], [0, 0])
        self.assertEqual(batches, [refs[:5], refs[5:]], 'the list and its shared standard are read in one batch')
        self.assertEqual(self.model.call_count, 2)
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 0)
        with self.store._db() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')], [1] * 7)
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            standard_rows = [r for r in rows if refs[6] in [e['ref'] for e in json.loads(r['evidence'])]]
            self.assertEqual(len(standard_rows), 2, 'the standard is no generic pending item of its own')
            for quote, other in (self.SHARED_ACTIONS, self.SHARED_ACTIONS[::-1]):
                row = next(r for r in standard_rows if quote in r['body'])
                self.assertNotIn(other, row['body'])
                self.assertIn('以上两项均请家长核对并在记录本签字', row['body'])
                self.assertEqual((row['due'], row['state']), ('2026-10-16', 'accepted'))
                self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs[5:])
                self.assertEqual({a['ref'] for a in json.loads(row['plan'])['school_original_action']['anchors']}, set(refs[5:]))
            key = 'messages:' + agent._hash([self.source['id'], [m['id'] for m in payload['messages'][5:]]])[:40]
            self.assertEqual(tuple(c.execute('SELECT attempts,done FROM agent_jobs WHERE id=?', (key,)).fetchone()), (1, 1))
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=8))
        self.assertEqual((replay['processed'], replay['created'], self.model.call_count), (0, 0, 2))

    def test_p11_standard_groups_only_with_a_proved_same_publisher_complete_neighbour(self):
        payload, refs = self._p11_payload()
        views = [dict(source_id=self.source['id'], message=m) for m in payload['messages'][5:]]
        self.assertEqual([g['reason'] for g in agent._publication_groups(views)], ['同一发言人紧接清单的共同要求'])
        for changes in (dict(sender_id='synthetic-teacher-2'), dict(sender_id=''), dict(time='2026-10-15T08:00:01+08:00'),
                        dict(message_order='112'), dict(unread=True), dict(text='以上两项都很重要。'), dict(kind='image')):
            with self.subTest(changes=changes):
                changed = [views[0], dict(views[1], message=dict(views[1]['message'], **changes))]
                self.assertEqual(len(agent._publication_groups(changed)), 2)
        raw = [dict(payload=json.dumps(m)) for m in payload['messages']]
        self.assertEqual([[m['id'] for m in b] for b in agent._school_batches(self.source['id'], raw)],
                         [[m['id'] for m in payload['messages'][:5]], ['16', '17']])

    def test_p11_claimed_cooling_six_message_batch_keeps_its_key_and_holds_the_standard(self):
        payload, refs = self._p11_payload()
        self.store.ingest(payload)
        values = payload['messages'][:6]
        key = 'messages:' + agent._hash([self.source['id'], [v['id'] for v in values]])[:40]
        fp = self.store._job(key, dict(school_learning_policy=8, messages=values), self.now, model=True)
        self.assertTrue(fp)
        self.store._fail(key, self.now, fingerprint=fp, reason='虚构旧批冷却')
        with self.store._db() as c:
            before = tuple(c.execute('SELECT attempts,done,fingerprint,next_try FROM agent_jobs WHERE id=?', (key,)).fetchone())
        self.assertEqual([[v['id'] for v in b] for b in agent._school_pending_batches(self.store, self.source['id'])],
                         [[v['id'] for v in values]], 'the claimed job is not regrouped and its standard waits')
        self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=1))['processed'], 0)
        self.model.assert_not_called()
        with self.store._db() as c:
            self.assertEqual(tuple(c.execute('SELECT attempts,done,fingerprint,next_try FROM agent_jobs WHERE id=?', (key,)).fetchone()), before)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()[0], 1)

    def _saved_fresh(self, texts, stamps):
        """Run one synthetic intake in its own isolated family; return the saved (title, body, due, state)."""
        case = type(self)('test_list_and_its_next_shared_standard_message_save_like_one_message')
        case.setUp()
        try:
            payload, refs, proposals = case._shared_messages(texts, stamps=stamps)
            case._use_replies(payload, [dict(proposals=proposals)])
            result = agent.run_once(case.app, case.now)
            self.assertEqual((result['failed'], result['processed'], case.model.call_count), (0, len(texts), 1), texts)
            with case.store._db() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
                tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)
                self.assertEqual((tasks[row['task_id']]['action'], tasks[row['task_id']]['due']), (row['body'], row['due']))
            return sorted((r['title'], r['body'], r['due'], r['state']) for r in rows)
        finally:
            case.doCleanups()

    def test_shared_standard_in_a_next_message_saves_like_the_same_message(self):
        """A: midnight (the standard's own day), B: 以上作业都, C: 两项都 — split and merged forms save alike."""
        undated = '英语，完成两项要求：1. 朗读Unit 8课文两遍；2. 完成练习卷第2–4题。'
        morning = ('2026-10-15T07:58:00+08:00', '2026-10-15T07:59:00+08:00')
        for listing, standard, stamps in (
                (undated, '以上两项都今天完成并请家长签字。', ('2026-10-15T23:59:00+08:00', '2026-10-16T00:00:00+08:00')),
                (self.SHARED_LIST, '以上作业都请家长核对并在记录本签字。', morning),
                (self.SHARED_LIST, '两项都请家长核对并在记录本签字。', morning),
                (self.SHARED_LIST, '上述两项均请家长核对并在记录本签字。', morning)):
            with self.subTest(standard=standard):
                split = self._saved_fresh([listing, standard], stamps)
                merged = self._saved_fresh([listing + standard], stamps[1:] if listing is undated else stamps[:1])
                self.assertEqual(split, merged)
                self.assertEqual([('2026-10-16', 'accepted')] * 2, [(row[2], row[3]) for row in split])
                self.assertTrue(all(standard.rstrip('。') in row[1] for row in split))

    def test_p11_claimed_batch_recovers_completely_when_due_without_a_new_budget(self):
        payload, refs = self._p11_payload()
        self.store.ingest(payload)
        values = payload['messages'][:6]
        old = 'messages:' + agent._hash([self.source['id'], [v['id'] for v in values]])[:40]
        fp = self.store._job(old, dict(school_learning_policy=8, messages=values), self.now, model=True)
        self.store._fail(old, self.now, fingerprint=fp, reason='虚构旧批冷却')
        proposals = [fixtures.school_proposal(
            title_quote=quote, due='2026-10-16', evidence=[dict(ref=ref) for ref in refs[5:]],
            learning_subject='英语', task_title='英语：' + quote, task_goal=quote + '；以上两项均请家长核对并在记录本签字。',
            task_state='ready', task_reason='虚构回执：本项行动与共同核对签字标准明确。', task_purpose='learning')
            for quote in self.SHARED_ACTIONS]
        batches = []

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            evidence = json.loads(messages[-1]['content'])['evidence']
            batches.append([e['ref'] for e in evidence])
            if batches[-1] == refs[5:]:return copy.deepcopy(dict(proposals=proposals))
            return dict(proposals=[fixtures.school_proposal(title_quote=e['text'], evidence=[dict(ref=e['ref'])],
                task_state='reference', task_purpose='unknown', task_reason='虚构通知按原文保留。') for e in evidence])

        self.model.side_effect = reply
        def jobs():
            with self.store._db() as c:
                return {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'")}
        frozen = jobs()[old]
        for minute in (1, 4):
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=minute))['processed'], 0)
            self.assertEqual(jobs(), {old: frozen}, 'cooling keeps the original key, fingerprint, attempts and retry time')
        self.model.assert_not_called()
        for minute in (5, 6, 7, 8, 10, 15):
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=minute))['failed'], 0)
        self.assertEqual(batches, [refs[:5], refs[5:]], 'the due batch is continued by its head and its complete last publication')
        after = jobs()
        head = 'messages:' + agent._hash([self.source['id'], [v['id'] for v in values[:5]]])[:40]
        tail = 'messages:' + agent._hash([self.source['id'], ['16', '17']])[:40]
        self.assertEqual(set(after), {old, head, tail})
        self.assertEqual((after[old]['fingerprint'], after[old]['attempts'], after[old]['done']), (frozen['fingerprint'], 1, 1))
        self.assertIn(head, after[old]['error']);self.assertIn(tail, after[old]['error'])
        self.assertTrue(frozen['error'] and after[old]['error'].startswith(frozen['error']), 'the original failure text is kept first')
        self.assertEqual([(after[k]['attempts'], after[k]['done']) for k in (head, tail)], [(2, 1), (2, 1)],
                         'successors start from the original attempt, never from a fresh budget')
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 0)
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        standard_rows = [r for r in rows if refs[6] in [e['ref'] for e in json.loads(r['evidence'])]]
        self.assertEqual(len(standard_rows), 2, 'no generic pending item for the standard')
        for row in standard_rows:
            self.assertIn('以上两项均请家长核对并在记录本签字', row['body'])
            self.assertEqual((row['due'], row['state']), ('2026-10-16', 'accepted'))

    def _p11_old_prefix_jobs(self, prefix_value=None):
        """The older append form: claimed jobs for the first five and the first six originals, both cooling from attempt 1."""
        payload, refs = self._p11_payload()
        self.store.ingest(payload)
        keys = []
        for count, value in ((5, prefix_value), (6, None)):
            values = payload['messages'][:count]
            key = 'messages:' + agent._hash([self.source['id'], [v['id'] for v in values]])[:40]
            fp = self.store._job(key, value or dict(school_learning_policy=8, messages=values), self.now, model=True)
            self.store._fail(key, self.now, fingerprint=fp, reason='虚构旧批冷却' + str(count))
            keys.append(key)
        with self.store._db() as c:
            frozen = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'")}
        return payload, refs, keys, frozen

    def test_p11_same_fingerprint_old_prefix_job_is_reused_as_the_due_head(self):
        payload, refs, (five, six), frozen = self._p11_old_prefix_jobs()
        proposals = [fixtures.school_proposal(
            title_quote=quote, due='2026-10-16', evidence=[dict(ref=ref) for ref in refs[5:]],
            learning_subject='英语', task_title='英语：' + quote, task_goal=quote + '；以上两项均请家长核对并在记录本签字。',
            task_state='ready', task_reason='虚构回执：本项行动与共同核对签字标准明确。', task_purpose='learning')
            for quote in self.SHARED_ACTIONS]
        batches = []

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            evidence = json.loads(messages[-1]['content'])['evidence']
            batches.append([e['ref'] for e in evidence])
            if batches[-1] == refs[5:]:return copy.deepcopy(dict(proposals=proposals))
            return dict(proposals=[fixtures.school_proposal(title_quote=e['text'], evidence=[dict(ref=e['ref'])],
                task_state='reference', task_purpose='unknown', task_reason='虚构通知按原文保留。') for e in evidence])

        self.model.side_effect = reply
        self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=4))['processed'], 0)
        self.model.assert_not_called()
        for minute in (5, 6, 7, 8, 10, 15):
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=minute))['failed'], 0)
        self.assertEqual(batches, [refs[:5], refs[5:]])
        tail = 'messages:' + agent._hash([self.source['id'], ['16', '17']])[:40]
        with self.store._db() as c:
            after = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'")}
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        self.assertEqual(set(after), {five, six, tail})
        for key in (five, six):
            self.assertEqual(after[key]['fingerprint'], frozen[key]['fingerprint'])
        self.assertTrue(frozen[six]['error'] and after[six]['error'].startswith(frozen[six]['error']), 'the continued job keeps its failure text')
        # The reused head then succeeded on its own key: the existing success path clears its retry state as for any recovery.
        self.assertEqual((after[five]['error'], after[five]['next_try']), ('', ''))
        self.assertEqual([(after[k]['attempts'], after[k]['done']) for k in (five, six, tail)], [(2, 1), (1, 1), (2, 1)])
        self.assertIn(five, after[six]['error']);self.assertIn(tail, after[six]['error'])
        standard_rows = [r for r in rows if refs[6] in [e['ref'] for e in json.loads(r['evidence'])]]
        self.assertEqual([(r['due'], r['state']) for r in standard_rows], [('2026-10-16', 'accepted')] * 2)
        self.assertTrue(all('以上两项均请家长核对并在记录本签字' in r['body'] for r in standard_rows))
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 0)

    def test_p11_conflicting_successor_key_runs_nothing_and_keeps_every_original(self):
        payload, refs, (five, six), frozen = self._p11_old_prefix_jobs(
            prefix_value=dict(school_learning_policy=7, messages=['虚构旧策略输入']))
        self.assertNotEqual(frozen[five]['fingerprint'], agent._hash(dict(school_learning_policy=8, messages=payload['messages'][:5])))
        for minute in (5, 6, 10):
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=minute))['processed'], 0)
        self.model.assert_not_called()
        with self.store._db() as c:
            after = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'")}
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE kind='school'").fetchone()[0], 0)
        self.assertEqual(set(after), {five, six})
        self.assertEqual(after[five], frozen[five])
        self.assertEqual({k: after[six][k] for k in ('fingerprint', 'attempts', 'done', 'next_try')},
                         {k: frozen[six][k] for k in ('fingerprint', 'attempts', 'done', 'next_try')})
        self.assertTrue(after[six]['error'].startswith(frozen[six]['error']))
        self.assertEqual(after[six]['error'].count('不能安全接续'), 1)
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 7)

    def test_p11_exhausted_batch_keeps_its_visible_state_and_waits_for_manual_retry(self):
        payload, refs = self._p11_payload()
        self.store.ingest(payload)
        values = payload['messages'][:6]
        old = 'messages:' + agent._hash([self.source['id'], [v['id'] for v in values]])[:40]
        for minutes in (0, 6, 17):
            fp = self.store._job(old, dict(school_learning_policy=8, messages=values), self.now + dt.timedelta(minutes=minutes), model=True)
            self.store._fail(old, self.now + dt.timedelta(minutes=minutes), fingerprint=fp, reason='虚构固定失败')
        with self.store._db() as c:
            frozen = [tuple(r) for r in c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'")]
        self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=60))['processed'], 0)
        self.model.assert_not_called()
        with self.store._db() as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'")], frozen)
            self.assertIn('需人工重试', c.execute('SELECT error FROM agent_jobs WHERE id=?', (old,)).fetchone()[0])
        self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 7, 'the held standard stays visibly pending')

    def test_background_about_the_list_is_not_bound_as_a_standard(self):
        payload, refs, proposals = self._shared_messages([self.SHARED_LIST, '以上两项都很重要。'])
        upgraded = [dict(p, task_goal=p['title_quote'] + '；以上两项都很重要。') for p in proposals]
        self._use_replies(payload, [dict(proposals=upgraded)])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_unread_shared_standard_binds_nothing(self):
        self._assert_shared_rejected([self.SHARED_LIST, self.SHARED_STANDARD], unread_last=True)

    def test_receipt_omitting_the_shared_standard_is_rejected(self):
        self._assert_shared_rejected([self.SHARED_LIST, self.SHARED_STANDARD],
                                     cited=['message:' + self.source['id'] + ':11'])

    def test_shared_standard_as_a_third_task_is_rejected(self):
        payload, refs, proposals = self._shared_messages([self.SHARED_LIST, self.SHARED_STANDARD])
        third = fixtures.school_proposal(
            title_quote='以上两项均请家长核对并在记录本签字', due='2026-10-16', evidence=[dict(ref=refs[1])],
            learning_subject='英语', task_title='英语：家长核对签字', task_goal='以上两项均请家长核对并在记录本签字。',
            task_state='ready', task_reason='虚构错误回执把共同标准当成第三项。', task_purpose='learning')
        self._use_replies(payload, [dict(proposals=proposals + [third])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_one_exercise_with_numbered_print_check_and_sign_steps_stays_one_task(self):
        # This is a steps list, not a counted list of independent outcomes.
        # The ordinary reader already returns the correct single receipt;
        # native coverage must not require three separate tasks for its steps.
        payload, refs = self._ingest([
            '英语，明天完成一份练习卷作业，步骤如下：\n'
            '1. 单面打印练习卷；\n'
            '2. 完成练习卷第1–3题并自查；\n'
            '3. 请家长在这份练习卷上签字；第4题选做。'])
        exercise = fixtures.school_proposal(
            title_quote='完成练习卷第1–3题并自查', due='2026-10-06', evidence=[dict(ref=refs[0])],
            learning_subject='英语', task_title='英语：完成练习卷',
            task_goal='单面打印练习卷；完成练习卷第1–3题并自查；请家长在这份练习卷上签字；第4题选做。',
            task_state='ready', task_reason='同一份练习卷的准备、作答和签字步骤。', task_purpose='learning')
        self._use_replies(payload, [dict(proposals=[exercise])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            for clause in ('单面打印练习卷', '完成练习卷第1–3题并自查', '请家长在这份练习卷上签字', '第4题选做'):
                self.assertIn(clause, row['body'])
            self.assertEqual((row['state'], row['due']), ('accepted', '2026-10-06'))
            self.assertEqual([q['ref'] for q in json.loads(row['evidence'])], refs)
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
            self.assertEqual(len(tasks), 1)
            self.assertEqual((tasks[0]['id'], tasks[0]['action'], tasks[0]['original_status']),
                             (row['task_id'], row['body'], '待跟进'))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)

    def test_original_text_changed_inside_save_transaction_rolls_back_all_business_writes(self):
        payload, refs, reading, exercise = self._two_actions()
        self._use_replies(payload, [dict(proposals=[reading, exercise])])
        real_save = agent.Store._save
        real_current = agent.Store._school_selection_current
        saving = []
        injected = []

        def capture_save(store, key, fingerprint, items, *args, **kwargs):
            if kwargs.get('school_context'):
                saving.append(True)
            return real_save(store, key, fingerprint, items, *args, **kwargs)

        def changed_original(store, c, *args, **kwargs):
            if saving and c.in_transaction and not injected:
                message = copy.deepcopy(payload['messages'][1])
                message['text'] = '补充英语练习卷：第4题改为必做。'
                c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                          (agent._json(message), self.source['id'], message['id']))
                injected.append(True)
            return real_current(store, c, *args, **kwargs)

        # Fault injection uses the save connection after BEGIN IMMEDIATE.
        # It is not a claim that another writer can bypass SQLite's write lock.
        with patch.object(agent.Store, '_save', new=capture_save), \
                patch.object(agent.Store, '_school_selection_current', new=changed_original):
            result = agent.run_once(self.app, self.now)
        self.assertEqual(injected, [True], 'the fault must occur in the real save transaction')
        self._assert_rejected_batch(payload, result)

    def test_assigned_requirement_changed_inside_save_transaction_is_not_saved(self):
        payload, refs, reading, exercise = self._two_actions()
        self._use_replies(payload, [dict(proposals=[reading, exercise])])
        real_save = agent.Store._save
        real_current = agent.Store._school_selection_current
        inflight = []
        injected = []

        def capture_items(store, key, fingerprint, items, *args, **kwargs):
            if kwargs.get('school_context'):
                inflight[:] = items
            return real_save(store, key, fingerprint, items, *args, **kwargs)

        def changed_assignment(store, c, *args, **kwargs):
            current = real_current(store, c, *args, **kwargs)
            if current and c.in_transaction and inflight and not injected:
                selected = next(item for item in inflight if item['plan'].get('school_native_action'))
                selected['plan']['school_native_action']['quote'] = '朗读Unit 2课文三遍'
                injected.append(True)
            return current

        # Mutate the proof actually produced by _select, not a hand-built copy
        # of the coverage implementation. Full messages remain unchanged;
        # the real save transaction must recheck this assigned requirement.
        with patch.object(agent.Store, '_save', new=capture_items), \
                patch.object(agent.Store, '_school_selection_current', new=changed_assignment):
            result = agent.run_once(self.app, self.now)
        self.assertEqual(injected, [True], 'the assigned proof must change after the input check in the save transaction')
        self._assert_rejected_batch(payload, result)

    def _vocabulary_writing(self):
        payload, refs = self._ingest(['英语作业：朗读Unit 2课文两遍；将生词写进词汇本，每词两行。'])
        reading, writing = (fixtures.school_proposal(
            title_quote=quote, evidence=[dict(ref=refs[0])], learning_subject='英语',
            task_title='英语：' + quote, task_goal=goal, task_state='ready',
            task_reason='虚构固定回执，非模型质量证据。', task_purpose='learning')
            for quote, goal in [('朗读Unit 2课文两遍', '朗读Unit 2课文两遍。'),
                                ('将生词写进词汇本', '将生词写进词汇本，每词两行。')])
        return payload, refs, reading, writing

    def test_directed_writing_into_its_own_notebook_is_a_separate_outcome(self):
        payload, refs, reading, writing = self._vocabulary_writing()
        self._use_replies(payload, [dict(proposals=[reading, writing])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), 2)
            read = next(r for r in rows if '朗读' in r['body'])
            write = next(r for r in rows if '词汇本' in r['body'])
            self.assertIn('两遍', read['body'])
            self.assertNotIn('词汇本', read['body'])
            self.assertIn('每词两行', write['body'])
            self.assertNotIn('朗读', write['body'])
            self.assertEqual((read['due'], write['due']), ('', ''), 'no date is stated, so none is invented or borrowed')
            for row in rows:
                self.assertEqual([q['ref'] for q in json.loads(row['evidence'])], refs)
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
            self.assertEqual(sorted(t['id'] for t in tasks), sorted(r['task_id'] for r in rows))
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],
                             payload['messages'], 'the complete original stays with both outcomes')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)

    def test_directed_outcome_merged_into_its_sibling_rejects_the_whole_batch(self):
        payload, refs, reading, writing = self._vocabulary_writing()
        merged = dict(reading, task_goal='朗读Unit 2课文两遍；将生词写进词汇本，每词两行。')
        self._use_replies(payload, [dict(proposals=[merged])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_directed_outcomes_keep_their_own_conditions_without_splitting_same_work_steps(self):
        split = {
            '语文作业：背诵《静夜思》；把好词好句摘抄到积累本上，不少于五句。':
                ['背诵《静夜思》', '把好词好句摘抄到积累本上，不少于五句'],
            '数学作业：完成练习册第12页，把错题抄在错题本上，并写出正确解法。':
                ['完成练习册第12页', '把错题抄在错题本上，并写出正确解法'],
            '英语：将新单词记在单词卡上，每张卡一个词；跟读Unit 3对话三遍。':
                ['将新单词记在单词卡上，每张卡一个词', '跟读Unit 3对话三遍'],
            '语文作业：朗读第5课两遍，将本课生字写入田字格本，每字三遍。':
                ['朗读第5课两遍', '将本课生字写入田字格本，每字三遍'],
        }
        for text, quotes in split.items():
            with self.subTest(text=text):
                self.assertEqual([a['quote'] for a in agent._school_native_blocks(text)], quotes)
        # Answers, uploads and working of the same exercise are its steps, not another homework.
        for text in ['数学作业：完成练习卷第1–3题；将答案写在作业本上；完成后自查并请家长签字。',
                     '英语作业：完成练习卷第1–3题；把完成的练习卷拍照上传到班级群。',
                     '数学作业：完成练习册第8页；把计算过程写在草稿本上。']:
            with self.subTest(text=text):
                self.assertEqual(len(agent._school_native_blocks(text)), 1)
        # Administrative handbacks, parent notes and plain notices never become learning outcomes.
        for text in ['请家长将回执签字后交回。', '请将意见写在家校联系本上。', '本周五学校开放日，欢迎家长来校参观。']:
            with self.subTest(text=text):
                self.assertEqual(agent._school_native_blocks(text), [])

    def _keyword_note_writing(self):
        payload, refs = self._ingest(['英语作业：朗读Unit 6课文两遍；把关键词写在便签上，每词三遍。'],
                                     ['synthetic-english-teacher-vocabulary'])
        reading, writing = (fixtures.school_proposal(
            title_quote=quote, evidence=[dict(ref=refs[0])], learning_subject='英语',
            task_title='英语：' + quote, task_goal=goal, task_state='ready',
            task_reason='虚构固定回执，非模型质量证据。', task_purpose='learning')
            for quote, goal in [('朗读Unit 6课文两遍', '朗读Unit 6课文两遍。'),
                                ('把关键词写在便签上', '把关键词写在便签上，每词三遍。')])
        return payload, refs, reading, writing

    def test_disclosed_writing_onto_a_note_is_its_own_outcome_with_its_own_count(self):
        payload, refs, reading, writing = self._keyword_note_writing()
        self._use_replies(payload, [dict(proposals=[reading, writing])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), 2)
            read = next(r for r in rows if '朗读' in r['body'])
            write = next(r for r in rows if '便签' in r['body'])
            self.assertIn('两遍', read['body'])
            self.assertNotIn('便签', read['body'])
            self.assertNotIn('三遍', read['body'])
            self.assertIn('每词三遍', write['body'])
            self.assertNotIn('朗读', write['body'])
            self.assertNotIn('两遍', write['body'])
            self.assertEqual((read['due'], write['due']), ('', ''), 'no date is stated, so none is invented')
            for row in rows:
                self.assertEqual([q['ref'] for q in json.loads(row['evidence'])], refs)
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
            self.assertEqual(sorted(t['id'] for t in tasks), sorted(r['task_id'] for r in rows))
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],
                             payload['messages'], 'the complete original stays with both outcomes')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)

    def test_disclosed_note_writing_merged_into_reading_rejects_the_whole_batch(self):
        payload, refs, reading, writing = self._keyword_note_writing()
        merged = dict(reading, task_goal='朗读Unit 6课文两遍；把关键词写在便签上，每词三遍。')
        self._use_replies(payload, [dict(proposals=[merged])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_directed_writing_closes_on_a_bounded_destination_not_a_destination_list(self):
        # Any short destination closed by its clause ends the phrase; its own count stays with it, first or later.
        split = {
            '语文作业：背诵第3课；把好词摘抄在作文纸上，不少于五个。':
                ['背诵第3课', '把好词摘抄在作文纸上，不少于五个'],
            '把生词写在课本空白处，每个两遍；跟读Unit 4对话。':
                ['把生词写在课本空白处，每个两遍', '跟读Unit 4对话'],
            '英语作业：朗读Unit 6课文两遍，把关键词写在便签上，每词三遍。':
                ['朗读Unit 6课文两遍', '把关键词写在便签上，每词三遍'],
        }
        for text, quotes in split.items():
            with self.subTest(text=text):
                self.assertEqual([a['quote'] for a in agent._school_native_blocks(text)], quotes)
        # Working of the same exercise and items to bring stay with their own work.
        for text in ['数学作业：完成练习册第8页；把计算过程写在练习纸背面。',
                     '英语作业：背诵Unit 6单词；把单词卡带到学校。']:
            with self.subTest(text=text):
                self.assertEqual(len(agent._school_native_blocks(text)), 1)
        # A parent's errand, a form and packing items never become learning outcomes.
        for text in ['请家长将孩子体温记在体温卡上。', '请将接送人电话写在回执上。', '请把文具整理到书包里。']:
            with self.subTest(text=text):
                self.assertEqual(agent._school_native_blocks(text), [])

    def _administrative_notice(self, text):
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time=self.now.isoformat(), kind='text',
                                    sender='虚构学校办公室', sender_id='synthetic-school-office', text=text, unread=False)]
        self.store.ingest(payload)
        return payload, 'message:' + self.source['id'] + ':11'

    def _admin_proposal(self, ref, quote, title, goal):
        return fixtures.school_proposal(title_quote=quote, evidence=[dict(ref=ref)], learning_subject='',
                                        task_title=title, task_goal=goal, task_state='ready',
                                        task_reason='全虚构固定行政回执，不是模型质量证据。', task_purpose='admin')

    def test_disclosed_directed_writing_under_an_administrative_heading_keeps_its_admin_purpose(self):
        # Writing an object somewhere is one outcome; the phrase alone does not make it learning.
        text = '学校行政事项：请同学把校车申请理由写在A4纸上，供老师审核。'
        payload, ref = self._administrative_notice(text)
        self._use_replies(payload, [dict(proposals=[
            self._admin_proposal(ref, '把校车申请理由写在A4纸上', '填写校车申请理由', text)])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), 1)
            self.assertIn('校车申请理由', rows[0]['body'])
            self.assertEqual(rows[0]['due'], '', 'no date is stated, so none is invented')
            self.assertEqual([q['ref'] for q in json.loads(rows[0]['evidence'])], [ref])
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
            self.assertEqual([t['id'] for t in tasks], [rows[0]['task_id']])
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],
                             payload['messages'], 'the complete original stays with the outcome')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)

    def test_administrative_writing_beside_a_form_stays_its_own_outcome(self):
        text = '学校行政事项：请家长签署校车安全承诺书；请同学把校车申请理由写在A4纸上，供老师审核。'
        payload, ref = self._administrative_notice(text)
        sign = self._admin_proposal(ref, '签署校车安全承诺书', '签署校车安全承诺书', '请家长签署校车安全承诺书。')
        write = self._admin_proposal(ref, '把校车申请理由写在A4纸上', '填写校车申请理由',
                                     '请同学把校车申请理由写在A4纸上，供老师审核。')
        self._use_replies(payload, [dict(proposals=[sign, write])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), 2)
            self.assertNotIn('承诺书', next(r for r in rows if '申请理由' in r['body'])['body'])
            self.assertNotIn('申请理由', next(r for r in rows if '承诺书' in r['body'])['body'])
            self.assertEqual([r['due'] for r in rows], ['', ''])

    def test_administrative_writing_merged_into_its_form_rejects_the_whole_batch(self):
        text = '学校行政事项：请家长签署校车安全承诺书；请同学把校车申请理由写在A4纸上，供老师审核。'
        payload, ref = self._administrative_notice(text)
        merged = self._admin_proposal(ref, '签署校车安全承诺书', '签署承诺书并写申请理由', text)
        self._use_replies(payload, [dict(proposals=[merged])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_open_destination_writing_under_a_subject_heading_still_rejects_an_admin_reply(self):
        # The subject heading keeps the writing a learning outcome: relabelling it administrative is not saved.
        payload, refs, reading, writing = self._keyword_note_writing()
        admin = dict(writing, task_purpose='admin', learning_subject='')
        self._use_replies(payload, [dict(proposals=[reading, admin])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))


    def test_disclosed_subject_word_does_not_turn_a_plainly_administrative_writing_into_learning(self):
        # D01 full entry: a subject word in the heading is context; the body's own administrative use stands.
        text = '英语课行政事项：请同学把校车申请理由写在A4纸上，供学校办公室登记。'
        payload, ref = self._administrative_notice(text)
        self._use_replies(payload, [dict(proposals=[
            self._admin_proposal(ref, '把校车申请理由写在A4纸上', '填写校车申请理由', text)])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), 1)
            self.assertIn('校车申请理由', rows[0]['body'])
            self.assertEqual(rows[0]['due'], '', 'no date is stated, so none is invented')
            self.assertEqual([q['ref'] for q in json.loads(rows[0]['evidence'])], [ref])
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
            self.assertEqual([t['id'] for t in tasks], [rows[0]['task_id']])
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],
                             payload['messages'], 'the complete original stays with the outcome')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)

    def test_model_input_asks_only_for_purposes_its_schema_allows(self):
        # The internal ba-phrase outcome marker is not a reply value: every purpose the input asks for is allowed.
        text = '学校行政事项：请同学把校车申请理由写在A4纸上，供老师审核。'
        payload, ref = self._administrative_notice(text)
        self._use_replies(payload, [dict(proposals=[
            self._admin_proposal(ref, '把校车申请理由写在A4纸上', '填写校车申请理由', text)])])
        agent.run_once(self.app, self.now)
        messages, schema = self.model.call_args.args[:2]
        allowed = set(schema['properties']['proposals']['items']['properties']['task_purpose']['enum'])
        actions = json.loads(messages[-1]['content'])['required_native_actions']
        self.assertTrue(actions)
        for action in actions:
            asked = [action['purpose']] if 'purpose' in action else action.get('purpose_options', [])
            self.assertTrue(asked and set(asked) <= allowed, action)

    def test_learning_writing_under_a_homework_heading_still_rejects_an_admin_reply(self):
        # The whole original reads as learning, so an administrative relabel is not saved.
        text = '英语作业：把生词写在卡片上，每词三遍。'
        payload, ref = self._administrative_notice(text)
        self._use_replies(payload, [dict(proposals=[self._admin_proposal(ref, '把生词写在卡片上', '写生词卡片', text)])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def _mixed_purpose_notice(self):
        # M01 full entry: one reading and one administrative writing in the same school message.
        payload, ref = self._administrative_notice('英语事项：朗读Unit 2课文两遍；将校服尺码写在便签上，供学校办公室统计订购信息。')
        reading = fixtures.school_proposal(title_quote='朗读Unit 2课文两遍', evidence=[dict(ref=ref)],
                                           learning_subject='英语', task_title='朗读Unit 2课文两遍',
                                           task_goal='朗读Unit 2课文两遍。', task_state='ready',
                                           task_reason='全虚构固定学习回执，不是模型质量证据。', task_purpose='learning')
        sizes = self._admin_proposal(ref, '将校服尺码写在便签上', '记录校服尺码',
                                     '将校服尺码写在便签上，供学校办公室统计订购信息。')
        return payload, ref, reading, sizes

    def test_disclosed_sibling_reading_does_not_turn_an_administrative_writing_into_learning(self):
        payload, ref, reading, sizes = self._mixed_purpose_notice()
        self._use_replies(payload, [dict(proposals=[reading, sizes])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), 2)
            read_row = next(r for r in rows if '朗读' in r['body'])
            size_row = next(r for r in rows if '校服尺码' in r['body'])
            self.assertEqual([json.loads(r['plan'])['school_task']['purpose'] for r in (read_row, size_row)],
                             ['learning', 'admin'], 'each outcome keeps the use of its own requirement')
            self.assertIn('供学校办公室统计订购信息', size_row['body'])
            self.assertNotIn('校服', read_row['body'])
            self.assertNotIn('朗读', size_row['body'])
            self.assertNotIn('英语', json.dumps(json.loads(size_row['plan'])['school_task'], ensure_ascii=False),
                             'the subject stays with the reading')
            self.assertEqual([r['due'] for r in rows], ['', ''], 'no date is stated, so none is invented or borrowed')
            for row in rows:
                self.assertEqual([q['ref'] for q in json.loads(row['evidence'])], [ref])
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
            self.assertEqual(sorted(t['id'] for t in tasks), sorted(r['task_id'] for r in rows))
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],
                             payload['messages'], 'the complete original stays with both outcomes')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)
        messages, schema = self.model.call_args.args[:2]
        allowed = set(schema['properties']['proposals']['items']['properties']['task_purpose']['enum'])
        actions = json.loads(messages[-1]['content'])['required_native_actions']
        self.assertEqual(len(actions), 2)
        asked = [[a['purpose']] if 'purpose' in a else a.get('purpose_options', []) for a in actions]
        for options in asked:
            self.assertTrue(options and set(options) <= allowed, actions)
        self.assertEqual(asked[0], ['learning'])
        self.assertIn('admin', asked[1], 'a sibling reading does not decide the writing\'s use')

    def test_disclosed_mixed_message_still_rejects_an_administrative_reading(self):
        payload, ref, reading, sizes = self._mixed_purpose_notice()
        admin_reading = dict(reading, task_purpose='admin', learning_subject='')
        self._use_replies(payload, [dict(proposals=[admin_reading, sizes])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_each_outcome_reads_its_use_from_its_own_requirement_and_shared_heading(self):
        def asked(text):
            return [a.get('purpose') or tuple(a['purpose_options'])
                    for a in map(agent._school_native_view, agent._school_native_blocks(text))]
        options = ('learning', 'admin')
        self.assertEqual(asked('英语事项：朗读Unit 2课文两遍；将校服尺码写在便签上，供学校办公室统计订购信息。'), ['learning', options])
        self.assertEqual(asked('英语事项：将校服尺码写在便签上，供学校办公室统计订购信息；朗读Unit 2课文两遍。'), [options, 'learning'])
        # The writing's own learning object still makes it learning; it is not lent to the administrative sibling.
        self.assertEqual(asked('英语事项：将校服尺码写在便签上，供学校办公室统计订购信息；把课文生词写在卡片上，每词三遍。'),
                         [options, 'learning'])
        # A heading stated for every outcome still applies to each.
        self.assertEqual(asked('英语作业：朗读Unit 2课文两遍；将校服尺码写在便签上。'), ['learning', 'learning'])

    # The frozen synthetic case of the late shared standard: the list is saved as two tasks by one run_once; the same
    # stable teacher's all-items standard is collected 60 seconds later and read alone by the next run_once.
    LATE_SOURCE = 'synthetic-late-group'
    LATE_LIST = '英语，明天完成两项要求：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题。'
    LATE_STANDARD = '以上两项均请家长核对并在记录本签字。'
    LATE_ACTIONS = ('朗读Unit 2课文两遍', '完成练习卷第1–3题')
    # Frozen receipt IDs from the recorded run; real task IDs are regenerated and are bound from the first run.
    LATE_FROZEN_TARGETS = ('AGENT-cbc1946298d488488dba7bf5', 'AGENT-6706e356f8e23dbf85bd27ae')

    def _late_message(self, ident, time, text, sender_id='synthetic-stable-teacher', **extra):
        return dict(dict(id=ident, message_order=ident, time=time, kind='text', sender='虚构英语老师',
                         sender_id=sender_id, text=text, unread=False), **extra)

    def _late_ingest(self, expected, messages, checked):
        self.store.ingest(dict(source_id=self.LATE_SOURCE, expected_cursor=expected, cursor=messages[-1]['id'],
                               checked_at=checked, last_message_time=messages[-1]['time'], error='', messages=messages))

    def _late_first_reply(self, ref):
        return dict(proposals=[fixtures.school_proposal(
            title_quote=quote, due='2026-10-16', evidence=[dict(ref=ref)], learning_subject='英语',
            task_title=title, task_goal=quote + '。', task_state='ready', task_reason=reason, task_purpose='learning')
            for quote, title, reason in ((self.LATE_ACTIONS[0], '英语：朗读Unit 2课文', '第一项明确。'),
                                         (self.LATE_ACTIONS[1], '英语：完成练习卷', '第二项明确。'))])

    def _late_second_reply(self, ref, targets, standard=None, **values):
        """The frozen append/ready receipt with each frozen target replaced by the task the first run actually saved."""
        standard = standard or self.LATE_STANDARD
        return dict(proposals=[fixtures.school_proposal(**dict(dict(
            title_quote=standard, due='', evidence=[dict(ref=ref)], learning_subject='英语',
            task_title='英语：' + quote, task_goal=standard, task_state='ready',
            task_reason='明确以上两项共同完成标准，追加到已存原作业。', task_change='append', task_target_id=target,
            task_purpose='learning'), **values)) for quote, target in zip(self.LATE_ACTIONS, targets)])

    def _late_first_run(self):
        """Run 1 of the frozen case: the list alone becomes two accepted tasks; returns the task IDs in action order."""
        self.source['id'] = self.LATE_SOURCE
        self.fixture.config()
        self.now = self.fixture.now = dt.datetime(2026, 10, 15, 14, tzinfo=agent.TZ)
        first = self._late_message('11', '2026-10-15T14:00:00+08:00', self.LATE_LIST)
        self._late_ingest('10', [first], '2026-10-15T14:00:00+08:00')
        ref = 'message:' + self.LATE_SOURCE + ':11'
        replies = [self._late_first_reply(ref)]
        self.model.side_effect = lambda messages, *args, **kwargs: copy.deepcopy(replies.pop(0))
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['state'] == 'accepted' and r['task_id'] for r in rows))
        # Bound from this run's saved tasks; whether they equal the frozen receipt's IDs is not a premise of any check.
        targets = tuple(next(r['task_id'] for r in rows if quote in r['body']) for quote in self.LATE_ACTIONS)
        self.assertEqual(len(set(targets)), 2)
        return first, targets

    def _late_second_run(self, targets, *, message=None, reply=None, at=None):
        later = message or self._late_message('12', '2026-10-15T14:01:00+08:00', self.LATE_STANDARD)
        with self.store._db() as c:
            cursor = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (self.LATE_SOURCE,)).fetchone()[0]
        self._late_ingest(cursor, [later], later['time'] if not at else at.isoformat())
        ref = 'message:' + self.LATE_SOURCE + ':' + later['id']
        replies = [reply or self._late_second_reply(ref, targets)]
        seen = []

        def second(messages, schema, name, timeout=60, *, data_path=None):
            context = json.loads(messages[-1]['content'])
            seen.append([e['ref'] for e in context['evidence']])
            return copy.deepcopy(replies.pop(0))

        self.model.side_effect = second
        result = agent.run_once(self.app, at or dt.datetime(2026, 10, 15, 14, 1, tzinfo=agent.TZ))
        return result, ref, seen

    def _late_state(self):
        with self.store._db() as c:
            present = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return {table: [dict(r) for r in c.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in ('agent_items', 'agent_jobs', 'agent_messages', 'manual_tasks', 'task_updates', 'task_focus',
                                  'task_focus_history', 'records', 'study_items') if table in present}

    def _late_tasks(self, targets):
        with self.store._db() as c:
            updates = {r['id']: r['status'] for r in c.execute('SELECT id,status FROM task_updates')}
            return {t['id']: dict(t, status=self.app.task_status(t, updates.get(t['id']))) for t in self.app.tasks(c) if t['id'] in targets}

    def _late_scoped(self, task_id, message_id):
        return self.store.message(dict(child_id='child-1', source_id=self.LATE_SOURCE, message_id=message_id, task_id=task_id),
                                  self.app.upload_info)

    def _late_clock(self, at=dt.datetime(2026, 10, 15, 14, 1, tzinfo=agent.TZ)):
        """Freeze the system clock read without an argument (apply_school_change's same-day guard) to the case's round."""
        real = agent._now
        self.stack.enter_context(patch.object(agent, '_now', lambda value=None: real(value or at)))

    def test_late_shared_standard_reaches_each_saved_task_of_its_list(self):
        self._late_clock()
        first, targets = self._late_first_run()
        before = self._late_tasks(targets)
        with self.store._db() as c:
            canonicals = {r['task_id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
        real_apply, requests = agent.apply_school_change, []

        def recorded(app, store, obj, **kwargs):
            requests.append((copy.deepcopy(obj), kwargs))
            return real_apply(app, store, obj, **kwargs)

        with patch.object(agent, 'apply_school_change', side_effect=recorded):
            result, ref, seen = self._late_second_run(targets)
        self.assertEqual(sorted((obj['target_id'], kwargs) for obj, kwargs in requests),
                         sorted((t, dict(school_auto=True)) for t in targets), 'the existing automatic append path, once per task')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual(seen, [[ref]], 'the standard is read alone; no extra model call')
        state = self._late_state()
        self.assertEqual({t['id'] for t in state['manual_tasks']}, set(targets), 'no third task')
        appends = [r for r in state['agent_items'] if r['kind'] == 'school' and ref in r['evidence']]
        self.assertEqual(sorted((r['state'], r['task_id']) for r in appends), sorted(('accepted', t) for t in targets))
        after = self._late_tasks(targets)
        for quote, task_id in zip(self.LATE_ACTIONS, targets):
            task, old = after[task_id], before[task_id]
            self.assertEqual(task['action'], old['action'] + '\n补充要求：' + self.LATE_STANDARD)
            self.assertNotIn((set(self.LATE_ACTIONS) - {quote}).pop(), task['action'], 'the sibling outcome is never merged')
            self.assertEqual((task['title'], task['agenda']['due_on'], task['status']), (old['title'], old['agenda']['due_on'], old['status']))
            self.assertTrue(task['source'].startswith(old['source']), 'the original source 11 is kept first')
            self.assertIn('\n\n' + ref + '\n', task['source'])
            self.assertTrue(task['source'].endswith('\n' + self.LATE_STANDARD))
            canonical = state['agent_items'][[r['id'] for r in state['agent_items']].index(canonicals[task_id]['id'])]
            self.assertEqual((canonical['evidence'], canonical['body'], canonical['state']),
                             (canonicals[task_id]['evidence'], canonicals[task_id]['body'], 'accepted'))
            change, = json.loads(canonical['plan'])['school_changes']
            self.assertEqual((change['change'], change['goal'], change['auto_added']), ('append', self.LATE_STANDARD, True))
            for message_id, text in (('11', self.LATE_LIST), ('12', self.LATE_STANDARD)):
                view = self._late_scoped(task_id, message_id)
                self.assertEqual((view['task_id'], view['message']['text']), (task_id, text))
        self.assertEqual(state['records'], [])
        # The lost-receipt replay of the same request changes nothing; the next natural tick neither calls nor writes.
        for obj, kwargs in requests:
            self.assertTrue(real_apply(self.app, self.store, obj, **kwargs)['replayed'])
        self.model.side_effect = AssertionError('no model call on replay')
        tick = agent.run_once(self.app, dt.datetime(2026, 10, 15, 14, 8, tzinfo=agent.TZ))
        self.assertEqual((tick['failed'], tick['processed']), (0, 0))
        self.assertEqual(self._late_state()['agent_items'], state['agent_items'])
        self.assertEqual(self._late_tasks(targets), after)
        # Later feedback and completion stay on the same task through another tick.
        self.app.save_task(dict(id=targets[0], status='已完成', note='虚构家长核对：已朗读并签字。'))
        done = self._late_tasks(targets)
        agent.run_once(self.app, dt.datetime(2026, 10, 15, 14, 15, tzinfo=agent.TZ))
        self.assertEqual(self._late_tasks(targets), done)
        self.assertEqual(done[targets[0]]['status'], '已完成')

    def _late_variant(self, change_message=None, reply=None, extra=None, child_source=None):
        """One fresh synthetic family per variant: run 1 as frozen, then a changed second message or receipt."""
        case = type(self)('test_late_shared_standard_reaches_each_saved_task_of_its_list')
        case.setUp()
        try:
            first, targets = case._late_first_run()
            before = case._late_tasks(targets)
            message = case._late_message('12', '2026-10-15T14:01:00+08:00', case.LATE_STANDARD)
            message.update(change_message or {})
            if child_source:
                config = json.loads((case.fixture.data / 'agent.json').read_text())
                config['sources'].append(dict(case.source, id=child_source[0], child_id=child_source[1], cursor='10'))
                (case.fixture.data / 'agent.json').write_text(json.dumps(config))
                case.store.ingest(dict(source_id=child_source[0], expected_cursor='10', cursor=message['id'], checked_at=message['time'],
                                       last_message_time=message['time'], error='', messages=[message]))
                ref = 'message:' + child_source[0] + ':' + message['id']
                case.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply(ref, targets))
                result = agent.run_once(case.app, dt.datetime(2026, 10, 15, 14, 1, tzinfo=agent.TZ))
            else:
                messages = (extra or []) + [message]
                with case.store._db() as c:
                    cursor = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (case.LATE_SOURCE,)).fetchone()[0]
                case._late_ingest(cursor, messages, message['time'])
                refs = ['message:' + case.LATE_SOURCE + ':' + m['id'] for m in messages]
                value = reply(refs[-1], targets) if reply else case._late_second_reply(refs[-1], targets)
                for other in refs[:-1]:
                    value['proposals'].append(fixtures.school_proposal(title_quote='明天带跳绳', evidence=[dict(ref=other)],
                        task_state='reference', task_purpose='unknown', task_reason='虚构其他通知按原文保留。'))
                case.model.side_effect = lambda *args, **kwargs: copy.deepcopy(value)
                result = agent.run_once(case.app, dt.datetime(2026, 10, 15, 14, 1, tzinfo=agent.TZ))
            state = case._late_state()
            after = case._late_tasks(targets)
            for task_id in targets:
                self.assertEqual(after[task_id]['action'], before[task_id]['action'], 'no standard reaches a task unproven')
                self.assertEqual(after[task_id]['source'], before[task_id]['source'])
                with self.assertRaises(agent.AgentError):case._late_scoped(task_id, '12')
            self.assertEqual({t['id'] for t in state['manual_tasks']}, set(targets), 'never a third task')
            return result, [(r['state'], json.loads(r['plan'])['school_task']['state'], json.loads(r['plan'])['school_task']['change'])
                            for r in state['agent_items'] if r['kind'] == 'school' and r['task_id'] not in targets]
        finally:
            case.doCleanups()

    def test_late_shared_standard_unproven_relations_stay_for_review(self):
        review = [('pending', 'review', 'append')] * 2
        for name, change in (('other teacher', dict(sender_id='synthetic-other-teacher')),
                             ('stated count differs', dict(text='以上三项均请家长核对并在记录本签字。')),
                             ('true negation', dict(text='以上两项均不用家长签字。')),
                             ('incomplete original', dict(unread=True)),
                             ('outside the window', dict(time='2026-10-15T14:03:00+08:00')),
                             ('a date of its own', dict(text='以上两项都明天前请家长核对并在记录本签字。'))):
            with self.subTest(name):
                result, held = self._late_variant(change)
                self.assertEqual((result['failed'], result['processed']), (0, 1))
                self.assertEqual(held, review)
        with self.subTest('an independent message between'):
            other = self._late_message('12', '2026-10-15T14:00:30+08:00', '明天带跳绳。', sender_id='synthetic-other-teacher')
            result, held = self._late_variant(dict(id='13', message_order='13'), extra=[other])
            self.assertEqual((result['failed'], result['processed']), (0, 2))
            self.assertEqual(sorted(h for h in held if h[2] == 'append'), review)
            self.assertEqual([h[0] for h in held if h[2] != 'append'], ['pending'], 'the other notice keeps its own item')
        with self.subTest('another source of the same child'):
            new = lambda ref, targets: self._late_second_reply(ref, targets)
            result, held = self._late_variant(child_source=('synthetic-late-other', 'child-1'), reply=new)
            self.assertEqual(held, review)
        with self.subTest('another child'):
            third = lambda ref, targets: dict(proposals=[fixtures.school_proposal(
                title_quote=self.LATE_STANDARD, evidence=[dict(ref=ref)], learning_subject='英语', task_title='英语：家长核对签字',
                task_goal=self.LATE_STANDARD, task_state='ready', task_reason='虚构错误回执。', task_purpose='learning')])
            result, held = self._late_variant(child_source=('synthetic-late-sibling', 'child-2'), reply=third)
            self.assertEqual((result['failed'], held), (0, [('pending', 'review', 'new')]))

    def test_late_shared_standard_wrong_receipts_keep_the_batch_without_a_third_task(self):
        def new(ref, targets):
            return dict(proposals=[fixtures.school_proposal(
                title_quote=self.LATE_STANDARD, evidence=[dict(ref=ref)], learning_subject='英语', task_title='英语：家长核对签字',
                task_goal=self.LATE_STANDARD, task_state='ready', task_reason='虚构错误回执把共同标准当成新作业。', task_purpose='learning')])
        def partial(ref, targets):
            return dict(proposals=self._late_second_reply(ref, targets)['proposals'][:1])
        def twice(ref, targets):
            return self._late_second_reply(ref, (targets[0], targets[0]))
        def plus_new(ref, targets):
            return dict(proposals=self._late_second_reply(ref, targets)['proposals'] + new(ref, targets)['proposals'])
        for reply in (new, partial, twice, plus_new):
            with self.subTest(reply.__name__):
                result, held = self._late_variant(reply=reply)
                self.assertEqual((result['failed'], result['processed']), (1, 0))
                self.assertEqual(held, [], 'nothing of the rejected receipt is saved')

    def test_late_shared_standard_next_system_day_is_refused_and_kept_for_review(self):
        self._late_clock(dt.datetime(2026, 10, 16, 14, 1, tzinfo=agent.TZ))
        first, targets = self._late_first_run()
        before = self._late_tasks(targets)
        result, ref, seen = self._late_second_run(targets)
        self.assertEqual((result['failed'], result['processed']), (2, 1), 'each append is refused (409) on another day')
        self.assertEqual(self._late_tasks(targets), before, 'no task is changed')
        state = self._late_state()
        self.assertEqual({t['id'] for t in state['manual_tasks']}, set(targets), 'no third task')
        appends = {json.loads(r['plan'])['school_task']['target_id']: r for r in state['agent_items'] if ref in r['evidence']}
        self.assertEqual({t: (r['state'], json.loads(r['plan'])['school_task']['state']) for t, r in appends.items()},
                         {t: ('pending', 'review') for t in targets})

    def test_late_shared_standard_model_failure_writes_nothing_and_retries_the_same_job(self):
        self._late_clock()
        first, targets = self._late_first_run()
        later = self._late_message('12', '2026-10-15T14:01:00+08:00', self.LATE_STANDARD)
        self._late_ingest('11', [later], later['time'])
        before = self._late_state()
        self.model.side_effect = agent.family_llm.LLMDraftError('虚构503未写入')
        failed = agent.run_once(self.app, dt.datetime(2026, 10, 15, 14, 1, tzinfo=agent.TZ))
        self.assertEqual((failed['failed'], failed['processed']), (1, 0))
        after = self._late_state()
        for table in ('agent_items', 'agent_messages', 'manual_tasks', 'task_focus_history', 'records'):
            self.assertEqual(after.get(table), before.get(table), table)
        job, = [j for j in after['agent_jobs'] if j['id'].startswith('messages:') and not j['done']]
        ref = 'message:' + self.LATE_SOURCE + ':12'
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(self._late_second_reply(ref, targets))
        retried = agent.run_once(self.app, dt.datetime(2026, 10, 15, 14, 7, tzinfo=agent.TZ))
        self.assertEqual((retried['failed'], retried['processed']), (0, 1))
        done = next(j for j in self._late_state()['agent_jobs'] if j['id'] == job['id'])
        self.assertEqual((done['fingerprint'], done['attempts'], done['done']), (job['fingerprint'], 2, 1))
        self.assertTrue(all('补充要求：' + self.LATE_STANDARD in t['action'] for t in self._late_tasks(targets).values()))

    def test_late_shared_standard_respects_parent_edits_and_feedback(self):
        first, targets = self._late_first_run()
        record = self.app.save_record(dict(child='示例甲', day='2026-10-15', category='学习进展', subject='英语', title='虚构反馈',
                                           note='虚构家长反馈：已开始练习卷。', source='事项:' + targets[1])) \
            if hasattr(self.app, 'save_record') else None
        if record is None:
            with self.app.connect() as c:
                c.execute('INSERT INTO records(child,day,category,subject,title,note,source,created,linked_task_id) VALUES(?,?,?,?,?,?,?,?,?)',
                          ('示例甲', '2026-10-15', '学习进展', '英语', '虚构反馈', '虚构家长反馈：已开始练习卷。', '家长记录',
                           self.now.isoformat(), targets[1]))
        edited = []

        def parent_edit():
            with self.store._db() as c:
                focus = next(t for t in self.app.tasks(c) if t['id'] == targets[0])['focus']
            agent.family_task_focus.save(self.app, dict(id=targets[0], version=focus['version'], request_key='synthetic-late-edit',
                mode='later', next_action='等家长核对', waiting_for='', review_on='2026-10-16', goal='家长改写：只朗读第一段。'))
            edited.append(True)

        ref = 'message:' + self.LATE_SOURCE + ':12'
        reply = self._late_second_reply(ref, targets)

        def during_model(*args, **kwargs):
            parent_edit()
            return copy.deepcopy(reply)

        later = self._late_message('12', '2026-10-15T14:01:00+08:00', self.LATE_STANDARD)
        self._late_ingest('11', [later], later['time'])
        self.model.side_effect = during_model
        result = agent.run_once(self.app, dt.datetime(2026, 10, 15, 14, 1, tzinfo=agent.TZ))
        # The edited task's append is refused in its write transaction (409) and kept for review, counted as before.
        self.assertEqual((edited, result['failed'], result['processed']), ([True], 1, 1))
        tasks = self._late_tasks(targets)
        self.assertEqual(tasks[targets[0]]['action'], '家长改写：只朗读第一段。', 'a concurrent parent edit is never overwritten')
        self.assertNotIn(self.LATE_STANDARD, tasks[targets[1]]['action'], 'a task with feedback is not changed automatically')
        state = self._late_state()
        appends = {json.loads(r['plan'])['school_task']['target_id']: r for r in state['agent_items'] if ref in r['evidence']}
        self.assertEqual({t: (r['state'], json.loads(r['plan'])['school_task']['state']) for t, r in appends.items()},
                         {t: ('pending', 'review') for t in targets})
        self.assertEqual(len(state['records']), 1)


class SchoolActionAnchorTests(unittest.TestCase):
    """One fictional notice holding two English actions joined by a semicolon, through run_once's real _select/_save.

    The ledger locates only the dictation; the copying is an unlisted action on the existing general route. The
    retained real-model shape quoted the whole sentence for the copying, reaching into the listed dictation, so the
    batch stays refused with nothing written. Own-segment receipts are fixed local substitutes: they show the anchor
    contract reaches the model and the unchanged guards save, replay, date and correct each action, never that a
    product model now quotes this way.
    """
    setUp = SchoolNativeCoverageTests.setUp
    _assert_rejected_batch = SchoolNativeCoverageTests._assert_rejected_batch
    NOTICE = '英语：今晚把Unit 3单词每个抄写两遍，明天交；周五听写Unit 3单词。'
    SENT = '2026-10-07T19:15:00+08:00'

    def _notice(self):
        self.now = self.fixture.now = dt.datetime(2026, 10, 7, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time=self.SENT, kind='text', sender='示例英语老师',
                                    sender_id='synthetic-english', text=self.NOTICE, unread=False)]
        self.store.ingest(payload)
        return payload, 'message:' + self.source['id'] + ':11'

    def _replies(self, replies):
        calls = []

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual((name, data_path), ('family_agent_selection', self.app.DATA))
            calls.append((messages[0]['content'], json.loads(messages[-1]['content'])))
            self.assertLessEqual(len(calls), len(replies), 'replay must not request another model receipt')
            value = replies[len(calls) - 1]
            return copy.deepcopy(value(calls[-1][1]) if callable(value) else value)

        self.model.side_effect = reply
        return calls

    def _copying(self, ref, quote):
        # The retained receipt's own content; only title_quote varies between the refused and the own-segment shape.
        return fixtures.school_proposal(
            title_quote=quote, due='2026-10-08', evidence=[dict(ref=ref)], learning_subject='英语',
            task_title='英语：Unit 3单词抄写两遍', task_goal='今晚把Unit 3单词每个抄写两遍。\n明天交。',
            task_advice='抄写时按单词逐个核对拼写，完成后检查遍数。', task_state='ready',
            task_reason='原消息明确要求今晚抄写Unit 3单词每个两遍并明天交，按发送日2026-10-07换算为2026-10-08。',
            task_purpose='learning', task_submission='明天交抄写')

    def _dictation(self, ref):
        return fixtures.school_proposal(
            title_quote='周五听写Unit 3单词。', due='2026-10-09', evidence=[dict(ref=ref)], learning_subject='英语',
            task_title='英语：Unit 3单词听写（周五）', task_goal='周五听写Unit 3单词。',
            task_advice='可提前按Unit 3单词表自测拼写。', task_state='ready',
            task_reason='原消息明确周五听写Unit 3单词，按发送日2026-10-07换算为2026-10-09。', task_purpose='learning')

    def _rows(self):
        with self.store._db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]

    def _assert_two_actions_saved(self, quote):
        rows = self._rows()
        self.assertEqual(len(rows), 2, 'copying and dictation are two independent outcomes')
        copying, = [r for r in rows if '抄写' in r['title']]
        dictation, = [r for r in rows if '听写' in r['title']]
        # Each action keeps its own day: the copying's handback is tomorrow, the dictation is on Friday.
        self.assertEqual((copying['state'], copying['due']), ('accepted', '2026-10-08'))
        self.assertEqual((dictation['state'], dictation['due']), ('accepted', '2026-10-09'))
        for own in ('每个抄写两遍', '明天交'):
            self.assertIn(own, copying['body'])
        self.assertNotIn('听写', copying['body'])
        self.assertNotIn('抄写', dictation['body'])
        copy_plan, dictation_plan = json.loads(copying['plan']), json.loads(dictation['plan'])
        self.assertNotIn('school_native_action', copy_plan, 'the unlisted action keeps the existing general route')
        self.assertEqual(copy_plan['school_date_quote'], quote.strip())
        self.assertEqual(dictation_plan['school_native_action']['quote'], '周五听写Unit 3单词')
        with self.store._db() as c:
            tasks = {r['id']: r['due'] for r in c.execute('SELECT id,due FROM manual_tasks')}
            self.assertEqual(tasks, {copying['task_id']: '2026-10-08', dictation['task_id']: '2026-10-09'})
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            self.assertEqual([json.loads(r[0])['text'] for r in c.execute('SELECT payload FROM agent_messages')], [self.NOTICE])
        return copying, dictation

    def test_retained_whole_sentence_quote_stays_refused_until_an_own_segment_retry(self):
        payload, ref = self._notice()
        retained = [self._copying(ref, self.NOTICE[3:]), self._dictation(ref)]
        own = [self._copying(ref, '今晚把Unit 3单词每个抄写两遍，明天交'), self._dictation(ref)]
        calls = self._replies([dict(proposals=retained), dict(proposals=own)])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))
        prompt, context = calls[0]
        # Why the unchanged guard refuses: only the dictation is located and the copying quote reaches into it.
        self.assertEqual([a['quote'] for a in context['required_native_actions']], ['周五听写Unit 3单词'])
        self.assertIn(agent.SCHOOL_ACTION_ANCHOR, prompt)
        for clause in ('逐字使用该项quote', '不一定齐全', '不能包含或重叠任一已列项的quote和conditions'):
            self.assertIn(clause, prompt)
        retry = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((retry['failed'], retry['processed']), (0, 1))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], calls[0], 'the retry sends the same contract and context')
        self._assert_two_actions_saved('今晚把Unit 3单词每个抄写两遍，明天交')

    def test_own_segment_anchor_saves_each_action_once_with_its_own_date(self):
        # The segment may keep or drop its leading subject label and closing mark; neither reaches the dictation.
        for quote in ('今晚把Unit 3单词每个抄写两遍，明天交', '英语：今晚把Unit 3单词每个抄写两遍，明天交；'):
            with self.subTest(quote=quote):
                t = type(self)(methodName='runTest')
                t.setUp()
                try:
                    payload, ref = t._notice()
                    t._replies([dict(proposals=[t._copying(ref, quote), t._dictation(ref)])])
                    result = agent.run_once(t.app, t.now)
                    self.assertEqual((result['failed'], result['processed']), (0, 1))
                    before = t._assert_two_actions_saved(quote)
                    replay = agent.run_once(t.app, t.now + dt.timedelta(minutes=6))
                    self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
                    self.assertEqual(t.model.call_count, 1)
                    self.assertEqual(t._assert_two_actions_saved(quote), before, 'a replay never duplicates or rewrites')
                finally:
                    t.doCleanups()

    def test_quote_after_a_leading_filler_keeps_only_its_own_clause_day(self):
        text = '各位家长：请打印《秋游安全告知书》，家长签字后于10月10日前交回班主任，不需要盖章。另外周四学校体检，请孩子穿运动服。'
        ref = 'message:synthetic-school-a:3'
        evidence = [dict(ref=ref, text=text, time='2026-10-07T19:10:00+08:00', kind='text', publisher='publisher:synthetic-head',
                         content_incomplete=False, attachments=[], unread=False)]
        form = fixtures.school_proposal(
            title_quote='请打印《秋游安全告知书》，家长签字后于10月10日前交回班主任，不需要盖章。', due='2026-10-10',
            evidence=[dict(ref=ref)], task_title='打印《秋游安全告知书》并签字交回', task_state='ready', task_purpose='admin',
            task_goal='打印《秋游安全告知书》，家长签字后于10月10日前交回班主任，不需要盖章。', task_reason='虚构回执。')
        for quote, due, expected in (('周四学校体检，请孩子穿运动服', '2026-10-08', ('2026-10-08', 'ready')),
                                     ('另外周四学校体检，请孩子穿运动服', '2026-10-08', ('2026-10-08', 'ready')),
                                     ('周四学校体检，请孩子穿运动服', '2026-10-10', ('', 'review')),
                                     ('学校体检，请孩子穿运动服', '2026-10-08', ('', 'review'))):
            exam = fixtures.school_proposal(
                title_quote=quote, due=due, evidence=[dict(ref=ref)], task_title='周四体检：穿运动服', task_state='ready',
                task_goal='周四学校体检，请孩子穿运动服。', task_purpose='admin', task_reason='虚构回执。')
            with self.subTest(quote=quote, due=due), patch.object(agent.family_llm, '_chat_json',
                                                                 return_value=dict(proposals=[form, exam])):
                items = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-07')
                item, = [i for i in items if '体检' in i['title']]
                self.assertEqual((item['due'], item['plan']['school_task']['state']), expected)
                other, = [i for i in items if '告知书' in i['title']]
                self.assertEqual((other['due'], other['plan']['school_task']['state']), ('2026-10-10', 'ready'))

    def test_later_correction_batch_reviews_only_the_action_it_names(self):
        payload, ref = self._notice()
        correction = '更正：周五的Unit 3单词听写改到下周一。'

        def update(context):
            target, = [t['id'] for t in context['school_tasks'] if '听写' in t['title']]
            return dict(proposals=[fixtures.school_proposal(
                title_quote=correction, due='', evidence=[dict(ref=later_ref)], learning_subject='英语',
                task_title='英语：Unit 3单词听写改期', task_goal='Unit 3单词听写由周五改到下周一。', task_state='review',
                task_reason='老师更正了原听写日期，原事项待家长核对后改期。', task_change='update',
                task_target_id=target, task_purpose='learning')])

        later_ref = 'message:' + self.source['id'] + ':12'
        calls = self._replies([dict(proposals=[self._copying(ref, '今晚把Unit 3单词每个抄写两遍，明天交'),
                                               self._dictation(ref)]), update])
        self.assertEqual(agent.run_once(self.app, self.now)['processed'], 1)
        copying, dictation = self._assert_two_actions_saved('今晚把Unit 3单词每个抄写两遍，明天交')
        later = dict(id='12', message_order='12', time='2026-10-08T07:30:00+08:00', kind='text', sender='示例英语老师',
                     sender_id='synthetic-english', text=correction, unread=False)
        self.store.ingest(dict(source_id=self.source['id'], expected_cursor='11', cursor='12', checked_at=later['time'],
                               last_message_time=later['time'], error='', messages=[later]))
        result = agent.run_once(self.app, dt.datetime(2026, 10, 8, 8, tzinfo=agent.TZ))
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual([e['ref'] for e in calls[1][1]['evidence']], [later_ref], 'the later batch reads only the new message')
        rows = self._rows()
        change, = [r for r in rows if later_ref in r['evidence']]
        brief = json.loads(change['plan'])['school_task']
        self.assertEqual((change['state'], brief['change'], brief['target_id'], brief['state']),
                         ('pending', 'update', dictation['task_id'], 'review'))
        # Until the parent decides, both saved tasks keep their own days and the copying is untouched.
        with self.store._db() as c:
            tasks = {r['id']: r['due'] for r in c.execute('SELECT id,due FROM manual_tasks')}
        self.assertEqual(tasks, {copying['task_id']: '2026-10-08', dictation['task_id']: '2026-10-09'})
        self.assertEqual({r['id']: r for r in rows if r['id'] in (copying['id'], dictation['id'])},
                         {copying['id']: copying, dictation['id']: dictation})


if __name__ == '__main__':
    unittest.main()
