"""After-school time accounts attached to the existing family tasks."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import math
import re
import sqlite3

TZ = dt.timezone(dt.timedelta(hours=8))
RESULTS = ('完成', '做了一部分', '需要帮助')


class StudyError(ValueError):
    def __init__(self, message, status=400, code='invalid_study'):
        super().__init__(message); self.status = status; self.code = code


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _text(obj, key, limit, default=''):
    value = obj.get(key, default)
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise StudyError('字段格式或长度不正确：' + key)
    return value.strip()


def _day(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): raise ValueError()
        dt.date.fromisoformat(value)
    except ValueError: raise StudyError('请选择有效日期') from None
    return value


def _minutes(value, optional=True):
    if value is None and optional: return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1440:
        raise StudyError('分钟数须为 0 到 1440；不知道时可以留空')
    return round(value, 2)


def _clock(value):
    if not isinstance(value, str) or value and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise StudyError('时间须为 HH:MM；不知道时可以留空')
    return value


def _minute(clock):
    hours, minutes = map(int, clock.split(':')); return hours * 60 + minutes


def task_changed(c, task_id, now):
    """Pause and invalidate linked timers inside the original task's transaction."""
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='study_items'").fetchone(): return
    for old in c.execute('SELECT * FROM study_items WHERE task_id=?', (task_id,)).fetchall():
        seconds, review = Store._elapsed(old, now)
        c.execute('''UPDATE study_items SET elapsed_seconds=?,running_since=NULL,status=?,time_needs_review=?,
            version=version+1,last_request_key='',last_request_hash='' WHERE id=?''',
            (seconds, 'paused' if old['running_since'] else old['status'], int(review), old['id']))


