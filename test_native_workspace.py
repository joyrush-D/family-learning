"""Run python3 -B test_native_workspace.py. The one-child day projection that the web home (/api/state today_view) and the Mac
workbench (GET /api/day) both read, over Root's frozen fictional whole day (test_daily_list_whole_day, 2026-11-04). Opening reads
only: no model, collector, printer or household path; writes go through the existing feedback, wrong-note and record contracts."""
import datetime as dt
import unittest
from unittest import mock

import test_daily_list_whole_day as whole


def frozen(fixed):
    class FrozenDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            value = fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
            return cls(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=value.tzinfo)
    return mock.patch.object(dt, 'datetime', FrozenDateTime)


def ids(view, key='groups'):
    return [item['id'] for group in view[key] for item in group['items']]


class NativeWorkspaceProjectionTests(unittest.TestCase):
    def setUp(self):
        self.case = whole.WholeDayTests('test_root_actual_title_reply_keeps_title_and_summary_to_their_own_words')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case._old_saved(whole.ACTUAL_TITLE_REPLY, ())
        self.app = self.case.app
        patch = frozen(self.case.now); patch.start(); self.addCleanup(patch.stop)
        self.app.family_llm._chat_json = lambda *a, **k: self.fail('opening a day must not call a model')
        self.children = self.app.profiles()
        self.today = self.app.snapshot()['today']
        views = {c['id']: self.app.day_view(c['id'], self.today) for c in self.children}
        self.child = max(self.children, key=lambda c: len(ids(views[c['id']])))
        self.other = next(c for c in self.children if c['id'] != self.child['id'])

    def test_web_home_and_mac_read_the_same_day(self):
        snap = self.app.snapshot()
        for c in self.children:
            day = self.app.day_view(c['id'], self.today)
            self.assertEqual(ids(day), ids(snap['today_view'][c['id']]))
            self.assertEqual([g['subject'] for g in day['groups']], [g['subject'] for g in snap['today_view'][c['id']]['groups']])
        view = self.app.day_view(self.child['id'], self.today)
        subjects = [g['subject'] for g in view['groups']]
        self.assertEqual(len(subjects), len(set(subjects)), 'one flat section per subject')
        tail = [s for s in subjects if s in ('综合事务', '科目待定')]
        self.assertEqual(subjects[len(subjects) - len(tail):], tail, '综合事务 and 科目待定 come last')
        inbox = {x['id']: x for x in snap['today_calendar']['inbox']}
        for item in view['groups'][0]['items'] + [i for g in view['groups'] for i in g['items']]:
            self.assertIn(self.child['id'], inbox[item['id']]['child_ids'])
            self.assertFalse(item['closed'])
            due = next(f for f in item['facts'] if f['role'] == 'due')
            if not inbox[item['id']]['agenda'].get('due_on'): self.assertFalse(due['known'])  # unknown stays unknown, never guessed

    def test_frozen_whole_day_items_are_listed_once_under_their_subjects(self):
        view = self.app.day_view(self.child['id'], self.today)
        rows = [(g['subject'], i) for g in view['groups'] for i in g['items']]
        for anchor, _words, subject, _day in whole_items():
            found = [(s, i) for s, i in rows if anchor in i['title']]
            self.assertEqual(len(found), 1, anchor)
            if subject: self.assertEqual(found[0][0], subject, anchor)
        oral = [i for _s, i in rows if i['origin'] == 'oral']
        self.assertTrue(oral, 'the oral addition is listed and source-signed')
        for item in oral:
            self.assertEqual(item['origin_label'], '孩子口头转述')

    def test_children_never_see_each_others_rows(self):
        mine, theirs = self.app.day_view(self.child['id'], self.today), self.app.day_view(self.other['id'], self.today)
        self.assertFalse(set(ids(mine)) & set(ids(theirs)))
        self.assertEqual(mine['child_name'], self.child['name'])

    def test_bounds_and_unknown_child(self):
        for child, day, status in [('nobody', self.today, 404), (self.child['id'], 'x', 400), (self.child['id'], '2026-02-30', 400)]:
            with self.assertRaises(self.app.TaskError) as caught: self.app.day_view(child, day)
            self.assertEqual(caught.exception.status, status)
        self.assertEqual(self.app.day_view('', '')['child_id'], self.children[0]['id'])
        # Any exact date stays navigable (history is not narrowed to a window); one day is still one read.
        self.assertEqual(self.app.day_view(self.child['id'], '2025-01-06')['day'], '2025-01-06')

    def test_day_keeps_publisher_progress_and_honest_counts(self):
        snap = self.app.snapshot()
        tasks = {t['id']: t for t in snap['tasks']}
        view = self.app.day_view(self.child['id'], self.today)
        rows = [i for g in view['groups'] for i in g['items']]
        for item in rows:
            task = tasks.get(item['task_id'])
            if not task: continue
            pubs = task.get('agenda', {}).get('publications') or []
            self.assertEqual(item['publications'], [dict(ref=p['ref'], source_name=p['source_name'], sender=p['sender']) for p in pubs])
            self.assertEqual(item['progress'], task.get('progress'))
        c = view['counts']
        self.assertEqual(c['open'], len(rows))
        self.assertEqual(sum(c[k] for k in ('today', 'later', 'overdue', 'earlier', 'unknown')), len(rows))
        self.assertEqual(c['today'], sum(bool(i['today']) for i in rows))
        self.assertEqual((c['open'], c['today'], c['later']), (7, 5, 2), 'the frozen whole day: 7 items, 5 today, 2 later')

    def test_material_states_read_the_saved_interpretation_only(self):
        a, b = 'a' * 32, 'b' * 32
        ready = dict(state='ready', updated='2026-11-04T16:00:00+08:00', upload_ids=[a, b], draft=dict(kind='school_material', originals=[
            dict(upload_id=a, title='虚构英语作业', note='虚构：朗读课文两遍。', uncertainties=[]),
            dict(upload_id=b, title='虚构练习', note='虚构：练习第8页。', uncertainties=['右下角看不清'])]))
        got = self.app.homework_material_state(ready, a)
        self.assertEqual((got['state'], got['label'], got['summary']), ('ready', '已整理', '虚构：朗读课文两遍。'))
        got = self.app.homework_material_state(ready, b)
        self.assertEqual((got['state'], got['unclear']), ('partial', ['右下角看不清']))
        self.assertEqual(self.app.homework_material_state(ready, 'c' * 32)['state'], 'saved')
        got = self.app.homework_material_state(dict(state='unavailable', explanation='虚构：原件含图片，未读取。'), a)
        self.assertEqual((got['state'], got['label'], got['summary']), ('unread', '尚未读清', ''))
        self.assertEqual(self.app.homework_material_state(None, a)['state'], 'saved')
        self.assertEqual(self.app.homework_material_state(dict(state='pending'), a)['state'], 'pending')
        self.assertNotIn('教师答案', str(self.app.MATERIAL_ROLES))

    def test_opening_a_day_writes_nothing(self):
        before = self.case._rows()
        for c in self.children:
            self.app.day_view(c['id'], self.today)
            self.app.day_view(c['id'], (dt.date.fromisoformat(self.today) + dt.timedelta(days=1)).isoformat())
        self.app.snapshot()
        self.assertEqual(self.case._rows(), before)

    def test_feedback_wrong_note_and_correction_reopen_on_the_same_task(self):
        view = self.app.day_view(self.child['id'], self.today)
        item = next(i for g in view['groups'] for i in g['items'] if i['kind'] == 'task')
        body = dict(task_id=item['task_id'], child=self.child['name'], note='虚构：照片可不加，只写文字。', attachments=[],
                    complete=False, request_key='native-feedback-0001', day=self.today)
        self.app.save_task_feedback(body)
        self.app.save_task_feedback(dict(body))  # a lost reply resent with the same request key is the same record
        again = next(i for g in self.app.day_view(self.child['id'], self.today)['groups'] for i in g['items'] if i['id'] == item['id'])
        self.assertEqual([r['note'] for r in again['records']], [body['note']])
        self.assertFalse(again['closed'], 'saving words never marks the task done')
        record = again['records'][0]
        subject = '' if item['subject'] in ('综合事务', '科目待定') else item['subject']
        self.app.wrong_review_store().save(dict(child=self.child['name'], day=self.today, subject=subject, request_key='native-wrong-00001',
                                                items=[dict(label='第3题', note='')], task_id=item['task_id'],
                                                feedback_record_id=record['id'], feedback_created=record['created']))
        reread = self.app.day_view(self.child['id'], self.today)
        row = next(i for g in reread['groups'] for i in g['items'] if i['id'] == item['id'])
        self.assertEqual([w['state'] for w in row['wrong']], ['待订正'])
        self.assertEqual((row['progress']['feedback'], row['progress']['wrong']), (1, 1), 'the same progress /api/state reads')
        self.assertEqual([r['id'] for r in row['records']], [record['id']], 'the wrong note is not counted as feedback')
        wrong = row['wrong'][0]
        self.assertEqual([g['subject'] for g in reread['wrong']], [subject or '科目待定'])
        self.app.save_record(dict(child=self.child['name'], day=self.today, category='学习进展', title='订正：' + wrong['title'], subject=subject,
                                  note='虚构：已订正第3题。', related_record_id=wrong['id'], followup_kind='订正', request_key='native-correct-0001'))
        row = next(i for g in self.app.day_view(self.child['id'], self.today)['groups'] for i in g['items'] if i['id'] == item['id'])
        self.assertEqual([w['state'] for w in row['wrong']], ['已订正'])
        other = self.app.day_view(self.other['id'], self.today)
        self.assertFalse(other['wrong'])
        self.assertFalse([r for g in other['groups'] for i in g['items'] for r in i['records'] if r['note'].startswith('虚构')])


def whole_items():
    # The frozen whole-day truth the browser check reads (test_daily_list_actual_scope_ui.cjs ITEMS): anchor, words, subject, day.
    return [('晚照', (), '语文', None), ('练习册第12页', (), '数学', None), ('跟读', (), '英语', None), ('英语课听写', (), '英语', None),
            ('单词听写本', (), '英语', None), ('出游回执', (), '', None), ('订正课堂练习第5、6题', (), '数学', None)]


if __name__ == '__main__':
    unittest.main()
