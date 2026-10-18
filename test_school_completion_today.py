"""Own-original completion day for the known fictional six school messages; no real model, collectors or devices.

The saved parsed reply is the earlier fictional replay receipt, used only as a fixed local seam. Today must list the work
the item's own words give to its sending day (今天/今晚) on that day, while the same task keeps its handback due.
"""
import copy
import datetime as dt
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import family_agenda
import family_agent as agent
import family_study
import family_task_focus
import test_school_native_coverage as native
import test_school_old_pending_recovery as recovery


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

        def card_lines(task):  # as the card reads them: its own lines where it leaves words out, else the saved lines
            return task.get('action_lines', [x.strip() for x in task['action'].splitlines() if x.strip()])
        for key, lines in FLASH27_CARD_LINES.items():
            with self.subTest(item=key):
                task = tasks[ids[key]]
                self.assertEqual(card_lines(task), lines)
                # Only the two cards that leave words out carry their own lines; the others keep the exact task shape.
                self.assertEqual('action_lines' in task, key in ('星芽', '数格'))
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
            card = '\n'.join([tasks[ids[key]]['title']] + card_lines(tasks[ids[key]]))
            for fact in facts:
                self.assertIn(fact, card, (key, fact))
        self.assertEqual(sum('第4题' in x for x in card_lines(tasks[ids['数格']])), 1, 'the 4th-question note stays its own line')
        self.assertNotIn('今晚', '\n'.join(card_lines(tasks[ids['塑料瓶']])))

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


# Root's isolated actual Flash reply for the cleared English 34 gave its goal as one paragraph (fictional words). The
# ordinary run_once saved reread replays that fixed reply here through its mocked transport: no request, no hand edit.
ENGLISH_PARAGRAPH = '英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。'
ENGLISH_PARAGRAPH_LINES = ['听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。', '今晚完成，明天早读检查记录本。']


def card_lines(task):
    """As a parent card reads them: its own lines where the projection differs, else the saved lines."""
    return task.get('action_lines', [x.strip() for x in task['action'].splitlines() if x.strip()])


class RecoveredParagraphCardTests(unittest.TestCase):
    """The R09 recovered English 34, saved as one paragraph, reads as its own sentences on the parent and child cards."""
    setUp = recovery.R259ClearedDateRereadTests.setUp
    _old_store = recovery.R259ClearedDateRereadTests._old_store
    _replies = recovery.R259ClearedDateRereadTests._replies
    _at = recovery.R259ClearedDateRereadTests._at
    _listed = recovery.R259OldPendingRecoveryTests._listed

    def save_recovered(self):
        self._old_store()
        self._replies(dict(recovery.NEW_RECEIPT, goal=ENGLISH_PARAGRAPH))
        result = self._at(0)
        self.assertEqual((result['failed'], result['created'], len(self.calls)), (0, 5, 1), result)
        with self.store._db() as c:
            saved = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
        return {key: next(i for i, t in saved.items() if key in t['title']) for key in recovery.KEYS}, saved

    def test_the_recovered_paragraph_reads_as_its_own_sentences_and_stays_saved_byte_for_byte(self):
        ids, saved = self.save_recovered()
        english = saved[ids['Unit 4']]
        self.assertEqual((english['title'], english['action'], english['due']), ('英语：跟读Unit 4两遍并家长签字', ENGLISH_PARAGRAPH, '2026-10-20'))
        tasks = {t['id']: t for t in self.app.tasks()}
        task = tasks[ids['Unit 4']]
        self.assertEqual((task['title'], task['action'], task['due']), (english['title'], ENGLISH_PARAGRAPH, '2026-10-20'), 'API original fields')
        self.assertEqual(card_lines(task), ENGLISH_PARAGRAPH_LINES)
        agenda = self._listed('2026-10-19')[ids['Unit 4']]['agenda']
        self.assertEqual((agenda['complete_on'], agenda['due_on'], agenda['category']), ('2026-10-19', '2026-10-20', 'homework'))
        self.assertNotEqual(agenda['due_kind'], 'handback', 'a check day is not a handback')
        for key in ('星芽', '数格', '回执', '塑料瓶'):  # the four recovered rows read as in r261
            with self.subTest(item=key):
                self.assertEqual(card_lines(tasks[ids[key]]), FLASH27_CARD_LINES[key])
        # The child card reads the same projection from the same task, added by the parent's existing 作业计时.
        child_id = next(c['id'] for c in self.app.snapshot()['children'] if c['name'] == english['child'])
        study = family_study.Store(SimpleNamespace(**vars(self.app)))
        study.save_item(dict(child_id=child_id, day='2026-10-19', request_key='recovered-english-paragraph', version=0,
                             task_id=ids['Unit 4'], planned_minutes=20))
        row = next(r for r in study.snapshot(child_id, '2026-10-19')['items'] if r['task_id'] == ids['Unit 4'])
        self.assertEqual((row['title'], row['source_task_action']), (english['title'], ENGLISH_PARAGRAPH))
        self.assertEqual(row['source_task_action_lines'], ENGLISH_PARAGRAPH_LINES)
        with self.store._db() as c:
            self.assertEqual(dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (ids['Unit 4'],)).fetchone()), english, 'storage unchanged')


class ActionLinesTests(unittest.TestCase):
    def test_a_saved_line_reads_as_its_own_sentences_and_an_exact_heading_label_once(self):
        # Only a full-width 。！？ outside 《》, quotes and brackets ends a sentence; nothing else is cut or reworded.
        for title, action, shown in [
                ('英语：跟读Unit 4两遍并家长签字', ENGLISH_PARAGRAPH, ENGLISH_PARAGRAPH_LINES),
                ('语文：读《你好。再见！》', '读《你好。再见！》第2页。今晚完成。', ['读《你好。再见！》第2页。', '今晚完成。']),
                ('语文：摘抄', '摘抄“春天来了。花开了。”两句。明天交。', ['摘抄“春天来了。花开了。”两句。', '明天交。']),
                ('数学：练习', '完成第2.5节练习，Mr. Li will check it. 明天交。', ['完成第2.5节练习，Mr. Li will check it. 明天交。']),
                ('语文：A', '读第3课（重点段。今晚完成。', ['读第3课（重点段。今晚完成。']),
                ('语文：A', '不用抄写。口头回答后家长签字！明天检查？', ['不用抄写。', '口头回答后家长签字！', '明天检查？']),
                ('语文：A', '读B！！今晚完成', ['读B！！', '今晚完成']),
                ('英语：跟读', '英语听录音。今晚完成。', ['英语听录音。', '今晚完成。']),
                ('语文：A', '英语：读B。今晚完成。', ['英语：读B。', '今晚完成。']),
                ('英语：跟读', '英语：', ['英语：']),
                ('读三段并回答', '读三段并回答。每题写出依据。', ['每题写出依据。'])]:
            with self.subTest(title=title, action=action):
                self.assertEqual(family_agenda.action_lines(title, action), shown)
                # Every word, mark and order kept: at most a leading exact repetition of the heading is left out.
                self.assertTrue(action.replace('\n', '').endswith(''.join(shown)), shown)

    def test_only_the_title_s_own_line_and_a_restated_handback_clause_are_left_out(self):
        for title, action, shown in [
                ('读三段并回答', '读三段并回答', []),
                ('读三段并回答', '读三段并回答。\n每题写出依据，不少于20字\n提交要求：交纸质稿', ['每题写出依据，不少于20字', '提交要求：交纸质稿']),
                ('写生词', '写生词10个，每个3遍；家长签字', ['写生词10个，每个3遍；家长签字']),
                ('数学：完成同步练习第3课', '完成同步练习第3课，周四交\n提交要求：交同步练习第3课作业', ['完成同步练习第3课，周四交', '提交要求：交同步练习第3课作业']),
                ('科学：带一个空透明塑料瓶', '明天来校带一个空透明塑料瓶，科学课用。', ['明天来校带一个空透明塑料瓶，科学课用。']),
                ('英语：跟读Unit 4两遍并家长签字', '听录音跟读 Unit 4 A day at the lake 两遍。', ['听录音跟读 Unit 4 A day at the lake 两遍。']),
                ('语文：A', '今晚完成，明天交。\n提交要求：明天交。', ['今晚完成，明天交。']),
                ('语文：A', '今晚完成，不用明天交。\n提交要求：明天交练习册。', ['今晚完成，不用明天交。', '提交要求：明天交练习册。']),
                ('语文：A', '提交要求：明天交练习册。', ['提交要求：明天交练习册。'])]:
            with self.subTest(title=title, action=action):
                self.assertEqual(family_agenda.action_lines(title, action), shown)


