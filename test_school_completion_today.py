"""Own-original completion day for the known fictional six school messages; no real model, collectors or devices.

The saved parsed reply is the earlier fictional replay receipt, used only as a fixed local seam. Today must list the work
the item's own words give to its sending day (今天/今晚) on that day, while the same task keeps its handback due.
"""
import copy
import datetime as dt
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import family_agenda
import family_agent as agent
import family_study
import family_task_focus
import test_school_native_coverage as native


# The fictional unseen mixed day (HANDOFF unseen-mixed-school-day-20261019-v1): its 7 originals and the actual Flash27
# reply, both unchanged; the reply cites the originals by their own source and message IDs.
FLASH27_SOURCE = 'synthetic-unseen-daygroup-20261019'
FLASH27_MESSAGES = json.loads('[{"id": "31", "kind": "text", "message_order": "31", "sender": "虚构语文许老师", "sender_id": "synthetic-unseen-cn-xu", "text": "今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。今晚完成，明天早上交。", "time": "2026-10-19T16:08:00+08:00", "unread": false}, {"id": "32", "kind": "text", "message_order": "32", "sender": "虚构数学魏老师", "sender_id": "synthetic-unseen-math-wei", "text": "数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。", "time": "2026-10-19T16:12:00+08:00", "unread": false}, {"id": "33", "kind": "text", "message_order": "33", "sender": "虚构数学魏老师", "sender_id": "synthetic-unseen-math-wei", "text": "补充一下，第34页第4题要把计算过程写完整，写在原题下面即可。", "time": "2026-10-19T16:13:00+08:00", "unread": false}, {"id": "34", "kind": "text", "message_order": "34", "sender": "虚构英语乔老师", "sender_id": "synthetic-unseen-en-qiao", "text": "英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。", "time": "2026-10-19T16:22:00+08:00", "unread": false}, {"id": "35", "kind": "text", "message_order": "35", "sender": "虚构班主任温老师", "sender_id": "synthetic-unseen-head-wen", "text": "《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。另外，明天来校带一个空透明塑料瓶，科学课用。", "time": "2026-10-19T17:10:00+08:00", "unread": false}, {"id": "36", "kind": "text", "message_order": "36", "sender": "虚构科学唐老师", "sender_id": "synthetic-unseen-science-tang", "text": "今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。", "time": "2026-10-19T17:35:00+08:00", "unread": false}, {"id": "37", "kind": "text", "message_order": "37", "sender": "虚构予澄家长", "sender_id": "synthetic-unseen-parent-yucheng", "text": "收到，谢谢老师。", "time": "2026-10-19T17:42:00+08:00", "unread": false}]')
FLASH27_REPLY = json.loads('{"proposals": [{"title_quote": "今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。", "focus": "school", "due": "2026-10-20", "evidence": [{"ref": "message:synthetic-unseen-daygroup-20261019:31"}], "task_title": "语文：完成《星芽阅读练习册》第28页第1、2题", "task_goal": "完成《星芽阅读练习册》第28页第1、2题。\\n答案写在练习册上。\\n今晚完成，明天早上交。", "task_advice": "可先读题再作答，完成后自查是否两题都已写在练习册上。", "learning_subject": "语文", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求完成练习册第28页第1、2题，答案写在练习册上，今晚完成、明天早上交。", "task_purpose": "learning", "task_submission": "明天早上交练习册。"}, {"title_quote": "数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。", "focus": "school", "due": "2026-10-20", "evidence": [{"ref": "message:synthetic-unseen-daygroup-20261019:32"}, {"ref": "message:synthetic-unseen-daygroup-20261019:33"}], "task_title": "数学：完成《数格练习册》第34页第1—4题", "task_goal": "完成《数格练习册》第34页第1—4题。\\n第34页第4题要把计算过程写完整，写在原题下面即可。\\n今晚完成，明天早上交。", "task_advice": "可先完成第1—3题，再重点检查第4题计算过程是否写完整。", "learning_subject": "数学", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求完成练习册第34页第1—4题，并补充第4题写完整计算过程，今晚完成、明天早上交。", "task_purpose": "learning", "task_submission": "明天早上交练习册。"}, {"title_quote": "英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。", "focus": "school", "due": "2026-10-20", "evidence": [{"ref": "message:synthetic-unseen-daygroup-20261019:34"}], "task_title": "英语：跟读Unit 4两遍并家长签字", "task_goal": "听录音跟读 Unit 4 A day at the lake 两遍。\\n读完请家长在记录本上签字。\\n今晚完成，明天早读检查记录本。", "task_advice": "可跟读时注意模仿录音语音语调，读完后请家长及时签字。", "learning_subject": "英语", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求听录音跟读Unit 4两遍，家长在记录本上签字，今晚完成、明天早读检查记录本。", "task_purpose": "learning", "task_submission": "明天早读检查记录本。"}, {"title_quote": "《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。", "focus": "school", "due": "2026-10-20", "evidence": [{"ref": "message:synthetic-unseen-daygroup-20261019:35"}], "task_title": "交《秋季校园开放日回执》", "task_goal": "《秋季校园开放日回执》今晚请家长签字。\\n明天早上让孩子交给班主任。", "task_advice": "可今晚请家长签字后，明早提醒孩子带回学校交给班主任。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求家长今晚签字，明天早上让孩子把回执交给班主任。", "task_purpose": "admin", "task_submission": "明天早上交给班主任。"}, {"title_quote": "明天来校带一个空透明塑料瓶，科学课用。", "focus": "school", "due": "2026-10-20", "evidence": [{"ref": "message:synthetic-unseen-daygroup-20261019:35"}], "task_title": "科学：带一个空透明塑料瓶", "task_goal": "明天来校带一个空透明塑料瓶，科学课用。", "task_advice": "可今晚把空透明塑料瓶放进书包，避免明早遗忘。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "已读文字明确要求明天来校带一个空透明塑料瓶，科学课用。", "task_purpose": "admin", "task_submission": ""}, {"title_quote": "今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。", "focus": "school", "due": "", "evidence": [{"ref": "message:synthetic-unseen-daygroup-20261019:36"}], "task_title": "", "task_goal": "", "task_advice": "", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "reference", "task_reason": "该消息仅为本周课程进度说明，供家长了解，没有新增行动要求。", "task_purpose": "optional", "task_submission": ""}]}')

