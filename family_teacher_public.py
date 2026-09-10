"""Weekly checks of explicitly configured public teaching pages; no model calls."""
import datetime as dt
import json
import http.client
import ipaddress
import re
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

TZ = dt.timezone(dt.timedelta(hours=8))
INTERVAL = dt.timedelta(days=7)
MAX_BYTES = 512 * 1024


def validate_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('公开资料链接格式不正确')
    value = value.strip()
    if not value:
        return ''
    try:
        url = urlsplit(value)
        host = (url.hostname or '').encode('idna').decode('ascii').lower()
        if (url.scheme != 'https' or url.username is not None or url.password is not None
                or url.fragment or url.port not in (None, 443) or '.' not in host
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host)
                or any(ord(c) <= 32 or ord(c) == 127 for c in value)
                or host.endswith(('.local', '.localhost', '.internal'))):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
        return urlunsplit(('https', host, url.path or '/', url.query, ''))
    except (ValueError, UnicodeError):
        raise ValueError('请填写无账号信息的公开 HTTPS 网页链接') from None


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocked = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'template'):
            self.blocked += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'template'):
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, data):
        if not self.blocked and data.strip():
            self.parts.append(data.strip())


def fetch_text(value):
    url = urlsplit(validate_url(value))
    deadline = time.monotonic() + 10
    addresses = socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
    ips = [item[4][0] for item in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast
                      for ip in ips):
        raise ValueError('公开链接不能访问本机或内网')

    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError()
        return left

    # Pin the checked address while retaining the original host for TLS and HTTP.
    # DNS/OS calls use cooperative deadlines, not an OS hard real-time guarantee.
    connection = http.client.HTTPSConnection(url.hostname, timeout=remaining())
    raw_socket = socket.create_connection((ips[0], 443), timeout=remaining())
    try:
        raw_socket.settimeout(remaining())
        tls_socket = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=url.hostname)
        connection.sock = tls_socket
        connection.sock.settimeout(remaining())
        connection.request('GET', url.path + ('?' + url.query if url.query else ''),
                           headers={'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity',
                                    'User-Agent': 'FamilyLearning/0.1 public-teaching-page-check'})
        response = connection.getresponse()
        if response.status != 200:  # Never follow redirects to an unchecked address.
            raise ValueError('公开页面未返回可读取内容')
        if response.getheader('Content-Encoding', 'identity').lower() not in ('identity', ''):
            raise ValueError('公开页面编码暂不支持')
        content_type = response.headers.get_content_type()
        if content_type not in ('text/html', 'text/plain'):
            raise ValueError('请使用公开文字网页链接')
        content = bytearray()
        while True:
            tls_socket.settimeout(remaining())
            chunk = response.read1(min(16384, MAX_BYTES + 1 - len(content)))
            remaining()
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise ValueError('公开页面过大，未保存')
        text = content.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        if content_type == 'text/html':
            parser = PageText(); parser.feed(text); text = '\n'.join(parser.parts)
        text = re.sub(r'[ \t]+', ' ', text).strip()
        if not text:
            raise ValueError('公开页面没有可读取文字')
        # ponytail: compare the first 6000 readable characters; full-page diffs need a real use case.
        return text[:6000]
    finally:
        connection.close()
        raw_socket.close()


def init(c):
    c.execute('''CREATE TABLE IF NOT EXISTS teacher_public_pages (
        teacher_id TEXT PRIMARY KEY, url TEXT NOT NULL, last_attempt TEXT NOT NULL,
        last_success TEXT NOT NULL DEFAULT '', changed_at TEXT NOT NULL DEFAULT '',
        text TEXT NOT NULL DEFAULT '', previous_text TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '')''')


def snapshot(c, teacher_id, public_url):
    row = c.execute('SELECT * FROM teacher_public_pages WHERE teacher_id=? AND url=?',
                    (teacher_id, public_url)).fetchone()
    result = dict(url=public_url, status='pending' if public_url else 'unconfigured',
                  last_attempt='', last_success='', changed_at='', text='', previous_text='', error='', next_check_at='')
    if row:
        result.update({key: row[key] for key in result if key in row.keys()})
        result['status'] = 'error' if row['error'] else 'changed' if row['changed_at'] else 'checked'
        result['next_check_at'] = (dt.datetime.fromisoformat(row['last_attempt']) + INTERVAL).isoformat()
    return result


def run_one(app, now=None, fetch=fetch_text):
    now = now or dt.datetime.now(TZ)
    with app.connect() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='teachers'").fetchone():
            return {'state': 'idle'}
        init(c)
        candidates = []
        for row in c.execute('SELECT id,data FROM teachers'):
            teacher = json.loads(row['data'])
            if teacher['archived'] or not teacher['public_url']:
                continue
            cached = snapshot(c, row['id'], teacher['public_url'])
            last = cached['last_attempt']
            if not last or dt.datetime.fromisoformat(last) + INTERVAL <= now:
                candidates.append(dict(id=row['id'], public_url=teacher['public_url'], last_attempt=last))
        target = min(candidates, key=lambda r: (r['last_attempt'], r['id']), default=None)
        if target is None:
            return {'state': 'idle'}
    error = ''
    try:
        text = fetch(target['public_url'])
        if not isinstance(text, str) or not text.strip() or len(text) > 6000:
            raise ValueError()
    except (OSError, ValueError, http.client.HTTPException, UnicodeError, LookupError):
        text = ''; error = '公开页面暂未读取成功，保留上次资料；七天后再检查。'
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT data FROM teachers WHERE id=?', (target['id'],)).fetchone()
        current = json.loads(row['data']) if row else None
        if current is None or current['archived'] or current['public_url'] != target['public_url']:
            return {'state': 'superseded'}
        old = snapshot(c, target['id'], target['public_url'])
        # The existing Agent lock serializes scheduled checks. Preserve newer results if another caller completed first.
        if old['last_attempt'] and old['last_attempt'] != (target['last_attempt'] or ''):
            return {'state': 'superseded'}
        changed = bool(not error and old['text'] and old['text'] != text)
        success = now.isoformat() if not error else old['last_success']
        changed_at = now.isoformat() if changed else old['changed_at']
        previous = old['text'] if changed else old['previous_text']
        c.execute('''INSERT OR REPLACE INTO teacher_public_pages
            (teacher_id,url,last_attempt,last_success,changed_at,text,previous_text,error) VALUES (?,?,?,?,?,?,?,?)''',
            (target['id'], target['public_url'], now.isoformat(), success, changed_at,
             old['text'] if error else text, previous, error))
    return {'state': 'error' if error else 'changed' if changed else 'checked', 'teacher_id': target['id']}
