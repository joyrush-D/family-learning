"""Parent HTTPS login and sessions; Basic credentials also serve calendar clients."""
import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from urllib.parse import urlsplit


ITERATIONS = 600000
CONFIG_KEYS = {'base_url', 'username', 'salt', 'password_hash'}
MAX_CONFIG_BYTES = 16384
_HOST_LABEL = r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?'
_HOST = re.compile(r'^(?:' + _HOST_LABEL + r'\.)+' + _HOST_LABEL + r'$', re.ASCII)
_PATH = re.compile(r'^/(?:[A-Za-z0-9._~-]+/)*[A-Za-z0-9._~-]+/?$', re.ASCII)
_USERNAME = re.compile(r'^[\x21-\x7e]+$', re.ASCII)
_BASIC = re.compile(r'^Basic ([A-Za-z0-9+/]+={0,2})$', re.ASCII | re.IGNORECASE)
_success_cache = None
COOKIE = 'family_parent_session'
SESSION_AGE = 180 * 24 * 60 * 60  # Parent devices: 180 days from login.
_login_attempts = []
_login_lock = threading.Lock()


class AccessError(ValueError):
    """Safe configuration or authentication input error."""


def _safe_text(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit and
            not any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value))


def validate_base_url(value):
    if not _safe_text(value, 512) or any(char.isspace() for char in value) or '?' in value or '#' in value:
        raise AccessError('访问配置不正确')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise AccessError('访问配置不正确') from None
    host = parsed.hostname
    if (parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None or
            parsed.query or parsed.fragment or port is not None and not 1 <= port <= 65535 or
            host.lower() in {'localhost', 'localhost.localdomain'}):
        raise AccessError('访问配置不正确')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise AccessError('访问配置不正确')
    if len(host) > 253 or not _HOST.fullmatch(host):
        raise AccessError('访问配置不正确')
    if (parsed.path not in ('', '/') and
            (not _PATH.fullmatch(parsed.path) or any(segment in ('.', '..') for segment in parsed.path.split('/')))):
        raise AccessError('访问配置不正确')
    return value


def _validate_config(config):
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise AccessError('访问配置不正确')
    if not all(isinstance(config[key], str) for key in CONFIG_KEYS):
        raise AccessError('访问配置不正确')
    validate_base_url(config['base_url'])
    if (not _USERNAME.fullmatch(config['username']) or ':' in config['username'] or
            len(config['username']) > 64):
        raise AccessError('访问配置不正确')
    if not re.fullmatch(r'[0-9a-f]{32}', config['salt']) or not re.fullmatch(r'[0-9a-f]{64}', config['password_hash']):
        raise AccessError('访问配置不正确')
    return config


def _password(value):
    if not isinstance(value, str) or not 16 <= len(value) <= 200 or not all(
            ord(char) >= 32 and not 127 <= ord(char) <= 159 for char in value):
        raise AccessError('访问口令不符合要求')
    return value


def make_config(base_url, username, password):
    """Validate installer inputs and return a private, hashed credential record."""
    base_url = validate_base_url(base_url)
    if not isinstance(username, str) or not _USERNAME.fullmatch(username) or ':' in username or len(username) > 64:
        raise AccessError('访问配置不正确')
    password = _password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), ITERATIONS).hex()
    return dict(base_url=base_url, username=username, salt=salt, password_hash=digest)


def read_config(data_path):
    path = Path(data_path) / 'access.json'
    if not path.exists():
        if path.is_symlink():
            raise AccessError('访问配置不正确')
        return None
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CONFIG_BYTES:
            raise AccessError('访问配置不正确')
        if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise AccessError('访问配置权限不正确')
        config = json.loads(path.read_text(encoding='utf-8'))
    except AccessError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError):
        raise AccessError('访问配置不正确') from None
    return _validate_config(config)


def _header_values(headers, name):
    try:
        if hasattr(headers, 'get_all'):
            values = headers.get_all(name) or []
        elif hasattr(headers, 'getheaders'):
            values = headers.getheaders(name) or []
        else:
            values = []
            for key, value in headers.items():
                if str(key).lower() == name.lower():
                    values.extend(value if isinstance(value, (list, tuple)) else [value])
    except (AttributeError, TypeError):
        return []
    return values if isinstance(values, list) else list(values)


def authorized(headers, config):
    """Return whether exactly one valid Basic credential authorizes this request."""
    global _success_cache
    if not isinstance(config, dict):
        return False
    _validate_config(config)
    values = _header_values(headers, 'Authorization')
    if len(values) != 1 or not isinstance(values[0], str) or len(values[0]) > 4096:
        return False
    header = values[0]
    match = _BASIC.fullmatch(header)
    if not match:
        return False
    try:
        raw = base64.b64decode(match.group(1), validate=True)
        credentials = raw.decode('utf-8')
    except (binascii.Error, UnicodeError, ValueError):
        return False
    if ':' not in credentials:
        return False
    username, password = credentials.split(':', 1)
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    cache_key = hashlib.sha256(canonical + b'\x00' + header.encode('utf-8')).hexdigest()
    if _success_cache is not None and hmac.compare_digest(_success_cache, cache_key):
        return True
    try:
        candidate_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                             bytes.fromhex(config['salt']), ITERATIONS).hex()
    except (UnicodeError, ValueError):
        return False
    candidate = (username + ':' + candidate_hash).encode('utf-8', 'surrogatepass')
    expected = (config['username'] + ':' + config['password_hash']).encode('utf-8')
    if not hmac.compare_digest(candidate, expected):
        return False
    _success_cache = cache_key
    return True


def _fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _cookies(headers):
    values = _header_values(headers, 'Cookie')
    if not values:
        return []
    if len(values) != 1 or not isinstance(values[0], str) or len(values[0]) > 8192:
        return ['invalid']
    raw = values[0]
    return [part.strip().split('=', 1)[1] for part in raw.split(';')
            if part.strip().startswith(COOKIE + '=')]


