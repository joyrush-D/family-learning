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
            self.assertTrue(after[key]['error'].startswith(frozen[key]['error']), 'both original failure texts stay')
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

if __name__ == '__main__':
    unittest.main()
