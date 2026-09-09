"""Small, local parent BasicAuth configuration for an HTTPS Tailscale entrypoint."""
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


def _authorization_values(headers):
    try:
        if hasattr(headers, 'get_all'):
            values = headers.get_all('Authorization') or []
        elif hasattr(headers, 'getheaders'):
            values = headers.getheaders('Authorization') or []
        else:
            values = []
            for key, value in headers.items():
                if str(key).lower() == 'authorization':
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
    values = _authorization_values(headers)
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
