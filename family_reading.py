"""Deterministic reading agreements, works and stamps; no model or network calls.

Store(connect, profiles, tasks) reuses the application's SQLite connection and
profile/source-task callbacks. Every mutation needs child_id and request_key;
existing objects also need id and version. Stamps never modify ordinary tasks
or the separate record-energy system.
"""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import re
import secrets
import sqlite3


class ReadingError(ValueError):
    def __init__(self,message,code='invalid_input',status=400):
        super().__init__(message);self.code=code;self.status=status


def _text(obj,key,limit,default='',required=False):
    value=obj.get(key,default)
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:
        raise ReadingError('字段格式或长度不正确：'+key)
    value=value.strip()
    if required and not value: raise ReadingError('请填写：'+key)
    return value


def _integer(value,low,high,label):
    if type(value) is not int or not low<=value<=high:
        raise ReadingError(label+'须为'+str(low)+'至'+str(high)+'的整数')
    return value


def _day(value):
    if not isinstance(value,str): raise ReadingError('安排日期不正确')
    if not value: return ''
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): raise ValueError()
        dt.date.fromisoformat(value)
    except ValueError: raise ReadingError('安排日期须为有效的年-月-日') from None
    return value


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def validate_record_attachments(connection,child_id,attachment_ids):
    """Call inside save_record's transaction to enforce the reverse ownership check.

    Older databases without reading tables remain compatible. This helper never
    claims an upload; submitting a reading work performs the first binding.
    """
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reading_uploads'").fetchone(): return
    for ident in attachment_ids:
        row=connection.execute('SELECT child_id FROM reading_uploads WHERE upload_id=?',(ident,)).fetchone()
        if row and row[0]!=child_id:
            raise ReadingError('原件已关联另一位孩子的阅读作品，请使用对应孩子的资料')


