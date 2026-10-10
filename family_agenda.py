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

def sent_at(value):
    try:
        stamp=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp.replace(tzinfo=stamp.tzinfo or family_agent.TZ).astimezone(family_agent.TZ).isoformat()
    except (ValueError,TypeError,AttributeError):return ''

def sent_day(value):
    return sent_at(value)[:10]


_WEEKDAYS={'一':0,'二':1,'三':2,'四':3,'五':4,'六':5,'日':6,'天':6}


def _relative_weekday(text,anchor):
    """Ground 本周X/下周X/周X against the sending day; recurring (每周), past (上周) or unknown anchors stay as written."""
    if not anchor: return text
    sent=dt.date.fromisoformat(anchor); monday=sent-dt.timedelta(days=sent.weekday())
    def resolve(match):
        if match.group('range') or (match.group('prefix') or '').startswith(('每','上')) or re.search(r'[每上本这下个]\s+$',text[:match.start()]): return match[0]
        prefix,name=match.group('prefix') or '',_WEEKDAYS[match.group('day')]
        if prefix in ('本','这','这个','本个'): value=monday+dt.timedelta(days=name)
        elif prefix in ('下','下个'): value=monday+dt.timedelta(days=7+name)
        else: value=monday+dt.timedelta(days=name+(7 if name<sent.weekday() else 0))
        # A day already gone this week is not a usable deadline; leave the phrase for review.
        return value.isoformat() if value>=sent else match[0]
    return re.sub(r'(?<![每上本这下个])(?P<prefix>每个|上个|本个|这个|下个|每|上|本|这|下)?(?:周|星期|礼拜)(?P<day>[一二三四五六日天])(?P<range>\s*(?:到|至|[-–—~～])\s*(?:本个|这个|下个|本|这|下)?(?:周|星期|礼拜)?[一二三四五六日天])?(?![周月年])',resolve,text)


def _grounded_text(text,anchor):
    def chinese_date(match):
        year,month,day=match.groups()
        # ponytail: an omitted year is grounded only within the sending month; other cases need review.
        if not year and (not anchor or int(month)!=int(anchor[5:7])): return match[0]
        value=f'{int(year or anchor[:4]):04d}-{int(month):02d}-{int(day):02d}'
        return value if date(value) else match[0]
    return re.sub(r'(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日',chinese_date,text or '')


def deadlines(text,published):
    """Every date the text ties to a required action or dated school event, grounded on the sending day."""
    return _action_deadlines(text,published)|event_days(text,published)


