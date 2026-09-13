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
function calendarItems(items,day){return items.filter(x=>x.day===day&&(!calendarState.childID||(x.child_ids||[x.child_id]).includes(calendarState.childID)))}
function calendarInvalidate(keep=false){calendarState.sequence++;calendarState.controller?.abort();calendarState.loading=false;calendarState.dirty=true;if(!keep){calendarState.result=null;calendarState.range=''}calendarState.error=''}
window.FamilyCalendar={invalidate:calendarInvalidate,hasPending:()=>!!(calendarPending||occurrencePending),openDraft:calendarOpenAssistant,openCitation:calendarOpenCitation,leave(){if(calendarState.visible){calendarJump++;calendarState.visible=false;calendarState.sequence++;calendarState.controller?.abort();calendarState.loading=false}}};
function calendarHomeHTML(){return `<section class="calendar-entry"><span aria-hidden="true">▦</span><div><h2>把一周留给成长</h2><p>上学、探索、一起度过的时间，放在同一张日历里。</p></div><div class="calendar-entry-actions"><button class="primary" data-page="calendar">打开成长日历</button><button data-calendar-weekend-home>看看本周末</button></div></section>`}
function calendarRepeatLabel(e){const mode={none:'',daily:'每天',weekly:'每周',weekends:'周末',monthly:'每月'}[e.repeat]||'';return mode+(e.repeat_days?.length?' '+e.repeat_days.map(d=>e.repeat==='weekly'?'周'+'一二三四五六日'[d-1]:d+'日').join('、'):'')}
function calendarEventHTML(e){
 const t=e.task_id?data.tasks.find(t=>t.id===e.task_id&&e.child_ids.includes(data.children.find(c=>c.name===t.child)?.id)):null;
 return `<article tabindex="-1" data-query-target="calendar:${esc(e.id)}:${esc(e.day)}" class="calendar-event ${e.status==='cancelled'?'calendar-cancelled':''}"><div class="calendar-event-meta"><span>${esc(calendarKinds[e.category]||'安排')}</span><span class="calendar-status calendar-${esc(e.status)}">${esc(calendarStatuses[e.status]||'状态待核对')}</span></div><h3>${esc(e.title)}</h3><p class="calendar-time">${esc(e.day)} · ${e.start_time?esc(e.start_time)+(e.end_time?'–'+esc(e.end_time):''):'时间未填写'}</p><p class="calendar-who">${esc(calendarNames(e.child_ids))}${calendarRepeatLabel(e)?' · '+esc(calendarRepeatLabel(e)):''}</p>${e.location?`<p class="calendar-location">⌖ ${esc(e.location)}</p>`:''}${e.note?`<p class="source calendar-requirements">${esc(e.note)}</p>`:''}${e.source||e.repeat!=='none'?`<details><summary>出处与重复规则</summary>${e.source?`<p class="source">出处：${esc(e.source)}</p>`:''}${e.repeat!=='none'?`<p>起点 ${esc(e.series_day)}${e.until?' · 截至 '+esc(e.until):' · 未设截止'}</p>`:''}</details>`:''}${t?`<p class="calendar-task-status ${taskDismissed(t)?'calendar-family-decision':''}">${taskDismissed(t)?esc(t.child)+'：':'清单：'}${esc(taskStatusLabel(status(t)))}</p>`:''}${e.task_id?`<button class="calendar-card-action" data-calendar-task="${esc(e.task_id)}">核对原事项 →</button>`:''}${e.editable&&!e.occurrence?.series_id&&e.repeat==='none'&&!['cancelled','completed'].includes(e.status)?`<button data-calendar-complete="${esc(e.id)}">确认完成</button>`:''}${e.occurrence?.series_id?`<p class="small muted">${e.occurrence.day!==e.day?'从 '+esc(e.occurrence.day)+' 改期 · ':''}本次记录独立保留</p><button data-calendar-once="${esc(e.id)}" data-occurrence-day="${esc(e.day)}">处理本次</button>`:''}${e.editable&&(!e.occurrence?.series_id||e.repeat!=='none')?`<button class="calendar-card-action" data-calendar-edit="${esc(e.id)}">${e.repeat!=='none'?'编辑重复规则':'编辑安排'}</button>`:''}</article>`;
}
function calendarTimetableHTML(t){return `<details tabindex="-1" data-query-target="timetable:${esc(t.id)}:${esc(t.day)}" class="calendar-timetable"><summary><span>课表 · ${esc(calendarNames([t.child_id]))}</span><small>${t.sessions.length} 个节次</small></summary><p class="small">${esc(t.title)}</p><ol>${t.sessions.map(s=>`<li><span>${esc(s.slot)}</span><strong>${esc(s.title)}</strong></li>`).join('')}</ol>${t.note?`<p class="source small">${esc(t.note)}</p>`:''}${t.source?`<p class="source small">出处：${esc(t.source)}</p>`:''}${(t.uploads||[]).map(id=>`<a href="${endpoint('/upload/')}${encodeURIComponent(id)}" target="_blank" rel="noopener">查看课表原件</a>`).join(' ')}${t.import_id?`<button data-timetable-edit="${esc(t.import_id)}">更正课表</button>`:''}${t.attachment?`<a href="${endpoint('/attachment/')}${encodeURIComponent(t.attachment)}" target="_blank" rel="noopener">查看课表原件 ↗</a>`:''}<p class="small muted">按已提供节次展示，未填写的钟点和单双周仍待核对。</p></details>`}
function agendaDateHTML(m,day=data.today){return `<p class="agenda-dates"><span>发布：${esc(m.published_on||'待核对')}</span><span>${m.due_on?`${m.due_on<day?'逾期 · ':''}截止：${esc(m.due_on)}`:'截止待核对'}</span>${m.scheduled_on?`<span>计划：${esc(m.scheduled_on)}</span>`:''}</p>`}
function agendaItemHTML(item){
 if(item.kind==='event')return calendarEventHTML(item.event);
 if(item.kind==='study')return agendaStudyHTML(item);
 if(item.kind==='task'){const t=data.tasks.find(t=>t.id===item.task_id);if(t?.focus?.box==='wish')return wishTaskHTML(t);return t?`<div class="agenda-task">${taskHTML(t,{compact:true})}</div>`:''}
 const source=(data.agent?.items||[]).find(x=>x.id===item.id);
 return `<div class="agenda-school">${source?agentItemHTML(source,{compact:true,agenda:item.agenda}):`<h3>${esc(item.title)}</h3><p>此条尚未载入详情，请在学校信息中核对。</p><button data-page="agent">查看学校信息</button>`}</div>`;
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
  const groups=[['作业',rows.filter(x=>x.kind==='study'||x.agenda?.category==='homework')],['待办',rows.filter(x=>x.kind!=='study'&&x.agenda?.category!=='homework')]];
  const item=(title,meta,closed=false)=>`<button class="calendar-week-item${closed?' is-closed':''}" data-calendar-day="${day}" data-calendar-detail><strong>${esc(title)}</strong><small>${esc(meta)}</small></button>`;
  return `<section class="calendar-day${day===data.today?' is-today':''}" data-calendar-column="${day}"><button class="calendar-day-heading" data-calendar-day="${day}" data-calendar-detail aria-pressed="${day===calendarState.day}" ${day===data.today?'aria-current="date"':''}><span>周${'一二三四五六日'[i]}</span><strong>${Number(day.slice(5,7))}/${Number(day.slice(8))}</strong>${day===data.today?'<small>今天</small>':''}</button><div class="calendar-day-body">${groups.map(([label,list])=>list.length?`<h3>${label}</h3>${list.map(x=>item(x.title||data.tasks.find(t=>t.id===x.task_id)?.title||'事项待核对',[calendarNames(x.child_ids),x.kind==='school'?'待核对':x.kind==='study'?calendarStudyStatus(x):taskStatusLabel(x.status)].filter(Boolean).join(' · '),x.closed)).join('')}`:'').join('')}${events.length?`<h3>计划</h3>${events.map(x=>item(x.title,[x.start_time||'时间待定',calendarNames(x.child_ids),calendarStatuses[x.status]].join(' · '),['completed','cancelled'].includes(x.status))).join('')}`:''}${tables.length?`<h3>课表</h3>${tables.map(x=>item(x.sessions.map(s=>s.title).join(' · '),calendarNames([x.child_id]))).join('')}`:''}${!rows.length&&!events.length&&!tables.length?'<p class="small muted">暂无已收录安排</p>':''}</div></section>`;
 }).join('')}</div></div>`;
}
function calendarAgendaHTML(){
 if(calendarState.loading&&!calendarState.result)return '<p role="status">正在读取安排…</p>';
 if(calendarState.error)return `<p class="error" role="alert">${esc(calendarState.error)}</p><button data-calendar-retry>重试</button>`;
 if(!calendarState.result)return '<p role="status">准备读取日历…</p>';
 const r=calendarState.result,day=calendarState.day,items=calendarDayItems(day);
 const groups=[['homework','课内作业'],['todo','待办事项']];
 const section=(title,html)=>`<section class="card agenda-group"><h2>${title}</h2>${html||'<p class="small muted">没有已收录的事项</p>'}</section>`;
 return `${r.source_error?`<p class="error">${esc(r.source_error)}</p>`:''}${calendarWeekHTML()}<h2 class="agenda-day-title" id="calendarDayDetails" tabindex="-1">${esc(day)}${day===data.today?' · 今天':''} · 当天详情</h2><div class="agenda-groups">${groups.map(([kind,label])=>section(label,items.filter(x=>(x.kind==='study'||x.agenda?.category==='homework'?'homework':'todo')===kind).map(agendaItemHTML).join(''))).join('')}${section('手动计划与课程',(calendarItems(r.timetables,day).map(calendarTimetableHTML).join('')||'<p class="small muted">当天课表尚未提供</p>')+calendarItems(r.events,day).map(calendarEventHTML).join(''))}</div><p class="small muted">限期事项每天显示直到完成；逾期继续保留。未明确日期的事项在收集箱核对。</p>`;
}
function calendarHTML(){
 if(!calendarState.week){calendarState.week=calendarMonday(data.today);calendarState.day=data.today;calendarState.result=data.today_calendar;calendarState.range=data.today+'/'+data.today}
 if(!calendarState.visible){calendarState.childID=data.children.find(c=>c.name===child)?.id||'';calendarState.visible=true}
 if(calendarState.childID&&!data.children.some(c=>c.id===calendarState.childID))calendarState.childID='';
 return `<section class="calendar-heading"><div><h1>家庭日历</h1></div><div class="toolbar"><button class="primary" data-calendar-new="${calendarState.day}">＋ 新建计划</button><button data-calendar-ask>说一句安排</button><details class="calendar-tools"><summary>课表与设置</summary><div class="toolbar"><button data-timetable-open>导入 / 管理课表</button><button data-calendar-sync>同步到手机</button><button data-new-task="yes">收集事务</button></div></details></div></section><div class="calendar-controls"><button data-calendar-shift="-7" aria-label="上一周">‹</button><label><span class="sr-only">跳到日期</span><input type="date" data-agenda-date value="${calendarState.day}"></label><button data-calendar-shift="7" aria-label="下一周">›</button><button data-calendar-current>今天</button></div><div class="calendar-kids"><button data-calendar-child="" aria-pressed="${!calendarState.childID}">全部孩子</button>${data.children.map(c=>`<button data-calendar-child="${esc(c.id)}" aria-pressed="${c.id===calendarState.childID}">${esc(c.name)}</button>`).join('')}</div>${calendarPending||occurrencePending?'<p role="status">上次保存未确认。<button data-calendar-resume>继续核对</button></p>':''}<div id="calendarAgenda">${calendarAgendaHTML()}</div>`;
}
function taskInboxItems(){return (data.today_calendar?.inbox||[]).filter(x=>!child||x.child_ids.includes(data.children.find(c=>c.name===child)?.id))}
function taskItemCompleted(x){return x.closed&&(x.kind==='task'?x.status==='已完成':x.kind==='event'?x.event.status==='completed':x.kind==='study'&&x.result==='完成'&&x.result_actor==='parent')}
function taskItemOverdue(x){const day=exactTaskDay(x.agenda.due_on||x.agenda.scheduled_on);return !x.closed&&x.agenda.box!=='wish'&&(!x.event?.repeat||x.event.repeat==='none')&&!!day&&day<data.today}
function taskBoxes(){const all=taskInboxItems(),open=all.filter(x=>!x.closed);return {'Inbox':open.filter(x=>x.agenda.box!=='wish'),'Wish':open.filter(x=>x.agenda.box==='wish'),'计划':open.filter(x=>x.agenda.box!=='wish'&&x.agenda.scheduled_on),'已完成':all.filter(taskItemCompleted),'已逾期':all.filter(taskItemOverdue),'已搁置':all.filter(x=>x.closed&&!taskItemCompleted(x)),'全部':all}}
function taskBoxesHTML(){return `<div class="tasktabs task-boxes">${Object.entries(taskBoxes()).sort(([a],[b])=>a==='全部'?-1:b==='全部'?1:0).map(([name,rows])=>`<button data-task-box="${name}" aria-pressed="${page==='tasks'&&taskView===name}">${({Inbox:'收集箱',Wish:'心愿'})[name]||name} <span>${rows.length}</span></button>`).join('')}</div>`}
function wishTaskHTML(t){return `<article class="task wish-task" data-query-target="task:${esc(t.id)}"><span class="chip">${esc(t.child)} · 心愿</span><h3>${esc(t.title)}</h3>${taskActionHTML(t)}<div class="tasktools">${!taskClosed(t)?`<button class="primary" data-task-plan="${esc(t.id)}">转成计划</button><button data-task-focus="${esc(t.id)}">编辑心愿</button><button data-task-decisions="${esc(t.id)}">暂时放下</button>`:`<button data-task-restore="${esc(t.id)}">恢复心愿</button>`}</div></article>`}
function taskGroupsHTML(items,homeworkLabel='课内作业'){
 return [['homework',homeworkLabel],['todo','待办事项']].map(([kind,label])=>{
  const rows=items.filter(x=>(x.agenda.category==='homework'?'homework':'todo')===kind),confirmed=rows.filter(x=>x.kind!=='school'),pending=rows.filter(x=>x.kind==='school');
  return `<section class="card agenda-group" id="task-group-${kind}" tabindex="-1"><div class="task-group-heading"><h2>${label} · ${confirmed.length}${pending.length?` <span class="review-badge">待核对 ${pending.length}</span>`:''}</h2>${homeworkLabel==='今日作业'?`<button class="task-show-all" data-task-all="${kind}">所有${kind==='homework'?'作业':'待办'} →</button>`:''}</div>${confirmed.map(agendaItemHTML).join('')||'<p class="small muted">暂无已确认事项</p>'}${pending.map(agendaItemHTML).join('')}</section>`;
 }).join('');
}
function taskInboxHTML(){
 if(!Array.isArray(data.today_calendar?.inbox))return `<h1>事务收集箱</h1><p role="alert" class="error">${esc(data.today_calendar?.source_error||'收集箱暂时无法读取，请刷新记录；不能据此判断没有待办。')}</p>`;
 const views=taskBoxes();if(!(taskView in views))taskView='Inbox';
 return `<header class="today-heading"><h1>${taskView==='Wish'?'心愿清单':taskView==='全部'?'所有作业与待办':'收集箱'}</h1><button class="primary" data-new-task="${taskView==='Wish'?'wish':'yes'}">${taskView==='Wish'?'＋ 记心愿':'＋ 记一件事'}</button></header>${filters()}${taskBoxesHTML()}<p class="small muted">${({'Inbox':'所有未完成事务，包含已安排和已逾期的事项。','Wish':'想做的事先留在这里，选定日期再转成计划。','计划':'已安排日期、尚未完成的事项。','已完成':'已确认完成的事项，可撤销完成。','已逾期':'截止日已过；未填截止日时按计划日判断。重复安排不计入。','已搁置':'不参加、无需处理、已取消等事项，保留原决定。','全部':'所有日期的作业与待办，包含未完成、已完成及已搁置；心愿单独标注。'})[taskView]}</p>${taskView==='Wish'?`<section class="card checklist">${views[taskView].map(agendaItemHTML).join('')||'<p>这里暂时没有心愿。</p>'}</section>`:`<div class="today-task-groups">${taskGroupsHTML(views[taskView])}</div>`}`;
}
function todayTasksHTML(){
 const r=data.today_calendar;if(!Array.isArray(r?.inbox))return taskInboxHTML();
 const matches=x=>!child||(x.child_ids||[x.child_id]).includes(data.children.find(c=>c.name===child)?.id);
 const items=taskInboxItems().filter(x=>!x.closed&&x.kind!=='event'&&x.agenda.box!=='wish'&&(!x.agenda.published_on||x.agenda.published_on<=data.today)&&(!x.agenda.scheduled_on||x.agenda.scheduled_on<=data.today||x.agenda.due_on));
 const plans=(r.timetables||[]).filter(matches).map(calendarTimetableHTML).join('')+(r.events||[]).filter(x=>matches(x)&&!['cancelled','completed'].includes(x.status)).map(calendarEventHTML).join('');
 return `<header class="today-heading"><div><h1>今天</h1><p>${esc(data.today)}</p></div><button class="primary" data-new-task="yes">＋ 记一件事</button></header>${sourceCoverageHTML()}${r.source_error?`<p class="error" role="status">${esc(r.source_error)}</p>`:''}<div class="today-controls">${filters()}<div class="today-sections" aria-label="跳到事务分类"><a href="#task-group-homework">作业 ${items.filter(x=>x.agenda.category==='homework'&&x.kind!=='school').length}</a><a href="#task-group-todo">待办 ${items.filter(x=>x.agenda.category!=='homework'&&x.kind!=='school').length}</a></div></div><div class="today-task-groups">${taskGroupsHTML(items,'今日作业')}</div>${plans?`<section class="card agenda-group"><h2>课表与计划</h2>${plans}</section>`:''}<p class="small muted">未完成事项继续保留；待核对通知需确认后才成为任务。</p>`;
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
function calendarUUID(){return crypto.randomUUID().replaceAll('-','')}
function calendarOpen(event=null,preset={}){
 if(calendarSaving||occurrenceSaving)return false;
 if(occurrencePending){$('#calendarOccurrenceDialog').showModal();return false}
 if(calendarPending){$('#calendarDialog').showModal();return false}
 calendarRememberDraft();calendarDraftContext=null;
 document.getElementById?.('calendarDraftDetails')?.remove();
 const e=event||{id:calendarUUID(),version:0,child_ids:calendarState.childID?[calendarState.childID]:data.children.map(c=>c.id),title:'',category:'activity',day:calendarState.day||data.today,start_time:'',end_time:'',location:'',note:'',status:'tentative',repeat:'none',until:'',...preset};
 const f=$('#calendarForm');f.reset();for(const k of ['id','version','title','category','start_time','end_time','location','note','status','repeat','until'])f.elements[k].value=e[k]??'';f.elements.day.value=e.series_day||e.day;f.elements.id.value=e.series_id||e.id;f.elements.start_time.value=e.series_start_time??e.start_time;f.elements.end_time.value=e.series_end_time??e.end_time;
 const days=e.repeat_days||[];calendarWeekdaysChosen=e.repeat==='weekly'&&days.length>0;const weekday=new Date((e.series_day||e.day||data.today)+'T12:00:00Z').getUTCDay()||7;for(const input of f.querySelectorAll('[name=repeat_weekday]'))input.checked=(e.repeat==='weekly'&&days.length?days:[weekday]).includes(Number(input.value));f.elements.repeat_monthdays.value=e.repeat==='monthly'?days.join('、'):'';$('#calendarExtraRows').innerHTML=(e.extra_times||[]).map((slot,n)=>calendarExtraHTML(slot,n,e.id===e.series_id+'.'+slot.id)).join('');
 $('#calendarChildChoices').innerHTML=data.children.map(c=>`<label><input type="checkbox" name="child_ids" value="${esc(c.id)}" ${(e.child_ids||[]).includes(c.id)?'checked':''}><span>${esc(c.name)}</span></label>`).join('');
 $('#calendarDialogTitle').textContent=event?'编辑安排':'写下一个安排';$('#calendarEditNote').textContent=event&&event.repeat!=='none'?'修改未单独处理的重复日期；已单独改期、完成或取消的记录保留。':'可以先暂定，和孩子商量后再确定。';$('#calendarFormError').textContent='';$('#calendarRetryNote').textContent='';calendarFormLock(false);calendarRepeat();$('#calendarDialog').showModal();const active=$('#calendarExtraRows').querySelector?.('.is-selected-slot');if(active){active.scrollIntoView({block:'center'});active.focus({preventScroll:true})}return true;
}
function calendarDraftMissing(context){const d=context.form||context.draft;return d?[!d.child_ids?.length?'孩子':'',!d.title?.trim()?'安排内容':'',!d.day?'日期':''].filter(Boolean).join('、'):''}
function calendarDraftDetails(context,id=''){return `<details class="ask-citation" ${id?`id="${esc(id)}"`:''}><summary>原话与核对说明</summary><p class="source">${esc(context.text)}</p>${context.needs_review.length?`<ul>${context.needs_review.map(x=>`<li class="source">${esc(x)}</li>`).join('')}</ul>`:''}</details>`}
function calendarDraftNote(context){const missing=calendarDraftMissing(context);return '按 '+context.reference_date+' 理解相对日期。'+(missing?'待核对：'+missing+'。':'请核对后保存。')}
function calendarRememberDraft(){if(calendarDraftContext&&!calendarSaving&&!calendarPending){calendarDraftContext.form=calendarPayload();$('#calendarEditNote').textContent=calendarDraftNote(calendarDraftContext)}}
function calendarOpenAssistant(context){
 if(calendarSaving||calendarPending)return false;
 if(!context?.draft||context.saved)return false;
 const preset=context.form||{...context.draft,child_ids:context.draft.child_ids||[],day:context.draft.day||''};
 if(!calendarOpen(null,preset))return false;
 calendarDraftContext=context;calendarRememberDraft();
 $('#calendarDialogTitle').textContent='核对一句话安排';
 $('#calendarEditNote').textContent=calendarDraftNote(context);
 $('#calendarEditNote').insertAdjacentHTML('afterend',calendarDraftDetails(context,'calendarDraftDetails'));
 return true;
}
async function calendarOpenCitation(c,childID){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(c.day||'')||!data.children.some(x=>x.id===childID)){toast('原安排的日期或孩子待核对，请重新查询。');return}
 calendarJump++;calendarInvalidate();calendarState.week=calendarMonday(c.day);calendarState.day=c.day;calendarState.childID=childID;calendarState.visible=true;page='calendar';render();
 const seq=calendarState.sequence;
 // render starts the existing read; await that same request instead of a second one.
 if(calendarState.reading)await calendarState.reading;
 if(page!=='calendar'||calendarState.sequence!==seq)return;
 const target=[...document.querySelectorAll('[data-query-target]')].find(el=>el.dataset.queryTarget===c.kind+':'+c.target_id+':'+c.day);
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
$('#calendarCancel').onclick=()=>{if(!calendarSaving){calendarRememberDraft();$('#calendarDialog').close();if(page==='calendar')render()}};
$('#calendarDialog').addEventListener('cancel',e=>{if(calendarSaving)e.preventDefault();else{calendarRememberDraft();if(page==='calendar')setTimeout(render,0)}});
window.addEventListener('beforeunload',e=>{if(calendarPending||calendarDraftContext&&!calendarDraftContext.saved){e.preventDefault();e.returnValue=''}});
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(['homework','todo'].includes(b.dataset.taskAll)){taskView='全部';page='tasks';render();const target=$('#task-group-'+b.dataset.taskAll);target?.scrollIntoView({block:'start'});target?.focus({preventScroll:true});return}
 if(b.dataset.taskBox){taskView=b.dataset.taskBox;page='tasks';render();return}
 if(b.dataset.taskPlan){openTaskFocus(b.dataset.taskPlan);const f=$('#taskFocusForm');f.elements.box.value='inbox';f.elements.scheduled_on.required=true;if(f.elements.category.value==='unknown')f.elements.category.value='todo';$('#taskFocusScheduleLabel').textContent='计划在哪天做 · 必填';$('#taskFocusTitle').textContent='选定日期，转成计划';return}
 if(b.dataset.agendaStudy){studyChildID=b.dataset.agendaStudy;studyDay=b.dataset.agendaDay;studyTaskID='';page='study';render();return}
 if(b.hasAttribute('data-calendar-sync'))calendarSyncOpen();
 if(b.hasAttribute('data-calendar-child')){calendarJump++;calendarState.childID=b.dataset.calendarChild;child=data.children.find(c=>c.id===calendarState.childID)?.name||'';render()}
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
  try{await load();if(seq!==calendarJump||page!=='calendar')return;const t=data.tasks.find(x=>x.id===id);if(!t){toast('原事项当前未找到，请在来源与附件核对。');return}child=t.child;taskView='全部';page='tasks';render();const target=[...document.querySelectorAll('[data-query-target]')].find(x=>x.dataset.queryTarget==='task:'+id);target?.scrollIntoView({block:'center'});target?.focus({preventScroll:true})}catch{toast('读取原事项失败，请重试。')}finally{if(b.isConnected)b.disabled=false}
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
