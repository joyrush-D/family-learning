"""Optional, bounded local WeChat image saving inside the existing Agent cycle.

Only the pinned CLI's original V2/WXGF still-image variant is supported. No
key extraction or downloads. Linked images can be interpreted as parent-review
drafts by the existing model budget; message payloads and family facts stay intact.
"""
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from xml.etree import ElementTree
import zipfile

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


def collection_view(store, c, source, message, attachments):
    """Describe saved evidence and current eligibility; never fetch or enqueue on view."""
    row = c.execute('SELECT state,attempts,error FROM agent_media WHERE source_id=? AND message_id=?',
                    (source['id'], message['id'])).fetchone()
    supported = source['platform'] == 'wechat' and message['kind'] == 'image'
    if row is None and not supported:
        return None
    result = dict(state=row['state'] if row else 'not_started', attempts=row['attempts'] if row else 0)
    if attachments:
        note = '已自动保存可读首帧，完整内容仍需核对。' if result['state'] == 'saved' else ''
    elif result['state'] == 'dismissed':
        note = '已停止自动关联，可手动补充。'
    else:
        reason = {'process_timeout': '上次读取原图超时。',
                  'media_original_unavailable': '上次未在本机找到可用原图。'}.get(
                      row['error'] if row and row['state'] == 'error' else '', '')
        if not supported:
            status = '这类消息尚不支持自动取图。'
        elif not source['enabled'] or not store._config(c)['enabled']:
            status = '此来源的自动读取已暂停。'
        else:
            try:
                settings = config(store.data)
                if settings is None:
                    status = '自动取图未启用。'
                elif not message['time'] or dt.datetime.fromisoformat(message['time']) < settings['since']:
                    status = '这条图片不在已配置的自动取图时间范围内。'
                elif result['state'] == 'error' and result['attempts'] >= 3:
                    status = '这张图片自动取图已达重试上限。'
                else:
                    status = '尚未取得原图。' if not reason else ''
            except (OSError, ValueError, TypeError, MediaError):
                status = '自动取图配置待修复。'
        note = status + reason + '可在下面补充原件。'
    return {**result, 'explanation': note}


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
    current = store._config(c)
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
            sources = store._config(c)
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


# Drafts are derived from linked originals; they never overwrite messages or learning facts.
SCHOOL_MATERIAL = 'school_material'


def _material_kind(message):
    from family_qq_capture import KIND, NOTICE
    ocr = message.get('kind') == KIND and message.get('text', '').startswith(NOTICE+'\n截图本机文字识别（')
    return SCHOOL_MATERIAL if ocr else ''


# Linked DOCX originals are read in memory as plain body text. A file that cannot be read
# completely is refused, so a draft never claims more than the text it was given.
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
DOCX_LIMITS = dict(entries=200, total=8 * 1024 * 1024, member=4 * 1024 * 1024, chars=10000)
_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_DOCX_SKIP = frozenset(_W + n for n in ('pPr', 'rPr', 'tblPr', 'tblPrEx', 'tblGrid', 'trPr', 'tcPr', 'sectPr',
                                        'bookmarkStart', 'bookmarkEnd', 'proofErr', 'lastRenderedPageBreak'))
_DOCX_MARKS = {_W + 'tab': '\t', _W + 'br': '\n', _W + 'cr': '\n', _W + 'noBreakHyphen': '-', _W + 'softHyphen': ''}
# Text kept outside the body, or text whose meaning plain characters would misstate.
_DOCX_UNREAD = frozenset(_W + n for n in ('headerReference', 'footerReference'))
_DOCX_TOGGLES = frozenset(_W + n for n in ('vanish', 'webHidden', 'specVanish', 'strike', 'dstrike'))


def _docx_xml(data):
    # Word writes UTF-8 without a DTD; declarations and entities are refused before parsing.
    require(b'\x00' not in data and b'<!DOCTYPE' not in data and b'<!ENTITY' not in data, 'draft_docx_rejected')
    try:
        data.decode('utf-8')
        return ElementTree.fromstring(data)
    except (ElementTree.ParseError, ValueError, LookupError):
        raise MediaError('draft_docx_rejected') from None


