"""Calendar views of existing tasks, school inbox and study sessions; no copied tasks."""
import datetime as dt
import functools
import json
import re
import family_agent
import family_calendar
import family_study


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


def _in_title(text,index):
    """A 《》 title is an object's name, not a sentence: a day or verb written inside it is not one the text states."""
    return text.count('《',0,index)>text.count('》',0,index)


def _titles_read_as_objects(text):
    """The text as its actions are read: each 《》 title's own words are blanked to the same length, keeping its
    clause marks, so a title can neither give a day or verb of its own nor hide the real one written after it."""
    out=[];opened=closed=0
    for ch in text:
        out.append('_' if opened>closed and ch not in '《》。；;，,\n' else ch)
        opened+=ch=='《';closed+=ch=='》'
    return ''.join(out)


# The direct negation of the predicate that follows it (不、不用、无需再…); 不晚于/不迟于/不超过 bound a day instead, and
# 别 ending another word (分别、特别、区别) negates nothing.
_NEGATED_LEAD=(r'(?:不(?!晚于|迟于|超过)|没有?|未|无需|无须|免|(?<![分区特告个差识辨离派级类性])别|勿)'
               r'(?:用|必|需要?|要求?|得)?\s*(?:再|额外|另行)?\s*')


def _action_deadlines(text,published):
    """Every date the text ties to a required action, grounded on the sending day."""
    anchor=date(published)
    text=_grounded_text(text,anchor)
    if date(text): return {text}
    text=_relative_weekday(text,anchor)
    candidates=set()
    # 把 right after the day names the object its own verb acts on. A complete name ending in its own noun
    # (把校内参观活动回执签字交回) is one object however long, so only that noun counts toward the window below; a
    # state, another day or a clause word inside the name (把已取消的活动回执), or a day that is itself written inside a
    # 《》 title (资料标题为《明天把…回执交回指南》), leaves the text as it was.
    text=re.sub(r'((?:\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)(?:(?:由家长|家长|孩子|学生|请)[ \t]*){0,2}把)'
                r'(?:(?!'+_EVENT_STATE+r'|'+_DAY_WORDS+r'|'+_EVENT_CLAUSE_WORD+r')[一-鿿A-Za-z0-9])*?'
                r'('+_EVENT_OBJECT_NOUN+r')(?=签字|盖章|交|带|上交|提交)',lambda m:m[0] if _in_title(m.string,m.start()) else m[1]+m[2],text or '')
    action=r'(?:前|截止|完成|订正|提交|上交|交齐|带到|带来|交作业|朗读|背诵|抄写|预习|听[^。；;，,\n]{0,12}录音|带|穿|交(?!流|通|换|谈)|测验|考试|听写|默写|检测)'
    # A 《》 title ends at its own closing bracket, and a page/lesson number ends a plain book name the same way, so
    # 把《图形与证明综合练习》的第4页完成, 把《单位换算强化训练》练习第2页订正 or 把数学练习册第4页完成 is likewise one object
    # for the same action list below; a state or another day inside it, a clause word in the plain name, or anything
    # else before the action leaves the text as it was.
    locator=r'(?:[、和]?的?第?[0-9一二三四五六七八九十百]+(?:[-–~～至到]第?[0-9一二三四五六七八九十百]+)?(?:页|题|课|单元|章|节))'
    plain=r'(?:(?!'+_EVENT_STATE+r'|'+_DAY_WORDS+r'|'+_EVENT_CLAUSE_WORD+r')[一-鿿A-Za-z])'
    text=re.sub(r'((?:\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)(?:(?:由家长|家长|孩子|学生|请)[ \t]*){0,2}把)'
                r'(?:《(?:(?!'+_EVENT_STATE+r'|'+_DAY_WORDS+r')[^《》。；;，,\n])+》(?:'+plain+r'*?'+locator+r'+)?'
                r'|'+plain+r'+?'+locator+r'+)'
                r'(?='+action+r')',lambda m:m[0] if _in_title(m.string,m.start()) else m[1]+'《》',text)
    text=_titles_read_as_objects(text)
    # A date alone is not a deadline; it must be tied to an explicit action or dated school event.
    pattern=r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)([^。；;，,\n]{0,8}?)'+action
    for match in re.finditer(pattern,text or ''):
        # A direct negation right before the action (今晚不交纸质作业、明天不用带) ties the day to no action of its own.
        if re.search(_NEGATED_LEAD+r'$',match[2]):continue
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
    # A day directly heading one of the child's own learning activities, after at most its asker and subject (今晚跟读Unit 5、
    # 语文今晚阅读《晨星故事》、数学今晚口算第1题、英语明天跟读、今晚读《长叶读本》), ties it just as 今晚复习 does: the native
    # reader's activities and the completion verbs, no list of its own. A report or question after the verb (读了、读过的、
    # 跟读吗), a negation or condition (not an asker word), or a question or condition in its clause states no requirement.
    learning=r'(?:'+family_agent._SCHOOL_LEARNING_ACTS+'|'+_COMPLETION_VERB+r')(?![了过的着吗册本卷]|资料|材料|计划|安排|通知|要求|时间|指南|方法|建议|结果|情况)'
    for match in re.finditer(r'(今天|今日|今晚|明天|明日|后天)'+direct_prefix+learning,text):
        clause=re.split(r'[。；;，,\n]',text[:match.start()])[-1]+re.split(r'[。；;，,\n]',text[match.start():])[0]
        if re.search(r'吗|[？?]|如果|假如|若是|要是|是否',clause):continue
        offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[match[1]]
        if not anchor:continue
        try:candidates.add((dt.date.fromisoformat(anchor)+dt.timedelta(days=offset)).isoformat())
        except OverflowError:pass
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
    # A dated pickup the family is asked to do: when and where (放学、东门) stand between the day and 接孩子, past the
    # tight window above. It stays inside its clause; another day or a negation (不用接) before it leaves the day unread.
    pickup=r'(?:(?!\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天|不|无|勿|别|免|未|没)[^。；;，,\n]){0,16}?接\s*(?:'+_PARTICIPANTS['学生']+r')'
    exam_event=r'单元测|体育测试|小测|月考|期中|期末|测验|考试|统考|联考|水平测|质检|摸底'
    for match in re.finditer(r'(\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天)(?:'+span+r'(?:'+exam_event+r')|'+pickup+r')',text or ''):
        token=match[1];value=date(token)
        if not value and published and token in ('今天','今日','今晚','明天','明日','后天'):
            offset={'今天':0,'今日':0,'今晚':0,'明天':1,'明日':1,'后天':2}[token]
            try:value=(dt.date.fromisoformat(published)+dt.timedelta(days=offset)).isoformat()
            except OverflowError:pass
        if value:candidates.add(value)
    return candidates


