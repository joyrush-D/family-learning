"""Local family dashboard. Run: python3 app.py; private data stays outside Git."""
import datetime as dt
import json
import io
import math
import os
from pathlib import Path
import re
import secrets
import hashlib
import gzip
from functools import lru_cache
import sqlite3
import subprocess
import wave
import tempfile
import zipfile
import family_llm
import family_growth
import family_print
import family_reading
import family_calendar
import family_child
import family_agent
import family_study
import family_settings
import family_teachers
import family_access
import family_task_focus
import family_agenda
import family_guided
import family_goals
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as _ThreadingHTTPServer
from socketserver import TCPServer
from urllib.parse import urlparse, urlsplit, unquote, quote, parse_qs


class ThreadingHTTPServer(_ThreadingHTTPServer):
    def server_bind(self):
        TCPServer.server_bind(self)
        # Local listening does not need reverse DNS, which can block while offline.
        self.server_name, self.server_port = self.server_address[:2]


ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('FAMILY_DATA', ROOT / 'private'))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'family.sqlite3'
TOKEN = secrets.token_urlsafe(32)
CATEGORIES = ['学习进展', '成绩', '兴趣', '情绪', '家长观察']
MAX_UPLOAD = 20 * 1024 * 1024
ASSISTANCE = ('', '独立尝试', '少量提示', '逐步帮助', '看过讲解或答案')
PRACTICE_RELATIONS = ('', '同一道题或同一片段', '相近的新题或新片段', '范围或难度不同')
CARE_CHOICES = ('', '愿意试试', '暂不考虑', '改天回看')
TASK_DISMISSED = ('不参加', '不适用')
TASK_CLOSED = ('已完成', *TASK_DISMISSED, '已归档')
TASK_STATUSES = ('待跟进', '进行中', '已完成', *TASK_DISMISSED)
BUNDLE = ('app.js', 'reading.js', 'calendar.js', 'child-access.js', 'learning.js', 'study.js', 'settings.js', 'guided.js', 'teachers.js', 'goals.js')
STATIC = {'/': 'index.html', **{'/'+name: name for name in (
    *BUNDLE, 'startup.js', 'ui.css', 'learning.css', 'study.css', 'teachers.css', 'growth-world.js',
    'vendor/three.module.min.js', 'vendor/three.core.min.js')}}


@lru_cache(maxsize=32)
def static_asset(files, versions):
    body = b'\n;\n'.join(p.read_bytes() for p in files)
    if len(files) > 1:
        body = b'(()=>{\n' + body + b'\n})();\n'
    return body, gzip.compress(body, mtime=0), 'W/"'+hashlib.sha256(body).hexdigest()+'"'


def asset(files):
    files = tuple(files)
    versions = tuple((s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) for s in (p.stat() for p in files))
    return static_asset(files, versions)


def prepare_assets():
    # Fixed pages contain no family data. Prepare once; file changes rebuild on access.
    groups = [(ROOT/name,) for name in (*STATIC.values(), 'child.html', 'child.js', 'child.css')]
    for files in [*groups, tuple(ROOT/name for name in BUNDLE)]:
        if all(p.is_file() for p in files):
            asset(files)


def accepts_gzip(value):
    accepted = {}
    for item in value.lower().split(','):
        coding, *params = item.strip().split(';')
        quality = 1.0
        for param in params:
            key, _, val = param.strip().partition('=')
            if key == 'q':
                try: quality = float(val)
                except ValueError: quality = 0
        accepted[coding.strip()] = 0 < quality <= 1
    return accepted.get('gzip', accepted.get('*', False))

class ProfileError(ValueError):
    def __init__(self,message,status=400,code='invalid_profile'):
        super().__init__(message);self.status=status;self.code=code

class TaskError(ValueError):
    def __init__(self,message,status=400,code='invalid_task'):
        super().__init__(message);self.status=status;self.code=code

class RecordError(ValueError):
    def __init__(self,message,status=400,code='invalid_record'):
        super().__init__(message);self.status=status;self.code=code
        self.not_saved=False;self.request_known=False

def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, child TEXT, day TEXT, category TEXT, subject TEXT, title TEXT, note TEXT, source TEXT, score REAL, total REAL, created TEXT, attachments TEXT NOT NULL DEFAULT '[]', related_record_id INTEGER, followup_kind TEXT NOT NULL DEFAULT '')")
    for name, declaration in [('attachments', "TEXT NOT NULL DEFAULT '[]'"), ('related_record_id', 'INTEGER'), ('followup_kind', "TEXT NOT NULL DEFAULT ''"), ('assistance', "TEXT NOT NULL DEFAULT ''"), ('practice_relation', "TEXT NOT NULL DEFAULT ''"), ('comparison_note', "TEXT NOT NULL DEFAULT ''"), ('care_choice', "TEXT NOT NULL DEFAULT ''"), ('care_review_on', "TEXT NOT NULL DEFAULT ''"), ('request_key', "TEXT NOT NULL DEFAULT ''"), ('request_hash', "TEXT NOT NULL DEFAULT ''")]:
        if name not in [r['name'] for r in c.execute('PRAGMA table_info(records)')]:
            try: c.execute('ALTER TABLE records ADD COLUMN '+name+' '+declaration)
            except sqlite3.OperationalError:
                if name not in [r['name'] for r in c.execute('PRAGMA table_info(records)')]:
                    c.close(); raise
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS record_request_key ON records(request_key) WHERE request_key<>''")
    c.execute('CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, mime TEXT NOT NULL, created TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS revisions (id INTEGER PRIMARY KEY, record_id INTEGER, previous TEXT, changed TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS task_updates (id TEXT PRIMARY KEY, status TEXT, note TEXT, updated TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS task_history (id INTEGER PRIMARY KEY, task_id TEXT, status TEXT, note TEXT, updated TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS manual_tasks (id TEXT PRIMARY KEY, child TEXT NOT NULL, title TEXT NOT NULL, due TEXT NOT NULL, original_status TEXT NOT NULL, source TEXT NOT NULL, action TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS profile_overrides (child_id TEXT PRIMARY KEY, name TEXT NOT NULL, grade TEXT NOT NULL, classroom TEXT NOT NULL, version INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS profile_aliases (alias TEXT PRIMARY KEY, child_id TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS profile_history (child_id TEXT NOT NULL, version INTEGER NOT NULL, previous TEXT NOT NULL, current TEXT NOT NULL, reason TEXT NOT NULL, changed TEXT NOT NULL, PRIMARY KEY(child_id,version))')
    return c

def read(name):
    p = ROOT / name
    return p.read_text() if p.exists() else ''

def profile_state(connection=None):
    if connection is None:
        with connect() as c: return profile_state(c)
    rows = []
    for line in read('家庭运行规则.md').splitlines():
        cells = [x.strip() for x in line.strip('|').split('|')]
        if len(cells) == 5 and cells[0].startswith('child-'):
            rows.append(dict(id=cells[0], name=cells[1].split('（')[0], label=cells[1], age=cells[3], grade=cells[4]))
    if len({p['id'] for p in rows})!=len(rows) or len({p['name'] for p in rows})!=len(rows):
        raise ProfileError('孩子档案标识或称呼重复，请先核对家庭配置',409,'profile_conflict')
    owners={r['alias']:r['child_id'] for r in connection.execute('SELECT * FROM profile_aliases')}
    overrides={r['child_id']:dict(r) for r in connection.execute('SELECT * FROM profile_overrides')}
    known={p['id'] for p in rows}
    for ident,row in overrides.items():
        if ident not in known:
            rows.append(dict(id=ident,name=row['name'],label=row['name'],age='未填写',grade=row['grade']))
    def reserve(name,ident):
        if name in owners and owners[name]!=ident:
            raise ProfileError('孩子称呼与历史归属冲突，请先核对家庭配置',409,'profile_conflict')
        owners[name]=ident
    for p in rows:
        reserve(p['name'],p['id'])
        suffix=p['label'][len(p['name']):]
        p.update(classroom='',version=0,history=[])
        if p['id'] in overrides:
            row=overrides[p['id']]
            p.update({k:row[k] for k in ['name','grade','classroom','version']})
        reserve(p['name'],p['id']);p['label']=p['name']+suffix
        p['history']=[dict(version=r['version'],previous=json.loads(r['previous']),current=json.loads(r['current']),reason=r['reason'],changed=r['changed'])
                      for r in connection.execute('SELECT * FROM profile_history WHERE child_id=? ORDER BY version DESC',(p['id'],))]
    return rows,owners

def profiles(connection=None):
    return profile_state(connection)[0]

def child_names(connection=None):
    children,owners=profile_state(connection);names={p['id']:p['name'] for p in children}
    return {alias:names[ident] for alias,ident in owners.items() if ident in names}

def save_profile(obj):
    ident=clean(obj,'child_id',100);name=clean(obj,'name',80)
    grade=clean(obj,'grade',80);classroom=clean(obj,'classroom',80);reason=clean(obj,'reason',1000)
    if not name or not reason: raise ProfileError('请填写孩子称呼和更正依据')
    for value in [name,grade,classroom]:
        if '|' in value or any(ord(c)<32 or ord(c)==127 for c in value): raise ProfileError('档案字段不能含竖线、换行或控制字符')
    if '（' in name or '）' in name: raise ProfileError('称呼不加全角括号备注')
    version=obj.get('version')
    if type(version) is not int or not 0<=version<2147483647: raise ProfileError('档案版本不正确，请刷新后重试')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        children,owners=profile_state(c);profile=next((p for p in children if p['id']==ident),None)
        if profile is None: raise ProfileError('孩子档案不存在',404,'profile_not_found')
        if profile['version']!=version: raise ProfileError('档案已更新，请刷新后核对再保存',409,'profile_version_conflict')
        if name in owners and owners[name]!=ident: raise ProfileError('该称呼已属于另一位孩子，历史称呼也不能重新分配',409,'profile_alias_conflict')
        if name not in owners and (c.execute('SELECT 1 FROM records WHERE child=?',(name,)).fetchone() or c.execute('SELECT 1 FROM manual_tasks WHERE child=?',(name,)).fetchone()):
            raise ProfileError('该称呼已有归属未核对的记录，请先核对',409,'profile_alias_conflict')
        if name not in owners:
            unclaimed={t['child'] for t in tasks(c)}
            try:
                for filename in ['陪伴建议.json','采集状态.json']:
                    path=DATA/filename
                    if not path.exists(): continue
                    sources=json.loads(path.read_text())
                    if not isinstance(sources,(list,dict)): raise ValueError()
                    for source in sources if isinstance(sources,list) else sources.values():
                        if isinstance(source,dict) and isinstance(source.get('child'),str): unclaimed.add(source['child'])
            except (OSError,ValueError):
                raise ProfileError('来源归属暂时无法核对，请修复后再更正称呼',409,'profile_source_error') from None
            if name in unclaimed: raise ProfileError('该称呼已有归属未核对的来源，请先核对',409,'profile_alias_conflict')
        previous={k:profile[k] for k in ['name','grade','classroom']}
        current=dict(name=name,grade=grade,classroom=classroom)
        if previous==current: return profile
        # Reserve all existing names, not only the changed child's name. Historical
        # ownership survives later renames and is never assigned to another child.
        for alias,owner in owners.items(): c.execute('INSERT OR IGNORE INTO profile_aliases VALUES (?,?)',(alias,owner))
        c.execute('INSERT OR IGNORE INTO profile_aliases VALUES (?,?)',(name,ident))
        c.execute('INSERT INTO profile_overrides VALUES (?,?,?,?,?) ON CONFLICT(child_id) DO UPDATE SET name=excluded.name,grade=excluded.grade,classroom=excluded.classroom,version=excluded.version',
                  (ident,name,grade,classroom,version+1))
        c.execute('INSERT INTO profile_history VALUES (?,?,?,?,?,?)',(ident,version+1,json.dumps(previous,ensure_ascii=False),json.dumps(current,ensure_ascii=False),reason,dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()))
        for alias,owner in owners.items():
            if owner==ident:
                c.execute('UPDATE records SET child=? WHERE child=?',(name,alias))
                c.execute('UPDATE manual_tasks SET child=? WHERE child=?',(name,alias))
        return next(p for p in profiles(c) if p['id']==ident)

def tasks(connection=None):
    if connection is None:
        with connect() as c: return tasks(c)
    names=child_names(connection)
    result = []
    for line in read('跟踪台账.md').splitlines():
        cells = [x.strip() for x in line.strip('|').split('|')]
        if len(cells) == 7 and re.fullmatch(r'[A-Z]+\d+', cells[0]):
            result.append(dict(zip(['id','child','title','due','original_status','source','action'], cells)))
    manual=[dict(r) for r in connection.execute('SELECT * FROM manual_tasks ORDER BY rowid DESC')]
    focuses=family_task_focus.read_all(connection)
    for task in manual+result:
        task['child']=names.get(task['child'],task['child'])
        task['focus']=focuses.get(task['id'],family_task_focus.default())
        if task['source'].startswith('Agent建议:'):
            origin=task['source'].splitlines()[0].removeprefix('Agent建议:')
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='agent_items'").fetchone():
                proposal=connection.execute('SELECT plan FROM agent_items WHERE id=?',(origin,)).fetchone()
                if proposal: task['advice']=json.loads(proposal['plan']).get('school_task',{}).get('advice','')
        if task['focus']['title']: task['original_title']=task['title'];task['title']=task['focus']['title']
        if task['focus']['goal']: task['original_action']=task['action'];task['action']=task['focus']['goal']
    return family_agenda.enrich(SimpleNamespace(**globals()),connection,manual+result)

