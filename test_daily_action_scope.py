"""A day's list separates read actions from school material still to be organized, and each date keeps its own role.

Wholly fictional children, messages and tasks (no family record, no model, no collector). One shared server projection
(family_agenda.day_view through app.day_view / state.today_view) gives the Web and Mac lists the same rows and counts."""
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import datetime as dt
import app
import family_agenda as agenda

DAY = '2026-11-19'
C, D = 'child-dev-c', 'child-dev-d'
# (key, title, saved brief, published day): pending school rows exactly as an organizer would have saved them.
PENDING = [
    ('unknown-unread-material', '体育：资料内容待整理', dict(state='review', purpose='unknown', policy=9, title='', goal=''), '2026-09-05'),
    ('known-undated-review-action', '体育：定点投球', dict(state='review', purpose='learning', policy=10, title='体育：定点投球',
                                                     goal='站在线后定点投球6次。', reason='附件中的动作细节尚未读清。'), '2026-09-06'),
    ('today-known-action-unread-detail', '体育：绕圈慢跑', dict(state='review', purpose='learning', policy=10, title='体育：绕圈慢跑',
                                                          goal='今晚慢跑2圈。', reason='附件中热身示范尚未读清。'), DAY),
    ('reference-with-unread-original', '体育：课堂参考', dict(state='review', purpose='optional', policy=10, title='', goal=''), '2026-11-18'),
]
MATERIAL = {'体育：资料内容待整理', '体育：课堂参考'}


class ActionScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); data = root / 'private'; data.mkdir()
        (root / '家庭运行规则.md').write_text('| child-dev-c | 虚构孩子丙 | 男 | 10岁 | 四年级 |\n| child-dev-d | 虚构孩子丁 | 女 | 9岁 | 三年级 |\n')
        ledger = ''.join(f'| {p}{tid} | {name} | {title} | {due} | 待跟进 | 虚构学校通知 | {action} |\n'
                         for p, name in (('', '虚构孩子丙'), ('D-', '虚构孩子丁'))
                         for tid, title, due, action in (('DEV-PE-01', '体育：跳绳练习', '无明确截止', '双脚并拢跳绳80下。'),
                                                         ('DEV-CN-02', '语文：阅读记录签字', '2026-11-18', '阅读第3页并请家长签字。')))
        (root / '跟踪台账.md').write_text(ledger)
        p = patch.multiple(app, ROOT=root, DATA=data, DB=data / 'family.sqlite3'); p.start(); self.addCleanup(p.stop)
        self.store = app.agent_store()
        for child in (C, D):  # the same titles for the other child are the cross-child control
            for key, title, brief, published in PENDING:
                plan = dict(school_task=dict(brief, change='new', target_id=''), school_learning=dict(subject='体育', goal_id=''))
                self.store._save(f'dev-{child}-{key}', f'fp-{child}-{key}', [dict(child_id=child, kind='school', title=title,
                                 body=brief['goal'] or '请核对这条学校消息。', due='', evidence=[], plan=plan)],
                                 dt.datetime.fromisoformat(published + 'T12:00:00+08:00'))

    @staticmethod
    def listed(view):
        return [i for g in view['groups'] for i in g['items']]

    @staticmethod
    def every_id(view):
        return ({i['id'] for g in view['groups'] + view['closed'] for i in g['items']} | {u['id'] for u in view['upcoming']}
                | {m['id'] for g in view['materials'] for m in g['items']})

    def test_material_leaves_the_days_actions_while_read_actions_stay(self):
        with app.connect() as c: before = '\n'.join(c.iterdump())
        for day in (DAY, '2026-11-20'):  # the next day lists the same, nothing grows into new work
            view = app.day_view(C, day)
            rows = {i['title']: i for i in self.listed(view)}
            material = {m['title']: (g['subject'], m) for g in view['materials'] for m in g['items']}
            with self.subTest(day=day):
                self.assertEqual(set(material), MATERIAL, 'unknown/unread material and a reference are named, not listed as actions')
                self.assertFalse(MATERIAL & set(rows))
                self.assertTrue(all(s == '体育' for s, _ in material.values()), material)
                self.assertEqual(view['counts']['material'], 2)
                self.assertEqual(view['counts']['open'], len(rows), 'the day count is its listed actions only')
                # A read action with unread detail stays visible as an action awaiting review, with its read goal only.
                for title, goal in (('体育：定点投球', '站在线后定点投球6次。'), ('体育：绕圈慢跑', '今晚慢跑2圈。')):
                    self.assertTrue(rows[title]['pending_review'], title)
                    self.assertIn(goal, rows[title]['lines'])
                    self.assertNotIn('material', rows[title])
                self.assertEqual(rows['体育：定点投球']['when'], 'unknown')
                self.assertFalse(rows['体育：定点投球']['today'])
                # The legacy undated ready task: same id and content, date unknown, never today, never dropped for age.
                pe = rows['体育：跳绳练习']
                self.assertEqual((pe['task_id'], pe['when'], pe['today'], pe['lines']), ('DEV-PE-01', 'unknown', False, ['双脚并拢跳绳80下。']))
                self.assertFalse(next(f for f in pe['facts'] if f['role'] == 'due')['known'])
                # The open handback stays overdue on its original date with the same id.
                cn = rows['语文：阅读记录签字']
                self.assertEqual((cn['task_id'], cn['when']), ('DEV-CN-02', 'overdue'))
                self.assertEqual(next(f for f in cn['facts'] if f['role'] == 'due')['value'], '2026-11-18')
                group = next(g for g in view['groups'] if g['subject'] == '体育')
                self.assertEqual(group['undated'], sum(i['when'] == 'unknown' for i in group['items']))
                self.assertGreaterEqual(group['undated'], 2)
                # Nothing invented for material: its saved title is all it shows; no requirement is generated for it.
                words = json.dumps(view, ensure_ascii=False)
                self.assertNotIn('跑步', words); self.assertNotIn('家长确认是否完成', words)
                # Cross-child: the other child's copies appear nowhere in this child's day, and the reverse.
                other = app.day_view(D, day)
                self.assertFalse(self.every_id(view) & self.every_id(other))
                self.assertEqual({m['title'] for g in other['materials'] for m in g['items']}, MATERIAL)
        with app.connect() as c:
            self.assertEqual(before, '\n'.join(c.iterdump()), 'reading a day writes nothing')
            states = {r['title']: r['state'] for r in c.execute("SELECT title,state FROM agent_items WHERE child_id=?", (C,))}
        self.assertEqual(states, {title: 'pending' for _k, title, _b, _p in PENDING}, 'every original pending row is kept as it was')
        inbox = [x for x in app.calendar_snapshot(DAY, DAY)['inbox'] if C in x['child_ids'] and x['kind'] == 'school']
        self.assertEqual({x['title'] for x in inbox}, {t for _k, t, _b, _p in PENDING}, 'material stays in the school inbox')

    def test_web_and_mac_read_one_projection(self):
        snap = app.snapshot(); today = snap['today']
        for child in (C, D):
            view = app.day_view(child, today)
            shared = snap['today_view'][child]
            for key in ('groups', 'materials', 'counts', 'upcoming'):
                self.assertEqual(view[key], shared[key], key)
        js = Path(app.__file__).with_name('calendar.js').read_text()
        sources = Path(app.__file__).parent / 'packaging' / 'macos' / 'Sources'
        swift = (sources / 'Workspace.swift').read_text() + (sources / 'WorkspaceAPI.swift').read_text()
        for words in ('已过', '日期未定', '学校资料待整理，不算当天要做：'):
            self.assertIn(words, js); self.assertIn(words, swift)
        self.assertIn('view.materials', js); self.assertIn('g.undated', js); self.assertIn("passed:'已过'", js)
        self.assertIn('let materials: [MaterialGroup]?', swift); self.assertIn('let undated: Int?', swift)
        self.assertIn('"passed": "已过"', swift)
        self.assertNotRegex(js, re.escape('${g.items.length} 项</span>'), 'a subject tag no longer counts undated rows as the day')


def school_row(id, title, subject, due='', kind='', **dates):
    a = dict(published_on='2026-11-09', due_on=due, scheduled_on='', complete_on='', submit_on='', subjects=[subject], subject_state='known',
             **({'due_kind': kind} if kind else {}), **dates)
    return dict(id=id, task_id=id, kind='task', child_ids=[C], title=title, agenda=a, status='待跟进', closed=False, closed_on='', body=title)