_EVENT_DAY=r'\d{4}-\d{2}-\d{2}|今天|今日|今晚|明天|明日|后天'
_DAY_WORDS=r'\d{4}-\d{2}-\d{2}|\d{1,2}\s*月\s*\d{1,2}|今天|今日|今晚|明天|明日|明早|明晚|后天|昨天|前天|(?:周|星期|礼拜)[一二三四五六日天]'
# Who is asked to attend: everyone, a counted few (一位家长、两名学生) or a named group.
_ATTENDEE=r'(?:各位|全体|(?:至少)?[一二两1-2]\s*(?:位|名))?(?:家长|学生|同学们?|孩子们?)?'
_ATTEND_REQUEST=r'(?:请|务必|必须|须|需|每(?:家|户))'+_ATTENDEE+r'(?:准时|按时|届时|务必|必须|须|需)?(?:参加|出席|到场|参会)(?!安排|通知|方式|时间|人员|名单)'
# Excusing someone from attending or coming (孩子不用来、可不参加).
_EXCUSE=r'(?:可以?不|不必|无需|无须|不用|不需要?)\s*(?:参加|出席|到场|参会|来|到校)'
# The two kinds of participant a notice asks or excuses (家长 / 孩子、学生).
_PARTICIPANTS={'家长':r'家长|父母|爸爸|妈妈','学生':r'孩子们?|学生|同学们?|小朋友'}
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


def _excused_others(sentence):
    """The clauses that only excuse the other kind of participant than the one the sentence asks to attend.

    请一位家长参加，孩子不用参加 still asks a parent to attend: 孩子不用参加 neither cancels the meeting nor makes the parent's
    attending optional. A request naming no participant, or an excuse of the same one (请家长参加，家长不用参加), stays a state.
    """
    asked=re.search(_ATTEND_REQUEST,sentence)
    kinds=[words for words in _PARTICIPANTS.values() if asked and re.search(words,asked[0])]
    if len(kinds)!=1:return set()
    other=next(words for words in _PARTICIPANTS.values() if words!=kinds[0])
    return {c.strip() for c in re.split(r'[，,]',sentence) if re.fullmatch(r'\s*(?:'+other+r')\s*'+_EXCUSE+r'\s*',c)}


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
        # The event is held on its day (…举行/召开), or its day is fixed (家长会定在10月24日14:20).
        held=[n for n,c in enumerate(clauses) if re.search(r'(?:'+_EVENT_DAY+r')(?:(?!'+_EVENT_DAY+r').)*?(?:举行|召开|举办)'
                                                           r'|^\s*[^，,]{2,12}?(?:定在|定于)\s*(?:'+_EVENT_DAY+r')',c)]
        # Who attends may be asked in the very next sentence when it names no day (…学校报告厅。每家一位家长参加，孩子不用来。).
        following=sentences[at+1] if at+1<len(sentences) else ''
        if (not re.search(_ATTEND_REQUEST,sentence) and re.search(_ATTEND_REQUEST,following) and not re.search(_DAY_WORDS,following)
                and len(held)==1
                # …unless it names another event (讲座定在…。另一个家长会每家一位家长参加): that attending is not this event's.
                and not re.search(r'(?<!参)会|讲座|活动|典礼|仪式|比赛|开放日',re.sub('|'.join(map(re.escape,_event_names(clauses[held[0]]))) or '$^','',following))):
            sentence=sentence+'，'+following;clauses=clauses+[c for c in re.split(r'[，,]',following) if c.strip()]
        if len(values)!=1 or '' in values or len(held)!=1 or not re.search(_ATTEND_REQUEST,sentence):continue
        value=next(iter(values));event=clauses[held[0]]
        if (anchor and value<anchor or re.search(_EVENT_STATE,event) or re.search(_EVENT_OTHER_DAY,event)
                or re.search(r'(?:不是|并非|而非|并不在|不在|不于|不会在)\s*(?:于|在)?\s*(?:'+_EVENT_DAY+r')|(?:不|未|没有?|无法|不能|不会|不再)\s*(?:如期|按时|正常)?\s*(?:举行|召开|举办)',event)
                or re.search(r'(?:根据|依据|按照|参照|参见|据|按|见|同)\s*(?:'+_EVENT_DAY+r')|(?:'+_EVENT_DAY+r')[^，,]{0,6}?(?:通知|公告|文件|来函|消息|发布|发出)',event)):continue
        mention=_event_mention(event);excused=_excused_others(sentence)
        # Excusing the asked attendee, or anyone unnamed, from coming leaves the event unconfirmed (家长不用来).
        if any(re.search(_EXCUSE,c) and c.strip() not in excused for n,c in enumerate(clauses) if n!=held[0]):continue
        if any(_modifies_event(part,mention) for n,c in enumerate(clauses) if n!=held[0] and c.strip() not in excused
               for part in re.split(r'、|(?<!\d)[：:]|[：:](?!\d)',c)):continue
        # A sentence end does not end the same notice: a later part naming the event itself, as a whole object, is read by the same rule.
        named=_event_named(event,True)
        if any(re.search(named,part) and _modifies_event(part,named) for later in sentences[at+1:]
               for c in re.split(r'[，,]',later) for part in re.split(r'、|(?<!\d)[：:]|[：:](?!\d)',c)):continue
        found.append((value,event))
    return found


