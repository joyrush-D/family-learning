"""错题网页核对入库：标注草稿只读、保存成 错题 学习记录并关联原件。合成数据。"""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQ0AAAAASUVORK5CYII=')

DRAFT = dict(pages=[dict(page=1, regions=[
    dict(kind='wrong_item', box=dict(x=100, y=120, w=300, h=90), label='第3题',
         text='27 + 8 = ?', answer='35', correction='35 应为 35？订正 35', uncertain=False),
    dict(kind='layout', box=dict(x=0, y=0, w=1000, h=60), label='卷头', text='数学小测', answer='', correction='', uncertain=False),
])], uncertainties=['第3题字迹较淡，请核对'])


class WrongQuestionReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self._prev = (app.ROOT, app.DATA, app.DB)
        app.ROOT, app.DATA, app.DB = root, root/'private', root/'private'/'family.sqlite3'
        app.DATA.mkdir(parents=True)
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        (app.DATA/'uploads').mkdir()
        self.uid = 'a'*32
        (app.DATA/'uploads'/self.uid).write_bytes(PNG)
        with app.connect() as c:
            c.execute('INSERT INTO uploads VALUES (?,?,?,?,?)', (self.uid, '错题.png', len(PNG), 'image/png', '2026-09-16'))
        self.addCleanup(lambda: setattr(app, 'ROOT', self._prev[0]))
        self.addCleanup(lambda: setattr(app, 'DATA', self._prev[1]))
        self.addCleanup(lambda: setattr(app, 'DB', self._prev[2]))

    def test_annotate_returns_draft_and_saves_nothing(self):
        with app.connect() as c:
            before = c.execute('SELECT count(*) FROM records').fetchone()[0]
        with patch.object(app.family_wrong_questions, 'annotate_pages', return_value=DRAFT) as m:
            out = app.wrong_questions_annotate(dict(child_id='child-1', subject_hint='数学', attachments=[self.uid]))
        self.assertTrue(out['ok'])
        self.assertEqual(out['draft'], DRAFT)
        self.assertEqual(out['attachments'], [self.uid])  # order preserved for mapping page->original
        # It read the uploaded image bytes and passed them to the model, and persisted nothing.
        images = m.call_args[0][0]
        self.assertEqual(images[0]['data'], PNG)
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0], before)

    def test_annotate_rejects_bad_input(self):
        for bad in [dict(child_id='nope', subject_hint='', attachments=[self.uid]),
                    dict(child_id='child-1', subject_hint='', attachments=['zzz']),
                    dict(child_id='child-1', subject_hint='', attachments=[self.uid], extra=1)]:
            with self.assertRaises(ValueError):
                with patch.object(app.family_wrong_questions, 'annotate_pages', return_value=DRAFT):
                    app.wrong_questions_annotate(bad)

    def test_save_creates_wrong_question_records_with_attachment(self):
        items = [dict(label='第3题', text='27 + 8 = ?', answer='35', correction='正确 35',
                      topic_hint='两位数进位加法', error_hint='进位漏加', upload_id=self.uid)]
        out = app.wrong_questions_save(dict(child_id='child-1', day='2026-09-16', subject='数学',
                                            request_key='synthetic-wrongq-000001', items=items))
        self.assertTrue(out['ok']); self.assertEqual(len(out['saved']), 1)
        rid = out['saved'][0]['record_id']
        with app.connect() as c:
            row = c.execute("SELECT category,note,subject,title,attachments FROM records WHERE id=?", (rid,)).fetchone()
        self.assertEqual(row['category'], '错题'); self.assertEqual(row['subject'], '数学')
        self.assertTrue(row['title'].startswith('错题：第3题'))
        self.assertIn(self.uid, row['attachments'])
        for fragment in ['题面：27 + 8', '学生作答：35', '订正/正确答案：正确 35', '知识点候选（待核对）：两位数进位加法', '错误类型候选（待核对）：进位漏加']:
            self.assertIn(fragment, row['note'])
        # 错题 is now a valid record category.
        self.assertIn('错题', app.CATEGORIES)

    def test_save_is_idempotent_per_item(self):
        items = [dict(label='第1题', text='a', answer='', correction='', topic_hint='', error_hint='', upload_id='')]
        body = dict(child_id='child-1', day='2026-09-16', subject='语文', request_key='synthetic-wrongq-000009', items=items)
        first = app.wrong_questions_save(body)['saved'][0]['record_id']
        again = app.wrong_questions_save(body)['saved'][0]['record_id']
        self.assertEqual(first, again)
        with app.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM records WHERE category='错题'").fetchone()[0], 1)

    def test_save_rejects_bad_input(self):
        good = dict(child_id='child-1', day='2026-09-16', subject='数学', request_key='synthetic-wrongq-000002',
                    items=[dict(label='x', text='', answer='', correction='', topic_hint='', error_hint='', upload_id='')])
        for bad in [dict(good, child_id='nope'), dict(good, day='2026-13-40'), dict(good, request_key='short'),
                    dict(good, items=[]), dict(good, items=[dict(label='x', junk=1)])]:
            with self.assertRaises((ValueError,)):
                app.wrong_questions_save(bad)


if __name__ == '__main__':
    unittest.main()
