"""原错题→知识点→上游诊断逐题保存→看说明→新题再试（DeepTutor原LearningService）→复测原记录。合成数据。

知识包是虚构小图谱（不是上游题库，也不代表教师审核）；DeepTutor判定在设置FAMILY_DEEPTUTOR_PYTHON
（py>=3.11+pydantic2）时真实运行deeptutor_sidecar.py，未设置时只验证“未配置只降级这一步、零写入”。"""
import hashlib, json, os, sqlite3, tempfile, unittest
from pathlib import Path
from unittest import mock

import app
import family_deeptutor
import family_taxonomy as ft

TOPICS = [{'id': 'cnm_t1', 'name': '分数与小数互化', 'chapter': '五下 第4单元'},
          {'id': 'cnm_t2', 'name': '小数加法', 'chapter': '五上 第1单元'},
          {'id': 'cnm_t9', 'name': '无关的点', 'chapter': '一上'}]
DEPS = [{'topicId': 'cnm_t2', 'prerequisiteId': 'cnm_t1', 'strength': 'hard'}]
QS = [{'id': 'cnm_t1_q%d' % i, 'topicId': 'cnm_t1', 'type': 'numeric', 'prompt': '1/2写成小数？', 'answer': '0.5', 'explanation': '1÷2=0.5'} for i in (1, 2, 3)] + \
     [{'id': 'cnm_t2_q1', 'topicId': 'cnm_t2', 'type': 'numeric', 'prompt': '0.2+0.3=?', 'answer': '0.5', 'explanation': '十分位相加'},
      {'id': 'cnm_t2_q2', 'topicId': 'cnm_t2', 'type': 'choice', 'prompt': '0.1+0.1=?', 'choices': [{'key': 'A', 'text': '0.2'}, {'key': 'B', 'text': '0.11'}], 'answer': 'A'},
      {'id': 'cnm_t9_q1', 'topicId': 'cnm_t9', 'type': 'numeric', 'prompt': '1+1', 'answer': '2'}]
