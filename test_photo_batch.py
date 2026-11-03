"""Synthetic contract for batch photo understanding (PRD 5.1 B1–B3).

Only fictional pages and fixed raw model JSON at the transport (``family_llm._chat_json``): every reply still passes the
real annotate, grouping and review validators. No real family data, configuration, network or product model.
"""
import base64
from http.client import HTTPConnection
import json
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote

import app
import family_agent
import family_llm
import family_photo_batch as fpb
import family_wrong_questions as fwq

PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000d49444154789c6360000002000100ffff03000006000557bfab4400'
    '00000049454e44ae426082')


def page_bytes(tag):
    return PNG + b'synthetic-' + tag.encode()


def evidence(subject, title, printed, kind='answered', readability='clear', first='', last=''):
    return dict(subject=subject, subject_basis='题面内容', title=title, printed_page=printed, first_label=first,
                last_label=last, head='虚构题面开头', tail='虚构题面结尾', page_kind=kind, readability=readability)


def region(label, y=200, kind='wrong_item'):
    return dict(kind=kind, box=dict(x=40, y=y, w=600, h=120), label=label, text='虚构题面', answer='35' if kind == 'wrong_item' else '',
                correction='', uncertain=False)


# Fictional pages: two math pages imported out of order, a Chinese page, an exact byte duplicate, a math answer key,
# an unreadable page, and a Chinese-text math word problem page that must stay math.
PAGES = {
    'm2': dict(evidence=evidence('数学', '虚构数学单元练习', '2', first='第5题', last='第6题'), regions=[region('第5题', 300), region('第6题', 500)]),
    'c1': dict(evidence=evidence('语文', '虚构语文小测', '1'), regions=[region('第2题', 260)]),
    'm1': dict(evidence=evidence('数学', '虚构数学单元练习', '1'), regions=[region('第2题', 240)]),
    'mk': dict(evidence=evidence('数学', '虚构数学单元练习 参考答案', '', kind='answer_key'), regions=[]),
    'blur': dict(evidence=evidence('', '', '', kind='other', readability='unreadable', first='', last=''), regions=[]),
}
ORDER = ['m2', 'c1', 'm1', 'dup', 'mk', 'blur']  # import order; dup has the same bytes as m2


def item(label, judgment, answer='35', uncertainty='', kind='objective'):
    return dict(label=label, question='虚构题面' + label, student_answer=answer, answer='25', judgment=judgment,
                error_reason='与参考答案不同' if judgment == 'incorrect' else '', possible_cause='',
                steps='按参考重算' if judgment == 'incorrect' else '', uncertainty=uncertainty, question_kind=kind)


def original_review(items):
    raw = dict(items=items, coverage='虚构', question_labels=[i['label'] for i in items])
    with patch.object(family_llm, '_chat_json', return_value=raw):
        out = family_llm.homework_reference_draft([dict(mime='image/png', data=PNG)], review=True)
    return [q['judgment'] for q in out['questions']]


class Model:
    """Fixed raw replies by task name; counts calls so tests prove no hidden retries."""

    def __init__(self, ids):
        self.ids = ids
        self.calls = []
        self.fail = set()
        self.group = None
        self.review = None
        self.fail_review_once = set()

    def images(self, messages):
        found = []
        for message in messages:
            if isinstance(message['content'], list):
                for part in message['content']:
                    if part.get('type') == 'image_url':
                        data = base64.b64decode(part['image_url']['url'].split(',', 1)[1])
                        found.append(self.ids[data])
        return found

    def __call__(self, messages, schema, name, timeout=60, *, data_path=None):
        self.calls.append(name)
        self.last_messages = [m['content'] if isinstance(m['content'], str) else [p.get('text', '') for p in m['content']] for m in messages]
        if name in self.fail:
            raise family_llm.LLMDraftError('模型暂时不可用（虚构）')
        tags = self.images(messages)
        if name == fwq.TASK_NAME:
            assert schema is fwq.EVIDENCE_SCHEMA
            return dict(pages=[dict(page=i, regions=PAGES[t]['regions'], evidence=PAGES[t]['evidence'])
                               for i, t in enumerate(tags, 1)], uncertainties=[])
        if name == fpb.GROUP_TASK:
            assert not tags, 'grouping is a text-only call'
            payload = json.loads(messages[1]['content'].split('：', 1)[1])
            self.seen_group = [p['page_id'] for p in payload['pages']]
            return self.group or dict(
                papers=[dict(subject='数学', title='虚构数学单元练习', basis='同标题、印刷页码1–2与参考答案',
                             pages=[dict(page_id='p03', order=1, role='answered'), dict(page_id='p01', order=2, role='answered'),
                                    dict(page_id='p05', order=3, role='answer_key')]),
                        dict(subject='语文', title='虚构语文小测', basis='语文题面', pages=[dict(page_id='p02', order=1, role='answered')])],
                pending=[dict(page_id='p06', reason='看不清')], same_pages=[])
        assert name == 'family_homework_reference', name
        if tags[0] in self.fail_review_once:
            self.fail_review_once.discard(tags[0])
            raise family_llm.LLMDraftError('模型暂时不可用（虚构）')
        if self.review:
            items = self.review(tags)
            return dict(items=items, coverage='虚构覆盖说明', question_labels=[i['label'] for i in items])
        if 'c1' in tags:
            items = [item('第2题', 'incorrect'), item('第3题', 'correct')]
        else:
            items = [item('第1题', 'correct'), item('第2题', 'incorrect'), item('第5题', 'incorrect', uncertainty='字迹不清'),
                     item('第6题', 'incorrect', answer='')]
        return dict(items=items, coverage='虚构覆盖说明', question_labels=[i['label'] for i in items])