class Store:
    def __init__(self, app, authorize=None):
        self.app = app
        self.authorize = authorize
        self.actor = 'child' if authorize else 'parent'
        with self._db() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS study_days (
                child_id TEXT NOT NULL, day TEXT NOT NULL, start_time TEXT NOT NULL DEFAULT '',
                stop_time TEXT NOT NULL DEFAULT '', bed_time TEXT NOT NULL DEFAULT '',
                closed_at TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL,
                last_request_key TEXT NOT NULL, last_request_hash TEXT NOT NULL,
                PRIMARY KEY(child_id,day))''')
            c.execute('''CREATE TABLE IF NOT EXISTS study_items (
                id TEXT PRIMARY KEY, child_id TEXT NOT NULL, day TEXT NOT NULL, task_id TEXT NOT NULL,
                title TEXT NOT NULL, subject TEXT NOT NULL, planned_minutes REAL,
                elapsed_seconds REAL NOT NULL DEFAULT 0, running_since TEXT,
                status TEXT NOT NULL DEFAULT 'ready', result TEXT NOT NULL DEFAULT '',
                assistance TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', record_id INTEGER,
                record_hash TEXT NOT NULL DEFAULT '',
                time_source TEXT NOT NULL DEFAULT '', time_needs_review INTEGER NOT NULL DEFAULT 0,
                task_completion_note TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL,
                creation_hash TEXT NOT NULL, last_request_key TEXT NOT NULL, last_request_hash TEXT NOT NULL,
                UNIQUE(child_id,day,task_id))''')
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS study_one_running ON study_items(child_id) WHERE running_since IS NOT NULL')
            if 'record_hash' not in {r['name'] for r in c.execute('PRAGMA table_info(study_items)')}:
                c.execute("ALTER TABLE study_items ADD COLUMN record_hash TEXT NOT NULL DEFAULT ''")
            if 'result_actor' not in {r['name'] for r in c.execute('PRAGMA table_info(study_items)')}:
                c.execute("ALTER TABLE study_items ADD COLUMN result_actor TEXT NOT NULL DEFAULT 'parent'")

    @contextmanager
    def _db(self):
        c = self.app.connect(); c.row_factory = sqlite3.Row
        try:
            yield c; c.commit()
        except Exception:
            c.rollback(); raise
        finally: c.close()

    def _now(self):
        return dt.datetime.now(TZ)

    def _child(self, c, child_id):
        if self.authorize: self.authorize(c, child_id)
        if not isinstance(child_id, str): raise StudyError('请选择孩子')
        child = next((p for p in self.app.profiles(c) if p['id'] == child_id), None)
        if child is None: raise StudyError('孩子不存在', 404, 'study_child_missing')
        return child

    def _child_edit(self, c, child, day, old):
        if self.actor != 'child': return
        today=self._now().date().isoformat()
        if day>today or old is None and day!=today:
            raise StudyError('只能新增今天的功课，过去的功课可在已有安排中核对')
        if old is None: return
        task=next((t for t in self.app.tasks(c) if t['id']==old['task_id'] and t['child']==child['name']),None)
        update=c.execute('SELECT status FROM task_updates WHERE id=?',(old['task_id'],)).fetchone()
        if task is None or self.app.task_status(task,update['status'] if update else None) in self.app.TASK_CLOSED:
            raise StudyError('这项功课已结束或原事项需核对，请家长处理',409,'study_task_closed')
        if old['result_actor']=='parent' and old['result']=='完成':
            raise StudyError('家长已确认完成，请家长核对后再调整',409,'study_parent_confirmed')

    def _request(self, obj, fields):
        if not isinstance(obj, dict) or set(obj) - set(fields) - {'child_id', 'day', 'request_key', 'version'}:
            raise StudyError('作息字段不正确')
        day = _day(obj.get('day')); key = _text(obj, 'request_key', 128)
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key): raise StudyError('请保留本次提交标识后重试')
        version = obj.get('version', 0)
        if type(version) is not int or not 0 <= version < 2147483647: raise StudyError('作息版本不正确，请刷新')
        try: digest = hashlib.sha256(_json(obj).encode()).hexdigest()
        except (ValueError, TypeError): raise StudyError('作息字段不正确') from None
        return obj.get('child_id'), day, key, version, digest

    @staticmethod
    def _replay(row, key, version, digest):
        if row is not None and row['last_request_key'] == key:
            if row['last_request_hash'] == digest: return True
            raise StudyError('同一提交标识的内容不同，请先核对原提交', 409, 'study_request_conflict')
        if (row is None and version != 0) or (row is not None and row['version'] != version):
            raise StudyError('记录已更新，请刷新核对；当前输入未覆盖', 409, 'study_conflict')
        return False

    @staticmethod
    def _day_row(c, child_id, day):
        row = c.execute('SELECT * FROM study_days WHERE child_id=? AND day=?', (child_id, day)).fetchone()
        if row: return dict(row)
        return dict(child_id=child_id, day=day, start_time='', stop_time='', bed_time='', closed_at='', version=0)

    def save_day(self, obj):
        child_id, day, key, version, digest = self._request(obj, {'start_time', 'stop_time', 'bed_time'})
        values = {k: _clock(obj.get(k, '')) for k in ('start_time', 'stop_time', 'bed_time')}
        start, stop, bed = (values[k] for k in ('start_time', 'stop_time', 'bed_time'))
        if start and stop and start >= stop or stop and bed and stop > bed or start and bed and start >= bed:
            raise StudyError('同日须开始早于收尾、收尾不晚于休息；跨日安排请按次日另记')
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE'); self._child(c, child_id)
            old = c.execute('SELECT * FROM study_days WHERE child_id=? AND day=?', (child_id, day)).fetchone()
            if not self._replay(old, key, version, digest):
                c.execute('''INSERT INTO study_days VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(child_id,day)
                    DO UPDATE SET start_time=excluded.start_time,stop_time=excluded.stop_time,bed_time=excluded.bed_time,
                    version=excluded.version,last_request_key=excluded.last_request_key,last_request_hash=excluded.last_request_hash''',
                    (child_id, day, start, stop, bed, old['closed_at'] if old else '', version+1, key, digest))
        return dict(ok=True, **self.snapshot(child_id, day))

    def save_item(self, obj):
        child_id, day, key, version, digest = self._request(obj, {'id', 'task_id', 'title', 'subject', 'planned_minutes'})
        ident = _text(obj, 'id', 30)
        if ident and not re.fullmatch(r'STUDY-[a-f0-9]{24}', ident): raise StudyError('功课编号不正确')
        creating = not ident
        ident = ident or 'STUDY-' + hashlib.sha256(_json([child_id, day, key]).encode()).hexdigest()[:24]
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE'); child = self._child(c, child_id)
            old = c.execute('SELECT * FROM study_items WHERE id=?', (ident,)).fetchone()
            if old and (old['child_id'] != child_id or old['day'] != day): raise StudyError('功课归属不正确')
            self._child_edit(c,child,day,old)
            if creating and old:
                # An old creation request must not overwrite subsequent timer or feedback changes.
                if old['last_request_key'] == key and old['creation_hash'] == digest:
                    pass
                else: raise StudyError('这次添加已保存并有后续进展，请刷新核对', 409, 'study_conflict')
            elif not self._replay(old, key, version, digest):
                if not creating and old is None: raise StudyError('功课不存在', 404, 'study_item_missing')
                subject = _text(obj, 'subject', 80, old['subject'] if old else '')
                planned = _minutes(obj.get('planned_minutes', old['planned_minutes'] if old else None))
                if old:
                    if 'task_id' in obj and obj['task_id'] != old['task_id'] or 'title' in obj and obj['title'] != old['title']:
                        raise StudyError('原待办和标题保持不变，请修改原待办或添加另一项功课')
                    c.execute('UPDATE study_items SET subject=?,planned_minutes=?,version=?,last_request_key=?,last_request_hash=? WHERE id=?',
                        (subject, planned, version+1, key, digest, ident))
                    if old['record_id']:
                        updated = dict(c.execute('SELECT * FROM study_items WHERE id=?', (ident,)).fetchone())
                        self._record(c, updated, child)
                        c.execute('UPDATE study_items SET record_hash=? WHERE id=?', (updated['record_hash'], ident))
                else:
                    task_id = _text(obj, 'task_id', 30); title = _text(obj, 'title', 200)
                    if task_id:
                        task = next((t for t in self.app.tasks(c) if t['id'] == task_id and t['child'] == child['name']), None)
                        if task is None: raise StudyError('只能加入同一个孩子的现有待办')
                        update = c.execute('SELECT status FROM task_updates WHERE id=?', (task_id,)).fetchone()
                        if self.app.task_status(task, update['status'] if update else None) in self.app.TASK_CLOSED:
                            raise StudyError('这项待办已经结束，请先核对原待办', 409, 'study_task_closed')
                        title = task['title']
                    else:
                        if not title: raise StudyError('请填写功课，或选择已有待办')
                        task_id = ident
                        c.execute('INSERT INTO manual_tasks VALUES (?,?,?,?,?,?,?)',
                            (task_id, child['name'], title, day, '待跟进', '孩子自述功课，待家长核对' if self.actor=='child' else '家庭放学后录入', ''))
                    if c.execute('SELECT 1 FROM study_items WHERE child_id=? AND day=? AND task_id=?', (child_id, day, task_id)).fetchone():
                        raise StudyError('这项待办已加入当天安排，请刷新核对', 409, 'study_task_duplicate')
                    c.execute('''INSERT INTO study_items (id,child_id,day,task_id,title,subject,planned_minutes,version,
                        creation_hash,last_request_key,last_request_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                        (ident, child_id, day, task_id, title, subject, planned, 1, digest, key, digest))
        return dict(ok=True, **self.snapshot(child_id, day))

    @staticmethod
    def _elapsed(row, now):
        seconds = row['elapsed_seconds']; review = bool(row['time_needs_review'])
        if row['running_since']:
            start = dt.datetime.fromisoformat(row['running_since'])
            delta = (now - start).total_seconds()
            review = review or delta < 0 or delta > 4*3600 or start.astimezone(TZ).date() != now.astimezone(TZ).date()
            seconds += max(0, delta)
        return round(seconds, 2), review

    def _item(self, row, now):
        item = dict(row); seconds, review = self._elapsed(row, now)
        item.update(elapsed_seconds=seconds, time_needs_review=review,
            actual_minutes=round(seconds/60, 2) if row['time_source'] and not review else None)
        for key in ('creation_hash', 'last_request_key', 'last_request_hash', 'task_completion_note', 'record_hash'): item.pop(key, None)
        return item

    def action(self, obj):
        child_id, day, key, version, digest = self._request(obj, {'action', 'id', 'result', 'assistance', 'note', 'actual_minutes'})
        action = _text(obj, 'action', 30); now = self._now()
        if action not in ('start', 'pause', 'finish', 'manual', 'close_day'): raise StudyError('作息操作不正确')
        allowed={'child_id','day','request_key','version','action'} | ({'id'} if action != 'close_day' else set())
        if action == 'finish': allowed |= {'result','assistance','note','actual_minutes'}
        if action == 'manual': allowed.add('actual_minutes')
        if set(obj)-allowed: raise StudyError('这项操作的字段不正确')
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE'); child = self._child(c, child_id)
            if action == 'close_day':
                old = c.execute('SELECT * FROM study_days WHERE child_id=? AND day=?', (child_id, day)).fetchone()
                if not self._replay(old, key, version, digest):
                    if day != now.date().isoformat(): raise StudyError('当晚收尾只记录今天，不补猜过去的收尾时间')
                    if c.execute('SELECT 1 FROM study_items WHERE child_id=? AND running_since IS NOT NULL', (child_id,)).fetchone():
                        raise StudyError('请先暂停正在计时的功课，再记录当晚收尾')
                    values = self._day_row(c, child_id, day)
                    c.execute('''INSERT INTO study_days VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(child_id,day)
                        DO UPDATE SET closed_at=excluded.closed_at,version=excluded.version,
                        last_request_key=excluded.last_request_key,last_request_hash=excluded.last_request_hash''',
                        (child_id, day, values['start_time'], values['stop_time'], values['bed_time'], now.isoformat(), version+1, key, digest))
            else:
                ident = _text(obj, 'id', 30)
                old = c.execute('SELECT * FROM study_items WHERE id=?', (ident,)).fetchone()
                if old is None or old['child_id'] != child_id or old['day'] != day: raise StudyError('功课不存在或归属不正确', 404, 'study_item_missing')
                self._child_edit(c,child,day,old)
                if not self._replay(old, key, version, digest):
                    row = dict(old); seconds, review = self._elapsed(row, now)
                    if action in ('start', 'finish'):
                        task = next((t for t in self.app.tasks(c) if t['id'] == row['task_id'] and t['child'] == child['name']), None)
                        if task is None: raise StudyError('原待办归属暂时无法核对，请刷新后重试', 409, 'study_task_changed')
                        update = c.execute('SELECT status FROM task_updates WHERE id=?', (row['task_id'],)).fetchone()
                        source_status = self.app.task_status(task, update['status'] if update else None)
                        if source_status in self.app.TASK_DISMISSED:
                            raise StudyError('原待办已搁置；要继续请先到原待办恢复跟进', 409, 'study_task_dismissed')
                        if action == 'start' and source_status in self.app.TASK_CLOSED:
                            raise StudyError('原待办已经结束；需要继续时请先核对原待办', 409, 'study_task_closed')
                    if action == 'start':
                        if day != now.date().isoformat(): raise StudyError('实时计时只用于今天；过去用时请手动补录')
                        if row['result'] == '完成': raise StudyError('这项功课已确认完成；需要继续时先更正本次结果')
                        if review: raise StudyError('这段计时需要核对，请先手动补录实际分钟')
                        if c.execute('SELECT 1 FROM study_items WHERE child_id=? AND running_since IS NOT NULL', (child_id,)).fetchone():
                            raise StudyError('这个孩子已有功课在计时，请先暂停上一项', 409, 'study_already_running')
                        row.update(running_since=now.isoformat(), status='running', time_source='mixed' if row['time_source'] in ('manual','mixed') else 'timer')
                        c.execute("UPDATE study_days SET closed_at='',version=version+1,last_request_key='',last_request_hash='' WHERE child_id=? AND day=? AND closed_at<>''", (child_id, day))
                    elif action == 'pause':
                        if row['running_since'] is None: raise StudyError('这项功课没有正在计时，请刷新核对', 409, 'study_not_running')
                        row.update(elapsed_seconds=seconds, running_since=None, status='paused', time_needs_review=int(review))
                    else:
                        row.update(elapsed_seconds=seconds, running_since=None, time_needs_review=int(review))
                        if 'actual_minutes' in obj or action == 'manual':
                            row.update(elapsed_seconds=_minutes(obj.get('actual_minutes'), False)*60, time_source='manual', time_needs_review=0)
                        if action == 'manual':
                            if row['status'] == 'running': row['status'] = 'paused'
                        else:
                            result = _text(obj, 'result', 30)
                            if result not in RESULTS: raise StudyError('请选择完成、做了一部分或需要帮助')
                            assistance = _text(obj, 'assistance', 30, row['assistance'])
                            if assistance not in self.app.ASSISTANCE: raise StudyError('帮助情况不正确')
                            note_default='' if self.actor=='child' and row['result_actor']=='parent' else row['note']
                            row.update(status='finished', result=result, result_actor=self.actor, assistance=assistance, note=_text(obj, 'note', 2000, note_default))
                        if row['record_id'] or action == 'finish': self._record(c, row, child, update_task=action == 'finish')
                    row.update(version=version+1, last_request_key=key, last_request_hash=digest)
                    fields = [k for k in row if k != 'id']
                    c.execute('UPDATE study_items SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', [row[k] for k in fields]+[ident])
        return dict(ok=True, **self.snapshot(child_id, day))

    def _record(self, c, row, child, update_task=False):
        actual = None if row['time_needs_review'] or not row['time_source'] else round(row['elapsed_seconds']/60, 2)
        note = '\n'.join((
            '计划用时：'+(str(row['planned_minutes'])+' 分钟' if row['planned_minutes'] is not None else '未估计'),
            '实际用时：'+(str(actual)+' 分钟' if actual is not None else '待核对' if row['time_needs_review'] else '未记录'),
            '计时来源：'+({'timer':'页面计时（不等于全程专注）','manual':'家庭手动补录','mixed':'手动补录及页面计时（不等于全程专注）'}.get(row['time_source'], '未记录')),
            '本次结果：'+row['result'], '结果来源：'+('孩子自述，待家长核对' if row['result_actor']=='child' else '家长记录或核对'), '帮助情况：'+(row['assistance'] or '未填写'),
            '卡点或说明：'+(row['note'] or '未填写')))
        now = self._now().isoformat(); source = '作息记录:'+row['id']
        title = '作业复盘：'+row['title']
        if len(title)>200: title=title[:199]+'…'
        def owned_hash(record):
            return hashlib.sha256(_json({k:record[k] for k in ('day','category','title','subject','note','source','assistance')}).encode()).hexdigest()
        if row['record_id']:
            previous = c.execute('SELECT * FROM records WHERE id=?', (row['record_id'],)).fetchone()
            if previous is None or previous['child'] != child['name'] or previous['source'] != source:
                raise StudyError('关联学习记录已更正归属或来源，请先核对', 409, 'study_record_changed')
            if row['record_hash'] and owned_hash(previous) != row['record_hash']:
                raise StudyError('学习记录已在别处更正，请保留当前输入并核对；作息更正尚未保存', 409, 'study_record_changed')
            if any(previous[k] != value for k, value in (('title', title), ('subject', row['subject']), ('note', note), ('assistance', row['assistance']))):
                c.execute('INSERT INTO revisions (record_id,previous,changed) VALUES (?,?,?)', (row['record_id'], _json(dict(previous)), now))
                c.execute('UPDATE records SET title=?,subject=?,note=?,assistance=?,created=? WHERE id=?',
                    (title, row['subject'], note, row['assistance'], now, row['record_id']))
        else:
            row['record_id'] = c.execute('''INSERT INTO records (child,day,category,subject,title,note,source,created,assistance)
                VALUES (?,?,?,?,?,?,?,?,?)''', (child['name'], row['day'], '学习进展', row['subject'], title, note, source, now, row['assistance'])).lastrowid
        row['record_hash'] = owned_hash(c.execute('SELECT * FROM records WHERE id=?', (row['record_id'],)).fetchone())
        if not update_task or row['result_actor']=='child': return
        task = next((t for t in self.app.tasks(c) if t['id'] == row['task_id'] and t['child'] == child['name']), None)
        if task is None: raise StudyError('原待办归属暂时无法核对，请刷新后重试', 409, 'study_task_changed')
        previous = c.execute('SELECT * FROM task_updates WHERE id=?', (row['task_id'],)).fetchone()
        if self.app.task_status(task, previous['status'] if previous else None) in self.app.TASK_DISMISSED:
            raise StudyError('原待办已搁置；要继续请先到原待办恢复跟进', 409, 'study_task_dismissed')
        completion = '家长确认本次功课完成；作息记录 '+row['id']+'。'+('说明：'+row['note'] if row['note'] else '')
        status = '已完成' if row['result'] == '完成' else ''
        if not status and previous and previous['status'] == '已完成' and previous['note'] == row['task_completion_note']:
            status = '进行中'; completion = '家长更正本次结果为'+row['result']+'；作息记录 '+row['id']+'。'
        if status and (not previous or previous['status'] != status or previous['note'] != completion):
            if previous and not c.execute('SELECT 1 FROM task_history WHERE task_id=?', (row['task_id'],)).fetchone():
                c.execute('INSERT INTO task_history (task_id,status,note,updated) VALUES (?,?,?,?)', tuple(previous))
            values = (row['task_id'], status, completion, now)
            c.execute('INSERT INTO task_history (task_id,status,note,updated) VALUES (?,?,?,?)', values)
            c.execute('INSERT OR REPLACE INTO task_updates VALUES (?,?,?,?)', values)
        if row['result'] == '完成': row['task_completion_note'] = completion

    def snapshot(self, child_id, day):
        day = _day(day); now = self._now()
        date = dt.date.fromisoformat(day)
        first = (date-dt.timedelta(days=min(6,date.toordinal()-1))).isoformat()
        with self._db() as c:
            if self.authorize: c.execute('BEGIN IMMEDIATE')
            child = self._child(c, child_id)
            active=c.execute('SELECT * FROM study_items WHERE child_id=? AND running_since IS NOT NULL', (child_id,)).fetchone()
            active_item=({k:active[k] for k in ('id','day','title','running_since')} | {'time_needs_review':self._elapsed(active,now)[1]}) if active else None
            plan = self._day_row(c, child_id, day)
            plan = {k: plan[k] for k in ('child_id','day','start_time','stop_time','bed_time','closed_at','version')}
            week_items = [self._item(r, now) for r in c.execute('SELECT * FROM study_items WHERE child_id=? AND day BETWEEN ? AND ? ORDER BY day,rowid', (child_id,first,day))]
            items = [r for r in week_items if r['day'] == day]
            days = {r['day']:dict(r) for r in c.execute('SELECT * FROM study_days WHERE child_id=? AND day BETWEEN ? AND ?', (child_id,first,day))}
            updates = {r['id']:r['status'] for r in c.execute('SELECT id,status FROM task_updates')}
            tasks = {t['id']:t for t in self.app.tasks(c)}
            for row in week_items:
                task = tasks.get(row['task_id'])
                if task and task['child'] != child['name']: task = None
                row['source_task_status'] = self.app.task_status(task, updates.get(task['id'])) if task else '待核对'
                # Derive current requirements; never retain a second editable copy on a timer.
                missing = None if row['task_id'] else ''
                row['source_task_action'] = task.get('action', '') if task else missing
                row['source_task_due'] = task.get('due', '') if task else missing
                row['source_task_next_action'] = (task.get('focus') or {}).get('next_action', '') if task else missing
            used = {r['task_id'] for r in items}
            available = [dict(id=t['id'],title=t['title'],due=t['due'],status=self.app.task_status(t,updates.get(t['id'])))
                for t in tasks.values() if t['child'] == child['name'] and t['id'] not in used
                and self.app.task_status(t,updates.get(t['id'])) not in self.app.TASK_CLOSED]
        planned_items = [r for r in items if r['source_task_status'] not in self.app.TASK_DISMISSED]
        summary = dict(planned_minutes=round(sum(r['planned_minutes'] or 0 for r in planned_items),2),
            remaining_minutes=round(sum(max(0,r['planned_minutes']-(r['actual_minutes'] or 0)) for r in planned_items if r['planned_minutes'] is not None and r['result'] != '完成'),2),
            available_minutes=None, over_budget_minutes=None, remaining_available_minutes=None, remaining_over_budget_minutes=None,
            unknown_estimates=sum(r['planned_minutes'] is None for r in planned_items),
            recorded_actual_minutes=round(sum(r['actual_minutes'] or 0 for r in items),2),
            unfinished_count=sum(r['result'] != '完成' for r in planned_items), finished_count=sum(r['result'] == '完成' for r in items),
            warning='', source_gap='')
        try: calendar = self.app.calendar_store().snapshot(day,day)
        except (OSError,ValueError,sqlite3.Error,TypeError): calendar = dict(events=[], source_error='当日日历暂时无法核对')
        gaps = [calendar.get('source_error','')] if calendar.get('source_error') else []
        intervals = []
        for event in calendar['events']:
            if child_id not in event['child_ids'] or event['status'] != 'confirmed': continue
            task = tasks.get(event.get('task_id'))
            if task and task['child'] == child['name'] and self.app.task_status(task,updates.get(task['id'])) in self.app.TASK_DISMISSED: continue
            if not event['start_time'] or not event['end_time']:
                gaps.append('有已确认安排未填完整钟点'); continue
            if plan['start_time'] and plan['stop_time']:
                start=max(_minute(plan['start_time']),_minute(event['start_time'])); stop=min(_minute(plan['stop_time']),_minute(event['end_time']))
                if start<stop: intervals.append((start,stop))
        if plan['start_time'] and plan['stop_time']:
            def available_between(start, stop):
                covered=0; end=-1
                for begin,finish in sorted(intervals):
                    begin=max(begin,start); finish=min(finish,stop)
                    if begin<finish:
                        covered += max(0,finish-max(begin,end)); end=max(end,finish)
                return max(0,round(stop-start-covered,2))
            summary['available_minutes'] = available_between(_minute(plan['start_time']),_minute(plan['stop_time']))
            summary['over_budget_minutes'] = max(0,round(summary['planned_minutes']-summary['available_minutes'],2))
            if day == now.date().isoformat():
                summary['remaining_available_minutes'] = available_between(max(_minute(plan['start_time']),now.hour*60+now.minute+now.second/60),_minute(plan['stop_time']))
                summary['remaining_over_budget_minutes'] = max(0,round(summary['remaining_minutes']-summary['remaining_available_minutes'],2))
        warning=[]
        if summary['unknown_estimates']: warning.append(str(summary['unknown_estimates'])+' 项还没估时间')
        exhausted=sum(r['result'] != '完成' and r['planned_minutes'] is not None and r['actual_minutes'] is not None and r['actual_minutes']>=r['planned_minutes'] for r in planned_items)
        summary['needs_reestimate_count']=exhausted
        summary['unknown_remaining_count']=exhausted+sum(r['result']!='完成' and r['planned_minutes'] is None for r in planned_items)
        if exhausted: warning.append(str(exhausted)+' 项未完成但已达到预计用时，需要重估')
        if any(r['time_needs_review'] for r in items): warning.append('有计时需要核对，请核对实际分钟并按真实用时补录')
        if summary['over_budget_minutes']: warning.append('已估功课超过可用时间 '+str(summary['over_budget_minutes'])+' 分钟')
        if summary['remaining_over_budget_minutes']: warning.append('剩余功课预计超过今晚剩余时间 '+str(summary['remaining_over_budget_minutes'])+' 分钟')
        summary.update(warning='；'.join(warning),source_gap='；'.join(dict.fromkeys(gaps)))
        week=[]
        for date in sorted({r['day'] for r in week_items} | {d for d,r in days.items() if r['closed_at']}):
            entries=[r for r in week_items if r['day']==date]; unknown=sum(r['actual_minutes'] is None for r in entries)
            known=round(sum(r['actual_minutes'] or 0 for r in entries),2)
            week.append(dict(day=date,actual_minutes=None if unknown else known,known_actual_minutes=known,
                unknown_actual_count=unknown,item_count=len(entries),finished_count=sum(r['result']=='完成' for r in entries),
                needs_help_count=sum(r['result']=='需要帮助' for r in entries),closed_at=days.get(date,{}).get('closed_at','')))
        return dict(day=plan,items=items,available_tasks=available,summary=summary,week=week,active_item=active_item)
