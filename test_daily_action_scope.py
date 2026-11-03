"""A day's list separates read actions from school material still to be organized, and each date keeps its own role.

Wholly fictional children, messages and tasks (no family record, no model, no collector). One shared server projection
(family_agenda.day_view through app.day_view / state.today_view) gives the Web and Mac lists the same rows and counts."""
from http.client import HTTPConnection
import json
from pathlib import Path
import re
import tempfile
import threading
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
    # Voluntary/reference with a read goal is still no required work (the organizer keeps optional out of 必做).
    ('optional-read-goal', '体育：节奏讲解', dict(state='review', purpose='optional', policy=10, title='体育：节奏讲解', goal='看这份节奏讲解。',
                                              reason='附件里有未读内容。'), DAY),
]
MATERIAL = {'体育：资料内容待整理', '体育：课堂参考', '体育：节奏讲解'}


class ActionScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); data = root / 'private'; data.mkdir()
        (root / '家庭运行规则.md').write_text('| child-dev-c | 虚构孩子丙 | 男 | 10岁 | 四年级 |\n| child-dev-d | 虚构孩子丁 | 女 | 9岁 | 三年级 |\n')
        ledger = ''.join(f'| {p}{tid} | {name} | {title} | {due} | 待跟进 | 虚构学校通知 | {action} |\n'
                         for p, name in (('', '虚构孩子丙'), ('D', '虚构孩子丁'))  # ledger ids are [A-Z]+digits: PE01 = DEV-PE-01
                         for tid, title, due, action in (('PE01', '体育：跳绳练习', '无明确截止', '双脚并拢跳绳80下。'),
                                                         ('CN02', '语文：阅读记录签字', '2026-11-18', '阅读第3页并请家长签字。')))
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
                | {m['id'] for g in view['materials'] for m in g['items']} | {i['id'] for g in view['undated'] for i in g['items']})

    def test_material_leaves_the_days_actions_while_read_actions_stay(self):
        with app.connect() as c: before = '\n'.join(c.iterdump())
        for day in (DAY, '2026-11-20'):  # the next day lists the same, nothing grows into new work
            view = app.day_view(C, day)
            rows = {i['title']: i for i in self.listed(view)}
            kept = {i['title']: i for g in view['undated'] for i in g['items']}  # 日期未定/待安排: same rows, not the day's count
            material = {m['title']: (g['subject'], m) for g in view['materials'] for m in g['items']}
            with self.subTest(day=day):
                self.assertEqual(set(material), MATERIAL, 'unknown/unread material and a reference are named, not listed as actions')
                self.assertFalse(MATERIAL & set(rows))
                self.assertTrue(all(s == '体育' for s, _ in material.values()), material)
                self.assertEqual(view['counts']['material'], 3)
                self.assertEqual(view['counts']['open'], len(rows), 'the day count is its listed actions only')
                # A read action with unread detail stays visible as an action awaiting review, with its read goal only.
                for title, goal in (('体育：定点投球', '站在线后定点投球6次。'), ('体育：绕圈慢跑', '今晚慢跑2圈。')):
                    row = rows.get(title) or kept[title]
                    self.assertTrue(row['pending_review'], title)
                    self.assertIn(goal, row['lines'])
                    self.assertNotIn('material', row)
                self.assertNotIn('体育：定点投球', rows)
                self.assertEqual(kept['体育：定点投球']['when'], 'unknown')
                self.assertFalse(kept['体育：定点投球']['today'])
                # The legacy undated ready task: same id and content, date unknown, never today, never dropped for age.
                self.assertNotIn('体育：跳绳练习', rows, 'an undated action is not laid out in the day\'s list')
                pe = kept['体育：跳绳练习']
                self.assertEqual((pe['task_id'], pe['when'], pe['today'], pe['lines']), ('PE01', 'unknown', False, ['双脚并拢跳绳80下。']))
                self.assertFalse(next(f for f in pe['facts'] if f['role'] == 'due')['known'])
                # The open handback stays overdue on its original date with the same id.
                cn = rows['语文：阅读记录签字']
                self.assertEqual((cn['task_id'], cn['when']), ('CN02', 'overdue'))
                self.assertEqual(next(f for f in cn['facts'] if f['role'] == 'due')['value'], '2026-11-18')
                self.assertEqual(view['counts']['undated'], len(kept))
                self.assertLessEqual({'体育：定点投球', '体育：跳绳练习'}, set(kept))
                self.assertTrue(all(g['subject'] == '体育' for g in view['undated']))
                self.assertFalse([i['id'] for i in self.listed(view) if i['when'] in ('unknown', 'passed')])
                self.assertFalse(view['counts']['unknown'] or view['counts']['passed'])
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

    def test_http_day_is_the_same_projection_and_writes_nothing(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        with app.connect() as c: before = '\n'.join(c.iterdump())
        conn = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        try:
            with patch.object(app.family_llm, '_chat_json', side_effect=AssertionError('no model when reading a day')):
                conn.request('GET', f'/api/day?child_id={C}&day={DAY}'); r = conn.getresponse(); code, wire = r.status, json.loads(r.read())
        finally: conn.close()
        self.assertEqual(code, 200, wire)
        local = app.day_view(C, DAY)
        for key in ('groups', 'undated', 'materials', 'counts', 'upcoming', 'week'):
            self.assertEqual(wire[key], local[key], key)
        # The day's work is the overdue handback; the three undated actions are kept apart under 日期未定, by the same ids.
        self.assertEqual((wire['counts']['material'], wire['counts']['open'], wire['counts']['undated']), (3, 1, 3))
        self.assertIn('PE01', {i['task_id'] for g in wire['undated'] for i in g['items']})
        with app.connect() as c: self.assertEqual(before, '\n'.join(c.iterdump()), 'GET /api/day writes nothing')

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
        # The day's lessons and plans belong to 待办 only; scope change keeps the review hold.
        self.assertIn('if !store.showDone && !store.showUndated { scheduleSection }', swift)
        self.assertIn('func setScope(_ key: String) {\n        if reviewHold() { return }', swift)
        self.assertNotRegex(js, re.escape('${g.items.length} 项</span>'), 'a subject tag no longer counts undated rows as the day')


def school_row(id, title, subject, due='', kind='', **dates):
    a = dict(published_on='2026-11-09', due_on=due, scheduled_on='', complete_on='', submit_on='', subjects=[subject], subject_state='known')
    a.update(dates)
    if kind: a['due_kind'] = kind
    return dict(id=id, task_id=id, kind='task', child_ids=[C], title=title, agenda=a, status='待跟进', closed=False, closed_on='', body=title)


def pending_row(id, title, body, material=False, **dates):
    """A pending school row as family_agenda.snapshot gives it (school_material only when its saved brief has no read action)."""
    row = dict(school_row(id, title, '体育', **dates), task_id='', kind='school', status='待核对', body=body)
    return dict(row, school_material=True) if material else row


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
        # The lesson day is that day's history (listed on Friday with the same id), no open work on Saturday; deadline and
        # handback stay overdue there. The shared role still names the passed day 已过.
        self.assertEqual({k: v['when'] for k, v in rows.items()}, {'DEV-CN-RECEIPT': 'overdue', 'DEV-SCI-DEADLINE': 'overdue'})
        self.assertIn('DEV-PE-SHOES', friday)
        self.assertNotIn('DEV-PE-SHOES', {i['id'] for g in saturday['undated'] + saturday['closed'] for i in g['items']})
        self.assertEqual(agenda.day_role(inbox[0]['agenda'], '2026-11-14'), 'passed')
        self.assertEqual((saturday['counts']['overdue'], saturday['counts']['passed'], saturday['counts']['today'], saturday['counts']['open']), (2, 0, 0, 2))
        for r in rows.values():
            due = next(f for f in r['facts'] if f['role'] == 'due')
            self.assertEqual(due['value'], '2026-11-13')
            self.assertEqual(due['state'] == 'passed', r['when'] == 'passed', r['id'])
            self.assertEqual(due['state'] == 'overdue', r['when'] == 'overdue', r['id'])
        self.assertEqual([x['agenda']['due_on'] for x in inbox], ['2026-11-13'] * 3, 'no saved date changes')
        # Closed, the overdue handback leaves the open list and stays findable on the day it was closed.
        done = [dict(x, closed=True, status='已完成', closed_on='2026-11-14') if x['id'] == 'DEV-CN-RECEIPT' else x for x in inbox]
        closed_view = self.view(done, '2026-11-14')
        self.assertNotIn('DEV-CN-RECEIPT', {i['id'] for g in closed_view['groups'] for i in g['items']})
        self.assertIn('DEV-CN-RECEIPT', {i['id'] for g in closed_view['closed'] for i in g['items']})

    def test_tonight_action_with_unread_detail_is_todays_work_and_material_is_not(self):
        inbox = [pending_row('agent-run', '体育：绕圈慢跑', '今晚慢跑2圈。', published_on=DAY, complete_on=DAY),
                 pending_row('agent-material', '体育：资料内容待整理', '请核对这条学校消息。', material=True, published_on=DAY)]
        view = self.view(inbox, DAY)
        rows = {i['id']: i for g in view['groups'] for i in g['items']}
        self.assertEqual(list(rows), ['agent-run'])
        run = rows['agent-run']
        self.assertEqual((run['when'], run['today'], run['pending_review'], run['lines']), ('today', True, True, ['今晚慢跑2圈。']))
        self.assertEqual(next(f for f in run['facts'] if f['role'] == 'complete')['value'], DAY, 'complete day unchanged')
        self.assertEqual((view['counts']['today'], view['counts']['open'], view['counts']['material']), (1, 1, 1))
        self.assertEqual(view['materials'], [dict(subject='体育', items=[dict(id='agent-material', title='体育：资料内容待整理', published_at='')])])
        self.assertEqual([w['today'] for w in [view['counts']]], [1])

    def test_parent_plan_and_saved_progress_keep_the_same_task(self):
        plan = school_row('DEV-PE-01', '家长自定练习标题', '体育', scheduled_on=DAY)
        progress = dict(feedback=1, wrong=1)
        tasks = [dict(id='DEV-PE-01', child='虚构孩子丙', title='家长自定练习标题', focus=dict(version=1, scheduled_on=DAY), progress=progress)]
        row = next(i for g in self.view([plan], DAY, tasks)['groups'] for i in g['items'])
        self.assertEqual((row['task_id'], row['title'], row['when'], row['today'], row['progress']),
                         ('DEV-PE-01', '家长自定练习标题', 'today', True, progress))
        undated = school_row('DEV-PE-01', '体育：跳绳练习', '体育')
        later = self.view([undated], '2026-12-31', [dict(tasks[0], title='体育：跳绳练习')])
        row = next(i for g in later['undated'] for i in g['items'])  # kept under 日期未定 with its progress, never dropped for age
        self.assertEqual((row['task_id'], row['when'], row['progress']), ('DEV-PE-01', 'unknown', progress), 'never dropped for age')
        self.assertEqual((later['counts']['undated'], later['counts']['today'], later['counts']['open']), (1, 0, 0))


if __name__ == '__main__':
    unittest.main()


class RealChainDateRoleTest(unittest.TestCase):
    """Store.ingest -> run_once with a fixed fictional reply (not model output) -> saved agenda -> the day list."""
    def setUp(self):
        import test_school_date_role as role
        self.role = role; self.case = role.SchoolDateRoleTests('run_one'); self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def one(self, text, purpose, due, sent, days):
        import copy
        import family_agent as agent
        self.case.setUp()  # one original per fresh fictional store
        c = self.case; c.fixture.source.update(self.role.SOURCE); c.fixture.config()
        c.fixture.now = c.now = dt.datetime.fromisoformat(sent).replace(tzinfo=agent.TZ) + dt.timedelta(minutes=30)
        payload = c.fixture.payload(cursor='1')
        payload['messages'] = [dict(id='1', time=sent, kind='text', sender='虚构老师', text=text, unread=False,
                                    sender_id='qa-teacher-day-scope', message_order='1')]
        c.store.ingest(payload)
        proposal = dict(title_quote=text, focus='school', due=due, evidence=[{'ref': 'message:%s:1' % self.role.SOURCE['id']}],
                        learning_subject='', learning_goal_id='', task_title=text[:16], task_goal=text, task_advice='', task_change='new',
                        task_target_id='', task_state='ready', task_reason='纯虚构固定回复，不是模型产物。', task_purpose=purpose, task_submission='')
        c.model.side_effect = lambda *args, **kwargs: dict(proposals=[copy.deepcopy(proposal)])
        self.assertEqual(agent.run_once(c.app, c.now)['failed'], 0)
        with c.store._db() as db:
            row = dict(db.execute("SELECT * FROM agent_items WHERE kind='school'").fetchone())
        with c.app.connect() as db:
            agenda = {t['id']: t for t in c.app.tasks(db)}[row['task_id']]['agenda']
        return row, agenda, {d: c.app.day_view(row['child_id'], d) for d in days}

    def ids(self, view, key):
        return {i['task_id'] or i['id'] for g in view[key] for i in g['items']}

    def task(self, task_id):
        with self.case.app.connect() as db:
            return {t['id']: t for t in self.case.app.tasks(db)}[task_id]

    def test_open_homework_past_its_own_completion_and_check_day_stays_overdue_work(self):
        row, a, v = self.one('11月17日今晚朗读2遍，11月18日早读检查。', 'learning', '2026-11-18', '2026-11-17T16:00:00+08:00',
                             ('2026-11-17', '2026-11-19'))
        self.assertEqual((a['complete_on'], a['due_on'], a['due_kind'], a['category']), ('2026-11-17', '2026-11-18', 'inspection', 'homework'))
        self.assertIn(row['task_id'], self.ids(v['2026-11-17'], 'groups'), 'its own work day')
        late = {i['task_id']: i for g in v['2026-11-19']['groups'] for i in g['items']}
        self.assertIn(row['task_id'], late, 'unfinished homework with a real completion day is not lost when its check day passes')
        self.assertNotIn(row['task_id'], self.ids(v['2026-11-19'], 'undated') | self.ids(v['2026-11-19'], 'closed'))
        r = late[row['task_id']]; facts = {f['role']: f for f in r['facts']}
        self.assertEqual((r['when'], facts['complete']['value'], facts['due']['value'], facts['due']['kind'], facts['due']['label'], facts['due']['state']),
                         ('overdue', '2026-11-17', '2026-11-18', 'inspection', '检查', 'overdue'))
        self.assertEqual(self.task(row['task_id'])['original_status'], '待跟进', 'the list changes no row')

    def test_past_arranged_day_is_history_until_the_parent_keeps_it_open_with_a_due_review(self):
        import family_task_focus as focus
        row, a, v = self.one('11月18日美术课带彩纸。', 'admin', '2026-11-18', '2026-11-17T16:00:00+08:00', ('2026-11-18', '2026-11-19'))
        self.assertEqual(a['due_on'], '2026-11-18'); self.assertIn(a['due_kind'], agenda.PASSED_KINDS)
        self.assertIn(row['task_id'], self.ids(v['2026-11-18'], 'groups'))
        bare = v['2026-11-19']
        self.assertNotIn(row['task_id'], self.ids(bare, 'groups') | self.ids(bare, 'undated'), 'a bare past lesson day is its own day\'s history')

        class Noon(dt.datetime):
            @classmethod
            def now(cls, tz=None): return dt.datetime(2026, 11, 19, 12, 0, tzinfo=tz)
        with patch.object(focus.dt, 'datetime', Noon):
            focus.save(self.case.app, dict(id=row['task_id'], version=self.task(row['task_id'])['focus']['version'], request_key='synthetic-art-paper-waiting',
                                           mode='waiting', next_action='', waiting_for='学校回复', review_on='2026-11-19'))
        task = self.task(row['task_id'])
        self.assertEqual((task['focus']['mode'], task['focus']['waiting_for'], task['focus']['review_on'], task['original_status']), ('waiting', '学校回复', '2026-11-19', '待跟进'))
        for day in ('2026-11-19', '2026-11-20'):
            view = self.case.app.day_view(row['child_id'], day)
            listed = {i['task_id']: i for g in view['groups'] for i in g['items']}
            self.assertIn(row['task_id'], listed, 'the parent\'s due review keeps it in the day\'s work')
            r = listed[row['task_id']]; due = next(f for f in r['facts'] if f['role'] == 'due')
            self.assertEqual((r['when'], due['value'], due['state'], due['label']), ('earlier', '2026-11-18', 'passed', agenda.DUE_LABELS[a['due_kind']]))
            self.assertNotIn('2026-11-19', [f.get('value') for f in r['facts']], 'the review day is no school date')
        self.assertEqual(self.case.app.day_view(row['child_id'], '2026-11-18')['counts']['today'], 1, 'its own day unchanged')

    def test_d2_an_evening_counted_exercise_keeps_tonight_and_its_next_morning_check(self):
        text = '体育作业：今晚原地高抬腿30次，每10次休息半分钟；明早体育课检查。'
        row, a, v = self.one(text, 'learning', '2026-11-04', '2026-11-03T16:00:00+08:00', ('2026-11-03', '2026-11-04'))
        self.assertTrue(row['task_id'], 'one saved task, not a pending card without dates')
        self.assertEqual((a['complete_on'], a['due_on']), ('2026-11-03', '2026-11-04'), 'done tonight, checked at the next morning lesson')
        self.assertIn(row['task_id'], self.ids(v['2026-11-03'], 'groups'), 'tonight is its work day')
        self.assertNotIn(row['task_id'], self.ids(v['2026-11-03'], 'undated'))
        self.assertIn(row['task_id'], self.ids(v['2026-11-04'], 'groups'), 'its check day lists the same task')
        with self.case.app.connect() as db:
            task = {t['id']: t for t in self.case.app.tasks(db)}[row['task_id']]
        self.assertEqual(a['due_kind'], 'inspection', 'the next-morning lesson check, not a handback')
        self.assertIn('30次', task['action']); self.assertIn('每10次休息半分钟', task['action'])  # the saved original words keep quantity and rest

    # 明晚…；后天…检查: the later evening's own work clause is its completion day, the check its due (never tonight).
    def test_d2_not_tonight_an_evening_exercise_keeps_its_own_work_day(self):
        later, a, v = self.one('体育作业：明晚原地高抬腿30次；后天体育课检查。', 'learning', '2026-11-05', '2026-11-03T16:00:00+08:00', ('2026-11-03', '2026-11-04'))
        self.assertEqual((a['complete_on'], a['due_on']), ('2026-11-04', '2026-11-05'), 'not tonight: 明晚 is its own work day')
        self.assertNotIn(later['task_id'], self.ids(v['2026-11-03'], 'undated'))
        self.assertIn(later['task_id'], self.ids(v['2026-11-04'], 'groups'))

    # 明晚按四拍节奏拍手3组: an ordinary method opening the counted work keeps 明晚 its own completion day, the lesson its check.
    def test_d2_a_method_led_counted_exercise_keeps_its_own_later_work_day(self):
        import family_agenda as fa, family_agent as agent
        text = '音乐作业：明晚按四拍节奏拍手3组，每组8拍；11月16日音乐课检查。'
        row, a, v = self.one(text, 'learning', '2026-11-16', '2026-11-12T16:00:00+08:00', ('2026-11-12', '2026-11-13', '2026-11-16'))
        self.assertTrue(row['task_id'], 'one saved task, not a pending card without dates')
        self.assertEqual((a['complete_on'], a['due_on'], a['due_kind']), ('2026-11-13', '2026-11-16', 'inspection'))
        self.assertIn(row['task_id'], self.ids(v['2026-11-13'], 'groups'), '明晚 is its own work day')
        self.assertIn(row['task_id'], self.ids(v['2026-11-16'], 'groups'), 'its check day lists the same task')
        self.assertNotIn(row['task_id'], self.ids(v['2026-11-12'], 'undated'))
        task = self.task(row['task_id']); self.assertIn('按四拍节奏拍手3组', task['action']); self.assertIn('每组8拍', task['action'])
        T, sent = '2026-11-12T16:00:00+08:00', '2026-11-12'
        self.assertEqual(fa.deadlines('明晚按四拍节奏拍手3组。', sent), {'2026-11-13'})
        self.assertEqual(fa.completion_day('音乐作业：今晚按四拍节奏拍手3组，每组8拍；明天音乐课检查。', '音乐作业', T, '2026-11-13'), sent)
        for text in ('今晚不用按四拍节奏拍手3组；明天音乐课检查。', '今晚按四拍节奏拍了3组；明天音乐课检查。', '今晚按四拍节奏已拍手3组；明天音乐课检查。'):
            self.assertEqual(fa.completion_day(text, '', T, '2026-11-13'), '', text)
        for text in ('明晚不用按四拍节奏拍手3组。', '明晚按四拍节奏拍了3组。', '明晚按明天的节奏拍手3组。', '今晚或明晚按四拍节奏拍手3组。',
                     '明晚按四拍节奏拍手3组吗？'):
            self.assertNotIn('2026-11-13', fa.deadlines(text, sent), text)
        # A condition in an earlier clause is the role reader's guard (below); the calendar tie reads it as the plain name does.
        self.assertEqual(fa.deadlines('如果下雨，明晚按四拍节奏拍手3组。', sent), fa.deadlines('如果下雨，明晚拍手3组。', sent))
        for quote in ('明晚不用按四拍节奏拍手3组；11月16日音乐课检查。', '明晚按四拍节奏拍了3组；11月16日音乐课检查。',
                      '如果下雨，明晚按四拍节奏拍手3组；11月16日音乐课检查。', '今晚或明晚按四拍节奏拍手3组；11月16日音乐课检查。',
                      '明晚按四拍节奏拍手3组吗？11月16日音乐课检查。', '明晚按四拍节奏拍手3组。'):
            self.assertNotIn('2026-11-13', (agent._school_role_days(quote, [dict(text=quote, time=T)], []) or (set(),))[0], quote)

    def test_d2_guards_a_counted_exercise_reads_no_day_it_does_not_state(self):
        import family_agenda as fa, family_agent as agent
        sent = '2026-11-03'
        self.assertEqual(fa.deadlines('今晚原地高抬腿30次，每10次休息半分钟；明早体育课检查。', sent), {'2026-11-03'})
        self.assertEqual(fa.deadlines('明早交。', sent), {'2026-11-04'}, '明早 is the next day as 明天早上 is')
        self.assertEqual(fa.deadlines('明晚跳绳100下。', sent), {'2026-11-04'})
        for text in ('今晚不用原地高抬腿30次。', '今晚或明晚跳绳100下。', '今晚有3次机会。', '今晚已练30次。', '今晚练了30次。',
                     '今晚第2次提醒。', '今晚原地高抬腿30次吗？', '每10次休息半分钟。'):
            self.assertEqual(fa.deadlines(text, sent), set(), text)
        quote = '今晚原地高抬腿30次，每10次休息半分钟；明早体育课检查。'
        self.assertEqual(agent._school_role_days(quote, [dict(text=quote, time='2026-11-03T16:00:00+08:00')], []), ({'2026-11-03'}, '2026-11-04'))
        for quote in ('明晚不用跳绳100下；后天体育课检查。', '明晚别跳绳100下；后天体育课检查。', '如果下雨，明晚跳绳100下；后天体育课检查。',
                      '明晚跳绳100下，后天或大后天检查。', '明晚有3次机会；后天检查。', '明晚原地高抬腿30次吗？后天体育课检查。', '明晚朗读课文3遍。'):
            self.assertNotIn('2026-11-04', (agent._school_role_days(quote, [dict(text=quote, time='2026-11-03T16:00:00+08:00')], []) or (set(),))[0], quote)
        quote = '体育作业：明晚原地高抬腿30次；后天体育课检查。'
        self.assertEqual(agent._school_role_days(quote, [dict(text=quote, time='2026-11-03T16:00:00+08:00')], []), ({'2026-11-04'}, '2026-11-05'))
        quote = '今晚或明晚跳绳100下；后天体育课检查。'
        self.assertNotEqual((agent._school_role_days(quote, [dict(text=quote, time='2026-11-03T16:00:00+08:00')], []) or (set(),))[0], {'2026-11-04'},
                            'an option between two evenings is no chosen work day')

        future, a, v = self.one('11月10日（周二）美术课带一张白色卡纸，不用今晚画画。', 'admin', '2026-11-10', '2026-11-03T16:20:00+08:00', ('2026-11-03', '2026-11-10'))
        self.assertEqual((a['due_on'], a['due_kind']), ('2026-11-10', 'arranged'), 'the negated 今晚 lends no day')
        self.assertNotIn(future['task_id'], self.ids(v['2026-11-03'], 'groups') | self.ids(v['2026-11-03'], 'undated'))
        self.assertIn('2026-11-10', [u['day'] for u in v['2026-11-03']['upcoming']], 'named once before its lesson day')
        self.assertIn(future['task_id'], self.ids(v['2026-11-10'], 'groups'))
        past, a, v = self.one('11月2日（周一）音乐课带一个干净纸杯。', 'admin', '2026-11-02', '2026-11-01T17:00:00+08:00', ('2026-11-02', '2026-11-03'))
        self.assertEqual((a['due_on'], a['due_kind']), ('2026-11-02', 'arranged'))
        self.assertIn(past['task_id'], self.ids(v['2026-11-02'], 'groups'), 'its own day lists it with the same id')
        self.assertNotIn(past['task_id'], self.ids(v['2026-11-03'], 'groups') | self.ids(v['2026-11-03'], 'undated'), 'no open work later')
        self.assertEqual(v['2026-11-03']['counts']['open'], 0)
        back, a, v = self.one('请家长签字，11月2日交回活动回执。', 'admin', '2026-11-02', '2026-11-01T17:00:00+08:00', ('2026-11-03',))
        self.assertEqual((a['due_on'], a['due_kind']), ('2026-11-02', 'handback'))
        self.assertEqual([(i['task_id'], i['when']) for g in v['2026-11-03']['groups'] for i in g['items']], [(back['task_id'], 'overdue')])