def care_notes(connection=None):
    p=DATA/'陪伴建议.json'
    if not p.exists(): return dict(items=[],error='')
    if connection is None:
        with connect() as c: return care_notes(c)
    try:
        items=json.loads(p.read_text())
        if not isinstance(items,list) or len(items)>20: raise ValueError()
        seen=set();names=child_names(connection);original_dates={}
        for item in items:
            for key in ['id','child','topic','title','evidence','action','review_on','expires_on']:
                if not isinstance(item.get(key),str) or not item[key].strip() or len(item[key])>2000: raise ValueError()
            if len(item['id'])>60 or len(item['title'])>120 or item['id'] in seen: raise ValueError()
            if item['child'] not in names: raise ValueError()
            item['child']=names[item['child']]
            seen.add(item['id'])
            dt.date.fromisoformat(item['review_on']);dt.date.fromisoformat(item['expires_on'])
            original_dates[item['id']]=item['review_on']
            item.update(review_status='',care_choice='',care_review_on='',choice_record_id=None,review_state_source='none')
    except (OSError,ValueError,TypeError,AttributeError):
        return dict(items=[],error='陪伴建议读取失败，其他记录仍可使用。')
    error='';state_path=DATA/'陪伴提醒状态.json'
    state_error='陪伴提醒状态暂时无法核对，仍保留已有建议；请核对是否停推或延期。'
    try:
        states=json.loads(state_path.read_text()) if state_path.exists() else {}
        if not isinstance(states,dict): raise ValueError()
        for item in items:
            if item['id'] not in states: continue
            state=states[item['id']]
            if not isinstance(state,dict) or state.get('status') not in ['awaiting_parent_feedback','declined','deferred']:
                error=state_error;continue
            status=state['status']
            if status=='deferred':
                date=state.get('next_review_on')
                try:
                    if not isinstance(date,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',date): raise ValueError()
                    dt.date.fromisoformat(date)
                except ValueError:
                    error=state_error;continue
                item['review_on']=date
            item['review_status']=status
            item['review_state_source']='legacy_json'
    except (OSError,ValueError,TypeError):
        error=state_error
    columns={row['name'] for row in connection.execute('PRAGMA table_info(records)')}
    if {'care_choice','care_review_on'} <= columns:
        by_id={item['id']:item for item in items}
        for row in connection.execute("SELECT id,child,source,care_choice,care_review_on FROM records WHERE care_choice<>'' ORDER BY id"):
            source=row['source']
            if not isinstance(source,str) or not source.startswith('陪伴建议:'): continue
            item=by_id.get(source[len('陪伴建议:'):])
            if item is None: continue
            choice,date=row['care_choice'],row['care_review_on']
            try:
                if names.get(row['child'])!=item['child'] or choice not in CARE_CHOICES[1:]: raise ValueError()
                if choice=='改天回看':
                    if not isinstance(date,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',date): raise ValueError()
                    dt.date.fromisoformat(date)
                elif date!='': raise ValueError()
            except (ValueError,TypeError):
                error='陪伴建议的明确选择记录暂时无法核对，请检查孩子归属和回看日期。';continue
            item.update(care_choice=choice,care_review_on=date,choice_record_id=row['id'],review_state_source='record',
                        review_status={'愿意试试':'accepted','暂不考虑':'declined','改天回看':'deferred'}[choice])
            if choice=='改天回看': item['review_on']=date
            else:
                # A later choice resets a prior deferral to the original proposal date.
                item['review_on']=original_dates[item['id']]
    elif {'care_choice','care_review_on'} & columns:
        error='陪伴建议选择字段不完整，请检查应用升级状态。'
    return dict(items=items,error=error)

def snapshot():
    with connect() as c:
        c.execute('BEGIN')
        children=profiles(c);names=child_names(c);ts=tasks(c);care=care_notes(c)
        records = [dict(r) for r in c.execute('SELECT * FROM records ORDER BY day DESC,id DESC')]
        for r in records: r['attachments'] = json.loads(r['attachments'])
        uploads = [upload_info(r) for r in c.execute('SELECT * FROM uploads ORDER BY created DESC,id DESC')]
        updates = {r['id']:dict(r) for r in c.execute('SELECT * FROM task_updates')}
        history = {}
        for r in c.execute('SELECT * FROM task_history ORDER BY id DESC'):
            history.setdefault(r['task_id'], []).append(dict(r))
    for t in ts:
        t['update'] = updates.get(t['id'])
        t['history'] = history.get(t['id'], [])
    p = DATA / '采集状态.json'
    sync_error=''
    try:
        sync=json.loads(p.read_text()) if p.exists() else {}
        if not isinstance(sync,dict): raise ValueError('invalid collection state')
    except (OSError,ValueError):
        sync={}
        sync_error='消息采集状态暂时无法读取；已有家庭记录仍可查看、手动录入和跟进。'
    for source in sync.values():
        if isinstance(source,dict) and isinstance(source.get('child'),str): source['child']=names.get(source['child'],source['child'])
    attachments = [p.name for p in (DATA/'attachments').glob('*') if p.is_file() and not p.is_symlink()]
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    try:
        today_calendar=calendar_snapshot(today,today)
    except (OSError,sqlite3.Error,ValueError,TypeError,RecursionError):
        today_calendar=dict(events=[],timetables=[],source_error='今日日历暂时无法读取，请到日历重试；不能据此判断今天没有安排。')
    try:
        agent=agent_store().snapshot()
    except (OSError,sqlite3.Error,ValueError,TypeError):
        agent=dict(enabled=False,state='error',last_error='成长助手状态暂时无法读取，已有记录仍可使用。',items=[],sources=[])
    printing=printer_config();printing['jobs']=print_store().list_jobs()
    return dict(asr=dict(configured=bool(os.environ.get('FAMILY_ASR_URL'))),llm=dict(configured=settings_store().model_state()['configured']),children=children, tasks=ts, records=records, sync=sync, sync_error=sync_error, attachments=attachments, uploads=uploads, care=care,
                growth=read('学习与成长.md'), sources=read('消息来源.md'), token=TOKEN,
                rewards=family_growth.summarize(children,records,ts,today),reading=family_reading.Store(connect,lambda:children,lambda:ts).snapshot(),printing=printing,today=today,today_calendar=today_calendar,agent=agent)

def agent_store():
    return family_agent.Store(connect,profiles,DATA)

def settings_store():
    return family_settings.Store(SimpleNamespace(**globals()))

def teacher_store():
    return family_teachers.Store(SimpleNamespace(**globals()))

def study_store():
    return family_study.Store(SimpleNamespace(**globals()))

def guided_store():
    return family_guided.Store(SimpleNamespace(**globals()))

def goal_store():
    return family_goals.Store(SimpleNamespace(**globals()))

def calendar_store():
    return family_calendar.Store(connect,profiles,DATA)

def calendar_snapshot(start,end):
    result=calendar_store().snapshot(start,end)
    result.update(family_agenda.snapshot(SimpleNamespace(**globals()),start,end))
    return result

def calendar_subscription():
    events=calendar_store().subscription_events()
    linked={e['task_id'] for e in events if e.get('task_id')}
    states={}
    with connect() as c:
        c.execute('BEGIN')
        children=profiles(c)
        by_name={p['name']:p['id'] for p in children}
        updates={r['id']:r['status'] for r in c.execute('SELECT id,status FROM task_updates')}
        for task in tasks(c):
            if task['id'] not in linked: continue
            if task['child'] not in by_name or task['id'] in states:
                raise family_calendar.CalendarError('关联事项的孩子归属无法核对',503,'calendar_task_error')
            states[task['id']]={by_name[task['child']]:task_status(task,updates.get(task['id']))}
    if linked-set(states) or any(e.get('task_id') and not set(states[e['task_id']])<=set(e['child_ids']) for e in events):
        raise family_calendar.CalendarError('关联事项或参加孩子无法核对',503,'calendar_task_error')
    namespace=os.environ.get('FAMILY_CALENDAR_ID') or os.environ.get('FAMILY_HOST') or 'local-family-learning'
    return family_calendar.render_ics(events,children,dt.datetime.now(dt.timezone.utc),namespace,states)

def reading_store():
    return family_reading.Store(connect,profiles,tasks)

def print_store():
    # Resolve DATA and connect at request time, including isolated test instances.
    return family_print.PrintStore(DATA,connect)

def printer_config():
    path=DATA/'打印机配置.json'
    if not path.exists() and not path.is_symlink(): return dict(printers=[],error='')
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>16384: raise ValueError()
        def unique_pairs(pairs):
            obj={}
            for key,value in pairs:
                if key in obj: raise ValueError()
                obj[key]=value
            return obj
        config=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique_pairs)
        if not isinstance(config,dict) or set(config)!={'printers'}: raise ValueError()
        printers=config['printers']
        if not isinstance(printers,list) or len(printers)>20: raise ValueError()
        seen=set()
        for printer in printers:
            if not isinstance(printer,dict) or set(printer)!={'name','label','color','duplex'}: raise ValueError()
            name=family_print.printer_name(printer['name'])
            label=printer['label']
            if name in seen or not isinstance(label,str) or not label.strip() or len(label)>100 or any(ord(c)<32 or ord(c)==127 for c in label): raise ValueError()
            if type(printer['color']) is not bool or type(printer['duplex']) is not bool: raise ValueError()
            seen.add(name)
        return dict(printers=printers,error='')
    except (OSError,UnicodeError,ValueError,TypeError):
        return dict(printers=[],error='打印机配置无法读取，请由管理员检查；当前未授权打印机。')

def authorized_printer(name, *, color='monochrome', sides='one-sided'):
    config=printer_config()
    if config['error']: raise family_print.PrintError(config['error'],'printer_configuration_error',503)
    family_print.printer_name(name)
    printer=next((p for p in config['printers'] if p['name']==name),None)
    if printer is None: raise family_print.PrintError('打印机未授权，请先配置家庭打印机','printer_not_authorized',403)
    if not isinstance(color,str) or color not in family_print.COLORS or not isinstance(sides,str) or sides not in family_print.SIDES:
        raise family_print.PrintError('单双面或颜色设置不正确')
    if color=='color' and not printer['color']: raise family_print.PrintError('该打印机未授权彩色打印')
    if sides!='one-sided' and not printer['duplex']: raise family_print.PrintError('该打印机未授权双面打印')
    return printer

def clean(obj, key, limit=4000):
    value=obj.get(key,'')
    if not isinstance(value,str) or len(value)>limit: raise ValueError('字段格式或长度不正确')
    return value.strip()

def record_result(connection,ident,replayed=False):
    row=connection.execute('SELECT id,child,source,care_choice,care_review_on FROM records WHERE id=?',(ident,)).fetchone()
    result=dict(ok=True,record_id=ident,replayed=replayed,record=dict(row))
    if row['source'].startswith('陪伴建议:'):
        notes=care_notes(connection)
        item=next((item for item in notes['items'] if item['id']==row['source'][len('陪伴建议:'):]),None)
        if item is not None and item['child']!=child_names(connection).get(row['child']): item=None
        result['care']=({key:item[key] for key in ['id','child','care_choice','care_review_on','choice_record_id',
                                                 'review_status','review_on','expires_on','review_state_source']}
                        if item is not None and not notes['error'] else None)
        result['care_error']=notes['error'] or ('' if item is not None else '建议当前无法读取，保存回执不表示当前安排已核对。')
    return result

def save_record(obj,care_only=False):
    receipt={}
    try: return _save_record(obj,care_only,receipt)
    except (ValueError,TypeError) as error:
        if not care_only: raise
        failure=error if isinstance(error,RecordError) else RecordError(str(error))
        failure.request_known=receipt.get('known',False)
        failure.not_saved=receipt.get('checked',False) and not failure.request_known
        raise failure

def _save_record(obj,care_only,receipt):
    child=clean(obj,'child',100)
    day=clean(obj,'day',10); dt.date.fromisoformat(day)
    category=clean(obj,'category',20)
    if category not in CATEGORIES: raise ValueError('记录类型不正确')
    title=clean(obj,'title',200)
    if not title: raise ValueError('请填写记录标题')
    subject=clean(obj,'subject',80);note=clean(obj,'note');source=clean(obj,'source',200)
    request_key=clean(obj,'request_key',128)
    if request_key and not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',request_key): raise RecordError('提交标识格式不正确')
    if care_only and (obj.get('id') not in (None,'') or not source.startswith('陪伴建议:') or not request_key):
        raise RecordError('请用新的反馈提交明确选择，并保留本次提交标识')
    if care_only and category!='家长观察': raise RecordError('建议反馈须保存为家长观察')
    score=total=None
    if category=='成绩':
        score=float(obj.get('score',''));total=float(obj.get('total',''))
        if not all(math.isfinite(v) for v in [score,total]) or not 0<=score<=total or total<=0: raise ValueError('成绩须在0到满分之间')
        if not subject: raise ValueError('请填写成绩科目')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        names=child_names(c)
        if child not in names: raise ValueError('请选择孩子')
        child=names[child]
        child_id=next(p['id'] for p in profiles(c) if p['name']==child)
        request_hash='';prior=None
        if request_key:
            if obj.get('id'): raise RecordError('更正已有文字记录不能复用新增反馈的提交标识')
            payload={key:value for key,value in obj.items() if key!='request_key'}
            payload['child']=child_id
            request_hash=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            prior=c.execute('SELECT id,child,source,request_hash FROM records WHERE request_key=?',(request_key,)).fetchone()
            receipt.update(checked=True,known=prior is not None)
            if prior is not None:
                if prior['request_hash']!=request_hash: raise RecordError('同一提交标识的内容不同，请先核对原提交',409,'request_conflict')
                if names.get(prior['child'])!=child or prior['source']!=source:
                    raise RecordError('这条已保存反馈的归属或来源后来已更正，请先核对原记录',409,'request_context_changed')
                return record_result(c,prior['id'],True)
        if source.startswith('陪伴建议:'):
            notes=care_notes(c)
            if notes['error']: raise RecordError('陪伴建议或提醒状态暂时无法核对，请刷新后重试',409,'care_unverified')
            suggestion=next((item for item in notes['items'] if item['id']==source[len('陪伴建议:'):]),None)
            if suggestion is None: raise ValueError('陪伴建议不存在或暂时无法读取，请刷新后核对')
            if suggestion['child']!=child: raise ValueError('建议反馈只能关联同一个孩子')
        ident=obj.get('id')
        previous=c.execute('SELECT * FROM records WHERE id=?',(int(ident),)).fetchone() if ident else None
        if ident and previous is None: raise ValueError('记录不存在')
        family_guided.guard_record_write(c,previous,source)
        if source.startswith('作息记录:') or previous is not None and previous['source'].startswith('作息记录:'):
            owned=dict(child=child,day=day,category=category,subject=subject,title=title,note=note,source=source,
                       assistance=clean(obj,'assistance',30))
            if previous is None or any((names.get(previous[k],previous[k]) if k=='child' else previous[k])!=value for k,value in owned.items()):
                raise RecordError('用时、结果和说明请到“放学后”更正；这里可以补充原件，也可以新增关联观察。',409,'study_record_owned')
        choice=clean(obj,'care_choice',20) if 'care_choice' in obj else previous['care_choice'] if previous else ''
        review_on=clean(obj,'care_review_on',10) if 'care_review_on' in obj else previous['care_review_on'] if previous else ''
        if choice not in CARE_CHOICES: raise RecordError('请选择有效的陪伴安排')
        if previous is not None:
            if choice!=previous['care_choice'] or review_on!=previous['care_review_on']:
                raise RecordError('调整安排请追加一条新反馈；旧记录的明确选择保留不变',409,'care_choice_immutable')
            if previous['care_choice'] and (child!=names.get(previous['child']) or source!=previous['source']):
                raise RecordError('明确选择的孩子和建议来源不能更换',409,'care_choice_immutable')
        if choice:
            if not source.startswith('陪伴建议:') or category!='家长观察': raise RecordError('明确选择只能作为对应建议的家长反馈')
            if not previous and not request_key: raise RecordError('请保留本次反馈的提交标识后重试')
            if choice=='改天回看':
                if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',review_on): raise RecordError('请指定明确的回看日期')
                date=dt.date.fromisoformat(review_on)
                if not previous and date<=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date():
                    raise RecordError('回看日期须晚于今天')
            elif review_on: raise RecordError('只有改天回看才能设置新的回看日期')
        elif review_on: raise RecordError('填写回看日期时须明确选择改天回看')
        related=obj.get('related_record_id',previous['related_record_id'] if previous else None)
        if related is not None and (type(related) is not int or not 0<related<=9223372036854775807):
            raise ValueError('关联记录编号不正确')
        kind=clean(obj,'followup_kind',20) if 'followup_kind' in obj else previous['followup_kind'] if previous else ''
        if kind not in ['', '订正', '复测', '独立复测', '补充观察']: raise ValueError('跟进类型不正确')
        context={}
        for key, choices, limit in [('assistance',ASSISTANCE,20),('practice_relation',PRACTICE_RELATIONS,30),('comparison_note',None,1000)]:
            value=clean(obj,key,limit) if key in obj else previous[key] if previous else ''
            if '\x00' in value or choices is not None and value not in choices: raise ValueError('学习条件字段不正确')
            context[key]=value
        seen={int(ident)} if ident else set()
        ancestor=related
        while ancestor is not None:
            if ancestor in seen: raise ValueError('关联记录不能指向自身或形成循环')
            seen.add(ancestor)
            linked=c.execute('SELECT child,related_record_id FROM records WHERE id=?',(ancestor,)).fetchone()
            if linked is None: raise ValueError('关联记录不存在')
            if linked['child']!=child: raise ValueError('只能关联同一个孩子的记录')
            ancestor=linked['related_record_id']
        if ident and c.execute('SELECT 1 FROM records WHERE related_record_id=? AND child<>?',(int(ident),child)).fetchone():
            raise ValueError('已有该孩子的后续记录，不能更换孩子')
        attachments=obj.get('attachments',json.loads(previous['attachments']) if previous else [])
        if not isinstance(attachments,list) or len(attachments)>20 or any(not isinstance(i,str) or not re.fullmatch(r'[a-f0-9]{32}',i) for i in attachments):
            raise ValueError('附件格式不正确')
        attachments=list(dict.fromkeys(attachments))
        if care_only and not choice and not note and not attachments: raise RecordError('请填写反馈或保留至少一份原件')
        if any(not c.execute('SELECT 1 FROM uploads WHERE id=?',(i,)).fetchone() for i in attachments):
            raise ValueError('附件不存在，请重新上传')
        family_reading.validate_record_attachments(c,next(p['id'] for p in profiles(c) if p['name']==child),attachments)
        now=dt.datetime.now().isoformat()
        values=(child,day,category,subject,title,note,source or '家长网页记录',score,total,now,json.dumps(attachments),related,kind,context['assistance'],context['practice_relation'],context['comparison_note'],choice,review_on)
        if ident:
            c.execute('INSERT INTO revisions (record_id,previous,changed) VALUES (?,?,?)',(int(ident),json.dumps(dict(previous),ensure_ascii=False),now))
            c.execute('UPDATE records SET child=?,day=?,category=?,subject=?,title=?,note=?,source=?,score=?,total=?,created=?,attachments=?,related_record_id=?,followup_kind=?,assistance=?,practice_relation=?,comparison_note=?,care_choice=?,care_review_on=? WHERE id=?',values+(int(ident),))
        else:
            cursor=c.execute('INSERT INTO records (child,day,category,subject,title,note,source,score,total,created,attachments,related_record_id,followup_kind,assistance,practice_relation,comparison_note,care_choice,care_review_on,request_key,request_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',values+(request_key,request_hash))
            ident=cursor.lastrowid
        return record_result(c,int(ident))

def upload_info(row):
    return dict(id=row['id'],name=row['name'],size=row['size'],mime=row['mime'],url='/upload/'+row['id'])

def record_history(ident):
    """Read prior snapshots by stable record ID; never restore or rewrite a version."""
    if type(ident) is not int or not 0<ident<=9223372036854775807: raise ValueError('记录编号不正确')
    attachment_ids=[]
    fields=['id','child','day','category','subject','title','note','source','score','total','created','related_record_id','followup_kind']
    def invalid_constant(value): raise ValueError('invalid JSON number')
    def decode(value):
        if not isinstance(value,dict) or value.get('id')!=ident or type(value.get('id')) is not int:
            raise ValueError('invalid snapshot')
        if any(not isinstance(value.get(key),str) for key in ['child','day','category','title']): raise ValueError('invalid snapshot')
        for key in ['subject','note','source','created','followup_kind']:
            if key in value and value[key] is not None and not isinstance(value[key],str): raise ValueError('invalid snapshot')
        for key,choices,limit in [('assistance',ASSISTANCE,20),('practice_relation',PRACTICE_RELATIONS,30),('comparison_note',None,1000)]:
            if key in value and (not isinstance(value[key],str) or len(value[key])>limit or '\x00' in value[key] or choices is not None and value[key] not in choices):
                raise ValueError('invalid learning context')
        for key in ['score','total']:
            number=value.get(key)
            if number is not None and (type(number) not in (int,float) or not math.isfinite(number)): raise ValueError('invalid snapshot')
        relation=value.get('related_record_id')
        if relation is not None and (type(relation) is not int or not 0<relation<=9223372036854775807): raise ValueError('invalid snapshot')
        attachments=value.get('attachments',[])
        if isinstance(attachments,str): attachments=json.loads(attachments,parse_constant=invalid_constant)
        if not isinstance(attachments,list) or any(not isinstance(i,str) or not re.fullmatch(r'[a-f0-9]{32}',i) for i in attachments):
            raise ValueError('invalid attachment references')
        result={key:value[key] for key in fields if key in value}
        result.update({key:value.get(key) for key in ['assistance','practice_relation','comparison_note']})
        for key in ['care_choice','care_review_on']:
            if key in value and (not isinstance(value[key],str) or len(value[key])>20): raise ValueError('invalid care choice')
        if value.get('care_choice','') not in CARE_CHOICES: raise ValueError('invalid care choice')
        if value.get('care_choice')=='改天回看':
            date=value.get('care_review_on','')
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',date): raise ValueError('invalid care date')
            dt.date.fromisoformat(date)
        elif value.get('care_review_on'): raise ValueError('invalid care date')
        result.update({key:value.get(key) for key in ['care_choice','care_review_on']})
        result.update(attachments=attachments,attachments_recorded='attachments' in value)
        for upload in attachments:
            if upload not in attachment_ids: attachment_ids.append(upload)
        return result
    with connect() as c:
        c.execute('BEGIN')
        row=c.execute('SELECT * FROM records WHERE id=?',(ident,)).fetchone()
        if row is None: return None
        current=decode(dict(row));history=[];unreadable=0
        children,owners=profile_state(c)
        profile=next((p for p in children if p['id']==owners.get(current['child'])),None)
        for revision in c.execute('SELECT id,changed,previous FROM revisions WHERE record_id=? ORDER BY id DESC',(ident,)):
            item=dict(id=revision['id'],changed=revision['changed'],previous=None,error='')
            try: item['previous']=decode(json.loads(revision['previous'],parse_constant=invalid_constant))
            except (ValueError,TypeError,OverflowError):
                item['error']='这份旧快照损坏或格式不完整，无法读取；其他版本仍可查看。';unreadable+=1
            history.append(item)
        attachments=[]
        for upload in attachment_ids:
            metadata=c.execute('SELECT * FROM uploads WHERE id=?',(upload,)).fetchone()
            info=dict(id=upload,name='',mime='',size=None,available=False,error='原件元数据缺失，无法核对或打开。')
            if metadata is not None:
                info.update({key:metadata[key] for key in ['name','mime','size']})
                path=DATA/'uploads'/upload
                try:
                    info['available']=not path.is_symlink() and path.is_file() and path.stat().st_size==metadata['size']
                except OSError: pass
                info['error']='' if info['available'] else '原件文件缺失、不可读取或长度不符，请核对备份；原ID已保留。'
            attachments.append(info)
    return dict(record_id=ident,current=current,history=history,attachments=attachments,
                child_context=dict(child_id=profile['id'],name=profile['name']) if profile else None,
                complete=True,unreadable_count=unreadable,
                note='按更正顺序倒序列出这条记录的全部已留存旧版本，损坏项另行标明；旧称呼和时间按当时记录保留，不作为新进展。旧版本缺失的学习条件返回空值，不能由旧的独立复测标签推定实际独立完成。未记录附件字段的旧版本不能据此认定从未有原图；原件可用性仅核对现存元数据、文件和长度，不代表内容已读。')

def upload_mime(path, name):
    """Check the extension and signature; never trust the browser's MIME header."""
    ext=Path(name).suffix.lower()
    with path.open('rb') as f: head=f.read(65536)
    mime=None
    if ext in ['.jpg','.jpeg'] and head.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
    elif ext=='.png' and head.startswith(b'\x89PNG\r\n\x1a\n') and head[12:16]==b'IHDR': mime='image/png'
    elif ext=='.webp' and head[:4]==b'RIFF' and head[8:12]==b'WEBP': mime='image/webp'
    elif ext in ['.heic','.heif'] and head[4:8]==b'ftyp' and any(b in head[8:64] for b in [b'heic',b'heix',b'hevc',b'hevx',b'mif1',b'msf1']): mime='image/heif' if ext=='.heif' else 'image/heic'
    elif ext=='.pdf' and head.startswith(b'%PDF-'): mime='application/pdf'
    elif ext=='.doc' and head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'): mime='application/msword'
    elif ext in ['.docx','.pptx'] and head.startswith(b'PK\x03\x04'):
        try:
            with zipfile.ZipFile(path) as z:
                names=z.namelist()
                expected='word/document.xml' if ext=='.docx' else 'ppt/presentation.xml'
                if '[Content_Types].xml' in names and expected in names and not any(n.startswith(('/','\\')) or '..' in n.split('/') or 'vbaproject' in n.lower() for n in names):
                    mime='application/vnd.openxmlformats-officedocument.'+('wordprocessingml.document' if ext=='.docx' else 'presentationml.presentation')
        except (zipfile.BadZipFile,OSError): pass
    elif ext=='.wav' and head[:4]==b'RIFF' and head[8:12]==b'WAVE': mime='audio/wav'
    elif ext=='.mp3' and (head.startswith(b'ID3') or len(head)>3 and head[0]==255 and head[1]&224==224 and head[1]&6 and head[2]&12!=12): mime='audio/mpeg'
    elif ext=='.m4a' and head[4:8]==b'ftyp' and any(b in head[8:64] for b in [b'M4A ',b'M4B ',b'mp42',b'isom']): mime='audio/mp4'
    elif ext=='.webm' and head.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in head[:4096]: mime='audio/webm'
    elif ext=='.ogg' and head.startswith(b'OggS'): mime='audio/ogg'
    elif ext=='.txt':
        try:
            text=path.read_text(encoding='utf-8-sig')
            if '\x00' not in text and not re.match(r'\s*<(?:!doctype|html|svg|script|iframe|object|embed|\?xml)\b',text,re.I): mime='text/plain; charset=utf-8'
        except UnicodeError: pass
    if not mime: raise ValueError('文件类型不支持或内容与扩展名不符')
    return mime

def save_upload(stream, size, encoded_name):
    if not 0<size<=MAX_UPLOAD: raise ValueError('每个文件须在20MB以内且不能为空')
    name=unquote(encoded_name,encoding='utf-8',errors='strict').strip()
    if not name or len(name)>200 or '/' in name or '\\' in name or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('文件名不正确')
    directory=DATA/'uploads';directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    ident=secrets.token_hex(16);target=directory/ident;temporary=None;stored=False
    try:
        with tempfile.NamedTemporaryFile(dir=directory,prefix='.upload-',delete=False) as f:
            temporary=Path(f.name)
            left=size
            while left:
                block=stream.read(min(left,65536))
                if not block: raise ValueError('文件上传不完整，请重试')
                f.write(block);left-=len(block)
        mime=upload_mime(temporary,name)
        with connect() as c:
            c.execute('INSERT INTO uploads (id,name,size,mime,created) VALUES (?,?,?,?,?)',(ident,name,size,mime,dt.datetime.now().isoformat()))
            os.replace(temporary,target)
            stored=True
        return upload_info(dict(id=ident,name=name,size=size,mime=mime))
    except Exception:
        if stored: target.unlink(missing_ok=True)
        raise
    finally:
        if temporary: temporary.unlink(missing_ok=True)

def new_task(obj):
    child=clean(obj,'child',100)
    title=clean(obj,'title',200)
    if not title: raise ValueError('请填写待办标题')
    key=clean(obj,'request_key',64)
    if key and not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',key): raise ValueError('请保留本次提交标识后重试')
    box=clean(obj,'box',10) or 'inbox'; category=clean(obj,'category',20);advice=clean(obj,'advice',2000)
    if box not in ('inbox','wish'): raise ValueError('请选择收集箱或心愿')
    task=dict(id='MANUAL-'+(hashlib.sha256(key.encode()).hexdigest()[:20] if key else secrets.token_hex(10)),child=child,title=title,
              due=clean(obj,'due',200) or '无明确截止',original_status='待跟进',
              source=clean(obj,'source',200) or '家长录入',action=clean(obj,'action'))
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        names=child_names(c)
        if child not in names: raise ValueError('请选择孩子')
        task['child']=names[child]
        existing=c.execute('SELECT * FROM manual_tasks WHERE id=?',(task['id'],)).fetchone()
        if existing:
            if not key: raise sqlite3.IntegrityError('Duplicate manual task id')
            creation=c.execute('SELECT current FROM task_focus_history WHERE request_key=?',('new-task-'+key,)).fetchone()
            initial=json.loads(creation['current']) if creation else {}
            if dict(existing)!=task or (initial.get('box'),initial.get('category'),initial.get('next_action'))!=(box,category,advice):
                raise TaskError('这次收集已保存，内容已变化，请先到收集箱核对原事项',409,'task_create_conflict')
            return next(t for t in tasks(c) if t['id']==task['id'])
        c.execute('INSERT INTO manual_tasks (id,child,title,due,original_status,source,action) VALUES (?,?,?,?,?,?,?)',tuple(task.values()))
        if key or any(k in obj for k in ('box','category','advice')):
            family_task_focus.save(SimpleNamespace(**globals()),dict(id=task['id'],version=0,request_key='new-task-'+(key or secrets.token_hex(16)),mode='next',next_action=advice,waiting_for='',review_on='',box=box,category=category,due_on=family_agenda.date(task['due'])),connection=c)
    return task

def task_status(task, update=None):
    original=task['original_status']
    return update or (original if original in (*TASK_STATUSES,'已归档') else '已归档' if '已归档' in original else '待跟进')

def save_task(obj):
    ident=clean(obj,'id',30);status=clean(obj,'status',30);note=clean(obj,'note')
    if status not in TASK_STATUSES: raise TaskError('状态不正确')
    if status in ('已完成',*TASK_DISMISSED) and not note: raise TaskError('请补充完成依据或不参加、无需处理的原因')
    expected=clean(obj,'expected_updated',100) if 'expected_updated' in obj else None
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        task=next((t for t in tasks(c) if t['id']==ident),None)
        if task is None: raise TaskError('事项不存在，请刷新',404,'task_missing')
        previous=c.execute('SELECT * FROM task_updates WHERE id=?',(ident,)).fetchone()
        if not (previous and previous['status']==status and previous['note']==note):
            if expected is not None and expected!=(previous['updated'] if previous else ''):
                raise TaskError('事项已在别处更新，请刷新核对；本次选择尚未保存',409,'task_conflict')
            if previous and not c.execute('SELECT 1 FROM task_history WHERE task_id=?',(ident,)).fetchone():
                c.execute('INSERT INTO task_history (task_id,status,note,updated) VALUES (?,?,?,?)',tuple(previous))
            values=(ident,status,note,dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat())
            if status in TASK_CLOSED or task_status(task,previous['status'] if previous else None) in TASK_DISMISSED:
                family_study.task_changed(c,ident,dt.datetime.fromisoformat(values[3]))
            c.execute('INSERT INTO task_history (task_id,status,note,updated) VALUES (?,?,?,?)',values)
            c.execute('INSERT OR REPLACE INTO task_updates VALUES (?,?,?,?)',values)
        task['update']=dict(c.execute('SELECT * FROM task_updates WHERE id=?',(ident,)).fetchone())
        task['history']=[dict(r) for r in c.execute('SELECT * FROM task_history WHERE task_id=? ORDER BY id DESC',(ident,))]
    return task

def material_images(ids):
    if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(i,str) or not re.fullmatch('[a-f0-9]{32}',i) for i in ids):
        raise ValueError('每次最多整理3张图片')
    images=[]
    with connect() as c:
        for ident in dict.fromkeys(ids):
            row=c.execute('SELECT * FROM uploads WHERE id=?',(ident,)).fetchone()
            if row is None: raise ValueError('原件不存在，请先上传')
            if row['mime'] not in ['image/jpeg','image/png','image/webp']:
                raise ValueError('目前可整理文字及JPG、PNG、WebP图片；其他原件可保存并手动记录')
            p=DATA/'uploads'/ident
            if p.is_symlink(): raise ValueError('原件无法读取')
            images.append(dict(mime=row['mime'],data=p.read_bytes()))
    return images

