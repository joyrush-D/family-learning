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
# A state word that can take what follows as its object: 取消打印材料 cancels the printing, 可不参加 the attending.
_EVENT_STATE_OBJECT=r'取消|暂停|停办|推迟|延期|改期|改为|改到|改至|可以?不|不必|无需|无须|不用|不需要?|不要求|不强制'
# Of those, one whose object is what it acts on (取消安全讲座), not the new value it gives (改为安全讲座).
_EVENT_STATE_ON=r'(?:(?!改为|改到|改至)(?:'+_EVENT_STATE_OBJECT+r'))'
# Another object's own noun. A Chinese name ends in its noun, so it is the last word before the state or the clause end.
_EVENT_OBJECT_NOUN=r'回执|资料|材料|座位|车位|表|单|册|书|证|卡|票|物品|用品'
# Words that open a clause around a name rather than sit inside it: a cause or agent (因单位安排、由…), a place or
# time preposition, a conjunction joining another predicate (并退费), an adverb or a negation.
_EVENT_CLAUSE_WORD=r'因|由|被|把|将|于|在|从|据|经|并|且|而|已|未|没|仍|还|再|又|均|都|也|不|无|非'
# The only words that make the event's words a modifier of another object: what follows them is that object's
# complete name ending in its own noun (家长会回执、会议资料、家长会安排表), then only how that object stands
# (家长会回执已经取消). A noun inside a cause or another word (因单位安排、因书面通知、因书面材料), or any other words
# between them and the state (原本已经、因故、已), leaves the state on the event itself, so a relation that cannot be
# read from the original stays unconfirmed.
_EVENT_OTHER_OBJECT=(r'的?(?:(?!'+_EVENT_STATE+r'|'+_DAY_WORDS+r'|'+_EVENT_CLAUSE_WORD+r')[^，,])*?(?:'+_EVENT_OBJECT_NOUN+r')'
                     r'(?:'+_EVENT_STATE+r'|已|均|都|也|亦|一律|全部|暂时?)*')
# What can report an event: a document or material carrying its content, never a seat, a ticket or a book.
_EVENT_DOCUMENT=r'资料|材料|回执|通知书?|告知书|告家长书|倡议书|说明书|公告|文件|简报|来函|海报|消息|邮件|表格|清单|手册'
# A day labelling an edition (2026年10月10日版), or one whose 的 phrase names a document that reports the event before it
# is held (10月10日的家长会资料说明家长会将…举行), dates that edition or document, not when the event is held. The
# reporting word must be the predicate of that complete document name, followed by a complete reported clause: the
# holding itself or a nameable event of its own before it. A reporting word inside the held event's own name, after
# anything but a document (2026年10月18日的学校说明会、学校科创成果介绍交流会在报告厅举行), leaves the day on that event.
_EVENT_OTHER_DAY=(r'(?:'+_EVENT_DAY+r')\s*(?:[（(][^）)]*[）)])?\s*版(?!画)'
                  r'|(?:'+_EVENT_DAY+r')\s*的(?:(?!'+_EVENT_DAY+r'|[将定拟于在]|举行|召开|举办)[^，,])*?(?:'+_EVENT_DOCUMENT+r')'
                  r'(?:说明|显示|表示|指出|提到|写明|写道|告知|介绍|载明|注明)'
                  r'(?:(?:(?!'+_EVENT_DAY+r'|[将定拟于在]|举行|召开|举办)[^，,]){2,})?(?:[将定拟于在]|举行|召开|举办)')


def _event_names(event):
    """The held event's own names in its clause: the words before its day or place (家长会定于… → 家长会) and after 举行."""
    cut=r'(?:'+_EVENT_DAY+r')|[\d\s：:（）()]|(?:定|将|拟|计划|安排|暂定|初定|原定)?(?:于|在)|暂定|初定|原定|举行|召开|举办|不是|并非|不'
    return [p for p in re.split(cut,event) if len(p)>=2][:1]+re.findall(r'(?:举行|召开|举办)([^\d\s：:（）()]{2,})',event)


def _event_mention(event):
    """What still means this held event in another clause: its own name (家长会定于… → 家长会), attending or holding it, or its time."""
    own=sorted({name[i:] for name in _event_names(event) for i in range(len(name)-1)},key=len,reverse=True)
    return '|'.join([re.escape(x) for x in own]+[r'参加|出席|到场|参会|举行|召开|举办|活动|会议|^的?(?:时间|日期)|(?:具体|准确|确切|详细)的?(?:时间|日期)'])


