"""Parent-only teacher records: observable teaching evidence, never personality scores."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import re
import sqlite3
from urllib.parse import urlsplit

import family_agent
import family_teacher_public

TEACHER_FIELDS = {'display_name', 'subject', 'child_ids', 'source_ids', 'archived', 'public_url'}
OBSERVATION_FIELDS = {'teacher_id', 'day', 'kind', 'target', 'child_id', 'behavior', 'teacher_reason',
                      'parent_note', 'source_url', 'source_id', 'message_id', 'status'}


class TeacherError(ValueError):
    def __init__(self, message, status=400, code='invalid_teacher'):
        super().__init__(message); self.status = status; self.code = code


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def observation_scope(observation, teacher):
    if 'scope_child_id' in observation: return observation['scope_child_id']
    if observation['child_id']: return observation['child_id']
    # Legacy single-child profiles at version 1 have never been reassigned. Shared scope stays unknown.
    return teacher['child_ids'][0] if teacher['version'] == 1 and len(teacher['child_ids']) == 1 else ''


def _text(obj, key, limit, required=False):
    value = obj.get(key, '')
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' or ord(c) == 127 for c in value):
        raise TeacherError('字段格式或长度不正确：' + key)
    value = value.strip()
    if required and not value: raise TeacherError('请填写：' + key)
    return value


def _ids(obj, key, allowed, required=False):
    values = obj.get(key, [])
    if (not isinstance(values, list) or len(values) > 20 or required and not values
            or any(not isinstance(v, str) or v not in allowed for v in values) or len(set(values)) != len(values)):
        raise TeacherError('请选择已存在且不重复的' + ('孩子' if key == 'child_ids' else '群来源'))
    return sorted(values)


def _request(obj, fields, prefix):
    if not isinstance(obj, dict) or set(obj) - fields - {'id', 'version', 'request_key'}:
        raise TeacherError('档案字段不正确')
    key = _text(obj, 'request_key', 128)
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key): raise TeacherError('请保留本次提交标识后重试')
    ident = _text(obj, 'id', 40)
    if ident and not re.fullmatch(prefix + r'[a-f0-9]{24}', ident): raise TeacherError('记录编号不正确')
    version = obj.get('version', 0)
    if type(version) is not int or not 0 <= version < 2147483647: raise TeacherError('记录版本不正确')
    try: digest = hashlib.sha256(_json(obj).encode()).hexdigest()
    except (ValueError, TypeError): raise TeacherError('档案字段不正确') from None
    return ident or prefix + hashlib.sha256(key.encode()).hexdigest()[:24], version, key, digest


class Store:
    def __init__(self, app):
        self.app = app
        self.agent = app.agent_store()
        with self._db() as c:
            for table in ('teachers', 'teacher_observations'):
                c.execute('CREATE TABLE IF NOT EXISTS ' + table + ''' (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL,
                    last_request_key TEXT NOT NULL, last_request_hash TEXT NOT NULL)''')
            family_teacher_public.init(c)

    @contextmanager
    def _db(self):
        c = self.app.connect(); c.row_factory = sqlite3.Row
        try:
            yield c; c.commit()
        except Exception:
            c.rollback(); raise
        finally: c.close()

    def _sources(self):
        try:
            return [{key: row[key] for key in ('id', 'name', 'platform', 'child_id', 'enabled')}
                    for row in self.agent._config()['sources']], ''
        except family_agent.AgentError:
            return [], '群来源暂时无法核对；仍可手动记录，来源关联请修复配置后重试'

    @staticmethod
    def _view(row):
        return dict(json.loads(row['data']), **{key: row[key] for key in ('id', 'version', 'created', 'updated')})

    def _teacher(self, c, row):
        result = self._view(row)
        result['public_info'] = family_teacher_public.snapshot(c, result['id'], result['public_url'])
        return result

    def snapshot(self):
        sources, error = self._sources()
        with self._db() as c:
            return dict(teachers=[self._teacher(c, r) for r in c.execute('SELECT * FROM teachers ORDER BY created,id')],
                        observations=[self._view(r) for r in c.execute('SELECT * FROM teacher_observations ORDER BY updated DESC,id')],
                        children=[{key: p[key] for key in ('id', 'name')} for p in self.app.profiles(c)],
                        sources=sources, source_error=error)

    @staticmethod
    def _persist(c, table, request, fields, old):
        ident, version, key, digest = request
        if old and old['last_request_key'] == key:
            if old['last_request_hash'] == digest: return old
            raise TeacherError('同一提交标识的内容不同，请先核对原提交', 409, 'teacher_request_conflict')
        if (old is None and version != 0) or (old is not None and old['version'] != version):
            raise TeacherError('记录已更新，请刷新核对；当前输入未覆盖', 409, 'teacher_conflict')
        now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds')
        values = (ident, _json(fields), version + 1, old['created'] if old else now, now, key, digest)
        c.execute('INSERT INTO ' + table + ''' VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            data=excluded.data,version=excluded.version,updated=excluded.updated,
            last_request_key=excluded.last_request_key,last_request_hash=excluded.last_request_hash''', values)
        return c.execute('SELECT * FROM ' + table + ' WHERE id=?', (ident,)).fetchone()

    def save_teacher(self, obj):
        request = _request(obj, TEACHER_FIELDS, 'TEACH-')
        if type(obj.get('archived', False)) is not bool: raise TeacherError('归档状态不正确')
        fields = dict(display_name=_text(obj, 'display_name', 80, True), subject=_text(obj, 'subject', 80),
                      archived=obj.get('archived', False))
        if any('\n' in value or '\t' in value for value in (fields['display_name'], fields['subject'])):
            raise TeacherError('老师称呼和学科请使用单行文字')
        try: fields['public_url'] = family_teacher_public.validate_url(obj.get('public_url', ''))
        except ValueError as error: raise TeacherError(str(error)) from None
        sources, source_error = self._sources()
        if source_error and obj.get('source_ids'): raise TeacherError(source_error, 409, 'teacher_source_unavailable')
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            fields['child_ids'] = _ids(obj, 'child_ids', {p['id'] for p in self.app.profiles(c)}, True)
            fields['source_ids'] = _ids(obj, 'source_ids', {s['id'] for s in sources if s['child_id'] in fields['child_ids']})
            old = c.execute('SELECT * FROM teachers WHERE id=?', (request[0],)).fetchone()
            if old:
                for row in c.execute('SELECT id,data FROM teacher_observations'):
                    observation = json.loads(row['data'])
                    if observation['teacher_id'] != request[0]: continue
                    scope = observation_scope(observation, self._view(old))
                    if (scope and scope not in fields['child_ids']
                            or observation['source_id'] and observation['source_id'] not in fields['source_ids']):
                        raise TeacherError('已有观察使用这位孩子或群来源，请先更正观察，或归档老师并保留原关联',
                                           409, 'teacher_binding_conflict')
                    if 'scope_child_id' not in observation:
                        # Freeze legacy scope before any profile edit can change its inference.
                        observation['scope_child_id'] = scope
                        c.execute('UPDATE teacher_observations SET data=? WHERE id=?', (_json(observation), row['id']))
            row = self._persist(c, 'teachers', request, fields, old)
            return dict(ok=True, teacher=self._teacher(c, row))

    def save_observation(self, obj):
        request = _request(obj, OBSERVATION_FIELDS, 'TEACHOBS-')
        fields = {key: _text(obj, key, limit, key in {'teacher_id', 'day', 'kind', 'target', 'behavior'}) for key, limit in (
            ('teacher_id', 40), ('day', 10), ('kind', 20), ('target', 20), ('child_id', 80), ('behavior', 3000),
            ('teacher_reason', 2000), ('parent_note', 2000), ('source_url', 2000), ('source_id', 160), ('message_id', 160))}
        fields['status'] = _text(obj, 'status', 20) if 'status' in obj else 'active'
        if fields['kind'] not in {'requirement', 'praise', 'preference'}: raise TeacherError('观察类别不正确')
        if fields['target'] not in {'household', 'other_students', 'class'}: raise TeacherError('观察对象不正确')
        if fields['status'] not in {'active', 'withdrawn'}: raise TeacherError('观察状态不正确')
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', fields['day']): raise ValueError()
            if dt.date.fromisoformat(fields['day']) > dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date():
                raise ValueError()
        except ValueError: raise TeacherError('观察日期须为今天或过去的有效日期') from None
        if fields['source_url']:
            try:
                url = urlsplit(fields['source_url'])
                if (url.scheme not in {'https', 'http'} or not url.hostname or url.username is not None
                        or url.password is not None or any(c.isspace() for c in fields['source_url']) or url.port == 0):
                    raise ValueError()
            except ValueError: raise TeacherError('来源链接须为不含账号口令的 HTTP(S) 地址') from None
        if fields['target'] != 'household' and fields['child_id']:
            raise TeacherError('其他同学或全班观察只记录行为，不关联本家孩子或他人姓名')
        if fields['message_id'] and not fields['source_id']: raise TeacherError('关联已采集消息时须同时选择群来源')
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            teacher_row = c.execute('SELECT * FROM teachers WHERE id=?', (fields['teacher_id'],)).fetchone()
            if teacher_row is None: raise TeacherError('老师档案不存在', 404, 'teacher_missing')
            teacher = json.loads(teacher_row['data'])
            source = None
            if fields['target'] == 'household' and (fields['child_id'] not in teacher['child_ids']
                    or fields['child_id'] not in {p['id'] for p in self.app.profiles(c)}):
                raise TeacherError('请选择这位老师关联的本家孩子')
            if fields['source_id']:
                sources, source_error = self._sources()
                source = next((s for s in sources if s['id'] == fields['source_id']), None)
                if source_error: raise TeacherError(source_error, 409, 'teacher_source_unavailable')
                if (source is None or source['id'] not in teacher['source_ids'] or source['child_id'] not in teacher['child_ids']
                        or fields['child_id'] and fields['child_id'] != source['child_id']):
                    raise TeacherError('群来源不属于这位老师与所选孩子', 403, 'teacher_source_conflict')
                try:
                    saved = c.execute('SELECT * FROM agent_sources WHERE id=?', (source['id'],)).fetchone()
                    self.agent._binding(source, saved)
                except family_agent.AgentError as error:
                    raise TeacherError(str(error), error.status, 'teacher_source_conflict') from None
                if fields['message_id']:
                    try:
                        self.agent._message_context(c, dict(child_id=source['child_id'], source_id=source['id'], message_id=fields['message_id']))
                    except family_agent.AgentError as error:
                        raise TeacherError(str(error), error.status, 'teacher_message_unavailable') from None
            old = c.execute('SELECT * FROM teacher_observations WHERE id=?', (request[0],)).fetchone()
            if old and json.loads(old['data'])['teacher_id'] != fields['teacher_id']:
                raise TeacherError('已有观察不能改给另一位老师；请撤回后在正确档案新建', 409, 'teacher_binding_conflict')
            if teacher['archived'] and old is None: raise TeacherError('老师档案已归档，请先恢复后新增观察', 409)
            fields['scope_child_id'] = (fields['child_id'] or (source['child_id'] if source else
                teacher['child_ids'][0] if len(teacher['child_ids']) == 1 else ''))
            if old:
                previous = json.loads(old['data'])
                if all(previous[key] == fields[key] for key in ('target', 'child_id', 'source_id')):
                    fields['scope_child_id'] = observation_scope(previous, self._view(teacher_row))
            row = self._persist(c, 'teacher_observations', request, fields, old)
            return dict(ok=True, observation=self._view(row))