def draft_from_material(obj):
    child=next((p for p in profiles() if p['id']==clean(obj,'child_id',100)),None)
    if child is None: raise ValueError('请先选择孩子，再整理草稿')
    draft=family_llm.extract_draft(clean(obj,'text',6000),material_images(obj.get('attachments',[])),
                                   target_child=child['name'],data_path=DATA)
    return dict(draft=draft,child_id=child['id'],child_name=child['name'])

def reading_feedback(obj):
    task=next((t for t in reading_store().snapshot()['tasks'] if t['id']==obj.get('id') and t['child_id']==obj.get('child_id')),None)
    if task is None: raise ValueError('阅读任务不存在，请刷新')
    if type(obj.get('version')) is not int or obj['version']!=task['version']:
        raise family_reading.ReadingError('作品或约定已更新，请刷新后再获取反馈',status=409)
    with connect() as c:
        image_ids=[i for i in task['attachments'] if (r:=c.execute('SELECT mime FROM uploads WHERE id=?',(i,)).fetchone()) and r['mime'] in ['image/jpeg','image/png','image/webp']]
    if len(image_ids)>3: raise ValueError('本次作品超过3张可读图片，请先选出重点并修改作品')
    agreement={key:task[key] for key in ['book','edition','scope','method','criteria']}
    result=family_llm.reading_feedback(agreement,task['work_text'],material_images(image_ids),clean(obj,'excerpt',4000),data_path=DATA)
    return dict(feedback=result,version=task['version'])

