"""One explicitly shared question, original attempts and bounded optional hints.

The application owns records and uploads. This store adds only material/access
state and an event/receipt log in the same SQLite database. No rewards or timers.
"""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import re
import secrets
import time

import family_llm
import family_reading

TZ = dt.timezone(dt.timedelta(hours=8))
SOURCE = '短引导尝试:'
IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/webp')


class GuidedError(ValueError):
    def __init__(self, message, status=400, code='invalid_guided'):
        super().__init__(message)
        self.status, self.code = status, code


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _fields(obj, allowed):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        raise GuidedError('字段格式不正确，请保留输入并核对')


def _text(obj, key, limit, default=''):
    value = obj.get(key, default)
    if not isinstance(value, str) or len(value) > limit or any(ord(ch) < 32 and ch not in '\n\t' for ch in value):
        raise GuidedError('字段格式或长度不正确：' + key)
    return value.strip()


def _version(obj, minimum=1):
    value = obj.get('version')
    if type(value) is not int or not minimum <= value <= 2147483647:
        raise GuidedError('请保留输入，刷新核对当前版本', 409, 'version_conflict')
    return value


def _exists(c, table):
    return bool(c.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?', (table,)).fetchone())


def guard_record_write(c, previous, source):
    """Called by the ordinary record API, inside its existing writer transaction."""
    owned = previous is not None and ((previous['source'] or '').startswith(SOURCE) or
        _exists(c, 'guided_events') and c.execute('SELECT 1 FROM guided_events WHERE record_id=?', (previous['id'],)).fetchone())
    if source.startswith(SOURCE) or owned:
        raise GuidedError('原始尝试保留不覆盖；请新增关联观察或在短引导中再次表达。', 409, 'guided_record_owned')


def child_upload_allowed(c, child_id, upload_id):
    if not _exists(c, 'guided_sessions'):
        return False
    return any(upload_id in json.loads(row[0]) for row in c.execute(
        'SELECT question_attachments FROM guided_sessions WHERE child_id=? AND shared=1', (child_id,)))


class Store:
    def __init__(self, app, authorize=None):
        self.app, self.authorize = app, authorize
        self.actor = 'child' if authorize else 'parent'
        with self._db() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS guided_sessions (
                    id TEXT PRIMARY KEY, child_id TEXT NOT NULL, version INTEGER NOT NULL,
                    state TEXT NOT NULL, shared INTEGER NOT NULL, ever_shared INTEGER NOT NULL,
                    title TEXT NOT NULL, subject TEXT NOT NULL, question_text TEXT NOT NULL,
                    question_attachments TEXT NOT NULL, reference_text TEXT NOT NULL,
                    reference_checked INTEGER NOT NULL, related_record_id INTEGER,
                    practice_relation TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS guided_events (
                    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, child_id TEXT NOT NULL,
                    actor TEXT NOT NULL, kind TEXT NOT NULL, request_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
                    record_id INTEGER, record_hash TEXT NOT NULL DEFAULT '',
                    context_version INTEGER NOT NULL, expires REAL NOT NULL DEFAULT 0,
                    created TEXT NOT NULL, UNIQUE(actor,child_id,request_key));
            ''')

    @contextmanager
    def _db(self):
        c = self.app.connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def _child(self, c, child_id):
        if self.authorize:
            self.authorize(c, child_id)
        child = next((p for p in self.app.profiles(c) if p['id'] == child_id), None)
        if child is None:
            raise GuidedError('请选择现有孩子', 404, 'child_missing')
        return child

    def _row(self, c, child_id, ident, check_shared=True):
        if not isinstance(ident, str):
            raise GuidedError('请选择这位孩子的短引导')
        row = c.execute('SELECT * FROM guided_sessions WHERE id=? AND child_id=?', (ident, child_id)).fetchone()
        if row is None:
            raise GuidedError('这位孩子的短引导不存在', 404, 'not_found')
        if self.authorize and check_shared and not row['shared']:
            raise GuidedError('这道题尚未向你开放，请联系家长', 403, 'not_shared')
        return dict(row)

    def _request(self, c, child_id, obj):
        key = _text(obj, 'request_key', 128)
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
            raise GuidedError('请保留本次提交标识后重试')
        digest = _hash({k: v for k, v in obj.items() if k != 'request_key'})
        old = c.execute('SELECT * FROM guided_events WHERE actor=? AND child_id=? AND request_key=?',
                        (self.actor, child_id, key)).fetchone()
        if old and old['request_hash'] != digest:
            raise GuidedError('同一提交标识的内容不同，请先核对已保存内容', 409, 'request_conflict')
        return key, digest, old

    def _attachments(self, c, child, ids, own=False):
        if not isinstance(ids, list) or len(ids) > 3 or any(not isinstance(i, str) or not re.fullmatch(r'[a-f0-9]{32}', i) for i in ids):
            raise GuidedError('每次最多选择三份原件')
        ids = list(dict.fromkeys(ids))
        family_reading.validate_record_attachments(c, child['id'], ids)
        names = self.app.child_names(c)
        for ident in ids:
            if not c.execute('SELECT 1 FROM uploads WHERE id=?', (ident,)).fetchone():
                raise GuidedError('原件不存在，请重新上传')
            if own and (not _exists(c, 'child_uploads') or not c.execute(
                    'SELECT 1 FROM child_uploads WHERE upload_id=? AND child_id=?', (ident, child['id'])).fetchone()):
                raise GuidedError('只能提交自己上传的尝试原件', 403, 'upload_not_allowed')
            for row in c.execute('SELECT child,attachments FROM records WHERE attachments LIKE ?', ('%' + ident + '%',)):
                if ident in json.loads(row['attachments']) and names.get(row['child']) != child['name']:
                    raise GuidedError('原件属于其他孩子或归属尚未核对', 403, 'upload_not_allowed')
        if ids:
            # Reuse the existing cross-feature upload ownership index, including
            # first parent uploads that have not yet entered a reading task.
            c.execute('CREATE TABLE IF NOT EXISTS reading_uploads (upload_id TEXT PRIMARY KEY, child_id TEXT NOT NULL)')
            for ident in ids:
                c.execute('INSERT OR IGNORE INTO reading_uploads VALUES (?,?)', (ident, child['id']))
        return ids

    def _metadata(self, c, ident):
        row = c.execute('SELECT id,name,size,mime FROM uploads WHERE id=?', (ident,)).fetchone()
        value = dict(row) if row else dict(id=ident, name='原件暂不可读取', size=None, mime='')
        value['url'] = ('/child/upload/' if self.authorize else '/upload/') + ident
        return value

    def _gaps(self, c, row, events):
        gaps = []
        if not row['question_text'] and not json.loads(row['question_attachments']):
            gaps.append('题目尚未提供，可以保留尝试并请家长补充题目后重新分享。')
        if not row['reference_checked'] or not row['reference_text']:
            gaps.append('家长尚未提供并核对参考，暂不生成提示；仍可保存自己的表达。')
        count = 0
        for ids in [json.loads(row['question_attachments'])] + [json.loads(e['data']).get('attachments', []) for e in events if e['kind'] == 'attempt']:
            for ident in ids:
                original = c.execute('SELECT mime,size FROM uploads WHERE id=?', (ident,)).fetchone()
                file = self.app.DATA / 'uploads' / ident
                if original is None or file.is_symlink() or not file.is_file() or file.stat().st_size != original['size']:
                    gaps.append('有原件暂不可读取，模型不能据此补全内容。')
                elif original['mime'] not in IMAGE_TYPES:
                    gaps.append('PDF、录音或其他格式原件已保留，提示模型只读取文字和 JPEG、PNG、WebP 图片。')
                else:
                    count += 1
        if count > 3:
            gaps.append('本次超过三张可用图片，请用文字补充核对摘录；未完整读取原件时不会猜测其内容。')
        return list(dict.fromkeys(gaps))

    def _snapshot(self, c, child_id=None):
        if self.authorize:
            self._child(c, child_id)
        elif child_id is not None:
            self._child(c, child_id)
        rows = c.execute('SELECT * FROM guided_sessions' + (' WHERE child_id=?' if child_id is not None else '') +
                         ' ORDER BY updated DESC,id', (child_id,) if child_id is not None else ())
        sessions = []
        for original in rows:
            row = dict(original)
            if self.authorize and not row['shared']:
                continue
            events = [dict(e) for e in c.execute('SELECT * FROM guided_events WHERE session_id=? ORDER BY id', (row['id'],))]
            value = {k: row[k] for k in ('id', 'version', 'state', 'title', 'subject', 'question_text', 'practice_relation', 'created', 'updated')}
            value['question_attachments'] = [self._metadata(c, i) for i in json.loads(row['question_attachments'])]
            value['material_gaps'] = self._gaps(c, row, events)
            visible = []
            for event in events:
                data = json.loads(event['data'])
                item = {k: event[k] for k in ('id', 'kind', 'actor', 'created', 'status')}
                if event['kind'] == 'attempt':
                    item.update({k: data[k] for k in ('attempt_kind', 'text', 'assistance')})
                    item['attachments'] = [self._metadata(c, i) for i in data['attachments']]
                    if not self.authorize:
                        item['record_id'] = event['record_id']
                elif event['kind'] == 'hint':
                    item['actor'] = 'model'
                    if event['status'] == 'ready':
                        item.update({k: data[k] for k in ('hint', 'question', 'uncertainties')})
                    else:
                        expired = event['status'] == 'pending' and event['expires'] <= time.time()
                        if expired:
                            item['status'] = 'stale'
                        item['message'] = ('等待已结束，可重新请求一个提示。' if expired else data.get('message', '提示正在整理，可以暂停或跳过。'))
                elif event['actor'] == 'child' or not self.authorize:
                    if 'note' in data:
                        item['text'] = data['note']
                visible.append(item)
            value['events'] = visible
            pending = any(e['kind'] == 'hint' and e['status'] == 'pending' and e['expires'] > time.time() for e in events)
            attempts = [e for e in events if e['kind'] == 'attempt']
            hints = [e for e in events if e['kind'] == 'hint' and e['status'] == 'ready']
            if self.authorize:
                actions = []
                if row['state'] == 'active':
                    actions = ['pause', 'skip', 'finish']
                    if len(attempts) < 20:
                        actions.insert(0, 'attempt')
                    if attempts and row['reference_checked'] and row['reference_text'] and not pending and len(hints) < 20:
                        actions.insert(1, 'hint')
                elif row['state'] == 'paused':
                    actions = ['resume', 'skip']
            else:
                actions = ['unshare' if row['shared'] else 'share']
                if not row['ever_shared']:
                    actions.append('edit')
                if row['state'] == 'active':
                    actions += ['pause', 'close']
                elif row['state'] == 'paused':
                    actions += ['resume', 'close']
                value.update({k: row[k] for k in ('child_id', 'reference_text', 'related_record_id')})
                value.update(shared=bool(row['shared']), reference_checked=bool(row['reference_checked']), editable=not bool(row['ever_shared']))
            value['allowed_actions'] = actions
            sessions.append(value)
        return dict(ok=True, sessions=sessions)

    def snapshot(self, child_id=None):
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE' if self.authorize else 'BEGIN')
            return self._snapshot(c, child_id)

    def _result(self, c, child_id):
        return self._snapshot(c, child_id if self.authorize else None)

    def _event(self, c, row, key, digest, kind, data, status='ready', record_id=None, record_hash='', expires=0):
        return c.execute('''INSERT INTO guided_events
            (session_id,child_id,actor,kind,request_key,request_hash,status,data,record_id,record_hash,context_version,expires,created)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (row['id'], row['child_id'], self.actor, kind, key, digest, status,
            _json(data), record_id, record_hash, row['version'], expires, dt.datetime.now(TZ).isoformat())).lastrowid

    def _invalidate(self, c, ident):
        c.execute("UPDATE guided_events SET status='stale',data=? WHERE session_id=? AND kind='hint' AND status='pending'",
                  (_json(dict(message='安排或尝试已经变化，旧提示未发布；需要时请重新请求。')), ident))

    def save_material(self, obj):
        if self.authorize:
            raise GuidedError('题目与参考由家长核对后分享', 403, 'parent_required')
        _fields(obj, ('id', 'child_id', 'version', 'request_key', 'title', 'subject', 'question_text', 'question_attachments',
                      'reference_text', 'reference_checked', 'related_record_id', 'practice_relation', 'shared'))
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            child = self._child(c, obj.get('child_id'))
            key, digest, receipt = self._request(c, child['id'], obj)
            if receipt:
                return self._result(c, child['id'])
            previous = self._row(c, child['id'], obj['id']) if obj.get('id') else None
            if previous:
                if _version(obj) != previous['version']:
                    raise GuidedError('材料已更新，请保留输入并核对', 409, 'version_conflict')
                if previous['ever_shared'] or c.execute("SELECT 1 FROM guided_events WHERE session_id=? AND kind='attempt'", (previous['id'],)).fetchone():
                    raise GuidedError('已分享的题目和参考保留不覆盖；请撤销分享后新建一题。', 409, 'material_frozen')
            elif obj.get('version', 0) != 0 or type(obj.get('version', 0)) is not int:
                raise GuidedError('新材料版本须为零')
            title = _text(obj, 'title', 200)
            if not title:
                raise GuidedError('请给这一题起一个简短名称')
            checked, shared = obj.get('reference_checked', False), obj.get('shared', False)
            if type(checked) is not bool or type(shared) is not bool:
                raise GuidedError('请明确参考是否已核对、是否分享')
            reference = _text(obj, 'reference_text', 4000)
            if checked and not reference:
                raise GuidedError('请先填写已核对的参考')
            relation = obj.get('related_record_id')
            if relation is not None:
                if type(relation) is not int or not 0 < relation <= 9223372036854775807:
                    raise GuidedError('关联原记录编号不正确')
                source = c.execute('SELECT child FROM records WHERE id=?', (relation,)).fetchone()
                if source is None or self.app.child_names(c).get(source['child']) != child['name']:
                    raise GuidedError('只能关联当前孩子的已有记录')
            practice = _text(obj, 'practice_relation', 30)
            if practice not in self.app.PRACTICE_RELATIONS:
                raise GuidedError('题目关系不正确；不知道时请留空')
            now = dt.datetime.now(TZ).isoformat()
            row = dict(id=previous['id'] if previous else secrets.token_hex(16), child_id=child['id'],
                       version=previous['version'] + 1 if previous else 1, state='active' if shared else 'draft',
                       shared=int(shared), ever_shared=int(shared), title=title, subject=_text(obj, 'subject', 80),
                       question_text=_text(obj, 'question_text', 4000), question_attachments=_json(self._attachments(c, child, obj.get('question_attachments', []))),
                       reference_text=reference, reference_checked=int(checked), related_record_id=relation,
                       practice_relation=practice, created=previous['created'] if previous else now, updated=now)
            if previous:
                fields = [k for k in row if k != 'id']
                c.execute('UPDATE guided_sessions SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', [row[k] for k in fields] + [row['id']])
            else:
                c.execute('INSERT INTO guided_sessions (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            self._event(c, row, key, digest, 'material', {})
            return self._result(c, child['id'])

    def _record_hash(self, row):
        return _hash({k: row[k] for k in ('day', 'category', 'subject', 'title', 'note', 'source', 'attachments', 'assistance', 'related_record_id', 'practice_relation', 'comparison_note')})

    def _verify_records(self, c, row, child):
        for event in c.execute("SELECT * FROM guided_events WHERE session_id=? AND kind='attempt' ORDER BY id", (row['id'],)):
            record = c.execute('SELECT * FROM records WHERE id=?', (event['record_id'],)).fetchone()
            if record is None or self.app.child_names(c).get(record['child']) != child['name'] or self._record_hash(record) != event['record_hash']:
                raise GuidedError('原始尝试已在别处变化，请联系家长核对；当前输入尚未保存。', 409, 'attempt_changed')

    def _attempt(self, c, row, child, obj, key, digest):
        attempts = [dict(e) for e in c.execute("SELECT * FROM guided_events WHERE session_id=? AND kind='attempt' ORDER BY id", (row['id'],))]
        if len(attempts) >= 20:
            raise GuidedError('这次已保留二十次表达，可以先结束并与家长安排回看。')
        kind = obj.get('kind')
        if kind not in ('first', 'explain_again') or bool(attempts) != (kind == 'explain_again'):
            raise GuidedError('请先保存首次尝试；已有表达后请使用再次解释。')
        _text(obj, 'text', 4000)
        text, assistance = obj.get('text', ''), _text(obj, 'assistance', 30)
        if assistance not in self.app.ASSISTANCE:
            raise GuidedError('帮助情况不正确；不知道时可以留空')
        attachments = self._attachments(c, child, obj.get('attachments', []), own=self.actor == 'child')
        if not text.strip() and not attachments:
            raise GuidedError('可以说说自己的思路或卡在哪里，也可以提交自己的原件。')
        self._verify_records(c, row, child)
        related = attempts[-1]['record_id'] if attempts else row['related_record_id']
        if related is not None:
            original = c.execute('SELECT child FROM records WHERE id=?', (related,)).fetchone()
            if original is None or self.app.child_names(c).get(original['child']) != child['name']:
                raise GuidedError('关联原记录的归属发生变化，请家长核对后再试', 409, 'record_context_changed')
        now = dt.datetime.now(TZ)
        title = ('首次尝试：' if kind == 'first' else '再次解释：') + row['title']
        hint_count = c.execute("SELECT COUNT(*) FROM guided_events WHERE session_id=? AND kind='hint' AND status='ready'", (row['id'],)).fetchone()[0]
        comparison = '本次表达前已提供 ' + str(hint_count) + ' 条系统提示；其他帮助以自述为准，不据此认定独立完成或掌握。'
        practice = '同一道题或同一片段' if attempts else row['practice_relation']
        record_id = c.execute('''INSERT INTO records
            (child,day,category,subject,title,note,source,created,attachments,related_record_id,followup_kind,assistance,practice_relation,comparison_note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (child['name'], now.date().isoformat(), '学习进展', row['subject'], title[:200],
            text, SOURCE + row['id'], now.isoformat(), _json(attachments), related, '补充观察', assistance, practice, comparison)).lastrowid
        record = c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
        self._event(c, row, key, digest, 'attempt', dict(attempt_kind=kind, text=text, attachments=attachments, assistance=assistance),
                    record_id=record_id, record_hash=self._record_hash(record))

    def _model_input(self, c, row):
        attempts, hints, pictures = [], [], []
        candidates = [(i, '题目原件', bool(row['question_text'])) for i in json.loads(row['question_attachments'])]
        for event in c.execute('SELECT * FROM guided_events WHERE session_id=? ORDER BY id', (row['id'],)):
            value = json.loads(event['data'])
            if event['kind'] == 'attempt':
                attempts.append(dict(kind=value['attempt_kind'], text=value['text'], assistance=value['assistance']))
                candidates.extend((i, '首次尝试原件' if value['attempt_kind'] == 'first' else '再次解释原件', bool(value['text'])) for i in value['attachments'])
            elif event['kind'] == 'hint' and event['status'] == 'ready':
                hints.append({k: value[k] for k in ('hint', 'question', 'uncertainties')})
        if not row['question_text'] and not candidates:
            raise GuidedError('题目尚未提供，先保留表达并请家长补充。', 409, 'material_missing')
        if not attempts:
            raise GuidedError('先保存自己的思路或卡点，再按需请求一个提示。')
        if not row['reference_checked'] or not row['reference_text']:
            raise GuidedError('请家长先提供并核对参考；原始尝试会保留。', 409, 'reference_missing')
        if len(hints) >= 20:
            raise GuidedError('这次已保留二十个提示，可以先结束并请家长安排回看。')
        omitted = 0
        for ident, label, has_text in candidates:
            upload = c.execute('SELECT * FROM uploads WHERE id=?', (ident,)).fetchone()
            file = self.app.DATA / 'uploads' / ident
            readable = upload is not None and upload['mime'] in IMAGE_TYPES and not file.is_symlink() and file.is_file() and file.stat().st_size == upload['size']
            if not readable or len(pictures) >= 3:
                if not has_text:
                    raise GuidedError('有原件格式不支持、不可读取或超过三张；请补充已核对文字后再请求提示，现有尝试已保留。', 409, 'material_unreadable')
                omitted += 1
                continue
            pictures.append(dict(mime=upload['mime'], data=file.read_bytes(), label=label))
        if not row['question_text'] and not any(p['label'] == '题目原件' for p in pictures):
            raise GuidedError('尚无可读取的题目，请家长补充；现有尝试已保留。', 409, 'material_missing')
        material = {k: row[k] for k in ('title', 'subject', 'question_text', 'reference_text')}
        material['reference_checked'] = bool(row['reference_checked'])
        if omitted:
            material['question_text'] += '\n[资料范围说明：有 ' + str(omitted) + ' 份原件未读取，本次只依据提供的文字及标注图片，不补全未读取内容。]'
        if len(_json(dict(material=material, attempts=attempts, hints=hints))) > 20000 or sum(len(p['data']) for p in pictures) > 20 * 1024 * 1024:
            raise GuidedError('本次材料超出单次提示范围；原始尝试保留，请家长缩小范围后新建一题。', 409, 'material_too_large')
        return material, attempts, hints, pictures

    def action(self, obj):
        action = obj.get('action') if isinstance(obj, dict) else None
        allowed = {'child_id', 'id', 'version', 'request_key', 'action'}
        if action == 'attempt':
            allowed |= {'kind', 'text', 'attachments', 'assistance'}
        elif action in ('pause', 'resume', 'skip', 'finish', 'close', 'share', 'unshare'):
            allowed.add('note')
        _fields(obj, allowed)
        operations = ('attempt', 'hint', 'pause', 'resume', 'skip', 'finish') if self.authorize else ('share', 'unshare', 'pause', 'resume', 'close')
        if action not in operations:
            raise GuidedError('这个入口没有这项操作', 403, 'action_not_allowed')
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            child = self._child(c, obj.get('child_id'))
            row = self._row(c, child['id'], obj.get('id'))
            key, digest, receipt = self._request(c, child['id'], obj)
            if receipt:
                return self._result(c, child['id'])
            if _version(obj) != row['version']:
                raise GuidedError('这道题已在别处更新，请保留当前输入并核对。', 409, 'version_conflict')
            active = row['state'] == 'active'
            if action in ('attempt', 'hint', 'pause', 'finish') and not active or action == 'resume' and row['state'] != 'paused' or action in ('skip', 'close') and row['state'] not in ('active', 'paused'):
                raise GuidedError('这次引导已经暂停或结束，请先核对当前状态。', 409, 'state_conflict')
            if action == 'hint':
                pending = c.execute("SELECT * FROM guided_events WHERE session_id=? AND kind='hint' AND status='pending'", (row['id'],)).fetchall()
                if any(e['expires'] > time.time() for e in pending):
                    raise GuidedError('已有一个提示正在整理，可以暂停或稍后查看。', 409, 'hint_pending')
                self._invalidate(c, row['id'])
                self._verify_records(c, row, child)
                model_input = self._model_input(c, row)
                event_id = self._event(c, row, key, digest, 'hint', {}, 'pending', expires=time.time() + 90)
            else:
                self._invalidate(c, row['id'])
                if action == 'attempt':
                    self._attempt(c, row, child, obj, key, digest)
                else:
                    self._event(c, row, key, digest, action, dict(note=_text(obj, 'note', 1000)))
                    if action in ('share', 'unshare'):
                        row['shared'] = int(action == 'share')
                        row['ever_shared'] = max(row['ever_shared'], row['shared'])
                        if action == 'share' and row['state'] == 'draft':
                            row['state'] = 'active'
                    else:
                        row['state'] = {'pause': 'paused', 'resume': 'active', 'skip': 'skipped', 'finish': 'closed', 'close': 'closed'}[action]
                c.execute('UPDATE guided_sessions SET state=?,shared=?,ever_shared=?,version=version+1,updated=? WHERE id=?',
                          (row['state'], row['shared'], row['ever_shared'], dt.datetime.now(TZ).isoformat(), row['id']))
                return self._result(c, child['id'])
        # Network work is deliberately outside every SQLite lock.
        error = None
        try:
            material, attempts, hints, images = model_input
            result = family_llm.guided_hint(material, attempts, hints, images=images, data_path=self.app.DATA)
            if (not isinstance(result, dict) or set(result) != {'hint', 'question', 'uncertainties'}
                or any(not isinstance(result[k], str) or len(result[k]) > (500 if k == 'hint' else 200) or '\x00' in result[k] for k in ('hint', 'question'))
                or not isinstance(result['uncertainties'], list) or len(result['uncertainties']) > 3
                or any(not isinstance(v, str) or not v.strip() or len(v) > 300 or '\x00' in v for v in result['uncertainties'])
                or not any([result['hint'].strip(), result['question'].strip(), result['uncertainties']])):
                raise ValueError('invalid model shape')
        except (family_llm.LLMDraftError, ValueError, OSError, TimeoutError):
            error = '提示暂不可用，原始尝试已保留。可以继续表达、找家长或稍后重新请求。'
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                current_child = self._child(c, child['id'])
                current = self._row(c, child['id'], row['id'])
            except Exception:
                c.execute("UPDATE guided_events SET status='stale',data=? WHERE id=? AND status='pending'",
                          (_json(dict(message='访问授权已变化，这个提示未发布。')), event_id))
                c.commit()
                raise
            event = c.execute('SELECT status,expires FROM guided_events WHERE id=?', (event_id,)).fetchone()
            if current['version'] != row['version'] or current['state'] != 'active' or not event or event['status'] != 'pending' or event['expires'] <= time.time():
                c.execute("UPDATE guided_events SET status='stale',data=? WHERE id=? AND status='pending'",
                          (_json(dict(message='安排或尝试已经变化，旧提示未发布；需要时请重新请求。')), event_id))
                return self._result(c, child['id'])
            try:
                self._verify_records(c, current, current_child)
            except GuidedError:
                self._invalidate(c, row['id'])
                c.commit()
                raise
            c.execute('UPDATE guided_events SET status=?,data=? WHERE id=?', ('failed' if error else 'ready',
                      _json(dict(message=error) if error else result), event_id))
            c.execute('UPDATE guided_sessions SET version=version+1,updated=? WHERE id=?', (dt.datetime.now(TZ).isoformat(), row['id']))
            return self._result(c, child['id'])
