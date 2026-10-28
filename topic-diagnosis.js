// 原错题卡片里的“知识点诊断”面板：上游cn-math-taxonomy的DiagEngine原样在浏览器运行
// （buildGraph/createSession/replay/nextItem/judgeQuestion/applyAnswer/summarize），服务端逐题幂等保存、
// 新题再试交DeepTutor原LearningService登记/判定。上游“掌握/推断掌握”只当本轮线索，不写成掌握。
// 面板可能放在作业反馈对话框的<form>里，所以这里不用<form>：输入框form属性指向不存在的表单，回车不提交外层。
(function(root,factory){const api=factory();if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.FamilyTopicDiagnosis=api})(typeof self!=='undefined'?self:this,function(){
 'use strict';
 const STATUS={mastered_direct:'本轮连续答对（线索，不等于掌握）',mastered_inferred:'未直接测（图谱推断）',shaky:'有对有错，不稳（线索）',weak:'两次未答对（线索）',unconfirmed:'答错一题后题量用完（未确认）',unknown:'未测'};
 const OUTCOME={independent_correct:'独立做对新题（两项检查一致）· 已记为原错题的“复测”',independent_wrong:'独立再试新题未做对（两项检查一致）· 已记为原错题的“复测”',parent_check:'需核对：两项检查结果不一致或无法自动判断，请家长看原答；这次没有写复测',not_new:'这题此前出现过、答过或看过说明，不算独立再试',not_independent:'这题有帮助记录，不算独立再试'};
 const VERDICT={correct:'判对',wrong:'判错',manual:'待家长核对',skip:'跳过/不会（上游计为未答对）'};
 const ANSWER_MAX=500; // 与服务端family_taxonomy.ANSWER_MAX一致；只防误输，超长以服务端400为准
 // 由服务端已保存的逐题事实重建上游会话；题号与保存的不一致说明知识包或引擎变了，不继续出题。
 function restore(E,graph,diag){const answers=diag.items.map(i=>({id:i.topic_id,result:i.engine_result,text:i.answer}));const s=E.replay(graph,[diag.topic_id],answers,diag.opts);const bad=s.answers.some((a,k)=>a.qid!==diag.items[k].qid);return bad?null:s}
 function judge(E,q,kind,text){if(kind!=='answer')return {verdict:'skip',engine:'skip'};const v=E.judgeQuestion(q,text).verdict;return {verdict:v,engine:v==='manual'?'skip':v}}
 // 同孩历次诊断/再试的全部痕迹（服务端state.seen_qids：出示、作答、看说明、再试），不只看当前这次诊断。
 function seenQids(st){return new Set(st&&st.seen_qids||[])}
 // 新题：上游avoid只是“优先避开”，抽到旧题不代表新题用尽。所以先从真实原题集滤掉所有见过的题号，再交原
 // buildGraph/createSession/nextItem选题。过滤后题库变小，上游needConfirm=min(3,剩余题数)随之变化；
 // 再试会话limit=1，单题对错只记这一次尝试，不推断掌握。剩下没有未见题就停在“没有新题”，不换seed碰运气。
 function retryItem(E,raw,full,diag,seen){const qs=raw.questions.filter(q=>!seen.has(q.id));const g=E.buildGraph(raw.topics,raw.dependencies,qs);const s=E.createSession(g,[diag.topic_id],{limit:1,seed:'retry-'+diag.id});const it=E.nextItem(g,s);const orig=it&&E.questionById(full,it.question.id);return it&&!seen.has(it.question.id)&&orig&&orig.prompt===it.question.prompt?it:null}
 // 长推断祖先不堆屏幕：直接测过的点逐条列出，图谱推断的先修点合成一行（全部原样保存在服务端summary里）。
 function summaryLines(graph,session,E){const sum=E.summarize(graph,session),unc=new Set(sum.unconfirmed);return session.order.filter(id=>session.status[id]||session.attempts[id]).map(id=>{const st=session.status[id];const key=!st?'unknown':st.s==='mastered'?'mastered_'+st.src:st.s==='weak'&&unc.has(id)?'unconfirmed':st.s;return {id,name:graph.byId[id]?.name||id,label:STATUS[key]||STATUS.unknown,asked:(session.attempts[id]||[]).length,inferred:key==='mastered_inferred'}})}
 const logic={STATUS,OUTCOME,VERDICT,ANSWER_MAX,restore,judge,seenQids,retryItem,summaryLines};
 if(typeof document==='undefined')return logic;

 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
 const key=()=>(crypto.randomUUID?.()||Math.random().toString(36).slice(2)+Date.now().toString(36)).replace(/[^A-Za-z0-9_-]/g,'').padEnd(20,'0');
 const panels={};let enginePromise=null;
 function engine(){return enginePromise??=new Promise((ok,no)=>{if(window.DiagEngine)return ok(window.DiagEngine);const s=document.createElement('script');s.src=endpoint('/api/topic/engine.js');s.onload=()=>window.DiagEngine?ok(window.DiagEngine):no(Error('诊断引擎没有加载'));s.onerror=()=>{enginePromise=null;s.remove();no(Error('诊断引擎没有加载：知识包可能未安装'))};document.head.appendChild(s)})}
 // 走本项目apiFetch：同一局域网基路径、当前令牌与过期令牌恢复；令牌不进全局变量或URL。
 async function post(path,body){const r=await apiFetch(path,{method:'POST',signal:AbortSignal.timeout(60000),headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)});const v=await r.json().catch(()=>({}));if(!r.ok){const e=Error(v.error||'保存未成功');e.status=r.status;e.code=v.code;throw e}return v}
 function slot(r,childId){return childId?`<div class="topic-diagnosis" data-topic-diagnosis="${esc(r.id)}" data-topic-child="${esc(childId)}"><button type="button" data-topic-open>知识点诊断</button></div>`:''}
 // 面板按“孩子:原错题”分开保存，切换孩子不串状态。
 async function open(box){const id=box.dataset.topicChild+':'+box.dataset.topicDiagnosis;const p=panels[id]??={child_id:box.dataset.topicChild,record_id:Number(box.dataset.topicDiagnosis),pending:null,search:null,message:'',draft:{},keys:{}};p.box=box;p.message=p.pending?p.message:'正在读取…';draw(p);await load(p);draw(p)}
 async function apply(p,v){p.state=v;if(!v.graph){p.graph=null;p.raw=null;p.target='';return}if(p.target!==v.graph.target||!p.graph){p.E=await engine();p.raw=v.graph;p.graph=p.E.buildGraph(v.graph.topics,v.graph.dependencies,v.graph.questions);p.target=v.graph.target}}
 async function load(p){try{await apply(p,await post('/api/topic/state',{child_id:p.child_id,record_id:p.record_id}));if(p.message==='正在读取…')p.message=''}catch(e){p.message=e.message}}
 // 每个写操作都回完整状态；万一缺字段就整体重读，不拿半截回执替换面板。失败或丢回执：保留同一请求体，
 // “重试保存”原样再发（服务端按编号与内容去重）；409冲突重读已保存内容，输入框里的原答保留。
 async function send(p,path,body,done){if(p.busy)return;p.busy=true;p.pending={path,body,done};p.message='正在保存…';draw(p);
  try{const v=await post(path,body);p.pending=null;if(v&&v.pack&&Array.isArray(v.diagnoses)&&Array.isArray(v.links))await apply(p,v);else await load(p);p.message=done(v)||''}
  catch(e){if(e.status&&e.status<500&&e.code!=='deeptutor_unavailable')p.pending=null;const msg=e.message+(p.pending?'。点“重试保存”会原样再发，不会重复保存':'');if(e.status===409)await load(p);p.message=msg}
  p.busy=false;draw(p)}
 const field=(p,k,ph,max)=>`<input form="topic-diagnosis-none" data-topic-input="${esc(k)}" autocomplete="off"${max?` maxlength="${max}"`:''} placeholder="${esc(ph)}" value="${esc(p.draft[k]||'')}">`;
 function linkHTML(p,st,current){const s=p.search;let h='';
  if(current&&['unclear','no_match'].includes(current.state))h+=`<p class="small">已记为“${current.state==='no_match'?'知识包里没有匹配':'暂时说不清'}”：请回原题和原材料核对；也可以再查一次。</p>`;
  h+=`<div class="topic-row">${field(p,'search','知识点名称或册章，如：有理数的加法法则')}<button type="button" data-topic-search>查找</button></div>`;
  if(s)h+=s.status==='unique'||s.status==='ambiguous'?`<ul class="topic-list">${s.candidates.map(c=>`<li>${esc(c.name)} <span class="small muted">${esc(c.chapter||'')}</span> <button type="button" data-topic-confirm="${esc(c.id)}">就是这个</button></li>`).join('')}</ul>${s.total>s.candidates.length?`<p class="small">共 ${esc(s.total)} 个，请加上册章缩小范围。</p>`:''}<button type="button" data-topic-mark="no_match">都不对，回原题核对</button>`:`<p class="small" data-topic-none>${esc(s.message||(s.status==='unclear'?'请输入知识点名称或册章。':'知识包里没有匹配的数学知识点：请回原题和原材料核对。'))}</p>${s.status==='none'?'<button type="button" data-topic-mark="no_match">记为没有匹配</button> ':''}<button type="button" data-topic-mark="unclear">暂时说不清</button>`;
  return h}
 // 已答只留一行：原答与判定；答错且有上游说明的，在“当前操作”空出来时给一小步说明。
 function itemLine(p,i,helpable){const q=p.E.questionById(p.graph,i.qid),seen=i.help.includes('explanation');return `<li data-topic-item="${i.seq}">第${i.seq}题 原答“${esc(i.answer||'—')}” · ${VERDICT[i.verdict]}${seen?' · 看过说明':''}${helpable&&i.verdict!=='correct'&&q?.explanation&&!seen?` <button type="button" data-topic-help="${i.seq}">看一小步说明</button>`:''}${seen&&q?.explanation?`<span class="topic-explain">说明（AI初稿，未经教师审核）：${esc(q.explanation)}</span>`:''}</li>`}
 function questionHTML(p,q,mode){const k=mode+':'+q.id,name='td-'+p.child_id+'-'+p.record_id+'-'+mode;const input=q.type==='choice'&&q.choices?.length?`<div class="topic-choices" role="radiogroup">${q.choices.map(c=>`<label class="topic-choice"><input type="radio" form="topic-diagnosis-none" name="${esc(name)}" data-topic-input="${esc(k)}" value="${esc(c.key)}"${p.draft[k]===c.key?' checked':''}><span>${esc(c.key)}. ${esc(c.text)}</span></label>`).join('')}</div>`:field(p,k,'写答案',ANSWER_MAX);
  return `<div class="topic-question" data-topic-form="${mode}" data-qid="${esc(q.id)}"><p>${esc(q.prompt)}</p>${input}<div class="topic-actions"><button type="button" class="primary" data-topic-submit>提交</button>${mode==='answer'?'<button type="button" data-topic-kind="skip">跳过</button><button type="button" data-topic-kind="unknown">不会</button><button type="button" data-topic-pause>先暂停</button>':''}</div></div>`}
 function diagHTML(p,st,linked){const d=st.diagnoses.find(x=>x.basis==='current');p.view=null;
  const startBtn=`<button type="button" data-topic-start="${esc(linked.topic_id)}">${d?'按这个知识点重新诊断':'开始诊断（最多8题，可随时暂停）'}</button>`;
  if(!d||!p.graph)return `<div class="topic-actions">${startBtn}</div>`;
  const s=restore(p.E,p.graph,d);if(!s)return '<p class="error">保存的作答与当前知识包版本对不上，原作答保留；请联系家长核对知识包版本。</p>';
  const item=d.items.length<d.opts.limit?p.E.nextItem(p.graph,s):null,offer=d.retry_offer,asking=item&&(d.state!=='paused'||p.resume);
  let h=`<p class="small muted">已做 ${d.items.length}/${d.opts.limit} 题${d.state==='paused'&&!p.resume?' · 已暂停，随时可继续':''}</p>`;
  const idle=!(offer?.fresh)&&!asking;
  if(d.items.length)h+=`<ol class="topic-done">${d.items.map(i=>itemLine(p,i,idle)).join('')}</ol>`;
  h+=d.retries.map(x=>`<p class="small" data-topic-retry-result="${esc(x.outcome)}">新题再试 原答“${esc(x.answer)}” · ${esc(OUTCOME[x.outcome]||x.outcome)}${x.outcome==='parent_check'?`（题库核对：${VERDICT[x.taxonomy_verdict]}；复核结果：${x.deeptutor.is_correct==null?'未判定':x.deeptutor.is_correct?'对':'错'}）`:''}</p>`).join('');
  // 当前操作只有一个：新题再试 > 诊断下一题 > 小结与下一步。题目先登记“已出示”才显示。
  if(offer?.fresh){p.view={mode:'retry',qid:offer.qid,diag:d.id};const q=p.E.questionById(p.graph,offer.qid);return h+(q?`<p><b>独立再试一道新题</b> <span class="small muted">先别看说明；提交后才判定</span></p>${questionHTML(p,q,'retry')}`:'<p class="error">新题不在当前知识包里，请刷新。</p>')}
  if(offer&&!offer.fresh)h+='<p class="small">上次出示的新题后来又在别处出现过，不再算独立；可以换一道没见过的。</p>';
  if(asking){p.view={mode:'answer',qid:item.question.id,diag:d.id,item,session:s};
   if(!d.shown.includes(item.question.id)){const k=d.id+':'+item.question.id;if(p.shownTried!==k){p.autoShow=k;return h+'<p class="small" data-topic-showing>正在出题…</p>'}return h+'<div class="topic-actions"><button type="button" class="primary" data-topic-show>出下一题</button></div>'}
   return h+`<p class="small muted">第${d.items.length+1}题 · ${esc(p.graph.byId[item.topicId]?.name||item.topicId)}</p>${questionHTML(p,item.question,'answer')}`}
  const lines=summaryLines(p.graph,s,p.E),tested=lines.filter(l=>!l.inferred),inferred=lines.filter(l=>l.inferred);
  if(tested.length)h+=`<ul class="topic-list" data-topic-summary>${tested.map(l=>`<li>${esc(l.name)} · ${esc(l.label)}${l.asked?` · 问过${l.asked}题`:''}</li>`).join('')}</ul>`;
  if(inferred.length)h+=`<p class="small muted" data-topic-inferred>另有${inferred.length}个先修点未直接测，只是图谱推断（不算掌握）：${esc(inferred.slice(0,3).map(l=>l.name).join('、'))}${inferred.length>3?'等':''}</p>`;
  h+=item?'':'<p class="small">这轮诊断结束。上面只是本轮线索，不写成掌握；先看答错题的说明，再独立做一道新题。</p>';
  if(p.noNew===d.id)h+='<p class="small" data-topic-no-new>这个知识点已没有这孩子历次都没见过的新题；不标为独立复测。</p>';
  if(!st.deeptutor?.available&&d.items.length)h+=`<p class="small muted">${esc(st.deeptutor?.message||'')}</p>`;
  return h+`<div class="topic-actions">${item?'<button type="button" class="primary" data-topic-resume>继续诊断</button>':''}${d.items.length&&p.noNew!==d.id?`<button type="button"${item?'':' class="primary"'} data-topic-retry>独立再试一道新题</button>`:''}${startBtn}</div>`}
 function staleHTML(st){const old=st.diagnoses.filter(d=>d.basis!=='current');if(!old.length&&!st.links.some(l=>l.basis==='basis_changed'))return '';
  const n=old.reduce((k,d)=>k+d.items.length+d.retries.length,0),pending=old.some(d=>d.void?.state==='pending'),voided=old.some(d=>d.void?.state==='voided');
  return `<p class="small" data-topic-stale>原错题更正过：之前的知识点和诊断依据已失效${n?`，${n}条作答作为历史保留，不当作当前结果`:''}${voided?'；DeepTutor里的旧作答已作废':''}${pending?'；DeepTutor旧作答待作废（判定组件不可用，下次打开再试）':''}。请按更正后的题重新确认。</p>`}
 function draw(p){const st=p.state;let h='<p class="topic-head"><b>知识点诊断</b> <span class="small muted">数学 · 知识包e0f931b · AI初稿，未经教师审核</span></p>';
  if(st&&!st.pack?.installed)h+=`<p class="small" data-topic-pack-missing>${esc(st.pack?.message||'知识包未安装')}；原错题、短引导和每日待办照常可用。</p>`;
  else if(st){const current=st.links.filter(l=>l.basis==='current').at(-1),topic=current?.state==='confirmed'&&st.topics?.[current.topic_id];h+=staleHTML(st);
   if(topic)h+=`<p class="small" data-topic-linked>知识点：<b>${esc(topic.name)}</b> <span class="muted">${esc(topic.chapter||'')} · ${esc(current.topic_id)}</span></p>`+diagHTML(p,st,current);else h+=linkHTML(p,st,current)}
  h+=`<p class="small" data-topic-status role="status">${esc(p.message)}</p>${p.pending&&!p.busy?'<button type="button" data-topic-resend>重试保存</button>':''}`;
  p.box.innerHTML=h;p.box.classList.toggle('is-busy',!!p.busy);bind(p);
  if(p.autoShow&&!p.busy&&!p.pending&&p.view?.mode==='answer'){const [did,qid]=[p.view.diag,p.view.qid];p.shownTried=p.autoShow;p.autoShow=null;send(p,'/api/topic/diagnosis/mark',{child_id:p.child_id,record_id:p.record_id,diagnosis_id:did,action:'shown',mode:'diagnosis',qid},()=>'')}}
 function bind(p){const b=p.box,base={child_id:p.child_id,record_id:p.record_id},v=p.view;
  b.querySelectorAll('[data-topic-input]').forEach(x=>{const k=x.dataset.topicInput;x.addEventListener(x.type==='radio'?'change':'input',()=>{p.draft[k]=x.value});x.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();(x.closest('[data-topic-form]')?.querySelector('[data-topic-submit]')||b.querySelector('[data-topic-search]'))?.click()}})});
  if(p.busy){b.querySelectorAll('button,input').forEach(x=>x.disabled=true);return}
  b.querySelector('[data-topic-resend]')?.addEventListener('click',()=>send(p,p.pending.path,p.pending.body,p.pending.done));
  b.querySelector('[data-topic-search]')?.addEventListener('click',async()=>{const query=String(p.draft.search||'').trim();if(!query)return;try{p.search={query,...await post('/api/topic/search',{...base,query})};p.message=''}catch(x){p.message=x.message}draw(p)});
  b.querySelectorAll('[data-topic-confirm]').forEach(x=>x.onclick=()=>send(p,'/api/topic/link',{...base,topic_id:x.dataset.topicConfirm,state:'confirmed',request_id:key()},()=>{p.search=null;return '知识点已确认；可以开始诊断'}));
  b.querySelectorAll('[data-topic-mark]').forEach(x=>x.onclick=()=>send(p,'/api/topic/link',{...base,state:x.dataset.topicMark,request_id:key()},()=>{p.search=null;return '已记下；请回原题和原材料核对'}));
  b.querySelector('[data-topic-start]')?.addEventListener('click',e=>send(p,'/api/topic/diagnosis/start',{...base,topic_id:e.target.dataset.topicStart,request_id:key()},()=>{p.resume=false;p.noNew=null;return ''}));
  b.querySelector('[data-topic-resume]')?.addEventListener('click',()=>{p.resume=true;draw(p)});
  b.querySelector('[data-topic-show]')?.addEventListener('click',()=>{if(v)send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:v.diag,action:'shown',mode:'diagnosis',qid:v.qid},()=>'')});
  const d=p.state?.diagnoses?.find(x=>x.basis==='current');if(!d)return;
  b.querySelector('[data-topic-pause]')?.addEventListener('click',()=>send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'pause'},()=>{p.resume=false;return '已暂停：保存的作答都在，下次打开从这里继续'}));
  b.querySelectorAll('[data-topic-help]').forEach(x=>x.onclick=()=>send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'help_explanation',seq:Number(x.dataset.topicHelp)},()=>'说明已打开：这题记为“看过说明”'));
  b.querySelector('[data-topic-retry]')?.addEventListener('click',()=>{const it=retryItem(p.E,p.raw,p.graph,d,seenQids(p.state));if(!it){p.noNew=d.id;draw(p);return}
   send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'shown',mode:'retry',qid:it.question.id},()=>'')});
  const answer=(kind,text)=>{const it=v.item,j=judge(p.E,it.question,kind,text),s=p.E.applyAnswer(p.graph,v.session,it.topicId,j.engine,{text});
   send(p,'/api/topic/diagnosis/answer',{...base,diagnosis_id:d.id,seq:d.items.length+1,topic_id:it.topicId,qid:it.question.id,kind,answer:text,verdict:j.verdict,engine_result:j.engine,session:s,summary:p.E.summarize(p.graph,s)},()=>{delete p.draft['answer:'+it.question.id];return VERDICT[j.verdict]})};
  b.querySelectorAll('[data-topic-kind]').forEach(x=>x.onclick=()=>answer(x.dataset.topicKind,''));
  b.querySelector('[data-topic-submit]')?.addEventListener('click',()=>{if(!v)return;const k=v.mode+':'+v.qid,t=String(p.draft[k]||'').trim();if(!t){p.message='请先写答案或选一项';draw(p);return}
   if(v.mode==='answer')return answer('answer',t);
   const q=p.E.questionById(p.graph,v.qid),rid=p.keys[d.id+':'+v.qid]??=key();
   send(p,'/api/topic/diagnosis/retry',{...base,diagnosis_id:d.id,qid:q.id,answer:t,verdict:judge(p.E,q,'answer',t).verdict,request_id:rid},x=>{delete p.draft[k];return OUTCOME[x.diagnoses?.find(y=>y.id===d.id)?.retries?.at(-1)?.outcome]||''})})}
 document.addEventListener('click',e=>{const b=e.target.closest('[data-topic-open]');if(b)open(b.closest('[data-topic-diagnosis]'))});
 return {...logic,slot,open};
});
