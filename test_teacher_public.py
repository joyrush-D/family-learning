"""Synthetic public-page checks; never contact a real teacher or website."""
import datetime as dt
from email.message import Message
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import family_teacher_public as public


class Socket:
    closed = False
    def settimeout(self, seconds): assert 0 < seconds <= 10
    def close(self): self.closed = True


class Response:
    def __init__(self, body, status=200, content_type='text/html; charset=utf-8', encoding=None):
        self.body, self.status, self.headers = body, status, Message()
        self.headers['Content-Type'] = content_type
        if encoding: self.headers['Content-Encoding'] = encoding
    def getheader(self, name, default=None): return self.headers.get(name, default)
    def read1(self, amount):
        if self.body is None: raise OSError('SYNTHETIC_RESET')
        result, self.body = self.body[:amount], self.body[amount:]; return result


class Connection:
    closed = False
    def __init__(self, response): self.response = response
    def request(self, method, path, headers):
        self.path = path
        assert method == 'GET' and 'Cookie' not in headers and 'Authorization' not in headers
    def getresponse(self): return self.response
    def close(self): self.closed = True


def synthetic_fetch(body, status=200, content_type='text/html; charset=utf-8', encoding=None,
                    value='https://school.example/teaching', call=None):
    # DNS, dialing, TLS and HTTP are all patched: nothing here reaches a real host.
    connection, raw, tls = Connection(Response(body, status, content_type, encoding)), Socket(), Socket()
    with patch.object(public.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]), \
         patch.object(public.socket, 'create_connection', return_value=raw) as dial, \
         patch.object(public.ssl, 'create_default_context') as context, \
         patch.object(public.http.client, 'HTTPSConnection', return_value=connection):
        context.return_value.wrap_socket.return_value = tls
        try:
            result = (call or public.fetch_page)(value)
        except (ValueError, OSError) as error:
            result = error
    assert dial.call_args.args[0] == ('93.184.216.34', 443)
    assert context.return_value.wrap_socket.call_args.kwargs['server_hostname'] == 'school.example'
    assert connection.closed and raw.closed, 'connection must close on every path'
    return result, connection