MESSAGES = [  # (time, publisher, sender, text, related)
    ('2026-10-07T19:00:00+08:00', 'synthetic-chinese', '示例语文老师',
     '今天语文作业：1. 背诵《秋夜》第2自然段，明天早读抽查；2. 完成练习册第12页第1-5题，本周五交。', (6,)),
    ('2026-10-07T19:05:00+08:00', 'synthetic-math', '示例数学老师', '数学：口算本第8页全部完成，明天交给课代表。', ()),
    ('2026-10-07T19:10:00+08:00', 'synthetic-head', '示例班主任',
     '各位家长：请打印《秋游安全告知书》，家长签字后于10月10日前交回班主任，不需要盖章。另外周四学校体检，请孩子穿运动服。', ()),
    ('2026-10-07T19:15:00+08:00', 'synthetic-english', '示例英语老师', '英语：今晚把Unit 3单词每个抄写两遍，明天交；周五听写Unit 3单词。', ()),
    ('2026-10-07T19:20:00+08:00', 'synthetic-parent', '示例家长甲', '请问练习册第5题必须做吗？', ()),
    ('2026-10-07T19:25:00+08:00', 'synthetic-chinese', '示例语文老师', '补充：练习册第5题不用做，只做第1-4题。', (1,)),
]

# (title_quote, due, refs, title, goal, subject, state, purpose, submission) as the fictional receipt returned them.
REPLY = [
    ('背诵《秋夜》第2自然段，明天早读抽查', '', [1], '语文：背诵《秋夜》第2自然段', '背诵《秋夜》第2自然段。\n明天早读接受抽查。', '语文', 'ready', 'learning', ''),
    ('完成练习册第12页第1-5题，本周五交', '2026-10-09', [1, 6], '语文：完成练习册第12页第1-4题', '完成练习册第12页第1-4题。\n第5题不用做。\n本周五交。',
     '语文', 'ready', 'learning', '本周五交'),
    ('口算本第8页全部完成，明天交给课代表', '2026-10-08', [2], '数学：完成口算本第8页', '口算本第8页全部完成。\n明天交给课代表。', '数学', 'ready', 'learning',
     '明天交给课代表'),
    ('请打印《秋游安全告知书》，家长签字后于10月10日前交回班主任，不需要盖章', '2026-10-10', [3], '打印《秋游安全告知书》并签字交回',
     '打印《秋游安全告知书》。\n家长签字后于10月10日前交回班主任。\n不需要盖章。', '', 'ready', 'admin', '10月10日前交回班主任'),
    ('周四学校体检，请孩子穿运动服', '2026-10-08', [3], '周四体检：穿运动服', '周四学校体检，孩子穿运动服。', '', 'ready', 'admin', ''),
    ('今晚把Unit 3单词每个抄写两遍，明天交', '2026-10-08', [4], '英语：抄写Unit 3单词两遍', '今晚把Unit 3单词每个抄写两遍。\n明天交。', '英语', 'ready', 'learning',
     '明天交'),
    ('周五听写Unit 3单词', '2026-10-09', [4], '英语：Unit 3单词听写（周五）', '周五听写Unit 3单词。', '英语', 'ready', 'learning', ''),
    ('请问练习册第5题必须做吗？', '', [5], '', '', '', 'reference', 'optional', ''),
]


class OwnCompletionDayTests(unittest.TestCase):
    def test_only_own_today_words_on_their_own_sending_day_give_a_completion_day(self):
        sent = '2026-10-07T19:00:00+08:00'
        cases = [
            ('今晚把Unit 3单词每个抄写两遍，明天交', '英语', sent, '2026-10-08', '2026-10-07'),
            ('背诵《秋夜》第2自然段，明天早读抽查', '今天语文作业', sent, '2026-10-08', '2026-10-07'),
            # A teacher's later handback correction keeps the original completion day of the same outcome.
            ('背诵《秋夜》第2自然段，明天早读抽查', '今天语文作业', sent, '2026-10-09', '2026-10-07'),
            # Only a handback day, a heading item with its own later deadline, or a day inside a title stays unknown.
            ('口算本第8页全部完成，明天交给课代表', '数学', sent, '2026-10-08', ''),
            ('完成练习册第12页第1-5题，本周五交', '今天语文作业', sent, '2026-10-09', ''),
            ('背诵《今天的秋夜》第2自然段，明天早读抽查', '语文作业', sent, '2026-10-08', ''),
            ('周五听写Unit 3单词', '英语', sent, '2026-10-09', ''),
            # No written offset or no parseable sending time proves no day.
            ('今晚把Unit 3单词每个抄写两遍，明天交', '英语', '2026-10-07T19:15:00', '2026-10-08', ''),
            ('今晚把Unit 3单词每个抄写两遍，明天交', '英语', '', '2026-10-08', ''),
            # The own sending day is read in its own written timezone, not the family's or the UI's date.
            ('今晚把Unit 3单词每个抄写两遍，明天交', '英语', '2026-10-07T23:30:00-05:00', '2026-10-09', '2026-10-07'),
            # A handback that is not later than the work day keeps the one existing due role.
            ('今晚把Unit 3单词每个抄写两遍，今晚交', '英语', sent, '2026-10-07', ''),
            ('今晚把Unit 3单词每个抄写两遍，周三前交', '英语', sent, '2026-10-06', ''),
        ]
        for quote, header, time, due, expected in cases:
            with self.subTest(quote=quote, header=header, time=time, due=due):
                self.assertEqual(family_agenda.completion_day(quote, header, time, due), expected)

    def test_completion_day_is_visible_on_its_day_and_handback_due_keeps_its_own(self):
        item = dict(closed=False, agenda=dict(published_on='2026-10-07', due_on='2026-10-08', scheduled_on='',
                                              complete_on='2026-10-07'))
        self.assertEqual([d for d in ('2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09') if family_agenda.visible_on(item, d)],
                         ['2026-10-07', '2026-10-08', '2026-10-09'])
        closed = dict(item, closed=True, closed_on='2026-10-08')
        self.assertEqual([d for d in ('2026-10-07', '2026-10-08', '2026-10-09') if family_agenda.visible_on(closed, d)],
                         ['2026-10-07', '2026-10-08'])


