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


_WEEKDAYS={'一':0,'二':1,'三':2,'四':3,'五':4,'六':5,'日':6,'天':6}


def _relative_weekday(text,anchor):
    """Ground 本周X/下周X/周X against the sending day; recurring (每周), past (上周) or unknown anchors stay as written."""
    if not anchor: return text
    sent=dt.date.fromisoformat(anchor); monday=sent-dt.timedelta(days=sent.weekday())
    def resolve(match):
        if match.group('range'): return match[0]
        prefix,name=match.group('prefix') or '',_WEEKDAYS[match.group('day')]
        if prefix in ('本','这','这个','本个'): value=monday+dt.timedelta(days=name)
        elif prefix in ('下','下个'): value=monday+dt.timedelta(days=7+name)
        else: value=monday+dt.timedelta(days=name+(7 if name<sent.weekday() else 0))
        # A day already gone this week is not a usable deadline; leave the phrase for review.
        return value.isoformat() if value>=sent else match[0]
    return re.sub(r'(?<![每上本这下个])(?P<prefix>本个|这个|下个|本|这|下)?(?:周|星期|礼拜)(?P<day>[一二三四五六日天])(?P<range>\s*(?:到|至|[-–—~～])\s*(?:本个|这个|下个|本|这|下)?(?:周|星期|礼拜)?[一二三四五六日天])?(?![周月年])',resolve,text)


def deadlines(text,published):
    """Every date the text ties to a required action or dated school event, grounded on the sending day."""
    anchor=date(published)
    def chinese_date(match):
        year,month,day=match.groups()
        # ponytail: an omitted year is grounded only within the sending month; other cases need review.
        if not year and (not anchor or int(month)!=int(anchor[5:7])): return match[0]
        value=f'{int(year or anchor[:4]):04d}-{int(month):02d}-{int(day):02d}'
        return value if date(value) else match[0]
    text=re.sub(r'(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日',chinese_date,text or '')
    if date(text): return {text}
    text=_relative_weekday(text,anchor)
    candidates=set()
    # A date alone is not a deadline; it must be tied to handing in, bringing or a dated test the child sits.
    pattern=r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)(?:[^。；;\n]{0,8}?)(?:前|截止|完成|提交|上交|交齐|带到|带来|交作业|带|穿|交(?!流|通|换|谈)|测验|考试|听写|默写|检测)'
    for match in re.finditer(pattern,text or ''):
        token=match[1];value=date(token)
        if not value and published and token in ('今天','今日','今晚','明天','明日','后天'):
            offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[token]
            try:value=(dt.date.fromisoformat(published)+dt.timedelta(days=offset)).isoformat()
            except OverflowError:pass
        if value:candidates.add(value)
    for match in re.finditer(r'截止(?:时间|日期)?\s*[：:为是]*\s*(\d{4}-\d{2}-\d{2})',text):
        if date(match[1]): candidates.add(match[1])
    for match in re.finditer(r'(?:报名|填报|选课|提交|上交)时间\s*[：:为是]*\s*(\d{4}-\d{2}-\d{2})([^。；;\n]*)',text):
        day,tail=match.groups()
        clock=r'(?:[01]?\d|2[0-3])[:：][0-5]\d'
        if date(day) and not re.search(r'\d{4}-\d{2}-\d{2}|起|开始|持续',tail) and re.fullmatch(r'\s*'+clock+r'\s*[-–—‑~～至到]\s*'+clock+r'[！!❗‼️\s]*',tail):
            start,end=[tuple(map(int,t)) for t in re.findall(r'(\d{1,2})[:：](\d{2})',tail)]
            if start<=end:candidates.add(day)
    return candidates


def deadline(text,published):
    """Only an unambiguous deadline phrase; several different dates need review."""
    candidates=deadlines(text,published)
    return next(iter(candidates)) if len(candidates)==1 else ''


_EXAM_RE = re.compile(r'测验|测试|考试|单元测|小测|月考|期中|期末|检测|统考|联考|水平测|质检|摸底')


def is_exam(text):
    """A graded test event worth recording a result for; daily 听写/默写 homework is not one."""
    # ponytail: title-only heuristic; explicit event types can replace it if ambiguous titles recur.
    text = text or ''
    if re.search(r'打印|复习|订正|报名|缴费|签字|回执|备考|准备|核酸|视力|体检|听力筛查|软件|设备|网络|成绩|结果|试卷|卷子', text): return False
    return bool(_EXAM_RE.search(text))


def task_category(title):
    """Classify the requested work, not a school subject mentioned by an admin task."""
    title=re.sub(r'^待核对[：:]?\s*','',title)
    if re.search(r'打印|报名|缴费|回执|签字|署名|登记|确认书|请假|接送|招新|选拔|提交渠道|(?:作业|学习)入口|^核(?:对|查)|(?:听写|考试|测验)(?:情况|结果|成绩)|等级',title):
        return 'todo'
    if re.search(r'作业|习作|作文|听写|默写|背诵|练习|订正|摘抄|抄写|朗读|阅读单|阅读任务|预习|复习|^(?:语文|英语|数学|科学|历史|地理|生物|物理|化学)[：:]',title):
        return 'homework'
    # ponytail: uncertain school material stays a to-do to review, never an invented assignment.
    return 'todo'


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
    category=focus.get('category','')
    if category not in ('homework','todo'):category='todo' if category=='unknown' else task_category(title)
    return dict(category=category,published_on=published,due_on=due_on,scheduled_on=focus.get('scheduled_on',''),
                category_confirmed=focus.get('category') in ('homework','todo'),publication_known=bool(published),box=focus.get('box') or 'inbox')


def enrich(app,c,tasks):
    owners={p['name']:p['id'] for p in app.profiles(c)}
    for task in tasks:
        refs=[x.strip() for x in task['source'].splitlines() if x.strip().startswith('message:')]
        task['agenda']=metadata(app,c,owners.get(task['child'],''),task.get('original_title',task['title']),task['due'],refs,task.get('focus'))
    return tasks


def visible_on(item,day):
    m=item['agenda']
    if m.get('box')=='wish': return False
    published=m['published_on'];due=m['due_on'];scheduled=m['scheduled_on']
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
                if row['child_id'] not in ids or json.loads(row['plan']).get('school_task',{}).get('state')=='reference':continue
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
            saved=family_calendar.Store.saved_rows(c,ids)
            parents={e['id']:e for e in saved if not e['occurrence']}
            for event in saved:
                if any(child not in ids for child in event['child_ids']):continue
                if event['occurrence']:
                    event['occurrence']=dict(event['occurrence'],version=event['version'],series_version=parents[event['occurrence']['series_id']]['version'])
                plans.append(dict(id='calendar:'+event['id'],task_id='',kind='event',child_ids=event['child_ids'],title=event['title'],
                    agenda=dict(category='todo',published_on='',due_on='',scheduled_on=event['day']),closed=event['status'] in ('cancelled','completed'),event=event))
    first=dt.date.fromisoformat(start);count=(dt.date.fromisoformat(end)-first).days+1
    agenda=[]
    for offset in range(count):
        day=(first+dt.timedelta(days=offset)).isoformat()
        agenda.extend(dict(item,day=day) for item in items if visible_on(item,day))
    return dict(agenda=agenda,study=study,inbox=items+plans)
