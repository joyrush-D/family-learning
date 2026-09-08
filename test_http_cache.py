"""python3 test_http_cache.py: synthetic HTTP cache and fresh-data checks."""
import gzip
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

import app


def check():
    with tempfile.TemporaryDirectory(prefix='synthetic-http-cache-') as folder:
        root = Path(folder)
        data = root / 'private'
        data.mkdir()
        files = ('index.html', 'app.js', 'reading.js', 'calendar.js', 'child-access.js',
                 'learning.js', 'study.js', 'settings.js', 'guided.js', 'startup.js', 'ui.css', 'learning.css', 'study.css', 'growth-world.js',
                 'vendor/three.module.min.js', 'vendor/three.core.min.js',
                 'child.html', 'child.js', 'child.css')
        for name in files:
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes((('/* synthetic ' + name + ' */\n') * 200).encode())
        (root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        (root / '跟踪台账.md').write_text('| T01 | 示例甲 | 虚构阅读 | 无截止 | 待跟进 | 示例来源 | 一起读 |\n')
        (data / 'attachments').mkdir()
        (data / 'attachments' / 'example.txt').write_bytes(b'synthetic private original')
        with patch.multiple(app, ROOT=root, DATA=data, DB=data / 'family.sqlite3'), patch.dict(os.environ, {
                'FAMILY_HOST': 'family.example.invalid', 'FAMILY_USER': 'parent@example.invalid'}):
            app.prepare_assets()
            server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def request(path, headers=None, obj=None):
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    body = json.dumps(obj).encode() if obj is not None else None
                    conn.request('POST' if obj is not None else 'GET', path, body, headers or {})
                    response = conn.getresponse()
                    return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
                finally:
                    conn.close()

            try:
                etag = ''
                for path, name in (('/ui.css', 'ui.css'), ('/child/child.js', 'child.js')):
                    original = (root / name).read_bytes()
                    status, headers, body = request(path, {'Accept-Encoding': 'gzip'})
                    assert status == 200 and headers['content-encoding'] == 'gzip'
                    assert gzip.decompress(body) == original and len(body) < len(original)
                    assert headers['cache-control'] == 'private, no-cache'
                    assert headers['vary'].lower() == 'accept-encoding'
                    assert headers['x-content-type-options'] == 'nosniff'
                    assert headers['x-frame-options'] == 'DENY'
                    csp = headers['content-security-policy']
                    assert "frame-ancestors 'none'" in csp
                    assert ("'unsafe-inline'" not in csp) if path.startswith('/child/') else ("'unsafe-inline'" in csp)
                    etag = headers['etag']
                    assert etag.startswith('W/"') and etag.endswith('"')
                    for accept in ('gzip;q=0', 'gzip;q=0, *;q=1', 'gzip ; q=0, *;q=1'):
                        status, plain, body = request(path, {'Accept-Encoding': accept})
                        assert status == 200 and 'content-encoding' not in plain and body == original
                        assert plain['etag'] == etag
                    status, unchanged, body = request(path, {'Accept-Encoding': 'gzip', 'If-None-Match': etag})
                    assert status == 304 and body == b'' and 'content-length' not in unchanged
                    assert unchanged['etag'] == etag and unchanged['cache-control'] == 'private, no-cache'
                    assert unchanged['content-security-policy'] == csp

                status, _, body = request('/app.bundle.js', {'Accept-Encoding': 'gzip'})
                names = ('app.js', 'reading.js', 'calendar.js', 'child-access.js', 'learning.js', 'study.js', 'settings.js', 'guided.js')
                expected = b'(()=>{\n' + b'\n;\n'.join((root / name).read_bytes() for name in names) + b'\n})();\n'
                assert status == 200 and gzip.decompress(body) == expected

                status, before, _ = request('/ui.css')
                replacement = root / 'replacement.css'
                replacement.write_bytes(b'/* replaced synthetic stylesheet */' * 100)
                replacement.replace(root / 'ui.css')
                status, after, body = request('/ui.css', {'If-None-Match': before['etag']})
                assert status == 200 and after['etag'] != before['etag'] and body == (root / 'ui.css').read_bytes()
                other = root / 'other-root'
                other.mkdir()
                (other / 'ui.css').write_bytes(b'other synthetic installation')
                with patch.object(app, 'ROOT', other):
                    status, _, body = request('/ui.css', {'If-None-Match': after['etag']})
                    assert status == 200 and body == b'other synthetic installation'

                for path in ('/ui.css', '/child/child.js', '/api/state'):
                    status, denied, _ = request(path, {'Host': 'untrusted.example.invalid', 'If-None-Match': etag})
                    assert status == 403 and denied['cache-control'] == 'no-store'
                status, denied, _ = request('/child/api/state', {'If-None-Match': etag})
                assert status == 401 and denied['cache-control'] == 'no-store'

                status, private, body = request('/api/state', {'If-None-Match': etag})
                state = json.loads(body)
                assert status == 200 and private['cache-control'] == 'no-store' and not state['records']
                status, packed, body = request('/api/state', {'Accept-Encoding': 'gzip'})
                assert status == 200 and packed['cache-control'] == 'no-store' and 'etag' not in packed
                assert packed['content-encoding'] == 'gzip' and json.loads(gzip.decompress(body)) == state
                status, plain, body = request('/api/state', {'Accept-Encoding': 'gzip;q=0'})
                assert status == 200 and 'content-encoding' not in plain and json.loads(body) == state
                status, saved, _ = request('/api/record', {'X-Family-Token': state['token']},
                    dict(child='示例甲', day='2026-09-08', category='家长观察', title='虚构的新记录', note='只用于检查'))
                assert status == 200 and saved['cache-control'] == 'no-store'
                status, _, body = request('/api/state', {'If-None-Match': etag})
                assert status == 200 and json.loads(body)['records'][0]['title'] == '虚构的新记录'
                status, packed, body = request('/api/state', {'Accept-Encoding': 'gzip'})
                assert packed['cache-control'] == 'no-store' and json.loads(gzip.decompress(body))['records'][0]['title'] == '虚构的新记录'
                (root / '跟踪台账.md').write_text('| T02 | 示例甲 | 外部更新的虚构事项 | 无截止 | 待跟进 | 示例来源 | 一起读 |\n')
                status, _, body = request('/api/state')
                assert status == 200 and [task['id'] for task in json.loads(body)['tasks']] == ['T02']
                status, private, body = request('/attachment/example.txt', {'If-None-Match': etag, 'Accept-Encoding': 'gzip'})
                assert status == 200 and private['cache-control'] == 'no-store'
                assert 'etag' not in private and 'content-encoding' not in private and body == b'synthetic private original'
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
    print('HTTP cache, access boundaries and immediate data freshness: OK')


if __name__ == '__main__':
    check()
