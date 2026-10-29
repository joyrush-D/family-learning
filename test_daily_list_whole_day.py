"""Run python3 test_daily_list_whole_day.py. Root's frozen fictional whole day (ROOT-FROZEN-WHOLE-DAY.json, 2026-11-04).

Six teacher messages, frozen before this test, go through the real Store ingest -> run_once -> save -> calendar list with one
fixed, correct fictional selection receipt: six executable school actions, one reference-only message, plus the child's own
oral report through the study store: seven original tasks, five for today and two future classroom/carrying actions. A pass
proves the real save/date/list path with a correct reply, never the product model's own extraction, which stays unmeasured.
Then the math task: its existing feedback -> an explicitly linked wrong record -> diagnosis and new attempts through the real
family_taxonomy calls (fabricated pack, stubbed grader as in test_deeptutor_bridge) -> that same task's saved progress.
"""
import datetime as dt
import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

import family_agent as agent
import family_deeptutor
import family_study
import family_taxonomy as ft
import test_agent as fixtures
import test_daily_list_frozen as frozen

DAY = '2026-11-04'
# The frozen originals, byte for byte (ids, order, senders and send times included).
MESSAGES = (('501', 'fictional-chinese', '虚构语文老师', '语文：今晚朗读《晚照》2遍，请家长签字，明天早读检查。', '16:00'),
            ('502', 'fictional-math', '虚构数学老师', '数学：今晚完成练习册第12页第2至4题，写出计算过程，明天交回。', '16:01'),
            ('503', 'fictional-english', '虚构英语老师', '英语：今晚听音频跟读Unit 7第3至10个单词，每词3遍，不用抄写；明天英语课听写。', '16:02'),
            ('504', 'fictional-english', '虚构英语老师', '英语：明天英语课带《单词听写本》，不用在家练习。', '16:03'),
            ('505', 'fictional-form', '虚构班主任', '班主任通知：今晚请家长在《出游回执》勾选参加或不参加并签名，下周一由孩子交回。', '16:04'),
            ('506', 'fictional-reference', '虚构班主任', '供参考：读物《海边小记》，自愿阅读，不布置作业，不用提交。', '16:05'))
ORAL = '今天数学口头作业：订正课堂练习第5、6题，写出每题错因。'
# The frozen expectations: (anchor, own message, subjects ('综合事务' = no course, filed as 综合), complete_on, due_on, due_kind
# (None = tonight's work whose day may stand as completion or plain deadline), words kept, words never in it).
EXPECTED = (
    ('晚照', '501', ['语文'], DAY, '2026-11-05', 'inspection', ('《晚照》', '2遍', '家长', '签'), ('交回', '听写', '回执')),
    ('练习册第12页', '502', ['数学'], DAY, '2026-11-05', 'handback', ('12', '2', '4', '计算过程'), ('签', '听写', '回执')),
    ('跟读', '503', ['英语'], DAY, None, None, ('Unit 7', '3', '10', '3遍', '不用抄写'), ('听写本', '回执', '交回')),
    ('英语课听写', '503', ['英语'], '', '2026-11-05', 'inspection', ('听写',), ('今晚', '跟读', '回执')),
    ('单词听写本', '504', ['英语'], '', '2026-11-05', 'arranged', ('《单词听写本》', '不用在家练习'), ('跟读', '今晚', '回执')),
    ('出游回执', '505', '综合事务', DAY, '2026-11-09', 'handback', ('出游回执', '家长', '勾选', '参加或不参加', '签名', '孩子', '交回'),
     ('已选择', '确认参加', '报名参加', '晚照', '听写')))
NOTE = '题面：0.2+0.3=?\n学生原答：0.23\n可见订正/正确答案：0.5\n由照片标注生成，家长已核对；这不是掌握程度结论。'
TOPICS = [{'id': 'cnm_t1', 'name': '分数与小数互化', 'chapter': '五下 第4单元'}, {'id': 'cnm_t2', 'name': '小数加法', 'chapter': '五上 第1单元'}]
DEPS = [{'topicId': 'cnm_t2', 'prerequisiteId': 'cnm_t1', 'strength': 'hard'}]
QS = [{'id': 'cnm_t1_q%d' % i, 'topicId': 'cnm_t1', 'type': 'numeric', 'prompt': '1/2写成小数？', 'answer': '0.5'} for i in (1, 2)] + \
     [{'id': 'cnm_t2_q1', 'topicId': 'cnm_t2', 'type': 'numeric', 'prompt': '0.2+0.3=?', 'answer': '0.5'},
      {'id': 'cnm_t2_q2', 'topicId': 'cnm_t2', 'type': 'choice', 'prompt': '0.1+0.1=?', 'choices': [{'key': 'A', 'text': '0.2'}, {'key': 'B', 'text': '0.11'}], 'answer': 'A'}]


