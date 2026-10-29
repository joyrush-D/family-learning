"""Run python3 test_daily_list_whole_day.py. Root's frozen fictional whole day (ROOT-FROZEN-WHOLE-DAY.json, 2026-11-04).

Six teacher messages, frozen before this test, go through the real Store ingest -> run_once -> save -> calendar list with one
fixed, correct fictional selection receipt: six executable school actions, one reference-only message, plus the child's own
oral report through the study store: seven original tasks, five for today and two future classroom/carrying actions. A pass
proves the real save/date/list path with a correct reply, never the product model's own extraction, which stays unmeasured.
Then the math task: its existing feedback -> an explicitly linked wrong record -> diagnosis and new attempts through the real
family_taxonomy calls (fabricated pack, stubbed grader as in test_deeptutor_bridge) -> that same task's saved progress.
"""
import contextlib
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


# Root's one actual product reply for these frozen originals (2026-10-30, deepseek-v4-1-flash-261017, ACTUAL-SELECTION.json), parsed and
# unchanged; only its fictional source id is mapped to this fixture's. Its 明天英语课听写 summary borrowed the sibling's range.
ACTUAL_REPLY = json.loads('{"proposals": [{"title_quote": "今晚朗读《晚照》2遍，请家长签字，明天早读检查", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:501"}], "task_title": "语文：朗读《晚照》2遍并家长签字", "task_goal": "今晚朗读《晚照》2遍。\\n请家长签字。\\n明天早读检查。", "task_advice": "可先通读一遍熟悉内容，再朗读第二遍；读完后请家长签字。", "learning_subject": "语文", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求今晚朗读2遍、家长签字，明天早读检查。", "task_purpose": "learning", "task_submission": "家长在朗读处签字，明天早读接受检查。"}, {"title_quote": "今晚完成练习册第12页第2至4题，写出计算过程，明天交回", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:502"}], "task_title": "数学：练习册第12页第2至4题", "task_goal": "今晚完成练习册第12页第2至4题。\\n须写出计算过程。\\n明天交回。", "task_advice": "可先独立完成，再检查计算过程是否写完整。", "learning_subject": "数学", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求完成练习册第12页第2至4题并写出计算过程，明天交回。", "task_purpose": "learning", "task_submission": "明天交回练习册。"}, {"title_quote": "今晚听音频跟读Unit 7第3至10个单词，每词3遍，不用抄写", "focus": "school", "due": "", "evidence": [{"ref": "message:synthetic-group:503"}], "task_title": "英语：跟读Unit 7第3至10个单词", "task_goal": "今晚听音频跟读Unit 7第3至10个单词。\\n每词3遍。\\n不用抄写。", "task_advice": "可先听一遍音频再跟读，每个单词跟读3遍。", "learning_subject": "英语", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求听音频跟读Unit 7第3至10个单词，每词3遍，不用抄写。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "明天英语课听写", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:503"}], "task_title": "英语：明天英语课听写", "task_goal": "明天英语课进行听写。\\n听写范围与今晚跟读的Unit 7第3至10个单词相关。", "task_advice": "可结合今晚跟读内容，听写前再听一遍音频熟悉单词。", "learning_subject": "英语", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确宣布明天英语课听写，按发送日换算为2026-11-05。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "明天英语课带《单词听写本》，不用在家练习", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:504"}], "task_title": "英语：明天带《单词听写本》", "task_goal": "明天英语课带《单词听写本》。\\n不用在家练习。", "task_advice": "可今晚把《单词听写本》放进书包，避免明天忘带。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求明天英语课携带《单词听写本》，并说明不用在家练习，属于带物事务。", "task_purpose": "admin", "task_submission": ""}, {"title_quote": "今晚请家长在《出游回执》勾选参加或不参加并签名，下周一由孩子交回", "focus": "school", "due": "2026-11-09", "evidence": [{"ref": "message:synthetic-group:505"}], "task_title": "家长：填写《出游回执》并签名", "task_goal": "今晚请家长在《出游回执》上勾选参加或不参加。\\n家长签名。\\n下周一由孩子交回。", "task_advice": "可今晚勾选并签名后放入孩子书包，提醒孩子下周一交回。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求家长今晚勾选参加或不参加并签名，下周一由孩子交回；按发送日换算交回日为2026-11-09。", "task_purpose": "admin", "task_submission": "下周一由孩子交回《出游回执》。"}, {"title_quote": "供参考：读物《海边小记》，自愿阅读，不布置作业，不用提交", "focus": "school", "due": "", "evidence": [{"ref": "message:synthetic-group:506"}], "task_title": "", "task_goal": "", "task_advice": "", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "reference", "task_reason": "仅为自愿阅读的参考读物，明确不布置作业、不用提交，不生成必做任务。", "task_purpose": "optional", "task_submission": ""}]}')
# Root's second actual reply (ACTUAL-SELECTION-TITLE.json), as returned: 明天英语课听写 now also titles itself from its sibling.
ACTUAL_TITLE_REPLY = json.loads('{"proposals": [{"title_quote": "今晚朗读《晚照》2遍，请家长签字，明天早读检查", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:501"}], "task_title": "语文：朗读《晚照》2遍并家长签字", "task_goal": "今晚朗读《晚照》2遍。\\n请家长签字。\\n明天早读检查。", "task_advice": "可分两遍朗读，中间稍作休息；家长听完后在书上或指定处签字。", "learning_subject": "语文", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求今晚朗读2遍、家长签字，明天早读检查。", "task_purpose": "learning", "task_submission": "家长签字，明天早读接受检查"}, {"title_quote": "今晚完成练习册第12页第2至4题，写出计算过程，明天交回", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:502"}], "task_title": "数学：练习册第12页第2–4题", "task_goal": "今晚完成练习册第12页第2至4题。\\n须写出计算过程。\\n明天交回。", "task_advice": "做完后逐题检查计算过程是否写全，再整理进书包。", "learning_subject": "数学", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求完成练习册指定页题、写出过程并明天交回。", "task_purpose": "learning", "task_submission": "明天交回练习册"}, {"title_quote": "今晚听音频跟读Unit 7第3至10个单词，每词3遍，不用抄写", "focus": "school", "due": "", "evidence": [{"ref": "message:synthetic-group:503"}], "task_title": "英语：跟读Unit 7第3–10个单词", "task_goal": "今晚听音频跟读Unit 7第3至10个单词。\\n每词3遍。\\n不用抄写。", "task_advice": "跟读时可先听一遍再逐词模仿，注意发音。", "learning_subject": "英语", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求今晚听音频跟读指定单词及遍数，并说明不用抄写。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "明天英语课听写", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:503"}], "task_title": "英语：Unit 7单词听写（明天）", "task_goal": "明天英语课进行听写。\\n范围与今晚跟读的Unit 7第3至10个单词对应。", "task_advice": "可在跟读后请家长抽问几个单词，帮助回忆。", "learning_subject": "英语", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确宣布明天英语课听写，范围与同条跟读单词对应。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "明天英语课带《单词听写本》，不用在家练习", "focus": "school", "due": "2026-11-05", "evidence": [{"ref": "message:synthetic-group:504"}], "task_title": "英语：明天带《单词听写本》", "task_goal": "明天英语课带《单词听写本》。\\n不用在家练习。", "task_advice": "今晚把《单词听写本》放进书包，避免明早遗漏。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求明天英语课携带听写本，并说明不用在家练习，属于带物事务。", "task_purpose": "admin", "task_submission": ""}, {"title_quote": "今晚请家长在《出游回执》勾选参加或不参加并签名，下周一由孩子交回", "focus": "school", "due": "2026-11-09", "evidence": [{"ref": "message:synthetic-group:505"}], "task_title": "交回《出游回执》（勾选并签名）", "task_goal": "今晚请家长在《出游回执》上勾选参加或不参加。\\n家长签名。\\n下周一由孩子交回。", "task_advice": "勾选后请家长确认签名，再放入孩子书包。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "班主任明确要求家长勾选参加或不参加并签名，下周一由孩子交回。", "task_purpose": "admin", "task_submission": "下周一由孩子交回《出游回执》"}, {"title_quote": "供参考：读物《海边小记》，自愿阅读，不布置作业，不用提交", "focus": "school", "due": "", "evidence": [{"ref": "message:synthetic-group:506"}], "task_title": "", "task_goal": "", "task_advice": "", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "reference", "task_reason": "仅为自愿阅读的参考读物，明确不布置作业、不用提交，不生成任务。", "task_purpose": "optional", "task_submission": ""}]}')