def _docx_inline(paragraph):
    parts, stack = [], list(reversed(paragraph))
    while stack:
        node = stack.pop()
        if node.tag == _W + 't':
            parts.append(node.text or '')
        elif node.tag in _DOCX_MARKS:
            parts.append(_DOCX_MARKS[node.tag])
        elif node.tag in (_W + 'r', _W + 'hyperlink'):
            stack.extend(reversed(node))
        else:  # Pictures, formulas, fields, notes, revisions and anything else that is not plain text.
            require(node.tag in _DOCX_SKIP, 'draft_docx_unsupported')
    return ''.join(parts)


def _docx_children(node, tag):
    for child in node:
        if child.tag not in _DOCX_SKIP:
            require(child.tag == tag, 'draft_docx_unsupported')
            yield child


def docx_text(body):
    """Body paragraphs and table rows of one DOCX; never unpacked to disk, executed or fetched."""
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            infos = z.infolist(); names = [i.filename for i in infos]; low = [n.lower() for n in names]
            require(len(infos) <= DOCX_LIMITS['entries'] and len(set(low)) == len(low)
                    and sum(i.file_size for i in infos) <= DOCX_LIMITS['total']
                    and all(i.file_size <= DOCX_LIMITS['member'] and not i.flag_bits & 0x41
                            and i.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) for i in infos)
                    and not any(n.startswith('/') or '\\' in n or '..' in n.split('/') or 'vba' in n for n in low)
                    and '[Content_Types].xml' in names and 'word/document.xml' in names, 'draft_docx_rejected')
            parts = {}
            for info in infos:
                if info.filename in ('[Content_Types].xml', 'word/document.xml') or info.filename.endswith('.rels'):
                    with z.open(info) as f:  # A bounded read: the declared size alone never stops a bomb.
                        parts[info.filename] = f.read(DOCX_LIMITS['member'] + 1)
                    require(len(parts[info.filename]) == info.file_size, 'draft_docx_rejected')
    except MediaError:
        raise
    except Exception:  # Damaged, truncated or password-protected archives all fail closed.
        raise MediaError('draft_docx_rejected') from None
    types = _docx_xml(parts['[Content_Types].xml'])
    main = [e.get('ContentType') for e in types.iter() if e.get('PartName') == '/word/document.xml']
    require(main == [DOCX_MIME + '.main+xml'] and not any(word in e.get('ContentType', '').lower()
            for e in types.iter() for word in ('macro', 'vba')), 'draft_docx_rejected')
    for name, data in parts.items():  # Nothing is fetched; a file that points outside itself is not read at all.
        require(not name.endswith('.rels') or not any(e.get('TargetMode', '').lower() == 'external'
                                                       for e in _docx_xml(data).iter()), 'draft_docx_rejected')
    # Embedded pictures, objects and fonts are not text; charts and diagrams also need a drawing in the body.
    require(all(n.endswith(('.xml', '.rels', '/')) for n in low if n.startswith('word/')), 'draft_docx_unsupported')
    root = _docx_xml(parts['word/document.xml'])
    require(root.tag == _W + 'document' and [e.tag for e in root] == [_W + 'body'], 'draft_docx_unsupported')
    for e in root.iter():
        on = e.get(_W + 'val', 'true').lower() not in ('0', 'false', 'off')
        require(e.tag not in _DOCX_UNREAD and not (e.tag in _DOCX_TOGGLES and on), 'draft_docx_unsupported')
    lines = []
    for block in root[0]:
        if block.tag == _W + 'p':
            lines.append(_docx_inline(block))
        elif block.tag == _W + 'tbl':  # One line per row; nested tables are not flattened.
            for row in _docx_children(block, _W + 'tr'):
                cells = [[' '.join(_docx_inline(p).split()) for p in _docx_children(cell, _W + 'p')]
                         for cell in _docx_children(row, _W + 'tc')]
                lines.append(' | '.join(' / '.join(p for p in cell if p) for cell in cells))
        else:
            require(block.tag in _DOCX_SKIP, 'draft_docx_unsupported')
    text = '\n'.join(line for line in lines if line.strip())
    require(text, 'draft_docx_unsupported')
    require(len(text) <= DOCX_LIMITS['chars'], 'draft_text_too_long')
    return text


