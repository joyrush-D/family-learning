// Calendar dates are date-only values. UTC arithmetic avoids daylight-saving shifts.
const calendarKinds={school:'学校安排',activity:'课外活动',study:'学习安排',family:'家庭时光',other:'其他'};
const calendarStatuses={tentative:'暂定',confirmed:'已确定',cancelled:'已取消',completed:'已完成'};
const calendarState={week:'',day:'',childID:'',visible:false,result:null,range:'',error:'',loading:false,sequence:0,controller:null};
let calendarPending=null,calendarSaving=false,calendarJump=0,calendarDraftContext=null;
let calendarSyncVersion=0;
function calendarAdd(day,n){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)}
function calendarMonday(day){const n=new Date(day+'T12:00:00Z').getUTCDay();return calendarAdd(day,-((n+6)%7))}
function calendarDays(){return Array.from({length:7},(_,i)=>calendarAdd(calendarState.week,i))}
function calendarNames(ids){return (ids||[]).map(id=>data.children.find(c=>c.id===id)?.name||'档案待核对').join('、')}
function calendarItems(items,day){return items.filter(x=>x.day===day&&(!calendarState.childID||(x.child_ids||[x.child_id]).includes(calendarState.childID)))}
function calendarInvalidate(){calendarState.sequence++;calendarState.controller?.abort();calendarState.loading=false;calendarState.result=null;calendarState.range='';calendarState.error=''}
window.FamilyCalendar={invalidate:calendarInvalidate,hasPending:()=>!!calendarPending,openDraft:calendarOpenAssistant,openCitation:calendarOpenCitation,leave(){if(calendarState.visible){calendarJump++;calendarState.visible=false;calendarState.sequence++;calendarState.controller?.abort();calendarState.loading=false}}};
function calendarHomeHTML(){return `<section class="calendar-entry"><span aria-hidden="true">▦</span><div><h2>把一周留给成长</h2><p>上学、探索、一起度过的时间，放在同一张日历里。</p></div><div class="calendar-entry-actions"><button class="primary" data-page="calendar">打开成长日历</button><button data-calendar-weekend-home>看看本周末</button></div></section>`}
function calendarEventHTML(e){
 const t=e.task_id?data.tasks.find(t=>t.id===e.task_id&&e.child_ids.includes(data.children.find(c=>c.name===t.child)?.id)):null;
 return `<article tabindex="-1" data-query-target="calendar:${esc(e.id)}:${esc(e.day)}" class="calendar-event ${e.status==='cancelled'?'calendar-cancelled':''}"><div class="calendar-event-meta"><span>${esc(calendarKinds[e.category]||'安排')}</span><span class="calendar-status calendar-${esc(e.status)}">${esc(calendarStatuses[e.status]||'状态待核对')}</span></div><h3>${esc(e.title)}</h3><p class="calendar-time">${e.start_time?esc(e.start_time)+(e.end_time?'–'+esc(e.end_time):''):'时间未填写'}</p><p class="calendar-who">${esc(calendarNames(e.child_ids))}${e.repeat==='weekly'?' · 每周':''}</p>${e.location?`<p class="calendar-location">⌖ ${esc(e.location)}</p>`:''}${e.note?`<p class="source calendar-requirements">${esc(e.note)}</p>`:''}${e.source||e.repeat==='weekly'?`<details><summary>出处与重复规则</summary>${e.source?`<p class="source">出处：${esc(e.source)}</p>`:''}${e.repeat==='weekly'?`<p>起点 ${esc(e.series_day)}${e.until?' · 截至 '+esc(e.until):' · 未设截止'}</p>`:''}</details>`:''}${t?`<p class="calendar-task-status ${taskDismissed(t)?'calendar-family-decision':''}">${taskDismissed(t)?esc(t.child)+'：':'清单：'}${esc(taskStatusLabel(status(t)))}</p>`:''}${e.task_id?`<button class="calendar-card-action" data-calendar-task="${esc(e.task_id)}">核对原事项 →</button>`:''}${e.editable&&e.repeat==='none'&&!['cancelled','completed'].includes(e.status)?`<button data-calendar-complete="${esc(e.id)}">确认完成</button>`:''}${e.editable?`<button class="calendar-card-action" data-calendar-edit="${esc(e.id)}">${e.repeat==='weekly'?'编辑整条重复安排':'编辑安排'}</button>`:''}</article>`;
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
function agendaStudyHTML(item){return `<article class="task agenda-study"><span class="chip">${esc(calendarNames(item.child_ids))}</span><h3>${esc(item.title)}</h3><p>${esc(item.result||(item.status==='running'?'正在计时':item.status==='paused'?'已暂停':'待开始'))}${item.result_actor==='child'?' · 孩子自述待核对':''}</p><button data-agenda-study="${esc(item.child_ids[0])}" data-agenda-day="${item.day}">打开作业执行</button></article>`}
function calendarAgendaHTML(){
 if(calendarState.loading&&!calendarState.result)return '<p role="status">正在读取安排…</p>';
 if(calendarState.error)return `<p class="error" role="alert">${esc(calendarState.error)}</p><button data-calendar-retry>重试</button>`;
 if(!calendarState.result)return '<p role="status">准备读取日历…</p>';
 const r=calendarState.result,day=calendarState.day,items=calendarItems(r.agenda||[],day),studies=calendarItems(r.study||[],day),linked=new Set(items.map(x=>x.task_id).filter(Boolean));
 const groups=[['homework','课内作业'],['todo','待办事项']];
 const section=(title,html)=>`<section class="card agenda-group"><h2>${title}</h2>${html||'<p class="small muted">没有已收录的事项</p>'}</section>`;
 return `${r.source_error?`<p class="error">${esc(r.source_error)}</p>`:''}<h2 class="agenda-day-title">${esc(day)}${day===data.today?' · 今天':''}</h2><div class="agenda-groups">${groups.map(([kind,label])=>{const rows=items.filter(x=>(x.agenda.category==='homework'?'homework':'todo')===kind);let html=rows.map(agendaItemHTML).join('');if(kind==='homework')html+=studies.filter(x=>!items.some(i=>i.id===x.id)&&(!x.task_id||!linked.has(x.task_id))).map(agendaStudyHTML).join('');return kind===''&&!html?'':section(label,html)}).join('')}${section('手动计划与课程',(calendarItems(r.timetables,day).map(calendarTimetableHTML).join('')||'<p class="small muted">当天课表尚未提供</p>')+calendarItems(r.events,day).map(calendarEventHTML).join(''))}</div><p class="small muted">限期事项每天显示直到完成；逾期继续保留。未明确日期的事项在收集箱核对。</p>`;
}
function calendarHTML(){
 if(!calendarState.week){calendarState.week=calendarMonday(data.today);calendarState.day=data.today;calendarState.result=data.today_calendar;calendarState.range=data.today+'/'+data.today}
 if(!calendarState.visible){calendarState.childID=data.children.find(c=>c.name===child)?.id||'';calendarState.visible=true}
 if(calendarState.childID&&!data.children.some(c=>c.id===calendarState.childID))calendarState.childID='';
 const days=calendarDays();
 return `<section class="calendar-heading"><div><h1>家庭日历</h1></div><div class="toolbar"><button class="primary" data-calendar-new="${calendarState.day}">＋ 新建计划</button><button data-calendar-ask>说一句安排</button><details class="calendar-tools"><summary>课表与设置</summary><div class="toolbar"><button data-timetable-open>导入 / 管理课表</button><button data-calendar-sync>同步到手机</button><button data-new-task="yes">收集事务</button></div></details></div></section><div class="calendar-controls"><button data-calendar-shift="-7" aria-label="上一周">‹</button><label><span class="sr-only">跳到日期</span><input type="date" data-agenda-date value="${calendarState.day}"></label><button data-calendar-shift="7" aria-label="下一周">›</button><button data-calendar-current>今天</button></div><div class="calendar-kids"><button data-calendar-child="" aria-pressed="${!calendarState.childID}">全家</button>${data.children.map(c=>`<button data-calendar-child="${esc(c.id)}" aria-pressed="${c.id===calendarState.childID}">${esc(c.name)}</button>`).join('')}</div><div class="calendar-day-picker" aria-label="选择一天">${days.map((d,i)=>`<button data-calendar-day="${d}" aria-pressed="${d===calendarState.day}" ${d===data.today?'aria-current="date"':''}><span>周${'一二三四五六日'[i]}</span><strong>${Number(d.slice(8))}</strong></button>`).join('')}</div>${calendarPending?'<p role="status">上次保存未确认。<button data-calendar-resume>继续核对</button></p>':''}<div id="calendarAgenda">${calendarAgendaHTML()}</div>`;
}
function taskInboxItems(){return (data.today_calendar?.inbox||[]).filter(x=>!child||x.child_ids.includes(data.children.find(c=>c.name===child)?.id))}
function taskBoxes(){const all=taskInboxItems(),open=all.filter(x=>!x.closed);return {'Inbox':open.filter(x=>x.agenda.box!=='wish'),'Wish':open.filter(x=>x.agenda.box==='wish'),'计划':open.filter(x=>x.agenda.box!=='wish'&&x.agenda.scheduled_on),'已结束':all.filter(x=>x.closed),'全部':all}}
function taskBoxesHTML(){return `<div class="tasktabs task-boxes">${Object.entries(taskBoxes()).map(([name,rows])=>`<button data-task-box="${name}" aria-pressed="${page==='tasks'&&taskView===name}">${({Inbox:'收集箱',Wish:'心愿'})[name]||name} <span>${rows.length}</span></button>`).join('')}</div>`}
function wishTaskHTML(t){return `<article class="task wish-task" data-query-target="task:${esc(t.id)}"><span class="chip">${esc(t.child)} · 心愿</span><h3>${esc(t.title)}</h3>${taskActionHTML(t)}<div class="tasktools">${!taskClosed(t)?`<button class="primary" data-task-plan="${esc(t.id)}">转成计划</button><button data-task-focus="${esc(t.id)}">编辑心愿</button><button data-task-decisions="${esc(t.id)}">暂时放下</button>`:`<button data-task-restore="${esc(t.id)}">恢复心愿</button>`}</div></article>`}
function taskGroupsHTML(items,homeworkLabel='课内作业'){
 return [['homework',homeworkLabel],['todo','待办事项']].map(([kind,label])=>{
  const rows=items.filter(x=>(x.agenda.category==='homework'?'homework':'todo')===kind),confirmed=rows.filter(x=>x.kind!=='school'),pending=rows.filter(x=>x.kind==='school');
  return `<section class="card agenda-group" id="task-group-${kind}"><h2>${label} · ${confirmed.length}${pending.length?` <span class="review-badge">待核对 ${pending.length}</span>`:''}</h2>${confirmed.map(agendaItemHTML).join('')||'<p class="small muted">暂无已确认事项</p>'}${pending.map(agendaItemHTML).join('')}</section>`;
 }).join('');
}
function taskInboxHTML(){
 if(!Array.isArray(data.today_calendar?.inbox))return `<h1>事务收集箱</h1><p role="alert" class="error">${esc(data.today_calendar?.source_error||'收集箱暂时无法读取，请刷新记录；不能据此判断没有待办。')}</p>`;
 const views=taskBoxes();if(!(taskView in views))taskView='Inbox';
 return `<header class="today-heading"><h1>${taskView==='Wish'?'心愿清单':'收集箱'}</h1><button class="primary" data-new-task="${taskView==='Wish'?'wish':'yes'}">${taskView==='Wish'?'＋ 记心愿':'＋ 记一件事'}</button></header>${filters()}${taskBoxesHTML()}<p class="small muted">${taskView==='Wish'?'想做的事先留在这里，选定日期再转成计划。':'先收集，再安排；未完成的事务会保留。'}</p>${taskView==='Wish'?`<section class="card checklist">${views[taskView].map(agendaItemHTML).join('')||'<p>这里暂时没有心愿。</p>'}</section>`:`<div class="today-task-groups">${taskGroupsHTML(views[taskView])}</div>`}`;
}
function todayTasksHTML(){
 const r=data.today_calendar;if(!Array.isArray(r?.inbox))return taskInboxHTML();
 const matches=x=>!child||(x.child_ids||[x.child_id]).includes(data.children.find(c=>c.name===child)?.id);
 const items=taskInboxItems().filter(x=>!x.closed&&x.kind!=='event'&&x.agenda.box!=='wish'&&(!x.agenda.published_on||x.agenda.published_on<=data.today)&&(!x.agenda.scheduled_on||x.agenda.scheduled_on<=data.today||x.agenda.due_on));
 const plans=(r.timetables||[]).filter(matches).map(calendarTimetableHTML).join('')+(r.events||[]).filter(x=>matches(x)&&!['cancelled','completed'].includes(x.status)).map(calendarEventHTML).join('');
 return `<header class="today-heading"><div><h1>今天</h1><p>${esc(data.today)}</p></div><button class="primary" data-new-task="yes">＋ 记一件事</button></header><div class="today-controls">${filters()}<div class="today-sections" aria-label="跳到事务分类"><a href="#task-group-homework">作业 ${items.filter(x=>x.agenda.category==='homework'&&x.kind!=='school').length}</a><a href="#task-group-todo">待办 ${items.filter(x=>x.agenda.category!=='homework'&&x.kind!=='school').length}</a></div></div><div class="today-task-groups">${taskGroupsHTML(items,'今日作业')}</div>${plans?`<section class="card agenda-group"><h2>课表与计划</h2>${plans}</section>`:''}<p class="small muted">未完成事项继续保留；待核对通知需确认后才成为任务。</p>`;
}
async function calendarRead(){
 const start=calendarState.week,end=calendarAdd(start,6),range=start+'/'+end;
 if(calendarState.loading||calendarState.range===range&&calendarState.result)return;
 const seq=++calendarState.sequence;calendarState.controller?.abort();const controller=new AbortController();calendarState.controller=controller;calendarState.loading=true;calendarState.error='';
 const timer=setTimeout(()=>controller.abort(),20000);
 const paint=()=>{if(page==='calendar'&&calendarState.visible&&$('#calendarAgenda')){$('#calendarAgenda').innerHTML=calendarAgendaHTML();$('#calendarAgenda').setAttribute('aria-busy',String(calendarState.loading))}};paint();
 try{const r=await apiFetch('/api/calendar?start='+start+'&end='+end,{signal:controller.signal}),result=await r.json();if(!r.ok)throw Error(result.error||'读取日历失败');if(!Array.isArray(result.events)||!Array.isArray(result.timetables))throw Error('日历资料格式无法读取，请重试');if(seq!==calendarState.sequence||start!==calendarState.week)return;calendarState.result=result;calendarState.range=range;
 }catch(err){if(seq!==calendarState.sequence)return;calendarState.error=err.name==='AbortError'?'读取超时，请稍后重试。':['TypeError','SyntaxError'].includes(err.name)?'暂时无法读取，请检查登录或连接后重试。':err.message;
 }finally{clearTimeout(timer);if(seq===calendarState.sequence){calendarState.loading=false;paint()}}
}
function wireCalendar(){if(!calendarState.error)calendarState.reading=calendarRead()}
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
 if(calendarSaving)return false;
 if(calendarPending){$('#calendarDialog').showModal();return false}
 calendarRememberDraft();calendarDraftContext=null;
 document.getElementById?.('calendarDraftDetails')?.remove();
 const e=event||{id:calendarUUID(),version:0,child_ids:calendarState.childID?[calendarState.childID]:data.children.map(c=>c.id),title:'',category:'activity',day:calendarState.day||data.today,start_time:'',end_time:'',location:'',note:'',status:'tentative',repeat:'none',until:'',...preset};
 const f=$('#calendarForm');f.reset();for(const k of ['id','version','title','category','start_time','end_time','location','note','status','repeat','until'])f.elements[k].value=e[k]??'';f.elements.day.value=e.series_day||e.day;
 $('#calendarChildChoices').innerHTML=data.children.map(c=>`<label><input type="checkbox" name="child_ids" value="${esc(c.id)}" ${(e.child_ids||[]).includes(c.id)?'checked':''}><span>${esc(c.name)}</span></label>`).join('');
 $('#calendarDialogTitle').textContent=event?'编辑安排':'写下一个安排';$('#calendarEditNote').textContent=event?.repeat==='weekly'?'这是每周重复安排，保存会修改整条安排及所有展开日期。':'可以先暂定，和孩子商量后再确定。';$('#calendarFormError').textContent='';$('#calendarRetryNote').textContent='';calendarFormLock(false);calendarRepeat();$('#calendarDialog').showModal();return true;
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
function calendarRepeat(){const f=$('#calendarForm'),weekly=f.elements.repeat.value==='weekly';$('#calendarUntil').classList.toggle('hide',!weekly);f.elements.until.disabled=!weekly;$('#calendarRepeatNote').textContent=weekly?'从所选日期开始，每周同一天。编辑时会修改整条安排，不会只改某一次。':''}
function calendarFormLock(locked){$('#calendarFields').disabled=locked;$('#calendarSave').disabled=calendarSaving;$('#calendarSave').textContent=calendarSaving?'正在保存…':calendarPending?'重试这次保存':'保存安排';$('#calendarCancel').disabled=calendarSaving}
function calendarPayload(){const f=$('#calendarForm'),v=Object.fromEntries(new FormData(f));return {id:v.id,version:Number(v.version),child_ids:[...f.querySelectorAll('[name=child_ids]:checked')].map(x=>x.value),title:v.title,category:v.category,day:v.day,start_time:v.start_time,end_time:v.end_time,location:v.location,note:v.note,status:v.status,repeat:v.repeat,until:v.repeat==='weekly'?v.until:''}}
async function calendarRequest(obj){
 if(!calendarPending)calendarPending=JSON.stringify(obj);
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try{const r=await apiFetch('/api/calendar/save',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:calendarPending}),result=await r.json();if(!r.ok){if([400,404,409].includes(r.status))calendarPending=null;throw Error((result.error||'保存失败')+(r.status===409?'。请关闭表单刷新日历，重新打开最新安排后修改。':[401,403].includes(r.status)?'。当前输入已保留；完成登录或恢复连接后，请在这里重试保存。':''))}if(!result.event?.id)throw Error('保存响应暂时无法核对，请使用原内容重试');calendarPending=null;return result.event;
 }finally{clearTimeout(timer)}
}
$('#calendarForm').onsubmit=async e=>{
 e.preventDefault();if(calendarSaving)return;const obj=calendarPending?JSON.parse(calendarPending):calendarPayload();if(!obj.child_ids.length){$('#calendarFormError').textContent='请至少选择一位孩子。';return}
 calendarSaving=true;calendarFormLock(true);$('#calendarFormError').textContent='';
 try{await calendarRequest(obj);if(calendarDraftContext){calendarDraftContext.saved=true;calendarDraftContext.form=null;calendarDraftContext=null}$('#calendarDialog').close();toast('安排已保存');calendarInvalidate();try{await load()}catch{if(page==='calendar')render();toast('安排已保存，最新资料暂时无法刷新，请稍后刷新日历。')}}
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
 if(b.dataset.taskBox){taskView=b.dataset.taskBox;page='tasks';render();return}
 if(b.dataset.taskPlan){openTaskFocus(b.dataset.taskPlan);const f=$('#taskFocusForm');f.elements.box.value='inbox';f.elements.scheduled_on.required=true;if(f.elements.category.value==='unknown')f.elements.category.value='todo';$('#taskFocusScheduleLabel').textContent='计划在哪天做 · 必填';$('#taskFocusTitle').textContent='选定日期，转成计划';return}
 if(b.dataset.agendaStudy){studyChildID=b.dataset.agendaStudy;studyDay=b.dataset.agendaDay;studyTaskID='';page='study';render();return}
 if(b.hasAttribute('data-calendar-sync'))calendarSyncOpen();
 if(b.hasAttribute('data-calendar-child')){calendarJump++;calendarState.childID=b.dataset.calendarChild;child=data.children.find(c=>c.id===calendarState.childID)?.name||'';render()}
 if(b.dataset.calendarShift)calendarNavigate(calendarAdd(calendarState.day,Number(b.dataset.calendarShift)));
 if(b.hasAttribute('data-calendar-current'))calendarNavigate(data.today);
 if(b.hasAttribute('data-calendar-weekend')||b.hasAttribute('data-calendar-weekend-home')){calendarNavigate(calendarAdd(calendarMonday(data.today),5));$('#calendarWeekend')?.scrollIntoView({behavior:'auto',block:'center'})}
 if(b.dataset.calendarDay){calendarJump++;calendarState.day=b.dataset.calendarDay;render()}
 if(b.hasAttribute('data-calendar-retry')){calendarInvalidate();render()}
 if(b.hasAttribute('data-calendar-new'))calendarOpen(null,{day:b.dataset.calendarNew});
 if(b.hasAttribute('data-calendar-resume'))$('#calendarDialog').showModal();
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
