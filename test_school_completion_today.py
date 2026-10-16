"""Own-original completion day for the known fictional six school messages; no real model, collectors or devices.

The saved parsed reply is the earlier fictional replay receipt, used only as a fixed local seam. Today must list the work
the item's own words give to its sending day (今天/今晚) on that day, while the same task keeps its handback due.
"""
import copy
import datetime as dt
import json
import unittest

import family_agenda
import family_agent as agent
import test_school_native_coverage as native

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


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['--saved-h01-state']:
        saved_h01_state(sys.argv[2])
    else:
        unittest.main()
