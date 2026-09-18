"""Run python3 test_wrong_questions.py. Mock model only; never sends material out."""
import base64
import importlib.util
import json
import os
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import family_llm
import family_wrong_questions as fwq

PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
JPEG_HEADER = b'\xff\xd8\xff\xe0' + b'\x00' * 20
WEBP_HEADER = b'RIFF' + b'\x00' * 4 + b'WEBP' + b'\x00' * 16


def region(kind='wrong_item', x=10, y=20, w=100, h=50, label='第1题', text='1+1=3',
           answer='3', correction='2', uncertain=False):
    return dict(kind=kind, box=dict(x=x, y=y, w=w, h=h), label=label, text=text,
                answer=answer, correction=correction, uncertain=uncertain)


def page(number, *regions):
    return dict(page=number, regions=list(regions))


class Capture:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, messages, schema, name, timeout=60, *, data_path=None):
        self.calls.append(dict(messages=messages, schema=schema, name=name,
                               timeout=timeout, data_path=data_path))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class AnnotateTests(unittest.TestCase):
    def setUp(self):
        self.image = dict(data=PNG_1X1, mime='image/png')

    def _call(self, result, images=None, **kwargs):
        capture = Capture(result)
        with patch.object(family_llm, 'configuration', return_value=('http://example.invalid/v1/chat/completions', 'synthetic')), \
                patch.object(family_llm, '_chat_json', capture):
            draft = fwq.annotate_pages(images or [self.image], data_path='/tmp/synthetic-data', **kwargs)
        return draft, capture

    def test_happy_path_sorted_deduped_and_payload(self):
        r1 = region('wrong_item', 10, 100, 100, 80, '第1题', '1+1=3', '3', '2', False)
        result = dict(pages=[
            page(2, region('layout', 5, 5, 200, 60, '卷头', '数学练习', '', '', False),
                 region('handwriting', 10, 900, 300, 80, '', '手写过程', '不应保留', '不应保留', False)),
            page(1, region('wrong_item', 10, 500, 100, 80, '第2题', '2+2=5', '5', '4', True),
                 r1, json.loads(json.dumps(r1))),
        ], uncertainties=[' 虚构模糊处待核对 '])
        draft, capture = self._call(result, images=[self.image, self.image], subject_hint='数学')
        self.assertEqual([p['page'] for p in draft['pages']], [1, 2])
        p1 = draft['pages'][0]['regions']
        self.assertEqual([r['label'] for r in p1], ['第1题', '第2题'])  # 阅读带排序
        self.assertEqual(len(p1), 2)  # 完全重复去重
        handwritten = draft['pages'][1]['regions'][1]
        self.assertEqual(handwritten['answer'], '')
        self.assertEqual(handwritten['correction'], '')  # 非错题不带作答判断
        self.assertEqual(draft['uncertainties'], ['虚构模糊处待核对'])
        call = capture.calls[0]
        self.assertEqual(call['name'], 'family_wrong_questions_annotate')
        self.assertEqual(call['timeout'], 90)
        self.assertEqual(call['data_path'], '/tmp/synthetic-data')
        system_text = call['messages'][0]['content']
        self.assertIn('wrong_item', system_text)
        self.assertIn('1000', system_text)
        user_parts = call['messages'][1]['content']
        self.assertTrue(any(part['type'] == 'text' and 'subject_hint' in part['text'] for part in user_parts))
        self.assertTrue(all(part['image_url']['url'].startswith('data:image/png;base64,')
                            for part in user_parts if part['type'] == 'image_url'))
        self.assertEqual(call['schema']['required'], ['pages', 'uncertainties'])

    def test_empty_regions_allowed(self):
        draft, _ = self._call(dict(pages=[page(1)], uncertainties=[]))
        self.assertEqual(draft['pages'][0]['regions'], [])

    def test_page_coverage_must_match_input(self):
        for bad in (dict(pages=[page(2)], uncertainties=[]),
                    dict(pages=[page(1), page(1)], uncertainties=[]),
                    dict(pages=[page(1)], uncertainties=[])):
            images = [self.image, self.image] if len(bad['pages']) != 1 or bad['pages'][0]['page'] == 2 else [self.image]
            if bad['pages'][0]['page'] == 1 and len(bad['pages']) == 1 and len(images) == 1:
                continue  # 唯一合法组合
            with self.assertRaises(family_llm.LLMDraftError):
                self._call(bad, images=images)

    def test_invalid_boxes_rejected(self):
        bad_boxes = [
            dict(x=-1, y=0, w=10, h=10), dict(x=0, y=0, w=0, h=10),
            dict(x=991, y=0, w=10, h=10), dict(x=0, y=0, w=10, h=10.5),
            dict(x=0, y=0, w=1001, h=10),
        ]
        for box in bad_boxes:
            raw = region()
            raw['box'] = box
            with self.assertRaises(family_llm.LLMDraftError, msg=box):
                self._call(dict(pages=[page(1, raw)], uncertainties=[]))

    def test_structure_guards(self):
        cases = [
            dict(pages=[], uncertainties=[]),
            dict(pages=[dict(page=1)], uncertainties=[]),
            dict(pages=[dict(page=1, regions=[dict(region(), extra=True)])], uncertainties=[]),
            dict(pages=[page(1, dict(region(), kind='other'))], uncertainties=[]),
            dict(pages=[page(1, dict(region(), uncertain='yes'))], uncertainties=[]),
            dict(pages=[page(1)], uncertainties=['x'] * 11),
            dict(pages='x', uncertainties=[]),
        ]
        for result in cases:
            with self.assertRaises(family_llm.LLMDraftError, msg=str(result)):
                self._call(result)

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            fwq.annotate_pages([])
        with self.assertRaises(ValueError):
            fwq.annotate_pages([self.image] * 4)
        with self.assertRaises(ValueError):
            fwq.annotate_pages([dict(data=b'', mime='image/png')])
        with self.assertRaises(ValueError):
            fwq.annotate_pages([dict(data=PNG_1X1, mime='image/gif')])
        with self.assertRaises(ValueError):
            fwq.annotate_pages([self.image], subject_hint='数' * 81)
        with self.assertRaises(ValueError):
            fwq.annotate_pages([self.image], timeout=0)

    def test_model_unavailable_propagates(self):
        with self.assertRaises(family_llm.LLMUnavailable):
            self._call(family_llm.LLMUnavailable('未配置模型'))