# Who attends and how, before an item's own predicate of attending (请家长准时参加、按时出席、到场参加).
_ATTEND_TITLE=r'(?:请|务必|必须|须|需)?'+_ATTENDEE+r'(?:准时|按时|届时|务必|必须|须|需)?(?:参加|出席|到场|参会)+'


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


_CARRIED=r'(?:带(?:上|好|齐)?|携带)(?![回到去来领着读])\s*[^\s，,]'
_CARRIED_VERB=r'填|写|做|完成|交|签|订正|背|读|练|准备'
# A name ends in its own object noun, as 把…回执 reads it in _action_deadlines, so a verb's character inside the name (英语练习册、
# 读书记录表、书写练习本) is none of its predicates. One taking its complement (填好、写完、交给), a modal, state, day or clause
# word, or any word after that noun is another predicate; without such a noun ending the name, the verb's character stays one.
_CARRIED_NAME=(r'(?:(?!'+_EVENT_STATE+r'|'+_DAY_WORDS+r'|'+_EVENT_CLAUSE_WORD+r'|要|需|须|请|应|(?:'+_CARRIED_VERB+r')(?:好|完|进|入|到|给|回|在|上|齐|成|了|过|着))'
               r'[^\s，,])*?(?:'+_EVENT_OBJECT_NOUN+r'|'+family_agent._SCHOOL_NATIVE_WORKSHEET+r')')
# The same carrying with the lesson named first (T06: 附件是明天带去课堂的实验观察表): a thing of its own after 的, no other predicate.
_CARRIED_TO=(r'(?:(?:附件|这份?|此表)(?:是|为)\s*)?(?:'+family_agent._SCHOOL_NATIVE_DATE+r'|明早)\s*(?:(?:早上|上午|中午|下午)\s*)?(?:要|需|须|请)?\s*'
             r'带去(?:课堂|教室|学校|[一-鿿]{1,4}课)上?的\s*(?:(?:(?!'+_CARRIED_VERB+r')[^\s，,])+|'+_CARRIED_NAME+r')')


def _day_clauses(quote,due,published):
    """The quote's own clauses naming due for themselves on their sending day, 《》 titles read as objects."""
    return [_titles_read_as_objects(c) for c in re.split(r'[，,。；;！!？?\n]',quote or '') if date(published) and family_agent._school_clause_day(c,published)==due]


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
    if not held:
        # Read by the item's own clauses naming this day and their own predicates (《》 titles are objects): only checking
        # (明天早读检查、明天上课检查) makes it the teacher's check, and only handing it in on that day itself (由孩子明早交给班主任、明天早上
        # 交) makes it the teacher's handback. A day it must come before (于10月22日前交回), a negation ahead of the predicate
        # (不用明天交回), any other or a second role on that day stays the ordinary deadline it was.
        own=_day_clauses(quote,due,published)
        roles=[family_agent._school_clause_roles(c) for c in own]
        if roles and all(r=={'check'} for r in roles):return 'inspection'
        if (roles and all(r=={'handback'} for r in roles) and not any(re.search(r'之前|以前|前',c) for c in own)
                and not any(re.search(r'不|没|无|未|别|勿|免',c[:re.search(r'上交|提交|交',c).start()]) for c in own)):return 'handback'
        # Only carrying a thing of its own on that day, at its lesson or arrival (明天体育课带跳绳), is the day's arrangement:
        # a day it must come before (11月5日前带跳绳), a negation, another predicate (准备好、不用带) or the work itself (明天带来)
        # stays the deadline, and the parent's own plan day is never touched.
        if own and not any(roles) and all(family_agent._school_native_errand(c,()) and re.search(_CARRIED,c) or re.fullmatch(_CARRIED_TO,c.strip())
                                          for c in own):return 'arranged'
        # So is a lesson its own day directly heads (周五课堂用时间轴口头讲述、周五历史课…): what is done there is that lesson's,
        # never a home completion or deadline. A negated clause, a check, test or handing in there (明天英语课听写、周四数学课
        # 交练习册) or another role on that day stays as it was.
        if own and not any(roles) and all(re.search(family_agent._SCHOOL_ROLE_DAY+family_agent._SCHOOL_LESSON_PLACE,c)
                                          and not re.search(family_agent._SCHOOL_ARRANGEMENT+r'|完成|做完|写完|读完|'+family_agent._SCHOOL_SIGN+'|'+_EVENT_STATE_OBJECT,c)
                                          and not family_agent._school_negated_day(c) for c in own):return 'arranged'
        return 'deadline'
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


