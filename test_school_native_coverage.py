"""Synthetic native school-action coverage; no real model, collectors or devices.

The incomplete receipt is structurally valid and cites both original messages,
but omits the exercise and all its supplemental standards. It must not finish
the intake batch. This regression uses run_once's real _select/_save route;
the saved replies are fixtures, not a measurement of model extraction accuracy.
"""
import copy
import datetime as dt
import io
import json
import re
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

    def _ingest(self, texts, publishers=None, orders=None, sender='虚构英语老师'):
        publishers = publishers or ['synthetic-teacher-1'] * len(texts)
        payload = self.fixture.payload(cursor=str(10 + len(texts)))
        common = dict(time=self.now.isoformat(), kind='text', sender=sender,
                      unread=False)
        payload['messages'] = [dict(common, id=str(11 + index), message_order=str(11 + index),
                                    sender_id=publisher, text=text)
                               for index, (text, publisher) in enumerate(zip(texts, publishers))]
        for message, order in zip(payload['messages'], orders or ()):
            # A collector without a stored position for this message sends no order at all.
            if order is None: message.pop('message_order')
            else: message['message_order'] = order
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

    def _disclosed_save(self, texts, publishers, replies, index):
        """Known fictional regressions: unchanged replies, only each cited ref bound to its ingested message by position."""
        payload, refs = self._ingest(texts, publishers)
        replies = copy.deepcopy(replies)
        for reply in replies: reply['evidence'] = [dict(ref=refs[index[e['ref']]]) for e in reply['evidence']]
        self._use_replies(payload, [dict(proposals=replies)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual(result['failed'], 0)
        with self.store._db() as c:
            saved = {r['title']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
            rows = [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        with self.store._db() as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')], rows, 'no second task')
        return saved, refs

    def test_a_complete_completion_prefix_or_title_named_correction_or_dated_activity_saves_its_own_final_day(self):
        geo = ['地理：2026年10月22日19:00前完成《等高线观察》纸质记录表，标出山脊和河谷各一处并各写两句判断依据；纸质记录表2026年10月23日下午课前交给地理老师；2026年10月24日地理课做3分钟口头说明，说明等高线疏密与坡度的关系。',
               '更正：纸质记录表改为2026年10月24日下午课前交给地理老师；完成时间仍是2026年10月22日19:00前；3分钟口头说明的时间和要求不变。']
        art = ['美术：2026年10月20日19:30前完成《树叶拓印》作品，在背面写上姓名和日期；作品2026年10月21日上午交给美术老师。',
               '更正：《树叶拓印》作品改为2026年10月22日上午交给美术老师；完成时间仍是2026年10月20日19:30前。']
        talk = ['2026年10月29日美术课上向同组同学介绍自己的画，并回答同学提出的一个问题；2026年10月30日美术课带油画棒一盒。']
        cases = [
            (geo, ['t1', 't1'], [fixtures.school_proposal(
                title_quote='2026年10月22日19:00前完成《等高线观察》纸质记录表，标出山脊和河谷各一处并各写两句判断依据', due='2026-10-24',
                evidence=[dict(ref='c1'), dict(ref='c3')], task_title='地理：完成《等高线观察》纸质记录表', learning_subject='地理',
                task_goal='2026年10月22日19:00前完成《等高线观察》纸质记录表。\n标出山脊和河谷各一处，并各写两句判断依据。\n纸质记录表2026年10月24日下午课前交给地理老师（原为10月23日下午课前，已更正）。',
                task_state='ready', task_purpose='learning', task_reason='虚构回执。', task_submission='纸质记录表2026年10月24日下午课前交给地理老师。'),
                fixtures.school_proposal(
                title_quote='2026年10月24日地理课做3分钟口头说明，说明等高线疏密与坡度的关系', due='2026-10-24', evidence=[dict(ref='c1'), dict(ref='c3')],
                task_title='地理：3分钟口头说明等高线疏密与坡度', learning_subject='地理', task_state='ready', task_purpose='learning', task_reason='虚构回执。',
                task_goal='2026年10月24日地理课做3分钟口头说明。\n说明等高线疏密与坡度的关系。\n该口头说明的时间和要求不变。')],
             {'c1': 0, 'c3': 1}, '《等高线观察》', '2026-10-24', ('2026年10月22日19:00前完成', '山脊和河谷各一处', '两句判断依据', '2026年10月24日下午课前交给地理老师')),
            (art, ['a1', 'a1'], [fixtures.school_proposal(
                title_quote=art[0], due='2026-10-22', evidence=[dict(ref='d1'), dict(ref='d3')], task_title='美术：完成《树叶拓印》作品', learning_subject='美术',
                task_goal='2026年10月20日19:30前完成《树叶拓印》作品。\n作品背面写上姓名和日期。\n2026年10月22日上午交给美术老师（原为10月21日上午，已更正）。',
                task_state='ready', task_purpose='learning', task_reason='虚构回执。', task_submission='2026年10月22日上午将作品交给美术老师')],
             {'d1': 0, 'd3': 1}, '《树叶拓印》', '2026-10-22', ('2026年10月20日19:30前完成', '背面写上姓名和日期', '2026年10月22日上午交给美术老师')),
            (talk, ['e1'], [fixtures.school_proposal(
                title_quote='2026年10月29日美术课上向同组同学介绍自己的画，并回答同学提出的一个问题', due='2026-10-29', evidence=[dict(ref='e1')],
                task_title='美术：向同组介绍自己的画并答问', learning_subject='美术', task_state='ready', task_purpose='learning', task_reason='虚构回执。',
                task_goal='10月29日美术课上向同组同学介绍自己的画；回答同学提出的一个问题。'),
                fixtures.school_proposal(
                title_quote='2026年10月30日美术课带油画棒一盒', due='2026-10-30', evidence=[dict(ref='e1')], task_title='美术：10月30日带油画棒一盒',
                task_state='ready', task_purpose='admin', task_reason='虚构回执。', task_goal='10月30日美术课带油画棒一盒。')],
             {'e1': 0}, '介绍自己的画', '2026-10-29', ('向同组同学介绍自己的画', '回答同学提出的一个问题')),
        ]
        for texts, publishers, replies, index, name, due, words in cases:
            with self.subTest(name=name):
                self.setUp()
                saved, refs = self._disclosed_save(texts, publishers, replies, index)
                row, = [r for t, r in saved.items() if name in t]
                self.assertEqual((row['due'], row['state']), (due, 'accepted'))
                for word in words: self.assertIn(word, row['body'])
                self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs[:len(index)])
                self.doCleanups()
        # Another publisher's correction, or a correction naming another title, never moves the work's day.
        for publishers, fix in ((['a1', 'a2'], art[1]), (['a1', 'a1'], art[1].replace('《树叶拓印》', '《枫叶拓印》'))):
            with self.subTest(publishers=publishers, fix=fix[:12]):
                self.setUp()
                saved, refs = self._disclosed_save([art[0], fix], publishers, cases[1][2], cases[1][3])
                row, = [r for t, r in saved.items() if '树叶拓印' in t]
                self.assertEqual((row['due'], json.loads(row['plan'])['school_task']['state']), ('', 'review'))
                self.doCleanups()

    def test_a_complete_prefix_never_takes_another_objects_handback_day(self):
        text = '数学：2026年10月18日20:00前完成《分数练习》第3页；回执2026年10月19日交给班主任。'
        for due, expected in (('2026-10-18', ('2026-10-18', 'ready')), ('2026-10-19', ('', 'review'))):
            with self.subTest(due=due):
                work = fixtures.school_proposal(
                    title_quote='2026年10月18日20:00前完成《分数练习》第3页', due=due, evidence=[dict(ref='message:x:1')],
                    learning_subject='数学', task_title='数学：完成《分数练习》第3页', task_goal='2026年10月18日20:00前完成《分数练习》第3页。',
                    task_state='ready', task_purpose='learning', task_reason='虚构对抗回执。')
                evidence = [dict(ref='message:x:1', text=text, time=self.now.isoformat(), kind='text', publisher='publisher:t1',
                                 content_incomplete=False, attachments=[], unread=False)]
                with patch.object(agent.family_llm, '_chat_json', return_value=dict(proposals=[work])):
                    item, = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-05')
                self.assertEqual((item['due'], item['plan']['school_task']['state']), expected,
                                 'the receipt handback is another object, so the work keeps its own day only')

    def test_an_unconfirmed_history_note_keeps_the_excerpt_for_review_and_tonight_stays_in_the_copying(self):
        payload, refs, replies = self._excerpt_batch('2026-10-20')
        for note, expected in (('（原为10月19日早读，已更正）', ('2026-10-20', 'accepted')),
                               ('（原为10月19日早读交，尚未更正为10月20日早读）', ('', 'pending'))):
            with self.subTest(note=note):
                self.setUp()
                payload, refs, replies = self._excerpt_batch('2026-10-20')
                replies[0]['task_goal'] = replies[0]['task_goal'].replace('（原为10月19日早读，已更正）', note)
                self._use_replies(payload, [dict(proposals=replies)])
                self.assertEqual(agent.run_once(self.app, self.now)['failed'], 0)
                with self.store._db() as c:
                    excerpt, = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'") if '河岸随记' in r['title']]
                self.assertEqual(json.loads(excerpt['plan'])['school_task']['state'], 'ready' if expected[1] == 'accepted' else 'review')
                self.doCleanups()
        self.setUp()
        text = '英语：今晚把Unit 3单词每个抄写两遍，明天交；周五听写Unit 3单词。'
        payload, refs = self._ingest([text])
        copying = fixtures.school_proposal(
            title_quote='今晚把Unit 3单词每个抄写两遍，明天交', due='2026-10-06', evidence=[dict(ref=refs[0])], learning_subject='英语',
            task_title='英语：Unit 3单词每个抄写两遍', task_goal='把Unit 3单词每个抄写两遍；明天交。', task_state='ready',
            task_purpose='learning', task_reason='虚构回执。', task_submission='明天交')
        dictation = fixtures.school_proposal(
            title_quote='周五听写Unit 3单词', due='2026-10-09', evidence=[dict(ref=refs[0])], learning_subject='英语',
            task_title='英语：听写Unit 3单词', task_goal='周五听写Unit 3单词', task_state='ready', task_purpose='learning', task_reason='虚构回执。')
        self._use_replies(payload, [dict(proposals=[copying, dictation])])
        self.assertEqual(agent.run_once(self.app, self.now)['failed'], 0)
        with self.store._db() as c:
            rows = {r['title']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
        self.assertIn('今晚把Unit 3单词每个抄写两遍', rows['英语：Unit 3单词每个抄写两遍']['body'])
        self.assertNotIn('今晚', rows['英语：听写Unit 3单词']['body'], 'the dictation stays its own item')

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
                    # The ingested originals share one second; their collector order (11, 12, 13) is what proves the fix later.
                    evidence = [dict(ref=r, text=m['text'], time=m['time'], kind='text', publisher='publisher:' + p,
                                     message_order=m['message_order'], content_incomplete=False, attachments=[], unread=False)
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
                                 unread=False, message_order=m['message_order'], **({} if publisher is None and n < 2 else
                                                  dict(publisher='publisher:p1' if n == 2 else publisher and 'publisher:' + publisher)))
                            for n, (r, m) in enumerate(zip(refs, payload['messages']))]
                items = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-05')
                excerpt, = [i for i in items if '河岸随记' in i['title']]
                self.assertEqual((excerpt['due'], excerpt['plan']['school_task']['state']), expected)
                for words in ('2026年10月18日20:00前完成', '摘录两句', '各写一句选择理由'):
                    self.assertIn(words, excerpt['plan']['school_task']['goal'])
                self.assertEqual([q['ref'] for q in excerpt['evidence']], refs[:2])

    def _correction_batch(self, quote, corrector='synthetic-teacher-1', orders=None):
        texts = ['数学：2026年10月17日21:00前订正《小数运算练习》第2页第3、5、7题，每题写出正确过程并写一句错因；订正本2026年10月18日第一节课前交给数学课代表；2026年10月18日数学课前独立完成10道两位小数加减口算，写在口算本上。',
                 '2026年10月19日科学课请带透明塑料杯一个和纸巾两张，装在同一个袋子里；这些用品用于课堂观察，不要求在家提前做实验。',
                 '更正：口算改成6道，其他要求和2026年10月18日的时间不变；第2页订正仍只做第3、5、7题。',
                 '家长：孩子说不用交订正本，这个说法还需要问老师；我也想知道纸巾能不能改成毛巾。']
        payload, refs = self._ingest(texts, ['synthetic-teacher-1', 'synthetic-teacher-2', corrector, 'synthetic-parent-1'], orders)
        texts, refs = [texts[0], texts[2], texts[3], texts[1]], [refs[0], refs[2], refs[3], refs[1]]
        fix = fixtures.school_proposal(
            title_quote=quote, due='2026-10-18', evidence=[dict(ref=refs[0]), dict(ref=refs[1])], learning_subject='数学',
            task_title='数学：订正《小数运算练习》第2页', task_state='ready', task_purpose='learning', task_reason='虚构回执。',
            task_goal='订正《小数运算练习》第2页第3、5、7题；每题写出正确过程并写一句错因；2026年10月17日21:00前完成；订正本2026年10月18日第一节课前交给数学课代表。',
            task_submission='订正本2026年10月18日第一节课前交给数学课代表。')
        oral = fixtures.school_proposal(
            title_quote='2026年10月18日数学课前独立完成10道两位小数加减口算，写在口算本上', due='2026-10-18',
            evidence=[dict(ref=refs[0]), dict(ref=refs[1])], learning_subject='数学', task_title='数学：完成6道两位小数加减口算',
            task_goal='2026年10月18日数学课前独立完成6道两位小数加减口算，写在口算本上；口算数量已由10道更正为6道。',
            task_state='ready', task_purpose='learning', task_reason='虚构回执。')
        question = fixtures.school_proposal(title_quote='孩子说不用交订正本，这个说法还需要问老师；我也想知道纸巾能不能改成毛巾',
                                            evidence=[dict(ref=refs[2])], task_state='reference',
                                            task_purpose='optional', task_reason='虚构回执：家长转述，不是老师要求。')
        cups = fixtures.school_proposal(
            title_quote='2026年10月19日科学课请带透明塑料杯一个和纸巾两张，装在同一个袋子里', due='2026-10-19', evidence=[dict(ref=refs[3])],
            task_title='科学：带透明塑料杯和纸巾', task_state='ready', task_purpose='admin', task_reason='虚构回执。',
            task_goal='2026年10月19日科学课带透明塑料杯一个和纸巾两张，装在同一个袋子里；这些用品用于课堂观察，不要求在家提前做实验。')
        return payload, refs, [fix, oral, cups, question]

    def test_full_completion_and_handback_anchor_saves_the_handback_day_and_a_proven_short_anchor_keeps_the_whole_outcome(self):
        full = '数学：2026年10月17日21:00前订正《小数运算练习》第2页第3、5、7题，每题写出正确过程并写一句错因；订正本2026年10月18日第一节课前交给数学课代表'
        short = '订正《小数运算练习》第2页第3、5、7题，每题写出正确过程并写一句错因'
        # All four originals share one stored second; only their collector order puts the correction after the list.
        for quote in (full, short):
            with self.subTest(quote=quote[:12]):
                self.setUp()
                payload, refs, replies = self._correction_batch(quote)
                self._use_replies(payload, [dict(proposals=replies)])
                self.assertEqual(agent.run_once(self.app, self.now)['failed'], 0)
                with self.store._db() as c:
                    rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
                    self.assertEqual(len(rows), 4, 'three independent outcomes and the parent relay')
                    row, = [r for r in rows if '小数运算练习' in r['title']]
                    # The short anchor lies inside the one located outcome, so the program states that outcome's whole original.
                    self.assertEqual((row['due'], row['state'], json.loads(row['plan'])['school_task']['state']),
                                     ('2026-10-18', 'accepted', 'ready'))
                    for words in ('2026年10月17日21:00前订正', '第3、5、7题', '每题写出正确过程并写一句错因',
                                  '订正本2026年10月18日第一节课前交给数学课代表'):
                        self.assertIn(words, row['body'])
                    self.assertNotIn('口算', row['body'], 'the independent oral drill keeps its own outcome')
                    self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs[:2])
                    oral, = [r for r in rows if '口算' in r['title']]
                    self.assertEqual(oral['due'], '2026-10-18')
                    self.assertIn('6道', oral['body'])
                    self.assertNotIn('小数运算练习', oral['body'])
                    self.assertEqual([e['ref'] for e in json.loads(oral['evidence'])], refs[:2])
                    cups, = [r for r in rows if '塑料杯' in r['title']]
                    self.assertEqual((cups['due'], [e['ref'] for e in json.loads(cups['evidence'])]), ('2026-10-19', refs[3:]))
                    relay, = [r for r in rows if '不用交订正本' in r['title']]
                    self.assertEqual((json.loads(relay['plan'])['school_task']['state'], relay['task_id']), ('reference', ''))
                    tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
                    self.assertTrue(any('小数运算练习' in t['title'] for t in tasks))
                    self.assertFalse(any('不用交订正本' in t['action'] for t in tasks), 'the parent relay stays reference')
                self.doCleanups()

    def test_a_bare_correction_word_binds_only_the_one_outcome_whose_original_has_it(self):
        text = '数学：2026年10月17日21:00前订正《小数运算练习》第2页第3、5、7题，每题写出正确过程并写一句错因；订正本2026年10月18日第一节课前交给数学课代表；2026年10月18日数学课前独立完成10道两位小数加减口算，写在口算本上。'
        actions = agent._school_native_actions([dict(ref='message:m4-math:1', text=text, time='2026-10-16T17:00:00+08:00', kind='text',
                                                     publisher='publisher:m4-math', content_incomplete=False, attachments=[], unread=False)])
        self.assertEqual(len(actions), 2)
        owner = agent._school_native_change_target('口算改成6道', actions)
        self.assertTrue(owner and '口算' in owner['primary'] and '小数运算练习' not in owner['primary'])
        # A word both outcomes contain, one no outcome has, another subject, or a page or question binds nothing.
        for clause in ('课前改成课后', '听写改成6道', '语文口算改成6道', '口算第3题改成6道', '口算本第2页改成第3页'):
            with self.subTest(clause=clause):
                self.assertIsNone(agent._school_native_change_target(clause, actions))

    def test_a_same_second_correction_binds_only_a_known_later_order_from_the_same_teacher(self):
        oral_quote = '2026年10月18日数学课前独立完成10道两位小数加减口算，写在口算本上'
        cases = (('another teacher', dict(corrector='synthetic-teacher-3')),
                 ('equal order', dict(orders=['11', '12', '11', '14'])),
                 ('unknown order', dict(orders=['11', '12', None, '14'])),
                 ('reversed order', dict(orders=['13', '12', '11', '14'])),
                 # A short anchor in both the correction's restated questions and the list, or another outcome's own clause.
                 ('ambiguous anchor', dict(quote='第3、5、7题')),
                 ('cross-item anchor', dict(quote=oral_quote)))
        for name, options in cases:
            with self.subTest(case=name):
                self.setUp()
                quote = options.pop('quote', '订正《小数运算练习》第2页第3、5、7题，每题写出正确过程并写一句错因')
                payload, refs, replies = self._correction_batch(quote, **options)
                self._use_replies(payload, [dict(proposals=replies)])
                self.assertEqual(agent.run_once(self.app, self.now)['failed'], 1, 'the whole batch stays for retry')
                self.assertEqual(self.store.snapshot()['sources'][0]['pending_message_count'], 4)
                with self.store._db() as c:
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE kind='school'").fetchone()[0], 0)
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
                self.doCleanups()

    def test_a_clause_headed_by_its_full_date_states_that_day_whatever_its_verb(self):
        ref = 'message:m4-geo:1'
        for clause, expected in (('2026年10月24日地理课做3分钟口头说明，说明等高线疏密与坡度的关系', ('2026-10-24', 'ready')),
                                 ('2026年10月24日地理课口头说明取消', ('', 'review')),
                                 ('2026年10月24日地理课要做口头说明吗？', ('', 'review')),
                                 ('2026年10月24日起地理课做口头说明', ('', 'review'))):
            text = clause + '；2026年10月20日前把地图册交给地理课代表。'
            evidence = [dict(ref=ref, text=text, time='2026-10-16T18:00:00+08:00', kind='text', publisher='publisher:m4-geo',
                             content_incomplete=False, attachments=[], unread=False)]
            talk = fixtures.school_proposal(title_quote=clause, due='2026-10-24', evidence=[dict(ref=ref)], learning_subject='地理',
                                            task_title='地理：口头说明', task_goal=clause + '。', task_state='ready',
                                            task_purpose='learning', task_reason='虚构回执。')
            atlas = fixtures.school_proposal(title_quote='2026年10月20日前把地图册交给地理课代表', due='2026-10-20', evidence=[dict(ref=ref)],
                                             task_title='地理：交地图册', task_goal='2026年10月20日前把地图册交给地理课代表。',
                                             task_state='ready', task_purpose='admin', task_reason='虚构回执。')
            with self.subTest(clause=clause), patch.object(agent.family_llm, '_chat_json', return_value=dict(proposals=[talk, atlas])):
                items = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-16')
                item, = [i for i in items if '口头说明' in i['title']]
                self.assertEqual((item['due'], item['plan']['school_task']['state']), expected)
                other, = [i for i in items if '地图册' in i['title']]
                self.assertEqual((other['due'], other['plan']['school_task']['state']), ('2026-10-20', 'ready'))

    def test_a_handback_of_other_work_keeps_both_days_unconfirmed(self):
        ref = 'message:m4-math:1'
        text = '数学：2026年10月17日21:00前订正第2页第3题；回执2026年10月18日交给数学课代表。'
        evidence = [dict(ref=ref, text=text, time='2026-10-16T17:00:00+08:00', kind='text', publisher='publisher:m4-math',
                         content_incomplete=False, attachments=[], unread=False)]
        quote = '数学：2026年10月17日21:00前订正第2页第3题；回执2026年10月18日交给数学课代表。'
        item = fixtures.school_proposal(title_quote=quote, due='2026-10-18', evidence=[dict(ref=ref)], learning_subject='数学',
                                        task_title='数学：订正第2页', task_goal=quote, task_state='ready', task_purpose='learning',
                                        task_reason='虚构回执。')
        with patch.object(agent.family_llm, '_chat_json', return_value=dict(proposals=[item])):
            result, = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-16')
        self.assertEqual(result['plan']['school_task']['state'], 'review')

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

    _COMPOUND = '2026年10月22日前，请填写《虚构营地报名表》的学生姓名并在《虚构交通回执》上完成家长签字，两份分别交回班主任。'

    def _compound_reply(self, ref, goal, text=None):
        return dict(proposals=[dict(title_quote=text or self._COMPOUND, focus='school', due='2026-10-22', evidence=[dict(ref=ref)],
                                    learning_subject='', learning_goal_id='', task_title='填写营地报名表并交回', task_goal=goal,
                                    task_advice='', task_state='ready', task_reason='虚构固定回执，仅作程序验证。', task_change='new',
                                    task_target_id='', task_purpose='admin', task_submission='')])

    def test_one_clause_with_two_named_outcomes_rejects_a_goal_missing_one_then_saves_the_complete_reply(self):
        payload, refs = self._ingest([self._COMPOUND])
        partial = self._compound_reply(refs[0], '2026年10月22日前填写《虚构营地报名表》的学生姓名并交回班主任。')
        full = self._compound_reply(refs[0], self._COMPOUND)
        self._use_replies(payload, [partial, full])
        first = agent.run_once(self.app, self.now)
        # The full original and its full title_quote were read; a goal dropping the second form is no complete summary.
        self._assert_rejected_batch(payload, first)
        recovered = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((recovered['failed'], recovered['processed']), (0, 1))
        self.assertEqual(self.model.call_count, 2)
        with self.store._db() as c:
            saved = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual(len(saved), 1, 'one combined task with both outcomes is a complete reading; no task count is forced')
            row = saved[0]
            self.assertEqual((row['state'], row['due']), ('accepted', '2026-10-22'))
            for words in ('《虚构营地报名表》', '学生姓名', '《虚构交通回执》', '家长签字', '两份', '交回班主任'):
                self.assertIn(words, row['body'])
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)
            task = c.execute('SELECT * FROM manual_tasks').fetchone()
            self.assertEqual((task['action'], task['due']), (row['body'], '2026-10-22'))
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            self.assertEqual([json.loads(r[0])['text'] for r in c.execute('SELECT payload FROM agent_messages')], [self._COMPOUND])
            item_rows = [tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')]
            task_rows = [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 2)
        with self.store._db() as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')], item_rows)
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')], task_rows)

    def test_a_complete_goal_writing_both_names_without_title_marks_saves_on_its_first_receipt(self):
        payload, refs = self._ingest([self._COMPOUND])
        goal = '2026年10月22日前填写虚构营地报名表的学生姓名，在虚构交通回执上完成家长签字，两份分别交回班主任。'
        self._use_replies(payload, [self._compound_reply(refs[0], goal)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual([(r['state'], r['body']) for r in rows], [('accepted', goal)])

    def _compound_control(self, text, goal):
        payload, refs = self._ingest([text])
        self._use_replies(payload, [self._compound_reply(refs[0], goal, text)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual(len(rows), 1, 'one form keeps one task')
            self.assertEqual(rows[0]['state'], 'accepted')
            self.assertIn(goal.rstrip('。'), rows[0]['body'])

    def test_one_named_form_with_its_continuous_steps_keeps_the_short_goal(self):
        self._compound_control('请于10月22日前填写《虚构营地报名表》并交回班主任。', '10月22日前填写《虚构营地报名表》并交回班主任。')

    def test_a_conjunction_inside_one_title_is_no_second_outcome(self):
        self._compound_control('请于10月22日前填写《虚构营地并联活动报名表》并交回班主任。', '10月22日前填写《虚构营地并联活动报名表》并交回班主任。')

    def test_a_reference_title_beside_the_form_is_no_second_outcome(self):
        self._compound_control('请于10月22日前填写《虚构营地报名表》并交回班主任，《虚构营地说明》仅供了解。', '10月22日前填写《虚构营地报名表》并交回班主任。')

    def test_a_negated_second_title_is_no_second_outcome(self):
        self._compound_control('请于10月22日前填写《虚构营地报名表》并交回班主任，《虚构交通回执》并不是本次要交的材料。', '10月22日前填写《虚构营地报名表》并交回班主任。')

    def _clause_reply(self, ref, text, goal, *, purpose='admin', subject='', title='填写两份表并交回', due='2026-11-06', quote=None):
        return dict(proposals=[dict(title_quote=quote or text, focus='school', due=due, evidence=[dict(ref=ref)],
                                    learning_subject=subject, learning_goal_id='', task_title=title, task_goal=goal,
                                    task_advice='', task_state='ready', task_reason='虚构固定回执，仅作程序验证。', task_change='new',
                                    task_target_id='', task_purpose=purpose, task_submission='')])

    def _partial_then_full(self, text, partial, full, words, **reply):
        payload, refs = self._ingest([text])
        self._use_replies(payload, [self._clause_reply(refs[0], text, partial, **reply), self._clause_reply(refs[0], text, full, **reply)])
        first = agent.run_once(self.app, self.now)
        # The complete original and its complete title_quote were read; a goal dropping one stated requirement is no complete summary.
        self._assert_rejected_batch(payload, first)
        recovered = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((recovered['failed'], recovered['processed']), (0, 1))
        self.assertEqual(self.model.call_count, 2)
        with self.store._db() as c:
            saved = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual(len(saved), 1, 'one faithful combined task is complete; no task count is forced')
            self.assertEqual((saved[0]['state'], saved[0]['due'], saved[0]['body']), ('accepted', reply.get('due', '2026-11-06'), full))
            for word in words:self.assertIn(word, saved[0]['body'])
            task = c.execute('SELECT * FROM manual_tasks').fetchone()
            self.assertEqual(task['action'], full)
            self.assertEqual([json.loads(r[0])['text'] for r in c.execute('SELECT payload FROM agent_messages')], [text])
            rows = [tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')], [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['processed'], replay['created'], self.model.call_count), (0, 0, 2))
        with self.store._db() as c:
            self.assertEqual(([tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')], [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]), rows)

    def test_root_h1_a_learning_goal_dropping_its_unnamed_recording_is_rejected_then_the_full_reply_saves(self):
        text = '科学：制作《发芽观察卡》并录一段30秒讲解，2026年11月6日交回。'
        self._partial_then_full(text, '制作《发芽观察卡》，2026年11月6日交回。', '制作《发芽观察卡》并录一段30秒讲解，2026年11月6日交回。',
                                ('发芽观察卡', '录', '30秒', '讲解', '交回'), purpose='learning', subject='科学', title='科学：制作发芽观察卡')

    def test_root_h2s_both_names_kept_but_the_parent_signature_dropped_is_rejected_then_the_full_reply_saves(self):
        text = '2026年11月6日前，请将《植物角报名表》填写联系电话以及将《校外出行确认单》交家长签字，两份均交回班主任。'
        self._partial_then_full(text, '2026年11月6日前，填写《植物角报名表》的联系电话并将《校外出行确认单》交回班主任，两份都交回。', text,
                                ('植物角报名表', '联系电话', '校外出行确认单', '家长签字', '两份', '交回班主任'))

    def test_both_forms_and_signature_kept_but_the_two_copy_handback_dropped_is_rejected(self):
        text = '2026年10月22日前，请填写《虚构营地报名表》的学生姓名并在《虚构交通回执》上完成家长签字，两份分别交回班主任。'
        self._partial_then_full(text, '2026年10月22日前，请填写《虚构营地报名表》的学生姓名并在《虚构交通回执》上完成家长签字。', text,
                                ('两份', '交回班主任'), due='2026-10-22')

    def test_an_unnamed_photo_step_after_a_named_drawing_is_kept_or_rejected(self):
        text = '美术：画一幅《虚构秋叶》并拍一张照片，10月9日前交回。'
        self._partial_then_full(text, '画一幅《虚构秋叶》，10月9日前交回。', '画一幅《虚构秋叶》并拍照片，10月9日前交回。',
                                ('虚构秋叶', '拍', '照片'), purpose='learning', title='美术：画虚构秋叶', due='2026-10-09')

    def _clause_saved(self, text, goal, **reply):
        payload, refs = self._ingest([text])
        self._use_replies(payload, [self._clause_reply(refs[0], text, goal, **reply)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            self.assertEqual([(r['state'], r['body']) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")], [('accepted', goal)])

    def _named_material(self, book):
        """Root's synthetic counterexample through run_once, _save, manual_tasks and app.tasks; the fixed reply is the correct one."""
        text = '语文作业：阅读' + book + '，写三句话读后感，今晚完成。'
        title, goal = '语文：阅读' + book, '阅读' + book + '，写三句话读后感，今晚完成。'
        payload, refs = self._ingest([text], ['synthetic-chinese-teacher'], sender='虚构语文老师')
        self._use_replies(payload, [dict(proposals=[dict(
            title_quote='阅读' + book, focus='school', due='2026-10-05', evidence=[dict(ref=refs[0])], learning_subject='语文',
            learning_goal_id='', task_title=title, task_goal=goal, task_advice='', task_state='ready',
            task_reason='虚构固定回执，仅作程序验证。', task_change='new', task_target_id='', task_purpose='learning', task_submission='')])])
        result = agent.run_once(self.app, self.now)

        def saved():
            with self.store._db() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
                manual = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
                originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            with self.app.connect() as c:
                tasks = [t for t in self.app.tasks(c) if t['id'] in {m['id'] for m in manual}]
            return rows, manual, tasks, originals

        rows, manual, tasks, originals = saved()
        self.assertEqual((result['failed'], len(rows), len(manual), len(tasks)), (0, 1, 1, 1), 'one outcome, one saved task')
        plan = json.loads(rows[0]['plan'])
        self.assertEqual(plan['school_learning']['subject'], '语文')
        self.assertEqual(plan['school_task']['purpose'], 'learning')
        self.assertEqual((rows[0]['state'], rows[0]['due'], rows[0]['task_id']), ('accepted', '2026-10-05', manual[0]['id']))
        # The saved card, its main-list task and its learning link name one subject; the book keeps its own words.
        self.assertEqual((rows[0]['title'], manual[0]['title'], tasks[0]['title']), (title, title, title))
        self.assertEqual(tasks[0]['title'].split('：', 1)[0], plan['school_learning']['subject'])
        for words in (book, '三句话', '读后感', '今晚'):
            self.assertIn(words, manual[0]['action'])
        self.assertEqual([e['ref'] for e in json.loads(rows[0]['evidence'])], refs)
        self.assertEqual(originals, payload['messages'], 'the original stays unchanged')
        self.assertEqual((originals[0]['sender_id'], originals[0]['text']), ('synthetic-chinese-teacher', text))
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(saved(), (rows, manual, tasks, originals), 'reopen keeps the same card without a duplicate')
        self.assertEqual(self.model.call_count, 1)

    def test_a_subject_word_inside_a_closed_book_title_is_never_the_saved_subject(self):
        # 《数学家的故事》 is the 语文 reading's material, not a 数学 outcome; 《小河边的故事》 is the unchanged control.
        for book in ('《数学家的故事》', '《小河边的故事》'):
            with self.subTest(book=book):
                case = type(self)(methodName='runTest')
                case.setUp()
                try:case._named_material(book)
                finally:case.doCleanups()

    def test_native_subject_ignores_closed_titles_but_keeps_an_explicit_subject_outside_them(self):
        actions = lambda text:[(a['subject'], a['primary']) for a in agent._school_native_actions([dict(
            ref='message:s:1', text=text, kind='text', publisher='synthetic-teacher-1', time='2026-10-05T08:00:00+08:00')])]
        # Two outcomes each naming their own subject outside titles keep them; a title's subject word never decides.
        self.assertEqual(actions('今晚两项作业：1. 语文：阅读《数学家的故事》并写三句话读后感；2. 数学：完成练习册第18页。'),
                         [('语文', '语文：阅读《数学家的故事》并写三句话读后感'), ('数学', '数学：完成练习册第18页')])
        # Without any subject outside a title, a closed book name supplies none; an explicit one outside it stays.
        self.assertEqual(agent._school_native_subjects('阅读《数学家的故事》，写三句话读后感'), set())
        self.assertEqual(agent._school_native_subjects('数学：完成《语文园地》旁的练习'), {'数学'})

    # Root's MATH-M4-SAFE case math-supplement-101-102 (pure fiction; source chain from a retained trace, never run alone):
    # the same teacher re-sends this outcome's own worksheet a minute later with more requirements; only 102 has the sheet.
    MATH_TEXTS = ('数学：今天完成《平均分练习单》第1、2题，把答案直接写在练习单上。明天交给数学课代表。',
                  '补上刚才的练习单。第2题要画出分组过程，不用抄题。第3题不用做。')
    MATH_PROPOSAL = dict(title_quote='今天完成《平均分练习单》第1、2题，把答案直接写在练习单上。明天交给数学课代表', focus='school',
                         due='2026-10-23', evidence=[0, 1], learning_subject='数学', learning_goal_id='',
                         task_title='数学：完成《平均分练习单》第1、2题', task_goal=MATH_TEXTS[0] + '\n' + MATH_TEXTS[1], task_advice='',
                         task_change='new', task_target_id='', task_state='ready',
                         task_reason='独立冻结的纯虚构程序验证固定回复，不是实际模型产物。', task_purpose='learning', task_submission='')

    def _math_entries(self, second=None, publisher='publisher:math-lan', first=None):
        return [dict(ref='message:s:101', text=first or self.MATH_TEXTS[0], kind='text', publisher='publisher:math-lan',
                     time='2026-10-22T16:05:00+08:00', attachments=[], content_incomplete=False, related_messages=['message:s:101']),
                dict(ref='message:s:102', text=second or self.MATH_TEXTS[1], kind='text', publisher=publisher, time='2026-10-22T16:06:00+08:00',
                     attachments=[dict(name='平均分练习单.txt', mime='text/plain; charset=utf-8')], content_incomplete=False,
                     related_messages=['message:s:102'])]

    def test_a_same_teacher_resent_worksheet_with_more_requirements_binds_to_its_one_outcome_as_review(self):
        self.fixture.now = self.now = dt.datetime(2026, 10, 22, 16, 30, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='102')
        payload['messages'] = [dict(id=str(101 + i), message_order=str(101 + i), time=time, kind='text', sender='岚老师（虚构）',
                                    sender_id='qa-teacher-math-lan', text=text, unread=False)
                               for i, (time, text) in enumerate(zip(('2026-10-22T16:05:00+08:00', '2026-10-22T16:06:00+08:00'), self.MATH_TEXTS))]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        sheet = '虚构练习单原件测试字节（内容未解释）\n'.encode()
        upload = self.app.save_upload(io.BytesIO(sheet), len(sheet), '平均分练习单.txt')
        self.store.message_attachment(dict(child_id='child-1', source_id=self.source['id'], message_id='102',
                                           attachment_id=upload['id'], action='attach'), dict)
        calls = []

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual((name, data_path), ('family_agent_selection', self.app.DATA))
            context = json.loads(messages[-1]['content'])
            self.assertEqual([(e['ref'], e['text'], e['attachments']) for e in context['evidence']],
                             [(refs[0], self.MATH_TEXTS[0], []), (refs[1], self.MATH_TEXTS[1], [dict(name='平均分练习单.txt', mime=upload['mime'])])])
            calls.append(name)
            return dict(proposals=[dict(copy.deepcopy(self.MATH_PROPOSAL), evidence=[dict(ref=ref) for ref in refs])])

        self.model.side_effect = reply
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 2), 'the faithful merged reply is not rejected as an extra source')

        def facts():
            with self.store._db() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
                manual = c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]
                links = [tuple(r) for r in c.execute('SELECT * FROM agent_message_attachments')]
                originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            with self.app.connect() as c:
                stored = [tuple(r) for r in c.execute('SELECT id,name,size FROM uploads')]
            return rows, manual, links, originals, stored

        rows, manual, links, originals, stored = first = facts()
        row, = rows
        plan = json.loads(row['plan']);brief = plan['school_task']
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)
        self.assertEqual((row['state'], row['title'], brief['purpose'], brief['state']),
                         ('pending', '数学：完成《平均分练习单》第1、2题', 'learning', 'review'))
        # Every literal requirement of both originals stays; the unread sheet keeps a specific reason, never ready.
        for words in self.MATH_TEXTS:self.assertIn(words, row['body'])
        self.assertIn('附件尚未核实', brief['reason'])
        # Its own words give two days (今天完成 22, 明天交 23): the ledger picks none and says so, never another day.
        self.assertIn(row['due'], ('', '2026-10-23'))
        self.assertIn('多个日期', brief['reason'])
        self.assertEqual(plan['school_native_cover']['linked'], [refs[1]])
        self.assertEqual(manual, 0, 'no automatic task while the re-sent sheet is unread')
        self.assertEqual(links, [(self.source['id'], '102', upload['id'])])
        self.assertEqual(stored, [(upload['id'], '平均分练习单.txt', len(sheet))])
        self.assertEqual(originals, payload['messages'], 'the complete originals stay unchanged')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(facts(), first, 'reopen and the next round keep the one item without duplicates')
        self.assertEqual(len(calls), 1)

    def test_only_a_same_teacher_resend_naming_one_outcome_material_links_to_it(self):
        linked = lambda entries:[a.get('linked') for a in agent._school_native_actions(entries)]
        self.assertEqual(linked(self._math_entries()), [['message:s:102']])
        # Another teacher, another object, or a material two outcomes name stays unlinked and keeps the existing rejection.
        self.assertEqual(linked(self._math_entries(publisher='publisher:someone-else')), [None])
        self.assertEqual(linked(self._math_entries('补上刚才的口算本。第2题要画出分组过程。')), [None])
        two = '数学：1. 完成《平均分练习单》第1题；2. 完成《除法练习单》第2题。'
        self.assertEqual(linked(self._math_entries(first=two)), [None, None])

    def test_a_faithful_paraphrase_of_every_requirement_saves_on_its_first_receipt(self):
        self._clause_saved('科学：制作《发芽观察卡》并录一段30秒讲解，2026年11月6日交回。', '制作发芽观察卡，再录30秒的讲解，2026年11月6日前交回。',
                           purpose='learning', subject='科学', title='科学：制作发芽观察卡')

    def test_a_voluntary_extra_in_the_same_quote_is_no_obligation(self):
        self._clause_saved('科学：制作《发芽观察卡》，2026年11月6日交回；有兴趣的同学可以自愿录一段30秒讲解。', '制作《发芽观察卡》，2026年11月6日交回。',
                           purpose='learning', subject='科学', title='科学：制作发芽观察卡')

    H5Q = '2026年11月6日前，请将《植物角报名表》填写联系电话以及将《校外出行确认单》交家长签字，两份均交回班主任。'

    def test_root_h5q_a_clipped_quote_of_the_first_form_is_no_proof_the_whole_sentence_was_organized(self):
        # The quote is a literal prefix; the teacher's own sentence still states the second form, its signature and the handback.
        self._partial_then_full(self.H5Q, '2026年11月6日前，将《植物角报名表》填写联系电话。', self.H5Q,
                                ('植物角报名表', '联系电话', '校外出行确认单', '家长签字', '两份', '交回班主任'),
                                title='填写植物角报名表', quote='2026年11月6日前，请将《植物角报名表》填写联系电话')

    def test_root_h6a_a_child_signature_is_not_the_parent_signature_the_teacher_requires(self):
        self._partial_then_full('请填写《虚构观察表》的孩子姓名并请家长签字，2026年11月18日交回班主任。',
                                '填写《虚构观察表》的孩子姓名并请孩子签字，2026年11月18日交回班主任。',
                                '填写《虚构观察表》的孩子姓名并请家长签字，2026年11月18日交回班主任。',
                                ('虚构观察表', '孩子姓名', '家长签字', '交回班主任'), title='填写观察表并签字交回', due='2026-11-18')

    def test_a_parent_named_elsewhere_in_the_goal_does_not_make_a_child_signature_the_parent_one(self):
        self._partial_then_full('请填写《虚构观察表》的孩子姓名并请家长签字，2026年11月18日交回班主任。',
                                '填写《虚构观察表》的家长姓名和孩子姓名并请孩子签字，2026年11月18日交回班主任。',
                                '填写《虚构观察表》的孩子姓名并请家长签字，2026年11月18日交回班主任。',
                                ('虚构观察表', '孩子姓名', '家长签字'), title='填写观察表并签字交回', due='2026-11-18')

    def test_a_signer_named_in_the_earlier_step_of_the_same_part_must_still_sign(self):
        text = '请家长填写《虚构接送卡》的联系电话并签字，2026年11月6日交回班主任。'
        self._partial_then_full(text, '请孩子填写《虚构接送卡》的联系电话并签字，2026年11月6日交回班主任。', text, ('家长填写', '签字'), title='填写接送卡并签字')

    def test_the_same_parent_role_in_other_words_signs_on_its_first_receipt(self):
        self._clause_saved('请填写《虚构观察表》的孩子姓名并请家长签字，2026年11月18日交回班主任。',
                           '填写《虚构观察表》的孩子姓名，请父母签字，2026年11月18日交回班主任。', title='填写观察表并签字交回', due='2026-11-18')

    def test_actual_flash24_paraphrase_of_the_whole_sentence_saves_as_one_task(self):
        text = '2026年10月22日前，请填写《虚构营地报名表》的学生姓名并在《虚构交通回执》上完成家长签字，两份分别交回班主任。'
        goal = '在2026年10月22日前，填写《虚构营地报名表》的学生姓名；在《虚构交通回执》上完成家长签字；两份材料分别交回班主任。'
        payload, refs = self._ingest([text])
        self._use_replies(payload, [dict(proposals=[dict(
            title_quote=text, focus='school', due='2026-10-22', evidence=[dict(ref=refs[0])], task_title='填写营地报名表并签交通回执', task_goal=goal,
            task_advice='可先填好报名表姓名，再请家长在交通回执上签字，两份材料分开放置以免混淆。', learning_subject='', learning_goal_id='',
            task_change='new', task_target_id='', task_state='ready', task_reason='已读文字明确要求填写报名表姓名、家长签字并分别交回班主任，属全班事务性待办，日期明确。',
            task_purpose='admin', task_submission='两份材料分别交回班主任，截止2026年10月22日。')])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            self.assertEqual([(r['state'], r['due'], r['body']) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")], [('accepted', '2026-10-22', goal)])
            self.assertEqual([r['action'] for r in c.execute('SELECT * FROM manual_tasks')], [goal])

    def _several(self, text, proposals):
        payload, refs = self._ingest([text])
        self._use_replies(payload, [dict(proposals=[dict(quote, evidence=[dict(ref=refs[0])], focus='school', learning_subject='', learning_goal_id='',
                                                         task_advice='', task_reason='虚构固定回执，仅作程序验证。', task_change='new', task_target_id='',
                                                         task_submission='') for quote in proposals])])
        return payload, agent.run_once(self.app, self.now)

    def test_several_tasks_each_keeping_its_own_part_of_one_sentence_save_without_a_forced_count(self):
        text = '2026年10月22日前，请填写《虚构营地报名表》的学生姓名并在《虚构交通回执》上完成家长签字，两份分别交回班主任。'
        goals = ['2026年10月22日前填写《虚构营地报名表》的学生姓名，交回班主任。', '2026年10月22日前在《虚构交通回执》上完成家长签字，两份分别交回班主任。']
        payload, result = self._several(text, [
            dict(title_quote='请填写《虚构营地报名表》的学生姓名', due='2026-10-22', task_title='填写营地报名表', task_goal=goals[0], task_state='ready', task_purpose='admin'),
            dict(title_quote='在《虚构交通回执》上完成家长签字，两份分别交回班主任', due='2026-10-22', task_title='交通回执家长签字', task_goal=goals[1],
                 task_state='ready', task_purpose='admin')])
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            saved = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        self.assertEqual(sorted(r['state'] for r in saved), ['accepted', 'accepted'])
        bodies = '\n'.join(r['body'] for r in saved)
        for word in ('虚构营地报名表', '学生姓名', '虚构交通回执', '家长签字', '两份', '交回班主任'):self.assertIn(word, bodies)

    def test_a_reference_sibling_carrying_the_rest_of_the_sentence_is_no_visible_requirement(self):
        payload, result = self._several(self.H5Q, [
            dict(title_quote='2026年11月6日前，请将《植物角报名表》填写联系电话', due='2026-11-06', task_title='填写植物角报名表',
                 task_goal='2026年11月6日前，将《植物角报名表》填写联系电话。', task_state='ready', task_purpose='admin'),
            dict(title_quote='将《校外出行确认单》交家长签字，两份均交回班主任', due='', task_title='出行确认单说明',
                 task_goal='将《校外出行确认单》交家长签字，两份均交回班主任。', task_state='reference', task_purpose='optional')])
        self._assert_rejected_batch(payload, result)

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
                self.assertIn('请家长核对并在记录本签字', row['body']);self.assertNotIn('以上两项', row['body'])
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

    # Each card: its action, the heading's day, then the bound standard without its list words (以上两项均).
    SHARED_SAVED = [('英语：完成练习卷第2–4题', '完成练习卷第2–4题\n明天\n请家长核对并在记录本签字', '2026-10-16', 'accepted'),
                    ('英语：朗读Unit 8课文两遍', '朗读Unit 8课文两遍\n明天\n请家长核对并在记录本签字', '2026-10-16', 'accepted')]

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
                self.assertIn('请家长核对并在记录本签字', row['body']);self.assertNotIn('以上两项', row['body'])
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
                self.assertTrue(all(re.sub(agent._SCHOOL_NATIVE_COMMON, '', standard.rstrip('。')) in row[1].split('\n') for row in split))

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
            self.assertIn('请家长核对并在记录本签字', row['body']);self.assertNotIn('以上两项', row['body'])
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
        self.assertTrue(all('请家长核对并在记录本签字' in r['body'] and '以上两项' not in r['body'] for r in standard_rows))
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

    def _daily_lists(self):
        """Root's held-out fictional day (heldout-natural-day-20261020-v1): six complete posts, unchanged."""
        self.now = self.fixture.now = dt.datetime(2026, 10, 20, 18, tzinfo=agent.TZ)
        posts = [
            ('synthetic-heldout-chinese-lin', '虚构语文林老师', '16:10', '语文作业：2026年10月20日晚完成两项：1. 朗读《山谷的早晨》第3自然段三遍；2. 完成《字词随练》第8页，做完自行检查。两项都在2026年10月21日早读检查，《字词随练》交给语文课代表。'),
            ('synthetic-heldout-math-xu', '虚构数学许老师', '16:12', '数学：2026年10月20日晚完成《计算练习》第12页第1至6题，列出计算过程，做完自行检查；2026年10月21日上午交给数学课代表。'),
            ('synthetic-heldout-history-tao', '虚构历史陶老师', '16:14', '历史：请在2026年10月20日晚完成两项：1. 复习第4课《河畔聚落》，完成课后练习第1、2题；2. 订正上周《历史小练习》中做错的题，每题写一句错因。两项都在2026年10月21日历史课检查。'),
            ('synthetic-heldout-english-shen', '虚构英语沈老师', '16:16', '英语：今天有两项作业：1. 听录音并跟读Lesson 3《The Garden》两遍；2. 抄写本课单词表前6个单词，每个写3遍。'),
            ('synthetic-heldout-english-shen', '虚构英语沈老师', '16:17', '补充英语作业：以上两项均在2026年10月20日晚完成，完成后请家长在英语作业记录本上签字；2026年10月21日英语课检查这两项作业。'),
            ('synthetic-heldout-headteacher-yu', '虚构班主任余老师', '16:20', '家长通知：请家长在《秋季安全教育回执》上签字，并于2026年10月22日前交回班主任；无需盖章。')]
        payload = self.fixture.payload(cursor='16')
        payload['messages'] = [dict(id=str(11 + i), message_order=str(11 + i), time='2026-10-20T' + clock + ':00+08:00', kind='text',
                                    sender=sender, sender_id=publisher, text=text, unread=False)
                               for i, (publisher, sender, clock, text) in enumerate(posts)]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        academic = '\n2026年10月20日晚完成。\n'
        reply = [fixtures.school_proposal(
            title_quote=quote, due='2026-10-21', evidence=[dict(ref=refs[i]) for i in cited], learning_subject=subject,
            task_title=subject + '：' + title, task_goal=quote + '。' + academic + check, task_state='ready',
            task_reason='虚构回执：完成日与检查日各自保留。', task_purpose='learning', task_submission=handback)
            for quote, cited, subject, title, check, handback in (
                ('朗读《山谷的早晨》第3自然段三遍', [0], '语文', '朗读《山谷的早晨》第3自然段三遍', '2026年10月21日早读检查。', ''),
                ('完成《字词随练》第8页，做完自行检查', [0], '语文', '完成《字词随练》第8页', '2026年10月21日早读检查。', '《字词随练》交给语文课代表。'),
                ('完成《计算练习》第12页第1至6题，列出计算过程，做完自行检查', [1], '数学', '完成《计算练习》第12页第1至6题', '2026年10月21日上午交给数学课代表。', '2026年10月21日上午交给数学课代表。'),
                ('复习第4课《河畔聚落》，完成课后练习第1、2题', [2], '历史', '复习第4课《河畔聚落》并完成课后练习第1、2题', '2026年10月21日历史课检查。', ''),
                ('订正上周《历史小练习》中做错的题，每题写一句错因', [2], '历史', '订正《历史小练习》错题并写错因', '2026年10月21日历史课检查。', ''),
                ('听录音并跟读Lesson 3《The Garden》两遍', [3, 4], '英语', '听录音并跟读Lesson 3《The Garden》两遍', '完成后请家长在英语作业记录本上签字。\n2026年10月21日英语课检查。', ''),
                ('抄写本课单词表前6个单词，每个写3遍', [3, 4], '英语', '抄写本课单词表前6个单词', '完成后请家长在英语作业记录本上签字。\n2026年10月21日英语课检查。', ''))]
        reply.append(fixtures.school_proposal(
            title_quote='请家长在《秋季安全教育回执》上签字，并于2026年10月22日前交回班主任', due='2026-10-22', evidence=[dict(ref=refs[5])],
            task_title='家长签字并交回《秋季安全教育回执》', task_goal='请家长在《秋季安全教育回执》上签字，并于2026年10月22日前交回班主任；无需盖章。',
            task_state='ready', task_reason='虚构回执：行政回执。', task_purpose='admin', task_submission='2026年10月22日前交回班主任。'))
        return payload, refs, reply

    def test_a_labelled_counted_list_intro_is_its_heading_so_a_held_out_day_reaches_the_ordinary_caller(self):
        payload, refs, reply = self._daily_lists()
        native = agent._school_native_blocks(payload['messages'][2]['text'])
        self.assertEqual([(a['purpose'], a['quote']) for a in native],
                         [('learning', '复习第4课《河畔聚落》，完成课后练习第1、2题'), ('learning', '订正上周《历史小练习》中做错的题，每题写一句错因')])
        self.assertEqual(native[0]['header'], '历史：请在2026年10月20日晚完成两项')
        self.assertEqual([a['quote'] for a in agent._school_native_blocks(payload['messages'][3]['text'])],
                         ['听录音并跟读Lesson 3《The Garden》两遍', '抄写本课单词表前6个单词，每个写3遍'])
        self._use_replies(payload, [dict(proposals=reply)])
        # The same English teacher's next message is a clause list of the two items' one scope (以上两项均…晚完成，完成后
        # 请家长…签字；…英语课检查这两项作业): it binds to both English items, so the complete reply is saved whole.
        result = agent.run_once(self.app, self.now)
        with self.store._db() as c:
            error = c.execute("SELECT error FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
        self.assertEqual((result["failed"], result["processed"]), (0, 6), error and error[0])
        self.assertEqual(self.model.call_count, 1)
        # Reopened through new connections: every original processed and kept, each semantic unit one saved school row.
        with self.store._db() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')], [1] * 6)
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')], payload['messages'])
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")]
        with self.app.connect() as c:
            visible = {t['id']: t for t in self.app.tasks(c)}
        saved = [(json.loads(r['plan'])['school_task'], r['due'], {q['ref'] for q in json.loads(r['evidence'])}, r) for r in rows]
        self.assertEqual(len(saved), 8, [b['title'] for b, *_ in saved])
        def unit(literal):
            found = [s for s in saved if literal in s[0]['goal']]
            self.assertEqual(len(found), 1, literal)
            return found[0]
        for literal, subject, purpose, standards, due, cited in (
                ('朗读《山谷的早晨》第3自然段三遍', '语文', 'learning', ['2026年10月20日晚完成', '2026年10月21日早读检查'], '2026-10-20', {refs[0]}),
                ('完成《字词随练》第8页', '语文', 'learning', ['做完自行检查', '2026年10月20日晚完成', '2026年10月21日早读检查', '《字词随练》交给语文课代表'], '2026-10-20', {refs[0]}),
                ('《计算练习》第12页第1至6题', '数学', 'learning', ['列出计算过程', '做完自行检查', '2026年10月20日晚完成', '2026年10月21日上午交给数学课代表'], '2026-10-21', {refs[1]}),
                ('复习第4课《河畔聚落》', '历史', 'learning', ['完成课后练习第1、2题', '2026年10月20日晚完成', '2026年10月21日历史课检查'], '2026-10-20', {refs[2]}),
                ('订正上周《历史小练习》中做错的题', '历史', 'learning', ['每题写一句错因', '2026年10月20日晚完成', '2026年10月21日历史课检查'], '2026-10-20', {refs[2]}),
                ('听录音并跟读Lesson 3《The Garden》两遍', '英语', 'learning', ['2026年10月20日晚完成', '完成后请家长在英语作业记录本上签字', '2026年10月21日英语课检查'], '2026-10-20', {refs[3], refs[4]}),
                ('抄写Lesson 3《The Garden》单词表前6个单词，每个写3遍', '英语', 'learning', ['2026年10月20日晚完成', '完成后请家长在英语作业记录本上签字', '2026年10月21日英语课检查'], '2026-10-20', {refs[3], refs[4]}),
                ('《秋季安全教育回执》上签字', '', 'admin', ['2026年10月22日前交回班主任', '无需盖章'], '2026-10-22', {refs[5]})):
            brief, saved_due, saved_refs, row = unit(literal)
            self.assertTrue(all(s in brief['goal'] for s in standards), (literal, brief['goal']))
            self.assertEqual((brief['purpose'], saved_due, saved_refs), (purpose, due, cited), literal)
            self.assertTrue(brief['title'].startswith(subject + '：') if subject else not re.search(agent._SCHOOL_NATIVE_SUBJECTS, brief['title']), brief['title'])
            if row['task_id']:
                self.assertEqual(visible[row['task_id']]['agenda']['due_on'], due, literal)
        # The receipt keeps its own day and stays administrative; the signature is no third English task, and the
        # English supplement is no other teacher's standard.
        receipt = unit('《秋季安全教育回执》上签字')[0]['goal']
        self.assertNotIn('2026年10月20日', receipt);self.assertNotIn('盖章', receipt.replace('无需盖章', ''))
        self.assertEqual(sum('英语作业记录本' in b['goal'] for b, *_ in saved), 2)
        self.assertEqual({b['title'][:2] for b, _, cited, _ in saved if refs[4] in cited}, {'英语'})
        # Each card reads alone: its action first, then its own completion, signature and check lines. The date lead is one
        # reading (数学：完成…, never 晚完成…) and the goal keeps 晚完成; 本课 shows its own original's one lesson; no bare
        # 今天 line or list words (以上两项/这两项作业/两项都) remain. The anchors and originals stay literal.
        self.assertEqual(unit('《计算练习》第12页第1至6题')[0]['title'], '数学：完成《计算练习》第12页第1至6题')
        self.assertIn('2026年10月20日晚完成《计算练习》', unit('《计算练习》第12页第1至6题')[0]['goal'])
        copy, *_, copy_row = unit('抄写Lesson 3《The Garden》单词表前6个单词')
        self.assertEqual((copy['title'], copy['goal']), ('英语：抄写Lesson 3《The Garden》单词表前6个单词',
                         '抄写Lesson 3《The Garden》单词表前6个单词，每个写3遍\n2026年10月20日晚完成\n完成后请家长在英语作业记录本上签字\n2026年10月21日英语课检查'))
        self.assertIn('抄写本课单词表前6个单词，每个写3遍', [a['quote'] for a in json.loads(copy_row['plan'])['school_original_action']['anchors']])
        for brief, *_ in saved:
            self.assertFalse(set(brief['goal'].split('\n')) & {'今天'} or re.search('以上两项|这两项作业|两项都', brief['goal']), brief['goal'])

    def test_this_lesson_reads_only_its_own_originals_one_lesson_and_a_date_lead_keeps_its_day_part_in_the_goal(self):
        """本课 is never guessed from two lessons or another message; one date-lead reading strips 20日晚 but not 早读."""
        def values(*texts):
            evidence = [dict(ref='message:s:' + str(n), text=text, time='2026-10-20T16:%02d:00+08:00' % n, kind='text', content_incomplete=False,
                             attachments=[], unread=False, publisher='publisher:english', message_order=str(n)) for n, text in enumerate(texts, 10)]
            texts = {e['ref']: e['text'] for e in evidence}
            return {a['quote']: agent._school_native_value(a, texts[a['ref']]) for a in agent._school_native_actions(evidence)}
        copy = '抄写本课单词表前6个单词，每个写3遍'
        for texts in (['英语：今天有两项作业：1. 跟读Lesson 3《The Garden》和Lesson 4《The River》各两遍；2. ' + copy + '。'],
                      ['英语：本周学习Lesson 3《The Garden》。', '英语：今天有两项作业：1. 听录音并跟读课文两遍；2. ' + copy + '。']):
            value = values(*texts)[copy]
            self.assertEqual((value['title'], value['goal'].split('\n')[0]), ('英语：抄写本课单词表前6个单词', copy), texts)
        # The same original's one lesson still names an outside 本课; a closed literal name (《本课单词表》) stays whole.
        value = values('英语：今天有两项作业：1. 听录音并跟读Lesson 3《The Garden》两遍；2. ' + copy + '。')[copy]
        self.assertEqual(value['title'], '英语：抄写Lesson 3《The Garden》单词表前6个单词')
        literal = values('英语：今天完成两项：1. 跟读Lesson 3《The Garden》两遍；2. 抄写《本课单词表》第1页。')['抄写《本课单词表》第1页']
        self.assertEqual((literal['title'], literal['goal'].split('\n')[0]), ('英语：抄写《本课单词表》第1页', '抄写《本课单词表》第1页'))
        dated = values('数学：2026年10月20日晚完成《计算练习》第12页第1至6题，列出计算过程；2026年10月21日上午交给数学课代表。')
        self.assertEqual([(v['title'], v['goal']) for v in dated.values()],
                         [('数学：完成《计算练习》第12页第1至6题', '2026年10月20日晚完成《计算练习》第12页第1至6题，列出计算过程；2026年10月21日上午交给数学课代表')])
        early = values('语文：今天完成两项：1. 2026年10月21日早读前背诵《春》第一段；2. 抄写《春》生字每个两遍。')
        self.assertEqual(early['2026年10月21日早读前背诵《春》第一段']['title'], '语文：早读前背诵《春》第一段')

    def test_a_held_out_day_reply_missing_a_numbered_item_is_not_silently_ready(self):
        payload, refs, reply = self._daily_lists()
        self._use_replies(payload, [dict(proposals=[p for p in reply if not p['title_quote'].startswith('复习第4课')])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))

    def test_the_same_clause_list_from_another_teacher_binds_to_no_english_item(self):
        """The supplement's identity is the list's own teacher: the same words from another teacher bind to nothing."""
        evidence = [dict(ref='message:s:' + n, text=text, time='2026-10-20T16:' + clock + ':00+08:00', kind='text', content_incomplete=False,
                         attachments=[], unread=False, publisher=publisher, message_order=n)
                    for n, clock, publisher, text in (
                        ('14', '16', 'publisher:english', '英语：今天有两项作业：1. 听录音并跟读Lesson 3《The Garden》两遍；2. 抄写本课单词表前6个单词，每个写3遍。'),
                        ('15', '17', 'publisher:english', '补充英语作业：以上两项均在2026年10月20日晚完成，完成后请家长在英语作业记录本上签字；2026年10月21日英语课检查这两项作业。'))]
        bound = lambda: [len(a.get('shared_supplements', [])) for a in agent._school_native_actions(evidence)]
        self.assertEqual(bound(), [1, 1])
        evidence[1]['publisher'] = 'publisher:history'
        self.assertEqual(bound(), [0, 0])


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

    # Fictional known regression A, byte-for-byte: four originals and the saved model reply whose excerpt anchor omits its
    # own completion limit and its handback. Only the collector identity is supplied: each symbolic publisher becomes the
    # same sender_id (publisher:p1-heldout-a-language -> sender_id p1-heldout-a-language -> one natural publisher hash), so
    # one teacher stays one identity and the head teacher and parent stay others. Times, refs, texts and the reply are kept;
    # the originals carry no message_order, so none is invented.
    _A_MESSAGES = [
        ('1', '2026-10-16T17:00:00+08:00', 'p1-heldout-a-language', '虚构语文老师',
         '语文：2026年10月18日20:00前完成《河岸随记》的阅读摘记，摘录两句并各写一句选择理由；摘记本2026年10月19日早读交给语文课代表；2026年10月19日早读默写《山行》全文。'),
        ('2', '2026-10-16T17:03:00+08:00', 'p1-heldout-a-head', '虚构班主任',
         '请家长2026年10月20日前把秋季活动回执签字交班主任；老师会在班会说明活动安排，此说明仅供参考。'),
        ('3', '2026-10-16T17:10:00+08:00', 'p1-heldout-a-language', '虚构语文老师',
         '更正：摘记本改为2026年10月20日早读交给语文课代表；摘记仍须2026年10月18日20:00前完成；《山行》默写安排不变。'),
        ('4', '2026-10-16T17:15:00+08:00', 'p1-heldout-a-parent', '虚构家长', '家长问：摘记本是不是只交一本？活动回执有没有电子版？')]
    _A_REPLY = json.loads('{"proposals": [{"title_quote": "完成《河岸随记》的阅读摘记，摘录两句并各写一句选择理由", "focus": "school", "due": "2026-10-20", "evidence": [{"ref": "message:p1-heldout-a:1"}, {"ref": "message:p1-heldout-a:3"}], "task_title": "语文：完成《河岸随记》阅读摘记", "task_goal": "完成《河岸随记》的阅读摘记：摘录两句，并各写一句选择理由。\\n摘记须在2026年10月18日20:00前完成。\\n摘记本于2026年10月20日早读交给语文课代表（原为10月19日早读交，已更正为10月20日早读）。", "task_advice": "可先通读《河岸随记》，选定两句后分别写下选择理由，再誊入摘记本。", "learning_subject": "语文", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求完成摘记、摘录两句并各写一句理由，且更正后交回时间明确。", "task_purpose": "learning", "task_submission": "摘记本于2026年10月20日早读交给语文课代表。"}, {"title_quote": "2026年10月19日早读默写《山行》全文", "focus": "school", "due": "2026-10-19", "evidence": [{"ref": "message:p1-heldout-a:1"}, {"ref": "message:p1-heldout-a:3"}], "task_title": "语文：早读默写《山行》全文", "task_goal": "2026年10月19日早读默写《山行》全文。\\n《山行》默写安排不变。", "task_advice": "可提前熟记《山行》全文，默写前自查易错字。", "learning_subject": "语文", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确安排2026年10月19日早读默写《山行》全文，且更正说明该安排不变。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "请家长2026年10月20日前把秋季活动回执签字交班主任", "focus": "school", "due": "2026-10-20", "evidence": [{"ref": "message:p1-heldout-a:2"}], "task_title": "秋季活动回执签字交班主任", "task_goal": "请家长在2026年10月20日前把秋季活动回执签字后交班主任。\\n老师会在班会说明活动安排，此说明仅供参考。", "task_advice": "可先签字回执，再按班主任要求交回。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求家长在2026年10月20日前将秋季活动回执签字交班主任。", "task_purpose": "admin", "task_submission": "签字后的秋季活动回执交班主任。"}, {"title_quote": "家长问：摘记本是不是只交一本？活动回执有没有电子版？", "focus": "school", "due": "", "evidence": [{"ref": "message:p1-heldout-a:4"}], "task_title": "", "task_goal": "", "task_advice": "", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "reference", "task_reason": "家长提问，不是新增学校要求，不生成任务。", "task_purpose": "optional", "task_submission": ""}]}')

    def _a_select(self, texts=None, publishers=None, excerpt=None, extra=()):
        """Real _select on A's originals and reply; a variant replaces only the named texts, publishers or excerpt fields."""
        texts = texts or {};publishers = publishers if publishers is not None else {}
        evidence = [dict(ref='message:p1-heldout-a:' + n, text=texts.get(n, text), time=time, kind='text', content_incomplete=False,
                         attachments=[], unread=False, sender=sender,
                         **({} if publishers.get(n, publisher) is None else dict(publisher=publishers.get(n, 'publisher:' + publisher))))
                    for n, time, publisher, sender, text in self._A_MESSAGES]
        reply = copy.deepcopy(self._A_REPLY);reply['proposals'][0].update(excerpt or {});reply['proposals'][1:1] = copy.deepcopy(list(extra))
        with patch.object(agent.family_llm, '_chat_json', return_value=reply):
            items = agent._select('school', evidence, school_goals=[], school_tasks=[], as_of='2026-10-16')
        return items

    def test_known_a_short_excerpt_anchor_saves_the_corrected_handback_day_from_its_whole_original(self):
        self.fixture.source['id'] = 'p1-heldout-a';self.fixture.config()
        stamp = '2026-10-16T17:20:00+08:00'
        payload = dict(source_id='p1-heldout-a', expected_cursor='10', cursor='14', checked_at=stamp, last_message_time=stamp, error='',
                       messages=[dict(id=n, time=time, kind='text', sender=sender, sender_id=publisher, text=text, unread=False)
                                 for n, time, publisher, sender, text in self._A_MESSAGES])
        self.store.ingest(copy.deepcopy(payload))
        calls = []

        def saved_reply(messages, schema, name, timeout=60, *, data_path=None):
            context = json.loads(messages[-1]['content'])
            self.assertEqual([(e['ref'], e['text'], e['time']) for e in context['evidence']],
                             [('message:p1-heldout-a:' + n, text, time) for n, time, _, _, text in self._A_MESSAGES])
            self.assertEqual(len({e['publisher'] for e in context['evidence']}), 3)
            self.assertEqual(context['evidence'][0]['publisher'], context['evidence'][2]['publisher'])
            calls.append(name)
            return copy.deepcopy(self._A_REPLY)

        self.model.side_effect = saved_reply
        now = dt.datetime(2026, 10, 16, 17, 30, tzinfo=agent.TZ)
        result = agent.run_once(self.app, now)
        self.assertEqual((result['failed'], result['processed'], len(calls)), (0, 4, 1))
        with self.store._db() as c:
            items = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")]
            tasks = {t['title']: dict(t) for t in c.execute('SELECT * FROM manual_tasks')}
            rows = [tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
        self.assertEqual([(m['id'], m['time'], m['text']) for m in originals], [(n, t, x) for n, t, _, _, x in self._A_MESSAGES])
        self.assertFalse(any('message_order' in m for m in originals), 'no collector order is invented')
        excerpt, = [i for i in items if '河岸随记' in i['title']]
        self.assertEqual((excerpt['due'], excerpt['state']), ('2026-10-20', 'accepted'))
        self.assertEqual([e['ref'] for e in json.loads(excerpt['evidence'])], ['message:p1-heldout-a:1', 'message:p1-heldout-a:3'])
        plan = json.loads(excerpt['plan'])
        self.assertEqual(plan['school_selection_receipt']['goal'], self._A_REPLY['proposals'][0]['task_goal'], 'the reply is kept as said')
        for words in ('2026年10月18日20:00前完成', '摘录两句', '各写一句选择理由', '2026年10月20日早读交给语文课代表'):
            self.assertIn(words, tasks['语文：完成《河岸随记》阅读摘记']['action'])
        self.assertIn('摘记本2026年10月19日早读交给语文课代表', tasks['语文：完成《河岸随记》阅读摘记']['source'], 'the old handback stays in its original')
        self.assertEqual({t: tasks[t]['due'] for t in tasks},
                         {'语文：完成《河岸随记》阅读摘记': '2026-10-20', '语文：早读默写《山行》全文': '2026-10-19', '秋季活动回执签字交班主任': '2026-10-20'})
        self.assertNotIn('河岸随记', tasks['语文：早读默写《山行》全文']['action'])
        self.assertNotIn('摘记', tasks['秋季活动回执签字交班主任']['action'])
        question, = [i for i in items if json.loads(i['evidence'])[0]['ref'] == 'message:p1-heldout-a:4']
        self.assertEqual(json.loads(question['plan'])['school_task']['state'], 'reference')
        self.assertFalse(question['task_id'], 'the parent question stays reference, never a todo')
        replay = agent.run_once(self.app, now + dt.timedelta(minutes=7))
        self.assertEqual((replay['processed'], replay['created'], len(calls)), (0, 0, 1))
        with self.store._db() as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')], rows, 'no second task')

    def test_a_same_shaped_excerpt_of_another_subject_and_book_reads_its_whole_original_range(self):
        texts = {'1': '英语：2026年11月3日19:30前完成《海边灯塔》的读书卡，写出三个生词并各造一个句子；读书卡2026年11月4日第一节课前交给英语课代表；2026年10月19日早读默写《山行》全文。',
                 '3': '更正：读书卡改为2026年11月5日第一节课前交给英语课代表；读书卡仍须2026年11月3日19:30前完成；《山行》默写安排不变。'}
        items = self._a_select(texts, excerpt=dict(
            title_quote='完成《海边灯塔》的读书卡，写出三个生词并各造一个句子', due='2026-11-05', task_title='英语：完成《海边灯塔》读书卡',
            task_goal='完成《海边灯塔》的读书卡：写出三个生词，并各造一个句子。\n读书卡须在2026年11月3日19:30前完成。\n读书卡于2026年11月5日第一节课前交给英语课代表（原为11月4日，已更正）。',
            task_submission='读书卡于2026年11月5日第一节课前交给英语课代表。', learning_subject='英语'))
        card, = [i for i in items if '海边灯塔' in i['title']]
        self.assertEqual((card['due'], card['plan']['school_task']['state']), ('2026-11-05', 'ready'))
        dictation, = [i for i in items if '山行' in i['title']]
        self.assertEqual((dictation['due'], dictation['plan']['school_task']['state']), ('2026-10-19', 'ready'))

    def test_an_unproven_excerpt_range_or_correction_keeps_the_short_anchor_for_review(self):
        self.assertEqual([(i['due'], i['plan']['school_task']['state']) for i in self._a_select() if '河岸随记' in i['title']],
                         [('2026-10-20', 'ready')])
        first = self._A_MESSAGES[0][4];fix = self._A_MESSAGES[2][4]
        cases = {
            'another teacher corrects': dict(publishers={'3': 'publisher:p1-heldout-a-head'}),
            'no publisher proves the teacher': dict(publishers={'1': None, '3': None}),
            'an empty publisher proves no one': dict(publishers={'1': '', '3': ''}),
            'another object is handed back': dict(texts={'1': first.replace('摘记本2026', '回执2026'), '3': fix.replace('摘记本改为', '回执改为')}),
            'the correction names another book': dict(texts={'3': fix.replace('摘记本改为', '《湖畔随记》摘记本改为')}),
            'the anchor drops its verb': dict(excerpt=dict(title_quote='《河岸随记》的阅读摘记，摘录两句并各写一句选择理由')),
            'the anchor stops inside its clause': dict(excerpt=dict(title_quote='完成《河岸随记》的阅读摘记')),
            'another action precedes the anchor': dict(texts={'1': first.replace('20:00前完成', '20:00前朗读课文，完成'),
                                                              '3': fix.replace('摘记仍须2026年10月18日20:00前完成', '摘记仍须按时完成')}),
            'the handback does not follow the completion': dict(texts={'1': first.replace('2026年10月18日20:00前', '2026年10月21日20:00前'),
                                                                       '3': fix.replace('2026年10月18日20:00前', '2026年10月21日20:00前')}),
            'the anchor is in two originals': dict(texts={'3': fix + '完成《河岸随记》的阅读摘记，摘录两句并各写一句选择理由。'}),
            # Another proposal quoting the handback clause makes the range shared, so it is not this excerpt's own.
            'another proposal claims the handback clause': dict(extra=[dict(
                self._A_REPLY['proposals'][1], title_quote='摘记本2026年10月19日早读交给语文课代表', due='2026-10-20',
                task_title='语文：交摘记本', task_goal='摘记本2026年10月20日早读交给语文课代表。')]),
            # The old day kept as the item's own while its note claims an unproven change: the note is not history, so it stays read.
            'an unproven change note on the old day': dict(publishers={'3': 'publisher:p1-heldout-a-head'}, excerpt=dict(
                due='2026-10-19', task_goal=self._A_REPLY['proposals'][0]['task_goal'].replace('摘记本于2026年10月20日', '摘记本于2026年10月19日'))),
        }
        for name, case in cases.items():
            with self.subTest(name):
                if name == 'another action precedes the anchor':
                    # The listed reading action is an outcome of its own, so this reply leaves the whole batch retried.
                    with self.assertRaises(agent.AgentError) as refused:self._a_select(**case)
                    self.assertEqual(refused.exception.code, 'school_action_coverage')
                    continue
                excerpt, = [i for i in self._a_select(**case) if '河岸随记' in i['title']]
                self.assertEqual(excerpt['plan']['school_task']['state'], 'review')
                self.assertEqual([q['ref'] for q in excerpt['evidence']], ['message:p1-heldout-a:1', 'message:p1-heldout-a:3'])

    # Frozen synthetic chronology variants of A (criteria 1352afeb…): only the declared time, collector message_order or ref of
    # A's first original and its correction change; every text, publisher, as_of and the saved reply stay as they were.
    _SAME = '2026-10-16T17:00:00+08:00'
    _A_CHRONOLOGY = {
        'T00-original-strictly-later': (dict(), True),
        'T01-same-instant-no-order': (dict(time=_SAME), False),
        'T02-same-instant-equal-order': (dict(time=_SAME, orders=('11', '11')), False),
        'T03-same-instant-reversed-order': (dict(time=_SAME, orders=('12', '11')), False),
        'T04-same-instant-explicit-increasing-order': (dict(time=_SAME, orders=('11', '12')), True),
        'T05-same-instant-numeric-ref-900-to12-no-order': (
            dict(time=_SAME, refs=('message:p1-heldout-a:900', 'message:p1-heldout-a:12')), False),
        'T06-different-source-same-symbolic-publisher': (dict(refs=(None, 'message:fictional-other-source:3')), False),
        'T07-earlier-correction-time': (dict(time='2026-10-16T16:59:00+08:00'), False),
        'T08-same-instant-numeric-ref-900-to12-positive-order': (
            dict(time=_SAME, refs=('message:p1-heldout-a:900', 'message:p1-heldout-a:12'), orders=('11', '12')), True),
    }
    # T05, T06 and T08 remap refs the unchanged reply does not cite, so they stay direct-helper evidence only.
    _A_SAVED = ('T00-original-strictly-later', 'T01-same-instant-no-order', 'T02-same-instant-equal-order',
                'T03-same-instant-reversed-order', 'T04-same-instant-explicit-increasing-order', 'T07-earlier-correction-time')

    def _a_evidence(self, time=None, orders=(None, None), refs=(None, None)):
        evidence = [dict(ref='message:p1-heldout-a:' + n, text=text, time=t, kind='text', content_incomplete=False, attachments=[],
                         unread=False, sender=sender, publisher='publisher:' + publisher)
                    for n, t, publisher, sender, text in self._A_MESSAGES]
        if time:evidence[2]['time'] = time
        for entry, order, ref in zip((evidence[0], evidence[2]), orders, refs):
            if order is not None:entry['message_order'] = order
            if ref is not None:entry['ref'] = ref
        return evidence

    def test_frozen_a_chronology_corrects_the_handback_only_when_strictly_later_from_the_same_teacher_and_source(self):
        from family_agenda import sent_day
        original = self._A_MESSAGES[0][4].split('；2026年10月19日早读默写')[0]
        corrected = original.replace('摘记本2026年10月19日', '摘记本2026年10月20日')
        for name, (change, proven) in self._A_CHRONOLOGY.items():
            with self.subTest(name):
                evidence = self._a_evidence(**change);home, fix = evidence[0], evidence[2]
                self.assertEqual(agent._school_native_later_text(home, fix), proven)
                quote = agent._school_corrected_quote(original, home, [home, fix])
                self.assertEqual(quote, corrected if proven else original)
                self.assertEqual(agent._school_own_dates(quote, sent_day(home['time'])), {'2026-10-20' if proven else '2026-10-19'})
                self.assertEqual(evidence, self._a_evidence(**change), 'the originals are read, never rewritten')
        # An order that is not both sides' plain decimal collector position orders nothing within the same second.
        for orders in (('11', '12a'), ('11', '-12'), ('11', ' 12'), ('11', '１２'), ('11', ''), ('', '12'), ('11', '1' * 41)):
            with self.subTest(orders=orders):
                evidence = self._a_evidence(time=self._SAME, orders=orders)
                self.assertFalse(agent._school_native_later_text(evidence[0], evidence[2]))
                self.assertEqual(agent._school_corrected_quote(original, evidence[0], [evidence[0], evidence[2]]), original)

    def test_the_shared_later_proof_needs_one_positive_stable_publisher_at_every_gap(self):
        original = self._A_MESSAGES[0][4].split('；2026年10月19日早读默写')[0]
        stable = lambda sender:agent._publisher('p1-heldout-a', {} if sender is None else dict(sender_id=sender))
        self.assertEqual(stable('p1-heldout-a-language'), stable('p1-heldout-a-language'))
        self.assertNotIn(stable('p1-heldout-a-language'), ('publisher:p1-heldout-a-language', stable('p1-heldout-a-head')))
        cases = {
            'the same symbolic publisher': ('publisher:p1-heldout-a-language', 'publisher:p1-heldout-a-language', True),
            'one stable collector hash': (stable('p1-heldout-a-language'), stable('p1-heldout-a-language'), True),
            'another symbolic publisher': ('publisher:p1-heldout-a-language', 'publisher:p1-heldout-a-head', False),
            'another stable collector hash': (stable('p1-heldout-a-language'), stable('p1-heldout-a-head'), False),
            'a raw symbolic string is not its stable hash': ('publisher:p1-heldout-a-language', stable('p1-heldout-a-language'), False),
            'both publishers missing': (None, None, False),
            'both publishers empty': ('', '', False),
            'both publishers blank': (' ', ' ', False),
            'no sender id hashes to no one': (stable(None), stable(None), False),
        }
        for change in (dict(), dict(time=self._SAME, orders=('11', '12'))):
            for name, (first, second, proven) in cases.items():
                with self.subTest(name, same_instant=bool(change)):
                    evidence = self._a_evidence(**change)
                    for entry, publisher in ((evidence[0], first), (evidence[2], second)):
                        entry.pop('publisher')
                        if publisher is not None:entry['publisher'] = publisher
                    self.assertEqual(agent._school_native_later_text(evidence[0], evidence[2]), proven)
                    self.assertEqual(agent._school_corrected_quote(original, evidence[0], [evidence[0], evidence[2]]) != original, proven)

    def test_frozen_a_chronology_variants_save_only_a_proven_correction_through_ingest_reopen_and_replay(self):
        # The strictly later T00 times whose teacher messages carry no sender_id: the collector hashes no publisher, so no one.
        cases = [(case, *self._A_CHRONOLOGY[case], False) for case in self._A_SAVED] + [('T00-without-sender-ids', dict(), False, True)]
        for case, change, proven, anonymous in cases:
            with self.subTest(case):
                self.setUp()
                self.fixture.source['id'] = 'p1-heldout-a';self.fixture.config()
                stamp = '2026-10-16T17:20:00+08:00'
                messages = [dict(id=n, time=time, kind='text', sender=sender, sender_id=publisher, text=text, unread=False)
                            for n, time, publisher, sender, text in self._A_MESSAGES]
                for message in (messages[0], messages[2]) if anonymous else ():message.pop('sender_id')
                if change.get('time'):messages[2]['time'] = change['time']
                for message, order in zip((messages[0], messages[2]), change.get('orders', (None, None))):
                    if order is not None:message['message_order'] = order
                self.store.ingest(dict(source_id='p1-heldout-a', expected_cursor='10', cursor='14', checked_at=stamp,
                                       last_message_time=stamp, error='', messages=copy.deepcopy(messages)))
                calls = []

                def saved_reply(prompt, schema, name, timeout=60, *, data_path=None):
                    context = json.loads(prompt[-1]['content'])
                    self.assertEqual([e['publisher'] for e in context['evidence']],
                                     [agent._publisher('p1-heldout-a', m) for m in messages])
                    self.assertFalse(any('message_order' in e for e in context['evidence']))
                    calls.append(name)
                    return copy.deepcopy(self._A_REPLY)

                self.model.side_effect = saved_reply
                now = dt.datetime(2026, 10, 16, 17, 30, tzinfo=agent.TZ)
                result = agent.run_once(self.app, now)
                self.assertEqual((result['failed'], result['processed'], len(calls)), (0, 4, 1))

                def saved(store):
                    with store._db() as c:
                        return ([dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")],
                                [dict(t) for t in c.execute('SELECT * FROM manual_tasks ORDER BY id')],
                                [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')],
                                c.execute('SELECT COUNT(*) FROM records').fetchone()[0],
                                c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0])

                items, tasks, originals, records, updates = saved(self.store)
                self.assertEqual([(m['id'], m['time'], m['text'], m.get('message_order')) for m in originals],
                                 [(m['id'], m['time'], m['text'], m.get('message_order')) for m in messages], 'only declared order')
                self.assertEqual((records, updates), (0, 0))
                excerpt, = [i for i in items if '河岸随记' in i['title']]
                plan = json.loads(excerpt['plan'])
                self.assertEqual(plan['school_selection_receipt']['goal'], self._A_REPLY['proposals'][0]['task_goal'])
                self.assertEqual([e['ref'] for e in json.loads(excerpt['evidence'])], ['message:p1-heldout-a:1', 'message:p1-heldout-a:3'])
                due = {t['title']: t['due'] for t in tasks}
                if proven:
                    self.assertEqual((excerpt['due'], excerpt['state'], plan['school_task']['state']), ('2026-10-20', 'accepted', 'ready'))
                    self.assertEqual(due.pop('语文：完成《河岸随记》阅读摘记'), '2026-10-20')
                else:
                    # Unproven order: neither accepted nor a mandatory corrected task; the item waits for a parent's review.
                    self.assertNotEqual(excerpt['state'], 'accepted')
                    self.assertEqual(plan['school_task']['state'], 'review')
                    self.assertFalse(excerpt['task_id'])
                    self.assertNotIn('语文：完成《河岸随记》阅读摘记', due)
                    self.assertFalse(any('河岸随记' in t['action'] for t in tasks))
                # The independent dictation and receipt keep their own days; neither dates A, and the parent question stays reference.
                self.assertEqual(due, {'语文：早读默写《山行》全文': '2026-10-19', '秋季活动回执签字交班主任': '2026-10-20'})
                question, = [i for i in items if json.loads(i['evidence'])[0]['ref'] == 'message:p1-heldout-a:4']
                self.assertEqual((json.loads(question['plan'])['school_task']['state'], question['task_id']), ('reference', ''))
                reopened = agent.Store(self.app.connect, self.app.profiles, self.fixture.data, app=self.app)
                self.assertEqual(saved(reopened), (items, tasks, originals, records, updates), 'a reopened store reads the same save')
                replay = agent.run_once(self.app, now + dt.timedelta(minutes=7))
                self.assertEqual((replay['failed'], replay['processed'], replay['created'], len(calls)), (0, 0, 0, 1))
                self.assertEqual(saved(self.store), (items, tasks, originals, records, updates), 'the same numbering saves nothing twice')
                self.doCleanups()


class SchoolActionPurposeTests(unittest.TestCase):
    """Known fictional F: learning or administrative use follows each item's own action and outcome.

    Fixed receipts are local substitutes. The old Flash receipt came from the previous prompt and is only a
    program control; none of these replies measures the changed prompt's real model accuracy.
    """
    setUp = SchoolNativeCoverageTests.setUp
    _use_replies = SchoolNativeCoverageTests._use_replies
    _ingest = SchoolNativeCoverageTests._ingest
    _assert_rejected_batch = SchoolNativeCoverageTests._assert_rejected_batch
    F_MESSAGES = (
        ('2026-10-16T19:00:00+08:00', '示例科学老师', 'p1-heldout-f-science',
         '科学：请于2026年11月2日18:30前写好《叶片观察》记录卡，分别记录两种叶片的颜色和边缘形状；记录卡2026年11月3日科学课交给科学老师。'),
        ('2026-10-16T19:03:00+08:00', '示例班主任', 'p1-heldout-f-head',
         '班主任：2026年11月4日科学课前带两片不同的落叶，用一个透明袋装好，不用购买标本。'),
        ('2026-10-16T19:10:00+08:00', '示例科学老师', 'p1-heldout-f-science',
         '更正：《叶片观察》记录卡改为2026年11月5日科学课交给科学老师；11月2日18:30前写好的要求不变。'),
        ('2026-10-16T19:15:00+08:00', '示例家长', 'p1-heldout-f-parent', '家长问：记录卡拍照提交是否就不用交纸质了？'))
    # The unchanged projected fields of the known Flash receipt (old prompt), evidence by message position.
    F_RAW = (
        dict(title_quote='请于2026年11月2日18:30前写好《叶片观察》记录卡，分别记录两种叶片的颜色和边缘形状', focus='school', due='2026-11-05',
             evidence=[0, 2], task_title='科学：完成《叶片观察》记录卡',
             task_goal='2026年11月2日18:30前写好《叶片观察》记录卡。\n分别记录两种叶片的颜色和边缘形状。\n记录卡于2026年11月5日科学课交给科学老师（原为11月3日，已更正）。',
             task_advice='可先观察两种叶片，再分别填写颜色和边缘形状，写完后按更正后的日期带去科学课。', learning_subject='科学', learning_goal_id='',
             task_change='new', task_target_id='', task_state='ready',
             task_reason='科学老师明确要求全班完成记录卡，并给出完成时间、记录内容和更正后的交回时间。', task_purpose='learning',
             task_submission='2026年11月5日科学课交给科学老师'),
        dict(title_quote='2026年11月4日科学课前带两片不同的落叶，用一个透明袋装好，不用购买标本。', focus='school', due='2026-11-04',
             evidence=[1], task_title='科学：带两片不同落叶（11月4日）',
             task_goal='2026年11月4日科学课前带两片不同的落叶。\n用一个透明袋装好。\n不用购买标本。',
             task_advice='可提前捡拾两片不同落叶，装入透明袋并确认日期。', learning_subject='科学', learning_goal_id='',
             task_change='new', task_target_id='', task_state='ready',
             task_reason='班主任明确要求2026年11月4日科学课前带两片不同落叶，并说明不用购买标本。', task_purpose='learning',
             task_submission=''),
        dict(title_quote='家长问：记录卡拍照提交是否就不用交纸质了？', focus='school', due='', evidence=[3], task_title='', task_goal='',
             task_advice='', learning_subject='', learning_goal_id='', task_change='new', task_target_id='', task_state='reference',
             task_reason='家长仅询问拍照提交是否可替代纸质提交，属于个人提问，不是新增学校要求，也不改变已明确的交回方式。',
             task_purpose='optional', task_submission=''))

    def _known_f(self, replies):
        """Ingest F, run the real intake once, then reopen (replay) it; return the saved facts per original role."""
        self.fixture.now = self.now = dt.datetime(2026, 10, 16, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='14')
        payload['messages'] = [dict(id=str(11 + i), message_order=str(11 + i), time=time, kind='text', sender=sender,
                                    sender_id=publisher, text=text, unread=False)
                               for i, (time, sender, publisher, text) in enumerate(self.F_MESSAGES)]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        replies = [dict(copy.deepcopy(r), evidence=[dict(ref=refs[i]) for i in r['evidence']]) for r in replies]
        self._use_replies(payload, [dict(proposals=replies)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 4))

        def facts():
            with self.store._db() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
                originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            with self.app.connect() as c:
                tasks = {t['id']: t for t in self.app.tasks(c)}
            roles = {}
            for row in rows:
                cited = [e['ref'] for e in json.loads(row['evidence'])]
                plan = json.loads(row['plan'])
                task = tasks.get(row['task_id'])
                roles[{refs[0]: 'F1', refs[1]: 'F2', refs[3]: 'parent'}[cited[0]]] = dict(
                    id=row['id'], task_id=row['task_id'], state=row['state'], due=row['due'], refs=cited,
                    brief_state=plan['school_task']['state'], purpose=plan['school_task'].get('purpose'),
                    school_learning=plan.get('school_learning'), goal_id=plan.get('school_goal_id', ''),
                    category=task['agenda']['category'] if task else '', due_on=task['agenda']['due_on'] if task else '',
                    action=task['action'] if task else '')
            goals = goals_store.school_candidates(self.source['child_id'])
            return roles, sorted(tasks), originals, goals

        from family_goals import Store as Goals
        goals_store = Goals(self.app, self.store)
        first = facts()
        self.assertEqual(first[2], payload['messages'], 'the complete originals stay unchanged')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(facts(), first, 'reopen keeps the same items, tasks, links and goals without duplicates')
        self.assertEqual(self.model.call_count, 1)
        return first[0], first[3]

    def test_known_f_carrying_is_admin_and_the_record_card_stays_learning_through_save_and_reopen(self):
        # The changed contract's expected reply; the second variant is a model that labels the carrying admin but
        # still fills a subject: an administrative action never keeps a learning link either way.
        for subject in ('', '科学'):
            with self.subTest(subject=subject):
                t = type(self)(methodName='runTest')
                t.setUp()
                try:
                    replies = copy.deepcopy(self.F_RAW)
                    replies[1].update(task_purpose='admin', learning_subject=subject)
                    roles, goals = t._known_f(replies)
                    self.assertEqual(set(roles), {'F1', 'F2', 'parent'})
                    f1, f2, parent = roles['F1'], roles['F2'], roles['parent']
                    self.assertEqual((f2['purpose'], f2['school_learning'], f2['goal_id'], f2['state'], f2['due'], f2['category'], f2['due_on']),
                                     ('admin', None, '', 'accepted', '2026-11-04', 'todo', '2026-11-04'),
                                     'carrying stays a pending administrative to-do without a learning link')
                    for standard in ('两片不同的落叶', '一个透明袋', '不用购买标本'):self.assertIn(standard, f2['action'])
                    self.assertEqual(f2['refs'], ['message:' + t.source['id'] + ':12'])
                    self.assertEqual((f1['purpose'], f1['school_learning'], f1['state'], f1['due'], f1['category']),
                                     ('learning', dict(subject='科学', goal_id=''), 'accepted', '2026-11-05', 'homework'))
                    self.assertTrue(f1['goal_id'], 'the record card alone routes to a school learning goal')
                    self.assertIn('2026年11月2日18:30前', f1['action'])
                    self.assertEqual([(g['subject'], g['id']) for g in goals], [('科学', f1['goal_id'])],
                                     'only the learning outcome creates the one science goal')
                    self.assertEqual((parent['brief_state'], parent['task_id'], parent['school_learning']), ('reference', '', None))
                finally:t.doCleanups()

    # Known fictional K03: the actual parsed Flash reply (configured effort none) on c131 was admin/ready/due 10-29 with
    # no subject; only the program's guard read 阅读 inside the closed form name. Fixed here as a program control.
    K03_TEXT = '请于2026年10月29日前填写《语文阅读调查登记表》的学生姓名和家长联系方式，家长签字后交回班主任。本次只登记这些信息。'
    K03_RAW = dict(title_quote='请于2026年10月29日前填写《语文阅读调查登记表》的学生姓名和家长联系方式，家长签字后交回班主任。', focus='school',
                   due='2026-10-29', evidence=[0], task_title='填写《语文阅读调查登记表》并交回',
                   task_goal='填写《语文阅读调查登记表》的学生姓名和家长联系方式。\n本次只登记这些信息。\n家长签字后交回班主任。\n2026年10月29日前完成。',
                   task_advice='可先确认学生姓名与家长联系方式无误，再请家长签字，按班主任要求交回。', learning_subject='', learning_goal_id='',
                   task_change='new', task_target_id='', task_state='ready',
                   task_reason='已读文字明确要求填写登记表、家长签字并交回班主任，属全班或本孩子需办理的行政事务。', task_purpose='admin',
                   task_submission='家长签字后交回班主任')

    def test_known_k03_form_name_is_not_learning_through_save_auto_intake_and_fresh_store_reopen(self):
        self.fixture.now = self.now = dt.datetime(2026, 10, 16, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time='2026-10-16T18:03:00+08:00', kind='text', sender='示例学校发布人',
                                    sender_id='p1-classification-k03-school', text=self.K03_TEXT, unread=False)]
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':11'
        self._use_replies(payload, [dict(proposals=[dict(copy.deepcopy(self.K03_RAW), evidence=[dict(ref=ref)])])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        from family_goals import Store as Goals
        import family_review

        def facts(app, store):
            with store._db() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
                originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            with app.connect() as c:
                tasks = {t['id']: t for t in app.tasks(c)}
            return rows, tasks, originals, Goals(app, store).school_candidates(self.source['child_id'])

        def check(rows, tasks, originals, goals):
            row, = rows
            plan = json.loads(row['plan']);brief = plan['school_task'];task = tasks[row['task_id']]
            self.assertEqual((row['state'], row['due'], brief['state'], brief['purpose'], plan.get('school_learning'), plan.get('school_goal_id', '')),
                             ('accepted', '2026-10-29', 'ready', 'admin', None, ''), 'a pure registration stays a pending administrative to-do')
            self.assertEqual((task['agenda']['category'], task['agenda']['due_on']), ('todo', '2026-10-29'))
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], [ref])
            for standard in ('《语文阅读调查登记表》', '学生姓名', '家长联系方式', '家长签字', '交回班主任', '本次只登记这些信息'):
                self.assertIn(standard, task['action'])
            self.assertEqual(plan['school_selection_receipt']['purpose'], 'admin')
            self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no attachment was read or prepared')
            self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')
            self.assertEqual(goals, [], 'no school learning goal')

        first = facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app))
        check(*fresh)
        self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first[0]], 'reopen keeps the one item without duplicates')
        self.assertEqual(sorted(fresh[1]), sorted(first[1]))
        self.assertEqual(self.model.call_count, 1)

    def test_closed_form_name_is_an_object_while_outside_learning_open_or_other_names_stay_guarded(self):
        value = dict(title='', goal='', advice='', state='ready', reason='', purpose='admin')
        ready = (self.K03_TEXT, '请家长在《数学练习安排确认单》上签字，2026年10月21日交回班主任。')
        review = (self.K03_TEXT + '另请阅读课文第3段。', self.K03_TEXT + '完成第1-3题后再签字。',
                  self.K03_TEXT.replace('》', ''), '请完成《阅读理解专项练习》第3页并签字交回。',
                  '请填写《阅读，调查登记表》并交回。', '朗读《语文阅读调查登记表》后签字交回。')
        for text, state in [(t, 'ready') for t in ready] + [(t, 'review') for t in review]:
            for separate in (False, True):
                with self.subTest(text=text, separate=separate):
                    evidence = [dict(ref='message:synthetic-form-name:1', text=text, kind='text', unread=False)]
                    brief = agent._school_brief(dict(value, title='登记事务', goal=text), evidence=evidence, separate_learning=separate)
                    self.assertEqual((brief['state'], brief['purpose'], brief['goal']), (state, 'admin', text))
                    self.assertEqual(evidence[0]['text'], text)
                    if state == 'review':self.assertIn('同时提到学习活动', brief['reason'])
        # A reply's own closed name that the original never wrote cannot hide the original's reading.
        evidence = [dict(ref='message:synthetic-form-name:2', text='请阅读课文并填写登记表交回。', kind='text', unread=False)]
        brief = agent._school_brief(dict(value, title='《阅读课文并填写登记表》', goal='《阅读课文并填写登记表》交回。'),
                                    evidence=evidence, separate_learning=True)
        self.assertEqual(brief['state'], 'review')

    # Root's frozen fictional 104 (a program counterexample, not a model result): the parent reads an administrative agreement
    # and signs its guardian field, the child only hands it back. The 15-field correct fixed reply is kept unchanged.
    P104_TEXT = '请家长今天阅读孩子带回的《图书借阅约定》，在末页“监护人”栏签字。孩子明天交给班主任。'
    P104_RAW = dict(title_quote='请家长今天阅读孩子带回的《图书借阅约定》，在末页“监护人”栏签字。孩子明天交给班主任', focus='school',
                    due='2026-10-23', evidence=[0], learning_subject='', learning_goal_id='', task_title='《图书借阅约定》家长阅读并签字',
                    task_goal=P104_TEXT, task_advice='', task_change='new', task_target_id='', task_state='ready',
                    task_reason='独立冻结的纯虚构程序验证固定回复，不是实际模型产物。', task_purpose='admin', task_submission='')
    READ_ALOUD_TEXT = '英语：今晚朗读课本第20页三遍，请家长听完后在这一页签字。'

    def test_a_parent_reading_what_the_parent_signs_saves_as_a_todo_beside_the_same_batch_learning(self):
        self.fixture.now = self.now = dt.datetime(2026, 10, 22, 16, 30, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='105')
        payload['messages'] = [
            dict(id='104', message_order='104', time='2026-10-22T16:20:00+08:00', kind='text', sender='蒋老师（虚构）',
                 sender_id='qa-teacher-head-jiang', text=self.P104_TEXT, unread=False),
            dict(id='105', message_order='105', time='2026-10-22T16:22:00+08:00', kind='text', sender='虚构英语老师',
                 sender_id='synthetic-english-teacher', text=self.READ_ALOUD_TEXT, unread=False)]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        reading = fixtures.school_proposal(
            title_quote='今晚朗读课本第20页三遍，请家长听完后在这一页签字', due='2026-10-22', evidence=[dict(ref=refs[1])],
            learning_subject='英语', task_title='英语：朗读课本第20页三遍', task_goal='今晚朗读课本第20页三遍，请家长听完后在这一页签字。',
            task_state='ready', task_reason='虚构回执。', task_purpose='learning')
        self._use_replies(payload, [dict(proposals=[dict(copy.deepcopy(self.P104_RAW), evidence=[dict(ref=refs[0])]), reading])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 2), 'the faithful admin reply finishes the batch')

        def facts():
            with self.store._db() as c:
                rows = {json.loads(r['evidence'])[0]['ref']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
                manual = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
                originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            with self.app.connect() as c:
                tasks = {t['id']: t for t in self.app.tasks(c) if t['id'] in {m['id'] for m in manual}}
            return rows, manual, tasks, originals

        rows, manual, tasks, originals = first = facts()
        self.assertEqual((sorted(rows), len(manual), len(tasks)), (sorted(refs), 2, 2))
        notice, homework = rows[refs[0]], rows[refs[1]]
        plan = json.loads(notice['plan']);brief = plan['school_task'];task = tasks[notice['task_id']]
        self.assertEqual((notice['state'], notice['due'], brief['state'], brief['purpose'], plan.get('school_learning')),
                         ('accepted', '2026-10-23', 'ready', 'admin', None), 'a parent reading and signing is an administrative to-do')
        self.assertEqual((task['agenda']['category'], task['title']), ('todo', '《图书借阅约定》家长阅读并签字'))
        for words in ('请家长今天阅读', '《图书借阅约定》', '末页“监护人”栏签字', '孩子明天交给班主任'):self.assertIn(words, task['action'])
        self.assertEqual([e['ref'] for e in json.loads(notice['evidence'])], [refs[0]])
        self.assertEqual(plan['school_selection_receipt']['purpose'], 'admin')
        # The child's own reading aloud that a parent signs after listening stays the same batch's homework.
        lesson = json.loads(homework['plan'])
        self.assertEqual((homework['state'], lesson['school_task']['purpose'], lesson['school_learning']['subject'],
                          tasks[homework['task_id']]['agenda']['category']), ('accepted', 'learning', '英语', 'homework'))
        self.assertEqual(originals, payload['messages'], 'the complete originals stay unchanged')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(facts(), first, 'reopen and the next round keep both tasks without duplicates')
        self.assertEqual(self.model.call_count, 1)

    def test_who_reads_decides_a_reading_purpose_while_the_child_reading_stays_learning(self):
        actions = lambda text:[a['purpose'] for a in agent._school_native_actions([dict(
            ref='message:s:1', text=text, kind='text', publisher='synthetic-teacher-1', time='2026-10-22T16:20:00+08:00')])]
        # A sole administrative outcome leaves the ledger to its existing guards; in a list it keeps its own purpose.
        self.assertEqual(actions(self.P104_TEXT), [])
        self.assertEqual(actions('请家长今天阅读孩子带回的《图书借阅约定》，在末页“监护人”栏签字；今晚朗读课文三遍，家长听完后签字。'),
                         ['admin', 'learning'])
        # The child reads, or the parent reads the child's own work: still learning.
        self.assertEqual(actions('今晚阅读课文第3段，请家长听完后签字。'), ['learning'])
        self.assertEqual(actions('请家长阅读孩子的作文并签字。'), ['learning'])
        value = dict(title='', goal='', advice='', state='ready', reason='', purpose='admin')
        for text, state in ((self.P104_TEXT, 'ready'), ('今晚阅读课文第3段，请家长听完后签字。', 'review'),
                            ('请家长阅读孩子的作文并签字。', 'review'), ('请家长今天阅读《图书借阅约定》后，孩子朗读课文三遍。', 'review')):
            with self.subTest(text=text):
                evidence = [dict(ref='message:s:1', text=text, kind='text', unread=False)]
                brief = agent._school_brief(dict(value, title='家长阅读并签字', goal=text), evidence=evidence, separate_learning=True)
                self.assertEqual((brief['state'], brief['goal']), (state, text))

    def _parent_signed_notice(self, message_id, time, sender_id, text, title, due):
        """Root's fictional admin notice with an own correct fixed 15-field admin reply, beside the English read-aloud."""
        self.fixture.now = self.now = dt.datetime(2026, 10, 26, 16, 30, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='105')
        payload['messages'] = [
            dict(id=message_id, message_order=message_id, time=time, kind='text', sender='虚构班主任', sender_id=sender_id, text=text, unread=False),
            dict(id='105', message_order='105', time='2026-10-26T16:25:00+08:00', kind='text', sender='虚构英语老师',
                 sender_id='synthetic-english-teacher', text=self.READ_ALOUD_TEXT, unread=False)]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        notice = dict(title_quote=text.rstrip('。'), focus='school', due=due, evidence=[dict(ref=refs[0])], learning_subject='',
                      learning_goal_id='', task_title=title, task_goal=text, task_advice='', task_change='new', task_target_id='',
                      task_state='ready', task_reason='纯虚构程序验证固定回复，不是实际模型产物。', task_purpose='admin', task_submission='')
        reading = fixtures.school_proposal(
            title_quote='今晚朗读课本第20页三遍，请家长听完后在这一页签字', due='2026-10-26', evidence=[dict(ref=refs[1])],
            learning_subject='英语', task_title='英语：朗读课本第20页三遍', task_goal='今晚朗读课本第20页三遍，请家长听完后在这一页签字。',
            task_state='ready', task_reason='虚构回执。', task_purpose='learning')
        self._use_replies(payload, [dict(proposals=[notice, reading])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 2), 'the faithful admin reply finishes the batch')

        def facts():
            with self.store._db() as c:
                rows = {json.loads(r['evidence'])[0]['ref']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
                manual = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
                originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            with self.app.connect() as c:
                tasks = {t['id']: t for t in self.app.tasks(c) if t['id'] in {m['id'] for m in manual}}
            return rows, manual, tasks, originals

        rows, manual, tasks, originals = first = facts()
        self.assertEqual((sorted(rows), len(manual), len(tasks)), (sorted(refs), 2, 2))
        row = rows[refs[0]];plan = json.loads(row['plan']);task = tasks[row['task_id']]
        self.assertEqual((row['state'], row['due'], plan['school_task']['state'], plan['school_task']['purpose'], plan.get('school_learning')),
                         ('accepted', due, 'ready', 'admin', None))
        self.assertEqual((task['agenda']['category'], task['title']), ('todo', title))
        self.assertIn(text.rstrip('。'), task['action'], 'the whole original, its executor, carrier, field and days stay in the action')
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], [refs[0]])
        homework = rows[refs[1]];lesson = json.loads(homework['plan'])
        self.assertEqual((homework['state'], lesson['school_task']['purpose'], lesson['school_learning']['subject'],
                          tasks[homework['task_id']]['agenda']['category']), ('accepted', 'learning', '英语', 'homework'))
        self.assertEqual(originals, payload['messages'], 'the complete originals stay unchanged')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(facts(), first, 'reopen and the next round keep both tasks without duplicates')
        self.assertEqual(self.model.call_count, 1)
        return task

    def test_a_child_handing_back_the_signed_slip_by_a_ba_phrase_keeps_the_parent_reading_administrative(self):
        # Root's A01: the parent reads tonight and signs the slip's guardian field; the child only hands that slip back tomorrow morning.
        text = '请家长今晚阅读学校发回的《校车乘坐须知》，在随附回条的“监护人确认”栏签字，孩子明早将回条交给班主任。'
        task = self._parent_signed_notice('201', '2026-10-26T16:10:00+08:00', 'qa-teacher-head-a01', text, '《校车乘坐须知》家长阅读并签字', '2026-10-27')
        self.assertEqual((task['agenda']['complete_on'], task['agenda']['due_on'], task['agenda']['due_kind']), ('2026-10-26', '2026-10-27', 'handback'))
        # The child's own different outcome handed in by the same phrase is no carried slip: it stays the child's.
        actions = lambda value:[a['purpose'] for a in agent._school_native_actions([dict(
            ref='message:s:1', text=value, kind='text', publisher='synthetic-teacher-1', time='2026-10-26T16:10:00+08:00')])]
        self.assertEqual(actions(text), [])
        self.assertEqual(actions('请家长今晚阅读学校发回的《校车乘坐须知》，在随附回条的“监护人确认”栏签字，孩子明早将作文交给班主任。'), ['learning'])

    def test_a_guardian_reading_signed_today_lists_today_and_keeps_the_parent_handback_day(self):
        # Root's A02: the guardian reads and signs 已阅 today (26th); the parent hands the receipt to the gate office tomorrow (27th).
        text = '请监护人今天阅读纸质《学生接送安排告知书》，在签收联写明“已阅”并签字。请家长明天把签收联交到校门口值班室。'
        task = self._parent_signed_notice('202', '2026-10-26T16:20:00+08:00', 'qa-teacher-head-a02', text, '《学生接送安排告知书》监护人阅读签字并交回', '2026-10-27')
        self.assertEqual((task['agenda']['complete_on'], task['agenda']['due_on'], task['agenda']['due_kind']), ('2026-10-26', '2026-10-27', 'handback'))

    # Known fictional TB02: the actual parsed Flash reply (configured effort none) on 632a778 was admin/ready/due 10-22 with
    # no subject, and so was a synthetic correct reply; only the program's guard read 听写/背诵/订正 inside the closed name
    # of the form the original itself has filled in. Both are fixed here as program controls.
    TB02_TEXT = '2026年10月22日前，在《听写背诵订正材料领取登记单》上填写学生姓名和领取份数，家长签字后交回班主任。只办理本次领取登记。'
    TB02_ACTUAL_RAW = dict(title_quote='2026年10月22日前，在《听写背诵订正材料领取登记单》上填写学生姓名和领取份数，家长签字后交回班主任。',
                           focus='school', due='2026-10-22', evidence=[0], task_title='填写领取登记单并交回班主任',
                           task_goal='在《听写背诵订正材料领取登记单》上填写学生姓名和领取份数；家长签字后交回班主任；2026年10月22日前完成；只办理本次领取登记。',
                           task_advice='可先确认领取份数再填写，避免涂改；签字后按班主任要求交回。', learning_subject='', learning_goal_id='',
                           task_change='new', task_target_id='', task_state='ready',
                           task_reason='已读文字明确要求填写登记单、家长签字并交回班主任，属全班或本孩子需办理的行政事务，截止日期明确。',
                           task_purpose='admin', task_submission='家长签字后交回班主任')
    TB02_SYNTHETIC_RAW = dict(title_quote=TB02_TEXT, focus='school', due='2026-10-22', evidence=[0], learning_subject='', learning_goal_id='',
                              task_title='填写《听写背诵订正材料领取登记单》并交回', task_goal=TB02_TEXT, task_advice='', task_state='ready',
                              task_reason='本项行动和完成标准明确，按冻结虚构标准分类。', task_change='new', task_target_id='',
                              task_purpose='admin', task_submission='')

    def _registration_through_save_auto_intake_and_fresh_store_reopen(self, text, raw, due, standards):
        self.fixture.now = self.now = dt.datetime(2026, 10, 16, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time='2026-10-16T18:00:00+08:00', kind='text', sender='示例班主任',
                                    sender_id='p1-title-boundary-tb02-school', text=text, unread=False)]
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':11'
        self._use_replies(payload, [dict(proposals=[dict(copy.deepcopy(raw), evidence=[dict(ref=ref)])])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        from family_goals import Store as Goals
        import family_review

        def facts(app, store):
            with store._db() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
                originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            with app.connect() as c:
                tasks = {t['id']: t for t in app.tasks(c)}
            return rows, tasks, originals, Goals(app, store).school_candidates(self.source['child_id'])

        def check(rows, tasks, originals, goals):
            row, = rows
            plan = json.loads(row['plan']);brief = plan['school_task'];task = tasks[row['task_id']]
            self.assertEqual((row['state'], row['due'], brief['state'], brief['purpose'], plan.get('school_learning'), plan.get('school_goal_id', '')),
                             ('accepted', due, 'ready', 'admin', None, ''), 'a pure registration stays a pending administrative to-do')
            self.assertEqual((task['agenda']['category'], task['agenda']['due_on']), ('todo', due))
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], [ref])
            self.assertEqual([text in e['text'] for e in json.loads(row['evidence'])], [True], 'the quoted original is kept whole')
            for standard in standards:
                self.assertIn(standard, task['action'])
            self.assertEqual(plan['school_selection_receipt']['purpose'], 'admin')
            self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no attachment was read or prepared')
            self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')
            self.assertEqual(goals, [], 'no school learning goal')

        first = facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app))
        check(*fresh)
        self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first[0]], 'reopen keeps the one item without duplicates')
        self.assertEqual(sorted(fresh[1]), sorted(first[1]))
        self.assertEqual(self.model.call_count, 1)

    def test_known_tb02_actual_reply_filled_form_name_is_not_learning_through_save_and_fresh_store_reopen(self):
        self._registration_through_save_auto_intake_and_fresh_store_reopen(
            self.TB02_TEXT, self.TB02_ACTUAL_RAW, '2026-10-22',
            ('《听写背诵订正材料领取登记单》', '学生姓名', '领取份数', '家长签字', '交回班主任', '只办理本次领取登记'))

    def test_known_tb02_synthetic_reply_filled_form_name_is_not_learning_through_save_and_fresh_store_reopen(self):
        self._registration_through_save_auto_intake_and_fresh_store_reopen(
            self.TB02_TEXT, self.TB02_SYNTHETIC_RAW, '2026-10-22',
            ('《听写背诵订正材料领取登记单》', '学生姓名', '领取份数', '家长签字', '交回班主任', '只办理本次领取登记'))

    def test_filled_form_name_needs_the_originals_own_fill_clause_while_outside_learning_and_other_names_stay_guarded(self):
        value = dict(title='', goal='', advice='', state='ready', reason='', purpose='admin')
        name = '《听写背诵订正材料领取登记单》'
        ready = (self.TB02_TEXT, self.K03_TEXT, '请于2026年10月23日前在《朗读练习安排领取单》中登记孩子姓名、班级，交回班主任。')
        review = (self.TB02_TEXT + '另请朗读课文第3段。', self.TB02_TEXT + '写一篇读后感。',
                  self.TB02_TEXT.replace('只办理本次领取登记。', '完成第1-3题后再签字。'),
                  '在《口算练习》上填写答案，交回班主任。', '在《阅读记录卡》上填写学生姓名和阅读页数，交回班主任。',
                  '在' + name + '上填写学生姓名和订正内容，交回班主任。', '不用在' + name + '上填写学生姓名，交回班主任。',
                  '请完成' + name + '，家长签字后交回班主任。', '在' + name.replace('》', '') + '上填写学生姓名，交回班主任。',
                  '《在《听写练习》上填写姓名的说明》请阅读。', '在《听写，背诵订正材料领取登记单》上填写学生姓名，交回班主任。')
        for text, state in [(t, 'ready') for t in ready] + [(t, 'review') for t in review]:
            for separate in (False, True):
                with self.subTest(text=text, separate=separate):
                    evidence = [dict(ref='message:synthetic-filled-form:1', text=text, kind='text', unread=False)]
                    brief = agent._school_brief(dict(value, title='登记事务', goal=text), evidence=evidence, separate_learning=separate)
                    self.assertEqual((brief['state'], brief['purpose'], brief['goal']), (state, 'admin', text))
                    self.assertEqual(evidence[0]['text'], text)
                    if state == 'review':self.assertIn('同时提到学习活动', brief['reason'])
        # A reply's own closed name around the original's learning cannot borrow the original's fill clause.
        evidence = [dict(ref='message:synthetic-filled-form:2', text='请听写课文生字，在登记单上填写学生姓名后交回。', kind='text', unread=False)]
        brief = agent._school_brief(dict(value, title='《听写课文生字登记单》', goal='在《听写课文生字登记单》上填写学生姓名后交回。'),
                                    evidence=evidence, separate_learning=True)
        self.assertEqual(brief['state'], 'review')

    # Known fictional K12: the actual parsed Flash reply (configured effort none) on c131 was reference/optional with no title,
    # goal or due; only the native ledger read 阅读 in the material's name as a required reading and refused it. The request now
    # carries no required native action for this message, so this exact old reply is a fixed program control, not prompt accuracy.
    K12_TEXT = '阅读活动参考资料仅供了解，自愿查看。下一次全班具体任务及日期将另行通知。'
    K12_RAW = dict(title_quote='阅读活动参考资料仅供了解，自愿查看。', focus='school', due='', evidence=[0], task_title='', task_goal='',
                   task_advice='', learning_subject='', learning_goal_id='', task_change='new', task_target_id='', task_state='reference',
                   task_reason='该消息说明阅读活动参考资料仅供了解、自愿查看，且下一次全班具体任务及日期将另行通知，本身没有新增行动要求，不生成待办任务。',
                   task_purpose='optional', task_submission='')

    def _k12_facts(self, app, store):
        from family_goals import Store as Goals
        with store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            manual = c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]
        with app.connect() as c:
            tasks = {t['id']: t for t in app.tasks(c)}
        return rows, tasks, originals, manual, Goals(app, store).school_candidates(self.source['child_id'])

    def test_known_k12_voluntary_reference_saves_one_reference_through_auto_intake_and_fresh_store_reopen(self):
        self.fixture.now = self.now = dt.datetime(2026, 10, 16, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time='2026-10-16T18:03:00+08:00', kind='text', sender='示例学校发布人',
                                    sender_id='p1-classification-k12-school', text=self.K12_TEXT, unread=False)]
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':11'
        self._use_replies(payload, [dict(proposals=[dict(copy.deepcopy(self.K12_RAW), evidence=[dict(ref=ref)])])])
        requests = []
        saved_reply = self.model.side_effect
        self.model.side_effect = lambda messages, *args, **kwargs: (requests.append(json.loads(messages[-1]['content'])), saved_reply(messages, *args, **kwargs))[1]
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertNotIn('required_native_actions', requests[0], 'material only for information is no required native action')
        import family_review

        def check(rows, tasks, originals, manual, goals):
            row, = rows
            plan = json.loads(row['plan']);brief = plan['school_task']
            self.assertEqual((brief['state'], brief['purpose'], row['due'], row['task_id'] or '', plan.get('school_learning'), plan.get('school_goal_id', '')),
                             ('reference', 'optional', '', '', None, ''), 'one reference: no to-do, date, learning link or goal')
            self.assertFalse({'school_native_action', 'school_original_action', 'school_native_cover'} & set(plan))
            self.assertEqual((brief['title'], brief['goal']), ('', ''))
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], [ref])
            self.assertEqual([self.K12_TEXT in e['text'] for e in json.loads(row['evidence'])], [True], 'the complete original is kept')
            self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no attachment was read or prepared')
            self.assertEqual((tasks, manual), ({}, 0), 'nothing to do was created')
            self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')
            self.assertEqual(goals, [], 'no school learning goal')

        first = self._k12_facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = self._k12_facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app))
        check(*fresh)
        self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first[0]], 'reopen keeps the one item without duplicates')
        self.assertEqual(self.model.call_count, 1)

    # Known fictional N06 (disclosed by Root): one school image whose content was never read; no bytes exist. Both receipts are
    # authored fictional controls, not provider output: the wrong one claims reference/optional, the correct one review/unknown.
    N06_TEXT = '[图片消息，内容尚未读取]'
    N06_CORRECT = dict(title_quote=N06_TEXT, focus='school', due='', evidence=[0], task_title='', task_goal='', task_advice='',
                       learning_subject='', learning_goal_id='', task_change='new', task_target_id='', task_state='review',
                       task_reason='仅有未读图片占位；尚不知其中是作业、通知或参考，原件仍待读取。', task_purpose='unknown', task_submission='')
    N06_WRONG = dict(N06_CORRECT, task_state='reference', task_reason='故意错误的合成回执：没有读取图片却宣称只是参考。', task_purpose='optional')

    def test_known_n06_unread_image_keeps_an_unknown_purpose_whatever_use_the_receipt_claims_on_full_evidence(self):
        ref = 'message:fictional-native-reference-n06:1'
        evidence = [dict(ref=ref, text=self.N06_TEXT, sender='虚构学校发布人', publisher='publisher:fictional-native-reference:n06',
                         time='2026-11-05T18:00:00+08:00', kind='image', content_incomplete=True, unread=True,
                         attachments=[dict(name='虚构学校资料.png', type='image/png')], source='fictional-school-image', related_messages=[])]
        claims = {'wrong reference': self.N06_WRONG, 'correct unknown': self.N06_CORRECT,
                  'guessed learning': dict(self.N06_WRONG, task_state='review', task_purpose='learning')}
        for label, raw in claims.items():
            with self.subTest(claim=label):
                self.model.side_effect = lambda *args, raw=raw, **kwargs: dict(proposals=[dict(copy.deepcopy(raw), evidence=[dict(ref=ref)])])
                item, = agent._select('school', copy.deepcopy(evidence), school_goals=[], as_of='2026-11-05')
                brief, receipt = item['plan']['school_task'], item['plan']['school_selection_receipt']
                self.assertEqual((brief['state'], brief['purpose'], item['due']), ('review', 'unknown', ''))
                self.assertEqual((brief['title'], brief['goal'], brief['advice']), ('', '', ''), 'nothing is guessed from a name or placeholder')
                self.assertEqual((receipt['state'], receipt['purpose']), (raw['task_state'], raw['task_purpose']), 'the raw receipt stays for audit')
                self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no attachment was read or prepared')

    def _n06_run_once(self, raw):
        self.fixture.now = self.now = dt.datetime(2026, 11, 5, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time='2026-11-05T18:00:00+08:00', kind='image', sender='虚构学校发布人',
                                    sender_id='fictional-native-reference-n06', text=self.N06_TEXT, unread=True)]
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':11'
        requests = []

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual((name, data_path), ('family_agent_selection', self.app.DATA), 'only the synthetic school selection')
            requests.append(json.loads(messages[-1]['content']))
            return dict(proposals=[dict(copy.deepcopy(raw), evidence=[dict(ref=ref)])])
        self.model.side_effect = reply
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual([(e['ref'], e['kind'], bool(e['content_incomplete'])) for e in requests[0]['evidence']], [(ref, 'image', True)])
        import family_review

        def check(rows, tasks, originals, manual, goals):
            row, = rows
            plan = json.loads(row['plan']);brief = plan['school_task'];receipt = plan['school_selection_receipt']
            self.assertEqual((brief['state'], brief['purpose'], row['due'], row['task_id'] or '', plan.get('school_learning'), plan.get('school_goal_id', '')),
                             ('review', 'unknown', '', '', None, ''), 'an unread original stays an unknown review, never a reference or a to-do')
            self.assertEqual((brief['title'], brief['goal'], brief['advice']), ('', '', ''))
            self.assertEqual((receipt['state'], receipt['purpose']), (raw['task_state'], raw['task_purpose']), 'the raw receipt is kept for audit only')
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], [ref])
            self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no attachment was read or prepared')
            self.assertEqual((tasks, manual), ({}, 0), 'no to-do is created from an unread image')
            self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')
            self.assertEqual(goals, [], 'no guessed learning goal')

        first = self._k12_facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = self._k12_facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app))
        check(*fresh)
        self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first[0]], 'reopen keeps the one item without duplicates')
        self.assertEqual(self.model.call_count, 1)

    def test_known_n06_wrong_reference_on_an_unread_image_saves_an_unknown_review_through_intake_and_fresh_store_reopen(self):
        self._n06_run_once(self.N06_WRONG)

    def test_known_n06_correct_unknown_receipt_saves_the_same_unknown_review_through_intake_and_fresh_store_reopen(self):
        self._n06_run_once(self.N06_CORRECT)

    def test_explicit_read_action_with_a_supplemental_unread_attachment_keeps_its_own_purpose_and_requirement(self):
        # Same full-evidence path as N06: fully read explicit text establishes the action; only its unread supplement waits.
        text = dict(ref='message:fictional-native-reference-n06:2', text='语文：请完成练习册第5页。', kind='text',
                    time='2026-11-05T18:00:00+08:00')
        supplement = dict(ref='message:fictional-native-reference-n06:3', text='练习册第5页附图尚未读取。', kind='text', content_incomplete=True,
                          time='2026-11-05T18:01:00+08:00', attachments=[dict(name='虚构学校资料.png', mime='image/png')])
        proposal = fixtures.school_proposal(
            title_quote='请完成练习册第5页', evidence=[dict(ref=text['ref']), dict(ref=supplement['ref'])], learning_subject='语文',
            task_title='语文：完成练习册第5页', task_goal='完成练习册第5页。', task_state='ready', task_reason='虚构回执。', task_purpose='learning')
        self.model.side_effect = lambda *args, **kwargs: dict(proposals=[copy.deepcopy(proposal)])
        item, = agent._select('school', [text, supplement], school_goals=[], as_of='2026-11-05')
        brief = item['plan']['school_task']
        self.assertEqual((brief['state'], brief['purpose']), ('review', 'learning'), 'explicit read text keeps its own use; only the supplement waits')
        self.assertIn('练习册第5页', brief['title'])
        self.assertIn('完成练习册第5页', brief['goal'])
        self.assertIn('已读正文要求已保留', brief['reason'])
        self.assertEqual([e['ref'] for e in item['evidence']], [text['ref'], supplement['ref']])

    def test_reference_scope_is_its_own_clause_and_never_hides_or_creates_a_required_outcome(self):
        def actions(text):
            entry = dict(ref='message:synthetic-reference:1', text=text, kind='text', publisher='p', time='2026-10-16T18:03:00+08:00')
            return [(a['quote'], a['purpose']) for a in agent._school_native_actions([entry])]
        self.assertEqual(actions(self.K12_TEXT), [], 'a later "另行通知" does not make the material a required activity')
        first = self.K12_TEXT.split('。')[0] + '。'
        cases = {
            first + '请阅读课文第3页。': [('请阅读课文第3页', 'learning')],
            '请完成练习册第5页。' + self.K12_TEXT: [('请完成练习册第5页', 'learning')],
            first[:-1] + '，请完成第3题。': [('请完成第3题', 'learning')],
            '1. 朗读课文三遍。2. 阅读拓展资料仅供了解，自愿查看。3. 背诵第一段。': [('朗读课文三遍', 'learning'), ('背诵第一段', 'learning')],
            # The voluntary use binds only material its own clause limits; an addressed or further requirement stays required.
            '阅读第10页，自愿查看拓展资料。': [('阅读第10页，自愿查看拓展资料', 'learning')],
            '阅读活动参考资料仅供了解，周五前交读后感。': [('阅读活动参考资料仅供了解，周五前交读后感', 'learning')],
            '阅读活动参考资料仅供了解，自愿读3篇。': [('阅读活动参考资料仅供了解，自愿读3篇', 'learning')],
            '请阅读资料仅供了解。': [('请阅读资料仅供了解', 'learning')],
            '朗读课文供家长检查。': [('朗读课文供家长检查', 'learning')],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):self.assertEqual(actions(text), expected)

    # Root's postcandidate exploratory N07/N08 (fictional; authored replies, not provider output): the same voluntary material whose
    # own name carries an edition number or a closed book title. The name stays a name; pages, counts and dates outside it stay required.
    N07_TEXT = '阅读活动第3期参考资料仅供了解，自愿查看。下一次全班具体任务及日期将另行通知。'
    N08_TEXT = '阅读《四季花园》活动参考资料仅供了解，自愿查看。下一次全班具体任务及日期将另行通知。'

    def _material_name_run_once(self, text):
        self.fixture.now = self.now = dt.datetime(2026, 11, 5, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time='2026-11-05T18:00:00+08:00', kind='text', sender='虚构学校发布人',
                                    sender_id='fictional-material-name', text=text, unread=False)]
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':11'
        raw = dict(copy.deepcopy(self.K12_RAW), title_quote=text.split('。')[0] + '。', evidence=[dict(ref=ref)],
                   task_reason='该条明确只供自愿查看，具体任务及日期另行通知；名称和期号不是行动要求。')
        self._use_replies(payload, [dict(proposals=[raw])])
        requests = []
        saved_reply = self.model.side_effect
        self.model.side_effect = lambda messages, *args, **kwargs: (requests.append(json.loads(messages[-1]['content'])), saved_reply(messages, *args, **kwargs))[1]
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertNotIn('required_native_actions', requests[0], 'a name inside material only for information is no required native action')
        import family_review

        def check(rows, tasks, originals, manual, goals):
            row, = rows
            plan = json.loads(row['plan']);brief = plan['school_task']
            self.assertEqual((brief['state'], brief['purpose'], row['due'], row['task_id'] or '', plan.get('school_learning'), plan.get('school_goal_id', '')),
                             ('reference', 'optional', '', '', None, ''), 'one reference: no to-do, date, learning link or goal')
            self.assertFalse({'school_native_action', 'school_original_action', 'school_native_cover'} & set(plan))
            self.assertEqual((brief['title'], brief['goal']), ('', ''))
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], [ref])
            self.assertEqual([text in e['text'] for e in json.loads(row['evidence'])], [True], 'the complete original keeps its name')
            self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no attachment was read or prepared')
            self.assertEqual((tasks, manual), ({}, 0), 'nothing to do was created')
            self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')
            self.assertEqual(goals, [], 'no school learning goal')

        first = self._k12_facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = self._k12_facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app))
        check(*fresh)
        self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first[0]], 'reopen keeps the one item without duplicates')
        self.assertEqual(self.model.call_count, 1)

    def test_n07_edition_number_in_a_voluntary_material_name_saves_one_reference_through_auto_intake_and_fresh_store_reopen(self):
        self._material_name_run_once(self.N07_TEXT)

    def test_n08_closed_book_title_in_a_voluntary_material_name_saves_one_reference_through_auto_intake_and_fresh_store_reopen(self):
        self._material_name_run_once(self.N08_TEXT)

    def test_material_name_is_a_name_only_inside_its_own_reference_clause(self):
        def actions(text):
            entry = dict(ref='message:synthetic-material-name:1', text=text, kind='text', publisher='p', time='2026-11-05T18:00:00+08:00')
            return [(a['quote'], a['purpose']) for a in agent._school_native_actions([entry])]
        for text in (self.N07_TEXT, self.N08_TEXT, '阅读《四季花园》第2版参考资料仅供了解，自愿查看。'):
            with self.subTest(text=text):self.assertEqual(actions(text), [])
        cases = {
            # A page or piece is no edition, and a title does not cover a count, date or obligation outside it.
            '阅读活动第3页参考资料仅供了解，自愿查看。': [('阅读活动第3页参考资料仅供了解，自愿查看', 'learning')],
            '阅读《四季花园》第3页，参考资料仅供了解，自愿查看。': [('阅读《四季花园》第3页，参考资料仅供了解，自愿查看', 'learning')],
            '阅读《四季花园》活动参考资料仅供了解，自愿读3篇。': [('阅读《四季花园》活动参考资料仅供了解，自愿读3篇', 'learning')],
            '阅读活动第3期参考资料仅供了解，周五前交读后感。': [('阅读活动第3期参考资料仅供了解，周五前交读后感', 'learning')],
            '请阅读《四季花园》参考资料仅供了解。': [('请阅读《四季花园》参考资料仅供了解', 'learning')],
            # A sibling requirement before or after the reference keeps its own action, page and date.
            self.N08_TEXT.split('。')[0] + '。请阅读《四季花园》第3页，11月7日前交读后感。': [('请阅读《四季花园》第3页，11月7日前交读后感', 'learning')],
            '请完成练习册第5页。' + self.N07_TEXT: [('请完成练习册第5页', 'learning')],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):self.assertEqual(actions(text), expected)

    def test_wrong_reference_over_a_real_page_date_or_count_beside_a_material_name_still_rejects_the_whole_batch(self):
        texts = (self.N08_TEXT.split('。')[0] + '。请阅读《四季花园》第3页，11月7日前交读后感。',
                 '阅读《四季花园》第3页，参考资料仅供了解，自愿查看。',
                 '阅读活动第3期参考资料仅供了解，自愿读3篇。')
        for text in texts:
            with self.subTest(text=text):
                t = type(self)(methodName='runTest');t.setUp()
                try:
                    t.fixture.now = t.now = dt.datetime(2026, 11, 5, 20, tzinfo=agent.TZ)
                    payload, refs = t._ingest([text], ['fictional-material-name'])
                    raw = dict(copy.deepcopy(self.K12_RAW), title_quote=text, evidence=[dict(ref=refs[0])], task_reason='故意错误的合成回执。')
                    t._use_replies(payload, [dict(proposals=[raw])])
                    t._assert_rejected_batch(payload, agent.run_once(t.app, t.now))
                finally:t.doCleanups()

    # Root's postcandidate independent C (fictional; authored replies, not provider output): the requirement's own date opens with
    # the time preposition 于 after 请. It is one required reading with its written outcome, never a voluntary reference.
    C_TEXT = '语文：请于11月6日前阅读第3期参考资料，并写一句理由。'
    C_QUOTE = '请于11月6日前阅读第3期参考资料，并写一句理由'
    C_RAW = dict(title_quote=C_QUOTE, focus='school', due='2026-11-06', evidence=[0], task_title='语文：阅读第3期参考资料并写一句理由',
                 task_goal='阅读第3期参考资料，并写一句理由。11月6日前完成。', task_advice='', learning_subject='语文', learning_goal_id='',
                 task_change='new', task_target_id='', task_state='ready', task_reason='原文有明确阅读成果及自身日期，按该项要求保留。',
                 task_purpose='learning', task_submission='')
    C_WRONG_RAW = dict(C_RAW, due='', task_title='', task_goal='', learning_subject='', task_state='reference', task_purpose='optional',
                       task_reason='故意错误的私有合成控制：把原文明示阅读与写出成果错归自愿参考；不是实际模型返回。')

    def _c_ingest(self, text=C_TEXT):
        self.fixture.now = self.now = dt.datetime(2026, 11, 5, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time='2026-11-05T18:00:00+08:00', kind='text', sender='虚构学校发布人',
                                    sender_id='fictional-native-name-c', text=text, unread=False)]
        self.store.ingest(payload)
        return payload, 'message:' + self.source['id'] + ':11'

    def _c_facts(self, app, store):
        rows, tasks, originals, manual, goals = self._k12_facts(app, store)
        return ([(r['id'], r['state'], r['due'], r['task_id'], json.loads(r['plan'])) for r in rows], tasks, originals, manual,
                [(g['subject'], g['id']) for g in goals])

    def test_c_dated_required_reading_with_its_outcome_saves_one_learning_task_through_auto_intake_and_fresh_store_reopen(self):
        payload, ref = self._c_ingest()
        self._use_replies(payload, [dict(proposals=[dict(copy.deepcopy(self.C_RAW), evidence=[dict(ref=ref)])])])
        requests = []
        saved_reply = self.model.side_effect
        self.model.side_effect = lambda messages, *args, **kwargs: (requests.append(json.loads(messages[-1]['content'])), saved_reply(messages, *args, **kwargs))[1]
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual([(a['quote'], a['purpose'], a['subject']) for a in requests[0]['required_native_actions']],
                         [(self.C_QUOTE, 'learning', '语文')], 'the dated reading is one required native action')
        import family_review

        def check(rows, tasks, originals, manual, goals):
            (_, state, due, task_id, plan), = rows
            brief = plan['school_task']
            self.assertEqual((state, due, brief['state'], brief['purpose'], plan.get('school_learning')),
                             ('accepted', '2026-11-06', 'ready', 'learning', dict(subject='语文', goal_id='')))
            self.assertEqual(plan['school_native_action']['quote'], self.C_QUOTE)
            task, = tasks.values()
            self.assertEqual((task['id'], task['agenda']['category'], task['agenda']['due_on']), (task_id, 'homework', '2026-11-06'))
            for standard in ('阅读第3期参考资料', '写一句理由', '11月6日前'):self.assertIn(standard, task['action'])
            self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no material was read or prepared')
            self.assertEqual(manual, 1, 'the one to-do is its one stored task, no other')
            self.assertEqual(originals, payload['messages'], 'the complete original and its time stay unchanged')
            self.assertEqual(goals, [('语文', plan['school_goal_id'])], 'the one reading routes to one Chinese learning goal')

        first = self._c_facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = self._c_facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app));check(*fresh)
        self.assertEqual([r[0] for r in fresh[0]], [r[0] for r in first[0]], 'reopen keeps the one item without duplicates')
        self.assertEqual(self.model.call_count, 1)

    def test_c_wrong_reference_over_a_dated_required_reading_rejects_the_batch_and_the_kept_original_retries(self):
        payload, ref = self._c_ingest()
        wrong = dict(copy.deepcopy(self.C_WRONG_RAW), evidence=[dict(ref=ref)])
        self._use_replies(payload, [dict(proposals=[wrong]), dict(proposals=[dict(copy.deepcopy(self.C_RAW), evidence=[dict(ref=ref)])])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))
        with self.store._db() as c:
            self.assertIn('整批保留重试', c.execute("SELECT error FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()[0])
        self.assertEqual(self._c_facts(self.app, self.store)[4], [], 'the rejected batch routes no learning goal')
        # The kept original retries under the same guard; only the complete required reading finishes it.
        retry = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((retry['failed'], retry['processed']), (0, 1))
        rows, tasks, originals, manual, goals = self._c_facts(self.app, self.store)
        self.assertEqual([(r[2], r[4]['school_task']['state'], r[4]['school_task']['purpose']) for r in rows], [('2026-11-06', 'ready', 'learning')])
        self.assertEqual((len(tasks), originals), (1, payload['messages']))
        self.assertEqual(self.model.call_count, 2)

    def test_c_tampered_selection_without_the_ledger_is_refused_by_the_save_guard(self):
        payload, ref = self._c_ingest()
        self._use_replies(payload, [dict(proposals=[dict(copy.deepcopy(self.C_WRONG_RAW), evidence=[dict(ref=ref)])])])
        real_select = agent._select

        def tampered(*args, **kwargs):
            # A selection that skipped the literal ledger still meets the original guard inside the write transaction.
            with patch.object(agent, '_school_native_actions', return_value=[]):
                return real_select(*args, **kwargs)
        with patch.object(agent, '_select', side_effect=tampered):
            self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))
        with self.store._db() as c:
            self.assertIn('整批未写入', c.execute("SELECT error FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()[0])

    def test_own_date_preposition_opens_an_outcome_only_when_an_outcome_follows_it(self):
        def actions(text):
            entry = dict(ref='message:synthetic-required-prefix:1', text=text, kind='text', publisher='p', time='2026-11-05T18:00:00+08:00')
            return [(a['quote'], a['purpose'], a['subject']) for a in agent._school_native_actions([entry])]
        cases = {
            self.C_TEXT: [(self.C_QUOTE, 'learning', '语文')],
            '数学：请在周五前复习第2单元，并写出三个问题。': [('请在周五前复习第2单元，并写出三个问题', 'learning', '数学')],
            '英语：请同学们于明天前背诵Unit 3对话，并录一段音频。': [('请同学们于明天前背诵Unit 3对话，并录一段音频', 'learning', '英语')],
            '于2026年11月6日前朗读课文两遍。': [('于2026年11月6日前朗读课文两遍', 'learning', '')],
            # A negation stays inside its own outcome's quote.
            '请于11月6日前阅读第3期参考资料，不用写理由。': [('请于11月6日前阅读第3期参考资料，不用写理由', 'learning', '')],
            # A dated reading beside a voluntary reference keeps its own clause; the reference adds nothing.
            self.N07_TEXT.split('。')[0] + '。请于11月7日前阅读第4期参考资料，写一句理由。': [('请于11月7日前阅读第4期参考资料，写一句理由', 'learning', '')],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):self.assertEqual(actions(text), expected)
        # A publication or event date, a date and verb inside a closed title, a cancellation or a voluntary reference is no outcome.
        for text in ('第3期参考资料于11月6日发布，仅供了解。', '请于11月6日到校参加读书会。', '于11月6日举行阅读分享会，自愿参加。',
                     '《11月6日前阅读》参考资料仅供了解，自愿查看。', '取消：请于11月6日前阅读第3期参考资料。',
                     self.K12_TEXT, self.N07_TEXT, self.A2_TEXT, self.A3_TEXT):
            with self.subTest(text=text):self.assertEqual(actions(text), [])
        # A dated administrative form alone keeps its own guards, outside this ledger.
        self.assertEqual(actions(self.K03_TEXT), [])
        due, = agent._school_native_dates(agent._school_native_actions([dict(ref='message:synthetic-required-prefix:1', text=self.C_TEXT,
            kind='text', publisher='p', time='2026-11-05T18:00:00+08:00')])[0])
        self.assertEqual(due, '2026-11-06')

    def test_wrong_reference_over_other_dated_required_readings_still_rejects_the_whole_batch(self):
        texts = ('数学：请在周五前复习第2单元，并写出三个问题。', '英语：请同学们于明天前背诵Unit 3对话，并录一段音频。',
                 self.N07_TEXT.split('。')[0] + '。请于11月7日前阅读第4期参考资料，写一句理由。')
        for text in texts:
            with self.subTest(text=text):
                t = type(self)(methodName='runTest');t.setUp()
                try:
                    payload, ref = t._c_ingest(text)
                    raw = dict(copy.deepcopy(self.C_WRONG_RAW), title_quote=text, evidence=[dict(ref=ref)])
                    t._use_replies(payload, [dict(proposals=[raw])])
                    t._assert_rejected_batch(payload, agent.run_once(t.app, t.now))
                finally:t.doCleanups()

    # Root's postcandidate exploratory A2/A3 (fictional; authored replies, not provider output): the closed material title itself
    # carries a date or a comma. Its contents are the name; dates, counts and parts outside the title stay the clause's own.
    A2_TEXT = '阅读《11月6日札记》活动参考资料仅供了解，自愿查看。下一次全班具体任务及日期将另行通知。'
    A3_TEXT = '阅读《四季，花园》活动参考资料仅供了解，自愿查看。下一次全班具体任务及日期将另行通知。'

    def test_a2_date_inside_a_closed_material_title_saves_one_reference_through_auto_intake_and_fresh_store_reopen(self):
        self._material_name_run_once(self.A2_TEXT)

    def test_a3_comma_inside_a_closed_material_title_saves_one_reference_through_auto_intake_and_fresh_store_reopen(self):
        self._material_name_run_once(self.A3_TEXT)

    def test_closed_title_contents_are_a_name_only_inside_its_own_reference_clause(self):
        def actions(text):
            entry = dict(ref='message:synthetic-material-name:1', text=text, kind='text', publisher='p', time='2026-11-05T18:00:00+08:00')
            return [(a['quote'], a['purpose']) for a in agent._school_native_actions([entry])]
        for text in (self.A2_TEXT, self.A3_TEXT, '阅读《周五，11月6日》第2版参考资料仅供了解，自愿查看。'):
            with self.subTest(text=text):self.assertEqual(actions(text), [])
        cases = {
            # A date, page, count or obligation outside the closed title stays required.
            '阅读《11月6日札记》，11月7日前交读后感。': [('阅读《11月6日札记》，11月7日前交读后感', 'learning')],
            '阅读《11月6日札记》活动参考资料仅供了解，11月7日前交读后感。': [('阅读《11月6日札记》活动参考资料仅供了解，11月7日前交读后感', 'learning')],
            '阅读《四季，花园》第3页，写一句理由。': [('阅读《四季，花园》第3页，写一句理由', 'learning')],
            '阅读《四季，花园》活动参考资料仅供了解，自愿读3篇。': [('阅读《四季，花园》活动参考资料仅供了解，自愿读3篇', 'learning')],
            '请阅读《11月6日札记》参考资料仅供了解。': [('请阅读《11月6日札记》参考资料仅供了解', 'learning')],
            # A sibling requirement after the reference keeps its own action, page and date.
            self.A2_TEXT.split('。')[0] + '。请阅读《四季，花园》第3页，11月7日前交读后感。': [('请阅读《四季，花园》第3页，11月7日前交读后感', 'learning')],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):self.assertEqual(actions(text), expected)
        # An unclosed, nested or cross-clause title is no name: its clause stays a required outcome.
        for text in ('阅读《四季，花园活动参考资料仅供了解，自愿查看。', '阅读《四季《11月6日》花园》活动参考资料仅供了解，自愿查看。',
                     '阅读《四季。花园》活动参考资料仅供了解，自愿查看。'):
            with self.subTest(text=text):
                found = actions(text)
                self.assertTrue(found and all(purpose == 'learning' for _, purpose in found), found)

    def test_a2_a3_reference_beside_a_real_titled_reading_keeps_the_reading_required_through_replay_and_reopen(self):
        import family_review
        for first in (self.A2_TEXT, self.A3_TEXT):
            text = first.split('。')[0] + '。请阅读《四季，花园》第3页，写一句理由。'
            with self.subTest(text=text):
                t = type(self)(methodName='runTest');t.setUp()
                try:
                    t.fixture.now = t.now = dt.datetime(2026, 11, 5, 20, tzinfo=agent.TZ)
                    payload, refs = t._ingest([text], ['fictional-material-name'])
                    reference = dict(copy.deepcopy(self.K12_RAW), title_quote=text.split('。')[0] + '。', evidence=[dict(ref=refs[0])])
                    reading = fixtures.school_proposal(
                        title_quote='请阅读《四季，花园》第3页，写一句理由', evidence=[dict(ref=refs[0])], task_title='阅读《四季，花园》第3页并写理由',
                        task_goal='阅读《四季，花园》第3页，写一句理由。', task_state='ready', task_reason='虚构回执。', task_purpose='learning')
                    t._use_replies(payload, [dict(proposals=[reference, reading])])
                    result = agent.run_once(t.app, t.now)
                    self.assertEqual((result['failed'], result['processed']), (0, 1))

                    def check(rows, tasks, originals, manual, goals):
                        states = sorted((json.loads(r['plan'])['school_task']['state'], json.loads(r['plan'])['school_task']['purpose'], bool(r['task_id'])) for r in rows)
                        self.assertEqual(states, [('ready', 'learning', True), ('reference', 'optional', False)])
                        reading_task, = tasks.values()
                        self.assertIn('写一句理由', reading_task['action'], 'the real requirement keeps its complete standard')
                        self.assertNotIn('仅供了解', reading_task['action'], 'the reference is not merged into it')
                        self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')

                    first_facts = t._k12_facts(t.app, t.store);check(*first_facts)
                    replay = agent.run_once(t.app, t.now + dt.timedelta(minutes=7))
                    self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
                    app = family_review.load_app(t.fixture.root, t.fixture.data)
                    fresh = t._k12_facts(app, agent.Store(app.connect, app.profiles, t.fixture.data, app=app));check(*fresh)
                    self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first_facts[0]], 'reopen keeps the items without duplicates')
                finally:t.doCleanups()

    def test_wrong_reference_over_a_real_reading_beside_a_dated_or_comma_title_still_rejects_the_whole_batch(self):
        texts = (self.A2_TEXT.split('。')[0] + '。请阅读《四季，花园》第3页，11月7日前交读后感。',
                 '阅读《11月6日札记》，11月7日前交读后感。',
                 '阅读《四季，花园》活动参考资料仅供了解，自愿读3篇。')
        for text in texts:
            with self.subTest(text=text):
                t = type(self)(methodName='runTest');t.setUp()
                try:
                    t.fixture.now = t.now = dt.datetime(2026, 11, 5, 20, tzinfo=agent.TZ)
                    payload, refs = t._ingest([text], ['fictional-material-name'])
                    raw = dict(copy.deepcopy(self.K12_RAW), title_quote=text, evidence=[dict(ref=refs[0])], task_reason='故意错误的合成回执。')
                    t._use_replies(payload, [dict(proposals=[raw])])
                    t._assert_rejected_batch(payload, agent.run_once(t.app, t.now))
                finally:t.doCleanups()

    def _k12_mixed(self, reference_state):
        self.fixture.now = self.now = dt.datetime(2026, 10, 16, 20, tzinfo=agent.TZ)
        texts = [self.K12_TEXT.split('。')[0] + '。请阅读课文第3页，写一句理由。', '请家长在安全确认单上签字，2026年10月21日交回班主任。']
        payload, refs = self._ingest(texts, ['p1-classification-k12-school'] * 2)
        reference = dict(copy.deepcopy(self.K12_RAW), evidence=[dict(ref=refs[0])])
        reading = fixtures.school_proposal(
            title_quote='请阅读课文第3页，写一句理由', evidence=[dict(ref=refs[0])], task_title='阅读课文第3页并写理由',
            task_goal='阅读课文第3页，写一句理由。', task_state=reference_state, task_reason='虚构回执。',
            task_purpose='learning' if reference_state == 'ready' else 'optional')
        form = fixtures.school_proposal(
            title_quote=texts[1], due='2026-10-21', evidence=[dict(ref=refs[1])], task_title='安全确认单签字交回',
            task_goal=texts[1], task_state='ready', task_reason='虚构回执。', task_purpose='admin', task_submission='交回班主任')
        return payload, refs, [reference, reading, form]

    def test_reference_beside_a_real_reading_and_errand_keeps_both_required_while_a_mislabelled_reading_rejects_the_batch(self):
        payload, refs, replies = self._k12_mixed('ready')
        self._use_replies(payload, [dict(proposals=replies)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        rows, tasks, originals, manual, goals = self._k12_facts(self.app, self.store)
        states = sorted((json.loads(r['plan'])['school_task']['state'], json.loads(r['plan'])['school_task']['purpose'], bool(r['task_id'])) for r in rows)
        self.assertEqual(states, [('ready', 'admin', True), ('ready', 'learning', True), ('reference', 'optional', False)])
        reading = next(t for t in tasks.values() if '课文第3页' in t['action'])
        self.assertIn('写一句理由', reading['action'], 'the real requirement keeps its complete standard')
        self.assertNotIn('仅供了解', reading['action'], 'the reference is not merged into it')
        self.assertEqual(originals, payload['messages'])
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))

    def test_mislabelled_reference_of_a_real_requirement_still_rejects_the_whole_batch(self):
        for variant in ('reading', 'whole'):
            with self.subTest(variant=variant):
                t = type(self)(methodName='runTest');t.setUp()
                try:
                    payload, refs, replies = t._k12_mixed('reference')
                    if variant == 'whole':
                        # One reference quoting the whole message cannot swallow its located reading.
                        replies = [dict(copy.deepcopy(self.K12_RAW), title_quote=payload['messages'][0]['text'], evidence=[dict(ref=refs[0])]), replies[2]]
                    t._use_replies(payload, [dict(proposals=replies)])
                    t._assert_rejected_batch(payload, agent.run_once(t.app, t.now))
                finally:t.doCleanups()

    # Root's frozen C1 (fictional, base 5bdb5dc; the fixed reply is an authored program control, not provider output): the material's
    # own limit stands as its next comma part (资料，仅供了解), and the words of its closed title (请填表并签字) are its name, not actions.
    # The exact reference/optional reply is complete: nothing to do, no date, learning link or goal, and no retry left waiting.
    C1_TEXT = '阅读《请填表并签字》活动参考资料，仅供了解，自愿查看。'
    C1_RAW = dict(title_quote=C1_TEXT, focus='school', due='', evidence=[0], task_title='', task_goal='', task_advice='',
                  learning_subject='', learning_goal_id='', task_change='new', task_target_id='', task_state='reference',
                  task_reason='仅虚构程序对照。', task_purpose='optional', task_submission='')

    def _c1_ingest(self, text=C1_TEXT):
        self.fixture.now = self.now = dt.datetime(2026, 11, 2, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        payload['messages'] = [dict(id='11', message_order='11', time='2026-11-02T17:20:00+08:00', kind='text', sender='虚构学校发布人',
                                    sender_id='fictional-root-c1', text=text, unread=False)]
        self.store.ingest(payload)
        return payload, 'message:' + self.source['id'] + ':11'

    def test_root_c1_comma_limited_reference_saves_one_reference_through_ingest_run_once_replay_and_fresh_store_reopen(self):
        payload, ref = self._c1_ingest()
        self._use_replies(payload, [dict(proposals=[dict(copy.deepcopy(self.C1_RAW), evidence=[dict(ref=ref)])])])
        requests = []
        saved_reply = self.model.side_effect
        self.model.side_effect = lambda messages, *args, **kwargs: (requests.append(json.loads(messages[-1]['content'])), saved_reply(messages, *args, **kwargs))[1]
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1), 'the exact reference reply completes its batch on the first receipt')
        self.assertNotIn('required_native_actions', requests[0], 'a comma-limited material is no required native action')
        with self.store._db() as c:
            job = c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
            self.assertEqual(tuple(job), (1, 1, '', ''), 'no retry is left waiting')
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
        import family_review

        def check(rows, tasks, originals, manual, goals):
            row, = rows
            plan = json.loads(row['plan']);brief = plan['school_task']
            self.assertEqual((brief['state'], brief['purpose'], row['due'], row['task_id'] or '', plan.get('school_learning'), plan.get('school_goal_id', '')),
                             ('reference', 'optional', '', '', None, ''), 'one reference: no to-do, date, learning link or goal')
            self.assertFalse({'school_native_action', 'school_original_action', 'school_native_cover'} & set(plan))
            self.assertEqual((brief['title'], brief['goal']), ('', ''))
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], [ref])
            self.assertEqual([self.C1_TEXT in e['text'] for e in json.loads(row['evidence'])], [True], 'the complete original keeps its title')
            self.assertFalse({'pdf_evidence', 'material_evidence', 'page_evidence'} & set(brief), 'no attachment was read or prepared')
            self.assertEqual((tasks, manual), ({}, 0), 'nothing to do was created')
            self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')
            self.assertEqual(goals, [], 'no school learning goal')

        first = self._k12_facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = self._k12_facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app))
        check(*fresh)
        self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first[0]], 'reopen keeps the one item without duplicates')
        self.assertEqual(self.model.call_count, 1)

    def test_root_c1_material_limit_as_its_next_comma_part_is_read_only_in_its_own_name_position(self):
        def actions(text):
            entry = dict(ref='message:synthetic-root-c1:1', text=text, kind='text', publisher='p', time='2026-11-02T17:20:00+08:00')
            return [(a['quote'], a['purpose']) for a in agent._school_native_actions([entry])]
        # The limit as the very next comma part reads like 资料仅供了解; a closed title's own words, verbs or dates are its name.
        for text in (self.C1_TEXT, '阅读活动参考资料，仅供了解，自愿查看。下一次全班具体任务及日期将另行通知。',
                     '阅读《请于周五前填表并签字》第2期参考资料，只供了解。'):
            with self.subTest(text=text):self.assertEqual(actions(text), [])
        cases = {
            # An addressed reading, or a date, count or further outcome after the limit, keeps the clause required.
            '请阅读《请填表并签字》活动参考资料，仅供了解，自愿查看。': [('请阅读《请填表并签字》活动参考资料，仅供了解，自愿查看', 'learning')],
            '阅读《请填表并签字》活动参考资料，仅供了解，11月6日前交读后感。': [('阅读《请填表并签字》活动参考资料，仅供了解，11月6日前交读后感', 'learning')],
            '阅读活动参考资料，仅供了解，自愿读3篇。': [('阅读活动参考资料，仅供了解，自愿读3篇', 'learning')],
            '阅读活动参考资料，仅供了解，并写一句理由。': [('阅读活动参考资料，仅供了解，并写一句理由', 'learning')],
            # Only the material noun's own limit joins it: another 仅供 part after a complete limit is any other part.
            '阅读活动参考资料仅供了解，仅供家长检查后签字。': [('阅读活动参考资料仅供了解，仅供家长检查后签字', 'learning')],
            # A page is no material name, whatever limit follows it.
            '阅读《四季花园》第3页，仅供了解，自愿查看。': [('阅读《四季花园》第3页，仅供了解，自愿查看', 'learning')],
            # A real outcome in the same sentence or the next keeps its own clause and date; the reference adds nothing to it.
            self.C1_TEXT[:-1] + '，请完成练习册第5页。': [('请完成练习册第5页', 'learning')],
            self.C1_TEXT + '请于11月6日前阅读第3期参考资料，并写一句理由。': [('请于11月6日前阅读第3期参考资料，并写一句理由', 'learning')],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):self.assertEqual(actions(text), expected)

    def test_root_c1_reference_beside_a_same_sentence_homework_keeps_the_homework_required_through_replay_and_reopen(self):
        import family_review
        text = self.C1_TEXT[:-1] + '，请完成练习册第5页。'
        payload, ref = self._c1_ingest(text)
        reference = dict(copy.deepcopy(self.C1_RAW), title_quote=self.C1_TEXT[:-1], evidence=[dict(ref=ref)])
        homework = fixtures.school_proposal(
            title_quote='请完成练习册第5页', evidence=[dict(ref=ref)], task_title='完成练习册第5页',
            task_goal='完成练习册第5页。', task_state='ready', task_reason='虚构回执。', task_purpose='learning')
        self._use_replies(payload, [dict(proposals=[reference, homework])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))

        def check(rows, tasks, originals, manual, goals):
            states = sorted((json.loads(r['plan'])['school_task']['state'], json.loads(r['plan'])['school_task']['purpose'], bool(r['task_id'])) for r in rows)
            self.assertEqual(states, [('ready', 'learning', True), ('reference', 'optional', False)])
            task, = tasks.values()
            self.assertIn('练习册第5页', task['action'], 'the real homework keeps its own requirement')
            self.assertNotIn('仅供了解', task['action'], 'the reference is not merged into it')
            self.assertEqual(manual, 1, 'the one to-do is the homework')
            self.assertEqual(originals, payload['messages'], 'the complete original stays unchanged')

        first = self._k12_facts(self.app, self.store);check(*first)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        app = family_review.load_app(self.fixture.root, self.fixture.data)
        fresh = self._k12_facts(app, agent.Store(app.connect, app.profiles, self.fixture.data, app=app));check(*fresh)
        self.assertEqual([r['id'] for r in fresh[0]], [r['id'] for r in first[0]], 'reopen keeps the items without duplicates')
        self.assertEqual(self.model.call_count, 1)

    def test_wrong_reference_over_a_comma_limited_required_reading_or_same_sentence_homework_still_rejects_the_whole_batch(self):
        texts = ('请阅读《请填表并签字》活动参考资料，仅供了解，自愿查看。',
                 '阅读《请填表并签字》活动参考资料，仅供了解，11月6日前交读后感。',
                 self.C1_TEXT[:-1] + '，请完成练习册第5页。')
        for text in texts:
            with self.subTest(text=text):
                t = type(self)(methodName='runTest');t.setUp()
                try:
                    payload, ref = t._c1_ingest(text)
                    raw = dict(copy.deepcopy(self.C1_RAW), title_quote=text, evidence=[dict(ref=ref)], task_reason='故意错误的合成回执。')
                    t._use_replies(payload, [dict(proposals=[raw])])
                    t._assert_rejected_batch(payload, agent.run_once(t.app, t.now))
                finally:t.doCleanups()

    def test_one_action_purpose_contract_reaches_batch_single_candidate_and_original_recovery(self):
        for prompt in (agent.SCHOOL_PROMPT, agent._task_prompt(None), agent._school_original_prompt(None, None, None)):
            self.assertIn('用途按本项明确的行动及其独立成果判定，不按老师称呼、科目或课程背景、文件名/材料名、任务标题或单一关键词判定', prompt)
            self.assertIn('只要求携带、准备、领取或购买物品/资料而本项没写学习成果', prompt)
            self.assertIn('不能只留提交而漏掉学习本身', prompt)
            self.assertIn('不为避免漏收或误收而猜成admin或learning', prompt)
            self.assertNotIn('learning：教学材料、课程', prompt)


if __name__ == '__main__':
    unittest.main()