class PhotoBatchTest(unittest.TestCase):
    def setUp(self):
        self.ctx = tempfile.TemporaryDirectory(prefix='synthetic-photo-batch-')
        root = pathlib.Path(self.ctx.name)
        private = root / 'private'
        private.mkdir()
        (root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.patches = [patch.multiple(app, ROOT=root, DATA=private, DB=private / 'family.sqlite3'),
                        patch.object(family_llm, 'configuration', return_value=('https://example.invalid', 'synthetic')),
                        patch.dict(app.os.environ, {'FAMILY_HOST': 'family.example.invalid', 'FAMILY_USER': 'parent@example.invalid'})]
        for p in self.patches:
            p.start()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.headers = {'X-Family-Token': app.TOKEN, 'Content-Type': 'application/json'}
        self.ids = {}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for p in self.patches:
            p.stop()
        self.ctx.cleanup()

    def request(self, path, obj=None, headers=None, body=None):
        c = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            c.request('GET' if obj is None and body is None else 'POST', path,
                      body if body is not None else None if obj is None else json.dumps(obj), headers or self.headers)
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            c.close()

    def upload(self, tag, key):
        data = page_bytes('m2' if tag == 'dup' else tag)
        code, out = self.request('/api/upload', body=data, headers={'X-Family-Token': app.TOKEN, 'X-File-Name': quote(tag + '.png'),
                                                                    'X-Request-Key': key, 'Content-Type': 'application/octet-stream'})
        self.assertEqual(code, 200, out)
        self.ids.setdefault(data, tag)  # an exact duplicate is the same original bytes
        return out['attachment']['id']

    def batch(self, key='batch-key-0000000001', tags=ORDER):
        uploads = [self.upload(t, '%s-%02d' % (key, i)) for i, t in enumerate(tags, 1)]
        return uploads, self.request('/api/photo-batch/create', dict(child_id='child-1', request_key=key, uploads=uploads))

    def rounds(self, model, n=12):
        with patch.object(family_llm, '_chat_json', side_effect=model):
            for _ in range(n):
                result = family_agent.run_once(app)  # the product backend round; school Agent is off here
                self.assertEqual(result['state'], 'disabled')

    def test_mixed_batch_groups_checks_frames_and_records_ai_wrongs_once(self):
        uploads, (code, created) = self.batch()
        self.assertEqual(code, 200, created)
        self.assertEqual([p['status'] for p in created['pages']], ['pending'] * 3 + ['duplicate', 'pending', 'pending'])
        self.assertEqual(created['pages'][3]['duplicate_of'], 'p01')
        model = Model(self.ids)
        with patch.object(family_llm, '_chat_json', side_effect=model):
            code, opened = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual((code, model.calls), (200, []), 'opening a batch is read only')
        self.rounds(model)
        self.assertEqual(model.calls, [fwq.TASK_NAME, fwq.TASK_NAME, fpb.GROUP_TASK, 'family_homework_reference', 'family_homework_reference'])
        self.assertNotIn('p04', model.seen_group, 'an exact duplicate is read once')
        code, done = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual(done['state'], 'done', done['progress'])
        math, chinese = done['papers']
        self.assertEqual((math['subject'], [p['page_id'] for p in math['pages']]), ('数学', ['p03', 'p01', 'p05']))
        self.assertEqual(chinese['subject'], '语文')
        # the unreadable page is marked by its own read and kept out of grouping; only that page waits
        self.assertEqual((done['pages'][5]['status'], done['pending']), ('unreadable', []))
        states = {q['label']: q['state'] for q in math['questions']}
        # 第5题 arrives as 'incorrect' with an uncertainty note. The original review contract — the same
        # homework_reference_draft(review=True) the homework feedback check uses, probed here independently of the batch
        # code — itself returns it as unknown. The batch keeps that unknown: no AI wrong, no suspected, no record.
        self.assertEqual(original_review([item('第5题', 'incorrect', uncertainty='字迹不清')]), ['unknown'])
        self.assertEqual(states, {'第1题': 'correct', '第2题': 'wrong', '第5题': 'unknown', '第6题': 'unknown'})
        self.assertTrue(all(q['record_id'] is None for q in math['questions'] if q['state'] != 'wrong'))
        wrong = next(q for q in math['questions'] if q['label'] == '第2题')
        self.assertEqual((wrong['page_id'], wrong['upload_id'], wrong['located']), ('p03', uploads[2], True))
        same_label = next(q for q in chinese['questions'] if q['label'] == '第2题')
        self.assertNotEqual(same_label['key'], wrong['key'], 'same question number in another paper is another question')
        self.assertEqual(same_label['page_id'], 'p02')
        self.assertIn('没有错题不代表全卷正确', math['coverage'])
        code, state = self.request('/api/state')
        records = [r for r in state['records'] if r['source'] == '错题照片核对']
        self.assertEqual(len(records), 2, [r['title'] for r in records])
        for r in records:
            self.assertIn('AI判断', r['note'])
            self.assertNotIn('家长已核对', r['note'])
            self.assertEqual(r['wrong_region']['context'], 'photo_batch')
            self.assertTrue(r['wrong_region']['current'])
        math_record = next(r for r in records if r['subject'] == '数学')
        self.assertEqual(math_record['attachments'], [uploads[2]])
        self.assertAlmostEqual(math_record['wrong_region']['y'], 0.24)
        # an unknown / blank answer is never a wrong record; reruns make no calls and no duplicates
        calls = len(model.calls)
        self.rounds(model, 2)
        self.assertEqual(len(model.calls), calls)
        # a lost create receipt replays the same batch; the same key for other photos is refused
        code, replay = self.request('/api/photo-batch/create', dict(child_id='child-1', request_key='batch-key-0000000001', uploads=uploads))
        self.assertEqual((code, replay['id'], replay['replayed']), (200, done['id'], True))
        code, conflict = self.request('/api/photo-batch/create', dict(child_id='child-1', request_key='batch-key-0000000001', uploads=uploads[:2]))
        self.assertEqual((code, conflict['code']), (409, 'request_conflict'))
        # child isolation
        code, other = self.request('/api/photo-batches?child_id=child-2')
        self.assertEqual((code, other['batches']), (200, []))
        code, mine = self.request('/api/photo-batches?child_id=child-1')
        self.assertEqual([b['id'] for b in mine['batches']], [done['id']])

    def paper_of(self, tags, title, kinds=None):
        for i, tag in enumerate(tags, 1):
            kind = (kinds or {}).get(tag, 'answered')
            PAGES.setdefault(tag, dict(evidence=evidence('数学', title, str(i), kind=kind),
                                       regions=[region('第3题', 300)] if i == 1 and kind == 'answered' else []))
        return dict(papers=[dict(subject='数学', title=title, basis='同标题与连续页码',
                                 pages=[dict(page_id='p%02d' % i, order=i, role=(kinds or {}).get(t, 'answered'))
                                        for i, t in enumerate(tags, 1)])], pending=[], same_pages=[])

    def test_long_paper_over_eight_pages_stays_one_paper_and_only_a_cross_segment_conflict_is_suspected(self):
        tags = ['L%02d' % i for i in range(1, 11)]
        model = Model(self.ids)
        model.group = self.paper_of(tags, '虚构长卷')
        model.review = lambda seen: ([item('第3题', 'incorrect'), item('第4题', 'correct')] if seen[0] == 'L01'
                                     else [item('第3题', 'correct'), item('第9题', 'correct')])
        model.fail_review_once = {'L09'}
        _, (code, created) = self.batch('batch-key-0000000008', tags)
        self.rounds(model, 10)
        self.assertEqual(model.calls, [fwq.TASK_NAME] * 4 + [fpb.GROUP_TASK] + ['family_homework_reference'] * 2)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual((view['state'], [f['kind'] for f in view['progress']['failed']]), ('needs_attention', ['check']))
        self.assertEqual(view['papers'][0]['unchecked_pages'], ['p09', 'p10'], 'the failed segment is not reported as checked')
        code, _ = self.request('/api/photo-batch/continue', dict(batch_id=created['id'], version=1))
        self.rounds(model, 3)
        self.assertEqual(model.calls[7:], ['family_homework_reference'], 'only the failed segment is redone')
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        (paper,) = view['papers']
        self.assertEqual((view['state'], paper['paper_id'], len(paper['pages']), paper['unchecked_pages']), ('done', 'paper-p01', 10, []))
        self.assertIn('已检查10页', paper['coverage'])
        # 第3题 on page 1 (segment 1) and 第3题 on page 9/10 (segment 2) are on different originals: no evidence they are
        # one question, so both stay, each with its own owner; no suspected is made up from the label alone.
        thirds = [q for q in paper['questions'] if q['label'] == '第3题']
        self.assertEqual(sorted(q['state'] for q in thirds), ['correct', 'wrong'])
        self.assertEqual(len({q['key'] for q in thirds}), 2)
        self.assertFalse([q for q in paper['questions'] if q['state'] == 'suspected'])
        wrong = next(q for q in thirds if q['state'] == 'wrong')
        self.assertEqual((wrong['page_id'], bool(wrong['record_id'])), ('p01', True))
        correct = next(q for q in thirds if q['state'] == 'correct')
        code, refused = self.request('/api/photo-batch/include', dict(batch_id=view['id'], version=view['version'], question_key=correct['key']))
        self.assertEqual((code, refused['code']), (409, 'photo_question_changed'))
        code, state = self.request('/api/state')
        saved = [r for r in state['records'] if r['source'] == '错题照片核对']
        self.assertEqual(len(saved), 1)
        self.assertIn('AI判断', saved[0]['note'])

    def test_hierarchical_labels_keep_their_boundaries(self):
        self.assertNotEqual(fpb._norm_label('第1题(1)'), fpb._norm_label('第11题'))
        self.assertEqual(fpb._norm_label('第1题（1）'), fpb._norm_label('1(1)'))
        self.assertEqual(fpb._norm_label(' 第 3 题 '), fpb._norm_label('3.'))
        self.assertNotEqual(fpb._norm_label('一、3'), fpb._norm_label('13'))

    def dense(self, key, followup):
        tags = ['D01']
        PAGES['D01'] = dict(evidence=evidence('数学', '虚构密集页', '1', first='第1题', last='第31题'), regions=[region('第1题', 100)])
        model = Model(self.ids)
        model.group = self.paper_of(tags, '虚构密集页')
        def review(seen):
            asked = '第26题' in json.dumps(model.last_messages, ensure_ascii=False)
            return [item('第%d题' % n, 'incorrect') for n in (range(26, 32) if asked and followup else range(1, 26))]
        model.review = review
        _, (code, created) = self.batch(key, tags)
        self.rounds(model, 6)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        return model, created, view

    def test_dense_page_known_gap_is_kept_and_a_bounded_follow_up_checks_only_it(self):
        model, created, view = self.dense('batch-key-0000000012', True)
        self.assertEqual(model.calls, [fwq.TASK_NAME, fpb.GROUP_TASK, 'family_homework_reference', 'family_homework_reference'])
        (paper,) = view['papers']
        self.assertEqual((view['state'], paper['unchecked_questions']), ('done', []), view['progress'])
        self.assertEqual(sorted(int(fpb._norm_label(q['label'])) for q in paper['questions']), list(range(1, 32)), 'no duplicate, no gap')
        code, state = self.request('/api/state')
        self.assertEqual(sum(r['source'] == '错题照片核对' for r in state['records']), 31)
        calls = len(model.calls)
        self.rounds(model, 2)
        self.assertEqual(len(model.calls), calls)

    def test_dense_page_follow_up_without_the_asked_range_stops_unknown_without_blind_retry(self):
        model, created, view = self.dense('batch-key-0000000013', False)
        (paper,) = view['papers']
        self.assertEqual(paper['unchecked_questions'], ['第%d题' % n for n in range(26, 32)])
        self.assertEqual((view['state'], view['can_continue']), ('needs_attention', True))
        self.assertEqual(len(paper['questions']), 25, 'the repeated 1–25 reply adds nothing')
        self.assertIn('第26题', json.dumps(view, ensure_ascii=False))
        calls = len(model.calls)
        self.rounds(model, 3)
        self.assertEqual(len(model.calls), calls, 'no automatic retry')

    def dense_with(self, key, review):
        PAGES['D01'] = dict(evidence=evidence('数学', '虚构密集页', '1', first='第1题', last='第31题'), regions=[region('第1题', 100)])
        model = Model(self.ids)
        model.group = self.paper_of(['D01'], '虚构密集页')
        model.review = lambda seen: review(model, '第26题' in json.dumps(model.last_messages, ensure_ascii=False))
        _, (code, created) = self.batch(key, ['D01'])
        return model, created

    def test_partial_follow_up_then_explicit_continue_accumulates_to_done_without_duplicates(self):
        asked = []
        def review(model, followup):
            if not followup:
                return [item('第%d题' % n, 'incorrect') for n in range(1, 26)]
            asked.append(1)
            return [item('第%d题' % n, 'incorrect') for n in (range(26, 31) if len(asked) == 1 else range(26, 32))]
        model, created = self.dense_with('batch-key-0000000014', review)
        self.rounds(model, 6)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual((view['state'], view['can_continue'], view['papers'][0]['unchecked_questions']), ('needs_attention', True, ['第31题']))
        self.request('/api/photo-batch/continue', dict(batch_id=created['id'], version=1))
        self.rounds(model, 4)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        (paper,) = view['papers']
        self.assertEqual((view['state'], view['can_continue'], paper['unchecked_questions']), ('done', False, []), view['progress'])
        self.assertEqual(sorted(int(fpb._norm_label(q['label'])) for q in paper['questions']), list(range(1, 32)))
        calls = len(model.calls)
        self.rounds(model, 2)
        code, state = self.request('/api/state')
        self.assertEqual((len(model.calls), sum(r['source'] == '错题照片核对' for r in state['records'])), (calls, 31))

    def test_follow_up_budget_counts_actual_attempts_including_explicit_continue(self):
        def review(model, followup):
            if followup:
                raise family_llm.LLMDraftError('模型暂时不可用（虚构）')
            return [item('第%d题' % n, 'incorrect') for n in range(1, 26)]
        model, created = self.dense_with('batch-key-0000000015', review)
        with patch.object(fpb, 'FOLLOWUP_LIMIT', 2):
            self.rounds(model, 4)
            for _ in range(3):
                self.request('/api/photo-batch/continue', dict(batch_id=created['id'], version=1))
                self.rounds(model, 3)
            code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual(model.calls.count('family_homework_reference'), 1 + 2, 'two actual follow-up attempts, retries included')
        self.assertEqual((view['state'], view['can_continue'], view['progress']['attempts']['followup']), ('needs_attention', False, 2))
        self.assertEqual(view['papers'][0]['unchecked_questions'], ['第%d题' % n for n in range(26, 32)])
        self.assertTrue(any('上限' in f['error'] for f in view['progress']['failed']))

    def test_total_attempt_hard_cap_blocks_without_a_continue_entry(self):
        _, (code, created) = self.batch('batch-key-0000000016', ['m1', 'c1'])
        model = Model(self.ids)
        with patch.object(fpb, 'TOTAL_LIMIT', 1):
            self.rounds(model, 4)
            code, view = self.request('/api/photo-batch?id=' + created['id'])
            self.request('/api/photo-batch/continue', dict(batch_id=created['id'], version=1))
            self.rounds(model, 2)
        self.assertEqual(model.calls, [fwq.TASK_NAME], 'the hard cap stops further calls')
        self.assertEqual((view['state'], view['can_continue']), ('needs_attention', False))

    def test_subjective_or_missing_kind_is_never_an_ai_wrong(self):
        raw = dict(items=[dict(item('第1题', 'incorrect'), question_kind='subjective')], coverage='虚构', question_labels=['第1题'])
        with patch.object(family_llm, '_chat_json', return_value=raw):
            plain = family_llm.homework_reference_draft([dict(mime='image/png', data=PNG)], review=True)
        with patch.object(family_llm, '_chat_json', return_value=json.loads(json.dumps(raw))):
            kept = family_llm.homework_reference_draft([dict(mime='image/png', data=PNG)], review=True, keep_question_kind=True)
        self.assertNotIn('question_kind', plain['questions'][0], 'other callers see the unchanged fields')
        self.assertEqual((fpb._classify(plain['questions'][0]), kept['questions'][0]['question_kind'], fpb._classify(kept['questions'][0])),
                         ('unknown', 'subjective', 'unknown'))
        _, (code, created) = self.batch('batch-key-0000000017', ['m1'])
        model = Model(self.ids)
        model.group = dict(papers=[dict(subject='数学', title='虚构', basis='', pages=[dict(page_id='p01', order=1, role='answered')])], pending=[], same_pages=[])
        model.review = lambda seen: [dict(item('第1题', 'incorrect'), question_kind='subjective'), item('第2题', 'incorrect')]
        self.rounds(model, 5)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        states = {q['label']: q['state'] for q in view['papers'][0]['questions']}
        self.assertEqual(states, {'第1题': 'unknown', '第2题': 'wrong'})
        code, state = self.request('/api/state')
        self.assertEqual([r['title'] for r in state['records'] if r['source'] == '错题照片核对'], ['数学错题：第2题'])

    def test_reading_text_keeps_ordinary_line_breaks_and_still_refuses_other_controls(self):
        page = dict(page=1, regions=[dict(region('卷头'), kind='layout', text='虚构卷头第一行\r\n第二行\t附注', answer='', correction='')],
                    evidence=PAGES['m1']['evidence'])
        out = fwq._validated(dict(pages=[page], uncertainties=['第一行\n第二行']), 1, evidence=True)
        self.assertEqual((out['pages'][0]['regions'][0]['text'], out['uncertainties']), ('虚构卷头第一行\n第二行 附注', ['第一行\n第二行']))
        bad = lambda **change: dict(pages=[dict(page, **change)], uncertainties=[])
        for control in ('\x00', '\x1b', '\x7f'):
            with self.assertRaises(family_llm.LLMDraftError):
                fwq._validated(bad(regions=[dict(page['regions'][0], text='甲' + control + '乙')]), 1, evidence=True)
        with self.assertRaises(family_llm.LLMDraftError):  # a question label is never merged across a line break
            fwq._validated(bad(regions=[dict(page['regions'][0], label='第1题\n第2题')]), 1, evidence=True)
        with self.assertRaises(family_llm.LLMDraftError):
            fwq._validated(bad(evidence=dict(page['evidence'], first_label='第1题\n第2题')), 1, evidence=True)
        import family_wrong_review as fwr
        self.assertEqual(fwr._text(dict(text='甲\r\n乙\t丙'), 'text', 100, multiline=True), '甲\n乙 丙')
        for value, multiline in (('甲\n乙', False), ('甲\x00乙', True)):
            with self.assertRaises(fwr.WrongReviewError):
                fwr._text(dict(text=value), 'text', 100, multiline=multiline)
        upload = self.upload('m1', 'manual-save-key-000001')
        code, out = self.request('/api/wrong/save', dict(child='示例甲', day='2026-11-03', subject='数学', request_key='manual-save-key-0000002',
                                                         items=[dict(attachment=upload, label='第1题', text='虚构题面第一行\r\n第二行', answer='35', correction='')]))
        self.assertEqual(code, 200, out)
        code, state = self.request('/api/state')
        self.assertIn('题面：虚构题面第一行\n第二行', next(r['note'] for r in state['records'] if r['id'] == out['saved'][0]['id']))

    def test_a_saves_only_round_never_claims_or_counts_an_unsent_model_step(self):
        # Root's counterexample through ordinary HTTP batches: an earlier batch waits on a model step, a later one on a save.
        model = Model(self.ids)
        _, (code, a) = self.batch('cross-batch-old-model-000001', ['m1'])
        model.fail = {fwq.TASK_NAME}
        with patch.object(family_llm, '_chat_json', side_effect=model):
            self.assertEqual(fpb.advance(app, budget=1)['failed'], 1)
        model.fail = set()
        _, (code, b) = self.batch('cross-batch-new-save-000001', ['m1'])
        model.group = dict(papers=[dict(subject='数学', title='虚构', basis='', pages=[dict(page_id='p01', order=1, role='answered')])],
                           pending=[], same_pages=[])
        model.review = lambda seen: [item('第2题', 'incorrect')]
        with patch.object(family_llm, '_chat_json', side_effect=model):
            for _ in range(2):
                fpb.advance(app, budget=1)
            with patch.object(fpb, '_save_questions', side_effect=OSError('虚构一次存储失败')):
                fpb.advance(app, budget=1)
        for batch in (b, a):
            self.assertEqual(self.request('/api/photo-batch/continue', dict(batch_id=batch['id'], version=1))[0], 200)
        def rows():
            with app.connect() as c:
                return {r[0]: json.loads(r[1]) for r in c.execute('SELECT id,understanding FROM photo_batches')}
        before, calls = rows(), list(model.calls)
        self.assertTrue(any(s['kind'] == 'read' and s['state'] == 'todo' for s in before[a['id']]['steps']))
        self.assertTrue(any(s['kind'] == 'save' and s['state'] == 'todo' for s in before[b['id']]['steps']))
        with patch.object(family_llm, '_chat_json', side_effect=model):
            out = fpb.advance(app, budget=0)  # the round's model budget is spent: only record writes may run
        after = rows()
        self.assertEqual((out['used'], model.calls), (0, calls), 'no model step dispatched')
        old, new = before[a['id']], after[a['id']]
        self.assertEqual((new['attempts'], new['calls'], new['steps']), (old['attempts'], old['calls'], old['steps']),
                         'the unsent model step is neither claimed nor counted as an actual attempt')
        self.assertEqual(new['attempts']['1'], dict(all=1, followup=0), 'the real failed read still counts')
        self.assertTrue(all(s['state'] == 'done' for s in after[b['id']]['steps'] if s['kind'] == 'save'))
        code, state = self.request('/api/state')
        self.assertEqual(sum(r['source'] == '错题照片核对' for r in state['records']), 1)

    def test_grouping_cannot_turn_a_questions_only_page_into_an_answered_page(self):
        info = {'p01': dict(evidence=dict(page_kind='questions_only')), 'p02': dict(evidence=dict(page_kind='answered'))}
        raw = dict(papers=[dict(subject='数学', title='甲', basis='', pages=[dict(page_id='p01', order=1, role='answered'),
                                                                       dict(page_id='p02', order=2, role='answered')])],
                   pending=[], same_pages=[])
        papers, pending, _ = fpb.validate_grouping(raw, ['p01', 'p02'], info)
        self.assertEqual([p['page_id'] for p in pending], ['p01'])
        self.assertIn('只有题面', pending[0]['reason'])
        self.assertEqual([p['page_id'] for p in papers[0]['pages']], ['p02'], 'the other page of the paper continues')

    def test_more_than_thirty_wrongs_save_in_stable_chunks_and_a_failed_chunk_resumes_without_duplicates(self):
        tags = ['W%02d' % i for i in range(1, 10)]
        model = Model(self.ids)
        model.group = self.paper_of(tags, '虚构大卷')
        model.review = lambda seen: [item('第%d题' % n, 'incorrect') for n in (range(1, 21) if seen[0] == 'W01' else range(21, 41))]
        original, fired = app.save_record, []
        def flaky(record, **kw):
            if record['title'].endswith('第35题') and not fired:
                fired.append(1)
                raise app.RecordError('虚构写入失败')
            return original(record, **kw)
        _, (code, created) = self.batch('batch-key-0000000009', tags)
        with patch.object(app, 'save_record', side_effect=flaky):
            self.rounds(model, 8)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        code, state = self.request('/api/state')
        wrong = [r for r in state['records'] if r['source'] == '错题照片核对']
        self.assertEqual((view['state'], len(wrong)), ('needs_attention', 30), 'the failed chunk wrote nothing; the first chunk stays')
        self.assertEqual(view['progress']['failed'][0]['kind'], 'save')
        calls = len(model.calls)
        code, _ = self.request('/api/photo-batch/continue', dict(batch_id=created['id'], version=1))
        self.rounds(model, 3)
        self.assertEqual(len(model.calls), calls, 'record writes need no model call')
        code, state = self.request('/api/state')
        wrong = [r for r in state['records'] if r['source'] == '错题照片核对']
        self.assertEqual(len(wrong), 40)
        self.assertEqual(len({r['request_key'] for r in wrong}), 40)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual(view['papers'][0]['counts']['wrong'], 40)
        self.assertEqual(len({q['record_id'] for q in view['papers'][0]['questions']}), 40)

    def test_questions_only_and_answer_key_pages_never_judge_the_child(self):
        tags = ['Q01', 'K01']
        model = Model(self.ids)
        model.group = self.paper_of(tags, '虚构题面卷', {'Q01': 'questions_only', 'K01': 'answer_key'})
        _, (code, created) = self.batch('batch-key-0000000010', tags)
        self.rounds(model, 4)
        self.assertNotIn('family_homework_reference', model.calls)
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual(view['state'], 'done')
        self.assertIn('没有学生作答', view['papers'][0]['note'])
        code, state = self.request('/api/state')
        self.assertFalse([r for r in state['records'] if r['source'] == '错题照片核对'])

    def test_a_round_with_no_school_budget_left_makes_no_photo_call(self):
        _, (code, created) = self.batch('batch-key-0000000011', ['m1'])
        model = Model(self.ids)
        with patch.object(family_llm, '_chat_json', side_effect=model):
            out = family_agent._photo_batches(app, None, 0)
        self.assertEqual((out['used'], model.calls), (0, []))

    def test_failure_is_kept_not_retried_and_continue_redoes_only_the_failed_step(self):
        _, (code, created) = self.batch('batch-key-0000000002')
        model = Model(self.ids)
        model.fail = {fpb.GROUP_TASK}
        self.rounds(model, 6)
        self.assertEqual(model.calls, [fwq.TASK_NAME, fwq.TASK_NAME, fpb.GROUP_TASK], 'no automatic retry')
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual((view['state'], view['can_continue'], view['papers']), ('needs_attention', True, []))
        model.fail = set()
        code, resumed = self.request('/api/photo-batch/continue', dict(batch_id=created['id'], version=1))
        self.assertEqual((code, resumed['state']), (200, 'queued'))
        self.rounds(model, 6)
        self.assertEqual(model.calls[3:], [fpb.GROUP_TASK, 'family_homework_reference', 'family_homework_reference'],
                         'read steps already done are not repeated')
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual(view['state'], 'done')

    def test_interrupted_call_is_unknown_and_not_sent_again(self):
        _, (code, created) = self.batch('batch-key-0000000003', ['m1', 'm2'])
        claim = fpb._claim(app, fpb._now())  # a round died after claiming its read call
        self.assertEqual(claim['kind'], 'read')
        model = Model(self.ids)
        with patch.object(family_llm, '_chat_json', side_effect=model):
            fpb.advance(app, fpb._now() + fpb.STALE_RUNNING * 2, 1)
        self.assertEqual(model.calls, [])
        code, view = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual((view['state'], view['progress']['failed'][0]['kind']), ('needs_attention', 'read'))

    def test_grouping_validation_marks_bad_parts_pending_without_guessing(self):
        info = {p: dict(evidence=dict(page_kind='answer_key' if p == 'p04' else 'answered')) for p in ('p01', 'p02', 'p03', 'p04')}
        raw = dict(papers=[dict(subject='数学', title='甲', basis='', pages=[dict(page_id='p01', order=1, role='answered'),
                                                                       dict(page_id='p02', order=1, role='answered'),
                                                                       dict(page_id='p04', order=2, role='answered'),
                                                                       dict(page_id='p99', order=3, role='answered')]),
                           dict(subject='数学', title='乙', basis='', pages=[dict(page_id='p01', order=1, role='answered')])],
                   pending=[], same_pages=[])
        papers, pending, issues = fpb.validate_grouping(raw, ['p01', 'p02', 'p03', 'p04'], info)
        reasons = {p['page_id']: p['reason'] for p in pending}
        self.assertEqual(set(reasons), {'p01', 'p02', 'p03', 'p04'})
        self.assertIn('多个去向', reasons['p01'])
        self.assertIn('页序冲突', reasons['p02'])
        self.assertIn('没有说明', reasons['p03'])
        self.assertIn('参考答案页', reasons['p04'])
        self.assertEqual(papers, [])
        self.assertTrue(any('本批没有的页编号' in i for i in issues))
        with self.assertRaises(family_llm.LLMDraftError):
            fpb.validate_grouping(dict(papers=[]), ['p01'], info)

    def test_append_new_version_rechecks_only_affected_paper_and_keeps_old_records(self):
        uploads, (code, created) = self.batch('batch-key-0000000004', ['m1', 'c1'])
        model = Model(self.ids)
        model.group = dict(papers=[dict(subject='数学', title='虚构数学单元练习', basis='', pages=[dict(page_id='p01', order=1, role='answered')]),
                                   dict(subject='语文', title='虚构语文小测', basis='', pages=[dict(page_id='p02', order=1, role='answered')])],
                           pending=[], same_pages=[])
        self.rounds(model, 6)
        code, v1 = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual(v1['state'], 'done', v1['progress'])
        code, state = self.request('/api/state')
        before = {r['id'] for r in state['records'] if r['source'] == '错题照片核对'}
        extra = self.upload('m2', 'batch-key-0000000004-add-01')
        body = dict(batch_id=created['id'], version=1, request_key='batch-key-0000000004-add', uploads=[extra])
        code, v2 = self.request('/api/photo-batch/append', body)
        self.assertEqual((code, v2['version']), (200, 2), v2)
        code, replay = self.request('/api/photo-batch/append', body)
        self.assertEqual((code, replay['replayed'], replay['version']), (200, True, 2))
        model.group = dict(papers=[dict(subject='数学', title='虚构数学单元练习', basis='', pages=[dict(page_id='p01', order=1, role='answered'),
                                                                                             dict(page_id='p03', order=2, role='answered')]),
                                   dict(subject='语文', title='虚构语文小测', basis='', pages=[dict(page_id='p02', order=1, role='answered')])],
                           pending=[], same_pages=[])
        calls = len(model.calls)
        self.rounds(model, 6)
        self.assertEqual(model.calls[calls:], [fwq.TASK_NAME, fpb.GROUP_TASK, 'family_homework_reference'],
                         'only the new page is read and only the changed math paper is checked again')
        code, v2 = self.request('/api/photo-batch?id=' + created['id'])
        self.assertEqual([s['paper_id'] for s in v2['stale']], ['paper-p01'])
        chinese = next(p for p in v2['papers'] if p['subject'] == '语文')
        self.assertEqual(chinese['based_on_version'], 1)
        code, state = self.request('/api/state')
        after = {r['id'] for r in state['records'] if r['source'] == '错题照片核对'}
        self.assertTrue(before <= after, 'older records are kept')
        stale_ids = set(v2['stale'][0]['record_ids'])
        for r in state['records']:
            if r['id'] in stale_ids:
                self.assertFalse(r['wrong_region']['current'])

    def test_old_single_annotate_contract_is_unchanged(self):
        raw = dict(pages=[dict(page=1, regions=[region('第1题')], evidence=PAGES['m1']['evidence'])], uncertainties=[])
        with patch.object(family_llm, '_chat_json', return_value=raw) as model:
            with self.assertRaises(family_llm.LLMDraftError):
                fwq.annotate_pages([dict(mime='image/png', data=PNG)])
        self.assertIs(model.call_args.args[1], fwq.SCHEMA)
        with patch.object(family_llm, '_chat_json', return_value=raw):
            out = fwq.annotate_pages([dict(mime='image/png', data=PNG)], evidence=True)
        self.assertEqual(out['pages'][0]['evidence']['subject'], '数学')

    def test_unsupported_page_only_affects_itself_and_wrong_child_is_refused(self):
        code, out = self.request('/api/photo-batch/create', dict(child_id='child-9', request_key='batch-key-0000000005', uploads=[]))
        self.assertEqual(code, 400)
        uploads, (code, created) = self.batch('batch-key-0000000006', ['m1'])
        code, refused = self.request('/api/photo-batch/create', dict(child_id='child-9', request_key='batch-key-0000000007', uploads=uploads))
        self.assertEqual(code, 400, refused)


if __name__ == '__main__':
    unittest.main()
