const basePath=new URL('.',location.href).pathname;
// LAN HTTP has getRandomValues but no randomUUID; keep all save/retry IDs cryptographically random.
if(typeof crypto!=='undefined'&&!crypto.randomUUID)crypto.randomUUID=()=>{
 const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
 const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
 return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
};
const endpoint=path=>basePath+path.replace(/^\//,'');
const apiFetch=async(path,options)=>{
 const headers=new Headers(options?.headers);if(headers.has('X-Family-Token')&&data?.token)headers.set('X-Family-Token',data.token);
 const response=await fetch(endpoint(path),{...options,headers});
 if(response.status===401)showParentLogin();
 if(response.status===403&&headers.has('X-Family-Token')){
  const result=await response.clone().json().catch(()=>null);
  if(result?.code==='csrf_expired'&&typeof result.token==='string'&&/^[A-Za-z0-9_-]{43}$/.test(result.token)&&data?.token===headers.get('X-Family-Token'))data.token=result.token;
 }
 return response;
};
let teacherSelectedID='';
let data, page=['home','calendar','tasks','more','ask','settings'].includes(document.body.dataset.startupPage)?document.body.dataset.startupPage:'home', child='', subject='', taskView='Inbox', busy=false, pendingTask=null;
let studyChildID='',studyDay='',studyTaskID='',studyRecordContext=null,schoolRecordContext=null,schoolRecordOpening=false;
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const status=t=>t.update?.status || (['待跟进','进行中','已完成','不参加','不适用','已归档'].includes(t.original_status)?t.original_status:t.original_status.includes('已归档')?'已归档':'待跟进');
const taskDismissed=t=>['不参加','不适用'].includes(status(t));
const taskClosed=t=>taskDismissed(t)||['已完成','已归档'].includes(status(t));
const taskStatusLabel=value=>value==='不适用'?'无需处理':value;
const selected=xs=>xs.filter(x=>!child||x.child===child);
const empty=s=>`<div class="empty">${esc(s)}</div>`;
function toast(s){$('#toast').textContent=s;$('#toast').style.display='block';setTimeout(()=>$('#toast').style.display='none',3500)}
const parentLogoutAvailable=['https:','http:'].includes(location.protocol)&&!['localhost','127.0.0.1','[::1]'].includes(location.hostname);
let parentLoginCheck=null,parentLoginAuthenticated=false,parentLogoutBusy=false;
function parentLoginURL(){const url=new URL(endpoint('/login'),location.href);url.hash=location.hash;return url.href}
function paintParentLogin(){
 const form=$('#parentLoginForm'),pending=!!parentLoginCheck;
 form.elements.username.readOnly=pending||parentLoginAuthenticated;form.elements.password.readOnly=pending||parentLoginAuthenticated;form.elements.password.required=!parentLoginAuthenticated;
 $('#parentLoginSubmit').disabled=pending;$('#parentLoginShow').disabled=pending;
 $('#parentLoginSubmit').textContent=pending?'正在连接…':parentLoginAuthenticated?'重试连接':'登录并继续';
}
function showParentLogin(){
 const dialog=$('#parentLoginDialog');$('#parentLoginNotice').classList.remove('hide');
 if(!dialog.open){parentLoginAuthenticated=false;$('#parentLoginStatus').textContent='';paintParentLogin();dialog.showModal()}
}
async function checkParentLogin(event){
 event.preventDefault();const form=$('#parentLoginForm');if(parentLoginCheck||!form.reportValidity())return;
 if(!parentLogoutAvailable){$('#parentLoginStatus').textContent='请从配置的家庭入口登录。当前填写仍留在本页。';return}
 const controller=new AbortController();parentLoginCheck=controller;const timer=setTimeout(()=>controller.abort(),20000);
 paintParentLogin();$('#parentLoginStatus').textContent='正在恢复登录…';
 try{
  if(!parentLoginAuthenticated){
   const response=await fetch(endpoint('/api/parent/login'),{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Login':'1'},body:JSON.stringify({username:form.elements.username.value,password:form.elements.password.value})});
   const result=await response.json();if(!response.ok||result.ok!==true)throw Error(typeof result.error==='string'?result.error:'登录未成功，请核对账号与密码。');
   if(parentLoginCheck!==controller||!$('#parentLoginDialog').open)return;
   parentLoginAuthenticated=true;form.elements.password.value='';form.elements.password.type='password';$('#parentLoginShow').textContent='显示';$('#parentLoginShow').setAttribute('aria-pressed','false');
  }
  const response=await apiFetch('/api/state',{signal:controller.signal,credentials:'same-origin',cache:'no-store'});
  if(!response.ok){if(response.status===401)parentLoginAuthenticated=false;throw Error(response.status===401?'登录未能恢复，请重新填写密码。':'已登录，暂时无法核对家庭记录，请重试连接。')}
  const next=await response.json();if(parentLoginCheck!==controller||!$('#parentLoginDialog').open)return;
  if(data)data.token=next.token;
  $('#parentLoginNotice').classList.add('hide');$('#parentLoginDialog').close();
  if(data)toast('登录已恢复，请重试刚才的操作。');else await load().catch(showStartupError);
 }catch(error){
  if(parentLoginCheck===controller&&$('#parentLoginDialog').open)$('#parentLoginStatus').textContent=error.name==='AbortError'?'核对超时，请检查连接后重试。':error instanceof TypeError||error instanceof SyntaxError?'未能核对登录，请检查连接后重试。':error.message;
 }finally{clearTimeout(timer);if(parentLoginCheck===controller){parentLoginCheck=null;paintParentLogin()}}
}
async function parentLogout(){
 if(parentLogoutBusy)return;parentLogoutBusy=true;
 const buttons=[...$('#parentLogoutDialog').querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);$('#parentLogoutStatus').textContent='正在退出…';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
 try{
  const response=await fetch(endpoint('/api/parent/logout'),{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Login':'1'},body:'{}'});
  const result=await response.json();if(!response.ok||result.ok!==true)throw Error(typeof result.error==='string'?result.error:'退出未成功，请重试。');
  location.replace(parentLoginURL());
 }catch(error){$('#parentLogoutStatus').textContent=error.name==='AbortError'?'退出结果尚未确认，请检查连接后重试。':error instanceof TypeError||error instanceof SyntaxError?'退出结果尚未确认，请重试。':error.message}
 finally{clearTimeout(timer);parentLogoutBusy=false;buttons.forEach(b=>b.disabled=false)}
}
$('#parentLoginOpen').onclick=showParentLogin;$('#parentLoginForm').onsubmit=checkParentLogin;
$('#parentLoginShow').onclick=()=>{const input=$('#parentLoginForm').elements.password,visible=input.type==='password';input.type=visible?'text':'password';$('#parentLoginShow').textContent=visible?'隐藏':'显示';$('#parentLoginShow').setAttribute('aria-pressed',String(visible))};
$('#parentLoginDialog').addEventListener('close',()=>{parentLoginCheck?.abort();parentLoginCheck=null;parentLoginAuthenticated=false;const input=$('#parentLoginForm').elements.password;input.value='';input.type='password';$('#parentLoginShow').textContent='显示';$('#parentLoginShow').setAttribute('aria-pressed','false');paintParentLogin()});
$('#parentLogoutConfirm').onclick=parentLogout;
$('#parentLogoutDialog').addEventListener('cancel',event=>{if(parentLogoutBusy)event.preventDefault()});
document.addEventListener('click',event=>{if(event.target.closest('[data-parent-logout]')&&parentLogoutAvailable){$('#parentLogoutStatus').textContent='';$('#parentLogoutDialog').showModal()}});
let stateLoadSequence=0;
async function load(paint=true){
 const seq=++stateLoadSequence,controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
 try{
  const r=await apiFetch('/api/state',{signal:controller.signal});
  if(!r.ok)throw Error(r.status===401?'请先重新登录，再重试读取。':r.status===403?'当前入口没有访问权限，请核对家庭入口。':'家庭记录暂时无法读取，请重试。');
  const next=await r.json();if(seq!==stateLoadSequence)return;
  const selectedID=data?.children.find(c=>c.name===child)?.id,askedID=data?.children.find(c=>c.name===askState.child)?.id;
  data=next;if(!data.children.length)page='settings';if(selectedID)child=data.children.find(c=>c.id===selectedID)?.name||'';
  if(askedID){const name=data.children.find(c=>c.id===askedID)?.name||'';if(name!==askState.child){askState.child=name;askState.result=null;askState.error='档案已更正，可重新查询。'}}
  $('#date').textContent=data.today+' · 家庭学习与成长';window.FamilyCalendar?.invalidate(page==='calendar');if(paint)render();$('#content').dataset.ready='true';
 }catch(error){
  if(seq!==stateLoadSequence)return;
  if(error.name==='AbortError')throw Error('读取超时，请检查网络后重试。');
  if(['TypeError','SyntaxError'].includes(error.name))throw Error('家庭记录加载未成功，请重新加载页面。');
  throw error;
 }finally{clearTimeout(timer)}
}
function showStartupError(error){$('#content').innerHTML=`<section class="card" data-startup-error role="alert"><h1>家庭记录暂未加载成功</h1><p>${esc(error.message||'请检查连接后重试。')}</p><button class="primary" type="button" data-startup-retry>重试读取</button></section>`;const retry=$('[data-startup-retry]');retry.onclick=()=>{retry.disabled=true;$('#content [data-startup-error] p').textContent='正在重新读取家庭记录…';load().catch(showStartupError)}}
function filters(){return `<div class="calendar-kids child-filters" role="group" aria-label="查看孩子"><button type="button" data-child-filter="" aria-pressed="${!child}">全部孩子</button>${data.children.map(c=>`<button type="button" data-child-filter="${esc(c.id)}" aria-pressed="${child===c.name}">${esc(c.name)}</button>`).join('')}</div>`}
function taskFocus(t){return t.focus||{mode:'next',next_action:'',waiting_for:'',review_on:'',version:0}}
function taskReviewDue(t){if(taskClosed(t))return false;const f=taskFocus(t);return f.mode!=='next'&&exactTaskDay(f.review_on)&&f.review_on<=data.today}
function taskActionHTML(t){const f=taskFocus(t),advice=f.next_action||t.advice||'',goal=t.action?.startsWith('请核对这条通知是否适用')?'':t.action;return `${goal?`<div class="task-goal"><span class="small muted">完成目标</span><p class="task-requirement">${esc(goal)}</p></div>`:'<p class="task-needs-action">完成目标待明确</p>'}${advice?`<div class="task-next"><span>操作建议</span><p>${esc(advice)}</p></div>`:''}${f.mode==='waiting'?`<p class="task-waiting">等待：${esc(f.waiting_for)}${f.review_on?' · '+esc(f.review_on)+' 回看':''}</p>`:f.mode==='later'?`<p class="task-waiting">${f.review_on?'改天回看：'+esc(f.review_on):'以后再说 · 尚未约定回看日期'}</p>`:''}${taskReviewDue(t)?'<p class="task-review-due">到了回看日期，确认现在能否推进。</p>':''}`}

function taskHTML(t,options={}){
 const compact=options.compact===true,done=status(t)==='已完成',dismissed=taskClosed(t)&&!done,pending=pendingTask?.id===t.id,open=!taskClosed(t);
 const primary=open&&t.focus?.box!=='wish'&&t.agenda?.category==='homework'?`<button class="primary" data-study-task-add="${esc(t.id)}">${t.homework_report?.needs_review?'核对报来的功课':'作业计时'}</button>`:open&&t.title.includes('打印')?'<button class="primary" data-page="print">准备打印</button>':'';
 return `<article class="task ${done?'done':''}" data-query-target="task:${esc(t.id)}" aria-busy="${pending}" ${compact?`data-today-task="${esc(t.id)}"`:''} tabindex="-1"><div class="checkrow">${dismissed?'<span class="task-dismiss-icon" aria-hidden="true">−</span>':`<label class="checkhit"><input type="checkbox" data-check="${esc(t.id)}" ${(pending?pendingTask.checked:done)?'checked':''} ${pendingTask?'aria-disabled="true"':''} aria-label="${done?'撤销完成':'确认完成'}：${esc(t.title)}"><span class="sr-only">${done?'撤销完成':'确认完成'}</span></label>`}<div class="taskbody"><h3>${esc(t.title)}</h3><div class="task-meta"><span>${esc(t.child)}</span>${status(t)!=='待跟进'||pending?`<span class="chip">${pending?'<span role="status">正在保存…</span>':esc(taskStatusLabel(status(t)))}</span>`:''}${options.when?`<span>${esc(options.when)}</span>`:''}</div>${agendaDateHTML(t.agenda||{})}${!t.agenda?.due_on&&t.due?`<p class="small muted">原日期要求：${esc(t.due)}</p>`:''}${taskActionHTML(t)}${t.school_completion_needs_review?'<p class="note" data-school-completion-review>原要求已完成；更正后是否需补做、是否已完成，待家长核对。</p>':''}${t.update?.note?`<p class="feedback">${esc(t.update.note)}</p>`:''}<div class="tasktools">${primary}<button data-task="${esc(t.id)}">反馈进展</button>${dismissed?`<button data-task-restore="${esc(t.id)}">恢复跟进</button>`:!done?`<button data-task-decisions="${esc(t.id)}">不参加 / 不用做</button>`:''}</div><details class="task-reference task-more"><summary>更多操作与原通知</summary><div class="tasktools">${open?`<button data-task-plan="${esc(t.id)}">${t.agenda?.scheduled_on?'改计划日期':'转成计划'}</button><button data-task-focus="${esc(t.id)}">修改标题 / 日期</button>`:''}<button data-school-record-task="${esc(t.id)}">留作学习记录</button>${/阅读|读书|篇目|读后感/.test(t.title+t.action)?`<button data-reading-source="${esc(t.id)}">约定阅读任务</button>`:''}</div>${schoolOriginalButtons(String(t.source||'').split('\n').filter(r=>r.startsWith('message:')),data.children.find(c=>c.name===t.child)?.id)}<div class="source">${t.original_title?esc('原标题：'+t.original_title)+'<br>':''}${t.original_action?esc('原要求：'+t.original_action)+'<br>':''}${esc(t.source)}<br>整理状态：${esc(t.original_status)}</div>${(t.history||[]).map(h=>`<p class="history"><time>${esc(h.updated.slice(0,16).replace('T',' '))}</time> · ${esc(taskStatusLabel(h.status))}<br>${esc(h.note||'已更新状态')}</p>`).join('')}</details></div></div></article>`;
}
async function postTask(obj){
 const r=await apiFetch('/api/task',{method:'POST',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify({...obj,expected_updated:obj.expected_updated??data.tasks.find(t=>t.id===obj.id)?.update?.updated??''})});
 const result=await r.json();if(!r.ok){const error=Error(result.error||'保存失败');error.status=r.status;throw error}
 if(result.task?.id===obj.id){
  ++stateLoadSequence; // A state read started before this save must not undo its acknowledgement.
  data.tasks=data.tasks.map(t=>t.id===obj.id?result.task:t);if(data.today_calendar?.inbox){for(const row of [...data.today_calendar.inbox,...(data.today_calendar.agenda||[])].filter(x=>x.task_id===obj.id)){row.status=status(result.task);row.closed=taskClosed(result.task);row.closed_on=(result.task.update?.updated||'').slice(0,10)}}window.FamilyCalendar?.invalidate(page==='calendar');
 }else await load(); // Older servers still return only {ok:true} during an upgrade.
 return result;
}
document.addEventListener('change',async e=>{
 const el=e.target;if(!el.dataset.check)return;const t=data.tasks.find(t=>t.id===el.dataset.check),done=el.checked;
 if(busy){el.checked=!done;return}
 // ponytail: serialize task decisions in this page; use per-task locks if concurrent editing is needed.
 busy=true;pendingTask={id:t.id,checked:done};render();
 try{await postTask({id:t.id,status:done?'已完成':'待跟进',note:done?'家长通过清单勾选确认此事项已完成。':'家长撤销完成，继续跟进。'});toast(done?'已完成；在收集箱“已完成”中可撤销':'已恢复待跟进')}
 catch(err){toast(err.message||'保存结果未确认，请重试核对。')}
 finally{busy=false;pendingTask=null;render()}
});
function uploadHTML(a){return `<div class="upload-item"><a href="${endpoint('/upload/')}${encodeURIComponent(a.id)}" target="_blank" rel="noopener">${esc(a.name)}</a> <span class="muted small">${(a.size/1024/1024).toFixed(2)} MB</span>${['image/jpeg','image/png','image/webp'].includes(a.mime)?`<img src="${endpoint('/upload/')}${encodeURIComponent(a.id)}" alt="${esc(a.name)}" loading="lazy">`:a.mime.startsWith('audio/')?`<audio controls preload="none" src="${endpoint('/upload/')}${encodeURIComponent(a.id)}"></audio>`:a.mime.startsWith('video/')?`<video controls playsinline preload="metadata" src="${endpoint('/upload/')}${encodeURIComponent(a.id)}"></video><p class="meta">视频原件；保存不代表内容已分析，无法回放时可点文件名打开原件。</p>`:''}</div>`}
function recordUploads(r){return (r.attachments||[]).map(id=>(data.uploads||[]).find(a=>a.id===id)).filter(Boolean).map(uploadHTML).join('')}
function inboxHTML(){const linked=new Set([...data.records,...(data.reading?.tasks||[])].flatMap(r=>r.attachments||[]).concat(data.agent?.linked_upload_ids||[])),items=(data.uploads||[]).filter(a=>!linked.has(a.id));return `<section class="card"><h2>待整理资料${items.length?' · '+items.length:''}</h2><p class="muted">原件已保存。可以关联学校通知，需要记录实际学习情况时再补充记录。</p>${items.map(a=>`${uploadHTML(a)}<button data-upload="${esc(a.id)}">补充记录</button>${['image/jpeg','image/png','image/webp'].includes(a.mime)?`<button data-timetable-upload="${esc(a.id)}">作为课表导入</button>`:''}`).join('')||empty('没有待整理资料。')}</section>`}
const currentSources=()=>Array.isArray(data.agent?.sources)?data.agent.sources:[];
function currentSourceStatus(s){
 if(!s.enabled)return '已停用';
 if(data.agent?.enabled===false)return '采集已暂停';
 if(s.inbox)return s.inbox.state==='error'?'截图待重试':s.inbox.pending?'截图待整理':'截图收集已启用';
 if(s.error)return '最近读取未成功';
 if(!s.last_success)return '尚未读取';
 const time=Date.parse(s.last_success),due=Date.parse(s.next_collection_at),interval=data.agent?.collection_interval_minutes;
 const overdue=Number.isFinite(due)?Date.now()>due+5*60*1000:Date.now()-time>([30,60].includes(interval)?interval+5:15)*60*1000;
 return !Number.isFinite(time)||time>Date.now()+60000||overdue?'读取待核对':'最近读取成功';
}
function sourceCoverageHTML(){
 const sources=currentSources(),lines=sources.flatMap(s=>{
  const status=currentSourceStatus(s),unread=Number.isSafeInteger(s.unread_count)&&s.unread_count>0?s.unread_count:0;
  if(status==='最近读取成功'&&!unread)return [];
  const owner=data.children.find(c=>c.id===s.child_id),platform=s.platform==='qq'?'QQ':s.platform==='wechat'?'微信':'消息来源';
  const label=({'已停用':'已暂停，不同步新消息','采集已暂停':'采集已暂停，不同步新消息','最近读取未成功':'读取未成功，新消息可能未收录','尚未读取':'尚无成功读取记录','读取待核对':'读取已过时或时间待核对','截图待重试':'截图整理失败，原图保留待重试','截图待整理':'已有截图等待整理，其他新消息需手动收集','截图收集已启用':'仅整理已选截图，新消息需手动收集'})[status]||`${unread} 条消息含未读内容`;
  return [`<span>${esc(owner?.name||'归属待核对')} · ${platform} · ${esc(s.name||'未命名来源')}：<strong>${esc(label)}</strong></span>`];
 });
 if(!lines.length&&(data.sync_error||(!sources.length&&data.agent?.last_error)))lines.push('<span>学校信息状态暂时无法核对，已有记录仍可查看。</span>');
 if(!lines.length&&!sources.length&&Object.values(data.sync||{}).some(s=>s?.last_error||s?.collection_status==='awaiting_login'))lines.push('<span>历史来源接入或读取待核对，新消息可能未收录。</span>');
 return lines.length?`<button type="button" class="source-coverage" data-source-coverage data-page="sources">${lines.join('')}<span class="source-coverage-link">查看来源 →</span></button>`:'';
}
function currentSourceCardsHTML(){
 if(!currentSources().length)return '';
 return `<div class="grid source-cards" data-current-sources>${currentSources().map(s=>{
  const owner=data.children.find(c=>c.id===s.child_id),label=currentSourceStatus(s),unread=Number.isSafeInteger(s.unread_count)&&s.unread_count>0?s.unread_count:null;
  return `<section class="card agent-source" data-current-source="${esc(s.id)}"><span class="chip ${label==='最近读取成功'?'':'amber'}" data-current-source-status>${label}</span><h3>${esc(s.name||'未命名来源')}</h3><p>${esc(owner?.name||'归属待核对')} · ${s.platform==='wechat'?'微信':s.platform==='qq'?'QQ':'平台待核对'}</p>${s.inbox?`<p class="note" data-source-inbox>当前使用本机截图收集，待整理 ${Number.isSafeInteger(s.inbox.pending)?s.inbox.pending:0} 张。打开班级群后使用“QQ截图收集”，框选时包含群名；Agent自动整理，家长核对后加入今天或日历。</p>${s.inbox.error?`<p class="error">${esc(s.inbox.error)}</p>`:""}`:""}<p class="small source">${s.inbox?"历史原生读取记录 · ":""}最近成功：${agentTime(s.last_success)}<br>最近尝试：${agentTime(s.last_attempt)}<br>已读消息最新时间：${agentTime(s.last_message_time)}</p>${s.fragment?`<p class="small" data-source-fragment>窗口片段保存于 ${agentTime(s.fragment.captured_at)}；完整消息与附件原件仍待核对。</p><button data-school-original-ref="${esc(`message:${s.id}:${s.fragment.id}`)}" data-school-original-child="${esc(s.child_id)}">查看窗口片段</button>`:''}${s.error&&!s.inbox?`<p class="error" role="status">${esc(s.error)}</p>`:''}${unread?`<p class="small" data-current-source-unread>${unread} 条已保存消息含未读图片、附件或截断内容。</p>`:'<p class="small muted">未列出内容缺口不代表历史或原件全部读完。</p>'}${label==='读取待核对'?'<p class="small muted">已超过下次读取时间与轮询余量，或时间无法核对，请检查采集电脑与连接。</p>':''}${owner?`<button data-source-tasks="${esc(owner.name)}">查看这个孩子的待办</button>`:''}</section>`;
 }).join('')}</div>`;
}
function sourceCardsHTML(){
 const entries=Object.entries(data.sync||{}),kinds={image:'图片',file:'文件',video:'视频',link:'文章链接',miniprogram:'小程序',announcement:'群公告'};
 return `${data.sync_error?`<p class="error" role="status" data-source-error>${esc(data.sync_error)}</p>`:''}<div class="grid source-cards">${entries.map(([key,value])=>{
  if(!value||typeof value!=='object'||Array.isArray(value))return `<section class="card" data-source-card><p class="error">一项来源记录格式异常，需核对采集结果。</p></section>`;
  const s=value,qq=key.startsWith('qq:'),waiting=s.collection_status==='awaiting_login',failed=!!s.last_error,pending=Array.isArray(s.pending_content)?s.pending_content:null;
  const count=Number.isSafeInteger(s.incremental_new_records)&&s.incremental_new_records>=0?s.incremental_new_records:null,total=Number.isSafeInteger(s.fetched_local_records)&&s.fetched_local_records>=0?s.fetched_local_records:null;
  const label=waiting?'接入待验证':failed?'最近读取未成功':'已有保存的读取结果';
  return `<section class="card" data-source-card="${esc(key)}"><span class="chip amber" data-source-status>${label}</span><h3>${esc(s.name||(qq?'QQ班级群':'微信班级群'))}</h3><p>${esc(s.child||'归属待核对')} · ${qq?'QQ':'微信'}</p><p class="small source">上次成功读取记录：${esc(s.last_checked||'未记录')}<br>最近尝试：${esc(s.last_attempt||s.last_checked||'未记录')}</p>${waiting?'<p class="note">当前接口的登录与指定群读取尚待验证，历史已读资料继续保留。</p>':''}${failed?`<p class="error source" role="status">${esc(s.last_error)}</p>`:''}<p class="small source">已读内容中最近消息：${esc(s.last_message_time||s.latest_visible||'未记录')}</p><p class="small" data-source-count>${count!==null?'历史增量登记：'+count+' 条；不是当前实时新增数。':total!==null?'已保存扫描记录：'+total+' 条；不代表完整历史。':'消息数量未记录，不推算新增条数。'}</p>${s.incremental_count_note?`<details><summary>查看这次历史登记的说明</summary><p class="small source">${esc(s.incremental_count_note)}</p></details>`:''}<details data-source-gaps><summary>${pending?.length?'还有 '+pending.length+' 项资料待核对':'查看内容覆盖缺口'}</summary>${pending?.length?`<ul class="source-gap-list">${pending.map(item=>{
   if(typeof item==='string')return `<li>${esc(item)}</li>`;
   if(!item||typeof item!=='object'||Array.isArray(item))return '<li>一项资料的说明格式异常，需核对原记录。</li>';
   return `<li><strong>${esc(kinds[item.kind]||'资料')}${Number.isSafeInteger(item.local_id)?' · 消息 '+esc(item.local_id):''}</strong><p>${esc(item.gap||'具体缺口尚未说明，不能视为已读。')}</p></li>`;
  }).join('')}</ul>`:`<p class="small">${s.full_content_complete===true?'已登记的内容标为已核对；完整历史范围仍以来源说明为准。':'尚未列出逐项明细，不能据此认定全部内容已读。'}</p>`}<p class="small muted">正文读取成功不代表图片、链接和更早历史已全部读到；缺口不会因为刷新页面而消失。</p></details>${data.children.some(c=>c.name===s.child)?`<button type="button" data-source-tasks="${esc(s.child)}">查看这个孩子的待办</button>`:''}</section>`;
 }).join('')||(data.sync_error?'':empty('还没有保存的消息来源。可以先手动记录或上传资料。'))}</div>`;
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-source-tasks]');if(!b)return;const name=b.dataset.sourceTasks;if(!data.children.some(c=>c.name===name))return;child=name;page='tasks';taskView='Inbox';render();window.scrollTo(0,0)});
function learningEvidenceHTML(r){
 if(!['成绩','学习进展'].includes(r.category)&&!r.followup_kind&&!r.assistance&&!r.practice_relation&&!r.comparison_note)return '';
 return `<p class="small source">本次帮助：${esc(r.assistance||'未记录，不能推定独立')}<br>与关联的上一次相比：${esc(r.practice_relation||'未记录，不能推定可比')}${r.comparison_note?'<br>比较条件：'+esc(r.comparison_note):''}</p>`;
}
function careChoiceText(r){return r.care_choice?(r.care_choice+(r.care_choice==='改天回看'?' · '+(r.care_review_on||'日期未记录'):r.care_choice==='愿意试试'?' · 不代表已经尝试或完成':'')):'未登记明确选择（文字 / 原件反馈）'}
function careRecordHTML(r){return String(r.source||'').startsWith('陪伴建议:')?`<p class="small source">当时选择：${esc(careChoiceText(r))}</p>`:''}
function recordHTML(r){const parent=data.records.find(x=>x.id===r.related_record_id);return `<article class="record" data-query-target="record:${r.id}" tabindex="-1"><div class="date">${esc(r.day)} · ${esc(r.child)} · ${esc(r.category)} · ${esc(r.source)}</div><h3>${esc(r.title)}</h3>${parent?`<p class="small muted">${esc(r.followup_kind)} · 来源：${esc(parent.title)}</p>`:''}${r.score!==null?`<div class="score">${esc(r.score)} <small>/ ${esc(r.total)}</small></div>`:''}<p class="source">${esc(r.note)}</p>${learningEvidenceHTML(r)}${careRecordHTML(r)}${recordUploads(r)}<span class="muted">${esc(r.subject)}</span> ${String(r.source||'').startsWith('短引导尝试:')?'<span class="small muted">原始尝试保留；更正请追加观察。</span>':`<button data-record="${r.id}">编辑记录</button>`} <button data-followup="${r.id}">跟进 / 复测</button>${['成绩','学习进展'].includes(r.category)?` <button data-guided-new="${r.id}">围绕这条记录一起学</button>`:''}<details data-record-history="${r.id}"><summary>查看更正历史</summary><div class="history-body"></div></details></article>`}
function revealLearningTarget(target){if(!target)return;for(let p=target.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;target.scrollIntoView({block:'center'});target.focus({preventScroll:true})}
function recordVersionHTML(v,files){
 const parent=data.records.find(r=>r.id===v.related_record_id);
 return `<p class="small muted">当时记录：${esc(v.child)} · ${esc(v.day)} · ${esc(v.category)}${v.subject?' · '+esc(v.subject):''}</p><h3>${esc(v.title)}</h3>${v.score!==null&&v.score!==undefined?`<p>分数：${esc(v.score)} / ${esc(v.total??'未记录满分')}</p>`:''}<p class="source">${esc(v.note||'未填写详情')}</p>${v.transcript?`<p class="source">转写（${esc(v.transcript_state)}）：${esc(v.transcript)}</p>`:''}${learningEvidenceHTML(v)}${careRecordHTML(v)}<p class="source small">来源：${esc(v.source||'未填写')}${v.related_record_id?'<br>跟进关联：'+esc(v.followup_kind||'未注明类型')+' · \u5173\u8054\u8bb0\u5f55\uff08\u5f53\u524d\u6807\u9898\uff09\uff1a'+esc(parent?.title||'关联记录当前不可用'):''}</p>${v.attachments_recorded===false?'<p class="small muted">这个旧版本未保留原件关联信息。</p>':(v.attachments||[]).map(id=>{const f=files.find(f=>f.id===id);return f?.available?`<p class="small"><a href="${endpoint('/upload/')}${encodeURIComponent(id)}" target="_blank" rel="noopener">查看原件：${esc(f.name||'已保存文件')}</a></p>`:`<p class="small error">原件当前不可读取：${esc(f?.name||'未保留文件名')}</p>`}).join('')||'<p class="small muted">此版本没有关联原件。</p>'}`;
}
function recordHistoryHTML(result){
 const labels={child:'归属称呼',day:'日期',category:'记录类型',subject:'科目',title:'标题',note:'详情',source:'来源',score:'分数',total:'满分',related_record_id:'关联记录',followup_kind:'跟进类型',assistance:'帮助情况',practice_relation:'材料关系',comparison_note:'比较条件',attachments:'原件',transcript:'语音转写',transcript_state:'转写核对'};
 let newer=result.current;
 return `<p class="small muted">这里只查看已保存的版本。旧内容保留当时的称呼，不计为新的学习进展。</p>${result.unreadable_count?`<p class="error" role="status">${result.unreadable_count} 个旧版本暂时无法读取，其余版本仍可查看。</p>`:''}<details open><summary>当前保存的版本</summary>${recordVersionHTML(result.current,result.attachments)}</details>${result.history.map(h=>{
  const changed=String(h.changed||'时间未记录').replace('T',' ').slice(0,16),previous=h.previous;
  const fields=previous&&newer?Object.keys(labels).filter(k=>{const value=v=>['assistance','practice_relation','comparison_note'].includes(k)?v[k]??'':v[k];return JSON.stringify(value(previous))!==JSON.stringify(value(newer))}).map(k=>labels[k]):[];newer=previous;
  return `<details><summary>${esc(changed)} 更正前${fields.length?' · '+esc(fields.join('、')):''}</summary>${previous?recordVersionHTML(previous,result.attachments):`<p class="error">${esc(h.error||'这个旧版本暂时无法读取。')}</p>`}</details>`;
 }).join('')||'<p class="muted">这条记录还没有更正历史。</p>'}<p class="small muted">列出系统已保留的版本，更正时间按原记录显示。</p><button type="button" data-history-refresh>刷新更正历史</button>`;
}
async function loadRecordHistory(details){
 if(details.dataset.loading)return;details.dataset.loading='yes';const body=details.querySelector('.history-body');body.textContent='正在读取更正历史…';body.setAttribute('aria-busy','true');
 try{
  const r=await apiFetch('/api/record/history/'+encodeURIComponent(details.dataset.recordHistory)),result=await r.json();if(!r.ok)throw Error(result.error||'读取失败，请重试');
  if(!details.isConnected)return;body.innerHTML=recordHistoryHTML(result);
 }catch(error){if(details.isConnected)body.innerHTML=`<p class="error" role="alert">${esc(['TypeError','SyntaxError'].includes(error.name)?'暂时无法读取，请检查登录或连接后重试。':error.message)}</p><button type="button" data-history-refresh>重试读取</button>`;}
 finally{delete details.dataset.loading;body.removeAttribute('aria-busy')}
}
document.addEventListener('toggle',e=>{const d=e.target;if(d.matches?.('[data-record-history]')&&d.open)loadRecordHistory(d)},true);
document.addEventListener('click',e=>{const b=e.target.closest('[data-history-refresh]');if(b)loadRecordHistory(b.closest('[data-record-history]'))});
let careFeedbackContext=null,careFeedbackPending=null;
function updateCareFields(){
 if(!careFeedbackContext||careFeedbackPending)return;
 const f=$('#recordForm'),deferred=f.elements.care_choice.value==='改天回看';
 $('#careReviewDate').classList.toggle('hide',!deferred);f.elements.care_review_on.disabled=!deferred;f.elements.care_review_on.required=deferred;
 f.elements.care_review_on.min=new Date(Date.parse(data.today+'T12:00:00Z')+86400000).toISOString().slice(0,10);
 if(!deferred)f.elements.care_review_on.value='';
 f.elements.note.required=!f.elements.care_choice.value&&!pendingIDs.length;
}
$('#careChoiceFields').onchange=updateCareFields;
function resetCareFeedback(){
 careFeedbackContext=null;$('#careChoiceFields').disabled=true;$('#careChoiceFields').classList.add('hide');$('#careSavedChoice').classList.add('hide');$('#careSavedChoice').textContent='';
 const f=$('#recordForm');f.elements.care_choice.value='';f.elements.care_review_on.value='';f.elements.care_review_on.required=false;f.elements.care_review_on.disabled=true;
}
function openCareFeedback(id){
 const c=data.care.items.find(x=>x.id===id);if(!c){toast('建议暂时无法找到，请刷新后核对');return}
 if(careFeedbackPending){toast('请先核对上次反馈的保存结果');return}
 $('#add').click();const f=$('#recordForm');careFeedbackContext={id};f.classList.add('care-mode');$('#careChoiceFields').disabled=false;$('#careChoiceFields').classList.remove('hide');
 $('#recordDialog h2').textContent='这条建议怎么安排？';$('#recordDialog .muted').textContent=c.child+' · '+c.title;
 f.elements.child.value=c.child;f.elements.category.value='家长观察';f.elements.subject.value=c.topic;f.elements.title.value=('建议反馈：'+c.title).slice(0,200);
 f.elements.source.add(new Option('陪伴建议:'+c.id,'陪伴建议:'+c.id,false,true));f.elements.note.placeholder='可以补充孩子的想法、实际尝试或不适合的原因，也可以上传原音或照片。';f.querySelector('[type=submit]').textContent='保存选择与反馈';updateCareFields();$('#careChoiceFields input:checked').focus();
}
async function submitCareFeedback(f){
 const retry=!!careFeedbackPending;
 if(!careFeedbackPending){
  const body={...Object.fromEntries(new FormData(f)),attachments:[...pendingIDs],related_record_id:f.elements.related_record_id.value?Number(f.elements.related_record_id.value):null,care_review_on:f.elements.care_review_on.value,request_key:crypto.randomUUID()};delete body.id;
  const childID=data.children.find(c=>c.name===body.child)?.id;if(!childID)throw Error('孩子归属暂时无法核对，请刷新记录');
  careFeedbackPending={body,childID,controls:[...f.querySelectorAll('input,select,textarea,button:not([type="submit"]):not([data-close])')].map(el=>({el,disabled:el.disabled}))};
  careFeedbackPending.controls.forEach(({el})=>el.disabled=true);
 }
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),45000);
 const clear=()=>{careFeedbackPending.controls.forEach(({el,disabled})=>el.disabled=disabled);careFeedbackPending=null;updateCareFields()};
 try{
  if(retry)await load();
  const r=await apiFetch('/api/care/feedback',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(careFeedbackPending.body)}),result=await r.json();
  if(r.ok){
   const body=careFeedbackPending.body,record=result.record,current=result.care,currentName=data.children.find(c=>c.id===careFeedbackPending.childID)?.name;
   const matched=result.ok===true&&Number.isSafeInteger(result.record_id)&&result.record_id>0&&record?.id===result.record_id&&typeof result.replayed==='boolean'&&!!currentName&&record.child===currentName&&['source','care_choice','care_review_on'].every(k=>record[k]===body[k]);
   if(!matched||typeof result.care_error!=='string'||(current!==null&&(!current||current.id!==body.source.slice('陪伴建议:'.length)||current.child!==currentName)))throw Error('保存回执与本次反馈不一致');
   clear();return result;
  }
  if([400,404,409].includes(r.status)&&result.not_saved===true&&result.request_known===false)clear();
  throw Error(result.error||'反馈暂时未能保存');
 }catch(error){throw Error((error.name==='AbortError'?'等待超时':error.message)+(careFeedbackPending?'。保存结果尚未核对；内容已保留，请用原编号核对并重试。':''))}
 finally{clearTimeout(timer)}
}
function careHTML(showHistory=false){
 const items=(data.care?.items||[]).filter(x=>(showHistory||(!data.care?.error&&x.expires_on>=data.today&&x.review_status!=='declined'&&!(x.review_status==='deferred'&&x.review_on>data.today)))&&(!showHistory||!child||x.child===child));
 return `<section class="card"><h2>陪伴小动作</h2><p class="muted">根据已有记录整理的建议，可选择尝试，也可告诉我不适合。</p>${data.care?.error?`<p class="error" role="status">${esc(data.care.error)}</p>`:''}${items.length?items.map(c=>{
  const feedback=data.records.filter(r=>r.source==='陪伴建议:'+c.id&&r.child===c.child).sort((a,b)=>String(b.created||'').localeCompare(String(a.created||''))||b.id-a.id);
  const reviewLabel=data.care?.error?'当前安排待核对':c.review_status==='accepted'?'愿意试试 · 不代表已经尝试或完成':c.review_status==='declined'?'暂不考虑 · 已停止推荐':c.review_status==='deferred'?(c.review_on>data.today?'已延期至 '+c.review_on:'延期回看日期已到 · 待回看'):'';
  return `<article class="task" data-query-target="care:${esc(c.id)}" tabindex="-1"><span class="chip">${esc(c.child)} · ${esc(c.topic)}</span><h3>${esc(c.title)}</h3>${reviewLabel?`<span class="chip amber">${esc(reviewLabel)}</span>`:''}${c.expires_on<data.today?'<span class="chip amber">已过期 · 历史建议</span>':''}<p class="source">原建议动作：${esc(c.action)}</p><details><summary>为什么建议这件事</summary><p class="source">${esc(c.evidence)}</p><p>计划回看：${esc(c.review_on)} · 建议有效至：${esc(c.expires_on)}</p></details>${feedback.length?`<p class="feedback">最近反馈：${esc(careChoiceText(feedback[0]))}${feedback[0].note?'<br>'+esc(feedback[0].note):feedback[0].attachments?.length?'<br>已保存原件，可在成长记录查看。':''}</p>`:''}<div class="toolbar"><button data-care="${esc(c.id)}">${feedback.length?'补充反馈':'记录选择或反馈'}</button></div></article>`
 }).join(''):empty(data.care?.error?'建议安排当前无法核对，可在历史建议中查看已有资料。':'暂时没有有依据的新建议。记录一次学习情况或孩子的原话，就能在后续检查时结合它跟进。')}${!showHistory?'<button data-page="care">查看历史建议与反馈 →</button>':''}</section>`;
}
let worldLoading;
function mountWorld(){if(window.FamilyWorld)window.FamilyWorld.mount($('#growthWorld'),data?.rewards?.children||[]);else worldLoading??=import(endpoint('/growth-world.js')).catch(()=>{worldLoading=null;toast('探索场景暂未加载，其他功能仍可使用')})}
window.addEventListener('family-world-ready',()=>{if(page==='world'&&data)mountWorld()});
function worldHTML(active){return `<section class="universe"><div id="growthWorld" class="world"><div class="world-fallback" aria-hidden="true"><i></i><i></i></div></div><div class="world-heading"><div class="orbit-label">OUR LITTLE UNIVERSE</div><h1>探索星球</h1><p>用已有记录，回看自己的探索轨迹。</p></div><div class="world-controls"><button data-world-motion aria-pressed="false">开启动效</button></div><div class="world-caption">${data.children.map((c,i)=>`<span>0${i+1} / ${esc(c.name)}的探索岛</span>`).join('')}</div></section><div class="mission-strip"><button class="mission-link" data-page="tasks"><b>☷</b><span><strong>${active.length} 件待跟进</strong><small>打个勾，留一句反馈</small></span></button><button class="mission-link" data-capture="yes"><b>◎</b><span><strong>留下成长瞬间</strong><small>拍照 · 语音 · 随手记</small></span></button><button class="mission-link" data-page="print"><b>▤</b><span><strong>准备学习资料</strong><small>勾选文件 · 提交打印</small></span></button></div><div class="grid">${data.children.map(c=>{const g=data.rewards?.children.find(x=>x.id===c.id)||{energy:0,level:0,progress:0,badges:[]},cr=data.records.filter(r=>r.child===c.name);return `<section class="card island-pass"><div class="childtop"><div class="avatar">${esc(c.name.slice(-1))}</div><div><h3>${esc(c.name)}</h3><span class="stage">${esc([c.grade,c.classroom].filter(Boolean).join(" · "))} · ${g.level?'探索 Lv.'+g.level:'等待第一颗种子'}</span></div></div><div class="energy-row"><strong>${g.energy}<small>成长能量</small></strong><span class="small muted">${g.energy?'再积累 '+Math.max(0,g.next_level_at-g.energy)+' 点，继续生长':'记录一次尝试，让小芽生长'}</span></div><div class="energy-track" role="progressbar" aria-label="${esc(c.name)}的记录能量进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${g.progress}"><i style="width:${g.progress}%"></i></div><div class="badges">${g.badges.length?g.badges.map(b=>`<span class="badge" title="${esc(b.description)}">✧ ${esc(b.name)}</span>`).join(''):'<span class="badge locked">◇ 学习探索</span><span class="badge locked">◇ 复测尝试</span><span class="badge locked">◇ 兴趣记录</span>'}</div><div class="passport-footer"><span>${cr.length} 个被记住的瞬间</span><button data-profile="${esc(c.id)}" aria-label="更正${esc(c.name)}的档案">更正档案</button><button data-child-access="${esc(c.id)}">孩子入口</button><button data-child="${esc(c.name)}">查看成长轨迹 ↗</button></div></section>`}).join('')}</div><p class="gamification-note">能量鼓励有依据的学习尝试、复测和兴趣记录。每人每天每类最多 10 点，不按成绩排名，不因断签扣分。记录可纠正，能量随之重新计算。</p>`}
function exactTaskDay(value){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value||'')||value.startsWith('0000'))return '';
 const d=new Date(value+'T12:00:00Z');return !Number.isNaN(+d)&&d.toISOString().slice(0,10)===value?value:'';
}
function todayChildHTML(c,active){
 const own=active.filter(t=>t.child===c.name),cal=data.today_calendar||{events:[],timetables:[]};
 const events=cal.events.filter(e=>e.day===data.today&&e.status!=='cancelled'&&e.child_ids.includes(c.id));
 const linked=new Map();
 for(const e of events){const t=own.find(t=>t.id===e.task_id);if(t&&!linked.has(t.id))linked.set(t.id,e)}
 const due=own.filter(t=>linked.has(t.id)||exactTaskDay(t.due)===data.today).sort((a,b)=>(linked.get(a.id)?.start_time||'99').localeCompare(linked.get(b.id)?.start_time||'99'));
 const reviews=own.filter(t=>!due.includes(t)&&taskReviewDue(t));
 const later=own.filter(t=>!due.includes(t)&&!reviews.includes(t)),past=later.filter(t=>exactTaskDay(t.due)&&t.due<data.today),other=later.filter(t=>!past.includes(t));
 const tables=cal.timetables.filter(t=>t.child_id===c.id&&t.day===data.today);
 const appointments=events.filter(e=>!e.task_id||!data.tasks.some(t=>t.id===e.task_id&&t.child===c.name));
 return `<section class="card today-child" id="today-child-${esc(c.id)}" data-today-child="${esc(c.id)}"><header class="today-child-head"><div><h2>${esc(c.name)}</h2><span class="small muted">${esc([c.grade,c.classroom].filter(Boolean).join(' · '))}</span></div><button data-today-capture="${esc(c.id)}">拍照 / 记录</button></header>
 <button class="today-study-entry" data-study-child="${esc(c.id)}"><span>今日作业</span><strong>安排 / 开始 →</strong></button>

 <div class="today-priorities"><h3 class="today-section-label">今天要处理 <span class="today-count">${due.length+appointments.length} 项</span></h3>${due.map(t=>{const e=linked.get(t.id);return taskHTML(t,{compact:true,when:e?(e.start_time?e.start_time+' · ':'')+(e.status==='tentative'?'暂定 · 先商量':'今天 · '+(calendarKinds[e.category]||'安排')):'今天到期'})}).join('')||(appointments.length?'':'<p class="today-empty">还没收录今天要处理的事项。</p>')}
 ${appointments.map(e=>`<article class="today-appointment" data-today-event="${esc(e.id)}"><span class="small muted">${esc(e.start_time||'钟点待定')} · ${esc(calendarKinds[e.category]||'安排')}${e.status==='tentative'?' · 暂定':''}${e.task_id?' · 原事项归属待核对':''}</span><h3>${esc(e.title)}</h3>${e.location?`<p>${esc(e.location)}</p>`:''}${e.note?`<p class="task-requirement">${esc(e.note)}</p>`:''}<button data-page="calendar">查看安排</button></article>`).join('')}</div>
 ${reviews.length?`<section class="today-reviews"><h3 class="today-section-label">今天回看</h3>${reviews.map(t=>taskHTML(t,{compact:true,when:'回看安排 · '+taskFocus(t).review_on})).join('')}</section>`:''}
 ${agentChildHTML(c)}
 ${past.length?`<details class="today-backlog"><summary>${past.length} 项已过日期 · 核对是否处理</summary>${past.map(t=>taskHTML(t,{compact:true,when:'日期已过 · '+t.due})).join('')}</details>`:''}
 ${other.length?`<details class="today-backlog"><summary>其它待办 ${other.length} · 含日期待核对事项</summary>${other.map(t=>taskHTML(t,{compact:true,when:exactTaskDay(t.due)?t.due:'日期待核对 · '+t.due})).join('')}</details>`:''}
 <div class="today-school">${tables.length?tables.map(t=>`<details><summary><span>在校</span> ${esc(t.sessions.map(s=>s.title).join(' · '))}</summary>${t.sessions.map(s=>`<p class="small">${esc(s.slot)} · ${esc(s.title)}</p>`).join('')}${t.note?`<p class="small">${esc(t.note)}</p>`:""}<p class="small source">${esc(t.source)}</p></details>`).join(''):`<p class="muted small">${cal.source_error?'当天课表暂时无法核对':'当天课表尚未录入'} <button data-page="calendar">补充 / 查看日历</button></p>`}</div>
 <footer class="today-child-footer"><button data-child="${esc(c.name)}">学习进展</button><button data-child-access="${esc(c.id)}">孩子入口</button><button data-profile="${esc(c.id)}" aria-label="更正${esc(c.name)}的档案">档案</button></footer></section>`;
}
function homeHTML(active){
 return `<section class="today-dashboard"><header class="today-heading"><h1>学校与作业</h1><button data-page="calendar">日历与课表 →</button></header>${sourceCoverageHTML()}${data.today_calendar?.source_error?`<p class="error" role="status">${esc(data.today_calendar.source_error)}</p>`:''}<div class="today-jump" aria-label="跳到孩子的今日事项">${data.children.map(c=>`<a href="#today-child-${esc(c.id)}">${esc(c.name)}</a>`).join('')}</div><div class="today-children">${data.children.map(c=>todayChildHTML(c,active)).join('')}</div>
 <div class="today-shortcuts"><button data-page="goals">学习目标与每日反馈</button><button data-page="tasks">待核对与跟进 · ${active.length}</button><button data-page="print">打印作业</button></div></section>`;
}

function rewardHistory(){return `<section class="card"><h2>能量从哪里来</h2><details><summary>查看能量与徽章规则</summary><p>${esc(data.rewards?.note||'记录尝试，鼓励探索；能量不代表知识掌握程度。')}</p></details>${(data.rewards?.children||[]).filter(g=>!child||g.name===child).map(g=>`<h3>${esc(g.name)} · ${g.energy} 能量</h3>${g.events.slice().reverse().slice(0,10).map(e=>`<div class="energy-event"><b>+${e.points}</b><div><button data-record="${e.source_id}">${esc(e.title)}</button><p>${esc(e.day)} · ${esc(e.reason)}</p></div></div>`).join('')||empty('尚未记录符合条件的学习尝试或兴趣实践。')}`).join('')}</section>`}
document.addEventListener('click',e=>{if(e.target.closest('[data-capture]'))$('#add').click();if(e.target.closest('[data-refresh-records]'))$('#refresh').click()});
let renderedPage='';
function captureContentFocus(){
 const root=$('#content'),el=document.activeElement;
 if(!root.contains(el)||el===root||document.querySelector('dialog[open]'))return null;
 const parts=[];
 for(let node=el;node&&node!==root;node=node.parentElement){
  if(node.id){parts.unshift('#'+CSS.escape(node.id));break}
  const attrs=[...node.attributes].filter(a=>a.name.startsWith('data-')||['name','type','href'].includes(a.name));
  const key=attrs.map(a=>'['+a.name+'="'+CSS.escape(a.value)+'"]').join('');
  const index=[...node.parentElement.children].filter(x=>x.localName===node.localName).indexOf(node)+1;
  const unique=key&&[...node.parentElement.children].filter(x=>x.matches(node.localName+key)).length===1;
  parts.unshift(node.localName+key+(unique?'':':nth-of-type('+index+')'));
 }
 return {selector:parts.join(' > '),page:renderedPage,start:el.selectionStart,end:el.selectionEnd};
}
function restoreContentFocus(saved){
 // Restore only what this synchronous render removed; dialogs and explicit jumps own their focus.
 if(!saved||document.querySelector('dialog[open]')||document.activeElement!==document.body)return;
 const root=$('#content');let target=saved.page===page?root.querySelector(saved.selector):null;
 const retained=!!target&&!target.matches(':disabled')&&!!target.getClientRects().length;
 if(!retained)target=root.querySelector('.tasktabs [aria-pressed="true"]')||root.querySelector('h1');
 if(!target)return;
 if(!target.matches('button,input,select,textarea,a[href],summary,[tabindex]'))target.tabIndex=-1;
 target.focus({preventScroll:retained});
 if(saved.page===page&&typeof saved.start==='number'&&target.matches('input,textarea')){try{target.setSelectionRange(saved.start,saved.end)}catch{}}
}
function render(){if(!data)return;const savedFocus=captureContentFocus();if(page!=='calendar')window.FamilyCalendar?.leave();window.FamilyStudy?.leave();window.FamilySettings?.leave();window.FamilyTeachers?.leave();window.FamilyWorld?.destroy();let html='';const openLearningPanels=[...document.querySelectorAll('details[data-learning-panel][open]')].map(x=>x.dataset.learningPanel);const ts=selected(data.tasks),rs=selected(data.records);const active=ts.filter(t=>!taskClosed(t));
if(page==='home'){
html=todayTasksHTML();
 }else if(page==='tasks'){
 html=taskInboxHTML();
}else if(page==='learning'){
let scores=rs.filter(r=>r.category==='成绩'&&(!subject||r.subject===subject));let subjects=[...new Set(rs.filter(r=>r.category==='成绩').map(r=>r.subject))];
html=`<div class="learning-heading"><div><h1>学习任务与进展</h1><p class="muted">选一个任务，按指南一起试，再记下实际表现。</p></div><div class="actions"><button type="button" data-course-record>记课程进度</button><button data-page="reading">阅读与作品</button></div></div>${filters()}${window.FamilyGuided?.html()||''}${learningJourneysHTML()}<details class="card learning-archive" data-learning-panel="scores"><summary>成绩记录 · ${rs.filter(r=>r.category==='成绩').length}</summary><select id="subjectFilter" aria-label="筛选成绩科目"><option value="">全部科目</option>${subjects.map(s=>`<option ${s===subject?'selected':''}>${esc(s)}</option>`).join('')}</select>${scores.length?`<p class="note">柱高为得分比例；不同考试范围、难度与满分不能直接判断进退。</p><div class="chart">${scores.slice(0,8).reverse().map(r=>`<div class="bar" style="height:${Math.max(2,r.score/r.total*100)}%"><span>${esc(r.score)}/${esc(r.total)}</span><small>${esc(r.day.slice(5))}<br>${esc(r.subject)} · ${esc(r.child)}</small></div>`).join('')}</div>${scores.map(recordHTML).join('')}`:empty('尚无成绩数据，不推算分数或排名。可以从最近一张试卷开始记录。')}</details><details class="card learning-archive" data-learning-panel="records"><summary>全部学习记录 · ${rs.filter(r=>['学习进展','课程进度'].includes(r.category)).length}</summary>${rs.filter(r=>['学习进展','课程进度'].includes(r.category)).map(recordHTML).join('')||empty('还没有学习进展记录。')}</details><details class="card learning-archive" data-learning-panel="background"><summary>成长档案与背景</summary><pre>${esc(data.growth)}</pre></details>`;
}else if(page==='world'){html=worldHTML(active);
}else if(page==='growth'){html=`<h1>成长记录</h1><button data-page="world">打开探索星球</button><p class="muted">兴趣、情绪与日常学习，都有自己的位置。</p>${filters()}${rewardHistory()}<section class="card">${rs.map(recordHTML).join('')||empty('这里会按日期保存你的观察与孩子的自述。')}</section><section class="card"><h2>已有成长档案与回顾</h2><pre>${esc(data.growth)}</pre></section>`;
}else if(page==='care'){html=`<h1>陪伴建议与反馈</h1><div class="toolbar"><button data-page="home">返回首页</button><button data-page="ask">问问助手</button></div>${careHTML(true)}`;
}else if(page==='study'){html='<div id="studyRoot"></div>';
}else if(page==='goals'){html='<div id="goalsRoot"></div>';
}else if(page==='wrong'){html='<div id="wrongRoot"></div>';
}else if(page==='teachers'){html='<div id="teachersRoot"></div>';
}else if(page==='settings'){html='<div id="settingsRoot"></div>';
}else if(page==='agent'){html=agentPageHTML();
}else if(page==='ask'){html=askHTML();
}else if(page==='calendar'){html=calendarHTML();
}else if(page==='reading'){html=readingHTML();
}else if(page==='print'){html=printHTML();
}else if(page==='more'){html=`<h1>更多</h1><div class="toolbar"><button data-capture>记录反馈</button><button data-refresh-records>刷新记录</button></div><section class="card more-links">${[['ask','问问助手'],['study','作业计时与结果'],['print','打印作业'],['sources','消息来源与附件'],['wrong','试卷错题集'],['goals','学习目标与每日反馈'],['learning','学习任务与进展'],['teachers','老师档案'],['growth','成长记录'],['reading','阅读与作品'],['care','陪伴建议'],['agent','助手跟进'],['settings','家庭设置']].map(([key,label])=>`<button data-page="${key}">${label} →</button>`).join('')}</section>${parentLogoutAvailable?'<button type="button" data-parent-logout>退出这台设备</button>':''}`;
 }else{html=`<h1>来源与附件</h1><p class="muted">这里展示已保存的采集结果。刷新页面不会立即扫描微信和QQ；历史记录也不代表接口此刻在线。</p>${currentSourceCardsHTML()}<details class="card" data-source-history ${currentSources().length?'':'open'}><summary>历史采集记录与覆盖说明</summary>${sourceCardsHTML()}</details>${inboxHTML()}<section class="card files"><h2>已保存附件</h2>${data.attachments.map(f=>`<a href="${endpoint('/attachment/')}${encodeURIComponent(f)}" download="${esc(f)}">↓ ${esc(f)}</a>`).join('')||empty('暂无附件')}</section><section class="card"><h2>来源与覆盖说明</h2><pre>${esc(data.sources)}</pre></section>`}
document.body.dataset.page=page;$('#content').innerHTML=html;for(const p of document.querySelectorAll('details[data-learning-panel]'))p.open=openLearningPanels.includes(p.dataset.learningPanel);window.FamilyGuided?.sync?.();if(page==='world')mountWorld();if(page==='print')wirePrint();if(page==='ask')wireAsk();if(page==='learning')window.FamilyGuided?.wire();if(page==='reading')wireReading();if(page==='calendar')wireCalendar();if(page==='study')mountStudy();if(page==='settings')mountSettings();if(page==='goals')window.FamilyGoals?.mount({root:$('#goalsRoot'),apiFetch,endpoint,token:data.token,children:data.children,records:data.records,agentEnabled:data.agent?.enabled,child_id:goalChildID,goal_id:goalSelectedID,focus:goalFocus,onChildChanged:id=>{goalChildID=id;goalSelectedID=''},onGoalSelected:id=>goalSelectedID=id,onTaskChanged:async()=>{try{await load(false)}catch{toast('计划已保存，任务列表暂未更新，请刷新后跟进。')}}});if(page==='wrong')window.FamilyWrongReview?.mount({root:$('#wrongRoot'),apiFetch,endpoint,token:data.token,children:data.children,uploads:data.uploads,reload:()=>load(false)});if(page==='teachers')window.FamilyTeachers?.mount({root:$('#teachersRoot'),apiFetch,token:data.token,teacherId:teacherSelectedID});document.querySelectorAll('nav button, .top-actions button').forEach(b=>{b.disabled=false;if(b.closest('nav'))b.classList.toggle('active',b.dataset.page===page||(b.dataset.page==='more'&&!['home','tasks','calendar'].includes(page)))});
$('#subjectFilter')?.addEventListener('change',e=>{subject=e.target.value;render()});restoreContentFocus(savedFocus);renderedPage=page;}
document.addEventListener('click',e=>{let b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-child-filter')){const selected=data.children.find(c=>c.id===b.dataset.childFilter);if(b.dataset.childFilter&&!selected)return;child=selected?.name||'';subject='';render();return}if(b.dataset.newTask){const f=$('#newTaskForm');f.reset();f.elements.child.innerHTML=data.children.map(c=>`<option>${esc(c.name)}</option>`).join('');if(child)f.elements.child.value=child;f.elements.box.value=b.dataset.newTask==='wish'?'wish':'inbox';f.elements.request_key.value=crypto.randomUUID();$('#newTaskError').textContent='';$('#newTaskDialog').showModal();}if(b.dataset.followup){const r=data.records.find(x=>x.id===Number(b.dataset.followup));$('#add').click();const f=$('#recordForm');f.elements.child.value=r.child;f.elements.subject.value=r.subject;f.elements.title.value=('跟进：'+r.title).slice(0,200);f.elements.related_record_id.value=r.id;f.elements.followup_kind.value=['订正','复测','补充观察'].includes(b.dataset.followupKind)?b.dataset.followupKind:'补充观察';$('#learningEvidenceFields').open=true;$('#relationTitle').textContent='关联原记录：'+r.title;$('#relationFields').classList.remove('hide');}if(b.dataset.upload){$('#add').click();pendingIDs=[b.dataset.upload];drawPending();$('#recordForm').elements.title.value=(data.uploads||[]).find(a=>a.id===b.dataset.upload)?.name||'';}if(b.dataset.care)openCareFeedback(b.dataset.care);if(b.dataset.view){taskView=b.dataset.view;render()}if(b.dataset.page){page=b.dataset.page;if(page==='home')child='';render();window.scrollTo(0,0)}if(b.dataset.child){child=b.dataset.child;page='learning';render();window.scrollTo(0,0)}if(b.dataset.close){if(b.dataset.close==='timetableDialog'&&timetableBusy)return;if(b.dataset.close==='taskDialog'&&(captureBusy()||taskFeedbackPending)){toast('请先完成当前保存或录音');return}if(b.dataset.close==='recordDialog'&&(careFeedbackPending||recordTaskLinkPending||recordTaskLinkBusy)){toast('保存结果尚未核对，请先用原编号重试');return}if(b.dataset.close==='recordDialog'&&(recorder||uploading||micPending||drafting)){toast('请等待录音、上传或整理结束');return}if(b.dataset.close==='taskDialog'&&!discardTaskFeedback())return;$('#'+b.dataset.close).close();}if(b.dataset.record){if(recordTaskLinkPending||recordTaskLinkBusy)return;if($('#taskDialog').open){if(captureBusy()||taskFeedbackPending||taskFeedbackDirty()||pendingIDs.length||$('#taskForm').elements.note.value.trim()||$('#taskTranscript').value.trim()){toast('请先保存当前反馈或状态，再打开关联记录');return}$('#taskDialog').close()}let r=data.records.find(r=>r.id===Number(b.dataset.record));if(!r){toast('记录列表尚未更新，请刷新后重试');return}$('#add').click();let f=$('#recordForm');if(![...f.elements.source.options].some(o=>o.value===r.source))f.elements.source.add(new Option(r.source,r.source));for(let k of ['id','child','day','category','subject','title','note','source','score','total','assistance','practice_relation','comparison_note'])f.elements[k].value=r[k]??'';f.elements.related_record_id.value=r.related_record_id||'';f.elements.followup_kind.value=r.followup_kind||'';$('#learningEvidenceFields').open=!!(r.assistance||r.practice_relation||r.comparison_note);$('#relationFields').classList.toggle('hide',!r.related_record_id);$('#relationTitle').textContent='关联原记录：'+(data.records.find(x=>x.id===r.related_record_id)?.title||'');pendingIDs=[...(r.attachments||[])];drawPending();updateRecordCategory();prepareRecordTaskLink(r);prepareRecordVideo(r);if(String(r.source||'').startsWith('陪伴建议:')){f.classList.add('care-mode');$('#recordDialog h2').textContent='更正这条反馈';$('#careSavedChoice').textContent='当时选择：'+careChoiceText(r)+'。更正文字不会改变原选择；要调整安排，请到建议卡片追加新反馈。';$('#careSavedChoice').classList.remove('hide');}}if(b.dataset.task){if(captureBusy()||taskFeedbackPending){toast('请先完成当前保存或录音');return}let t=data.tasks.find(t=>t.id===b.dataset.task);if(!t)return;prepareTaskCapture(t);$('#taskTitle').textContent=t.title;let f=$('#taskForm');f.elements.id.value=t.id;f.elements.expected_updated.value=t.update?.updated||'';f.elements.status.value=status(t)==='已归档'?'待跟进':status(t);f.elements.note.value='';$('#taskError').textContent='';taskFeedbackBaseline=taskFeedbackSnapshot();taskStatusBaseline=f.elements.status.value;$('#taskDialog').showModal()}});
$('#add').onclick=()=>{if(!data||uploading||recorder||micPending||drafting||careFeedbackPending||taskFeedbackPending||recordTaskLinkPending||recordTaskLinkBusy)return;prepareRecordTaskLink();prepareRecordVideo();resetTaskCapture();resetStudyRecord();resetSchoolRecord();transcriptChildExplicit=data.children.some(c=>c.name===child);formVersion++;pendingIDs=[];draft=null;draftVersion++;appliedDraft=null;$('#draftResult').innerHTML='';$('#draftStatus').textContent=data.llm?.configured?'会整理已上传的图片和填写的文字，结果由你核对后保存。':'识别服务未配置，仍可保存原件和手动记录。';$('#draftButton').disabled=!data.llm?.configured;$('#uploadStatus').textContent=failedFiles.length?'有资料未上传，可点击重试；刷新或关闭页面前请先保存。':'';for(const id of ['retryUpload','discardFailed'])$('#'+id).classList.toggle('hide',!failedFiles.length);drawPending();let f=$('#recordForm');f.reset();resetCareFeedback();f.elements.source.innerHTML=['家长观察','孩子自述','老师反馈','试卷 / 作业核对'].map(value=>'<option>'+esc(value)+'</option>').join('');f.elements.id.value='';f.elements.related_record_id.value='';f.elements.followup_kind.value='';$('#learningEvidenceFields').open=false;$('#relationFields').classList.add('hide');f.classList.remove('care-mode');$('#recordDialog h2').textContent='记下一个成长瞬间';$('#recordDialog .muted').textContent='写具体发生的事，也可以记下孩子的原话。';f.elements.note.required=false;f.elements.note.placeholder='具体情况、孩子的原话、采取的方法和后续反馈。';f.elements.child.innerHTML=data.children.map(c=>`<option>${esc(c.name)}</option>`).join('');if(child)f.elements.child.value=child;f.elements.day.value=data.today;$('#scoreFields').classList.add('hide');$('#recordError').textContent='';$('#recordDialog').showModal()};
$('#recordForm').elements.child.addEventListener('change',()=>{
 transcriptChildExplicit=true;
 const hadDraft=!!(draft||appliedDraft||drafting),f=$('#recordForm');
 if(appliedDraft){for(const [name,value] of Object.entries(appliedDraft.values))if(f.elements[name].value===value)f.elements[name].value=appliedDraft.before[name];appliedDraft=null;updateRecordCategory()}
 invalidateDraft();
 if(hadDraft)$('#draftStatus').textContent='已切换孩子，旧草稿已撤下。手动填写或修改的内容仍保留，请核对后重新整理。';
});
function updateRecordCategory(){const f=$('#recordForm'),category=f.elements.category.value;f.elements.subject.required=category==='课程进度';$('#scoreFields').classList.toggle('hide',category!=='成绩');$('#courseRecordHint').classList.toggle('hide',category!=='课程进度')}
$('#recordForm').elements.category.onchange=updateRecordCategory;
async function submit(e,path,dialog,error){
 e.preventDefault();const f=e.target,b=f.querySelector('[type=submit]'),care=f===$('#recordForm')&&careFeedbackContext,school=f===$('#recordForm')&&schoolRecordContext;
 if(f.dataset.saving)return;
 if(f===$('#recordForm')&&(recordTaskLinkPending||recordTaskLinkBusy)){$(error).textContent='任务关联保存结果尚未核对，请先重试关联。';return;}
 if(f===$('#recordForm')&&!f.elements.transcript.disabled&&recordVideoGuard?.record_id!==Number(f.elements.id.value)){$(error).textContent='转写依据尚未核对，请重新读取原视频并明确使用核对文字；输入保留。';return;}
 if(f===$('#recordForm')&&recordTaskCreateDirty()){$(error).textContent='新事项草稿尚未保存，请先新建并关联，或清空新事项草稿。';return;}
 if(f===$('#recordForm')&&recordTaskLinkContext&&!recordTaskLinkContext.inherited&&$('#recordTaskSelect').value!==recordTaskLinkContext.task_id){$(error).textContent='任务选择尚未保存，请先点“保存任务关联”。';return;}
 if((f===$('#recordForm')||f===$('#taskForm'))&&(captureBusy()||taskFeedbackPending)){toast('请等待录音、上传或整理结束');return}
 if(f===$('#taskForm')&&(pendingIDs.length||$('#taskTranscript').value.trim())){$(error).textContent='请先点“保存反馈”保留本次原件，再更新事项状态。';return}
 f.dataset.saving='yes';b.setAttribute('aria-disabled','true');$(error).textContent='';
 try{
  let result;
  if(care)result=await submitCareFeedback(f);
  else if(path==='/api/task')result=await postTask(Object.fromEntries(new FormData(f)));
  else{
   const r=await apiFetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify({...Object.fromEntries(new FormData(f)),...(f===$('#recordForm')?{...(!f.elements.transcript.disabled&&recordVideoGuard?{id:Number(f.elements.id.value),video_transcript_guard:{upload_id:recordVideoGuard.upload_id,expected_fingerprint:recordVideoGuard.expected_fingerprint},...(!f.elements.transcript.value?{transcript_state:''}:{})}:{}),attachments:pendingIDs,related_record_id:f.elements.related_record_id.value?Number(f.elements.related_record_id.value):null,...(studyRecordContext&&String(studyRecordContext.id)===f.elements.id.value?studyRecordContext.values:{}),...(school?{child:school.child,source:school.source,request_key:school.request_key}:{})}:{})})});result=await r.json();if(!r.ok){if(r.status===409&&f===$('#recordForm')&&recordVideoGuard){$('#refreshRecordTaskLink').classList.remove('hide');throw Error((result.error||'保存依据已变化')+'；转写草稿保留，请读取最新关联和视频后重新核对；若上次回执丢失，先关闭重开核对已保存文字。')}throw Error(result.error)};
  }
  $(dialog).close();
  if(care&&result.care){const current=data.care.items.find(c=>c.id===result.care.id);if(current)Object.assign(current,result.care);render()}
  const careMessage=!result.care||result.care_error?'反馈已保存，当前安排待核对。':!result.record.care_choice?'反馈已保存；只记录反馈不改安排。':result.care.choice_record_id!==result.record.id?'反馈已保存；已有更新选择，当前安排以最新记录为准。':'选择与反馈已保存；愿意试试不代表已经做过。';
  toast(care?careMessage:'已保存到家庭记录');
  try{if(path==='/api/task')render();else await load();if(school)openSchoolLearningRecord(result.record_id)}catch{toast('已保存，但列表暂时无法刷新。请稍后点“刷新记录”核对。')}
 }catch(err){$(error).textContent=err.message+(school?'。输入仍保留；重试沿用本次编号。也可关闭后从原入口核对已保存记录。':'')}
 finally{delete f.dataset.saving;b.removeAttribute('aria-disabled');if(care)b.textContent=careFeedbackPending?'核对并重试':'保存选择与反馈'}
}
$('#recordForm').onsubmit=e=>submit(e,'/api/record','#recordDialog','#recordError');$('#taskForm').onsubmit=e=>submit(e,'/api/task','#taskDialog','#taskError');$('#refresh').onclick=()=>load().then(()=>toast('已读取最新保存结果')).catch(e=>{if($('#content').dataset.ready!=='true')showStartupError(e);else toast(e.message)});window.addEventListener('DOMContentLoaded',()=>load().catch(showStartupError),{once:true});

let recordTaskLinkContext=null,recordTaskLinkPending=null,recordTaskLinkBusy=false;
function recordTaskCreateDirty(){return !$('#recordTaskLink').classList.contains('hide')&&[...$('#recordTaskCreateFields').querySelectorAll('input,select,textarea')].some(el=>el.value.trim())}
function clearRecordTaskDraft(){for(const el of $('#recordTaskCreateFields').querySelectorAll('input,select,textarea'))el.value='';$('#recordTaskCreate').open=false}
function recordTaskControls(){
 const ctx=recordTaskLinkContext,locked=recordTaskLinkBusy||!!recordTaskLinkPending;
 $('#recordTaskSelect').disabled=locked||!!ctx?.inherited;
 $('#saveRecordTaskLink').disabled=recordTaskLinkBusy||!!ctx?.inherited||!!recordTaskLinkPending?.task;
 $('#createRecordTask').disabled=recordTaskLinkBusy||!!ctx?.inherited||!!ctx?.task_id||!!(recordTaskLinkPending&&!recordTaskLinkPending.task);
 $('#recordTaskCreateFields').disabled=locked;$('#discardRecordTaskDraft').disabled=locked;
 $('#refreshRecordTaskLink').disabled=locked;
}
function prepareRecordTaskLink(record,preserveDraft=false){
 if(!preserveDraft)clearRecordTaskDraft();
 const section=$('#recordTaskLink');recordTaskLinkContext=null;section.classList.toggle('hide',!record);if(!record)return;
 const owner=data.children.find(c=>c.name===record.child||c.aliases?.includes(record.child));
 const inherited=String(record.source||'').startsWith('事项:')?record.source.slice(3):'',current=inherited||record.linked_task_id||'';
 recordTaskLinkContext={record_id:record.id,child:owner?.name||record.child,task_id:current,expected_linked_at:record.linked_task_at||'',inherited:!!inherited};
 const choices=data.tasks.filter(t=>t.child===recordTaskLinkContext.child),select=$('#recordTaskSelect');
 select.innerHTML='<option value="">未关联 / 解除关联</option>'+choices.map(t=>`<option value="${esc(t.id)}">${esc(t.title)} · ${esc(t.due||'未定日期')} · ${esc(status(t))}</option>`).join('');
 if(current&&!choices.some(t=>t.id===current))select.add(new Option('原关联任务当前不可用',current));select.value=current;
 select.disabled=!!inherited;$('#saveRecordTaskLink').disabled=!!inherited;$('#saveRecordTaskLink').textContent='保存任务关联';$('#refreshRecordTaskLink').classList.add('hide');
 $('#recordTaskCurrent').textContent=inherited?'这条反馈来自原事项，归属随原事项保留。':'当前：'+(choices.find(t=>t.id===current)?.title||(current?'原任务当前不可用':'未关联'))+'。这里只保存归属，不改记录内容或完成状态。';
 $('#recordTaskLinkStatus').textContent='';$('#recordTaskCreate').classList.toggle('hide',!!inherited);recordTaskControls();
}
async function saveRecordTaskAssociation(create=false){
 const ctx=recordTaskLinkContext,f=$('#recordForm'),button=$(create?'#createRecordTask':'#saveRecordTaskLink');if(!ctx||ctx.inherited||recordTaskLinkBusy||captureBusy()||f.dataset.saving)return;
 if(recordTaskLinkPending&&!!recordTaskLinkPending.task!==create)return;
 if(!recordTaskLinkPending){
  if(f.elements.child.value!==ctx.child){$('#recordTaskLinkStatus').textContent='孩子尚未保存，请先保存记录、重新打开后再关联任务。';return}
  if(create){
   if(ctx.task_id){$('#recordTaskLinkStatus').textContent='请先解除已有任务关联。';return}
   if($('#recordTaskSelect').value!==ctx.task_id){$('#recordTaskLinkStatus').textContent='已有任务选择尚未保存，请先核对或清空选择。';return}
   const title=$('#recordTaskTitle').value.trim();if(!title){$('#recordTaskLinkStatus').textContent='请填写新事项标题。';$('#recordTaskTitle').focus();return}
   recordTaskLinkPending={record_id:ctx.record_id,child:ctx.child,expected_linked_at:ctx.expected_linked_at,task:{request_key:crypto.randomUUID(),title,category:$('#recordTaskCategory').value,due:$('#recordTaskDue').value,action:$('#recordTaskAction').value,advice:$('#recordTaskAdvice').value}};
  }else{
   if(recordTaskCreateDirty()&&$('#recordTaskSelect').value){$('#recordTaskLinkStatus').textContent='新事项草稿尚未保存，请先新建或清空草稿。';return}
   recordTaskLinkPending={record_id:ctx.record_id,child:ctx.child,task_id:$('#recordTaskSelect').value,expected_linked_at:ctx.expected_linked_at};
  }
 }
 const body=recordTaskLinkPending;recordTaskLinkBusy=true;recordTaskControls();button.textContent=create?'正在新建并关联…':'正在保存关联…';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try{
  const response=await apiFetch(create?'/api/record/task-create':'/api/record/task-link',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)}),out=await response.json();
  if(!response.ok){if(response.status===409||response.status===400||response.status===404){recordTaskLinkPending=null;$('#refreshRecordTaskLink').classList.remove('hide')}throw Error(out.error||'关联未保存')}
  if(!out.ok||out.record_id!==body.record_id||out.link?.child!==body.child||(create?(!out.task?.id||out.link.task_id!==out.task.id||typeof out.created!=='boolean'):out.link?.task_id!==body.task_id))throw Error('关联回执不一致');
  const record=data.records.find(r=>r.id===body.record_id);recordTaskLinkPending=null;Object.assign(record,{linked_task_id:out.link.task_id,linked_task_at:out.link.linked_at});
  if(out.task){const i=data.tasks.findIndex(t=>t.id===out.task.id);if(i<0)data.tasks.push(out.task);else data.tasks[i]=out.task}
  prepareRecordTaskLink(record,!create);prepareRecordVideo(record);$('#recordTaskLinkStatus').textContent=create?'新事项与关联已保存；原记录内容尚未保存，完成状态未改变。':body.task_id?'任务关联已保存；原件与完成状态未改变。':'关联已解除；原记录和原件保留。';
 }catch(error){$('#recordTaskLinkStatus').textContent=(error.name==='AbortError'?'连接超时':error instanceof TypeError?'连接中断，请核对网络':error.message)+(recordTaskLinkPending?'。结果尚未核对，请用原选择重试。':'。选择与记录内容保留，请读取最新关联再核对。')}
 finally{clearTimeout(timer);recordTaskLinkBusy=false;recordTaskControls();$('#saveRecordTaskLink').textContent=recordTaskLinkPending&&!recordTaskLinkPending.task?'核对并重试关联':'保存任务关联';$('#createRecordTask').textContent=recordTaskLinkPending?.task?'核对并重试新建':'新建并关联'}
}
$('#saveRecordTaskLink').onclick=()=>saveRecordTaskAssociation();
$('#createRecordTask').onclick=()=>saveRecordTaskAssociation(true);
$('#discardRecordTaskDraft').onclick=()=>{if(!recordTaskLinkPending&&!recordTaskLinkBusy)clearRecordTaskDraft()};
$('#refreshRecordTaskLink').onclick=async()=>{
 if(recordTaskLinkBusy||recordTaskLinkPending||!recordTaskLinkContext)return;const button=$('#refreshRecordTaskLink'),id=recordTaskLinkContext.record_id,wanted=$('#recordTaskSelect').value;button.disabled=true;recordTaskLinkBusy=true;$('#saveRecordTaskLink').disabled=true;$('#recordTaskSelect').disabled=true;
 try{await load(false);const record=data.records.find(r=>r.id===id);if(!record)throw Error('记录当前不可用');prepareRecordTaskLink(record,true);prepareRecordVideo(record);if(!recordTaskLinkContext.inherited&&[...$('#recordTaskSelect').options].some(o=>o.value===wanted))$('#recordTaskSelect').value=wanted;$('#recordTaskLinkStatus').textContent='已读取当前关联；请核对后再保存你的选择。'}catch(error){$('#recordTaskLinkStatus').textContent=error.message+'；原选择保留。'}finally{recordTaskLinkBusy=false;recordTaskControls()}
};

