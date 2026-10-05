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

    def _assert_rejected_batch(self, payload, result):
        self.assertEqual((result['failed'], result['processed'], result['created']), (1, 0, 0),
                         'invalid action allocation must not finish or partially save the batch')
        self.assertEqual(self.model.call_count, 1)
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
        agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual(self.model.call_count, 1, 'respect the existing retry delay')

        recovered = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((recovered['failed'], recovered['processed']), (0, 2))
        self.assertEqual(self.model.call_count, 2)
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


if __name__ == '__main__':
    unittest.main()
