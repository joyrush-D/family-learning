"""Calendar views of existing tasks, school inbox and study sessions; no copied tasks."""
import datetime as dt
import json
import re
import family_agent
import family_calendar


def date(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value or ''): return ''
        return dt.date.fromisoformat(value).isoformat()
    except (ValueError,TypeError): return ''

def sent_day(value):
    try:
        stamp=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp.replace(tzinfo=stamp.tzinfo or family_agent.TZ).astimezone(family_agent.TZ).date().isoformat()
    except (ValueError,TypeError,AttributeError):return ''


def deadline(text,published):
    """Only an unambiguous deadline phrase; an event date alone is not a deadline."""
    if date(text): return text
    candidates=set()
    pattern=r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)(?:[^。；;\n]{0,8}?)(?:前|截止|完成|提交|上交|交齐|带到|交作业)'
    for match in re.finditer(pattern,text or ''):
        token=match[1];value=date(token)
        if not value and published and token in ('今天','今日','今晚','明天','明日','后天'):
            offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[token]
            try:value=(dt.date.fromisoformat(published)+dt.timedelta(days=offset)).isoformat()
            except OverflowError:pass
        if value:candidates.add(value)
    return next(iter(candidates)) if len(candidates)==1 else ''


def metadata(app,c,child_id,title,due,refs=(),focus=None):
    focus=focus or {};messages=[]
    store=family_agent.Store(app.connect,app.profiles,app.DATA,initialize=False)
    for ref in refs:
        if not isinstance(ref,str) or not ref.startswith('message:'):continue
        parts=ref[8:].rsplit(':',1)
        if len(parts)!=2:continue
        try:
            _,msg=store._message_context(c,dict(child_id=child_id,source_id=parts[0],message_id=parts[1]))
            messages.append(msg)
        except family_agent.AgentError:continue
    days=sorted({sent_day(m.get('time','')) for m in messages}-{''})
    organized=focus.get('category') in ('unknown','homework','todo')
    published=focus.get('published_on','') if organized else (days[0] if len(days)==1 else '')
    # Only borrow a source deadline from the clause naming this task, not a sibling instruction.
    subject=re.sub(r'^待核对[：:]?\s*','',title).rstrip('。')
    dates={deadline(clause,sent_day(m.get('time',''))) for m in messages
           for clause in re.split(r'[。；;，,\n]',m.get('text','')) if subject and subject in clause}-{''}
    due_on=focus.get('due_on','') if organized else deadline(due,published) or deadline(title,published) or (next(iter(dates)) if len(dates)==1 else '')
    # ponytail: conservative visible-word classification; parents can correct it in the existing arrangement form.
    category=focus.get('category','')
    if not category:
        if re.search('打印|报名|缴费|回执|签字|带.*(?:用品|材料)|通知|活动',title):category='todo'
        elif re.search('作业|习作|作文|听写|默写|背诵|练习|订正',title):category='homework'
    return dict(category=category if category!='unknown' else '',published_on=published,due_on=due_on,scheduled_on=focus.get('scheduled_on',''),
                category_confirmed=bool(focus.get('category')),publication_known=bool(published))


def enrich(app,c,tasks):
    owners={p['name']:p['id'] for p in app.profiles(c)}
    for task in tasks:
        refs=[x.strip() for x in task['source'].splitlines() if x.strip().startswith('message:')]
        task['agenda']=metadata(app,c,owners.get(task['child'],''),task['title'],task['due'],refs,task.get('focus'))
    return tasks


def visible_on(item,day):
    m=item['agenda'];published=m['published_on'];due=m['due_on'];scheduled=m['scheduled_on']
    if published and day<published:return False
    if item['closed']:
        return day in {published,scheduled,due,item.get('closed_on','')} and (not item.get('closed_on') or day<=item['closed_on'])
    if day==published or day==scheduled:return True
    # An undated item remains in the inbox; a deadline carries forward until a parent closes it.
    # Unknown publication stays unknown, but a known deadline must not hide from today's work.
    return bool(due and day>=(published or min(due,scheduled or due,dt.datetime.now(family_agent.TZ).date().isoformat())))


def snapshot(app,start,end):
    with app.connect() as c:
        c.execute('BEGIN')
        profiles=app.profiles(c);owners={p['name']:p['id'] for p in profiles};ids=set(owners.values())
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        updates={r['id']:dict(r) for r in c.execute('SELECT * FROM task_updates')}
        items=[]
        for task in app.tasks(c):
            if task['child'] not in owners:continue
            u=updates.get(task['id'],{});status=app.task_status(task,u.get('status'))
            items.append(dict(id=task['id'],task_id=task['id'],kind='task',child_ids=[owners[task['child']]],
                title=task['title'],agenda=task['agenda'],status=status,closed=status in app.TASK_CLOSED,
                closed_on=date(u.get('updated','')[:10]),body=task['action']))
        if 'agent_items' in tables:
            for row in c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='pending' ORDER BY created,id"):
                if row['child_id'] not in ids:continue
                refs=[e['ref'] for e in json.loads(row['evidence'])]
                m=metadata(app,c,row['child_id'],row['title'],row['due'],refs)
                items.append(dict(id=row['id'],task_id='',kind='school',child_ids=[row['child_id']],title=row['title'],
                    agenda=m,status='待核对',closed=False,closed_on='',body=row['body']))
        study=[]
        if 'study_items' in tables:
            for row in c.execute('SELECT * FROM study_items ORDER BY day,rowid'):
                if row['child_id'] not in ids:continue
                entry=dict(id=row['id'],task_id=row['task_id'],kind='study',child_ids=[row['child_id']],day=row['day'],
                    title=row['title'],status=row['status'],result=row['result'],result_actor=dict(row).get('result_actor','parent'))
                if start<=row['day']<=end:study.append(entry)
                if not row['task_id']:
                    items.append(dict(entry,agenda=dict(category='homework',published_on='',due_on='',scheduled_on=row['day']),
                        closed=row['result']=='完成' and entry['result_actor']=='parent',closed_on=row['day']))
        plans=[]
        if 'calendar_events' in tables:
            for row in c.execute('SELECT * FROM calendar_events ORDER BY day,id'):
                event=family_calendar.Store._manual(row)
                if any(child not in ids for child in event['child_ids']):continue
                plans.append(dict(id='calendar:'+event['id'],task_id='',kind='event',child_ids=event['child_ids'],title=event['title'],
                    agenda=dict(category='todo',published_on='',due_on='',scheduled_on=event['day']),closed=event['status'] in ('cancelled','completed'),event=event))
    first=dt.date.fromisoformat(start);count=(dt.date.fromisoformat(end)-first).days+1
    agenda=[]
    for offset in range(count):
        day=(first+dt.timedelta(days=offset)).isoformat()
        agenda.extend(dict(item,day=day) for item in items if visible_on(item,day))
    return dict(agenda=agenda,study=study,inbox=items+plans)