_COMPLETION_VERB=r'背诵|背熟|抄写|默写|朗读|预习|复习|订正|完成|练习|阅读|读|写|做|背'


def completion_day(quote,header,time,due_on):
    """The day this item's own original words give its work, kept apart from its handback/check day (due_on).

    今天/今日/今晚 counts only when it opens the item's own work clause, after at most its own subject label whether or not
    that label was saved as a heading (英语：今晚把Unit 5词表每个单词抄写两遍，明天交给英语老师), or is its own list heading (今天语文作业：1. 背诵《秋夜》第2自然段，明天早读抽查) while its own words check/hand it back 明天, read on its
    own message's sending day in that message's own written timezone. Otherwise the one day that same first work clause ties
    to its own work by the deadline parse (语文：2026年10月18日20:00前完成…；2026年10月20日早读交回) is its day. A time without
    an offset, a heading item with a later deadline of its own (本周五交), a day inside a 《》 title, a second or handback day
    in the work clause, a negated clause, or only a handback day (口算本第8页全部完成，明天交给课代表) stays unknown; due_on
    is never rewritten.
    """
    stamp=(time or '').strip()
    if not quote or not re.search(r'(?:[+-]\d{2}:?\d{2}|Z)$',stamp):return ''
    try:sent=dt.datetime.fromisoformat(stamp.replace('Z','+00:00')).date()
    except ValueError:return ''
    words=_titles_read_as_objects(quote).strip()
    # The item's own subject label (语文：), its saved heading or the shared subject opening its own words, names it; its
    # work clause starts after it.
    label='|'.join(filter(None,(re.escape((header or '').strip()),family_agent._SCHOOL_NATIVE_SUBJECTS)))
    words=re.sub(r'^(?:'+label+r')\s*[：:]\s*','',words)
    first,_,rest=(re.split(r'([，,。；;\n])',words,maxsplit=1)+['',''])[:3]
    lead=re.match(r'(今天|今日|今晚)',first)
    work=first[lead.end():] if lead else first
    if not re.search(_COMPLETION_VERB,work) or re.search(r'不用|不必|无需|无须|不需要?|不要求',work):return ''
    day=sent.isoformat()
    if lead or (re.fullmatch(r'\s*(?:今天|今日|今晚)的?[^，,。；;\n\d]{0,8}?作业\s*[：:]?\s*',header or '')
                and re.match(r'\s*(?:明天|明日|明早)',rest) and not re.search(_DAY_WORDS,re.sub(r'^\s*(?:明天|明日|明早)','',rest))):
        if re.search(_DAY_WORDS,work):return ''
    else:
        grounded=_relative_weekday(_grounded_text(first,day),day)
        days=_action_deadlines(first,day)
        if len(days)!=1 or len(re.findall(_DAY_WORDS+r'|\d{1,2}\s*[日号]',grounded))!=1 or re.search(r'交|带',work):return ''
        day=next(iter(days))
    return day if not due_on or due_on>day else ''


def completion_words(quote,header,day,action):
    """The own words heading this item's work clause that its day was proven from, when they hold its clock and the saved
    action left them out: 2026年10月18日20:00前 before 完成《秋日观察》第2页 for a goal saved as 完成《秋日观察》第2页，….

    Copied as written from the same first work clause completion_day read, never from a title, another clause (the
    handback's own words), another item or the sending time; a saved action already holding the clock, or not opening
    exactly one line with the same work words, keeps its lines. Display only: nothing is saved or rewritten.
    """
    text=(quote or '').strip();masked=_titles_read_as_objects(text)
    if not day or not text:return None
    label='|'.join(filter(None,(re.escape((header or '').strip()),family_agent._SCHOOL_NATIVE_SUBJECTS)))
    at=(re.match(r'^(?:'+label+r')\s*[：:]\s*',masked) or re.match('',masked)).end()
    first=re.split(r'[，,。；;\n]',masked[at:],maxsplit=1)[0]
    verb=re.search(_COMPLETION_VERB,first)
    clock=verb and re.search(r'\d{1,2}\s*[:：]\s*\d{2}',first[:verb.start()])
    if not clock or '_' in first[:verb.start()]:return None
    lead=text[at:at+verb.start()].strip();work=text[at+verb.start():at+len(first)].strip()
    lines=[x.lstrip() for x in str(action or '').splitlines()]
    if len(work)<4 or clock[0] in str(action or '') or sum(x.startswith(work) for x in lines)!=1:return None
    return dict(lead=lead,work=work)


def deadline(text,published):
    """Only an unambiguous deadline phrase; several different dates need review, and so does a day the clause stating it
    leaves to choose (孩子明早或后天交给班主任, family_agent._SCHOOL_DAY_OR): the parse recognizes only one of its options.
    Another clause's choice (今晚或明晚请家长签字) or one between receivers names no day, so an explicit single day is kept."""
    candidates=deadlines(text,published)
    if len(candidates)!=1:return ''
    value=next(iter(candidates))
    if any(value in deadlines(clause,published) and re.search(family_agent._SCHOOL_DAY_OR,_titles_read_as_objects(clause))
           for clause in re.split(r'[，,。；;！!？?\n]',text or '')):return ''
    return value


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