# A word pointing back at what the notice already named (该、本次、上述).
_EVENT_POINTER=r'(?:该|此|本|这|上述|以上)(?:次|项|场|个)?'
# One negation word right before a predicate or another negation (不取消、并未延期、没有被取消、无需取消、不能不取消).
_EVENT_NEGATION=r'(?:不必|无需|无须|不用|不需要?|不得|不能|不会|不再|无法|没有?|不是|并非|不|未)被?'


def _negated(before):
    """Whether the negations right before a predicate state its opposite. They are read together as one chain, each negating
    what follows it: one states the opposite (不取消、不能取消、无需取消), a second restores the predicate (不得不取消、不能不取消、
    并非不取消), and so on by their count. A negation still left just before the chain (未必不取消、不可能不取消) makes the
    chain unreadable, so the predicate is never read as negated and its event stays unconfirmed."""
    count=0
    while True:
        m=re.search(_EVENT_NEGATION+r'$',before)
        if not m:break
        count+=1;before=before[:m.start()]
    return count%2==1 and not re.search(r'(?:不|没|未|无|非|别|莫|勿)\S{0,2}$',before)
# Where a whole name ends: the words after it open a predicate, a clause, a day or a joined name (安全讲座取消、安全讲座因故
#延期、安全讲座和运动会取消), or name its time. Any other word goes on naming a longer object it only heads (安全讲座筹备会议).
_EVENT_NAME_END=(r'(?!(?!'+_EVENT_STATE+r'|'+_EVENT_CLAUSE_WORD+r'|'+_DAY_WORDS+r'|[和与及或跟同等了]|的?(?:时间|日期))'
                 r'[^\s，,、；;：:。！!？?])')


def _event_named(event,whole=False):
    """What names this held event itself outside its own sentence or in an item's title: its name or a tail of at least three of
    its words (学校开放日 → 开放日), or a word pointing back at it (该活动、本次会议). Attending, a time, or 活动 ending another
    name (开放日活动取消) can belong to another action or event there, so they never stand for this one.

    In another sentence of the notice (whole) a shortened tail is the event only as a whole object, where its words begin,
    right after a pointer back, or right after a state predicate taking it as its object (开放日取消、该开放日延期、取消安全讲座);
    words before it make it the tail of another complete name, so 道路安全讲座取消 and 取消道路安全讲座 never cancel
    校园安全讲座. The whole object also ends with the tail: name words after it make the tail the head of another complete
    object, so 取消安全讲座筹备会议 and 安全讲座筹备会议取消 keep 校园安全讲座 as they keep it from 取消安全讲座回执. Its full
    name stays the event wherever it stands (现通知该学校开放日取消)."""
    names=set(_event_names(event))
    own=sorted({name[i:] for name in names for i in range(len(name)-min(3,len(name))+1)},key=len,reverse=True)
    lead=r'(?:^\s*|'+_EVENT_POINTER+'|'+_EVENT_STATE_ON+r'\s*)' if whole else ''
    end=_EVENT_NAME_END if whole else ''
    return '|'.join([re.escape(x) if x in names else lead+re.escape(x)+end for x in own]+[_EVENT_POINTER+r'(?:活动|会议)'])


def _modifies_event(part,mention):
    """A state word modifies the event when its own object, else the clause it predicates, still means the event.

    参加由家长自愿决定、本次家长会已取消、家长会原本已经取消 are about the event; 取消打印材料、座位可选、无需带材料 are
    about another object; a clause holding nothing but the state (不作统一要求) can only be about the event. The event's
    words only modify another object when the words from them to the state (or to the clause's end) complete that object's
    own name, so 家长会回执可选、家长会回执取消、家长会安排表可选 keep the meeting while 家长会安排可选、家长会因单位安排取消
    do not. What follows a state is its object only when it names one (取消打印材料、取消家长会、可不参加); a joined
    predicate or a complement (本次家长会取消并退费、延期至下周、取消了) leaves the state on the subject before it.
    Before or after its subject or object, a negated predicate (不取消安全讲座、家长会并未延期、安全讲座不能取消) states the
    opposite, and a state whose object is another predicate (无需取消、可以不改期) only sets that predicate's polarity, so
    neither is a state; a negated negation (不能不取消安全讲座、安全讲座不得不取消) is the state again.
    """
    for m in re.finditer(_EVENT_STATE,part):
        before=re.sub(r'[\s、：:]','',part[:m.start()]);after=re.sub(r'[\s、：:]','',part[m.end():])
        if _negated(before) or (re.fullmatch(_EVENT_STATE_OBJECT,m[0]) and re.match(_EVENT_STATE_OBJECT,after)):continue
        if re.fullmatch(_EVENT_STATE_OBJECT,m[0]) and (re.search(mention,after) or re.fullmatch(r'了?(?:'+_EVENT_OTHER_OBJECT+r')',after)):before=''
        if not before+after:return True
        if any(not re.fullmatch(_EVENT_OTHER_OBJECT,side[x.end():]) for side in (before,after) for x in re.finditer(mention,side)):return True
    return False