class KnownOriginalSixTodayTests(unittest.TestCase):
    setUp = native.SchoolNativeCoverageTests.setUp

    def _run(self):
        self.now = self.fixture.now = dt.datetime(2026, 10, 7, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor=str(10 + len(MESSAGES)))
        payload['messages'] = [dict(id=str(11 + n), message_order=str(11 + n), time=time, kind='text', sender=sender,
                                    sender_id=publisher, text=text, unread=False)
                               for n, (time, publisher, sender, text, _) in enumerate(MESSAGES)]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]
        reply = dict(proposals=[dict(title_quote=quote, focus='school', due=due, evidence=[dict(ref=refs[r - 1]) for r in cited],
                                     task_title=title, task_goal=goal, task_advice='', learning_subject=subject, learning_goal_id='',
                                     task_change='new', task_target_id='', task_state=state, task_reason='原文明确。',
                                     task_purpose=purpose, task_submission=submission)
                                for quote, due, cited, title, goal, subject, state, purpose, submission in REPLY])
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        return payload, agent.run_once(self.app, self.now)

    def _tasks(self):
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")]
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
        return rows, tasks

    def test_today_and_tonight_work_is_listed_on_the_sending_day_and_kept_on_its_handback_day(self):
        payload, result = self._run()
        self.assertEqual(result['failed'], 0, result)
        self.assertEqual(self.model.call_count, 1)
        rows, tasks = self._tasks()
        accepted = [r for r in rows if r['state'] == 'accepted']
        self.assertEqual(set(tasks), {r['task_id'] for r in accepted}, 'every saved item is one stored task row')
        named = {key: [t for t in tasks.values() if key in t['title']] for key in ('背诵', '抄写', '口算', '练习册', '听写')}
        for key, found in named.items():
            self.assertEqual(len(found), 1, (key, [t['title'] for t in tasks.values()]))
        ids = {key: found[0]['id'] for key, found in named.items()}

        def listed(day):
            calendar = self.app.calendar_snapshot(day, day)
            return calendar, {x['task_id']: x for x in calendar['inbox'] if x['task_id'] and self.source['child_id'] in x['child_ids']}

        calendar, inbox = listed('2026-10-07')
        expected = {'背诵': ('2026-10-07', '2026-10-08'), '抄写': ('2026-10-07', '2026-10-08'), '口算': ('', '2026-10-08'),
                    '练习册': ('', '2026-10-09'), '听写': ('', '2026-10-09')}
        for key, (complete, due) in expected.items():
            with self.subTest(item=key):
                agenda = inbox[ids[key]]['agenda']
                self.assertEqual((agenda['complete_on'], agenda['due_on'], agenda['category']), (complete, due, 'homework'))
                self.assertEqual(agenda['published_on'], '2026-10-07')
        for day in ('2026-10-07', '2026-10-08'):
            listed_ids = [x['task_id'] for x in self.app.calendar_snapshot(day, day)['agenda'] if x['task_id']]
            for key in ('背诵', '抄写'):
                self.assertEqual(listed_ids.count(ids[key]), 1, (day, key, 'one ID counted once that day'))
        # The handback stays on the same task: no second task, the original message and due are unchanged.
        self.assertEqual([tasks[ids[k]]['due'] for k in ('背诵', '抄写')], ['2026-10-08', '2026-10-08'])
        with self.store._db() as c:
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')], payload['messages'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)

        # Reopening and a repeated intake keep the same IDs and roles without a copy.
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((replay['failed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)
        rows_again, tasks_again = self._tasks()
        self.assertEqual(set(tasks_again), set(tasks))
        _, reopened = listed('2026-10-07')
        self.assertEqual({k: reopened[ids[k]]['agenda']['complete_on'] for k in ('背诵', '抄写', '口算')},
                         {'背诵': '2026-10-07', '抄写': '2026-10-07', '口算': ''})


H01 = ('2026-10-16T18:00:00+08:00', 'publisher:fictional-today-h01:teacher', '虚构学校教师',
       '语文：2026年10月18日20:00前完成《秋日观察》第2页，摘录两句，每句写一句理由；2026年10月20日早读交回语文老师。')
H01_BODY = '2026年10月18日20:00前完成《秋日观察》第2页，摘录两句，每句写一句理由；2026年10月20日早读交回语文老师'


class ExplicitOwnCompletionDayTests(unittest.TestCase):
    def test_the_own_work_clause_explicit_day_is_its_completion_day_and_opposites_stay_unknown(self):
        sent = H01[0]
        cases = [
            (H01[3], '语文', sent, '2026-10-20', '2026-10-18'),
            (H01_BODY, '语文', sent, '2026-10-20', '2026-10-18'),
            (H01_BODY, '', sent, '2026-10-20', '2026-10-18'),
            # A same-item handback correction keeps the work's own day; a weekday is read on its own sending day.
            (H01_BODY, '语文', sent, '2026-10-21', '2026-10-18'),
            ('周日前完成《秋日观察》第2页，下周二早读交回', '语文', sent, '2026-10-20', '2026-10-18'),
            # Only a handback day, a title's day, a handback/second day or negation in the work clause stays unknown.
            ('语文：完成《秋日观察》第2页，摘录两句；2026年10月20日早读交回语文老师。', '语文', sent, '2026-10-20', ''),
            ('语文：完成《2026年10月18日秋日观察》第2页，摘录两句；2026年10月20日早读交回语文老师。', '语文', sent, '2026-10-20', ''),
            ('2026年10月20日早读交回语文老师', '语文', sent, '2026-10-20', ''),
            ('语文：2026年10月18日前交回已写好的《秋日观察》第2页。', '语文', sent, '2026-10-18', ''),
            ('语文：2026年10月18日或19日完成《秋日观察》第2页；2026年10月20日早读交回。', '语文', sent, '2026-10-20', ''),
            ('语文：2026年10月18日不用完成《秋日观察》第2页；2026年10月20日早读交回。', '语文', sent, '2026-10-20', ''),
            # A work day not before the handback keeps the one due role; no offset proves no day.
            ('语文：2026年10月20日前完成《秋日观察》第2页；2026年10月20日早读交回。', '语文', sent, '2026-10-20', ''),
            (H01_BODY, '语文', '2026-10-16T18:00:00', '2026-10-20', ''),
        ]
        for quote, header, time, due, expected in cases:
            with self.subTest(quote=quote, header=header, time=time, due=due):
                self.assertEqual(family_agenda.completion_day(quote, header, time, due), expected)


class ExplicitOwnCompletionDayStoreTests(unittest.TestCase):
    setUp = native.SchoolNativeCoverageTests.setUp

    def _save_h01(self):
        self.now = self.fixture.now = dt.datetime(2026, 10, 16, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        time, publisher, sender, text = H01
        payload['messages'] = [dict(id='11', message_order='11', time=time, kind='text', sender=sender, sender_id=publisher,
                                    text=text, unread=False)]
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':11'
        reply = dict(proposals=[dict(title_quote=H01_BODY, focus='school', due='2026-10-20', evidence=[dict(ref=ref)],
                                     task_title='语文：完成《秋日观察》第2页摘录', task_goal='完成《秋日观察》第2页，摘录两句，每句写一句理由。\n2026年10月20日早读交回语文老师。',
                                     task_advice='', learning_subject='语文', learning_goal_id='', task_change='new', task_target_id='',
                                     task_state='ready', task_reason='原文明确。', task_purpose='learning',
                                     task_submission='2026年10月20日早读交回语文老师')])
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        result = agent.run_once(self.app, self.now)
        self.assertEqual(result['failed'], 0, result)
        with self.store._db() as c:
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
        self.assertEqual(len(tasks), 1, tasks)
        return payload, tasks[0]

    def test_saved_h01_is_one_task_on_its_work_day_and_its_handback_day_after_reopen_and_replay(self):
        payload, task = self._save_h01()
        self.assertEqual(task['due'], '2026-10-20')

        def listed(day):
            return [x for x in self.app.calendar_snapshot(day, day)['agenda'] if x['task_id'] == task['id']]

        for day, expected in (('2026-10-16', 1), ('2026-10-17', 1), ('2026-10-18', 1), ('2026-10-20', 1)):
            found = listed(day)
            self.assertEqual(len(found), expected, (day, 'one ID counted once that day'))
            self.assertEqual((found[0]['agenda']['complete_on'], found[0]['agenda']['due_on']), ('2026-10-18', '2026-10-20'))
        with self.app.connect() as c:
            saved = [t for t in self.app.tasks(c) if t['id'] == task['id']]
        self.assertEqual([(t['due'], t['agenda']['complete_on']) for t in saved], [('2026-10-20', '2026-10-18')])
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((replay['failed'], replay['created']), (0, 0))
        with self.store._db() as c:
            self.assertEqual([r['id'] for r in c.execute('SELECT id FROM manual_tasks')], [task['id']])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')], payload['messages'])
        reopened = agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        self.assertIsNotNone(reopened)
        self.assertEqual([x['agenda']['complete_on'] for x in listed('2026-10-18')], ['2026-10-18'])


H02 = ('2026-10-17T16:30:00Z', 'publisher:fictional-today-h02:teacher', '虚构英语教师',
       '英语：今晚把Unit 5词表每个单词抄写两遍，明天交给英语老师。')
H02_STANDARDS = ('Unit 5词表', '每个单词', '两遍', '交给英语老师')


class LabelledOwnTonightTests(unittest.TestCase):
    def test_own_tonight_after_its_own_subject_label_is_its_completion_day_with_or_without_a_saved_heading(self):
        sent = '2026-10-18T00:30:00+08:00'
        cases = [
            (H02[3], '', sent, '2026-10-19', '2026-10-18'),
            (H02[3], '英语', sent, '2026-10-19', '2026-10-18'),
            ('今晚把Unit 5词表每个单词抄写两遍，明天交给英语老师。', '', sent, '2026-10-19', '2026-10-18'),
            # Only a handback day, a day inside a title, a negated clause, a handback not after the work, or no offset stays unknown.
            ('英语：把Unit 5词表每个单词抄写两遍，明天交给英语老师。', '', sent, '2026-10-19', ''),
            ('英语：《今晚》词表每个单词抄写两遍，明天交给英语老师。', '', sent, '2026-10-19', ''),
            ('英语：今晚不用抄写Unit 5词表，明天交给英语老师。', '', sent, '2026-10-19', ''),
            ('英语：今晚把Unit 5词表每个单词抄写两遍，今晚交给英语老师。', '', sent, '2026-10-18', ''),
            (H02[3], '', '2026-10-18T00:30:00', '2026-10-19', ''),
        ]
        for quote, header, time, due, expected in cases:
            with self.subTest(quote=quote, header=header, time=time, due=due):
                self.assertEqual(family_agenda.completion_day(quote, header, time, due), expected)


class LabelledOwnTonightStoreTests(unittest.TestCase):
    setUp = native.SchoolNativeCoverageTests.setUp

    def _save_h02(self, text, title):
        self.now = self.fixture.now = dt.datetime(2026, 10, 18, 0, 31, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='11')
        time, publisher, sender, _ = H02
        payload['messages'] = [dict(id='11', message_order='11', time=time, kind='text', sender=sender, sender_id=publisher,
                                    text=text, unread=False)]
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':11'
        reply = dict(proposals=[dict(title_quote=text, focus='school', due='2026-10-19', evidence=[dict(ref=ref)],
                                     task_title=title, task_goal=text, task_advice='', learning_subject='英语', learning_goal_id='',
                                     task_change='new', task_target_id='', task_state='ready', task_reason='原文明确。',
                                     task_purpose='learning', task_submission='')])
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        result = agent.run_once(self.app, self.now)
        self.assertEqual(result['failed'], 0, result)
        with self.store._db() as c:
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
            plans = [json.loads(r['plan']) for r in c.execute("SELECT plan FROM agent_items WHERE kind='school' AND state='accepted'")]
        self.assertEqual((len(tasks), len(plans)), (1, 1), tasks)
        # The disclosed shape: the saved own words keep their subject label and no native heading was saved with them.
        self.assertEqual((plans[0].get('school_date_quote'), plans[0].get('school_native_action')), (text, None))
        return payload, tasks[0]

    def _roles(self, task, day):
        return [(x['agenda']['complete_on'], x['agenda']['due_on'])
                for x in self.app.calendar_snapshot(day, day)['agenda'] if x['task_id'] == task['id']]

    def test_saved_h02_is_one_task_on_its_own_local_tonight_and_its_handback_day_after_replay_and_reopen(self):
        payload, task = self._save_h02(H02[3], '英语：Unit 5词表每词抄写两遍')
        self.assertEqual((task['due'], task['title']), ('2026-10-19', '英语：Unit 5词表每词抄写两遍'))
        self.assertTrue(all(s in task['action'] for s in H02_STANDARDS), task['action'])
        # The UTC sending date (17) is not its tonight; the local sending day 18 is its work day and 19 its handback.
        self.assertEqual(self._roles(task, '2026-10-17'), [])
        for day in ('2026-10-18', '2026-10-19'):
            self.assertEqual(self._roles(task, day), [('2026-10-18', '2026-10-19')], (day, 'one ID counted once with its own roles'))
        with self.app.connect() as c:
            saved = [(t['due'], t['agenda']['complete_on'], t['agenda']['due_on']) for t in self.app.tasks(c) if t['id'] == task['id']]
        self.assertEqual(saved, [('2026-10-19', '2026-10-18', '2026-10-19')])
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((replay['failed'], replay['created'], self.model.call_count), (0, 0, 1))
        with self.store._db() as c:
            self.assertEqual([r['id'] for r in c.execute('SELECT id FROM manual_tasks')], [task['id']])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            # The original words stay as sent; ingest keeps the same sending instant in the family's own offset.
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')],
                             [dict(m, time='2026-10-18T00:30:00+08:00') for m in payload['messages']])
        reopened = agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        self.assertIsNotNone(reopened)
        with self.app.connect() as c:
            again = [(t['due'], t['agenda']['complete_on']) for t in self.app.tasks(c) if t['id'] == task['id']]
        self.assertEqual(again, [('2026-10-19', '2026-10-18')])
        self.assertEqual(self._roles(task, '2026-10-18'), [('2026-10-18', '2026-10-19')])

    def test_saved_labelled_handback_only_words_keep_no_completion_day_whatever_the_title_says(self):
        payload, task = self._save_h02('英语：把Unit 5词表每个单词抄写两遍，明天交给英语老师。', '英语：今晚抄写Unit 5词表两遍')
        self.assertEqual(task['due'], '2026-10-19')
        for day in ('2026-10-18', '2026-10-19'):
            self.assertEqual(self._roles(task, day), [('', '2026-10-19')], day)


def saved_h01_state(path):
    """The app's own state and day calendars after the fictional H01 is saved by run_once, for the Chrome Today check."""
    case = ExplicitOwnCompletionDayStoreTests('test_saved_h01_is_one_task_on_its_work_day_and_its_handback_day_after_reopen_and_replay')
    case.setUp()
    try:
        case._save_h01()
        state = case.app.snapshot()
        state['saved_calendars'] = {day: case.app.calendar_snapshot(day, day) for day in ('2026-10-16', '2026-10-18', '2026-10-20')}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, default=str)
    finally:
        case.doCleanups()


T08 = ('2026-10-16T18:10:00+08:00',
       '更正：《秋日观察》第2页摘录改为2026年10月21日早读交回语文老师；摘录仍须2026年10月18日20:00前完成，摘录两句、每句写一句理由的要求不变。')
T08_GOAL = '语文：2026年10月18日20:00前完成《秋日观察》第2页，摘录两句，每句写一句理由；2026年10月21日早读交回语文老师。'
T08_STANDARDS = ('《秋日观察》第2页', '摘录两句', '每句写一句理由', '20:00前', '早读交回')
T08_DELTA = '补充：《秋日观察》第2页摘录，每句理由另起一行。'


class ConfirmedSchoolHandbackCorrectionTests(unittest.TestCase):
    """Original T08: a parent-confirmed same-task teacher handback correction is the school's change, not a parent's plan."""
    setUp = native.SchoolNativeCoverageTests.setUp
    _save_h01 = ExplicitOwnCompletionDayStoreTests._save_h01

    def _agenda(self, task_id):
        with self.app.connect() as c:
            return [(t['agenda']['complete_on'], t['agenda']['due_on']) for t in self.app.tasks(c) if t['id'] == task_id]

    def _roles(self, task_id, day):
        return [(x['agenda']['complete_on'], x['agenda']['due_on'])
                for x in self.app.calendar_snapshot(day, day)['agenda'] if x['task_id'] == task_id]

    def _confirm_t08(self):
        _, task = self._save_h01()
        payload = self.fixture.payload(expected='11', cursor='12', offset=9)
        payload['messages'] = [dict(id='12', message_order='12', time=T08[0], kind='text', sender=H01[2], sender_id=H01[1],
                                    text=T08[1], unread=False)]
        self.store.ingest(payload)
        reply = dict(proposals=[dict(title_quote=T08[1], focus='school', due='2026-10-21', evidence=[dict(ref='message:' + self.source['id'] + ':12')],
                                     learning_subject='语文', learning_goal_id='', task_title='语文：完成《秋日观察》第2页摘录', task_goal=T08_GOAL,
                                     task_advice='', task_change='update', task_target_id=task['id'], task_state='ready',
                                     task_reason='全虚构固定更正回执。', task_purpose='learning', task_submission='')])
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        result = agent.run_once(self.app, self.now + dt.timedelta(minutes=10))
        self.assertEqual(result['failed'], 0, result)
        with self.store._db() as c:
            pending = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='pending'")]
        self.assertEqual(len(pending), 1, pending)
        # The natural run only proposes the correction; the saved task keeps its original roles until a parent confirms.
        self.assertEqual(self._agenda(task['id']), [('2026-10-18', '2026-10-20')])
        request = dict(action='school_change', id=pending[0]['id'], target_id=task['id'], change='update', title='语文：完成《秋日观察》第2页摘录',
                       body=T08_GOAL, due='2026-10-21', expected_updated=pending[0]['updated'], target_version=0, target_updated='')
        first = agent.apply_school_change(self.app, self.store, copy.deepcopy(request), school_auto=False)
        again = agent.apply_school_change(self.app, self.store, copy.deepcopy(request), school_auto=False)
        self.assertEqual((first['state'], first['replayed'], again['state'], again['replayed']), ('accepted', False, 'accepted', True))
        return task

    def test_confirmed_handback_correction_keeps_the_own_completion_day_on_the_same_task_after_replay_and_reopen(self):
        task = self._confirm_t08()
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=16))
        self.assertEqual((replay['failed'], replay['created']), (0, 0))
        reopened = agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        self.assertIsNotNone(reopened)
        with self.app.connect() as c:
            saved = self.app.tasks(c)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        self.assertEqual([t['id'] for t in saved], [task['id']])
        self.assertEqual((saved[0]['agenda']['complete_on'], saved[0]['agenda']['due_on'], saved[0]['focus']['version']), ('2026-10-18', '2026-10-21', 1))
        self.assertTrue(all(s in saved[0]['action'] for s in T08_STANDARDS), saved[0]['action'])
        self.assertEqual(saved[0]['original_action'], task['action'])
        for text in (H01[3], T08[1], ':11', ':12'):
            self.assertIn(text, saved[0]['source'])
        for day in ('2026-10-18', '2026-10-21'):
            self.assertEqual(self._roles(task['id'], day), [('2026-10-18', '2026-10-21')], (day, 'one ID counted once with its own roles'))

    def test_a_later_parent_edit_after_the_confirmed_correction_still_comes_first(self):
        task = self._confirm_t08()
        with self.app.connect() as c:
            focus = next(t for t in self.app.tasks(c) if t['id'] == task['id'])['focus']
        family_task_focus.save(self.app, dict({k: focus[k] for k in ('mode', 'waiting_for', 'review_on')}, id=task['id'], version=focus['version'],
                                              request_key='parent-note-t08-0001', next_action='先读第2页'))
        self.assertEqual(self._agenda(task['id']), [('', '2026-10-21')])

    def test_a_parent_plan_under_a_school_change_shaped_key_is_still_the_parent_choice(self):
        _, task = self._save_h01()
        family_task_focus.save(self.app, dict(id=task['id'], version=0, request_key='school-change-' + agent._hash('agent-forged')[:32], mode='next',
                                              next_action='', waiting_for='', review_on='', category='homework', published_on='2026-10-16',
                                              due_on='2026-10-21'))
        self.assertEqual(self._agenda(task['id']), [('', '2026-10-21')])

    def _parent_note_after_a_duplicate_append(self, use_duplicate_key):
        original = self._confirm_t08()

        def current():
            with self.app.connect() as c:
                return copy.deepcopy(next(t for t in self.app.tasks(c) if t['id'] == original['id']))

        accepted = []
        for index in (13, 14):
            self.fixture.now = self.now + dt.timedelta(minutes=index)  # collected after T08's saved check
            row = self.fixture._school_append_candidate(index, T08_DELTA, change='append', target=original['id'], title='语文：摘录补充',
                                                        goal=T08_DELTA, publisher=H01[1])
            task = current()
            with self.app.connect() as c:
                update = c.execute('SELECT updated FROM task_updates WHERE id=?', (original['id'],)).fetchone()
            request = dict(action='school_change', id=row['id'], target_id=original['id'], change='append', title=task['title'], body=T08_DELTA,
                           due=task['agenda']['due_on'], expected_updated=row['updated'], target_version=task['focus']['version'],
                           target_updated=update['updated'] if update else '')
            with patch.object(agent, '_now', return_value=self.now):
                accepted.append((row['id'], agent.apply_school_change(self.app, self.store, request, school_auto=False)))
        self.assertEqual([reply['deduplicated'] for _, reply in accepted], [False, True])
        before = current()
        # The first append really saved the focus and keeps the own day; the accepted duplicate saved nothing, so its key is unused.
        self.assertEqual((before['focus']['version'], before['agenda']['complete_on'], before['agenda']['due_on']), (2, '2026-10-18', '2026-10-21'))
        duplicate_key = 'school-change-' + agent._hash(accepted[-1][0])[:32]
        with self.app.connect() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM task_focus_history WHERE request_key=?', (duplicate_key,)).fetchone())
        focus = before['focus']
        family_task_focus.save(self.app, dict({k: focus[k] for k in ('mode', 'waiting_for', 'review_on', 'category', 'published_on', 'due_on',
                                                                      'scheduled_on', 'box', 'title', 'goal')},
                                              id=original['id'], version=focus['version'], next_action='先核对第2页摘录的安排',
                                              request_key=duplicate_key if use_duplicate_key else 'parent-note-duplicate-control-0001'))
        after = current()
        self.assertEqual((after['focus']['next_action'], after['focus']['version']), ('先核对第2页摘录的安排', 3))
        for key in ('due_on', 'title', 'goal'):
            self.assertEqual(after['focus'][key], focus[key])
        self.assertEqual((after['source'], after['original_action'], after['action'].count(T08_DELTA)), (before['source'], original['action'], 1))
        for text in (H01[3], T08[1], ':11', ':12', ':13', ':14'):
            self.assertIn(text, after['source'])
        return after['agenda']

    def test_a_parent_note_under_an_accepted_duplicate_append_key_is_still_the_parent_choice(self):
        for use_duplicate_key in (False, True):
            with self.subTest(use_duplicate_key=use_duplicate_key):
                if use_duplicate_key:
                    self.doCleanups()
                    self.setUp()
                agenda = self._parent_note_after_a_duplicate_append(use_duplicate_key)
                self.assertEqual((agenda['complete_on'], agenda['due_on']), ('', '2026-10-21'), 'a parent next_action save is no school-change write')