# Every tracked item is filed under the courses its own words name. The school's native learning subjects come first; the
# other school courses keep their own admin items (体育课带跳绳) without making them learning work. A teacher, class
# representative or other recipient (交给数学课代表、英语老师) only addresses the item and never names its subject.
# The list only recognises a course word where that word ends: 美术史 or 科学馆 is its own noun, never 美术 or 科学, and a
# course the family saved under its own name (美术史) is kept as written instead of being cut to a listed one.
_OTHER_COURSES='道德与法治|体育|美术|音乐|信息科技|劳动|书法'
_LONGER_NOUN='史馆家展会节院系界角团社'
GENERAL='综合'
# Only the item's own non-course matter says it has no subject. An admin or optional purpose, a signing step or a parent's
# to-do category is what the item is for, never proof that it belongs to no course (老师发的卷子上签字 stays 科目待定).
_NO_SUBJECT_RE=re.compile(r'同意书|确认书|回执|报名|缴费|交费|请假|接送|家长会|校外|参观|体检')


@functools.cache
def _subject_patterns():
    # Read on first use: family_agent imports this module before its own subject list exists.
    names=family_agent._SCHOOL_NATIVE_SUBJECTS+'|'+_OTHER_COURSES
    return re.compile('(?:'+names+')(?!['+_LONGER_NOUN+'])'),re.compile('(?:'+names+')(?:课代表|老师|教师|组长)'),re.compile(names)


def named_subjects(text):
    """The subjects an item's own words file it under, in order and without repeats."""
    seen=[];subject,addressee,_=_subject_patterns()
    for m in subject.finditer(addressee.sub('',re.sub(r'^待核对[：:]?\s*','',text or ''))):
        if m[0] not in seen:seen.append(m[0])
    return seen


def saved_subjects(value):
    """Saved course names as written. 道德与法治 or 美术史 stays one course; only a joint 科学与美术 of listed courses splits."""
    whole=_subject_patterns()[2];out=[]
    for part in re.split(r'[·、,，/+＋\s]+',value or ''):
        pieces=re.split(r'[与和及]',part)
        out.extend(pieces if len(pieces)>1 and all(whole.fullmatch(p) for p in pieces) else [part] if part else [])
    return list(dict.fromkeys(out))


def subject_fields(title,quote='',*,saved='',corrected='',no_subject=False):
    """File one item once under its own subjects, never by merging, sibling words or guessing.

    A parent's correction wins and can be cleared to reopen the automatic reading. Then a subject saved with the item
    (the school's learning subject, a child's or parent's capture), then the item's own title, then its own original
    words. A saved learning subject names only the learning outcome: when the item's own title names that subject together
    with other courses, the one joint result keeps all of them on its one card. Without any subject an item is 综合 only
    on positive evidence (its own non-course matter, or a family plan that names no course); everything else is 科目待定."""
    if corrected:
        return dict(subjects=[],subject_state='general',subject_basis='parent') if corrected==GENERAL else \
            dict(subjects=corrected.split('·'),subject_state='known',subject_basis='parent')
    saved=saved_subjects(saved);title=title or ''
    if saved:
        rest=title
        for s in saved:rest=rest.replace(s,'·')
        joint=[s for s in named_subjects(rest) if s not in saved] if all(s in title for s in saved) else []
        return dict(subjects=saved+joint,subject_state='known',subject_basis='saved')
    for subjects in (named_subjects(title),named_subjects(quote)):
        if subjects:return dict(subjects=subjects,subject_state='known',subject_basis='own_words')
    general=no_subject or bool(_NO_SUBJECT_RE.search(title+'\n'+(quote or '')))
    return dict(subjects=[],subject_state='general' if general else 'unknown',subject_basis='')


def metadata(app,c,child_id,title,due,refs=(),focus=None,purpose=None,*,publication_ref='',date_quote='',goal='',date_header='',school_focus=False,date_siblings=None,action='',pending=False):
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
    # A collected school task saved with no day (its reply left the day out) reads the one its own words prove, by the same
    # reading the selection now uses (family_agent._school_own_due); a parent's plan or edit keeps priority, nothing is saved.
    # A pending candidate's stored due is that selection's own verdict (a day it leaves to choose stays open): never re-read.
    own_day=(family_agent._school_own_due(date_quote,[dict(text=m.get('text',''),time=m.get('time','')) for m in messages],date_siblings)
             if not pending and not organized and not due_on and date_quote and date_siblings is not None and not focus.get('scheduled_on')
             and not focus.get('version') else '')
    due_on=due_on or own_day
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
    due_kind=date_meaning(date_quote,due_on,sent,subject,goal) if due_on and due_on in (original,own_day) else 'deadline' if due_on else ''
    # The work's own day is read only from this child's one original holding the item's own words; a parent's explicit
    # plan or edit keeps priority, and the handback due stays as it is. A focus saved only by parent-confirmed school changes
    # of this same item is no parent choice: the own day stays while the confirmed words still give that same day.
    own=[m for m in messages if date_quote and date_quote in m.get('text','')]
    home=sent_day(own[0].get('time','')) if len(own)==1 else ''
    if (due_kind=='deadline' and due_on in (original,own_day) and home and date_siblings is not None
            and not _day_clauses(date_quote,due_on,home)):
        # A quote stopping before its own role sentence (…答案写在练习册上。 before 今晚完成，明天早上交。) names no clause of that day:
        # its role is read from the one own range the due was proven from, the quote's sentence and a directly following sentence
        # of its roles alone (family_agent._school_role_days); a sibling's words, another original or a summary give none.
        ranged=family_agent._school_role_days(date_quote,[dict(text=m.get('text',''),time=m.get('time','')) for m in messages],date_siblings,words=True)
        if ranged and ranged[1]==due_on:due_kind=date_meaning(ranged[2],due_on,home,subject,goal)
    heading=date_header if len(own)==1 and date_header and 0<=own[0]['text'].find(date_header)<own[0]['text'].find(date_quote) else ''
    complete_on=(completion_day(date_quote,heading,own[0].get('time',''),due_on)
                 if len(own)==1 and not focus.get('scheduled_on') and (not focus.get('version') or school_focus) else '')
    if complete_on and focus.get('version') and completion_day(focus.get('goal',''),heading,own[0].get('time',''),due_on)!=complete_on:complete_on=''
    # The clock its own work clause gives that same day (20:00前) belongs to it on every card; the saved action stays.
    words=completion_words(date_quote,heading,complete_on,action) if complete_on else None
    if (not complete_on and len(own)==1 and due_on and date_siblings is not None and not focus.get('scheduled_on') and not focus.get('version')):
        # The same own-role reading the item was selected and saved with (今晚完成，明天早上交 / 今晚请家长签字，明天早上让孩子交给…):
        # its one earlier completion day is listed on that day; its handback/check due stays. Another item's quote or day gives none.
        roles=family_agent._school_role_days(date_quote,[dict(text=m.get('text',''),time=m.get('time','')) for m in messages],date_siblings)
        if roles and roles[1]==due_on and len(roles[0])==1 and next(iter(roles[0]))<due_on:complete_on=next(iter(roles[0]))
    return dict(category=category,published_on=published,published_at=published_at,publications=publications,due_on=due_on,due_kind=due_kind,complete_on=complete_on,scheduled_on=focus.get('scheduled_on',''),
                category_confirmed=focus.get('category') in ('homework','todo'),publication_known=bool(published),box=focus.get('box') or 'inbox',
                **({'complete_words':words} if words else {}))


