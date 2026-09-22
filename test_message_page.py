"""Synthetic school-message page reader: one explicit HTTPS address, private fragment cache, parent HTTP.
No family data, model, message CLI or network: the page fetch is always a fake."""
import datetime as dt
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import family_agent as agent
import family_llm
import family_review
import family_teacher_public

LINK = 'https://school.example.invalid/notice/2026-02'
LONG = 'https://school.example.invalid/n/' + 'a' * 600
TEXT = '各位家长，请查看 ' + LINK + ' ，另见 http://plain.example.invalid/x 和 ' + LONG + ' 谢谢。'


def page(url, text='虚构公开页面正文', truncated=False):
    return dict(url=url, text=text, text_truncated=truncated, content_type='text/html', fetched_at='2026-02-10T08:10:00+08:00')


class Fetch:
    def __init__(self, result=None, error=None, during=None):
        self.calls = []; self.result = result; self.error = error; self.during = during

    def __call__(self, url):
        self.calls.append(url)
        if self.during: self.during()
        if self.error: raise self.error
        return self.result if self.result is not None else page(url)


class PageStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-page-'); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve(); self.data = root / 'private'; self.data.mkdir()
        (root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 11岁 | 五年级 |\n')
        self.app = family_review.load_app(root, self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data)
        self.now = dt.datetime(2026, 2, 10, 8, tzinfo=agent.TZ)
        self.source = dict(id='wechat:12345@chatroom', platform='wechat', child_id='child-1', name='虚构班级', cursor='10', enabled=True)
        self.write_config()
        model = patch.object(family_llm, '_chat_json', side_effect=AssertionError('page reader must not call a model'))
        model.start(); self.addCleanup(model.stop)
        self.ingest(self.message())

    def write_config(self, enabled=True, source_enabled=True, child_id='child-1'):
        source = {**self.source, 'child_id': child_id, 'enabled': source_enabled}
        (self.data / 'agent.json').write_text(json.dumps({'enabled': enabled, 'sources': [source]}))

    def message(self, ident='1', text=TEXT):
        return dict(id=ident, time=self.now.isoformat(), kind='text', sender='虚构老师', text=text, unread=False)

    def ingest(self, message):
        with self.store._db() as c:
            row = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (self.source['id'],)).fetchone()
        expected = row['cursor'] if row else self.source['cursor']
        return self.store.ingest(dict(source_id=self.source['id'], expected_cursor=expected, cursor=str(int(expected) + 1),
            checked_at=message['time'], last_message_time=message['time'], error='', messages=[message]))

    def keys(self, url=LINK, **changes):
        return dict(child_id='child-1', source_id=self.source['id'], message_id='1', url=url) | changes

    def rows(self, sql='SELECT * FROM agent_message_pages', args=()):
        with self.store._db() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def post(self, fetch, **changes):
        return self.store.message_page(self.keys(**changes), lambda row: dict(row), fetch=fetch)

    def get(self, store=None):
        return (store or self.store).message({k: v for k, v in self.keys().items() if k != 'url'}, lambda row: dict(row))

    def correct_message(self):
        with self.store._db() as c:
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(self.message(text=TEXT + '（更正）'), ensure_ascii=False), self.source['id'], '1'))

    def test_read_save_reopen_truncation_flag_and_duplicate_zero_outbound(self):
        messages = self.rows('SELECT * FROM agent_messages')
        fetch = Fetch(page(LINK, 'x' * family_teacher_public.TEXT_LIMIT, True))
        result = self.post(fetch)
        self.assertFalse(result['cached']); self.assertEqual(fetch.calls, [LINK])
        self.assertEqual(len(result['page']['text']), 6000); self.assertTrue(result['page']['text_truncated'])
        self.assertEqual((result['page']['url'], result['page']['original_url'], result['page']['child_id']), (LINK, LINK, 'child-1'))
        self.assertEqual(result['pages'], [result['page']]); self.assertEqual(result['message']['text'], TEXT)
        rows = self.rows(); self.assertEqual(len(rows), 1); self.assertEqual(json.loads(rows[0]['payload']), result['page'])
        again = self.post(fetch)
        self.assertTrue(again['cached']); self.assertEqual(again['page'], result['page']); self.assertEqual(len(fetch.calls), 1)
        reopened = agent.Store(self.app.connect, self.app.profiles, self.data)
        self.assertEqual(self.get(reopened)['pages'], [result['page']]); self.assertEqual(self.get()['pages'], [result['page']])
        self.assertEqual(len(fetch.calls), 1); self.assertEqual(self.rows(), rows)
        # The saved message, drafts and teacher pages are untouched; the fragment is a quote, not a fact.
        self.assertEqual(self.rows('SELECT * FROM agent_messages'), messages)
        self.assertEqual(self.rows('SELECT * FROM agent_message_drafts'), [])
        with self.store._db() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='teacher_public_pages'").fetchone():
                self.assertEqual(c.execute('SELECT count(*) FROM teacher_public_pages').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0], 0)

    def test_rejections_make_no_call_and_no_write(self):
        fetch = Fetch()
        self.assertEqual(agent._links([dict(text=TEXT)])[2], LONG[:500])  # display clip; never an address to read
        cases = [
            (self.keys(child_id='child-2'), 403, 'source_not_allowed'),
            (self.keys(source_id='wechat:other@chatroom'), 403, 'source_not_allowed'),
            (self.keys(message_id='2'), 404, 'message_not_found'),
            (self.keys(url='https://school.example.invalid/other'), 400, 'page_link_not_in_message'),
            (self.keys(url=LONG[:500]), 400, 'page_link_not_in_message'),
            (self.keys(url=LINK[:-1]), 400, 'page_link_not_in_message'),
            (self.keys(url=LINK + '/../admin'), 400, 'page_link_not_in_message'),
            (self.keys(url='https://School.example.invalid/notice/2026-02'), 400, 'page_link_not_in_message'),
            (self.keys(url='http://plain.example.invalid/x'), 400, 'page_link_unsupported'),
            (self.keys(url=''), 400, 'invalid_agent'),
            (self.keys(url=7), 400, 'invalid_agent'),
            (self.keys() | {'refresh': True}, 400, 'invalid_agent'),
            ({k: v for k, v in self.keys().items() if k != 'url'}, 400, 'invalid_agent'),
        ]
        for obj, status, code in cases:
            with self.assertRaises(agent.AgentError) as caught:
                self.store.message_page(obj, lambda row: dict(row), fetch=fetch)
            self.assertEqual((caught.exception.status, caught.exception.code), (status, code), obj)
        self.assertEqual(fetch.calls, []); self.assertEqual(self.rows(), [])
        self.assertEqual(self.post(fetch, url=LONG)['page']['url'], LONG)  # the complete long address is fine
        self.assertEqual(fetch.calls, [LONG])
        for change in (dict(source_enabled=False), dict(enabled=False)):
            self.write_config(**change)
            with self.assertRaises(agent.AgentError) as caught: self.post(fetch)
            self.assertEqual((caught.exception.status, caught.exception.code), (403, 'source_not_enabled'))
            self.assertEqual(self.get()['pages'], [])  # withdrawn authorization hides the saved fragment too
        self.assertEqual(fetch.calls, [LONG]); self.assertEqual(len(self.rows()), 1)

    def test_concurrent_same_request_first_commit_wins(self):
        other = Fetch(page(LINK, '先提交的内容'))
        first = Fetch(page(LINK, '后提交的内容'), during=lambda: self.post(other))
        result = self.post(first)
        self.assertEqual((first.calls, other.calls), ([LINK], [LINK]))
        self.assertTrue(result['cached']); self.assertEqual(result['page']['text'], '先提交的内容')
        rows = self.rows(); self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]['payload'])['text'], '先提交的内容')
        self.assertEqual(self.get()['pages'], [result['page']])

    def test_change_during_fetch_rejects_and_stale_fragment_stays_hidden(self):
        with self.assertRaises(agent.AgentError) as caught: self.post(Fetch(during=self.correct_message))
        self.assertEqual((caught.exception.status, caught.exception.code), (409, 'page_context_changed'))
        self.assertEqual(self.rows(), []); self.assertEqual(self.get()['pages'], [])
        with self.assertRaises(agent.AgentError) as caught: self.post(Fetch(during=lambda: self.write_config(enabled=False)))
        self.assertEqual(caught.exception.code, 'source_not_enabled'); self.assertEqual(self.rows(), [])
        self.write_config()
        with self.assertRaises(agent.AgentError) as caught: self.post(Fetch(during=lambda: self.write_config(child_id='child-2')))
        self.assertIn(caught.exception.status, (403, 409)); self.assertEqual(self.rows(), [])
        self.write_config()
        saved = self.post(Fetch(page(LINK, '原内容')))
        self.assertEqual(self.get()['pages'], [saved['page']])
        self.correct_message(); before = self.rows()
        self.assertEqual(self.get()['pages'], []); self.assertEqual(self.rows(), before)  # hidden, not deleted, no write
        fetch = Fetch(page(LINK, '更正后内容'))
        renewed = self.post(fetch)
        self.assertFalse(renewed['cached']); self.assertEqual(fetch.calls, [LINK])
        self.assertEqual(len(self.rows()), 1); self.assertEqual(self.get()['pages'], [renewed['page']])
        self.assertNotIn('原内容', json.dumps(self.rows(), ensure_ascii=False))

    def test_fetch_failure_keeps_message_and_allows_retry(self):
        before = self.rows('SELECT * FROM agent_messages')
        failures = (Fetch(error=OSError('/private/peer boom')), Fetch(error=ValueError('公开页面过大，未保存')), Fetch(error=TimeoutError()),
                    Fetch(result=dict(url=LINK, text='')), Fetch(result=page('https://other.example.invalid/')),
                    Fetch(result=page(LINK, 'x' * (family_teacher_public.TEXT_LIMIT + 1))))
        for failing in failures:
            with self.assertRaises(agent.AgentError) as caught: self.post(failing)
            self.assertEqual((caught.exception.status, caught.exception.code), (502, 'page_fetch_failed'))
            self.assertNotIn('boom', str(caught.exception)); self.assertEqual(failing.calls, [LINK])
        self.assertEqual(self.rows(), []); self.assertEqual(self.rows('SELECT * FROM agent_messages'), before)
        self.assertEqual(self.get()['pages'], [])
        result = self.post(Fetch())
        self.assertFalse(result['cached']); self.assertEqual(len(self.rows()), 1)