NOTE = '题面：0.2+0.3=?\n学生原答：0.23\n可见订正/正确答案：0.5\n由照片标注生成，家长已核对；这不是掌握程度结论。'
DT_PYTHON = os.environ.get('FAMILY_DEEPTUTOR_PYTHON', '')


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve(); prev = dict(ROOT=app.ROOT, DATA=app.DATA, DB=app.DB)
        app.ROOT, app.DATA, app.DB = root, root / 'private', root / 'private' / 'family.sqlite3'
        app.DATA.mkdir(parents=True)
        (root / '家庭运行规则.md').write_text('| child-1 | 小明 | 男 | 9岁 | 三年级 |\n| child-2 | 小红 | 女 | 7岁 | 一年级 |\n')
        for k, v in prev.items(): self.addCleanup(setattr, app, k, v)
        self.rid = app.save_record(dict(child='小明', day='2026-10-20', category='学习进展', subject='数学', title='数学错题：第2题',
                                        note=NOTE, source=ft.WRONG_SOURCE))['record_id']
        pack = root / 'pack'; files = {'data/topics.json': TOPICS, 'data/dependencies.json': DEPS, 'data/questions.json': QS}
        manifest = {}
        for rel, body in list(files.items()) + [('diagnose/engine.js', None)]:
            (pack / rel).parent.mkdir(parents=True, exist_ok=True)
            raw = b'/* fabricated test placeholder, not the upstream engine */' if body is None else json.dumps(body, ensure_ascii=False).encode()
            (pack / rel).write_bytes(raw); manifest[rel] = (hashlib.sha256(raw).hexdigest(), len(raw))
        self.pack = pack
        patcher = mock.patch.object(ft, 'MANIFEST', manifest); patcher.start(); self.addCleanup(patcher.stop)
        ft._PACKS.clear(); ft._VERIFIED.clear()
        self.ns = app  # 与app.py路由一致：connect/profiles/save_record

    def call(self, fn, **obj):
        return fn(self.ns, dict(child_id='child-1', record_id=self.rid, **obj), self.pack)

    def tables(self):
        with app.connect() as c: return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'topic_%'")}

    def started(self):
        self.call(ft.link_record, topic_id='cnm_t2', state='confirmed', request_id='link-request-000001')
        return self.call(ft.start, topic_id='cnm_t2', request_id='start-request-00001')['diagnoses'][0]

    def answer(self, d, seq, qid, topic, kind='answer', text='0.23', verdict='wrong'):
        result = verdict if verdict in ('correct', 'wrong') else 'skip'
        answers = [{'id': 'cnm_t2', 'qid': 'x', 'result': 'wrong'}] * (seq - 1) + [{'id': topic, 'qid': qid, 'result': result, 'text': text}]
        return self.call(ft.answer, diagnosis_id=d['id'], seq=seq, topic_id=topic, qid=qid, kind=kind, answer=text, verdict=verdict,
                         engine_result=result, session={'answers': answers}, summary={'finished': False})

    def test_cross_child_is_403_with_zero_writes(self):
        with self.assertRaises(ft.TaxonomyError) as e:
            ft.state(self.ns, dict(child_id='child-2', record_id=self.rid), self.pack)
        self.assertEqual(e.exception.status, 403); self.assertEqual(self.tables(), set())
        with self.assertRaises(ft.TaxonomyError) as e:
            ft.link_record(self.ns, dict(child_id='child-2', record_id=self.rid, topic_id='cnm_t2', state='confirmed', request_id='link-request-cross1'), self.pack)
        self.assertEqual(e.exception.status, 403); self.assertEqual(self.tables(), set())

    def test_unknown_and_no_match_go_back_to_the_original_material(self):
        self.assertEqual(self.call(ft.search_record, query='三角函数')['status'], 'none')
        self.assertEqual(self.call(ft.search_record, query='小数')['status'], 'ambiguous')
        out = self.call(ft.link_record, state='no_match', request_id='link-request-nomatch')
        self.assertEqual(out['links'][-1]['topic_id'], '')
        with self.assertRaises(ft.TaxonomyError) as e: self.call(ft.start, topic_id='cnm_t2', request_id='start-request-nolink1')
        self.assertEqual(e.exception.code, 'topic_not_confirmed')

    def test_items_are_idempotent_scoped_and_ordered(self):
        d = self.started()
        self.assertEqual(self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2')['diagnoses'][0]['items'][0]['verdict'], 'wrong')
        again = self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2')  # 丢回执后同一题原样重发
        self.assertTrue(again['replayed']); self.assertEqual(len(again['diagnoses'][0]['items']), 1)
        with self.assertRaises(ft.TaxonomyError) as e: self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2', text='0.5', verdict='correct')
        self.assertEqual(e.exception.code, 'item_conflict')
        with self.assertRaises(ft.TaxonomyError) as e: self.answer(d, 2, 'cnm_t9_q1', 'cnm_t9')
        self.assertEqual(e.exception.code, 'qid_outside_scope')
        self.answer(d, 2, 'cnm_t1_q1', 'cnm_t1', kind='unknown', text='', verdict='skip')
        st = self.call(ft.mark, diagnosis_id=d['id'], action='help_explanation', seq=1)
        self.assertEqual(st['diagnoses'][0]['items'][0]['help'], 'explanation')
        self.call(ft.mark, diagnosis_id=d['id'], action='pause')
        reopened = self.call(ft.state)  # 刷新重开：逐题原答、帮助、暂停都在
        self.assertEqual([i['kind'] for i in reopened['diagnoses'][0]['items']], ['answer', 'unknown'])
        self.assertEqual(reopened['diagnoses'][0]['state'], 'paused'); self.assertEqual(reopened['graph']['target'], 'cnm_t2')
        self.assertNotIn('cnm_t9', [t['id'] for t in reopened['graph']['topics']])

    def test_corrected_original_invalidates_the_basis(self):
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2')
        with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?', (NOTE.replace('0.23', '0.32'), self.rid))
        st = self.call(ft.state)
        self.assertEqual(st['diagnoses'][0]['basis'], 'basis_changed'); self.assertEqual(st['links'][-1]['basis'], 'basis_changed')
        with self.assertRaises(ft.TaxonomyError) as e: self.answer(d, 2, 'cnm_t1_q1', 'cnm_t1')
        self.assertEqual(e.exception.code, 'basis_changed')
        with self.assertRaises(ft.TaxonomyError) as e:
            self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t1_q2', answer='0.5', verdict='correct', request_id='retry-request-stale1')
        self.assertEqual(e.exception.code, 'basis_changed')

    def test_seen_question_is_not_independent_and_skips_the_grader(self):
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2')
        with mock.patch.object(family_deeptutor, 'call', side_effect=AssertionError('must not grade a seen question')):
            st = self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t2_q1', answer='0.5', verdict='correct', request_id='retry-request-seen01')
        self.assertEqual(st['diagnoses'][0]['retries'][0]['outcome'], 'not_new')
        with app.connect() as c: self.assertEqual(c.execute("SELECT count(*) FROM records WHERE followup_kind='复测'").fetchone()[0], 0)

    def test_unconfigured_grader_degrades_only_this_step(self):
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2')
        with mock.patch.dict(os.environ, {'FAMILY_DEEPTUTOR_PYTHON': ''}):
            with self.assertRaises(family_deeptutor.DeepTutorUnavailable):
                self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t1_q2', answer='0.5', verdict='correct', request_id='retry-request-nodt01')
        st = self.call(ft.state)
        self.assertEqual(st['diagnoses'][0]['retries'], []); self.assertEqual(len(st['diagnoses'][0]['items']), 1)

    @unittest.skipUnless(DT_PYTHON, '需要FAMILY_DEEPTUTOR_PYTHON（py>=3.11+pydantic2）真实运行DeepTutor')
    def test_new_question_retry_runs_deeptutor_and_writes_one_followup(self):
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2'); self.call(ft.mark, diagnosis_id=d['id'], action='help_explanation', seq=1)
        st = self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t2_q2', answer='A', verdict='correct', request_id='retry-request-new001')
        r = st['diagnoses'][0]['retries'][0]
        self.assertEqual(r['outcome'], 'independent_correct'); self.assertIs(r['deeptutor']['independent'], True); self.assertIs(r['deeptutor']['is_correct'], True)
        again = self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t2_q2', answer='A', verdict='correct', request_id='retry-request-new001')
        self.assertTrue(again['replayed'])
        with app.connect() as c:
            rows = c.execute("SELECT related_record_id,assistance,practice_relation FROM records WHERE followup_kind='复测'").fetchall()
        self.assertEqual([tuple(x) for x in rows], [(self.rid, '独立尝试', '相近的新题或新片段')])
        # 判题器分歧：上游判1/2与0.5等值为对，DeepTutor按文本判错→交家长，不写复测。
        st = self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t1_q1', answer='1/2', verdict='correct', request_id='retry-request-split1')
        self.assertEqual(st['diagnoses'][0]['retries'][-1]['outcome'], 'parent_check')
        with app.connect() as c: self.assertEqual(c.execute("SELECT count(*) FROM records WHERE followup_kind='复测'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