class Flash27OwnRoleDaysTodayTests(unittest.TestCase):
    """The ordinary normal path for the fictional day: tonight's own work is listed on its own day, apart from its handback/check."""
    setUp = native.SchoolNativeCoverageTests.setUp

    def _listed(self, day):
        calendar = self.app.calendar_snapshot(day, day)
        return {x['task_id']: x for x in calendar['inbox'] if x['task_id'] and self.source['child_id'] in x['child_ids']}

    def test_flash27_tonight_work_is_on_its_sending_day_and_its_handback_or_check_day_stays_its_own(self):
        self.now = self.fixture.now = dt.datetime(2026, 10, 19, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='37')
        payload['messages'] = copy.deepcopy(FLASH27_MESSAGES)
        self.store.ingest(payload)
        reply = json.loads(json.dumps(FLASH27_REPLY, ensure_ascii=False).replace('message:' + FLASH27_SOURCE + ':', 'message:' + self.source['id'] + ':'))
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        first = agent.run_once(self.app, self.now)
        self.assertEqual((first['failed'], first['processed']), (0, 6), first)
        self.assertEqual(self.model.call_count, 1)
        with self.store._db() as c:
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
        named = {key: [t for t in tasks.values() if key in t['title']] for key in ('星芽', '数格', 'Unit 4', '回执', '塑料瓶')}
        for key, found in named.items():
            self.assertEqual(len(found), 1, (key, [t['title'] for t in tasks.values()]))
        ids = {key: found[0]['id'] for key, found in named.items()}
        self.assertFalse(any('水的三种状态' in t['title'] + t['action'] for t in tasks.values()), 'course progress is no task')
        # (own completion day, own handback/check day, category): tonight 19th and tomorrow 20th are each the item's own role.
        expected = {'星芽': ('2026-10-19', '2026-10-20', 'homework'), '数格': ('2026-10-19', '2026-10-20', 'homework'),
                    'Unit 4': ('2026-10-19', '2026-10-20', 'homework'), '回执': ('2026-10-19', '2026-10-20', 'todo'),
                    '塑料瓶': ('', '2026-10-20', 'todo')}

        def check(day_listed):
            for key, (complete, due, category) in expected.items():
                with self.subTest(item=key):
                    agenda = day_listed[ids[key]]['agenda']
                    self.assertEqual((agenda['complete_on'], agenda['due_on'], agenda['category']), (complete, due, category))
                    self.assertNotEqual(agenda['due_kind'], 'handback', 'a check day is not rewritten as a handback')
        check(self._listed('2026-10-19'))
        today = [x['task_id'] for x in self.app.calendar_snapshot('2026-10-19', '2026-10-19')['agenda'] if x['task_id']]
        for key in ('星芽', '数格', 'Unit 4'):
            self.assertEqual(today.count(ids[key]), 1, (key, 'tonight\'s own work is on the 19th, counted once'))
        english = tasks[ids['Unit 4']]
        self.assertIn('明天早读检查记录本', english['action'])
        self.assertNotIn('交', english['title'], 'checking the record book is not handing it in')
        bottle = tasks[ids['塑料瓶']]
        self.assertNotIn('今晚', bottle['action'], 'the bottle never borrows the receipt\'s tonight')
        self.assertEqual({t['due'] for t in tasks.values()}, {'2026-10-20'}, 'each task keeps its own handback/check due')

        # The next round reads the parent's thanks alone: no model, no task; reopening keeps the same IDs and roles.
        second = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((second['failed'], second['created']), (0, 0), second)
        self.assertEqual(self.model.call_count, 1)
        with self.store._db() as c:
            self.assertEqual({r['id'] for r in c.execute('SELECT id FROM manual_tasks')}, set(tasks))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages').fetchone()[0], 7, 'all 7 originals stay')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages WHERE processed=1').fetchone()[0], 7)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        check(self._listed('2026-10-19'))
        check(self._listed('2026-10-20'))


