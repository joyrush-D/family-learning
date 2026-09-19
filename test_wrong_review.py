"""Synthetic HTTP workflow for the wrong-question photo review (R14/R18).

Mocks the vision model; no real family data, uploads or external calls.
"""
from http.client import HTTPConnection
import json
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote
import uuid

import app
import family_wrong_questions as fwq

PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000d49444154789c6360000002000100ffff03000006000557bfab4400'
    '00000049454e44ae426082')
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 24


def draft(images, subject_hint='', timeout=90, *, data_path=None):
    return {'pages': [
        {'page': 1, 'regions': [
            {'kind': 'layout', 'box': {'x': 10, 'y': 5, 'w': 900, 'h': 70},
             'label': '卷头', 'text': '虚构数学小测', 'answer': '', 'correction': '', 'uncertain': False},
            {'kind': 'wrong_item', 'box': {'x': 30, 'y': 200, 'w': 700, 'h': 120},
             'label': '第2题', 'text': '42 - 17 =', 'answer': '35', 'correction': '25', 'uncertain': False},
        ]},
        {'page': 2, 'regions': [
            {'kind': 'wrong_item', 'box': {'x': 40, 'y': 500, 'w': 400, 'h': 150},
             'label': '第3题', 'text': 'chuāng wài', 'answer': '窗处', 'correction': '窗外', 'uncertain': True},
        ]},
    ], 'uncertainties': ['第2页光线偏暗，题面转写请对照原图']}