def _action_deadlines(text,published):
    """Every date the text ties to a required action, grounded on the sending day."""
    anchor=date(published)
    text=_grounded_text(text,anchor)
    if date(text): return {text}
    text=_relative_weekday(text,anchor)
    candidates=set()
    # A date alone is not a deadline; it must be tied to an explicit action or dated school event.
    pattern=r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)(?:[^。；;，,\n]{0,8}?)(?:前|截止|完成|订正|提交|上交|交齐|带到|带来|交作业|朗读|背诵|抄写|预习|听[^。；;，,\n]{0,12}录音|带|穿|交(?!流|通|换|谈)|测验|考试|听写|默写|检测)'
    for match in re.finditer(pattern,text or ''):
        token=match[1];value=date(token)
        if not value and published and token in ('今天','今日','今晚','明天','明日','后天'):
            offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[token]
            try:value=(dt.date.fromisoformat(published)+dt.timedelta(days=offset)).isoformat()
            except OverflowError:pass
        if value:candidates.add(value)
    for match in re.finditer(r'截止(?:时间|日期)?\s*[：:为是]*\s*(\d{4}-\d{2}-\d{2})',text):
        if date(match[1]): candidates.add(match[1])
    # A directly dated revision/parent action is just as explicit as 完成 or
    # 提交. Keep this grammar narrow: do not turn 公布复习资料, 打印机指南 or
    # 签字安排 into a deadline by searching arbitrarily past the date.
    direct_prefix=r'[ \t：:]*(?:(?:需要|务必|由家长|同学们|家长|孩子|学生|请|需|须|要|先)[ \t]*){0,2}(?:(?:语文|数学|英语|科学|历史|地理|生物|物理|化学)[ \t：:]*)?'
    direct_action=r'(?:复习|打印|签字|盖章)(?!资料|材料|计划|安排|通知|要求|时间|指南|方法|建议|结果|情况|方式|入口|功能|机)'
    for match in re.finditer(r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)'+direct_prefix+direct_action,text):
        token=match[1];value=date(token)
        if not value and anchor and token in ('今天','今日','今晚','明天','明日','后天'):
            offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[token]
            try:value=(dt.date.fromisoformat(anchor)+dt.timedelta(days=offset)).isoformat()
            except OverflowError:pass
        if value:candidates.add(value)
    for match in re.finditer(r'(?:报名|填报|选课|提交|上交)时间\s*[：:为是]*\s*(\d{4}-\d{2}-\d{2})([^。；;\n]*)',text):
        day,tail=match.groups()
        clock=r'(?:[01]?\d|2[0-3])[:：][0-5]\d'
        if date(day) and not re.search(r'\d{4}-\d{2}-\d{2}|起|开始|持续',tail) and re.fullmatch(r'\s*'+clock+r'\s*[-–—‑~～至到]\s*'+clock+r'[！!❗‼️\s]*',tail):
            start,end=[tuple(map(int,t)) for t in re.findall(r'(\d{1,2})[:：](\d{2})',tail)]
            if start<=end:candidates.add(day)
    # A dated test the child sits: the subject and unit name (e.g. 英语Unit1-3单元) often sit between the
    # date and the exam word, past the tight window above. Allow that gap but stop before another date
    # or a clause break so separate items keep their own dates. 测试/检测 stay out here: 设备测试/核酸检测
    # are not tests the child sits, and the tight pass already covers their own phrasings.
    span=r'(?:(?!\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)[^。；;，,\n]){0,16}?'
    reading_event=r'读(?=[一二两三四五六七八九十百0-9]+(?:遍|次))'
    # Unit/title names can separate the date from the reading action. Do not
    # cross a different date or clause, or treat a material's name as an action.
    for match in re.finditer(r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)'+span+r'(?:'+reading_event+r')',text or ''):
        token=match[1];value=date(token)
        if not value and published and token in ('今天','今日','今晚','明天','明日','后天'):
            offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[token]
            try:value=(dt.date.fromisoformat(published)+dt.timedelta(days=offset)).isoformat()
            except OverflowError:pass
        if value:candidates.add(value)
    # A conflicting relative/explicit parenthetical is uncertainty, not a
    # reason to silently prefer one date. A mere date label remains no action.
    for match in re.finditer(r'(今天|今日|今晚|明天|明日|后天)\s*[（(]\s*(\d{4}-\d{2}-\d{2})\s*[）)]',text or ''):
        if not published or not re.match(span+r'(?:完成|订正|提交|上交|交齐|带到|带来|交作业|朗读|背诵|抄写|预习|'+reading_event+r')',text[match.end():]):continue
        offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[match[1]]
        try:relative=(dt.date.fromisoformat(published)+dt.timedelta(days=offset)).isoformat()
        except OverflowError:continue
        if date(match[2]):candidates.update((relative,match[2]))
    exam_event=r'单元测|体育测试|小测|月考|期中|期末|测验|考试|统考|联考|水平测|质检|摸底'
    for match in re.finditer(r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)'+span+r'(?:'+exam_event+r')',text or ''):
        token=match[1];value=date(token)
        if not value and published and token in ('今天','今日','今晚','明天','明日','后天'):
            offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[token]
            try:value=(dt.date.fromisoformat(published)+dt.timedelta(days=offset)).isoformat()
            except OverflowError:pass
        if value:candidates.add(value)
    return candidates