def _stored_date_quote(plan):
    """An item's own stored original words; its rewritten short title (参加家长会) states no day or request."""
    anchors=list((plan.get('school_action_anchor') or {}).values())[:1]
    # A native outcome kept for review by unread linked material keeps its own verified quote in its cover (read-only here).
    return next((v.strip() for v in (plan.get('school_date_quote'),(plan.get('school_native_action') or {}).get('quote'),
                                     (plan.get('school_native_cover') or {}).get('quote'),*anchors)
                 if isinstance(v,str) and v.strip()),'')


def _stored_date_header(plan,quote):
    """The list heading saved with the same native action whose own words are quote; any other source gives none."""
    native=plan.get('school_native_action') or {}
    return native.get('header','') if isinstance(native,dict) and native.get('quote')==quote and isinstance(native.get('header'),str) else ''


def _school_focus(c,task,proposal,plan):
    """Every saved focus version of this task is a parent-confirmed school change of its own accepted item, none a parent's choice.

    Each version's history row is the save of a change item accepted onto this same task for this item whose receipt records
    that it really wrote the focus (a deduplicated append wrote none, so its key proves nothing), recorded on the item with the
    same written due/title/requirements, and the last saved state is still the task's focus."""
    focus=task.get('focus') or {};version=focus.get('version') or 0
    if not version or not c.execute("SELECT 1 FROM sqlite_master WHERE name='task_focus_history'").fetchone():return False
    rows={}
    for row in c.execute('SELECT request_key,current FROM task_focus_history WHERE task_id=?',(task['id'],)):
        current=json.loads(row['current']);rows[current.get('version')]=(row['request_key'],current)
    events={'school-change-'+family_agent._hash(e['item_id'])[:32]:e for e in plan.get('school_changes',[])
            if isinstance(e,dict) and isinstance(e.get('item_id'),str) and e.get('change') in ('update','append')}
    for number in range(1,version+1):
        key,current=rows.get(number,('',{}));event=events.get(key)
        change=event and c.execute("SELECT plan FROM agent_items WHERE id=? AND kind='school' AND state='accepted' AND task_id=? AND child_id=?",
                                   (event['item_id'],task['id'],proposal['child_id'])).fetchone()
        receipt=json.loads(change['plan']) if change else {};written=receipt.get('school_change_receipt') or {}
        if (receipt.get('school_change_of')!=proposal['id'] or written.get('task_id')!=task['id'] or written.get('deduplicated') is not False
                or (current.get('due_on'),current.get('title'),current.get('goal'))!=(event['due'],event['title'],event.get('applied_goal',event['goal']))):
            return False
    return all(focus.get(k)==value for k,value in rows[version][1].items())


_TITLE_LABEL=re.compile(r'[^：:\s，,。；;、《》()（）]{1,8}[：:]\s*')
_LINE_END='。.；;！!？? '
_PAIRS={'《':'》','“':'”','‘':'’','「':'」','『':'』','（':'）','(':')','【':'】','[':']'}
_SENTENCE_END='。！？'
_STEP_END='；'


def _sentences(line,ends=_SENTENCE_END):
    """A saved line as its own sentences, each ending after a full-width 。！？ (a run of them stays together) outside
    《》, quotes and brackets. A line with an unbalanced pair or an ASCII double quote stays whole; no word is changed."""
    if '"' in line: return [line]
    parts,closing,start=[],[],0
    for i,ch in enumerate(line):
        if ch in _PAIRS: closing.append(_PAIRS[ch])
        elif ch in _PAIRS.values():
            if not closing or closing.pop()!=ch: return [line]
        elif ch in ends and not closing and (i+1==len(line) or line[i+1] not in ends):
            parts.append(line[start:i+1].strip());start=i+1
    if closing: return [line]
    return [x for x in parts+[line[start:].strip()] if x]


