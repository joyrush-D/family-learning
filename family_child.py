"""Restricted reading entrance; child identity never comes from request fields."""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import quote, urlsplit

import family_reading
import family_study
import family_guided

COOKIE = 'family_child_session'
TASK_FIELDS = ('id', 'version', 'state', 'book', 'edition', 'scope', 'method',
               'criteria', 'stamps', 'planned_on', 'work_text')


class ChildError(ValueError):
    def __init__(self, message, status=400, code='invalid_child_request'):
        super().__init__(message)
        self.status, self.code = status, code


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def _db(app):
    c = app.connect()
    try:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS child_invites (
                hash TEXT PRIMARY KEY, child_id TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS child_sessions (
                hash TEXT PRIMARY KEY, child_id TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS child_shares (
                task_id TEXT PRIMARY KEY, child_id TEXT NOT NULL, shared INTEGER NOT NULL CHECK(shared IN (0,1)));
            CREATE TABLE IF NOT EXISTS child_uploads (
                upload_id TEXT PRIMARY KEY, child_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS child_study_access (
                child_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)));
        ''')
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _fields(obj, allowed):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        raise ChildError('请求包含未允许的操作或字段')


def _profile(app, c, ident):
    child = next((p for p in app.profiles(c) if p['id'] == ident), None)
    if child is None:
        raise ChildError('孩子入口尚未配置，请联系家长', 403, 'child_unavailable')
    return {'id': child['id'], 'name': child['name']}


def parent_state(app):
    with _db(app) as c:
        now = int(time.time())
        children = []
        for child in app.profiles(c):
            ident = child['id']
            active = any(c.execute('SELECT 1 FROM ' + table + ' WHERE child_id=? AND expires>? LIMIT 1', (ident, now)).fetchone()
                         for table in ('child_invites', 'child_sessions'))
            children.append(dict(child_id=ident, has_access=active, study_enabled=_study_enabled(c,ident),
                                 shared_task_ids=[r[0] for r in c.execute('SELECT task_id FROM child_shares WHERE child_id=? AND shared=1', (ident,))]))
        return {'children': children}


def parent_action(app, action, obj):
    if action == 'state':
        _fields(obj, ())
        return parent_state(app)
    if action not in ('invite', 'revoke', 'share', 'study'):
        raise ChildError('入口操作不存在', 404, 'not_found')
    _fields(obj, ('child_id', 'task_id', 'shared') if action == 'share' else ('child_id','enabled') if action=='study' else ('child_id',))
    if not isinstance(obj.get('child_id'), str):
        raise ChildError('请选择孩子')
    app.reading_store()
    with _db(app) as c:
        c.execute('BEGIN IMMEDIATE')
        ident = _profile(app, c, obj['child_id'])['id']
        if action=='study':
            enabled=obj.get('enabled')
            if type(enabled) is not bool: raise ChildError('请明确是否开放每日功课')
            c.execute('INSERT INTO child_study_access VALUES (?,?) ON CONFLICT(child_id) DO UPDATE SET enabled=excluded.enabled',(ident,int(enabled)))
            return dict(child_id=ident,study_enabled=enabled)
        if action == 'invite':
            entry = os.environ.get('FAMILY_CHILD_PUBLIC_URL', '')
            if entry:
                parsed = urlsplit(entry)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.path.endswith('/child/') or any(ord(ch) < 33 for ch in entry):
                    raise ChildError('孩子入口公开地址配置错误', 503, 'configuration_error')
            invite = secrets.token_urlsafe(32)
            expires = int(time.time()) + 86400
            c.execute('DELETE FROM child_invites WHERE child_id=?', (ident,))
            c.execute('INSERT INTO child_invites VALUES (?,?,?)', (_digest(invite), ident, expires))
            return dict(invite=invite, expires_at=expires, child_id=ident, entry_url=entry)
        if action == 'revoke':
            for table in ('child_invites', 'child_sessions'):
                c.execute('DELETE FROM ' + table + ' WHERE child_id=?', (ident,))
            return {'ok': True, 'child_id': ident}
        task_id, shared = obj.get('task_id'), obj.get('shared')
        if not isinstance(task_id, str) or type(shared) is not bool:
            raise ChildError('请选择阅读任务及是否开放')
        row = c.execute('SELECT state FROM reading_tasks WHERE id=? AND child_id=?', (task_id, ident)).fetchone()
        if row is None:
            raise ChildError('这位孩子的阅读任务不存在', 404, 'not_found')
        if shared and row['state'] == '草案':
            raise ChildError('请先与孩子约定并开始任务，再开放给孩子')
        c.execute('INSERT INTO child_shares VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE SET shared=excluded.shared', (task_id, ident, int(shared)))
        return dict(task_id=task_id, child_id=ident, shared=shared)


def _cookie(secret='', lifetime=604800):
    path = os.environ.get('FAMILY_CHILD_COOKIE_PATH', '/child/')
    if not re.fullmatch(r'/[A-Za-z0-9_/-]*child/', path):
        raise ChildError('孩子入口路径配置错误', 503, 'configuration_error')
    return (COOKIE + '=' + secret + '; Path=' + path + '; Max-Age=' + str(lifetime)
            + '; HttpOnly; SameSite=Strict' + ('; Secure' if os.environ.get('FAMILY_CHILD_SECURE') == '1' else ''))


def _secret(handler):
    raw = handler.headers.get('Cookie', '')
    if len(raw) > 8192:
        return ''
    values = [piece.strip().split('=', 1)[1] for piece in raw.split(';')
              if piece.strip().startswith(COOKIE + '=')]
    return values[0] if len(values) == 1 and re.fullmatch(r'[A-Za-z0-9_-]{43}', values[0]) else ''


def _session(app, c, secret):
    row = c.execute('SELECT child_id FROM child_sessions WHERE hash=? AND expires>?', (_digest(secret), int(time.time()))).fetchone()
    if not secret or row is None:
        raise ChildError('请使用家长提供的新邀请进入', 401, 'login_required')
    return _profile(app, c, row['child_id'])


def _csrf(secret):
    return _digest('csrf:' + secret)


def _metadata(app, c, ident):
    row = c.execute('SELECT id,name,size,mime FROM uploads WHERE id=?', (ident,)).fetchone()
    if row is None:
        return {'id': ident, 'name': '原件暂不可读取', 'size': None, 'mime': '', 'url': '/child/upload/' + ident}
    result = dict(row)
    result['url'] = '/child/upload/' + ident
    return result


def _task(app, c, row):
    result = {key: row[key] for key in TASK_FIELDS}
    attachments = row['attachments']
    if isinstance(attachments, str):
        attachments = json.loads(attachments)
    result['attachments'] = [_metadata(app, c, ident) for ident in attachments]
    award = c.execute('SELECT amount,status,granted_on FROM reading_awards WHERE task_id=?', (row['id'],)).fetchone()
    result['award'] = dict(award) if award else None
    return result


def _state(app, secret):
    app.reading_store()
    with _db(app) as c:
        c.execute('BEGIN')
        child = _session(app, c, secret)
        rows = c.execute('''SELECT t.* FROM reading_tasks t JOIN child_shares s ON s.task_id=t.id
            WHERE t.child_id=? AND s.child_id=? AND s.shared=1 AND t.state<>'草案' ORDER BY t.updated DESC,t.id''', (child['id'], child['id']))
        return dict(child=child, csrf=_csrf(secret), tasks=[_task(app, c, row) for row in rows],
                    asr={'configured': bool(os.environ.get('FAMILY_ASR_URL'))},study_enabled=_study_enabled(c,child['id']),
                    today=family_study.dt.datetime.now(family_study.TZ).date().isoformat())


def _study_enabled(c, child_id):
    row=c.execute('SELECT enabled FROM child_study_access WHERE child_id=?',(child_id,)).fetchone()
    return bool(row and row['enabled'])


def _guided(app, secret, action, obj):
    allowed = {'id'} if action == 'state' else {'id', 'version', 'request_key', 'action', 'kind', 'text', 'attachments', 'assistance', 'note'}
    if action not in ('state', 'action'):
        raise ChildError('孩子入口没有这项引导操作', 404, 'not_found')
    _fields(obj, allowed)
    with _db(app) as c:
        current = _session(app, c, secret)
    def authorize(connection, child_id):
        child = _session(app, connection, secret)
        if child_id != child['id']:
            raise ChildError('孩子归属不正确', 403, 'wrong_child')
    store = family_guided.Store(app, authorize=authorize)
    if action == 'state':
        result = store.snapshot(current['id'])
        if 'id' in obj:
            if not isinstance(obj['id'], str):
                raise ChildError('请选择已开放的短引导')
            result['sessions'] = [row for row in result['sessions'] if row['id'] == obj['id']]
        return result
    return store.action(dict(obj, child_id=current['id']))


def _study(app, secret, action, obj):
    allowed={'day'}
    if action=='item': allowed|={'request_key','id','version','title','subject','planned_minutes'}
    elif action=='action': allowed|={'request_key','id','version','action','result','assistance','note','actual_minutes'}
    elif action!='state': raise ChildError('孩子入口没有这项功课操作',404,'not_found')
    _fields(obj,allowed)
    if action=='action' and obj.get('action') not in ('start','pause','finish','manual'):
        raise ChildError('作息时间和收尾由家长安排')
    day=family_study._day(obj.get('day'))
    if day>family_study.dt.datetime.now(family_study.TZ).date().isoformat():
        raise ChildError('请选择今天或以前已有安排的日期')
    with _db(app) as c:
        child=_session(app,c,secret)
    def authorize(connection, ident):
        current=_session(app,connection,secret)
        if ident!=current['id']: raise ChildError('孩子归属不正确',403,'wrong_child')
        if not _study_enabled(connection,ident): raise ChildError('家长尚未开放每日功课，请先联系家长',403,'study_not_shared')
    store=family_study.Store(app,authorize=authorize)
    payload=dict(obj,child_id=child['id'])
    state=store.snapshot(child['id'],day) if action=='state' else getattr(store,'save_item' if action=='item' else 'action')(payload)
    fields=('id','day','title','subject','planned_minutes','elapsed_seconds','running_since','status','result','result_actor',
            'assistance','note','actual_minutes','time_source','time_needs_review','version',
            'source_task_action','source_task_next_action','source_task_due')
    items=[]
    for row in state['items']:
        item={key:row[key] for key in fields}
        item['editable']=row['source_task_status'] not in (*app.TASK_CLOSED,'待核对') and not (row['result_actor']=='parent' and row['result']=='完成')
        if row['result_actor']!='child': item['note']=''
        items.append(item)
    return dict(ok=True,day={key:value for key,value in state['day'].items() if key!='child_id'},
                items=items,summary=state['summary'],active_item=state['active_item'])


def _shared(c, child, task_id):
    if not isinstance(task_id, str):
        raise ChildError('请选择已开放的阅读任务')
    row = c.execute('''SELECT t.* FROM reading_tasks t JOIN child_shares s ON s.task_id=t.id
        WHERE t.id=? AND t.child_id=? AND s.child_id=? AND s.shared=1 AND t.state<>'草案' ''', (task_id, child, child)).fetchone()
    if row is None:
        raise ChildError('这项任务未向你开放，请联系家长', 403, 'not_shared')
    return row


def _own(c, child, ident):
    return isinstance(ident, str) and bool(c.execute('SELECT 1 FROM child_uploads WHERE upload_id=? AND child_id=?', (ident, child)).fetchone())


def _submit(app, secret, obj):
    _fields(obj, ('child_id', 'id', 'version', 'request_key', 'work_text', 'attachments'))
    # Reuse the reading store's transaction and idempotency, checking access under
    # its write lock so revocation/unsharing cannot race the saved submission.
    active = {}
    def connection():
        active['c'] = app.connect()
        return active['c']
    def profiles():
        c = active['c']
        child = _session(app, c, secret)
        if 'child_id' in obj and obj['child_id'] != child['id']:
            raise ChildError('孩子归属不正确', 403, 'wrong_child')
        row = _shared(c, child['id'], obj.get('id'))
        ids = obj.get('attachments')
        if not isinstance(ids, list) or len(ids) > 20 or any(not isinstance(i, str) or not re.fullmatch(r'[a-f0-9]{32}', i) for i in ids):
            raise ChildError('请选择自己的作品原件，最多20份')
        already_shared = json.loads(row['attachments'])
        if any(not _own(c, child['id'], ident) and ident not in already_shared for ident in ids):
            raise ChildError('只能使用自己上传或这项任务已开放的原件', 403, 'upload_not_allowed')
        return [child]
    with _db(app) as c:
        child = _session(app, c, secret)
    if 'child_id' in obj and obj['child_id'] != child['id']:
        raise ChildError('孩子归属不正确', 403, 'wrong_child')
    payload = dict(obj, child_id=child['id'], note='通过孩子独立入口提交，内容待家长核对。')
    result = family_reading.Store(connection, profiles, lambda: []).mutate('submit', payload)
    with _db(app) as c:
        return {'task': _task(app, c, result['task'])}


def _reply(handler, status, body, kind='application/json; charset=utf-8', cookie=None, disposition=None, headers=None):
    if not isinstance(body, bytes):
        body = json.dumps(body, ensure_ascii=False).encode()
    body, encoding = handler.json_body(body, kind)
    handler.send_response(status)
    if status != 304:
        handler.send_header('Content-Length', str(len(body)))
    for key, value in {'Content-Type': kind, 'Cache-Control': 'no-store',
                       'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
                       'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'", **encoding, **(headers or {})}.items():
        handler.send_header(key, value)
    if cookie:
        handler.send_header('Set-Cookie', cookie)
    if disposition:
        handler.send_header('Content-Disposition', disposition)
    handler.end_headers()
    handler.wfile.write(body)


def _run(handler, operation):
    try:
        operation()
    except (ChildError, family_reading.ReadingError, family_study.StudyError, family_guided.GuidedError) as exc:
        _reply(handler, exc.status, {'error': str(exc), 'code': exc.code})
    except (ValueError, TypeError):
        _reply(handler, 400, {'error': '输入格式不正确，请保留作品并核对后重试', 'code': 'invalid_input'})
    except (OSError, sqlite3.Error):
        _reply(handler, 503, {'error': '读取或保存暂未完成，请保留作品后重试', 'code': 'temporarily_unavailable'})


def dispatch_get(app, handler, path):
    if path != '/child' and not path.startswith('/child/'):
        return False
    def action():
        if path == '/child':
            handler.send_response(308)
            handler.send_header('Location', os.environ.get('FAMILY_CHILD_COOKIE_PATH', '/child/'))
            handler.send_header('Content-Length', '0')
            handler.end_headers()
            return
        static = {'/child/': ('child.html', 'text/html'), '/child/child.js': ('child.js', 'text/javascript'),
                  '/child/child.css': ('child.css', 'text/css')}
        if path in static:
            name, kind = static[path]
            return handler.reply_static((app.ROOT / name,), kind + '; charset=utf-8',
                                        reply=lambda *args, **kwargs: _reply(handler, *args, **kwargs))
        secret = _secret(handler)
        if path == '/child/api/state':
            return _reply(handler, 200, _state(app, secret))
        if path.startswith('/child/upload/'):
            ident = path.removeprefix('/child/upload/')
            if not re.fullmatch(r'[a-f0-9]{32}', ident):
                raise ChildError('原件不存在', 404, 'not_found')
            app.reading_store()
            with _db(app) as c:
                c.execute('BEGIN')
                child = _session(app, c, secret)['id']
                if not _own(c, child, ident):
                    rows = c.execute('''SELECT t.attachments FROM reading_tasks t JOIN child_shares s ON t.id=s.task_id
                        WHERE t.child_id=? AND s.child_id=? AND s.shared=1 AND t.state<>'草案' ''', (child, child))
                    if not any(ident in json.loads(row[0]) for row in rows) and not family_guided.child_upload_allowed(c, child, ident):
                        raise ChildError('这份原件未向你开放', 403, 'upload_not_allowed')
                row = c.execute('SELECT * FROM uploads WHERE id=?', (ident,)).fetchone()
                file = app.DATA / 'uploads' / ident
                if row is None or file.is_symlink() or not file.is_file() or file.stat().st_size != row['size']:
                    raise ChildError('原件暂不可读取，请联系家长', 404, 'not_found')
                mode = 'inline' if row['mime'].startswith(('image/', 'audio/')) else 'attachment'
                return _reply(handler, 200, file.read_bytes(), row['mime'], disposition=mode + "; filename*=UTF-8''" + quote(row['name'], safe=''))
        raise ChildError('孩子入口没有这项功能', 404, 'not_found')
    _run(handler, action)
    return True


def dispatch_post(app, handler, path):
    if path != '/child' and not path.startswith('/child/'):
        return False
    handler.close_connection = True
    def action():
        allowed = {'/child/api/' + item for item in ('login', 'logout', 'upload', 'submit', 'transcribe','study/state','study/item','study/action','guided/state','guided/action')}
        if path not in allowed:
            raise ChildError('孩子入口没有这项操作', 404, 'not_found')
        if handler.headers.get('Transfer-Encoding') or len(handler.headers.get_all('Content-Length', [])) != 1:
            raise ChildError('请求格式不正确')
        size = int(handler.headers.get('Content-Length', '0'))
        limit = app.MAX_UPLOAD if path.endswith('/upload') else 20000
        if not 0 < size <= limit:
            raise ChildError('文件最多20MB；文字请求不能为空或过长', 413, 'request_too_large')
        handler.connection.settimeout(30)
        secret = _secret(handler)
        if path != '/child/api/login':
            with _db(app) as c:
                child = _session(app, c, secret)['id']
            token = handler.headers.get('X-Child-CSRF', '')
            if not secrets.compare_digest(token.encode(), _csrf(secret).encode()):
                raise ChildError('页面已过期，请重新打开后提交', 403, 'csrf_required')
        if path == '/child/api/upload':
            app.reading_store()
            attachment = app.save_upload(handler.rfile, size, handler.headers.get('X-File-Name', ''))
            try:
                with _db(app) as c:
                    c.execute('BEGIN IMMEDIATE')
                    current = _session(app, c, secret)['id']
                    c.execute('INSERT INTO child_uploads VALUES (?,?)', (attachment['id'], current))
                    c.execute('INSERT INTO reading_uploads VALUES (?,?)', (attachment['id'], current))
            except Exception:
                with app.connect() as c:
                    c.execute('DELETE FROM uploads WHERE id=?', (attachment['id'],))
                (app.DATA / 'uploads' / attachment['id']).unlink(missing_ok=True)
                raise
            attachment['url'] = '/child/upload/' + attachment['id']
            return _reply(handler, 200, {'ok': True, 'attachment': attachment})
        if handler.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            raise ChildError('请使用网页表单提交')
        raw = handler.rfile.read(size)
        if len(raw) != size:
            raise ChildError('请求未传输完整，请保留作品重试')
        obj = json.loads(raw)
        if path == '/child/api/login':
            _fields(obj, ('invite',))
            invite = obj.get('invite', '')
            if not isinstance(invite, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', invite):
                raise ChildError('邀请已失效，请向家长索取新邀请', 401, 'invite_invalid')
            secret = secrets.token_urlsafe(32)
            cookie = _cookie(secret)
            with _db(app) as c:
                c.execute('BEGIN IMMEDIATE')
                row = c.execute('SELECT child_id FROM child_invites WHERE hash=? AND expires>?', (_digest(invite), int(time.time()))).fetchone()
                if row is None:
                    raise ChildError('邀请已使用或已过期，请向家长索取新邀请', 401, 'invite_invalid')
                _profile(app, c, row['child_id'])
                c.execute('DELETE FROM child_invites WHERE hash=?', (_digest(invite),))
                c.execute('INSERT INTO child_sessions VALUES (?,?,?)', (_digest(secret), row['child_id'], int(time.time()) + 604800))
            return _reply(handler, 200, _state(app, secret), cookie=cookie)
        if path == '/child/api/logout':
            _fields(obj, ())
            with _db(app) as c:
                c.execute('DELETE FROM child_sessions WHERE hash=?', (_digest(secret),))
            return _reply(handler, 200, {'ok': True}, cookie=_cookie('', 0))
        if path == '/child/api/submit':
            return _reply(handler, 200, _submit(app, secret, obj))
        if path.startswith('/child/api/study/'):
            return _reply(handler,200,_study(app,secret,path.removeprefix('/child/api/study/'),obj))
        if path.startswith('/child/api/guided/'):
            return _reply(handler,200,_guided(app,secret,path.removeprefix('/child/api/guided/'),obj))
        _fields(obj, ('attachment',))
        with _db(app) as c:
            current = _session(app, c, secret)['id']
            if not _own(c, current, obj.get('attachment')):
                raise ChildError('只能转写自己上传的录音', 403, 'upload_not_allowed')
        try:
            result = app.transcribe_material(obj)
        except app.family_llm.LLMDraftError:
            raise ChildError('录音转写暂不可用，原音已保留，可直接提交或稍后重试', 503, 'transcription_unavailable') from None
        return _reply(handler, 200, {'text': result})
    _run(handler, action)
    return True