def calendar_text_range(text,today):
    """Only common explicit date phrases; the chosen range is returned to the parent."""
    ranges=[]; remaining=text
    if re.search(r'(最近|过去|近)(一|1)周',remaining):
        ranges.append((today-dt.timedelta(days=6),today));remaining=re.sub(r'(最近|过去|近)(一|1)周',' ',remaining)
    def add_date(match):
        value=dt.date.fromisoformat(match.group(0));ranges.append((value,value));return ' '
    remaining=re.sub(r'[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}',add_date,remaining)
    def add_chinese(match):
        year,month,day=match.groups();value=dt.date(int(year) if year else today.year,int(month),int(day))
        ranges.append((value,value));return ' '
    remaining=re.sub(r'(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]?',add_chinese,remaining)
    for phrase,offset in [('大后天',3),('后天',2),('明天',1),('今天',0),('昨天',-1),('前天',-2)]:
        if phrase in remaining:
            value=today+dt.timedelta(days=offset);ranges.append((value,value));remaining=remaining.replace(phrase,' ')
    monday=today-dt.timedelta(days=today.weekday())
    def add_week(match):
        prefix,weekday=match.groups()
        if not prefix and not weekday:return match.group(0)
        start=monday+dt.timedelta(weeks={'上上':-2,'上':-1,'下':1,'下下':2}.get(prefix,0))
        if weekday=='末': start+=dt.timedelta(days=5);end=start+dt.timedelta(days=1)
        elif weekday:
            start+=dt.timedelta(days='一二三四五六日'.index('日' if weekday=='天' else weekday));end=start
        else: end=start+dt.timedelta(days=6)
        ranges.append((start,end));return ' '
    remaining=re.sub(r'(上上|下下|上|下|本|这)?(?:周|星期)([一二三四五六日天末])?',add_week,remaining)
    if re.search(r'\d{4}/\d+/\d+|\d+月|月底|月初|下个月|下月|明年|下星期几|周几|(?:最近|过去|近)[两二三四五六七八九十\d]+周',remaining):
        raise ValueError('这句里的日期还不能明确，请选择查询日期范围或写成 YYYY-MM-DD')
    if not ranges:return None
    return min(start for start,end in ranges),max(end for start,end in ranges)

def is_calendar_question(question):
    return any(word in question for word in ['日历','日程','安排','课表','上课','什么课','空闲','做什么','要做','干什么','带什么'])

def calendar_query_range(question,start=None,end=None,now=None):
    today=(now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))).date()
    explicit=start is not None or end is not None
    if explicit:
        first=dt.date.fromisoformat(family_calendar._day(start));last=dt.date.fromisoformat(family_calendar._day(end))
        defaulted=False
    else:
        inferred=calendar_text_range(question,today) if is_calendar_question(question) else None
        first,last=inferred if inferred else (today-dt.timedelta(days=today.weekday()),today+dt.timedelta(days=6-today.weekday()))
        defaulted=inferred is None
    if not 0<=(last-first).days<31: raise ValueError('请选择按先后排列的1至31天（含首尾）')
    return dict(start=first.isoformat(),end=last.isoformat(),defaulted=defaulted)