def event_days(text,published):
    """The arranged day of a held school event the family is directly asked to attend (家长会定于10月15日举行，请家长参加).

    It is that item's own arranged day, not a completion deadline. One sentence states one grounded day, one clause
    holding the event and a direct request to attend (明日 grounds on the sending day; 务必/须参加 is as direct as
    请参加); ！？ end a sentence, so a notice's own date never reaches a later event. A negation, state or option counts
    on what it modifies: the event's own clause (不是10月15日举行、暂定、原定…取消、按10月9日通知), the request (自愿参加)
    or another clause whose state's object or subject is still the event (本次家长会已取消、参加由家长自愿决定、准确时间后续告知)
    or which states nothing else (不作统一要求). 座位可选、取消打印材料、无需带材料、家长会回执可选 keep the meeting; a past day
    stays out, and so does a day that dates an edition or a material reporting the event (2026年10月10日版的家长会资料说明…举行).
    A later sentence of the same original still states the event's own state when it names the event itself or points back at
    it (现通知该家长会取消、本次活动因故取消); cancelling another event (运动会取消、开放日活动取消) or another object of it
    (家长会回执取消) does not.
    """
    return {value for value,_ in _held_events(text,published)}


def _held_events(text,published):
    """Each arranged day event_days keeps, with the clause holding its event."""
    anchor=date(published)
    text=_relative_weekday(_grounded_text(text,anchor),anchor)
    relative={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}
    found=[];sentences=re.split(r'[。；;！!？?\n]',text)
    for at,sentence in enumerate(sentences):
        values={date(d) or (anchor and d in relative and (dt.date.fromisoformat(anchor)+dt.timedelta(days=relative[d])).isoformat()) or '' for d in re.findall(_DAY_WORDS,sentence)}
        clauses=[c for c in re.split(r'[，,]',sentence) if c.strip()]
        # A long place or gathering note between the day and 举行 is still the same clause; another day is not.
        held=[n for n,c in enumerate(clauses) if re.search(r'(?:'+_EVENT_DAY+r')(?:(?!'+_EVENT_DAY+r').)*?(?:举行|召开|举办)',c)]
        if len(values)!=1 or '' in values or len(held)!=1 or not re.search(_ATTEND_REQUEST,sentence):continue
        value=next(iter(values));event=clauses[held[0]]
        if (anchor and value<anchor or re.search(_EVENT_STATE,event) or re.search(_EVENT_OTHER_DAY,event)
                or re.search(r'(?:不是|并非|而非|并不在|不在|不于|不会在)\s*(?:于|在)?\s*(?:'+_EVENT_DAY+r')|(?:不|未|没有?|无法|不能|不会|不再)\s*(?:如期|按时|正常)?\s*(?:举行|召开|举办)',event)
                or re.search(r'(?:根据|依据|按照|参照|参见|据|按|见|同)\s*(?:'+_EVENT_DAY+r')|(?:'+_EVENT_DAY+r')[^，,]{0,6}?(?:通知|公告|文件|来函|消息|发布|发出)',event)):continue
        mention=_event_mention(event)
        if any(_modifies_event(part,mention) for n,c in enumerate(clauses) if n!=held[0] for part in re.split(r'、|(?<!\d)[：:]|[：:](?!\d)',c)):continue
        # A sentence end does not end the same notice: a later part naming the event itself, as a whole object, is read by the same rule.
        named=_event_named(event,True)
        if any(re.search(named,part) and _modifies_event(part,named) for later in sentences[at+1:]
               for c in re.split(r'[，,]',later) for part in re.split(r'、|(?<!\d)[：:]|[：:](?!\d)',c)):continue
        found.append((value,event))
    return found


# Who attends and how, before an item's own predicate of attending (请家长准时参加、按时出席、到场参加).
_ATTEND_TITLE=r'(?:请|务必|必须|须|需)?(?:各位|全体)?(?:家长|学生|同学们?|孩子们?)?(?:准时|按时|届时|务必|必须|须|需)?(?:参加|出席|到场|参会)+'


