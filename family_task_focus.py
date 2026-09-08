"""Family follow-up choices over existing task IDs; no school or time-account edits."""
import datetime as dt
import hashlib
import json
import re


class FocusError(ValueError):
    def __init__(self, message, status=400, code='invalid_task_focus'):
        super().__init__(message); self.status=status; self.code=code


def default():
    return dict(mode='next',next_action='',waiting_for='',review_on='',version=0,updated='')


def read_all(connection):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_focus'").fetchone():
        return {}
    return {row['task_id']:{key:row[key] for key in default()} for row in connection.execute('SELECT * FROM task_focus')}


def _text(obj, key, limit):
    value=obj.get(key,'')
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\t' or ord(c)==127 for c in value):
        raise FocusError('字段格式或长度不正确：'+key)
    return value.strip()


def save(app, obj):
    ident=_text(obj,'id',100); request_key=_text(obj,'request_key',100)
    if not ident or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',request_key):
        raise FocusError('事项或请求标识不正确，请刷新后重试')
    version=obj.get('version')
    if type(version) is not int or not 0<=version<2147483647:
        raise FocusError('事项安排版本不正确，请刷新后重试')
    focus={key:_text(obj,key,limit) for key,limit in [('mode',20),('next_action',2000),('waiting_for',200),('review_on',10)]}
    if focus['mode'] not in ('next','waiting','later'):
        raise FocusError('请选择下一步、等待回复或以后再说')
    if focus['review_on']:
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',focus['review_on']): raise ValueError()
            dt.date.fromisoformat(focus['review_on'])
        except ValueError: raise FocusError('请选择有效的回看日期') from None
    if focus['mode']=='waiting' and not focus['waiting_for']:
        raise FocusError('请填写在等谁或等什么')
    if focus['mode']!='waiting': focus['waiting_for']=''
    if focus['mode']=='next': focus['review_on']=''
    digest=hashlib.sha256(json.dumps(dict(id=ident,version=version,**focus),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    c=app.connect()
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            task=next((t for t in app.tasks(c) if t['id']==ident),None)
            if task is None: raise FocusError('事项不存在，请刷新',404,'task_missing')
            update=c.execute('SELECT * FROM task_updates WHERE id=?',(ident,)).fetchone()
            task['update']=dict(update) if update else None
            c.execute('''CREATE TABLE IF NOT EXISTS task_focus (
                task_id TEXT PRIMARY KEY, mode TEXT NOT NULL, next_action TEXT NOT NULL,
                waiting_for TEXT NOT NULL, review_on TEXT NOT NULL,
                version INTEGER NOT NULL, updated TEXT NOT NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS task_focus_history (
                request_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, request_hash TEXT NOT NULL,
                previous TEXT NOT NULL, current TEXT NOT NULL, updated TEXT NOT NULL)''')
            receipt=c.execute('SELECT * FROM task_focus_history WHERE request_key=?',(request_key,)).fetchone()
            if receipt:
                if receipt['task_id']!=ident or receipt['request_hash']!=digest:
                    raise FocusError('该请求已用于另一份安排，请刷新核对',409,'task_focus_request_conflict')
                return dict(task=task,focus=task['focus'],request_replayed=True)
            if app.task_status(task,update['status'] if update else None) in app.TASK_CLOSED:
                raise FocusError('事项已完成或已搁置，请先恢复跟进再安排',409,'task_focus_closed')
            previous=task['focus']
            if previous['version']!=version:
                raise FocusError('事项安排已在别处更新，请读取最新安排后核对；本次输入尚未保存',409,'task_focus_conflict')
            updated=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
            focus.update(version=version+1,updated=updated)
            c.execute('''INSERT INTO task_focus VALUES (?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                mode=excluded.mode,next_action=excluded.next_action,waiting_for=excluded.waiting_for,
                review_on=excluded.review_on,version=excluded.version,updated=excluded.updated''',
                (ident,*(focus[key] for key in default())))
            c.execute('INSERT INTO task_focus_history VALUES (?,?,?,?,?,?)',
                (request_key,ident,digest,json.dumps(previous,ensure_ascii=False),json.dumps(focus,ensure_ascii=False),updated))
            task['focus']=focus
            return dict(task=task,focus=focus,request_replayed=False)
    finally: c.close()
