(() => {
'use strict';
// The invite is a one-use login secret: remove it before rendering or API work.
let invitation = new URLSearchParams(location.hash.slice(1)).get('invite') || '';
if (location.hash) history.replaceState(null, '', location.pathname + location.search);
const base = new URL('./', location.href), drafts = new Map();
let identityGeneration=0;
let state = null, selected = null, loading = false, operation = false, recorder = null, micPending = false, recordTimer;
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const editable = t => ['进行中','需补充','待确认'].includes(t.state);
const key = () => [...crypto.getRandomValues(new Uint8Array(20))].map(n => n.toString(16).padStart(2,'0')).join('');
const originalURL = a => /^[a-f0-9]{32}$/.test(a.id) ? new URL('upload/' + a.id, base).href : '';
const message = (text, error = false, where = 'notice') => { $(where).textContent = text; $(where).classList.toggle('error', error); };
async function api(path, body, options = {}) {
  const generation=identityGeneration;const obsolete=()=>{const e=Error('旧会话请求已停止');e.staleIdentity=true;return e};
  const abort = new AbortController(), timer = setTimeout(() => abort.abort(), options.timeout || 12000);
  const headers = body === undefined ? {} : {'Content-Type':'application/json','X-Child-CSRF':state?.csrf || ''};
  try {
    const response = await fetch(new URL('api/' + path, base), {method:body === undefined?'GET':'POST', credentials:'same-origin', cache:'no-store', referrerPolicy:'no-referrer', signal:abort.signal, headers:{...headers,...options.headers}, ...(body === undefined?{}:{body:options.raw?body:JSON.stringify(body)})});
    let result; try { result = await response.json(); } catch { throw Error('营地暂时没有返回完整结果，请重试。'); }
    if(generation!==identityGeneration)throw obsolete();
    if (!response.ok) { const err = Error(result.error || '这次操作没有成功。'); err.status = response.status; err.code = result.code; throw err; }
    return result;
  } catch (err) { if(generation!==identityGeneration)throw obsolete();if (err.name === 'AbortError') throw Error('等待超时，请稍后重试。'); throw err; }
  finally { clearTimeout(timer); }
}
const guided={sequence:0,applied:0,sessions:[],selected:null,loaded:false,loading:false,busy:false,hint:null,hintBusy:false,pending:null,drafts:new Map(),writing:false,conflict:false};
const study = {snapshot:null,day:'',readAt:0,loading:false,busy:false,pending:null,editor:null,add:{},conflict:false};
let campArea = null;
const studyItem = id => study.snapshot?.items.find(item => String(item.id) === String(id));
const today = () => state?.today || new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const minuteText = n => n === null || n === undefined ? '未记录' : n + ' 分钟';
function showArea(area, focus=false) {
  if(guided.selected){renderGuide(false);return}
  campArea = state?.study_enabled ? area : 'reading';
  if (!state?.study_enabled) { study.snapshot=null; $('study-items').replaceChildren(); $('study-summary').replaceChildren(); $('study-editor').replaceChildren(); }
  $('camp-tabs').hidden = !state?.study_enabled;
  $('study-tab').setAttribute('aria-pressed',String(campArea === 'study'));
  $('reading-tab').setAttribute('aria-pressed',String(campArea === 'reading'));
  $('child-study').hidden = campArea !== 'study';
  $('journey').hidden = campArea !== 'reading' || !!selected;
  $('workshop').hidden = campArea !== 'reading' || !selected;
  if (campArea === 'study' && !study.snapshot && !study.loading) readStudy();
  if (focus) (campArea === 'study' ? $('study-title') : selected ? $('work-title') : $('books-title')).scrollIntoView({block:'nearest'});
}
function studyStatus(text, error=false) {
  message(text,error,'study-status');
  const button = document.createElement('button'); button.type = 'button';
  if (study.pending) { button.textContent = '核对并重试这次保存'; button.onclick = saveStudy; button.disabled = study.busy; }
  else if (study.conflict && study.editor && studyItem(study.editor.id)?.editable) {
    button.textContent = '已核对新状态，保留输入继续';
    button.onclick = () => { study.editor.version = studyItem(study.editor.id).version; study.conflict = false; studyStatus('输入已保留，可以继续修改或保存。'); lockStudy(); $('study-edit-form')?.querySelector('input')?.focus(); };
  } else if (!study.snapshot) { button.textContent = '重试读取功课'; button.onclick = readStudy; button.disabled = study.loading; }
  else return;
  $('study-status').append(document.createElement('br'),button);
}
function studyClock(item) {
  const seconds = Math.max(0,Number(item.elapsed_seconds)||0) + (item.status === 'running' ? Math.max(0,Math.floor((Date.now()-study.readAt)/1000)) : 0);
  return `${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
}
function tickStudy() {
  for (const node of $('study-items').querySelectorAll('[data-study-clock]')) { const item = studyItem(node.dataset.studyClock); if (item) node.textContent = studyClock(item); }
}
function studyCard(item) {
  const running = item.status === 'running', finished = item.status === 'finished', active = !!study.snapshot.active_item;
  const waiting = item.result_actor === 'child' && !!item.result;
  const requirement = item.source_task_next_action || item.source_task_action;
  return `<article class="study-card ${running?'is-running':''}" data-study-item="${esc(item.id)}" tabindex="-1"><div class="study-card-heading"><div><p class="small">${esc(item.subject || '功课')}${waiting?' · 我的自述，待家长核对':''}</p><h3>${esc(item.title)}</h3></div>${running?'<span class="chip">正在做</span>':''}</div>${requirement?`<p class="study-requirement"><strong>要做：</strong>${esc(requirement)}</p>`:''}${item.source_task_action && item.source_task_action !== requirement?`<p class="study-requirement">要求：${esc(item.source_task_action)}</p>`:''}${item.source_task_due?`<p class="small">原截止：${esc(item.source_task_due)}</p>`:''}<div class="study-time-row"><span>预计 <strong>${item.planned_minutes === null?'待填写':esc(item.planned_minutes)+' 分钟'}</strong></span><span>实际 <strong>${esc(minuteText(item.actual_minutes))}</strong>${item.time_source==='manual'?' · 补录':''}</span>${running?`<span>当前计时 <strong class="running-clock" data-study-clock="${esc(item.id)}">${studyClock(item)}</strong> <span class="small">分:秒</span></span>`:''}</div>${item.result?`<p>${waiting?'我说：':'已记录：'}${esc(item.result)}${item.assistance?' · '+esc(item.assistance):''}</p>`:item.status==='paused'?'<p class="small">已暂停</p>':''}${item.note?`<p class="study-requirement">${esc(item.note)}</p>`:''}${item.time_needs_review?'<p class="notice error">计时可能包含离开或跨日时间，请与家长核对后补录实际分钟。</p>':''}${!item.editable?'<p class="small">家长已确认或搁置，这里只作回看；需要调整时请告诉家长。</p>':`<div class="study-actions">${running?`<button data-study-action="pause" data-id="${esc(item.id)}" class="primary">暂停休息</button>`:!finished || item.result !== '完成'?`<button data-study-action="start" data-id="${esc(item.id)}" class="primary" ${study.day!==today()||active?'disabled':''}>${item.status==='paused'||finished?'继续这项':'开始这项'}</button>`:''}<button data-study-edit="finish" data-id="${esc(item.id)}">${finished?'补充结果':'我做得怎么样'}</button><button data-study-edit="item" data-id="${esc(item.id)}">改预计</button><button data-study-edit="manual" data-id="${esc(item.id)}">补记用时</button></div>`}${running?'<p class="small">关闭网页还会继续计时。离开前点“暂停休息”。</p>':''}</article>`;
}
function renderStudyEditor() {
  const editor = study.editor, item = editor && studyItem(editor.id);
  $('study-add').hidden = study.day !== today() || !!editor || !study.snapshot;
  if (!editor) { $('study-editor').replaceChildren(); return; }
  const v = editor.values, isItem = editor.type === 'item', finish = editor.type === 'finish';
  const blocked = !item?.editable;
  $('study-editor').innerHTML = `<section class="paper study-edit" tabindex="-1" aria-label="${isItem?'修改功课':finish?'记录结果':'补记用时'}"><h3>${esc(item?.title || '这项功课')}</h3>${blocked?'<p class="notice error">这项功课已被家长确认、搁置或停止分享。输入暂时保留，不能在这里覆盖。</p>':''}<form id="study-edit-form">${isItem?`<label>预计分钟 · 可留空<input name="planned_minutes" type="number" min="0" max="1440" step="1" inputmode="numeric" value="${esc(v.planned_minutes)}"></label><label>科目 · 可留空<input name="subject" maxlength="60" value="${esc(v.subject)}"></label>`:`${finish?`<fieldset class="study-results"><legend>这次做到哪一步？</legend>${['完成','做了一部分','需要帮助'].map(result=>`<label><input name="result" type="radio" value="${result}" required ${v.result===result?'checked':''}>${result}</label>`).join('')}</fieldset>`:''}<label>实际分钟${finish?' · 忘记计时时再补填':''}<input name="actual_minutes" type="number" min="0" max="1440" step="0.01" inputmode="decimal" ${finish?'':'required'} value="${esc(v.actual_minutes)}" placeholder="${finish?'留空使用已记录的计时':''}"></label>${finish?`<label>得到怎样的帮助？<select name="assistance"><option value="">还没记录</option>${['独立尝试','少量提示','逐步帮助','看过讲解或答案'].map(value=>`<option${v.assistance===value?' selected':''}>${value}</option>`).join('')}</select></label><label>卡在哪里，或有什么发现？<textarea name="note" maxlength="2000" rows="3" placeholder="可以直接说需要什么帮助，也可以留空。">${esc(v.note)}</textarea></label><p class="small">这是你的自述，会交给家长一起核对。</p>`:''}`}<div class="study-actions"><button type="submit" class="primary" ${blocked?'disabled':''}>${isItem?'保存预计':finish?'告诉家长':'保存用时'}</button><button type="button" data-study-cancel>先不改</button></div></form></section>`;
}
function renderStudy() {
  const data = study.snapshot;
  $('study-date').value = study.day || today(); $('study-date').max = today();
  $('study-title').textContent = study.day === today() ? '今天要做什么' : '回看这天的功课';
  if (!data) { $('study-summary').replaceChildren(); $('study-items').replaceChildren(); $('study-add').hidden = true; lockStudy(); return; }
  const d = data.day, s = data.summary, otherActive = data.active_item && data.active_item.day !== d.day;
  $('study-summary').innerHTML = `${otherActive?`<p class="notice error">${esc(data.active_item.day)} 的“${esc(data.active_item.title)}”还在计时。<br><button type="button" data-study-day="${esc(data.active_item.day)}">打开那天，暂停并核对</button></p>`:''}<div class="study-summary"><span>${esc(s.unfinished_count ?? data.items.filter(i=>i.result!=='完成').length)} 项尚需跟进</span>${d.stop_time?`<span>停止学习 <strong>${esc(d.stop_time)}</strong></span>`:''}${d.bed_time?`<span>准备睡觉 <strong>${esc(d.bed_time)}</strong></span>`:''}</div>${s.warning?`<p class="notice error">${esc(s.warning)}</p>`:''}`;
  $('study-items').innerHTML = [...data.items].sort((a,b) => Number(b.status==='running')-Number(a.status==='running') || Number(b.editable)-Number(a.editable)).map(studyCard).join('') || '<p class="empty">今天还没有功课记录。先说一项要做的事吧。</p>';
  $('study-add').hidden = study.day !== today();
  for (const [name,value] of Object.entries(study.add)) if ($('study-add').elements[name]) $('study-add').elements[name].value = value;
  renderStudyEditor(); lockStudy(); tickStudy();
}
function lockStudy() {
  const locked = study.busy || study.loading || !!study.pending || operation || !!recorder || micPending || !!(selected && drafts.get(selected)?.pending);
  for (const el of $('child-study').querySelectorAll('input,select,textarea,button')) {
    if (el.closest('#study-status')) continue;
    if (locked) { if (!el.hasAttribute('data-study-locked')) el.dataset.studyLocked=String(el.disabled); el.disabled=true; }
    else if (el.hasAttribute('data-study-locked')) { el.disabled=el.dataset.studyLocked==='true'; delete el.dataset.studyLocked; }
  }
  const submit = $('study-edit-form')?.querySelector('[type="submit"]');
  if (submit) submit.disabled = locked || study.conflict || !studyItem(study.editor?.id)?.editable;
  for (const id of ['study-tab','reading-tab','logout','refresh']) $(id).disabled = locked || loading;
}
function verifyStudy(data, day) {
  if (data?.ok !== true || data.day?.day !== day || !Array.isArray(data.items) || !data.summary || data.items.some(item=>!item || typeof item.id!=='string' || typeof item.title!=='string' || !Number.isInteger(item.version) || typeof item.editable!=='boolean')) throw Error('功课回执暂时无法核对');
  return data;
}
async function readStudy() {
  let generation=identityGeneration;
  if (!state?.study_enabled || study.loading || study.busy) return;
  study.day ||= today(); study.loading = true; lockStudy(); if (!study.snapshot) studyStatus('正在读取这天的功课…');
  try {
    study.snapshot = verifyStudy(await api('study/state',{day:study.day}),study.day); study.readAt=Date.now();
    if (study.editor && studyItem(study.editor.id)?.version !== study.editor.version) study.conflict=true;
    renderStudy();
    studyStatus(study.pending?'上次保存结果还没核对，请重试同一份内容。':study.conflict?'家长或另一个页面更新了这项功课。请看上方的新状态，输入仍保留。':'',study.conflict);
  } catch (err) { if(generation!==identityGeneration)return;
    studyStatus(err.message + ' 当前输入仍保留。',true);
    if (err.status===401) hideSession();
    if (err.status===403) { try { state=await api('state'); renderCamp(); showSession(); message('功课分享已调整，仍可查看家长分享的阅读路线。'); } catch { if(generation===identityGeneration)hideSession(); } }
  }
  finally { if(generation!==identityGeneration)return; study.loading=false; lockStudy(); if (!study.snapshot) studyStatus($('study-status').firstChild?.textContent || '暂时无法读取功课。',true); }
}
function requestStudy(path, body) {
  if (study.busy || study.pending || operation || recorder || micPending) return;
  study.pending={path,body:{...body,day:study.day,request_key:key()}}; saveStudy();
}
async function saveStudy() {
  let generation=identityGeneration;
  if (study.busy || !study.pending) return;
  const request=study.pending; study.busy=true; lockStudy(); studyStatus('正在保存…');
  try {
    const result=verifyStudy(await api(request.path,request.body,{timeout:20000}),request.body.day);
    study.pending=null; study.conflict=false; study.editor=null;
    if (request.path==='study/item' && !request.body.id) { study.add={}; $('study-add').reset(); }
    study.snapshot=result; study.readAt=Date.now(); renderStudy();
    studyStatus(request.body.action==='finish'?'已告诉家长。这是你的自述，等家长一起核对。':'已保存。');
    const savedItem = request.body.id || result.items.find(item => item.title===request.body.title)?.id;
    [...$('study-items').querySelectorAll('[data-study-item]')].find(node=>node.dataset.studyItem===savedItem)?.focus({preventScroll:true});
  } catch (err) { if(generation!==identityGeneration)return;
    if ([400,401,403,404,409,422].includes(err.status)) {
      study.pending=null;
      if (err.status===409 && study.editor) study.conflict=true;
      study.busy=false;
      if (err.status===401) hideSession();
      else { await readStudy();if(generation!==identityGeneration)return; studyStatus(err.message + (study.conflict?' 请核对新状态，输入仍保留。':' 输入仍保留，请核对后再操作。'),true); }
    } else studyStatus(err.message + ' 保存结果未确认，内容保留着，请重试同一次保存。',true);
  } finally { if(generation!==identityGeneration)return; study.busy=false; lockStudy(); const retry=$('study-status').querySelector('button'); if (retry && study.pending) retry.disabled=false; }
}
function hideSession() {
  $('guided-home').hidden=true;  $('login').hidden=false; $('journey').hidden=true; $('workshop').hidden=true; $('child-study').hidden=true; $('camp-tabs').hidden=true; $('logout').hidden=true;
  message('请使用家长给你的专属邀请进入营地。');
}
function wireStudy() {
  $('study-tab').onclick=()=>showArea('study',true); $('reading-tab').onclick=()=>showArea('reading',true);
  $('study-date').onchange=()=>{
    if (!/^\d{4}-\d{2}-\d{2}$/.test($('study-date').value) || $('study-date').value>today()) { $('study-date').value=study.day; return; }
    if (study.editor?.dirty && !confirm('还有结果没有保存，切换日期会清除这次编辑。继续吗？')) { $('study-date').value=study.day; return; }
    study.day=$('study-date').value; study.snapshot=null; study.editor=null; study.conflict=false; renderStudy(); readStudy();
  };
  $('child-study').addEventListener('input',event=>{
    const form=event.target.form; if (!form) return;
    if (form.id==='study-add') study.add=Object.fromEntries(new FormData(form));
    if (form.id==='study-edit-form' && study.editor) { study.editor.values=Object.fromEntries(new FormData(form)); study.editor.dirty=true; }
  });
  $('child-study').addEventListener('click',event=>{
    const b=event.target.closest('button'); if (!b || study.busy || study.pending || study.loading) return;
    const item=studyItem(b.dataset.id);
    if (b.hasAttribute('data-study-cancel')) { const id=study.editor?.id; study.editor=null; study.conflict=false; renderStudyEditor(); studyStatus(''); [...$('study-items').querySelectorAll('[data-study-item]')].find(node=>node.dataset.studyItem===id)?.focus({preventScroll:true}); }
    if (b.dataset.studyEdit && item?.editable) {
      if (study.editor?.dirty && !confirm('还有结果没有保存，要放下这次编辑吗？')) return;
      study.editor={id:item.id,version:item.version,type:b.dataset.studyEdit,dirty:false,values:{...item,actual_minutes:b.dataset.studyEdit==='finish'&&item.status!=='finished'?'':item.actual_minutes}};
      study.conflict=false; renderStudyEditor(); studyStatus(''); lockStudy(); $('study-editor').querySelector('section').scrollIntoView({block:'nearest'}); $('study-edit-form').querySelector('input').focus({preventScroll:true});
    }
    if (b.dataset.studyAction && item?.editable && (!study.editor?.dirty || confirm('还有结果没有保存，要放下这次编辑吗？'))) requestStudy('study/action',{id:item.id,version:item.version,action:b.dataset.studyAction});
    if (b.dataset.studyDay) { $('study-date').value=b.dataset.studyDay; $('study-date').onchange(); }
  });
  $('child-study').addEventListener('submit',event=>{
    const form=event.target; event.preventDefault(); if (study.busy || study.pending || study.loading || !form.reportValidity()) return;
    const v=Object.fromEntries(new FormData(form)), number=value=>value===''?null:Number(value);
    if (form.id==='study-add') { requestStudy('study/item',{title:v.title,subject:v.subject,planned_minutes:number(v.planned_minutes),version:0}); return; }
    const editor=study.editor,item=editor&&studyItem(editor.id);
    if (!editor || !item?.editable || study.conflict) return;
    if (item.version!==editor.version) { study.conflict=true; studyStatus('这项功课已更新。请核对上方新状态，输入仍保留。',true); lockStudy(); return; }
    if (editor.type==='item') requestStudy('study/item',{id:item.id,version:editor.version,subject:v.subject,planned_minutes:number(v.planned_minutes)});
    else { const body={id:item.id,version:editor.version,action:editor.type}; if (editor.type==='finish') Object.assign(body,{result:v.result,assistance:v.assistance,note:v.note}); if(v.actual_minutes!=='') body.actual_minutes=Number(v.actual_minutes); requestStudy('study/action',body); }
  });
  setInterval(tickStudy,1000);
}

function clearIdentity() {
  identityGeneration++;Object.assign(guided,{sequence:0,applied:0,sessions:[],selected:null,loaded:false,loading:false,busy:false,hintBusy:false,pending:null,hint:null,conflict:false,writing:false});guided.drafts.clear();$('guided-assistance-input').value='';$('guided-home').hidden=true;for(const id of ['guided-cards','guided-problem','guided-actions','guided-step','guided-status'])$(id).replaceChildren();$('guided-history').querySelector('div').replaceChildren();
  loading=false;operation=false;drafts.clear(); state = null; selected = null; campArea = null;
  Object.assign(study,{snapshot:null,day:'',readAt:0,loading:false,busy:false,pending:null,editor:null,add:{},conflict:false});
  $('study-add').reset(); $('study-items').replaceChildren(); $('study-summary').replaceChildren(); $('study-editor').replaceChildren();
  $('child-study').hidden=true; $('camp-tabs').hidden=true; studyStatus('');
  for (const id of ['books','agreement','attachments','saved-work']) $(id).replaceChildren();
  for (const id of ['work-text','transcript-text','photo','file']) $(id).value = '';
  $('work-title').textContent = ''; $('earned').textContent = '0'; $('greeting').textContent = '我的成长营地';
  $('welcome').textContent = '选一本想读的书，把你的发现带回来。'; $('book-count').textContent = '';
  $('transcript').hidden = true; $('workshop').hidden = true; message('',false,'work-status');
}
function guideCurrent(){return guided.sessions.find(s=>s.id===guided.selected)}
function guideDraft(){const prior=guided.drafts.get(guided.selected);if(prior&&!prior.dirty&&!guided.pending&&guideCurrent())prior.version=guideCurrent().version;if(!guided.drafts.has(guided.selected))guided.drafts.set(guided.selected,{text:'',entries:[],assistance:'',dirty:false,version:guideCurrent()?.version});return guided.drafts.get(guided.selected)}
function captureDraft(){return guided.selected?guideDraft():draftFor(current())}
function setGuideMode(on){$('welcome').textContent=on?'先试一小步，需要时再找帮助。':state?.study_enabled?'先做一项，休息一下，再看看进展。':'选一条阅读路线，分享自己的发现。';$('workshop').querySelector('.eyebrow').textContent=on?'一次只试一小步':'把发现带回来';$('work-form').querySelector('.small:last-child').textContent=on?'保留自己的尝试和实际帮助。结束这次不代表已经掌握。':'提交后等家长核对。这里不自动发印章，也不替你完成阅读。';for(const id of ['guided-problem','guided-step','guided-actions','guided-history','guided-assistance'])$(id).hidden=!on;$('agreement').hidden=on;$('back').textContent=on?'← 返回今天':'← 返回阅读路线';document.querySelector('label[for="work-text"]').textContent=on?'我想到的思路':'我想分享的发现';$('work-text').maxLength=on?4000:6000;$('work-text').placeholder=on?'先说自己想到哪一步；还没有思路也可以告诉家长。':'可以用自己的话，分享发现。';$('rest').textContent=on?'先保存并暂停':'先歇一会儿';$('workshop').classList.toggle('guided-workshop',on)}
function guideAccept(result,ticket){if(result.ok!==true||!Array.isArray(result.sessions))throw Error('题目回执暂时无法核对');if(ticket<guided.applied){let advanced=false;guided.sessions=guided.sessions.map(old=>{const next=result.sessions.find(s=>s.id===old.id);if(next&&next.version>old.version){advanced=true;return next}return old});if(advanced)renderGuides();return advanced}guided.applied=ticket;guided.sessions=result.sessions.map(s=>{const old=guided.sessions.find(x=>x.id===s.id);return old&&old.version>s.version?old:s});guided.loaded=true;renderGuides();return true}
async function readGuides(){if(guided.loading)return;const generation=identityGeneration,ticket=++guided.sequence;guided.loading=true;try{const result=await api('guided/state',{});if(generation!==identityGeneration)return;if(!guideAccept(result,ticket))return;if(guided.selected&&guideCurrent()&&guideDraft().dirty&&guideDraft().version!==guideCurrent().version)guided.conflict=true;message('',false,'guided-status');if(guided.selected)renderGuide(false)}catch(e){if(generation!==identityGeneration)return;message(e.message+' 可以稍后刷新题目。',true,'guided-status');if(e.status===401)hideSession()}finally{if(generation===identityGeneration)guided.loading=false}}
function renderGuides(){if(!state)return;$('guided-home').hidden=!!guided.selected||!guided.sessions.length&&!guided.loading;$('guided-cards').innerHTML=guided.sessions.map(s=>`<article class="study-card" data-guided-card="${esc(s.id)}"><p class="small">${esc(s.subject||'一起试试')} · ${esc(({active:'可以尝试',paused:'正在休息',closed:'这次结束了',skipped:'这次跳过'}[s.state]||'准备中'))}</p><h3>${esc(s.title)}</h3><button type="button" data-guided-open="${esc(s.id)}">${s.events.some(e=>e.kind==='attempt')?'接着看这道题':'试一试'}</button></article>`).join('');$('guided-cards').querySelectorAll('[data-guided-open]').forEach(b=>b.onclick=()=>{if(operation||recorder||micPending||study.busy||study.pending||selected&&drafts.get(selected)?.pending)return;guided.selected=b.dataset.guidedOpen;selected=null;guided.writing=!guideCurrent().events.some(e=>e.kind==='attempt');guided.conflict=guideDraft().dirty&&guideDraft().version!==guideCurrent().version;renderGuide(true)})}
function guideHistory(s){return s.events.filter(e=>['attempt','hint','pause','skip','finish'].includes(e.kind)).map(e=>`<article class="guided-event"><p class="small">${esc(e.kind==='attempt'?(e.attempt_kind==='first'?'第一次尝试':'再次表达'):({hint:'得到的提示',pause:'暂停',skip:'跳过',finish:'本次结束'}[e.kind]))}</p><p class="work-copy">${esc(e.kind==='hint'?(e.status==='ready'?[e.hint,e.question].filter(Boolean).join('\n'):e.status==='stale'?'这条提示已停止。':e.message||'提示尚未准备好'):e.text||e.message||'')}</p>${e.assistance?`<p class="small">帮助：${esc(e.assistance)}</p>`:''}${(e.attachments||[]).map(a=>`<a href="${esc(originalURL(a))}" target="_blank" rel="noopener noreferrer">${esc(a.name||'我的原件')}</a>`).join(' · ')}</article>`).join('')||'<p class="small">还没有保存自己的尝试。</p>'}
function renderGuide(focus=false){const s=guideCurrent();setGuideMode(true);$('child-study').hidden=true;$('journey').hidden=true;$('camp-tabs').hidden=true;$('guided-home').hidden=true;$('workshop').hidden=false;$('saved-work').hidden=true;const d=guideDraft();
 if(!s){$('work-title').textContent='这道题暂时没有分享';$('guided-problem').replaceChildren();$('guided-history').querySelector('div').replaceChildren();$('work-form').hidden=true;$('guided-actions').replaceChildren();message('家长调整了分享。你的输入仍保留，恢复分享后可以继续核对。',true,'work-status');return}
 $('work-title').textContent=s.title;$('guided-problem').innerHTML=`<p class="work-copy">${esc(s.question_text)}</p><div id="guided-question-originals"></div>${s.material_gaps.length?`<p class="small">${s.material_gaps.map(esc).join('；')}</p>`:''}`;renderAttachments(s.question_attachments.map(a=>({...a,status:'saved'})),'guided-question-originals',false);
 const attempts=s.events.filter(e=>e.kind==='attempt'),hint=[...s.events].reverse().find(e=>e.kind==='hint');
 $('guided-step').textContent=s.state==='paused'?'先休息，愿意时再继续。':s.state==='skipped'?'这次先跳过，已经留下的尝试仍保留。':s.state==='closed'?'这次引导已结束，家长可以一起看你的尝试。':guided.hintBusy?'正在准备一个提示。可以随时暂停或找家长。':!attempts.length?'先留下你自己的尝试。':hint?(hint.status==='ready'?[hint.hint,hint.question].filter(Boolean).join('\n'):hint.message||'这次没有新提示，可以继续表达或找家长'):'已经记下你的尝试。可以自己再说说，或要一个提示。';
 $('guided-history').querySelector('div').innerHTML=guideHistory(s);$('work-form').hidden=!s.allowed_actions.includes('attempt')||!guided.writing;
 $('work-text').value=d.text;$('guided-assistance-input').value=d.assistance;renderAttachments(d.entries);$('transcript').hidden=true;
 $('guided-actions').innerHTML=`${s.allowed_actions.includes('attempt')&&!guided.writing?'<button data-guide-write type="button">再说说我的思路</button>':''}${['hint','resume','finish'].filter(a=>s.allowed_actions.includes(a)).map(a=>`<button data-guide-action="${a}" type="button">${({hint:'给我一个提示',resume:'继续试试',finish:'这次先到这里'})[a]}</button>`).join('')}${s.allowed_actions.includes('pause')?'<button data-guide-action="pause" type="button">暂停</button><button data-guide-help type="button">找家长帮忙</button>':''}${s.allowed_actions.includes('skip')?'<button data-guide-action="skip" type="button">跳过这题</button>':''}`;
 if(guided.pending||guided.hint&&!guided.hintBusy)message('上次请求结果还没核对。内容和编号都保留着。',true,'work-status');else if(guided.conflict)message('安排已更新。输入仍保留，请核对后继续。',true,'work-status');else message('',false,'work-status');
 if(guided.pending||guided.hint&&!guided.hintBusy||guided.conflict){const b=document.createElement('button');b.type='button';b.id='guided-retry';b.textContent=guided.conflict?'已核对，保留输入继续':'核对并重试';b.onclick=()=>{if(guided.conflict){d.version=s.version;guided.conflict=false;renderGuide(false)}else if(guided.pending)guideSend(guided.pending.body.action);else guideSend('hint')};$('work-status').append(b)}lockGuide();if(focus){$('workshop').scrollIntoView({block:'start'});$('workshop').focus({preventScroll:true})}}
function lockGuide(){const s=guideCurrent(),d=guideDraft(),locked=operation||!!recorder||micPending||guided.busy||guided.hintBusy||!!guided.pending||guided.conflict;
 $('work-text').readOnly=locked;for(const id of ['photo','file','use-transcript','cancel-transcript','guided-assistance-input'])$(id).disabled=locked;$('record').disabled=operation||micPending||guided.busy||guided.hintBusy||!!guided.pending&&!recorder;$('submit').disabled=locked||!s?.allowed_actions.includes('attempt');$('submit').textContent='保存这次尝试';$('attachments').querySelectorAll('button').forEach(b=>b.disabled=locked);
 $('rest').disabled=operation||micPending||guided.busy||!!guided.pending;$('back').disabled=operation||!!recorder||micPending||guided.busy||!!guided.pending;$('refresh').disabled=operation||!!recorder||micPending||guided.busy;$('logout').disabled=operation||!!recorder||micPending||guided.busy;
 $('guided-actions').querySelectorAll('button').forEach(b=>b.disabled=['pause','skip'].includes(b.dataset.guideAction)||b.hasAttribute('data-guide-help')?guided.busy:locked||b.dataset.guideAction==='hint'&&d.dirty);if($('guided-retry'))$('guided-retry').disabled=guided.busy||guided.hintBusy;
}
async function submitGuideAttempt(afterPause=false){const s=guideCurrent(),d=guideDraft();if(!s||operation||recorder||micPending||guided.busy||guided.hintBusy||guided.conflict)return;if(d.entries.some(a=>a.status!=='saved')){message('原件还未上传成功，请先重试或移除。',true,'work-status');return}if(!d.text.trim()&&!d.entries.length){message('先写下自己的想法，或上传照片、录音。',true,'work-status');return}const saved=await guideSend('attempt',{kind:s.events.some(e=>e.kind==='attempt')?'explain_again':'first',text:d.text,attachments:d.entries.map(a=>a.id),assistance:d.assistance});if(afterPause&&saved===true)await guideSend('pause')}
async function guideSend(action,fields={},retried=false){const generation=identityGeneration,ticket=++guided.sequence,s=guideCurrent();if(!s)return;const safety=['pause','skip'].includes(action);if(action==='hint'&&guideDraft().dirty){message('先保存这次新想法，再请系统给提示。',true,'work-status');return}if(guided.busy||!s.allowed_actions.includes(action)&&!guided.pending&&!guided.hint)return;if(guided.pending&&guided.pending.body.action!==action){message('上次保存还未核对，请先重试同一份内容。',true,'work-status');return;}const isHint=action==='hint',stored=isHint?guided.hint:guided.pending,request=stored||{body:{id:s.id,version:action==='attempt'?(guideDraft().version??s.version):s.version,request_key:key(),action,...fields}};
 if(isHint){guided.hint=request;guided.hintBusy=true}else{guided.pending=request;guided.busy=true}lockGuide();if(isHint)$('guided-step').textContent='正在准备一个提示。可以随时暂停或找家长。';
 try{const result=await api('guided/action',request.body,{timeout:isHint?100000:25000});if(generation!==identityGeneration)return;const accepted=guideAccept(result,ticket);if(isHint){guided.hint=null;guided.hintBusy=false}else{guided.pending=null;guided.busy=false}if(action==='attempt'){guided.drafts.delete(s.id);guided.writing=false}if(isHint&&guideCurrent()?.state==='active')guided.writing=true;if(safety&&recorder)recorder.stop();if(accepted)guided.conflict=false;if(guided.selected===s.id)renderGuide(false);return true}catch(e){if(generation!==identityGeneration)return;if(e.status===401){hideSession();return}if(e.status&&e.status<500){if(isHint)guided.hint=null;else guided.pending=null;guided.conflict=e.status===409;await readGuides();if(generation!==identityGeneration)return;if(safety&&e.status===409&&!retried&&guideCurrent()?.allowed_actions.includes(action)){guided.busy=false;guided.conflict=false;return await guideSend(action,{note:request.body.note||''},true)}}message(e.message+' 你的输入和原件仍保留。',true,'work-status');if((guided.conflict||(isHint?guided.hint:guided.pending))&&!$('guided-retry')){const b=document.createElement('button');b.type='button';b.id='guided-retry';b.textContent=guided.conflict?'已核对，保留输入继续':'核对并重试';b.onclick=()=>{if(guided.conflict){guideDraft().version=guideCurrent()?.version;guided.conflict=false;renderGuide(false)}else guideSend(action)};$('work-status').append(b)}}finally{if(generation!==identityGeneration)return;if(isHint)guided.hintBusy=false;else guided.busy=false;if(guided.selected)lockGuide()}}
function wireGuided(){$('guided-refresh').onclick=readGuides;$('guided-assistance-input').onchange=()=>{const d=guideDraft();d.assistance=$('guided-assistance-input').value;d.dirty=true};$('guided-actions').onclick=e=>{const b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-guide-write')){guided.writing=true;renderGuide(false);$('work-text').focus()}if(b.dataset.guideAction)guideSend(b.dataset.guideAction);if(b.hasAttribute('data-guide-help'))guideSend('pause',{note:'需要家长帮助'})};const oldRest=()=>rest();$('rest').onclick=()=>guided.selected?submitGuideAttempt(true):oldRest()}

function current() { return state?.tasks.find(t => t.id === selected); }
function draftFor(t) {
  const prior = drafts.get(t.id);
  if (prior && !prior.dirty && !prior.pending && prior.version !== t.version) drafts.delete(t.id);
  if (!drafts.has(t.id)) drafts.set(t.id, {version:t.version, text:t.work_text || '', entries:(t.attachments || []).map(a => ({...a,status:'saved'})), pending:null, dirty:false});
  return drafts.get(t.id);
}
function renderCamp() {
  $('greeting').textContent = (state.child.name || '我') + '的成长营地';
  $('welcome').textContent = state.study_enabled ? '先做一项，休息一下，再看看进展。' : '选一条阅读路线，分享自己的发现。';
  $('earned').textContent = state.tasks.reduce((n,t) => n + (t.award?.status === '已获得' ? t.award.amount : 0), 0);
  $('book-count').textContent = state.tasks.length ? state.tasks.length + ' 条路线' : '';
  $('books').innerHTML = state.tasks.map((t,i) => `<article class="book"><div class="book-visual" aria-hidden="true"><span class="book-number">ROUTE ${String(i+1).padStart(2,'0')}</span><div class="book-object">${esc(t.book || '阅读之旅')}<span>✦</span></div></div><div class="book-body"><div class="book-meta"><span class="chip">${esc(t.state)}</span><span class="small">约定 ${esc(t.stamps)} 枚</span></div><h3>${esc(t.book || '阅读之旅')}</h3><p class="book-scope">${esc(t.scope)}</p><p class="book-scope reading-method">怎么分享：${esc(t.method||'待商量')}</p><p class="book-scope reading-criteria">怎样算完成：${esc(t.criteria||'待商量')}</p>${t.planned_on?`<p class="small">约定回看 ${esc(t.planned_on)}</p>`:''}${t.award?.status === '已获得'?`<p class="earned">✦ 已获得 ${esc(t.award.amount)} 枚印章</p>`:''}<button type="button" data-open="${esc(t.id)}">${t.state === '待确认'?'查看已交的作品':t.state === '已完成'?'回看我的发现':t.state === '暂停'?'看看这条路线':'走进这条路线 →'}</button></div></article>`).join('') || '<div class="empty"><strong>营地准备好了，等一本书来</strong><p>家长还没有与你分享阅读任务。可以一起挑本书，再约定读哪里、怎么分享。</p></div>';
  $('books').querySelectorAll('[data-open]').forEach(b => b.onclick = () => openWork(b.dataset.open));
}
function renderAgreement(t) {
  $('work-title').textContent = t.book;
  $('agreement').innerHTML = [['这次读','scope'],['用哪一版','edition'],['怎么分享','method'],['完成约定','criteria'],['回看日期','planned_on']].filter(([,k]) => t[k]).map(([label,k]) => `<dt>${label}</dt><dd>${esc(t[k])}</dd>`).join('') + `<dt>约定印章</dt><dd>${esc(t.stamps)} 枚 · 由家长看过作品后核对</dd>`;
}
function showSession() { renderGuides(); $('login').hidden = true; $('logout').hidden = false; showArea(campArea || (state.study_enabled ? 'study' : 'reading')); }
async function loadState() {
  let generation=identityGeneration;
  if (loading || operation || recorder || micPending || study.busy || study.pending) return;
  loading = true; $('refresh').disabled = true;
  try {
    const next = await api('state');
    if (state && state.child.id !== next.child.id) clearIdentity();
    generation=identityGeneration;state = next; renderCamp(); showSession();
    if (selected) {
      const t = current();
      if (t && campArea === 'reading') openWork(t.id, false);
      else if (!t) { selected = null; showSession(); message('这条路线暂时没有分享给你。页面内的作品仍保留，家长重新分享后可继续。'); return; }
    }
    if (state.study_enabled && !study.loading) await readStudy();
    await readGuides();
    if(generation!==identityGeneration)return;message('');
  } catch (err) { if(generation!==identityGeneration)return;
    if (err.status === 401) hideSession();
    else message(err.message + ' 页面内的作品仍保留。', true);
  } finally { if(generation!==identityGeneration)return; loading = false; $('refresh').disabled = false; lockStudy(); }
}
function lockWork() {
  if(guided.selected){lockGuide();return}
  const d = selected && drafts.get(selected), locked = operation || !!recorder || micPending || !!d?.pending;
  $('work-text').readOnly = locked;
  for (const id of ['photo','file','rest','back','use-transcript','cancel-transcript']) $(id).disabled = locked;
  $('record').disabled = operation || micPending || (!!d?.pending && !recorder);
  $('submit').disabled = operation || !!recorder || micPending;
  $('refresh').disabled = operation || !!recorder || micPending || loading;
  $('logout').disabled = operation || !!recorder || micPending;
  $('submit').textContent = d?.pending ? '重试这份作品' : '交给家长看看';
  $('attachments').querySelectorAll('button').forEach(b => b.disabled = locked);
  lockStudy();
  if (locked) { $('study-tab').disabled=true; $('reading-tab').disabled=true; }
}
function renderAttachments(entries, target = 'attachments', canEdit = true) {
  $(target).innerHTML = entries.map((a,i) => {
    const url = originalURL(a), ready = !!url && a.status !== 'error';
    return `<div class="attachment"><div class="attachment-line"><span class="attachment-name">${ready?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(a.name || '原件')}</a>`:esc(a.name || '原件')}</span><span class="small">${a.status === 'uploading'?'上传中…':a.status === 'pending'?'等待上传':a.status === 'error'?'未上传':'原件已保存'}</span></div>${ready && a.mime?.startsWith('image/')?`<img src="${esc(url)}" alt="${esc(a.name || '我的作品照片')}" loading="lazy">`:ready && a.mime?.startsWith('audio/')?`<audio controls preload="none" src="${esc(url)}" aria-label="播放${esc(a.name || '我的录音')}"></audio>`:''}${a.error?`<p class="attachment-error">${esc(a.error)}</p>`:''}${canEdit?`<div class="attachment-actions">${a.status === 'error'?`<button type="button" data-retry="${i}">重试上传</button>`:''}${ready && a.mime?.startsWith('audio/') && state.asr?.configured?`<button type="button" data-transcribe="${i}">把这段话转成文字</button>`:''}<button type="button" data-remove="${i}">从这次作品移除</button></div>`:''}</div>`;
  }).join('');
  if (!canEdit) return;
  $(target).querySelectorAll('[data-remove]').forEach(b => b.onclick = () => { const d = captureDraft(); d.entries.splice(Number(b.dataset.remove),1); d.dirty = true; renderAttachments(d.entries); lockWork(); });
  $(target).querySelectorAll('[data-retry]').forEach(b => b.onclick = () => uploadFiles([captureDraft().entries[Number(b.dataset.retry)]]));
  $(target).querySelectorAll('[data-transcribe]').forEach(b => b.onclick = () => transcribe(captureDraft().entries[Number(b.dataset.transcribe)]));
}
function openWork(id, focus = true) {
  const t = state.tasks.find(t => t.id === id); if (!t) return;
  if (focus) message('');
  guided.selected=null;setGuideMode(false);renderGuides();selected = id; campArea = 'reading'; const d = draftFor(t);
  $('journey').hidden = true; $('workshop').hidden = false; $('transcript').hidden = true; renderAgreement(t);
  $('work-form').hidden = !editable(t); $('saved-work').hidden = editable(t);
  if (editable(t)) {
    $('work-text').value = d.text; renderAttachments(d.entries); lockWork();
    message(d.pending?'上次提交的结果还未核对。原文和原件已保留，请重试同一份作品。':t.state === '待确认'?'作品已经交给家长，还在等家长核对。你也可以补充自己的发现。':t.state === '需补充'?'这份作品还需要补充。可以和家长聊聊想再说明什么。':'先看看约定，再用你自己的话分享。', false, 'work-status');
    if (d.version !== t.version && !d.pending) conflict(t, d);
  } else {
    $('saved-work').innerHTML = `<p class="notice">${t.state === '已完成'?'这次阅读已由家长确认，可以回看自己的发现。':t.state === '暂停'?'这条路线正在休息。想继续时，可以和家长商量。':'约定准备好以后，就可以一起开始。'}</p><p class="work-copy">${esc(t.work_text)}</p><div id="saved-originals"></div>${t.award?.status === '已获得'?`<p class="earned">✦ 这条路线已获得 ${esc(t.award.amount)} 枚印章</p>`:''}`;
    renderAttachments(t.attachments.map(a => ({...a,status:'saved'})), 'saved-originals', false); message('', false, 'work-status');
  }
  if (focus) { $('workshop').scrollIntoView({block:'start'}); $('workshop').focus({preventScroll:true}); }
}
function conflict(t, d) {
  message('约定已经更新。你的文字和原件仍保留，请先核对上方的新约定。', true, 'work-status');
  const button = document.createElement('button'); button.type = 'button'; button.textContent = '已看过新约定，保留作品继续';
  button.onclick = () => { d.version = t.version; d.pending = null; message('已保留你的作品，可以继续修改或提交。', false, 'work-status'); lockWork(); };
  $('work-status').append(document.createElement('br'),button); $('submit').disabled = true;
}
async function uploadFiles(entries) {
  let generation=identityGeneration;
  if (operation || (!current()&&!guided.selected)) return;
  const d = captureDraft(); operation = true; lockWork();
  for (const entry of entries) {
    entry.status = 'uploading'; entry.error = ''; renderAttachments(d.entries); lockWork();
    try {
      const result = await api('upload',entry.file,{raw:true,timeout:90000,headers:{'Content-Type':entry.file.type || 'application/octet-stream','X-File-Name':encodeURIComponent(entry.file.name)}});
      Object.assign(entry,result.attachment,{status:'saved',file:null});
    } catch (err) { if(generation!==identityGeneration)return; entry.status = 'error'; entry.error = err.message + ' 原文件保留在当前页面，可以重试。'; }
  }
  operation = false; renderAttachments(d.entries); lockWork();
  if (d.entries.some(e => e.status === 'error')) message('有原件还没上传成功。请重试，或先从这份作品中移除。', true, 'work-status');
  else message('原件已保存。还需要点击“交给家长看看”才会提交这份作品。', false, 'work-status');
}
async function addFiles(files) {
  const t = current(); if ((!t&&!guided.selected) || operation || recorder || micPending) return;
  const d = captureDraft(), entries = [];
  if (d.entries.length + files.length > (guided.selected?3:20)) { message(guided.selected?'这次尝试最多放 3 个原件。':'一份作品最多放 20 个原件，可以先选这次需要的。', true, 'work-status'); return; }
  for (const file of files) {
    entries.push({file,name:file.name,size:file.size,mime:file.type,status:file.size > 20*1024*1024 || !file.size?'error':'pending',error:file.size > 20*1024*1024?'这个文件超过 20 MiB，请换一份小一些的原件。':!file.size?'这份文件是空的，请重新选择。':''});
  }
  d.entries.push(...entries); d.dirty = true; renderAttachments(d.entries);
  await uploadFiles(entries.filter(e => e.status === 'pending'));
}
async function transcribe(entry) {
  let generation=identityGeneration;
  if (operation) return; operation = true; lockWork(); message('正在听这段录音，原音仍然保留。', false, 'work-status');
  try { const result = await api('transcribe',{attachment:entry.id},{timeout:90000}); $('transcript-text').value = result.text; $('transcript').hidden = false; message('转写好了，请听原音核对。文字还没有放进你的作品。', false, 'work-status'); }
  catch (err) { if(generation!==identityGeneration)return; message(err.message + ' 可以直接把原音交给家长，不必等待转写。', true, 'work-status'); }
  finally { if(generation!==identityGeneration)return; operation = false; lockWork(); }
}
async function submit(event) {
  let generation=identityGeneration;
  if(guided.selected){event.preventDefault();submitGuideAttempt();return}
  event.preventDefault(); const t = current(); if (!t || operation || recorder || micPending) return;
  const d = draftFor(t);
  if (!d.pending && d.version !== t.version) { conflict(t,d); return; }
  if (d.entries.some(e => e.status !== 'saved')) { message('请先处理还没上传成功的原件，输入和原文件都保留着。', true, 'work-status'); return; }
  if (!d.text.trim() && !d.entries.length) { message('先留下一点自己的发现，或选一张照片、一段录音。', true, 'work-status'); $('work-text').focus(); return; }
  d.pending ||= {id:t.id,version:d.version,request_key:key(),work_text:d.text,attachments:d.entries.map(a => a.id)};
  operation = true; lockWork(); message('正在把这份作品交给家长…', false, 'work-status');
  try {
    const result = await api('submit',d.pending,{timeout:30000});
    state.tasks[state.tasks.findIndex(x => x.id === t.id)] = result.task;
    drafts.delete(t.id); operation = false; openWork(t.id,false); renderCamp();
    message('作品交好了！等家长看过后再核对印章。', false, 'work-status');
  } catch (err) { if(generation!==identityGeneration)return;
    if (err.status && err.status < 500) {
      d.pending = null;
      if (err.code === 'version_conflict' || err.status === 403) {
        try { state = await api('state'); renderCamp(); const latest = current(); if (latest) { renderAgreement(latest); conflict(latest,d); } else message('这条路线暂时没有分享给你，作品仍保留在当前页面。',true,'work-status'); }
        catch { if(generation!==identityGeneration)return;message('资料已变化，暂时还没读到新约定。作品保留着，请稍后刷新营地。',true,'work-status'); }
      } else message(err.message + ' 文字和原件仍保留。',true,'work-status');
    } else message(err.message + ' 结果还未确认，原文和原件仍保留。请重试同一份作品。',true,'work-status');
  } finally { if(generation!==identityGeneration)return; operation = false; lockWork(); const kept = selected && drafts.get(selected); if (current() && kept?.version !== current().version && !kept?.pending) $('submit').disabled = true; }
}
async function record() {
  if (recorder) { recorder.stop(); return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { $('record-hint').textContent = '这个浏览器不能录音。可以用手机键盘的语音输入，或选择已有录音文件。'; return; }
  let stream;
  try {
    micPending = true; lockWork(); stream = await navigator.mediaDevices.getUserMedia({audio:true});
    const type = ['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(m => MediaRecorder.isTypeSupported(m));
    const active = new MediaRecorder(stream,type?{mimeType:type}:{}), chunks = []; recorder = active;
    active.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    active.onstop = async () => {
      clearTimeout(recordTimer); stream.getTracks().forEach(t => t.stop()); recorder = null; $('record').textContent = '● 说一段'; $('record-hint').textContent = '录音结束。可以先听原音，再决定提交。'; lockWork();
      const mime = active.mimeType || chunks[0]?.type || 'audio/webm', extension = mime.includes('mp4')?'m4a':mime.includes('ogg')?'ogg':'webm';
      if (chunks.length) await addFiles([new File(chunks,(guided.selected?'我的尝试.':'我的阅读分享.') + extension,{type:mime})]);
    };
    active.onerror = () => { $('record-hint').textContent = '录音中断了，请核对已保留的原音，也可以重新录制。'; if (active.state !== 'inactive') active.stop(); };
    active.start(); $('record').textContent = '■ 说好了，停止录音'; $('record-hint').textContent = '正在录音…点击停止，最长 3 分钟。'; recordTimer = setTimeout(() => { if (active.state !== 'inactive') active.stop(); },180000);
  } catch { stream?.getTracks().forEach(t => t.stop()); recorder = null; $('record-hint').textContent = '暂时没能打开麦克风。可以在浏览器允许录音，或使用键盘语音输入、上传已有录音。'; }
  finally { micPending = false; lockWork(); }
}
async function login(invite) {
  let generation=identityGeneration;
  const b = $('login').querySelector('button'); b.disabled = true; message('正在核对邀请…');
  try {
    const raw = invite.trim(); let secret = raw;
    if (raw.includes('://')) { try { secret = new URLSearchParams(new URL(raw).hash.slice(1)).get('invite') || ''; } catch { secret = ''; } }
    const next = await api('login',{invite:secret});
    if (state && state.child.id !== next.child.id) clearIdentity();
    generation=identityGeneration;state = next; $('invite').value = ''; renderCamp(); showSession(); readGuides(); if (selected) openWork(selected,false); message('');
  } catch (err) { if(generation!==identityGeneration)return;
    if (!err.status || err.status >= 500) {
      // The one-use login may have committed before its response was lost.
      try {
        const next = await api('state');
        if (state && state.child.id !== next.child.id) clearIdentity();
        generation=identityGeneration;state = next; $('invite').value = ''; renderCamp(); showSession(); readGuides(); if (selected) openWork(selected,false);
        message('已恢复这个浏览器登录的营地。请核对上方是不是你的名字。'); return;
      } catch { if(generation!==identityGeneration)return;/* No usable session: a fresh one-use invitation is required. */ }
    }
    $('login').hidden = false; message(err.message + ' 请家长生成一个新的专属邀请。',true);
  }
  finally { if(generation!==identityGeneration)return; b.disabled = false; }
}
function rest() { if(guided.selected){if(guided.pending){message('这次保存还未核对，请用原内容重试。',true,'work-status');return}guided.selected=null;setGuideMode(false);showSession();renderGuides();return}selected = null; $('workshop').hidden = true; $('journey').hidden = false; message('可以歇一会儿。没有标记完成，作品保留在这个页面里；关闭或刷新页面前请先提交。'); $('books-title').scrollIntoView({block:'start'}); }
function start() {
  wireStudy();wireGuided();
  $('refresh').onclick = e => { e.preventDefault(); loadState(); };
  $('login').onsubmit = e => { e.preventDefault(); login($('invite').value); };
  $('logout').onclick = async () => {
    const generation=identityGeneration;
    if (([...guided.drafts.values()].some(d=>d.dirty)||guided.pending||guided.hint||[...drafts.values()].some(d => d.dirty || d.pending) || study.pending || study.editor?.dirty || Object.values(study.add).some(Boolean)) && !confirm('还有作品或功课输入没有保存。退出会清除当前页面的输入，确定退出吗？')) return;
    try { await api('logout',{}); clearIdentity(); $('login').hidden = false; $('logout').hidden = true; $('journey').hidden = true; message('已经退出。在公共设备上，可以关闭这个页面。'); }
    catch (err) { if(generation!==identityGeneration)return;message(err.message + ' 退出还没有确认，请重试。',true); }
  };
  $('work-text').oninput = () => { const d = captureDraft(); d.text = $('work-text').value; d.dirty = true;if(guided.selected)lockGuide(); };
  for (const id of ['photo','file']) $(id).onchange = async () => { const files = [...$(id).files]; $(id).value = ''; await addFiles(files); };
  $('record').onclick = record; $('work-form').onsubmit = submit; $('back').onclick = rest; $('rest').onclick = ()=>guided.selected?submitGuideAttempt(true):rest();
  $('use-transcript').onclick = () => { const d = captureDraft(), combined = [d.text,$('transcript-text').value].filter(Boolean).join('\n'); if (combined.length > (guided.selected?4000:6000)) { message('文字超过这次输入的上限，可以先精简，再放进分享。',true,'work-status'); return; } d.text = combined; d.dirty = true; $('work-text').value = d.text; $('transcript').hidden = true; };
  $('cancel-transcript').onclick = () => { $('transcript').hidden = true; };
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) $('record-hint').textContent = '也可以使用手机键盘的语音输入，或上传已有录音。';
  window.addEventListener('beforeunload',e => { if (guided.pending||guided.hint||[...guided.drafts.values()].some(d=>d.dirty)||operation || recorder || micPending || study.pending || study.busy || study.editor?.dirty || Object.values(study.add).some(Boolean) || [...drafts.values()].some(d => d.dirty || d.pending)) { e.preventDefault(); e.returnValue = ''; } });
  window.addEventListener('offline',() => message('网络断开了。当前页面的文字和原文件保留着，连上网络后再重试。',true));
  window.addEventListener('online',() => message('网络回来了。可以继续上传或重试提交，页面内的作品仍保留。'));
  if (invitation) { const secret = invitation; invitation = ''; login(secret); } else loadState();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start,{once:true}); else start();
})();