class OutputTokenWiringTests(unittest.TestCase):
    """错题标注与学校筛选同为6000输出token，其他任务仍为3000。"""

    def test_token_limit_by_task(self):
        state = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                state['max_tokens'] = body.get('max_tokens')
                result = {'choices': [{'finish_reason': 'stop', 'message': {
                    'content': json.dumps(dict(pages=[dict(page=1, regions=[])], uncertainties=[]))}}]}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        import threading
        threading.Thread(target=server.serve_forever, daemon=True).start()
        schema = fwq.SCHEMA
        env = dict(FAMILY_LLM_BASE_URL='http://127.0.0.1:%d/v1' % server.server_address[1],
                   FAMILY_LLM_MODEL='synthetic-model')
        try:
            with patch.dict(os.environ, env, clear=True):
                family_llm._chat_json([dict(role='user', content='synthetic')], schema,
                                      fwq.TASK_NAME)
                self.assertEqual(state['max_tokens'], 6000)
                family_llm._chat_json([dict(role='user', content='synthetic')], schema,
                                      'family_learning_draft')
                self.assertEqual(state['max_tokens'], 3000)
        finally:
            server.shutdown()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.photo = self.root / 'p1.png'
        self.photo.write_bytes(PNG_1X1)

    def test_cli_batch_output_and_fallback_without_preview(self):
        second = self.root / 'p2.jpg'
        second.write_bytes(JPEG_HEADER)
        out = self.root / 'out'

        def fake_annotate(images, subject_hint='', timeout=90, *, data_path=None):
            self.assertEqual(len(images), 2)
            self.assertEqual(images[1]['mime'], 'image/jpeg')
            self.assertEqual(subject_hint, '数学')
            return dict(pages=[page(1, region()), page(2)], uncertainties=['虚构待核对'])

        with patch.object(family_llm, 'configuration',
                          return_value=('http://example.invalid/v1/chat/completions', 'synthetic')), \
                patch.object(fwq, 'annotate_pages', fake_annotate), \
                patch.object(fwq, 'render_preview', side_effect=RuntimeError('no Pillow')):
            code = fwq.main([str(self.photo), str(second), '--subject', '数学', '--out', str(out)])
        self.assertEqual(code, 0)
        payloads = list(out.glob('wrong-questions-*.json'))
        self.assertEqual(len(payloads), 1)
        payload = json.loads(payloads[0].read_text())
        self.assertEqual(payload['sources'], ['p1.png', 'p2.jpg'])
        self.assertEqual([p['page'] for p in payload['pages']], [1, 2])
        self.assertEqual(payload['pages'][0]['source'], 'p1.png')
        self.assertTrue(any('画框预览' in item for item in payload['uncertainties']))

    def test_cli_rejects_unknown_format(self):
        bad = self.root / 'x.png'
        bad.write_bytes(b'not an image')
        code = fwq.main([str(bad), '--out', str(self.root / 'out')])
        self.assertEqual(code, 2)

    def test_cli_model_failure_exit_code(self):
        with patch.object(family_llm, 'configuration',
                          return_value=('http://example.invalid/v1/chat/completions', 'synthetic')), \
                patch.object(fwq, 'annotate_pages',
                             side_effect=family_llm.LLMUnavailable('模型未配置')):
            code = fwq.main([str(self.photo), '--out', str(self.root / 'out')])
        self.assertEqual(code, 2)

    def test_load_image_sniff(self):
        self.assertEqual(fwq.load_image(str(self.photo))['mime'], 'image/png')
        webp = self.root / 'p.webp'
        webp.write_bytes(WEBP_HEADER)
        self.assertEqual(fwq.load_image(str(webp))['mime'], 'image/webp')
        with self.assertRaises(ValueError):
            fwq.load_image(__file__)

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow 仅用于画框预览')
    def test_preview_renders_jpeg_when_pillow_available(self):
        from PIL import Image
        import io
        buffer = io.BytesIO()
        Image.new('RGB', (200, 120), 'white').save(buffer, format='jpeg')
        image = dict(data=buffer.getvalue(), mime='image/jpeg')
        out = self.root / 'preview.jpg'
        fwq.render_preview(image, [region(), region('layout', 50, 60, 100, 40, '卷头', '数学', uncertain=True)], str(out))
        rendered = Image.open(out)
        self.assertEqual(rendered.format, 'JPEG')
        self.assertEqual(rendered.size, (200, 120))


if __name__ == '__main__':
    unittest.main(verbosity=2)