def query_evidence(child,question,start=None,end=None,now=None):
    """Local bounded retrieval. Never obtains the household snapshot or attachment bytes."""
    today=now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    date_range=calendar_query_range(question,start,end,now=today)
    calendar_intent=is_calendar_question(question)
    selected=[];shortened=set()
    words=set(re.findall(r'[a-z0-9]+',question.lower()))
    for segment in re.findall(r'[\u3400-\u9fff]+',question):
        words.update(segment[i:i+2] for i in range(len(segment)-1))
    def keyword_rank(body):
        return sum(1 for word in words if word in body.lower())
    wanted_states={state for state in ('已完成',*TASK_DISMISSED) if state in question}
    if '无需处理' in question: wanted_states.add('不适用')
    if '已搁置' in question: wanted_states.update(TASK_DISMISSED)
    task_intent=bool(wanted_states) or any(word in question for word in [
        '待办','下一步','等待','以后再说','回看事项','做什么','要做','截止','本周','事项','未完成','没完成','待处理','待跟进','日程'])
    reading_intent=any(word in question for word in ['阅读','读书','书目','作品','印章','奖励','兑现','兑换','书架','成就','营灯','读完'])
    balance_intent=any(word in question for word in ['印章','余额','几枚','多少枚','成就','营灯'])
    redemption_intent=any(word in question for word in ['兑现','兑换','待兑现'])
    def clipped(value,limit=700):
        value='' if value is None else str(value)
        if len(value)>limit:
            shortened.add('字段');return value[:limit]+'…（字段已截断）'
        return value
    def record_item(row):
        parent=None
        if row.get('related_record_id'):
            parent=c.execute('SELECT title FROM records WHERE id=? AND child=?',(row['related_record_id'],child)).fetchone()
        relation=parent['title'] if parent else '关联原记录未找到（资料缺口）' if row.get('related_record_id') else '未关联'
        detail='；'.join(k+'：'+clipped(v) for k,v in [
            ('类别',row.get('category')),('科目',row.get('subject')),
            ('实得分',row.get('score') if row.get('score') is not None else '未记录'),
            ('满分',row.get('total') if row.get('total') is not None else '未记录'),
            ('关联原记录',relation),('跟进类型',row.get('followup_kind') or '未记录'),
            ('帮助情况',row.get('assistance') or '未记录（不能推定独立）'),
            ('与直接关联记录的材料关系',row.get('practice_relation') or '未记录（不能推定可比较）'),
            ('可比较条件说明',row.get('comparison_note') or '未记录'),
            ('建议明确选择',row.get('care_choice') or '未记录（自由文字不自动改变安排）'),
            ('明确改天日期',row.get('care_review_on') or '未指定；愿意尝试不表示已完成'),
            ('来源',row.get('source')),('原记录说明',row.get('note'))])
        return dict(id='record:'+str(row['id']),kind='record',target_id=row['id'],
                    title=clipped(row['title'],200),child=child,day=row['day'],detail=detail)
    with connect() as c:
        c.execute('BEGIN')
        names=child_names(c)
        if child not in names: raise ValueError('请选择当前档案中的孩子')
        child=names[child]
        children=profiles(c);calendar_child=next(p['id'] for p in children if p['name']==child)
        try:
            calendar=family_calendar.Store(connect,lambda:children,DATA,initialize=False).snapshot(date_range['start'],date_range['end'])
        except (OSError,ValueError,sqlite3.Error,TypeError):
            calendar=dict(events=[],timetables=[],source_error='日历资料读取失败，不能判断这段时间有哪些安排')
        calendar_events=[e for e in calendar['events'] if calendar_child in e['child_ids']]
        calendar_tables=[t for t in calendar['timetables'] if t['child_id']==calendar_child]
        total_records=c.execute('SELECT count(*) FROM records WHERE child=?',(child,)).fetchone()[0]
        rows=[dict(r) for r in c.execute('SELECT id,child,day,category,subject,title,note,source,score,total,related_record_id,followup_kind,assistance,practice_relation,comparison_note,care_choice,care_review_on FROM records WHERE child=? ORDER BY day DESC,id DESC LIMIT 200',(child,))]
        task_rows=[t for t in tasks(c) if t['child']==child]
        task_lookup={t['id']:t for t in task_rows}
        total_tasks=len(task_rows)
        updates={}
        for offset in range(0,len(task_rows),500):
            batch=task_rows[offset:offset+500];marks=','.join('?' for _ in batch)
            updates.update({r['id']:dict(r) for r in c.execute('SELECT * FROM task_updates WHERE id IN ('+marks+')',tuple(t['id'] for t in batch))})
        task_states={t['id']:task_status(t,updates[t['id']]['status'] if t['id'] in updates else None) for t in task_rows}
        unfinished={ident for ident,status in task_states.items() if status not in TASK_CLOSED}
        task_ranks={}
        for t in task_rows:
            update=updates.get(t['id'],{});status=task_states[t['id']]
            preferred=2 if task_intent and (status in wanted_states if wanted_states else t['id'] in unfinished) else 0
            urgent=0;due_order=0;updated=0
            # Interpret only an explicit ISO date. "本周" and other free text stay unknown.
            if task_intent and t['id'] in unfinished and re.fullmatch(r'\d{4}-\d{2}-\d{2}',t['due']):
                try:
                    due=dt.date.fromisoformat(t['due']);delta=(due-today.date()).days
                    urgent=3 if delta<0 else 2 if delta<=6-today.weekday() else 1
                    due_order=-due.toordinal()
                except ValueError: pass
            try:
                changed=dt.datetime.fromisoformat(update.get('updated',''))
                if changed.tzinfo is None: changed=changed.replace(tzinfo=today.tzinfo)
                updated=changed.timestamp()
            except (ValueError,OverflowError,OSError): pass
            text=' '.join(str(t.get(k,'') or '') for k in ['title','action','source','due'])+' '+str(update.get('note',''))+' '+json.dumps(t['focus'],ensure_ascii=False)+' '+{'next':'下一步','waiting':'等待中','later':'以后再说'}[t['focus']['mode']]
            task_ranks[t['id']]=(preferred,urgent,keyword_rank(text),due_order,updated)
        # Apply current-state and due-date priorities before the candidate limit.
        task_rows.sort(key=lambda t:task_ranks[t['id']],reverse=True)
        task_rows=task_rows[:200]
        care=care_notes(c);care_rows=[i for i in care['items'] if i['child']==child]
        groups={'record':[record_item(r) for r in rows],'task':[],'care':[],'calendar':[]}
        for kind,entries in [('calendar',calendar_events),('timetable',calendar_tables)]:
            for row in entries:
                if kind=='calendar':
                    detail='；'.join(label+'：'+clipped(value) for label,value in [
                        ('安排状态',{'confirmed':'已确定，不代表已参加或完成','tentative':'暂定，尚未确认','cancelled':'已取消'}[row['status']]),
                        ('开始',row['start_time'] or '未填钟点'),('结束',row['end_time'] or '未填钟点'),
                        ('地点',row['location'] or '未填写'),('要求',row['note']),('来源',row['source'] or '家长手动安排'),
                        ('重复','每周，当前日期为这一次发生日' if row['repeat']=='weekly' else '单次')])
                    linked=task_lookup.get(row['task_id']) if row['task_id'] else None
                    if linked: detail+='；家庭当前事项决定：'+task_status(linked,updates.get(linked['id'],{}).get('status'))+'；保留学校原安排不代表家庭参加'
                else:
                    detail='课次：'+clipped('；'.join(s['slot']+' '+s['title'] for s in row['sessions']))+'；仅有节次，未提供对应钟点，不能据此判断空闲；说明：'+clipped(row['note'])+'；来源：'+clipped(row['source'])
                digest=hashlib.sha256(json.dumps([kind,row['id'],row['day']]).encode()).hexdigest()[:32]
                groups['calendar'].append(dict(id=kind+':'+digest,kind=kind,target_id=row['id'],title=clipped(row['title'],200),child=child,day=row['day'],detail=detail))
        for t in task_rows:
            update=updates.get(t['id']) or {}
            detail='；'.join(k+'：'+clipped(v) for k,v in [
                ('截止描述',t['due']),('当前状态',task_states[t['id']]),
                ('当前反馈',update.get('note','尚无反馈')),('反馈时间',update.get('updated','')),
                ('原始状态',t['original_status']),('来源',t['source']),('原建议动作',t['action']),
                ('家庭跟进安排',{'next':'下一步可推进','waiting':'等待条件，不应说成现在即可执行','later':'以后再说，不应当成今天必须执行'}[t['focus']['mode']]),
                ('家长明确的下一步',t['focus']['next_action'] or '未单独填写'),('等待对象或条件',t['focus']['waiting_for'] or '未填写'),
                ('家庭回看日期',t['focus']['review_on'] or '未约定'),('安排含义','回看日期不是学校截止时间；这些安排不表示完成')])
            groups['task'].append(dict(id='task:'+t['id'],kind='task',target_id=t['id'],
                title=clipped(t['title'],200),child=child,day=clipped(t['due'],200),detail=detail))
        for item in care_rows:
            review_status=item['review_status']
            review=('家长暂不考虑，已停止推荐，仅供回顾' if review_status=='declined' else
                    '已延期，尚未到回看日期，不是当前需执行的建议' if review_status=='deferred' and item['review_on']>today.date().isoformat() else
                    '延期回看日期已到，仅待回看，不代表已执行' if review_status=='deferred' else
                    '家长明确愿意试试，仍按原日期回看；不表示已执行或已有成效' if review_status=='accepted' else
                    '未确认停推或延期，是否采纳或执行须核对家长反馈')
            detail='；'.join(k+'：'+clipped(v) for k,v in [
                ('主题',item['topic']),('依据',item['evidence']),('原建议动作',item['action']),('回看状态',review),
                ('明确选择',item['care_choice'] or '未记录'),('选择记录ID',item['choice_record_id'] or '未记录'),
                ('回看日期',item['review_on']),('有效至',item['expires_on']),
                ('当前有效性','已过期，仅供回顾' if item['expires_on']<today.date().isoformat() else '有效期内仍须遵守回看状态，不表示当前待执行')])
            groups['care'].append(dict(id='care:'+item['id'],kind='care',target_id=item['id'],
                title=clipped(item['title'],200),child=child,day=item['review_on'],detail=detail))
        # Query only the selected stable child ID and current reading fields. Do not
        # load the full reading snapshot, history, upload names or attachment bytes.
        child_ids=[p['id'] for p in profiles(c) if p['name']==child]
        reading_total=redemption_total=0;reading_rows=[];redemption_rows=[]
        reading_tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('reading_tasks','reading_awards','reading_redemptions')")}
        reading_ready=len(child_ids)==1 and len(reading_tables)==3
        if reading_ready:
            child_id=child_ids[0]
            reading_total=c.execute('SELECT count(*) FROM reading_tasks WHERE child_id=?',(child_id,)).fetchone()[0]
            redemption_total=c.execute('SELECT count(*) FROM reading_redemptions WHERE child_id=?',(child_id,)).fetchone()[0]
            reading_rows=[dict(r) for r in c.execute('''SELECT t.id,t.book,t.edition,t.scope,t.method,t.criteria,t.state,
                t.work_text,t.parent_note,t.planned_on,t.updated,t.stamps,a.amount,a.status AS award_status,a.reason AS award_reason
                FROM reading_tasks t LEFT JOIN reading_awards a ON a.task_id=t.id AND a.child_id=t.child_id
                WHERE t.child_id=? ORDER BY t.updated DESC,t.id DESC LIMIT 200''',(child_id,))]
            redemption_rows=[dict(r) for r in c.execute('''SELECT id,state,reward,cost,planned_on,note,correction_note,updated
                FROM reading_redemptions WHERE child_id=? ORDER BY updated DESC,id DESC LIMIT 200''',(child_id,))]
            groups.update(reading=[],reading_balance=[],reading_redemption=[])
            for r in reading_rows:
                detail='；'.join(k+'：'+clipped(v,limit) for k,v,limit in [
                    ('当前状态',r['state'],20),('约定印章',r['stamps'],10),('奖项状态',r['award_status'] or '尚未发放',20),
                    ('奖项数量',r['amount'] if r['amount'] is not None else '尚未发放',10),
                    ('奖项更正原因',r['award_reason'] or '无',100),('家长当前反馈',r['parent_note'] or '未记录',150),
                    ('作品文字',r['work_text'] or '没有文字；可能另有原件，本次未读取',260),
                    ('安排日期',r['planned_on'] or '未约定',20),('书籍版本',r['edition'] or '未注明',40),
                    ('阅读范围',r['scope'] or '尚未约定',100),('表达方式',r['method'] or '尚未约定',40),
                    ('完成条件',r['criteria'] or '尚未约定',100)])
                groups['reading'].append(dict(id='reading:'+r['id'],kind='reading',target_id=r['id'],
                    title=clipped(r['book'] or '尚未确定书名的阅读草案',200),child=child,day=r['updated'][:10],detail=detail))
            for r in redemption_rows:
                detail='；'.join(k+'：'+clipped(v,500) for k,v in [
                    ('当前兑现状态',r['state']),('使用印章',r['cost']),('约定日期',r['planned_on'] or '未约定'),
                    ('当前依据',r['note']),('兑现更正说明',r['correction_note'] or '无')])
                groups['reading_redemption'].append(dict(id='reading_redemption:'+r['id'],kind='reading_redemption',target_id=r['id'],
                    title=clipped(r['reward'],200),child=child,day=r['updated'][:10],detail=detail))
            # An initialized zero wallet alone must not turn an empty family into evidence.
            if reading_total or redemption_total:
                earned,active=c.execute("SELECT coalesce(sum(amount),0),coalesce(sum(CASE WHEN status<>'已撤销' THEN amount ELSE 0 END),0) FROM reading_awards WHERE child_id=?",(child_id,)).fetchone()
                totals={r['state']:r['cost'] for r in c.execute('SELECT state,sum(cost) AS cost FROM reading_redemptions WHERE child_id=? GROUP BY state',(child_id,))}
                reserved=totals.get('待兑现',0);spent=totals.get('已兑现',0);available=active-reserved-spent
                detail=(f'历史首次获得{earned}枚；待兑现预留{reserved}枚；已兑现使用{spent}枚；当前可用{available}枚。'
                    '历史累计包含后来撤销的奖项，重新确认不重复累计；可用余额已剔除撤销并扣除预留及已兑现。'
                    '累计成就不消耗余额；任务奖励与记录能量完全独立。待兑现不是实际已交付。')
                if available<0: detail='印章账目出现不一致，当前余额不能作可兑换依据，请家长核对。'
                groups['reading_balance'].append(dict(id='reading_balance:'+child_id,kind='reading_balance',target_id=child_id,
                    title='阅读印章与兑现余额',child=child,day=today.date().isoformat(),detail=detail))
        def relevance(item):
            if item['kind'] in ('calendar','timetable'):
                return (7 if calendar_intent else 0,0,keyword_rank(item['title']+' '+item['detail']),0,0)
            if item['kind'].startswith('reading'):
                priority=(6 if item['kind']=='reading_balance' and balance_intent or item['kind']=='reading_redemption' and redemption_intent
                          else 5 if item['kind']=='reading' else 3) if reading_intent else 0
                return (priority,0,keyword_rank(item['title']+' '+item['detail']),0,0)
            if item['kind']=='task': return task_ranks[item['target_id']]
            return (0,0,keyword_rank(item['title']+' '+item['detail']),0,0)
        for group in groups.values():
            group.sort(key=relevance,reverse=True)
            selected.extend(group[:4])
        selected.sort(key=relevance,reverse=True)
        selected=selected[:12]
        extra=[i for group in groups.values() for i in group if i not in selected]
        extra.sort(key=relevance,reverse=True)
        selected.extend(extra[:max(0,12-len(selected))])
        selected.sort(key=relevance,reverse=True)
        # Expand same-child parent/followup links, with a hard context cap.
        seen={i['id'] for i in selected};cursor=0
        while cursor<len(selected) and len(selected)<20:
            item=selected[cursor];cursor+=1
            if item['kind']!='record': continue
            row=c.execute('SELECT related_record_id FROM records WHERE id=? AND child=?',(item['target_id'],child)).fetchone()
            related=[dict(r) for r in c.execute('SELECT id,child,day,category,subject,title,note,source,score,total,related_record_id,followup_kind,assistance,practice_relation,comparison_note FROM records WHERE child=? AND (id=? OR related_record_id=?) ORDER BY day DESC,id DESC LIMIT 21',
                        (child,row['related_record_id'],item['target_id']))]
            for r in related:
                key='record:'+str(r['id'])
                if key not in seen and len(selected)<20:
                    selected.append(record_item(r));seen.add(key)
        # Keep the exact excerpts sent to the model as the returned citation details.
        for item in selected:
            if len(item['detail'])>1100:
                item['detail']=item['detail'][:1100]+'…（字段已截断）';shortened.add('字段')
        while selected and len(json.dumps(selected,ensure_ascii=False))>14500:
            selected.pop();shortened.add('上下文')
        selected_ids={i['target_id'] for i in selected if i['kind']=='record'}
        incomplete=False
        for item in selected:
            if item['kind']!='record': continue
            parent=c.execute('SELECT related_record_id FROM records WHERE id=? AND child=?',(item['target_id'],child)).fetchone()[0]
            descendants=[r[0] for r in c.execute('SELECT id FROM records WHERE child=? AND related_record_id=?',(child,item['target_id']))]
            missing=bool(parent and parent not in selected_ids or any(i not in selected_ids for i in descendants))
            incomplete|=missing
            item['detail']+='；直接后续记录数：'+str(len(descendants))+'；本次链路'+('未全部纳入，不能断言从未复测' if missing else '已包含此记录的直接关联')
    amounts={kind:sum(i['kind']==kind for i in selected) for kind in ['record','task','care','reading','reading_balance','reading_redemption']}
    included_unfinished=sum(i['kind']=='task' and i['target_id'] in unfinished for i in selected)
    days=[i['day'] for i in selected if i['kind']=='record']
    coverage=(f'当前北京时间：{today.strftime("%Y-%m-%d %H:%M")}。仅检索所选孩子的当前资料。'
              f'记录候选为按日期倒序最近{len(rows)}/{total_records}条；待办先按问题意图、当前状态、明确截止日期和反馈时间排序，再选{len(task_rows)}/{total_tasks}项候选，候选截断{total_tasks-len(task_rows)}项；'
              f'当前未完成（含待核查）共{len(unfinished)}项，本次纳入{included_unfinished}项、未纳入{len(unfinished)-included_unfinished}项。截止仅解析明确ISO日期，其他时间描述保留原文；'
              f'可读取陪伴建议{len(care_rows)}条，其中暂不考虑{sum(i["review_status"]=="declined" for i in care_rows)}条、延期{sum(i["review_status"]=="deferred" for i in care_rows)}条，包含历史，不能都视为当前待执行建议。按问题关键词及近况选取，并补充同一孩子的订正关联；'
              f'本次提供记录{amounts["record"]}条、待办{amounts["task"]}项、建议{amounts["care"]}条，最多20条。')
    if days: coverage+=f'本次记录日期为{min(days)}至{max(days)}。'
    if total_records>len(rows) or total_tasks>len(task_rows): coverage+='候选范围已截断，部分资料未全部检索。'
    if shortened: coverage+='部分字段或上下文已截断。'
    if incomplete: coverage+='部分订正链未全部纳入。'
    if care['error']: coverage+='陪伴资料核对提示：'+care['error']
    included_calendar=sum(i['kind'] in ('calendar','timetable') for i in selected)
    coverage+=(f"日历查询范围：{date_range['start']}至{date_range['end']}（北京时间日期）；已读同孩安排{len(calendar_events)}项、课表日期{len(calendar_tables)}项，本次纳入{included_calendar}项，未纳入{len(calendar_events)+len(calendar_tables)-included_calendar}项。"
               '没有录入不等于没有实际安排，也不能推定空闲；只有课次的课表不能推定上课钟点。')
    if calendar['source_error']: coverage+='日历缺口：'+calendar['source_error']+'。'
    if not (DATA/'日历来源.json').exists(): coverage+='学校日历与课表来源尚未录入。'
    elif not calendar_tables: coverage+='本范围没有载入该孩子的课表，可能未覆盖这些日期。'
    if reading_ready and (reading_total or redemption_total):
        coverage+=(f'阅读任务按最近更新时间选{len(reading_rows)}/{reading_total}项候选，本次纳入{amounts["reading"]}项；'
                   f'兑现记录按最近更新时间选{len(redemption_rows)}/{redemption_total}项候选，本次纳入{amounts["reading_redemption"]}项；'
                   f'印章余额摘要纳入{amounts["reading_balance"]}项，余额汇总该孩子全部奖项和兑现记录。阅读相关问题优先选择阅读证据。')
        if reading_total>len(reading_rows) or redemption_total>len(redemption_rows): coverage+='阅读或兑现候选范围已截断，较早项未全部检索。'
    else: coverage+='本次没有可读取的专用阅读任务或兑现记录，不以零余额推断实际奖励情况。'
    coverage+='帮助情况与练习关系按实际字段记录，空值为未知；旧的独立复测标签本身不能证明独立完成，不由分数变化推断掌握或前后可比较。不含附件正文、群聊原文、未录入资料及完整修改历史；本次未检索到不等于历史不存在。不能由成长能量推断奖励已兑现；待兑现与已兑现分别判断。'
    return selected,coverage