# Six new fictional notices Root froze before any model receipt (daily-unseen-classification-20261018-truth-v1, messages.json
# sha256 a36c1281…234214) and the one actual Flash trial29 reply to the unchanged ordinary request (ACTUAL-PARSED-RAW.json
# sha256 655f0689…2ef99), both byte for byte; the reply cites the notices by their own group and message IDs. It left every
# due empty but the meeting's (10月23日): each item's own words still give its days.
OWNED_TIME_GROUP = 'fictional-group-20261021-01'
OWNED_TIME_MESSAGES = json.loads('[{"id": "m01", "group_id": "fictional-group-20261021-01", "sender_id": "teacher-cn", "sender_name": "岑老师", "sender_role": "语文", "sent_at": "2026-10-21T16:00:00+08:00", "text": "今晚语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。", "attachments": []}, {"id": "m02", "group_id": "fictional-group-20261021-01", "sender_id": "teacher-cn", "sender_name": "岑老师", "sender_role": "语文", "sent_at": "2026-10-21T16:01:00+08:00", "text": "补充上条第二项：三句话分别写颜色、形状和气味，不用抄写课文。", "attachments": []}, {"id": "m03", "group_id": "fictional-group-20261021-01", "sender_id": "teacher-math", "sender_name": "柳老师", "sender_role": "数学", "sent_at": "2026-10-21T16:05:00+08:00", "text": "数学今晚完成练习册第18页第2、4、6题。每题先列式，再写完整计算过程，算完后逐题验算。", "attachments": []}, {"id": "m04", "group_id": "fictional-group-20261021-01", "sender_id": "teacher-en", "sender_name": "邵老师", "sender_role": "英语", "sent_at": "2026-10-21T16:10:00+08:00", "text": "英语：今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。", "attachments": []}, {"id": "m05", "group_id": "fictional-group-20261021-01", "sender_id": "teacher-class", "sender_name": "唐老师", "sender_role": "班主任", "sent_at": "2026-10-21T16:15:00+08:00", "text": "请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。另通知：10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。", "attachments": []}, {"id": "m06", "group_id": "fictional-group-20261021-01", "sender_id": "teacher-science", "sender_name": "柏老师", "sender_role": "科学", "sent_at": "2026-10-21T16:20:00+08:00", "text": "分享一段校园种植园介绍文字：种植园里有薄荷、番茄和向日葵，大家可以了解。仅供参考，不是作业，不用摘抄，也不用提交。", "attachments": []}]')
OWNED_TIME_REPLY = json.loads('{"proposals": [{"title_quote": "朗读《秋天的小院》第2、3自然段两遍。", "focus": "school", "due": "", "evidence": [{"ref": "message:fictional-group-20261021-01:m01"}], "task_title": "语文：朗读《秋天的小院》第2、3段两遍", "task_goal": "朗读《秋天的小院》第2、3自然段两遍。", "task_advice": "可分两次朗读，每次读完稍作停顿，注意读准字音、读通句子。", "learning_subject": "语文", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求全班今晚完成的语文朗读作业，范围与遍数已读清。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "观察家里的一种植物，在观察本上写三句话。", "focus": "school", "due": "", "evidence": [{"ref": "message:fictional-group-20261021-01:m01"}, {"ref": "message:fictional-group-20261021-01:m02"}], "task_title": "语文：观察植物写三句话", "task_goal": "观察家里的一种植物，在观察本上写三句话；三句话分别写颜色、形状和气味，不用抄写课文。", "task_advice": "先看一看、闻一闻，再按颜色、形状、气味的顺序各写一句。", "learning_subject": "语文", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求全班今晚完成，补充消息已说明三句话的写作角度和不用抄写课文。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "数学今晚完成练习册第18页第2、4、6题。", "focus": "school", "due": "", "evidence": [{"ref": "message:fictional-group-20261021-01:m03"}], "task_title": "数学：练习册第18页第2、4、6题", "task_goal": "完成练习册第18页第2、4、6题；每题先列式，再写完整计算过程，算完后逐题验算。", "task_advice": "每题做完后回头验算一遍，确认列式与计算过程完整。", "learning_subject": "数学", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求今晚完成的数学练习，题号、作答步骤和验算要求已读清。", "task_purpose": "learning", "task_submission": ""}, {"title_quote": "今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。", "focus": "school", "due": "", "evidence": [{"ref": "message:fictional-group-20261021-01:m04"}], "task_title": "英语：朗读课本第20页对话三遍", "task_goal": "将课本第20页的对话朗读三遍；请家长听完后在这一页签字；明天早读检查。", "task_advice": "可分段朗读后再连读，家长听完后在第20页签字。", "learning_subject": "英语", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求今晚完成的英语朗读，遍数、家长签字和检查时间已读清。", "task_purpose": "learning", "task_submission": "家长听完后在第20页签字，明天早读检查。"}, {"title_quote": "请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。", "focus": "school", "due": "", "evidence": [{"ref": "message:fictional-group-20261021-01:m05"}], "task_title": "签字《秋游意见回执》并明早交班主任", "task_goal": "请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。", "task_advice": "签字后提醒孩子明早带回交给班主任。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确要求家长签字并由孩子明早交回，属待完成的行政事务。", "task_purpose": "admin", "task_submission": "家长签字后由孩子明早交给班主任。"}, {"title_quote": "10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。", "focus": "school", "due": "2026-10-23", "evidence": [{"ref": "message:fictional-group-20261021-01:m05"}], "task_title": "家长会：10月23日19:30本班教室", "task_goal": "10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。", "task_advice": "提前安排好时间，由一位家长准时参加。", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "ready", "task_reason": "老师明确通知的家长会日期、时间、地点和参加要求，属需办理的行政事项。", "task_purpose": "admin", "task_submission": ""}, {"title_quote": "仅供参考，不是作业，不用摘抄，也不用提交。", "focus": "school", "due": "", "evidence": [{"ref": "message:fictional-group-20261021-01:m06"}], "task_title": "", "task_goal": "", "task_advice": "", "learning_subject": "", "learning_goal_id": "", "task_change": "new", "task_target_id": "", "task_state": "reference", "task_reason": "校园种植园介绍文字明确说明仅供参考、不是作业、不用摘抄也不用提交，无新增行动要求。", "task_purpose": "optional", "task_submission": ""}]}')
# (category, own completion day shown apart, due, due kind) each item's own words give, by the frozen truth: a completion-only
# item is due on that day; the English check and the receipt's return are the due after tonight's work; the meeting is its event.
OWNED_TIME_DAYS = {
    '《秋天的小院》': ('homework', '', '2026-10-21', 'deadline'),
    '观察植物': ('homework', '', '2026-10-21', 'deadline'),
    '第18页': ('homework', '', '2026-10-21', 'deadline'),
    '第20页': ('homework', '2026-10-21', '2026-10-22', 'deadline'),
    '《秋游意见回执》': ('todo', '2026-10-21', '2026-10-22', 'deadline'),
    '家长会': ('todo', '', '2026-10-23', 'event'),
}


def owned_time_payload(case, notices, start='2026-10-21T16:00:00+08:00'):
    """notices: frozen message dicts, or (publisher, text) a minute apart from start; returns the payload and its refs."""
    first = dt.datetime.fromisoformat(start)
    rows = [m if isinstance(m, dict) else dict(id='v%02d' % n, sender_id=m[0], sender_name='虚构' + m[0],
                                               sent_at=(first + dt.timedelta(minutes=n)).isoformat(), text=m[1])
            for n, m in enumerate(notices, 1)]
    payload = case.fixture.payload(cursor=rows[-1]['id'])
    payload['messages'] = [dict(id=m['id'], message_order=str(n), time=m['sent_at'], kind='text', sender=m['sender_name'],
                                sender_id=m['sender_id'], text=m['text'], unread=False) for n, m in enumerate(rows, 1)]
    return payload, ['message:' + case.source['id'] + ':' + m['id'] for m in rows]