_EVENT_DAY=r'\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天'
_DAY_WORDS=r'\d{4}-\d{2}-\d{2}|\d{1,2}\s*月\s*\d{1,2}|今天|今日|今晚|明天|明日|明早|明晚|后天|昨天|前天|(?:周|星期|礼拜)[一二三四五六日天]'
_ATTEND_REQUEST=r'(?:请|务必|必须|须|需)(?:各位|全体)?(?:家长|学生|同学们?|孩子们?)?(?:准时|按时|届时|务必|必须|须|需)?(?:参加|出席|到场|参会)(?!安排|通知|方式|时间|人员|名单)'
# Not (yet) held on that day, or attending it is optional.
_EVENT_STATE=(r'取消|延期|改期|推迟|暂停|停办|改为|改到|改至|原定|已于|已经|已举行|已召开|已结束|回顾|暂定|初定|拟(?:于|在|定)|待定|待确定|尚未确定|未定'
              r'|另行(?:通知|告知|安排)|(?:后续|稍后|随后|再行|届时)(?:通知|告知|公布)|待通知'
              r'|自愿|自由|可选|可以?不|不必|无需|无须|不用|不需要?|不要求|不强制|非强制|非必须|不作(?:统一|强制)?要求|酌情|视情况|仅供参考|选择性')
# What is left of a clause about this event, its time or attending it; 座位、打印材料、带材料 are other objects.
_EVENT_SELF=(r'本次|此次|这次|该次?|届时|如有(?:变动|变化|调整)|若有(?:变动|变化|调整)|具体|准确|确切|详细|时间|日期|安排|的|将|会|再|均|都|也|是|为'
             r'|请|各位|全体|家长们?|学生们?|同学们?|孩子们?|准时|按时|务必|必须|须|需|参加|出席|到场|参会|会议|活动|开会|大会|集会|运动|典礼|仪式|讲座|开放日|演出|比赛|\s')


def event_days(text,published):
    """The arranged day of a held school event the family is directly asked to attend (家长会定于10月15日举行，请家长参加).

    It is that item's own arranged day, not a completion deadline. One sentence states one grounded day, one clause
    holding the event and a direct request to attend (明日 grounds on the sending day; 务必/须参加 is as direct as
    请参加); ！？ end a sentence, so a notice's own date never reaches a later event. A negation, state or option counts
    on what it modifies: the event's own clause (不是10月15日举行、暂定、原定…取消、按10月9日通知), the request (自愿参加)
    or a clause with no other object (参加自愿、不作统一要求、准确时间后续告知). 座位可选、取消打印材料、无需带材料 keep
    the meeting; a past day stays out.
    """
    anchor=date(published)
    text=_relative_weekday(_grounded_text(text,anchor),anchor)
    relative={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}
    found=set()
    for sentence in re.split(r'[。；;！!？?\n]',text):
        values={date(d) or (anchor and d in relative and (dt.date.fromisoformat(anchor)+dt.timedelta(days=relative[d])).isoformat()) or '' for d in re.findall(_DAY_WORDS,sentence)}
        clauses=[c for c in re.split(r'[，,、：:]',sentence) if c.strip()]
        held=[n for n,c in enumerate(clauses) if re.search(r'(?:'+_EVENT_DAY+r')[^，,]{0,20}?(?:举行|召开|举办)',c)]
        if len(values)!=1 or '' in values or len(held)!=1 or not re.search(_ATTEND_REQUEST,sentence):continue
        value=next(iter(values));event=clauses[held[0]]
        if (anchor and value<anchor or re.search(_EVENT_STATE,event)
                or re.search(r'(?:不是|并非|而非|并不在|不在|不于|不会在)\s*(?:于|在)?\s*(?:'+_EVENT_DAY+r')|(?:不|未|没有?|无法|不能|不会|不再)\s*(?:如期|按时|正常)?\s*(?:举行|召开|举办)',event)
                or re.search(r'(?:根据|依据|按照|参照|参见|据|按|见|同)\s*(?:'+_EVENT_DAY+r')|(?:'+_EVENT_DAY+r')[^，,]{0,6}?(?:通知|公告|文件|来函|消息|发布|发出)',event)):continue
        if any(re.search(_EVENT_STATE,c) and not re.sub(_EVENT_SELF,'',re.sub(_EVENT_STATE,'',c)) for n,c in enumerate(clauses) if n!=held[0]):continue
        found.add(value)
    return found


def date_meaning(quote,due,published):
    """'event' when due is the arranged day of the held event this item's own original clause asks to attend."""
    if not date(due):return ''
    return 'event' if due in event_days(quote,published) and due not in _action_deadlines(quote,published) else 'deadline'


def deadline(text,published):
    """Only an unambiguous deadline phrase; several different dates need review."""
    candidates=deadlines(text,published)
    return next(iter(candidates)) if len(candidates)==1 else ''


