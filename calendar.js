// Calendar dates are date-only values. UTC arithmetic avoids daylight-saving shifts.
const calendarKinds={school:'学校安排',activity:'课外活动',study:'学习安排',family:'家庭时光',other:'其他'};
const calendarStatuses={tentative:'暂定',confirmed:'已确定',cancelled:'已取消',completed:'已完成'};
const calendarState={week:'',day:'',childID:'',visible:false,result:null,range:'',error:'',loading:false,dirty:false,sequence:0,controller:null};
let calendarPending=null,calendarSaving=false,calendarJump=0,calendarDraftContext=null;
let calendarSyncVersion=0,calendarWeekdaysChosen=false;
let occurrenceContext=null,occurrencePending=null,occurrenceSaving=false,occurrenceConflict=false;
function calendarAdd(day,n){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)}
function calendarMonday(day){const n=new Date(day+'T12:00:00Z').getUTCDay();return calendarAdd(day,-((n+6)%7))}
function calendarDays(){return Array.from({length:7},(_,i)=>calendarAdd(calendarState.week,i))}
function calendarNames(ids){return (ids||[]).map(id=>data.children.find(c=>c.id===id)?.name||'档案待核对').join('、')}
function calendarItems(items,day){return items.filter(x=>x.day===day&&(x.child_ids||[x.child_id]).includes(currentChild()?.id))}
function calendarInvalidate(keep=false){calendarState.sequence++;calendarState.controller?.abort();calendarState.loading=false;calendarState.dirty=true;if(!keep){calendarState.result=null;calendarState.range=''}calendarState.error=''}
window.FamilyCalendar={invalidate:calendarInvalidate,hasPending:()=>!!(calendarPending||occurrencePending),openDraft:calendarOpenAssistant,openCitation:calendarOpenCitation,leave(){if(calendarState.visible){calendarJump++;calendarState.visible=false;calendarState.sequence++;calendarState.controller?.abort();calendarState.loading=false}}};
function calendarHomeHTML(){return `<section class="calendar-entry"><span aria-hidden="true">▦</span><div><h2>把一周留给成长</h2><p>上学、探索、一起度过的时间，放在同一张日历里。</p></div><div class="calendar-entry-actions"><button class="primary" data-page="calendar">打开成长日历</button><button data-calendar-weekend-home>看看本周末</button></div></section>`}
function calendarRepeatLabel(e){const mode={none:'',daily:'每天',weekly:'每周',weekends:'周末',monthly:'每月'}[e.repeat]||'';return mode+(e.repeat_days?.length?' '+e.repeat_days.map(d=>e.repeat==='weekly'?'周'+'一二三四五六日'[d-1]:d+'日').join('、'):'')}
function calendarEventHTML(e){
 const t=e.task_id?data.tasks.find(t=>t.id===e.task_id&&e.child_ids.includes(data.children.find(c=>c.name===t.child)?.id)):null;
 return `<article tabindex="-1" data-query-target="calendar:${esc(e.id)}:${esc(e.day)}" class="calendar-event ${e.status==='cancelled'?'calendar-cancelled':''}"><div class="calendar-event-meta"><span>${esc(calendarKinds[e.category]||'安排')}</span><span class="calendar-status calendar-${esc(e.status)}">${esc(calendarStatuses[e.status]||'状态待核对')}</span></div><h3>${esc(e.title)}</h3><p class="calendar-time">${esc(e.day)} · ${e.start_time?esc(e.start_time)+(e.end_time?'–'+esc(e.end_time):''):'时间未填写'}</p><p class="calendar-who">${esc(calendarNames(e.child_ids))}${calendarRepeatLabel(e)?' · '+esc(calendarRepeatLabel(e)):''}</p>${e.location?`<p class="calendar-location">⌖ ${esc(e.location)}</p>`:''}${e.note?`<p class="source calendar-requirements">${esc(e.note)}</p>`:''}${e.source||e.repeat!=='none'?`<details><summary>出处与重复规则</summary>${e.source?`<p class="source">出处：${esc(e.source)}</p>`:''}${e.repeat!=='none'?`<p>起点 ${esc(e.series_day)}${e.until?' · 截至 '+esc(e.until):' · 未设截止'}</p>`:''}</details>`:''}${t?`<p class="calendar-task-status ${taskDismissed(t)?'calendar-family-decision':''}">${taskDismissed(t)?esc(t.child)+'：':'清单：'}${esc(taskStatusLabel(status(t)))}</p>`:''}${e.task_id?`<button class="calendar-card-action" data-calendar-task="${esc(e.task_id)}">核对原事项 →</button>`:''}${e.editable&&!e.occurrence?.series_id&&e.repeat==='none'&&!['cancelled','completed'].includes(e.status)?`<button data-calendar-complete="${esc(e.id)}">确认完成</button>`:''}${e.occurrence?.series_id?`<p class="small muted">${e.occurrence.day!==e.day?'从 '+esc(e.occurrence.day)+' 改期 · ':''}本次记录独立保留</p><button data-calendar-once="${esc(e.id)}" data-occurrence-day="${esc(e.day)}">处理本次</button>`:''}${e.editable&&(!e.occurrence?.series_id||e.repeat!=='none')?`<button class="calendar-card-action" data-calendar-edit="${esc(e.id)}">${e.repeat!=='none'?'编辑重复规则':'编辑安排'}</button>`:''}</article>`;
}
function calendarTimetableHTML(t,options={}){return `<details ${options.open?'open':''} tabindex="-1" data-query-target="timetable:${esc(t.id)}:${esc(t.day)}" class="calendar-timetable"><summary><span>课表 · ${esc(calendarNames([t.child_id]))}</span><small>${t.sessions.length} 个节次</small></summary><p class="small">${esc(t.title)}</p><ol>${t.sessions.map(s=>`<li><span>${esc(s.slot)}</span><strong>${esc(s.title)}</strong></li>`).join('')}</ol>${t.note?`<p class="source small">${esc(t.note)}</p>`:''}${t.source?`<p class="source small">出处：${esc(t.source)}</p>`:''}${(t.uploads||[]).map(id=>`<a href="${endpoint('/upload/')}${encodeURIComponent(id)}" target="_blank" rel="noopener">查看课表原件</a>`).join(' ')}${t.import_id?`<button data-timetable-edit="${esc(t.import_id)}">更正课表</button>`:''}${t.attachment?`<a href="${endpoint('/attachment/')}${encodeURIComponent(t.attachment)}" target="_blank" rel="noopener">查看课表原件 ↗</a>`:''}<p class="small muted">按已提供节次展示，未填写的钟点和单双周仍待核对。</p></details>`}
function agendaDueLabel(m){return m?.due_kind==='event'?'活动日期':m?.due_kind==='handback'?'老师要求交回':m?.due_kind==='inspection'?'老师检查':m?.due_kind==='arranged'?'安排日':'截止'}
// A family entry has no school publication to check, so only a known date is shown; school items keep "待核对".
// noDeadline: the item's saved date words are the stored contract for "none given" (无明确截止), shown on its own line, so there is
// no teacher day left to check. Any other missing day (unread, ambiguous, an old cache without those words) keeps 截止待核对.
function agendaDateHTML(m,day=data.today,family=false,noDeadline=false){return `<p class="agenda-dates">${m.published_at||m.published_on||!family?`<span>发布：${esc(m.published_at?m.published_at.slice(0,16).replace('T',' '):m.published_on||'待核对')}</span>`:''}${m.complete_on&&(m.complete_on!==m.due_on||m.due_kind==='handback')?`<span data-complete-on="${esc(m.complete_on)}">${m.complete_on===day?'今天':''}完成：${esc(m.complete_on)}</span>`:''}${m.due_on||!noDeadline?`<span>${m.due_on?`${m.due_on<day?(['event','inspection','arranged'].includes(m.due_kind)?'已过 · ':'逾期 · '):''}${agendaDueLabel(m)}：${esc(m.due_on)}`:'截止待核对'}</span>`:''}${m.scheduled_on?`<span>计划：${esc(m.scheduled_on)}</span>`:''}</p>`}
function agendaItemHTML(item){
 if(item.kind==='event')return calendarEventHTML(item.event);
 if(item.kind==='study')return agendaStudyHTML(item);
 if(item.kind==='task'){const t=data.tasks.find(t=>t.id===item.task_id);if(t?.focus?.box==='wish')return wishTaskHTML(t);return t?`<div class="agenda-task">${taskHTML(t,{compact:true})}</div>`:''}
 const source=(data.agent?.items||[]).find(x=>x.id===item.id);
 return `<div class="agenda-school" id="school-review-${esc(item.id)}" data-query-target="school-review:${esc(item.id)}" tabindex="-1">${source?agentItemHTML(source,{compact:true,agenda:item.agenda}):`<h3>${esc(item.title)}</h3><p>此条尚未载入详情，请在学校信息中核对。</p><button data-page="agent">查看学校信息</button>`}</div>`;
}
function calendarStudyStatus(item){return (item.result||(item.status==='running'?'正在计时':item.status==='paused'?'已暂停':'待开始'))+(item.result_actor==='child'?' · 孩子自述待核对':'')}
function agendaStudyHTML(item){return `<article class="task agenda-study"><span class="chip">${esc(calendarNames(item.child_ids))}</span><h3>${esc(item.title)}</h3><p>${esc(calendarStudyStatus(item))}</p><button data-agenda-study="${esc(item.child_ids[0])}" data-agenda-day="${item.day}">打开作业执行</button></article>`}
function calendarDayItems(day){
 const r=calendarState.result,items=calendarItems(r.agenda||[],day),linked=new Set(items.map(x=>x.task_id).filter(Boolean));
 return [...items,...calendarItems(r.study||[],day).filter(x=>!items.some(i=>i.id===x.id)&&(!x.task_id||!linked.has(x.task_id)))];
}
function calendarRevealDay(){
 const strip=$('.calendar-week-scroll'),column=$('[data-calendar-column="'+calendarState.day+'"]');
 if(strip&&column&&strip.scrollWidth>strip.clientWidth)strip.scrollLeft=column.offsetLeft;
}
function calendarWeekHTML(){
 if(calendarState.range!==calendarState.week+'/'+calendarAdd(calendarState.week,6))return '<p role="status">正在读取一周安排…</p>';
 const r=calendarState.result;
 return `<p class="small muted calendar-week-help">一周总览 · 可滚动查看全部事项，点击日期在下方跟进。<span>左右滑动查看整周。</span></p><div class="calendar-week-scroll" tabindex="0" role="region" aria-label="一周事项总览"><div class="calendar-week-grid">${calendarDays().map((day,i)=>{
  const rows=calendarDayItems(day),events=calendarItems(r.events,day),tables=calendarItems(r.timetables,day);
  // The week keeps its time line for plans and lessons; its items are summarised by subject, never by two type counts.
  const groups=taskSubjectGroups(rows).map(([key,list])=>[esc(key)+' · '+list.length,list]);
  const item=(title,meta,closed=false)=>`<button class="calendar-week-item${closed?' is-closed':''}" data-calendar-day="${day}" data-calendar-detail><strong>${esc(title)}</strong><small>${esc(meta)}</small></button>`;
  return `<section class="calendar-day${day===data.today?' is-today':''}" data-calendar-column="${day}"><button class="calendar-day-heading" data-calendar-day="${day}" data-calendar-detail aria-pressed="${day===calendarState.day}" ${day===data.today?'aria-current="date"':''}><span>周${'一二三四五六日'[i]}</span><strong>${Number(day.slice(5,7))}/${Number(day.slice(8))}</strong>${day===data.today?'<small>今天</small>':''}</button><div class="calendar-day-body">${groups.map(([label,list])=>list.length?`<h3>${label}</h3>${list.map(x=>item(x.title||data.tasks.find(t=>t.id===x.task_id)?.title||'事项待核对',[calendarNames(x.child_ids),x.kind==='school'?'待核对':x.kind==='study'?calendarStudyStatus(x):taskStatusLabel(x.status)].filter(Boolean).join(' · '),x.closed)).join('')}`:'').join('')}${events.length?`<h3>计划</h3>${events.map(x=>item(x.title,[x.start_time||'时间待定',calendarNames(x.child_ids),calendarStatuses[x.status]].join(' · '),['completed','cancelled'].includes(x.status))).join('')}`:''}${tables.length?`<h3>课表</h3>${tables.map(x=>calendarTimetableHTML(x)).join('')}`:''}${!rows.length&&!events.length&&!tables.length?'<p class="small muted">暂无已收录安排</p>':''}</div></section>`;
 }).join('')}</div></div>`;
}
function calendarAgendaHTML(){
 if(calendarState.loading&&!calendarState.result)return '<p role="status">正在读取安排…</p>';
 if(calendarState.error)return `<p class="error" role="alert">${esc(calendarState.error)}</p><button data-calendar-retry>重试</button>`;
 if(!calendarState.result)return '<p role="status">准备读取日历…</p>';
 const r=calendarState.result,day=calendarState.day,items=calendarDayItems(day),tables=calendarItems(r.timetables,day);
 const section=(title,html)=>`<section class="card agenda-group"><h2>${title}</h2>${html||'<p class="small muted">没有已收录的事项</p>'}</section>`;
 return `${r.source_error?`<p class="error">${esc(r.source_error)}</p>`:''}${calendarWeekHTML()}<h2 class="agenda-day-title" id="calendarDayDetails" tabindex="-1">${esc(day)}${day===data.today?' · 今天':''} · 当天详情</h2><div class="agenda-groups">${calendarDayGroups(items,calendarItems(r.events,day),tables).map(([key,g])=>section(esc(key),[...g.lessons.map(({s})=>`<p class="subject-lesson"><span class="chip">课表 ${esc(s.slot)}</span> <strong>${esc(s.title)}</strong></p>`),...g.plans.map(calendarEventHTML),...g.rows.map(subjectItemHTML)].join(''))).join('')||section('当天事项','')}</div>${tables.length?`<div class="calendar-day-timetables">${tables.map(t=>calendarTimetableHTML(t)).join('')}</div>`:'<p class="small muted">当天课表尚未提供</p>'}<p class="small muted">限期事项每天显示直到完成；逾期继续保留。未明确日期的事项在收集箱核对。</p>`;
}
// One day is filed by subject too: each lesson sits under its own course name as the timetable writes it (slot and
// repeat rules unchanged), a family plan under the subject its own title names, then that subject's tracked items. The
// timetable record itself (original, correction, unchecked slots) stays below as its own management view.
function calendarDayGroups(items,plans,tables){
 const groups=new Map(taskSubjectGroups(items).map(([key,rows])=>[key,{rows,plans:[],lessons:[]}]));
 const add=(key,kind,x)=>{if(!groups.has(key))groups.set(key,{rows:[],plans:[],lessons:[]});groups.get(key)[kind].push(x)};
 for(const t of tables)for(const s of t.sessions)add(s.title||subjectUnknown,'lessons',{t,s});
 // A plan's subject is read from its own title on the server; plans of the same title read the same.
 for(const e of plans){const x=(calendarState.result?.inbox||[]).find(x=>x.kind==='event'&&x.title===e.title);add(x?taskSubjectKey(x):subjectGeneral,'plans',e)}
 const rank=key=>key===subjectUnknown?2:key===subjectGeneral?1:0;
 return [...groups].sort(([a],[b])=>rank(a)-rank(b));
}
function calendarHTML(){
 if(!calendarState.week){calendarState.week=calendarMonday(data.today);calendarState.day=data.today;calendarState.result=data.today_calendar;calendarState.range=data.today+'/'+data.today}
 calendarState.childID=currentChild()?.id||'';calendarState.visible=true;
 return `<section class="calendar-heading"><div><h1>家庭日历</h1></div><div class="toolbar"><button class="primary" data-calendar-new="${calendarState.day}">＋ 新建计划</button><button data-calendar-ask>说一句安排</button><details class="calendar-tools"><summary>课表与设置</summary><div class="toolbar"><button data-timetable-open>导入 / 管理课表</button><button data-calendar-sync>同步到手机</button><button data-new-task="yes">收集事务</button></div></details></div></section><div class="calendar-controls"><button data-calendar-shift="-7" aria-label="上一周">‹</button><label><span class="sr-only">跳到日期</span><input type="date" data-agenda-date value="${calendarState.day}"></label><button data-calendar-shift="7" aria-label="下一周">›</button><button data-calendar-current>今天</button></div><div class="calendar-kids">${data.children.map(c=>`<button data-calendar-child="${esc(c.id)}" aria-pressed="${c.id===calendarState.childID}">${esc(c.name)}</button>`).join('')}</div>${calendarPending||occurrencePending?'<p role="status">上次保存未确认。<button data-calendar-resume>继续核对</button></p>':''}<div id="calendarAgenda">${calendarAgendaHTML()}</div>`;
}
function taskInboxItems(){return (data.today_calendar?.inbox||[]).filter(x=>x.child_ids.includes(currentChild()?.id))}
function taskItemCompleted(x){return x.closed&&(x.kind==='task'?x.status==='已完成':x.kind==='event'?x.event.status==='completed':x.kind==='study'&&x.result==='完成'&&x.result_actor==='parent')}
function taskItemOverdue(x){const day=exactTaskDay(x.agenda.due_on||x.agenda.scheduled_on);return !x.closed&&x.agenda.box!=='wish'&&(!x.event?.repeat||x.event.repeat==='none')&&!!day&&day<data.today}
function taskBoxes(){const all=taskInboxItems(),open=all.filter(x=>!x.closed);return {'Inbox':open.filter(x=>x.agenda.box!=='wish'),'Wish':open.filter(x=>x.agenda.box==='wish'),'计划':open.filter(x=>x.agenda.box!=='wish'&&x.agenda.scheduled_on),'已完成':all.filter(taskItemCompleted),'已逾期':all.filter(taskItemOverdue),'已搁置':all.filter(x=>x.closed&&!taskItemCompleted(x)),'全部':all}}
function taskBoxesHTML(){return `<div class="tasktabs task-boxes">${Object.entries(taskBoxes()).sort(([a],[b])=>a==='全部'?-1:b==='全部'?1:0).map(([name,rows])=>`<button data-task-box="${name}" aria-pressed="${page==='tasks'&&taskView===name}">${({Inbox:'收集箱',Wish:'心愿'})[name]||name} <span>${rows.length}</span></button>`).join('')}</div>`}
function wishTaskHTML(t){return `<article class="task wish-task" data-query-target="task:${esc(t.id)}"><span class="chip">${esc(t.child)} · 心愿</span><h3>${esc(t.title)}</h3>${taskActionHTML(t)}<div class="tasktools">${!taskClosed(t)?`<button class="primary" data-task-plan="${esc(t.id)}">转成计划</button><button data-task-focus="${esc(t.id)}">编辑心愿</button><button data-task-decisions="${esc(t.id)}">暂时放下</button>`:`<button data-task-restore="${esc(t.id)}">恢复心愿</button>`}</div></article>`}
function homeworkByChildHTML(items){
 return items.length?`<div class="homework-child task-list" data-homework-child="${esc(currentChild()?.id)}">${items.map(agendaItemHTML).join('')}</div>`:'';
}
// Subject is the first and only grouping: one flat section per subject that has items. Type, date and status stay on
// each card; a cross-subject item is one card in its joint section, and 综合事务 and 科目待定 never mix.
const subjectGeneral='综合事务',subjectUnknown='科目待定';
function taskSubjectKey(x){const a=x.agenda||{};return a.subject_state==='known'&&(a.subjects||[]).length?a.subjects.join(' · '):a.subject_state==='general'?subjectGeneral:subjectUnknown}
function taskSubjectID(key){return 'subject-'+key.replace(/\s+/g,'')}
function taskSubjectGroups(items){return subjectFiled([...new Set(items)],taskSubjectKey)}
// Every other tracking list files the same way: its saved subject as written, else 科目待定 (never one read from a title
// or file name), 综合事务 and 科目待定 last. Rows keep their own order, card and id inside a subject, so nothing merges.
function subjectFiled(rows,keyOf){
 const groups=new Map();for(const x of rows){const key=String(keyOf(x)||'').trim()||subjectUnknown;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(x)}
 const rank=key=>key===subjectUnknown?2:key===subjectGeneral?1:0;
 return [...groups].sort(([a],[b])=>rank(a)-rank(b));
}
// A record or reading item with no saved subject is shown, read-only, under the one original it is reliably tied to: the
// same child's existing task, or the same child's related record. A missing, other-child or conflicting link stays
// 科目待定; a saved subject always wins and nothing is written back. Titles, book names and file names are never read.
function savedSubjectKey(value){const s=String(value||'').trim();return s==='综合'?subjectGeneral:s}
function linkedTaskSubjectKey(id,childName){if(!id)return null;const t=(data.tasks||[]).filter(t=>t.id===id);return t.length===1&&t[0].child===childName?taskSubjectKey(t[0]):undefined}
function recordSubjectKey(r,seen=new Set()){
 const own=savedSubjectKey(r?.subject);if(own||!r||seen.has(r.id))return own||subjectUnknown;seen.add(r.id);
 const source=String(r.source||''),task=linkedTaskSubjectKey(source.startsWith('事项:')?source.slice(3):r.linked_task_id,r.child);
 let parent=null;if(r.related_record_id!=null){const p=(data.records||[]).filter(x=>x.id===r.related_record_id);parent=p.length===1&&p[0].child===r.child?recordSubjectKey(p[0],seen):undefined}
 const keys=new Set([task,parent].filter(k=>k&&k!==subjectUnknown));
 return task===undefined||parent===undefined||keys.size!==1?subjectUnknown:[...keys][0];
}
function readingSubjectKey(t){return savedSubjectKey(t?.subject)||linkedTaskSubjectKey(t?.source_task_id,t?.child)||subjectUnknown}
function subjectFiledHTML(rows,keyOf,rowHTML,name){return subjectFiled(rows,keyOf).map(([key,list])=>`<section class="subject-filed" data-${name}="${esc(key)}"><h3 class="subject-filed-heading">${esc(key)} · ${list.length}</h3>${list.map(rowHTML).join('')}</section>`).join('')}
// The kind is said once at the start of a run of same-kind cards; every card still carries its own kind for checks.
function taskKindLabel(x){return x.kind==='event'||x.agenda?.box==='wish'?'':x.agenda?.category==='homework'||x.kind==='study'?'作业':'要办的事'}
function taskKindHTML(x,previous){const label=taskKindLabel(x);return !label||previous&&taskKindLabel(previous)===label?'':`<p class="subject-item-kind" data-category="${label==='作业'?'homework':'todo'}">${label}</p>`}
// data-today marks the cards the subject heading counts as 今天, so the first layer stays checkable inside each subject.
function taskIsToday(x){return [x.agenda?.due_on,x.agenda?.scheduled_on,x.agenda?.complete_on].some(day=>exactTaskDay(day)===data.today)}
function subjectItemHTML(x,i,list){return `<div class="subject-item" data-subject-item="${esc(x.id)}" data-category="${x.agenda?.category==='homework'?'homework':'todo'}" data-kind="${esc(x.kind)}"${taskIsToday(x)?' data-today':''}>${taskKindHTML(x,list[i-1])}${agendaItemHTML(x)}</div>`}
function taskGroupsHTML(items,today=false,emptyText=''){
 const groups=taskSubjectGroups(items);
 if(!groups.length)return `<section class="card agenda-group task-list subject-group subject-empty"><p class="small muted">${emptyText||(today?'当前没有已整理的未完成事项。':'这里暂时没有事项。')}</p></section>`;
 return groups.map(([key,rows])=>{
  const confirmed=rows.filter(x=>x.kind!=='school'),pending=rows.filter(x=>x.kind==='school'),due=today?confirmed.filter(taskIsToday).length:0;
  return `<section class="card agenda-group task-list subject-group" id="${esc(taskSubjectID(key))}" data-subject="${esc(key)}" tabindex="-1"><div class="task-group-heading"><h2>${esc(key)} · ${confirmed.length}${due?`<span class="subject-today">今天 ${due}</span>`:''}${pending.length?` <a class="review-badge review-link" href="#school-review-${esc(pending[0].id)}">待核对 ${pending.length}</a>`:''}</h2></div>${key===subjectUnknown?`<p class="small muted">${rows.every(x=>x.agenda?.box==='wish')?'没有填写科目；编辑心愿时可以补充，未补充也照常保留。':'原消息没有说明科目；可在事项里补充，未补充也照常保留。'}</p>`:''}<div class="homework-child task-list" data-homework-child="${esc(currentChild()?.id)}">${[...confirmed,...pending].map(subjectItemHTML).join('')}</div></section>`;
 }).join('');
}
function taskInboxHTML(){
 if(!Array.isArray(data.today_calendar?.inbox))return `<h1>事务收集箱</h1><p role="alert" class="error">${esc(data.today_calendar?.source_error||'收集箱暂时无法读取，请刷新记录；不能据此判断没有待办。')}</p>`;
 const views=taskBoxes();if(!(taskView in views))taskView='Inbox';setTimeout(revealTaskLink);
 return `<header class="today-heading"><h1>${taskView==='Wish'?'心愿清单':taskView==='全部'?'所有作业与待办':'收集箱'}</h1><button class="primary" data-new-task="${taskView==='Wish'?'wish':'yes'}">${taskView==='Wish'?'＋ 记心愿':'＋ 记一件事'}</button></header>${filters()}${taskBoxesHTML()}<p class="small muted">${({'Inbox':'所有未完成事务，包含已安排和已逾期的事项。','Wish':'想做的事先留在这里，选定日期再转成计划。','计划':'已安排日期、尚未完成的事项。','已完成':'已确认完成的事项，可撤销完成。','已逾期':'截止日已过；未填截止日时按计划日判断。重复安排不计入。','已搁置':'不参加、无需处理、已取消等事项，保留原决定。','全部':'所有日期的作业与待办，包含未完成、已完成及已搁置；心愿单独标注。'})[taskView]}</p><div class="today-task-groups" id="task-groups">${taskGroupsHTML(views[taskView],false,taskView==='Wish'?'这里暂时没有心愿。':'')}</div>`;
}
function todayTaskOrder(a,b){
 const key=x=>{
  const due=exactTaskDay(x.agenda?.due_on),planned=exactTaskDay(x.agenda?.scheduled_on),published=exactTaskDay(x.agenda?.published_on);
  if(due===data.today||planned===data.today||exactTaskDay(x.agenda?.complete_on)===data.today)return [0,data.today];
  if(due&&due<data.today)return [1,due];
  if(due)return [2,due];
  if(planned&&planned<data.today)return [3,planned];
  return published?[4,x.agenda.published_at||published]:[5,''];
 };
 const [ar,ad]=key(a),[br,bd]=key(b);
 return ar-br||(ar===2?ad.localeCompare(bd):bd.localeCompare(ad));
}
// The server's one-child day (family_agenda.day_view), the same selection, order and subjects the Mac workbench reads; a
// snapshot without it (older service, or its projection failed) keeps this page's own reading below.
function todayViewItems(){const view=data.today_view?.[currentChild()?.id];if(!Array.isArray(view?.groups))return null;const byID=new Map(taskInboxItems().map(x=>[x.id,x]));const rows=view.groups.flatMap(g=>g.items||[]).map(r=>byID.get(r.id));return rows.every(Boolean)?rows:null}
// The Mac workbench opens the same original task here (#task=<id>, optionally &do=<intent>): the task is shown once; an intent
// opens that task's own existing flow — the print dialog on its original or its parent reference, the feedback/photo-check
// dialog, its original message — where every confirmation, basis check and duplicate guard still applies. Nothing is printed or saved.
let taskLinkPending='',taskLinkIntent='';
{const m=/^#task=([^&]{1,100})(?:&do=(print-original|print-reference|check|original|history))?$/.exec(location.hash);if(m){taskLinkPending=decodeURIComponent(m[1]);taskLinkIntent=m[2]||''}}
function revealTaskLink(){
 if(!taskLinkPending||!data)return;const id=taskLinkPending;
 if(page==='home'&&groveView()){const row=groveRows(groveView()).find(r=>r.task_id===id||r.id===id);if(row&&groveSelected!==row.id){groveSelected=row.id;groveDetailOpen=true;return render()}}
 const target=[...document.querySelectorAll('[data-query-target]')].find(x=>x.dataset.queryTarget==='task:'+id)||[...document.querySelectorAll('[data-subject-item]')].find(x=>x.dataset.subjectItem===id);
 if(!target&&page==='home'){page='tasks';taskView='全部';return render()}
 const intent=taskLinkIntent;taskLinkPending='';taskLinkIntent='';history.replaceState(null,'',location.pathname+location.search);
 if(target){target.tabIndex=-1;target.classList.add('task-linked');target.scrollIntoView({block:'center'});target.focus({preventScroll:true})}
 const scope=page==='home'&&document.getElementById('groveDetail')||target?.closest('article')||document;
 if(intent==='print-original'||intent==='print-reference')openHomeworkPrint(id,intent==='print-reference'?'reference':'original');
 else if(intent==='check'||intent==='history')scope.querySelector('[data-task="'+CSS.escape(id)+'"]')?.click();
 else if(intent==='original')scope.querySelector('.grove-originals button,.grove-originals a')?.click();
}

// The home (今天): one child's day from the server projection (family_agenda.day_view, data.today_view), the same rows the Mac
// workbench reads. A compact subject-first list; the selected row's own detail beside it (>=900px) or in its place on a phone,
// where the browser's back returns to the list. Rows keep their original ids, task state and controllers; nothing is saved here.
let groveSelected='',groveDetailOpen=false,groveStamp=null;const groveMaterials=new Map();
const groveWhen={later:'以后安排',overdue:'已过期限',earlier:'之前安排',unknown:'日期未写明'};
function groveView(){const v=data?.today_view?.[currentChild()?.id];return Array.isArray(v?.groups)?v:null}
function groveRows(view){return [...(view?.groups||[]),...(view?.closed||[])].flatMap(g=>g.items||[])}
function groveWide(){return matchMedia('(min-width: 900px)').matches}
function groveFactWords(f){return f.state==='next_morning'?f.label+' 明天':f.state==='overdue'?'已逾期 · '+f.value:f.role==='complete'&&f.today?'今天完成':f.label+' '+(f.known?f.value:'日期未写明')}
function groveChipsHTML(r){
 const chips=[];if(groveWhen[r.when])chips.push(`<span class="grove-chip is-soft" data-when="${esc(r.when)}">${groveWhen[r.when]}</span>`);
 for(const f of (r.facts||[]).filter(f=>f.role==='due'||f.role==='complete'))
  chips.push(`<span class="grove-chip${f.state==='next_morning'||f.state==='overdue'?' is-coral':f.known?'':' is-soft'}" data-fact="${esc(f.role)}">${esc(groveFactWords(f))}</span>`);
 if(r.pending_review)chips.push('<span class="grove-chip is-coral">待核对</span>');
 return chips.join('');
}
function groveProgressWords(p){
 if(!p)return '';const parts=[];
 if(p.feedback)parts.push(`反馈${p.feedback}条`);if(p.wrong)parts.push(`错题${p.wrong}道`);if(p.clues)parts.push(`知识点线索${p.clues}条（不等于掌握）`);
 if(p.retries)parts.push(`独立再试${p.retries}次`);if(p.history)parts.push(`更正前的诊断${p.history}条作历史`);
 return parts.join(' · ');
}
function groveSource(r){return [r.publisher,String(r.published_at||'').slice(11,16)].filter(Boolean).join(' ')}
function groveCheckHTML(r){
 const t=r.task_id&&data.tasks.find(t=>t.id===r.task_id);
 if(r.pending_review)return '<span class="grove-mark" role="img" aria-label="学校消息待核对，确认后才算正式事项">?</span>';
 if(!t)return `<span class="grove-mark" aria-hidden="true">${r.closed?'✓':''}</span>`;
 const done=status(t)==='已完成',pending=pendingTask?.id===t.id;
 if(taskClosed(t)&&!done)return '<span class="grove-mark" aria-hidden="true">−</span>';
 if(t.agenda?.category==='homework'&&t.homework_report?.needs_review)return '<span class="grove-mark" role="img" aria-label="作业要求待核对，暂不能确认完成">?</span>';
 return `<label class="checkhit grove-check"><input type="checkbox" data-check="${esc(t.id)}" ${(pending?pendingTask.checked:done)?'checked':''} ${pendingTask?'aria-disabled="true"':''} aria-label="${done?'撤销完成':'确认完成'}：${esc(t.title)}"><span class="sr-only">${done?'撤销完成':'确认完成'}</span></label>`;
}
function groveRowHTML(r){
 const on=r.id===groveSelected,meta=[groveSource(r),groveProgressWords(r.progress)].filter(Boolean).join(' · ');
 const task=r.task_id?` data-today-task="${esc(r.task_id)}" data-query-target="task:${esc(r.task_id)}"`:'';
 return `<article class="grove-row${on?' is-selected':''}${r.closed?' is-done':''}" data-subject-item="${esc(r.id)}" data-category="${esc(r.category)}" data-kind="${esc(r.kind)}"${r.today?' data-today':''}${task} data-when="${esc(r.when||'')}">`
  +`${groveCheckHTML(r)}<button type="button" class="grove-open" data-grove-open="${esc(r.id)}" aria-controls="groveDetail" aria-pressed="${on}">`
  +`<span class="grove-title">${esc(r.title)}</span><span class="grove-lines">${r.lines?.length?esc(r.lines.join('；')):'<em>完成标准未提供，待补充</em>'}</span>`
  +`<span class="grove-chips">${groveChipsHTML(r)}</span>${meta?`<span class="grove-meta">${esc(meta)}</span>`:''}</button></article>`;
}
function groveMaterialHTML(f){
 const tone=f.state==='ready'?' is-leaf':['unread','error'].includes(f.state)?' is-coral':'';
 return `<div class="grove-material is-${esc(f.state||'saved')}" data-material="${esc(f.source?.id||'')}" data-material-state="${esc(f.state||'saved')}">`
  +`<p class="grove-material-head"><span class="grove-chip${tone}">${esc(f.label||'原件已保存')}</span><strong>${esc(f.name)}</strong></p>`
  +`<p class="small muted">${esc(f.role_label||'原件（用途未注明）')}</p>`
  +`${f.summary?`<p class="grove-material-summary">${esc(f.summary)}</p>`:''}`
  +`${f.unclear?.length?`<p class="grove-unclear">看不清：${esc(f.unclear.join('；'))}。请看原件。</p>`:''}`
  +`${!['ready','saved'].includes(f.state)&&f.explanation?`<p class="small">${esc(f.explanation)}</p>`:''}`
  +`<a class="grove-link" href="./upload/${encodeURIComponent(f.source?.id||'')}" target="_blank" rel="noopener">打开原件</a></div>`;
}
function groveMaterialsHTML(id){
 const m=groveMaterials.get(id);
 if(!m||m.loading)return '<h3>资料</h3><p class="small muted" role="status">正在读取资料…</p>';
 if(m.error)return `<h3>资料</h3><p class="error" role="alert">${esc(m.error)}</p><button type="button" data-grove-materials-retry="${esc(id)}">重新读取资料</button>`;
 const files=m.files||[],unread=files.filter(f=>['unread','error','partial'].includes(f.state)).length;
 return `<h3>资料 · ${files.length} 份${unread?`（${unread} 份尚未读清）`:''}</h3>${files.map(groveMaterialHTML).join('')||'<p class="small muted">这一项没有已保存的原件。</p>'}${m.school_error?`<p class="grove-unclear">${esc(m.school_error)}</p>`:''}`;
}
async function groveLoadMaterials(id,force=false){
 if(!force&&groveMaterials.has(id))return;groveMaterials.set(id,{loading:true});
 const paint=()=>{const host=document.querySelector('[data-grove-materials="'+CSS.escape(id)+'"]');if(host)host.innerHTML=groveMaterialsHTML(id)};paint();
 try{
  const r=await apiFetch('/api/print/homework/materials?task_id='+encodeURIComponent(id),{signal:AbortSignal.timeout(20000)}),out=await r.json();
  if(!r.ok)throw Error(out.error||'资料暂时读不到');
  groveMaterials.set(id,{files:Array.isArray(out.files)?out.files:[],school_error:typeof out.school_error==='string'?out.school_error:''});
 }catch(e){groveMaterials.set(id,{error:(e.name==='TimeoutError'?'资料读取超时':e.message||'资料暂时读不到')+'；记录未更改，可以重试。'})}
 paint();
}
function groveDetailHTML(r){
 const back='<div class="grove-back"><button type="button" data-grove-back>‹ 返回清单</button></div>';
 if(!r)return '<div class="grove-empty"><p>从清单里选一项，看要做什么、资料和反馈。</p></div>';
 const head=extra=>`<div class="grove-head"><span class="grove-tag">${esc(r.subject)}</span>${groveSource(r)?`<span class="grove-source">${esc(groveSource(r))} 发布</span>`:''}${extra||''}</div><h2 class="grove-h">${esc(r.title)}</h2>`;
 const item=taskInboxItems().find(x=>x.id===r.id),t=r.task_id&&data.tasks.find(t=>t.id===r.task_id);
 if(!t)return back+head()+(item?agendaItemHTML(item):'<p class="small muted">此条尚未载入详情，请刷新记录。</p>');
 const open=!taskClosed(t),done=status(t)==='已完成',homework=t.agenda?.category==='homework',reportPending=open&&homework&&t.homework_report?.needs_review;
 const originals=schoolOriginalButtons(String(t.source||'').split('\n').filter(x=>x.startsWith('message:')),data.children.find(c=>c.name===t.child)?.id,'看原消息',t.agenda?.publications,t.school_origin?t.id:'');
 const facts=(r.facts||[]).map(f=>`<div class="grove-fact${f.state==='next_morning'||f.state==='overdue'?' is-coral':''}" data-fact="${esc(f.role)}"><span>${esc(f.label)}</span><strong>${esc(f.known?(f.today?'今天 ':'')+f.value:'日期未写明，不猜')}</strong>${f.state==='next_morning'?'<em>明天</em>':f.state==='overdue'?'<em>已逾期</em>':''}</div>`).join('');
 const history=[...(r.records||[]).map(x=>`<li data-grove-record="${esc(x.id)}"><span class="grove-chip">${esc(x.followup_kind||'反馈')}</span> <span class="small muted">${esc(String(x.created||'').slice(0,16).replace('T',' '))}${x.attachments?.length?` · 照片${x.attachments.length}份`:''}</span>${x.retry?retryViewHTML(x):`<p>${esc(x.note||x.title)}</p>`}</li>`),
  ...(r.wrong||[]).map(w=>`<li data-grove-wrong="${esc(w.id)}"><span class="grove-chip${w.state==='待订正'?' is-coral':' is-leaf'}">${esc(w.state||'待订正')}</span> <span>错题：${esc(w.title)}</span></li>`)].join('');
 const primary=reportPending?`<button class="primary" data-study-task-add="${esc(t.id)}">核对报来的功课</button>`:open?`<button class="primary" data-task="${esc(t.id)}">${homework?'交作答照片 / 写反馈':'写反馈'}</button>`:`<button data-task="${esc(t.id)}">查看反馈</button>`;
 const more=(open?`<button data-task-decisions="${esc(t.id)}">不参加 / 不用做</button><button data-task-plan="${esc(t.id)}">${t.agenda?.scheduled_on?'改计划日期':'转成计划'}</button><button data-task-focus="${esc(t.id)}">修改标题 / 日期</button>`:'')
  +(open&&homework?`<button data-study-task-add="${esc(t.id)}">作业计时</button>`:'')+`<button data-school-record-task="${esc(t.id)}">留作学习记录</button>`
  +(/阅读|读书|篇目|读后感/.test(t.title+t.action)?`<button data-reading-source="${esc(t.id)}">约定阅读任务</button>`:'')+(taskClosed(t)&&!done?`<button data-task-restore="${esc(t.id)}">恢复跟进</button>`:'');
 const standards=r.lines?.length?`<ul class="grove-standards">${r.lines.map(l=>`<li>${esc(l)}</li>`).join('')}</ul>`:'<p class="grove-unclear">完成标准未提供，待补充</p>';
 return back+head(originals?`<span class="grove-originals">${originals}</span>`:'')
  +(groveWhen[r.when]?`<p class="grove-when" data-grove-when="${esc(r.when)}">这一项${groveWhen[r.when]}，不算这一天要交的作业。</p>`:'')
  +`<section class="grove-card"><h3>要做什么与完成标准</h3>${standards}${r.complete_words?`<p class="small muted">完成要求：${esc(r.complete_words)}</p>`:''}${!t.agenda?.due_on&&t.due&&t.due!=='无明确截止'?`<p class="small muted">原日期要求：${esc(t.due)}</p>`:''}${t.school_completion_needs_review?'<p class="note" data-school-completion-review>原要求已完成；更正后是否需补做、是否已完成，待家长核对。</p>':''}</section>`
  +`<div class="grove-facts">${facts}</div>`
  +(homework?`<section class="grove-card grove-materials" data-grove-materials="${esc(t.id)}" aria-live="polite">${groveMaterialsHTML(t.id)}</section><div class="grove-actions grove-print">${open?`<button data-homework-print="${esc(t.id)}" data-print-intent="original">打印原卷</button><button data-homework-print="${esc(t.id)}" data-print-intent="reference">打印家长参考</button>`:''}<p class="small muted">打印先在确认里核对依据和所选资料，确认后才排队。</p></div>`:'')
  +`<section class="grove-card"><h3>反馈与订正</h3>${taskProgressHTML(t)}${t.update?.note?`<p class="feedback task-feedback-summary">${esc(t.update.note)}</p>`:''}${history?`<ul class="grove-history">${history}</ul>`:'<p class="small muted">还没有反馈。照片可以不交，只写几句文字也行；没有反馈不等于没做。</p>'}<div class="grove-actions">${primary}</div></section>`
  +`<details class="grove-more"><summary>更多操作</summary><div class="tasktools">${more}</div></details>`;
}
function groveSelect(id,user){
 groveSelected=id;
 if(!groveWide()){groveDetailOpen=true;if(user&&!history.state?.grove)history.pushState({grove:id},'',location.pathname+location.search)}
 render();
 requestAnimationFrame(()=>{const d=document.getElementById('groveDetail');if(!groveWide())window.scrollTo(0,0);d?.focus({preventScroll:true})});
}
document.addEventListener('click',e=>{
 const open=e.target.closest('[data-grove-open]');if(open){groveSelect(open.dataset.groveOpen,true);return}
 if(e.target.closest('[data-grove-back]')){if(history.state?.grove)history.back();else{groveDetailOpen=false;render()}return}
 const retry=e.target.closest('[data-grove-materials-retry]');if(retry)groveLoadMaterials(retry.dataset.groveMaterialsRetry,true);
});
window.addEventListener('popstate',()=>{if(groveDetailOpen&&!history.state?.grove){groveDetailOpen=false;if(page==='home')render()}});
function todayTasksHTML(){
 const r=data.today_calendar;if(!Array.isArray(r?.inbox))return taskInboxHTML();
 const view=groveView();if(!view)return todayTasksLegacyHTML();  // an older service, or a snapshot whose projection failed
 if(groveStamp!==data){groveStamp=data;groveMaterials.clear()}
 const rows=groveRows(view);
 if(!rows.some(x=>x.id===groveSelected)){groveSelected=groveWide()?(rows[0]?.id||''):'';groveDetailOpen=false}
 const selected=rows.find(x=>x.id===groveSelected),c=view.counts||{};
 setTimeout(()=>{revealTaskLink();if(selected?.task_id&&selected.category==='homework')groveLoadMaterials(selected.task_id)});
 const matches=x=>(x.child_ids||[x.child_id]).includes(currentChild()?.id);
 const sources=currentSources().filter(s=>matches({child_ids:[s.child_id]}));
 const readGap=sources.some(s=>currentSourceStatus(s)!=='最近读取成功')||!!data.sync_error||(!currentSources().length&&!!data.agent?.last_error);
 const originalGap=sources.some(s=>s.unread_count>0);
 const summary=[`共 ${c.open||0} 项`,`今天要做 ${c.today||0}`,...[['later','以后安排'],['overdue','已过期限'],['earlier','之前安排'],['unknown','日期未写明']].filter(([k])=>c[k]).map(([k,l])=>`${l} ${c[k]}`)].join(' · ');
 const groups=view.groups.map(g=>`<section class="grove-subject subject-group" data-subject="${esc(g.subject)}" id="${esc(taskSubjectID(g.subject))}" tabindex="-1"><h2 class="grove-tag">${esc(g.subject)}<span>${g.items.length} 项</span></h2>`
  +`${g.subject===subjectUnknown?'<p class="small muted">原消息没有说明科目；可在事项里补充，未补充也照常保留。</p>':''}<div class="grove-rows homework-child" data-homework-child="${esc(currentChild()?.id)}">${g.items.map(groveRowHTML).join('')}</div></section>`).join('')
  ||'<p class="grove-empty-list">这一天没有已整理的未完成事项；没有反馈不等于没做。</p>';
 const closed=(view.closed||[]).flatMap(g=>g.items||[]);
 const plans=(r.timetables||[]).filter(matches).map(t=>calendarTimetableHTML(t,{open:true})).join('')+(r.events||[]).filter(x=>matches(x)&&!['cancelled','completed'].includes(x.status)).map(calendarEventHTML).join('');
 const gap=readGap?'<p class="note today-source-gap" role="status">消息读取有缺口，清单可能缺项。<button data-page="sources" data-collection-check>检查最新消息</button></p>':originalGap?'<p class="note today-source-gap">部分消息原件尚未读全。<button data-page="sources">查看消息来源</button></p>':'';
 const add=data.children.filter(x=>x.name===child).map(x=>`<button class="primary" data-homework-new="${esc(x.id)}">＋ 补录口头作业</button>`).join('');
 return `<div class="grove" data-view="${groveDetailOpen&&!groveWide()?'detail':'list'}"><section class="grove-list" aria-labelledby="groveListTitle">`
  +`<header class="grove-list-head"><div><h1 id="groveListTitle">当天清单</h1><p class="grove-summary" data-grove-summary>${[data.today,...String(summary).split(' · ')].map(s=>`<span class="grove-nowrap">${esc(s)}</span>`).join(' · ')}</p></div>${add}</header>`
  +`<div class="today-controls">${filters()}</div>${r.source_error?`<p class="error" role="status">${esc(r.source_error)}</p>`:''}${gap}${schoolProcessingHTML()}`
  +`<div class="today-task-groups" id="task-groups">${groups}</div>`
  +(closed.length?`<details class="grove-closed"><summary>这一天已办 ${closed.length} 项</summary><div class="grove-rows">${closed.map(groveRowHTML).join('')}</div></details>`:'')
  +`<details id="today-courses" class="grove-plans today-plans"><summary>今日课程与安排</summary>${plans||'<p class="small muted">当天课表尚未提供。</p><button data-page="calendar">查看日历 / 导入课表</button>'}</details></section>`
  +`<section class="grove-detail" id="groveDetail" tabindex="-1" aria-label="所选事项">${groveDetailHTML(selected)}</section></div>`;
}
function todayTasksLegacyHTML(){
 const r=data.today_calendar;if(!Array.isArray(r?.inbox))return taskInboxHTML();
 const matches=x=>(x.child_ids||[x.child_id]).includes(currentChild()?.id);
 const reviewDue=x=>x.kind==='task'&&data.tasks.some(t=>t.id===x.task_id&&taskReviewDue(t));
 const items=todayViewItems()||taskInboxItems().filter(x=>!x.closed&&x.kind!=='event'&&x.agenda.box!=='wish'&&(!x.agenda.published_on||x.agenda.published_on<=data.today)&&(!x.agenda.scheduled_on||x.agenda.scheduled_on<=data.today||x.agenda.due_on||reviewDue(x))).sort(todayTaskOrder);
 setTimeout(revealTaskLink);
 const sources=currentSources().filter(s=>matches({child_ids:[s.child_id]}));
 const readGap=sources.some(s=>currentSourceStatus(s)!=='最近读取成功')||!!data.sync_error||(!currentSources().length&&!!data.agent?.last_error);
 const originalGap=sources.some(s=>s.unread_count>0);
 const plans=(r.timetables||[]).filter(matches).map(t=>calendarTimetableHTML(t,{open:true})).join('')+(r.events||[]).filter(x=>matches(x)&&!['cancelled','completed'].includes(x.status)).map(calendarEventHTML).join('');
 return `<header class="today-heading"><div><h1>今天</h1><p>${esc(data.today)}</p></div><div class="toolbar">${data.children.filter(c=>c.name===child).map(c=>`<button class="primary" data-homework-new="${esc(c.id)}">＋ 记${esc(c.name)}的作业</button>`).join('')}</div></header>${r.source_error?`<p class="error" role="status">${esc(r.source_error)}</p>`:''}${readGap?'<p class="note today-source-gap" role="status">消息读取有缺口，作业可能缺项。<button data-page="sources" data-collection-check>检查最新消息</button></p>':originalGap?'<p class="note today-source-gap">部分消息原件尚未读全。<button data-page="sources">查看消息来源</button></p>':''}${schoolProcessingHTML()}<div class="today-controls">${filters()}</div><p class="small muted today-subject-note">各科按今天、逾期、以后、日期待定排列；未完成事项保留原日期，没有反馈不等于没做。</p><div class="today-task-groups" id="task-groups">${taskGroupsHTML(items,true)}</div><section id="today-courses" class="card agenda-group task-list today-plans"><h2>今日课程与安排</h2>${plans||'<p class="small muted">当天课表尚未提供。</p><button data-page="calendar">查看日历 / 导入课表</button>'}</section><details class="today-extra"><summary>其他记录与计数说明</summary><button data-new-task="yes">记其他事项</button><p class="small muted">事项按科目分区，作业和要办的事都保留原期限；未填日期不算今天到期。</p></details>`;
}
async function calendarRead(){
 const start=calendarState.week,end=calendarAdd(start,6),range=start+'/'+end;
 if(calendarState.loading||calendarState.range===range&&calendarState.result&&!calendarState.dirty)return;
 const seq=++calendarState.sequence;calendarState.controller?.abort();const controller=new AbortController();calendarState.controller=controller;calendarState.loading=true;calendarState.error='';
 const timer=setTimeout(()=>controller.abort(),20000);
 const paint=()=>{if(page==='calendar'&&calendarState.visible&&$('#calendarAgenda')){
  const pane=$('#calendarAgenda'),active=document.activeElement,ref=active?.closest?.('[data-query-target]')?.dataset.queryTarget;
  pane.innerHTML=calendarAgendaHTML();pane.setAttribute('aria-busy',String(calendarState.loading));calendarRevealDay();
  if(ref&&!active.isConnected&&!document.querySelector('dialog[open]')){const target=[...pane.querySelectorAll('[data-query-target]')].find(x=>x.dataset.queryTarget===ref);if(target){target.tabIndex=-1;target.focus({preventScroll:true})}}
 }};paint();
 try{const r=await apiFetch('/api/calendar?start='+start+'&end='+end,{signal:controller.signal}),result=await r.json();if(!r.ok)throw Error(result.error||'读取日历失败');if(!Array.isArray(result.events)||!Array.isArray(result.timetables))throw Error('日历资料格式无法读取，请重试');if(seq!==calendarState.sequence||start!==calendarState.week)return;calendarState.result=result;calendarState.range=range;calendarState.dirty=false;
 }catch(err){if(seq!==calendarState.sequence)return;calendarState.error=err.name==='AbortError'?'读取超时，请稍后重试。':['TypeError','SyntaxError'].includes(err.name)?'暂时无法读取，请检查登录或连接后重试。':err.message;
 }finally{clearTimeout(timer);if(seq===calendarState.sequence){calendarState.loading=false;paint()}}
}
function wireCalendar(){if(!calendarState.error)calendarState.reading=calendarRead();calendarRevealDay()}
function calendarSyncOpen(){
 const address=new URL(endpoint('/calendar.ics'),location.href),secure=address.protocol==='https:';
 address.username='';address.password='';calendarSyncVersion++;
 $('#calendarSyncURL').value=secure?address.href:'';$('#calendarSyncAddress').hidden=!secure;$('#calendarSyncCopy').disabled=!secure;$('#calendarSyncHelp').open=false;
 $('#calendarSyncStatus').textContent=secure?'复制地址后，在手机日历中添加订阅。':'请从已登录的 HTTPS 家庭入口打开，再获取手机订阅地址。';
 $('#calendarSyncDialog').showModal();
}
async function calendarSyncCopy(){
 const field=$('#calendarSyncURL'),button=$('#calendarSyncCopy'),dialog=$('#calendarSyncDialog'),version=calendarSyncVersion;
 if(button.disabled||!field.value)return;
 button.disabled=true;$('#calendarSyncStatus').textContent='正在复制…';
 try{await navigator.clipboard.writeText(field.value);if(dialog.open&&version===calendarSyncVersion)$('#calendarSyncStatus').textContent='已复制。请到手机日历添加订阅。'}
 catch{if(dialog.open&&version===calendarSyncVersion){field.focus();field.select();field.setSelectionRange(0,field.value.length);$('#calendarSyncStatus').textContent='未能自动复制，已选中地址。请长按或使用复制快捷键，手动复制。'}}
 finally{if(version===calendarSyncVersion)button.disabled=false}
}
$('#calendarSyncCopy').onclick=calendarSyncCopy;
$('#calendarSyncDialog').addEventListener('close',()=>calendarSyncVersion++);
function calendarNavigate(day){calendarJump++;calendarInvalidate();calendarState.week=calendarMonday(day);calendarState.day=day;page='calendar';render()}
function calendarUUID(){return crypto.randomUUID?crypto.randomUUID().replaceAll('-',''):[...crypto.getRandomValues(new Uint8Array(16))].map(n=>n.toString(16).padStart(2,'0')).join('')}
function calendarOpen(event=null,preset={}){
 if(calendarSaving||occurrenceSaving)return false;
 if(occurrencePending){$('#calendarOccurrenceDialog').showModal();return false}
 if(calendarPending){$('#calendarDialog').showModal();return false}
 calendarRememberDraft();calendarDraftContext=null;
 document.getElementById?.('calendarDraftDetails')?.remove();document.getElementById?.('calendarDraftSchedule')?.remove();
 const e=event||{id:calendarUUID(),version:0,child_ids:currentChild()?[currentChild().id]:[],title:'',category:'activity',day:calendarState.day||data.today,start_time:'',end_time:'',location:'',note:'',status:'tentative',repeat:'none',until:'',...preset};
 const f=$('#calendarForm');f.reset();for(const k of ['id','version','title','category','start_time','end_time','location','note','status','repeat','until'])f.elements[k].value=e[k]??'';f.elements.day.value=e.series_day||e.day;f.elements.id.value=e.series_id||e.id;f.elements.start_time.value=e.series_start_time??e.start_time;f.elements.end_time.value=e.series_end_time??e.end_time;
 const days=e.repeat_days||[];calendarWeekdaysChosen=e.repeat==='weekly'&&days.length>0;const weekday=new Date((e.series_day||e.day||data.today)+'T12:00:00Z').getUTCDay()||7;for(const input of f.querySelectorAll('[name=repeat_weekday]'))input.checked=(e.repeat==='weekly'&&days.length?days:[weekday]).includes(Number(input.value));f.elements.repeat_monthdays.value=e.repeat==='monthly'?days.join('、'):'';$('#calendarExtraRows').innerHTML=(e.extra_times||[]).map((slot,n)=>calendarExtraHTML(slot,n,e.id===e.series_id+'.'+slot.id)).join('');
 $('#calendarChildChoices').innerHTML=data.children.map(c=>`<label><input type="checkbox" name="child_ids" value="${esc(c.id)}" ${(e.child_ids||[]).includes(c.id)?'checked':''}><span>${esc(c.name)}</span></label>`).join('');
 $('#calendarDialogTitle').textContent=event?'编辑安排':'写下一个安排';$('#calendarEditNote').textContent=event&&event.repeat!=='none'?'修改未单独处理的重复日期；已单独改期、完成或取消的记录保留。':'可以先暂定，和孩子商量后再确定。';$('#calendarFormError').textContent='';$('#calendarRetryNote').textContent='';calendarFormLock(false);calendarRepeat();$('#calendarDialog').showModal();const active=$('#calendarExtraRows').querySelector?.('.is-selected-slot');if(active){active.scrollIntoView({block:'center'});active.focus({preventScroll:true})}return true;
}
function calendarDraftMissing(context){const d=context.form||context.draft;return d?[!d.child_ids?.length?'孩子':'',!d.title?.trim()?'安排内容':'',!d.day?'日期':''].filter(Boolean).join('、'):''}
function calendarDraftSchedule(context){const d=context.form||context.draft;if(!d||d.repeat==='none')return '';const times=[d,...(d.extra_times||[])].map((p,n)=>p.start_time?p.start_time+(p.end_time?'–'+p.end_time:''):'时段'+(n+1)+'钟点待定');return (d.day?'从 '+d.day:'起点待定')+(d.until?' 至 '+d.until:' · 未设截止')+' · '+calendarRepeatLabel(d)+' · '+times.join('、')}
function calendarDraftDetails(context,id=''){const schedule=calendarDraftSchedule(context);return `${schedule?`<p class="source" ${id?'id="calendarDraftSchedule"':''}>${esc(schedule)}</p>`:''}<details class="ask-citation" ${id?`id="${esc(id)}"`:''}><summary>原话与核对说明</summary><p class="source">${esc(context.text)}</p>${context.needs_review.length?`<ul>${context.needs_review.map(x=>`<li class="source">${esc(x)}</li>`).join('')}</ul>`:''}</details>`}
function calendarDraftNote(context){const missing=calendarDraftMissing(context);return '按 '+context.reference_date+' 理解相对日期。'+(missing?'待核对：'+missing+'。':'请核对后保存。')}
function calendarRememberDraft(){if(calendarDraftContext&&!calendarSaving&&!calendarPending){calendarDraftContext.form=calendarPayload();$('#calendarEditNote').textContent=calendarDraftNote(calendarDraftContext);const schedule=document.getElementById?.('calendarDraftSchedule');if(schedule)schedule.textContent=calendarDraftSchedule(calendarDraftContext)}}
function calendarOpenAssistant(context){
 if(calendarSaving||calendarPending)return false;
 if(!context?.draft||context.saved)return false;
 const preset=context.form||{...context.draft,child_ids:context.draft.child_ids||[],day:context.draft.day||''};
 if(!calendarOpen(null,preset))return false;
 if(preset.repeat==='weekly'&&!preset.repeat_days?.length){calendarWeekdaysChosen=true;for(const input of $('#calendarForm').querySelectorAll('[name=repeat_weekday]'))input.checked=false;calendarRepeat()}
 calendarDraftContext=context;calendarRememberDraft();
 $('#calendarDialogTitle').textContent='核对一句话安排';
 $('#calendarEditNote').textContent=calendarDraftNote(context);
 $('#calendarEditNote').insertAdjacentHTML('afterend',calendarDraftDetails(context,'calendarDraftDetails'));
 return true;
}
async function calendarOpenCitation(c,childID){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(c.day||'')||!data.children.some(x=>x.id===childID)){toast('原安排的日期或孩子待核对，请重新查询。');return}
 if(!selectChild(childID))return;calendarJump++;calendarInvalidate();calendarState.week=calendarMonday(c.day);calendarState.day=c.day;calendarState.childID=childID;calendarState.visible=true;page='calendar';render();
 const seq=calendarState.sequence;
 // render starts the existing read; await that same request instead of a second one.
 if(calendarState.reading)await calendarState.reading;
 if(page!=='calendar'||calendarState.sequence!==seq)return;
 const targets=[...document.querySelectorAll('[data-query-target]')].filter(el=>el.dataset.queryTarget===c.kind+':'+c.target_id+':'+c.day),target=targets.find(el=>el.closest?.('.agenda-groups'))||targets[0];
 if(target){if(c.kind==='timetable')target.open=true;target.scrollIntoView({block:'center'});target.focus({preventScroll:true})}else toast('原安排已变化或暂时无法读取，请重新查询。');
}
function calendarExtraHTML(slot={id:calendarUUID().slice(0,16),start_time:'',end_time:''},index=0,active=false){return `<div class="formrow calendar-extra-time ${active?'is-selected-slot':''}" data-calendar-slot="${esc(slot.id)}" tabindex="-1"><strong data-slot-label>时段 ${index+2}${active?' · 正在修改的时段':''}</strong><button type="button" data-calendar-remove-slot aria-label="移除时段 ${index+2}">移除</button><label>开始<input type="time" data-slot-start required value="${esc(slot.start_time)}"></label><label>结束 · 可选<input type="time" data-slot-end value="${esc(slot.end_time)}"></label></div>`}
function calendarRepeat(){
 const f=$('#calendarForm'),mode=f.elements.repeat.value,repeats=mode!=='none',date=f.elements.day.value,weekday=date?(new Date(date+'T12:00:00Z').getUTCDay()||7):0;
 if(!calendarWeekdaysChosen&&weekday)for(const input of f.querySelectorAll('[name=repeat_weekday]'))input.checked=Number(input.value)===weekday;
 for(const [id,visible] of [['calendarUntil',repeats],['calendarWeekdays',mode==='weekly'],['calendarMonthdays',mode==='monthly'],['calendarExtraTimes',repeats]]){const el=$('#'+id);el.classList.toggle('hide',!visible);for(const input of el.querySelectorAll('input,button'))input.disabled=!visible}
 $('#calendarPrimaryLabel').textContent=repeats?'时段 1 · 开始时间':'开始时间 · 可不填';
 let note=repeats?'在起止日期内重复；单独处理过的日期保留原记录。'+(mode==='monthly'?'没有所选日期的月份会跳过。':''):'';
 const days=[...f.querySelectorAll('[name=repeat_weekday]:checked')].map(x=>Number(x.value));if(mode==='weekly'&&weekday&&days.length){const offset=Array.from({length:7},(_,n)=>n).find(n=>days.includes((weekday+n-1)%7+1));note+='首次日期：'+calendarAdd(date,offset)+'。'}
 $('#calendarRepeatNote').textContent=note;
}
$('#calendarAddTime').onclick=()=>{const rows=$('#calendarExtraRows');if(rows.children.length>=7){$('#calendarFormError').textContent='每天最多8个时段。';return}rows.insertAdjacentHTML('beforeend',calendarExtraHTML(undefined,rows.children.length));calendarRememberDraft()};
$('#calendarExtraRows').onclick=e=>{const button=e.target.closest('[data-calendar-remove-slot]');if(button){button.closest('[data-calendar-slot]').remove();for(const [n,row] of [...$('#calendarExtraRows').children].entries()){row.querySelector('[data-slot-label]').textContent='时段 '+(n+2)+(row.classList.contains('is-selected-slot')?' · 正在修改的时段':'');row.querySelector('[data-calendar-remove-slot]').setAttribute('aria-label','移除时段 '+(n+2))}calendarRememberDraft()}};
$('#calendarForm').addEventListener('change',e=>{if(e.target.name==='repeat_weekday')calendarWeekdaysChosen=true;if(['day','repeat_weekday'].includes(e.target.name))calendarRepeat()});