def proposal(quote, refs, title, goal, subject='', due='', purpose='learning', submission=''):
    return fixtures.school_proposal(title_quote=quote, due=due, evidence=[dict(ref=r) for r in refs], learning_subject=subject,
                                    task_title=title, task_goal=goal, task_state='ready', task_purpose=purpose,
                                    task_submission=submission, task_reason='虚构固定回执，只验校验/保存/展示。')


class WholeDayTests(unittest.TestCase):
    setUp = frozen.DailyListFrozenTests.setUp
    _use_replies = frozen.DailyListFrozenTests._use_replies

    def _ingest(self):
        payload = self.fixture.payload(cursor='506')
        payload['messages'] = [dict(id=i, message_order=i, time=DAY + 'T' + hm + ':00+08:00', kind='text', sender=sender,
                                    sender_id=publisher, text=text, unread=False) for i, publisher, sender, text, hm in MESSAGES]
        self.store.ingest(payload)
        return payload, {i: 'message:' + self.source['id'] + ':' + i for i, *_ in MESSAGES}

    def _replies(self, r):
        """The correct fixed reply: one proposal per executable action and the reference-only 506 kept as reference."""
        return [proposal('今晚朗读《晚照》2遍，请家长签字，明天早读检查', [r['501']], '语文：朗读《晚照》2遍并请家长签字',
                         '今晚朗读《晚照》2遍；读完请家长签字；11月5日早读检查。', '语文', '2026-11-05'),
                proposal('今晚完成练习册第12页第2至4题，写出计算过程，明天交回', [r['502']], '数学：练习册第12页第2至4题',
                         '今晚完成练习册第12页第2至4题，写出计算过程；11月5日交回。', '数学', '2026-11-05', submission='明天交回'),
                proposal('今晚听音频跟读Unit 7第3至10个单词，每词3遍，不用抄写', [r['503']], '英语：跟读Unit 7第3至10个单词',
                         '今晚听音频跟读Unit 7第3至10个单词，每词3遍；不用抄写。', '英语'),
                proposal('明天英语课听写', [r['503']], '英语：明天英语课听写', '11月5日英语课听写。', '英语', '2026-11-05'),
                proposal('明天英语课带《单词听写本》，不用在家练习', [r['504']], '英语：携带单词听写本',
                         '11月5日英语课带《单词听写本》，不用在家练习。', '', '2026-11-05', 'admin'),
                proposal('今晚请家长在《出游回执》勾选参加或不参加并签名，下周一由孩子交回', [r['505']], '出游回执：家长勾选并签名，孩子交回',
                         '今晚家长在《出游回执》勾选参加或不参加并签名；孩子11月9日交回。', '', '2026-11-09', 'admin', '下周一由孩子交回'),
                fixtures.school_proposal(title_quote='供参考：读物《海边小记》，自愿阅读，不布置作业，不用提交', evidence=[dict(ref=r['506'])],
                                         task_state='reference', task_purpose='optional', task_reason='参考读物，不布置作业。')]

    @staticmethod
    def _header_kept(proposals):
        """The same correct reply quoting each original from its own start, its header (英语：、班主任通知：) kept, as Root's
        alternate fixed reply does; a quote not opening its original (503's 明天英语课听写, 506's whole text) is unchanged."""
        texts = {i: text for i, _, _, text, _ in MESSAGES}
        out = []
        for p in proposals:
            text = texts[p['evidence'][0]['ref'].rsplit(':', 1)[-1]]
            header = text[:text.index('：') + 1] if '：' in text[:8] else ''
            out.append(dict(p, title_quote=header + p['title_quote']) if header and text.startswith(header + p['title_quote']) else p)
        return out

    def _list(self):
        snapshot = self.app.calendar_snapshot(DAY, DAY)
        mine = [i for i in snapshot['inbox'] if i['child_ids'] == ['child-1'] and i['kind'] in ('task', 'school')]
        visible = {i['title'] for i in snapshot['agenda'] if i['kind'] in ('task', 'school')}
        return mine, visible

    def _check_school(self, mine, refs):
        """Every school item against the frozen expectations; returns each one's listed agenda by its anchor."""
        school = [i for i in mine if i['agenda'].get('publications')]
        self.assertEqual(len(school), 6)
        listed = {}
        for anchor, ref, subjects, complete, due, kind, keep, never in EXPECTED:
            item, = [i for i in school if anchor in i['title'] + i['body']]
            m, words = item['agenda'], item['title'] + '\n' + item['body']
            self.assertEqual([p['ref'] for p in m['publications']], [refs[ref]], (anchor, 'its own teacher original only'))
            self.assertEqual(m['published_at'][:16], DAY + 'T' + dict((i, hm) for i, _, _, _, hm in MESSAGES)[ref], anchor)
            if subjects == '综合事务': self.assertEqual((m['subjects'], m['subject_state']), ([], 'general'), anchor)
            else: self.assertEqual(m['subjects'], subjects, anchor)
            for word in keep: self.assertIn(word, words, anchor)
            for word in never: self.assertNotIn(word, words, anchor)
            self.assertEqual(m['scheduled_on'], '', (anchor, 'no planned day is invented'))
            if kind is None:
                self.assertNotIn(m.get('due_kind', ''), ('handback', 'inspection', 'arranged'), anchor)
                self.assertIn(complete, (m.get('complete_on', ''), m['due_on'] if m.get('due_kind', '') in ('', 'deadline') else ''), anchor)
            else:
                self.assertEqual((m.get('complete_on', ''), m['due_on'], m.get('due_kind', '')), (complete, due, kind), anchor)
            listed[anchor] = (item['id'], m)
        return listed

    def _oral(self):
        study = family_study.Store(self.app, authorize=lambda c, child_id: None)  # the child's own report
        study._now = lambda: dt.datetime(2026, 11, 4, 20, 30, tzinfo=family_study.TZ)
        return study.save_item(dict(child_id='child-1', day=DAY, request_key='oral-whole-day-request-0001', title='数学：订正课堂练习第5、6题',
                                    subject='数学', report=dict(text=ORAL, goal='订正课堂练习第5、6题，写出每题错因。')))

    def _pack(self):
        pack = self.fixture.root / 'pack'; manifest = {}
        for rel, body in (('data/topics.json', TOPICS), ('data/dependencies.json', DEPS), ('data/questions.json', QS), ('diagnose/engine.js', None)):
            (pack / rel).parent.mkdir(parents=True, exist_ok=True)
            raw = b'/* fabricated test placeholder, not the upstream engine */' if body is None else json.dumps(body, ensure_ascii=False).encode()
            (pack / rel).write_bytes(raw); manifest[rel] = (hashlib.sha256(raw).hexdigest(), len(raw))
        self.stack.enter_context(mock.patch.object(ft, 'MANIFEST', manifest))
        self.stack.enter_context(mock.patch.object(family_deeptutor, 'DEFAULT_PYTHON', self.fixture.root / 'no-runtime' / 'python'))
        ft._PACKS.clear(); ft._VERIFIED.clear()
        return pack

    @staticmethod
    def fake_dt(op, snapshot, **kw):  # the bridge test's stub grader; the real DeepTutor run is Root's
        if op == 'register': return {'snapshot': 'S1'}
        if op == 'grade': return {'snapshot': 'S2', 'replayed': False, 'deeptutor_sha': 'x',
                                  'interaction': {'result': {'is_correct': kw['answer'] == 'A', 'independent': True}}}
        raise AssertionError(op)

    def dump(self):
        with self.app.connect() as c: return '\n'.join(c.iterdump())

    def test_root_frozen_whole_day_seven_tasks_then_math_progress_on_the_same_task(self):
        payload, refs = self._ingest()
        self._use_replies(payload, [dict(proposals=self._replies(refs))])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 6))
        with self.store._db() as c:
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')], payload['messages'])
        self._oral(); self._oral()  # the same oral request again (a lost reply) adds nothing; counted below
        mine, visible = self._list()
        self.assertEqual(len(mine), 7, [i['title'] for i in mine])
        self.assertFalse([i for i in mine if '海边小记' in i['title'] + i['body']], '506 is reference only')
        self._check_school(mine, refs)
        oral, = [i for i in mine if '第5、6题' in i['title'] + i['body']]
        self.assertFalse(oral['agenda'].get('publications'), 'the oral addition has no teacher original')
        on_day = sorted(i['title'] for i in mine if DAY in (i['agenda']['due_on'], i['agenda']['scheduled_on'], i['agenda'].get('complete_on', '')) and i['title'] in visible)
        self.assertEqual(len(on_day), 5, on_day)
        future = sorted(i['title'] for i in mine if i['title'] not in on_day)
        self.assertEqual(len(future), 2, future)
        self.assertTrue(any('听写' in t and '听写本' not in t for t in future) and any('听写本' in t for t in future), future)
        tasks = {t['id']: t for t in self.app.tasks()}
        oral_task, = [t for t in tasks.values() if '第5、6题' in t['title']]
        self.assertEqual(oral_task['source'], family_study.CHILD_REPORT_PENDING, 'keeps its 孩子自述 origin')
        self.assertFalse([t for t in tasks.values() if t.get('progress')], 'nothing saved yet: no progress line anywhere')
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(self.model.call_count, 1)

        # The math task: existing feedback, a lost reply resent with the same request, an explicit link, then real taxonomy calls.
        math, = [t for t in tasks.values() if t.get('school_origin') and '练习册第12页' in t['title'] + t.get('action', '')]
        photo = self.app.save_upload(io.BytesIO(b'synthetic page'), 14, 'synthetic-page.txt')['id']
        body = dict(task_id=math['id'], child='示例甲', day=DAY, request_key='whole-day-feedback-0001', note='第3题进位错了', attachments=[photo])
        first = self.app.save_task_feedback(body)
        self.assertEqual(first['task']['progress'], dict(feedback=1, wrong=0, wrong_ids=[], clues=0, retries=0, history=0), 'the save returns the new line')
        again = self.app.save_task_feedback(body)
        self.assertEqual((again['record_id'], again['task']['progress']['feedback']), (first['record_id'], 1), 'a lost reply resent adds nothing')
        wrong = self.app.save_record(dict(child='示例甲', day=DAY, category='学习进展', subject='数学', title='数学错题：第3题', note=NOTE, source=ft.WRONG_SOURCE))['record_id']
        other = self.app.save_record(dict(child='示例乙', day=DAY, category='学习进展', subject='数学', title='数学错题：第3题', note=NOTE, source=ft.WRONG_SOURCE))['record_id']
        self.assertEqual(next(t for t in self.app.tasks() if t['id'] == math['id'])['progress']['wrong'], 0, 'same subject and title are never a link')
        linked = self.app.link_record_task(dict(record_id=wrong, child='示例甲', task_id=math['id']))
        self.assertEqual(linked['task']['progress'], dict(feedback=1, wrong=1, wrong_ids=[wrong], clues=0, retries=0, history=0))
        with self.assertRaises(self.app.RecordError): self.app.link_record_task(dict(record_id=other, child='示例乙', task_id=math['id']))
        pack = self._pack()
        call = lambda fn, **obj: fn(self.app, dict(child_id='child-1', record_id=wrong, **obj), pack)
        call(ft.link_record, topic_id='cnm_t2', state='confirmed', request_id='link-request-000001')
        d = call(ft.start, topic_id='cnm_t2', request_id='start-request-00001')['diagnoses'][0]
        call(ft.answer, diagnosis_id=d['id'], seq=1, topic_id='cnm_t2', qid='cnm_t2_q1', kind='answer', answer='0.23', verdict='wrong',
             engine_result='wrong', session={'answers': [{'id': 'cnm_t2', 'qid': 'cnm_t2_q1', 'result': 'wrong', 'text': '0.23'}]}, summary={'finished': False})
        for qid in ('cnm_t2_q2', 'cnm_t1_q2'): call(ft.mark, diagnosis_id=d['id'], action='shown', mode='retry', qid=qid)
        with mock.patch.object(family_deeptutor, 'call', side_effect=self.fake_dt):
            call(ft.retry, diagnosis_id=d['id'], qid='cnm_t2_q2', answer='D', verdict='wrong', request_id='retry-request-ind001')
        with mock.patch.object(family_deeptutor, 'call', side_effect=AssertionError('a parent check calls no grader')):
            call(ft.retry, diagnosis_id=d['id'], qid='cnm_t1_q2', answer='0.5', verdict='manual', request_id='retry-request-man001')
        with self.app.connect() as c:
            self.assertEqual(sorted(r[0] for r in c.execute('SELECT outcome FROM topic_retries')), ['independent_wrong', 'parent_check'])
        before = self.dump()
        progress = next(t for t in self.app.tasks() if t['id'] == math['id'])['progress']
        self.assertEqual(progress, dict(feedback=1, wrong=1, wrong_ids=[wrong], clues=1, retries=1, history=0), 'the parent check is no independent attempt')
        self.assertEqual(self.dump(), before, 'opening the list writes nothing')

        # Reopen: the same seven tasks, the oral report once, progress only on the math task.
        mine, _ = self._list()
        self.assertEqual(len(mine), 7)
        self.assertEqual(len([i for i in mine if '第5、6题' in i['title'] + i['body']]), 1)
        reopened = {t['id']: t for t in self.app.tasks()}
        self.assertEqual([i for i, t in reopened.items() if t.get('progress')], [math['id']])
        self.assertEqual(reopened[math['id']]['progress'], progress)

    def test_the_same_correct_reply_keeping_each_header_lists_and_reopens_the_same_whole_day(self):
        """Root's alternate fixed reply quotes 英语：明天英语课带《单词听写本》，不用在家练习 whole: its own course header names the
        item, never the predicate, so every action reads the same day and role as the header-stripped run above."""
        payload, refs = self._ingest()
        kept = self._header_kept(self._replies(refs))
        self.assertEqual(sorted(p['title_quote'] for p in kept if p['title_quote'] not in [q['title_quote'] for q in self._replies(refs)]),
                         sorted(text.rstrip('。').split('；')[0] for i, _, _, text, _ in MESSAGES if i != '506'), 'five header-kept quotes')
        self._use_replies(payload, [dict(proposals=kept)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 6))
        with self.store._db() as c:
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')], payload['messages'])
            plans = [json.loads(r[0]) for r in c.execute("SELECT plan FROM agent_items WHERE kind='school'")]
        quotes = [p.get('school_date_quote') or p.get('school_native_action', {}).get('quote', '') for p in plans]
        self.assertIn('英语：明天英语课带《单词听写本》，不用在家练习', quotes, 'the header-kept quote is the one saved')
        mine, visible = self._list()
        self.assertEqual(len(mine), 6, [i['title'] for i in mine])
        listed = self._check_school(mine, refs)
        on_day = [i['title'] for i in mine if DAY in (i['agenda']['due_on'], i['agenda'].get('complete_on', '')) and i['title'] in visible]
        future = [i['title'] for i in mine if i['title'] not in on_day]
        self.assertEqual(len(on_day), 4, on_day)
        self.assertTrue(len(future) == 2 and any('听写' in t and '听写本' not in t for t in future) and any('听写本' in t for t in future), future)
        # Reopen after a restart: a fresh Store over the same data asks nothing again and lists the same days and roles.
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(self.model.call_count, 1)
        self.assertEqual(self._check_school(self._list()[0], refs), listed)