_EXAM_RE = re.compile(r'测验|测试|考试|单元测|小测|月考|期中|期末|检测|统考|联考|水平测|质检|摸底')


def _exam_identity(text):
    """The smallest stable identity needed to keep one subject's exams apart."""
    text=(text or '').lower()
    kind=next((x for x in ('单元','期中','期末','月考','小测','统考','联考','水平测','质检','摸底') if x in text),
              '测验' if '测验' in text else '考试' if '考试' in text else '测试' if re.search(r'测试|检测',text) else '')
    units=set()
    for value in re.findall(r'unit\s*\d+(?:\s*[-–—~～至到]\s*(?:unit\s*)?\d+)?',text,re.I):
        units.add('unit'+'-'.join(re.findall(r'\d+',value)))
    units.update(re.findall(r'第?[一二三四五六七八九十百0-9]+单元',text))
    return kind,units


def is_exam(text):
    """A graded test event worth recording a result for; daily 听写/默写 homework is not one."""
    # ponytail: title-only heuristic; explicit event types can replace it if ambiguous titles recur.
    text = text or ''
    if re.search(r'打印|复习|订正|报名|缴费|签字|回执|备考|准备|核酸|视力|体检|听力筛查|软件|设备|网络|成绩|结果|试卷|卷子', text): return False
    return bool(_EXAM_RE.search(text))


def task_category(title,purpose=None):
    """Classify the requested work, not a school subject mentioned by an admin task."""
    if purpose in family_agent.PURPOSES:
        return 'homework' if purpose=='learning' and not is_exam(title) else 'todo'
    title=re.sub(r'^待核对[：:]?\s*','',title)
    if re.search(r'打印|报名|缴费|回执|签字|署名|登记|确认书|请假|接送|招新|选拔|提交渠道|(?:作业|学习)入口|^核(?:对|查)|(?:听写|考试|测验)(?:情况|结果|成绩)|等级',title):
        return 'todo'
    if re.search(r'作业|习作|作文|听写|默写|背诵|练习|订正|摘抄|抄写|朗读|阅读单|阅读任务|预习|复习|^(?:语文|英语|数学|科学|历史|地理|生物|物理|化学)[：:]',title):
        return 'homework'
    # ponytail: uncertain school material stays a to-do to review, never an invented assignment.
    return 'todo'


def metadata(app,c,child_id,title,due,refs=(),focus=None,purpose=None,*,publication_ref='',date_quote=''):
    focus=focus or {};messages=[];publications=[];original_time=''
    store=family_agent.Store(app.connect,app.profiles,app.DATA,initialize=False)
    for ref in refs:
        if not isinstance(ref,str) or not ref.startswith('message:'):continue
        parts=ref[8:].rsplit(':',1)
        if len(parts)!=2:continue
        try:
            source,msg=store._message_context(c,dict(child_id=child_id,source_id=parts[0],message_id=parts[1]))
            messages.append(msg)
            if ref==publication_ref:original_time=sent_at(msg.get('time',''))
            if not any(p['ref']==ref for p in publications):
                publications.append(dict(ref=ref,source_name=source['name'],sender=msg.get('sender','')))
        except family_agent.AgentError:continue
    times=sorted({sent_at(m.get('time','')) for m in messages}-{''})
    days=sorted({value[:10] for value in times})
    organized=focus.get('category') in ('unknown','homework','todo')
    published=focus.get('published_on','') if organized else (original_time[:10] if original_time else days[0] if len(days)==1 else '')
    subject=re.sub(r'^待核对[：:]?\s*','',title).rstrip('。')
    # Borrow a source deadline only from the clause naming THIS task, not a sibling instruction.
    # An exam task's title is usually rewritten (subject prefix, weekday suffix), so it is no longer a
    # literal substring of the notice. Match its school subject; do not borrow another exam's date.
    clauses=[(clause,m) for m in messages for clause in re.split(r'[。；;，,\n]',m.get('text',''))]
    named=[(clause,m) for clause,m in clauses if subject and subject in clause]
    prefix=re.match(r'\s*([^：:]{1,12})[：:]',subject)
    exam_subject=prefix[1].strip() if prefix else ''
    exam_kind,exam_units=_exam_identity(subject)
    fallback=[(clause,m) for clause,m in clauses if exam_subject and exam_subject in clause and
              _exam_identity(clause)[0]==exam_kind and (not exam_units or exam_units & _exam_identity(clause)[1])]
    selected=(named or fallback) if is_exam(subject) else named
    # A school item's date comes only from its own original clause, never from another action naming it.
    if date_quote:selected=[(clause,m) for clause,m in selected if clause.strip() and clause.strip() in date_quote]
    dates={deadline(clause,sent_day(m.get('time',''))) for clause,m in selected}-{''}
    source_unknown=any(re.search(r'(?:时间|日期).{0,6}(?:另行通知|另行安排|待定|未定)',clause) for clause,_ in selected)
    source_due=next(iter(dates)) if len(dates)==1 and not source_unknown else ''
    due_on=focus.get('due_on','') if organized else deadline(due,published) or deadline(title,published) or source_due
    category=focus.get('category','')
    if category not in ('homework','todo'):category='todo' if category=='unknown' else task_category(title,purpose)
    # Later supplements retain their own source entries, not the first notice's time.
    published_at=original_time if original_time and original_time[:10]==published else min((value for value in times if value[:10]==published),default='')
    # The same day reads as the meeting's arranged day or a hand-in deadline by what the item's own clause asks;
    # a parent-edited date keeps the deadline contract.
    due_kind=date_meaning(date_quote,due_on,published) if date_quote and not organized else 'deadline' if due_on else ''
    return dict(category=category,published_on=published,published_at=published_at,publications=publications,due_on=due_on,due_kind=due_kind,scheduled_on=focus.get('scheduled_on',''),
                category_confirmed=focus.get('category') in ('homework','todo'),publication_known=bool(published),box=focus.get('box') or 'inbox')