def teacher_query_evidence(child, question, start=None, end=None, now=None):
    # Query existing records without initializing optional tables or running a source check.
    with connect() as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'teachers','teacher_observations'} <= names:
            return [], ''
        child_id = next(p['id'] for p in profiles(c) if p['name'] == child)
        teachers = {r['id']: family_teachers.Store._view(r) for r in c.execute('SELECT * FROM teachers')}
        teachers = {key: t for key,t in teachers.items() if child_id in t['child_ids'] and not t['archived']}
        if not any(word in question for word in ['老师','教师','表扬'] + [t['display_name'] for t in teachers.values()]):
            return [], ''
        if start is None:
            inferred = calendar_text_range(question, (now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))).date())
            if inferred:
                first, last = inferred
                if not 0 <= (last-first).days < 31: raise ValueError('请选择按先后排列的1至31天（含首尾）')
                start, end = first.isoformat(), last.isoformat()
        rows = []
        for raw in c.execute('SELECT * FROM teacher_observations'):
            row = family_teachers.Store._view(raw)
            teacher = teachers.get(row['teacher_id'])
            if teacher is None or row['status'] != 'active' or row['child_id'] and row['child_id'] != child_id:
                continue
            if family_teachers.observation_scope(row, teacher) != child_id: continue
            if start and not start <= row['day'] <= end: continue
            rows.append(row)
    rows.sort(key=lambda r: (teachers[r['teacher_id']]['display_name'] in question,
                             bool(teachers[r['teacher_id']]['subject'] and teachers[r['teacher_id']]['subject'] in question),
                             r['day'], r['updated']), reverse=True)
    evidence = []
    def excerpt(label, value, limit):
        return label + value[:limit] + ('…（节选）' if len(value) > limit else '')
    for row in rows[:6]:
        teacher = teachers[row['teacher_id']]
        # Reserve scope and provenance before shortening free text; never cut away whose praise this is.
        detail = '；'.join(['对象：' + {'household':'本家孩子','other_students':'其他学生的行为','class':'全班'}[row['target']],
            excerpt('来源：', row['source_url'] or row['source_id'] or '家长手动记录', 180),
            excerpt('行为或要求：', row['behavior'], 330),
            excerpt('老师明确说的理由：', row['teacher_reason'], 220) if row['teacher_reason'] else '尚未记录老师明确说的理由，原因未知',
            excerpt('家长待核实理解：', row['parent_note'], 220) if row['parent_note'] else '没有家长推测'])
        evidence.append(dict(id='teacher_observation:'+row['id'],kind='teacher',target_id=teacher['id'],
            title=teacher['display_name']+' · '+{'requirement':'明确要求','praise':'表扬记录','preference':'明确教学偏好'}[row['kind']]
                +' · '+{'household':'本家孩子','other_students':'其他学生','class':'全班'}[row['target']],
            child=child,day=row['day'],detail=detail))
    return evidence, ('老师观察范围：'+(start+'至'+end if start else '已保存历史，未限定日期')+'。本次另选同一孩子老师档案中最近或与问题相关的'+str(len(evidence))+'/'+str(len(rows))+
        '条有效观察。老师明确理由与家长理解分开；理由未记录就说未知。不能从一次表扬推断长期偏好、人格或偏爱某人；'
        '建议聚焦孩子可选择的具体学习行为，不建议送礼、讨好或牺牲休息。公开网页是未核对来源资料，不是事实自动认证，本次未作为偏好证据。')


def ask_family(obj):
    if not isinstance(obj,dict) or set(obj)-{'child','question','start','end'}: raise ValueError('查询字段不正确')
    if ('start' in obj)!=('end' in obj) or 'start' in obj and (not isinstance(obj['start'],str) or not isinstance(obj['end'],str)):
        raise ValueError('查询日期须同时提供有效的开始和结束日期，或都不填写')
    child=clean(obj,'child',100);question=clean(obj,'question',1000)
    names=child_names()
    if child not in names: raise ValueError('请选择当前档案中的孩子')
    child=names[child]
    if not question: raise ValueError('请填写1000字以内的问题')
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    date_range=calendar_query_range(question,obj.get('start'),obj.get('end'),now=now)
    evidence,coverage=query_evidence(child,question,date_range['start'],date_range['end'],now=now)
    teacher_evidence,teacher_coverage=teacher_query_evidence(child,question,
        None if date_range['defaulted'] else date_range['start'], None if date_range['defaulted'] else date_range['end'], now=now)
    if teacher_coverage:
        evidence=(teacher_evidence+evidence)[:12]
        coverage='以下常规资料数量是合并老师证据前的候选统计，不等于最终纳入数量：'+coverage+teacher_coverage
        coverage+='最终提供'+str(len(teacher_evidence))+'条老师观察和'+str(len(evidence)-len(teacher_evidence))+'条常规资料，省略部分不能据此视为不存在。'
    if not evidence:
        return dict(answer='当前可检索的记录、待办和陪伴建议中没有这个孩子的可用资料，暂时无法回答。请先补充相关记录；这不表示实际没有发生。日历和课表没录入不代表没有安排或空闲。',citations=[],coverage=coverage,calendar_range=date_range)
    result=family_llm.answer_question(evidence[0]['child'],question,evidence,coverage,data_path=DATA)
    # The model selects IDs only. Never use model-provided titles, children or targets.
    mapping={item['id']:item for item in evidence}
    return dict(answer=result['answer'],citations=[mapping[i] for i in result['citation_ids']],coverage=coverage,calendar_range=date_range)

