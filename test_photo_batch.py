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


def evidence(subject, title, printed, kind='answered', readability='clear', first='第1题', last='第3题'):
    return dict(subject=subject, subject_basis='题面内容', title=title, printed_page=printed, first_label=first,
                last_label=last, head='虚构题面开头', tail='虚构题面结尾', page_kind=kind, readability=readability)


def region(label, y=200, kind='wrong_item'):
    return dict(kind=kind, box=dict(x=40, y=y, w=600, h=120), label=label, text='虚构题面', answer='35' if kind == 'wrong_item' else '',
                correction='', uncertain=False)


# Fictional pages: two math pages imported out of order, a Chinese page, an exact byte duplicate, a math answer key,
# an unreadable page, and a Chinese-text math word problem page that must stay math.
PAGES = {
    'm2': dict(evidence=evidence('数学', '虚构数学单元练习', '2', first='第4题', last='第6题'), regions=[region('第5题', 300), region('第6题', 500)]),
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


class Model:
    """Fixed raw replies by task name; counts calls so tests prove no hidden retries."""

    def __init__(self, ids):
        self.ids = ids
        self.calls = []
        self.fail = set()
        self.group = None

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
        self.assertEqual(states, {'第1题': 'correct', '第2题': 'wrong', '第5题': 'suspected', '第6题': 'unknown'})
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
        # suspected stays in the report until the parent includes it; a repeated click reads back the same record
        suspected = next(q for q in math['questions'] if q['state'] == 'suspected')
        self.assertIsNone(suspected['record_id'])
        body = dict(batch_id=done['id'], version=done['version'], question_key=suspected['key'])
        code, first = self.request('/api/photo-batch/include', body)
        code2, again = self.request('/api/photo-batch/include', body)
        self.assertEqual((code, code2), (200, 200), first)
        ids = [q['record_id'] for p in (first, again) for q in p['papers'][0]['questions'] if q['key'] == suspected['key']]
        self.assertTrue(ids[0] and ids[0] == ids[1])
        code, state = self.request('/api/state')
        chosen = [r for r in state['records'] if r['id'] == ids[0]]
        self.assertIn('家长选择纳入练习', chosen[0]['note'])
        self.assertEqual(sum(r['source'] == '错题照片核对' for r in state['records']), 3)
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
