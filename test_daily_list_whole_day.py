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


if __name__ == '__main__':
    unittest.main()