let taskFeedbackContext=null,taskFeedbackPending=null,taskFeedbackBaseline='',taskStatusBaseline='';
function taskFeedbackSnapshot(){
 return JSON.stringify([$('#taskForm').elements.note.value,$('#taskFeedbackDay').value,$('#taskTranscript').value,$('#taskTranscriptState').value,pendingIDs]);
}
function taskFeedbackDirty(){return $('#taskDialog').open&&(failedFiles.length>0||taskFeedbackSnapshot()!==taskFeedbackBaseline||$('#taskForm').elements.status.value!==taskStatusBaseline)}
function discardTaskFeedback(){return !taskFeedbackDirty()||confirm('还有未保存的反馈或状态更改。确定放弃并离开当前填写吗？点“取消”继续填写。已上传的原件仍保存在资料中。')}

const sharedCapture=$('#recordForm .capture'),captureHint=sharedCapture.querySelector('.muted.small'),recordCaptureHint=captureHint.textContent;
function captureBusy(){return uploading||recorder||micPending||drafting||readingBusy||!!$('#taskForm').dataset.saving}
function resetTaskCapture(){
 taskFeedbackContext=null;captureHint.textContent=recordCaptureHint;$('#recordCaptureHome').after(sharedCapture);$('#draftButton').classList.remove('hide');
 $('#taskFeedbackHistory').innerHTML='';$('#taskTranscript').value='';$('#taskTranscriptFields').hidden=true;
}
function prepareTaskCapture(task,record=null){
 taskFeedbackContext={task_id:task.id,child:task.child,day:record?.day||data.today,category:record?.category||(task.agenda?.category==='todo'?'家长观察':'学习进展'),request_key:crypto.randomUUID(),record_id:record?.id,expected_created:record?.created,originals:record?.attachments||[]};
 $('#taskFeedbackDay').value=record?.day||data.today;formVersion++;pendingIDs=[...(record?.attachments||[])];failedFiles=[];draft=null;draftVersion++;resetCareFeedback();
 $('#taskCaptureHome').append(sharedCapture);captureHint.textContent='每份最多20MB。照片、录音或视频随这项任务保存；语音可转写核对；图片内容尚未分析，视频保存后可在这项任务的反馈里查看待核对的画面观察，不评估声音。';$('#draftButton').classList.add('hide');$('#draftResult').innerHTML='';$('#draftStatus').textContent='';$('#uploadStatus').textContent='';
 $('#retryUpload').classList.add('hide');$('#discardFailed').classList.add('hide');$('#taskTranscript').value=record?.transcript||'';
 $('#taskTranscriptState').value=record?.transcript_state||'待核对';$('#taskTranscriptFields').hidden=!record?.transcript;
 $('#taskForm').elements.note.value=record?.note||'';$('#taskFeedbackStatus').textContent=record?'正在更正这条反馈，原件保留。':'';
 $('#saveTaskFeedback').textContent=record?'保存反馈更正':'保存反馈（不改状态）';drawPending();drawTaskFeedback(task);taskFeedbackBaseline=taskFeedbackSnapshot();
}
function drawTaskFeedback(task){
 videoDraftSerial++;videoDraftViews.clear();videoReviewPending.clear();videoTranscripts.clear();
 const records=data.records.filter(r=>(r.source==='事项:'+task.id||r.linked_task_id===task.id)&&r.child===task.child);
 $('#taskFeedbackHistory').innerHTML=records.length?'<h3>这项任务的反馈</h3>'+records.map(r=>`<article class="note"><p>${esc(r.day)} · ${esc(r.note||(r.transcript?'已保存语音转写':'已保存原件，内容待核对'))}</p>${r.transcript?`<p class="source">转写（${esc(r.transcript_state)}）：${esc(r.transcript)}</p>`:''}${(r.attachments||[]).map(id=>data.uploads.find(a=>a.id===id)).filter(Boolean).map(uploadHTML).join('')}${videoDraftPanelHTML(r)}${r.source==='事项:'+task.id?`<button type="button" data-task-feedback-edit="${r.id}">更正这条反馈</button>`:`<p class="small muted">关联记录 · ${esc(r.title)} · ${esc(r.source)}</p><button type="button" data-record="${r.id}">查看 / 更正原记录</button>`}</article>`).join(''):'';
}
// Same-page read of the background task-video observation draft (#22/#23): GET only, no model, parent check only.
let videoDraftSerial=0;const videoDraftViews=new Map();
// #23 Parent review of the listed observations: only the parent's explicit click sends POST /api/record/video/review, nothing is pre-selected, the server's echoed review is what gets shown, and a reply for a closed, reopened or refreshed panel is dropped. Not a learning record; nothing consumes it.
const videoReviewPending=new Map();
const videoToken=v=>typeof v?.token==='string'&&/^[0-9a-f]{64}$/.test(v.token)?v.token:'';
const videoReviewable=v=>!!(videoToken(v)&&typeof v?.upload_id==='string'&&v.review&&typeof v.review==='object'&&!Array.isArray(v.review));
function videoObservationHTML(o){return `<span class="small muted">${clockText(o?.start_seconds)}–${clockText(o?.end_seconds)}</span> ${esc(String(o?.text??''))}`}
function videoReviewHTML(recordId,v,i,obs){
 const review=v.review&&typeof v.review==='object'&&!Array.isArray(v.review)?v.review:null;if(!review)return '';
 const confirmed=review.state==='confirmed',shown=confirmed&&Array.isArray(review.observations)?review.observations:[],can=videoReviewable(v)&&obs.length>0;
 return `<div class="video-review" data-video-review="${confirmed?'confirmed':'unconfirmed'}"><p class="source">${esc(review.label||'家长核对')}：${confirmed?`已核对${shown.length}条${review.reviewed_at?'（'+esc(String(review.reviewed_at))+'）':''}`:'尚未核对'}</p>${shown.length?`<ul class="video-observations">${shown.map(o=>`<li>${videoObservationHTML(o)}</li>`).join('')}</ul>`:''}<p class="source">${esc(review.explanation||'')}${review.revoked_at?` 已于 ${esc(String(review.revoked_at))} 撤回。`:''}</p>${can?`<p class="source" data-video-review-status>勾选你核对过的画面观察后再确认；不会自动勾选，也不代表完成或掌握。</p><button type="button" data-video-review-confirm="${recordId}" data-video-index="${i}" disabled>确认所选画面观察</button>${confirmed?` <button type="button" data-video-review-revoke="${recordId}" data-video-index="${i}">撤回核对</button>`:''}`:''}</div>`;
}
function videoDraftPanelHTML(r){
 if(!(r.attachments||[]).some(id=>String((data.uploads||[]).find(a=>a.id===id)?.mime||'').startsWith('video/')))return '';
 return `<section class="video-draft" data-video-draft="${r.id}"><p class="small muted">画面观察待家长核对；声音未评估。</p><button type="button" data-video-draft-load="${r.id}">查看画面观察 / 视频转写</button></section>`;
}
function clockText(s){s=Math.max(0,Math.round(Number(s)||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
function videoDraftHTML(recordId,view,error){
 const refresh=`<button type="button" data-video-draft-load="${recordId}">刷新</button>`;
 if(error)return `<p class="source" data-video-draft-status>${esc(error)}</p><button type="button" data-video-draft-load="${recordId}">重试读取</button>`;
 const videos=Array.isArray(view?.videos)?view.videos:[];
 if(!videos.length)return `<p class="source" data-video-draft-status>${esc(view?.explanation||'这条反馈没有可整理的视频。')}</p>${refresh}`;
 const labels={ready:'画面观察（待家长核对）',pending:'后台尚未整理完成',error:'后台整理失败',unavailable:'暂时无法整理'};
 return videos.map((v,i)=>{
  const state=labels[v?.state]?v.state:'unavailable',name=(data.uploads||[]).find(a=>a.id===v?.upload_id)?.name||'视频';
  const head=`<p class="small muted">${esc(name)} · ${labels[state]}</p>`,note=`<p class="source" data-video-draft-status>${esc(v?.explanation||'')}</p>`;
  if(state==='ready'){
   const d=v.draft&&typeof v.draft==='object'?v.draft:{},obs=Array.isArray(d.observations)?d.observations:[],unknown=Array.isArray(d.uncertainties)?d.uncertainties:[];
   const review=videoReviewHTML(recordId,v,i,obs),boxes=!!review&&videoReviewable(v),chosen=boxes&&v.review.state==='confirmed'&&Array.isArray(v.review.selected)?v.review.selected:[];
   return `<div data-video-state="ready" data-video-item="${i}">${head}${obs.length?`<ul class="video-observations">${obs.map((o,n)=>`<li>${boxes?`<label class="print-file-check"><input type="checkbox" data-video-obs="${n}"><span>`:''}${videoObservationHTML(o)}${chosen.includes(n)?' <span class="small muted">（家长已核对）</span>':''}${boxes?'</span></label>':''}</li>`).join('')}</ul>`:'<p class="source">这次没有整理出可核对的画面观察。</p>'}<p class="source">未知或看不清：${unknown.length?esc(unknown.map(String).join('；')):'无'}</p><p class="source">声音未评估；这是待核对草稿，不代表完成或掌握。</p>${review}${v.updated?`<p class="small muted">整理于 ${esc(String(v.updated))}</p>`:''}${videoTranscriptHTML(recordId,v,i)}${refresh}</div>`;
  }
  if(state==='error')return `<div data-video-state="error">${head}<p class="source" data-video-draft-status>${esc(v?.explanation||'后台整理失败')}${v?.attempts?` · 已尝试${Number(v.attempts)||0}次`:''}${v?.exhausted?' · 自动重试已停止':''}</p><button type="button" data-video-draft-retry="${recordId}" data-video-index="${i}">重试整理</button> ${videoTranscriptHTML(recordId,v,i)}${refresh}</div>`;
  return `<div data-video-state="${state}">${head}${note}${videoTranscriptHTML(recordId,v,i)}${refresh}</div>`;
 }).join('');
}
function videoDraftPanel(recordId){return $($('#recordDialog').open?'#recordVideoPanel':'#taskFeedbackHistory').querySelector(`[data-video-draft="${recordId}"]`)}
function paintVideoDraft(recordId,html){const panel=videoDraftPanel(recordId);if(panel)panel.innerHTML=html}
async function loadVideoDraft(recordId){
 const serial=videoDraftSerial;if(!videoDraftPanel(recordId)||[...videoTranscripts.values()].some(x=>x.recordId===recordId&&x.busy))return;
 for(const [key,x] of videoTranscripts)if(x.recordId===recordId)videoTranscripts.delete(key);
 videoDraftViews.delete(recordId);for(const key of [...videoReviewPending.keys()])if(key.startsWith(recordId+':'))videoReviewPending.delete(key);
 paintVideoDraft(recordId,'<p class="source" data-video-draft-status>正在读取画面观察…</p>');
 try{
  const r=await apiFetch('/api/record/video?record_id='+encodeURIComponent(recordId));let view=null;try{view=await r.json()}catch{view=null}
  if(serial!==videoDraftSerial)return;
  if(!r.ok)throw Error(r.status===401?'请先重新登录，再重试读取；本页未保存的反馈仍然保留。':view?.error||'画面观察暂时无法读取，请重试。');
  videoDraftViews.set(recordId,view);paintVideoDraft(recordId,videoDraftHTML(recordId,view));
 }catch(e){if(serial!==videoDraftSerial)return;paintVideoDraft(recordId,videoDraftHTML(recordId,null,e instanceof TypeError?'网络中断，画面观察未能读取，请重试；本页未保存的反馈仍然保留。':e.message))}
}
async function retryVideoDraft(recordId,index){
 const serial=videoDraftSerial,panel=videoDraftPanel(recordId),jobId=videoDraftViews.get(recordId)?.videos?.[index]?.job_id;
 if(!panel||typeof jobId!=='string'||!jobId)return;
 const status=panel.querySelector('[data-video-draft-status]'),buttons=[...panel.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
 if(status)status.textContent='正在安排后台重试…';
 try{await agentAction({action:'retry',id:jobId});if(serial!==videoDraftSerial)return;if(status)status.textContent='已安排后台重试，稍后点“刷新”核对结果。'}
 catch(e){if(serial!==videoDraftSerial)return;if(status)status.textContent=e instanceof TypeError?'网络中断，重试尚未安排，请再试一次。':e.status===401?'请先重新登录，再安排重试。':e.message}
 finally{if(serial===videoDraftSerial)buttons.forEach(b=>b.disabled=false)}
}
async function submitVideoReview(recordId,index,action){
 const serial=videoDraftSerial,panel=videoDraftPanel(recordId),view=videoDraftViews.get(recordId),v=view?.videos?.[index],box=panel?.querySelector(`[data-video-item="${index}"]`);
 if(!panel||!box||v?.state!=='ready'||!videoReviewable(v))return;
 const key=recordId+':'+v.upload_id,status=box.querySelector('[data-video-review-status]'),say=s=>{if(status)status.textContent=s};
 let pending=videoReviewPending.get(key);if(pending?.busy)return;
 if(!pending){
  const selected=[...new Set([...box.querySelectorAll('[data-video-obs]:checked')].map(el=>Number(el.dataset.videoObs)).filter(n=>Number.isInteger(n)&&n>=0))].sort((a,b)=>a-b);
  if(action==='confirm'&&!selected.length){say('请先勾选至少一条你核对过的画面观察。');return}
  if(action==='revoke'&&v.review.state!=='confirmed'){say('当前版本没有已核对的内容，无需撤回。');return}
  pending={body:{record_id:recordId,upload_id:v.upload_id,expected_token:videoToken(v),action,selected:action==='confirm'?selected:[]},busy:false};videoReviewPending.set(key,pending);
 }
 const body=pending.body,controls=[...box.querySelectorAll('input,button')];pending.busy=true;controls.forEach(el=>el.disabled=true);
 say(body.action==='revoke'?'正在撤回核对…':'正在保存你的核对…');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);let known=false;
 try{
  const r=await apiFetch('/api/record/video/review',{signal:controller.signal,method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)});
  let result=null;try{result=await r.json()}catch{result=null}
  if(!r.ok){known=r.status>=400&&r.status<500;const error=Error(r.status===401?'请先重新登录，再重试核对；你的勾选仍保留。':r.status===409?(result?.error||'页面上的视频观察已不是当前版本')+' 本次核对未保存，请点“刷新”后重新勾选确认。':(result?.error||'核对未保存')+'，请重试。');error.status=r.status;throw error}
  if(!result||result.record_id!==body.record_id||result.upload_id!==body.upload_id||result.token!==body.expected_token||result.action!==body.action||!result.review||typeof result.review!=='object'||Array.isArray(result.review))throw Error('核对回执与本次请求不一致');
  if(videoReviewPending.get(key)===pending)videoReviewPending.delete(key);
  if(serial!==videoDraftSerial||videoDraftViews.get(recordId)!==view)return;
  view.videos[index]={...v,review:result.review};paintVideoDraft(recordId,videoDraftHTML(recordId,view));
  const fresh=videoDraftPanel(recordId)?.querySelector(`[data-video-item="${index}"] [data-video-review-status]`);
  if(fresh)fresh.textContent=result.review.state==='confirmed'?'已按服务端回执显示你核对的画面观察；未评估声音，不代表完成或掌握。':'已撤回核对；后台保留历史，当前版本按未核对显示。';
 }catch(error){
  if(known&&videoReviewPending.get(key)===pending)videoReviewPending.delete(key);
  if(serial!==videoDraftSerial||videoDraftViews.get(recordId)!==view)return;
  say((error.name==='AbortError'?'连接超时':error instanceof TypeError?'网络中断':error.message)+(videoReviewPending.get(key)===pending?'；核对结果尚未收到回执，请用原勾选重试。':''));
 }finally{
  clearTimeout(timer);pending.busy=false;
  if(serial===videoDraftSerial&&videoDraftViews.get(recordId)===view&&box.isConnected){
   const kept=videoReviewPending.get(key)===pending,confirm=box.querySelector('[data-video-review-confirm]'),revoke=box.querySelector('[data-video-review-revoke]');
   controls.forEach(el=>{el.disabled=kept&&el.matches('[data-video-obs]')});
   if(confirm){confirm.disabled=kept?body.action!=='confirm':!box.querySelector('[data-video-obs]:checked');confirm.textContent=kept&&body.action==='confirm'?'核对并重试确认':'确认所选画面观察'}
   if(revoke){revoke.disabled=kept&&body.action!=='revoke';revoke.textContent=kept&&body.action==='revoke'?'核对并重试撤回':'撤回核对'}
  }
 }
}

// #23 A saved independent record explicitly linked to a same-child task may transcribe one of its own videos from its edit panel through the same GET/POST/review path. Unlinked, other-child or unsaved records get no entry and no call, and nothing is guessed from the subject. The record form's transcript fields stay disabled, so they are never serialized and an absent field keeps the saved transcript, until a reviewed text is explicitly applied to this same record.
let recordVideoContext=null,recordVideoGuard=null;
function prepareRecordVideo(record){
 const f=$('#recordForm'),fields=$('#recordTranscriptFields'),host=$('#recordVideoPanel');
 // An explicitly applied, still unsaved transcript draft of the same open record survives link or upload refreshes: it stays the parent's input, is never rebuilt from an older reply, and is marked stale (待核对) when the link or original changed. Nothing is saved automatically.
 const same=!!record&&f.elements.id.value===String(record.id)&&!f.elements.transcript.disabled,draft=same&&(f.elements.transcript.value!==(record.transcript||'')||f.elements.transcript_state.value!==(record.transcript_state||'待核对'))?{text:f.elements.transcript.value,state:f.elements.transcript_state.value,task_id:f.elements.transcript.dataset.videoTask||''}:null;
 videoDraftSerial++;videoDraftViews.clear();videoReviewPending.clear();videoTranscripts.clear();recordVideoContext=null;host.innerHTML='';
 for(const el of fields.querySelectorAll('textarea,select'))el.disabled=!draft;
 if(!draft){delete f.elements.transcript.dataset.videoTask;recordVideoGuard=null;}
 f.elements.transcript.value=draft?draft.text:record?.transcript||'';f.elements.transcript_state.value=draft?draft.state:record?.transcript_state||'待核对';fields.hidden=!(draft||record?.transcript);
 if(!record)return;
 const hasVideo=(record.attachments||[]).some(id=>String((data.uploads||[]).find(a=>a.id===id)?.mime||'').startsWith('video/'));
 const ctx=recordTaskLinkContext,task=hasVideo&&ctx&&ctx.record_id===record.id&&!ctx.inherited&&ctx.task_id?data.tasks.find(t=>t.id===ctx.task_id&&t.child===ctx.child):null;
 let notice='';
 if(draft&&(!task||String(task.id)!==String(draft.task_id))){f.elements.transcript_state.value='待核对';notice='<p class="note" data-video-transcript-stale>原关联或原件已变化：已填入但未保存的转写文字仍留在更正栏，并改为待核对。这段文字来自变化前的关联，请读取当前视频、明确重新转写，重新核对后再使用；旧依据不能保存到新关联，未自动保存。</p>'}
 if(!hasVideo){host.innerHTML=notice;return}
 if(!task){host.innerHTML=notice+'<p class="small muted">视频转写仅在这条记录明确关联同一孩子的事项后可用；不按科目猜测关联。</p>';return}
 recordVideoContext={record_id:record.id,task_id:task.id,child:ctx.child};host.innerHTML=notice+videoDraftPanelHTML(record);
}
async function applyRecordVideoTranscript(recordId,index){
 const view=videoDraftViews.get(recordId),v=view?.videos?.[index],entry=videoTranscripts.get(recordId+':'+v?.upload_id),box=videoDraftPanel(recordId)?.querySelector(`[data-video-transcript="${index}"]`),ctx=recordVideoContext,f=$('#recordForm');
 if(!entry?.result||!box||entry.busy||captureBusy()||f.dataset.saving||recordTaskLinkPending||recordTaskLinkBusy||ctx?.record_id!==recordId||f.elements.id.value!==String(recordId))return;
 const status=box.querySelector('[data-video-transcript-status]'),input=box.querySelector('[data-video-transcript-text]'),text=input?.value.trim(),replace=box.querySelector('[data-video-transcript-replace]'),fields=$('#recordTranscriptFields');
 const snapshot=()=>JSON.stringify([recordVideoContext,recordTaskLinkContext,pendingIDs,failedFiles.map(x=>x.name),Object.fromEntries(new FormData(f)),f.elements.transcript.value,f.elements.transcript_state.value]);
 const initial=snapshot(),serial=videoDraftSerial,old=data.records.find(r=>r.id===recordId);
 if(!text||[...text].length>4000){status.textContent='请核对1至4000字的文字。';return}
 if(f.elements.child.value!==ctx.child){status.textContent='孩子已更改，请先保存记录并重新打开后再转写；未填入。';return}
 if(!pendingIDs.includes(v.upload_id)){status.textContent='这份视频已从本条记录移除，未填入；请先恢复原件或另行保存。';return}
 if((old?.transcript||f.elements.transcript.value)&&!replace.checked){status.textContent='原记录已有转写，请明确勾选替换后再使用；原转写未覆盖。';return}
 entry.busy=true;box.querySelector('[data-video-transcript-apply]').disabled=true;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try{
  const stateResponse=await apiFetch('/api/state',{signal:controller.signal});if(!stateResponse.ok)throw Error('请恢复登录或连接，再明确点击使用；文字仍留在本页。');
  const fresh=await stateResponse.json(),response=await apiFetch('/api/record/video?record_id='+recordId,{signal:controller.signal});
  const latest=await response.json();if(!response.ok||latest.videos?.find(x=>x.upload_id===v.upload_id)?.transcription_fingerprint!==v.transcription_fingerprint)throw Error('原记录或视频版本已变化，请刷新后重新转写；未填入记录。');
  if(!$('#recordDialog').open||!box.isConnected||serial!==videoDraftSerial||videoTranscripts.get(recordId+':'+v.upload_id)!==entry)return;
  if(initial!==snapshot()||input.value.trim()!==text||((old?.transcript||f.elements.transcript.value)&&!replace.checked)||captureBusy()||f.dataset.saving||recordTaskLinkPending||recordTaskLinkBusy)throw Error('记录输入已变化，请重新核对后明确使用；未覆盖输入。');
  const record=fresh.records.find(r=>r.id===recordId),task=fresh.tasks.find(t=>t.id===ctx.task_id),owner=fresh.children.find(c=>c.name===record?.child||c.aliases?.includes(record?.child));
  if(!record||record.linked_task_id!==ctx.task_id||String(record.source||'').startsWith('事项:')||(owner?.name||record.child)!==ctx.child||!task||task.child!==ctx.child||!record.attachments?.includes(v.upload_id))throw Error('原记录归属或关联已变化，请刷新重新核对；未填入记录。');
  for(const el of fields.querySelectorAll('textarea,select'))el.disabled=false;
  f.elements.transcript.value=text;f.elements.transcript_state.value='已核对';fields.hidden=false;f.elements.transcript.dataset.videoTask=ctx.task_id;recordVideoGuard={record_id:recordId,upload_id:v.upload_id,expected_fingerprint:v.transcription_fingerprint};$('#recordVideoPanel [data-video-transcript-stale]')?.remove();
  status.textContent='已填入本条记录的转写更正栏，尚未保存；请核对后点“保存”。原说明、原件与关联保留。';f.elements.transcript.focus();
 }catch(error){if(box.isConnected&&serial===videoDraftSerial)status.textContent=error.name==='AbortError'?'读取超时，文字保留，请再核对后使用。':error instanceof TypeError?'连接中断，文字保留，请再核对后使用。':error.message}
 finally{clearTimeout(timer);entry.busy=false;if(box.isConnected)box.querySelector('[data-video-transcript-apply]').disabled=false}
}
// A transcription has no durable receipt: each explicit click is a new request, never replayed after login or a lost reply.
const videoTranscripts=new Map();
function videoTranscriptHTML(recordId,v,index){
 if(!/^[0-9a-f]{64}$/.test(v?.transcription_fingerprint||''))return '';
 const record=data.records.find(r=>r.id===recordId);
 if($('#recordDialog').open?recordVideoContext?.record_id!==recordId:record?.source!=='事项:'+taskFeedbackContext?.task_id)return '<p class="source">关联记录的转写请在原记录核对；本处不覆盖其他记录。</p>';
 return `<section data-video-transcript="${index}"><button type="button" data-video-transcribe="${recordId}" data-video-index="${index}" ${data.asr?.configured?'':'disabled'}>转写这份视频的声音</button><p class="source" data-video-transcript-status role="status">${data.asr?.configured?'仅在点击后转写；每次点击可能再次转写，结果待核对，不自动保存。':'转写服务尚未配置，仍可手动记录。'} 未分说话人，未评估声音或发音，不代表孩子答案或掌握。</p><div data-video-transcript-result></div></section>`;
}
async function requestVideoTranscript(recordId,index){
 const panel=videoDraftPanel(recordId),view=videoDraftViews.get(recordId),v=view?.videos?.[index],box=panel?.querySelector(`[data-video-transcript="${index}"]`),serial=videoDraftSerial;
 if(!box||!data.asr?.configured||!/^[0-9a-f]{64}$/.test(v?.transcription_fingerprint||''))return;
 if([...videoTranscripts.values()].some(x=>x.recordId===recordId&&x.busy))return;
 const recordMode=$('#recordDialog').open,dialog=box.closest('dialog'),taskId=recordMode?recordVideoContext?.task_id:taskFeedbackContext?.task_id;
 if(recordMode&&!pendingIDs.includes(v.upload_id)){box.querySelector('[data-video-transcript-status]').textContent='这份视频已从本条记录移除，未请求转写；请先恢复原件或另行保存。';return}
 if(recordMode&&(recordVideoContext?.record_id!==recordId||$('#recordForm').elements.child.value!==recordVideoContext.child||$('#recordForm').dataset.saving||recordTaskLinkPending||recordTaskLinkBusy||(recordTaskLinkContext&&!recordTaskLinkContext.inherited&&$('#recordTaskSelect').value!==recordTaskLinkContext.task_id))){box.querySelector('[data-video-transcript-status]').textContent='孩子或关联正在更改，请先保存记录并重新打开后再转写；未请求。';return}
 const recordBasis=()=>JSON.stringify([$('#recordForm').elements.id.value,$('#recordForm').elements.child.value,$('#recordForm').elements.source.value,$('#recordTaskSelect').value,pendingIDs]);
 const initialRecordBasis=recordMode?recordBasis():null;
 const key=recordId+':'+v.upload_id,entry={recordId,busy:true,view,serial};videoTranscripts.set(key,entry);
 const current=()=>dialog?.open&&box.isConnected&&serial===videoDraftSerial&&videoDraftViews.get(recordId)===view&&videoTranscripts.get(key)===entry;
 const status=box.querySelector('[data-video-transcript-status]'),button=box.querySelector('[data-video-transcribe]'),resultBox=box.querySelector('[data-video-transcript-result]');
 const controls=[...panel.querySelectorAll('button')].map(x=>[x,x.disabled]);controls.forEach(([x])=>x.disabled=true);resultBox.innerHTML='';status.textContent='正在转写，原记录未改动…';
 const body={record_id:recordId,upload_id:v.upload_id,expected_fingerprint:v.transcription_fingerprint},controller=new AbortController(),timer=setTimeout(()=>controller.abort(),120000);
 try{
  const response=await apiFetch('/api/record/video/transcribe',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)});
  let out=null;try{out=await response.json()}catch{}
  if(!current())return;
  if(recordMode&&recordBasis()!==initialRecordBasis)throw Error('孩子、关联或原件选择已变化，本次回执未填入；请重新核对后明确请求。');
  if(!response.ok){
   if(response.status===409){entry.stale=true;throw Error('原记录、原件或权限已变化，请点“刷新”重新读取后再明确转写。')}
   if(response.status===401)throw Error('请恢复登录后再明确点击转写；不会自动重发。');
   throw Error(out?.error||'转写未成功，原记录与输入保留。');
  }
  if(out?.record_id!==recordId||out.upload_id!==v.upload_id||out.task_id!==taskId||out.transcription_fingerprint!==body.expected_fingerprint||out.state!=='pending_review'||out.saved!==false||typeof out.text!=='string'||!out.text.trim()||[...out.text].length>4000)throw Error('转写回执与本次请求不一致，未填入记录。');
  entry.result=out;
  status.textContent='机器转写待核对；尚未写入记录。未分说话人，未评估声音或发音，不代表孩子答案或掌握。';
  resultBox.innerHTML=`<p class="source">音轨起点 ${esc(out.audio?.audio_start_seconds)} 秒 · 实际声音 ${esc(out.audio?.pcm_seconds)} 秒 · 本次提供时间范围 ${esc(out.audio?.provided_seconds)} 秒。无法证明未提供的录像尾部。</p><label>待核对文字<textarea data-video-transcript-text maxlength="4000" rows="4">${esc(out.text)}</textarea></label><label class="print-file-check"><input type="checkbox" data-video-transcript-replace><span>如原记录已有转写，我已核对并同意替换原转写（保存后仍保留更正历史）</span></label><button type="button" data-video-transcript-apply="${recordId}" data-video-index="${index}">使用已核对文字</button>`;
 }catch(error){if(current())status.textContent=(error.name==='AbortError'?'转写连接超时':error instanceof TypeError?'转写回执未收到':error.message)+' 原件和反馈输入保留；再次点击可能再次转写，不会自动请求或保存。'}
 finally{clearTimeout(timer);entry.busy=false;if(current()){controls.forEach(([x,disabled])=>x.disabled=disabled);button.disabled=!!entry.stale;button.textContent=entry.result?'重新转写（会再次请求）':'再次明确转写（可能再次请求）'}}
}
async function applyVideoTranscript(recordId,index){
 const view=videoDraftViews.get(recordId),v=view?.videos?.[index],entry=videoTranscripts.get(recordId+':'+v?.upload_id),box=videoDraftPanel(recordId)?.querySelector(`[data-video-transcript="${index}"]`);
 if(!entry?.result||!box||entry.busy||captureBusy()||taskFeedbackPending)return;
 const status=box.querySelector('[data-video-transcript-status]'),input=box.querySelector('[data-video-transcript-text]'),text=input?.value.trim(),ctx=taskFeedbackContext,f=$('#taskForm');
 const snapshot=()=>JSON.stringify([taskFeedbackContext,pendingIDs,failedFiles.map(x=>x.name),f.elements.note.value,$('#taskTranscript').value,$('#taskTranscriptState').value,$('#taskFeedbackDay').value]);
 const initial=snapshot(),serial=videoDraftSerial,replace=box.querySelector('[data-video-transcript-replace]');
 if(!text||[...text].length>4000){status.textContent='请核对1至4000字的文字。';return}
 if(ctx?.record_id!==recordId&&(ctx?.record_id||pendingIDs.length||failedFiles.length||f.elements.note.value||$('#taskTranscript').value)){status.textContent='请先保存或处理当前反馈草稿，再重新读取这条原记录；现有输入未覆盖。';return}
 const old=data.records.find(r=>r.id===recordId);
 if((old?.transcript||$('#taskTranscript').value)&&!box.querySelector('[data-video-transcript-replace]').checked){status.textContent='原记录已有转写，请明确勾选替换后再使用；原转写未覆盖。';return}
 entry.busy=true;box.querySelector('[data-video-transcript-apply]').disabled=true;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try{
  const stateResponse=await apiFetch('/api/state',{signal:controller.signal});if(!stateResponse.ok)throw Error('请恢复登录或连接，再明确点击使用；文字仍留在本页。');
  const fresh=await stateResponse.json(),response=await apiFetch('/api/record/video?record_id='+recordId,{signal:controller.signal});
  const latest=await response.json();if(!response.ok||latest.videos?.find(x=>x.upload_id===v.upload_id)?.transcription_fingerprint!==v.transcription_fingerprint)throw Error('原记录或视频版本已变化，请刷新后重新转写；未填入记录。');
  if(!$('#taskDialog').open||!box.isConnected||serial!==videoDraftSerial||videoTranscripts.get(recordId+':'+v.upload_id)!==entry)return;
  if(initial!==snapshot()||input.value.trim()!==text||((old?.transcript||$('#taskTranscript').value)&&!replace.checked)||captureBusy()||taskFeedbackPending)throw Error('反馈输入已变化，请重新核对后明确使用；未覆盖输入。');
  const record=fresh.records.find(r=>r.id===recordId),task=fresh.tasks.find(t=>t.id===ctx.task_id);
  if(!record||record.source!=='事项:'+ctx.task_id||record.child!==ctx.child||!task||!record.attachments?.includes(v.upload_id))throw Error('原记录归属已变化，请刷新重新核对。');
  if(ctx.record_id!==recordId){data=fresh;prepareTaskCapture(task,record)}
  $('#taskTranscript').value=text;$('#taskTranscriptState').value='已核对';$('#taskTranscriptFields').hidden=false;
  $('#taskFeedbackStatus').textContent='已填入同一原记录的更正栏，尚未保存；请核对后点“保存反馈更正”。';$('#taskTranscript').focus();
 }catch(error){if(box.isConnected&&serial===videoDraftSerial)status.textContent=error.name==='AbortError'?'读取超时，文字保留，请再核对后使用。':error instanceof TypeError?'连接中断，文字保留，请再核对后使用。':error.message}
 finally{clearTimeout(timer);entry.busy=false;if(box.isConnected)box.querySelector('[data-video-transcript-apply]').disabled=false}
}
for(const host of ['#taskFeedbackHistory','#recordVideoPanel'])document.querySelector(host).addEventListener('click',e=>{const b=e.target.closest('[data-video-transcribe],[data-video-transcript-apply]');if(!b||b.disabled)return;const apply=b.hasAttribute('data-video-transcript-apply');(apply?($('#recordDialog').open?applyRecordVideoTranscript:applyVideoTranscript):requestVideoTranscript)(Number(apply?b.dataset.videoTranscriptApply:b.dataset.videoTranscribe),Number(b.dataset.videoIndex))});