def _attends(title,event):
    """True when an item's title is attending this held event itself, so the event's arranged day is its own action's day.

    Its own predicate attends the event and comes first, taking the event as its object, with any joined predicate after it
    (参加家长会、准时参加学校开放日、按时出席家长会并签到); or the title is the event's name, alone or followed only by
    attending it (学校开放日、家长会，请准时参加). Another predicate before the name (确认是否参加学校开放日、报名参加) or
    after it (学校开放日，确认是否参加) is the item's own action, and words after the name other than a joined predicate make
    it a modifier of another object (寄出家长会回执原件). A colon ends a label, so attending never reaches across it to the
    name (参加意向确认：学校开放日 labels the open day with another action).
    """
    words=re.sub(r'[（(][^）)]*[）)]|\s','',re.sub(r'^\s*待核对[：:]?','',title or ''))
    name=r'(?:'+_event_named(event)+r')';joined=r'(?:(?:[，,、；;。！!？?]|并|且|然后|同时|再).*)?'
    return bool(re.fullmatch(_ATTEND_TITLE+r'[^，,、；;。！!？?：:]*?'+name+joined+r'|'+name+r'(?:[，,、；;：:]*'+_ATTEND_TITLE+joined+r')?',words))


def date_meaning(quote,due,published,title='',goal=''):
    """'event' when due is the arranged day of the held event this item's own action attends.

    The same day can also be a sibling action's deadline in that notice (2026年10月18日前寄出家长会回执); it stays that
    action's. The item's own action decides: the quoted clauses its goal restates (family_agent._school_own_words) mean an
    event unless they tie the day to an action of their own (请家长2026年10月22日前确认是否参加学校开放日), however the title
    is shown (参加意向确认：学校开放日、落实家长会参会安排). Unplaced, its title's own predicate decides, not an event name
    its title ends with or holds: only a title whose own
    predicate attends the event (参加家长会、准时参加学校开放日、按时出席家长会并签到) or which is the event's name itself
    keeps the arranged day. A Chinese object ends in its own noun, so words after the event's name other than a joined
    predicate (并签到) make it a modifier of another object (寄出家长会回执原件); and a title whose own predicate comes first
    and takes attending or the event as its object (确认是否参加学校开放日、报名参加、回复是否参加) acts on that day as a
    deadline, as does one naming the event before another predicate (学校开放日，确认是否参加) or not naming it.
    """
    if not date(due):return ''
    held=[event for value,event in _held_events(quote,published) if value==due]
    if not held:return 'deadline'
    if due not in _action_deadlines(quote,published):return 'event'
    words,placed=family_agent._school_own_words(quote,0,len(quote.rstrip('。；;！!？? \n')),title,goal)
    if placed:return 'deadline' if any(due in _action_deadlines(own,published) for s,own in words) else 'event'
    return 'event' if any(_attends(title,event) for event in held) else 'deadline'


def later_dropped_days(quote,text,published,own=None,title=''):
    """Event days quote holds on its own that its original text, read from quote to the end, no longer holds.

    A model may quote only 家长会定于2026年10月18日在体育馆举行，请家长参加。 while the same notice goes on 现通知该家长会取消。;
    that later state still binds the meeting the quote holds. Cancelling another event or another object of it (运动会取消、
    家长会回执取消) keeps the day. Only a day the item's own words (own, else quote) tie to an action of its own stays that
    action's: a sibling's same-day deadline in the quoted sentence (并请家长2026年10月18日前寄出退款回执原件) is not the
    meeting item's, and an item whose title attends the event (参加家长会) has no other action of its own on that day.
    """
    kept=set(_held_events(text,published));mine=_action_deadlines(quote if own is None else own,published)
    return {value for value,event in _held_events(quote,published) if (value,event) not in kept and (value not in mine or _attends(title,event))}


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


