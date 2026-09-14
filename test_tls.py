"""Home-network HTTPS: family certificate issuing and the application's own TLS listener.

Synthetic data only: temporary directories, a fictional child and disposable certificates.
Uses the system openssl CLI; no network beyond loopback and no real device.
"""
import base64
import http.client
import json
import os
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import family_tls

ROOT = Path(__file__).resolve().parent


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name).resolve() / 'private'  # macOS temp dirs sit behind a /var symlink
        self.data.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_only_home_network_hosts_are_accepted(self):
        self.assertEqual(family_tls.validate_hosts(['192.168.50.2', 'Family-Mac.local', '192.168.50.2', '10.0.0.7', '172.31.1.1']),
                         ['192.168.50.2', 'family-mac.local', '10.0.0.7', '172.31.1.1'])
        for hosts in ([], ['8.8.8.8'], ['127.0.0.1'], ['localhost'], ['family.example.com'], ['172.32.0.1'],
                      ['169.254.1.1'], ['::1'], ['-bad.local'], ['a.local.evil'], ['192.168.1.%d' % n for n in range(9)], 'not-a-list'):
            with self.subTest(hosts=hosts):
                with self.assertRaises(family_tls.TLSError):
                    family_tls.validate_hosts(hosts)

    def test_issue_status_reissue_and_private_permissions(self):
        self.assertEqual(family_tls.status(self.data)['issued'], False)
        self.assertIsNone(family_tls.ca_certificate(self.data))
        with self.assertRaises(family_tls.TLSError):
            family_tls.server_context(self.data)
        result = family_tls.issue(self.data, ['192.168.50.2', 'family-mac.local'])
        self.assertTrue(result['created_ca'] and result['issued'])
        self.assertEqual(result['hosts'], ['192.168.50.2', 'family-mac.local'])
        self.assertRegex(result['ca_sha256'], r'^[0-9a-f]{64}$')
        paths = family_tls.paths(self.data)
        self.assertEqual(stat.S_IMODE(paths['ca.key'].parent.stat().st_mode), 0o700)
        for path in paths.values():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path)
        self.assertTrue(family_tls.covers(self.data, '192.168.50.2') and family_tls.covers(self.data, 'Family-Mac.local'))
        self.assertFalse(family_tls.covers(self.data, '192.168.50.3'))
        ca_before, server_before = paths['ca.crt'].read_bytes(), paths['server.crt'].read_bytes()
        self.assertEqual(family_tls.ca_certificate(self.data), ca_before)
        self.assertIn(b'BEGIN CERTIFICATE', ca_before)
        renewed = family_tls.issue(self.data, ['192.168.50.3'])
        self.assertFalse(renewed['created_ca'])
        self.assertEqual(paths['ca.crt'].read_bytes(), ca_before, 'renewal keeps the CA phones already trust')
        self.assertNotEqual(paths['server.crt'].read_bytes(), server_before)
        self.assertEqual(family_tls.status(self.data)['hosts'], ['192.168.50.3'])
        # Apple limits leaf validity; the CA lasts longer so phones are trusted once.
        text = subprocess.run(['openssl', 'x509', '-in', str(paths['server.crt']), '-noout', '-text'], capture_output=True, check=True).stdout.decode()
        self.assertIn('TLS Web Server Authentication', text)
        self.assertIn('IP Address:192.168.50.3', text)
        self.assertIn('CA:FALSE', text)
        ca_text = subprocess.run(['openssl', 'x509', '-in', str(paths['ca.crt']), '-noout', '-text'], capture_output=True, check=True).stdout.decode()
        self.assertIn('CA:TRUE', ca_text)
        context = family_tls.server_context(self.data)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        paths['server.key'].chmod(0o644)
        with self.assertRaises(family_tls.TLSError):
            family_tls.server_context(self.data)
        paths['server.key'].chmod(0o600)
        paths['ca.crt'].unlink()
        with self.assertRaises(family_tls.TLSError):
            family_tls.issue(self.data, ['192.168.50.2'])
        self.assertEqual(paths['server.crt'].read_bytes(), family_tls.paths(self.data)['server.crt'].read_bytes(), 'a broken CA directory changes nothing')
        paths['ca.key'].unlink()
        family_tls.issue(self.data, ['192.168.50.2'])
        self.assertNotEqual(paths['ca.crt'].read_bytes(), ca_before, 'without a CA a new one is created')
        paths['server.crt'].unlink()
        paths['server.crt'].symlink_to(paths['ca.crt'])
        with self.assertRaises(family_tls.TLSError):
            family_tls.issue(self.data, ['192.168.50.2'])
        with patch.object(family_tls.shutil, 'which', return_value=None), patch.object(family_tls.os, 'access', return_value=False):
            with self.assertRaises(family_tls.TLSError):
                family_tls.openssl_binary()

    def test_python_client_verifies_the_family_ca_and_hostnames(self):
        family_tls.issue(self.data, ['192.168.50.2', 'family-mac.local'])
        server = family_tls.server_context(self.data)
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(4)
        port = listener.getsockname()[1]

        def serve():
            for _ in range(3):
                connection, _ = listener.accept()
                try:
                    with server.wrap_socket(connection, server_side=True) as secure:
                        secure.sendall(secure.recv(16))
                except (OSError, ssl.SSLError):
                    connection.close()
        threading.Thread(target=serve, daemon=True).start()
        client = ssl.create_default_context(cafile=str(family_tls.paths(self.data)['ca.crt']))
        for name in ('192.168.50.2', 'family-mac.local'):
            with client.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5), server_hostname=name) as secure:
                secure.sendall(b'ping')
                self.assertEqual(secure.recv(16), b'ping')
        with self.assertRaises(ssl.SSLCertVerificationError):
            client.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5), server_hostname='other.local')
        listener.close()

    def test_cli_issue_and_status(self):
        cli = [sys.executable, str(ROOT / 'family_tls.py'), '--data', str(self.data)]
        missing = subprocess.run([*cli, 'status'], capture_output=True, text=True)
        self.assertEqual(missing.returncode, 1)
        self.assertIn('尚未签发', missing.stdout)
        rejected = subprocess.run([*cli, 'issue', '--host', '8.8.8.8'], capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 1)
        self.assertFalse((self.data / 'tls').exists() and any((self.data / 'tls').iterdir()))
        issued = subprocess.run([*cli, 'issue', '--host', '192.168.50.2', '--host', 'Family-Mac.local'], capture_output=True, text=True)
        self.assertEqual(issued.returncode, 0, issued.stderr)
        self.assertIn('192.168.50.2、family-mac.local', issued.stdout)
        self.assertIn('/family-ca.crt', issued.stdout)
        shown = subprocess.run([*cli, 'status'], capture_output=True, text=True)
        self.assertEqual(shown.returncode, 0)
        self.assertIn(family_tls.status(self.data)['ca_sha256'], shown.stdout)


