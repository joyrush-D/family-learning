"""Synthetic checks for the standalone parent access record; no server or family data."""
import base64
import http.client
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

import family_access as access


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-access-')
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.password = 'synthetic-parent-password-123'
        self.config = access.make_config('https://family.example.ts.net/family', 'parent', self.password)
        self.path = self.data / 'access.json'
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        if os.name != 'nt': self.path.chmod(0o600)

    def header(self, username='parent', password=None):
        value = username + ':' + (self.password if password is None else password)
        return 'Basic ' + base64.b64encode(value.encode('utf-8')).decode('ascii')

    def test_make_and_read_config_and_reject_unsafe_urls_or_passwords(self):
        self.assertEqual(access.read_config(self.data), self.config)
        self.assertEqual(access.read_config(self.data / 'missing'), None)
        for base_url in ('http://family.example.ts.net', 'https://localhost', 'https://127.0.0.1',
                         'https://[::1]', 'https://family.example.ts.net?x=1',
                         'https://user:pass@family.example.ts.net', 'https://family.example.ts.net/a/../b',
                         'https://family', 'https://-bad.example.ts.net',
                         ' https://family.example.ts.net', 'https://family.example.ts.net/with space'):
            with self.subTest(base_url=base_url):
                with self.assertRaises(access.AccessError): access.make_config(base_url, 'parent', self.password)
        for password in ('short', 'x' * 201, 'valid-password-\n-123'):
            with self.subTest(password=password):
                with self.assertRaises(access.AccessError): access.make_config('https://family.example.ts.net', 'parent', password)
        with self.assertRaises(access.AccessError): access.make_config('https://family.example.ts.net', 'bad:user', self.password)

    def test_bad_config_is_safe_and_permissions_or_symlink_are_rejected(self):
        bad = dict(self.config, password_hash='not-a-secret-hash')
        self.path.write_text(json.dumps(bad), encoding='utf-8')
        if os.name != 'nt': self.path.chmod(0o600)
        with self.assertRaises(access.AccessError) as raised: access.read_config(self.data)
        self.assertNotIn('not-a-secret-hash', str(raised.exception))
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        if os.name != 'nt':
            self.path.chmod(0o644)
            with self.assertRaises(access.AccessError): access.read_config(self.data)
            self.path.chmod(0o600)
        target = self.data / 'target.json'; target.write_text(json.dumps(self.config), encoding='utf-8')
        if os.name != 'nt': target.chmod(0o600)
        self.path.unlink(); self.path.symlink_to(target)
        with self.assertRaises(access.AccessError): access.read_config(self.data)

    def test_basic_auth_success_failure_and_last_success_cache(self):
        good = {'Authorization': self.header()}
        self.assertTrue(access.authorized(good, self.config))
        with patch.object(access.hashlib, 'pbkdf2_hmac', wraps=access.hashlib.pbkdf2_hmac) as derive:
            self.assertTrue(access.authorized(good, self.config))
            self.assertEqual(derive.call_count, 0)
            self.assertFalse(access.authorized({'Authorization': self.header(password='wrong-password-123')}, self.config))
            self.assertEqual(derive.call_count, 1)
            self.assertFalse(access.authorized({'Authorization': self.header(username='other')}, self.config))
            self.assertEqual(derive.call_count, 2)

        changed = dict(self.config, base_url='https://new-family.example.ts.net/family')
        with patch.object(access.hashlib, 'pbkdf2_hmac', wraps=access.hashlib.pbkdf2_hmac) as derive:
            self.assertTrue(access.authorized(good, changed))
            self.assertEqual(derive.call_count, 1)
            revoked = dict(changed, password_hash='0' * 64)
            self.assertFalse(access.authorized(good, revoked))
            self.assertEqual(derive.call_count, 2)

    def test_strict_single_basic_header_and_no_lightweight_cache_for_failures(self):
        good = self.header()
        self.assertFalse(access.authorized({}, self.config))
        self.assertFalse(access.authorized({'Authorization': [good, good]}, self.config))
        self.assertFalse(access.authorized({'authorization': good, 'Authorization': good}, self.config))
        for value in ('Bearer synthetic-token', 'Basic !!!', 'Basic ' + base64.b64encode(b'no-colon').decode(),
                      'Basic ' + base64.b64encode(b'parent:\xff').decode('latin1')):
            with self.subTest(value=value): self.assertFalse(access.authorized({'Authorization': value}, self.config))

    def test_handler_http_auth_boundaries_with_isolated_family(self):
        """Exercise the real Handler with a temporary DB and fictional child only."""
        root = Path(self.temp.name) / 'http-root'
        data = root / 'private'
        root.mkdir()
        data.mkdir()
        (root / '家庭运行规则.md').write_text(
            '| child-1 | 示例孩子 | 未填写 | 未填写 | 四年级 |\n', encoding='utf-8')
        for name in ('消息来源.md', '跟踪台账.md', '学习与成长.md'):
            (root / name).write_text('# 虚构测试资料\n', encoding='utf-8')
        for name in ('child.html', 'child.js', 'child.css'):
            (root / name).write_text('synthetic child asset', encoding='utf-8')
        (root / 'index.html').write_text('<!doctype html><title>虚构家庭</title>', encoding='utf-8')
        (root / 'login.html').write_text('<!doctype html><title>虚构家庭登录</title>', encoding='utf-8')
        (root / 'login.js').write_text('document.title = "synthetic login";', encoding='utf-8')
        # Delay app import until FAMILY_DATA points into this temporary case;
        # importing app otherwise creates its default private directory.
        with patch.dict(os.environ, {'FAMILY_DATA': str(data)}, clear=True):
            import app
            import family_child
            old = app.ROOT, app.DATA, app.DB
            app.ROOT, app.DATA, app.DB = root, data, data / 'family.sqlite3'
            app.connect().close()
            server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            access_path = data / 'access.json'
            password = 'synthetic-http-parent-password-123'
            configured = access.make_config('https://family.example.ts.net/family', 'parent', password)
            parent_auth = 'Basic ' + base64.b64encode(('parent:' + password).encode()).decode('ascii')

            def request(method, path, obj=None, host='127.0.0.1', headers=None):
                values = {'Host': host}
                values.update(headers or {})
                body = None
                if obj is not None:
                    body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
                    values.setdefault('Content-Type', 'application/json')
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request(method, path, body, values)
                reply = client.getresponse()
                status, raw, info = reply.status, reply.read(), dict(reply.getheaders())
                client.close()
                return status, raw, info

            def get(path='/api/state', host='127.0.0.1', headers=None):
                return request('GET', path, host=host, headers=headers)

            def post(path, obj, host='127.0.0.1', headers=None):
                return request('POST', path, obj, host=host, headers=headers)

            def install_config():
                access_path.write_text(json.dumps(configured, ensure_ascii=False), encoding='utf-8')
                if os.name != 'nt': access_path.chmod(0o600)

            def parent_login(password_value=password, host='family.example.ts.net', headers=None):
                values = {'Content-Type': 'application/json', 'X-Family-Login': '1',
                          'Origin': 'https://family.example.ts.net'}
                values.update(headers or {})
                return post('/api/parent/login', {'username': 'parent', 'password': password_value},
                            host=host, headers=values)

            def raw_status(raw_request):
                sock = socket.create_connection(('127.0.0.1', server.server_port), timeout=5)
                try:
                    sock.sendall(raw_request)
                    received = b''
                    while b'\r\n' not in received:
                        part = sock.recv(4096)
                        if not part: break
                        received += part
                    return int(received.split(b' ', 2)[1])
                finally:
                    sock.close()

            try:
                with patch.dict(os.environ, {
                    'FAMILY_HOST': 'family.example.ts.net',
                    'FAMILY_USER': 'parent@example.invalid',
                    'FAMILY_CHILD_COOKIE_PATH': '/child/',
                    'FAMILY_CHILD_PUBLIC_URL': 'https://family.example.ts.net/family/child/',
                    'FAMILY_PRINT_BRIDGE_TOKEN': 'synthetic-print-token'}, clear=True):
                    # Legacy deployments remain usable before access.json is installed.
                    self.assertEqual(get()[0], 200)
                    self.assertEqual(get(host='family.example.ts.net', headers={
                        'Tailscale-User-Login': 'parent@example.invalid'})[0], 200)
                    self.assertEqual(get(host='family.example.ts.net', headers={
                        'Tailscale-User-Login': 'other@example.invalid'})[0], 403)
                    self.assertEqual(get(host='untrusted.invalid')[0], 403)
                    self.assertEqual(get(host='localhost', headers={
                        'X-Forwarded-For': '192.0.2.10'})[0], 403)

                    install_config()
                    # A forwarded Serve request always needs the parent credential;
                    # a Tailscale identity alone and a spoofed localhost Host do not.
                    self.assertEqual(get(host='family.example.ts.net', headers={
                        'Tailscale-User-Login': 'parent@example.invalid'})[0], 401)
                    self.assertEqual(get(host='localhost', headers={
                        'Forwarded': 'for=192.0.2.10;proto=https;host=family.example.ts.net'})[0], 401)
                    self.assertEqual(get(host='localhost', headers={
                        'X-Forwarded-For': '192.0.2.10'})[0], 401)
                    # The login page is public; the family HTML and API are not.
                    status, body, info = get('/login', host='family.example.ts.net')
                    self.assertEqual(status, 200)
                    self.assertTrue(info.get('Content-Type', '').startswith('text/html'))
                    self.assertNotIn(b'child-1', body)
                    self.assertEqual(get('/login.js', host='family.example.ts.net')[0], 200)
                    status, _, info = get('/', host='family.example.ts.net', headers={'Accept': 'text/html'})
                    self.assertEqual(status, 303)
                    self.assertTrue(info.get('Location', '').endswith('/family/login'))
                    status, body, info = get('/api/state', host='family.example.ts.net')
                    self.assertEqual(status, 401)
                    self.assertNotIn('WWW-Authenticate', info)
                    self.assertNotIn(b'"token"', body)
                    status, _, info = get('/calendar.ics', host='family.example.ts.net')
                    self.assertEqual(status, 401)
                    self.assertTrue(info.get('WWW-Authenticate', '').startswith('Basic '))
                    wrong_auth = 'Basic ' + base64.b64encode(b'parent:wrong-synthetic-password').decode()
                    status, _, challenge = get(host='family.example.ts.net', headers={'Authorization': wrong_auth})
                    self.assertEqual(status, 401)
                    self.assertNotIn('WWW-Authenticate', challenge)
                    self.assertEqual(get(host='family.example.ts.net', headers={
                        'Authorization': parent_auth})[0], 200)

                    calendar = dict(id='a' * 32, version=0, child_ids=['child-1'],
                                    title='虚构家庭安排', category='activity', day='2026-09-12',
                                    start_time='09:00', end_time='10:00', location='虚构地点',
                                    note='虚构备注', status='tentative', repeat='none', until='')
                    # Default HTTPS port is omitted from the browser Origin even when configured explicitly.
                    port_config = access.make_config('https://FAMILY.example.ts.net:443/family', 'parent', password)
                    access_path.write_text(json.dumps(port_config, ensure_ascii=False), encoding='utf-8')
                    if os.name != 'nt': access_path.chmod(0o600)
                    self.assertEqual(parent_login(headers={'Origin': 'https://family.example.ts.net'})[0], 200)
                    self.assertIn(parent_login(headers={'Origin': 'https://family.example.ts.net:444'})[0], (400, 403))
                    install_config()
                    # Login binds a session to this config and stores only a digest.
                    login_started = int(access.time.time())
                    status, body, info = parent_login()
                    self.assertEqual(status, 200)
                    self.assertEqual(json.loads(body), {'ok': True})
                    cookie = info['Set-Cookie']
                    cookie_name, cookie_value = cookie.split(';', 1)[0].split('=', 1)
                    self.assertEqual(cookie_name, 'family_parent_session')
                    self.assertRegex(cookie_value, r'^[A-Za-z0-9_-]{43}$')
                    attrs = {part.strip().lower() for part in cookie.split(';')[1:]}
                    self.assertTrue({'secure', 'httponly', 'samesite=lax', 'path=/family/', 'max-age=15552000'} <= attrs)
                    parent_cookie = cookie.split(';', 1)[0]
                    with app.connect() as db:
                        session = db.execute('SELECT * FROM parent_sessions WHERE hash=?',
                                             (access._digest(cookie_value),)).fetchone()
                        self.assertIsNotNone(session)
                        self.assertNotIn(cookie_value, tuple(session))
                        self.assertNotIn(password, tuple(session))
                        self.assertEqual(len(session['hash']), 64)
                        self.assertEqual(len(session['config_hash']), 64)
                    self.assertEqual(access.SESSION_AGE, 180 * 24 * 60 * 60)
                    # Both persistence layers must last six months, with a fixed end.
                    expiry = session['expires']
                    self.assertGreaterEqual(expiry, login_started + access.SESSION_AGE)
                    self.assertLessEqual(expiry, int(access.time.time()) + access.SESSION_AGE)
                    with patch.object(access.time, 'time', return_value=expiry - 1):
                        self.assertTrue(access.session_authorized({'Cookie': parent_cookie}, access.read_config(app.DATA), app.connect))
                    with patch.object(access.time, 'time', return_value=expiry):
                        self.assertFalse(access.session_authorized({'Cookie': parent_cookie}, access.read_config(app.DATA), app.connect))
                    self.assertEqual(get('/api/state', host='family.example.ts.net',
                                         headers={'Cookie': parent_cookie})[0], 200)
                    self.assertEqual(get('/child/api/state', host='family.example.ts.net',
                                         headers={'Cookie': parent_cookie})[0], 401)
                    # Rotating the application CSRF token expires only the old write token.
                    csrf_calendar = {**calendar, 'id': 'c' * 32, 'title': '虚构轮转安排'}
                    old_token = app.TOKEN
                    new_token = 'n' * 43
                    app.TOKEN = new_token
                    try:
                        status, body, _ = post('/api/calendar/save', csrf_calendar,
                                               host='family.example.ts.net', headers={
                                                   'Cookie': parent_cookie, 'X-Family-Token': old_token})
                        self.assertEqual(status, 403)
                        reply = json.loads(body)
                        self.assertEqual(reply.get('code'), 'csrf_expired')
                        self.assertEqual(reply.get('token'), new_token)
                        with app.connect() as db:
                            self.assertEqual(db.execute('SELECT count(*) FROM calendar_events WHERE id=?',
                                                        (csrf_calendar['id'],)).fetchone()[0], 0)
                        self.assertEqual(post('/api/calendar/save', csrf_calendar,
                                              host='family.example.ts.net', headers={
                                                  'Cookie': parent_cookie, 'X-Family-Token': new_token})[0], 200)
                    finally:
                        app.TOKEN = old_token
                    session_calendar = {**calendar, 'id': 'b' * 32, 'title': '虚构会话安排'}
                    status, body, _ = post('/api/calendar/save', session_calendar,
                                           host='family.example.ts.net', headers={'Cookie': parent_cookie})
                    self.assertEqual(status, 403)
                    self.assertEqual(json.loads(body).get('code'), 'csrf_expired')
                    self.assertEqual(json.loads(body).get('token'), app.TOKEN)
                    self.assertEqual(post('/api/calendar/save', session_calendar,
                                          host='family.example.ts.net', headers={'Cookie': parent_cookie,
                                                                                'X-Family-Token': app.TOKEN})[0], 200)

                    # A second device remains valid when the first device logs out.
                    status, _, info_b = parent_login()
                    self.assertEqual(status, 200)
                    cookie_b = info_b['Set-Cookie'].split(';', 1)[0]
                    logout_headers = {'Cookie': parent_cookie, 'Content-Type': 'application/json',
                                      'X-Family-Login': '1', 'Origin': 'https://family.example.ts.net'}
                    status, _, logout_info = post('/api/parent/logout', {}, host='family.example.ts.net',
                                                  headers=logout_headers)
                    self.assertEqual(status, 200)
                    self.assertIn('family_parent_session=', logout_info.get('Set-Cookie', ''))
                    self.assertEqual(get('/api/state', host='family.example.ts.net',
                                         headers={'Cookie': parent_cookie})[0], 401)
                    self.assertEqual(get('/api/state', host='family.example.ts.net',
                                         headers={'Cookie': cookie_b})[0], 200)
                    with app.connect() as db:
                        db.execute('UPDATE parent_sessions SET expires=0')
                    self.assertEqual(get('/api/state', host='family.example.ts.net',
                                         headers={'Cookie': cookie_b})[0], 401)
                    status, _, info_c = parent_login()
                    self.assertEqual(status, 200)
                    cookie_c = info_c['Set-Cookie'].split(';', 1)[0]
                    changed_config = access.make_config('https://family.example.ts.net/family', 'parent',
                                                        password + '-changed')
                    access_path.write_text(json.dumps(changed_config, ensure_ascii=False), encoding='utf-8')
                    if os.name != 'nt': access_path.chmod(0o600)
                    self.assertEqual(get('/api/state', host='family.example.ts.net',
                                         headers={'Cookie': cookie_c})[0], 401)
                    install_config()
                    status, _, info_d = parent_login()
                    self.assertEqual(status, 200)
                    cookie_d = info_d['Set-Cookie'].split(';', 1)[0]
                    self.assertEqual(raw_status(
                        b'GET /api/state HTTP/1.1\r\nHost: family.example.ts.net\r\n'
                        b'Cookie: ' + cookie_d.encode('ascii') + b'\r\nCookie: ' + cookie_d.encode('ascii') +
                        b'\r\nConnection: close\r\n\r\n'), 401)
                    self.assertEqual(get('/api/state', host='family.example.ts.net', headers={
                        'Cookie': cookie_c + '; ' + cookie_c})[0], 401)
                    self.assertEqual(get('/api/state', host='family.example.ts.net', headers={
                        'Cookie': 'family_parent_session=invalid', 'Authorization': parent_auth})[0], 401)
                    self.assertEqual(get('/', host='family.example.ts.net', headers={
                        'Accept': 'text/html', 'Cookie': 'family_parent_session=invalid',
                        'Authorization': parent_auth})[0], 303)

                    # Basic remains a supported parent credential, while writes need the app token.
                    self.assertEqual(get('/api/state', host='family.example.ts.net',
                                         headers={'Authorization': parent_auth})[0], 200)
                    self.assertEqual(get('/', host='family.example.ts.net', headers={
                        'Accept': 'text/html', 'Authorization': parent_auth})[0], 200)
                    parent_headers = {'Authorization': parent_auth, 'X-Family-Token': app.TOKEN}
                    self.assertEqual(post('/api/calendar/save', calendar,
                                          host='family.example.ts.net', headers={'Authorization': parent_auth})[0], 403)
                    self.assertEqual(post('/api/calendar/save', calendar,
                                          host='family.example.ts.net', headers=parent_headers)[0], 200)
                    self.assertEqual(get('/api/calendar?start=2026-09-01&end=2026-09-30',
                                         host='family.example.ts.net', headers={'Authorization': parent_auth})[0], 200)
                    status, body, info = get('/calendar.ics', host='family.example.ts.net',
                                             headers={'Authorization': parent_auth})
                    self.assertEqual(status, 200)
                    self.assertEqual(info.get('Content-Type'), 'text/calendar; charset=utf-8')
                    self.assertIn(b'BEGIN:VCALENDAR', body)

                    # Parent Basic auth is not a child session, while the child
                    # invite cookie cannot cross into the parent API.
                    self.assertEqual(get('/child/', host='family.example.ts.net')[0], 200)
                    self.assertEqual(get('/child/api/state', host='family.example.ts.net',
                                         headers={'Authorization': parent_auth})[0], 401)
                    invitation = family_child.parent_action(app, 'invite', {'child_id': 'child-1'})
                    status, body, info = post('/child/api/login', {'invite': invitation['invite']},
                                              host='family.example.ts.net')
                    self.assertEqual(status, 200)
                    child_cookie = info['Set-Cookie'].split(';', 1)[0]
                    self.assertEqual(get('/child/api/state', host='family.example.ts.net',
                                         headers={'Cookie': child_cookie})[0], 200)
                    status, body, _ = get('/api/state', host='family.example.ts.net',
                                          headers={'Cookie': child_cookie})
                    self.assertEqual(status, 401)
                    self.assertNotIn(b'"token"', body)

                    # A malformed or unsafe access record fails closed.
                    if os.name != 'nt':
                        access_path.chmod(0o644)
                        self.assertEqual(get(host='family.example.ts.net',
                                             headers={'Authorization': parent_auth})[0], 503)
                        access_path.chmod(0o600)
                    access_path.write_text('{bad json', encoding='utf-8')
                    if os.name != 'nt': access_path.chmod(0o600)
                    self.assertEqual(get(host='family.example.ts.net',
                                         headers={'Authorization': parent_auth})[0], 503)
                    install_config()

                    self.assertEqual(get(host='family.example.ts.net,localhost')[0], 403)
                    self.assertEqual(raw_status(
                        b'GET /api/state HTTP/1.1\r\n'
                        b'Host: family.example.ts.net\r\nHost: localhost\r\n'
                        b'Connection: close\r\n\r\n'), 403)

                    # Local collector and print bridge retain their loopback Bearer
                    # boundary and never require the family Basic password.
                    self.assertEqual(get('/api/agent/collector', headers={
                        'Authorization': 'Bearer synthetic-print-token'})[0], 200)
                    self.assertEqual(get('/api/print/bridge/unknown', headers={
                        'Authorization': 'Bearer synthetic-print-token'})[0], 404)
                    status, body, _ = get('/api/print/bridge/unknown', headers={
                        'Authorization': 'Bearer wrong'})
                    self.assertEqual(status, 403)
                    self.assertNotIn(b'"token"', body)
                    status, body, _ = get('/api/print/bridge/unknown', host='family.example.ts.net', headers={
                        'Cookie': cookie_d, 'Authorization': 'Bearer wrong'})
                    self.assertEqual(status, 403)
                    self.assertNotIn(b'"code"', body)
                    self.assertNotIn(b'"token"', body)

                    with patch.object(access, '_login_attempts', [int(access.time.time())] * 10):
                        limited, _, limited_headers = parent_login()
                        self.assertEqual(limited, 429)
                        self.assertEqual(limited_headers.get('Retry-After'), '60')

                    # Login and logout reject unsafe origins, markers, content types and framing.
                    self.assertIn(parent_login(headers={'Origin': 'https://evil.example.ts.net'})[0], (400, 403, 415))
                    self.assertIn(parent_login(headers={'X-Family-Login': ''})[0], (400, 403, 415))
                    self.assertIn(parent_login(headers={'Content-Type': 'text/plain'})[0], (400, 403, 415))
                    self.assertIn(raw_status(
                        b'POST /api/parent/login HTTP/1.1\r\n'
                        b'Host: family.example.ts.net\r\n'
                        b'Content-Type: application/json\r\nX-Family-Login: 1\r\n'
                        b'Origin: https://family.example.ts.net\r\n'
                        b'Content-Length: 2\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}'), (400, 411))
                    self.assertIn(raw_status(
                        b'POST /api/parent/login HTTP/1.1\r\n'
                        b'Host: family.example.ts.net\r\nTransfer-Encoding: chunked\r\n'
                        b'Content-Type: application/json\r\nX-Family-Login: 1\r\n'
                        b'Origin: https://family.example.ts.net\r\nConnection: close\r\n\r\n0\r\n\r\n'), (400, 411))
                    self.assertIn(raw_status(
                        b'POST /api/parent/login HTTP/1.1\r\n'
                        b'Host: family.example.ts.net\r\nContent-Type: application/json\r\n'
                        b'X-Family-Login: 1\r\nOrigin: https://family.example.ts.net\r\n'
                        b'Content-Length: 7\r\nConnection: close\r\n\r\nnot-json'), (400, 415))
                    overlong = b'{' + b'a' * 20000 + b'}'
                    self.assertIn(raw_status(
                        b'POST /api/parent/login HTTP/1.1\r\n'
                        b'Host: family.example.ts.net\r\nContent-Type: application/json\r\n'
                        b'X-Family-Login: 1\r\nOrigin: https://family.example.ts.net\r\n'
                        + ('Content-Length: %d\r\n' % len(overlong)).encode() +
                        b'Connection: close\r\n\r\n' + overlong), (400, 413))
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
                app.ROOT, app.DATA, app.DB = old


if __name__ == '__main__': unittest.main()