FRIDAY = '2026-11-06'
# A fictional Friday whose correct reply quotes each action short: the later check, the ordered second step's 今晚 and the
# carrying arrangement are only in each item's own complete original words.
FRIDAY_MESSAGES = (('801', 'fictional-cn', '虚构语文老师', '语文今晚完成《溪边》课后第1、3题，只写答案；明早语文课检查。', '17:01'),
                   ('802', 'fictional-cn', '虚构语文老师', '更正：刚才《溪边》的课后题要写出理由，不是只写答案。其他要求不变。', '17:04'),
                   ('803', 'fictional-math', '虚构数学老师', '数学今晚先完成《口算本》第6页第2、5题，每题写计算过程。再订正《单元卷》第4题，订正写在原题旁。', '17:10'),
                   ('804', 'fictional-science', '虚构科学老师', '科学课下周一带《叶片记录表》；本周末不用填写，课堂上再做。', '17:21'))


class FridayOwnRangeTests(unittest.TestCase):
    """Short quotes and split actions keep the time, later check and carrying their own complete original words state."""
    setUp = frozen.DailyListFrozenTests.setUp
    _use_replies = frozen.DailyListFrozenTests._use_replies
    _list = WholeDayTests._list

    def _run(self, messages, replies):
        self.fixture.now = self.now = dt.datetime(2026, 11, 6, 18, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor=messages[-1][0])
        payload['messages'] = [dict(id=i, message_order=i, time=FRIDAY + 'T' + hm + ':00+08:00', kind='text', sender=sender,
                                    sender_id=publisher, text=text, unread=False) for i, publisher, sender, text, hm in messages]
        self.store.ingest(payload)
        refs = {i: 'message:' + self.source['id'] + ':' + i for i, *_ in messages}
        self._use_replies(payload, [dict(proposals=replies(refs))])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, len(messages)))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")]
        snapshot = self.app.calendar_snapshot(FRIDAY, '2026-11-12')
        listed = {i['id']: i for i in snapshot['inbox'] if i['kind'] in ('task', 'school') and i['child_ids'] == ['child-1']}
        return rows, listed, refs

    @staticmethod
    def _replies(cn='语文今晚完成《溪边》课后第1、3题', second='再订正《单元卷》第4题，订正写在原题旁',
                 carry='科学课下周一带《叶片记录表》；本周末不用填写，课堂上再做'):
        return lambda r: [
            proposal(cn, [r['801'], r['802']], '语文：完成溪边课后题并写出理由', '今晚完成《溪边》课后第1、3题，每题写出理由。明早语文课检查。',
                     '语文', '2026-11-07'),
            proposal('数学今晚先完成《口算本》第6页第2、5题，每题写计算过程', [r['803']], '数学：口算本第6页第2、5题',
                     '今晚完成《口算本》第6页第2、5题，每题写计算过程。', '数学'),
            proposal(second, [r['803']], '数学：订正单元卷第4题', '今晚订正《单元卷》第4题，订正写在原题旁。', '数学'),
            proposal(carry, [r['804']], '科学：下周一带叶片记录表', '科学课下周一带《叶片记录表》；本周末不用填写，课堂上再做。',
                     '', '2026-11-09', 'admin')]

    def _agenda(self, rows, listed, anchor):
        row, = [r for r in rows if anchor in json.loads(r['plan'])['school_task']['goal']]
        brief = json.loads(row['plan'])['school_task']
        return row, brief, listed[row['task_id'] or row['id']]['agenda']

    def _check_friday(self, rows, listed):
        self.assertEqual(len(rows), 4)
        row, brief, a = self._agenda(rows, listed, '溪边')
        self.assertEqual((row['state'], brief['state']), ('accepted', 'ready'), brief['reason'])
        self.assertEqual((a['complete_on'], a['due_on'], a['due_kind'], a['subjects']), (FRIDAY, '2026-11-07', 'inspection', ['语文']))
        self.assertNotIn('只写答案', brief['goal'])
        for anchor in ('口算本', '单元卷'):
            row, brief, a = self._agenda(rows, listed, anchor)
            self.assertEqual((row['state'], brief['state']), ('accepted', 'ready'), anchor)
            self.assertTrue(a['complete_on'] == FRIDAY or (a['due_on'], a['due_kind']) == (FRIDAY, 'deadline'), (anchor, a))
            self.assertNotIn(a['due_kind'], ('handback', 'inspection', 'arranged'), anchor)
        row, brief, a = self._agenda(rows, listed, '叶片记录表')
        self.assertEqual((row['state'], a['category'], a['complete_on'], a['due_on'], a['due_kind']), ('accepted', 'todo', '', '2026-11-09', 'arranged'))

    def test_friday_short_quotes_keep_their_own_check_ordered_step_and_carrying_through_the_store(self):
        rows, listed, _ = self._run(FRIDAY_MESSAGES, self._replies())
        self._check_friday(rows, listed)
        # Reopen after a restart: nothing asked or written again, the same days and roles.
        before = [dict(r) for r in rows]
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created'], self.model.call_count), (0, 0, 0, 1))
        with self.store._db() as c:
            self.assertEqual([dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")], before)

    def test_friday_variants_read_the_same_own_range(self):
        """The whole own clause quoted, 然后再, and the lesson after its day read the same; the reply's goal never dates it."""
        texts = {i: t for i, _, _, t, _ in FRIDAY_MESSAGES}
        for name, change, kwargs in (
                ('complete short quote', {}, dict(cn='语文今晚完成《溪边》课后第1、3题，只写答案')),
                ('然后再', {'803': texts['803'].replace('。再', '。然后再')}, dict(second='然后再订正《单元卷》第4题，订正写在原题旁')),
                ('day before lesson', {'804': '下周一科学课带《叶片记录表》；本周末不用填写，课堂上再做。'},
                 dict(carry='下周一科学课带《叶片记录表》；本周末不用填写，课堂上再做'))):
            with self.subTest(name):
                self.setUp()
                messages = tuple((i, p, s, change.get(i, t), hm) for i, p, s, t, hm in FRIDAY_MESSAGES)
                self._check_friday(*self._run(messages, self._replies(**kwargs))[:2])

    def test_friday_other_actions_teachers_days_and_negations_never_lend_their_words(self):
        sent = FRIDAY + 'T17:01:00+08:00'
        cited = lambda *texts: [dict(ref='message:fictional:%d' % n, text=t, time=sent) for n, t in enumerate(texts)]
        own = '语文今晚完成《溪边》课后第1、3题'
        self.assertEqual(agent._school_role_days(own, cited(FRIDAY_MESSAGES[0][3], FRIDAY_MESSAGES[1][3]), []), ({FRIDAY}, '2026-11-07'))
        for text in ('语文今晚完成《溪边》课后第1、3题，数学明天交练习册；明早语文课检查。',   # another action's own day in the rest
                     '语文今晚完成《溪边》课后第1、3题，只写答案；明早数学课检查。',          # another subject's lesson
                     '语文今晚完成《溪边》课后第1、3题，只写答案；后天或明早语文课检查。'):  # an open day
            with self.subTest(text):self.assertIsNone(agent._school_role_days(own, cited(text), []))
        self.assertIsNone(agent._school_role_days(own, cited(FRIDAY_MESSAGES[0][3]), ['明早语文课检查']), 'another proposal quotes the check')
        span = '语文今晚完成《溪边》课后第1、3题，只写答案；明早语文课检查。'
        for later in ('更正：刚才《溪边》的课后题改为后天检查。', '更正：《溪边》课后题明早不用检查了。', '更正：刚才《溪边》的课后题要带到学校再写。'):
            with self.subTest(later):self.assertTrue(agent._school_range_withdrawn(span, ['', '', later]))
        self.assertFalse(agent._school_range_withdrawn(span, ['', '', FRIDAY_MESSAGES[1][3]]), 'only how the work is written changed')
        math = FRIDAY_MESSAGES[2][3]
        self.assertEqual(agent._school_scope_day('再订正《单元卷》第4题，订正写在原题旁', cited(math))['day'], FRIDAY)
        for text, quote in ((math.replace('今晚先完成', '今晚完成'), '再订正《单元卷》第4题，订正写在原题旁'),  # no ordered 先
                            (math.replace('再订正', '再明天订正'), '再明天订正《单元卷》第4题，订正写在原题旁'),  # its own other day
                            (math.replace('再订正', '英语再订正'), '英语再订正《单元卷》第4题，订正写在原题旁'),  # another subject
                            (math.replace('再订正', '再请家长签字并订正'), '再请家长签字并订正《单元卷》第4题，订正写在原题旁')):
            with self.subTest(text):self.assertNotEqual((agent._school_scope_day(quote, cited(text)) or {}).get('kind'), 'continued')
        from family_agenda import date_meaning
        self.assertEqual(date_meaning('科学课下周一带《叶片记录表》', '2026-11-09', FRIDAY), 'arranged')
        for text in ('科学课下周一不用带《叶片记录表》', '科学课下周一前带《叶片记录表》', '科学课下周一交《叶片记录表》'):
            with self.subTest(text):self.assertNotEqual(date_meaning(text, '2026-11-09', FRIDAY), 'arranged')

    def test_friday_counted_heading_and_same_day_restating_correction_through_the_store(self):
        """数学今晚有两项：1.…；2.…，订正写在原题旁 keeps two items reading the shared 今晚; 今天照常完成，明天照常检查 moves no role."""
        messages = (('811', 'fictional-cn', '虚构语文老师', '语文今天先做《溪边》课后第1、3题，答案只需写结论。明天早读检查。', '17:01'),
                    ('812', 'fictional-cn', '虚构语文老师', '更正刚才《溪边》课后题：每题还要写出理由，今天照常完成，明天照常检查。', '17:04'),
                    ('813', 'fictional-math', '虚构数学老师', '数学今晚有两项：1.完成《口算本》第6页第2、5题，每题写计算过程；2.订正《单元卷》第4题，订正写在原题旁。', '17:10'))
        rows, listed, _ = self._run(messages, lambda r: [
            proposal('语文今天先做《溪边》课后第1、3题', [r['811'], r['812']], '语文：溪边课后题写出理由',
                     '今天完成《溪边》课后第1、3题，每题写出理由。明天早读检查。', '语文', '2026-11-07'),
            proposal('完成《口算本》第6页第2、5题，每题写计算过程', [r['813']], '数学：口算本第6页', '今晚完成《口算本》第6页第2、5题，每题写计算过程。', '数学'),
            proposal('订正《单元卷》第4题，订正写在原题旁', [r['813']], '数学：订正单元卷第4题', '今晚订正《单元卷》第4题，订正写在原题旁。', '数学')])
        self.assertEqual(len(rows), 3)
        row, brief, a = self._agenda(rows, listed, '溪边')
        self.assertEqual((row['state'], brief['state']), ('accepted', 'ready'), brief['reason'])
        self.assertEqual((a['complete_on'], a['due_on'], a['due_kind']), (FRIDAY, '2026-11-07', 'inspection'))
        for anchor, kept in (('口算本', '计算过程'), ('单元卷', '原题旁')):
            row, brief, a = self._agenda(rows, listed, anchor)
            self.assertEqual((row['state'], brief['state'], a['subjects']), ('accepted', 'ready', ['数学']), anchor)
            self.assertIn(kept, brief['goal'])
            self.assertTrue(a['complete_on'] == FRIDAY or (a['due_on'], a['due_kind']) == (FRIDAY, 'deadline'), (anchor, a))

    def test_friday_counted_heading_and_restating_correction_never_widen(self):
        sent = FRIDAY + 'T17:10:00+08:00'
        math = '数学今晚有两项：1.完成《口算本》第6页第2、5题，每题写计算过程；2.订正《单元卷》第4题，订正写在原题旁。'
        first, second = '完成《口算本》第6页第2、5题，每题写计算过程', '订正《单元卷》第4题，订正写在原题旁'
        ledger = lambda text: agent._school_native_actions([dict(ref='message:fictional:813', text=text, kind='text', publisher='p-math', time=sent)])
        # The standard 订正写在原题旁 stays with its own item: exactly two outcomes, each its whole numbered words.
        self.assertEqual([a['quote'] for a in ledger(math)], [first, second])
        cited = lambda text: [dict(text=text, time=sent)]
        self.assertEqual([agent._school_list_heading_day(q, cited(math), [o]) for q, o in ((first, second), (second, first))], [FRIDAY, FRIDAY])
        for text in (math.replace('两项', '三项'),               # numbers that do not meet the stated count head nothing
                     math.replace('今晚', '明天'),               # another heading day
                     math.replace('2.订正', '2.明天订正'),        # an item's own other day
                     math.replace('今晚有两项', '今晚第2项')):    # an ordinal is no count
            with self.subTest(text):
                self.assertEqual({agent._school_list_heading_day(q, cited(text), []) for q in (first, second) if q in text} - {''}, set())
        self.assertNotEqual([a['quote'] for a in ledger(math.replace('两项', '三项'))], [first, second])
        own, t1 = '语文今天先做《溪边》课后第1、3题', '语文今天先做《溪边》课后第1、3题，答案只需写结论。明天早读检查。'
        fix = '更正刚才《溪边》课后题：每题还要写出理由，今天照常完成，明天照常检查。'
        pair = lambda later, publisher='p-cn', hm='17:04': [
            dict(ref='message:fictional:811', text=t1, time=FRIDAY + 'T17:01:00+08:00', publisher='p-cn', kind='text', message_order='811'),
            dict(ref='message:fictional:812', text=later, time=FRIDAY + 'T' + hm + ':00+08:00', publisher=publisher, kind='text', message_order='812')]
        self.assertEqual(agent._school_role_days(own, pair(fix), []), ({FRIDAY}, '2026-11-07'))
        self.assertEqual(agent._school_role_days(own, pair(fix), [], words=True)[1], '2026-11-07')
        for later in (fix.replace('明天照常检查', '后天检查'),              # a changed day
                      fix.replace('明天照常检查', '明天不用检查'),          # a withdrawn check
                      fix.replace('明天照常检查', '明天或后天检查'),        # an open day
                      fix.replace('《溪边》', '《山行》'),                 # another title
                      fix.replace('《溪边》', '数学'),                     # another subject
                      fix + '后天再交一次。'):                             # a further sentence of its own
            with self.subTest(later):self.assertIsNone(agent._school_role_days(own, pair(later), []))
        self.assertIsNone(agent._school_role_days(own, pair(fix, 'p-other'), []), 'another teacher')
        self.assertIsNone(agent._school_role_days(own, pair(fix, 'p-cn', '16:00'), []), 'not later')
        self.assertIsNone(agent._school_role_days(own, [dict(text=t1, time=FRIDAY + 'T17:01:00+08:00'), dict(text=fix, time=FRIDAY + 'T17:04:00+08:00')], []),
                          'no proven teacher')
        # A bare check names this item only when the message holds nothing else.
        self.assertIsNone(agent._school_role_days(own, cited('英语今晚读Unit 2。' + t1), []))
        self.assertIsNone(agent._school_role_days(own, cited(t1 + '数学明天交练习册。'), []))


if __name__ == '__main__':
    unittest.main()
