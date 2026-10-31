"""Run python3 -B test_calendar_learning.py. The calendar-led day that the web home (/api/state today_view) and the Mac read
(GET /api/day) over a fictional week: lessons and plans already expanded by the calendar (weekly repeat, a per-date
cancellation, an extra time, a later timetable, an unknown clock, cancelled/completed left out), a plan tied to a listed task
only giving that row its time, another child's plan never shown, week counts equal to each single day, the wrong book's
own-child task link, learning evidence by subject (current/history basis, independent retry, course records apart) with the
same numbers as the task card, a parent's confirmed topic link shown as linked and pending diagnosis (never a clue), a broken
calendar row leaving the list readable, and opening writes nothing. Every global the module replaces (app paths and docs, the
model call, the clock, the environment) is put back in tearDownModule, so a later module in the same run reads its own. All
fictional."""
import datetime as dt
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import app
import family_taxonomy

TMP, PATCHES = None, []

NOW = dt.datetime(2026, 10, 28, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))  # a Wednesday
DOCS = {'家庭运行规则.md': '| child-1 | 示例甲 | — | 12岁 | 七年级 |\n| child-2 | 示例乙 | — | 10岁 | 五年级 |\n',
        '跟踪台账.md': '| T01 | 示例甲 | 虚构数学作业：有理数加法 | 2026-10-28 | 待跟进 | 虚构学校通知 | 完成两道加法并检查 |\n'
                     '| T02 | 示例甲 | 虚构语文：背诵古诗 | 2026-10-30 | 待跟进 | 虚构学校通知 | 背诵并默写一首古诗 |\n'
                     '| T03 | 示例乙 | 虚构英语：听读 | 2026-10-28 | 待跟进 | 虚构学校通知 | 听读第三课两遍 |\n',
        '学习与成长.md': '全虚构软件验收。', '消息来源.md': ''}
WEEK = [f'2026-10-{d}' for d in range(26, 32)] + ['2026-11-01']
PIANO, HAIRCUT, OUTING, EXTRA = 'a' * 32, 'b' * 32, 'c' * 32, '1' * 16