def metadata(app,c,child_id,title,due,refs=(),focus=None,purpose=None,*,publication_ref='',date_quote='',goal=''):
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
    # Only words found in this child's own originals of this item can tell what its day means.
    if date_quote and not any(date_quote in m.get('text','') for m in messages):date_quote=''
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
    # A school item's day not saved with it is its own only by the same shared placement its proposal passed: a sibling's
    # same-day deadline (另请家长…前参加科技讲座筹备会议) never dates an item whose own event the notice later cancels.
    if (not organized and date_quote and due_on and due_on!=date(due) and family_agent._school_borrowed_day(
            date_quote,[dict(text=m.get('text',''),time=m.get('time','')) for m in messages],due_on,goal,subject)):due_on=''
    category=focus.get('category','')
    if category not in ('homework','todo'):category='todo' if category=='unknown' else task_category(title,purpose)
    # Later supplements retain their own source entries, not the first notice's time.
    published_at=original_time if original_time and original_time[:10]==published else min((value for value in times if value[:10]==published),default='')
    # The same day reads as the meeting's arranged day or a hand-in deadline by the action the item itself names.
    # Saving the task records its original day in the focus too; a different (parent-edited) date keeps the deadline contract.
    original=date(due) if date_quote else ''
    sent=original_time[:10] if original_time else days[0] if len(days)==1 else ''
    due_kind=date_meaning(date_quote,due_on,sent,subject,goal) if original and due_on==original else 'deadline' if due_on else ''
    return dict(category=category,published_on=published,published_at=published_at,publications=publications,due_on=due_on,due_kind=due_kind,scheduled_on=focus.get('scheduled_on',''),
                category_confirmed=focus.get('category') in ('homework','todo'),publication_known=bool(published),box=focus.get('box') or 'inbox')


def _stored_date_quote(plan):
    """An item's own stored original words; its rewritten short title (参加家长会) states no day or request."""
    anchors=list((plan.get('school_action_anchor') or {}).values())[:1]
    return next((v.strip() for v in (plan.get('school_date_quote'),(plan.get('school_native_action') or {}).get('quote'),*anchors)
                 if isinstance(v,str) and v.strip()),'')


def enrich(app,c,tasks):
    owners={p['name']:p['id'] for p in app.profiles(c)}
    reported={r['task_id']:r['day'] for r in c.execute('SELECT task_id,day FROM study_items WHERE id=task_id')} if c.execute("SELECT 1 FROM sqlite_master WHERE name='study_items'").fetchone() else {}
    for task in tasks:
        refs=[x.strip() for x in task['source'].splitlines() if x.strip().startswith('message:')]
        focus=task.get('focus') or {}
        purpose=None;publication_ref='';date_quote='';goal=''
        if task.get('school_origin'):
            origin=task['source'].splitlines()[0].removeprefix('Agent建议:')
            proposal=c.execute("SELECT * FROM agent_items WHERE id=? AND task_id=? AND child_id=? AND kind='school' AND state='accepted'",
                               (origin,task['id'],owners.get(task['child'],''))).fetchone()
            if proposal:
                plan=json.loads(proposal['plan'])
                purpose=plan.get('school_task',{}).get('purpose');goal=str(plan.get('school_task',{}).get('goal') or '')
                store=family_agent.Store(app.connect,app.profiles,app.DATA,initialize=False)
                publication_ref=family_agent.school_original_publication_ref(store,c,proposal)
                date_quote=_stored_date_quote(plan) or re.sub(r'^待核对[：:]?\s*','',proposal['title']).strip()
        due=task['due']
        if task['id'] in reported and task['source'] in ('家庭放学后录入','孩子自述功课，待家长核对'):
            # The capture day is a plan date, not a teacher deadline; preserve explicit later edits.
            focus=dict(focus)
            if not focus.get('category'):focus['category']='homework'
            if not focus.get('scheduled_on') and not focus.get('version'):focus['scheduled_on']=reported[task['id']]
            due=task['due']=''
        task['agenda']=metadata(app,c,owners.get(task['child'],''),task.get('original_title',task['title']),due,refs,focus,purpose,publication_ref=publication_ref,date_quote=date_quote,goal=goal)
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
            store=family_agent.Store(app.connect,app.profiles,app.DATA,initialize=False)
            for row in c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='pending' ORDER BY created DESC,id DESC"):
                plan=json.loads(row['plan']);brief=plan.get('school_task',{})
                if row['child_id'] not in ids or brief.get('state')=='reference':continue
                refs=[e['ref'] for e in json.loads(row['evidence'])]
                purpose=brief.get('purpose')
                category=task_category((brief.get('title') or row['title']) if purpose in family_agent.PURPOSES else row['title'],purpose)
                # A candidate reads its day from the same stored original words and publication as its accepted item.
                m=metadata(app,c,row['child_id'],row['title'],row['due'],refs,publication_ref=family_agent.school_original_publication_ref(store,c,row),
                           date_quote=_stored_date_quote(plan),goal=str(brief.get('goal') or ''))
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
