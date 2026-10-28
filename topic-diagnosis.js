// 原错题卡片里的“知识点诊断”面板：上游cn-math-taxonomy的DiagEngine原样在浏览器运行
// （buildGraph/createSession/replay/nextItem/judgeQuestion/applyAnswer/summarize），服务端逐题幂等保存、
// 新题再试交DeepTutor原LearningService登记/判定。上游“掌握/推断掌握”只当本轮线索，不写成掌握。
(function(root,factory){const api=factory();if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.FamilyTopicDiagnosis=api})(typeof self!=='undefined'?self:this,function(){
 'use strict';
 const STATUS={mastered_direct:'本轮连续答对（线索，不等于掌握）',mastered_inferred:'未直接测（图谱推断）',shaky:'有对有错，不稳（线索）',weak:'两次未答对（线索）',unconfirmed:'答错一题后题量用完（未确认）',unknown:'未测'};
 const OUTCOME={independent_correct:'独立做对新题（两个判题器一致）· 已记为原错题的“复测”',independent_wrong:'独立再试新题未做对（两个判题器一致）· 已记为原错题的“复测”',parent_check:'两个判题器结果不一致或需要人工判断：请家长看原答核对，这次没有写复测',not_new:'这题本次诊断出现过（新题已用完），不算独立再试',not_independent:'这题有帮助记录，不算独立再试'};
 const VERDICT={correct:'判对',wrong:'判错',manual:'待家长核对',skip:'跳过/不会（上游计为未答对）'};
 // 由服务端已保存的逐题事实重建上游会话；题号与保存的不一致说明知识包或引擎变了，不继续出题。
 function restore(E,graph,diag){const answers=diag.items.map(i=>({id:i.topic_id,result:i.engine_result,text:i.answer}));const s=E.replay(graph,[diag.topic_id],answers,diag.opts);const bad=s.answers.some((a,k)=>a.qid!==diag.items[k].qid);return bad?null:s}
 function judge(E,q,kind,text){if(kind!=='answer')return {verdict:'skip',engine:'skip'};const v=E.judgeQuestion(q,text).verdict;return {verdict:v,engine:v==='manual'?'skip':v}}
 function seenQids(diag){return new Set(diag.items.map(i=>i.qid).concat(diag.retries.map(r=>r.qid)))}
 // 新题：上游avoid只是“优先避开”，用尽会退回见过的题，所以这里再按本会话已见题号把关。
 function retryItem(E,graph,diag){const seen=seenQids(diag);const s=E.createSession(graph,[diag.topic_id],{limit:1,seed:'retry-'+diag.id+'-'+diag.retries.length,avoid:[...seen]});const it=E.nextItem(graph,s);return it&&!seen.has(it.question.id)?it:null}
 function summaryLines(graph,session,E){const sum=E.summarize(graph,session),unc=new Set(sum.unconfirmed);return session.order.filter(id=>session.status[id]||session.attempts[id]).map(id=>{const st=session.status[id];const key=!st?'unknown':st.s==='mastered'?'mastered_'+st.src:st.s==='weak'&&unc.has(id)?'unconfirmed':st.s;return {id,name:graph.byId[id]?.name||id,label:STATUS[key]||STATUS.unknown,asked:(session.attempts[id]||[]).length}})}
 const logic={STATUS,OUTCOME,VERDICT,restore,judge,seenQids,retryItem,summaryLines};
 if(typeof document==='undefined')return logic;

 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
 const token=()=>typeof data!=='undefined'&&data?.token||'';
 const key=()=>(crypto.randomUUID?.()||Math.random().toString(36).slice(2)+Date.now().toString(36)).replace(/[^A-Za-z0-9_-]/g,'').padEnd(20,'0');
 const panels={};let enginePromise=null;
 function engine(){return enginePromise??=new Promise((ok,no)=>{if(window.DiagEngine)return ok(window.DiagEngine);const s=document.createElement('script');s.src='/api/topic/engine.js';s.onload=()=>window.DiagEngine?ok(window.DiagEngine):no(Error('诊断引擎没有加载'));s.onerror=()=>{enginePromise=null;no(Error('诊断引擎没有加载：知识包可能未安装'))};document.head.appendChild(s)})}
 async function post(path,body){const r=await fetch(path,{method:'POST',signal:AbortSignal.timeout(60000),headers:{'Content-Type':'application/json','X-Family-Token':token()},body:JSON.stringify(body)});const v=await r.json().catch(()=>({}));if(!r.ok){const e=Error(v.error||'保存未成功');e.status=r.status;e.code=v.code;throw e}return v}
 function slot(r,childId){return childId?`<div class="topic-diagnosis" data-topic-diagnosis="${esc(r.id)}" data-topic-child="${esc(childId)}"><button type="button" data-topic-open>知识点诊断 · 找点、做几题、看说明、再试新题</button></div>`:''}
 async function open(box){const p=panels[box.dataset.topicDiagnosis]??={child_id:box.dataset.topicChild,record_id:Number(box.dataset.topicDiagnosis),pending:null,search:null,current:null,message:''};p.box=box;await load(p)}
 async function load(p){try{p.state=await post('/api/topic/state',{child_id:p.child_id,record_id:p.record_id});p.E=p.state.graph?await engine():null;p.graph=p.E?p.E.buildGraph(p.state.graph.topics,p.state.graph.dependencies,p.state.graph.questions):null}catch(e){p.message=e.message}draw(p)}
 // 失败或丢回执：保留同一请求体，重试时原样再发；服务端按序号/提交标识去重。
 async function send(p,path,body,done){p.pending={path,body,done};p.message='正在保存…';draw(p);try{const v=await post(path,body);p.pending=null;p.state=v;p.message=done(v)||'';if(v.graph&&!p.graph){p.E=await engine();p.graph=p.E.buildGraph(v.graph.topics,v.graph.dependencies,v.graph.questions)}}catch(e){if(e.status&&e.status<500&&e.code!=='deeptutor_unavailable')p.pending=null;p.message=e.message+(p.pending?'。点“重试保存”会原样再发，不会重复保存':'')}draw(p)}
 function linkHTML(p){const st=p.state,current=st.links.filter(l=>l.basis==='current').at(-1),old=st.links.some(l=>l.basis==='basis_changed');
  const topic=current?.topic_id&&st.topics?.[current.topic_id];
  let h=old?'<p class="small" data-topic-stale>原错题更正过：之前的知识点和诊断依据已失效，请按更正后的题重新确认。</p>':'';
  if(current&&current.state==='confirmed'&&topic)return h+`<p data-topic-linked>知识点：<b>${esc(topic.name)}</b> <span class="small muted">${esc(topic.chapter||'')} · ${esc(current.topic_id)}</span></p>`;
  if(current&&['unclear','no_match'].includes(current.state))h+=`<p class="small">已记为“${current.state==='no_match'?'知识包里没有匹配':'暂时说不清'}”：请回原题和原材料核对；也可以再查一次。</p>`;
  const s=p.search;h+=`<form data-topic-search><label>按知识点名称或册章查找（数学）<input name="q" value="${esc(s?.query||'')}" placeholder="如：有理数的加法法则 / 七上 第二章"></label> <button>查找</button></form>`;
  if(s)h+=s.status==='unique'||s.status==='ambiguous'?`<ul class="word-status">${s.candidates.map(c=>`<li>${esc(c.name)} <span class="small muted">${esc(c.chapter||'')}</span> <button type="button" data-topic-confirm="${esc(c.id)}">就是这个</button></li>`).join('')}</ul>${s.total>s.candidates.length?`<p class="small">共 ${esc(s.total)} 个，请加上册章缩小范围。</p>`:''}<button type="button" data-topic-mark="no_match">都不对，回原题核对</button>`:`<p class="small" data-topic-none>${esc(s.message||(s.status==='unclear'?'请输入知识点名称或册章。':'知识包里没有匹配的数学知识点：请回原题和原材料核对。'))}</p>${s.status==='none'?'<button type="button" data-topic-mark="no_match">记为没有匹配</button> ':''}<button type="button" data-topic-mark="unclear">暂时说不清</button>`;
  return h}
 function diagHTML(p){const st=p.state,d=st.diagnoses[0],linked=st.links.filter(l=>l.basis==='current').at(-1);
  const startBtn=linked?.state==='confirmed'?`<button type="button" data-topic-start="${esc(linked.topic_id)}">${d?'按这个知识点重新诊断':'开始诊断（最多8题，可随时暂停）'}</button>`:'';
  if(!d||d.basis!=='current'||!p.graph)return startBtn?`<div class="toolbar">${startBtn}</div>`:'';
  const s=restore(p.E,p.graph,d);if(!s)return '<p class="error">保存的作答与当前知识包版本对不上，原作答保留；请联系家长核对知识包版本。</p>';
  const lines=summaryLines(p.graph,s,p.E),item=p.current?.diag===d.id?p.current.item:p.E.nextItem(p.graph,s);p.current={diag:d.id,item,session:s};
  let h=`<p class="small muted">已做 ${d.items.length}/${d.opts.limit} 题${d.state==='paused'?' · 已暂停，随时可继续':''}</p>`;
  h+=d.items.map(i=>{const q=p.E.questionById(p.graph,i.qid);const helped=i.help?` · 看过${i.help.includes('explanation')?'说明':''}${i.help.includes('guided')?'引导':''}`:'';return `<p class="small" data-topic-item="${i.seq}">第${i.seq}题 ${esc(q?.prompt||i.qid)} → 原答“${esc(i.answer||'—')}” · ${VERDICT[i.verdict]}${helped}${i.verdict!=='correct'&&q?.explanation&&!i.help.includes('explanation')?` <button type="button" data-topic-help="${i.seq}">看一小步说明</button>`:''}${i.help.includes('explanation')&&q?.explanation?`<br><span class="source">说明（AI初稿，未经教师审核）：${esc(q.explanation)}</span>`:''}</p>`}).join('');
  if(lines.length)h+=`<ul class="word-status" data-topic-summary>${lines.map(l=>`<li>${esc(l.name)} · ${esc(l.label)}${l.asked?` · 问过${l.asked}题`:''}</li>`).join('')}</ul>`;
  if(item&&d.items.length<d.opts.limit)h+=questionHTML(item.question,'answer')+`<div class="toolbar"><button type="button" data-topic-pause>先暂停</button></div>`;
  else h+='<p class="small">这轮诊断结束。上面的状态只是本轮线索，不写成掌握；先看答错题的说明，再独立做一道新题。</p>';
  if(d.items.length){const r=retryItem(p.E,p.graph,d);h+=d.retries.map(x=>`<p class="small" data-topic-retry-result="${esc(x.outcome)}">新题再试 → 原答“${esc(x.answer)}” · ${esc(OUTCOME[x.outcome]||x.outcome)}${x.outcome==='parent_check'?`（上游：${VERDICT[x.taxonomy_verdict]}；DeepTutor：${x.deeptutor.is_correct==null?'未判定':x.deeptutor.is_correct?'对':'错'}）`:''}</p>`).join('');
   h+=r?`<p><b>独立再试一道新题</b> <span class="small muted">作答前不看说明；提交后才判定</span></p>${questionHTML(r.question,'retry')}`:'<p class="small" data-topic-no-new>这个知识点已没有本次没见过的新题；不标为独立复测。</p>';
   if(!st.deeptutor?.available)h+=`<p class="small muted">${esc(st.deeptutor?.message||'')}</p>`}
  return h+(startBtn&&d.items.length?`<div class="toolbar">${startBtn}</div>`:'')}
 function questionHTML(q,mode){const choices=q.type==='choice'&&q.choices?.length?q.choices.map(c=>`<label><input type="radio" name="a" value="${esc(c.key)}"> ${esc(c.key)}. ${esc(c.text)}</label>`).join(' '):'<input name="a" autocomplete="off" placeholder="写答案">';return `<form data-topic-form="${mode}" data-qid="${esc(q.id)}"><p>${esc(q.prompt)}</p>${choices} <button>提交</button>${mode==='answer'?' <button type="button" data-topic-kind="skip">跳过</button> <button type="button" data-topic-kind="unknown">不会</button>':''}</form>`}
 function draw(p){const st=p.state;let h='<h4>知识点诊断 <span class="small muted">数学 · 知识包e0f931b · AI初稿，未经教师审核</span></h4>';
  if(st&&!st.pack?.installed)h+=`<p class="small" data-topic-pack-missing>${esc(st.pack?.message||'知识包未安装')}；原错题、短引导和每日待办照常可用。</p>`;
  else if(st)h+=linkHTML(p)+diagHTML(p);
  h+=`<p class="small" data-topic-status>${esc(p.message)}</p>${p.pending?'<button type="button" data-topic-resend>重试保存</button>':''}`;
  p.box.innerHTML=h;bind(p)}
 function bind(p){const b=p.box,base={child_id:p.child_id,record_id:p.record_id},d=p.state?.diagnoses?.[0];
  b.querySelector('[data-topic-resend]')?.addEventListener('click',()=>send(p,p.pending.path,p.pending.body,p.pending.done));
  b.querySelector('[data-topic-search]')?.addEventListener('submit',async e=>{e.preventDefault();const query=e.target.elements.q.value.trim();try{p.search={query,...await post('/api/topic/search',{...base,query})};p.message=''}catch(x){p.message=x.message}draw(p)});
  b.querySelectorAll('[data-topic-confirm]').forEach(x=>x.onclick=()=>send(p,'/api/topic/link',{...base,topic_id:x.dataset.topicConfirm,state:'confirmed',request_id:key()},()=>{p.search=null;return '知识点已确认；可以开始诊断'}));
  b.querySelectorAll('[data-topic-mark]').forEach(x=>x.onclick=()=>send(p,'/api/topic/link',{...base,state:x.dataset.topicMark,request_id:key()},()=>{p.search=null;return '已记下；请回原题和原材料核对'}));
  b.querySelector('[data-topic-start]')?.addEventListener('click',e=>send(p,'/api/topic/diagnosis/start',{...base,topic_id:e.target.dataset.topicStart,request_id:key()},()=>{p.current=null;load(p)}));
  b.querySelector('[data-topic-pause]')?.addEventListener('click',()=>send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'pause'},()=>'已暂停：保存的作答都在，刷新或下次打开从这里继续'));
  b.querySelectorAll('[data-topic-help]').forEach(x=>x.onclick=()=>send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'help_explanation',seq:Number(x.dataset.topicHelp)},()=>'说明已打开：这题记为“看过说明”'));
  const answer=(kind,text)=>{const it=p.current.item,j=judge(p.E,it.question,kind,text),s=p.E.applyAnswer(p.graph,p.current.session,it.topicId,j.engine,{text});p.current=null;
   send(p,'/api/topic/diagnosis/answer',{...base,diagnosis_id:d.id,seq:d.items.length+1,topic_id:it.topicId,qid:it.question.id,kind,answer:text,verdict:j.verdict,engine_result:j.engine,session:s,summary:p.E.summarize(p.graph,s)},()=>VERDICT[j.verdict])};
  b.querySelector('[data-topic-form="answer"]')?.addEventListener('submit',e=>{e.preventDefault();const t=String(new FormData(e.target).get('a')||'').trim();if(t)answer('answer',t)});
  b.querySelectorAll('[data-topic-kind]').forEach(x=>x.onclick=()=>answer(x.dataset.topicKind,''));
  b.querySelector('[data-topic-form="retry"]')?.addEventListener('submit',e=>{e.preventDefault();const t=String(new FormData(e.target).get('a')||'').trim();if(!t)return;const q=p.E.questionById(p.graph,e.target.dataset.qid);
   send(p,'/api/topic/diagnosis/retry',{...base,diagnosis_id:d.id,qid:q.id,answer:t,verdict:judge(p.E,q,'answer',t).verdict,request_id:key()},v=>OUTCOME[v.diagnoses?.[0]?.retries?.at(-1)?.outcome]||'')})}
 document.addEventListener('click',e=>{const b=e.target.closest('[data-topic-open]');if(b)open(b.closest('[data-topic-diagnosis]'))});
 return {...logic,slot,open};
});