class Frozen(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        v = NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
        return cls(v.year, v.month, v.day, v.hour, v.minute, v.second, tzinfo=v.tzinfo)


def no_model(*args, **kwargs):
    raise AssertionError('no product model call')


def setUpModule():
    global TMP, CREATED_ON_READ, IDS
    TMP = tempfile.TemporaryDirectory(prefix='synthetic-calendar-learning-'); data = Path(TMP.name)
    # The pack is absent here: names fall back to the saved topic id (FAMILY_TAXONOMY_DIR).
    for patch in [mock.patch.object(dt, 'datetime', Frozen),
                  mock.patch.dict(os.environ, {'FAMILY_DATA': TMP.name, 'FAMILY_TAXONOMY_DIR': str(data / 'no-pack')}),
                  mock.patch.multiple(app, DATA=data, DB=data / 'family.sqlite3', read=lambda name: DOCS.get(name, '')),
                  mock.patch.object(app.family_llm, '_chat_json', no_model)]:
        patch.start(); PATCHES.append(patch)
    f = app.save_task_feedback(dict(task_id='T01', child='示例甲', day='2026-10-28', note='虚构：第一题符号算错', request_key='synthetic-cal-feedback-01'))
    w1 = app.save_record(dict(child='示例甲', day='2026-10-28', category='学习进展', subject='数学', title='虚构加法错题', note='题面：(-8)+5=?\n学生原答：-13',
                              source='错题照片核对', related_record_id=f['record_id'], followup_kind='补充观察'))['record_id']
    w2 = app.save_record(dict(child='示例甲', day='2026-10-27', category='学习进展', subject='语文', title='虚构默写错字', note='“春眠不觉晓”写成“春眠不觉晚”', source='错题照片核对'))['record_id']
    app.save_record(dict(child='示例甲', day='2026-10-28', category='学习进展', subject='语文', title='虚构订正', note='已改正', source='家长', related_record_id=w2, followup_kind='订正'))
    app.save_record(dict(child='示例甲', day='2026-10-27', category='课程进度', subject='数学', title='虚构课堂：有理数加法', note='课堂讲到加法法则', source='家长转述'))
    w3 = app.save_record(dict(child='示例甲', day='2026-10-29', category='学习进展', subject='数学', title='虚构关联未诊断错题', note='题面：(-2)+7=?\n学生原答：-9', source='错题照片核对'))['record_id']
    other = app.save_record(dict(child='示例乙', day='2026-10-28', category='学习进展', subject='数学', title='另一孩子虚构错题', note='1+1=3', source='错题照片核对'))['record_id']
    app.day_view('child-1', '2026-10-28')  # before any calendar exists: a read must not create its tables
    with sqlite3.connect(app.DB) as c:
        CREATED_ON_READ = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'calendar%' OR name LIKE 'topic%'")}
    (app.DATA / '日历来源.json').write_text(json.dumps(dict(
        timetables=[dict(id='tt-old', child_id='child-1', effective_from='2026-09-01', effective_until='2026-12-31', title='虚构七年级课表', source='虚构学校课表',
                         week=[dict(weekday=d, sessions=[dict(slot='第1节', title='数学'), dict(slot='第2节', title='语文')] + ([dict(slot='第3节', title='英语')] if d == 3 else [])) for d in range(1, 6)]),
                    dict(id='tt-new', child_id='child-1', effective_from='2026-10-30', effective_until='', title='虚构调整后课表', source='虚构学校课表',
                         week=[dict(weekday=5, sessions=[dict(slot='上午第1节', title='科学')])]),
                    dict(id='tt-b', child_id='child-2', effective_from='2026-09-01', title='虚构五年级课表', source='虚构学校课表', week=[dict(weekday=3, sessions=[dict(slot='第1节', title='乙的英语')])])],
        events=[dict(id='hw-time', child_ids=['child-1'], title='虚构数学作业时段', day='2026-10-28', start_time='19:00', end_time='19:40', status='confirmed', source='虚构学校通知', task_id='T01'),
                dict(id='b-only', child_ids=['child-2'], title='虚构乙的活动', day='2026-10-28', start_time='15:00', status='confirmed', source='虚构学校通知'),
                dict(id='shared', child_ids=['child-1', 'child-2'], title='虚构家庭参观', day='2026-10-29', status='tentative', source='虚构学校通知', task_id='T03')]),
        ensure_ascii=False), encoding='utf-8')
    store = app.calendar_store()
    store.save(dict(id=PIANO, version=0, child_ids=['child-1'], title='虚构钢琴课', category='other', day='2026-10-05', start_time='16:00', end_time='17:00',
                    location='虚构琴房', note='', status='confirmed', repeat='weekly', until='', repeat_days=[1, 3], extra_times=[dict(id=EXTRA, start_time='18:00', end_time='18:30')]))
    store.save_occurrence(dict(series_id=PIANO, series_version=1, origin_day='2026-10-28', slot_id='', version=0, day='2026-10-28', start_time='16:00', end_time='17:00', status='cancelled', note='虚构：老师请假'))
    store.save(dict(id=HAIRCUT, version=0, child_ids=['child-1'], title='虚构理发', category='other', day='2026-10-31', start_time='10:00', end_time='', location='', note='', status='completed', repeat='none', until='', repeat_days=[], extra_times=[]))
    store.save(dict(id=OUTING, version=0, child_ids=['child-1'], title='虚构春游', category='other', day='2026-10-30', start_time='', end_time='', location='', note='', status='cancelled', repeat='none', until='', repeat_days=[], extra_times=[]))
    with sqlite3.connect(app.DB) as c:
        c.row_factory = sqlite3.Row; family_taxonomy.ensure_schema(c)
        row = c.execute('SELECT id,child,day,subject,title,note,source,attachments,created FROM records WHERE id=?', (w1,)).fetchone()
        now = family_taxonomy.record_hash({k: row[k] for k in row.keys()} | dict(child_id='child-1'))
        # The parent's own confirmed links (link_record's rows): w1's two are the topics its diagnoses already show, w3's is linked only.
        row3 = c.execute('SELECT id,child,day,subject,title,note,source,attachments,created FROM records WHERE id=?', (w3,)).fetchone()
        for record, digest, at in [(w1, 'an-earlier-text', 1793090000), (w1, now, 1793150000),
                                   (w3, family_taxonomy.record_hash({k: row3[k] for k in row3.keys()} | dict(child_id='child-1')), 1793250000)]:
            c.execute("INSERT INTO topic_links(child_id,record_id,record_hash,topic_id,state,pack_sha,note,request_id,created_at) VALUES('child-1',?,?,'cnm_010','confirmed',?,'',?,?)",
                      (str(record), digest, family_taxonomy.TAXONOMY_SHA, 'l' + str(at), at))
        for ident, digest, at in [(1, 'an-earlier-text', 1793100000), (2, now, 1793160000)]:
            c.execute("INSERT INTO topic_diagnoses(id,child_id,record_id,record_hash,topic_id,pack_sha,engine_sha256,opts,request_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (ident, 'child-1', str(w1), digest, 'cnm_010', family_taxonomy.TAXONOMY_SHA, 'e', '{}', 'r' + str(ident), at, at))
        for seq, helped in [(1, ''), (2, 'explain')]:
            c.execute("INSERT INTO topic_diagnosis_items(diagnosis_id,seq,topic_id,qid,kind,answer,verdict,engine_result,help,payload_hash,created_at) VALUES(2,?,?,?,?,?,?,?,?,?,?)",
                      (seq, 'cnm_010', 'cnm_010_q' + str(seq), 'answer', '-3', 'correct', '{}', helped, 'p', 1793160000))
        for outcome, answer, at in [('not_independent', '-2', 1793170000), ('independent_correct', '-3', 1793246400)]:
            c.execute("INSERT INTO topic_retries(diagnosis_id,child_id,record_id,record_hash,topic_id,qid,answer,taxonomy_verdict,outcome,request_id,created_at) VALUES(2,'child-1',?,?,?,?,?,?,?,?,?)",
                      (str(w1), now, 'cnm_010', 'cnm_010_q3', answer, 'correct', outcome, 'q' + outcome, at))
    IDS = dict(w1=w1, w2=w2, w3=w3, other=other)


def tearDownModule():
    while PATCHES: PATCHES.pop().stop()
    TMP.cleanup()


def items(view, key='groups'):
    return [i for g in view[key] for i in g['items']]


class CalendarLearningTests(unittest.TestCase):
    def test_a_read_creates_no_calendar_or_topic_table(self):
        self.assertEqual(CREATED_ON_READ, set())

    def test_lessons_and_plans_follow_the_calendars_own_expansion(self):
        mon = app.day_view('child-1', '2026-10-26')['schedule']
        self.assertEqual([s['title'] for t in mon['lessons'] for s in t['sessions']], ['数学', '语文'])
        self.assertEqual([(p['title'], p['start_time']) for p in mon['plans']], [('虚构钢琴课', '16:00'), ('虚构钢琴课', '18:00')])
        self.assertTrue(all(p['repeat'] for p in mon['plans']))
        wed = app.day_view('child-1', '2026-10-28')
        s = wed['schedule']
        self.assertEqual([x['slot'] for t in s['lessons'] for x in t['sessions']], ['第1节', '第2节', '第3节'])
        self.assertEqual([(p['title'], p['start_time']) for p in s['plans']], [('虚构钢琴课', '18:00')])  # 16:00 cancelled this date only
        self.assertEqual((s['cancelled'], s['completed']), (1, 0))
        t01 = next(i for i in items(wed) if i['task_id'] == 'T01')
        self.assertEqual([(t['start_time'], t['end_time']) for t in t01['times']], [('19:00', '19:40')])  # merged into its row, not listed again
        self.assertNotIn('source:hw-time', [p['id'] for p in s['plans']])
        self.assertNotIn('虚构乙的活动', json.dumps(wed, ensure_ascii=False))
        thu = app.day_view('child-1', '2026-10-29')['schedule']
        shared = next(p for p in thu['plans'] if p['title'] == '虚构家庭参观')
        self.assertEqual((shared['start_time'], shared['shared'], shared['task_id']), ('', True, 'T03'))
        self.assertIn('没有合并', shared['unmerged'])  # another child's task: kept apart, never guessed into a row
        self.assertEqual(thu['plans'][-1]['title'], '虚构家庭参观')  # unknown clock last, never given a time
        fri = app.day_view('child-1', '2026-10-30')['schedule']
        self.assertEqual([x['title'] for t in fri['lessons'] for x in t['sessions']], ['科学'])  # the later timetable from its own date
        self.assertEqual((fri['cancelled'], fri['plans']), (1, []))
        sat = app.day_view('child-1', '2026-10-31')['schedule']
        self.assertEqual((sat['lessons'], sat['plans'], sat['completed']), ([], [], 1))
        b = app.day_view('child-2', '2026-10-28')['schedule']
        self.assertEqual([x['title'] for t in b['lessons'] for x in t['sessions']], ['乙的英语'])
        self.assertEqual([p['title'] for p in b['plans']], ['虚构乙的活动'])
        self.assertFalse([i for i in items(app.day_view('child-1', '2026-10-28')) if i.get('kind') == 'event'])  # unexpanded rows never become items

    def test_week_counts_are_each_single_day(self):
        for day in ['2026-10-28', '2026-11-01']:
            week = app.day_view('child-1', day)['week']
            self.assertEqual([w['day'] for w in week], WEEK)
            for w in week:
                one = app.day_view('child-1', w['day'])
                s = one['schedule']
                self.assertEqual((w['open'], w['today'], w['overdue'], w['closed']),
                                 (one['counts']['open'], one['counts']['today'], one['counts']['overdue'], one['counts']['closed']), w['day'])
                self.assertEqual(w['schedule'], sum(len(t['sessions']) for t in s['lessons']) + len(s['plans']))

    def test_state_today_view_is_the_same_projection(self):
        snap = app.snapshot()
        for child in ['child-1', 'child-2']:
            day = app.day_view(child, snap['today'])
            home = snap['today_view'][child]
            for key in ['groups', 'closed', 'wrong', 'counts', 'schedule', 'week', 'learning']:
                self.assertEqual(json.dumps(home[key], sort_keys=True, ensure_ascii=False), json.dumps(day[key], sort_keys=True, ensure_ascii=False), (child, key))

    def test_wrong_book_names_only_its_own_childs_task(self):
        view = app.day_view('child-1', '2026-10-30')
        wrong = {r['id']: r for r in items(view, 'wrong')}
        self.assertEqual((wrong[IDS['w1']]['task_id'], wrong[IDS['w1']]['task_title']), ('T01', '虚构数学作业：有理数加法'))
        self.assertNotIn('task_id', wrong[IDS['w2']])
        self.assertEqual(wrong[IDS['w2']]['state'], '已订正')
        self.assertNotIn(IDS['other'], wrong)
        self.assertNotIn('另一孩子', json.dumps(app.day_view('child-1', '2026-10-28')['learning'], ensure_ascii=False))

    def test_learning_shows_evidence_with_the_task_cards_numbers(self):
        view = app.day_view('child-1', '2026-10-28')
        learning = view['learning']
        self.assertFalse(learning['pack']['installed'])
        math = next(s for s in learning['subjects'] if s['subject'] == '数学')
        entry = next(e for e in math['evidence'] if e['record_id'] == IDS['w1'])
        self.assertEqual([(t['name'], t['known'], t['basis']) for t in entry['topics']], [('cnm_010', False, 'history'), ('cnm_010', False, 'current')])
        labels = [l[0] for l in entry['lines']]
        self.assertEqual(labels, ['原错题', '历史诊断', '知识点诊断', '新题再试', '新题再试'])
        self.assertIn('答了2题，其中1题看过说明', entry['lines'][2][1])
        self.assertIn('有帮助，不算独立', entry['lines'][3][1])
        self.assertIn('2026-10-29 · 独立作答 · 对 · 孩子原答 -3', entry['lines'][4][1])
        self.assertIn('不等于掌握', entry['next'])
        self.assertEqual((entry['task_id'], entry['state']), ('T01', '待订正'))
        self.assertEqual([(c['title'], c['source']) for c in math['course']], [('虚构课堂：有理数加法', '家长转述')])  # its own source, no teacher inferred
        chinese = next(s for s in learning['subjects'] if s['subject'] == '语文')
        self.assertEqual((chinese['evidence'][0]['state'], chinese['evidence'][0]['topics'], chinese['evidence'][0]['next']), ('已订正', [], '知识点尚未评估。'))
        progress = next(i for i in items(view) if i['task_id'] == 'T01')['progress']
        current = [t for t in entry['topics'] if t['basis'] == 'current']
        self.assertEqual((progress['clues'], progress['history'], progress['retries']),
                         (len(current), len(entry['topics']) - len(current), sum('独立作答' in l[1] for l in entry['lines'] if l[0] == '新题再试')))
        text = json.dumps(learning, ensure_ascii=False)
        self.assertNotIn('%', text); self.assertNotIn('已掌握', text)

    def test_learning_shows_a_linked_topic_as_pending_never_as_a_clue(self):
        pack = dict(by_id={'cnm_010': dict(name='有理数的加法法则'), 'cnm_011': dict(name='虚构另一知识点')})
        made = [app.save_record(dict(child='示例甲', day='2026-10-29', category='学习进展', subject='数学', title='虚构' + t, note='虚构题面' + t, source='错题照片核对'))['record_id']
                for t in ['更正后改选无匹配', '其他包版本', '只标不明']]
        with sqlite3.connect(app.DB) as c:
            c.row_factory = sqlite3.Row
            def basis(ident):
                row = c.execute('SELECT id,child,day,subject,title,note,source,attachments,created FROM records WHERE id=?', (ident,)).fetchone()
                return family_taxonomy.record_hash({k: row[k] for k in row.keys()} | dict(child_id='child-1'))
            rows = [(made[0], 'an-old-text', 'cnm_011', 'confirmed', family_taxonomy.TAXONOMY_SHA), (made[0], basis(made[0]), 'cnm_010', 'confirmed', family_taxonomy.TAXONOMY_SHA),
                    (made[0], basis(made[0]), '', 'no_match', family_taxonomy.TAXONOMY_SHA), (made[1], basis(made[1]), 'cnm_010', 'confirmed', 'another-pack'),
                    (made[2], basis(made[2]), '', 'unclear', family_taxonomy.TAXONOMY_SHA)]
            for n, (record, digest, topic, state, sha) in enumerate(rows):
                c.execute("INSERT INTO topic_links(child_id,record_id,record_hash,topic_id,state,pack_sha,note,request_id,created_at) VALUES('child-1',?,?,?,?,?,'',?,?)",
                          (str(record), digest, topic, state, sha, 'edge' + str(n), 1793250000 + n))
        try:
            with mock.patch.object(family_taxonomy, 'load_pack', return_value=pack):
                view = app.day_view('child-1', '2026-10-28')
            math = {e['record_id']: e for e in next(s for s in view['learning']['subjects'] if s['subject'] == '数学')['evidence']}
            shown = lambda ident: [(t['name'], t['known'], t['basis'], t['state']) for t in math[ident]['topics']]
            # Linked only: the fixed pack's own name and the link's own date, pending, and not a clue or mastery.
            self.assertEqual(shown(IDS['w3']), [('有理数的加法法则', True, 'current', 'linked')])
            self.assertEqual(math[IDS['w3']]['lines'][1:], [['已关联知识点', '有理数的加法法则 · 2026-10-29 · 家长确认关联，待诊断']])
            self.assertEqual(math[IDS['w3']]['next'], '先订正。已关联知识点，待诊断；关联不等于掌握。')
            # The same topic already diagnosed on the same basis is one entry, never repeated by its link.
            self.assertEqual(shown(IDS['w1']), [('有理数的加法法则', True, 'history', 'diagnosed'), ('有理数的加法法则', True, 'current', 'diagnosed')])
            self.assertEqual([l[0] for l in math[IDS['w1']]['lines']], ['原错题', '历史诊断', '知识点诊断', '新题再试', '新题再试'])
            # A corrected record keeps its old link as history; the parent's later no-match on the present text names no topic.
            self.assertEqual(shown(made[0]), [('虚构另一知识点', True, 'history', 'linked')])
            self.assertIn('原错题之后已更正，只作历史', math[made[0]]['lines'][1][1])
            self.assertEqual(shown(made[1]), [('cnm_010', False, 'current', 'linked')])  # another pack's id is never named from this one
            self.assertEqual((shown(made[2]), math[made[2]]['next']), ([], '先订正。知识点尚未评估。'))  # unclear is not a confirmation
            progress = next(i for i in items(view) if i['task_id'] == 'T01')['progress']
            self.assertEqual((progress['clues'], progress['history'], progress['retries']), (1, 1, 1))  # diagnoses only, as before
            text = json.dumps(view['learning'], ensure_ascii=False)
            self.assertNotIn('%', text); self.assertNotIn('已掌握', text)
        finally:
            with sqlite3.connect(app.DB) as c:
                c.execute("DELETE FROM topic_links WHERE request_id LIKE 'edge%'")
                c.executemany('DELETE FROM records WHERE id=?', [(i,) for i in made])

    def test_opening_any_day_writes_nothing(self):
        app.snapshot()  # the first /api/state still sets up its own stores, as before this change; every later read is read only
        before = hashlib.sha256(Path(app.DB).read_bytes()).hexdigest()
        for day in WEEK: app.day_view('child-1', day); app.day_view('child-2', day)
        app.snapshot()
        self.assertEqual(hashlib.sha256(Path(app.DB).read_bytes()).hexdigest(), before)

    def test_query_stays_child_and_day_only(self):
        self.assertRaises(app.TaskError, app.day_view, 'child-1', '2026-10-32')

    def test_z_a_broken_calendar_row_keeps_the_list(self):
        with sqlite3.connect(app.DB) as c:
            c.execute("INSERT INTO calendar_events SELECT 'f'||substr(id,2),version,child_ids,title,category,'2026-10-27',start_time,end_time,location,note,status,'none','',last_request_hash,created,updated,'[]','[]',"
                      "json_object('series_id','" + 'e' * 32 + "','day','2026-10-27','slot_id','','original',json_object(),'history',json_array()) FROM calendar_events WHERE id=?", (HAIRCUT,))
        try:
            view = app.day_view('child-1', '2026-10-28')
            self.assertIn('T01', [i['task_id'] for i in items(view)])
            self.assertIsNone(view['schedule']); self.assertTrue(view['schedule_error'])
            self.assertTrue(all(w['schedule'] is None for w in view['week']))
            self.assertIn('T01', [i['task_id'] for i in items(app.snapshot()['today_view']['child-1'])])
        finally:
            with sqlite3.connect(app.DB) as c: c.execute("DELETE FROM calendar_events WHERE id=?", ('f' + HAIRCUT[1:],))


if __name__ == '__main__':
    unittest.main()