def has_session_cookie(headers):
    return bool(_cookies(headers))


def _secret(headers):
    values = _cookies(headers)
    return values[0] if len(values) == 1 and re.fullmatch(r'[A-Za-z0-9_-]{43}', values[0]) else ''


def _digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


@contextmanager
def _sessions(connect):
    with closing(connect()) as c:
        with c:
            c.execute('CREATE TABLE IF NOT EXISTS parent_sessions (hash TEXT PRIMARY KEY, expires INTEGER NOT NULL, config_hash TEXT NOT NULL)')
            yield c


def session_authorized(headers, config, connect):
    secret = _secret(headers)
    if not secret:
        return False
    with _sessions(connect) as c:
        return c.execute('SELECT 1 FROM parent_sessions WHERE hash=? AND expires>? AND config_hash=?',
                         (_digest(secret), int(time.time()), _fingerprint(config))).fetchone() is not None


def _path(config):
    return urlsplit(config['base_url']).path.rstrip('/') + '/'


def _cookie(config, secret):
    return (COOKIE + '=' + secret + '; Path=' + _path(config) + '; Max-Age=' + str(SESSION_AGE)
            + '; Secure; HttpOnly; SameSite=Lax')


def dispatch(handler, config, connect, root):
    """Handle only the public login surface after the caller has validated Host."""
    path = urlsplit(handler.path).path
    if path not in ('/login', '/login.js', '/api/parent/login', '/api/parent/logout'):
        return False
    handler.close_connection = True
    def reply(status, body, kind='application/json; charset=utf-8', headers=None):
        handler.reply(status, body, kind, headers={'Referrer-Policy': 'no-referrer', **(headers or {})})
    try:
        if path in ('/login', '/login.js'):
            if handler.command != 'GET':
                reply(405, {'error': '请打开登录页面'}); return True
            if path == '/login' and session_authorized(handler.headers, config, connect):
                reply(303, b'', headers={'Location': _path(config)}); return True
            name, kind = ('login.html', 'text/html') if path == '/login' else ('login.js', 'text/javascript')
            reply(200, (Path(root) / name).read_bytes(), kind + '; charset=utf-8'); return True
        if handler.command != 'POST':
            reply(405, {'error': '请使用登录页面提交'}); return True
        parsed = urlsplit(config['base_url'])
        origin = 'https://' + parsed.hostname + (':' + str(parsed.port) if parsed.port not in (None, 443) else '')
        origins = handler.headers.get_all('Origin', [])
        proto = handler.headers.get_all('X-Forwarded-Proto', [])
        if (origins != [origin]
                or proto not in ([], ['https']) or handler.headers.get_all('X-Family-Login', []) != ['1']):
            reply(403, {'error': '请从家庭 HTTPS 入口登录'}); return True
        lengths = handler.headers.get_all('Content-Length', [])
        if (handler.headers.get('Transfer-Encoding') or len(lengths) != 1
                or not re.fullmatch(r'[0-9]{1,5}', lengths[0])
                or not 0 < int(lengths[0]) <= 4096
                or handler.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json'):
            reply(400, {'error': '请使用登录页面提交'}); return True
        handler.connection.settimeout(10)
        raw = handler.rfile.read(int(lengths[0]))
        if len(raw) != int(lengths[0]):
            raise ValueError()
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError()
        if path == '/api/parent/logout':
            if obj:
                raise ValueError()
            with _sessions(connect) as c:
                c.execute('DELETE FROM parent_sessions WHERE hash=?', (_digest(_secret(handler.headers)),))
            # Keep a non-secret marker so a browser's cached Basic header cannot log it back in.
            reply(200, {'ok': True}, headers={'Set-Cookie': _cookie(config, 'logged-out')}); return True
        if set(obj) != {'username', 'password'} or not all(isinstance(value, str) for value in obj.values()):
            raise ValueError()
        if not 0 < len(obj['username']) <= 64 or not 0 < len(obj['password']) <= 200:
            raise ValueError()
        now = int(time.time())
        # ponytail: one family login budget per process; use a shared limiter only with multiple web workers.
        with _login_lock:
            _login_attempts[:] = [stamp for stamp in _login_attempts if stamp > now - 60]
            if len(_login_attempts) >= 10:
                reply(429, {'error': '尝试过于频繁，请一分钟后再试'}, headers={'Retry-After': '60'}); return True
            _login_attempts.append(now)
        header = 'Basic ' + base64.b64encode((obj['username'] + ':' + obj['password']).encode()).decode()
        if not authorized({'Authorization': header}, config):
            reply(401, {'error': '账号或密码不正确'}); return True
        secret = secrets.token_urlsafe(32)
        with _sessions(connect) as c:
            c.execute('DELETE FROM parent_sessions WHERE expires<=? OR config_hash<>?', (now, _fingerprint(config)))
            c.execute('DELETE FROM parent_sessions WHERE hash=?', (_digest(_secret(handler.headers)),))
            c.execute('INSERT INTO parent_sessions VALUES (?,?,?)', (_digest(secret), now + SESSION_AGE, _fingerprint(config)))
            c.execute('DELETE FROM parent_sessions WHERE hash NOT IN (SELECT hash FROM parent_sessions ORDER BY expires DESC, rowid DESC LIMIT 32)')
        reply(200, {'ok': True}, headers={'Set-Cookie': _cookie(config, secret)})
    except (OSError, sqlite3.Error):
        reply(503, {'error': '登录暂未完成，请稍后重试'})
    except (ValueError, TypeError, UnicodeError):
        reply(400, {'error': '登录信息格式不正确'})
    return True
