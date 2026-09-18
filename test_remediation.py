"""④ 引导讲解播种：从一道已核对错题开一个短引导草稿（复用 family_guided，答案安全）。合成数据。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import app
import family_remediation as rem


def _ns():
    return SimpleNamespace(connect=app.connect, profiles=app.profiles, guided_store=app.guided_store)


NOTE = '题面：27 + 8 = ?\n学生原答：315\n可见订正/正确答案：35\n由照片标注生成，家长已核对；这不是掌握程度结论。'


class RemediationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self._prev = dict(ROOT=app.ROOT, DATA=app.DATA, DB=app.DB)
        app.ROOT, app.DATA, app.DB = root, root/'private', root/'private'/'family.sqlite3'
        app.DATA.mkdir(parents=True)
        (root/'家庭运行规则.md').write_text('| child-1 | 小明 | 男 | 9岁 | 三年级 |\n')
        r = app.save_record(dict(child='小明', day='2026-09-16', category='学习进展', subject='数学',
                                 title='数学错题：第3题', note=NOTE, source=rem.WRONG_SOURCE))
        self.rid = r['record_id']
        for k, v in self._prev.items():
            self.addCleanup((lambda kk, vv: (lambda: setattr(app, kk, vv)))(k, v))

    def test_parse_note(self):
        q, ref = rem.parse_wrong_note(NOTE)
        self.assertEqual(q, '27 + 8 = ?'); self.assertEqual(ref, '35')

    def test_seeds_a_guided_draft_from_the_wrong_question(self):
        out = rem.from_wrong_question(_ns(), dict(child_id='child-1', record_id=self.rid, request_key='synthetic-remediate-0001'))
        sid = out['session_id']; self.assertTrue(sid)
        with app.connect() as c:
            s = c.execute('SELECT * FROM guided_sessions WHERE id=?', (sid,)).fetchone()
        self.assertEqual(s['question_text'], '27 + 8 = ?')       # child re-works the same mistake
        self.assertEqual(s['reference_text'], '35')               # parent reference carried, not shown to child yet
        self.assertEqual(s['reference_checked'], 0)               # parent must confirm the reference in the 短引导 UI
        self.assertEqual(s['shared'], 0)                          # a draft; not pushed to the child until the parent shares
        self.assertEqual(s['related_record_id'], self.rid)        # tied back to the original 错题
        self.assertEqual(s['subject'], '数学')
        self.assertTrue(s['title'].startswith('订正 · '))

    def test_idempotent_request(self):
        body = dict(child_id='child-1', record_id=self.rid, request_key='synthetic-remediate-0009')
        a = rem.from_wrong_question(_ns(), body)['session_id']
        b = rem.from_wrong_question(_ns(), body)['session_id']
        self.assertEqual(a, b)
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM guided_sessions').fetchone()[0], 1)

    def test_rejects_non_wrong_or_foreign_records(self):
        plain = app.save_record(dict(child='小明', day='2026-09-16', category='学习进展', subject='数学',
                                     title='普通观察', note='今天状态不错', source='家长观察'))['record_id']
        for bad in [dict(child_id='child-1', record_id=plain, request_key='synthetic-remediate-0002'),
                    dict(child_id='child-1', record_id=999999, request_key='synthetic-remediate-0003'),
                    dict(child_id='child-1', record_id=self.rid, request_key='short'),
                    dict(child_id='nobody', record_id=self.rid, request_key='synthetic-remediate-0004')]:
            with self.assertRaises(rem.RemediationError):
                rem.from_wrong_question(_ns(), bad)


if __name__ == '__main__':
    unittest.main()