def draft_input(store, c, source, message):
    import family_llm
    from family_agent import _json
    from family_qq_capture import KIND, NOTICE
    links = [r['upload_id'] for r in c.execute(
        'SELECT upload_id FROM agent_message_attachments WHERE source_id=? AND message_id=? ORDER BY upload_id',
        (source['id'], message['id']))]
    kind = _material_kind(message); screenshot = None
    if kind:
        # Already routed to school task drafts; the screenshot alone never becomes a study record.
        # Only explicitly linked extra originals are read, as school material for parent review.
        screenshot = re.fullmatch(r'fragment-([a-f0-9]{40})', message.get('id', ''))
        if screenshot is None:
            return None
        links = [i for i in links if i != screenshot.group(1)[:32]]  # The capture's own upload ID, not its name.
    if not links:
        return None
    _authorized(store, c, source, message)
    require(len(links) <= 3, 'draft_too_many_originals')
    child = next(p for p in store.profiles(c) if p['id'] == source['child_id'])
    images, documents, originals = [], [], []
    for ident in links:
        row = store._message_upload(c, source['child_id'], ident)
        docx = bool(kind) and row['mime'] == DOCX_MIME  # Only school material may have text originals.
        require(docx or row['mime'] in ('image/jpeg', 'image/png', 'image/webp'), 'draft_image_required')
        body = read_file(store.data / 'uploads' / ident)
        require(len(body) == row['size'], 'media_file_changed')
        digest = hashlib.sha256(body).hexdigest()
        if screenshot and hashlib.sha256(_json([KIND, source['id'], source['child_id'], message['text'][len(NOTICE) + 1:],
                                                digest]).encode()).hexdigest()[:40] == screenshot.group(1):
            continue  # The same capture uploaded again under another ID is still not an original.
        if docx:  # Every selected original must be readable in full, or nothing is sent.
            documents.append(dict(name=str(row['name'] or ''), text=docx_text(body)))
        else:
            images.append(dict(mime=row['mime'], data=body))
        originals.append([ident, row['mime'], digest])
    if not originals:
        return None
    text = json.dumps(dict(source_message=message, source_name=source['name']), ensure_ascii=False)
    words = text + ''.join(d['name'] + d['text'] for d in documents)
    require(not documents or len(words) <= family_llm.MAX_TEXT, 'draft_text_too_long')  # Never cut to fit.
    require(sum(len(i['data']) for i in images) + len(words.encode()) <= 20 * 1024 * 1024, 'draft_originals_too_large')
    # The legacy fingerprint is unchanged; a typed draft can never match a saved draft of another type.
    fingerprint = hashlib.sha256(json.dumps(([2, kind] if kind else [1]) + [source, child, message, originals],
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return dict(fingerprint=fingerprint, images=images, text=text, child=child['name'],
                upload_ids=[o[0] for o in originals], kind=kind, documents=documents)


def draft_key(source, message):
    return 'message-draft:' + hashlib.sha256(json.dumps([source['id'], message['id']]).encode()).hexdigest()[:40]


def _saved_draft(row, value):
    """Show a saved draft only for the same fingerprint and, when typed, the same checked shape."""
    import family_llm
    if row is None or row['fingerprint'] != value['fingerprint']:
        return None
    draft = json.loads(row['payload'])
    if not value['kind']:
        return draft
    try:
        require(isinstance(draft, dict) and draft.pop('kind', None) == value['kind'], 'draft_kind_mismatch')
        return family_llm.validate_school_material(draft)
    except (MediaError, family_llm.LLMDraftError):
        return None


def draft_view(store, c, source, message):
    kind = _material_kind(message); typed = dict(kind=kind) if kind else {}
    try:
        value = draft_input(store, c, source, message)
        if value is None:
            return None
    except Exception as error:
        explanation = {'draft_image_required':'补充原件中有PDF等目前尚不支持自动整理的文件，本次未读取任何原件；原件保留，可手动核对。' if kind
                           else '目前自动整理支持JPG、PNG、WebP图片；其他文件可保留并手动记录。',
                       'draft_too_many_originals':'一次最多整理3张原件，请分次关联或手动记录。',
                       'draft_docx_rejected':'DOCX原件已加密、损坏、超出读取限额或含宏、外部链接，本次未读取任何原件；原件保留，请打开原件核对。',
                       'draft_docx_unsupported':'DOCX原件含图片、公式、页眉页脚、批注、修订等暂不能完整读取的内容，为避免遗漏，本次未读取任何原件；原件保留，请打开原件核对。',
                       'draft_text_too_long':'DOCX正文与通知文字合计超过12000字，为避免截断，本次未读取任何原件；可拆分后关联或打开原件核对。',
                       'draft_originals_too_large':'本次原件与文字超过20MiB，可分次关联或手动记录。'}.get(
                           error.code if isinstance(error, MediaError) else '', '当前原件或授权无法完整核对，可保留原件并手动记录。')
        return dict(state='unavailable', explanation=explanation, **typed)
    row = c.execute('SELECT * FROM agent_message_drafts WHERE source_id=? AND message_id=?',
                    (source['id'], message['id'])).fetchone()
    draft = _saved_draft(row, value)
    if draft is not None:
        return dict(state='ready', draft=draft, updated=row['updated'], upload_ids=value['upload_ids'], **typed)
    key = draft_key(source, message)
    job = c.execute('SELECT * FROM agent_jobs WHERE id=?', (key,)).fetchone()
    current = hashlib.sha256(json.dumps({'material': value['fingerprint']}, ensure_ascii=False,
        separators=(',', ':'), sort_keys=True).encode()).hexdigest()
    failed = job and job['fingerprint'] == current and job['error']
    waiting = 'Agent将在后台整理已关联的补充原件；结果只供家长核对，不会改动任务或学习记录。' if kind else 'Agent将在后台整理已关联的图片，结果仍需家长核对。'
    return dict(state='error' if failed else 'pending', job_id=key, **typed,
                explanation='原件整理暂未成功；原图保留，可稍后重试或手动记录。' if failed else waiting)


def prepare_draft(store, now):
    """Use one existing model slot for a linked picture; existing jobs bound retries."""
    import family_llm
    selected = None
    with store._db() as c:
        config = store._config(c)
        if not config['enabled']:
            return dict(used=0, failed=0)
        sources = {s['id']: s for s in config['sources'] if s['enabled']}
        # ponytail: inspect at most 200 linked messages; add an indexed queue if this family backlog grows.
        rows = c.execute("""SELECT m.source_id,m.payload FROM agent_messages m WHERE EXISTS
            (SELECT 1 FROM agent_message_attachments a WHERE a.source_id=m.source_id AND a.message_id=m.id)
            ORDER BY m.rowid DESC LIMIT 200""").fetchall()
    for row in rows:
        source = sources.get(row['source_id'])
        if source is None:
            continue
        message = json.loads(row['payload'])
        try:
            with store._db() as c:
                value = draft_input(store, c, source, message)
                if not value:
                    continue
                old = c.execute('SELECT fingerprint FROM agent_message_drafts WHERE source_id=? AND message_id=?',
                                (source['id'], message['id'])).fetchone()
                if old and old['fingerprint'] == value['fingerprint']:
                    continue
        except Exception:
            continue  # No model receives unreadable, unsupported, or foreign originals.
        key = draft_key(source, message)
        fp = store._job(key, {'material': value['fingerprint']}, now, model=True)
        if fp:
            selected = (source, message, value, key, fp)
            break
    if selected is None:
        return dict(used=0, failed=0)
    source, message, value, key, fp = selected
    try:
        typed = dict(school_material=True, documents=value['documents']) if value['kind'] else {}
        result = family_llm.extract_draft(value['text'], value['images'], target_child=value['child'], timeout=45,
                                          data_path=store.data, **typed)
        if value['kind']:  # Re-checked here: no score, mastery or record field is ever persisted for school material.
            result = dict(kind=value['kind'], **family_llm.validate_school_material(result))
        with store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            current = draft_input(store, c, source, message)
            job = c.execute('SELECT fingerprint FROM agent_jobs WHERE id=?', (key,)).fetchone()
            require(current is not None and current['fingerprint'] == value['fingerprint']
                    and job is not None and job['fingerprint'] == fp, 'draft_material_changed')
            c.execute('INSERT OR REPLACE INTO agent_message_drafts VALUES(?,?,?,?,?)',
                      (source['id'], message['id'], value['fingerprint'], json.dumps(result, ensure_ascii=False), now.isoformat()))
            c.execute("UPDATE agent_jobs SET done=1,error='',next_try='' WHERE id=? AND fingerprint=?", (key, fp))
        return dict(used=1, failed=0)
    except Exception:
        store._fail(key, now, fingerprint=fp)
        return dict(used=1, failed=1)