class PublicChecks(unittest.TestCase):
    def test_weekly_changes_failures_and_url_race(self):
        with tempfile.TemporaryDirectory() as directory:
            def connect():
                c = sqlite3.connect(Path(directory) / 'fictional.sqlite3'); c.row_factory = sqlite3.Row
                return c
            app = SimpleNamespace(connect=connect)
            now = dt.datetime(2026, 1, 1, tzinfo=public.TZ)
            with connect() as c:
                c.execute('CREATE TABLE teachers(id TEXT PRIMARY KEY,data TEXT)')
                c.execute('INSERT INTO teachers VALUES (?,?)', ('fictional', json.dumps(dict(public_url='https://school.example/teaching', archived=False))))
            self.assertEqual(public.run_one(app, now, lambda _: '教学原文')['state'], 'checked')
            self.assertEqual(public.run_one(app, now + dt.timedelta(days=6), lambda _: self.fail('too early'))['state'], 'idle')
            self.assertEqual(public.run_one(app, now + dt.timedelta(days=7), lambda _: '教学更新')['state'], 'changed')
            with connect() as c:
                changed = public.snapshot(c, 'fictional', 'https://school.example/teaching')
                self.assertEqual((changed['previous_text'], changed['text']), ('教学原文', '教学更新'))
            def failed(_): raise OSError('SYNTHETIC_PRIVATE_ERROR')
            self.assertEqual(public.run_one(app, now + dt.timedelta(days=14), failed)['state'], 'error')
            with connect() as c:
                state = public.snapshot(c, 'fictional', 'https://school.example/teaching')
                self.assertEqual(state['last_success'], changed['last_success'])
                self.assertEqual(state['text'], changed['text'])
                self.assertNotIn('SYNTHETIC_PRIVATE_ERROR', state['error'])
                self.assertEqual(public.snapshot(c, 'fictional', 'https://other.example/profile')['status'], 'pending')
            def raced(_):
                with connect() as c:
                    c.execute('UPDATE teachers SET data=?', (json.dumps(dict(public_url='https://other.example/profile', archived=False)),))
                return '旧链接晚到的结果'
            self.assertEqual(public.run_one(app, now + dt.timedelta(days=21), raced)['state'], 'superseded')
            with connect() as c:
                self.assertEqual(public.snapshot(c, 'fictional', 'https://other.example/profile')['text'], '')

    def test_public_transport_and_bounded_plain_text(self):
        for url in ('http://school.example', 'https://127.0.0.1/', 'https://[::1]/', 'https://school.local/',
                    'https://user:password@school.example/', 'https://school.example:8765/',
                    'https://school.example/#fragment', 'https://school.example/\nprivate'):
            with self.subTest(url=url), self.assertRaises(ValueError): public.validate_url(url)
        self.assertEqual(public.validate_url('https://SCHOOL.example'), 'https://school.example/')
        for call in (public.fetch_text, public.fetch_page):
            with patch.object(public.socket, 'getaddrinfo') as resolve, self.assertRaises(ValueError): call('   ')
            resolve.assert_not_called()
            for ips in (['127.0.0.1'], ['93.184.216.34', '10.0.0.1'], ['224.0.0.1']):
                with patch.object(public.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', (ip, 443)) for ip in ips]), \
                     patch.object(public.socket, 'create_connection') as dial, self.assertRaises(ValueError):
                    call('https://school.example/')
                dial.assert_not_called()
            for body, status, content_type, encoding, expected in [
                    (b'<h1>Teaching</h1><script>private()</script><style>x</style><!--hidden--><p>Helpful</p>',
                     200, 'text/html; charset=utf-8', None, 'Teaching\nHelpful'),
                    (b'redirect', 302, 'text/html', None, ValueError('未返回')),
                    (b'x' * (public.MAX_BYTES + 1), 200, 'text/plain', None, ValueError('过大')),
                    (b'zipped', 200, 'text/html', 'gzip', ValueError('编码')),
                    (b'%PDF-1.7', 200, 'application/pdf', None, ValueError('文字网页')),
                    (b'<script>only()</script>', 200, 'text/html', None, ValueError('没有可读取文字')),
                    (None, 200, 'text/plain', None, OSError('SYNTHETIC_RESET'))]:
                with self.subTest(call=call.__name__, status=status, content_type=content_type, encoding=encoding):
                    result, _ = synthetic_fetch(body, status, content_type, encoding, call=call)
                    if isinstance(expected, Exception):
                        self.assertIsInstance(result, type(expected)); self.assertIn(str(expected), str(result))
                    else:
                        self.assertEqual(result if call is public.fetch_text else result['text'], expected)

    def test_fetch_page_structure_and_truncation(self):
        before = dt.datetime.now(public.TZ)
        page, connection = synthetic_fetch('第三周 作业  说明\n'.encode(), content_type='text/plain; charset=utf-8',
                                           value='https://SCHOOL.example/Week?no=3')
        after = dt.datetime.now(public.TZ)
        self.assertEqual(sorted(page), ['content_type', 'fetched_at', 'text', 'text_truncated', 'url'])
        self.assertEqual((page['url'], page['text'], page['text_truncated'], page['content_type']),
                         ('https://school.example/Week?no=3', '第三周 作业 说明', False, 'text/plain'))
        self.assertEqual(connection.path, '/Week?no=3')
        fetched = dt.datetime.fromisoformat(page['fetched_at'])
        self.assertEqual(fetched.utcoffset(), dt.timedelta(hours=8))
        self.assertTrue(before <= fetched <= after)
        for body, truncated in [(b'x' * public.TEXT_LIMIT + b'  \n', False), (b'x' * (public.TEXT_LIMIT + 1), True)]:
            with self.subTest(length=len(body)):
                page, _ = synthetic_fetch(body, content_type='text/plain')
                self.assertEqual((page['text'], page['text_truncated']), ('x' * public.TEXT_LIMIT, truncated))
                self.assertEqual(synthetic_fetch(body, content_type='text/plain', call=public.fetch_text)[0], page['text'])
        # Truncation is judged on the extracted text, not the raw document; script bodies never count or leak.
        padding = b'<script>' + b'p' * 8000 + b'</script>'
        page, _ = synthetic_fetch(b'<h1>Teaching</h1>' + padding + b'<p>Helpful</p>')
        self.assertEqual((page['text'], page['text_truncated'], page['content_type']), ('Teaching\nHelpful', False, 'text/html'))
        page, _ = synthetic_fetch(b'<p>' + '课'.encode() * (public.TEXT_LIMIT + 1) + b'</p>' + padding)
        self.assertEqual((page['text'], page['text_truncated']), ('课' * public.TEXT_LIMIT, True))


if __name__ == '__main__': unittest.main()
