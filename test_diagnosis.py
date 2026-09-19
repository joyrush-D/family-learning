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


if __name__ == '__main__':
    unittest.main()
