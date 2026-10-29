"""原图框题（wrong-notebook image-crop.ts 范围）保存与读回；全虚构，无模型调用。"""
import hashlib
import struct
import unittest
import uuid
import zlib

import app
import test_wrong_review as base


def png(width, height):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    raw = b''.join(b'\x00' + b'\x80\x80\x80' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


class WrongRegionTest(unittest.TestCase):
    setUp = base.WrongReviewHTTPTest.setUp
    tearDown = base.WrongReviewHTTPTest.tearDown
    upload = base.WrongReviewHTTPTest.upload
    request = base.WrongReviewHTTPTest.request

    def table(self):
        with app.connect() as c:
            return c.execute("SELECT 1 FROM sqlite_master WHERE name='wrong_regions'").fetchone() is not None

    def records(self):
        return [r for r in self.request('/api/state')[1]['records'] if r['source'] == '错题照片核对']

    def test_framed_item_keeps_original_and_freezes_its_basis(self):
        image = png(200, 100)
        photo = self.upload('虚构作答.png', image)
        other = self.upload('另一孩照片.png', png(200, 100))
        app.save_record(dict(child='示例乙', day='2026-09-18', category='学习进展', title='虚构乙作答', attachments=[other]))
        task = app.new_task(dict(child='示例甲', title='虚构数学作业', category='homework'))
        feedback = app.save_task_feedback(dict(task_id=task['id'], child='示例甲', day='2026-09-18',
                                               request_key=uuid.uuid4().hex, attachments=[photo]))
        answer = next(r for r in self.request('/api/state')[1]['records'] if r['id'] == feedback['record_id'])
        region = dict(x=0.1, y=0.2, width=0.5, height=0.4, natural_width=200, natural_height=100)
        item = dict(attachment=photo, label='第2题', text='', answer='35', correction='25')
        plain = dict(child='示例甲', day='2026-09-18', subject=answer['subject'] or '', task_id=task['id'],
                     feedback_record_id=answer['id'], feedback_created=answer['created'])
        # 无框旧流程不建表；读路径也不建表。
        self.assertEqual(self.request('/api/wrong/save', plain | dict(request_key=uuid.uuid4().hex, items=[item]))[0], 200)
        self.assertFalse(self.table())
        with app.connect() as c:
            uploads_before = c.execute('SELECT count(*) FROM uploads').fetchone()[0]
        body = plain | dict(request_key=uuid.uuid4().hex, items=[item | dict(label='第3题', region=region)])
        status, saved = self.request('/api/wrong/save', body)
        self.assertEqual(status, 200, saved)
        self.assertTrue(self.table())
        framed = next(r for r in self.records() if '第3题' in r['title'])
        self.assertEqual(framed['attachments'], [photo])
        self.assertEqual(framed['source'], '错题照片核对')
        self.assertNotIn('0.1', framed['note'])
        self.assertEqual(framed['wrong_region'], dict(region, upload_id=photo, feedback_record_id=answer['id'],
                                                      task_id=task['id'], current=True))
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM uploads').fetchone()[0], uploads_before)
            row = c.execute('SELECT * FROM wrong_regions').fetchone()
        self.assertEqual(row['upload_sha256'], hashlib.sha256(image).hexdigest())
        self.assertEqual((app.DATA / 'uploads' / photo).read_bytes(), image)
        # 丢回执后同键重放只一条；同键改框 409 零写。
        status, replay = self.request('/api/wrong/save', body)
        self.assertEqual(status, 200, replay)
        self.assertTrue(replay['saved'][0]['existing'])
        moved = body | dict(items=[body['items'][0] | dict(region=region | dict(x=0.2))])
        status, out = self.request('/api/wrong/save', moved)
        self.assertEqual((status, out.get('code')), (409, 'request_conflict'), out)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(self.records()[0]['wrong_region']['x'] if 'wrong_region' in self.records()[0] else 0.1, 0.1)
        # 跨孩照片、尺寸不符、科目不符、bool/越界/过小、无事项路径一律不保存。
        for changed, code in (
                (dict(items=[body['items'][0] | dict(attachment=other)]), 409),
                (dict(items=[body['items'][0] | dict(region=region | dict(natural_width=300))]), 409),
                (dict(subject='虚构别科'), 409),
                (dict(items=[body['items'][0] | dict(region=region | dict(x=True))]), 400),
                (dict(items=[body['items'][0] | dict(region=region | dict(width=0.95))]), 400),
                (dict(items=[body['items'][0] | dict(region=region | dict(width=0.05))]), 400)):
            status, out = self.request('/api/wrong/save', body | changed | dict(request_key=uuid.uuid4().hex))
            self.assertEqual(status, code, (changed, out))
        status, out = self.request('/api/wrong/save', dict(child='示例甲', day='2026-09-18', subject='数学',
                                                           request_key=uuid.uuid4().hex, items=[item | dict(region=region)]))
        self.assertEqual(status, 400, out)
        self.assertEqual(len(self.records()), 2)
        # 原作答更正后：旧框只作旧依据，不移挂到新版本。
        app.save_task_feedback(dict(task_id=task['id'], child='示例甲', record_id=answer['id'],
                                    expected_created=answer['created'], day='2026-09-18',
                                    note='原作答后来更正', attachments=[photo]))
        framed = next(r for r in self.records() if '第3题' in r['title'])
        self.assertFalse(framed['wrong_region']['current'])


if __name__ == '__main__':
    unittest.main()
