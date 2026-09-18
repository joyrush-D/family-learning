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
        (root/'家庭运行规则.md').write_text('| child-1 | 小明 | 男 | 9岁 | 三年级 |\n')
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

    def test_no_evidence_returns_note_without_calling_model(self):
        called = []
        with patch.object(family_llm, '_chat_json', side_effect=lambda *a, **k: called.append(1)):
            out = diag.diagnose(_app(), 'child-1', '英语')  # no 英语 records
        self.assertEqual(out['diagnosis']['knowledge_components'], [])
        self.assertTrue(out['diagnosis']['uncertainties'])
        self.assertEqual(called, [])  # no model call when there is nothing to diagnose


if __name__ == '__main__':
    unittest.main()