class ApplicationListenerTests(unittest.TestCase):
    """The real Handler behind the app's own TLS listener, with loopback HTTP still serving local tools."""
    HOST = 'family-mac.local'
    PASSWORD = 'synthetic-lan-https-password-123'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve() / 'app'
        self.data = root / 'private'
        root.mkdir()
        self.data.mkdir()
        (root / '家庭运行规则.md').write_text('| child-1 | 示例孩子 | 未填写 | 未填写 | 四年级 |\n', encoding='utf-8')
        for name in ('消息来源.md', '跟踪台账.md', '学习与成长.md'):
            (root / name).write_text('# 虚构测试资料\n', encoding='utf-8')
        for name, content in (('index.html', '<!doctype html><title>虚构家庭</title>'), ('login.html', '<!doctype html><title>虚构登录</title>'),
                              ('login.js', 'document.title="synthetic";'), ('child.html', 'child'), ('child.js', 'child'), ('child.css', 'child')):
            (root / name).write_text(content, encoding='utf-8')
        self.environment = patch.dict(os.environ, {'FAMILY_DATA': str(self.data)}, clear=True)
        self.environment.start()
        import app
        import family_access
        self.app, self.access = app, family_access
        self.saved = app.ROOT, app.DATA, app.DB
        app.ROOT, app.DATA, app.DB = root, self.data, self.data / 'family.sqlite3'
        app.connect().close()
        family_tls.issue(self.data, [self.HOST, '192.168.50.2'])
        self.secure = app.TLSServer(('127.0.0.1', 0), app.Handler, family_tls.server_context(self.data))
        self.plain = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        for server in (self.secure, self.plain):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.base_url = 'https://%s:%d' % (self.HOST, self.secure.server_port)
        config = family_access.make_config(self.base_url, 'parent', self.PASSWORD)
        (self.data / 'access.json').write_text(json.dumps(config))
        (self.data / 'access.json').chmod(0o600)
        self.client = ssl.create_default_context(cafile=str(family_tls.paths(self.data)['ca.crt']))

    def tearDown(self):
        for server in (self.secure, self.plain):
            server.shutdown()
            server.server_close()
        self.app.ROOT, self.app.DATA, self.app.DB = self.saved
        self.environment.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None, *, secure=True, host=None):
        values = {'Host': host or ('%s:%d' % (self.HOST, self.secure.server_port) if secure else '127.0.0.1')}
        values.update(headers or {})
        if body is not None:
            body = json.dumps(body).encode()
            values.setdefault('Content-Type', 'application/json')
        port = self.secure.server_port if secure else self.plain.server_port
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        if secure:
            connection.sock = self.client.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5), server_hostname=self.HOST)
        connection.request(method, path, body, values)
        reply = connection.getresponse()
        payload = reply.read()
        connection.close()
        return reply.status, payload, {key.lower(): value for key, value in reply.getheaders()}

    def test_tls_listener_authenticates_like_the_lan_entry_and_serves_the_ca(self):
        status, _, headers = self.request('GET', '/', headers={'Accept': 'text/html'})
        self.assertEqual((status, headers['location']), (303, '/login'))
        self.assertEqual(self.request('GET', '/login')[0], 200)
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        status, payload, headers = self.request('GET', '/family-ca.crt')
        self.assertEqual(status, 200)
        self.assertEqual(payload, family_tls.ca_certificate(self.data))
        self.assertEqual(headers['content-type'], 'application/x-x509-ca-cert')
        self.assertIn('attachment', headers['content-disposition'])
        self.assertEqual(headers['cache-control'], 'no-store')
        self.assertEqual(self.request('GET', '/family-ca.crt', secure=False)[0], 200, 'the Mac itself can fetch the CA to share it with a phone')
        self.assertEqual(self.request('GET', '/family-ca.crt', headers={'X-Forwarded-For': '203.0.113.9'})[0], 403)
        self.assertEqual(self.request('GET', '/', host='evil.invalid')[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'X-Forwarded-Proto': 'https'})[0], 403)
        login = {'Origin': self.base_url, 'X-Family-Login': '1'}
        self.assertEqual(self.request('POST', '/api/parent/login', {'username': 'parent', 'password': 'wrong-password-123456'}, login)[0], 401)
        self.assertEqual(self.request('POST', '/api/parent/login', {'username': 'parent', 'password': self.PASSWORD},
                                      {'Origin': 'http://%s:%d' % (self.HOST, self.secure.server_port), 'X-Family-Login': '1'})[0], 403)
        status, _, headers = self.request('POST', '/api/parent/login', {'username': 'parent', 'password': self.PASSWORD}, login)
        self.assertEqual(status, 200)
        self.assertIn('; Secure;', headers['set-cookie'])
        cookie = headers['set-cookie'].split(';', 1)[0]
        status, payload, _ = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)['children'][0]['name'], '示例孩子')
        basic = 'Basic ' + base64.b64encode(('parent:' + self.PASSWORD).encode()).decode()
        self.assertEqual(self.request('GET', '/calendar.ics', headers={'Authorization': basic})[0], 200, 'phone calendar subscription over the family certificate')
        self.assertEqual(self.request('GET', '/calendar.ics')[0], 401)
        # Loopback HTTP keeps serving the Agent, collector and print bridge without a certificate or login.
        self.assertEqual(self.request('GET', '/api/state', secure=False)[0], 200)
        self.assertEqual(self.request('GET', '/api/state', secure=False, host='%s:%d' % (self.HOST, self.plain.server_port))[0], 401)
        self.assertEqual(self.request('POST', '/api/parent/logout', {}, {**login, 'Cookie': cookie})[0], 200)
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie': cookie})[0], 401)

    def test_plain_or_stalled_clients_do_not_block_the_tls_listener(self):
        port = self.secure.server_port
        with socket.create_connection(('127.0.0.1', port), timeout=5) as plain:
            plain.sendall(b'GET / HTTP/1.1\r\nHost: %s\r\n\r\n' % self.HOST.encode())
            plain.settimeout(5)
            try:
                self.assertEqual(plain.recv(64), b'', 'a plain HTTP request on the TLS port is closed without a reply')
            except ConnectionResetError:
                pass  # The handshake failed and the listener dropped the connection; nothing was served.
        stalled = [socket.create_connection(('127.0.0.1', port), timeout=5) for _ in range(3)]
        try:
            started = time.monotonic()
            self.assertEqual(self.request('GET', '/login')[0], 200)
            self.assertLess(time.monotonic() - started, 5, 'handshakes run per connection, so silent clients cannot stall others')
            untrusting = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            untrusting.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(ssl.PEM_cert_to_DER_cert(_other_ca())))
            with self.assertRaises(ssl.SSLError):
                untrusting.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5), server_hostname=self.HOST)
            self.assertEqual(self.request('GET', '/login')[0], 200)
        finally:
            for item in stalled:
                item.close()

    def test_startup_refuses_missing_certificates_or_a_shared_port(self):
        (self.data / 'tls' / 'server.crt').unlink()
        env = {'FAMILY_DATA': str(self.data), 'PORT': '0', 'PATH': os.environ.get('PATH', '/usr/bin:/bin')}
        missing = subprocess.run([sys.executable, str(ROOT / 'app.py')], cwd=self.app.ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('尚未签发家庭证书', missing.stderr)
        family_tls.issue(self.data, [self.HOST])
        env['PORT'] = str(self.secure.server_port)
        shared = subprocess.run([sys.executable, str(ROOT / 'app.py')], cwd=self.app.ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(shared.returncode, 0)
        self.assertIn('端口须与本机应用端口不同', shared.stderr)


def _other_ca():
    with tempfile.TemporaryDirectory() as other:
        data = Path(other).resolve() / 'private'
        data.mkdir()
        family_tls.issue(data, ['192.168.99.9'])
        return family_tls.ca_certificate(data).decode()


if __name__ == '__main__':
    unittest.main()