def _steps(line):
    """A shown line as the parts its own top-level full-width ； joins, in order, each keeping its ；: the same guard as
    _sentences (never inside 《》, quotes or brackets; an unbalanced pair or an ASCII double quote keeps the line whole), and
    marks alone never make a line. Commas and an ASCII ; never cut. Lines of the same card, never items of their own."""
    steps=[]
    for part in _sentences(line,_STEP_END):
        if steps and not (re.search(r'\w',part) and re.search(r'\w',steps[-1])):steps[-1]+=part
        else:steps.append(part)
    return steps


_THIS_PAGE=r'这一页|这页|本页|该页|此页'


# Before a 这一页 that points back: only its asker and a word back to the same work (请家长听完后在…), no material of its own.
_BACK_TO_SAME_WORK=r'\s*(?:请|让|由)?\s*(?:家长|学生|孩子|同学们?)?\s*(?:[听读看做写]完(?:后|以后|之后)?|完成后)?\s*(?:在|于)?\s*'


def _stated_clauses(text):
    """A line's own clauses as the card reads them; a leading 请 asks nothing more.

    这一页/本页 is the line's one 第N页 only when it stands in the very next clause after nothing but its asker and a word
    back to the same work (…课本第20页的对话朗读三遍；请家长听完后在这一页签字). Another material named before it
    (听写本本页) or taken out in between (取出听写本；…本页) leaves its page unknown, so no clause is read as the same."""
    clauses=[c.strip() for c in re.split(r'[，,；;。！!？?]',text) if c.strip()]
    pages=[(n,m[0]) for n,c in enumerate(clauses) for m in re.finditer(r'第\s*\d+\s*页',c)]
    if len(pages)==1 and pages[0][0]+1<len(clauses):
        n,page=pages[0];back=re.match(_BACK_TO_SAME_WORK+'('+_THIS_PAGE+')',clauses[n+1])
        if back:clauses[n+1]=clauses[n+1][:back.start(1)]+page+clauses[n+1][back.end(1):]
    return {re.sub(r'^请','',c) for c in clauses}


def action_lines(title,action,words=None):
    """The saved action's lines as a card under this title shows them; display only, nothing is saved or rewritten.

    Each saved line reads as its own sentences. Only words the card would repeat are left out: a first sentence that is
    the title's own words (with or without its leading label such as 语文：), else the title's exact label opening it,
    and a 提交要求 line whose words begin with the previous line's last clause, which then reads once in that line.
    Every other word stays, in its saved order; partial overlaps stay. The own completion words (completion_words) the
    item's agenda carries head the one saved line opening with the same work words. Only after every repeat is read
    against whole lines (这一页 needs its line's 第N页) does each shown line read as its own top-level ； parts (_steps)."""
    saved=[x.strip() for x in str(action or '').splitlines()]
    if words:saved=[words['lead']+x if x.startswith(words['work']) else x for x in saved]
    lines=[x for line in saved if line for x in _sentences(line)]
    heading=str(title or '').strip().rstrip(_LINE_END);label=_TITLE_LABEL.match(heading)
    if lines and heading and lines[0].rstrip(_LINE_END) and lines[0].rstrip(_LINE_END) in (heading,heading[label.end():] if label else heading):
        lines=lines[1:]
    elif lines and label:
        own=heading[:label.end()].rstrip()  # the heading already shows this exact label (英语：)
        if lines[0].startswith(own) and lines[0][len(own):].strip():lines[0]=lines[0][len(own):].strip()
    shown=[]
    for line in lines:
        restated=re.fullmatch(r'提交要求[：:]\s*(.+?)[。.；;！!\s]*',line)
        if restated and shown:
            previous=shown[-1].rstrip(_LINE_END);clause=re.split(r'[，,；;]',previous)[-1].strip()
            if clause and restated[1].startswith(clause):
                shown[-1]=previous[:len(previous)-len(clause)]+restated[1]+shown[-1][len(previous):]
                continue
            # Every clause it restates is one the card already shows (家长听完后在第20页签字 for 请家长听完后在这一页签字 of
            # the one 第20页 line): read once. Another page, place, object or any added clause keeps the line.
            if _stated_clauses(restated[1])<=set().union(*map(_stated_clauses,shown)):continue
        shown.append(line)
    return [x for line in shown for x in _steps(line)]


def _cited_by(c):
    """Every live school item's own stored words by the child and original it cites, read once per listing."""
    cited_by={}
    for r in c.execute("SELECT id,child_id,plan,evidence FROM agent_items WHERE kind='school' AND state!='superseded'"):
        for ref in {e.get('ref') for e in json.loads(r['evidence'] or '[]') if isinstance(e,dict)}:
            cited_by.setdefault((r['child_id'],ref),{})[r['id']]=_stored_date_quote(json.loads(r['plan']))
    return cited_by


def _date_siblings(cited_by,row):
    """Every other live item of this child citing one of the same originals: its own words are never this item's role."""
    others={}
    for e in json.loads(row['evidence'] or '[]'):
        if isinstance(e,dict):others.update(cited_by.get((row['child_id'],e.get('ref')),{}))
    others.pop(row['id'],None)
    return list(others.values())


