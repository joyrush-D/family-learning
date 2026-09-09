"""Optional, bounded local WeChat image saving inside the existing Agent cycle.

Only the pinned CLI's original V2/WXGF still-image variant is supported. No
key extraction, downloads, OCR, model calls, or changes to message payloads.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from family_collect import source_chat, wechat_env
from family_wechat_media import (MediaError, MAX_BYTES, bounded_process,
                                 decrypt_v2, validate_png, wxgf_first_frame)


# This exact build was checked for WX_KEY_BIN=/usr/bin/false failing closed.
# A different build needs that check before changing this pin.
CLI_SHA256 = 'f39d2c714f11ad80d3cdd59b9b68cecc0e24bcb52bcf4615d77a67783fd032ee'


def require(condition, code):
    if not condition:
        raise MediaError(code)


def read_file(path, limit=MAX_BYTES, private=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path, 'media_path_rejected')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as f:
        info = os.fstat(f.fileno())
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit
                and (not private or stat.S_IMODE(info.st_mode) == 0o600), 'media_file_rejected')
        data = f.read(limit + 1)
    require(len(data) == info.st_size, 'media_file_changed')
    return data


def config(data):
    path = Path(data) / 'media.json'
    if not path.exists():
        return None
    value = json.loads(read_file(path, 8192, private=True))
    require(isinstance(value, dict) and set(value) == {'wechat_cli', 'wechat_config', 'wechat_config_sha256', 'ffmpeg', 'since'}, 'media_config_invalid')
    require(isinstance(value['wechat_config_sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', value['wechat_config_sha256']) is not None, 'media_config_invalid')
    for key in ('wechat_cli', 'wechat_config', 'ffmpeg'):
        require(isinstance(value[key], str) and Path(value[key]).is_absolute(), 'media_config_invalid')
    since = dt.datetime.fromisoformat(value['since'])
    require(since.tzinfo is not None, 'media_config_invalid')
    value['since'] = since
    return value


def fetch(settings, source, message):
    """One message's metadata, then a fixed set of paths in its chat directory."""
    chat = source_chat(source)
    require(re.fullmatch(r'[1-9][0-9]{0,31}', message['id']) is not None, 'media_message_invalid')
    cli = Path(settings['wechat_cli']).resolve(strict=True)
    require(hashlib.sha256(read_file(cli, 200 * 1024 * 1024)).hexdigest() == CLI_SHA256, 'media_cli_unverified')
    original_config = read_file(settings['wechat_config'], 2 * 1024 * 1024, private=True)
    require(hashlib.sha256(original_config).hexdigest() == settings['wechat_config_sha256'], 'media_config_changed')
    local = json.loads(original_config)
    key = local.get('image_key')
    require(isinstance(key, str) and len(key.encode()) in (16, 24, 32), 'media_existing_key_required')
    xor = local.get('image_xor_key')
    require(type(xor) is int and 0 <= xor <= 255, 'media_existing_key_required')
    root = Path(local['db_root']) / 'msg' / 'attach'
    require(root.is_absolute() and root.resolve(strict=True) == root, 'media_path_rejected')
    # The CLI's default media locator scans the account-wide temp directory.
    # Disable it; debug keeps resource metadata that the display view hides.
    raw = bounded_process([str(cli), 'media', chat, '--local-id', message['id'], '--type', 'image', '--limit', '1',
                           '--include-local-paths', 'false', '--include-debug', 'true', '--strict-read-only'],
                          wechat_env(settings['wechat_config']), timeout=15, max_stdout=8 * 1024 * 1024)
    require(read_file(settings['wechat_config'], 2 * 1024 * 1024, private=True) == original_config,
            'media_config_changed')
    result = json.loads(raw)
    require(isinstance(result, dict) and result.get('ok') is True, 'media_cli_response_invalid')
    data = result['data']; rows = data['media']; query = data['query']
    require(query.get('chat') == chat and query.get('type') == 'image'
            and isinstance(rows, list) and len(rows) == 1, 'media_cli_response_invalid')
    row = rows[0]; identity = row['id']
    require(identity.get('talker') == chat and type(identity.get('local_id')) is int
            and str(identity['local_id']) == message['id'] and row.get('kind') == 'image', 'media_message_mismatch')
    moment = dt.datetime.fromisoformat(row['time_iso'])
    require(moment.tzinfo is not None and moment == dt.datetime.fromisoformat(message['time']), 'media_message_mismatch')
    candidates = set()
    for resource in row.get('resources', []):
        if resource.get('resource_family') != 'image' or resource.get('variant_code') != 2:
            continue
        md5, size = resource.get('md5'), resource.get('size')
        require(isinstance(md5, str) and re.fullmatch(r'[a-f0-9]{32}', md5) is not None
                and type(size) is int and 0 < size <= MAX_BYTES, 'media_original_unavailable')
        # Use the CLI's offset-bearing month; do not try other months or chats.
        directory = root / hashlib.md5(chat.encode()).hexdigest() / moment.strftime('%Y-%m') / 'Img'
        for suffix in ('.dat', '_h.dat', '_t.dat'):
            candidate = directory / (md5 + suffix)
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            require(stat.S_ISREG(info.st_mode) and candidate.resolve(strict=True) == candidate, 'media_path_rejected')
            if info.st_size == size:
                candidates.add((candidate, size))
    require(len(candidates) == 1, 'media_original_unavailable')
    candidate, expected_size = candidates.pop()
    encrypted = read_file(candidate)
    require(len(encrypted) == expected_size, 'media_file_changed')
    plaintext = decrypt_v2(encrypted, key.encode(), xor)
    return wxgf_first_frame(plaintext, settings['ffmpeg'])