function calendarFormLock(locked){$('#calendarFields').disabled=locked;$('#calendarSave').disabled=calendarSaving;$('#calendarSave').textContent=calendarSaving?'正在保存…':calendarPending?'重试这次保存':'保存安排';$('#calendarCancel').disabled=calendarSaving}
function calendarPayload(){const f=$('#calendarForm'),v=Object.fromEntries(new FormData(f));return {id:v.id,version:Number(v.version),child_ids:[...f.querySelectorAll('[name=child_ids]:checked')].map(x=>x.value),title:v.title,category:v.category,day:v.day,start_time:v.start_time,end_time:v.end_time,location:v.location,note:v.note,status:v.status,repeat:v.repeat,until:v.repeat!=='none'?v.until:'',repeat_days:v.repeat==='weekly'?[...f.querySelectorAll('[name=repeat_weekday]:checked')].map(x=>Number(x.value)):v.repeat==='monthly'?(v.repeat_monthdays||'').trim().split(/[、，,\s]+/).filter(Boolean).map(Number):[],extra_times:v.repeat==='none'?[]:[...f.querySelectorAll('[data-calendar-slot]')].map(el=>({id:el.dataset.calendarSlot,start_time:el.querySelector('[data-slot-start]').value,end_time:el.querySelector('[data-slot-end]').value}))}}