def enrich(app,c,tasks):
    owners={p['name']:p['id'] for p in app.profiles(c)}
    reported={r['task_id']:(r['child_id'],r['day'],r['report'],r['subject']) for r in c.execute('SELECT task_id,child_id,day,report,subject FROM study_items WHERE id=task_id')} if c.execute("SELECT 1 FROM sqlite_master WHERE name='study_items'").fetchone() else {}
    cited_by=None  # read once per enrich, only when a school item needs its siblings
    for task in tasks:
        refs=[x.strip() for x in task['source'].splitlines() if x.strip().startswith('message:')]
        focus=task.get('focus') or {}
        purpose=None;publication_ref='';date_quote='';goal='';date_header='';school_focus=False;date_siblings=None
        subject_title=task.get('original_title',task['title']);own_quote='';saved_subject=''
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
                date_header=_stored_date_header(plan,date_quote)
                # The same saved row, words and subject its pending candidate was filed with.
                subject_title=proposal['title'];own_quote=_stored_date_quote(plan);saved_subject=str((plan.get('school_learning') or {}).get('subject') or '')
                school_focus=_school_focus(c,task,proposal,plan)
                if cited_by is None:cited_by=_cited_by(c)
                date_siblings=_date_siblings(cited_by,proposal)
        due=task['due'];teacher={}
        captured=reported.get(task['id'])
        if captured and captured[0]==owners.get(task['child']) and task['source'] in family_study.CAPTURE_SOURCES:
            # The capture day is a plan date, not a teacher deadline; preserve explicit later edits.
            focus=dict(focus)
            if not focus.get('category'):focus['category']='homework'
            if not focus.get('scheduled_on') and not focus.get('version'):focus['scheduled_on']=captured[1]
            due=task['due']=''
            # Only days the parent or child explicitly entered as the teacher's own are teacher days; a plan never writes them.
            teacher={k:v for k,v in json.loads(captured[2] or '{}').items() if k in family_study.TEACHER_DAYS and v}
            if teacher.get('handback_on'):focus['due_on']=teacher['handback_on']
            saved_subject=captured[3] or ''
        task['agenda']=metadata(app,c,owners.get(task['child'],''),task.get('original_title',task['title']),due,refs,focus,purpose,publication_ref=publication_ref,date_quote=date_quote,goal=goal,date_header=date_header,school_focus=school_focus,date_siblings=date_siblings,action=task.get('action',''))
        if teacher.get('handback_on'):task['agenda']['due_kind']='handback'
        if teacher.get('complete_on'):
            task['agenda']['complete_on']=teacher['complete_on'];task['agenda'].pop('complete_words',None)
        task['agenda'].update(subject_fields(subject_title,own_quote,saved=saved_subject,corrected=(task.get('focus') or {}).get('subject','')))
        # Only a card that leaves repeated words out carries its own lines; every other task keeps its exact shape and
        # its card reads the saved lines as they are.
        lines=action_lines(task['title'],task.get('action',''),task['agenda'].get('complete_words'))
        if lines!=[x.strip() for x in str(task.get('action') or '').splitlines() if x.strip()]:task['action_lines']=lines
    return tasks


def visible_on(item,day):
    m=item['agenda']
    if m.get('box')=='wish': return False
    published=m['published_on'];due=m['due_on'];scheduled=m['scheduled_on'];complete=m.get('complete_on','')
    if published and day<published:return False
    if item['closed']:
        return day in {published,scheduled,due,complete,item.get('closed_on','')}-{''} and (not item.get('closed_on') or day<=item['closed_on'])
    if day==published or day==scheduled or (complete and day==complete):return True
    # An undated item remains in the inbox; a deadline carries forward until a parent closes it.
    # Unknown publication stays unknown, but a known deadline must not hide from today's work.
    # A known teacher complete day with no handback day carries forward the same way; it is never made a handback/due day.
    known=due or complete
    return bool(known and day>=(published or min(known,scheduled or known,dt.datetime.now(family_agent.TZ).date().isoformat())))


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
            store=family_agent.Store(app.connect,app.profiles,app.DATA,initialize=False);cited_by=_cited_by(c)
            for row in c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='pending' ORDER BY created DESC,id DESC"):
                plan=json.loads(row['plan']);brief=plan.get('school_task',{})
                if row['child_id'] not in ids or brief.get('state')=='reference':continue
                refs=[e['ref'] for e in json.loads(row['evidence'])]
                purpose=brief.get('purpose')
                category=task_category((brief.get('title') or row['title']) if purpose in family_agent.PURPOSES else row['title'],purpose)
                # A candidate reads its day from the same stored original words, publication and siblings as its accepted item.
                m=metadata(app,c,row['child_id'],row['title'],row['due'],refs,publication_ref=family_agent.school_original_publication_ref(store,c,row),
                           date_quote=_stored_date_quote(plan),goal=str(brief.get('goal') or ''),date_header=_stored_date_header(plan,_stored_date_quote(plan)),
                           date_siblings=_date_siblings(cited_by,row),pending=True)
                m['category']=category
                m.update(subject_fields(row['title'],_stored_date_quote(plan),saved=str((plan.get('school_learning') or {}).get('subject') or '')))
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
                    items.append(dict(entry,agenda=dict(category='homework',published_on='',due_on='',scheduled_on=row['day'],**subject_fields(row['title'],saved=row['subject'])),
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
                    agenda=dict(category='todo',published_on='',due_on='',scheduled_on=event['day'],**subject_fields(event['title'],no_subject=True)),closed=event['status'] in ('cancelled','completed'),event=event))
    first=dt.date.fromisoformat(start);count=(dt.date.fromisoformat(end)-first).days+1
    agenda=[]
    for offset in range(count):
        day=(first+dt.timedelta(days=offset)).isoformat()
        agenda.extend(dict(item,day=day) for item in items if visible_on(item,day))
    return dict(agenda=agenda,study=study,inbox=items+plans)