# What each saved Flash27 card shows under its own title: every condition once, in the saved order and words; the
# title's own first line and the program's restated 提交要求 are not repeated. Partial overlaps stay as written.
FLASH27_CARD_LINES = {
    '星芽': ['答案写在练习册上。', '今晚完成，明天早上交练习册。'],
    '数格': ['第34页第4题要把计算过程写完整，写在原题下面即可。', '今晚完成，明天早上交练习册。'],
    'Unit 4': ['听录音跟读 Unit 4 A day at the lake 两遍。', '读完请家长在记录本上签字。', '今晚完成，明天早读检查记录本。'],
    '回执': ['《秋季校园开放日回执》今晚请家长签字。', '明天早上让孩子交给班主任。'],
    '塑料瓶': ['明天来校带一个空透明塑料瓶，科学课用。'],
}


class Flash27ReadableCardTests(unittest.TestCase):
    """Display only: the saved Flash27 day reads as title, own conditions and date roles; nothing saved is rewritten."""
    setUp = native.SchoolNativeCoverageTests.setUp

    def save_flash27(self):
        self.now = self.fixture.now = dt.datetime(2026, 10, 19, 20, tzinfo=agent.TZ)
        payload = self.fixture.payload(cursor='37')
        payload['messages'] = copy.deepcopy(FLASH27_MESSAGES)
        self.store.ingest(payload)
        reply = json.loads(json.dumps(FLASH27_REPLY, ensure_ascii=False).replace('message:' + FLASH27_SOURCE + ':', 'message:' + self.source['id'] + ':'))
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed'], self.model.call_count), (0, 6, 1), result)
        with self.store._db() as c:
            saved = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
        ids = {key: next(i for i, t in saved.items() if key in t['title']) for key in FLASH27_CARD_LINES}
        return ids, saved

    def test_each_card_shows_its_own_conditions_once_and_keeps_the_saved_words(self):
        ids, saved = self.save_flash27()
        self.assertEqual(len(saved), 5)
        self.assertIn('\n提交要求：明天早上交练习册。', saved[ids['星芽']]['action'], 'the program-added line stays saved')
        tasks = {t['id']: t for t in self.app.tasks()}
        for key, lines in FLASH27_CARD_LINES.items():
            with self.subTest(item=key):
                task = tasks[ids[key]]
                self.assertEqual(task['agenda']['action_lines'], lines)
                self.assertEqual((task['title'], task['action'], task['due']), tuple(saved[ids[key]][k] for k in ('title', 'action', 'due')))
                shown = [task['title']] + lines
                self.assertEqual(len(shown), len(set(x.rstrip('。') for x in shown)), 'no condition repeated on one card')
                self.assertFalse(any(x.startswith('提交要求') for x in lines))
        # The facts the parent must still read on each card (title or its own lines), each kept whole.
        for key, facts in {'星芽': ('《星芽阅读练习册》第28页第1、2题', '答案写在练习册上', '今晚完成', '明天早上交练习册'),
                           '数格': ('《数格练习册》第34页第1—4题', '第34页第4题要把计算过程写完整，写在原题下面即可', '今晚完成', '明天早上交练习册'),
                           'Unit 4': ('听录音跟读 Unit 4 A day at the lake 两遍', '读完请家长在记录本上签字', '今晚完成，明天早读检查记录本'),
                           '回执': ('《秋季校园开放日回执》今晚请家长签字', '明天早上让孩子交给班主任'),
                           '塑料瓶': ('明天来校带一个空透明塑料瓶，科学课用',)}.items():
            card = '\n'.join([tasks[ids[key]]['title']] + tasks[ids[key]]['agenda']['action_lines'])
            for fact in facts:
                self.assertIn(fact, card, (key, fact))
        self.assertEqual(sum('第4题' in x for x in tasks[ids['数格']]['agenda']['action_lines']), 1, 'the 4th-question note stays its own line')
        self.assertNotIn('今晚', '\n'.join(tasks[ids['塑料瓶']]['agenda']['action_lines']))

    def test_the_child_card_reads_the_same_projection_from_the_same_task(self):
        ids, saved = self.save_flash27()
        study = family_study.Store(SimpleNamespace(**vars(self.app)))
        child_id = self.source['child_id']
        for key in ('星芽', 'Unit 4'):
            # The parent's existing 作业计时 entry adds the task to the day; nothing is arranged for the child automatically.
            study.save_item(dict(child_id=child_id, day='2026-10-19', request_key='flash27-readable-' + str(len(key)) + 'x' * 12,
                                 version=0, task_id=ids[key], planned_minutes=20))
        rows = {r['task_id']: r for r in study.snapshot(child_id, '2026-10-19')['items']}
        self.assertEqual(set(rows), {ids['星芽'], ids['Unit 4']}, 'only the two items the parent added')
        for key in ('星芽', 'Unit 4'):
            with self.subTest(item=key):
                row = rows[ids[key]]
                self.assertEqual(row['source_task_action'], saved[ids[key]]['action'], 'the saved words are still read as they are')
                self.assertEqual(row['source_task_action_lines'], FLASH27_CARD_LINES[key])
                self.assertEqual((row['source_task_complete_on'], row['source_task_due']), ('2026-10-19', '2026-10-20'))


def saved_flash27_state(path):
    """The app's own state and 2026-10-19 calendar after the fictional Flash27 day is saved by run_once (no model)."""
    case = Flash27ReadableCardTests('test_each_card_shows_its_own_conditions_once_and_keeps_the_saved_words')
    case.setUp()
    try:
        ids, _ = case.save_flash27()
        state = case.app.snapshot()
        state['saved_calendar'] = case.app.calendar_snapshot('2026-10-19', '2026-10-19')
        state['flash27_ids'] = ids
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, default=str)
    finally:
        case.doCleanups()


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['--saved-h01-state']:
        saved_h01_state(sys.argv[2])
    elif sys.argv[1:2] == ['--saved-flash27-state']:
        saved_flash27_state(sys.argv[2])
    else:
        unittest.main()