async function calendarRequest(obj){
 if(!calendarPending)calendarPending=JSON.stringify(obj);
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try{const r=await apiFetch('/api/calendar/save',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:calendarPending}),result=await r.json();if(!r.ok){if([400,404,409].includes(r.status))calendarPending=null;throw Error((result.error||'保存失败')+(r.status===409?'。请关闭表单刷新日历，重新打开最新安排后修改。':[401,403].includes(r.status)?'。当前输入已保留；完成登录或恢复连接后，请在这里重试保存。':''))}if(!result.event?.id)throw Error('保存响应暂时无法核对，请使用原内容重试');calendarPending=null;return result.event;
 }finally{clearTimeout(timer)}
}
$('#calendarForm').onsubmit=async e=>{
 e.preventDefault();if(calendarSaving)return;const obj=calendarPending?JSON.parse(calendarPending):calendarPayload();if(!obj.child_ids.length){$('#calendarFormError').textContent='请至少选择一位孩子。';return}
 if(!calendarPending&&obj.repeat==='weekly'&&!obj.repeat_days.length){$('#calendarFormError').textContent='请至少选择每周的一天。';return}
 calendarSaving=true;calendarFormLock(true);$('#calendarFormError').textContent='';
 try{const saved=await calendarRequest(obj);if(page==='calendar'&&obj.version===0){calendarState.day=saved.day;calendarState.week=calendarMonday(saved.day)}if(calendarDraftContext){calendarDraftContext.saved=true;calendarDraftContext.form=null;calendarDraftContext=null}$('#calendarDialog').close();toast('安排已保存');calendarInvalidate(page==='calendar');try{await load()}catch{if(page==='calendar')render();toast('安排已保存，最新资料暂时无法刷新，请稍后刷新日历。')}}
 catch(err){$('#calendarFormError').textContent=['TypeError','SyntaxError'].includes(err.name)?'暂时无法核对保存结果，请检查连接后重试。':err.name==='AbortError'?'保存响应超时，请用原内容重试。':err.message;$('#calendarRetryNote').textContent=calendarPending?'保留了这次的内容与编号，重试不会新建另一条安排。可以先关闭，稍后在日历继续重试。':'';}
 finally{calendarSaving=false;calendarFormLock(!!calendarPending)}
};
$('#calendarForm').elements.repeat.onchange=calendarRepeat;
for(const type of ['input','change'])$('#calendarForm').addEventListener(type,calendarRememberDraft);
$('#calendarCancel').onclick=()=>{if(!calendarSaving){calendarRememberDraft();$('#calendarDialog').close();if(['calendar','ask'].includes(page))render()}};
$('#calendarDialog').addEventListener('cancel',e=>{if(calendarSaving)e.preventDefault();else{calendarRememberDraft();if(['calendar','ask'].includes(page))setTimeout(render,0)}});
window.addEventListener('beforeunload',e=>{if(calendarPending||calendarDraftContext&&!calendarDraftContext.saved){e.preventDefault();e.returnValue=''}});
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.taskBox){taskView=b.dataset.taskBox;page='tasks';render();return}
 if(b.dataset.taskPlan){openTaskFocus(b.dataset.taskPlan);const f=$('#taskFocusForm');f.elements.box.value='inbox';f.elements.scheduled_on.required=true;if(f.elements.category.value==='unknown')f.elements.category.value='todo';$('#taskFocusScheduleLabel').textContent='计划在哪天做 · 必填';$('#taskFocusTitle').textContent='选定日期，转成计划';return}
 if(b.dataset.agendaStudy){if(!selectChild(b.dataset.agendaStudy))return;studyChildID=b.dataset.agendaStudy;studyDay=b.dataset.agendaDay;studyTaskID='';page='study';render();return}
 if(b.hasAttribute('data-calendar-sync'))calendarSyncOpen();
 if(b.hasAttribute('data-calendar-child')){calendarJump++;if(!selectChild(b.dataset.calendarChild))return;render()}
 if(b.dataset.calendarShift)calendarNavigate(calendarAdd(calendarState.day,Number(b.dataset.calendarShift)));
 if(b.hasAttribute('data-calendar-current'))calendarNavigate(data.today);
 if(b.hasAttribute('data-calendar-weekend')||b.hasAttribute('data-calendar-weekend-home')){calendarNavigate(calendarAdd(calendarMonday(data.today),5));$('#calendarWeekend')?.scrollIntoView({behavior:'auto',block:'center'})}
 if(b.dataset.calendarDay){calendarJump++;calendarState.day=b.dataset.calendarDay;const left=$('.calendar-week-scroll')?.scrollLeft||0;render();const strip=$('.calendar-week-scroll');if(strip)strip.scrollLeft=left;if(b.hasAttribute('data-calendar-detail')){$('#calendarDayDetails')?.scrollIntoView({block:'start'});$('#calendarDayDetails')?.focus({preventScroll:true})}}
 if(b.hasAttribute('data-calendar-retry')){calendarInvalidate();render()}
 if(b.hasAttribute('data-calendar-new'))calendarOpen(null,{day:b.dataset.calendarNew});
 if(b.hasAttribute('data-calendar-resume'))$(occurrencePending?'#calendarOccurrenceDialog':'#calendarDialog').showModal();
 if(b.dataset.calendarOnce){const e=occurrenceEvents().find(x=>x.id===b.dataset.calendarOnce&&x.day===b.dataset.occurrenceDay);if(e)occurrenceOpen(e);return}
 if(b.dataset.calendarComplete){const event=calendarState.result?.events.find(x=>x.id===b.dataset.calendarComplete)||(data.today_calendar?.inbox||[]).find(x=>x.kind==='event'&&x.event.id===b.dataset.calendarComplete)?.event;if(event&&calendarOpen(event)){$('#calendarForm').elements.status.value='completed';$('#calendarDialogTitle').textContent='核对后确认完成'}}
 if(b.dataset.calendarEdit){const event=calendarState.result?.events.find(x=>x.id===b.dataset.calendarEdit&&x.editable)||(data.today_calendar?.inbox||[]).find(x=>x.kind==='event'&&x.event.id===b.dataset.calendarEdit)?.event;if(event)calendarOpen(event)}
 if(b.dataset.calendarDraft){const kind=b.dataset.calendarDraft;calendarOpen(null,{day:$('#calendarWeekendDay').value,title:{'运动':'一起留一段运动时间','自由探索':'一段自由探索时间','共读':'一起读一会儿'}[kind],category:kind==='共读'?'family':'activity',status:'tentative',note:'先和孩子商量想做什么、何时开始，以及需要准备什么。'})}
 if(b.dataset.calendarTask){
  const seq=++calendarJump,id=b.dataset.calendarTask;b.disabled=true;
  try{await load();if(seq!==calendarJump||page!=='calendar')return;const t=data.tasks.find(x=>x.id===id);if(!t){toast('原事项当前未找到，请在来源与附件核对。');return}if(!selectChild(data.children.find(c=>c.name===t.child)?.id))return;taskView='全部';page='tasks';render();const target=[...document.querySelectorAll('[data-query-target]')].find(x=>x.dataset.queryTarget==='task:'+id);target?.scrollIntoView({block:'center'});target?.focus({preventScroll:true})}catch{toast('读取原事项失败，请重试。')}finally{if(b.isConnected)b.disabled=false}
 }
});