def calendar_draft_from_text(obj):
    if not isinstance(obj,dict) or set(obj)!={'text','child_ids'}: raise ValueError('请提供安排文字和明确选择的孩子')
    text=clean(obj,'text',2000)
    if not text: raise ValueError('请写一句想安排的事')
    children=profiles();known={p['id']:p['name'] for p in children};selected=obj['child_ids']
    if not isinstance(selected,list) or any(not isinstance(i,str) or i not in known for i in selected) or len(set(selected))!=len(selected):
        raise ValueError('请选择现有孩子，或留空后在草稿里确认')
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date();reference=today.isoformat();notes=[]
    intent='cancel' if re.search(r'取消|不去|不参加',text) else 'edit' if re.search(r'改期|改到|改成|改为|推迟|提前到|挪到|调整原|修改原',text) else ''
    if intent:
        return dict(intent=intent,draft=None,needs_review=['这句话涉及已有安排，请从日历打开原安排，再修改或取消；没有新增任何安排。'],reference_date=reference)
    named=[ident for ident,name in known.items() if name and name in text]
    if re.search(r'所有孩子|全家',text) or len(known)==2 and re.search(r'两个孩子|两位孩子',text): named=list(known)
    if selected and any(ident not in selected for ident in named):
        allowed=[];notes.append('文字提到的孩子与所选孩子不一致，请重新确认归属。')
    else: allowed=selected or named
    if len(known)!=2 and re.search(r'两个孩子|两位孩子',text) and len(selected)!=2:
        allowed=[];notes.append('请明确这次参加的是哪两个孩子。')
    try: inferred=calendar_text_range(text,today)
    except (ValueError,OverflowError):
        inferred=None;notes.append('原话中的日期还不能明确，请在草稿里选择具体日期。')
    day_hint=inferred[0].isoformat() if inferred and inferred[0]==inferred[1] else ''
    if re.search(r'每(?:个)?(?:周|星期)',text) and not re.search(r'\d{4}-\d{2}-\d{2}|\d+月\d+|今天|明天|后天',text):
        day_hint='';notes.append('每周安排需要确认第一次发生的具体日期。')
    result=family_llm.calendar_draft(text,[dict(id=i,name=n) for i,n in known.items()],allowed,reference,day_hint,data_path=DATA)
    intent=result.pop('intent');notes.extend(result.pop('needs_review'))
    if intent!='create':
        notes.append('请从日历打开原安排修改或取消。' if intent in ('edit','cancel') else '这句话尚未明确要新增什么，请补充安排内容；查询可用“查资料”。')
        return dict(intent=intent,draft=None,needs_review=list(dict.fromkeys(notes)),reference_date=reference)
    try:
        for key in ('day','until'): family_calendar._day(result[key],optional=True)
        for key in ('start_time','end_time'): family_calendar._clock(result[key])
        if result['end_time'] and (not result['start_time'] or result['end_time']<=result['start_time']): raise ValueError()
        if result['repeat']=='weekly' and not re.search(r'每(?:个)?(?:周|星期)',text): raise ValueError()
        if result['until'] and (result['repeat']!='weekly' or result['until'] not in text or not result['day'] or result['until']<result['day']): raise ValueError()
    except (ValueError,TypeError):
        raise family_llm.LLMDraftError('日历草稿日期、钟点或重复规则无法核验，请重试或手动填写') from None
    result['status']='tentative'
    if not result['title']: notes.append('请补充具体要安排什么。')
    if not result['child_ids']: notes.append('请明确选择参加的孩子。')
    if not result['day']: notes.append('请确认具体日期，系统没有替你选择今天或周末某一天。')
    notes.append('这是未保存的暂定草稿，请核对后再保存。')
    return dict(intent='create',draft=result,needs_review=list(dict.fromkeys(notes)),reference_date=reference)