def _authorized(store, c, source, message):
    current = store._config()
    require(current['enabled'] and any(s == source and s['enabled'] for s in current['sources']), 'media_source_changed')
    _, saved = store._message_context(c, dict(child_id=source['child_id'], source_id=source['id'], message_id=message['id']))
    require(saved == message, 'media_message_mismatch')


def save(app, store, source, message, image, now):
    """Publish a stable file and its relation together; replay never overwrites."""
    body = image['data']; dimensions = validate_png(body)
    require(image.get('first_frame_only') is True and dimensions['width'] == image['width']
            and dimensions['height'] == image['height'], 'media_image_invalid')
    identity = (source['id'], message['id'])
    ident = hashlib.sha256(json.dumps(['wechat-first-frame', source['id'], source['child_id'], message['id']]).encode()).hexdigest()[:32]
    name = '学校图片-' + message['id'] + '（HEVC首帧）.png'
    directory = store.data / 'uploads'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(directory.resolve(strict=True) == directory, 'media_path_rejected')
    target = directory / ident; temporary = None; published = False
    try:
        with store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            _authorized(store, c, source, message)
            job = c.execute('SELECT * FROM agent_media WHERE source_id=? AND message_id=?', identity).fetchone()
            require(job is not None, 'media_job_missing')
            if job['state'] in ('saved', 'skipped', 'dismissed'):
                return {'state': job['state']}
            if c.execute('SELECT 1 FROM agent_message_attachments WHERE source_id=? AND message_id=?', identity).fetchone():
                c.execute("UPDATE agent_media SET state='skipped',error='',updated=? WHERE source_id=? AND message_id=?", (now.isoformat(), *identity))
                return {'state': 'skipped'}
            old = c.execute('SELECT * FROM uploads WHERE id=?', (ident,)).fetchone()
            if old:
                require(old['name'] == name and old['size'] == len(body) and old['mime'] == 'image/png', 'media_file_conflict')
            if target.exists() or target.is_symlink():
                require(read_file(target) == body, 'media_file_conflict')
            else:
                with tempfile.NamedTemporaryFile(dir=directory, prefix='.media-', delete=False) as f:
                    temporary = Path(f.name); f.write(body); f.flush(); os.fsync(f.fileno())
                os.link(temporary, target)  # No overwrite; crash replay reuses the same ID/bytes.
                published = True
            c.execute('INSERT OR IGNORE INTO uploads(id,name,size,mime,created) VALUES (?,?,?,?,?)',
                      (ident, name, len(body), 'image/png', now.isoformat()))
            store._message_upload(c, source['child_id'], ident)
            c.execute('INSERT INTO agent_message_attachments VALUES (?,?,?)', (*identity, ident))
            c.execute("UPDATE agent_media SET state='saved',error='',updated=?,upload_id=? WHERE source_id=? AND message_id=?",
                      (now.isoformat(), ident, *identity))
        return {'state': 'saved', 'first_frame_only': True}
    except Exception:
        if published:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def run_one(app, store, now):
    """Called under the existing Agent lock; one image and at most three attempts."""
    selected = None
    try:
        settings = config(store.data)
        if settings is None:
            return {'state': 'disabled'}
        with store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            sources = store._config()
            if not sources['enabled']:
                return {'state': 'disabled'}
            allowed = {s['id']: s for s in sources['sources'] if s['enabled'] and s['platform'] == 'wechat'}
            if not allowed:
                return {'state': 'idle'}
            # ponytail: scan recent saved images, indexed queue only if this bounded family backlog grows.
            rows = c.execute("""SELECT m.source_id,m.id,m.payload FROM agent_messages m
                LEFT JOIN agent_media a ON a.source_id=m.source_id AND a.message_id=m.id
                WHERE json_extract(m.payload,'$.kind')='image'
                AND m.source_id IN (""" + ','.join('?' for _ in allowed) + """)
                AND julianday(json_extract(m.payload,'$.time'))>=julianday(?)
                AND (a.source_id IS NULL OR (a.state IN ('pending','error') AND a.attempts<3 AND a.updated<=?))
                ORDER BY julianday(json_extract(m.payload,'$.time')) DESC,m.id DESC LIMIT 200""",
                (*allowed, settings['since'].isoformat(), (now - dt.timedelta(minutes=5)).isoformat())).fetchall()
            for row in rows:
                source = allowed.get(row['source_id']); message = json.loads(row['payload'])
                if source is None or not message['time']:
                    continue
                if dt.datetime.fromisoformat(message['time']) < settings['since']:
                    continue
                _authorized(store, c, source, message)
                identity = (source['id'], message['id'])
                c.execute('INSERT OR IGNORE INTO agent_media(source_id,message_id) VALUES (?,?)', identity)
                if c.execute('SELECT 1 FROM agent_message_attachments WHERE source_id=? AND message_id=?', identity).fetchone():
                    c.execute("UPDATE agent_media SET state='skipped',updated=? WHERE source_id=? AND message_id=?", (now.isoformat(), *identity))
                    continue
                c.execute("UPDATE agent_media SET state='pending',attempts=attempts+1,updated=?,error='' WHERE source_id=? AND message_id=?", (now.isoformat(), *identity))
                selected = (source, message)
                break
        if selected is None:
            return {'state': 'idle'}
        image = fetch(settings, *selected)
        return save(app, store, *selected, image, now)
    except Exception as error:
        # The worker and CLI may hold credentials/private paths. Never report raw errors.
        code = error.code if isinstance(error, MediaError) else 'media_unavailable'
        if selected:
            with store._db() as c:
                c.execute("UPDATE agent_media SET state='error',error=?,updated=? WHERE source_id=? AND message_id=? AND state='pending'",
                          (code, now.isoformat(), selected[0]['id'], selected[1]['id']))
        return {'state': 'error', 'error': code}
