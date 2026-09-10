// Parent-only teaching observations. Drafts stay in this open page, never browser storage.
(() => {
 let ctx=null,state=null,selected='',editing='',busy=false,pending=null,conflict=null,message='',sequence=0;
 const drafts=new Map();
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const root=()=>ctx?.root?.isConnected?ctx.root:null;
 const teacher=()=>state?.teachers.find(t=>t.id===selected);
 const kinds={requirement:'明确要求',praise:'表扬的行为',preference:'老师明说的偏好'};
 const targets={household:'自己家孩子',other_students:'其他学生的行为',class:'全班'};
 const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const stamp=v=>v?String(v).slice(0,16).replace('T',' '):'尚未检查';
 const link=v=>{try{const u=new URL(v);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:''}catch{return ''}};
 const options=(items,value)=>items.map(([id,label])=>`<option value="${esc(id)}"${id===value?' selected':''}>${esc(label)}</option>`).join('');
 const values=f=>[...new FormData(f)];
 function remember(){
  if(busy||pending)return;
  for(const f of root()?.querySelectorAll('[data-teacher-form]')||[]){
   const input=values(f);
   if(JSON.stringify(input)===f.dataset.initial)drafts.delete(f.dataset.key);
   else drafts.set(f.dataset.key,{values:input,version:Number(f.dataset.version),open:f.closest('details')?.open});
  }
 }
 function restore(){
  for(const f of root()?.querySelectorAll('[data-teacher-form]')||[]){
   f.dataset.initial=JSON.stringify(values(f));
   const d=drafts.get(f.dataset.key);if(!d)continue;
   for(const el of f.elements){if(!el.name)continue;const matches=d.values.filter(([key])=>key===el.name).map(([,value])=>value);if(el.type==='checkbox')el.checked=matches.includes(el.value);else if(matches.length)el.value=matches[0]}
   f.dataset.version=String(d.version);if(d.open&&f.closest('details'))f.closest('details').open=true;
  }
  targetFields();lock();
 }
 function checks(name,items,checked=[]){return items.map(x=>`<label class="teacher-check"><input type="checkbox" name="${name}" value="${esc(x.id)}"${checked.includes(x.id)?' checked':''}>${esc(x.name)}</label>`).join('')}
 function profileHTML(t){return `<details class="card teacher-profile"${t?'':' open'}><summary>${t?'修改老师档案':'添加老师'}</summary><form data-teacher-form="profile" data-key="profile:${esc(t?.id||'new')}" data-version="${Number(t?.version||0)}"><div class="formrow"><label>老师称呼<input name="display_name" maxlength="80" required value="${esc(t?.display_name)}" autocomplete="off"></label><label>科目<input name="subject" maxlength="80" value="${esc(t?.subject)}" placeholder="例如：语文"></label></div><fieldset><legend>教哪个孩子</legend><div class="teacher-checks">${checks('child_ids',state.children,t?.child_ids)}</div></fieldset><fieldset><legend>对应班级群 · 可选</legend><div class="teacher-checks">${checks('source_ids',state.sources,t?.source_ids)||'<span class="small muted">尚未绑定班级群，可先手动记录。</span>'}</div></fieldset><label>公开教学资料网址 · 可选<input name="public_url" type="url" maxlength="2000" value="${esc(t?.public_url)}" placeholder="https://学校官网上的教师介绍或教学页面"></label><p class="small muted">仅填写学校或老师公开的教学页面，后台按周检查。</p>${t?`<label class="teacher-check"><input name="archived" type="checkbox"${t.archived?' checked':''}>归档这位老师，保留记录</label>`:''}<div class="teacher-actions"><button class="primary" type="submit">保存档案</button><button type="button" data-teacher-discard>还原未保存填写</button></div></form></details>`}
 function publicHTML(t){
  const p=t.public_info||{},url=link(p.url||t.public_url),labels={unconfigured:'未配置',pending:'待首次检查',checked:'已检查',unchanged:'已检查',updated:'资料曾更新',changed:'资料曾更新',error:'读取失败'};
  if(!url)return '';
  const text=String(p.text||'');
  return `<section class="card teacher-public"><h2>公开教学资料</h2><p class="small">${esc(labels[p.status]||p.status||'待首次检查')} · <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">查看公开原页</a></p>${p.error?`<p class="error">${esc(p.error)}</p>`:''}${text?`<p class="source">${esc(text.slice(0,600))}</p>${text.length>600?`<details><summary>其余页面摘录</summary><p class="source">${esc(text.slice(600,6000))}</p></details>`:''}`:'<p class="muted small">尚无已读取的页面内容。</p>'}<p class="small muted">最近检查 ${esc(stamp(p.last_attempt))}${p.last_success?' · 最近成功 '+esc(stamp(p.last_success)):''}${p.changed_at?' · 发现变化 '+esc(stamp(p.changed_at)):''}${p.next_check_at?' · 下次 '+esc(stamp(p.next_check_at)):''}</p><p class="small muted">页面变化待家长核对，不自动写成老师偏好。</p></section>`;
 }
 function observationHTML(o){
  const source=state.sources.find(s=>s.id===o.source_id),url=link(o.source_url),child=state.children.find(c=>c.id===o.child_id);
  return `<article class="teacher-observation${o.status==='withdrawn'?' teacher-withdrawn':''}" data-teacher-observation="${esc(o.id)}"><div class="teacher-record-top"><span class="chip">${esc(kinds[o.kind]||o.kind)}${o.status==='withdrawn'?' · 已撤回':''}</span><time>${esc(o.day)}</time></div><p class="small muted">${esc(o.target==='household'?child?.name||'本家孩子待核对':targets[o.target])}</p><p class="source teacher-behavior">${esc(o.behavior)}</p>${o.teacher_reason?`<p class="source"><strong>老师说明的理由：</strong>${esc(o.teacher_reason)}</p>`:'<p class="small muted">尚未记录老师明确说的理由，原因未知。</p>'}${o.parent_note?`<p class="source teacher-interpretation"><strong>家长理解 · 待核对：</strong>${esc(o.parent_note)}</p>`:''}<div class="teacher-record-bottom"><p class="small muted">出处：${esc(source?.name||'家长手动记录')}${o.message_id?' · 消息 '+esc(o.message_id):''}${url?` · <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">原页</a>`:''}</p><button type="button" data-teacher-edit="${esc(o.id)}">更正 / 撤回</button></div></article>`;
 }
 function observationForm(t){
  const o=state.observations.find(x=>x.id===editing&&x.teacher_id===t.id),children=state.children.filter(c=>t.child_ids.includes(c.id)),sources=state.sources.filter(s=>t.source_ids.includes(s.id));
  return `<details class="card teacher-write"${o||!state.observations.some(x=>x.teacher_id===t.id)?' open':''}><summary>${o?'更正这条记录':'＋ 记一条老师反馈'}</summary><form data-teacher-form="observation" data-key="observation:${esc(o?.id||'new:'+t.id)}" data-version="${Number(o?.version||0)}"><div class="formrow"><label>发生日期<input name="day" type="date" required max="${today()}" value="${esc(o?.day||today())}"></label><label>记录什么<select name="kind">${options(Object.entries(kinds),o?.kind||'requirement')}</select></label></div><div class="formrow"><label>适用于谁<select name="target">${options(Object.entries(targets),o?.target||'class')}</select></label><label data-teacher-own>自己家的孩子<select name="child_id">${options(children.map(c=>[c.id,c.name]),o?.child_id||children[0]?.id)}</select></label></div><label>原话或观察到的具体行为<textarea name="behavior" required maxlength="3000" placeholder="例如：表扬订正后又独立做了一遍；其他学生只记行为。">${esc(o?.behavior)}</textarea></label><label>老师明确说的理由 · 可空<textarea name="teacher_reason" maxlength="2000" placeholder="老师没说就留空，不替老师猜原因。">${esc(o?.teacher_reason)}</textarea></label><label>我的理解 · 待核对，可空<textarea name="parent_note" maxlength="2000" placeholder="例如：下次沟通时确认是否需要写完整订正步骤。">${esc(o?.parent_note)}</textarea></label><div class="formrow"><label>出处群 · 可空<select name="source_id"><option value="">手动观察 / 公开页面</option>${options(sources.map(s=>[s.id,s.name]),o?.source_id)}</select></label><label>原消息编号 · 可空<input name="message_id" maxlength="160" value="${esc(o?.message_id)}" placeholder="有可核对的原消息时填写"></label></div><label>出处网址 · 可空<input name="source_url" type="url" maxlength="2000" value="${esc(o?.source_url)}"></label>${o?`<label>这条记录<select name="status">${options([['active','保留，更正内容'],['withdrawn','撤回，保留历史']],o.status)}</select></label>`:''}<div class="teacher-actions"><button class="primary" type="submit">${o?'保存更正':'保存记录'}</button><button type="button" data-teacher-discard>还原未保存填写</button>${o?'<button type="button" data-teacher-new-observation>返回新增</button>':''}</div><p class="small muted">草稿仅保留在当前打开的网页；刷新或关闭前请保存。</p></form></details>`;
 }
 function paint(preserve=true){
  const el=root();if(!el)return;if(preserve)remember();
  if(state&&!selected)selected=state.teachers[0]?.id||'new';
  const t=teacher();
  el.innerHTML=`<section class="teachers-view"><header class="teacher-heading"><div><h1>老师与教学要求</h1><p class="muted">看具体要求，记下值得学习的行为。</p></div><button type="button" data-teacher-select="new">＋ 添加老师</button></header><div id="teachersStatus" role="status" aria-live="polite"></div>${state?`<nav class="teacher-picker" aria-label="选择老师">${state.teachers.map(x=>`<button type="button" data-teacher-select="${esc(x.id)}" aria-pressed="${x.id===selected}">${esc(x.display_name)}<small>${esc(x.subject)}${x.archived?' · 已归档':''}</small></button>`).join('')}</nav>${state.source_error?`<p class="error">${esc(state.source_error)}</p>`:''}${profileHTML(t)}${t?`<div class="teacher-content"><section><h2>${esc(t.display_name)} · 已记录的要求与反馈</h2>${observationForm(t)}<div class="teacher-records">${state.observations.filter(o=>o.teacher_id===t.id).map(observationHTML).join('')||'<p class="muted">还没有记录。从老师最近一次明确要求或反馈开始。</p>'}</div><p class="small muted">一次表扬说明这次行为受到认可，不代表固定偏好。</p></section><div>${publicHTML(t)}</div></div>`:''}`:'<p class="muted">正在读取老师档案…</p>'}</section>`;
  restore();status(message);
 }
 function targetFields(){const f=root()?.querySelector('[data-teacher-form="observation"]');if(!f)return;const own=f.elements.target.value==='household';f.querySelector('[data-teacher-own]').hidden=!own;f.elements.child_id.required=own;f.elements.child_id.disabled=!own}
 function lock(){for(const b of root()?.querySelectorAll('button,input,textarea,select')||[]){if(busy||pending)b.disabled=!(b.hasAttribute('data-teacher-retry')&&!busy)}if(!busy&&!pending)targetFields()}
 function status(text){message=text;const el=root()?.querySelector('#teachersStatus');if(el)el.innerHTML=`${esc(text)}${pending?'<button type="button" data-teacher-retry>核对并重试这次保存</button>':conflict?`<button type="button" ${conflict.refreshed?'data-teacher-accept-version':'data-teacher-conflict'}>${conflict.refreshed?'已核对，继续编辑':'读取最新记录，保留填写'}</button>`:'<button type="button" data-teacher-refresh>刷新已保存记录</button>'}`;lock()}
 async function request(path,body){const active=ctx;if(!active)throw Error('请回到老师页面重试');const response=await active.apiFetch(path,{signal:AbortSignal.timeout(15000),...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':active.token},body:JSON.stringify(body)}:{})});let result;try{result=await response.json()}catch{throw Error('未能核对服务器答复')}if(!response.ok){const e=Error(result.error||'保存未成功');e.status=response.status;throw e}return result}
 async function read(){
  const seq=++sequence;
  try{const next=await request('/api/teachers');if(seq!==sequence||!root())return false;if(!['teachers','observations','children','sources'].every(k=>Array.isArray(next[k])))throw Error('老师记录格式暂时无法核对');remember();state=next;paint(false);return true}
  catch(e){if(seq===sequence)status(e.message+'；填写保留，可重试。');return false}
 }
 async function save(){
  if(busy||!pending)return;busy=true;sequence++;const operation=pending;status('正在保存…');
  try{
   const result=await request('/api/teachers/'+operation.kind,operation.body),item=result[operation.kind==='profile'?'teacher':'observation'];
   if(!result.ok||!item?.id)throw Error('保存答复无法核对');
   const list=operation.kind==='profile'?'teachers':'observations',at=state[list].findIndex(x=>x.id===item.id);if(at<0)state[list].unshift(item);else state[list][at]=item;
   drafts.delete(operation.key);pending=null;conflict=null;
   if(operation.kind==='profile'&&selected==='new')selected=item.id;
   if(operation.kind==='observation'&&editing===operation.body.id)editing='';
   message='已保存。';busy=false;paint(false);
   if(root()&&!await read())status('已保存，列表刷新失败；可刷新记录，不必再次提交。');
  }catch(e){
   if(e.status>=400&&e.status<500&&![401,403,408,429].includes(e.status)){pending=null;if(e.status===409)conflict={key:operation.key,refreshed:false}}
   message=e.message+(pending?'；结果尚未核对，请用原编号重试。':'；填写保留，请核对后再保存。');
  }finally{busy=false;paint(false)}
 }
 async function submit(e){
  const f=e.target.closest('[data-teacher-form]');if(!f)return;e.preventDefault();if(busy||pending||!f.reportValidity())return;
  if(conflict?.key===f.dataset.key){status('先核对最新记录，再继续保存更正。');return}
  remember();const entries=new FormData(f),v=Object.fromEntries(entries),kind=f.dataset.teacherForm,t=teacher();
  let body={id:kind==='profile'?t?.id||'':editing||'',version:Number(f.dataset.version),request_key:crypto.randomUUID()};
  if(kind==='profile'){Object.assign(body,v,{child_ids:entries.getAll('child_ids'),source_ids:entries.getAll('source_ids'),archived:entries.has('archived')});if(!body.child_ids.length){status('请选择老师教的孩子。');return}}
  else Object.assign(body,v,{teacher_id:t.id,child_id:v.target==='household'?v.child_id:'',status:v.status||'active'});
  pending={kind,body,key:f.dataset.key};await save();
 }
 async function click(e){
  const b=e.target.closest('button');if(!b||busy)return;
  if(b.hasAttribute('data-teacher-retry')){await save();return}if(pending)return;
  if(b.hasAttribute('data-teacher-refresh')){await read();return}
  if(b.hasAttribute('data-teacher-conflict')){if(await read()){conflict.refreshed=true;status('已显示最新保存内容；你的填写保留。对照记录后继续编辑。')}return}
  if(b.hasAttribute('data-teacher-accept-version')){const d=drafts.get(conflict.key),[kind,id]=conflict.key.split(':');if(d)d.version=(kind==='profile'?state.teachers:state.observations).find(x=>x.id===id)?.version??d.version;conflict=null;message='可以继续编辑；再次保存才会提交更正。';paint(false);return}
  remember();
  if(b.hasAttribute('data-teacher-select')){selected=b.dataset.teacherSelect;editing='';paint(false)}
  if(b.dataset.teacherEdit){editing=b.dataset.teacherEdit;paint(false);root()?.querySelector('.teacher-write')?.scrollIntoView({block:'nearest'})}
  if(b.hasAttribute('data-teacher-new-observation')){editing='';paint(false)}
  if(b.hasAttribute('data-teacher-discard')){const key=b.closest('form').dataset.key;drafts.delete(key);if(conflict?.key===key)conflict=null;paint(false)}
 }
 function input(){targetFields();remember()}
 function leave(){remember();if(ctx?.root){ctx.root.removeEventListener('submit',submit);ctx.root.removeEventListener('click',click);ctx.root.removeEventListener('input',input);ctx.root.removeEventListener('change',input)}ctx=null;sequence++}
 function mount(options){leave();ctx=options;if(options.teacherId&&!busy&&!pending){selected=options.teacherId;editing=''}for(const [event,handler] of [['submit',submit],['click',click],['input',input],['change',input]])ctx.root.addEventListener(event,handler);paint(false);if(!busy&&!pending)read()}
 window.FamilyTeachers={mount,leave};
})();