class OrdinaryOwnedTimeTests(unittest.TestCase):
    """Root's six frozen notices and the actual trial29 reply through the ordinary ingest -> run_once (mocked transport):
    every item keeps the days its own words state although the reply left them out; reference material is no todo."""
    setUp = native.SchoolNativeCoverageTests.setUp

    def save_day(self):
        self.now = self.fixture.now = dt.datetime(2026, 10, 21, 16, 30, tzinfo=agent.TZ)
        payload, refs = owned_time_payload(self, OWNED_TIME_MESSAGES)
        self.store.ingest(payload)
        reply = json.loads(json.dumps(OWNED_TIME_REPLY, ensure_ascii=False).replace('message:' + OWNED_TIME_GROUP + ':', 'message:' + self.source['id'] + ':'))
        requests = []

        def model(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual((name, timeout), ('family_agent_selection', 45))
            requests.append(json.loads(messages[-1]['content']))
            return copy.deepcopy(reply)
        self.model.side_effect = model
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed'], self.model.call_count), (0, 6, 1), result)
        # The unchanged ordinary request: every original verbatim, no program-located list (the ledger reads none of these).
        self.assertEqual([(e['ref'], e['text']) for e in requests[0]['evidence']], list(zip(refs, [m['text'] for m in OWNED_TIME_MESSAGES])))
        self.assertNotIn('required_native_actions', requests[0])
        with self.store._db() as c:
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
            items = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
        ids = {}
        for key in OWNED_TIME_DAYS:
            found = [i for i, t in tasks.items() if key in t['title']]
            self.assertEqual(len(found), 1, (key, [t['title'] for t in tasks.values()]))
            ids[key] = found[0]
        return ids, tasks, items, refs

    def _listed(self, day):
        calendar = self.app.calendar_snapshot(day, day)
        return {x['task_id']: x for x in calendar['inbox'] if x['task_id'] and self.source['child_id'] in x['child_ids']}

    def test_the_frozen_reply_saves_four_homework_and_two_parent_items_on_their_own_days(self):
        ids, tasks, items, refs = self.save_day()
        self.assertEqual(len(tasks), 6, [t['title'] for t in tasks.values()])
        # Every actionable item is collected on the existing acceptance path, none held for an unadopted day.
        actionable = [r for r in items.values() if json.loads(r['plan'])['school_task']['state'] != 'reference']
        self.assertEqual(sorted(r['state'] for r in actionable), ['accepted'] * 6)
        self.assertFalse(any('未采用模型日期' in json.loads(r['plan'])['school_task']['reason'] for r in items.values()))
        # The science introduction stays reference material only: kept, cited, no todo.
        reference = [r for r in items.values() if json.loads(r['plan'])['school_task']['state'] == 'reference']
        self.assertEqual([(r['state'], r['task_id'], [e['ref'] for e in json.loads(r['evidence'])]) for r in reference],
                         [('pending', '', [refs[5]])])
        self.assertFalse(any('种植园' in t['title'] + t['action'] + t['due'] for t in tasks.values()))

        def check(listed):
            for key, (category, complete, due, kind) in OWNED_TIME_DAYS.items():
                with self.subTest(item=key):
                    agenda = listed[ids[key]]['agenda']
                    self.assertEqual((agenda['category'], agenda['complete_on'], agenda['due_on'], agenda['due_kind']),
                                     (category, complete, due, kind))
                    self.assertEqual(tasks[ids[key]]['due'], due)
        check(self._listed('2026-10-21'))
        today = [x['task_id'] for x in self.app.calendar_snapshot('2026-10-21', '2026-10-21')['agenda'] if x['task_id']]
        for key in OWNED_TIME_DAYS:
            self.assertEqual(today.count(ids[key]), 1, (key, 'listed once on its own sending day'))
        # Each item keeps its own standard; a supplement or another item's words never move.
        observe, read = tasks[ids['观察植物']], tasks[ids['《秋天的小院》']]
        for words in ('三句话', '颜色、形状和气味', '不用抄写课文'):
            self.assertIn(words, observe['action'])
            self.assertNotIn(words, read['action'])
        self.assertIn(refs[1], observe['source'])
        self.assertNotIn(refs[1], read['source'] + tasks[ids['第18页']]['source'])
        self.assertIn('第2、4、6题', tasks[ids['第18页']]['action'])
        english = tasks[ids['第20页']]
        for words in ('朗读三遍', '请家长听完后在这一页签字', '明天早读检查'):
            self.assertIn(words, english['action'])
        self.assertNotIn('交', english['title'], 'checking is not handing in')
        self.assertNotRegex(english['action'], '交(?:回|给|到)', 'no handback invented')
        receipt, meeting = tasks[ids['《秋游意见回执》']], tasks[ids['家长会']]
        self.assertIn('明早交给班主任', receipt['action'])
        for words in ('19:30', '本班教室', '一位家长参加', '孩子不用参加'):
            self.assertIn(words, meeting['title'] + meeting['action'])
        self.assertNotIn('10-23', receipt['due'] + receipt['action'], 'the meeting day is not the receipt deadline')
        # The next round reads nothing new: no model, no task; reopening keeps the same IDs, days and roles.
        second = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((second['failed'], second['created'], self.model.call_count), (0, 0, 1), second)
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        with self.store._db() as c:
            self.assertEqual({r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}, tasks)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages WHERE processed=1').fetchone()[0], 6)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        for day in ('2026-10-21', '2026-10-22', '2026-10-23'):
            check(self._listed(day))

    def run_day(self, notices, proposals):
        """A fresh store, one ordinary round for notices and one reply; each proposal is (key, quote, model due, message
        numbers, purpose, subject). Returns each key's saved item due/state and its task due ('' when none)."""
        self.setUp()
        self.now = self.fixture.now = dt.datetime(2026, 10, 21, 16, 30, tzinfo=agent.TZ)
        payload, refs = owned_time_payload(self, notices)
        self.store.ingest(payload)
        reply = dict(proposals=[native.fixtures.school_proposal(
            title_quote=quote, due=due, evidence=[dict(ref=refs[n - 1]) for n in numbers], task_title=key,
            task_goal=quote.split('：', 1)[-1], task_state='ready', task_reason='老师原文要求明确。', task_purpose=purpose,
            learning_subject=subject) for key, quote, due, numbers, purpose, subject in proposals])
        cited = {r for p in reply['proposals'] for r in (e['ref'] for e in p['evidence'])}
        reply['proposals'] += [native.fixtures.school_proposal(title_quote=m['text'][:20], evidence=[dict(ref=r)], task_state='reference',
                                                        task_reason='无行动要求。', task_purpose='optional')
                               for r, m in zip(refs, payload['messages']) if r not in cited]
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        result = agent.run_once(self.app, self.now)
        with self.store._db() as c:
            errors = [r['error'] for r in c.execute("SELECT error FROM agent_jobs WHERE id LIKE 'messages:%'")]
        self.assertEqual((result['failed'], result['processed']), (0, len(notices)), (result, errors))
        out = {}
        with self.store._db() as c:
            for key, *_ in proposals:
                row = c.execute("SELECT * FROM agent_items WHERE kind='school' AND title=?", (key,)).fetchone()
                self.assertIsNotNone(row, key)
                task = c.execute('SELECT due FROM manual_tasks WHERE id=?', (row['task_id'],)).fetchone() if row['task_id'] else None
                out[key] = (row['due'], row['state'], task['due'] if task else '')
        return out

    def test_an_omitted_day_is_read_only_from_the_item_s_own_words(self):
        # Own days in other shapes: a list heading's 今晚 over items stating none (a 《》 title's 明天 is a name), a receipt
        # signed tonight in a named form and returned 明早 with a clock (spaced or not), a spaced meeting time, the subject
        # label left out of the quote, and a sibling that states no day of its own.
        days = self.run_day([
            ('teacher-cn', '今晚语文：1.朗读《明天的太阳》第2段两遍。2.观察家里的一种植物，在观察本上写三句话。'),
            ('teacher-class', '请家长今晚在《10月25日活动回执》上签字，由孩子明早 7:30 交给班主任。另通知：10月23日 19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。'),
            ('teacher-en', '英语：今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。'),
            ('teacher-math', '数学今晚完成练习册第18页第2、4、6题。另外，请准备一把量角器。'),
            ('teacher-class2', '请家长今晚在《秋游意见回执》上签字，由孩子明早7:30交给班主任。'),
        ], [
            ('语文：朗读《明天的太阳》', '朗读《明天的太阳》第2段两遍。', '', [1], 'learning', '语文'),
            ('语文：观察植物', '观察家里的一种植物，在观察本上写三句话。', '', [1], 'learning', '语文'),
            ('签字《10月25日活动回执》', '请家长今晚在《10月25日活动回执》上签字，由孩子明早 7:30 交给班主任。', '', [2], 'admin', ''),
            ('家长会（10月23日）', '10月23日 19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。', '', [2], 'admin', ''),
            ('英语：朗读第20页对话', '今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。', '', [3], 'learning', '英语'),
            ('数学：第18页', '数学今晚完成练习册第18页第2、4、6题。', '', [4], 'learning', '数学'),
            ('准备量角器', '请准备一把量角器。', '', [4], 'admin', ''),
            ('签字《秋游意见回执》', '请家长今晚在《秋游意见回执》上签字，由孩子明早7:30交给班主任。', '', [5], 'admin', ''),
        ])
        self.assertEqual(days, {
            '语文：朗读《明天的太阳》': ('2026-10-21', 'accepted', '2026-10-21'),
            '语文：观察植物': ('2026-10-21', 'accepted', '2026-10-21'),
            '签字《10月25日活动回执》': ('2026-10-22', 'accepted', '2026-10-22'),
            '家长会（10月23日）': ('2026-10-23', 'accepted', '2026-10-23'),
            '英语：朗读第20页对话': ('2026-10-22', 'accepted', '2026-10-22'),
            '数学：第18页': ('2026-10-21', 'accepted', '2026-10-21'),
            '准备量角器': ('', 'accepted', '无明确截止'),
            '签字《秋游意见回执》': ('2026-10-22', 'accepted', '2026-10-22'),
        })
        listed = {x['title']: x['agenda'] for x in self.app.calendar_snapshot('2026-10-21', '2026-10-21')['inbox'] if x['task_id']}
        for title in ('签字《10月25日活动回执》', '英语：朗读第20页对话', '签字《秋游意见回执》'):
            self.assertEqual((listed[title]['complete_on'], listed[title]['due_on']), ('2026-10-21', '2026-10-22'), title)
        self.assertEqual(listed['家长会（10月23日）']['due_kind'], 'event')

    def test_unknown_changed_cancelled_conflicting_or_borrowed_days_stay_unknown(self):
        days = self.run_day([
            # 今天语文： labels the day's list (as 今天…作业： does); its items state no day of their own.
            ('teacher-cn', '今天语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。'),
            ('teacher-cn2', '观察家里的一种植物，在观察本上写三句话。'),
            ('teacher-class', '另通知：10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。现通知该家长会取消。'),
            ('teacher-class2', '10月23日19:30在本班教室召开家长会，请一位家长参加。家长会延期，时间另行通知。'),
            ('teacher-class3', '10月23日19:30在本班教室召开家长会，家长自愿参加，孩子不用参加。'),
            ('teacher-math', '数学今晚完成练习册第3页，明天交或后天交。'),
        ], [
            ('今天：朗读', '朗读《秋天的小院》第2、3自然段两遍。', '', [1], 'learning', '语文'),
            ('今天：观察', '观察家里的一种植物，在观察本上写三句话。', '', [1], 'learning', '语文'),
            ('无日期：观察', '观察家里的一种植物，在观察本上写三句话。', '', [2], 'learning', '语文'),
            ('取消的家长会', '10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。', '2026-10-23', [3], 'admin', ''),
            ('延期的家长会', '10月23日19:30在本班教室召开家长会，请一位家长参加。', '2026-10-23', [4], 'admin', ''),
            ('自愿的家长会', '10月23日19:30在本班教室召开家长会，家长自愿参加，孩子不用参加。', '2026-10-23', [5], 'admin', ''),
            ('两个交回日', '数学今晚完成练习册第3页，明天交或后天交。', '', [6], 'learning', '数学'),
        ])
        for key in ('今天：朗读', '今天：观察', '无日期：观察', '两个交回日'):
            self.assertEqual(days[key][0], '', key)
        for key in ('取消的家长会', '延期的家长会', '自愿的家长会'):
            self.assertEqual(days[key], ('', 'pending', ''), key)
        # Another teacher's later day is never the list's: only the item its own heading covers keeps 今晚.
        days = self.run_day([
            ('teacher-cn', '今晚语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。'),
            ('teacher-sci', '补充上条第二项：明天交观察本。'),
        ], [
            ('跨老师：朗读', '朗读《秋天的小院》第2、3自然段两遍。', '', [1], 'learning', '语文'),
            ('跨老师：观察', '观察家里的一种植物，在观察本上写三句话。', '', [1, 2], 'learning', '语文'),
        ])
        self.assertEqual(days['跨老师：朗读'][0], '2026-10-21')
        self.assertEqual(days['跨老师：观察'][0], '')

    def test_a_meeting_another_participant_need_not_attend_keeps_its_day(self):
        sent = '2026-10-21'
        head = '请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。另通知：'
        for text, expected in [
                (head + '10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。', {'2026-10-23'}),
                (head + '10月23日 19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。', {'2026-10-23'}),
                ('10月23日19:30在本班教室召开家长会，请孩子参加，家长不用参加。', {'2026-10-23'}),
                (head + '10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。现通知该家长会取消。', set()),
                ('10月23日19:30在本班教室召开家长会，请家长参加，可不参加。', set()),
                ('10月23日19:30在本班教室召开家长会，家长自愿参加，孩子不用参加。', set()),
                ('10月23日19:30在本班教室召开家长会，请一位家长参加，家长不用参加。', set())]:
            with self.subTest(text=text):
                self.assertEqual(family_agenda.event_days(text, sent), expected)


# Root's ordinary save of the same frozen day by r262 code 488537d (NORMAL-AFTER.json sha256 92bd52e7…d8b53, fictional):
# its agent_items/jobs/messages/runtime/sources and manual_tasks rows byte for byte. The five collected tasks kept no day
# (无明确截止); the meeting is a pending review whose plan kept the reply's 2026-10-23 as not adopted.
SAVED_OWNED_TIME = json.loads('{"agent_items": [{"id": "agent-9c3415133158cdfc3f3dbe9c5864f9e3", "job_id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "child_id": "child-1", "kind": "school", "title": "语文：朗读《秋天的小院》第2、3段两遍", "body": "朗读《秋天的小院》第2、3自然段两遍。", "evidence": "[{\\"ref\\":\\"message:fictional-group-20261021-01:m01\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:00:00+08:00\\\\n今晚语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。\\"}]", "due": "", "care_id": "", "record_id": null, "state": "accepted", "created": "2026-10-21T16:30:00+08:00", "updated": "2026-10-18T14:37:22.322025+08:00", "task_id": "AGENT-bbec4c1a168671f34688d3cc", "plan": "{\\"school_date_quote\\":\\"朗读《秋天的小院》第2、3自然段两遍。\\",\\"school_generated_snapshot\\":\\"8e943b5504010cf75e65ff4b7e0be2fd77c4b2b37926175d6c475f9a46a64bcb\\",\\"school_goal_id\\":\\"goal-47b93177aabb4f3f89a919a79121db81\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"语文\\"},\\"school_messages\\":[{\\"message_id\\":\\"m01\\",\\"source_id\\":\\"fictional-group-20261021-01\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可分两次朗读，每次读完稍作停顿，注意读准字音、读通句子。\\",\\"change\\":\\"new\\",\\"goal\\":\\"朗读《秋天的小院》第2、3自然段两遍。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求全班今晚完成的语文朗读作业，范围与遍数已读清。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：朗读《秋天的小院》第2、3段两遍\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可分两次朗读，每次读完稍作停顿，注意读准字音、读通句子。\\",\\"auto_added\\":true,\\"change\\":\\"new\\",\\"goal\\":\\"朗读《秋天的小院》第2、3自然段两遍。\\",\\"origin_basis\\":{\\"message:fictional-group-20261021-01:m01\\":\\"f955a90a96174ca846f9b6e936331fb08a2f84436810348784612e272eee2f6e\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求全班今晚完成的语文朗读作业，范围与遍数已读清。\\",\\"state\\":\\"ready\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：朗读《秋天的小院》第2、3段两遍\\"}}"}, {"id": "agent-a9b7336bbe983980b8d628db094f00a8", "job_id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "child_id": "child-1", "kind": "school", "title": "语文：观察植物写三句话", "body": "观察家里的一种植物，在观察本上写三句话；三句话分别写颜色、形状和气味，不用抄写课文。", "evidence": "[{\\"ref\\":\\"message:fictional-group-20261021-01:m01\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:00:00+08:00\\\\n今晚语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。\\"},{\\"ref\\":\\"message:fictional-group-20261021-01:m02\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:01:00+08:00\\\\n补充上条第二项：三句话分别写颜色、形状和气味，不用抄写课文。\\"}]", "due": "", "care_id": "", "record_id": null, "state": "accepted", "created": "2026-10-21T16:30:00+08:00", "updated": "2026-10-18T14:37:22.327006+08:00", "task_id": "AGENT-7f717a7ce1b10fce394db2e0", "plan": "{\\"school_date_quote\\":\\"观察家里的一种植物，在观察本上写三句话。\\",\\"school_generated_snapshot\\":\\"9448413a8bfeb60b483902aeecc345fcf2e4713c719cc5e35e27db92d7c63696\\",\\"school_goal_id\\":\\"goal-47b93177aabb4f3f89a919a79121db81\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"语文\\"},\\"school_messages\\":[{\\"message_id\\":\\"m01\\",\\"source_id\\":\\"fictional-group-20261021-01\\"},{\\"message_id\\":\\"m02\\",\\"source_id\\":\\"fictional-group-20261021-01\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"先看一看、闻一闻，再按颜色、形状、气味的顺序各写一句。\\",\\"change\\":\\"new\\",\\"goal\\":\\"观察家里的一种植物，在观察本上写三句话；三句话分别写颜色、形状和气味，不用抄写课文。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求全班今晚完成，补充消息已说明三句话的写作角度和不用抄写课文。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：观察植物写三句话\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"先看一看、闻一闻，再按颜色、形状、气味的顺序各写一句。\\",\\"auto_added\\":true,\\"change\\":\\"new\\",\\"goal\\":\\"观察家里的一种植物，在观察本上写三句话；三句话分别写颜色、形状和气味，不用抄写课文。\\",\\"origin_basis\\":{\\"message:fictional-group-20261021-01:m01\\":\\"f955a90a96174ca846f9b6e936331fb08a2f84436810348784612e272eee2f6e\\",\\"message:fictional-group-20261021-01:m02\\":\\"0003b77add812f028a1d329ee5bbca31c037edcf3e2f98dabafa81bee3ddbd78\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求全班今晚完成，补充消息已说明三句话的写作角度和不用抄写课文。\\",\\"state\\":\\"ready\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：观察植物写三句话\\"}}"}, {"id": "agent-821b0f050ccfc29657094155df1e7443", "job_id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "child_id": "child-1", "kind": "school", "title": "数学：练习册第18页第2、4、6题", "body": "完成练习册第18页第2、4、6题；每题先列式，再写完整计算过程，算完后逐题验算。", "evidence": "[{\\"ref\\":\\"message:fictional-group-20261021-01:m03\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:05:00+08:00\\\\n数学今晚完成练习册第18页第2、4、6题。每题先列式，再写完整计算过程，算完后逐题验算。\\"}]", "due": "", "care_id": "", "record_id": null, "state": "accepted", "created": "2026-10-21T16:30:00+08:00", "updated": "2026-10-18T14:37:22.317413+08:00", "task_id": "AGENT-197de67f1ad60d9ae5d5096f", "plan": "{\\"school_date_quote\\":\\"数学今晚完成练习册第18页第2、4、6题。\\",\\"school_generated_snapshot\\":\\"2d3fb626fe92f811135500bb5ad1274eb5705d613688125d0aebad214b11604d\\",\\"school_goal_id\\":\\"goal-abb032574f6a363eeb620734538938c2\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"数学\\"},\\"school_messages\\":[{\\"message_id\\":\\"m03\\",\\"source_id\\":\\"fictional-group-20261021-01\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"每题做完后回头验算一遍，确认列式与计算过程完整。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成练习册第18页第2、4、6题；每题先列式，再写完整计算过程，算完后逐题验算。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求今晚完成的数学练习，题号、作答步骤和验算要求已读清。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"数学：练习册第18页第2、4、6题\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"每题做完后回头验算一遍，确认列式与计算过程完整。\\",\\"auto_added\\":true,\\"change\\":\\"new\\",\\"goal\\":\\"完成练习册第18页第2、4、6题；每题先列式，再写完整计算过程，算完后逐题验算。\\",\\"origin_basis\\":{\\"message:fictional-group-20261021-01:m03\\":\\"3e0b742504be30ee35771fca2726800dcc9536d125d3e0eb89f2c95aa8f0d52f\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求今晚完成的数学练习，题号、作答步骤和验算要求已读清。\\",\\"state\\":\\"ready\\",\\"target_id\\":\\"\\",\\"title\\":\\"数学：练习册第18页第2、4、6题\\"}}"}, {"id": "agent-d4ec1446c78687f595c7cfcb3d55f320", "job_id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "child_id": "child-1", "kind": "school", "title": "英语：朗读课本第20页对话三遍", "body": "今晚将课本第20页的对话朗读三遍；请家长听完后在这一页签字；明天早读检查。\\n提交要求：家长听完后在第20页签字，明天早读检查。", "evidence": "[{\\"ref\\":\\"message:fictional-group-20261021-01:m04\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:10:00+08:00\\\\n英语：今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。\\"}]", "due": "", "care_id": "", "record_id": null, "state": "accepted", "created": "2026-10-21T16:30:00+08:00", "updated": "2026-10-18T14:37:22.331380+08:00", "task_id": "AGENT-47d69320426840b7989d616b", "plan": "{\\"school_date_quote\\":\\"今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。\\",\\"school_generated_snapshot\\":\\"22813dc128f95acc2e4720ce729328d67e3c26cdcbcec0dfb92ed72ad167dd9d\\",\\"school_goal_id\\":\\"goal-4aa066595907e486319200acadd6c92f\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"英语\\"},\\"school_messages\\":[{\\"message_id\\":\\"m04\\",\\"source_id\\":\\"fictional-group-20261021-01\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可分段朗读后再连读，家长听完后在第20页签字。\\",\\"change\\":\\"new\\",\\"goal\\":\\"将课本第20页的对话朗读三遍；请家长听完后在这一页签字；明天早读检查。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求今晚完成的英语朗读，遍数、家长签字和检查时间已读清。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"家长听完后在第20页签字，明天早读检查。\\",\\"target_id\\":\\"\\",\\"title\\":\\"英语：朗读课本第20页对话三遍\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可分段朗读后再连读，家长听完后在第20页签字。\\",\\"auto_added\\":true,\\"change\\":\\"new\\",\\"goal\\":\\"今晚将课本第20页的对话朗读三遍；请家长听完后在这一页签字；明天早读检查。\\\\n提交要求：家长听完后在第20页签字，明天早读检查。\\",\\"origin_basis\\":{\\"message:fictional-group-20261021-01:m04\\":\\"62bdf58bc00add7a9ae8b080792693347acd0e5abfc952ad868083176ef60480\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"老师明确要求今晚完成的英语朗读，遍数、家长签字和检查时间已读清。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"家长听完后在第20页签字，明天早读检查。\\",\\"target_id\\":\\"\\",\\"title\\":\\"英语：朗读课本第20页对话三遍\\"}}"}, {"id": "agent-dc09a7753cdbae7cfd2537e64abd48fd", "job_id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "child_id": "child-1", "kind": "school", "title": "签字《秋游意见回执》并明早交班主任", "body": "请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。", "evidence": "[{\\"ref\\":\\"message:fictional-group-20261021-01:m05\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:15:00+08:00\\\\n请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。另通知：10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。\\"}]", "due": "", "care_id": "", "record_id": null, "state": "accepted", "created": "2026-10-21T16:30:00+08:00", "updated": "2026-10-18T14:37:22.335439+08:00", "task_id": "AGENT-baef0382d64d3bd88a52f208", "plan": "{\\"school_date_quote\\":\\"请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。\\",\\"school_generated_snapshot\\":\\"fdba97d22193dc61d2dd2774b74ab85eea71598be76cc57ed2b158e25be28d2c\\",\\"school_selection_receipt\\":{\\"advice\\":\\"签字后提醒孩子明早带回交给班主任。\\",\\"change\\":\\"new\\",\\"goal\\":\\"请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。\\",\\"purpose\\":\\"admin\\",\\"reason\\":\\"老师明确要求家长签字并由孩子明早交回，属待完成的行政事务。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"家长签字后由孩子明早交给班主任。\\",\\"target_id\\":\\"\\",\\"title\\":\\"签字《秋游意见回执》并明早交班主任\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"签字后提醒孩子明早带回交给班主任。\\",\\"auto_added\\":true,\\"change\\":\\"new\\",\\"goal\\":\\"请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。\\",\\"origin_basis\\":{\\"message:fictional-group-20261021-01:m05\\":\\"e486941dc1b0bd35dc62ba61c2691801e0293bb5a837bc1d0e2a6e30538c6155\\"},\\"policy\\":10,\\"purpose\\":\\"admin\\",\\"reason\\":\\"老师明确要求家长签字并由孩子明早交回，属待完成的行政事务。\\",\\"state\\":\\"ready\\",\\"target_id\\":\\"\\",\\"title\\":\\"签字《秋游意见回执》并明早交班主任\\"}}"}, {"id": "agent-5b04be34973b8fcf70a40d4c1160ffb6", "job_id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "child_id": "child-1", "kind": "school", "title": "家长会：10月23日19:30本班教室", "body": "10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。", "evidence": "[{\\"ref\\":\\"message:fictional-group-20261021-01:m05\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:15:00+08:00\\\\n请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。另通知：10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。\\"}]", "due": "", "care_id": "", "record_id": null, "state": "pending", "created": "2026-10-21T16:30:00+08:00", "updated": "2026-10-21T16:30:00+08:00", "task_id": "", "plan": "{\\"school_date_quote\\":\\"10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。\\",\\"school_generated_snapshot\\":\\"3c63220d2d386a39f23879cc3377716741604ff93708fe3da88e8cd5f132a725\\",\\"school_selection_receipt\\":{\\"advice\\":\\"提前安排好时间，由一位家长准时参加。\\",\\"change\\":\\"new\\",\\"goal\\":\\"10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。\\",\\"purpose\\":\\"admin\\",\\"reason\\":\\"老师明确通知的家长会日期、时间、地点和参加要求，属需办理的行政事项。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"家长会：10月23日19:30本班教室\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"提前安排好时间，由一位家长准时参加。\\",\\"change\\":\\"new\\",\\"goal\\":\\"10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。\\",\\"origin_basis\\":{\\"message:fictional-group-20261021-01:m05\\":\\"e486941dc1b0bd35dc62ba61c2691801e0293bb5a837bc1d0e2a6e30538c6155\\"},\\"policy\\":10,\\"purpose\\":\\"admin\\",\\"reason\\":\\"老师明确通知的家长会日期、时间、地点和参加要求，属需办理的行政事项。 截止日期尚无法从原文核对，未采用模型日期；请核对原通知。\\",\\"state\\":\\"review\\",\\"target_id\\":\\"\\",\\"title\\":\\"家长会：10月23日19:30本班教室\\"},\\"school_unadopted_due\\":\\"2026-10-23\\"}"}, {"id": "agent-3cf5156300c347b7824f0379028e3597", "job_id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "child_id": "child-1", "kind": "school", "title": "参考资料：仅供参考，不是作业，不用摘抄，也不用提交。", "body": "按参考资料保留，不自动加入待办或学习目标；内容以原通知为准。", "evidence": "[{\\"ref\\":\\"message:fictional-group-20261021-01:m06\\",\\"text\\":\\"晨露四年级三班（纯虚构） · 2026-10-21T16:20:00+08:00\\\\n分享一段校园种植园介绍文字：种植园里有薄荷、番茄和向日葵，大家可以了解。仅供参考，不是作业，不用摘抄，也不用提交。\\"}]", "due": "", "care_id": "", "record_id": null, "state": "pending", "created": "2026-10-21T16:30:00+08:00", "updated": "2026-10-21T16:30:00+08:00", "task_id": "", "plan": "{\\"school_date_quote\\":\\"仅供参考，不是作业，不用摘抄，也不用提交。\\",\\"school_generated_snapshot\\":\\"5ee0bee0b75440034500b80d0a7b55400b5d70437edbf5da86eee0d2670ce381\\",\\"school_selection_receipt\\":{\\"advice\\":\\"\\",\\"change\\":\\"new\\",\\"goal\\":\\"\\",\\"purpose\\":\\"optional\\",\\"reason\\":\\"校园种植园介绍文字明确说明仅供参考、不是作业、不用摘抄也不用提交，无新增行动要求。\\",\\"state\\":\\"reference\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"\\",\\"change\\":\\"new\\",\\"goal\\":\\"\\",\\"origin_basis\\":{\\"message:fictional-group-20261021-01:m06\\":\\"64c7e0e776c6f67c504887207bb3f2dcb291941c8b5b00d46ea08503252608c9\\"},\\"policy\\":10,\\"purpose\\":\\"optional\\",\\"reason\\":\\"校园种植园介绍文字明确说明仅供参考、不是作业、不用摘抄也不用提交，无新增行动要求。\\",\\"state\\":\\"reference\\",\\"target_id\\":\\"\\",\\"title\\":\\"\\"}}"}, {"id": "goal-abb032574f6a363eeb620734538938c2", "job_id": "manual-goal:goal-abb032574f6a363eeb620734538938c2", "child_id": "child-1", "kind": "care", "title": "数学：学校学习要求", "body": "由学校学习要求启动，尚无孩子实际作答或掌握证据。", "evidence": "[]", "due": "", "care_id": "", "record_id": null, "state": "draft", "created": "2026-10-18T14:37:22.336738+08:00", "updated": "2026-10-18T14:37:22.336940+08:00", "task_id": "", "plan": "{\\"create_hash\\":\\"3dee7b5c8c329cd1948faadf87c75cc23b030821840b6d29dd4f656fa1c2e5fc\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"数学\\",\\"title\\":\\"数学：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"}, {"id": "goal-47b93177aabb4f3f89a919a79121db81", "job_id": "manual-goal:goal-47b93177aabb4f3f89a919a79121db81", "child_id": "child-1", "kind": "care", "title": "语文：学校学习要求", "body": "由学校学习要求启动，尚无孩子实际作答或掌握证据。", "evidence": "[]", "due": "", "care_id": "", "record_id": null, "state": "draft", "created": "2026-10-18T14:37:22.341161+08:00", "updated": "2026-10-18T14:37:22.341350+08:00", "task_id": "", "plan": "{\\"create_hash\\":\\"0540f0c432a8f4c71632edfd93a7d9abd06ffaad8e9869fc4c5f634946907d6e\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"语文\\",\\"title\\":\\"语文：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"}, {"id": "goal-4aa066595907e486319200acadd6c92f", "job_id": "manual-goal:goal-4aa066595907e486319200acadd6c92f", "child_id": "child-1", "kind": "care", "title": "英语：学校学习要求", "body": "由学校学习要求启动，尚无孩子实际作答或掌握证据。", "evidence": "[]", "due": "", "care_id": "", "record_id": null, "state": "draft", "created": "2026-10-18T14:37:22.352259+08:00", "updated": "2026-10-18T14:37:22.352456+08:00", "task_id": "", "plan": "{\\"create_hash\\":\\"cdb877951b0c9f31ba8e4a0dc3ef754b6ae2603ae3af950f8ee8dad9bbf40ed5\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"英语\\",\\"title\\":\\"英语：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"}], "agent_jobs": [{"id": "school-audit-boundary", "fingerprint": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "attempts": 0, "next_try": "", "error": "", "done": 1}, {"id": "messages:bf6a5c15a541d6e3a58c1a8956ae50c1d8e17e74", "fingerprint": "a6cc5fefa03c5e26cf0c9c345d97a7ef3207ef20521094c950bae2d2f3d5eb1c", "attempts": 1, "next_try": "", "error": "", "done": 1}, {"id": "goal:goal-4aa066595907e486319200acadd6c92f", "fingerprint": "71a3bc18ac196b1d09a1176a59adc806861290bdd0ea65e21a4c804b3fedc2e5", "attempts": 1, "next_try": "", "error": "", "done": 0}], "agent_messages": [{"source_id": "fictional-group-20261021-01", "id": "m01", "payload": "{\\"id\\":\\"m01\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"1\\",\\"sender\\":\\"岑老师\\",\\"sender_id\\":\\"teacher-cn\\",\\"text\\":\\"今晚语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。\\",\\"time\\":\\"2026-10-21T16:00:00+08:00\\",\\"unread\\":false}", "processed": 1}, {"source_id": "fictional-group-20261021-01", "id": "m02", "payload": "{\\"id\\":\\"m02\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"2\\",\\"sender\\":\\"岑老师\\",\\"sender_id\\":\\"teacher-cn\\",\\"text\\":\\"补充上条第二项：三句话分别写颜色、形状和气味，不用抄写课文。\\",\\"time\\":\\"2026-10-21T16:01:00+08:00\\",\\"unread\\":false}", "processed": 1}, {"source_id": "fictional-group-20261021-01", "id": "m03", "payload": "{\\"id\\":\\"m03\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"3\\",\\"sender\\":\\"柳老师\\",\\"sender_id\\":\\"teacher-math\\",\\"text\\":\\"数学今晚完成练习册第18页第2、4、6题。每题先列式，再写完整计算过程，算完后逐题验算。\\",\\"time\\":\\"2026-10-21T16:05:00+08:00\\",\\"unread\\":false}", "processed": 1}, {"source_id": "fictional-group-20261021-01", "id": "m04", "payload": "{\\"id\\":\\"m04\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"4\\",\\"sender\\":\\"邵老师\\",\\"sender_id\\":\\"teacher-en\\",\\"text\\":\\"英语：今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。\\",\\"time\\":\\"2026-10-21T16:10:00+08:00\\",\\"unread\\":false}", "processed": 1}, {"source_id": "fictional-group-20261021-01", "id": "m05", "payload": "{\\"id\\":\\"m05\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"5\\",\\"sender\\":\\"唐老师\\",\\"sender_id\\":\\"teacher-class\\",\\"text\\":\\"请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。另通知：10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。\\",\\"time\\":\\"2026-10-21T16:15:00+08:00\\",\\"unread\\":false}", "processed": 1}, {"source_id": "fictional-group-20261021-01", "id": "m06", "payload": "{\\"id\\":\\"m06\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"6\\",\\"sender\\":\\"柏老师\\",\\"sender_id\\":\\"teacher-science\\",\\"text\\":\\"分享一段校园种植园介绍文字：种植园里有薄荷、番茄和向日葵，大家可以了解。仅供参考，不是作业，不用摘抄，也不用提交。\\",\\"time\\":\\"2026-10-21T16:20:00+08:00\\",\\"unread\\":false}", "processed": 1}], "agent_runtime": [{"id": 1, "state": "running", "last_run": "2026-10-21T16:30:00+08:00", "last_error": ""}], "agent_sources": [{"id": "fictional-group-20261021-01", "binding": "[\\"wechat\\",\\"child-1\\"]", "cursor": "fictional-six-06", "last_attempt": "2026-10-21T16:30:00+08:00", "last_success": "2026-10-21T16:30:00+08:00", "last_message_time": "2026-10-21T16:20:00+08:00", "error": "", "receipt": "4b3fb4e6c9659bf266c369421d602c897ceb9dd79dd20e1a0b58e5b6cb69feeb", "unread_count": 0, "check_request": "{}"}], "manual_tasks": [{"id": "AGENT-197de67f1ad60d9ae5d5096f", "child": "顾星禾", "title": "数学：练习册第18页第2、4、6题", "due": "无明确截止", "original_status": "待跟进", "source": "Agent建议:agent-821b0f050ccfc29657094155df1e7443\\nmessage:fictional-group-20261021-01:m03\\n晨露四年级三班（纯虚构） · 2026-10-21T16:05:00+08:00\\n数学今晚完成练习册第18页第2、4、6题。每题先列式，再写完整计算过程，算完后逐题验算。", "action": "完成练习册第18页第2、4、6题；每题先列式，再写完整计算过程，算完后逐题验算。"}, {"id": "AGENT-bbec4c1a168671f34688d3cc", "child": "顾星禾", "title": "语文：朗读《秋天的小院》第2、3段两遍", "due": "无明确截止", "original_status": "待跟进", "source": "Agent建议:agent-9c3415133158cdfc3f3dbe9c5864f9e3\\nmessage:fictional-group-20261021-01:m01\\n晨露四年级三班（纯虚构） · 2026-10-21T16:00:00+08:00\\n今晚语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。", "action": "朗读《秋天的小院》第2、3自然段两遍。"}, {"id": "AGENT-7f717a7ce1b10fce394db2e0", "child": "顾星禾", "title": "语文：观察植物写三句话", "due": "无明确截止", "original_status": "待跟进", "source": "Agent建议:agent-a9b7336bbe983980b8d628db094f00a8\\nmessage:fictional-group-20261021-01:m01\\n晨露四年级三班（纯虚构） · 2026-10-21T16:00:00+08:00\\n今晚语文：1.朗读《秋天的小院》第2、3自然段两遍。2.观察家里的一种植物，在观察本上写三句话。\\n\\nmessage:fictional-group-20261021-01:m02\\n晨露四年级三班（纯虚构） · 2026-10-21T16:01:00+08:00\\n补充上条第二项：三句话分别写颜色、形状和气味，不用抄写课文。", "action": "观察家里的一种植物，在观察本上写三句话；三句话分别写颜色、形状和气味，不用抄写课文。"}, {"id": "AGENT-47d69320426840b7989d616b", "child": "顾星禾", "title": "英语：朗读课本第20页对话三遍", "due": "无明确截止", "original_status": "待跟进", "source": "Agent建议:agent-d4ec1446c78687f595c7cfcb3d55f320\\nmessage:fictional-group-20261021-01:m04\\n晨露四年级三班（纯虚构） · 2026-10-21T16:10:00+08:00\\n英语：今晚将课本第20页的对话朗读三遍，请家长听完后在这一页签字，明天早读检查。", "action": "今晚将课本第20页的对话朗读三遍；请家长听完后在这一页签字；明天早读检查。\\n提交要求：家长听完后在第20页签字，明天早读检查。"}, {"id": "AGENT-baef0382d64d3bd88a52f208", "child": "顾星禾", "title": "签字《秋游意见回执》并明早交班主任", "due": "无明确截止", "original_status": "待跟进", "source": "Agent建议:agent-dc09a7753cdbae7cfd2537e64abd48fd\\nmessage:fictional-group-20261021-01:m05\\n晨露四年级三班（纯虚构） · 2026-10-21T16:15:00+08:00\\n请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。另通知：10月23日19:30在本班教室召开家长会，请一位家长参加，孩子不用参加。", "action": "请家长今晚在《秋游意见回执》上签字，由孩子明早交给班主任。"}]}')


class SavedOwnedTimeCopyTests(unittest.TestCase):
    """The untouched r262 save of the same day: Today reads each collected task's own days from its own words with no
    write, and only the existing zero-model reselect collects the meeting whose kept reply day its own words now prove."""
    setUp = native.SchoolNativeCoverageTests.setUp

    def _old_store(self, change=None):
        # No model is configured (no model.json, no FAMILY_LLM_*): these reads and rounds are the zero-model boundary.
        self.stack.enter_context(patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('FAMILY_LLM_')}, clear=True))
        self.now = self.fixture.now = dt.datetime(2026, 10, 21, 16, 40, tzinfo=agent.TZ)
        self.source.update(id=OWNED_TIME_GROUP, name='晨露四年级三班（纯虚构）')
        self.fixture.config()
        with self.store._db() as c:
            for table, rows in SAVED_OWNED_TIME.items():
                c.execute('DELETE FROM ' + table)
                for row in rows:
                    if table == 'manual_tasks':row = dict(row, child='示例甲')  # this fixture's profile name for child-1
                    c.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ','.join(row), ','.join('?' * len(row))), tuple(row.values()))
            if change: change(c)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)
        return self._tables()

    def _tables(self):
        with self.store._db() as c:
            return {t: [dict(r) for r in c.execute('SELECT * FROM %s ORDER BY rowid' % t)]
                    for t in ('agent_items', 'agent_jobs', 'agent_messages', 'agent_sources', 'manual_tasks', 'task_updates', 'records')}

    def _meeting(self, rows):
        return next(r for r in rows['agent_items'] if r['title'].startswith('家长会'))

    def test_the_saved_tasks_read_their_own_days_on_today_without_any_write(self):
        before = self._old_store()
        listed = {x['title']: x['agenda'] for x in self.app.calendar_snapshot('2026-10-21', '2026-10-21')['inbox'] if x['task_id']}
        expected = {'语文：朗读《秋天的小院》第2、3段两遍': ('homework', '', '2026-10-21'), '语文：观察植物写三句话': ('homework', '', '2026-10-21'),
                    '数学：练习册第18页第2、4、6题': ('homework', '', '2026-10-21'),
                    '英语：朗读课本第20页对话三遍': ('homework', '2026-10-21', '2026-10-22'),
                    '签字《秋游意见回执》并明早交班主任': ('todo', '2026-10-21', '2026-10-22')}
        self.assertEqual({t: (a['category'], a['complete_on'], a['due_on']) for t, a in listed.items()}, expected)
        self.assertEqual(listed['英语：朗读课本第20页对话三遍']['due_kind'], 'deadline', 'the check day is no handback')
        today = [x['title'] for x in self.app.calendar_snapshot('2026-10-21', '2026-10-21')['agenda'] if x['task_id']]
        for title in expected:
            self.assertEqual(today.count(title), 1, title)
        self.assertEqual(self._tables(), before, 'reading the page writes nothing')
        self.assertEqual(self.model.call_count, 0)

    def test_the_meeting_its_own_words_date_is_collected_once_on_the_natural_round_without_a_model(self):
        before = self._old_store()
        meeting = self._meeting(before)
        self.assertEqual((meeting['state'], meeting['due'], json.loads(meeting['plan'])['school_unadopted_due']), ('pending', '', '2026-10-23'))
        for i in range(3):
            result = agent.run_once(self.app, self.now + dt.timedelta(minutes=6 * i))
            self.assertEqual(result['failed'], 0, result)
        self.assertEqual(self.model.call_count, 0)
        after = self._tables()
        row = next(r for r in after['agent_items'] if r['id'] == meeting['id'])
        self.assertEqual((row['state'], row['due']), ('accepted', '2026-10-23'))
        plan, old_plan = json.loads(row['plan']), json.loads(meeting['plan'])
        self.assertEqual(plan['school_role_reselect']['previous_row'], meeting, 'the complete old row stays readable')
        for field in ('school_selection_receipt', 'school_generated_snapshot', 'school_date_quote', 'school_unadopted_due'):
            self.assertEqual(plan.get(field), old_plan.get(field), field)
        task = [t for t in after['manual_tasks'] if t['id'] == row['task_id']]
        self.assertEqual([t['due'] for t in task], ['2026-10-23'])
        for words in ('19:30', '一位家长参加', '孩子不用参加'):
            self.assertIn(words, task[0]['title'] + task[0]['action'])
        agenda = {x['task_id']: x['agenda'] for x in self.app.calendar_snapshot('2026-10-23', '2026-10-23')['inbox'] if x['task_id']}
        self.assertEqual(tuple(agenda[row['task_id']][k] for k in ('category', 'due_on', 'due_kind')), ('todo', '2026-10-23', 'event'))
        # Every other saved row, task, original and the batch's own attempts stay as saved; the reference is still reference.
        keep = lambda rows, skip: [r for r in rows if r['id'] not in skip]
        self.assertEqual(keep(after['agent_items'], {meeting['id']}), keep(before['agent_items'], {meeting['id']}))
        self.assertEqual(keep(after['manual_tasks'], {row['task_id']}), before['manual_tasks'])
        self.assertEqual(after['agent_messages'], before['agent_messages'])
        self.assertEqual([j for j in after['agent_jobs'] if j['id'].startswith('messages:')], [j for j in before['agent_jobs'] if j['id'].startswith('messages:')])
        self.assertEqual((after['task_updates'], after['records']), ([], []))
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=30))['created'], 0)
        self.assertEqual(self._tables()['manual_tasks'], after['manual_tasks'], 'reopen and later rounds collect nothing twice')

    def test_a_touched_or_truly_contradicted_meeting_keeps_its_saved_state(self):
        def edited(c):  # a parent edit after generation
            c.execute("UPDATE agent_items SET title=title||'（家长改）' WHERE title LIKE '家长会%'")
        def dismissed(c):
            c.execute("UPDATE agent_items SET state='dismissed' WHERE title LIKE '家长会%'")
        def other_day(c):  # generated with another rejected reply day: a real contradiction stays unknown
            row = dict(c.execute("SELECT * FROM agent_items WHERE title LIKE '家长会%'").fetchone())
            plan = json.loads(row['plan']);plan['school_unadopted_due'] = '2026-10-24'
            plan['school_generated_snapshot'] = agent._school_generated_snapshot(dict(row, plan=plan))
            c.execute('UPDATE agent_items SET plan=? WHERE id=?', (json.dumps(plan, ensure_ascii=False), row['id']))
        for name, change in dict(edited=edited, dismissed=dismissed, other_day=other_day).items():
            with self.subTest(case=name):
                self.setUp()
                before = self._old_store(change)
                for i in range(2):
                    self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=6 * i))['failed'], 0)
                after = self._tables()
                self.assertEqual(self._meeting(after), self._meeting(before), 'kept exactly as saved')
                self.assertEqual(after['manual_tasks'], before['manual_tasks'])
                self.assertEqual(self.model.call_count, 0)


