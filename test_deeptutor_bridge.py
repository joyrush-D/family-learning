"""原错题→知识点→上游诊断逐题保存→看说明→新题再试（DeepTutor原LearningService）→复测原记录。合成数据。

知识包是虚构小图谱（不是上游题库，也不代表教师审核）；DeepTutor判定在设置FAMILY_DEEPTUTOR_PYTHON
（py>=3.11+pydantic2）时真实运行deeptutor_sidecar.py，未设置时只验证“未配置只降级这一步、零写入”。"""
import hashlib, json, os, shutil, sqlite3, subprocess, sys, tempfile, unittest
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

    def offer(self, d, qid):
        return self.call(ft.mark, diagnosis_id=d['id'], action='shown', mode='retry', qid=qid)

    def counts(self):
        with app.connect() as c:
            out = {t: c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in sorted(self.tables())}
            out['records'] = c.execute('SELECT count(*) FROM records').fetchone()[0]
        return out

    def fake_dt(self, op, snapshot, **kw):  # 只用于桥接逻辑；真实判定见test_new_question_retry_runs_deeptutor…
        self.dt_calls.append((op, kw.get('question_id')))
        if op == 'register': return {'snapshot': 'S1'}
        if op == 'grade': return {'snapshot': 'S2', 'replayed': False, 'deeptutor_sha': 'x',
                                  'interaction': {'result': {'is_correct': kw['answer'] == 'A', 'independent': True}}}
        if op == 'void': return {'snapshot': snapshot + '+void', 'attempts': [{'question_id': kw['question_id'], 'voided': True}]}
        raise AssertionError(op)

    def test_every_mutation_returns_the_full_state(self):
        # R5：确认/说不清/无匹配后面板拿到的是完整状态（知识包、链接、诊断、图谱），不会误报“知识包未安装”。
        full = {'ok', 'record', 'links', 'diagnoses', 'seen_qids', 'pack', 'deeptutor', 'topics'}
        for state, rid in (('unclear', 'link-request-unclr1'), ('no_match', 'link-request-nomtc1')):
            out = self.call(ft.link_record, state=state, request_id=rid)
            self.assertTrue(full <= set(out), set(out)); self.assertTrue(out['pack']['installed']); self.assertNotIn('graph', out)
        out = self.call(ft.link_record, topic_id='cnm_t2', state='confirmed', request_id='link-request-000001')
        self.assertTrue(full <= set(out)); self.assertTrue(out['pack']['installed']); self.assertFalse(out['replayed'])
        self.assertEqual((out['graph']['target'], out['topics']['cnm_t2']['name'], out['links'][-1]['state']), ('cnm_t2', '小数加法', 'confirmed'))
        st = self.call(ft.start, topic_id='cnm_t2', request_id='start-request-00001')
        self.assertTrue(full <= set(st) and st['graph']['target'] == 'cnm_t2'); d = st['diagnoses'][0]
        st = self.call(ft.mark, diagnosis_id=d['id'], action='shown', mode='diagnosis', qid='cnm_t2_q1')
        self.assertTrue(full <= set(st)); self.assertEqual(st['diagnoses'][0]['shown'], ['cnm_t2_q1'])

    def test_same_request_id_with_other_content_is_409_with_zero_writes(self):
        other = app.save_record(dict(child='小明', day='2026-10-21', category='学习进展', subject='数学', title='数学错题：第5题',
                                     note=NOTE, source=ft.WRONG_SOURCE))['record_id']
        self.call(ft.link_record, topic_id='cnm_t2', state='confirmed', request_id='link-request-000001')
        self.assertTrue(self.call(ft.link_record, topic_id='cnm_t2', state='confirmed', request_id='link-request-000001')['replayed'])
        d = self.call(ft.start, topic_id='cnm_t2', request_id='start-request-00001')['diagnoses'][0]
        self.assertTrue(self.call(ft.start, topic_id='cnm_t2', request_id='start-request-00001')['replayed'])
        before = self.counts()
        for fn, body in ((ft.link_record, dict(record_id=self.rid, topic_id='cnm_t1', state='confirmed', request_id='link-request-000001')),
                         (ft.link_record, dict(record_id=self.rid, state='unclear', request_id='link-request-000001')),
                         (ft.link_record, dict(record_id=other, topic_id='cnm_t2', state='confirmed', request_id='link-request-000001')),
                         (ft.start, dict(record_id=self.rid, topic_id='cnm_t1', request_id='start-request-00001')),
                         (ft.start, dict(record_id=other, topic_id='cnm_t2', request_id='start-request-00001'))):
            with self.assertRaises(ft.TaxonomyError) as e: fn(self.ns, dict(child_id='child-1', **body), self.pack)
            self.assertEqual((e.exception.status, e.exception.code), (409, 'request_conflict'), body)
        self.assertEqual(self.counts(), before)

    def test_retry_request_id_is_bound_to_its_payload(self):
        # R3：同编号D→A等改答必须409零写，不能静默“重放”；原样重发才读回，不重复写。
        self.dt_calls = []
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2'); self.offer(d, 'cnm_t2_q2')
        body = dict(diagnosis_id=d['id'], qid='cnm_t2_q2', answer='D', verdict='wrong', request_id='retry-request-pay001')
        with mock.patch.object(family_deeptutor, 'call', side_effect=self.fake_dt):
            self.assertEqual(self.call(ft.retry, **body)['diagnoses'][0]['retries'][0]['answer'], 'D')
            before = self.counts()
            for change in (dict(answer='A', verdict='correct'), dict(answer='A'), dict(verdict='manual'), dict(qid='cnm_t1_q1'), dict(diagnosis_id=d['id'] + 1)):
                with self.assertRaises(ft.TaxonomyError) as e: self.call(ft.retry, **dict(body, **change))
                self.assertEqual((e.exception.status, e.exception.code), (409, 'request_conflict'), change)
            self.assertEqual(self.counts(), before)
            again = self.call(ft.retry, **body)
        self.assertTrue(again['replayed']); self.assertEqual(self.counts(), before); self.assertEqual(again['diagnoses'][0]['retries'][0]['answer'], 'D')
        self.assertEqual([op for op, _ in self.dt_calls], ['register', 'grade'])

    def test_history_across_diagnoses_blocks_seen_shown_or_helped_questions(self):
        # R1：诊断A答错并看过说明的题、A里只出示没提交的题，在同一原错题重开的诊断B里都不算新题；不调判定器、不写复测。
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2'); self.call(ft.mark, diagnosis_id=d['id'], action='help_explanation', seq=1)
        self.call(ft.mark, diagnosis_id=d['id'], action='shown', mode='diagnosis', qid='cnm_t1_q3')
        b = self.call(ft.start, topic_id='cnm_t2', request_id='start-request-00002')['diagnoses'][0]
        self.assertNotEqual(b['id'], d['id']); self.answer(b, 1, 'cnm_t1_q1', 'cnm_t1', text='0.5', verdict='correct')
        st = self.call(ft.state)
        self.assertTrue({'cnm_t2_q1', 'cnm_t1_q3', 'cnm_t1_q1'} <= set(st['seen_qids']))
        before = self.counts()
        for qid in ('cnm_t2_q1', 'cnm_t1_q3', 'cnm_t1_q1'):
            with self.assertRaises(ft.TaxonomyError) as e: self.offer(b, qid)
            self.assertEqual((e.exception.status, e.exception.code), (409, 'not_new'))
        self.assertEqual(self.counts(), before)
        with self.assertRaises(ft.TaxonomyError) as e:  # 没在面板上出示过的题不能直接当新题交
            self.call(ft.retry, diagnosis_id=b['id'], qid='cnm_t1_q2', answer='0.5', verdict='correct', request_id='retry-request-cross0')
        self.assertEqual(e.exception.code, 'retry_not_offered'); self.assertEqual(self.counts(), before)
        with mock.patch.object(family_deeptutor, 'call', side_effect=AssertionError('must not grade a seen question')):
            st = self.call(ft.retry, diagnosis_id=b['id'], qid='cnm_t2_q1', answer='0.5', verdict='correct', request_id='retry-request-cross1')
        self.assertEqual(st['diagnoses'][0]['retries'][0]['outcome'], 'not_new')
        # 新题出示给B后，若又在别的诊断里出现，B的这次再试也不再算独立。
        self.offer(b, 'cnm_t1_q2'); self.assertTrue(self.call(ft.state)['diagnoses'][0]['retry_offer']['fresh'])
        self.call(ft.mark, diagnosis_id=d['id'], action='shown', mode='diagnosis', qid='cnm_t1_q2')
        self.assertFalse(self.call(ft.state)['diagnoses'][0]['retry_offer']['fresh'])
        with app.connect() as c: self.assertEqual(c.execute("SELECT count(*) FROM records WHERE followup_kind='复测'").fetchone()[0], 0)
        # 另一个孩子不受这些历史影响，也看不到
        with self.assertRaises(ft.TaxonomyError) as e: ft.state(self.ns, dict(child_id='child-2', record_id=self.rid), self.pack)
        self.assertEqual(e.exception.status, 403)

    def test_correction_voids_old_deeptutor_attempts_or_marks_them_pending(self):
        # R2：更正后旧快照里已判定的作答经原repair_question(void)作废；组件不可用先记“待作废”，恢复后安全重试一次。
        self.dt_calls = []
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2'); self.offer(d, 'cnm_t2_q2')
        with mock.patch.object(family_deeptutor, 'call', side_effect=self.fake_dt):
            self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t2_q2', answer='A', verdict='correct', request_id='retry-request-void01')
        with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?', (NOTE.replace('0.23', '0.32'), self.rid))
        with mock.patch.dict(os.environ, {'FAMILY_DEEPTUTOR_PYTHON': ''}): st = self.call(ft.state)
        old = st['diagnoses'][0]
        self.assertEqual((old['basis'], old['void']['state']), ('basis_changed', 'pending'))
        self.assertEqual((old['retries'][0]['answer'], old['retries'][0]['outcome']), ('A', 'independent_correct'))  # 原话保留，只标依据已变
        self.assertIn('cnm_t2_q2', st['seen_qids']); self.assertNotIn('graph', st)  # 更正洗不掉已见历史；旧诊断不再当当前
        with mock.patch.object(family_deeptutor, 'call', side_effect=self.fake_dt): st = self.call(ft.state)
        self.assertEqual(st['diagnoses'][0]['void'], {'state': 'voided', 'question_ids': ['cnm_t2_q2']})
        self.assertIn(('void', 'cnm_t2_q2'), self.dt_calls)
        with app.connect() as c: self.assertEqual(c.execute('SELECT deeptutor_snapshot FROM topic_diagnoses WHERE id=?', (d['id'],)).fetchone()[0], 'S2+void')
        with mock.patch.object(family_deeptutor, 'call', side_effect=AssertionError('void runs once')): self.call(ft.state)
        with app.connect() as c: self.assertEqual(c.execute("SELECT count(*) FROM records WHERE followup_kind='复测'").fetchone()[0], 1)

    def test_sidecar_env_has_no_home_and_uses_an_explicit_work_dir(self):
        seen = {}
        def run(cmd, **kw):
            seen.update(kw); return mock.Mock(stdout=json.dumps({'ok': True, 'snapshot': ''}) + '\n')
        tmp_root = str(Path(self.tmp.name) / 'dt-work')
        with mock.patch.dict(os.environ, {'FAMILY_DEEPTUTOR_PYTHON': sys.executable, 'FAMILY_DEEPTUTOR_TMP': tmp_root}), \
                mock.patch.object(family_deeptutor.subprocess, 'run', side_effect=run):
            family_deeptutor.call('status', '')
        work = seen['env']['DEEPTUTOR_HOME']
        self.assertNotIn('HOME', seen['env']); self.assertEqual(seen['cwd'], work); self.assertTrue(work.startswith(tmp_root))
        self.assertEqual(json.loads(seen['input'])['work_dir'], work); self.assertFalse(Path(work).exists())

    def test_gitignore_admits_only_the_reviewed_deeptutor_files(self):
        here, git = Path(__file__).resolve().parent, shutil.which('git')
        if not git: self.skipTest('需要git')
        prov = json.loads((here / 'third_party/deeptutor/PROVENANCE.json').read_text())
        for f in prov['files']:  # 33个原字节文件+1个标明修改的文件，长度与sha256逐个核对
            raw = (here / 'third_party/deeptutor' / f['path']).read_bytes()
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (f['bytes'], f['sha256']), f['path'])
        self.assertEqual([f['path'] for f in prov['files'] if f['modified']], ['src/deeptutor/learning/lesson_evidence.py'])
        repo = Path(self.tmp.name) / 'ignore-check'; repo.mkdir()
        subprocess.run([git, 'init', '-q', str(repo)], check=True); shutil.copy(here / '.gitignore', repo / '.gitignore')
        reviewed = sorted(str(p.relative_to(here)) for p in (here / 'third_party').rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        private = ['third_party/deeptutor/.env', 'third_party/deeptutor/private/child.json', 'third_party/deeptutor/runtime.sqlite3',
                   'third_party/deeptutor/logs/trace.log', 'third_party/deeptutor/src/deeptutor/learning/data.json',
                   'third_party/deeptutor/src/deeptutor/data/user/x.json', 'third_party/deeptutor/patches/new.diff', 'third_party/other/x.py',
                   'third_party/deeptutor/src/deeptutor/learning/__pycache__/service.cpython-311.pyc']
        out = subprocess.run([git, 'check-ignore', '--no-index', '--stdin'], cwd=repo, input='\n'.join(reviewed + private) + '\n',
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(len(reviewed), 37); self.assertEqual(sorted(out), sorted(private))

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
        self.offer(d, 'cnm_t1_q2')
        with mock.patch.dict(os.environ, {'FAMILY_DEEPTUTOR_PYTHON': ''}):
            with self.assertRaises(family_deeptutor.DeepTutorUnavailable):
                self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t1_q2', answer='0.5', verdict='correct', request_id='retry-request-nodt01')
        st = self.call(ft.state)
        self.assertEqual(st['diagnoses'][0]['retries'], []); self.assertEqual(len(st['diagnoses'][0]['items']), 1)

    @unittest.skipUnless(DT_PYTHON, '需要FAMILY_DEEPTUTOR_PYTHON（py>=3.11+pydantic2）真实运行DeepTutor')
    def test_new_question_retry_runs_deeptutor_and_writes_one_followup(self):
        d = self.started(); self.answer(d, 1, 'cnm_t2_q1', 'cnm_t2'); self.call(ft.mark, diagnosis_id=d['id'], action='help_explanation', seq=1)
        self.offer(d, 'cnm_t2_q2')
        st = self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t2_q2', answer='A', verdict='correct', request_id='retry-request-new001')
        r = st['diagnoses'][0]['retries'][0]
        self.assertEqual(r['outcome'], 'independent_correct'); self.assertIs(r['deeptutor']['independent'], True); self.assertIs(r['deeptutor']['is_correct'], True)
        again = self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t2_q2', answer='A', verdict='correct', request_id='retry-request-new001')
        self.assertTrue(again['replayed'])
        with app.connect() as c:
            rows = c.execute("SELECT related_record_id,assistance,practice_relation FROM records WHERE followup_kind='复测'").fetchall()
        self.assertEqual([tuple(x) for x in rows], [(self.rid, '独立尝试', '相近的新题或新片段')])
        # 判题器分歧：上游判1/2与0.5等值为对，DeepTutor按文本判错→交家长，不写复测。
        self.offer(d, 'cnm_t1_q1')
        st = self.call(ft.retry, diagnosis_id=d['id'], qid='cnm_t1_q1', answer='1/2', verdict='correct', request_id='retry-request-split1')
        self.assertEqual(st['diagnoses'][0]['retries'][-1]['outcome'], 'parent_check')
        with app.connect() as c: self.assertEqual(c.execute("SELECT count(*) FROM records WHERE followup_kind='复测'").fetchone()[0], 1)
        # 更正原错题→真实sidecar用原repair_question(void)作废旧快照里的两道已判定作答；快照真变了，原复测记录保留。
        with app.connect() as c:
            before = c.execute('SELECT deeptutor_snapshot FROM topic_diagnoses WHERE id=?', (d['id'],)).fetchone()[0]
            c.execute('UPDATE records SET note=? WHERE id=?', (NOTE.replace('0.23', '0.32'), self.rid))
        st = self.call(ft.state)
        self.assertEqual(st['diagnoses'][0]['void'], {'state': 'voided', 'question_ids': ['cnm_t2_q2', 'cnm_t1_q1']})
        with app.connect() as c: after = c.execute('SELECT deeptutor_snapshot FROM topic_diagnoses WHERE id=?', (d['id'],)).fetchone()[0]
        self.assertNotEqual(after, before)
        attempts = family_deeptutor.call('status', after, topic={'id': 'cnm_t2', 'name': '小数加法'})['attempts']
        self.assertTrue(attempts and all(a['voided'] for a in attempts), attempts)
        self.assertTrue(all(not a['voided'] for a in family_deeptutor.call('status', before, topic={'id': 'cnm_t2', 'name': '小数加法'})['attempts']))
        with app.connect() as c: self.assertEqual(c.execute("SELECT count(*) FROM records WHERE followup_kind='复测'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