class Store:
    AGREEMENT={'book':200,'edition':200,'scope':1000,'method':100,'criteria':1000,'source_task_id':100}
    TASK_ACTIONS={'create','edit','start','submit','confirm','request_more','pause','resume','revoke'}
    REDEMPTION_ACTIONS={'reserve','fulfill','cancel_redemption','correct_redemption'}

    def __init__(self,connect,profiles,tasks):
        self.connect=connect;self.profiles=profiles;self.source_tasks=tasks
        with self._db() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS reading_tasks (
                    id TEXT PRIMARY KEY, child_id TEXT NOT NULL, child_name TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version>0),
                    state TEXT NOT NULL CHECK(state IN ('草案','进行中','待确认','需补充','已完成','暂停')),
                    resume_state TEXT NOT NULL DEFAULT '', book TEXT NOT NULL, edition TEXT NOT NULL,
                    scope TEXT NOT NULL, method TEXT NOT NULL, criteria TEXT NOT NULL,
                    stamps INTEGER NOT NULL CHECK(stamps BETWEEN 1 AND 20),
                    source_task_id TEXT NOT NULL, planned_on TEXT NOT NULL,
                    work_text TEXT NOT NULL DEFAULT '', attachments TEXT NOT NULL DEFAULT '[]',
                    parent_note TEXT NOT NULL DEFAULT '', started TEXT NOT NULL DEFAULT '',
                    created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reading_awards (
                    task_id TEXT PRIMARY KEY, child_id TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount BETWEEN 1 AND 20),
                    status TEXT NOT NULL CHECK(status IN ('已获得','已撤销','需家长处理')),
                    granted_on TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS reading_redemptions (
                    id TEXT PRIMARY KEY, child_id TEXT NOT NULL, child_name TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version>0),
                    state TEXT NOT NULL CHECK(state IN ('待兑现','已兑现','已取消')),
                    reward TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost BETWEEN 1 AND 100),
                    planned_on TEXT NOT NULL, note TEXT NOT NULL, correction_note TEXT NOT NULL DEFAULT '',
                    allocations TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reading_events (
                    id INTEGER PRIMARY KEY, child_id TEXT NOT NULL, request_key TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, action TEXT NOT NULL, task_id TEXT NOT NULL DEFAULT '',
                    redemption_id TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL,
                    previous TEXT NOT NULL, current TEXT NOT NULL, created TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '{}', UNIQUE(child_id,request_key));
                CREATE TABLE IF NOT EXISTS reading_uploads (
                    upload_id TEXT PRIMARY KEY, child_id TEXT NOT NULL);
            ''')

    @contextmanager
    def _db(self):
        c=self.connect();c.row_factory=sqlite3.Row
        try:
            yield c
        except Exception:
            c.rollback();raise
        finally: c.close()

    def _profiles(self):
        result={}
        for p in self.profiles():
            if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not p['id'] or not isinstance(p.get('name'),str) or not p['name'] or p['id'] in result or p['name'] in result.values():
                raise ReadingError('孩子档案暂时无法核对','profile_error',409)
            result[p['id']]=p['name']
        return result

    def _history(self,c,column,ident):
        return [dict(id=r['id'],action=r['action'],reason=r['reason'],created=r['created'],
                     previous=json.loads(r['previous']),current=json.loads(r['current']))
                for r in c.execute('SELECT * FROM reading_events WHERE '+column+'=? ORDER BY id',(ident,))]

    def _task(self,c,row,names):
        value=dict(row);value['child']=names.get(value['child_id'],value['child_name'])
        value.pop('child_name');value['attachments']=json.loads(value['attachments'])
        award=c.execute('SELECT amount,status,granted_on,reason FROM reading_awards WHERE task_id=?',(value['id'],)).fetchone()
        value['award']=dict(award) if award else None
        value['history']=self._history(c,'task_id',value['id'])
        return value

    def _redemption(self,c,row,names):
        value=dict(row);value['child']=names.get(value['child_id'],value['child_name']);value.pop('child_name')
        value['allocations']=json.loads(value['allocations'])
        value['history']=self._history(c,'redemption_id',value['id'])
        return value

    def _used(self,c,child_id):
        used={}
        for row in c.execute("SELECT allocations FROM reading_redemptions WHERE child_id=? AND state IN ('待兑现','已兑现')",(child_id,)):
            for item in json.loads(row['allocations']):
                used[item['task_id']]=used.get(item['task_id'],0)+item['amount']
        return used

    def _balance(self,c,child_id,name):
        awards=[dict(r) for r in c.execute('SELECT amount,status FROM reading_awards WHERE child_id=?',(child_id,))]
        totals={r['state']:r['cost'] for r in c.execute('SELECT state,sum(cost) AS cost FROM reading_redemptions WHERE child_id=? GROUP BY state',(child_id,))}
        earned=sum(r['amount'] for r in awards)
        active=sum(r['amount'] for r in awards if r['status']!='已撤销')
        reserved=totals.get('待兑现',0);spent=totals.get('已兑现',0)
        available=active-reserved-spent
        if available<0: raise ReadingError('印章账目需要家长核对，已停止新的兑现操作','balance_error',409)
        return dict(child_id=child_id,child=name,earned=earned,reserved=reserved,spent=spent,available=available)

    def snapshot(self):
        names=self._profiles()
        with self._db() as c:
            c.execute('BEGIN')
            tasks=[self._task(c,r,names) for r in c.execute('SELECT * FROM reading_tasks ORDER BY created DESC,id')]
            redemptions=[self._redemption(c,r,names) for r in c.execute('SELECT * FROM reading_redemptions ORDER BY created DESC,id')]
            balances=[self._balance(c,ident,name) for ident,name in names.items()]
            return dict(tasks=tasks,balances=balances,redemptions=redemptions)

    def _source(self,source_id,child_id,names):
        if not source_id: return
        matches=[t for t in self.source_tasks() if t.get('id')==source_id]
        if len(matches)!=1 or matches[0].get('child')!=names[child_id]:
            raise ReadingError('只能关联当前孩子的一项已有待办')

    def _attachments(self,c,ids,child_id,names):
        if not isinstance(ids,list) or len(ids)>20 or any(not isinstance(i,str) or not re.fullmatch(r'[a-f0-9]{32}',i) for i in ids):
            raise ReadingError('作品附件格式不正确，最多20份')
        ids=list(dict.fromkeys(ids))
        validate_record_attachments(c,child_id,ids)
        aliases={names[child_id]}|{r[0] for r in c.execute('SELECT DISTINCT child_name FROM reading_tasks WHERE child_id=?',(child_id,))}
        aliases-=set(name for ident,name in names.items() if ident!=child_id)
        columns={r['name'] for r in c.execute('PRAGMA table_info(records)')}
        for ident in ids:
            if not c.execute('SELECT 1 FROM uploads WHERE id=?',(ident,)).fetchone():
                raise ReadingError('作品原件不存在，请先上传')
            if 'attachments' in columns:
                for row in c.execute('SELECT child,attachments FROM records WHERE attachments LIKE ?',('%'+ident+'%',)):
                    if ident in json.loads(row['attachments']) and row['child'] not in aliases:
                        raise ReadingError('原件已有其他孩子或无法确认的归属，请核对后使用')
            c.execute('INSERT OR IGNORE INTO reading_uploads VALUES (?,?)',(ident,child_id))
        return ids

    def _load(self,c,table,obj,child_id):
        ident=_text(obj,'id',100,required=True)
        row=c.execute('SELECT * FROM '+table+' WHERE id=? AND child_id=?',(ident,child_id)).fetchone()
        if not row: raise ReadingError('这位孩子的阅读任务或兑现记录不存在','not_found',404)
        version=_integer(obj.get('version'),1,2147483647,'版本')
        if row['version']!=version: raise ReadingError('资料已更新，请刷新后核对再操作','version_conflict',409)
        return dict(row)

    def _save_task(self,c,row):
        columns=[k for k in row if k!='id']
        c.execute('UPDATE reading_tasks SET '+','.join(k+'=?' for k in columns)+' WHERE id=?',tuple(row[k] for k in columns)+(row['id'],))

    def mutate(self,action,obj):
        if not isinstance(action,str) or action not in self.TASK_ACTIONS|self.REDEMPTION_ACTIONS or not isinstance(obj,dict):
            raise ReadingError('阅读操作不正确')
        child_id=_text(obj,'child_id',100,required=True)
        key=_text(obj,'request_key',100,required=True)
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key): raise ReadingError('请求编号格式不正确')
        try: payload=_json(dict(action=action,input=obj))
        except (TypeError,ValueError): raise ReadingError('阅读请求格式不正确') from None
        if len(payload)>20000: raise ReadingError('阅读请求内容过长')
        digest=hashlib.sha256(payload.encode()).hexdigest()
        now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            # Serialize profile renames with source and attachment ownership checks.
            names=self._profiles()
            if child_id not in names: raise ReadingError('请选择当前档案中的孩子')
            existing=c.execute('SELECT payload_hash,result FROM reading_events WHERE child_id=? AND request_key=?',(child_id,key)).fetchone()
            if existing:
                if existing['payload_hash']!=digest: raise ReadingError('同一请求编号不能用于不同操作','idempotency_conflict',409)
                return json.loads(existing['result'])
            reason=_text(obj,'reason',1000);note=_text(obj,'note',2000)
            previous={};task_id='';redemption_id=''
            if action in self.TASK_ACTIONS:
                if action=='create':
                    row=dict(id='read-'+secrets.token_hex(12),child_id=child_id,child_name=names[child_id],version=1,
                             state='草案',resume_state='',stamps=_integer(obj.get('stamps',1),1,20,'印章数量'),
                             planned_on=_day(obj.get('planned_on','')),work_text='',attachments='[]',parent_note='',started='',created=now,updated=now)
                    row.update({k:_text(obj,k,limit) for k,limit in self.AGREEMENT.items()})
                    self._source(row['source_task_id'],child_id,names)
                    c.execute('INSERT INTO reading_tasks ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
                else:
                    row=self._load(c,'reading_tasks',obj,child_id);previous=dict(row)
                    prior_award=c.execute('SELECT * FROM reading_awards WHERE task_id=?',(row['id'],)).fetchone()
                    previous['award']=dict(prior_award) if prior_award else None
                    state=row['state']
                    if action=='edit':
                        if state not in ['草案','进行中','需补充','暂停']: raise ReadingError('请先请孩子补充，再调整约定','state_conflict',409)
                        if state=='暂停' and row['resume_state']=='待确认': raise ReadingError('请先恢复并请求补充，再调整待确认作品的约定','state_conflict',409)
                        if row['started'] and not reason: raise ReadingError('调整已开始的任务必须填写原因')
                        stamps=_integer(obj.get('stamps',row['stamps']),1,20,'印章数量')
                        if row['started'] and stamps!=row['stamps']: raise ReadingError('开始后的印章约定已锁定，不能改变已承诺奖项')
                        row['stamps']=stamps
                        for k,limit in self.AGREEMENT.items(): row[k]=_text(obj,k,limit,row[k])
                        if row['started'] and not all(row[k] for k in ['book','scope','method','criteria']):
                            raise ReadingError('已开始的任务必须保留书名、阅读范围、表达方式和完成条件')
                        row['planned_on']=_day(obj.get('planned_on',row['planned_on']))
                        if row['source_task_id']!=previous['source_task_id']: self._source(row['source_task_id'],child_id,names)
                    elif action=='start':
                        if state!='草案': raise ReadingError('只有草案可以开始','state_conflict',409)
                        if not all(row[k] for k in ['book','scope','method','criteria']): raise ReadingError('开始前请约定书名、阅读范围、表达方式和完成条件')
                        if not note: raise ReadingError('请记录孩子开始任务的确认依据')
                        row.update(state='进行中',started=now,parent_note=note)
                    elif action=='submit':
                        if state not in ['进行中','需补充','待确认']: raise ReadingError('当前状态不能提交作品','state_conflict',409)
                        text=_text(obj,'work_text',6000,row['work_text'])
                        ids=self._attachments(c,obj.get('attachments',json.loads(row['attachments'])),child_id,names)
                        if not text and not ids: raise ReadingError('请提供作品文字或一份已上传的原件')
                        row.update(work_text=text,attachments=_json(ids),state='待确认',parent_note='')
                    elif action=='confirm':
                        if state not in ['待确认','已完成']: raise ReadingError('请先提交当前作品供家长确认','state_conflict',409)
                        if not note: raise ReadingError('请填写实际阅读与作品的确认依据')
                        if not row['work_text'] and not json.loads(row['attachments']): raise ReadingError('当前任务没有可核对的作品')
                        c.execute("INSERT OR IGNORE INTO reading_awards VALUES (?,?,?,'已获得',?,'')",(row['id'],child_id,row['stamps'],now))
                        c.execute("UPDATE reading_awards SET status='已获得',reason='' WHERE task_id=?",(row['id'],))
                        row.update(state='已完成',parent_note=note)
                    elif action=='request_more':
                        if state not in ['待确认','已完成']: raise ReadingError('当前状态不能请求补充','state_conflict',409)
                        if not reason: raise ReadingError('请说明需要补充什么')
                        row.update(state='需补充',parent_note=reason)
                    elif action=='pause':
                        if state not in ['进行中','待确认','需补充']: raise ReadingError('当前状态不能暂停','state_conflict',409)
                        if not reason: raise ReadingError('请记录暂停原因')
                        row.update(state='暂停',resume_state=state,parent_note=reason)
                    elif action=='resume':
                        if state!='暂停' or row['resume_state'] not in ['进行中','待确认','需补充']: raise ReadingError('当前任务不能恢复','state_conflict',409)
                        row.update(state=row['resume_state'],resume_state='')
                    elif action=='revoke':
                        if not reason: raise ReadingError('撤销或更正奖励必须填写原因')
                        award=c.execute('SELECT * FROM reading_awards WHERE task_id=?',(row['id'],)).fetchone()
                        if not award: raise ReadingError('这项任务尚未获得印章','state_conflict',409)
                        status='需家长处理' if self._used(c,child_id).get(row['id'],0) else '已撤销'
                        c.execute('UPDATE reading_awards SET status=?,reason=? WHERE task_id=?',(status,reason,row['id']))
                    row['version']+=1;row['updated']=now;self._save_task(c,row)
                task_id=row['id'];current=dict(row)
                award=c.execute('SELECT * FROM reading_awards WHERE task_id=?',(task_id,)).fetchone()
                current['award']=dict(award) if award else None
            else:
                if action=='reserve':
                    reward=_text(obj,'reward',200,required=True);cost=_integer(obj.get('cost',3),1,100,'兑换所需印章')
                    if not note: raise ReadingError('请记录家长与孩子事先约定的奖励内容')
                    if self._balance(c,child_id,names[child_id])['available']<cost: raise ReadingError('可用印章不足，待兑现的印章不能重复使用','insufficient_balance',409)
                    used=self._used(c,child_id);left=cost;allocations=[]
                    for award in c.execute("SELECT * FROM reading_awards WHERE child_id=? AND status<>'已撤销' ORDER BY granted_on,task_id",(child_id,)):
                        amount=min(left,award['amount']-used.get(award['task_id'],0))
                        if amount>0: allocations.append(dict(task_id=award['task_id'],amount=amount));left-=amount
                        if not left: break
                    if left: raise ReadingError('奖项分配需要核对，未创建兑换','balance_error',409)
                    row=dict(id='redeem-'+secrets.token_hex(12),child_id=child_id,child_name=names[child_id],version=1,state='待兑现',
                             reward=reward,cost=cost,planned_on=_day(obj.get('planned_on','')),note=note,correction_note='',
                             allocations=_json(allocations),created=now,updated=now)
                    c.execute('INSERT INTO reading_redemptions ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
                else:
                    row=self._load(c,'reading_redemptions',obj,child_id);previous=dict(row)
                    if action=='fulfill':
                        if row['state']!='待兑现': raise ReadingError('只有待兑现的约定可以确认实际兑现','state_conflict',409)
                        if not note: raise ReadingError('请填写实际兑现的内容和依据')
                        row.update(state='已兑现',note=note)
                    elif action=='cancel_redemption':
                        if row['state']!='待兑现': raise ReadingError('只有待兑现的约定可以取消，已兑现请另记更正','state_conflict',409)
                        if not reason: raise ReadingError('取消兑现必须填写原因')
                        row.update(state='已取消',note=reason)
                    elif action=='correct_redemption':
                        if row['state']!='已兑现': raise ReadingError('只有已兑现记录可以登记更正','state_conflict',409)
                        if not reason: raise ReadingError('更正兑现记录必须填写原因')
                        row['correction_note']=reason
                    row['version']+=1;row['updated']=now
                    c.execute('UPDATE reading_redemptions SET version=?,state=?,note=?,correction_note=?,updated=? WHERE id=?',
                              (row['version'],row['state'],row['note'],row['correction_note'],now,row['id']))
                redemption_id=row['id'];current=dict(row)
            event=c.execute('INSERT INTO reading_events (child_id,request_key,payload_hash,action,task_id,redemption_id,reason,previous,current,created) VALUES (?,?,?,?,?,?,?,?,?,?)',
                (child_id,key,digest,action,task_id,redemption_id,reason or note,_json(previous),_json(current),now))
            result=dict(task=self._task(c,row,names)) if task_id else dict(redemption=self._redemption(c,row,names))
            c.execute('UPDATE reading_events SET result=? WHERE id=?',(_json(result),event.lastrowid));c.commit()
            return result