class PageHTTPTests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-page-http-'); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve(); private = root / 'private'; private.mkdir()
        (root / '家庭运行规则.md').write_text('| child-1 | 示例星星 | 男 | 10岁 | 四年级 |\n| child-2 | 示例月亮 | 男 | 13岁 | 初一 |\n')
        (root / 'index.html').write_text('<h1>Synthetic family application</h1>')
        self.fetch = Fetch(page(LINK, '虚构公开页面正文'))
        for started in (patch.multiple(app, ROOT=root, DATA=private, DB=private / 'family.sqlite3'),
                        patch.dict(app.os.environ, {'FAMILY_HOST': 'family.example.invalid', 'FAMILY_USER': 'parent@example.invalid',
                                                    'FAMILY_CHILD_COOKIE_PATH': '/child/'}),
                        patch.object(app.family_llm, '_chat_json', side_effect=AssertionError('HTTP page read must not call a model')),
                        patch.object(family_teacher_public, 'fetch_page', self.fetch)):
            started.start(); self.addCleanup(started.stop)
        app.connect().close()
        self.source = dict(id='synthetic@chatroom', platform='wechat', child_id='child-1', name='虚构授权班级群', cursor='100', enabled=True)
        path = app.DATA / 'agent.json'; path.write_text(json.dumps(dict(enabled=True, sources=[self.source]), ensure_ascii=False)); path.chmod(0o600)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.thread.join, 3); self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.parent = {'X-Family-Token': app.TOKEN}
        batch = dict(source_id=self.source['id'], expected_cursor='100', cursor='101', checked_at='2026-02-10T08:05:00+08:00',
                     last_message_time='2026-02-10T08:00:00+08:00', error='',
                     messages=[dict(id='101', time='2026-02-10T08:00:00+08:00', kind='text', sender='虚构老师', text=TEXT, unread=False)])
        status, result, _ = self.request('POST', '/api/agent/ingest', batch, self.parent)
        self.assertEqual(status, 200, result)

    def request(self, method, path, obj=None, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode() if obj is not None else None
        headers = dict(headers or {})
        if obj is not None: headers.setdefault('Content-Type', 'application/json')
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse(); raw = response.read(); info = dict(response.getheaders())
            result = json.loads(raw) if info.get('Content-Type', '').startswith('application/json') else raw
            return response.status, result, info
        finally:
            connection.close()

    def keys(self, **changes):
        return dict(child_id='child-1', source_id=self.source['id'], message_id='101', url=LINK) | changes

    def count(self):
        with self.app.connect() as db:
            return db.execute('SELECT count(*) FROM agent_message_pages').fetchone()[0]

    def test_parent_reads_once_then_cached_and_get_lists_pages(self):
        status, result, _ = self.request('POST', '/api/agent/message/page', self.keys(), self.parent)
        self.assertEqual(status, 200, result); self.assertFalse(result['cached'])
        self.assertEqual(result['page']['text'], '虚构公开页面正文'); self.assertEqual(result['pages'], [result['page']])
        self.assertEqual(self.fetch.calls, [LINK])
        status, again, _ = self.request('POST', '/api/agent/message/page', self.keys(), self.parent)
        self.assertEqual(status, 200); self.assertTrue(again['cached']); self.assertEqual(self.fetch.calls, [LINK])
        query = urlencode({k: v for k, v in self.keys().items() if k != 'url'})
        for _ in range(2):
            status, view, _ = self.request('GET', '/api/agent/message?' + query, headers=self.parent)
            self.assertEqual(status, 200); self.assertEqual(view['pages'], [result['page']])
        self.assertEqual(self.fetch.calls, [LINK]); self.assertEqual(self.count(), 1)
        status, denied, _ = self.request('POST', '/api/agent/message/page', self.keys(url=LONG[:500]), self.parent)
        self.assertEqual((status, denied['code']), (400, 'page_link_not_in_message'))
        self.assertEqual(self.request('POST', '/api/agent/message/page', self.keys(child_id='child-2'), self.parent)[0], 403)
        self.assertEqual(self.fetch.calls, [LINK]); self.assertEqual(self.count(), 1)

    def test_child_cookie_anonymous_and_csrf_are_refused_without_reading(self):
        invitation = self.app.family_child.parent_action(self.app, 'invite', {'child_id': 'child-1'})
        status, child, headers = self.request('POST', '/child/api/login', {'invite': invitation['invite']}, {})
        self.assertEqual(status, 200, child)
        child_headers = {'Cookie': headers['Set-Cookie'].split(';', 1)[0], 'X-Child-CSRF': child['csrf']}
        self.assertEqual(self.request('POST', '/api/agent/message/page', self.keys(), child_headers)[0], 403)
        self.assertEqual(self.request('POST', '/api/agent/message/page', self.keys(), child_headers | {'Host': 'family.example.invalid'})[0], 403)
        self.assertEqual(self.request('POST', '/child/api/agent/message/page', self.keys(), child_headers | self.parent)[0], 404)
        self.assertIn(self.request('POST', '/api/agent/message/page', self.keys(), {'Host': 'family.example.invalid'})[0], (401, 403))
        for headers in ({}, {'X-Family-Token': 'wrong'}, self.parent | {'Host': 'untrusted.invalid'}):
            self.assertEqual(self.request('POST', '/api/agent/message/page', self.keys(), headers)[0], 403)
        self.assertEqual(self.fetch.calls, []); self.assertEqual(self.count(), 0)
        trusted = {'Host': 'family.example.invalid', 'Tailscale-User-Login': 'parent@example.invalid', **self.parent}
        status, result, _ = self.request('POST', '/api/agent/message/page', self.keys(), trusted)
        self.assertEqual(status, 200, result); self.assertEqual(self.fetch.calls, [LINK]); self.assertEqual(self.count(), 1)


if __name__ == '__main__':
    unittest.main()