function lockTaskFeedback(locked){
 for(const el of $('#taskForm').querySelectorAll('input,select,textarea,button'))el.disabled=locked;
 if(!locked)captureLock(false);
 $('#saveTaskFeedback').disabled=!!$('#taskForm').dataset.saving;
}
$('#saveTaskFeedback').onclick=async()=>{
 const f=$('#taskForm'),ctx=taskFeedbackContext,wasPending=!!taskFeedbackPending;if(!ctx||captureBusy())return;
 if(failedFiles.length){$('#taskError').textContent='还有资料未上传成功，请重试或明确放弃后再保存反馈。';return}
 if(!taskFeedbackPending){
  const text=$('#taskTranscript').value.trim();
  if(!f.elements.note.value.trim()&&!pendingIDs.length&&!text){$('#taskError').textContent='请录音、选择原件或写一句反馈。';return}
  taskFeedbackPending={task_id:ctx.task_id,child:ctx.child,day:$('#taskFeedbackDay').value,category:ctx.category,note:f.elements.note.value,attachments:[...pendingIDs],transcript:text,transcript_state:text?$('#taskTranscriptState').value:'',
   ...(ctx.record_id?{record_id:ctx.record_id,expected_created:ctx.expected_created}:{request_key:ctx.request_key})};
 }
 const body=taskFeedbackPending;f.dataset.saving='yes';lockTaskFeedback(true);$('#saveTaskFeedback').textContent='正在保存反馈…';$('#taskError').textContent='';$('#taskFeedbackStatus').textContent='';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);let knownFailure=false;
 try{
  const response=await apiFetch('/api/task/feedback',{signal:controller.signal,method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok){knownFailure=response.status>=400&&response.status<500;throw Error(result.error||'保存失败')}
  if(!result.ok||!Number.isInteger(result.record_id)||result.feedback?.task_id!==body.task_id||result.feedback?.child!==body.child||result.record?.source!=='事项:'+body.task_id)throw Error('保存回执与本次反馈不一致');
  taskFeedbackPending=null;ctx.request_key=crypto.randomUUID();ctx.record_id=null;ctx.expected_created=null;ctx.originals=[];delete f.dataset.saving;lockTaskFeedback(false);
  try{await load();const task=data.tasks.find(t=>t.id===body.task_id);if(task)prepareTaskCapture(task);$('#taskFeedbackStatus').textContent='反馈已保存；事项状态未改变。'}
  catch{$('#taskFeedbackStatus').textContent='反馈已保存；列表未刷新，请关闭后刷新记录核对。';pendingIDs=[];f.elements.note.value='';$('#taskTranscript').value='';drawPending();taskFeedbackBaseline=taskFeedbackSnapshot()}
 }catch(error){
  if(knownFailure&&!wasPending)taskFeedbackPending=null;
  $('#taskError').textContent=(error.name==='AbortError'?'连接超时':error.message)+(taskFeedbackPending?'。保存结果尚未核对，请用原内容重试。':'。输入仍保留。');
 }finally{clearTimeout(timer);delete f.dataset.saving;lockTaskFeedback(!!taskFeedbackPending);$('#saveTaskFeedback').textContent=taskFeedbackPending?'核对并重试':taskFeedbackContext?.record_id?'保存反馈更正':'保存反馈（不改状态）'}
};
function closeTaskFeedback(e){e.preventDefault();if(!captureBusy()&&!taskFeedbackPending&&discardTaskFeedback())$('#taskDialog').close()}
$('#taskDialog').addEventListener('cancel',closeTaskFeedback);
// Handle Escape before the native close watcher: repeated cancel events may be non-cancelable.
$('#taskDialog').addEventListener('keydown',e=>{if(e.key==='Escape')closeTaskFeedback(e)});
$('#taskFeedbackHistory').addEventListener('click',e=>{const b=e.target.closest('[data-task-feedback-edit]');if(!b||captureBusy()||taskFeedbackPending)return;const record=data.records.find(r=>r.id===Number(b.dataset.taskFeedbackEdit)),task=data.tasks.find(t=>t.id===taskFeedbackContext?.task_id);if(record&&task&&discardTaskFeedback())prepareTaskCapture(task,record)});
for(const host of ['#taskFeedbackHistory','#recordVideoPanel'])document.querySelector(host).addEventListener('click',e=>{const b=e.target.closest('[data-video-draft-load],[data-video-draft-retry],[data-video-review-confirm],[data-video-review-revoke]');if(!b||b.disabled)return;if(b.hasAttribute('data-video-draft-load'))loadVideoDraft(Number(b.dataset.videoDraftLoad));else if(b.hasAttribute('data-video-draft-retry'))retryVideoDraft(Number(b.dataset.videoDraftRetry),Number(b.dataset.videoIndex));else submitVideoReview(Number(b.dataset.videoReviewConfirm??b.dataset.videoReviewRevoke),Number(b.dataset.videoIndex),b.hasAttribute('data-video-review-revoke')?'revoke':'confirm')});
for(const host of ['#taskFeedbackHistory','#recordVideoPanel'])document.querySelector(host).addEventListener('change',e=>{const el=e.target.closest('[data-video-obs]');if(!el)return;const box=el.closest('[data-video-item]'),button=box?.querySelector('[data-video-review-confirm]');if(button&&!box.querySelector('[data-video-obs]:disabled'))button.disabled=!box.querySelector('[data-video-obs]:checked')});