def transcribe_material(obj):
    ident=clean(obj,'attachment',32)
    if not re.fullmatch('[a-f0-9]{32}',ident): raise ValueError('请选择一份已上传的语音')
    with connect() as c: row=c.execute('SELECT * FROM uploads WHERE id=?',(ident,)).fetchone()
    if row is None or row['mime'] not in ['audio/wav','audio/mpeg','audio/mp4','audio/webm','audio/ogg']:
        raise ValueError('请选择一份已上传的语音')
    path=DATA/'uploads'/ident
    if path.is_symlink(): raise ValueError('原件无法读取')
    with path.open('rb') as f: raw=f.read(MAX_UPLOAD+1)
    if not raw or len(raw)>MAX_UPLOAD: raise ValueError('语音原件为空或超过20MB')
    mime=row['mime']
    if mime=='audio/webm':
        # WhisperKit cannot decode browser WebM; pipe-only decoding cannot fetch URLs.
        try:
            result=subprocess.run(['ffmpeg','-nostdin','-v','error','-protocol_whitelist','pipe',
                '-i','pipe:0','-t','181','-ac','1','-ar','16000','-f','s16le','pipe:1'],
                input=raw,capture_output=True,check=True,timeout=45)
        except (OSError,subprocess.SubprocessError):
            raise family_llm.LLMDraftError('录音格式转换失败，请重试或上传WAV、M4A、OGG；原件仍保留') from None
        if not result.stdout or len(result.stdout)>180*16000*2:
            raise ValueError('请提供3分钟以内且包含声音的录音')
        out=io.BytesIO()
        with wave.open(out,'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(result.stdout)
        raw=out.getvalue();mime='audio/wav'
    return family_llm.transcribe_audio(raw,mime)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def json_body(self,body,kind):
        if len(body)>=1024 and kind.startswith('application/json'):
            headers={'Vary':'Accept-Encoding'}
            if accepts_gzip(self.headers.get('Accept-Encoding','')):
                return gzip.compress(body,mtime=0),{**headers,'Content-Encoding':'gzip'}
            return body,headers
        return body,{}
    def reply(self,code,body,kind='application/json; charset=utf-8',disposition=None,preview=False,headers=None):
        if not isinstance(body,bytes): body=json.dumps(body,ensure_ascii=False).encode()
        body,encoding=self.json_body(body,kind)
        self.send_response(code);self.send_header('Content-Type',kind)
        if code != 304: self.send_header('Content-Length',str(len(body)))
        for key,value in {'Cache-Control':'no-store',**encoding,**(headers or {})}.items(): self.send_header(key,value)
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','SAMEORIGIN' if preview else 'DENY')
        if disposition: self.send_header('Content-Disposition',disposition)
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors "+("'self'" if preview else "'none'"))
        self.end_headers();self.wfile.write(body)
    def reply_static(self,files,kind,reply=None):
        body,compressed,etag=asset(files)
        headers={'Cache-Control':'private, no-cache','ETag':etag,'Vary':'Accept-Encoding'}
        if len(body)>=1024 and accepts_gzip(self.headers.get('Accept-Encoding','')):
            body=compressed;headers['Content-Encoding']='gzip'
        matches=self.headers.get('If-None-Match','').split(',')
        unchanged=any(tag.strip()=='*' or tag.strip().removeprefix('W/')==etag.removeprefix('W/') for tag in matches)
        return (reply or self.reply)(304 if unchanged else 200,b'' if unchanged else body,kind,headers=headers)
    def local_host(self):
        host=self.headers.get('Host','').split(':')[0]
        # Tailscale Serve forwards its validated hostname to this loopback-only service.
        allowed={'127.0.0.1','localhost',os.environ.get('FAMILY_HOST','')}
        if host == os.environ.get('FAMILY_HOST'):
            return bool(os.environ.get('FAMILY_USER')) and self.headers.get('Tailscale-User-Login') == os.environ['FAMILY_USER']
        return bool(host) and host in allowed
    def authorize_request(self):
        def deny(status, message, headers=None):
            self.close_connection=True
            self.reply(status,{'error':message},headers=headers)
            return False
        try:
            hosts=self.headers.get_all('Host',[])
            if len(hosts)!=1 or len(hosts[0])>255 or any(ord(c)<33 or ord(c)==127 for c in hosts[0]): raise ValueError()
            parsed=urlsplit('//'+hosts[0])
            if not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment or parsed.port==0: raise ValueError()
            host=parsed.hostname.lower()
        except ValueError:
            return deny(403,'访问地址未授权')
        path=urlparse(self.path).path
        child_request = 'X-Child-CSRF' in self.headers or any(piece.strip().startswith(family_child.COOKIE+'=')
            for piece in self.headers.get('Cookie','').split(';'))
        # Loopback tools stay local. A forwarded request cannot claim this exception by changing Host.
        forwarded=any(name in self.headers for name in ('Forwarded','X-Forwarded-For','X-Forwarded-Host',
                       'X-Forwarded-Proto','X-Real-IP','Tailscale-User-Login'))
        if host in ('127.0.0.1','localhost') and not forwarded and self.client_address[0] in ('127.0.0.1','::1'):
            if child_request and path!='/child' and not path.startswith('/child/'):
                return deny(403,'孩子凭据不能用于家长入口，请从孩子页面操作')
            return True
        try: config=family_access.read_config(DATA)
        except family_access.AccessError as error:
            return deny(503,str(error))
        if config is None:
            if host in ('127.0.0.1','localhost'): return deny(403,'转发访问需要配置家庭认证')
            return True if self.local_host() else deny(403,'访问地址未授权')
        allowed={'127.0.0.1','localhost',urlsplit(config['base_url']).hostname,os.environ.get('FAMILY_HOST','')}
        if host not in allowed: return deny(403,'访问地址未授权')
        path=urlparse(self.path).path
        if path=='/child' or path.startswith('/child/'):
            return True  # The child router requires its own invite/session; no parent identity is inherited.
        try:
            if family_access.dispatch(self,config,connect,ROOT): return False
            if family_access.session_authorized(self.headers,config,connect): return True
        except (OSError,sqlite3.Error):
            return deny(503,'登录状态暂不可读取，请稍后重试')
        has_cookie=family_access.has_session_cookie(self.headers)
        if (not has_cookie or path=='/calendar.ics') and family_access.authorized(self.headers,config): return True
        if self.command=='GET' and path=='/' and 'text/html' in self.headers.get('Accept',''):
            self.reply(303,b'',headers={'Location':urlsplit(config['base_url']).path.rstrip('/')+'/login'})
            return False
        return deny(401,'请登录家庭账号后重试，当前输入请保留',{'WWW-Authenticate':'Basic realm="Family Agent", charset="UTF-8"'} if path=='/calendar.ics' else {})
    def bridge_authorized(self):
        secret=os.environ.get('FAMILY_PRINT_BRIDGE_TOKEN','')
        header=self.headers.get('Authorization','')
        return bool(secret) and secrets.compare_digest(header.encode(),('Bearer '+secret).encode())
    def do_GET(self):
        if not self.authorize_request(): return
        path=urlparse(self.path).path
        if family_child.dispatch_get(SimpleNamespace(**globals()),self,path): return
        try:
            if path.startswith('/api/print/bridge/'):
                if not self.bridge_authorized(): return self.reply(403,{'error':'打印桥接未授权'})
                if path.startswith('/api/print/bridge/pdf/'):
                    claim=self.headers.get('X-Print-Claim','')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',claim): return self.reply(403,{'error':'打印领取凭据无效'})
                    body,name=print_store().claimed_pdf(path[len('/api/print/bridge/pdf/'):],claim)
                    return self.reply(200,body,'application/pdf',"attachment; filename*=UTF-8''"+quote(name,safe=''))
                return self.reply(404,{'error':'不存在'})
            if path=='/api/child-access': return self.reply(200,family_child.parent_action(SimpleNamespace(**globals()),'state',{}))
            if path=='/api/state': return self.reply(200,snapshot())
            if path=='/api/agent/collector': return self.reply(200,agent_store().collector_plan())
            if path=='/api/teachers': return self.reply(200,teacher_store().snapshot())
            if path=='/api/settings': return self.reply(200,settings_store().snapshot())
            if path=='/api/agent': return self.reply(200,agent_store().snapshot())
            if path=='/api/goals': return self.reply(200,goal_store().snapshot())
            if path=='/api/agent/message':
                query=parse_qs(urlparse(self.path).query,keep_blank_values=True)
                if any(len(values)!=1 for values in query.values()):
                    raise family_agent.AgentError('请提供唯一的孩子、来源和消息编号')
                return self.reply(200,agent_store().message({key:values[0] for key,values in query.items()},upload_info))
            if path=='/api/study':
                query=parse_qs(urlparse(self.path).query,keep_blank_values=True)
                if set(query)!={'child_id','day'} or any(len(v)!=1 for v in query.values()):
                    raise family_study.StudyError('请提供唯一的孩子和日期')
                return self.reply(200,study_store().snapshot(query['child_id'][0],query['day'][0]))
            if path=='/api/calendar':
                query=parse_qs(urlparse(self.path).query,keep_blank_values=True)
                if set(query)!={'start','end'} or any(len(v)!=1 for v in query.values()):
                    raise family_calendar.CalendarError('请提供唯一的开始及结束日期')
                return self.reply(200,calendar_snapshot(query['start'][0],query['end'][0]))
            if path=='/calendar.ics':
                if urlparse(self.path).query: raise family_calendar.CalendarError('家庭日历订阅不接受筛选参数')
                return self.reply(200,calendar_subscription(),'text/calendar; charset=utf-8','inline; filename="family-calendar.ics"')
            if path=='/api/record/history' or path.startswith('/api/record/history/'):
                ident=path.removeprefix('/api/record/history/')
                if not re.fullmatch(r'[1-9][0-9]{0,18}',ident) or int(ident)>9223372036854775807:
                    return self.reply(400,dict(error='记录编号须为有效正整数'))
                try: result=record_history(int(ident))
                except (ValueError,TypeError,OverflowError): return self.reply(500,dict(error='当前记录格式无法读取，资料未更改'))
                return self.reply(200,result) if result is not None else self.reply(404,dict(error='当前记录不存在，无法读取其更正历史'))
            if path=='/api/print/jobs': return self.reply(200,dict(jobs=print_store().list_jobs()))
            if path.startswith('/api/print/preview/'):
                body,name=print_store().preview(path[len('/api/print/preview/'):])
                return self.reply(200,body,'application/pdf',"inline; filename*=UTF-8''"+quote(name,safe=''),preview=True)
            if path=='/app.bundle.js':
                return self.reply_static(tuple(ROOT/name for name in BUNDLE),'text/javascript; charset=utf-8')
            if path in STATIC:
                p=ROOT/STATIC[path]
                if not p.is_file(): return self.reply(404,{'error':'不存在'})
                kind='text/html' if path=='/' else 'text/css' if path.endswith('.css') else 'text/javascript'
                return self.reply_static((p,),kind+'; charset=utf-8')
            if path.startswith('/upload/'):
                ident=path[len('/upload/'):]
                if not re.fullmatch(r'[a-f0-9]{32}',ident): return self.reply(404,{'error':'附件不存在'})
                with connect() as c: row=c.execute('SELECT * FROM uploads WHERE id=?',(ident,)).fetchone()
                p=DATA/'uploads'/ident
                if row is None or p.is_symlink() or not p.is_file(): return self.reply(404,{'error':'附件不存在'})
                mode='inline' if row['mime'].startswith(('image/','audio/')) else 'attachment'
                return self.reply(200,p.read_bytes(),row['mime'],mode+"; filename*=UTF-8''"+quote(row['name'],safe=''))
            if path.startswith('/attachment/'):
                name=unquote(path[len('/attachment/'):]);base=(DATA/'attachments').resolve();p=(base/name).resolve()
                if p.parent!=base or not p.is_file(): return self.reply(404,{'error':'附件不存在'})
                return self.reply(200,p.read_bytes(),'application/octet-stream')
            return self.reply(404,{'error':'不存在'})
        except (family_print.PrintError,family_calendar.CalendarError,ProfileError,family_child.ChildError,family_agent.AgentError,family_study.StudyError,family_settings.SettingsError,family_teachers.TeacherError) as e: return self.reply(e.status,dict(error=str(e),code=e.code))
        except (OSError,sqlite3.Error,json.JSONDecodeError): return self.reply(500,{'error':'读取失败，记录未更改'})
    def do_POST(self):
        if not self.authorize_request(): return
        path=urlparse(self.path).path
        if family_child.dispatch_post(SimpleNamespace(**globals()),self,path): return
        bridge=path.startswith('/api/print/bridge/')
        if bridge:
            if not self.bridge_authorized(): return self.reply(403,{'error':'打印桥接未授权'})
        elif self.headers.get('X-Family-Token')!=TOKEN:
            return self.reply(403,{'error':'连接已更新，请重试当前操作。填写已保留。','code':'csrf_expired','token':TOKEN})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if self.path=='/api/upload':
                self.close_connection=True
                if self.headers.get('Transfer-Encoding'): return self.reply(400,{'error':'上传请求格式不正确'})
                if n>MAX_UPLOAD: return self.reply(413,{'error':'每个文件最多20MB'})
                self.connection.settimeout(30)
                try: attachment=save_upload(self.rfile,n,self.headers.get('X-File-Name',''))
                except ValueError: return self.reply(400,{'error':'文件为空、文件名不正确或内容与支持的类型不符'})
                return self.reply(200,dict(ok=True,attachment=attachment))
            max_json=2*1024*1024 if path=='/api/agent/ingest' else 65536 if path in ('/api/guided/material','/api/goals/action') else 20000
            if not 0<n<=max_json: raise ValueError('请求过大或为空')
            if path=='/api/agent/ingest':
                self.close_connection=True
                if self.headers.get('Transfer-Encoding'): return self.reply(400,{'error':'采集请求格式不正确'})
                self.connection.settimeout(30)
            obj=json.loads(self.rfile.read(n))
            if not isinstance(obj,dict): raise ValueError('格式不正确')
            if bridge:
                store=print_store()
                if path=='/api/print/bridge/claim':
                    authorized_printer(obj.get('printer'))
                    return self.reply(200,dict(job=store.claim(obj.get('bridge_id'),obj.get('printer'),obj.get('request_key'))))
                if path=='/api/print/bridge/report':
                    claim=obj.get('claim_token')
                    if not isinstance(claim,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',claim): return self.reply(403,{'error':'打印领取凭据无效'})
                    return self.reply(200,dict(job=store.report(obj.get('job_id'),claim,obj.get('status'),obj.get('cups_job_id',''),obj.get('note',''))))
                return self.reply(404,{'error':'不存在'})
            if path.startswith('/api/child-access/'):
                return self.reply(200,family_child.parent_action(SimpleNamespace(**globals()),path.removeprefix('/api/child-access/'),obj))
            if path=='/api/agent/ingest': return self.reply(200,agent_store().ingest(obj))
            if path=='/api/agent/action': return self.reply(200,agent_store().act(obj))
            if path=='/api/goals/action': return self.reply(200,goal_store().action(obj))
            if path=='/api/agent/message/attachment': return self.reply(200,agent_store().message_attachment(obj,upload_info))
            if path=='/api/teachers/profile': return self.reply(200,teacher_store().save_teacher(obj))
            if path=='/api/teachers/observation': return self.reply(200,teacher_store().save_observation(obj))
            if path=='/api/study/day': return self.reply(200,study_store().save_day(obj))
            if path=='/api/study/item': return self.reply(200,study_store().save_item(obj))
            if path=='/api/study/action': return self.reply(200,study_store().action(obj))
            if path=='/api/guided/state':
                if set(obj)-{'child_id'}: raise family_guided.GuidedError('请只选择要回看的孩子')
                return self.reply(200,guided_store().snapshot(obj.get('child_id')))
            if path=='/api/guided/material': return self.reply(200,guided_store().save_material(obj))
            if path=='/api/guided/action': return self.reply(200,guided_store().action(obj))
            if path=='/api/task/focus': return self.reply(200,family_task_focus.save(SimpleNamespace(**globals()),obj))
            if path=='/api/settings/child': return self.reply(200,settings_store().create_child(obj))
            if path=='/api/settings/sources': return self.reply(200,settings_store().save_sources(obj))
            if path=='/api/settings/model': return self.reply(200,settings_store().save_model(obj))
            if path=='/api/settings/model/test':
                if obj and obj!={'kind':'light'}: raise ValueError('模型连接检查只接收已保存的连接类型，不接收模型名称或家庭资料')
                light=obj.get('kind')=='light'
                try:
                    if light and not family_llm.model_values(DATA).get('light_model'):
                        raise ValueError('尚未保存轻模型；请先保存轻模型名称，再检查连接')
                    result=family_llm._chat_json([dict(role='user',content='Connection test only. Return {"ok":true}.')],
                        dict(type='object',properties=dict(ok=dict(type='boolean')),required=['ok'],additionalProperties=False),
                        'family_light_connection_test' if light else 'family_connection_test',timeout=10,data_path=DATA)
                    if result!={'ok':True}: raise family_llm.LLMDraftError('服务已响应，但返回格式未通过检查')
                    return self.reply(200,dict(ok=True))
                except family_llm.LLMDraftError as e: return self.reply(503,dict(error=str(e)))
            if path=='/api/profile':
                try: return self.reply(200,dict(profile=save_profile(obj)))
                except ProfileError: raise
                except ValueError as e: return self.reply(400,dict(error=str(e)))
            if path=='/api/calendar/save':
                return self.reply(200,dict(event=calendar_store().save(obj)))
            if path=='/api/calendar/draft':
                try: return self.reply(200,calendar_draft_from_text(obj))
                except family_llm.LLMDraftError as e: return self.reply(503,dict(error=str(e)))
                except ValueError as e: return self.reply(400,dict(error=str(e)))
            if path=='/api/reading/feedback':
                try: return self.reply(200,reading_feedback(obj))
                except family_llm.LLMDraftError as e: return self.reply(503,dict(error=str(e)))
                except family_reading.ReadingError: raise
                except ValueError as e: return self.reply(400,dict(error=str(e)))
            if path=='/api/care/feedback':
                return self.reply(200,save_record(obj,care_only=True))
            if path.startswith('/api/reading/'):
                return self.reply(200,reading_store().mutate(path.removeprefix('/api/reading/'),obj))
            if path=='/api/print/prepare':
                return self.reply(200,dict(preparation=print_store().prepare(obj.get('source'),obj.get('idempotency_key'))))
            if path=='/api/print/enqueue':
                authorized_printer(obj.get('printer'),color=obj.get('color','monochrome'),sides=obj.get('sides','one-sided'))
                return self.reply(200,dict(job=print_store().enqueue(obj)))
            if path=='/api/print/cancel': return self.reply(200,dict(job=print_store().cancel(obj.get('job_id'))))
            if path=='/api/print/received': return self.reply(200,dict(job=print_store().confirm_received(obj.get('job_id'),obj.get('note'))))
            if self.path=='/api/task/new':
                try: return self.reply(200,dict(ok=True,task=new_task(obj)))
                except ValueError as e: return self.reply(400,dict(error=str(e)))
            if self.path=='/api/transcribe':
                try: return self.reply(200,dict(text=transcribe_material(obj)))
                except family_llm.LLMDraftError as e: return self.reply(503,dict(error=str(e)))
                except ValueError as e: return self.reply(400,dict(error=str(e)))
            if self.path=='/api/draft':
                try: return self.reply(200,draft_from_material(obj))
                except family_llm.LLMDraftError as e: return self.reply(503,dict(error=str(e)))
                except ValueError as e: return self.reply(400,dict(error=str(e)))
            if self.path=='/api/ask':
                try: return self.reply(200,ask_family(obj))
                except family_llm.LLMDraftError as e: return self.reply(503,dict(error=str(e)))
                except ValueError as e: return self.reply(400,dict(error=str(e)))
                except (sqlite3.Error,OSError): return self.reply(503,dict(error='查询资料读取失败，请稍后重试；原记录未更改'))
            if self.path=='/api/record': return self.reply(200,save_record(obj))
            elif self.path=='/api/task': return self.reply(200,dict(ok=True,task=save_task(obj)))
            else: return self.reply(404,{'error':'不存在'})
            self.reply(200,{'ok':True})
        except RecordError as e: self.reply(e.status,dict(error=str(e),code=e.code,not_saved=e.not_saved,request_known=e.request_known))
        except (family_print.PrintError,family_reading.ReadingError,family_calendar.CalendarError,ProfileError,TaskError,family_child.ChildError,family_agent.AgentError,family_study.StudyError,family_settings.SettingsError,family_teachers.TeacherError,family_task_focus.FocusError,family_guided.GuidedError) as e: self.reply(e.status,dict(error=str(e),code=e.code))
        except (ValueError,TypeError): self.reply(400,{'error':'输入不完整或格式不正确；完成事项必须填写依据'})
        except (sqlite3.Error,OSError): self.reply(500,{'error':'保存失败，请重试；请保留当前输入'})

if __name__=='__main__':
    connect().close()
    prepare_assets()
    port=int(os.environ.get('PORT','8765'))
    print('家庭学习助手 http://127.0.0.1:'+str(port),flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
