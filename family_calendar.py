"""Bounded family calendar; manual SQLite entries and a read-only private source."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3


class CalendarError(ValueError):
    def __init__(self, message, status=400, code='invalid_calendar'):
        super().__init__(message); self.status=status; self.code=code


FIELDS=('child_ids','title','category','day','start_time','end_time','location','note','status','repeat','until')
REPEAT_FIELDS=('repeat_days','extra_times')
FIELDS+=REPEAT_FIELDS
CATEGORIES={'school','activity','study','family','other'}


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def _text(obj,key,limit,default='',required=False):
    value=obj.get(key,default)
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):
        raise CalendarError('字段格式或长度不正确：'+key)
    value=value.strip()
    if required and not value: raise CalendarError('请填写：'+key)
    return value


def _day(value,optional=False):
    if optional and value=='': return ''
    try:
        if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value): raise ValueError()
        dt.date.fromisoformat(value)
    except ValueError: raise CalendarError('日期须为有效的 YYYY-MM-DD') from None
    return value


def _clock(value):
    if not isinstance(value,str) or (value and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',value)):
        raise CalendarError('时间须为 HH:MM；不知道时可以留空')
    return value


def occurs(row, day):
    origin=dt.date.fromisoformat(row['day'])
    if day<origin or row['until'] and day.isoformat()>row['until']: return False
    mode=row['repeat']; days=row.get('repeat_days',[])
    return (day==origin if mode=='none' else True if mode=='daily' else
            day.isoweekday()>=6 if mode=='weekends' else
            day.isoweekday() in (days or [origin.isoweekday()]) if mode=='weekly' else
            day.day in (days or [origin.day]))


def first_day(row):
    origin=dt.date.fromisoformat(row['day'])
    # A requested 31st can skip February; no occurrence needs a >62-day search.
    for offset in range(min(62,(dt.date.max-origin).days+1)):
        day=origin+dt.timedelta(days=offset)
        if occurs(row,day): return day.isoformat()
    raise CalendarError('所选日期范围没有符合重复规则的日期，请核对起止日期')


def slots(row):
    excluded=row.get('excluded_dates',{})
    yield dict(row,excluded_days=excluded['']) if '' in excluded else row
    for slot in row.get('extra_times',[]):
        yield dict(row,id=row['id']+'.'+slot['id'],series_id=row['id'],
                   series_start_time=row['start_time'],series_end_time=row['end_time'],
                   start_time=slot['start_time'],end_time=slot['end_time'],
                   **({'excluded_days':excluded[slot['id']]} if slot['id'] in excluded else {}))


def occurrence_id(series,day,slot):
    return hashlib.sha256(('calendar-occurrence\0'+series+'\0'+day+'\0'+slot).encode()).hexdigest()[:32]


def timetable_week(week):
    if not isinstance(week,list) or len(week)>7: raise CalendarError('每周课表最多七天')
    days={}
    for w in week:
        if not isinstance(w,dict) or set(w)!={'weekday','sessions'} or type(w['weekday']) is not int or not 1<=w['weekday']<=7 or w['weekday'] in days:
            raise CalendarError('课表星期须为不重复的1至7')
        sessions=w['sessions']
        if not isinstance(sessions,list) or len(sessions)>30: raise CalendarError('每日课程最多30项')
        normalized=[]
        for session in sessions:
            if not isinstance(session,dict) or set(session)!={'slot','title'}: raise CalendarError('课程结构不正确')
            normalized.append(dict(slot=_text(session,'slot',100,required=True),title=_text(session,'title',200,required=True)))
        if len({s['slot'] for s in normalized})!=len(normalized): raise CalendarError('同一天的节次不能重复，请核对原课表')
        days[w['weekday']]=normalized
    return days


class Store:
    def __init__(self,connect,profiles,data,initialize=True):
        self.connect=connect; self.profiles=profiles; self.data=Path(data)
        if not initialize: return
        with self._db() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS calendar_events (
                id TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version>0),
                child_ids TEXT NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL,
                day TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                location TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL,
                repeat TEXT NOT NULL, until TEXT NOT NULL, last_request_hash TEXT NOT NULL,
                created TEXT NOT NULL, updated TEXT NOT NULL)''')
            columns={r[1] for r in c.execute('PRAGMA table_info(calendar_events)')}
            for name in (*REPEAT_FIELDS,'occurrence'):
                if name not in columns:
                    default='{}' if name=='occurrence' else '[]'
                    try: c.execute('ALTER TABLE calendar_events ADD COLUMN '+name+" TEXT NOT NULL DEFAULT '"+default+"'")
                    except sqlite3.OperationalError:
                        if name not in {r[1] for r in c.execute('PRAGMA table_info(calendar_events)')}: raise

    @contextmanager
    def _db(self, connection=None):
        """A supplied sqlite3.Row connection remains owned by the caller."""
        if connection is not None:
            if connection.row_factory is not sqlite3.Row:
                raise CalendarError('传入的日历连接须使用 sqlite3.Row')
            yield connection
            return
        c=self.connect(); c.row_factory=sqlite3.Row
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback(); raise
        finally: c.close()

    def _children(self):
        rows=self.profiles()
        if not isinstance(rows,list) or any(not isinstance(p,dict) or not isinstance(p.get('id'),str) or not p['id'] for p in rows):
            raise CalendarError('孩子档案暂时无法核对',409,'profile_error')
        ids={p['id'] for p in rows}
        if len(ids)!=len(rows): raise CalendarError('孩子档案标识重复',409,'profile_error')
        return ids

    @staticmethod
    def _fields(obj,children,source=False):
        ids=obj.get('child_ids')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in children for i in ids) or len(set(ids))!=len(ids):
            raise CalendarError('请至少选择一位已存在的孩子，且不能重复')
        row=dict(child_ids=sorted(ids),title=_text(obj,'title',200,required=True),
                 category=_text(obj,'category',20,'other'),day=_day(obj.get('day')),
                 start_time=_clock(obj.get('start_time','')),end_time=_clock(obj.get('end_time','')),
                 location=_text(obj,'location',200),note=_text(obj,'note',4000),
                 status=_text(obj,'status',20,'tentative'),repeat='none' if source else _text(obj,'repeat',20,'none'),
                 until='' if source else _day(obj.get('until',''),optional=True))
        if row['category'] not in CATEGORIES: raise CalendarError('安排类别不正确')
        if row['status'] not in {'tentative','confirmed','cancelled','completed'}: raise CalendarError('安排状态不正确')
        if row['status']=='completed' and (source or row['repeat']!='none'):
            raise CalendarError('仅单次手动计划可以确认完成；重复安排请逐次记录反馈')
        if row['repeat'] not in {'none','daily','weekly','weekends','monthly'}: raise CalendarError('重复方式不正确')
        if row['end_time'] and (not row['start_time'] or row['end_time']<=row['start_time']):
            raise CalendarError('结束时间须晚于同日开始时间')
        if row['until'] and (row['repeat']=='none' or row['until']<row['day']):
            raise CalendarError('重复结束日期须不早于首次日期；单次安排不填写重复结束日期')
        days=obj.get('repeat_days',[]); extra=obj.get('extra_times',[])
        limit=31 if row['repeat']=='monthly' else 7 if row['repeat']=='weekly' else 0
        if (not isinstance(days,list) or len(days)>limit or
                any(type(d) is not int or not 1<=d<=limit for d in days) or len(set(days))!=len(days)):
            raise CalendarError('请选择不重复的星期或每月日期')
        if not isinstance(extra,list) or len(extra)>7 or extra and (source or row['repeat']=='none' or not row['start_time']):
            raise CalendarError('重复计划最多每天8个时段，添加时段前请填写首次时间')
        normalized=[]; ids=set(); periods=[(row['start_time'],row['end_time'])]
        for slot in extra:
            if not isinstance(slot,dict) or set(slot)!={'id','start_time','end_time'} or not isinstance(slot['id'],str) or not re.fullmatch('[a-f0-9]{16}',slot['id']) or slot['id'] in ids:
                raise CalendarError('重复时段标识不正确')
            start=_clock(slot['start_time']); end=_clock(slot['end_time'])
            if not start or end and end<=start: raise CalendarError('请填写时段开始时间，结束须晚于开始')
            ids.add(slot['id']);periods.append((start,end));normalized.append(dict(slot))
        periods.sort()
        if any(a[0]==b[0] or a[1] and a[1]>b[0] for a,b in zip(periods,periods[1:])):
            raise CalendarError('同一计划的时段不能重复或重叠')
        row.update(repeat_days=sorted(days),extra_times=normalized)
        first_day(row)
        return row

    @staticmethod
    def _manual(row):
        raw=dict(row)
        result={k:raw.get(k,'[]') if k in REPEAT_FIELDS else raw[k] for k in ('id','version')+FIELDS+('created','updated')}
        result['child_ids']=json.loads(result['child_ids'])
        for key in REPEAT_FIELDS: result[key]=json.loads(result[key])
        result.update(series_day=result['day'],editable=True,source='',task_id='')
        result['occurrence']=json.loads(raw.get('occurrence','{}'))
        if not isinstance(result['occurrence'],dict):
            raise CalendarError('逐次安排记录格式无法核对，请保留记录并检查备份',503,'calendar_data_error')
        return result

    @staticmethod
    def saved_rows(c,children):
        rows=[Store._manual(r) for r in c.execute('SELECT * FROM calendar_events ORDER BY day,id')]
        parents={r['id']:r for r in rows if not r['occurrence']}
        for row in rows:
            Store._fields(row,children)
            origin=row['occurrence']
            if not origin: continue
            Store._origin(row,children)
            parent=parents.get(origin['series_id'])
            if parent is None:
                raise CalendarError('逐次安排的归属无法核对',503,'calendar_data_error')
            parent.setdefault('excluded_dates',{}).setdefault(origin['slot_id'],[]).append(origin['day'])
        return rows

    @staticmethod
    def _origin(row,children):
        """Check saved history before reads, edits or restoring a private database."""
        try:
            o=row['occurrence']
            if not isinstance(o,dict) or set(o)!={'series_id','day','slot_id','original','history'}: raise ValueError()
            if not isinstance(o['series_id'],str) or not re.fullmatch('[a-f0-9]{32}',o['series_id']): raise ValueError()
            if not isinstance(o['slot_id'],str) or not re.fullmatch('(?:[a-f0-9]{16})?',o['slot_id']): raise ValueError()
            if row['repeat']!='none' or row['id']!=occurrence_id(o['series_id'],_day(o['day']),o['slot_id']): raise ValueError()
            original=o['original'];history=o['history']
            if not isinstance(original,dict) or set(original)!=set(FIELDS) or original['day']!=o['day'] or original['repeat']!='none': raise ValueError()
            Store._fields(original,children)
            if not isinstance(history,list) or len(history)!=row['version']: raise ValueError()
            for version,h in enumerate(history,1):
                if not isinstance(h,dict) or set(h)!=set(FIELDS)|{'version','at'} or type(h['version']) is not int or h['version']!=version or h['repeat']!='none': raise ValueError()
                if dt.datetime.fromisoformat(h['at']).tzinfo is None: raise ValueError()
                Store._fields(h,children)
                if any(h[k]!=original[k] for k in set(FIELDS)-{'day','start_time','end_time','status','note'}): raise ValueError()
            if not history or any(history[-1][k]!=row[k] for k in FIELDS): raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise CalendarError('逐次安排的原记录或历史无法核对，请保留记录并检查备份',503,'calendar_data_error') from None

    @staticmethod
    def _write(c,ident,version,fields,digest,old,origin=None):
        now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds')
        values=dict(id=ident,version=version+1,**fields,last_request_hash=digest,
                    created=old['created'] if old else now,updated=now)
        values['child_ids']=_json(values['child_ids'])
        for key in REPEAT_FIELDS: values[key]=_json(values[key])
        if origin is not None: values['occurrence']=_json(origin)
        if old:
            columns=[k for k in values if k!='id']
            c.execute('UPDATE calendar_events SET '+','.join(k+'=?' for k in columns)+' WHERE id=?',
                      [values[k] for k in columns]+[ident])
        else:
            c.execute('INSERT INTO calendar_events ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',list(values.values()))
        return Store._manual(values)

    def save(self,obj):
        if not isinstance(obj,dict) or set(obj)-set(FIELDS)-{'id','version'}:
            raise CalendarError('只能保存手动安排字段，学校来源保持只读')
        ident=obj.get('id'); version=obj.get('version')
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident): raise CalendarError('手动安排编号不正确')
        if type(version) is not int or not 0<=version<=2147483647: raise CalendarError('安排版本不正确')
        fields=self._fields(obj,self._children())
        digest=hashlib.sha256(_json(dict(id=ident,version=version,**fields)).encode()).hexdigest()
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM calendar_events WHERE id=?',(ident,)).fetchone()
            if old and json.loads(old['occurrence']): raise CalendarError('请从“处理本次”修改这次安排',409,'calendar_occurrence_required')
            # Reconcile a lost response before rejecting the now-stale version.
            if old and old['last_request_hash']==digest: return self._manual(old)
            if old and not any(key in obj or json.loads(old[key]) for key in REPEAT_FIELDS):
                legacy=hashlib.sha256(_json(dict(id=ident,version=version,**{k:v for k,v in fields.items() if k not in REPEAT_FIELDS})).encode()).hexdigest()
                if old['last_request_hash']==legacy: return self._manual(old)
            if (old is None and version!=0) or (old is not None and old['version']!=version):
                raise CalendarError('这条安排已更新，请刷新核对；当前输入未覆盖',409,'calendar_conflict')
            if old and any(key not in obj and json.loads(old[key]) for key in REPEAT_FIELDS):
                raise CalendarError('此计划包含新的重复设置，请刷新页面后修改',409,'calendar_conflict')
            if old and old['repeat']!='none' and fields['repeat']=='none' and any(
                    json.loads(r[0]).get('series_id')==ident for r in c.execute("SELECT occurrence FROM calendar_events WHERE occurrence!='{}'")):
                raise CalendarError('此重复计划已有逐次记录，请保留重复规则；需要单次安排时可另建一条',409,'calendar_conflict')
            return self._write(c,ident,version,fields,digest,old)

    def save_occurrence(self,obj):
        allowed={'series_id','series_version','origin_day','slot_id','version','day','start_time','end_time','status','note'}
        if not isinstance(obj,dict) or set(obj)!=allowed: raise CalendarError('请只填写本次安排的日期、时间、状态与反馈')
        series=obj['series_id'];slot_id=obj['slot_id'];day=_day(obj['origin_day']);version=obj['version']
        if not isinstance(series,str) or not re.fullmatch('[a-f0-9]{32}',series) or not isinstance(slot_id,str) or slot_id and not re.fullmatch('[a-f0-9]{16}',slot_id):
            raise CalendarError('原重复计划或时段标识不正确')
        if any(type(v) is not int or not 0<=v<2147483647 for v in [version,obj['series_version']]): raise CalendarError('本次安排的版本不正确')
        ident=occurrence_id(series,day,slot_id);digest=hashlib.sha256(_json(obj).encode()).hexdigest();children=self._children()
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            raw=c.execute('SELECT * FROM calendar_events WHERE id=?',(series,)).fetchone()
            if raw is None or json.loads(raw['occurrence']): raise CalendarError('原重复计划不存在',404,'calendar_missing')
            parent=self._manual(raw);self._fields(parent,children)
            old=c.execute('SELECT * FROM calendar_events WHERE id=?',(ident,)).fetchone()
            if old:
                origin=json.loads(old['occurrence']);current=self._manual(old);self._fields(current,children)
                self._origin(current,children)
                if not origin or (origin['series_id'],origin['day'],origin['slot_id'])!=(series,day,slot_id): raise CalendarError('本次安排的标识冲突',409,'calendar_conflict')
                if old['last_request_hash']==digest:return current
            if (old['version'] if old else 0)!=version or raw['version']!=obj['series_version']:
                raise CalendarError('这次安排或原计划已更新，请刷新核对；当前输入未覆盖',409,'calendar_conflict')
            if not old:
                slot=next((s for s in slots(parent) if s['id']==series+('.'+slot_id if slot_id else '')),None)
                if parent['repeat']=='none' or slot is None or not occurs(parent,dt.date.fromisoformat(day)):
                    raise CalendarError('这一天或时段不在原重复计划中，请刷新核对',409,'calendar_conflict')
                current={k:slot[k] for k in FIELDS};current.update(day=day,repeat='none',until='',repeat_days=[],extra_times=[])
                origin=dict(series_id=series,day=day,slot_id=slot_id,original=dict(current),history=[])
            fields=self._fields(dict(current,**{k:obj[k] for k in ['day','start_time','end_time','status','note']}),children)
            origin['history'].append(dict(version=version+1,at=dt.datetime.now(dt.timezone.utc).isoformat(),**fields))
            return self._write(c,ident,version,fields,digest,old,origin)

    def _sources(self,children):
        path=self.data/'日历来源.json'
        if not path.exists() and not path.is_symlink(): return [],[],''
        try:
            if path.is_symlink() or not path.is_file(): raise CalendarError('来源文件类型不正确')
            with path.open('rb') as f: raw=f.read(1024*1024+1)
            if len(raw)>1024*1024: raise CalendarError('来源文件超过1 MiB')
            obj=json.loads(raw)
            if not isinstance(obj,dict) or set(obj)-{'events','timetables'}: raise CalendarError('来源顶层结构不正确')
            events=obj.get('events',[]); tables=obj.get('timetables',[])
            if not isinstance(events,list) or len(events)>500 or not isinstance(tables,list) or len(tables)>64:
                raise CalendarError('来源安排或课表数量超出范围')
            result=[]; timetables=[]; seen=set()
            for n,item in enumerate(events,1):
                try:
                    if not isinstance(item,dict) or set(item)-set(FIELDS)-{'id','source','task_id'} or set(item)&{'repeat','until',*REPEAT_FIELDS}:
                        raise CalendarError('来源安排结构不正确')
                    ident=_text(item,'id',100,required=True)
                    if ident in seen: raise CalendarError('来源安排编号重复')
                    seen.add(ident)
                    row=self._fields(item,children,source=True)
                    row.update(id='source:'+ident,version=0,series_day=row['day'],editable=False,
                               source=_text(item,'source',1000,required=True),task_id=_text(item,'task_id',100))
                    result.append(row)
                except CalendarError as e: raise CalendarError('第'+str(n)+'条学校安排：'+str(e)) from None
            seen=set()
            for n,item in enumerate(tables,1):
                try:
                    if not isinstance(item,dict) or set(item)-{'id','child_id','effective_from','effective_until','title','source','attachment','note','week'}:
                        raise CalendarError('课表结构不正确')
                    ident=_text(item,'id',100,required=True); child=_text(item,'child_id',100,required=True)
                    if ident in seen or child not in children: raise CalendarError('课表编号重复或孩子归属不正确')
                    seen.add(ident)
                    first=_day(item.get('effective_from')); last=_day(item.get('effective_until',''),optional=True)
                    if last and last<first: raise CalendarError('课表结束日期早于生效日期')
                    attachment=_text(item,'attachment',255)
                    if attachment and (attachment in {'.','..'} or '/' in attachment or '\\' in attachment or ':' in attachment or any(ord(c)<32 for c in attachment)):
                        raise CalendarError('课表原件须为本项目附件文件名')
                    days=timetable_week(item.get('week'))
                    timetables.append(dict(id=ident,child_id=child,effective_from=first,effective_until=last,
                        title=_text(item,'title',200,required=True),source=_text(item,'source',1000,required=True),
                        attachment=attachment,note=_text(item,'note',4000),week=days))
                except CalendarError as e: raise CalendarError('第'+str(n)+'份课表：'+str(e)) from None
            return result,timetables,''
        except (OSError,ValueError,UnicodeError,RecursionError) as e:
            detail=str(e) if isinstance(e,CalendarError) else '文件无法读取或JSON格式损坏'
            return [],[],'学校日历来源未载入：'+detail+'；手动安排仍可使用。'

    def saved_timetables(self, connection=None):
        with self._db(connection) as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='calendar_timetables'").fetchone(): return []
            return [json.loads(r['payload'])|dict(id=r['id'],version=r['version'],updated=r['updated']) for r in c.execute('SELECT * FROM calendar_timetables ORDER BY updated DESC')]

    def save_timetable(self,obj,validate_uploads):
        fields={'child_id','title','effective_from','effective_until','note','week','attachments'}
        if not isinstance(obj,dict) or set(obj)!=fields|{'id','version'}: raise CalendarError('课表字段不正确')
        ident=obj['id'];version=obj['version']
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident) or type(version) is not int or not 0<=version<2147483647: raise CalendarError('课表编号或版本不正确')
        child=_text(obj,'child_id',100,required=True)
        if child not in self._children(): raise CalendarError('请选择孩子')
        week=timetable_week(obj['week'])
        if not any(week.values()): raise CalendarError('还没有明确课程，请先识别或填写课表')
        first=_day(obj['effective_from']);last=_day(obj['effective_until'],optional=True)
        if last and last<first: raise CalendarError('课表结束日期早于生效日期')
        row=dict(child_id=child,title=_text(obj,'title',200,required=True),effective_from=first,effective_until=last,
                 note=_text(obj,'note',4000),week=[dict(weekday=d,sessions=s) for d,s in sorted(week.items())],attachments=obj['attachments'])
        digest=hashlib.sha256(_json(dict(id=ident,version=version,**row)).encode()).hexdigest()
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            validate_uploads(c,child,row['attachments'])
            c.execute('CREATE TABLE IF NOT EXISTS calendar_timetables (id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL, last_request_hash TEXT NOT NULL, updated TEXT NOT NULL)')
            old=c.execute('SELECT * FROM calendar_timetables WHERE id=?',(ident,)).fetchone()
            if old and old['last_request_hash']==digest: return json.loads(old['payload'])|dict(id=ident,version=old['version'])
            if (old is None and version!=0) or (old and (old['version']!=version or json.loads(old['payload'])['child_id']!=child)):
                raise CalendarError('课表已更新或孩子归属不同；输入已保留，请重新打开核对',409,'timetable_conflict')
            now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
            c.execute('INSERT INTO calendar_timetables VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload=excluded.payload,last_request_hash=excluded.last_request_hash,updated=excluded.updated',
                      (ident,version+1,_json(row),digest,now))
        return row|dict(id=ident,version=version+1)

    def snapshot(self,start,end,connection=None):
        first=dt.date.fromisoformat(_day(start)); last=dt.date.fromisoformat(_day(end))
        if not 0<=(last-first).days<31: raise CalendarError('每次查询须为按先后排列的1至31天（包含结束日）')
        children=self._children()
        with self._db(connection) as c:
            ready=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_events'").fetchone()
            rows=self.saved_rows(c,children) if ready else []
        events=[]
        parents={r['id']:r for r in rows if not r['occurrence']}
        for row in rows:
            for offset in range((last-first).days+1):
                day=first+dt.timedelta(days=offset)
                if not occurs(row,day):continue
                for slot in slots(row):
                    if day.isoformat() in slot.get('excluded_days',[]):continue
                    event=dict(slot,day=day.isoformat())
                    if row['repeat']!='none':
                        event['occurrence']=dict(series_id=row['id'],day=day.isoformat(),slot_id=slot['id'][len(row['id'])+1:],original={k:event[k] for k in ['day','start_time','end_time']},history=[])
                    if event['occurrence']:
                        event['occurrence']=dict(event['occurrence'],version=row['version'] if row['occurrence'] else 0,series_version=parents[event['occurrence']['series_id']]['version'])
                    events.append(event)
        sources,tables,error=self._sources(children)
        events.extend(row for row in sources if start<=row['day']<=end)
        for row in self.saved_timetables(connection):
            if row['child_id'] not in children: raise CalendarError('已导入课表的孩子归属无法核对')
            tables.append(dict(row,week=timetable_week(row['week']),source='家长核对导入',attachment=''))
        expanded=[]
        for offset in range((last-first).days+1):
            date=first+dt.timedelta(days=offset); day=date.isoformat()
            # ponytail: one current school timetable per child; activity plans remain calendar events.
            selected={}
            for table in tables:
                if day<table['effective_from']: continue
                rank=(bool(table.get('version')),table['effective_from'],table.get('updated',''))
                previous=selected.get(table['child_id'])
                if previous is None or rank>previous[0]: selected[table['child_id']]=(rank,table)
            for _,table in selected.values():
                if table['effective_until'] and day>table['effective_until']: continue
                sessions=table['week'].get(date.isoweekday(),[])
                if sessions:
                    expanded.append(dict((k,table[k]) for k in ('id','child_id','title','source','attachment','note'))|dict(day=day,sessions=sessions,import_id=table['id'] if 'version' in table else '',uploads=table.get('attachments',[])))
        events.sort(key=lambda r:(r['day'],r['start_time'],r['title'],r['id']))
        expanded.sort(key=lambda r:(r['day'],r['child_id'],r['id']))
        return dict(events=events,timetables=expanded,source_error=error)

    def subscription_events(self):
        """Read original series, including cancellations; never expand or truncate.

        ponytail: 1,000 saved/source series; add archival policy if families reach it.
        Keeping old rows avoids silently losing cancellation or reschedule updates.
        """
        children=self._children()
        with self._db() as c:
            ready=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_events'").fetchone()
            rows=self.saved_rows(c,children) if ready else []
        sources,_,error=self._sources(children)
        if error: raise CalendarError('学校日历来源无法完整读取，请在系统内核对后重试',503,'calendar_source_unavailable')
        if len(rows)+len(sources)>1000:
            raise CalendarError('日历订阅超过1000条原始安排，请在系统内核对',503,'calendar_limit')
        try:
            result=rows+sources
            for row in result: self._fields(row,children)
        except (KeyError,TypeError,ValueError) as e:
            if isinstance(e,CalendarError): raise
            raise CalendarError('已保存日历无法完整核对',503,'calendar_data_error') from None
        return result


def _ics_text(value):
    # RFC 5545 TEXT escaping; user content cannot create another property line.
    return value.replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def _ics_lines(lines):
    """Fold on UTF-8 code point boundaries, counting the continuation space."""
    folded=[]
    try:
        for line in lines:
            part=''; size=0
            for char in line:
                width=len(char.encode('utf-8'))
                if size+width>75:
                    folded.append(part); part=' '; size=1
                part+=char; size+=width
            folded.append(part)
        return ('\r\n'.join(folded)+'\r\n').encode('utf-8')
    except UnicodeError:
        raise CalendarError('日历包含无法编码的文字',503,'calendar_data_error') from None


def _ics_utc(day,clock):
    try:
        local=dt.datetime.fromisoformat(day+'T'+clock).replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
        value=local.astimezone(dt.timezone.utc)
        return f'{value.year:04d}{value.month:02d}{value.day:02d}T{value.hour:02d}{value.minute:02d}00Z'
    except (ValueError,OverflowError):
        raise CalendarError('日历时间无法转换为UTC') from None


def render_ics(events,profiles,as_of,uid_namespace,task_states=None):
    """Pure, minimal family feed: original series in, RFC 5545 UTF-8 bytes out.

    Only names, title, dates/times, status and location leave the application.
    The caller supplies a trusted, stable deployment namespace, never a Host header.
    Task overlays are per child; completion alone does not mean nonparticipation.
    """
    if not isinstance(events,list) or len(events)>1000:
        raise CalendarError('日历订阅须为不超过1000条原始安排',503,'calendar_limit')
    if not isinstance(profiles,list): raise CalendarError('孩子档案暂时无法核对',409,'profile_error')
    children={}
    for profile in profiles:
        if not isinstance(profile,dict): raise CalendarError('孩子档案暂时无法核对',409,'profile_error')
        ident=_text(profile,'id',128,required=True); name=_text(profile,'name',100,required=True)
        if ident!=profile['id'] or any(ord(c)<32 for c in ident) or ident in children:
            raise CalendarError('孩子档案标识无法核对',409,'profile_error')
        children[ident]=name
    if not isinstance(as_of,dt.datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise CalendarError('订阅生成时间须包含时区')
    namespace=_text({'namespace':uid_namespace},'namespace',255,required=True)
    if namespace!=uid_namespace or any(ord(c)<32 for c in namespace): raise CalendarError('订阅命名空间不正确')
    states={} if task_states is None else task_states
    if not isinstance(states,dict): raise CalendarError('事项参与状态无法核对')
    for task_id,by_child in states.items():
        if not isinstance(task_id,str) or not task_id or not isinstance(by_child,dict):
            raise CalendarError('事项参与状态无法核对')
        for child,status in by_child.items():
            if child not in children or not isinstance(status,str) or status not in {'待跟进','进行中','已完成','不参加','不适用','已归档'}:
                raise CalendarError('事项参与状态或孩子归属无法核对')
    try:
        stamp=as_of.astimezone(dt.timezone.utc)
    except (ValueError,OverflowError): raise CalendarError('订阅生成时间无法转换为UTC') from None
    timestamp=f'{stamp.year:04d}{stamp.month:02d}{stamp.day:02d}T{stamp.hour:02d}{stamp.minute:02d}{stamp.second:02d}Z'
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Family Growth//Family Calendar//ZH','CALSCALE:GREGORIAN']
    # Custom local weekdays/month-days must not shift when morning time is UTC's previous day.
    lines+=['BEGIN:VTIMEZONE','TZID:Asia/Shanghai','BEGIN:STANDARD','DTSTART:19700101T000000',
            'TZOFFSETFROM:+0800','TZOFFSETTO:+0800','END:STANDARD','END:VTIMEZONE']
    expanded=[]
    for item in events:
        if not isinstance(item,dict): raise CalendarError('日历安排格式不正确')
        Store._fields(item,children)
        expanded.extend(dict(slot,extra_times=[]) for slot in slots(item))
    seen=set()
    for item in expanded:
        if not isinstance(item,dict): raise CalendarError('日历安排格式不正确')
        ident=_text(item,'id',128,required=True)
        if ident!=item['id'] or any(ord(c)<32 for c in ident) or ident in seen:
            raise CalendarError('日历安排编号重复或无法核对')
        seen.add(ident)
        row=Store._fields(item,children)
        origin=_day(item.get('series_day',row['day']))
        # Feed only the original saved series, not duplicate snapshot occurrences.
        if origin!=row['day']: raise CalendarError('日历订阅需要原始系列，不能使用已展开的每周实例')
        origin=first_day(row)
        task_id=_text(item,'task_id',100)
        participants=[child for child in row['child_ids'] if states.get(task_id,{}).get(child) not in {'不参加','不适用'}]
        status=row['status'] if participants else 'cancelled'
        # Cancellation still identifies the original children; the cancelled label
        # makes clear that these names no longer imply participation.
        names='、'.join(children[child] for child in (participants or row['child_ids']))
        title=(names+' · ' if names else '')+row['title']
        if status=='tentative': title='[暂定] '+title
        if status=='cancelled': title='[已取消] '+title
        if status=='completed': title='[已完成] '+title
        if not row['start_time']: title='[时间待定] '+title
        try: uid=hashlib.sha256((namespace+'\0'+ident).encode('utf-8')).hexdigest()+'@family-calendar'
        except UnicodeError: raise CalendarError('日历编号无法编码') from None
        lines+=['BEGIN:VEVENT','UID:'+uid,'DTSTAMP:'+timestamp,'SUMMARY:'+_ics_text(title),
                'STATUS:'+('CONFIRMED' if status=='completed' else status.upper()),'TRANSP:'+('OPAQUE' if status=='confirmed' and row['start_time'] else 'TRANSPARENT')]
        local_rule=row['repeat'] in {'daily','weekends','monthly'} or bool(row['repeat_days'])
        def date_time(key,clock,on=origin):
            return (key+';TZID=Asia/Shanghai:'+on.replace('-','')+'T'+clock.replace(':','')+'00'
                    if local_rule else key+':'+_ics_utc(on,clock))
        if row['start_time']:
            lines.append(date_time('DTSTART',row['start_time']))
            if row['end_time']: lines.append(date_time('DTEND',row['end_time']))
        else:
            # DATE without DTEND means one day; no guessed busy interval or clock.
            lines.append('DTSTART;VALUE=DATE:'+origin.replace('-',''))
        if row['repeat']!='none':
            rule='RRULE:FREQ='+{'daily':'DAILY','weekly':'WEEKLY','weekends':'WEEKLY','monthly':'MONTHLY'}[row['repeat']]
            if row['repeat']=='weekends': rule+=';BYDAY=SA,SU'
            elif row['repeat']=='weekly' and row['repeat_days']:
                rule+=';BYDAY='+','.join(['MO','TU','WE','TH','FR','SA','SU'][d-1] for d in row['repeat_days'])
            elif row['repeat']=='monthly': rule+=';BYMONTHDAY='+','.join(map(str,row['repeat_days'] or [dt.date.fromisoformat(row['day']).day]))
            if row['until']:
                until=_ics_utc(row['until'],row['start_time']) if row['start_time'] else row['until'].replace('-','')
                rule+=';UNTIL='+until
            lines.append(rule)
        excluded=item.get('excluded_days',[])
        if not isinstance(excluded,list) or any(not isinstance(day,str) for day in excluded): raise CalendarError('逐次安排的排除日期无法核对')
        # A saved one-off keeps its own stable UID; EXDATE removes only its original slot.
        # RFC 5545 3.8.5.1 also allows excluding DTSTART itself; the master keeps DTSTART.
        for day in sorted(set(excluded)):
            _day(day)
            lines.append(date_time('EXDATE',row['start_time'],day) if row['start_time'] else 'EXDATE;VALUE=DATE:'+day.replace('-',''))
        if row['location']: lines.append('LOCATION:'+_ics_text(row['location']))
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return _ics_lines(lines)