let transcriptChildExplicit=false;
let pendingIDs=[],uploading=false,formVersion=0,recorder=null,recordTimer,micPending=false,failedFiles=[];
function selectedAudio(){return pendingIDs.map(id=>(data?.uploads||[]).find(a=>a.id===id)).filter(a=>a?.mime.startsWith('audio/'))}
function drawPending(){const items=pendingIDs.map(id=>(data?.uploads||[]).find(a=>a.id===id)).filter(Boolean);$('#pendingUploads').innerHTML=items.map(a=>`${uploadHTML(a)}${taskFeedbackContext?.originals?.includes(a.id)?'':`<button type="button" data-detach="${esc(a.id)}">从本条记录移除</button>`}`).join('');$('#transcribeButton').disabled=uploading||drafting||!data?.asr?.configured||selectedAudio().length!==1;updateCareFields()}
function invalidateDraft(){draftVersion++;draft=null;$('#draftResult').innerHTML='';$('#draftStatus').textContent=data?.llm?.configured?'资料或文字已变化，可重新整理草稿。':'识别服务未配置，仍可保存原件和手动记录。'}
function captureLock(locked){if(taskFeedbackContext){$('#saveTaskFeedback').disabled=locked;$('#taskForm [type=submit]').disabled=locked;}$('#transcribeButton').disabled=locked||!data?.asr?.configured||selectedAudio().length!==1;$('#draftButton').disabled=locked||!data?.llm?.configured;$('#fileInput').disabled=locked;$('#cameraInput').disabled=locked;$('#videoInput').disabled=locked;$('#recordForm [type=submit]').disabled=locked;$('#recordAudio').disabled=uploading;}
async function uploadFiles(files){if(uploading||drafting||readingBusy||taskFeedbackPending)return;invalidateDraft();uploading=true;captureLock(true);const version=formVersion;let failures=[];for(const file of files){let timeout;try{if(file.size>20*1024*1024||!file.size)throw Error('文件为空或超过20MB');$('#uploadStatus').textContent='正在保存：'+file.name;const controller=new AbortController();timeout=setTimeout(()=>controller.abort(),120000);const r=await apiFetch('/api/upload',{signal:controller.signal,method:'POST',headers:{'X-Family-Token':data.token,'X-File-Name':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'},body:file});const result=await r.json();if(!r.ok)throw Error(result.error||'上传失败');failedFiles=failedFiles.filter(f=>f!==file);data.uploads=data.uploads||[];if(!data.uploads.some(x=>x.id===result.attachment.id))data.uploads.unshift(result.attachment);if(version===formVersion&&!pendingIDs.includes(result.attachment.id))pendingIDs.push(result.attachment.id);drawPending();}catch(err){if(!failedFiles.includes(file))failedFiles.push(file);failures.push(file.name+'：'+(err.name==='AbortError'?'上传超时，请重试':err.message))}finally{clearTimeout(timeout)}}uploading=false;captureLock(false);for(const id of ['retryUpload','discardFailed'])$('#'+id).classList.toggle('hide',!failedFiles.length);$('#uploadStatus').textContent=failures.length?failures.join('；')+'。已成功上传的原件仍保留。':taskFeedbackContext?'原件已上传；点“保存反馈”关联到这项任务。':'原件已保存，尚未加入日历或学习记录。课表请到“日历 → 导入 / 管理课表”核对导入；也可在“来源与附件”选择已保存的图片。';render();}
for(const id of ['fileInput','cameraInput','videoInput'])$('#'+id).onchange=e=>{const files=[...e.target.files];e.target.value='';uploadFiles(files)};
document.addEventListener('click',e=>{const b=e.target.closest('[data-detach]');if(b){if(uploading||drafting||recorder||micPending||taskFeedbackPending||taskFeedbackContext?.originals?.includes(b.dataset.detach))return;invalidateDraft();pendingIDs=pendingIDs.filter(id=>id!==b.dataset.detach);drawPending();toast('原件仍保存在待整理资料中')}});
$('#recordAudio').onclick=async()=>{if(micPending||readingBusy||taskFeedbackPending)return;if(recorder){recorder.stop();return}if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){$('#uploadStatus').textContent='此浏览器暂不支持录音，可用“照片 / 文件”上传已有录音。';return}let stream,current;try{micPending=true;captureLock(true);$('#recordAudio').disabled=true;stream=await navigator.mediaDevices.getUserMedia({audio:true});const mime=['audio/webm','audio/mp4','audio/ogg'].find(m=>MediaRecorder.isTypeSupported(m));current=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);recorder=current;micPending=false;let chunks=[];current.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};current.onerror=()=>{$('#uploadStatus').textContent='录音失败，请重试或上传已有录音。';};current.onstop=async()=>{clearTimeout(recordTimer);stream.getTracks().forEach(t=>t.stop());recorder=null;$('#recordAudio').textContent='录一段语音';captureLock(false);const type=current.mimeType.split(';')[0],ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':'webm';if(chunks.length)await uploadFiles([new File(chunks,'语音-'+new Date().toISOString().replace(/[:.]/g,'-')+'.'+ext,{type})]);};current.start(1000);captureLock(true);$('#recordAudio').disabled=false;$('#recordAudio').textContent='结束并保存录音';$('#uploadStatus').textContent='正在录音，最长3分钟。';recordTimer=setTimeout(()=>{if(current.state==='recording')current.stop()},180000);}catch(err){micPending=false;clearTimeout(recordTimer);stream?.getTracks().forEach(t=>t.stop());recorder=null;captureLock(false);$('#recordAudio').textContent='录一段语音';$('#recordAudio').disabled=false;$('#uploadStatus').textContent='未能开启麦克风。可检查浏览器权限，或上传已有录音。';}};
$('#recordDialog').addEventListener('cancel',e=>{if(recorder||uploading||micPending||drafting||readingBusy||careFeedbackPending||recordTaskLinkPending||recordTaskLinkBusy)e.preventDefault()});

$('#retryUpload').onclick=()=>uploadFiles([...failedFiles]);
window.addEventListener('beforeunload',e=>{if(taskFeedbackDirty()||uploading||recorder||micPending||drafting||failedFiles.length||careFeedbackPending||taskFeedbackPending||recordTaskLinkPending||recordTaskLinkBusy||recordTaskCreateDirty()||timetableBusy||timetablePending){e.preventDefault();e.returnValue='';}});

$('#discardFailed').onclick=()=>{if(uploading)return;failedFiles=[];$('#retryUpload').classList.add('hide');$('#discardFailed').classList.add('hide');$('#uploadStatus').textContent='已放弃待重试的资料，成功上传的原件仍保留。';};

let drafting=false,draft=null,draftVersion=0,appliedDraft=null;
$('#draftButton').onclick=async()=>{
 if(drafting||uploading||recorder||micPending||readingBusy)return;
 const f=$('#recordForm'),selected=data.children.find(c=>c.name===f.elements.child.value);
 if(!selected){$('#draftStatus').textContent='请先选择孩子，再整理草稿';return}
 const version=++draftVersion,text=[f.elements.title.value,f.elements.note.value].filter(Boolean).join('\n');
 const current=()=>version===draftVersion&&f.elements.child.value===selected.name;
 drafting=true;f.elements.title.readOnly=true;f.elements.note.readOnly=true;captureLock(true);$('#recordAudio').disabled=true;
 $('#draftStatus').textContent='正在为'+selected.name+'整理，原件已经保存。';$('#draftResult').innerHTML='';draft=null;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
 try{
  const r=await apiFetch('/api/draft',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify({child_id:selected.id,text,attachments:pendingIDs.filter(id=>['image/jpeg','image/png','image/webp'].includes((data.uploads||[]).find(a=>a.id===id)?.mime))})});
  const result=await r.json();if(!current())return;if(!r.ok)throw Error(result.error);
  if(result.child_id!==selected.id||result.child_name!==selected.name)throw Error('孩子归属已变化，请重新选择并整理');
  draft=result.draft;
  $('#draftResult').innerHTML=`<div class="note"><strong>${esc(selected.name)} · 请核对草稿</strong><p>${esc(draft.title)}</p><p>${esc(draft.subject)}${draft.score!==null?' · '+esc(draft.score)+' / '+esc(draft.total??'满分待核对'):''}</p><p class="source">${esc(draft.note)}</p>${draft.uncertainties.length?`<p>待核对：${draft.uncertainties.map(esc).join('；')}</p>`:''}<button type="button" id="applyDraft">填入表单，继续核对</button></div>`;
  $('#draftStatus').textContent='草稿尚未写入成长记录。请核对，再保存。';
  $('#applyDraft').onclick=()=>{
   if(!current()||!draft)return;
   const values={title:draft.title,subject:draft.subject,note:(draft.note+(draft.uncertainties.length?'\n待核对：'+draft.uncertainties.join('；'):'')).slice(0,4000),score:String(draft.score??''),total:String(draft.total??''),category:f.elements.category.value==='课程进度'?'课程进度':draft.score!==null&&draft.total!==null?'成绩':'学习进展'},before={};
   for(const [name,value] of Object.entries(values)){before[name]=appliedDraft&&f.elements[name].value===appliedDraft.values[name]?appliedDraft.before[name]:f.elements[name].value;f.elements[name].value=value}
   appliedDraft={before,values};$('#applyDraft').disabled=true;
   updateRecordCategory();
   $('#draftStatus').textContent='已填入表单，可修改任何字段；点击保存记录才会入档。';
  };
 }catch(err){if(current())$('#draftStatus').textContent=(err.name==='AbortError'?'整理超时，请稍后重试':err.message)+'。原件和当前填写内容仍保留。';}
 finally{clearTimeout(timer);drafting=false;f.elements.title.readOnly=false;f.elements.note.readOnly=false;captureLock(false);}
};

for(const name of ['title','note'])$('#recordForm').elements[name].addEventListener('input',()=>{if(draft)invalidateDraft()});

$('#newTaskForm').onsubmit=e=>submit(e,'/api/task/new','#newTaskDialog','#newTaskError');

$('#transcribeButton').onclick=async()=>{
  if(drafting||uploading||recorder||micPending||readingBusy||taskFeedbackPending)return;
  const items=selectedAudio();if(items.length!==1){toast('请每次选择一份语音');return}
  const f=taskFeedbackContext?$('#taskForm'):$('#recordForm');drafting=true;draft=null;captureLock(true);$('#recordAudio').disabled=true;
  if(f.elements.title)f.elements.title.readOnly=true;f.elements.note.readOnly=true;
  $('#draftResult').innerHTML='';$('#draftStatus').textContent='正在转写语音，原件已经保存。';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),145000);
  try{
    const r=await apiFetch('/api/transcribe',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify({attachment:items[0].id})});
    const result=await r.json();if(!r.ok)throw Error(result.error);
    if(taskFeedbackContext){
      if(typeof result.text!=='string'||result.text.length>4000)throw Error('转写超过本条4000字上限，请保留原音并分段补充');
      $('#taskTranscript').value=result.text;$('#taskTranscriptState').value='待核对';$('#taskTranscriptFields').hidden=false;
      $('#draftStatus').textContent='转写尚未保存；请核对后保存反馈。';return;
    }
    $('#draftResult').innerHTML=`<div class="note"><label>请核对听写文字<textarea id="transcriptText" maxlength="6000">${esc(result.text)}</textarea></label><button type="button" id="applyTranscript">填入详情，继续核对</button><button type="button" id="askTranscript">用于问询 / 安排</button></div>`;
    $('#draftStatus').textContent='转写文字尚未入档，请核对人名、数字与原意。';
    $('#applyTranscript').onclick=()=>{const text=$('#transcriptText').value.trim(),note=[f.elements.note.value,text].filter(Boolean).join('\n');if(!text||note.length>4000){toast('请将本条详情整理为1至4000字后填入');return}f.elements.note.value=note;$('#applyTranscript').disabled=true;$('#draftStatus').textContent='已填入详情。可继续整理文字草稿或直接核对保存。';};
    $('#askTranscript').onclick=()=>{if(careFeedbackPending||f.dataset.saving){toast('保存结果尚未核对，请先处理原表单。');return}if(uploading||recorder||micPending||drafting||readingBusy){toast('请等待录音、上传或整理结束');return}const text=$('#transcriptText').value.trim();if(!text||text.length>1000){toast('请先把这句话核对为1至1000字，再带入问询。');return}if(askState.busy){toast('请等当前问询结束再带入文字。');return}if(askState.question&&askState.question!==text&&!confirm('用这段已核对的转写替换问询框里的文字吗？'))return;askState.question=text;askState.child=transcriptChildExplicit||f.elements.id.value||f.elements.related_record_id.value||careFeedbackContext?f.elements.child.value:'';askState.initialized=true;askState.result=null;askState.error='';$('#recordDialog').close();page='ask';render();$('#askForm textarea').focus();};
  }catch(err){$('#draftStatus').textContent=(err.name==='AbortError'?'转写超时，请稍后重试':err.message)+'。原件和当前填写内容仍保留。';}
  finally{clearTimeout(timer);drafting=false;if(f.elements.title)f.elements.title.readOnly=false;f.elements.note.readOnly=false;captureLock(false);}
};

function openProfile(id){
  const c=data.children.find(c=>c.id===id);if(!c){toast('档案暂时找不到，请刷新后重试');return}
  const f=$('#profileForm');f.reset();for(const k of ['name','grade','classroom','version'])f.elements[k].value=c[k]??(k==='version'?0:'');f.elements.child_id.value=c.id;
  $('#profileError').textContent='';$('#profileHistory div').innerHTML=(c.history||[]).map(h=>`<p class="history"><time>${esc(String(h.changed).slice(0,16).replace('T',' '))}</time> · ${esc(h.reason)}<br>${['name','grade','classroom'].filter(k=>h.previous?.[k]!==h.current?.[k]).map(k=>`${({name:'称呼',grade:'年级',classroom:'班级'})[k]}：${esc(h.previous?.[k]||'未填写')} → ${esc(h.current?.[k]||'未填写')}`).join('<br>')}</p>`).join('')||'<p class="muted">还没有更正记录。</p>';
  $('#profileDialog').showModal();
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-profile]');if(b)openProfile(b.dataset.profile)});
$('#reloadProfile').onclick=async()=>{const id=$('#profileForm').elements.child_id.value;try{await load();openProfile(id)}catch(e){$('#profileError').textContent=e.message}};
$('#profileForm').onsubmit=async e=>{
  e.preventDefault();const f=e.target,buttons=[...f.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);$('#profileError').textContent='';
  try{
    const obj=Object.fromEntries(new FormData(f));obj.version=Number(obj.version);
    const r=await apiFetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(obj)}),result=await r.json();if(!r.ok)throw Error(result.error||'保存失败，请保留输入并重试');
    await load();$('#profileDialog').close();toast('档案已更正，已有记录与奖励继续保留');
  }catch(error){$('#profileError').textContent=error.message+'；当前输入已保留，可读取最新档案再核对。'}
  finally{buttons.forEach(b=>b.disabled=false)}
};

