"""诊断/学习者模型层（③）：确定性汇总错题/考试证据，模型只据证据命名知识点并引用原记录。合成数据。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
import family_diagnosis as diag
import family_llm


def _app():
    return SimpleNamespace(connect=app.connect, profiles=app.profiles, DATA=app.DATA)


class DiagnosisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self._prev = (app.ROOT, app.DATA, app.DB)
        app.ROOT, app.DATA, app.DB = root, root/'private', root/'private'/'family.sqlite3'
        app.DATA.mkdir(parents=True)
        (root/'家庭运行规则.md').write_text('| child-1 | 小明 | 男 | 9岁 | 三年级 |\n| child-2 | 小红 | 女 | 7岁 | 一年级 |\n')
        # Two math wrong questions + one exam; one unrelated Chinese record.
        app.save_record(dict(child='小明', day='2026-09-10', category='学习进展', subject='数学',
                             title='错题：第3题', note='题面：27+8=？ 学生原答：35', source=diag.WRONG_SOURCE))
        app.save_record(dict(child='小明', day='2026-09-12', category='学习进展', subject='数学',
                             title='错题：第5题', note='题面：46+7=？ 学生原答：43', source=diag.WRONG_SOURCE))
        app.save_record(dict(child='小明', day='2026-09-13', category='成绩', subject='数学',
                             title='单元测验', score='72', total='100', note='进位加法多题出错'))
        app.save_record(dict(child='小明', day='2026-09-11', category='学习进展', subject='语文',
                             title='错题：比喻句', note='本体喻体混淆', source=diag.WRONG_SOURCE))
        for k in ('ROOT', 'DATA', 'DB'):
            self.addCleanup((lambda kk: (lambda: setattr(app, kk, dict(zip(('ROOT','DATA','DB'), self._prev))[kk])))(k))

    def _refs_seen(self):
        return {e['ref'] for e in diag.evidence(_app(), 'child-1', '数学')}

    def test_evidence_gathers_math_errors_only(self):
        ev = diag.evidence(_app(), 'child-1', '数学')
        kinds = sorted(set(e['kind'] for e in ev))
        self.assertEqual(kinds, ['exam', 'wrong_question'])  # no 语文, no cross-subject
        self.assertTrue(all(e['subject'] in ('数学', '') for e in ev))
        self.assertEqual(len(ev), 3)

    def test_diagnose_validates_refs_persists_and_supersedes(self):
        refs = list(self._refs_seen())
        good = refs[0]
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加',
                     misconception='个位相加满十未向十位进1', status='有支持',
                     evidence=[good, 'record:99999'], suggestion='选2道进位题，问孩子个位满十怎么办')],
                     summary='先解决进位漏加', uncertainties=['字迹较淡'])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            out = diag.diagnose(_app(), 'child-1', '数学')
        comp = out['diagnosis']['knowledge_components'][0]
        self.assertEqual(comp['name'], '两位数进位加法')
        self.assertEqual(comp['evidence'], [good])  # invented record:99999 dropped, no fabricated refs
        latest = diag.latest(_app(), 'child-1', '数学')
        self.assertEqual(len(latest), 1)
        # A second run supersedes the first; history is kept, only one current.
        with patch.object(family_llm, '_chat_json', return_value=dict(draft, summary='更新')):
            diag.diagnose(_app(), 'child-1', '数学')
        self.assertEqual(len(diag.latest(_app(), 'child-1', '数学')), 1)
        with app.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM diagnoses WHERE child_id='child-1'").fetchone()[0], 2)

    def test_diagnose_rejects_malformed_model_output(self):
        for bad in [dict(knowledge_components='x', summary='', uncertainties=[]),
                    dict(knowledge_components=[dict(name='a', error_type='', misconception='', status='猜的', evidence=[], suggestion='')], summary='', uncertainties=[]),
                    dict(summary='', uncertainties=[])]:
            with patch.object(family_llm, '_chat_json', return_value=bad):
                with self.assertRaises(family_llm.LLMDraftError):
                    diag.diagnose(_app(), 'child-1', '数学')

    def test_interval_recheck_scheduled_and_due(self):
        import datetime as dt
        refs = list(self._refs_seen())
        draft = dict(knowledge_components=[
            dict(name='两位数进位加法', error_type='进位漏加', misconception='个位满十未进1', status='有支持',
                 evidence=[refs[0]], suggestion='用小棒摆一摆'),
            dict(name='读题', error_type='', misconception='待核对', status='待验证', evidence=[], suggestion='')],
            summary='先解决进位', uncertainties=[])
        base = dt.datetime(2026, 9, 20, 10, 0, 0)
        with patch.object(family_llm, '_chat_json', return_value=draft):
            out = diag.diagnose(_app(), 'child-1', '数学', now=base)
        comps = {c['name']: c for c in out['diagnosis']['knowledge_components']}
        self.assertEqual(comps['两位数进位加法']['review_on'], '2026-09-27')  # supported weakness gets a re-check date
        self.assertEqual(comps['读题']['review_on'], '')                      # 待验证 is not scheduled
        self.assertEqual(diag.due_reviews(_app(), 'child-1', now=base + dt.timedelta(days=6)), [])
        due = diag.due_reviews(_app(), 'child-1', now=base + dt.timedelta(days=7))
        self.assertEqual([d['name'] for d in due], ['两位数进位加法'])
        self.assertEqual(due[0]['subject'], '数学')

    def test_no_evidence_returns_note_without_calling_model(self):
        called = []
        with patch.object(family_llm, '_chat_json', side_effect=lambda *a, **k: called.append(1)):
            out = diag.diagnose(_app(), 'child-1', '英语')  # no 英语 records
        self.assertEqual(out['diagnosis']['knowledge_components'], [])
        self.assertTrue(out['diagnosis']['uncertainties'])
        self.assertEqual(called, [])  # no model call when there is nothing to diagnose

    def _math_ids(self):
        return sorted(int(e['ref'][7:]) for e in diag.evidence(_app(), 'child-1', '数学') if e['kind'] == 'wrong_question')

    def test_overview_is_read_only_and_lists_subjects_before_any_diagnosis(self):
        with patch.object(family_llm, '_chat_json', side_effect=AssertionError('overview must not call the model')):
            view = diag.overview(_app(), 'child-1')
        self.assertEqual({s['subject']: s['wrong_count'] for s in view['subjects']}, {'数学': 2, '语文': 1})
        self.assertTrue(all(s['diagnosis'] is None and not s['evidence_changed'] for s in view['subjects']))
        self.assertEqual(view['due'], [])
        self.assertEqual(diag.overview(_app(), 'child-2')['subjects'], [])  # no leakage across children
        with app.connect() as c:  # reading never creates the diagnoses table
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='diagnoses'").fetchone())

    def test_overview_rechecks_refs_flags_new_evidence_and_schedules_the_recheck(self):
        import datetime as dt
        first, second = self._math_ids()
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加', misconception='个位满十未进1',
                     status='有支持', evidence=['record:%d' % first, 'record:%d' % second, 'record:99999'], suggestion='摆小棒')],
                     summary='先解决进位', uncertainties=['字迹较淡'])
        base = dt.datetime(2026, 9, 20, 10, 0, 0)
        with patch.object(family_llm, '_chat_json', return_value=draft):
            diag.diagnose(_app(), 'child-1', '数学', now=base)
        view = diag.overview(_app(), 'child-1', now=base)
        math = next(s for s in view['subjects'] if s['subject'] == '数学')
        kc = math['diagnosis']['knowledge_components'][0]
        self.assertEqual([e['id'] for e in kc['evidence']], [first, second])  # the invented ref never reaches the view
        self.assertTrue(all(e['available'] and e['title'] for e in kc['evidence']))
        self.assertEqual((kc['record_id'], kc['practice_record_id']), (second, second))  # latest cited 错题
        self.assertEqual((kc['review_on'], kc['due'], math['evidence_changed']), ('2026-09-27', False, False))
        self.assertEqual(view['due'], [])
        due_view = diag.overview(_app(), 'child-1', now=base + dt.timedelta(days=7))
        self.assertEqual([(d['name'], d['record_id']) for d in due_view['due']], [('两位数进位加法', second)])
        self.assertEqual(due_view['subjects'][0]['subject'], '数学')  # a subject with a due re-check comes first
        # A later independent re-check on a fresh item makes the stored conclusion out of date.
        app.save_record(dict(child='小明', day='2026-09-27', category='学习进展', subject='数学', title='复测：进位加法',
                             note='新题 38+5=43，自己做对', source='家长观察', related_record_id=second, followup_kind='复测',
                             assistance='独立尝试', practice_relation='相近的新题或新片段'))
        again = next(s for s in diag.overview(_app(), 'child-1', now=base)['subjects'] if s['subject'] == '数学')
        self.assertTrue(again['evidence_changed'])
        recheck = next(e for e in diag.evidence(_app(), 'child-1', '数学') if e['followup'] == '复测')
        self.assertEqual((recheck['related'], recheck['assistance'], recheck['practice_relation']),
                         ('record:%d' % second, '独立尝试', '相近的新题或新片段'))  # the model can tell independent from helped

    def test_a_cited_record_corrected_to_another_child_is_not_shown(self):
        first, second = self._math_ids()
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='', misconception='待核对', status='待验证',
                     evidence=['record:%d' % first], suggestion='')], summary='', uncertainties=[])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            diag.diagnose(_app(), 'child-1', '数学')
        with app.connect() as c:
            row = dict(c.execute('SELECT * FROM records WHERE id=?', (first,)).fetchone())
        app.save_record(dict({k: row[k] or '' for k in ('day', 'category', 'subject', 'title', 'note', 'source')}, id=first, child='小红'))
        kc = next(s for s in diag.overview(_app(), 'child-1')['subjects'] if s['subject'] == '数学')['diagnosis']['knowledge_components'][0]
        self.assertEqual(kc['evidence'], [dict(ref='record:%d' % first, id=first, available=False, kind='', day='', title='', remediable=False)])
        self.assertIsNone(kc['record_id'])  # nothing to follow up on for this child
        self.assertEqual(diag.overview(_app(), 'child-2')['subjects'][0]['diagnosis'], None)  # 小红 sees her record, not 小明's diagnosis

    def test_due_review_names_evidence_and_the_record_to_recheck(self):
        import datetime as dt
        first, second = self._math_ids()
        exam = next(e for e in diag.evidence(_app(), 'child-1', '数学') if e['kind'] == 'exam')['ref']
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加', misconception='个位满十未进1',
                     status='有支持', evidence=[exam, 'record:%d' % first], suggestion='摆小棒')], summary='', uncertainties=[])
        base = dt.datetime(2026, 9, 20, 10, 0, 0)
        with patch.object(family_llm, '_chat_json', return_value=draft):
            diag.diagnose(_app(), 'child-1', '数学', now=base)
        due = diag.due_reviews(_app(), 'child-1', now=base + dt.timedelta(days=7))[0]
        self.assertEqual(due['record_id'], first)  # the 错题 is re-checked even though the exam is more recent
        self.assertEqual({e['ref'] for e in due['evidence']}, {exam, 'record:%d' % first})
        self.assertTrue(all(e['title'] and e['day'] for e in due['evidence']))

    def test_goals_snapshot_carries_the_read_only_diagnosis(self):
        snap = app.goals_snapshot()
        self.assertEqual(set(snap['diagnosis']), {'child-1', 'child-2'})
        self.assertEqual({s['subject']: s['wrong_count'] for s in snap['diagnosis']['child-1']['subjects']}, {'数学': 2, '语文': 1})
        self.assertNotIn('diagnosis_error', snap)
        with patch.object(diag, 'overview', side_effect=ValueError('broken payload')):
            broken = app.goals_snapshot()
        self.assertEqual(broken['diagnosis'], {})
        self.assertIn('错题原记录仍在', broken['diagnosis_error'])
        self.assertIn('goals', broken)  # the rest of the goals page still loads

    def test_recheck_date_survives_unrelated_rediagnosis_but_restarts_on_new_mistake(self):
        import datetime as dt
        first, second = self._math_ids()
        def run(when, name, refs):
            draft = dict(knowledge_components=[dict(name=name, error_type='进位漏加', misconception='个位满十未进1',
                         status='有支持', evidence=refs, suggestion='')], summary='', uncertainties=[])
            with patch.object(family_llm, '_chat_json', return_value=draft):
                return diag.diagnose(_app(), 'child-1', '数学', now=when)['diagnosis']['knowledge_components'][0]['review_on']
        cited = ['record:%d' % first, 'record:%d' % second]
        self.assertEqual(run(dt.datetime(2026, 9, 20, 9), '两位数进位加法', cited), '2026-09-27')
        # An unrelated record re-triggers diagnosis; the same weakness (renamed, same cited records) keeps its date.
        app.save_record(dict(child='小明', day='2026-09-22', category='学习进展', subject='数学', title='口算练习',
                             note='今天口算状态不错', source='家长观察'))
        self.assertEqual(run(dt.datetime(2026, 9, 22, 9), '两位数加一位数的进位加法', cited), '2026-09-27')
        # A new mistake on that point restarts the interval from the day it is diagnosed.
        new = app.save_record(dict(child='小明', day='2026-09-24', category='学习进展', subject='数学', title='数学错题：第7题',
                                   note='题面：38+5=？ 学生原答：313', source=diag.WRONG_SOURCE))['record_id']
        self.assertEqual(run(dt.datetime(2026, 9, 24, 9), '两位数进位加法', cited + ['record:%d' % new]), '2026-10-01')

    def test_stale_subjects_gate_background_diagnosis(self):
        self.assertEqual([s['subject'] for s in diag.stale_subjects(_app(), 'child-1')], ['数学', '语文'])
        draft = dict(knowledge_components=[], summary='', uncertainties=['证据不足'])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            diag.diagnose(_app(), 'child-1', '数学')
        self.assertEqual([s['subject'] for s in diag.stale_subjects(_app(), 'child-1')], ['语文'])
        # Same-subject context alone (a daily note) is not a reason to re-run; a re-check of a 错题 is.
        app.save_record(dict(child='小明', day='2026-09-14', category='学习进展', subject='数学', title='口算练习', note='口算都对',
                             source='家长观察'))
        self.assertEqual([s['subject'] for s in diag.stale_subjects(_app(), 'child-1')], ['语文'])
        self.assertFalse(next(s for s in diag.overview(_app(), 'child-1')['subjects'] if s['subject'] == '数学')['evidence_changed'])
        first = self._math_ids()[0]
        app.save_record(dict(child='小明', day='2026-09-15', category='学习进展', subject='数学', title='复测', note='新题做对',
                             source='家长观察', related_record_id=first, followup_kind='复测'))
        stale = diag.stale_subjects(_app(), 'child-1')
        self.assertEqual([s['subject'] for s in stale], ['数学', '语文'])
        self.assertEqual(stale[0]['evidence'], diag.evidence(_app(), 'child-1', '数学'))  # the window the model would see
        self.assertEqual(diag.stale_subjects(_app(), 'child-2'), [])

    def test_correcting_a_wrong_question_outdates_its_diagnosis(self):
        with patch.object(family_llm, '_chat_json', return_value=dict(knowledge_components=[], summary='', uncertainties=['x'])):
            diag.diagnose(_app(), 'child-1', '数学')
        self.assertNotIn('数学', [s['subject'] for s in diag.stale_subjects(_app(), 'child-1')])
        first = self._math_ids()[0]
        with app.connect() as c:
            row = dict(c.execute('SELECT * FROM records WHERE id=?', (first,)).fetchone())
        app.save_record(dict({k: row[k] or '' for k in ('child', 'day', 'category', 'subject', 'title', 'source')},
                             id=first, note='题面：27+8=？ 学生原答：25（家长更正转写）'))
        self.assertIn('数学', [s['subject'] for s in diag.stale_subjects(_app(), 'child-1')])
        self.assertTrue(next(s for s in diag.overview(_app(), 'child-1')['subjects'] if s['subject'] == '数学')['evidence_changed'])

    # ② → ③ 家长核对后保留的候选标签：note 中两个精确前缀的行（交接-错题VL-第二开发.md，2026-09-19 定稿）。
    TOPIC, ERROR = '知识点（家长核对）：', '错误类型（家长核对）：'
    BODY = '题面：38+5=？\n学生原答：313\n可见订正/正确答案：43'
    TAIL = '由照片标注生成，家长已核对；这不是掌握程度结论。'

    def _note(self, topic='两位数进位加法', error='进位漏加', body=None):
        lines = [body or self.BODY] + ([self.TOPIC + topic] if topic is not None else []) + ([self.ERROR + error] if error is not None else [])
        return '\n'.join(lines + [self.TAIL])

    def _tagged(self, child='小明', subject='数学', day='2026-09-14', title='数学错题：第7题', **note):
        return app.save_record(dict(child=child, day=day, category='学习进展', subject=subject, title=title,
                                    note=self._note(**note), source=diag.WRONG_SOURCE))['record_id']

    def _item(self, record_id, child_id='child-1', subject='数学'):
        return next(e for e in diag.evidence(_app(), child_id, subject) if e['ref'] == 'record:%d' % record_id)

    def _math(self, child_id='child-1', now=None):
        return next(s for s in diag.overview(_app(), child_id, now=now)['subjects'] if s['subject'] == '数学')

    def test_parent_kept_tags_reach_the_model_as_a_starting_point_and_old_records_are_unchanged(self):
        legacy = diag.evidence(_app(), 'child-1', '数学')
        keys = {'ref', 'kind', 'day', 'subject', 'title', 'text', 'score', 'total', 'followup'}
        self.assertTrue(all(set(e) == keys for e in legacy))  # untagged records: exactly the earlier evidence item
        tagged = self._tagged()
        window = diag.evidence(_app(), 'child-1', '数学')
        self.assertEqual([e for e in window if e['ref'] != 'record:%d' % tagged], legacy)  # same window, same fingerprint
        item = self._item(tagged)
        self.assertEqual((item['topic_hint'], item['error_hint']), ('两位数进位加法', '进位漏加'))
        self.assertIn(self.TOPIC + '两位数进位加法', item['text'])  # the parent's record stays verbatim
        sent = []
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加', misconception='个位满十未进1',
                     status='有支持', evidence=['record:%d' % tagged], suggestion='摆小棒')], summary='', uncertainties=[])
        with patch.object(family_llm, '_chat_json', side_effect=lambda messages, *a, **k: sent.append(messages) or draft):
            out = diag.diagnose(_app(), 'child-1', '数学')
        system, user = sent[0][0]['content'], sent[0][1]['content']
        for phrase in ('topic_hint', 'error_hint', '核对的起点', '候选本身不是证据', '以实际记录为准', '不因为家长保留过候选就维持有支持', '没有候选的记录照常判断'):
            self.assertIn(phrase, system)
        import json
        given = next(r for r in json.loads(user)['records'] if r['ref'] == 'record:%d' % tagged)
        self.assertEqual((given['topic_hint'], given['error_hint']), ('两位数进位加法', '进位漏加'))
        self.assertEqual(out['diagnosis']['knowledge_components'][0]['evidence'], ['record:%d' % tagged])  # still cites the record
        view = self._math()
        self.assertEqual((view['wrong_count'], view['tagged_count']), (3, 1))
        cited = view['diagnosis']['knowledge_components'][0]['evidence'][0]
        self.assertEqual((cited['id'], cited['topic_hint'], cited['error_hint']), (tagged, '两位数进位加法', '进位漏加'))
        chinese = next(s for s in diag.overview(_app(), 'child-1')['subjects'] if s['subject'] == '语文')
        self.assertEqual(chinese['tagged_count'], 0)

    def test_tag_lines_are_read_strictly_bounded_and_only_on_wrong_questions(self):
        long_body = '题面：' + '虚构长题面' * 260  # the tags sit beyond the 1000-char excerpt the model reads
        far = self._tagged(title='数学错题：长题', body=long_body)
        item = self._item(far)
        self.assertNotIn(self.TOPIC, item['text'])
        self.assertEqual((item['topic_hint'], item['error_hint']), ('两位数进位加法', '进位漏加'))
        bounded = self._item(self._tagged(title='数学错题：超长标签', topic='知' * 90, error='错' * 70))
        self.assertEqual((len(bounded['topic_hint']), len(bounded['error_hint'])), (60, 40))
        only_error = self._item(self._tagged(title='数学错题：清空知识点', topic='', error='进位漏加'))  # a cleared tag is no tag
        self.assertNotIn('topic_hint', only_error); self.assertEqual(only_error['error_hint'], '进位漏加')
        remark = self._item(self._tagged(title='数学错题：备注里提到', topic=None, error=None,
                                         body=self.BODY + '\n家长备注：老师说' + self.TOPIC + '进位'))
        self.assertFalse({'topic_hint', 'error_hint'} & set(remark))  # only a line that starts with the exact prefix
        superseded = self._item(self._tagged(title='数学错题：旧交接格式', topic=None, error=None,
                                             body=self.BODY + '\n知识点：进位加法\n错误类型：进位漏加（候选，家长已核对）'))
        self.assertFalse({'topic_hint', 'error_hint'} & set(superseded))  # no second line format
        note = self._note()
        exam = app.save_record(dict(child='小明', day='2026-09-15', category='成绩', subject='数学', title='虚构小测',
                                    score='80', total='100', note=note))['record_id']
        recheck = app.save_record(dict(child='小明', day='2026-09-16', category='学习进展', subject='数学', title='复测',
                                       note=note, source='家长观察', related_record_id=far, followup_kind='复测'))['record_id']
        for other in (exam, recheck):
            self.assertFalse({'topic_hint', 'error_hint'} & set(self._item(other)))

    def test_a_kept_tag_alone_never_becomes_a_conclusion(self):
        import datetime as dt
        tagged = self._tagged()
        base = dt.datetime(2026, 9, 20, 10, 0, 0)
        def run(*comps):
            draft = dict(knowledge_components=[dict(name=name, error_type='进位漏加', misconception='个位满十未进1', status=status,
                         evidence=refs, suggestion='') for name, status, refs in comps], summary='', uncertainties=[])
            with patch.object(family_llm, '_chat_json', return_value=draft):
                return diag.diagnose(_app(), 'child-1', '数学', now=base)['diagnosis']['knowledge_components']
        # The model repeats the parent's tag as a finding without citing any real record (or only an invented one).
        parroted = run(('两位数进位加法', '有支持', []), ('两位数进位加法（已改善）', '有反证', ['record:99999']))
        self.assertEqual([(c['status'], c['evidence'], c['review_on']) for c in parroted], [('待验证', [], ''), ('待验证', [], '')])
        self.assertEqual(diag.due_reviews(_app(), 'child-1', now=base + dt.timedelta(days=30)), [])  # no re-check, no reminder
        self.assertEqual([k['status'] for k in self._math()['diagnosis']['knowledge_components']], ['待验证', '待验证'])
        # Citing this child's real record keeps the model's status; the parent checks it by opening that record.
        cited = run(('两位数进位加法', '有支持', ['record:%d' % tagged]))[0]
        self.assertEqual((cited['status'], cited['evidence'], cited['review_on']), ('有支持', ['record:%d' % tagged], '2026-09-27'))

    def test_counter_evidence_overrides_a_parent_kept_tag(self):
        import datetime as dt
        tagged = self._tagged()
        ref = 'record:%d' % tagged
        def run(when, status, refs):
            draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加', misconception='个位满十未进1',
                         status=status, evidence=refs, suggestion='')], summary='', uncertainties=[])
            with patch.object(family_llm, '_chat_json', return_value=draft):
                return diag.diagnose(_app(), 'child-1', '数学', now=when)['diagnosis']['knowledge_components'][0]
        base = dt.datetime(2026, 9, 20, 10, 0, 0)
        self.assertEqual(run(base, '有支持', [ref])['review_on'], '2026-09-27')
        self.assertEqual([d['record_id'] for d in diag.due_reviews(_app(), 'child-1', now=base + dt.timedelta(days=7))], [tagged])
        recheck = app.save_record(dict(child='小明', day='2026-09-27', category='学习进展', subject='数学', title='复测：进位加法',
                                       note='新题 47+6=53，自己做对', source='家长观察', related_record_id=tagged, followup_kind='复测',
                                       assistance='独立尝试', practice_relation='相近的新题或新片段'))['record_id']
        self.assertTrue(self._math(now=base)['evidence_changed'])
        # The model gets the kept tag and the later independent re-check side by side, so the evidence can win.
        self.assertEqual(self._item(tagged)['topic_hint'], '两位数进位加法')
        later = self._item(recheck)
        self.assertEqual((later['related'], later['assistance'], later['practice_relation']), (ref, '独立尝试', '相近的新题或新片段'))
        self.assertFalse({'topic_hint', 'error_hint'} & set(later))
        cleared = run(base + dt.timedelta(days=7), '有反证', [ref, 'record:%d' % recheck])
        self.assertEqual((cleared['status'], cleared['review_on']), ('有反证', ''))
        after = base + dt.timedelta(days=30)
        self.assertEqual(diag.due_reviews(_app(), 'child-1', now=after), [])
        view = self._math(now=after)
        self.assertEqual((view['due_count'], view['evidence_changed']), (0, False))
        kc = view['diagnosis']['knowledge_components'][0]
        self.assertEqual(kc['status'], '有反证')
        # The tag stays what the parent saved (a starting point on the record); it is not rewritten as a finding.
        self.assertEqual(next(e for e in kc['evidence'] if e['id'] == tagged)['topic_hint'], '两位数进位加法')
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT note FROM records WHERE id=?', (tagged,)).fetchone()[0], self._note())

    def test_correcting_or_clearing_a_tag_outdates_only_that_subject(self):
        tagged = self._tagged()
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加', misconception='待核对', status='待验证',
                     evidence=['record:%d' % tagged], suggestion='')], summary='', uncertainties=[])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            diag.diagnose(_app(), 'child-1', '数学'); diag.diagnose(_app(), 'child-1', '语文')
        self.assertEqual(diag.stale_subjects(_app(), 'child-1'), [])
        def rewrite(**note):
            app.save_record(dict(id=tagged, child='小明', day='2026-09-14', category='学习进展', subject='数学', title='数学错题：第7题',
                                 note=self._note(**note), source=diag.WRONG_SOURCE))
        rewrite(topic='两位数进位加法', error='数位对齐错误')  # the parent corrects the candidate in the original record
        self.assertEqual([s['subject'] for s in diag.stale_subjects(_app(), 'child-1')], ['数学'])
        view = self._math()
        self.assertTrue(view['evidence_changed'])
        self.assertEqual(view['diagnosis']['knowledge_components'][0]['evidence'][0]['error_hint'], '数位对齐错误')  # as the record says now
        self.assertFalse(next(s for s in diag.overview(_app(), 'child-1')['subjects'] if s['subject'] == '语文')['evidence_changed'])
        rewrite(topic=None, error=None)  # cleared tags write no line: the record diagnoses like an untagged one
        self.assertFalse({'topic_hint', 'error_hint'} & set(self._item(tagged)))
        self.assertEqual(self._math()['tagged_count'], 0)

    def test_tags_never_cross_children(self):
        mine = self._tagged()
        hers = self._tagged(child='小红', title='数学错题：第2题', topic='退位减法', error='借位漏减')
        text = str(diag.evidence(_app(), 'child-1', '数学')) + str(diag.overview(_app(), 'child-1'))
        self.assertNotIn('退位减法', text); self.assertNotIn('借位漏减', text)
        self.assertEqual((self._math()['tagged_count'], self._math('child-2')['tagged_count']), (1, 1))
        self.assertEqual(self._item(hers, 'child-2')['topic_hint'], '退位减法')
        # 小明's diagnosis cannot cite 小红's tagged record, even if the model names it.
        draft = dict(knowledge_components=[dict(name='退位减法', error_type='借位漏减', misconception='待核对', status='有支持',
                     evidence=['record:%d' % hers], suggestion='')], summary='', uncertainties=[])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            comp = diag.diagnose(_app(), 'child-1', '数学')['diagnosis']['knowledge_components'][0]
        self.assertEqual((comp['status'], comp['evidence'], comp['review_on']), ('待验证', [], ''))
        # A cited tagged record later corrected to the other child shows as unavailable, without its tag.
        draft['knowledge_components'][0].update(name='两位数进位加法', evidence=['record:%d' % mine])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            diag.diagnose(_app(), 'child-1', '数学')
        app.save_record(dict(id=mine, child='小红', day='2026-09-14', category='学习进展', subject='数学', title='数学错题：第7题',
                             note=self._note(), source=diag.WRONG_SOURCE))
        kc = self._math()['diagnosis']['knowledge_components'][0]
        self.assertEqual(kc['evidence'], [dict(ref='record:%d' % mine, id=mine, available=False, kind='', day='', title='', remediable=False)])


if __name__ == '__main__':
    unittest.main()