class WrongReviewHTTPTest(unittest.TestCase):
    def setUp(self):
        self.ctx = tempfile.TemporaryDirectory(prefix='synthetic-wrong-')
        root = pathlib.Path(self.ctx.name)
        private = root / 'private'
        private.mkdir()
        (root / '家庭运行规则.md').write_text(
            '| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n'
            '| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self._patches = [
            patch.multiple(app, ROOT=root, DATA=private, DB=private / 'family.sqlite3'),
            patch.object(fwq, 'annotate_pages', side_effect=draft),
            patch.dict(app.os.environ, {'FAMILY_HOST': 'family.example.invalid',
                                        'FAMILY_USER': 'parent@example.invalid'}),
        ]
        for p in self._patches:
            p.start()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.headers = {'X-Family-Token': app.TOKEN, 'Content-Type': 'application/json'}
        code, state = self.request('/api/state')
        assert code == 200 and {c['name'] for c in state['children']} == {'示例甲', '示例乙'}, state.get('children')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for p in self._patches:
            p.stop()
        self.ctx.cleanup()

    def request(self, path, obj=None, headers=None, raw=None):
        c = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            if raw is not None:
                c.request('POST', path, body=raw['body'], headers=raw['headers'])
            else:
                c.request('GET' if obj is None else 'POST', path,
                          None if obj is None else json.dumps(obj),
                          headers or self.headers)
            r = c.getresponse()
            body = r.read()
            return r.status, json.loads(body) if body else {}
        finally:
            c.close()

    def upload(self, name, data):
        headers = {'X-Family-Token': app.TOKEN, 'X-File-Name': quote(name),
                   'Content-Type': 'application/octet-stream'}
        status, out = self.request('/api/upload', raw={'body': data, 'headers': headers})
        self.assertEqual(status, 200, out)
        return out['attachment']['id']

    def test_full_review_flow(self):
        id1 = self.upload('虚构卷1.png', PNG)
        id2 = self.upload('虚构卷2.jpg', JPEG)

        # 标注：模型草稿挂上真实附件信息
        status, out = self.request('/api/wrong/annotate',
                                   dict(child='示例甲', subject_hint='数学', attachments=[id1, id2]))
        self.assertEqual(status, 200, out)
        self.assertEqual([p['attachment']['id'] for p in out['pages']], [id1, id2])
        self.assertEqual(out['pages'][0]['attachment']['url'], '/upload/' + id1)
        self.assertEqual(len(out['uncertainties']), 1)

        # 保存家长核对后的两处错题
        items = [
            dict(attachment=id1, label='第2题', text='42 - 17 =', answer='35', correction='25', note=''),
            dict(attachment=id2, label='第3题', text='chuāng wài', answer='窗处', correction='窗外',
                 note='形近字混淆'),
        ]
        batch = uuid.uuid4().hex
        status, saved = self.request('/api/wrong/save',
                                     dict(child='示例甲', day='2026-09-18', subject='数学',
                                          request_key=batch, items=items))
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved['count'], 2)

        status, state = self.request('/api/state')
        records = [r for r in state['records'] if r['source'] == '错题照片核对']
        self.assertEqual(len(records), 2)
        first = next(r for r in records if '第2题' in r['title'])
        self.assertEqual(first['category'], '学习进展')
        self.assertEqual(first['subject'], '数学')
        self.assertEqual(first['attachments'], [id1])
        self.assertIn('学生原答：35', first['note'])
        self.assertIn('可见订正/正确答案：25', first['note'])
        second = next(r for r in records if '第3题' in r['title'])
        self.assertIn('家长备注：形近字混淆', second['note'])
        self.assertEqual(second['attachments'], [id2])

        # 同批重放幂等，不新增记录
        replay_status, replay = self.request('/api/wrong/save',
                                             dict(child='示例甲', day='2026-09-18', subject='数学',
                                                  request_key=batch, items=items))
        self.assertEqual(replay_status, 200, replay)
        self.assertTrue(all(x['existing'] for x in replay['saved']))
        status, state = self.request('/api/state')
        self.assertEqual(len([r for r in state['records'] if r['source'] == '错题照片核对']), 2)

    def test_confirmed_candidate_tags_saved_as_reviewed_lines(self):
        img = self.upload('虚构标签卷.png', PNG)
        items = [
            dict(attachment=img, label='第1题', text='28 + 14 =', answer='32', correction='42',
                 note='', topic_hint='两位数进位加法', error_hint='进位漏加'),
            dict(attachment=img, label='第2题', text='1+1=', answer='3', correction='2',
                 note='', topic_hint='  ', error_hint=''),
        ]
        status, saved = self.request('/api/wrong/save',
                                     dict(child='示例甲', day='2026-09-18', subject='数学',
                                          request_key=uuid.uuid4().hex, items=items))
        self.assertEqual(status, 200, saved)
        status, state = self.request('/api/state')
        records = [r for r in state['records'] if r['source'] == '错题照片核对']
        first = next(r for r in records if '第1题' in r['title'])
        self.assertIn('知识点（家长核对）：两位数进位加法', first['note'])
        self.assertIn('错误类型（家长核对）：进位漏加', first['note'])
        self.assertIn('题面：28 + 14 =', first['note'])  # 原题面前缀不变
        self.assertIn('可见订正/正确答案：42', first['note'])
        second = next(r for r in records if '第2题' in r['title'])
        self.assertNotIn('知识点（家长核对）', second['note'])  # 清空不写行
        self.assertNotIn('错误类型（家长核对）', second['note'])

        over_topic = [dict(attachment=img, label='第3题', text='x', answer='', correction='',
                           topic_hint='知' * 61, error_hint='')]
        status, out = self.request('/api/wrong/save',
                                   dict(child='示例甲', day='2026-09-18', subject='数学',
                                        request_key=uuid.uuid4().hex, items=over_topic))
        self.assertEqual(status, 400, out)
        over_error = [dict(attachment=img, label='第3题', text='x', answer='', correction='',
                           topic_hint='', error_hint='错' * 41)]
        status, out = self.request('/api/wrong/save',
                                   dict(child='示例甲', day='2026-09-18', subject='数学',
                                        request_key=uuid.uuid4().hex, items=over_error))
        self.assertEqual(status, 400, out)

    def test_overlong_second_item_rejects_whole_batch_and_can_retry(self):
        img = self.upload('synthetic-long.png', PNG)
        first = dict(attachment=img, label='第1题', text='28+14=', answer='32', correction='42',
                     topic_hint='进位加法', error_hint='进位漏加')
        second = dict(attachment=img, label='第2题', text='Q' * 2000, answer='A' * 1000,
                      correction='C' * 1000, topic_hint='候选', error_hint='待核对')
        payload = dict(child='示例甲', day='2026-09-18', subject='数学',
                       request_key=uuid.uuid4().hex, items=[first, second])
        status, out = self.request('/api/wrong/save', payload)
        self.assertEqual(status, 400, out)
        self.assertIn('第2条错题总内容超过4000字', out['error'])
        self.assertEqual(self.request('/api/state')[1]['records'], [])
        second.update(text='3×4=', answer='7', correction='12')
        status, out = self.request('/api/wrong/save', payload)
        self.assertEqual(status, 200, out)
        records = self.request('/api/state')[1]['records']
        self.assertEqual(len(records), 2)
        self.assertTrue(any('错误类型（家长核对）：进位漏加' in r['note'] for r in records))
        self.assertTrue(any('可见订正/正确答案：12' in r['note'] for r in records))

    def test_rejections(self):
        img = self.upload('a.png', PNG)
        doc = self.upload('note.txt', b'not an image')
        cases = [
            ('/api/wrong/annotate', dict(child='示例甲', attachments=[]), 400),
            ('/api/wrong/annotate', dict(child='示例甲', attachments=[img] * 4), 400),
            ('/api/wrong/annotate', dict(child='示例甲', attachments=[img, img]), 400),
            ('/api/wrong/annotate', dict(child='示例甲', attachments=[doc]), 400),
            ('/api/wrong/annotate', dict(child='不存在的孩子', attachments=[img]), 400),
            ('/api/wrong/annotate', dict(child='示例甲', attachments=['x' * 32]), 400),
            ('/api/wrong/save', dict(child='示例甲', day='2026-09-18', request_key=uuid.uuid4().hex,
                                     items=[dict(attachment=img, label='', text='', answer='', correction='')]), 400),
            ('/api/wrong/save', dict(child='示例甲', day='18-09-2026', request_key=uuid.uuid4().hex,
                                     items=[dict(attachment=img, label='第1题', text='x')]), 400),
            ('/api/wrong/save', dict(child='示例甲', day='2026-09-18', request_key='short',
                                     items=[dict(attachment=img, label='第1题', text='x')]), 400),
        ]
        for path, obj, expected in cases:
            status, out = self.request(path, obj)
            self.assertEqual(status, expected, (path, out))
            self.assertIn('error', out)

    def test_requires_parent_token(self):
        status, _ = self.request('/api/wrong/annotate',
                                 dict(child='示例甲', attachments=[]),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main()
