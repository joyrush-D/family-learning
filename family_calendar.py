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

    @contextmanager
    def _db(self):
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
        if row['status'] not in {'tentative','confirmed','cancelled'}: raise CalendarError('安排状态不正确')
        if row['repeat'] not in {'none','weekly'}: raise CalendarError('重复方式不正确')
        if row['end_time'] and (not row['start_time'] or row['end_time']<=row['start_time']):
            raise CalendarError('结束时间须晚于同日开始时间')
        if row['until'] and (row['repeat']!='weekly' or row['until']<row['day']):
            raise CalendarError('重复结束日期须不早于首次日期；单次安排不填写重复结束日期')
        return row

    @staticmethod
    def _manual(row):
        result={k:row[k] for k in ('id','version')+FIELDS+('created','updated')}
        result['child_ids']=json.loads(result['child_ids'])
        result.update(series_day=result['day'],editable=True,source='',task_id='')
        return result

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
            # Reconcile a lost response before rejecting the now-stale version.
            if old and old['last_request_hash']==digest: return self._manual(old)
            if (old is None and version!=0) or (old is not None and old['version']!=version):
                raise CalendarError('这条安排已更新，请刷新核对；当前输入未覆盖',409,'calendar_conflict')
            now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds')
            values=dict(id=ident,version=version+1,**fields,last_request_hash=digest,
                        created=old['created'] if old else now,updated=now)
            values['child_ids']=_json(values['child_ids'])
            if old:
                columns=[k for k in values if k!='id']
                c.execute('UPDATE calendar_events SET '+','.join(k+'=?' for k in columns)+' WHERE id=?',
                          [values[k] for k in columns]+[ident])
            else:
                c.execute('INSERT INTO calendar_events ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',list(values.values()))
            return self._manual(values)

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
                    if not isinstance(item,dict) or set(item)-set(FIELDS)-{'id','source','task_id'} or 'repeat' in item or 'until' in item:
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
                    week=item.get('week')
                    if not isinstance(week,list) or len(week)>7: raise CalendarError('每周课表结构不正确')
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
                        days[w['weekday']]=normalized
                    timetables.append(dict(id=ident,child_id=child,effective_from=first,effective_until=last,
                        title=_text(item,'title',200,required=True),source=_text(item,'source',1000,required=True),
                        attachment=attachment,note=_text(item,'note',4000),week=days))
                except CalendarError as e: raise CalendarError('第'+str(n)+'份课表：'+str(e)) from None
            return result,timetables,''
        except (OSError,ValueError,UnicodeError,RecursionError) as e:
            detail=str(e) if isinstance(e,CalendarError) else '文件无法读取或JSON格式损坏'
            return [],[],'学校日历来源未载入：'+detail+'；手动安排仍可使用。'

    def snapshot(self,start,end):
        first=dt.date.fromisoformat(_day(start)); last=dt.date.fromisoformat(_day(end))
        if not 0<=(last-first).days<31: raise CalendarError('每次查询须为按先后排列的1至31天（包含结束日）')
        children=self._children()
        with self._db() as c:
            ready=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_events'").fetchone()
            rows=c.execute("SELECT * FROM calendar_events WHERE day<=? AND (repeat='weekly' OR day>=?) ORDER BY day,id",(end,start)).fetchall() if ready else []
        events=[]
        for raw in rows:
            row=self._manual(raw)
            if any(i not in children for i in row['child_ids']): raise CalendarError('手动安排的孩子归属无法核对',409,'profile_error')
            origin=dt.date.fromisoformat(row['series_day'])
            if row['repeat']=='weekly':
                offset=max(0,((first-origin).days+6)//7)*7
                # Do not add a week beyond date.max merely to terminate iteration.
                for number in range(offset, (last-origin).days+1, 7):
                    day=(origin+dt.timedelta(days=number)).isoformat()
                    if row['until'] and day>row['until']: break
                    events.append(dict(row,day=day))
            elif first<=origin<=last: events.append(row)
        sources,tables,error=self._sources(children)
        events.extend(row for row in sources if start<=row['day']<=end)
        expanded=[]
        for offset in range((last-first).days+1):
            date=first+dt.timedelta(days=offset); day=date.isoformat()
            for table in tables:
                if day<table['effective_from'] or (table['effective_until'] and day>table['effective_until']): continue
                sessions=table['week'].get(date.isoweekday(),[])
                if sessions:
                    expanded.append(dict((k,table[k]) for k in ('id','child_id','title','source','attachment','note'))|dict(day=day,sessions=sessions))
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
            rows=c.execute('SELECT * FROM calendar_events ORDER BY id LIMIT 1001').fetchall() if ready else []
        sources,_,error=self._sources(children)
        if error: raise CalendarError('学校日历来源无法完整读取，请在系统内核对后重试',503,'calendar_source_unavailable')
        if len(rows)+len(sources)>1000:
            raise CalendarError('日历订阅超过1000条原始安排，请在系统内核对',503,'calendar_limit')
        try:
            result=[self._manual(row) for row in rows]+sources
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
    seen=set()
    for item in events:
        if not isinstance(item,dict): raise CalendarError('日历安排格式不正确')
        ident=_text(item,'id',128,required=True)
        if ident!=item['id'] or any(ord(c)<32 for c in ident) or ident in seen:
            raise CalendarError('日历安排编号重复或无法核对')
        seen.add(ident)
        row=Store._fields(item,children)
        origin=_day(item.get('series_day',row['day']))
        # Feed only the original saved series, not duplicate snapshot occurrences.
        if origin!=row['day']: raise CalendarError('日历订阅需要原始系列，不能使用已展开的每周实例')
        task_id=_text(item,'task_id',100)
        participants=[child for child in row['child_ids'] if states.get(task_id,{}).get(child) not in {'不参加','不适用'}]
        status=row['status'] if participants else 'cancelled'
        # Cancellation still identifies the original children; the cancelled label
        # makes clear that these names no longer imply participation.
        names='、'.join(children[child] for child in (participants or row['child_ids']))
        title=(names+' · ' if names else '')+row['title']
        if status=='tentative': title='[暂定] '+title
        if status=='cancelled': title='[已取消] '+title
        if not row['start_time']: title='[时间待定] '+title
        try: uid=hashlib.sha256((namespace+'\0'+ident).encode('utf-8')).hexdigest()+'@family-calendar'
        except UnicodeError: raise CalendarError('日历编号无法编码') from None
        lines+=['BEGIN:VEVENT','UID:'+uid,'DTSTAMP:'+timestamp,'SUMMARY:'+_ics_text(title),
                'STATUS:'+status.upper(),'TRANSP:'+('OPAQUE' if status=='confirmed' and row['start_time'] else 'TRANSPARENT')]
        if row['start_time']:
            lines.append('DTSTART:'+_ics_utc(origin,row['start_time']))
            if row['end_time']: lines.append('DTEND:'+_ics_utc(origin,row['end_time']))
        else:
            # DATE without DTEND means one day; no guessed busy interval or clock.
            lines.append('DTSTART;VALUE=DATE:'+origin.replace('-',''))
        if row['repeat']=='weekly':
            rule='RRULE:FREQ=WEEKLY'
            if row['until']:
                until=_ics_utc(row['until'],row['start_time']) if row['start_time'] else row['until'].replace('-','')
                rule+=';UNTIL='+until
            lines.append(rule)
        if row['location']: lines.append('LOCATION:'+_ics_text(row['location']))
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return _ics_lines(lines)