class DateRoleTest(unittest.TestCase):
    """Friday's PE lesson (bring a clean shoe bag) is a lesson day: on Saturday it has passed. Friday's signed-receipt
    handback still open is overdue on Saturday, same id and date. The row role and its due fact say the same."""
    child = dict(id=C, name='虚构孩子丙')

    def view(self, inbox, day, tasks=()):
        return agenda.day_view(inbox, list(tasks) or [dict(id=x['task_id'], child='虚构孩子丙', title=x['title']) for x in inbox if x['task_id']],
                               [], self.child, day, day, 'synthetic-wrong')

    def test_past_lesson_day_has_passed_and_open_handback_stays_overdue(self):
        inbox = [school_row('DEV-PE-SHOES', '体育：带干净鞋袋', '体育', '2026-11-13', 'arranged'),
                 school_row('DEV-CN-RECEIPT', '语文：交回签字回执', '语文', '2026-11-13', 'handback'),
                 school_row('DEV-SCI-DEADLINE', '科学：观察记录', '科学', '2026-11-13')]
        friday = {i['id']: i for g in self.view(inbox, '2026-11-13')['groups'] for i in g['items']}
        self.assertEqual({k: v['when'] for k, v in friday.items()}, dict.fromkeys(friday, 'today'))
        saturday = self.view(inbox, '2026-11-14')
        rows = {i['id']: i for g in saturday['groups'] for i in g['items']}
        self.assertEqual({k: v['when'] for k, v in rows.items()},
                         {'DEV-PE-SHOES': 'passed', 'DEV-CN-RECEIPT': 'overdue', 'DEV-SCI-DEADLINE': 'overdue'})
        self.assertEqual((saturday['counts']['overdue'], saturday['counts']['passed'], saturday['counts']['today']), (2, 1, 0))
        for r in rows.values():
            due = next(f for f in r['facts'] if f['role'] == 'due')
            self.assertEqual(due['value'], '2026-11-13')
            self.assertEqual(due['state'] == 'passed', r['when'] == 'passed', r['id'])
            self.assertEqual(due['state'] == 'overdue', r['when'] == 'overdue', r['id'])
        self.assertEqual(list(rows)[-1], 'DEV-PE-SHOES', 'a passed lesson day sorts after open work')
        self.assertEqual([x['agenda']['due_on'] for x in inbox], ['2026-11-13'] * 3, 'no saved date changes')
        # Closed, the overdue handback leaves the open list and stays findable on the day it was closed.
        done = [dict(x, closed=True, status='已完成', closed_on='2026-11-14') if x['id'] == 'DEV-CN-RECEIPT' else x for x in inbox]
        closed_view = self.view(done, '2026-11-14')
        self.assertNotIn('DEV-CN-RECEIPT', {i['id'] for g in closed_view['groups'] for i in g['items']})
        self.assertIn('DEV-CN-RECEIPT', {i['id'] for g in closed_view['closed'] for i in g['items']})

    def test_parent_plan_and_saved_progress_keep_the_same_task(self):
        plan = school_row('DEV-PE-01', '家长自定练习标题', '体育', scheduled_on=DAY)
        progress = dict(feedback=1, wrong=1)
        tasks = [dict(id='DEV-PE-01', child='虚构孩子丙', title='家长自定练习标题', focus=dict(version=1, scheduled_on=DAY), progress=progress)]
        row = next(i for g in self.view([plan], DAY, tasks)['groups'] for i in g['items'])
        self.assertEqual((row['task_id'], row['title'], row['when'], row['today'], row['progress']),
                         ('DEV-PE-01', '家长自定练习标题', 'today', True, progress))
        undated = school_row('DEV-PE-01', '体育：跳绳练习', '体育')
        later = self.view([undated], '2026-12-31', [dict(tasks[0], title='体育：跳绳练习')])
        row = next(i for g in later['groups'] for i in g['items'])
        self.assertEqual((row['task_id'], row['when'], row['progress']), ('DEV-PE-01', 'unknown', progress), 'never dropped for age')
        self.assertEqual((later['groups'][0]['undated'], later['counts']['today']), (1, 0))


if __name__ == '__main__':
    unittest.main()