def enrich(app,c,tasks):
    owners={p['name']:p['id'] for p in app.profiles(c)}
    reported={r['task_id']:r['day'] for r in c.execute('SELECT task_id,day FROM study_items WHERE id=task_id')} if c.execute("SELECT 1 FROM sqlite_master WHERE name='study_items'").fetchone() else {}
    for task in tasks:
        refs=[x.strip() for x in task['source'].splitlines() if x.strip().startswith('message:')]
        focus=task.get('focus') or {}
        purpose=None;publication_ref='';date_quote=''
        if task.get('school_origin'):
            origin=task['source'].splitlines()[0].removeprefix('Agent建议:')
            proposal=c.execute("SELECT * FROM agent_items WHERE id=? AND task_id=? AND child_id=? AND kind='school' AND state='accepted'",
                               (origin,task['id'],owners.get(task['child'],''))).fetchone()
            if proposal:
                purpose=json.loads(proposal['plan']).get('school_task',{}).get('purpose')
                store=family_agent.Store(app.connect,app.profiles,app.DATA,initialize=False)
                publication_ref=family_agent.school_original_publication_ref(store,c,proposal)
                date_quote=re.sub(r'^待核对[：:]?\s*','',proposal['title'])
        due=task['due']
        if task['id'] in reported and task['source'] in ('家庭放学后录入','孩子自述功课，待家长核对'):
            # The capture day is a plan date, not a teacher deadline; preserve explicit later edits.
            focus=dict(focus)
            if not focus.get('category'):focus['category']='homework'
            if not focus.get('scheduled_on') and not focus.get('version'):focus['scheduled_on']=reported[task['id']]
            due=task['due']=''
        task['agenda']=metadata(app,c,owners.get(task['child'],''),task.get('original_title',task['title']),due,refs,focus,purpose,publication_ref=publication_ref,date_quote=date_quote)
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
            for row in c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='pending' ORDER BY created DESC,id DESC"):
                brief=json.loads(row['plan']).get('school_task',{})
                if row['child_id'] not in ids or brief.get('state')=='reference':continue
                refs=[e['ref'] for e in json.loads(row['evidence'])]
                purpose=brief.get('purpose')
                category=task_category((brief.get('title') or row['title']) if purpose in family_agent.PURPOSES else row['title'],purpose)
                m=metadata(app,c,row['child_id'],row['title'],row['due'],refs)
                m['category']=category
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
