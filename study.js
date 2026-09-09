// Timer transitions are saved on the server; browser ticks only update the display.
(() => {
 let ctx=null,snapshot=null,controller=null,sequence=0,clock=null,busy=false,pending=null,editor=null,message='',readAt=0;
 // ponytail: drafts live only in this open page; no database or browser storage writes.
 const drafts=new Map();
 const contextKey=c=>JSON.stringify([c.token,c.child_id,c.day]);
 const draftView=()=>{const key=contextKey(ctx);if(!drafts.has(key))drafts.set(key,{forms:new Map(),editor:null,task_id:''});return drafts.get(key)};
 const formValues=f=>[...new FormData(f)];
 function remember(){
  const el=root();if(!el||!snapshot||busy||pending||el.dataset.studyContext!==contextKey(ctx))return;
  const view=draftView();
  for(const f of el.querySelectorAll('[data-study-form]')){
   if(!f.dataset.studyKey)continue;
   const values=formValues(f);
   if(JSON.stringify(values)===f.dataset.studyInitial)view.forms.delete(f.dataset.studyKey);
   else view.forms.set(f.dataset.studyKey,{values,version:Number(f.dataset.studyVersion),open:f.closest('details')?.open,details:[...f.querySelectorAll('details')].map(d=>d.open)});
  }
  view.editor=editor?{...editor}:null;
 }
 function resetForm(key){const f=[...root()?.querySelectorAll('[data-study-form]')||[]].find(f=>f.dataset.studyKey===key);if(f){f.reset();f.dataset.studyInitial=JSON.stringify(formValues(f))}}
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const root=()=>ctx?.root?.isConnected?ctx.root:null;
 const find=id=>snapshot?.items.find(item=>String(item.id)===String(id));
 const clockText=value=>{const d=new Date(value);return Number.isNaN(+d)?'时间待核对':new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(d)};
 const minutes=value=>value===null||value===undefined?'未记录':`${value} 分钟`;
 const chosen=(actual,value)=>actual===value?' selected':'';
 const fields=(values={})=>`<label>作业名称<input name="title" maxlength="200" required value="${esc(values.title)}" placeholder="例如：数学练习第 3 页"></label><div class="study-fields"><label>预计分钟 · 可留空<input name="planned_minutes" type="number" min="0" max="1440" step="1" inputmode="numeric" value="${esc(values.planned_minutes)}"></label><label>科目 · 可留空<input name="subject" maxlength="60" value="${esc(values.subject)}"></label></div>`;
 function budgetHTML(){
  const d=snapshot.day,s=snapshot.summary,range=d.start_time&&d.stop_time?`${d.start_time} — ${d.stop_time}`:'尚未设置学习时段';
  const childReported=snapshot.items.filter(item=>item.result==='完成'&&item.result_actor==='child').length;
  return `<section class="study-budget" aria-label="今晚时间预算"><div><span>可安排时间</span><strong>${s.remaining_available_minutes===null||s.remaining_available_minutes===undefined?'时间待核对':`${esc(s.remaining_available_minutes)} <small>分钟</small>`}</strong></div><div><span>未完成作业原预估</span><strong>${esc(s.remaining_minutes)} <small>分钟</small></strong>${s.unknown_remaining_count?'<span class="study-warning">另有待估 / 重估项</span>':''}</div><p class="study-meta">整晚 ${esc(range)}${d.bed_time?` · ${esc(d.bed_time)} 准备睡觉`:''} · ${esc(clockText(readAt))} 更新</p>${snapshot.items.length?`<p class="study-completion">已记录“完成” <b>${esc(s.finished_count)}</b> 项 <span>／ 共 ${snapshot.items.length} 项作业${childReported?` · 其中 ${childReported} 项是孩子自述，待家长核对`:''}</span></p>`:''}${s.warning?`<p class="study-warning">${esc(s.warning)}</p>`:''}${s.source_gap?`<details><summary>安排信息待核对</summary><p>${esc(s.source_gap)}</p></details>`:''}</section>`;
 }
 function activeHTML(){const item=snapshot?.active_item;if(!item||item.day===snapshot.day.day)return '';return `<section class="study-active-gap" role="status"><p>${item.day<snapshot.day.day?'有一项较早的计时未结束':'另一天有一项计时未结束'}</p><p class="study-meta">${esc(item.day)} · ${esc(item.title)}</p><button data-study-day="${esc(item.day)}">打开那天，暂停并核对</button></section>`}
 function elapsed(item){return Math.max(0,Number(item.elapsed_seconds)||0)+(item.status==='running'?Math.max(0,Math.floor((Date.now()-readAt)/1000)):0)}
 function timerText(item){const total=Math.floor(elapsed(item));return `${Math.floor(total/60)}:${String(total%60).padStart(2,'0')}`}
 function itemOrder(item){return ['不参加','不适用'].includes(item.source_task_status)?3:item.status==='running'?-1:item.status==='finished'&&item.result_actor==='child'?0:item.result==='完成'?2:1}
 function itemHTML(item){
  const dismissed=['不参加','不适用'].includes(item.source_task_status),ended=item.status==='finished',running=item.status==='running',old=snapshot.day.day!==today(),active=!!snapshot.active_item||snapshot.items.some(x=>x.status==='running');
  const source=item.task_id&&item.source_task_action===null?'<p class="study-warning">原事项暂时无法核对，行动要求和截止时间待核对。</p>':`${item.source_task_next_action?`<p class="study-note"><strong>下一步：</strong>${esc(item.source_task_next_action)}</p>`:''}${item.source_task_action&&item.source_task_action!==item.source_task_next_action?`<p class="study-note">行动要求：${esc(item.source_task_action)}</p>`:''}${item.source_task_due?`<p class="study-meta">原截止：${esc(item.source_task_due)}</p>`:''}`;
  const mainActions=dismissed?`<button data-study-task="${esc(item.task_id)}">查看决定 / 恢复跟进</button>`:!ended?`${running?`<button class="primary" data-study-action="pause" data-id="${esc(item.id)}">暂停</button>`:`<button class="primary" data-study-action="start" data-id="${esc(item.id)}" ${old||active?'disabled':''}>${item.status==='paused'?'继续':'开始'}</button>`}<button data-study-editor="finish" data-id="${esc(item.id)}">结束这项</button>`:`<button ${item.result_actor==='child'?'class="primary"':''} data-study-editor="finish" data-id="${esc(item.id)}">${item.result_actor==='child'?'核对孩子的结果':'更正结果'}</button>${item.result!=='完成'?`<button data-study-action="start" data-id="${esc(item.id)}" ${old||active?'disabled':''}>继续这项</button>`:''}`;
  const secondaryActions=dismissed?`<button data-study-editor="manual" data-id="${esc(item.id)}">核对已记用时</button>`:`${!ended?`<button data-study-editor="item" data-id="${esc(item.id)}">改预计</button>`:''}<button data-study-editor="manual" data-id="${esc(item.id)}">${ended?'更正':'补记'}用时</button>${ended&&item.record_id?`<button data-study-record="${esc(item.record_id)}">学习记录 / 后续尝试</button>`:''}${item.task_id?`<button data-study-task="${esc(item.task_id)}">查看原事项</button>`:''}`;
  return `<article class="study-item ${running?'study-running':''}" data-study-item="${esc(item.id)}"><div class="study-item-top"><div><span class="study-meta">${esc(item.subject||'作业')}${item.task_id?' · 已有待办':''} · 预计 ${item.planned_minutes===null?'待填写':esc(item.planned_minutes)+' 分钟'}</span><h3>${esc(item.title)}</h3></div><span class="study-timer" ${running?`data-study-clock="${esc(item.id)}"`:''}>${ended?esc(minutes(item.actual_minutes)):timerText(item)}</span></div>${source}${ended?`<p>${esc(item.result)}${item.assistance?' · '+esc(item.assistance):''}${item.result_actor==='child'?' · 孩子自述，待家长核对':''}</p>`:running?'<p class="study-meta">正在计时 · 关闭网页仍会继续，休息时请暂停</p>':item.status==='paused'?'<p class="study-meta">已暂停</p>':''}${dismissed?`<p class="study-meta">原事项：${item.source_task_status==='不适用'?'无需处理':'不参加'} · 已移出今晚安排，已记用时保留</p>`:''}${item.time_needs_review?'<p class="study-warning">这段计时可能包含离开或跨日时间，请核对实际分钟。</p>':''}${item.note?`<p class="study-note">${esc(item.note)}</p>`:''}<div class="study-actions study-primary-actions">${mainActions}</div><div class="study-actions study-secondary-actions">${secondaryActions}</div></article>`;
 }
 function editorHTML(){
  if(!editor)return '';
  const item=find(editor.id);if(!item)return '<p class="study-warning">草稿对应的作业暂时无法读取，内容仍保留。<button data-study-cancel>取消编辑</button></p>';
  const v=editor.values||item,type=editor.type;
  if(type==='item')return `<section class="study-editor" aria-label="修改作业"><h3>调整这项作业</h3><form data-study-form="item">${fields(v)}<div class="study-actions"><button class="primary" type="submit">保存修改</button><button type="button" data-study-cancel>取消</button></div></form></section>`;
  return `<section class="study-editor" aria-label="${type==='manual'?'更正用时':'结束作业'}"><h3>${esc(item?.title)}</h3><form data-study-form="${type}">${type==='finish'?`<fieldset class="study-results"><legend>这次做到哪一步？</legend>${['完成','做了一部分','需要帮助'].map(value=>`<label><input type="radio" name="result" value="${value}" required ${v.result===value?'checked':''}>${value}</label>`).join('')}</fieldset>`:''}<label>${type==='manual'?'实际分钟':'实际分钟 · 需要时再更正'}<input name="actual_minutes" type="number" min="0" max="1440" step="0.01" inputmode="decimal" ${type==='manual'?'required':''} value="${esc(type==='finish'&&item?.status!=='finished'?'':v.actual_minutes)}" placeholder="${type==='finish'?'留空则使用已记录计时':''}"></label>${type==='finish'?`<details><summary>帮助与卡点 · 可选</summary><label>当时得到的帮助<select name="assistance"><option value="">未记录</option>${['独立尝试','少量提示','逐步帮助','看过讲解或答案'].map(value=>`<option${chosen(v.assistance,value)}>${value}</option>`).join('')}</select></label><label>哪里卡住了，或这次用了什么方法？<textarea name="note" maxlength="2000">${esc(v.note)}</textarea></label></details>`:''}<p class="study-meta">${type==='finish'&&item?.result_actor==='child'?'以下是孩子自述，请核对实际功课后保存。选择完成会确认原待办完成。':'记录本次结果，不据此判断已经掌握。'}</p><div class="study-actions"><button class="primary" type="submit">${type==='finish'&&item?.result_actor==='child'?'核对并保存':`保存${type==='manual'?'用时':'结果'}`}</button><button type="button" data-study-cancel>取消</button></div></form></section>`;
 }
 function settingsHTML(){
  const d=snapshot.day;
  return `<details class="study-settings"><summary>今晚的时间安排</summary><form data-study-form="day"><p class="study-meta">原计划 ${esc(snapshot.summary.planned_minutes)} 分钟${snapshot.summary.unknown_estimates?'，尚未估全':''}${snapshot.summary.available_minutes===null?'':` · 整晚可用 ${esc(snapshot.summary.available_minutes)} 分钟`}</p><div class="study-fields study-times">${[['start_time','晚间安排开始'],['stop_time','停止学习'],['bed_time','准备睡觉']].map(([name,label])=>`<label>${label}<input type="time" name="${name}" value="${esc(d[name])}"></label>`).join('')}</div><p class="study-meta">时间由家长和孩子约定。已有日历里确定的晚饭、运动等安排会占用相应时段。</p><button type="submit">保存今晚安排</button></form></details>`;
 }
 function weekHTML(){
  return `<details class="study-week"><summary>最近 7 天 · 看自己的变化</summary>${snapshot.week.length?`<div class="study-week-list">${snapshot.week.map(d=>`<button data-study-day="${esc(d.day)}"><span>${esc(d.day.slice(5))} · ${d.item_count} 项</span><span>${d.actual_minutes===null?(d.unknown_actual_count?`已记录 ${d.known_actual_minutes} 分钟 · ${d.unknown_actual_count} 项待补`:'用时未记录'):minutes(d.actual_minutes)}</span><span>${d.needs_help_count?`${d.needs_help_count} 项需要帮助`:d.closed_at?'收尾 '+clockText(d.closed_at):'尚未收尾'}</span></button>`).join('')}</div>`:'<p>还没有这段时间的作业记录。</p>'}<p class="study-meta">只比较已记录的过程，题量、难度和帮助不同时，用时不能直接代表效率。</p></details>`;
 }
 function paint(preserve=true){
  const el=root();if(!el)return;if(preserve)remember();el.dataset.studyContext=contextKey(ctx);
  const itemsHTML=snapshot?[...snapshot.items].sort((a,b)=>itemOrder(a)-itemOrder(b)).map(item=>itemHTML(item)+(editor&&String(editor.id)===String(item.id)?editorHTML():'')).join(''):'';
  el.innerHTML=`<section class="study-view" ${snapshot?'data-study-ready="true"':''}><header class="study-heading"><h1>今日作业</h1><div class="study-picker"><label><span class="sr-only">孩子</span><select data-study-child aria-label="孩子">${ctx.children.map(c=>`<option value="${esc(c.id)}"${chosen(ctx.child_id,c.id)}>${esc(c.name)}</option>`).join('')}</select></label><label><span class="sr-only">查看日期</span><input type="date" data-study-date aria-label="查看日期" value="${esc(ctx.day)}" max="${today()}"></label></div></header><div id="studyStatus" class="study-status" role="status" aria-live="polite">${esc(message)}${pending?'<button data-study-retry>核对并重试这次保存</button>':''}</div>${snapshot?`${activeHTML()}${budgetHTML()}${snapshot.day.closed_at?`<p class="study-closed">${esc(clockText(snapshot.day.closed_at))} 已收尾 · 仍可补充结果</p>`:''}<div class="study-list">${itemsHTML||'<p class="study-empty">说说今天要做的作业。一项一项添加，也可以用手机键盘语音输入。</p>'}${editor&&!find(editor.id)?editorHTML():''}</div><details class="study-add" ${!snapshot.items.length?'open':''}><summary>＋ 添加一项作业</summary><form data-study-form="new"><label>从已有待办选择 · 可选<select name="task_id"><option value="">自己填写</option>${snapshot.available_tasks.map(t=>`<option value="${esc(t.id)}">${esc(t.title)}</option>`).join('')}</select></label>${fields()}<button class="primary" type="submit">加入今晚</button><button type="button" data-study-discard-new>清空草稿</button><p class="study-meta">未提交内容暂存在当前网页，切页可继续；确认加入后才保存到家庭记录。</p></form></details>${settingsHTML()}${weekHTML()}<div class="study-footer"><button data-study-close ${snapshot.day.day!==today()||snapshot.day.closed_at||!snapshot.items.length||snapshot.active_item||snapshot.items.some(i=>i.status==='running')?'disabled':''}>今晚收尾</button><button data-study-refresh>刷新已保存状态</button><span class="study-meta">${snapshot.summary.unfinished_count} 项尚需跟进</span></div>`:'<p class="study-empty">正在读取放学后的安排…</p>'}</section>`;
  for(const form of el.querySelectorAll('[data-study-form]')){
   const kind=form.dataset.studyForm,key=['new','day'].includes(kind)?kind:kind+':'+editor.id;
   form.dataset.studyKey=key;form.dataset.studyInitial=JSON.stringify(formValues(form));
   form.dataset.studyVersion=String(kind==='new'?0:kind==='day'?snapshot.day.version:find(editor.id).version);
   const draft=draftView().forms.get(key);if(!draft)continue;
   for(const [name,value] of draft.values){const field=form.elements[name];if(field instanceof RadioNodeList){for(const radio of field)radio.checked=radio.value===value}else if(field){if(name==='task_id'&&value&&![...field.options].some(o=>o.value===value))field.add(new Option('原待办暂不可用 · 请核对',value));field.value=value}}
   form.dataset.studyVersion=String(draft.version);
   if(draft.open&&form.closest('details'))form.closest('details').open=true;
   [...form.querySelectorAll('details')].forEach((d,i)=>d.open=!!draft.details[i]);
  }
  const title=el.querySelector('[data-study-form="item"] [name="title"]');if(title&&find(editor?.id)?.task_id)title.readOnly=true;
  const selecting=el.querySelector('[data-study-form="new"] [name="task_id"]');if(selecting?.value)setSource(selecting.closest('form'));
  lock();tick();
 }
 function consumeTask(){
  if(pending)return;
  const view=draftView();if(ctx.task_id){view.task_id=ctx.task_id;ctx.task_id='';ctx.onTaskSelected?.()}
  const taskID=view.task_id;if(!taskID)return;
  const existing=snapshot.items.find(item=>String(item.task_id)===String(taskID));
  if(existing){view.task_id='';const target=[...root()?.querySelectorAll('[data-study-item]')||[]].find(item=>item.dataset.studyItem===String(existing.id));if(target){target.tabIndex=-1;target.scrollIntoView({block:'center'});target.focus({preventScroll:true})}return}
  if(!snapshot.available_tasks.some(task=>String(task.id)===String(taskID))){view.task_id='';status('所选事项暂不可安排，请刷新后重新从事项卡进入');return}
  const form=root()?.querySelector('[data-study-form="new"]');if(!form)return;
  if(form.elements.task_id.value!==String(taskID)&&JSON.stringify(formValues(form))!==form.dataset.studyInitial){form.closest('details').open=true;status('已有未提交作业草稿，请先加入今晚或清空草稿，再安排刚选择的事项。');return}
  view.task_id='';form.closest('details').open=true;form.elements.task_id.value=String(taskID);setSource(form);remember();status('已带入所选事项，请核对后加入今晚。');form.scrollIntoView({block:'center'});
 }
 function lock(){const el=root();if(!el)return;for(const control of el.querySelectorAll('input,select,textarea,button')){if(busy||pending){if(!control.hasAttribute('data-study-locked'))control.dataset.studyLocked=String(control.disabled);control.disabled=!(control.hasAttribute('data-study-retry')&&!busy)}else if(control.hasAttribute('data-study-locked')){control.disabled=control.dataset.studyLocked==='true';delete control.dataset.studyLocked}}}
 function status(text){message=text;const area=root()?.querySelector('#studyStatus');if(area)area.innerHTML=`${esc(text)}${pending?'<button data-study-retry>核对并重试这次保存</button>':!snapshot?'<button data-study-refresh>重试读取</button>':''}`;lock()}
 function tick(){for(const node of root()?.querySelectorAll('[data-study-clock]')||[]){const item=find(node.dataset.studyClock);if(item)node.textContent=timerText(item)}}
 async function read(rebase=false){
  if(!ctx||busy)return;controller?.abort();const serial=++sequence,active=ctx;controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),15000);
  try{const response=await active.apiFetch('/api/study?'+new URLSearchParams({child_id:active.child_id,day:active.day}),{signal:controller.signal}),data=await response.json();if(!response.ok)throw Error(data.error||'读取失败');if(serial!==sequence||ctx!==active)return;if(!data.day||!Array.isArray(data.items)||!data.summary||!Array.isArray(data.week)||!Array.isArray(data.available_tasks))throw Error('返回资料无法核对');remember();snapshot=data;readAt=Date.now();if(rebase){for(const [key,draft] of draftView().forms){const [kind,id]=key.split(':');if(kind==='day')draft.version=snapshot.day.version;else if(kind!=='new'&&find(id))draft.version=find(id).version}}paint(false);if(active===ctx&&!pending)consumeTask()}
  catch(e){if(serial===sequence)status(e.name==='AbortError'?'读取超时，请刷新重试。':e.message||'暂时无法读取。')}
  finally{clearTimeout(timeout)}
 }
 function newRequest(path,body,form=''){if(busy||pending)return;remember();pending={path,form,context:contextKey(ctx),body:{...body,child_id:ctx.child_id,day:ctx.day,request_key:crypto.randomUUID()}};save()}
 async function save(){
  if(busy||!pending)return;busy=true;status('正在保存…');const current=pending,active=ctx,abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),20000);
  try{
   const response=await active.apiFetch(current.path,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json','X-Family-Token':active.token},body:JSON.stringify(current.body)}),result=await response.json();
   if(!response.ok){if([400,404,409,422].includes(response.status))pending=null;if(response.status===403&&result.code==='csrf_expired'){status('尚未保存，填写已保留。请重试保存。');return}throw Error((result.error||'保存失败')+(response.status===409?'。输入已保留，请刷新状态后再保存。':''))}
   if(result.ok!==true||result.day?.child_id!==current.body.child_id||result.day?.day!==current.body.day||!Array.isArray(result.items)||!Array.isArray(result.available_tasks)||!Array.isArray(result.week)||!result.summary)throw Error('保存回执暂时无法核对');
   const view=drafts.get(current.context);if(current.form){view?.forms.delete(current.form);if(view?.editor&&current.form===view.editor.type+':'+view.editor.id)view.editor=null}
   pending=null;message='已保存';
   if(ctx&&contextKey(ctx)===current.context){if(current.form)resetForm(current.form);editor=view?.editor||null;snapshot=result;readAt=Date.now();paint()}
   try{await active.onSaved?.()}catch{message='已保存；首页暂未刷新。'}
  }catch(e){status((e.name==='AbortError'?'保存等待超时':e.message||'连接暂时中断')+(pending?'。结果尚未核对，内容已保留，请重试原请求。':''))}
  finally{clearTimeout(timeout);busy=false;lock();if(pending===current&&ctx===active){const retry=root()?.querySelector('[data-study-retry]');retry?.scrollIntoView({block:'nearest'});retry?.focus({preventScroll:true})}if(!pending&&message==='已保存')await read()}
 }
 function setSource(form){const source=snapshot.available_tasks.find(t=>String(t.id)===form.elements.task_id.value),title=form.elements.title;title.readOnly=!!form.elements.task_id.value;title.required=!title.readOnly;if(source)title.value=source.title}
 function change(e){
  if(busy||pending)return;
  if(e.target.matches('[data-study-child],[data-study-date]')){const value=e.target.value;if(!value)return;remember();ctx={...ctx,child_id:e.target.matches('[data-study-child]')?value:ctx.child_id,day:e.target.matches('[data-study-date]')?value:ctx.day};if(e.target.matches('[data-study-child]'))ctx.onChildChanged?.(ctx.child_id);else ctx.onDayChanged?.(ctx.day);snapshot=null;editor=draftView().editor;message='';paint();read()}
  if(e.target.name==='task_id')setSource(e.target.form);
 }
 function click(e){
  const button=e.target.closest('button');if(!button||!root()?.contains(button)||busy)return;
  if(button.hasAttribute('data-study-retry')){save();return}if(pending)return;
  if(button.hasAttribute('data-study-refresh')){message='';read(true)}
  if(button.hasAttribute('data-study-cancel')){remember();if(editor){const key=editor.type+':'+editor.id;draftView().forms.delete(key);resetForm(key)}editor=null;paint()}
  if(button.hasAttribute('data-study-discard-new')){remember();draftView().forms.delete('new');resetForm('new');paint();consumeTask()}
  if(button.dataset.studyEditor){const item=find(button.dataset.id);if(!item)return;remember();editor={type:button.dataset.studyEditor,id:item.id};paint();root()?.querySelector('.study-editor')?.scrollIntoView({block:'nearest'});root()?.querySelector('.study-editor input:not([readonly])')?.focus()}
  if(button.dataset.studyAction){const item=find(button.dataset.id);if(item)newRequest('/api/study/action',{id:item.id,version:item.version,action:button.dataset.studyAction})}
  if(button.dataset.studyRecord)ctx.onRecord?.(Number(button.dataset.studyRecord));
  if(button.dataset.studyTask)ctx.onTask?.(button.dataset.studyTask);
  if(button.dataset.studyDay){remember();ctx={...ctx,day:button.dataset.studyDay};ctx.onDayChanged?.(ctx.day);snapshot=null;editor=draftView().editor;message='';paint();read()}
  if(button.hasAttribute('data-study-close'))newRequest('/api/study/action',{action:'close_day',version:snapshot.day.version});
 }
 function submit(e){
  const form=e.target.closest('[data-study-form]');if(!form)return;e.preventDefault();if(busy||pending||!form.reportValidity())return;
  const type=form.dataset.studyForm,v=Object.fromEntries(new FormData(form)),item=find(editor?.id),version=Number(form.dataset.studyVersion),number=value=>value===''?null:Number(value);
  if(type==='day')newRequest('/api/study/day',{...v,version},form.dataset.studyKey);
  if(type==='new'||type==='item'){const body={subject:v.subject,planned_minutes:number(v.planned_minutes),version};if(type==='item'){body.id=item.id;if(!item.task_id)body.title=v.title}else if(v.task_id)body.task_id=v.task_id;else body.title=v.title;newRequest('/api/study/item',body,form.dataset.studyKey)}
  if(type==='finish'||type==='manual'){const body={id:item.id,version,action:type};if(type==='finish'){body.result=v.result;body.assistance=v.assistance;body.note=v.note}if(v.actual_minutes!=='')body.actual_minutes=Number(v.actual_minutes);newRequest('/api/study/action',body,form.dataset.studyKey)}
 }
 function leave(){remember();clearInterval(clock);clock=null;controller?.abort();sequence++;if(ctx?.root){ctx.root.removeEventListener('click',click);ctx.root.removeEventListener('submit',submit);ctx.root.removeEventListener('change',change)}ctx=null}
 function mount(options){
  leave();ctx={...options,day:options.day||today()};snapshot=null;editor=null;message=pending?'上次保存结果尚未核对，请先重试。':'';
  if(pending){ctx.child_id=pending.body.child_id;ctx.day=pending.body.day;ctx.onChildChanged?.(ctx.child_id);ctx.onDayChanged?.(ctx.day)}
  editor=draftView().editor;
  ctx.root.addEventListener('click',click);ctx.root.addEventListener('submit',submit);ctx.root.addEventListener('change',change);paint();read();clock=setInterval(tick,1000);
 }
 window.addEventListener('beforeunload',e=>{remember();if(pending||[...drafts.values()].some(view=>view.forms.size)){e.preventDefault();e.returnValue=''}});
 window.FamilyStudy={mount,leave};
})();
