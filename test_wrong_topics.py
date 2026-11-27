"""Synthetic check for the topic roll-up of photographed wrong questions.

Only the roll-up is exercised: rows are written straight into the records table so the test
does not depend on the vision model, and no real family data, upload or network is used.
"""
from http.client import HTTPConnection
from urllib.parse import quote
import datetime
import json
import pathlib
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import app


def day(offset):
    return (datetime.date.today() - datetime.timedelta(days=offset)).isoformat()


class TopicRollupTest(unittest.TestCase):
    def setUp(self):
        self.ctx = tempfile.TemporaryDirectory(prefix='synthetic-topics-')
        root = pathlib.Path(self.ctx.name)
        private = root / 'private'
        private.mkdir()
        (root / '家庭运行规则.md').write_text(
            '| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        self._patches = [
            patch.multiple(app, ROOT=root, DATA=private, DB=private / 'family.sqlite3'),
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
        self.assertEqual(code, 200, state)
        self.child = state['children'][0]['name']
        self.db = private / 'family.sqlite3'
        self.ids = []

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for p in self._patches:
            p.stop()
        self.ctx.cleanup()

    def request(self, path, obj=None):
        c = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            c.request('GET' if obj is None else 'POST', path,
                      None if obj is None else json.dumps(obj), headers=self.headers)
            r = c.getresponse()
            body = r.read()
            return r.status, json.loads(body) if body else {}
        finally:
            c.close()

    def wrong(self, when, hint, subject='数学', label='第1题'):
        note = ['题面：3+5', '由照片标注生成，家长已核对；这不是掌握程度结论。']
        if hint:
            note.insert(2, '知识点（家长核对）：' + hint)
        with sqlite3.connect(self.db) as c:
            cur = c.execute(
                "INSERT INTO records(child,day,subject,title,note,source,created,followup_kind)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (self.child, when, subject, subject + '错题：' + label, '\n'.join(note),
                 '错题照片核对', when + 'T20:00:00', ''))
            self.ids.append(cur.lastrowid)
            return cur.lastrowid

    def correct(self, record_id, when):
        with sqlite3.connect(self.db) as c:
            c.execute(
                "INSERT INTO records(child,day,subject,title,note,source,created,"
                "related_record_id,followup_kind) VALUES(?,?,?,?,?,?,?,?,?)",
                (self.child, when, '数学', '订正：第1题', '已订正', '错题订正', when + 'T21:00:00',
                 record_id, '订正'))

    def test_the_rollup_reads_names_days_and_open_items(self):
        self.wrong(day(25), '10以内的加法', label='第3题')
        self.wrong(day(25), '10以内的加法', label='第7题')
        self.wrong(day(6), '10以内的加法', label='第2题')
        last = self.wrong(day(0), '10以内的加法', label='第4题')
        self.wrong(day(0), '20以内的退位减法', label='第5题')
        self.wrong(day(0), '', label='第6题')
        self.correct(last, day(0))
        code, out = self.request('/api/wrong/topics?days=30')
        self.assertEqual(code, 200, out)
        self.assertEqual(out['pending']['count'], 1, out)
        topics = {t['name']: t for t in out['topics']}
        self.assertEqual(set(topics), {'10以内的加法', '20以内的退位减法'}, topics)
        first = topics['10以内的加法']
        self.assertEqual((first['items'], first['days'], first['open']), (4, 3, 3), first)
        self.assertEqual(first['last_day'], day(0))
        self.assertEqual(first['score'], 2.3, first)
        self.assertTrue(first['weak'])
        self.assertEqual(first['tier'], '反复错')
        self.assertIn('错了 3 次（4 题）', first['reason'])
        self.assertIn('还有 3 题没订正', first['reason'])
        second = topics['20以内的退位减法']
        self.assertEqual((second['items'], second['days'], second['score']), (1, 1, 1.0), second)
        self.assertFalse(second['weak'])

    def test_a_topic_lists_its_questions_and_a_correction_closes_one(self):
        first = self.wrong(day(3), '10以内的加法', label='第1题')
        second = self.wrong(day(1), '10以内的加法', label='第2题')
        self.wrong(day(0), '20以内的退位减法', label='第3题')
        code, out = self.request('/api/wrong/topic?name=' + quote('10以内的加法'))
        self.assertEqual(code, 200, out)
        self.assertEqual((out['count'], out['open']), (2, 2), out)
        self.assertEqual([item['day'] for item in out['items']], [day(1), day(3)], out)
        self.assertEqual(out['items'][0]['label'], '第2题', out)
        key = 'k' * 32
        code, out = self.request('/api/wrong/followup', {'record_id': second, 'kind': 'correction', 'request_key': key})
        self.assertEqual(code, 200, out)
        code, again = self.request('/api/wrong/followup', {'record_id': second, 'kind': 'correction', 'request_key': key})
        self.assertEqual(code, 200, again)
        code, detail = self.request('/api/wrong/topic?name=' + quote('10以内的加法'))
        self.assertEqual((detail['count'], detail['open']), (2, 1), detail)
        code, rollup = self.request('/api/wrong/topics?days=30')
        topic = {row['name']: row for row in rollup['topics']}['10以内的加法']
        self.assertEqual(topic['open'], 1, topic)
        self.assertEqual(topic['score'], 1.7, topic)
        code, missing = self.request('/api/wrong/followup', {'record_id': 999999, 'kind': 'correction', 'request_key': key})
        self.assertEqual(code, 404, missing)
        self.assertEqual(missing['code'], 'wrong_unknown', missing)
        code, bad = self.request('/api/wrong/followup', {'record_id': first, 'kind': 'nope', 'request_key': key})
        self.assertEqual(code, 400, bad)
        self.assertEqual(self.request('/api/wrong/topic?name=')[0], 400)

    def test_a_narrower_window_leaves_the_old_day_out(self):
        self.wrong(day(25), '10以内的加法')
        self.wrong(day(6), '10以内的加法')
        self.wrong(day(0), '10以内的加法')
        code, out = self.request('/api/wrong/topics?days=7')
        self.assertEqual(code, 200, out)
        first = out['topics'][0]
        self.assertEqual((first['items'], first['days'], first['score']), (2, 2, 2.0), first)
        self.assertTrue(first['weak'])

    def test_an_unknown_window_is_a_plain_400(self):
        for bad in ('soon', '0', '99999'):
            code, out = self.request('/api/wrong/topics?days=' + bad)
            self.assertEqual(code, 400, (bad, out))
            self.assertEqual(out['code'], 'topics_query_invalid', (bad, out))
        code, out = self.request('/api/wrong/topics?days=30&child_id=child-1')
        self.assertEqual(code, 400, out)


if __name__ == '__main__':
    unittest.main()