# ROOT-baseline-native-titles.json: 46b8687 saving the second actual reply, before any title guard. The original native path
# already reads 501 and 502 as these headings and goals; the title guard leaves them so.
NATIVE_BASELINE = (('501', '语文：朗读《晚照》2遍', '今晚朗读《晚照》2遍，请家长签字，明天早读检查'),
                   ('502', '数学：完成练习册第12页第2至4题', '今晚完成练习册第12页第2至4题，写出计算过程，明天交回'))
# ROOT-old-saved-on-13d9e09.json: what earlier releases saved for 明天英语课听写 (first reply; second reply under 46b8687).
OLD_GUARDS = ('_school_sibling_free_title', '_school_sibling_free_goal')
OLD_SAVED = ('英语：明天英语课听写', '明天英语课进行听写。\n听写范围与今晚跟读的Unit 7第3至10个单词相关。')
OLD_TITLE_SAVED = ('英语：Unit 7单词听写（明天）', '明天英语课进行听写。')


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

    def test_root_actual_reply_keeps_each_action_of_one_original_to_its_own_words(self):
        """The actual reply's 明天英语课听写 goal adds 今晚跟读的Unit 7第3至10个单词 as its scope; the teacher gave none. Through the
        real run_once the classroom action stays ready and dated with only its own sentence, its sibling stays complete, the
        model's suggestion stays in advice, the other items and the oral addition are unchanged, and a reopen reads the same."""
        payload, refs = self._ingest()
        reply = [dict(p, evidence=[dict(ref=refs[q['ref'].rsplit(':', 1)[-1]]) for q in p['evidence']]) for p in ACTUAL_REPLY['proposals']]
        self._use_replies(payload, [dict(proposals=reply)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 6))
        with self.store._db() as c:
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')], payload['messages'])
            plans = {r[0]: json.loads(r[1]) for r in c.execute("SELECT title, plan FROM agent_items WHERE kind='school'")}
        self._oral()
        mine, visible = self._list()
        self.assertEqual(len(mine), 7, [i['title'] for i in mine])
        listed = self._check_school(mine, refs)
        bodies = {i['title']: i['body'] for i in mine}
        self.assertEqual(bodies['英语：明天英语课听写'], '明天英语课进行听写。', 'its own action and teacher time; the range stays unknown')
        self.assertEqual(bodies['英语：跟读Unit 7第3至10个单词'], '今晚听音频跟读Unit 7第3至10个单词。\n每词3遍。\n不用抄写。')
        self.assertEqual(plans['英语：明天英语课听写']['school_task']['state'], 'ready', 'no extra parent confirmation')
        self.assertEqual(plans['英语：明天英语课听写']['school_task']['advice'], ACTUAL_REPLY['proposals'][3]['task_advice'], 'advice stays advice')
        self.assertEqual(sorted(p['school_task']['state'] for p in plans.values()), ['ready'] * 6 + ['reference'], '506 alone is reference')
        self.assertTrue(any('听写' in t and '听写本' not in t for t in visible) and len(mine) == 7)
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(self.model.call_count, 1)
        self.assertEqual(self._check_school(self._list()[0], refs), listed)

    def _actual(self, reply):
        """One actual reply, only its fictional source ids mapped to this fixture, through the real run_once -> Store, then
        the child's own oral addition through study: the seven tasks the served browser fixture lists."""
        payload, refs = self._ingest()
        self._use_replies(payload, [dict(proposals=[dict(p, evidence=[dict(ref=refs[q['ref'].rsplit(':', 1)[-1]]) for q in p['evidence']])
                                                    for p in reply['proposals']])])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 6))
        self._oral()
        return payload, refs

    def test_root_actual_title_reply_keeps_title_and_summary_to_their_own_words(self):
        """The second actual reply titles 明天英语课听写 英语：Unit 7单词听写（明天） and scopes its goal by 今晚跟读的Unit 7第3至10个单词;
        the teacher gave it neither. Through the real run_once its title and summary keep only its own words, ready and dated;
        every other title, the read-aloud's range, the advice and the oral addition stay, and a reopen reads the same."""
        payload, refs = self._actual(ACTUAL_TITLE_REPLY)
        with self.store._db() as c:
            plans = {r[0]: json.loads(r[1]) for r in c.execute("SELECT title, plan FROM agent_items WHERE kind='school'")}
        mine, visible = self._list()
        self.assertEqual(len(mine), 7, [i['title'] for i in mine])
        listed = self._check_school(mine, refs)
        items = {i['title']: i for i in mine}
        dictation, = [i for i in mine if '听写' in i['title'] and '听写本' not in i['title']]
        self.assertEqual(dictation['body'], '明天英语课进行听写。', 'its own action and teacher time; the range stays unknown')
        self.assertIn('英语课听写', dictation['title'])
        self.assertLessEqual(len(dictation['title']), 31, 'a short heading')
        for word in ('Unit', '单词', '第3', '10', '跟读', '今晚', '范围'):
            self.assertNotIn(word, dictation['title'] + '\n' + dictation['body'], word)
        by_ref = {i['agenda']['publications'][0]['ref'].rsplit(':', 1)[-1]: i for i in mine if i['agenda'].get('publications')}
        for ref, title, body in NATIVE_BASELINE:
            self.assertEqual((by_ref[ref]['title'], by_ref[ref]['body']), (title, body), (ref, 'the native baseline stays'))
        for title in ('英语：跟读Unit 7第3–10个单词', '英语：明天带《单词听写本》', '交回《出游回执》（勾选并签名）', '数学：订正课堂练习第5、6题'):
            self.assertIn(title, items, 'every other title stays as returned')
        self.assertEqual(items['英语：跟读Unit 7第3–10个单词']['body'], '今晚听音频跟读Unit 7第3至10个单词。\n每词3遍。\n不用抄写。')
        self.assertEqual(plans[dictation['title']]['school_task']['state'], 'ready', 'no extra parent confirmation')
        self.assertEqual(plans[dictation['title']]['school_task']['advice'], ACTUAL_TITLE_REPLY['proposals'][3]['task_advice'], 'advice stays advice')
        self.assertEqual(sorted(p['school_task']['state'] for p in plans.values()), ['ready'] * 6 + ['reference'], '506 alone is reference')
        self.assertIn(dictation['title'], visible, 'the future classroom dictation is listed')
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0))
        self.assertEqual(self.model.call_count, 1)
        self.assertEqual(self._check_school(self._list()[0], refs), listed)

    def _old_saved(self, reply, guards=OLD_GUARDS):
        """An earlier release's saved whole day: the real run_once saves the reply with only the named sibling guards as
        identities, as a release before them did, plus the oral addition; then the real guards are back for every read."""
        with contextlib.ExitStack() as stack:
            for name in guards: stack.enter_context(mock.patch.object(agent, name, lambda quote, text, value, others: value))
            return self._actual(reply)

    def _rows(self):
        with self.app.connect() as c:
            names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {n: [tuple(r) for r in c.execute('SELECT * FROM "%s" ORDER BY rowid' % n)] for n in names}

    def _read_old_saved(self, reply, guards, saved=None):
        """Only reading an earlier release's list: the dictation saved with its sibling's range shows its own words, the
        seven tasks, days, originals and ids are the frozen ones, and no row, receipt or original changes; no model call."""
        payload, refs = self._old_saved(reply, guards)
        with self.app.connect() as c:
            row, = [r for r in c.execute("SELECT * FROM agent_items WHERE kind='school'") if json.loads(r['plan']).get('school_date_quote') == '明天英语课听写']
            sibling, = [r for r in c.execute("SELECT * FROM agent_items WHERE kind='school'") if json.loads(r['plan']).get('school_date_quote') == '今晚听音频跟读Unit 7第3至10个单词，每词3遍，不用抄写']
            task = c.execute('SELECT title, action FROM manual_tasks WHERE id=?', (row['task_id'],)).fetchone()
            receipts = {r['id']: json.loads(r['plan']).get('school_selection_receipt') for r in c.execute("SELECT id, plan FROM agent_items")}
            ids = {r[0] for r in c.execute('SELECT id FROM manual_tasks')}
        self.assertEqual((row['state'], tuple(task)), ('accepted', (row['title'], row['body'])), 'the saved task is the item\'s own words')
        if saved: self.assertEqual((row['title'], row['body']), saved, 'the earlier release saved these borrowed words')
        self.assertIn('Unit 7', row['title'] + row['body'], 'the saved words borrow the sibling range')
        rows, calls = self._rows(), self.model.call_count
        mine, visible = self._list()
        self.assertEqual(len(mine), 7, [i['title'] for i in mine])
        self.assertEqual({i['id'] for i in mine}, ids, 'the same saved task ids')
        listed = self._check_school(mine, refs)
        dictation, = [i for i in mine if i['id'] == row['task_id']]
        self.assertEqual((dictation['title'], dictation['body']), ('英语：明天英语课听写', '明天英语课进行听写。'), 'shown by its own words')
        self.assertIn(dictation['title'], visible, 'listed on its own day')
        shown, = [t for t in self.app.tasks() if t['id'] == row['task_id']]
        self.assertEqual((shown['title'], shown['action']), (dictation['title'], dictation['body']), 'the task reader shows the same')
        read, = [i for i in mine if i['id'] == sibling['task_id']]
        self.assertEqual((read['title'], read['body']), (sibling['title'], '今晚听音频跟读Unit 7第3至10个单词。\n每词3遍。\n不用抄写。'), 'the sibling keeps its own words and range')
        self.assertIn('Unit 7第3', read['title'], 'its own range stays in its own title')
        self.assertEqual(self._check_school(self._list()[0], refs), listed, 'a reopen reads the same')
        self.assertEqual(self._rows(), rows, 'reading changed no saved row')
        self.assertEqual(self.model.call_count, calls, 'reading called no model')
        with self.app.connect() as c:
            self.assertEqual({r['id']: json.loads(r['plan']).get('school_selection_receipt') for r in c.execute("SELECT id, plan FROM agent_items")}, receipts)
        return row

    def test_an_old_saved_summary_borrowing_its_siblings_range_reads_its_own_words(self):
        self._read_old_saved(ACTUAL_REPLY, OLD_GUARDS, OLD_SAVED)

    def test_an_old_saved_title_borrowing_its_siblings_range_reads_its_own_words(self):
        self._read_old_saved(ACTUAL_TITLE_REPLY, OLD_GUARDS[:1], OLD_TITLE_SAVED)

    def test_an_old_saved_title_and_summary_both_borrowing_read_their_own_words(self):
        self._read_old_saved(ACTUAL_TITLE_REPLY, OLD_GUARDS)

    def test_a_parents_own_title_and_goal_on_an_old_saved_task_stay_the_parents(self):
        import family_task_focus
        row = self._read_old_saved(ACTUAL_TITLE_REPLY, OLD_GUARDS)
        mine = '英语：Unit 7单词听写（家长改）', '家长更正：明天听写Unit 7第3至10个单词。'
        family_task_focus.save(self.app, dict(id=row['task_id'], request_key='parent-own-fix-0001', version=0, mode='next', next_action='',
                                              waiting_for='', review_on='', title=mine[0], goal=mine[1]))
        shown, = [t for t in self.app.tasks() if t['id'] == row['task_id']]
        self.assertEqual((shown['title'], shown['action']), mine, 'a parent\'s own words are never read again')
        item, = [i for i in self._list()[0] if i['id'] == row['task_id']]
        self.assertEqual((item['title'], item['body']), mine)
        with self.app.connect() as c:
            self.assertEqual(tuple(c.execute('SELECT title, action FROM manual_tasks WHERE id=?', (row['task_id'],)).fetchone()), (row['title'], row['body']))
        self.assertEqual(self.model.call_count, 1)

    def test_an_old_saved_task_whose_original_changed_keeps_its_saved_words(self):
        row = self._read_old_saved(ACTUAL_TITLE_REPLY, OLD_GUARDS)
        key = json.loads(row['evidence'])[0]['ref'][len('message:'):].rsplit(':', 1)
        with self.app.connect() as c:
            payload = c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?', key).fetchone()[0]
        original = json.loads(payload)
        for change in (dict(text=original['text'] + '（虚构补充）'), dict(time='2026-11-04T16:03:00+08:00'),
                       dict(sender_id='fictional-other'), dict(kind='image'), dict(unread=True)):
            with self.app.connect() as c:
                c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?', (json.dumps(dict(original, **change), ensure_ascii=False), *key))
                c.commit()
            shown, = [t for t in self.app.tasks() if t['id'] == row['task_id']]
            self.assertEqual((shown['title'], shown['action']), (row['title'], row['body']), 'a changed original proves no old basis: %s' % change)
        with self.app.connect() as c:
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?', (payload, *key))
            c.commit()
        shown, = [t for t in self.app.tasks() if t['id'] == row['task_id']]
        self.assertEqual((shown['title'], shown['action']), ('英语：明天英语课听写', '明天英语课进行听写。'), 'the unchanged original reads again')
        with self.app.connect() as c:
            self.assertEqual(tuple(c.execute('SELECT title, action FROM manual_tasks WHERE id=?', (row['task_id'],)).fetchone()), (row['title'], row['body']))
        self.assertEqual(self.model.call_count, 1)

    def test_a_title_naming_a_sibling_scope_becomes_the_teachers_own_heading(self):
        text, own = MESSAGES[2][3], '明天英语课听写'
        sibling = '今晚听音频跟读Unit 7第3至10个单词，每词3遍，不用抄写'
        title = agent._school_sibling_free_title(own, text, '英语：Unit 7单词听写（明天）', [sibling])
        self.assertIn('英语课听写', title)
        for word in ('Unit', '单词', '（明天）'): self.assertNotIn(word, title)
        for kept in ('英语：明天英语课听写', '英语：课堂听写'):  # nothing borrowed: the returned title stays
            self.assertEqual(agent._school_sibling_free_title(own, text, kept, [sibling]), kept)
        self.assertEqual(agent._school_sibling_free_title(sibling, text, '英语：跟读Unit 7第3–10个单词', [own]), '英语：跟读Unit 7第3–10个单词')
        back = '英语：今晚跟读Unit 7第3至10个单词；明天听写上述同一组单词。'
        self.assertEqual(agent._school_sibling_free_title('明天听写上述同一组单词', back, '英语：听写Unit 7单词', ['今晚跟读Unit 7第3至10个单词']),
                         '英语：听写Unit 7单词', 'a quote pointing back shares the scope')
        long = '明天英语课先默写课文第一段再完成课堂听写练习并当堂交给老师批改和订正，不用在家准备'
        title = agent._school_sibling_free_title(long, '英语：今晚跟读Unit 7第3至10个单词；' + long + '。', '英语：Unit 7单词听写', ['今晚跟读Unit 7第3至10个单词'])
        self.assertTrue(title.endswith('…') and len(title) <= 31 and 'Unit' not in title, title)

    def test_a_sibling_scope_stays_only_where_the_teacher_points_back_to_it(self):
        text = '英语：今晚跟读Unit 7第3至10个单词；明天听写上述同一组单词。'
        own, sibling = '明天听写上述同一组单词', '今晚跟读Unit 7第3至10个单词'
        self.assertEqual(agent._school_sibling_free_goal(own, text, '明天听写Unit 7第3至10个单词。', [sibling]), '明天听写Unit 7第3至10个单词。')
        plain = text.replace('上述同一组', '')
        self.assertEqual(agent._school_sibling_free_goal('明天听写单词', plain, '明天听写今晚跟读的Unit 7第3至10个单词。', [sibling]), '明天听写单词。')
        self.assertEqual(agent._school_sibling_free_goal('明天听写单词', plain, '明天课堂听写单词。\n范围是今晚跟读的单词。', [sibling]), '明天课堂听写单词。')
        self.assertEqual(agent._school_sibling_free_goal(sibling, plain, '今晚跟读Unit 7第3至10个单词。', ['明天听写单词']), '今晚跟读Unit 7第3至10个单词。')

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


def serve_actual(port, guards=()):
    """Browser fixture for test_daily_list_actual_scope_ui.cjs: Root's second actual reply saved by the real run_once into a
    disposable fictional Store, plus the child's oral addition, served as of the frozen 2026-11-04 evening. No model is
    configured or called; no household path, collector, print or device is used."""
    case = WholeDayTests('test_root_actual_title_reply_keeps_title_and_summary_to_their_own_words')
    case.setUp()
    try:
        case._old_saved(ACTUAL_TITLE_REPLY, guards)  # no guards: today's saving; OLD_GUARDS: an earlier release's saved list
        frozen.serve_store(case, port, 'Actual whole day served')
    finally:
        case.doCleanups()


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['--serve-actual']:
        serve_actual(int(sys.argv[2]))
    elif sys.argv[1:2] == ['--serve-actual-saved']:
        serve_actual(int(sys.argv[2]), OLD_GUARDS)
    else:
        unittest.main()