let printBusy=false,printNotice='',printPhase='';
const printDrafts=new Map(),printSelected=new Set();
let printDefaults={printer:'',copies:'1',sides:'one-sided',color:'monochrome'};
const printStorageKey='family-print-drafts:v1:'+basePath;
function persistPrintDrafts(){
  try{
    // Same-origin tab storage preserves retries across reloads; no auth headers or tokens.
    sessionStorage.setItem(printStorageKey,JSON.stringify({selected:[...printSelected],defaults:printDefaults,drafts:[...printDrafts].map(([key,d])=>[key,{source:d.source,preparation:d.preparation,prepareKey:d.prepareKey,enqueueKey:d.enqueueKey,submitted:d.submitted,pending:d.pending,settings:d.settings}])}));
    return true;
  }catch{return false}
}
try{
  const saved=JSON.parse(sessionStorage.getItem(printStorageKey)||'null');
  if(saved&&Array.isArray(saved.drafts)){
    for(const entry of saved.drafts){
      if(!Array.isArray(entry)||entry.length!==2)continue;
      const [key,d]=entry;
      if(typeof key!=='string'||!d||JSON.stringify(d.source)!==key||!['upload','attachment'].includes(d.source?.type)||typeof d.prepareKey!=='string'||typeof d.enqueueKey!=='string'||!d.settings||typeof d.settings.pages!=='string'||typeof d.settings.copies!=='string')continue;
      if(d.preparation&&(!/^[a-f0-9]{32}$/.test(d.preparation.id)||d.preparation.preview_url!=='/api/print/preview/'+d.preparation.id))continue;
      if(d.pending&&(d.pending.idempotency_key!==d.enqueueKey||d.pending.preparation_id!==d.preparation?.id))continue;
      d.error=d.pending?'上次提交结果待核对，重试会沿用原请求。':'';d.stage='';
      if(d.pending)d.pending=Object.freeze(d.pending);
      printDrafts.set(key,d);
    }
    const keys=Array.isArray(saved.selected)?saved.selected:typeof saved.selected==='string'?[saved.selected]:[];
    for(const key of keys)if(printDrafts.has(key))printSelected.add(key);
    // Migrate the original single-file v1 draft without changing its pending payload.
    const defaults=saved.defaults||printDrafts.get(keys[0])?.settings;
    if(defaults)for(const key of Object.keys(printDefaults))if(typeof defaults[key]==='string')printDefaults[key]=defaults[key];
  }
}catch{/* Invalid local drafts do not prevent reading server-side print progress. */}
function selectedPrintDrafts(){return [...printSelected].map(key=>printDrafts.get(key)).filter(Boolean)}
function refreshPrintView(){if(page==='print')render()}
function normalizePrintDefaults(){
  const printers=data?.printing?.printers||[];
  if(!printers.some(p=>p.name===printDefaults.printer))printDefaults.printer=printers.length===1?printers[0].name:'';
  const printer=printers.find(p=>p.name===printDefaults.printer);
  if(!printer?.color)printDefaults.color='monochrome';
  if(!printer?.duplex)printDefaults.sides='one-sided';
}
function applyPrintDefaults(){
  normalizePrintDefaults();
  for(const d of selectedPrintDrafts())if(!d.pending&&!d.submitted)d.settings={...d.settings,...printDefaults};
}
function newPrintDraft(source){return {source,preparation:null,prepareKey:crypto.randomUUID(),enqueueKey:crypto.randomUUID(),submitted:false,pending:null,error:'',stage:'',settings:{...printDefaults,pages:''}}}
function selectPrintSource(source,checked=true){
  if(printBusy||!source||!['upload','attachment'].includes(source.type))return;
  normalizePrintDefaults();const key=JSON.stringify(source);
  if(checked){
    if(!printDrafts.has(key))printDrafts.set(key,newPrintDraft(source));
    printSelected.add(key);
    const d=printDrafts.get(key);if(!d.pending&&!d.submitted)d.settings={...d.settings,...printDefaults};
  }else printSelected.delete(key);
  printNotice='';persistPrintDrafts();refreshPrintView();
}
const printLabels={queued:'等待家中电脑领取',claimed:'家中电脑已领取',submitted:'已进入打印机队列',spooler_completed:'队列报告完成 · 待确认取纸',received:'家长已确认拿到纸张',cancelled:'已取消',failed:'打印失败 · 需核对',uncertain:'结果不确定 · 请先核对打印机'};
function printSources(){return [...(data.attachments||[]).map(name=>({source:{type:'attachment',name},name,url:endpoint('/attachment/')+encodeURIComponent(name)})),...(data.uploads||[]).filter(a=>/\.(pdf|jpe?g|png|docx?|pptx)$/i.test(a.name)).map(a=>({source:{type:'upload',id:a.id},name:a.name,url:endpoint('/upload/')+a.id}))]}
function printSummary(){
  const selected=selectedPrintDrafts(),remaining=selected.filter(d=>!d.submitted);
  if(!selected.length)return '勾选要打印的文件，可一次选择多份资料。';
  if(!remaining.length)return `所选 ${selected.length} 个文件已提交，可在打印进展中查看。`;
  try{
    let sheets=0;
    for(const d of remaining){
      if(!d.preparation)return `已选 ${selected.length} 个文件 · 提交时自动准备资料`;
      const s=d.pending||d.settings,n=countPrintPages(s.pages.trim(),d.preparation.page_count),copies=Number(s.copies);
      if(!Number.isInteger(copies)||copies<1||copies>10)throw Error('份数须为 1–10');
      sheets+=Math.ceil(n/(s.sides==='one-sided'?1:2))*copies;
    }
    return `${remaining.length} 个文件待提交 · 预计 ${sheets} 张 A4 纸`;
  }catch{return '请检查各文件的页码和打印份数。'}
}
function printHTML(){
  applyPrintDefaults();
  const printers=data.printing?.printers||[],files=printSources(),selected=selectedPrintDrafts(),remaining=selected.filter(d=>!d.submitted),locked=printBusy||selected.some(d=>d.pending),printer=printers.find(p=>p.name===printDefaults.printer);
  return `<h1>家庭打印站</h1><p class="muted">勾选文件，选好单双面，直接提交。</p><div class="print-layout"><section class="card print-picker"><form id="printForm" novalidate><div class="section-head"><h2>要打印的文件</h2><button type="button" data-capture="yes" ${printBusy?'disabled':''}>上传资料</button></div><p class="muted small">${printers.length?'每份默认黑白打印 1 份；需要时可单独指定页码。':'尚未配置家中打印机，可以先选择资料和下载原件。'}</p>${data.printing?.error?`<p class="error">${esc(data.printing.error)}</p>`:''}<div class="print-file-list">${files.map((file,i)=>{
    const key=JSON.stringify(file.source),d=printDrafts.get(key),chosen=printSelected.has(key),job=d?.preparation&&(data.printing?.jobs||[]).find(j=>j.preparation_id===d.preparation.id);
    const state=d?.submitted?(printLabels[job?.status]||'已提交打印'):d?.pending?'提交结果待核对':d?.stage==='preparing'?'正在准备文件':d?.preparation?`${d.preparation.page_count} 页 · 已准备`:'';
    return `<article class="print-choice ${chosen?'is-selected':''}"><label class="print-file-check"><input type="checkbox" data-print-select="${i}" ${chosen?'checked':''} ${printBusy?'disabled':''}><span><strong>${esc(file.name)}</strong><small>${esc(state||(file.source.type==='upload'?'你上传的资料':'已保存的附件'))}</small></span></label><div class="print-file-tools"><a href="${file.url}" download="${esc(file.name)}">下载原件</a>${d?.preparation?`<a href="${endpoint(d.preparation.preview_url)}" target="_blank" rel="noopener">查看 PDF</a>`:''}</div>${chosen?`<label class="print-page-input">页码（选填）<input data-print-pages="${i}" value="${esc(d.settings.pages)}" maxlength="1000" placeholder="全部；例如 1-3,5" ${printBusy||d.pending||d.submitted?'disabled':''}></label>${d.pending?`<p class="small muted print-file-note">此文件沿用原设置：${d.pending.copies} 份 · ${d.pending.sides==='one-sided'?'单面':'双面'} · ${d.pending.color==='color'?'彩色':'黑白'}。重试不会新建第二个任务。</p>`:''}${d.error?`<p class="error print-file-note" role="status">${esc(d.error)}</p>`:''}`:''}</article>`;
  }).join('')||empty('上传作业、图片或保存通知附件后，可在这里勾选打印。')}</div><div class="print-settings"><label class="print-sides">单双面<select name="sides" ${locked?'disabled':''}><option value="one-sided" ${printDefaults.sides==='one-sided'?'selected':''}>单面</option><option value="two-sided-long-edge" ${printDefaults.sides==='two-sided-long-edge'?'selected':''} ${!printer?.duplex?'disabled':''}>双面 · 长边翻页</option><option value="two-sided-short-edge" ${printDefaults.sides==='two-sided-short-edge'?'selected':''} ${!printer?.duplex?'disabled':''}>双面 · 短边翻页</option></select></label><details class="print-advanced"><summary>更多设置 · ${esc(printDefaults.copies)} 份 · ${printDefaults.color==='color'?'彩色':'黑白'}</summary><div class="formrow"><label>份数<input name="copies" type="number" min="1" max="10" value="${esc(printDefaults.copies)}" ${locked?'disabled':''}></label><label>颜色<select name="color" ${locked?'disabled':''}><option value="monochrome" ${printDefaults.color==='monochrome'?'selected':''}>黑白</option><option value="color" ${printDefaults.color==='color'?'selected':''} ${!printer?.color?'disabled':''}>彩色</option></select></label></div><label>打印机<select name="printer" ${locked?'disabled':''}><option value="">${printers.length?'请选择打印机':'等待配置打印机'}</option>${printers.map(p=>`<option value="${esc(p.name)}" ${p.name===printDefaults.printer?'selected':''}>${esc(p.label||p.name)}</option>`).join('')}</select></label></details></div><div class="print-submit-area"><p id="printTotal" class="print-summary" aria-live="polite">${esc(printSummary())}</p><p id="printError" class="error" role="status">${esc(printNotice)}</p><button id="submitPrint" type="submit" class="primary" ${printBusy||!printers.length||data.printing?.error||!remaining.length?'disabled':''}>${printBusy?esc(printPhase||'正在处理…'):remaining.some(d=>d.pending)?'继续 / 核对本次提交':remaining.length?`提交打印 · ${remaining.length} 个文件`:'提交打印'}</button><p class="small muted">按 PDF 页序选页，留空打印全部。点击提交即发送所选文件；转换失败会先停下，已提交的文件不会重复提交。</p></div></form></section><section class="card print-progress"><div class="section-head"><h2>打印进展</h2><button type="button" data-refresh-print="yes" ${printBusy?'disabled':''}>刷新</button></div><p class="print-status">${printers.length?'家中电脑在线时处理已提交文件':'等待连接打印机'}</p>${(data.printing?.jobs||[]).map(j=>`<article class="print-job"><span class="chip ${j.status==='received'?'':'amber'}">${esc(printLabels[j.status]||j.status)}</span><h3>${esc(j.name)}</h3><p class="muted small">PDF ${esc(j.pages)} 页 · ${j.copies} 份 · ${j.sides==='one-sided'?'单面':'双面'} · ${j.color==='color'?'彩色':'黑白'}</p><p class="small">${esc(j.note)}</p>${j.cups_job_id?`<p class="small muted">队列编号：${esc(j.cups_job_id)}</p>`:''}${j.status==='queued'?`<button type="button" data-cancel-print="${esc(j.id)}" ${printBusy?'disabled':''}>取消未领取任务</button>`:''}${['submitted','spooler_completed'].includes(j.status)?`<form data-received-print="${esc(j.id)}"><label>纸张是否齐全<input name="note" required maxlength="1000" placeholder="例如：已拿到，页码和内容齐全" ${printBusy?'disabled':''}></label><button ${printBusy?'disabled':''}>确认拿到纸张</button></form>`:''}</article>`).join('')||empty('还没有打印任务。勾选文件后即可提交。')}</section></div>`;
}
async function printPost(path,body){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
  try{
    const r=await apiFetch('/api/print/'+path,{signal:controller.signal,method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)});
    let result;try{result=await r.json()}catch{throw Error('打印服务返回了无法读取的结果')}
    if(!r.ok){const error=Error(result.error||'打印请求未完成');error.status=r.status;throw error}
    return result;
  }catch(error){if(error.name==='AbortError')throw Error('打印请求超时');throw error}
  finally{clearTimeout(timer)}
}
function countPrintPages(value,total){
  if(!Number.isInteger(total)||total<1||total>200||typeof value!=='string'||value.length>1000)throw Error('PDF页数或页码不正确');
  if(!value||value==='all')return total;
  if(!/^[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*$/.test(value))throw Error('页码请写成 1-3,5');
  const pages=new Set();
  for(const part of value.split(',')){
    const nums=part.split('-').map(Number),a=nums[0],b=nums.at(-1);
    if(!Number.isSafeInteger(a)||!Number.isSafeInteger(b)||a>b||b>total)throw Error('页码超出这份PDF范围');
    for(let p=a;p<=b;p++)pages.add(p);
  }
  return pages.size;
}
function printRequest(d){
  const s=d.settings,n=countPrintPages(s.pages.trim(),d.preparation.page_count),copies=Number(s.copies);
  if(!Number.isInteger(copies)||copies<1||copies>10)throw Error('份数须为 1–10');
  if(n*copies>500)throw Error('每个文件最多 500 个页面副本');
  const printer=(data.printing?.printers||[]).find(p=>p.name===s.printer);
  if(!printer)throw Error('请先选择已配置的打印机');
  if(!['one-sided','two-sided-long-edge','two-sided-short-edge'].includes(s.sides)||s.sides!=='one-sided'&&!printer.duplex)throw Error('这台打印机未配置双面能力');
  if(!['monochrome','color'].includes(s.color)||s.color==='color'&&!printer.color)throw Error('这台打印机未配置彩色能力');
  return {printer:s.printer,pages:s.pages.trim()||'all',copies,sides:s.sides,color:s.color,confirmed:true,preparation_id:d.preparation.id,pdf_sha256:d.preparation.pdf_sha256,idempotency_key:d.enqueueKey};
}
async function submitPrintBatch(){
  if(printBusy)return;
  applyPrintDefaults();const batch=selectedPrintDrafts().filter(d=>!d.submitted);
  if(!batch.length){printNotice='请勾选尚未提交的文件。';refreshPrintView();return}
  if(data.printing?.error||!data.printing?.printers?.length){printNotice=data.printing?.error||'请先配置家中打印机。';refreshPrintView();return}
  if(!persistPrintDrafts()){printNotice='无法保存本次请求编号，请启用站点存储后再提交打印。';refreshPrintView();return}
  printBusy=true;printNotice='';printPhase='正在准备文件…';
  for(const d of batch)d.error='';refreshPrintView();
  let active=null;
  try{
    // Complete every conversion before enqueuing anything, including later files.
    for(const d of batch){
      if(d.submitted)continue;active=d;
      if(!d.preparation){
        d.stage='preparing';refreshPrintView();
        const result=await printPost('prepare',{source:d.source,idempotency_key:d.prepareKey}),p=result.preparation;
        if(!p||!/^[a-f0-9]{32}$/.test(p.id)||!/^[a-f0-9]{64}$/.test(p.pdf_sha256)||p.preview_url!=='/api/print/preview/'+p.id)throw Error('文件准备结果不完整，请重试');
        countPrintPages('',p.page_count);d.preparation=p;d.stage='';
        if(!persistPrintDrafts())throw Error('无法保存文件准备状态，已暂停提交');
        refreshPrintView();
      }
    }
    const requests=new Map();
    for(const d of batch){
      if(d.submitted)continue;active=d;
      if(d.pending){
        printRequest({...d,settings:d.pending}); // Validate current capabilities without rewriting the saved payload.
        requests.set(d,d.pending);
      }else requests.set(d,Object.freeze(printRequest(d)));
    }
    printPhase='正在提交打印…';refreshPrintView();
    for(const d of batch){
      if(d.submitted)continue;active=d;
      const payload=requests.get(d);d.pending=payload;
      if(!persistPrintDrafts())throw Error('无法保存本次请求编号，已暂停提交');
      try{
        const result=await printPost('enqueue',payload);
        if(!result.job?.id)throw Error('打印服务未返回任务编号');
        d.submitted=true;d.pending=null;d.error='';
        data.printing.jobs=[result.job,...(data.printing.jobs||[]).filter(j=>j.id!==result.job.id)];
      }catch(error){
        if(d.submitted){d.error='';continue} // A concurrent refresh already found this job.
        if(error.status>=400&&error.status<500&&error.status!==409)d.pending=null;
        throw error;
      }
      if(!persistPrintDrafts())throw Error('本机状态未保存，已暂停后续文件；请刷新进展核对');
      refreshPrintView();
    }
    printNotice='所选文件已提交，可在打印进展中查看。';
    toast('打印任务已保存，等待家中电脑处理');
  }catch(error){
    if(active&&!active.submitted)active.error=error.message+(active.pending?'；结果待核对，重试将沿用原请求。':'');
    const done=batch.filter(d=>d.submitted).length;
    printNotice=`已暂停：本次 ${done} / ${batch.length} 个文件已确认提交。${error.message}。已成功的文件不会重复提交。`;
  }finally{
    for(const d of batch)d.stage='';printBusy=false;printPhase='';persistPrintDrafts();refreshPrintView();
  }
}
function wirePrint(){
  const f=$('#printForm');if(!f)return;
  const updateSummary=()=>{const el=$('#printTotal');if(el)el.textContent=printSummary()};
  const changed=e=>{
    if(printBusy)return;const el=e.target;
    if(el.dataset?.printSelect!==undefined){
      if(e.type==='input')return;
      const file=printSources()[Number(el.dataset.printSelect)];if(file)selectPrintSource(file.source,el.checked);return;
    }
    if(el.dataset?.printPages!==undefined){
      const file=printSources()[Number(el.dataset.printPages)],d=file&&printDrafts.get(JSON.stringify(file.source));
      if(!d||d.pending||d.submitted)return;
      d.settings.pages=el.value;d.error='';printNotice='';el.closest('.print-choice')?.querySelector('.error')?.remove();const error=$('#printError');if(error)error.textContent='';persistPrintDrafts();updateSummary();return;
    }
    if(!Object.prototype.hasOwnProperty.call(printDefaults,el.name)||selectedPrintDrafts().some(d=>d.pending))return;
    for(const key of Object.keys(printDefaults))printDefaults[key]=f.elements[key].value;
    applyPrintDefaults();printNotice='';persistPrintDrafts();
    if(e.type==='change')refreshPrintView();else updateSummary();
  };
  f.addEventListener('input',changed);f.addEventListener('change',changed);
  f.onsubmit=e=>{e.preventDefault();return submitPrintBatch()};
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.cancelPrint){if(printBusy)return;b.disabled=true;try{await printPost('cancel',{job_id:b.dataset.cancelPrint});await refreshPrintJobs();toast('已取消，尚未送入打印机')}catch(error){toast(error.message)}finally{b.disabled=false}}
  if(b.dataset.refreshPrint){b.disabled=true;try{await refreshPrintJobs()}catch(error){toast(error.message)}finally{b.disabled=false}}
});
async function refreshPrintJobs(){
  const r=await apiFetch('/api/print/jobs');if(!r.ok)throw Error('读取打印进展失败');
  const result=await r.json();if(!Array.isArray(result.jobs))throw Error('打印进展格式不正确');data.printing.jobs=result.jobs;
  for(const d of printDrafts.values())if(d.preparation&&result.jobs.some(j=>j.preparation_id===d.preparation.id)){
    d.submitted=true;d.pending=null;d.error='';
  }
  persistPrintDrafts();refreshPrintView();
}
document.addEventListener('submit',async e=>{
  const f=e.target;if(!f.dataset.receivedPrint)return;e.preventDefault();if(printBusy)return;const b=f.querySelector('button');b.disabled=true;
  try{await printPost('received',{job_id:f.dataset.receivedPrint,note:f.elements.note.value});await refreshPrintJobs();toast('已记下你确认拿到的纸张')}
  catch(error){toast(error.message)}finally{b.disabled=false}
});