class OwnedEventAndCorrectionTests(unittest.TestCase):
    """Root's two held-out ordinary shapes (fictional, same child and teachers, first sent 2026-10-21 16:20), reply due empty:
    a fixed meeting day (定在) asked of one parent per family while the child need not come, and one teacher's later
    correction of a named form's handback day sent with a cancelled meeting."""
    setUp = native.SchoolNativeCoverageTests.setUp
    MEETING = '家长会定在10月24日14:20，地点是学校报告厅。每家一位家长参加，孩子不用来。'
    ORIGINAL = '请家长10月22日前交回兴趣班回执。10月23日19:00召开家长会。'
    FIX = '更正：兴趣班回执改为10月24日前交回；原定10月23日19:00的家长会取消，不用到校。'

    def run_reply(self, notices, proposals):
        self.setUp()
        self.now = self.fixture.now = dt.datetime(2026, 10, 21, 16, 40, tzinfo=agent.TZ)
        payload, refs = owned_time_payload(self, notices, '2026-10-21T16:19:00+08:00')
        self.store.ingest(payload)
        reply = dict(proposals=[native.fixtures.school_proposal(**dict(p, evidence=[dict(ref=refs[n - 1]) for n in p['evidence']]))
                                for p in proposals])
        self.model.side_effect = lambda *args, **kwargs: copy.deepcopy(reply)
        result = agent.run_once(self.app, self.now)
        with self.store._db() as c:
            errors = [r['error'] for r in c.execute("SELECT error FROM agent_jobs WHERE id LIKE 'messages:%'")]
            rows = {r['title']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
        self.assertEqual((result['failed'], result['processed']), (0, len(notices)), (result, errors))
        return rows, tasks

    def _agenda(self, task_id):
        return {x['task_id']: x['agenda'] for x in self.app.calendar_snapshot('2026-10-21', '2026-10-21')['inbox'] if x['task_id']}[task_id]

    def test_a_fixed_meeting_day_asked_of_one_parent_is_its_event_never_homework(self):
        rows, tasks = self.run_reply([('teacher-class', self.MEETING)], [dict(
            title_quote=self.MEETING, due='', evidence=[1], task_title='家长会', task_goal=self.MEETING, task_state='ready',
            task_reason='老师通知家长会时间、地点和参加人。', task_purpose='admin', task_change='new')])
        row = rows['家长会']
        self.assertEqual((row['state'], row['due']), ('accepted', '2026-10-24'))
        task = tasks[row['task_id']]
        self.assertEqual(task['due'], '2026-10-24')
        for words in ('14:20', '学校报告厅', '每家一位家长参加', '孩子不用来'):
            self.assertIn(words, task['title'] + task['action'])
        agenda = self._agenda(task['id'])
        self.assertEqual((agenda['category'], agenda['due_on'], agenda['due_kind']), ('todo', '2026-10-24', 'event'), 'the meeting is no handback')

    def test_a_fixed_meeting_day_keeps_its_guards(self):
        sent = '2026-10-21'
        for text, expected in [
                (self.MEETING, {'2026-10-24'}),
                ('家长会定在10月24日 14:20，地点是学校报告厅。每家一位家长参加，孩子不用来。', {'2026-10-24'}),
                ('家长会时间待定，地点是学校报告厅。每家一位家长参加，孩子不用来。', set()),
                (self.MEETING + '现通知该家长会取消。', set()),
                ('家长会定在10月24日14:20，地点是学校报告厅。每家一位家长参加，家长不用来。', set()),
                ('家长会定在10月24日14:20，地点是学校报告厅。', set()),
                ('家长会延期到10月24日14:20。每家一位家长参加，孩子不用来。', set()),
                ('家长会定在10月24日14:20，地点是学校报告厅。家长自愿参加，孩子不用来。', set())]:
            with self.subTest(text=text):
                self.assertEqual(family_agenda.event_days(text, sent), expected)

    def correction(self, fix, quote, goal, publishers=('teacher-class', 'teacher-class')):
        meeting = '原定10月23日19:00的家长会取消'
        return self.run_reply([(publishers[0], self.ORIGINAL), (publishers[1], fix)], [
            dict(title_quote=quote, due='', evidence=[1, 2], task_title='交回兴趣班回执', task_goal=goal, task_state='ready',
                 task_reason='同一老师后发更正了交回日期。', task_purpose='admin', task_change='new'),
            dict(title_quote=meeting if meeting in fix else fix[:12], due='', evidence=[1, 2], task_state='reference',
                 task_reason='原定家长会已取消，无需行动。', task_purpose='optional', task_change='new')])

    def test_one_teacher_s_correction_gives_the_named_form_its_corrected_handback_day(self):
        for quote in ('兴趣班回执改为10月24日前交回', '请家长10月22日前交回兴趣班回执'):
            with self.subTest(quote=quote):
                rows, tasks = self.correction(self.FIX, quote, '兴趣班回执改为10月24日前交回。')
                row = rows['交回兴趣班回执']
                self.assertEqual((row['state'], row['due']), ('accepted', '2026-10-24'))
                self.assertEqual([t['due'] for t in tasks.values()], ['2026-10-24'], 'one task; the cancelled meeting is none')
                self.assertEqual(self._agenda(row['task_id'])['due_kind'], 'deadline')

    def test_another_object_teacher_or_an_open_cancelled_or_postponed_change_never_moves_the_day(self):
        cases = [
            # Another object's correction leaves the form's own day; the meeting's 23 is never the form's.
            ('other_object', '更正：作业本改为10月24日前交回；原定10月23日19:00的家长会取消，不用到校。', None, '2026-10-22'),
            ('other_teacher', self.FIX, ('teacher-class', 'teacher-other'), ''),
            ('undated', '更正：兴趣班回执的交回日期另行通知；原定10月23日19:00的家长会取消，不用到校。', None, ''),
            ('cancelled', '更正：兴趣班回执不用交了；原定10月23日19:00的家长会取消，不用到校。', None, ''),
            ('postponed', '更正：兴趣班回执延期交回，时间另行通知。', None, '')]
        for label, fix, publishers, expected in cases:
            with self.subTest(label):
                rows, tasks = self.correction(fix, '请家长10月22日前交回兴趣班回执', '交回兴趣班回执。', publishers or ('teacher-class', 'teacher-class'))
                self.assertEqual(rows['交回兴趣班回执']['due'], expected)
                self.assertFalse({'2026-10-23'} & {t['due'] for t in tasks.values()})


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


def saved_recovered_state(path):
    """The app's own state and 2026-10-19 calendar after the R09 reread saved the English paragraph (mocked transport)."""
    case = RecoveredParagraphCardTests('test_the_recovered_paragraph_reads_as_its_own_sentences_and_stays_saved_byte_for_byte')
    case.setUp()
    try:
        ids, _ = case.save_recovered()
        state = case.app.snapshot()
        state['saved_calendar'] = case.app.calendar_snapshot('2026-10-19', '2026-10-19')
        state['recovered_ids'] = ids
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, default=str)
    finally:
        case.doCleanups()


def saved_owned_time_state(path):
    """The app's own state and 2026-10-21..23 calendar after Root's six frozen notices are saved from the actual trial29 reply."""
    case = OrdinaryOwnedTimeTests('test_the_frozen_reply_saves_four_homework_and_two_parent_items_on_their_own_days')
    case.setUp()
    try:
        ids = case.save_day()[0]
        state = case.app.snapshot()
        state['saved_calendar'] = case.app.calendar_snapshot('2026-10-21', '2026-10-23')
        state['owned_time_ids'] = ids
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
    elif sys.argv[1:2] == ['--saved-recovered-state']:
        saved_recovered_state(sys.argv[2])
    elif sys.argv[1:2] == ['--saved-owned-time-state']:
        saved_owned_time_state(sys.argv[2])
    else:
        unittest.main()