document.addEventListener('change',e=>{if(e.target.matches('[data-agenda-date]')&&exactTaskDay(e.target.value))calendarNavigate(e.target.value)});


function timetableLock(value){timetableBusy=value;$('#timetableFields').disabled=value||!!timetablePending;$('#timetableForm [type=submit]').disabled=value;$('#timetableForm [data-close]').disabled=value}
let timetableBusy=false,timetableRows=[],timetableID='',timetableVersion=0,timetableUploads=[],timetablePending=null;
function timetableLines(week){return week.flatMap(w=>w.sessions.map(s=>'周'+'一二三四五六日'[w.weekday-1]+'｜'+s.slot+'｜'+s.title)).join('\n')}
function timetableWeek(text){
 const days=new Map();
 for(const line of text.split('\n').filter(v=>v.trim())){const m=line.trim().match(/^(?:周|星期)([一二三四五六日天1-7])(?:｜|\|)([^｜|]+)(?:｜|\|)(.+)$/)||line.trim().match(/^(?:周|星期)([一二三四五六日天1-7])\s+(\S+)\s+(.+)$/);if(!m)throw Error('请每行写一节，例如：周一 第一节 语文');const day='1234567'.includes(m[1])?Number(m[1]):'一二三四五六日'.indexOf(m[1]==='天'?'日':m[1])+1;if(!days.has(day))days.set(day,[]);days.get(day).push({slot:m[2],title:m[3]})}
 return [...days].sort((a,b)=>a[0]-b[0]).map(([weekday,sessions])=>({weekday,sessions}));
}
function timetableOriginals(){ $('#timetableOriginals').innerHTML=timetableUploads.map(id=>{const a=data.uploads.find(a=>a.id===id);return (a?uploadHTML(a):'<p>原件仍保留，可在来源与附件查看。</p>')+`<button type="button" data-timetable-detach="${esc(id)}">移除这张照片</button>`}).join('') }
function timetableFill(row){
 const f=$('#timetableForm');f.reset();timetableID=row?.id||crypto.randomUUID().replaceAll('-','');timetableVersion=row?.version||0;timetableUploads=[...(row?.attachments||[])];timetablePending=null;
 f.elements.child_id.value=row?.child_id||calendarState.childID||data.children.find(c=>c.name===child)?.id||data.children[0]?.id||'';
 for(const k of ['title','effective_from','effective_until','note'])f.elements[k].value=row?.[k]||(k==='title'?'学校课表':'');
 f.elements.child_id.disabled=!!row;f.elements.lessons.value=row?timetableLines(row.week):'';$('#timetableSaved').value=row?.id||'';
 $('#timetableTitle').textContent=row?'更正课表':'导入课表';for(const id of ['timetableError','timetableUploadStatus','timetableDraftStatus'])$('#'+id).textContent='';timetableOriginals();
}
async function timetableOpen(id='',upload=''){
 if(timetableBusy)return;if(timetablePending){$('#timetableDialog').showModal();$('#timetableError').textContent='上次保存结果尚未核对，请保留原内容，再点确认重试。';return}const f=$('#timetableForm');f.elements.child_id.innerHTML=data.children.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');$('#timetableDialog').showModal();
 if(timetablePending){$('#timetableError').textContent='上次保存结果尚未核对，请保留原内容，再点确认重试。';return}
 timetableLock(true);
 try{const r=await apiFetch('/api/calendar/timetables',{signal:AbortSignal.timeout(15000)}),v=await r.json();if(!r.ok)throw Error(v.error||'课表列表暂时无法读取');timetableRows=v.timetables;$('#timetableSaved').innerHTML='<option value="">新增一份课表</option>'+timetableRows.map(t=>`<option value="${esc(t.id)}">${esc(calendarNames([t.child_id]))} · ${esc(t.title)}</option>`).join('');const row=id?timetableRows.find(t=>t.id===id):null;if(id&&!row)throw Error('这份课表暂时找不到，请重试');timetableFill(row);if(upload){timetableUploads=[upload];timetableOriginals();$('#timetableUploadStatus').textContent='原件已保存，请识别并核对课表。'} }
 catch(err){$('#timetableError').textContent=err.message||'读取课表失败，请关闭后重试'}finally{timetableLock(false)}
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-timetable-open],[data-timetable-edit],[data-timetable-upload]');if(b&&['timetableOpen','timetableEdit','timetableUpload'].some(k=>k in b.dataset))timetableOpen(b.dataset.timetableEdit||'',b.dataset.timetableUpload||'')});
$('#timetableSaved').onchange=e=>{if(!timetableBusy&&!timetablePending)timetableFill(timetableRows.find(t=>t.id===e.target.value))};
$('#timetableFile').onchange=async e=>{
 const file=e.target.files[0];e.target.value='';if(!file||timetableBusy)return;timetableLock(true);$('#timetableUploadStatus').textContent='正在保存原件…';
 try{if(timetableUploads.length>=3)throw Error('每份课表最多三张图片');if(!file.size||file.size>20*1024*1024)throw Error('照片为空或超过20MB');if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw Error('请使用JPG、PNG或WebP课表照片');const r=await apiFetch('/api/upload',{method:'POST',signal:AbortSignal.timeout(120000),headers:{'X-Family-Token':data.token,'X-File-Name':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'},body:file}),v=await r.json();if(!r.ok)throw Error(v.error||'上传失败');data.uploads.unshift(v.attachment);timetableUploads.push(v.attachment.id);timetableOriginals();$('#timetableUploadStatus').textContent='原件已保存。下一步：识别课表，再核对后加入日历。';$('#timetableForm').elements.confirmed.checked=false}
 catch(err){$('#timetableUploadStatus').textContent=(err.name==='TimeoutError'?'上传超时，请在来源与附件核对是否已保存，再重试':err.message)+'。尚未加入日历。'}finally{timetableLock(false)}
};
$('#timetableRecognize').onclick=async()=>{
 if(timetableBusy)return;const f=$('#timetableForm');timetableLock(true);$('#timetableDraftStatus').textContent='正在识别课表，原件和填写内容保留…';
 try{const r=await apiFetch('/api/calendar/timetable/draft',{method:'POST',signal:AbortSignal.timeout(90000),headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify({child_id:f.elements.child_id.value,text:$('#timetableText').value,attachments:timetableUploads})}),v=await r.json();if(!r.ok)throw Error(v.error||'识别失败');if(v.child_id!==f.elements.child_id.value)throw Error('孩子归属已变化，请重新核对');if(v.draft.week.some(w=>w.sessions.length))f.elements.lessons.value=timetableLines(v.draft.week);f.elements.confirmed.checked=false;if(v.draft.uncertainties.length){const note=[f.elements.note.value,'识别待核对：'+v.draft.uncertainties.join('；')].filter(Boolean).join('\n');if(note.length<=4000)f.elements.note.value=note;}$('#timetableDraftStatus').textContent=(v.draft.week.length?'识别完成，请核对下方课程并填写适用日期。':'没有识别到明确课程，请补充清晰图片或手动填写。')+(v.draft.uncertainties.length?' 待核对：'+v.draft.uncertainties.join('；'):''); }
 catch(err){$('#timetableDraftStatus').textContent=(err.name==='TimeoutError'?'识别超时，可重试或手动填写':err.message)+'。输入与已上传原件保留，尚未加入日历。'}finally{timetableLock(false)}
};
$('#timetableForm').onsubmit=async e=>{
 e.preventDefault();if(timetableBusy)return;const f=e.target;
 try{const body={id:timetableID,version:timetableVersion,child_id:f.elements.child_id.value,title:f.elements.title.value,effective_from:f.elements.effective_from.value,effective_until:f.elements.effective_until.value,note:f.elements.note.value,week:timetableWeek(f.elements.lessons.value),attachments:timetableUploads};if(timetablePending&&JSON.stringify(body)!==JSON.stringify(timetablePending))throw Error('上次保存结果尚未核对，请保留原内容重试');timetablePending=body;timetableLock(true);$('#timetableError').textContent='正在保存课表…';
 const r=await apiFetch('/api/calendar/timetable/save',{method:'POST',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)}),v=await r.json();if(!r.ok){if(r.status<500)timetablePending=null;throw Error(v.error||'课表保存失败')}timetablePending=null;$('#timetableDialog').close();page='calendar';calendarState.day=v.timetable.effective_from;calendarState.week=calendarMonday(calendarState.day);calendarState.childID=v.timetable.child_id;calendarInvalidate();try{await load();toast('课表已加入日历，按适用日期每周显示')}catch{render();toast('课表已保存，页面暂未刷新，请点刷新记录')}
 }catch(err){$('#timetableError').textContent=(err.name==='TimeoutError'?'保存结果尚未确认，请用原内容重试':err.message)+'。输入已保留。'}finally{timetableLock(false)}
};
$('#timetableDialog').addEventListener('cancel',e=>{if(timetableBusy)e.preventDefault()});

document.addEventListener('click',e=>{const b=e.target.closest('[data-timetable-detach]');if(b?.dataset.timetableDetach&&!timetableBusy&&!timetablePending){timetableUploads=timetableUploads.filter(id=>id!==b.dataset.timetableDetach);timetableOriginals();$('#timetableForm').elements.confirmed.checked=false;$('#timetableUploadStatus').textContent='已从本课表移除，原件仍保存在资料中。'}});

// One explicit occurrence uses the existing event record, never another repeating series.
function occurrenceEvents(){return [...(calendarState.result?.events||[]),...(data.today_calendar?.events||[]),...(data.today_calendar?.inbox||[]).filter(x=>x.kind==='event').map(x=>x.event)]}
function occurrenceKey(e){const o=e.occurrence;return o.series_id+'/'+o.day+'/'+o.slot_id}
function occurrenceValues(){return Object.fromEntries(new FormData($('#calendarOccurrenceForm')))}
function occurrenceDirty(){return occurrenceContext&&JSON.stringify(occurrenceValues())!==occurrenceContext.initial}
function occurrenceHistory(e){const o=e.occurrence,original=o.original||{};return `<p>原日期：${esc(o.day)} · ${esc(original.start_time||'时间未定')}${original.end_time?'–'+esc(original.end_time):''}</p>${original.note?`<p class="source">原说明：${esc(original.note)}</p>`:''}${(o.history||[]).map(h=>`<p class="source">${esc(new Date(h.at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))} · ${esc(calendarStatuses[h.status])} · ${esc(h.day)} ${esc(h.start_time)}${h.end_time?'–'+esc(h.end_time):''}${h.note?'\n'+esc(h.note):''}</p>`).join('')}`}
function occurrenceHeader(e){$('#calendarOccurrenceContext').textContent=calendarNames(e.child_ids)+' · '+e.title;$('#calendarOccurrenceHistory').innerHTML=occurrenceHistory(e);$('#calendarOccurrenceSummary').textContent='原安排：'+e.occurrence.day+' '+(e.occurrence.original?.start_time||'时间未定')+' · 更改记录'}
function occurrenceLock(){const locked=occurrenceSaving||!!occurrencePending;$('#calendarOccurrenceFields').disabled=locked;$('#calendarOccurrenceSave').disabled=occurrenceSaving||occurrenceConflict;$('#calendarOccurrenceClose').disabled=occurrenceSaving;$('#calendarOccurrenceRefresh').hidden=!occurrenceConflict;$('#calendarOccurrenceRefresh').disabled=occurrenceSaving;$('#calendarOccurrenceSave').textContent=occurrencePending?'核对并重试这次保存':'保存这一次'}
function occurrenceOpen(e){
 if(occurrenceSaving||calendarSaving)return;
 if(calendarPending){$('#calendarDialog').showModal();return}
 if(occurrencePending){$('#calendarOccurrenceDialog').showModal();return}
 if(!e.occurrence?.series_id)return;
 if(occurrenceContext&&occurrenceKey(e)===occurrenceKey(occurrenceContext.event)&&!occurrenceConflict){$('#calendarOccurrenceDialog').showModal();return}
 if(occurrenceDirty()&&!confirm('切换安排会清除这份尚未保存的输入，继续吗？'))return;
 const f=$('#calendarOccurrenceForm');f.reset();for(const k of ['day','start_time','end_time','status','note'])f.elements[k].value=e[k]||'';
 occurrenceContext={event:e,initial:JSON.stringify(occurrenceValues())};occurrenceConflict=false;occurrenceHeader(e);$('#calendarOccurrenceStatus').textContent='';occurrenceLock();$('#calendarOccurrenceDialog').showModal();
}
$('#calendarOccurrenceForm').onsubmit=async e=>{
 e.preventDefault();if(occurrenceSaving||occurrenceConflict||!occurrenceContext)return;
 if(!occurrencePending){const o=occurrenceContext.event.occurrence;occurrencePending=JSON.stringify({...occurrenceValues(),series_id:o.series_id,series_version:o.series_version,origin_day:o.day,slot_id:o.slot_id,version:o.version})}
 occurrenceSaving=true;$('#calendarOccurrenceStatus').textContent='正在保存这一次…';occurrenceLock();
 try{
  const r=await apiFetch('/api/calendar/occurrence',{method:'POST',signal:AbortSignal.timeout(20000),headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:occurrencePending}),v=await r.json();
  if(!r.ok){if([400,404,409].includes(r.status))occurrencePending=null;if(r.status===409)occurrenceConflict=true;throw Error(v.error||'保存未完成')}
  if(!v.event?.id||!v.event.occurrence?.series_id)throw Error('保存回执尚未核对，请重试原请求');
  occurrencePending=null;occurrenceContext=null;$('#calendarOccurrenceDialog').close();calendarState.day=v.event.day;calendarState.week=calendarMonday(v.event.day);page='calendar';calendarInvalidate();
  try{await load();toast('这次安排已保存，其余日期保留')}catch{render();toast('已经保存，最新日历暂时无法读取，请重试读取')}
 }catch(err){$('#calendarOccurrenceStatus').textContent=(['AbortError','TimeoutError'].includes(err.name)?'保存回执超时':err.message||'保存暂未完成')+'；输入保留。'+(occurrencePending?'请重试同一次保存。':occurrenceConflict?'请读取最新状态后核对。':'请核对后再保存。')}
 finally{occurrenceSaving=false;occurrenceLock()}
};
$('#calendarOccurrenceRefresh').onclick=async()=>{
 if(occurrenceSaving||!occurrenceContext)return;const old=occurrenceContext.event,o=old.occurrence,typed=occurrenceValues(),initial=JSON.parse(occurrenceContext.initial);occurrenceSaving=true;occurrenceLock();
 try{
  await load();let fresh=(data.today_calendar?.inbox||[]).filter(x=>x.kind==='event').map(x=>x.event).find(e=>e.occurrence?.series_id&&occurrenceKey(e)===occurrenceKey(old)&&e.occurrence.version>0);
  if(!fresh){const r=await apiFetch('/api/calendar?start='+o.day+'&end='+o.day,{signal:AbortSignal.timeout(20000)}),v=await r.json();if(!r.ok)throw Error(v.error||'读取失败');fresh=v.events.find(e=>e.occurrence?.series_id&&occurrenceKey(e)===occurrenceKey(old))}
  if(!fresh)throw Error('原计划已不包含这一次，请返回日历重新选择');
  if([...fresh.child_ids].sort().join()!==[...old.child_ids].sort().join())throw Error('参加孩子已变化，请返回日历重新打开这次安排');
  const baseline=Object.fromEntries(Object.keys(initial).map(k=>[k,fresh[k]||''])),updated=[],labels={day:'日期',start_time:'开始时间',end_time:'结束时间',status:'状态',note:'说明'};
  for(const k of Object.keys(initial))if(typed[k]===initial[k]){if(typed[k]!==baseline[k])updated.push(labels[k]);$('#calendarOccurrenceForm').elements[k].value=baseline[k]}
  occurrenceContext={event:fresh,initial:JSON.stringify(baseline)};occurrenceConflict=false;occurrenceHeader(fresh);$('#calendarOccurrenceStatus').textContent='最新记录：'+calendarStatuses[fresh.status]+' · '+fresh.day+' '+(fresh.start_time||'时间未定')+'。'+(updated.length?'你未修改的'+updated.join('、')+'已更新。':'')+'你的修改已保留，请核对后再次保存。';
 }catch(err){$('#calendarOccurrenceStatus').textContent=err.message||'读取最新状态失败，可以重试'}finally{occurrenceSaving=false;occurrenceLock()}
};
$('#calendarOccurrenceClose').onclick=()=>{if(!occurrenceSaving)$('#calendarOccurrenceDialog').close()};
$('#calendarOccurrenceDialog').addEventListener('cancel',e=>{if(occurrenceSaving)e.preventDefault()});
window.addEventListener('beforeunload',e=>{if(occurrencePending||occurrenceDirty()){e.preventDefault();e.returnValue=''}});