const askState={child:'',question:'',start:'',end:'',initialized:false,result:null,answeredQuestion:'',answeredChild:'',askedAt:'',busy:false,operation:'',error:'',calendarDraft:null};
function askHTML(){
  if(!askState.initialized){askState.child=data.children.some(c=>c.name===child)?child:'';askState.initialized=true}
  if(askState.child&&!data.children.some(c=>c.name===askState.child)){askState.child='';askState.result=null}
  const a=askState,result=a.result,d=a.calendarDraft;
  return `<h1>问问成长助手</h1><p class="muted">查已有安排，或说一句接下来想做的事。</p><div class="ask-layout"><section class="card"><form id="askForm"><label>这次说的是谁<select name="child" ${a.busy?'disabled':''}><option value="">暂不指定 · 可在句中说孩子</option>${data.children.map(c=>`<option value="${esc(c.name)}" ${c.name===a.child?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label>你想问什么，或安排什么<textarea name="question" required maxlength="1000" placeholder="例如：下周末有什么安排？或：周六下午三点带两个孩子去公园。" ${a.busy?'readonly':''}>${esc(a.question)}</textarea></label><div class="ask-prompts">${['下周末有什么安排？','明天要带什么去学校？','最近的学习进展和复测情况怎样？'].map(q=>`<button type="button" data-ask-prompt="${esc(q)}" ${a.busy?'disabled':''}>${esc(q)}</button>`).join('')}</div><details class="ask-citation" ${a.start||a.end?'open':''}><summary>限定查询日期 · 可选</summary><p class="small muted">不填写时，按问题里的日期查。这里不决定新安排的日期。</p><div class="formrow"><label>从哪天<input name="start" type="date" value="${esc(a.start)}" ${a.busy?'disabled':''}></label><label>到哪天<input name="end" type="date" value="${esc(a.end)}" ${a.start?`min="${esc(a.start)}"`:''} ${a.busy?'disabled':''}></label></div><div class="ask-prompts"><button type="button" data-ask-range="week" ${a.busy?'disabled':''}>本周</button><button type="button" data-ask-range="weekend" ${a.busy?'disabled':''}>本周末</button><button type="button" data-ask-range="clear" ${a.busy?'disabled':''}>按问题里的日期</button></div></details><p class="error" id="askError" role="alert">${esc(a.error)}</p><div class="toolbar"><button class="primary" type="submit" ${a.busy?'disabled':''}>${a.busy&&a.operation==='query'?'正在查询…':'查已有记录'}</button><button type="button" id="askCalendarDraft" ${a.busy?'disabled':''}>${a.busy&&a.operation==='draft'?'正在整理…':'整理成日历'}</button></div><p class="muted small">可以用手机键盘语音输入。已有录音转写后，也可带到这里。整理后先核对，点击“保存安排”才会写入日历。</p></form>${d?`<section class="note" id="askCalendarResult"><strong>${d.saved?'这份安排已保存':d.draft?'有一份日历草稿待核对':'先核对你的意图'}</strong><p class="small">按 ${esc(d.reference_date)} 理解相对日期${!d.saved&&calendarDraftMissing(d)?` · 待核对：${esc(calendarDraftMissing(d))}`:''}</p>${!d.draft?`<p>${esc(({edit:'请到日历打开原安排，核对后修改。',cancel:'请到日历打开原安排，核对后取消。',query:'这是一次查询，请选择孩子后查已有记录。',unclear:'请补充想安排什么，再整理一次。'}[d.intent]))}</p>`:''}${calendarDraftDetails(d)}${d.saved||!d.draft?'<button type="button" data-page="calendar">查看日历</button>':'<button type="button" data-ask-open-draft>继续核对这份草稿</button>'}</section>`:''}${window.FamilyCalendar?.hasPending()?'<p class="note">另有一次安排保存结果未确认。<button type="button" data-calendar-resume>继续核对原保存</button></p>':''}</section><section class="card ask-answer" tabindex="-1" aria-busy="${a.busy&&a.operation==='query'}"><h2>${result?'查到的情况':'已有安排与进展'}</h2>${a.busy&&a.operation==='query'?'<p role="status">正在结合已保存资料查找依据。</p>':result?`<p class="small muted">${esc(a.answeredChild)} · ${esc(a.askedAt)} 的查询结果</p><p class="small source">你问的是：${esc(a.answeredQuestion)}</p>${result.calendar_range?`<p class="note" id="askCalendarRange">本次日历范围：${esc(result.calendar_range.start)} 至 ${esc(result.calendar_range.end)}${result.calendar_range.defaulted?' · 未指定日期，使用本周':''}</p>`:''}<p class="source ask-text">${esc(result.answer)}</p><p class="muted small">依据已保存记录，未包括未读附件和未录入资料。</p><details class="ask-scope"><summary>本次查了哪些资料</summary><p class="source">${esc(result.coverage)}</p></details><h3>这次回答的依据</h3>${result.citations.map((c,i)=>`<details class="ask-citation"><summary>${i+1}. ${esc(c.title)}${c.day?' · '+esc(c.day):''}</summary><p class="source">${esc(c.detail)}</p><button data-ask-citation="${i}">打开${({record:'成长记录',task:'原事项',care:'陪伴建议',reading:'阅读作品',reading_balance:'印章小铺',reading_redemption:'兑现约定',calendar:'日历当天安排',timetable:'当天课表',teacher:'老师档案'}[c.kind]||'来源')}</button></details>`).join('')||'<p class="muted small">目前没有可引用的个人记录。</p>'}`:empty('查记录时先选一位孩子；想加安排，可以直接说时间、孩子和要做的事。')}<div class="toolbar"><button data-page="tasks">查看行动清单</button><button data-capture="yes">补充一件事</button></div></section></div>`;
}
function askOpenCalendarDraft(){
  const context=askState.calendarDraft;if(!context?.draft||context.saved)return;
  if(!window.FamilyCalendar.openDraft(context)){askState.error='上一次保存结果还未核对。新草稿已保留，请先继续核对原保存。';if(page==='ask')render()}
}
function wireAsk(){
  const f=$('#askForm');
  f.elements.question.oninput=()=>{askState.question=f.elements.question.value;askState.error='';$('#askError').textContent=''};
  f.elements.child.onchange=()=>{askState.child=f.elements.child.value;askState.result=null;askState.error='';render()};
  for(const name of ['start','end'])f.elements[name].onchange=()=>{askState[name]=f.elements[name].value;askState.error='';$('#askError').textContent='';if(name==='start')f.elements.end.min=askState.start};
  f.onsubmit=e=>{e.preventDefault();askRun('query')};
  $('#askCalendarDraft').onclick=()=>askRun('draft');
}
async function askRun(operation){
  const f=$('#askForm');if(askState.busy||!f||!(operation==='query'?f.reportValidity():f.elements.question.reportValidity()))return;
  Object.assign(askState,{question:f.elements.question.value,child:f.elements.child.value,start:f.elements.start.value,end:f.elements.end.value});
  const a=askState,question=a.question.trim(),requestedChild=a.child;
  if(!question)return;
  if(operation==='query'&&(!requestedChild||!!a.start!==!!a.end||a.start&&a.end<a.start)){a.error=!requestedChild?'查记录时请先选一位孩子。':'请一起填写起止日期，并确认结束不早于开始。';render();return}
  if(operation==='draft'&&a.calendarDraft?.draft&&!a.calendarDraft.saved&&!confirm('已有一份尚未保存的日历草稿。重新整理成功后会替换它，继续吗？'))return;
  a.busy=true;a.operation=operation;a.error='';if(operation==='query')a.result=null;render();
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
  try{
    const body=operation==='query'?{child:requestedChild,question,...(a.start&&a.end?{start:a.start,end:a.end}:{})}:{text:question,child_ids:requestedChild?[data.children.find(c=>c.name===requestedChild).id]:[]};
    const r=await apiFetch(operation==='query'?'/api/ask':'/api/calendar/draft',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)}),result=await r.json();
    if(!r.ok)throw Error(result.error||'暂时未能整理，请稍后重试');
    if(requestedChild!==a.child)throw Error('档案已更正，请重新查询或整理。');
    if(operation==='query'){
      if(typeof result.answer!=='string'||typeof result.coverage!=='string'||!Array.isArray(result.citations))throw Error('回答格式不正确，请重试');
      a.result=result;a.answeredQuestion=question;a.answeredChild=requestedChild;a.askedAt=new Date().toLocaleString('zh-CN',{hour12:false});
    }else{
      const d=result.draft;
      if(!['create','edit','cancel','query','unclear'].includes(result.intent)||!Array.isArray(result.needs_review)||typeof result.reference_date!=='string'||result.intent==='create'&&(!d||!Array.isArray(d.child_ids)||d.child_ids.some(id=>!data.children.some(c=>c.id===id))||typeof d.day!=='string'||typeof d.title!=='string'))throw Error('草稿格式无法核对，请重试');
      a.calendarDraft={draft:result.intent==='create'?{...d,child_ids:[...d.child_ids],day:d.day}:null,intent:result.intent,needs_review:result.needs_review,text:question,reference_date:result.reference_date,saved:false,form:null};
    }
  }catch(error){a.error=(error.name==='AbortError'?'整理等待超时':error.message)+'。原话和已有草稿仍保留，可以重试。'}
  finally{clearTimeout(timer);a.busy=false;a.operation='';if(page==='ask'){render();if(!a.error){if(operation==='draft')askOpenCalendarDraft();else{const answer=$('.ask-answer');answer.focus({preventScroll:true});if(matchMedia('(max-width:850px)').matches)answer.scrollIntoView({block:'start'})}}}}
}
function askFromCalendar(){
  if(askState.busy){page='ask';render();return}
  askState.child=data.children.find(c=>c.id===calendarState.childID)?.name||'';askState.initialized=true;askState.result=null;askState.error='';page='ask';render();$('#askForm textarea').focus();
}
document.addEventListener('click',async e=>{
  const prompt=e.target.closest('[data-ask-prompt]');
  if(prompt&&!askState.busy){askState.question=prompt.dataset.askPrompt;askState.error='';render();$('#askForm textarea').focus()}
  const range=e.target.closest('[data-ask-range]');
  if(range&&!askState.busy){const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()),monday=calendarMonday(today);askState.start=range.dataset.askRange==='clear'?'':calendarAdd(monday,range.dataset.askRange==='weekend'?5:0);askState.end=range.dataset.askRange==='clear'?'':calendarAdd(monday,6);askState.error='';render()}
  if(e.target.closest('[data-ask-open-draft]'))askOpenCalendarDraft();
  if(e.target.closest('[data-calendar-ask]')){askFromCalendar();return}
  const button=e.target.closest('[data-ask-citation]');if(!button)return;
  const c=askState.result?.citations[Number(button.dataset.askCitation)];if(!c)return;
  if(!['record','task','care','reading','reading_balance','reading_redemption','calendar','timetable','teacher'].includes(c.kind)||askState.openingSource)return;
  askState.openingSource=true;button.disabled=true;const answer=askState.result,sourceChildID=data.children.find(x=>x.name===c.child)?.id;
  try{
    const r=await apiFetch('/api/state');if(!r.ok)throw Error('读取原记录失败，请重试');
    const latest=await r.json();if(page!=='ask'||askState.result!==answer)return;data=latest;
  }catch(error){toast(error.message);return}
  finally{askState.openingSource=false;if(button.isConnected)button.disabled=false}
  child=data.children.find(x=>x.id===sourceChildID)?.name||c.child;subject='';
  if(c.kind==='teacher'){teacherSelectedID=c.target_id;page='teachers';render();window.scrollTo(0,0);return}
  if(['calendar','timetable'].includes(c.kind)){await window.FamilyCalendar.openCitation(c,sourceChildID);return}
  page=c.kind==='record'?'growth':c.kind==='task'?'tasks':c.kind==='care'?'care':'reading';taskView='全部';if(page==='reading')readingView='全部';render();
  const target=[...document.querySelectorAll('[data-query-target]')].find(el=>el.dataset.queryTarget===c.kind+':'+c.target_id);
  if(target)revealLearningTarget(target);else toast('原记录可能已更新或建议已过期，请刷新后重新查询。');
});

document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.todayCapture){const c=data.children.find(c=>c.id===b.dataset.todayCapture);if(!c)return;$('#add').click();if(!$('#recordDialog').open)return;const f=$('#recordForm');f.elements.child.value=c.name;transcriptChildExplicit=true;f.elements.category.value='学习进展';$('#recordDialog h2').textContent='记学习 · '+c.name;f.elements.note.placeholder='今天学了什么？哪里顺利或卡住了？是自己完成，还是有人帮忙？也可以记录孩子的原话。';}
});

function agentTime(value){return value&&Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'尚未记录或时间待核对'}
function agentPending(childID){return (data.agent?.items||[]).filter(x=>x.state==='pending'&&(!childID||x.child_id===childID)&&(!x.plan?.exam_result_pending||data.tasks.some(t=>t.id===x.task_id&&!taskClosed(t))))}
// School evidence uses the existing record form and source key; it never completes a task.
function resetSchoolRecord(){
 schoolRecordContext=null;const f=$('#recordForm');f.elements.subject.required=false;for(const key of ['child','source','category'])f.elements[key].disabled=false;f.elements.category.innerHTML=data.record_categories.map(v=>'<option>'+esc(v)+'</option>').join('');$('#courseRecordHint').classList.add('hide');
}
function schoolRecordEvidence(origin){
 if(origin.material){
  const view=origin.material,owner=data.children.find(c=>c.id===view.child_id),d=view.material_draft;
  if(!owner||d?.kind||d?.state!=='ready'||!d.upload_ids?.length||d.upload_ids.some(id=>!view.attachments.some(a=>a.id===id)))return null;
  const source='message:'+view.source_id+':'+view.message_id;if(source.length>200)return null;
  const draft=d.draft,note=('图片识别草稿，待家长核对；不能据此认定完成或掌握。\n'+draft.note+(draft.uncertainties?.length?'\n待核对：'+draft.uncertainties.join('；'):'')).slice(0,4000);
  return {child:owner.name,child_id:owner.id,title:draft.title,source,aliases:[source],note,draft,attachments:d.upload_ids};
 }
 const item=origin.agent?(data.agent?.items||[]).find(x=>x.id===origin.agent&&x.kind==='school'):null;
 const task=origin.task?data.tasks.find(t=>t.id===origin.task):item?.task_id?data.tasks.find(t=>t.id===item.task_id):null;
 if(!item&&!task)return null;
 const owner=item?data.children.find(c=>c.id===item.child_id):data.children.find(c=>c.name===task.child);
 if(!owner||task&&task.child!==owner.name)return null;
 const sourceText=String(task?.source||''),agentKey=item?'Agent建议:'+item.id:sourceText.split('\n')[0].match(/^Agent建议:[A-Za-z0-9_-]+$/)?.[0];
 const refs=[...new Set(item?(item.evidence||[]).map(e=>e.ref).filter(r=>typeof r==='string'&&r.startsWith('message:')):sourceText.split('\n').filter(r=>/^message:[^\s]+$/.test(r)))];
 const source=origin.exam&&task?'事项:'+task.id:(refs.length===1&&refs[0].length<=200?refs[0]:agentKey||'事项:'+task.id);
 const aliases=[source,agentKey,task?'事项:'+task.id:null].filter(Boolean);
 const history=task?.history?.length?[...task.history].reverse():task?.update?[task.update]:[];
 const original=item?(item.evidence||[]).map(e=>e.ref+'\n'+(e.text||e.quote||'')).join('\n\n'):sourceText;
 const parts=['待核对的学习事件：原消息与以下反馈保留各自说法，实际完成情况尚未核实。',
  '原出处：'+source,original?'原消息 / 出处说明：\n'+original:'原消息正文尚未保存，请补充核对。',
  task?.action?'事项原要求：'+task.action:'',history.length?'已有事项反馈（保留当时说法，不代表老师已确认或已完成）：\n'+history.map(h=>(h.updated||'日期未记录')+' · '+taskStatusLabel(h.status)+'\n'+(h.note||'未写说明')).join('\n\n'):'',
  '请补充实际发生日期、孩子的说法与核对结果；未读图片请添加原件核对。'].filter(Boolean);
 const full=parts.join('\n\n'),note=full.length<=4000?full:full.slice(0,3850)+'\n\n（内容较长，本表单仅预填部分；完整出处与反馈仍在原事项中，请核对后整理。）';
 return {child:owner.name,child_id:owner.id,title:(task?.title||item.title).slice(0,200),source,aliases,note};
}
function openSchoolLearningRecord(id){
 const record=data.records.find(r=>r.id===Number(id));if(!record)return false;
 child=record.child;page='learning';render();
 const group=learningCases(data.records,child).find(g=>g.items.some(r=>r.id===record.id));
 const target=group?document.querySelector('[data-learning-case="'+group.root.id+'"]'):document.querySelector('[data-query-target="record:'+record.id+'"]');
 if(target){target.tabIndex=-1;revealLearningTarget(target)}return !!target;
}
async function openSchoolRecord(origin,button){
 if(schoolRecordOpening||document.querySelector('dialog[open]')||uploading||recorder||micPending||drafting||careFeedbackPending)return;
 schoolRecordOpening=true;button.disabled=true;const seq=++stateLoadSequence;
 try{
  const response=await apiFetch('/api/state',{signal:AbortSignal.timeout(12000)});if(!response.ok)throw Error('当前资料无法核对，请刷新后重试。');
  const latest=await response.json();if(seq!==stateLoadSequence||!button.isConnected||document.querySelector('dialog[open]'))return;
  data=latest;
  if(origin.message){
   const r=await apiFetch('/api/agent/message?'+new URLSearchParams(origin.message),{signal:AbortSignal.timeout(12000)});
   if(!r.ok)throw Error('原通知或图片已变化，请重新打开核对。');const view=await r.json();verifySchoolOriginal(view,{identity:origin.message});origin={material:view};
  }
  const evidence=schoolRecordEvidence(origin);if(!evidence)throw Error('来源或孩子归属已变化，请刷新后核对。');
  const existing=data.records.filter(r=>r.child===evidence.child&&evidence.aliases.includes(r.source)&&(['学习进展','课程进度','成绩'].includes(r.category)||r.related_record_id||r.followup_kind)).sort((a,b)=>a.id-b.id)[0];
  if(existing){openSchoolLearningRecord(existing.id);toast('已有这条来源的学习记录，可以补充观察。');return}
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify([evidence.child_id,evidence.source])));
  if(seq!==stateLoadSequence||!button.isConnected||document.querySelector('dialog[open]'))return;
  $('#add').click();const f=$('#recordForm');if(!$('#recordDialog').open)return;
  schoolRecordContext={...evidence,request_key:'school-'+Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')};
  f.elements.child.value=evidence.child;f.elements.category.innerHTML='<option>学习进展</option><option>课程进度</option><option>成绩</option>';f.elements.category.value='学习进展';f.elements.source.add(new Option(evidence.source,evidence.source,false,true));
  for(const key of ['child','source'])f.elements[key].disabled=true;
  f.elements.title.value=evidence.title;f.elements.note.value=evidence.note;f.elements.day.value='';
  if(evidence.draft){
   f.elements.subject.value=evidence.draft.subject;f.elements.score.value=evidence.draft.score??'';f.elements.total.value=evidence.draft.total??'';
   f.elements.category.value=evidence.draft.score!==null?'成绩':'学习进展';updateRecordCategory();
   pendingIDs=[...evidence.attachments];drawPending();
  }
  $('#recordDialog h2').textContent='留作学习记录';$('#recordDialog .muted').textContent='请核对各方说法；日期不清楚，可填记录日并在正文注明。保存不改变事项状态，图片需添加原件核对。';
  f.elements.day.focus();
 }catch(error){toast(error.message||'暂时无法读取，请重试。')}finally{schoolRecordOpening=false;if(button.isConnected)button.disabled=false}
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-school-record-agent],[data-school-record-task],[data-school-record-exam-task]');if(b)openSchoolRecord({agent:b.dataset.schoolRecordAgent,task:b.dataset.schoolRecordTask||b.dataset.schoolRecordExamTask,exam:Boolean(b.dataset.schoolRecordExamTask)},b)});
function schoolMessageIdentity(ref,childID){
 if(typeof ref!=='string')return null;
 const matches=currentSources().filter(s=>s.child_id===childID&&ref.startsWith('message:'+s.id+':')&&ref.length>('message:'+s.id+':').length);
 if(matches.length!==1)return null;
 return {child_id:childID,source_id:matches[0].id,message_id:ref.slice(('message:'+matches[0].id+':').length)};
}
function schoolOriginalButtons(refs,childID){
 const entries=[...new Set(refs)].filter(ref=>schoolMessageIdentity(ref,childID));
 return entries.length?`<div class="toolbar">${entries.map((ref,i)=>`<button data-school-original-ref="${esc(ref)}" data-school-original-child="${esc(childID)}">${entries.length===1?'原通知与原件':'第 '+(i+1)+' 条原通知与原件'}</button>`).join('')}</div>`:'';
}
// Same link boundary as family_agent._URL (without lookbehind so older engines still parse this file) and the same trailing
// ASCII punctuation trim as the server's _page_link, so a sentence-ending . , ; : ! ? or quote is never sent as part of the
// address while dots and query marks inside it stay untouched. Only complete https addresses that appear in the message can be
// read, and the server checks the address, authorization and message again (QQ window fragments included).
const SCHOOL_URL=/(?:https?:\/\/|www\.)[^\s一-鿿，。；！？、（）【】《》]+|(?:[a-z0-9-]+\.)+[a-z]{2,}\/[^\s一-鿿，。；！？、（）【】《》]*/gi,SCHOOL_URL_TAIL=/[.,;:!?'"]+$/;
function schoolPageLinks(text){
 const source=String(text||''),seen=new Set(),links=[];
 for(const m of source.matchAll(SCHOOL_URL)){
  const raw=m[0],before=source[m.index-1]||'';
  if(!/^(?:https?:\/\/|www\.)/i.test(raw)&&/[a-z0-9.@-]/i.test(before))continue;
  const url=raw.replace(SCHOOL_URL_TAIL,'');
  if(!url||seen.has(url))continue;seen.add(url);links.push({url,https:/^https:\/\/./i.test(url)});
 }
 return links;
}
function schoolPagesHTML(s){
 const m=s.view?.message;if(!m?.text)return '';
 const links=schoolPageLinks(m.text);if(!links.length)return '';
 const pages=Array.isArray(s.view.pages)?s.view.pages:[],p=s.page||{};
 return `<section class="note" data-school-pages><h3>通知里的网址</h3><p class="small">点击读取并保存此页的文字片段（最多6000字），供你对照原通知核对。</p>${links.map(l=>{
  const page=l.https?pages.find(x=>x&&(x.original_url===l.url||x.url===l.url)):null,mine=p.url===l.url,status=mine&&p.notice?`<p role="status" data-school-page-status>${esc(p.notice)}</p>`:'';
  return `<div data-school-page="${esc(l.url)}"><p class="source" style="overflow-wrap:anywhere;word-break:break-all">${esc(l.url)}</p>${status}${page?`<p class="small muted" data-school-page-meta>读取于 ${agentTime(page.fetched_at)} · 仅静态文字${page.text_truncated?'，超过6000字的部分未保存':''}${page.url&&page.url!==page.original_url?' · 实际打开：'+esc(page.url):''}</p><details open><summary>核对网页片段</summary><blockquote class="source" data-school-page-text style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:40vh;overflow:auto">${esc(page.text)}</blockquote></details><p class="small muted">网页文字只供对照原通知核对，不代表学校要求已确认；图片、附件、动态或登录后的内容未读取。</p>`:l.https?`<button data-school-page-read="${esc(l.url)}">${mine&&p.request?'重试读取这个网址':'读取网页片段'}</button>`:'<p class="small muted">未读取，保持原文：只支持完整的 https 地址。</p>'}</div>`}).join('')}</section>`;
}
// One unresolved association keeps its exact message and upload ID until retried.
let schoolOriginal=null;
function schoolOriginalPending(s){return s?.pending||s?.teacher?.pending}
function schoolTeacherHTML(s){
 const t=s.teacher,m=s.view?.message;if(!m?.text?.trim()||m.kind==='qq_window_fragment')return '';
 if(!t)return '<p><button data-school-teacher-open>存为老师要求</button></p>';
 if(t.saved)return `<section class="note" data-school-teacher-saved><p>${esc(t.notice)}</p><button data-school-teacher-profile="${esc(t.saved.teacher_id)}">查看 / 更正老师记录</button></section>`;
 if(!t.profiles)return `<section class="note"><p>${esc(t.notice||'正在读取已保存的老师档案…')}</p>${!s.busy?'<button data-school-teacher-open>重试读取老师</button>':''}</section>`;
 if(!t.profiles.length)return '<section class="note"><p>还没有老师关联到这个孩子和群。</p><button data-school-teacher-profile="new">添加 / 关联老师</button></section>';
 const f=t.fields;
 return `<section class="note"><h3>存为老师要求</h3><p class="small">请确认这段话来自哪位老师、适用于谁；发送者称呼不能代替身份确认。只保存文字，未读附件仍待核对。</p><form data-school-teacher-form><label>老师<select name="teacher_id" required><option value="">请选择已确认的老师</option>${t.profiles.map(x=>`<option value="${esc(x.id)}"${x.id===f.teacher_id?' selected':''}>${esc(x.display_name)} · ${esc(x.subject||'科目待填写')}</option>`).join('')}</select></label><label>适用范围<select name="target" required><option value="">请选择</option><option value="class"${f.target==='class'?' selected':''}>全班</option><option value="household"${f.target==='household'?' selected':''}>本家孩子</option></select></label><label>要求日期 · 请核对<input name="day" type="date" required max="${esc(data.today)}" value="${esc(f.day)}"></label><label>保留的原话<textarea name="quote" rows="5" maxlength="3000" required>${esc(f.quote)}</textarea></label>${m.text.length>3000?'<p class="small">原消息较长，请从上方选取本次要求的原文，最多3000字。</p>':''}<p class="small">可保留原文中的一段；同一消息和老师只归档一次，后续到原记录更正。</p><p role="status">${esc(t.notice||'')}</p><button type="submit"${t.pending?' disabled':''}>确认并保存</button>${t.pending?'<button type="button" data-school-teacher-retry>核对并重试保存</button>':''}</form></section>`;
}
async function openSchoolTeacher(){
 const s=schoolOriginal;if(!s||s.busy||schoolOriginalPending(s))return;
 if(!s.teacher){const m=s.view.message,date=new Date(m.time);s.teacher={fields:{teacher_id:'',target:'',day:m.time&&!isNaN(date)?new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(date):'',quote:m.text.length<=3000?m.text:''},profiles:null}}
 s.busy=true;s.teacher.notice='';paintSchoolOriginal();
 try{const r=await apiFetch('/api/teachers',{signal:AbortSignal.timeout(12000)}),view=await r.json();if(!r.ok||!Array.isArray(view.teachers))throw Error(view.error||'老师档案暂不可读取');s.teacher.profiles=view.teachers.filter(t=>!t.archived&&t.child_ids.includes(s.identity.child_id)&&t.source_ids.includes(s.identity.source_id))}
 catch(e){s.teacher.notice=e.message||'读取失败，请重试。'}finally{s.busy=false;paintSchoolOriginal();$('#schoolOriginalDialog [data-school-teacher-form]')?.scrollIntoView({block:'nearest'})}
}
async function saveSchoolTeacher(){
 const s=schoolOriginal,t=s?.teacher;if(!t?.pending||s.busy)return;s.busy=true;t.notice='正在保存…';paintSchoolOriginal();
 try{
  const body=t.pending,r=await apiFetch('/api/teachers/message',{method:'POST',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-Family-Token':s.token},body:JSON.stringify(body)}),result=await r.json();
  if(!r.ok){if(!(r.status===403&&result.code==='csrf_expired')&&[400,403,404,409,422].includes(r.status))t.pending=null;throw Error(result.error||'暂未保存')}
  const o=result.observation;if(!result.ok||!o?.id||o.teacher_id!==body.teacher_id||o.source_id!==body.source_id||o.message_id!==body.message_id)throw Error('保存回执暂时无法核对');
  t.saved=o;t.pending=null;t.notice=result.already_saved?'这条消息已有记录，保留现有更正与撤回状态。':'已保存到老师档案，可继续核对原通知。';
 }catch(e){t.notice=(e.message||'连接中断')+(t.pending?'；填写已保留，请核对并重试保存。':'；填写已保留。')}
 finally{s.busy=false;paintSchoolOriginal()}
}
function paintSchoolOriginal(){
 const s=schoolOriginal,dialog=$('#schoolOriginalDialog');if(!s||!dialog)return;
 const teacherForm=dialog.querySelector('[data-school-teacher-form]');if(teacherForm&&s.teacher)for(const el of teacherForm.elements)if(el.name)s.teacher.fields[el.name]=el.value;
 const view=s.view,attachments=view?.attachments||[],unavailable=view?.unavailable_attachment_ids||[],linked=new Set(attachments.map(a=>a.id));
 const d=view?.material_draft,schoolMaterial=d?.kind==='school_material',recordDraft=d&&!d.kind,pdf=view?.pdf_material||null;
 // A linked PDF or layout Word original is reported by pdf_material; while it is present the older picture/DOCX draft, its status and its learning-record entry are hidden entirely, even if a stale untyped draft already reads ready.
 const draftHTML=d&&!pdf?d.state==='ready'?`<section class="note" data-school-material-draft><strong>${schoolMaterial?'学校资料 · 待家长核对':'Agent已整理 · 待家长核对'}</strong><p>${esc(d.draft.title)}</p>${recordDraft?`<p>${esc(d.draft.subject)}${d.draft.score!==null?' · '+esc(d.draft.score)+' / '+esc(d.draft.total??'满分待核对'):''}</p>`:''}<p class="source">${esc(d.draft.note)}</p>${d.draft.uncertainties?.length?`<p>待核对：${d.draft.uncertainties.map(esc).join('；')}</p>`:''}${recordDraft?'<button data-school-material-record>核对并填入学习记录</button><p class="small muted">只整理所附图片；保存前请核对原图、孩子归属和实际日期。</p>':'<p class="small muted">仅整理本通知补充的图片原件，未改动任务或学习记录。题目、答案和范文不代表孩子的作答或掌握；请对照原件核对要求。</p>'}</section>`:`<p data-school-material-status>${esc(d.explanation)}${d.state==='error'?'<button data-school-material-retry>重试这份原件</button>':''}</p>`:'';

 const available=(data.uploads||[]).filter(a=>!linked.has(a.id)),owner=data.children.find(c=>c.id===s.identity.child_id);
 const mediaNote=view?.media?.explanation||'';
 dialog.innerHTML=`<h2>${view?.message.kind==='qq_window_fragment'?'QQ群窗口片段':'通知原件'}</h2>${view?.message.kind==='qq_window_fragment'?`<p class="note" data-fragment-note>采集于 ${agentTime(view.message.captured_at)}。仅本次可见内容，不是老师附件原件；发布时间与发言人仍需核对。</p>`:''}<p class="small">${esc(owner?.name||'孩子归属待核对')} · ${esc(view?.source_name||currentSources().find(x=>x.id===s.identity.source_id)?.name||'来源待核对')}</p>${view?`<p class="small muted">${esc(view.message.sender||'发送者未记录')} · ${agentTime(view.message.time)}</p><blockquote class="source" style="overflow-wrap:anywhere">${esc(view.message.text)}</blockquote>${schoolPagesHTML(s)}${schoolTeacherHTML(s)}${mediaNote?`<p class="small muted" data-school-media-note>${esc(mediaNote)}</p>`:''}${schoolPdfHTML(s)}${draftHTML}<div data-school-original-files>${attachments.map(a=>`${uploadHTML(a)}<button data-school-original-detach="${esc(a.id)}">移除关联</button>`).join('')}${unavailable.map(id=>`<p class="error">一份关联原件暂不可读取，请核对文件或重新上传。</p><button data-school-original-detach="${esc(id)}">移除失效关联</button>`).join('')}${!attachments.length&&!unavailable.length&&!mediaNote?'<p>这条通知还没有关联原件，可以在下面补充。</p>':''}</div><p class="small muted">原件用于核对通知，作者、具体要求和完成情况仍需确认。</p><label>拍照或上传原件<input type="file" data-school-original-upload accept="image/*,.pdf,.doc,.docx,.ppt,.pptx,.txt,.mp3,.m4a,.wav,.webm"></label><label>选择已保存的原件<select name="attachment_id"><option value="">请选择</option>${available.map(a=>`<option value="${esc(a.id)}"${s.selected===a.id?' selected':''}>${esc(a.name)}</option>`).join('')}</select></label><button data-school-original-attach>关联所选原件</button>`:''}<p role="status" aria-live="polite" data-school-original-status>${esc(s.error||(s.busy?'正在读取…':''))}</p>${s.pending||!view?'<button data-school-original-retry>重试</button>':''}<div class="toolbar"><button data-school-original-close>关闭</button></div>`;
 for(const control of dialog.querySelectorAll('button,input,select,textarea'))control.disabled=s.busy||!!schoolOriginalPending(s)&&!control.hasAttribute('data-school-original-retry')&&!control.hasAttribute('data-school-teacher-retry')&&!control.hasAttribute('data-school-original-close');
}
// PDF page groups come only from the server view: totals, processed/unread pages and completeness are the backend's; nothing here renders, calls a model or writes.
// The kind is the backend's `original` ('pdf' | 'docx'), never guessed from the file name: a Word original is listed by the page numbers of its converted copy, so the panel says so; a refusal that names no kind stays neutral.
function schoolPdfHTML(s){
 const p=s.view?.pdf_material;if(!p)return '';
 const word=p.original==='docx',kind=word?'Word':'PDF',pages=list=>(Array.isArray(list)?list:[]).map(n=>esc(String(n))).join('、'),notice=`<p role="status" aria-live="polite" data-school-pdf-notice>${esc(s.pdfNotice||'')}</p>`;
 if(p.state==='unavailable')return `<section class="note" data-school-pdf-material data-school-pdf-state="unavailable"><strong>${word?'Word资料':p.original==='pdf'?'PDF资料':'学校资料'} · 本次未整理</strong><p data-school-pdf-status>${esc(p.explanation||'当前原件或授权无法完整核对，可保留原件并手动记录。')}</p><p class="small muted">原件仍保留在下方，可打开核对或手动记录；未改动任务或学习记录。</p>${notice}<div class="tasktools"><button data-school-pdf-refresh>刷新读取最新</button></div></section>`;
 const done=Array.isArray(p.processed_pages)?p.processed_pages:[],left=Array.isArray(p.pending_pages)?p.pending_pages:[],batches=Array.isArray(p.batches)?p.batches:[],total=Number.isInteger(p.page_count)?p.page_count:null;
 const progress=total===null?`总页数尚未核对；已整理 ${done.length} 页，其余页数未知。`:p.complete===true?`全部 ${total} 页已整理，待家长核对。`:`已整理 ${done.length} / ${total} 页${left.length?`；未读页：${pages(left)}（共 ${left.length} 页）`:'；剩余页尚未确认完整。'}`;
 return `<section class="note" data-school-pdf-material data-school-pdf-state="${esc(String(p.state||''))}" data-school-pdf-original="${word?'docx':'pdf'}"><strong>学校资料 · ${kind}逐页整理 · 待家长核对</strong><p>${esc(p.name||kind+'原件')}</p>${word?'<p class="small muted" data-school-pdf-conversion>Word原件按转换后的页码逐页整理，页码可能与Word里显示的分页不同；下方仍是原Word文件，可打开核对。</p>':''}<p data-school-pdf-progress>${progress}</p>${p.explanation?`<p data-school-pdf-status>${esc(p.explanation)}</p>`:''}${batches.map(b=>{const dr=b?.draft||{};return `<div class="task-goal" data-school-pdf-batch="${esc((Array.isArray(b?.pages)?b.pages:[]).join(','))}"><span class="small muted">第 ${pages(b?.pages)} 页</span><p>${esc(dr.title||'标题待核对')}</p><p class="source">${esc(dr.note||'')}</p>${Array.isArray(dr.uncertainties)&&dr.uncertainties.length?`<p>待核对：${dr.uncertainties.map(u=>esc(String(u))).join('；')}</p>`:''}</div>`}).join('')}${!batches.length?'<p class="small muted">还没有整理完成的页组。</p>':''}${notice}<div class="tasktools"><button data-school-pdf-refresh>刷新读取最新</button>${p.state==='error'?'<button data-school-pdf-retry>重试整理</button>':''}</div><p class="small muted">仅按页组整理本通知关联的${kind}原件，未改动任务或学习记录；题目、答案和范文不代表孩子的作答或掌握，请对照原件核对要求。</p></section>`;
}
// Refresh re-reads the same message view (GET only). A failed read keeps the progress already shown; a reply for a closed or replaced dialog is dropped.
async function refreshSchoolPdf(){
 const s=schoolOriginal;if(!s||s.busy||schoolOriginalPending(s)||!s.view)return;
 s.busy=true;s.error='';s.pdfNotice='正在读取最新进度…';paintSchoolOriginal();
 try{
  const r=await apiFetch('/api/agent/message?'+new URLSearchParams(s.identity),{signal:AbortSignal.timeout(12000)}),view=await r.json().catch(()=>null);
  if(schoolOriginal!==s)return;
  if(!r.ok)throw Error(r.status===401?'请先重新登录，再刷新读取':view?.error||'这条通知暂时无法读取');
  const wasWord=s.view?.pdf_material?.original==='docx';s.view=verifySchoolOriginal(view,s);
  if(s.view.pdf_material)s.pdfNotice='已读取最新进度。';else{s.pdfNotice='';s.error=wasWord?'这条通知当前没有可整理的Word原件，之前显示的Word页组草稿已收起。':'这条通知当前没有可整理的PDF原件，之前显示的PDF草稿已收起。'}
 }catch(error){if(schoolOriginal!==s)return;s.pdfNotice=(error.name==='TimeoutError'?'读取超时':error.message||'连接暂时中断')+'；已显示的进度和填写内容保留，可再次刷新。'}
 finally{if(schoolOriginal===s){s.busy=false;paintSchoolOriginal()}}
}
// Retry only queues the existing background job; progress is read back with refresh, never rendered or modelled here.
async function retrySchoolPdf(){
 const s=schoolOriginal,p=s?.view?.pdf_material;if(!s||s.busy||schoolOriginalPending(s)||s.pdfRetry||typeof p?.job_id!=='string')return;
 s.busy=true;s.pdfRetry=true;s.error='';s.pdfNotice='正在安排重试…';paintSchoolOriginal();
 try{
  const r=await apiFetch('/api/agent/action',{method:'POST',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-Family-Token':s.token},body:JSON.stringify({action:'retry',id:p.job_id})}),result=await r.json().catch(()=>null);
  if(schoolOriginal!==s)return;
  if(!r.ok||!result?.ok)throw Error(r.status===401?'请先重新登录，再安排重试':result?.error||'重试未能安排，请稍后再试');
  s.pdfNotice='已安排后台重试；独立Agent稍后继续整理未读页，可点“刷新读取最新”查看。已整理页组保留。';
 }catch(error){if(schoolOriginal!==s)return;s.pdfNotice=(error.name==='TimeoutError'?'等待回执超时':error.message||'连接暂时中断')+'；已整理页组保留，可再次重试。'}
 finally{if(schoolOriginal===s){s.busy=false;s.pdfRetry=false;paintSchoolOriginal()}}
}
function verifySchoolOriginal(view,s){
 if(!view||Object.entries(s.identity).some(([k,v])=>view[k]!==v)||!view.message||!Array.isArray(view.attachments))throw Error('原件归属暂时无法核对，请重试。');
 return view;
}
async function readSchoolOriginal(){
 const s=schoolOriginal;if(!s||s.busy||schoolOriginalPending(s))return;s.busy=true;s.error='';paintSchoolOriginal();
 try{const r=await apiFetch('/api/agent/message?'+new URLSearchParams(s.identity),{signal:AbortSignal.timeout(12000)}),view=await r.json();if(!r.ok)throw Error(view.error||'这条通知暂时无法读取');s.view=verifySchoolOriginal(view,s)}
 catch(error){s.error=error.name==='TimeoutError'?'读取超时，请重试。':error.message||'暂时无法读取，请重试。'}
 finally{s.busy=false;paintSchoolOriginal()}
}
// One click reads one address from the message itself; a lost reply is retried with the same request and served from the server cache.
async function readSchoolPage(url){
 const s=schoolOriginal;if(!s||s.busy||schoolOriginalPending(s)||!s.view)return;
 if(!schoolPageLinks(s.view.message.text).some(l=>l.https&&l.url===url)){s.error='只读取原通知里完整的 https 地址。';paintSchoolOriginal();return}
 const request={...s.identity,url};s.page={request,url,notice:''};s.busy=true;s.error='';paintSchoolOriginal();
 let keep=true;
 try{
  const r=await apiFetch('/api/agent/message/page',{method:'POST',signal:AbortSignal.timeout(20000),headers:{'Content-Type':'application/json','X-Family-Token':s.token},body:JSON.stringify(request)}),view=await r.json();
  if(schoolOriginal!==s)return;
  if(!r.ok){keep=!([400,404,422].includes(r.status)||r.status===403&&view.code!=='csrf_expired');throw Error(view.error||(r.status===401?'请先登录家长账号':'网页片段暂未读取'))}
  verifySchoolOriginal(view,s);const p=view.page;
  if(!p||typeof p.text!=='string'||p.original_url!==url&&p.url!==url||!Array.isArray(view.pages)||!view.pages.some(x=>x&&x.original_url===p.original_url))throw Error('读取回执暂时无法核对，请重试同一网址。');
  s.view=view;s.page={request:null,url,notice:view.cached?'已使用之前保存的网页片段，没有再次访问网页。':'已读取网页片段，请对照原通知核对。'};
 }catch(error){
  if(schoolOriginal!==s)return;
  s.page={request:keep?request:null,url,notice:(error.name==='TimeoutError'?'读取网页超时':error.message||'连接暂时中断')+(keep?'；原通知、原件和已填写内容都保留，可重试读取同一网址。':'。')};
 }finally{if(schoolOriginal===s){s.busy=false;paintSchoolOriginal()}}
}
async function saveSchoolOriginal(){
 const s=schoolOriginal;if(!s||s.busy||!s.pending)return;s.busy=true;s.error='正在保存关联…';paintSchoolOriginal();
 try{
  const request=s.pending,r=await apiFetch('/api/agent/message/attachment',{method:'POST',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-Family-Token':s.token},body:JSON.stringify(request)}),view=await r.json();
  if(!r.ok){if(!(r.status===403&&view.code==='csrf_expired')&&[400,403,404,409,413,415,422].includes(r.status))s.pending=null;throw Error(view.error||'关联暂未保存')}
  verifySchoolOriginal(view,s);
  if(view.attachments.some(a=>a.id===request.attachment_id)!==(request.action==='attach'))throw Error('保存回执暂时无法核对');
  s.view=view;s.pending=null;s.selected='';s.error=request.action==='attach'?'原件已关联到这条通知。':'已移除关联，原文件仍保留。';
  try{await load()}catch{s.error+='页面其他资料暂未刷新。'}
 }catch(error){s.error=(error.name==='TimeoutError'?'等待保存超时':error.message||'连接暂时中断')+(s.pending?'。请重试这笔关联，已上传的文件无需重传。':'')}
 finally{s.busy=false;paintSchoolOriginal()}
}
async function uploadSchoolOriginal(file){
 const s=schoolOriginal;if(!s||s.busy||schoolOriginalPending(s)||!file)return;
 if(!file.size||file.size>20*1024*1024){s.error='文件为空或超过20MB';paintSchoolOriginal();return}
 s.busy=true;s.error='正在保存原件…';paintSchoolOriginal();
 try{
  const r=await apiFetch('/api/upload',{method:'POST',signal:AbortSignal.timeout(120000),headers:{'X-Family-Token':s.token,'X-File-Name':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'},body:file}),result=await r.json();
  if(!r.ok)throw Error(result.error||'上传失败');const a=result.attachment;
  if(!a||typeof a.id!=='string')throw Error('上传回执无法核对，可刷新后从已保存原件中查找');
  data.uploads=data.uploads||[];if(!data.uploads.some(x=>x.id===a.id))data.uploads.unshift(a);
  s.selected=a.id;s.pending={...s.identity,attachment_id:a.id,action:'attach'};
 }catch(error){
  s.error=(error.name==='TimeoutError'?'上传等待超时':error.message||'上传连接中断')+'。尚未关联。';
  try{await load();s.error+='已刷新文件列表；请先从已保存原件中查找，避免重复上传。'}
  catch{s.error+='文件列表暂未刷新；恢复连接后请刷新页面，再从已保存原件中查找。'}
 }
 finally{s.busy=false;paintSchoolOriginal()}
 if(s.pending)await saveSchoolOriginal();
}
function openSchoolOriginal(ref,childID){
 if(document.querySelector('dialog[open]'))return;
 const identity=schoolMessageIdentity(ref,childID);if(!identity){toast('消息或孩子归属暂时无法核对，请刷新。');return}
 let dialog=$('#schoolOriginalDialog');
 if(!dialog){
  dialog=document.createElement('dialog');dialog.id='schoolOriginalDialog';document.body.append(dialog);
  dialog.addEventListener('cancel',e=>{if(schoolOriginal?.busy)e.preventDefault()});
  dialog.addEventListener('close',()=>{if(!schoolOriginalPending(schoolOriginal))schoolOriginal=null});
  dialog.addEventListener('submit',e=>{const f=e.target.closest('[data-school-teacher-form]'),s=schoolOriginal;if(!f||!s)return;e.preventDefault();if(s.busy||schoolOriginalPending(s)||!f.reportValidity())return;s.teacher.pending={...s.identity,...Object.fromEntries(new FormData(f))};saveSchoolTeacher()});
  dialog.addEventListener('change',e=>{if(e.target.matches('[data-school-original-upload]'))uploadSchoolOriginal(e.target.files[0]);if(e.target.name==='attachment_id'&&schoolOriginal)schoolOriginal.selected=e.target.value});
  dialog.addEventListener('click',e=>{
   const b=e.target.closest('button'),s=schoolOriginal;if(!b||!s||s.busy)return;
   if(b.hasAttribute('data-school-original-close')){dialog.close();return}
   if(b.hasAttribute('data-school-original-retry')){s.pending?saveSchoolOriginal():readSchoolOriginal();return}
   if(b.hasAttribute('data-school-teacher-retry')){saveSchoolTeacher();return}
   if(schoolOriginalPending(s))return;
   if(b.hasAttribute('data-school-pdf-refresh')){refreshSchoolPdf();return}
   if(b.hasAttribute('data-school-pdf-retry')){retrySchoolPdf();return}
   if(b.hasAttribute('data-school-page-read')){readSchoolPage(b.dataset.schoolPageRead);return}
   if(b.hasAttribute('data-school-teacher-open')){openSchoolTeacher();return}
   if(b.hasAttribute('data-school-teacher-profile')){const id=b.dataset.schoolTeacherProfile;dialog.close();teacherSelectedID=id;page='teachers';render();window.scrollTo(0,0);return}
   if(b.hasAttribute('data-school-material-record')){const identity={...s.identity};dialog.close();openSchoolRecord({message:identity},b);return}
   if(b.hasAttribute('data-school-material-retry')){
    s.busy=true;s.error='';paintSchoolOriginal();
    apiFetch('/api/agent/action',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':s.token},body:JSON.stringify({action:'retry',id:s.view.material_draft.job_id})})
     .then(r=>{if(!r.ok)throw Error('重试未能安排，请稍后再试。');s.error='已安排后台重试，可稍后重开核对。'})
     .catch(e=>{s.error=e.message}).finally(()=>{s.busy=false;paintSchoolOriginal()});return;
   }
   const detach=b.dataset.schoolOriginalDetach,attach=b.hasAttribute('data-school-original-attach');
   if(detach||attach){const id=detach||s.selected;if(!id){s.error='请先选择一份已保存的原件。';paintSchoolOriginal();return}s.pending={...s.identity,attachment_id:id,action:detach?'detach':'attach'};saveSchoolOriginal()}
  });
 }
 if(!schoolOriginalPending(schoolOriginal))schoolOriginal={identity,token:data.token,view:null,busy:false,pending:null,selected:'',error:'',page:null,pdfNotice:''};
 else schoolOriginal.error='请先核对上次未确认的保存；这里仍是上次选择的孩子和通知。';
 paintSchoolOriginal();dialog.showModal();if(!schoolOriginalPending(schoolOriginal))readSchoolOriginal();
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-school-original-ref]');if(b)openSchoolOriginal(b.dataset.schoolOriginalRef,b.dataset.schoolOriginalChild)});
window.addEventListener('beforeunload',e=>{if(schoolOriginalPending(schoolOriginal)||schoolOriginal?.busy){e.preventDefault();e.returnValue=''}});
function agentItemHTML(item,options={}){
 const c=data.children.find(c=>c.id===item.child_id),care=item.care_id&&(data.care?.items||[]).some(c=>c.id===item.care_id),record=item.record_id&&data.records.some(r=>r.id===item.record_id),plan=item.plan&&typeof item.plan==='object'&&Object.keys(item.plan).length;
 const isPlannedCare=item.kind==='care'&&plan, reviewPlan=item.kind==='review'&&plan,needsDetails=item.kind==='school'&&item.needs_task_details&&item.state==='pending';
 const schoolReason=item.kind==='school'&&item.plan?.school_task?.reason?`<p class="small muted">${item.plan.school_task.state==='reference'?'参考说明 · ':''}${esc(item.plan.school_task.reason)}</p>`:'';
 const acceptedSchool=item.kind==='school'&&item.state==='accepted'?data.tasks.find(t=>t.id===item.task_id):null;
 const parentItem=reviewPlan&&item.plan.parent_item_id?(data.agent?.items||[]).find(x=>x.id===item.plan.parent_item_id):null;
 const displayTitle=needsDetails?'原件内容待核对':acceptedSchool?.title||isPlannedCare&&item.state==='accepted'&&item.plan.approved?.title||item.title,displayBody=needsDetails?'请先核对原件，再填写具体要做的事。':acceptedSchool?.action||isPlannedCare&&item.state==='accepted'&&item.plan.approved?.action||item.body,displayReview=isPlannedCare&&item.state==='accepted'&&item.plan.approved?.review_on||item.plan?.review_on;
 if(options.compact&&item.kind==='school'){
  const lines=displayTitle.replace(/^待核对[：:]\s*/,'').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  const excerpt=lines.find(s=>!['','通知','重要通知','温馨提醒','提醒','所有人'].includes(s.replace(/[^\p{L}\p{N}]/gu,'')))||lines[0]||'学校通知',short=excerpt.length>64?excerpt.slice(0,64)+'…':excerpt,goal=displayBody.startsWith('请核对这条通知是否适用')?'':displayBody;
  return `<article class="agent-item school-review" data-agent-item="${esc(item.id)}"><div class="task-meta"><span>${esc(c?.name||'归属待核对')}</span><span class="review-badge">待核对通知</span></div><h3>${esc(short)}</h3>${agendaDateHTML(options.agenda||{})}${goal?`<div class="task-goal"><p>${esc(goal)}</p></div>`:''}${schoolReason}<div class="tasktools"><button class="primary" data-agent-accept="${esc(item.id)}">核对要求</button><button data-agent-dismiss="${esc(item.id)}">忽略这条</button></div><details class="task-reference task-more"><summary>原通知与其他操作</summary>${schoolOriginalButtons((item.evidence||[]).map(e=>e.ref),item.child_id)}<p>${esc(displayTitle)}</p>${(item.evidence||[]).map(e=>`<blockquote>${esc(e.text||e.quote)}</blockquote><p class="small muted">${esc(e.ref)}</p>`).join('')}${item.plan?.school_task?.advice?`<p>操作建议：${esc(item.plan.school_task.advice)}</p>`:''}<div class="tasktools"><button data-school-record-agent="${esc(item.id)}">留作学习记录</button>${item.goal_id?`<button data-goal-id="${esc(item.goal_id)}" data-goal-child="${esc(item.child_id)}">查看学习目标</button>`:''}</div></details></article>`;
 }
 const details=isPlannedCare?`<div class="agent-plan"><p><strong>目标：</strong>${esc(item.plan.goal||'待家长补充')}</p><p><strong>为什么现在：</strong>${esc(item.plan.why_now||'根据最新记录回看')}</p><p><strong>预计投入：</strong>${(item.state==='accepted'?item.plan.approved?.estimated_minutes:item.plan.estimated_minutes)==null?'未设定':esc(item.state==='accepted'?item.plan.approved.estimated_minutes:item.plan.estimated_minutes)+' 分钟'} · <strong>建议回看：</strong>${esc(displayReview||item.due||'待约定')}</p></div>`:'';
 let actions='';if(item.state==='accepted'){actions+=`<button data-task="${esc(item.task_id)}">跟进待办</button>`;if(record)actions+=`<button data-followup="${esc(item.record_id)}">补充实际进展</button>`;if(isPlannedCare)actions+=`<button data-agent-defer="${esc(item.id)}">改天回看</button>`}else if(item.kind==='school')actions+=`<button data-agent-accept="${esc(item.id)}">${item.plan?.school_task?.change&&item.plan.school_task.change!=='new'?'核对学校变更':needsDetails?'补充具体要求':'核对并加入待办'}</button><button data-school-record-agent="${esc(item.id)}">留作学习记录</button>`;else if(isPlannedCare)actions+=`<button data-agent-accept="${esc(item.id)}">核对并安排</button>${record?`<button data-followup="${esc(item.record_id)}">补充实际进展</button>`:''}`;else if(reviewPlan&&item.plan.diagnosis_review_pending)actions+=`${record&&data.records.some(r=>r.id===item.record_id&&r.child===c?.name)?`<button data-followup="${esc(item.record_id)}" data-followup-kind="复测">记录复测结果</button>`:''}<button data-diagnosis-child="${esc(item.child_id)}">查看错题诊断</button>`;else if(reviewPlan)actions+=`${item.plan.exam_result_pending&&item.task_id?`<button data-school-record-exam-task="${esc(item.task_id)}">记录考试结果</button>`:''}${item.task_id?`<button data-task="${esc(item.task_id)}">跟进待办</button>`:''}${record?`<button data-followup="${esc(item.record_id)}">补充实际进展</button>`:''}${parentItem?`<button data-agent-defer="${esc(parentItem.id)}">改天回看</button>`:''}`;else if(care)actions+=`<button data-care="${esc(item.care_id)}">记录选择或反馈</button>`;else if(record)actions+=`<button data-followup="${esc(item.record_id)}">补充实际进展</button>`;else actions+=`<button data-today-capture="${esc(item.child_id)}">记一次尝试</button>`;
 if(item.goal_id)actions=(item.kind==='school'?actions:'')+`<button data-goal-id="${esc(item.goal_id)}" data-goal-child="${esc(item.child_id)}">查看目标 / 反馈 / 审核</button>`;
 if(item.state==='pending'&&(!item.goal_id||item.kind==='school'))actions+=`<button data-agent-dismiss="${esc(item.id)}">${item.kind==='school'?'忽略这条':isPlannedCare?'暂不考虑':'已看过'}</button>`;
 return `<article class="agent-item" data-agent-item="${esc(item.id)}"><span class="small muted">${esc(c?.name||'归属待核对')} · ${item.kind==='school'?'学校信息':item.kind==='review'?'到期回看':'学习跟进'}</span><h3>${esc(displayTitle)}</h3>${item.kind==='school'?`<div class="task-goal"><span class="small muted">${item.plan?.school_task?.state==='reference'?'资料要点':'完成目标'}</span><p>${esc(displayBody.startsWith('请核对这条通知是否适用')?'尚待核对具体成果与要求':displayBody)}</p></div>${item.plan?.school_task?.advice?`<div class="task-next"><span>操作建议</span><p>${esc(item.plan.school_task.advice)}</p></div>`:''}`:`<p>${esc(displayBody)}</p>`}${schoolReason}${details}${item.kind==='school'?schoolOriginalButtons((item.evidence||[]).map(e=>e.ref),item.child_id):''}${item.due&&!isPlannedCare?`<p class="small">日期：${esc(item.due)}</p>`:''}<details><summary>查看依据</summary>${(item.evidence||[]).map(e=>`<blockquote>${esc(e.text||e.quote)}</blockquote><p class="small muted">${esc(e.ref)}</p>`).join('')}</details><div class="toolbar">${actions}</div></article>`;
}
function agentChildHTML(c){const items=agentPending(c.id).filter(item=>['school','care','review'].includes(item.kind));return items.length?`<div class="agent-child"><h3 class="today-section-label">需要核对与跟进 · ${items.length}</h3>${items.slice(0,2).map(agentItemHTML).join('')}${items.length>2?'<button data-page="agent">查看其余提醒 →</button>':''}</div>`:''}
function agentStatusHTML(full){
 const a=data.agent,coverage=sourceCoverageHTML();if(!a||(!a.enabled&&!a.last_error&&!coverage))return '';
 const stale=a.enabled&&a.last_run&&Date.now()-Date.parse(a.last_run)>10*60*1000;
 const state={waiting:'等待首次整理',running:'正在整理',ready:'已完成本轮整理',idle:'已完成本轮整理',error:'整理遇到问题',partial:'部分资料待重试',needs_attention:'部分资料待重试',interrupted:'整理中断，等待恢复',disabled:'尚未启用'}[a.state]||'已保存运行状态';
 return `<section class="agent-status" aria-label="成长助手运行状态"><div><strong>成长助手</strong><span class="small">后台整理：${a.last_error||stale?'有资料待核对':state} · ${a.pending_count||0} 条待看</span></div>${coverage}${full?'':'<button data-page="agent">查看提醒与状态 →</button>'}${full?`<p class="small">上次整理：${agentTime(a.last_run)}${stale?' · 已超过10分钟，请检查后台服务':''}</p>${a.last_error?`<p role="status" class="error">${esc(a.last_error)}</p>`:''}${a.failed_jobs?`<p class="error">${a.failed_jobs} 批资料仍未整理成功 <button data-agent-retry>重新尝试</button></p>`:''}<details><summary>消息来源与读取情况</summary>${currentSourceCardsHTML()||empty('尚未配置消息来源')}</details><p class="small muted">后台整理只处理已保存资料，不代表所有群的新消息已同步。此处提醒不代表已向微信或手机发送通知。</p>`:''}</section>`;
}
function agentPageHTML(){return `<h1>成长助手</h1><div class="toolbar"><button data-page="home">返回今天</button><button data-agent-refresh>更新显示</button></div>${agentStatusHTML(true)}<section class="card">${agentPending().map(agentItemHTML).join('')||empty('目前没有待看的提醒；读取情况见上方。')}</section>${(data.agent?.items||[]).some(x=>x.state==='accepted')?`<details class="card"><summary>最近加入的待办与依据</summary>${data.agent.items.filter(x=>x.state==='accepted').map(agentItemHTML).join('')}</details>`:''}`}
async function agentAction(obj){const r=await apiFetch('/api/agent/action',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(obj)});const result=await r.json();if(!r.ok){const error=Error(result.error||'处理失败，请重试');error.status=r.status;throw error}return result}
function schoolChangeForm(f,item){
 const brief=item.plan?.school_task||{},panel=document.createElement('div');let expected=item.updated,targetVersion=0,targetUpdated='',dateEdited=false;
 panel.innerHTML=`<button type="button" data-school-change-open>这条通知更正或取消了已有事项</button><div data-school-change-panel class="hide"><label>处理方式<select name="school_mode"><option value="new">另建事项</option><option value="update">更正原事项</option><option value="cancel">学校取消原事项</option></select></label><label data-school-target-label>原事项<select name="target_id"><option value="">请选择需要变更的原事项</option></select></label><div data-school-current></div><button type="button" data-school-change-refresh class="hide">读取最新记录</button><p class="small muted">保留原状态和反馈；确认取消会暂停计时。</p></div>`;
 f.querySelector('label').before(panel);
 const bodyLabel=f.elements.body.closest('label'),dateLabel=f.elements.due.closest('label'),titleLabel=f.elements.title.closest('label'),adviceLabel=f.elements.advice.closest('label');dateLabel.before(bodyLabel);
 f.elements.due.addEventListener('input',()=>dateEdited=true);
 const newSource=document.createElement('div');newSource.innerHTML=schoolOriginalButtons((item.evidence||[]).map(e=>e.ref),item.child_id).replaceAll('原通知与原件','本次通知原文');bodyLabel.after(newSource);newSource.classList.add('hide');
 const mode=panel.querySelector('[name="school_mode"]'),select=panel.querySelector('[name="target_id"]'),current=panel.querySelector('[data-school-current]'),open=panel.querySelector('[data-school-change-open]'),box=panel.querySelector('[data-school-change-panel]'),submit=f.querySelector('[type="submit"]');
 const tasks=()=>data.tasks.filter(t=>t.child===data.children.find(c=>c.id===item.child_id)?.name&&t.school_origin);
 const fill=()=>{const keep=select.value;select.innerHTML='<option value="">请选择需要变更的原事项</option>'+tasks().map(t=>`<option value="${esc(t.id)}">${esc(t.title)}</option>`).join('');select.value=keep};
 const show=()=>{const t=tasks().find(t=>t.id===select.value),changing=mode.value!=='new';panel.querySelector('[data-school-target-label]').classList.toggle('hide',!changing);current.innerHTML=t&&changing?`<p>原要求：${esc(t.action)}</p><p class="small">${esc(taskStatusLabel(status(t)))} · 原截止：${esc(t.agenda?.due_on||'未定')}</p>${schoolOriginalButtons(String(t.source).split('\n').filter(r=>r.startsWith('message:')),item.child_id)}`:'';targetVersion=t?.focus?.version||0;targetUpdated=t?.update?.updated||'';if(changing&&mode.value==='update'&&!item.due&&!dateEdited)f.elements.due.value=t?.agenda?.due_on||'';dateLabel.firstChild.textContent=changing?'截止日期 · 可修改或清空':'哪一天';newSource.classList.toggle('hide',!changing);for(const label of [dateLabel,titleLabel,adviceLabel])label.classList.toggle('hide',mode.value==='cancel');bodyLabel.firstChild.textContent=mode.value==='cancel'?'取消依据':changing?'更正后的完成要求':'完成目标';submit.textContent=changing?(mode.value==='cancel'?'确认学校取消':'确认更正原事项'):'加入待办'};
 fill();mode.value=['update','cancel'].includes(brief.change)?brief.change:'new';select.value=brief.target_id||'';mode.onchange=show;select.onchange=show;
 open.onclick=()=>{box.classList.remove('hide');open.classList.add('hide');mode.value='update';show()};
 if(mode.value!=='new'){box.classList.remove('hide');open.classList.add('hide');f.querySelector('h2').textContent='核对学校变更'}show();
 panel.querySelector('[data-school-change-refresh]').onclick=async()=>{try{await load();const latest=data.agent?.items.find(x=>x.id===item.id);if(latest)expected=latest.updated;fill();show();$('#agentError').textContent='已读取最新记录，请核对原事项和本次填写后再确认。'}catch(e){$('#agentError').textContent=e.message}};
 return values=>mode.value==='new'?{action:'accept',id:values.id,title:values.title,body:values.body,due:values.due,advice:values.advice,school_new:true}:{action:'school_change',id:item.id,target_id:select.value,change:mode.value,title:values.title,body:values.body,due:values.due,expected_updated:expected,target_version:targetVersion,target_updated:targetUpdated};
}
function openAgentTask(id){
 const item=(data.agent?.items||[]).find(x=>x.id===id);if(!item)return;
 let dialog=$('#agentDialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='agentDialog';document.body.append(dialog)}
 const care=item.kind==='care'&&item.plan&&Object.keys(item.plan).length,needsDetails=item.kind==='school'&&item.needs_task_details&&item.state==='pending';
 dialog.innerHTML=`<form id="agentForm"><h2>${care?'核对并安排学习小动作':'核对学校待办'}</h2>${needsDetails?`<p class="note">原件内容尚未读取，请先核对并填写具体事项。也可以明确安排先核对原件。</p><details><summary>原通知出处</summary>${(item.evidence||[]).map(e=>`<blockquote>${esc(e.text||e.quote)}</blockquote>`).join('')}</details>`:''}<input type="hidden" name="id"><label>要做什么<input name="title" required maxlength="200"></label><label>${care?'家长约定回看日':'哪一天'}<input name="${care?'review_on':'due'}" type="date" ${care?'required':''}></label>${care?'<label>预计投入分钟数（可留空）<input name="estimated_minutes" type="number" min="1" max="60" step="1"></label>':''}<label>${care?'具体动作':'完成目标'}<textarea name="body" rows="4" maxlength="4000" required></textarea></label>${care?'':'<label>操作建议 · 可选<textarea name="advice" maxlength="2000" rows="2"></textarea></label>'}<p class="small muted">${care?'回看日是家庭约定，不是学校截止；默认建议可修改。':'日期不明确可以留空，加入后仍是待跟进。'}</p><p id="agentError" class="error" role="alert"></p><div class="toolbar"><button type="button" data-close="agentDialog">取消</button><button type="submit" class="primary">${care?'确认安排':'加入待办'}</button></div></form>`;
 const f=$('#agentForm');f.elements.id.value=id;f.elements.title.value=needsDetails?'':item.plan?.approved?.title||item.title;f.elements[care?'review_on':'due'].value=exactTaskDay(care?(item.plan.approved?.review_on||item.plan.review_on):item.due);if(care){f.elements.review_on.min=data.today;f.elements.review_on.max=new Date(Date.parse(data.today+'T12:00:00Z')+30*86400000).toISOString().slice(0,10)}f.elements.body.value=needsDetails?'':item.plan?.approved?.action||item.body;if(!care)f.elements.advice.value=item.plan?.school_task?.advice||'';if(care&&item.plan.estimated_minutes!=null)f.elements.estimated_minutes.value=item.plan.estimated_minutes;$('#agentError').textContent='';const schoolPayload=care?null:schoolChangeForm(f,item);f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type="submit"]');if(b.disabled)return;b.disabled=true;$('#agentError').textContent='';try{const values=Object.fromEntries(new FormData(f));const payload=care?{id:values.id,action:'accept',title:values.title,body:values.body,review_on:values.review_on,estimated_minutes:values.estimated_minutes?Number(values.estimated_minutes):null}:schoolPayload(values);const result=await agentAction(payload);dialog.close();await load();toast(result.completion_needs_review?'已更正要求；原完成记录保留，新要求是否需补做请核对。':result.school_changed?'已更新原事项，状态和反馈已保留':result.deduplicated?(result.state==='dismissed'?'相同通知已忽略，保留原决定':'相同通知已收集，保留原事项及处理状态'):care?'已安排，可在待办中跟进':'已加入待办，可在清单里跟进')}catch(err){$('#agentError').textContent=err.message;if(err.status===409)f.querySelector('[data-school-change-refresh]')?.classList.remove('hide')}finally{b.disabled=false}};dialog.showModal();
}
function openAgentDefer(id){const item=(data.agent?.items||[]).find(x=>x.id===id);if(!item)return;let dialog=$('#agentDeferDialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='agentDeferDialog';dialog.innerHTML='<form id="agentDeferForm"><h2>改天回看</h2><input type="hidden" name="id"><label>回看日期<input name="review_on" type="date" required></label><p class="small muted">请约定未来30天内的日期。</p><p id="agentDeferCurrent" class="small muted"></p><p id="agentDeferError" class="error" role="alert"></p><div class="toolbar"><button type="button" data-agent-refresh-defer class="hide">读取最新安排</button><button type="button" data-close="agentDeferDialog">取消</button><button type="submit" class="primary">保存回看</button></div></form>';document.body.append(dialog)}const f=$('#agentDeferForm'),refresh=f.querySelector('[data-agent-refresh-defer]');let expected=item.updated;$('#agentDeferCurrent').textContent='';f.elements.id.value=id;f.elements.review_on.value='';f.elements.review_on.min=new Date(Date.parse(data.today+'T12:00:00Z')+86400000).toISOString().slice(0,10);f.elements.review_on.max=new Date(Date.parse(data.today+'T12:00:00Z')+30*86400000).toISOString().slice(0,10);$('#agentDeferError').textContent='';refresh.classList.add('hide');f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type="submit"]');b.disabled=true;$('#agentDeferError').textContent='';try{await agentAction({id,action:'defer',review_on:f.elements.review_on.value,expected_updated:expected});dialog.close();await load();toast('已保存回看日期')}catch(err){$('#agentDeferError').textContent=err.message;if(err.status===409){refresh.classList.remove('hide');$('#agentDeferCurrent').textContent='服务端当前安排已变化，请读取后核对；你填写的日期已保留。'}}finally{b.disabled=false}};refresh.onclick=async()=>{const keep=f.elements.review_on.value;try{await load();f.elements.review_on.value=keep;const latest=(data.agent?.items||[]).find(x=>x.id===id);if(latest)expected=latest.updated;$('#agentDeferCurrent').textContent=latest?.plan?.approved?.review_on?'服务端当前安排：'+latest.plan.approved.review_on:'已读取最新安排，请核对后保存';refresh.classList.add('hide')}catch(err){$('#agentDeferError').textContent=err.message}};dialog.showModal()}
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b||!data)return;if(b.dataset.agentAccept){openAgentTask(b.dataset.agentAccept);return}if(b.dataset.agentDefer){openAgentDefer(b.dataset.agentDefer);return}if(!b.hasAttribute('data-agent-dismiss')&&!b.hasAttribute('data-agent-retry')&&!b.hasAttribute('data-agent-refresh'))return;if(b.disabled)return;b.disabled=true;try{if(b.hasAttribute('data-agent-dismiss'))await agentAction({id:b.dataset.agentDismiss,action:'dismiss'});if(b.hasAttribute('data-agent-retry'))await agentAction({action:'retry'});await load();if(b.hasAttribute('data-agent-retry'))toast('已安排重试，后台下一轮会处理')}catch(err){toast(err.message)}finally{b.disabled=false}});
// One lightweight saved-state read per minute; never collect or call a model on page visits.
setInterval(async()=>{if(!data?.agent?.enabled||document.hidden||document.querySelector('dialog[open]')||!['home','calendar','tasks','agent'].includes(page)||document.activeElement?.matches('input,textarea,select'))return;try{const r=await apiFetch('/api/agent',{signal:AbortSignal.timeout(8000)});if(!r.ok)return;const next=await r.json();if(document.querySelector('dialog[open]'))return;if(JSON.stringify(next)!==JSON.stringify(data.agent)){data.agent=next;await load();window.FamilyCalendar?.invalidate(page==='calendar');render()}}catch{}},60000);

function mountStudy(){
 const root=$('#studyRoot');if(!window.FamilyStudy){root.innerHTML=empty('放学后安排暂未加载，请刷新后重试。');return}
 window.FamilyStudy.mount({root,child_id:studyChildID||data.children[0]?.id,onChildChanged:id=>studyChildID=id,onDayChanged:day=>studyDay=day,task_id:studyTaskID,onTaskSelected:()=>studyTaskID='',day:studyDay||data.today,children:data.children,apiFetch,token:data.token,
  onSaved:async()=>{try{const response=await apiFetch('/api/state',{signal:AbortSignal.timeout(12000)});if(response.ok)data=await response.json()}catch{}},
  onTask:async id=>{const origin=$('#studyRoot');try{const response=await apiFetch('/api/state',{signal:AbortSignal.timeout(12000)});if(!response.ok)throw Error();const latest=await response.json();if(!origin?.isConnected)return;const task=latest.tasks.find(t=>t.id===id);if(!task)throw Error();data=latest;child=task.child;taskView=taskDismissed(task)?'已搁置':'全部';page='tasks';render();const target=document.querySelector('[data-query-target="task:'+id+'"]');target?.scrollIntoView({block:'center'});target?.focus({preventScroll:true})}catch{toast('最新决定暂时无法读取，请重试。')}},
  onRecord:id=>{const record=data.records.find(r=>r.id===Number(id));if(!record){toast('记录已保存，请刷新后查看。');return}child=record.child;page='learning';render();const target=document.querySelector('[data-query-target="record:'+Number(id)+'"]');revealLearningTarget(target)}
 });
}
document.addEventListener('click',e=>{const b=e.target.closest('button[data-study-child]');if(!b||!data)return;studyChildID=b.dataset.studyChild;studyDay=data.today;studyTaskID='';page='study';render();window.scrollTo(0,0)});

document.addEventListener('click',e=>{const b=e.target.closest('[data-study-task-add]');if(!b||!data)return;const task=data.tasks.find(t=>t.id===b.dataset.studyTaskAdd&&!taskClosed(t)),owner=data.children.find(c=>c.name===task?.child);if(!owner)return;studyChildID=owner.id;studyDay=task.homework_report?.day||(page==='calendar'&&calendarState.day<=data.today?calendarState.day:data.today);studyTaskID=task.id;page='study';render();window.scrollTo(0,0)});

const studyOwnedFields=['child','day','category','subject','title','note','source','assistance'];
function resetStudyRecord(){studyRecordContext=null;$('#studyRecordNotice')?.remove();const f=$('#recordForm');for(const k of studyOwnedFields){if(f.elements[k])f.elements[k].disabled=false}}
document.addEventListener('click',e=>{const b=e.target.closest('[data-record]');if(!b||!data)return;const r=data.records.find(x=>x.id===Number(b.dataset.record));if(!r?.source.startsWith('作息记录:'))return;
 const f=$('#recordForm');studyRecordContext={id:r.id,values:Object.fromEntries(studyOwnedFields.map(k=>[k,r[k]??'']))};for(const k of studyOwnedFields)f.elements[k].disabled=true;
 $('#recordDialog h2').textContent='给这次功课补充原件';const note=document.createElement('p');note.id='studyRecordNotice';note.className='small';note.textContent='用时、结果和说明统一在“放学后”更正；这里可上传原件。新的观察可以用“跟进 / 复测”另记。';$('#recordError').before(note);
});

function openTaskDecision(id){
 if(busy)return;const t=data.tasks.find(t=>t.id===id);if(!t)return;
 const f=$('#taskDecisionForm');f.reset();f.elements.id.value=id;f.elements.expected_updated.value=t.update?.updated||'';
 $('#taskDecisionTask').textContent=t.title;$('#taskDecisionError').textContent='';$('#taskDecisionCurrent').textContent='';$('#taskDecisionReload').hidden=true;$('#taskDecisionDialog').showModal();
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.taskDecisions)openTaskDecision(b.dataset.taskDecisions);
 if(b.dataset.taskRestore&&!busy){busy=true;b.disabled=true;try{await postTask({id:b.dataset.taskRestore,status:'待跟进',note:'家长恢复此事项，继续跟进。'});render();toast('已恢复跟进')}catch(err){toast(err.message)}finally{busy=false;if(b.isConnected)b.disabled=false}}
});
$('#taskDecisionForm').onsubmit=async e=>{
 e.preventDefault();if(busy)return;const f=e.target;if(!f.reportValidity())return;
 const v=Object.fromEntries(new FormData(f));v.note='家长选择'+taskStatusLabel(v.status)+'；从待跟进移出。'+(v.note.trim()?' '+v.note.trim():'');
 busy=true;for(const c of f.querySelectorAll('button,input,textarea'))c.disabled=true;$('#taskDecisionError').textContent='';
 try{await postTask(v);$('#taskDecisionDialog').close();render();toast('已移到收集箱“已搁置”，可随时恢复')}
 catch(err){$('#taskDecisionError').textContent=(err.message||'暂时无法保存')+(err.status===409?'。选择与说明已保留，请读取最新状态后核对。':'。选择与说明已保留，可以重试核对。');$('#taskDecisionReload').hidden=err.status!==409}
 finally{busy=false;for(const c of f.querySelectorAll('button,input,textarea'))c.disabled=false}
};
$('#taskDecisionReload').onclick=async()=>{
 if(busy)return;busy=true;const b=$('#taskDecisionReload'),f=$('#taskDecisionForm');b.disabled=true;
 try{await load();const t=data.tasks.find(t=>t.id===f.elements.id.value);if(!t)throw Error('原事项暂时无法找到');f.elements.expected_updated.value=t.update?.updated||'';$('#taskDecisionCurrent').textContent='最新状态：'+taskStatusLabel(status(t))+(t.update?.note?' · '+t.update.note:'');$('#taskDecisionError').textContent='请核对最新状态，再决定是否保存当前选择。';b.hidden=true}
 catch(err){$('#taskDecisionError').textContent=err.message||'读取失败，请重试'}finally{busy=false;b.disabled=false}
};
$('#taskDecisionDialog').addEventListener('cancel',e=>{if(busy)e.preventDefault()});

function mountSettings(){
 const root=$('#settingsRoot');if(!window.FamilySettings){root.innerHTML=empty('设置暂未加载，请刷新后重试。');return}
 window.FamilySettings.mount({root,apiFetch,token:data.token,onSaved:async()=>{const r=await apiFetch('/api/state',{signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('配置已保存，家庭资料暂未刷新，请重试读取。');data=await r.json()}});
}

function taskFocusFields(){
 const f=$('#taskFocusForm'),mode=f.elements.mode.value;
 $('#taskFocusWaiting').hidden=mode!=='waiting';f.elements.waiting_for.required=mode==='waiting';
 $('#taskFocusReview').hidden=mode==='next';
 if(mode!=='waiting')f.elements.waiting_for.value='';if(mode==='next')f.elements.review_on.value='';
}
function openTaskFocus(id){
 if(busy)return;const t=data.tasks.find(t=>t.id===id);if(!t||taskClosed(t))return;
 const f=$('#taskFocusForm'),focus=taskFocus(t);f.reset();f.elements.id.value=id;f.elements.version.value=focus.version;f.elements.request_key.value=crypto.randomUUID();
 for(const key of ['mode','next_action','waiting_for','review_on','category','published_on','due_on','scheduled_on'])f.elements[key].value=['category','published_on','due_on','scheduled_on'].includes(key)?(t.agenda?.[key]||(key==='category'?'todo':'')):(focus[key]||'');
 f.elements.title.value=t.title;f.elements.goal.value=t.action||'';f.elements.box.value=focus.box||'inbox';f.elements.scheduled_on.required=false;f.classList.toggle('wish-mode',focus.box==='wish');$('#taskFocusDeadline').hidden=focus.box==='wish';$('#taskFocusTask').hidden=true;$('#taskFocusScheduleLabel').textContent='计划在哪天做 · 可选';$('#taskFocusTitle').textContent=focus.box==='wish'?'编辑心愿':'整理任务与目标';
 $('#taskFocusTask').textContent=t.title;$('#taskFocusDeadline').textContent='原日期要求：'+(t.due||'尚未明确');
 $('#taskFocusError').textContent='';$('#taskFocusLatest').textContent='';$('#taskFocusReload').hidden=true;taskFocusFields();$('#taskFocusDialog').showModal();
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-task-focus]');if(b)openTaskFocus(b.dataset.taskFocus)});
$('#taskFocusForm').elements.mode.onchange=taskFocusFields;
$('#taskFocusForm').onsubmit=async e=>{
 e.preventDefault();if(busy)return;const f=e.target;if(!f.reportValidity())return;
 const body=Object.fromEntries(new FormData(f));body.version=Number(body.version);
 busy=true;const controls=[...f.querySelectorAll('button,input,textarea,select')];for(const c of controls)c.disabled=true;$('#taskFocusError').textContent='';
 try{const r=await apiFetch('/api/task/focus',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});const value=await r.json();if(!r.ok){const err=Error(value.error||'安排暂时无法保存');err.status=r.status;throw err}$('#taskFocusDialog').close();try{await load();toast('安排已保存，日历已更新')}catch{toast('安排已保存，列表暂未刷新，请重试刷新记录')}}
 catch(err){$('#taskFocusError').textContent=(err.message||'安排暂时无法保存')+'。输入已保留，可以重试核对。';$('#taskFocusReload').hidden=err.status!==409}
 finally{busy=false;for(const c of controls)c.disabled=false}
};
$('#taskFocusReload').onclick=async()=>{
 if(busy)return;busy=true;const f=$('#taskFocusForm'),b=$('#taskFocusReload');b.disabled=true;
 try{await load();const t=data.tasks.find(t=>t.id===f.elements.id.value);if(!t)throw Error('原事项已不可用');const focus=taskFocus(t);f.elements.version.value=focus.version;f.elements.request_key.value=crypto.randomUUID();$('#taskFocusLatest').textContent='最新标题：'+t.title+'；完成目标：'+(t.action||'待明确')+'；计划日期：'+(t.agenda?.scheduled_on||'未定')+'；截止：'+(t.agenda?.due_on||'待核对')+'；最新安排：'+({next:'下一步',waiting:'等待中',later:'以后再说'}[focus.mode])+' · '+(focus.next_action||'未写下一步')+(focus.waiting_for?' · 等待'+focus.waiting_for:'')+(focus.review_on?' · '+focus.review_on+'回看':'')+'；事项状态：'+taskStatusLabel(status(t));$('#taskFocusError').textContent='输入仍保留，请核对后再保存。';b.hidden=true}
 catch(err){$('#taskFocusError').textContent=err.message||'读取失败，请重试'}finally{busy=false;b.disabled=false}
};
$('#taskFocusDialog').addEventListener('cancel',e=>{if(busy)e.preventDefault()});

let goalChildID='',goalSelectedID='',goalFocus='';
document.addEventListener('click',e=>{const b=e.target.closest('[data-goal-id]');if(b){goalSelectedID=b.dataset.goalId;goalChildID=b.dataset.goalChild;page='goals';render();window.scrollTo(0,0)}});
// A due re-check reminder opens that child's profile at the wrong-question diagnosis.
document.addEventListener('click',e=>{const b=e.target.closest('[data-diagnosis-child]');if(b&&data.children.some(c=>c.id===b.dataset.diagnosisChild)){goalSelectedID='';goalChildID=b.dataset.diagnosisChild;goalFocus='diagnosis';page='goals';render();goalFocus='';window.scrollTo(0,0)}});

document.addEventListener('click',e=>{const b=e.target.closest('[data-goal-teacher]');if(!b||b.disabled)return;teacherSelectedID=b.dataset.goalTeacher;page='teachers';render();window.scrollTo(0,0)});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-goal-record],[data-goal-task],[data-goal-followup]');if(!b)return;const followup=b.dataset.goalFollowup,record=b.dataset.goalRecord||followup,task=b.dataset.goalTask;b.disabled=true;try{await load(false);const exists=record?data.records.some(r=>r.id===Number(record)):data.tasks.some(t=>t.id===task);if(!exists)throw Error('记录已变化，请更新显示');const open=document.createElement('button');if(followup){open.dataset.followup=followup;open.dataset.followupKind=b.dataset.followupKind||''}else if(record)open.dataset.record=record;else open.dataset.task=task;open.hidden=true;document.body.append(open);open.click();open.remove()}catch(error){const label=document.querySelector('[data-goal-status]');if(label)label.textContent=error.message||'读取失败，请重试'}finally{b.disabled=false}});

document.addEventListener('click',e=>{if(!e.target.closest('[data-course-record]'))return;$('#add').click();if(!$('#recordDialog').open)return;const f=$('#recordForm');f.elements.category.value='课程进度';f.elements.source.value='老师反馈';$('#recordDialog h2').textContent='记课程进度';updateRecordCategory();f.elements.subject.focus()});
