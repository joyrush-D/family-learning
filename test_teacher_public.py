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
        for ips in (['127.0.0.1'], ['93.184.216.34', '10.0.0.1'], ['224.0.0.1']):
            with patch.object(public.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', (ip, 443)) for ip in ips]), \
                 patch.object(public.socket, 'create_connection') as dial, self.assertRaises(ValueError):
                public.fetch_text('https://school.example/')
            dial.assert_not_called()

        class Socket:
            def settimeout(self, seconds): assert 0 < seconds <= 10
            def close(self): pass
        class Response:
            status = 200
            def __init__(self, body):
                self.body = body; self.headers = Message(); self.headers['Content-Type'] = 'text/html; charset=utf-8'
            def getheader(self, name, default=None): return self.headers.get(name, default)
            def read1(self, amount):
                result, self.body = self.body[:amount], self.body[amount:]; return result
        class Connection:
            def __init__(self, response): self.response = response
            def request(self, method, path, headers):
                self.headers = headers
                assert method == 'GET' and 'Cookie' not in headers and 'Authorization' not in headers
            def getresponse(self): return self.response
            def close(self): pass
        for body, status, fails in [(b'<h1>Teaching</h1><script>private()</script><style>x</style><!--hidden--><p>Helpful</p>', 200, False),
                                    (b'redirect', 302, True), (b'x' * (public.MAX_BYTES + 1), 200, True)]:
            response = Response(body); response.status = status; connection = Connection(response); tls = Socket()
            with patch.object(public.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]), \
                 patch.object(public.socket, 'create_connection', return_value=Socket()) as dial, \
                 patch.object(public.ssl, 'create_default_context') as context, \
                 patch.object(public.http.client, 'HTTPSConnection', return_value=connection):
                context.return_value.wrap_socket.return_value = tls
                if fails:
                    with self.assertRaises(ValueError): public.fetch_text('https://school.example/teaching')
                else:
                    self.assertEqual(public.fetch_text('https://school.example/teaching'), 'Teaching\nHelpful')
                self.assertEqual(dial.call_args.args[0], ('93.184.216.34', 443))
                self.assertEqual(context.return_value.wrap_socket.call_args.kwargs['server_hostname'], 'school.example')


if __name__ == '__main__': unittest.main()
