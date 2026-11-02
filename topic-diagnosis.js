// 原错题卡片里的“知识点诊断”面板：上游cn-math-taxonomy的DiagEngine原样在浏览器运行
// （buildGraph/createSession/replay/nextItem/judgeQuestion/applyAnswer/summarize），服务端逐题幂等保存、
// 新题再试交DeepTutor原LearningService登记/判定。上游“掌握/推断掌握”只当本轮线索，不写成掌握。
// 面板可能放在作业反馈对话框的<form>里，所以这里不用<form>：输入框form属性指向不存在的表单，回车不提交外层。
(function(root,factory){const api=factory();if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.FamilyTopicDiagnosis=api})(typeof self!=='undefined'?self:this,function(){
 'use strict';
 const STATUS={mastered_direct:'本轮连续答对（线索，不等于掌握）',mastered_inferred:'未直接测（图谱推断）',shaky:'有对有错，不稳（线索）',weak:'两次未答对（线索）',unconfirmed:'答错一题后题量用完（未确认）',unknown:'还没有结论'};
 const OUTCOME={independent_correct:'独立做对新题（两项检查一致）· 已记为原错题的“复测”',independent_wrong:'独立再试新题未做对（两项检查一致）· 已记为原错题的“复测”',parent_check:'需核对：两项检查结果不一致或无法自动判断，请家长看原答；这次没有写复测',not_new:'这题此前出现过、答过或看过说明，不算独立再试',not_independent:'这题有帮助记录，不算独立再试'};
 const VERDICT={correct:'判对',wrong:'判错',manual:'待家长核对',skip:'跳过/不会（上游计为未答对）'};
 const ANSWER_MAX=500; // 与服务端family_taxonomy.ANSWER_MAX一致；只防误输，超长以服务端400为准
 // 由服务端已保存的逐题事实重建上游会话；题号与保存的不一致说明知识包或引擎变了，不继续出题。
 // 有待核题（服务端replay_result=skip）时只按“未答对”重放，之后的选题与本轮线索不把它当对或错；重放出的题号与已问的题对不上（之后的题是按它当时的判定续出的）
// 就返回null，绝不退回按原判定重放——面板据此保留历史、标明待核并只给“重新诊断这个知识点”。没有待核题的会话照原判定重放，与原来一样。
function restore(E,graph,diag){const run=held=>{const answers=diag.items.map(i=>({id:i.topic_id,result:held&&i.replay_result||i.engine_result,text:i.answer}));const s=E.replay(graph,[diag.topic_id],answers,diag.opts);return s.answers.some((a,k)=>a.qid!==diag.items[k].qid)?null:s};return run(diag.items.some(i=>i.replay_result))}
 function judge(E,q,kind,text){if(kind!=='answer')return {verdict:'skip',engine:'skip'};const v=E.judgeQuestion(q,text).verdict;return {verdict:v,engine:v==='manual'?'skip':v}}
 // 同孩历次诊断/再试的全部痕迹（服务端state.seen_qids：出示、作答、看说明、再试），不只看当前这次诊断。
 function seenQids(st){return new Set(st&&st.seen_qids||[])}
 // 新题：上游avoid只是“优先避开”，抽到旧题不代表新题用尽。所以先从真实原题集滤掉所有见过的题号，再交原
 // buildGraph/createSession/nextItem选题。过滤后题库变小，上游needConfirm=min(3,剩余题数)随之变化；
 // 再试会话limit=1，单题对错只记这一次尝试，不推断掌握。剩下没有未见题就停在“没有新题”，不换seed碰运气。
 function retryItem(E,raw,full,diag,seen){const qs=raw.questions.filter(q=>!seen.has(q.id));const g=E.buildGraph(raw.topics,raw.dependencies,qs);const s=E.createSession(g,[diag.topic_id],{limit:1,seed:'retry-'+diag.id});const it=E.nextItem(g,s);const orig=it&&E.questionById(full,it.question.id);return it&&!seen.has(it.question.id)&&orig&&orig.prompt===it.question.prompt?it:null}
 // 长推断祖先不堆屏幕：直接测过的点逐条列出，图谱推断的先修点合成一行（全部原样保存在服务端summary里）。
 function summaryLines(graph,session,E){const sum=E.summarize(graph,session),unc=new Set(sum.unconfirmed);return session.order.filter(id=>session.status[id]||session.attempts[id]).map(id=>{const st=session.status[id];const key=!st?'unknown':st.s==='mastered'?'mastered_'+st.src:st.s==='weak'&&unc.has(id)?'unconfirmed':st.s;return {id,name:graph.byId[id]?.name||id,label:STATUS[key]||STATUS.unknown,asked:(session.attempts[id]||[]).length,inferred:key==='mastered_inferred'}})}
 // 家庭复习在日历上的显示标题由原错题标题派生：沿用日历原有的200字（码位）上限，超出时按完整字形截短并以“…”标明；
 // 原错题标题、题面、原答与关联都不动，同一次提交的请求体一经生成就不再变。
 function reviewTitle(title){const full='家庭复习：'+(title||'原错题'),cp=s=>Array.from(s).length;if(cp(full)<=200)return full;
  const parts=typeof Intl!=='undefined'&&Intl.Segmenter?Array.from(new Intl.Segmenter('zh',{granularity:'grapheme'}).segment(full),x=>x.segment):Array.from(full);
  let out='',n=0;for(const p of parts){const k=cp(p);if(n+k>199)break;out+=p;n+=k}return out+'…'}
 const logic={STATUS,OUTCOME,VERDICT,ANSWER_MAX,restore,judge,seenQids,retryItem,summaryLines,reviewTitle};
 if(typeof document==='undefined')return logic;

 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
 const key=()=>(crypto.randomUUID?.()||Math.random().toString(36).slice(2)+Date.now().toString(36)).replace(/[^A-Za-z0-9_-]/g,'').padEnd(20,'0');
 const hex=()=>[...crypto.getRandomValues(new Uint8Array(16))].map(x=>x.toString(16).padStart(2,'0')).join('');
 const REVIEW_STATUS={tentative:'暂定',confirmed:'已安排',completed:'已完成这次复习',cancelled:'已取消'};
 const panels={};let enginePromise=null;
 function engine(){return enginePromise??=new Promise((ok,no)=>{if(window.DiagEngine)return ok(window.DiagEngine);const s=document.createElement('script');s.src=endpoint('/api/topic/engine.js');s.onload=()=>window.DiagEngine?ok(window.DiagEngine):no(Error('诊断引擎没有加载'));s.onerror=()=>{enginePromise=null;s.remove();no(Error('诊断引擎没有加载：知识包可能未安装'))};document.head.appendChild(s)})}
 // 走本项目apiFetch：同一局域网基路径、当前令牌与过期令牌恢复；令牌不进全局变量或URL。
 async function post(path,body){const r=await apiFetch(path,{method:'POST',signal:AbortSignal.timeout(60000),headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(body)});const v=await r.json().catch(()=>({}));if(!r.ok){const e=Error(v.error||'保存未成功');e.status=r.status;e.code=v.code;throw e}return v}
 function slot(r,childId){return childId?`<div class="topic-diagnosis" data-topic-diagnosis="${esc(r.id)}" data-topic-child="${esc(childId)}"><button type="button" data-topic-open>知识点诊断</button></div>`:''}
 // 面板按“孩子:原错题”分开保存，切换孩子不串状态。
 async function open(box){const id=box.dataset.topicChild+':'+box.dataset.topicDiagnosis;const p=panels[id]??={child_id:box.dataset.topicChild,record_id:Number(box.dataset.topicDiagnosis),pending:null,search:null,message:'',draft:{},keys:{}};p.box=box;
  // 每次打开（含同一页面里关掉再开的暖重开）都只读：不沿用上次的显式继续/自动出题状态；回执不明的请求仍在p.pending，可原样重试。
  p.live=null;p.autoShow=null;p.resume=false;p.message=p.pending?p.message:'正在读取…';draw(p);await load(p);draw(p)}
 async function apply(p,v){p.state=v;if(!v.graph){p.graph=null;p.raw=null;p.target='';return}if(p.target!==v.graph.target||!p.graph){p.E=await engine();p.raw=v.graph;p.graph=p.E.buildGraph(v.graph.topics,v.graph.dependencies,v.graph.questions);p.target=v.graph.target}}
 async function load(p){try{await apply(p,await post('/api/topic/state',{child_id:p.child_id,record_id:p.record_id}));if(p.message==='正在读取…')p.message=''}catch(e){p.message=e.message}}
 // 每个写操作都回完整状态；万一缺字段就整体重读，不拿半截回执替换面板。失败或丢回执：保留同一请求体，
 // “重试保存”原样再发（服务端按编号与内容去重）；409冲突重读已保存内容，输入框里的原答保留。
 async function send(p,path,body,done){if(p.busy)return;p.busy=true;p.pending={path,body,done};p.message='正在保存…';draw(p);
  try{const v=await post(path,body);p.pending=null;if(v&&v.pack&&Array.isArray(v.diagnoses)&&Array.isArray(v.links))await apply(p,v);else await load(p);p.message=done(v)||''}
  catch(e){if(e.status&&e.status<500&&e.code!=='deeptutor_unavailable')p.pending=null;const msg=e.message+(p.pending?'。点“重试保存”会原样再发，不会重复保存':'');if(e.status===409)await load(p);p.message=msg}
  p.busy=false;draw(p)}
 const field=(p,k,ph,max)=>`<input form="topic-diagnosis-none" data-topic-input="${esc(k)}" autocomplete="off"${max?` maxlength="${max}"`:''} placeholder="${esc(ph)}" value="${esc(p.draft[k]||'')}">`;
 // 年级只排序/筛选：孩子写明的年级排前，其他年级（可能是先修）照样能选；没填年级不按年龄推。
 function gradesHTML(s){if(!s.groups?.length||s.groups.length<2&&s.grade==null)return '';const all=s.groups.reduce((n,g)=>n+g.count,0);
  return `<div class="topic-grades" role="group" aria-label="按年级看"><button type="button" data-topic-grade="" aria-pressed="${s.grade==null}">全部 ${esc(all)}</button>${s.groups.map(g=>`<button type="button" data-topic-grade="${esc(g.grade)}" aria-pressed="${s.grade===g.grade}">${esc(g.label)}${g.child?'（孩子年级）':''} ${esc(g.count)}</button>`).join('')}</div><p class="small muted">${s.child_grades?.length?'孩子年级的排在前面；其他年级的可能是先修，也可以选。':'孩子年级没填，不按年龄推测；可以点年级只看那一年级。'}</p>`}
 function linkHTML(p,st,current){const s=p.search;let h='';
  // 原错题里家长核对时留下的知识点线索：按原知识包只读检索出的候选，不是确认；家长点“就是这个”才关联，不确定可另查或记没有匹配/说不清。
  // 已保存的当前诊断引用了这道原错题时它提到的知识点，也一样只读列成候选（不是确认）。
  const hints=!s&&!current?[...(st.hint?[{attr:'data-topic-hint',lead:'原错题里保存过知识点线索',...st.hint}]:[]),...(st.diagnosis_hints||[]).map(g=>({attr:'data-topic-diagnosis-hint',lead:`${g.created||''} 保存的${g.subject||''}诊断引用了这道原错题，提到`,...g}))]:[];
  if(hints.length)h+=hints.map(g=>`<div class="topic-hint" ${g.attr}><p class="small">${esc(g.lead)}（<b>还没确认</b>）：“${esc(g.text)}”</p>${g.candidates?.length?`<ul class="topic-list topic-found">${g.candidates.map(c=>`<li><span><b>${esc(c.name)}</b> <span class="small muted">${esc(c.chapter||'')}</span></span><button type="button" data-topic-confirm="${esc(c.id)}">就是这个</button></li>`).join('')}</ul>`:'<p class="small">固定数学知识包里没有找到与这条线索对应的知识点。</p>'}</div>`).join('')+'<p class="topic-actions"><button type="button" data-topic-mark="no_match">都不对，回原题核对</button> <button type="button" data-topic-mark="unclear">暂时说不清</button></p>';
  if(current&&['unclear','no_match'].includes(current.state))h+=`<p class="small">已记为“${current.state==='no_match'?'知识包里没有匹配':'暂时说不清'}”：请回原题和原材料核对；也可以再查一次。</p>`;
  h+=`<div class="topic-row">${field(p,'search','这道题考什么，如：有理数加法、三角形面积')}<button type="button" class="primary" data-topic-search>查找</button></div>`;
  if(s)h+=gradesHTML(s)+(s.status==='unique'||s.status==='ambiguous'?`<ul class="topic-list topic-found">${s.candidates.map(c=>`<li><span><b>${esc(c.name)}</b> <span class="small muted">${esc(c.chapter||'')}</span></span><button type="button" data-topic-confirm="${esc(c.id)}">就是这个</button></li>`).join('')}</ul>${s.total>s.candidates.length?`<p class="small">共 ${esc(s.total)} 个，先列 ${esc(s.candidates.length)} 个：点年级只看那一年级，或多写几个字。</p>`:''}<button type="button" data-topic-mark="no_match">都不对，回原题核对</button>`:`<p class="small" data-topic-none>${esc(s.message||(s.status==='unclear'?'请输入知识点名称或册章。':'知识包里没有匹配的数学知识点：请回原题和原材料核对。'))}</p>${s.status==='none'?'<button type="button" data-topic-mark="no_match">记为没有匹配</button> ':''}<button type="button" data-topic-mark="unclear">暂时说不清</button>`);
  return h}
 // 已答只留一行：原答与判定；答错且有上游说明的，在“当前操作”空出来时给一小步说明。
 function itemLine(p,i,helpable){const q=p.E.questionById(p.graph,i.qid),seen=i.help.includes('explanation');return `<li data-topic-item="${i.seq}" data-topic-item-qid="${esc(i.qid)}"><span data-topic-item-prompt>诊断第${i.seq}题：${q?esc(q.prompt):'知识包里找不到这道题'}</span><br>原答“${esc(i.answer||'—')}” · ${i.evidence_note?`当时判定：${VERDICT[i.stored_verdict]||'未知'} · <span class="small" data-topic-evidence="${i.seq}">${esc(i.evidence_note)}</span>`:VERDICT[i.verdict]}${seen?' · 看过说明':''}${helpable&&i.verdict!=='correct'&&q?.explanation&&!seen?` <button type="button" data-topic-help="${i.seq}">看一小步说明</button>`:''}${seen&&q?.explanation?`<span class="topic-explain">说明：${esc(q.explanation)}</span>`:''}</li>`}
 function questionHTML(p,q,mode){const k=mode+':'+q.id,name='td-'+p.child_id+'-'+p.record_id+'-'+mode;const input=q.type==='choice'&&q.choices?.length?`<div class="topic-choices" role="radiogroup">${q.choices.map(c=>`<label class="topic-choice"><input type="radio" form="topic-diagnosis-none" name="${esc(name)}" data-topic-input="${esc(k)}" value="${esc(c.key)}"${p.draft[k]===c.key?' checked':''}><span>${esc(c.key)}. ${esc(c.text)}</span></label>`).join('')}</div>`:field(p,k,'写答案',ANSWER_MAX);
  return `<div class="topic-question" data-topic-form="${mode}" data-qid="${esc(q.id)}"><p>${esc(q.prompt)}</p>${input}<div class="topic-actions"><button type="button" class="primary" data-topic-submit>提交</button>${mode==='answer'?'<button type="button" data-topic-kind="skip">跳过</button><button type="button" data-topic-kind="unknown">不会</button><button type="button" data-topic-pause>先暂停</button>':''}</div></div>`}
 function retryLines(p,d){return d.retries.map(x=>`<p class="small" data-topic-retry-result="${esc(x.outcome)}">新题再试：${esc(p.E.questionById(p.graph,x.qid)?.prompt||'知识包里找不到这道题')} · 原答“${esc(x.answer)}” · ${x.stored_outcome&&x.stored_outcome!==x.outcome?`当时结果：${esc(OUTCOME[x.stored_outcome]||x.stored_outcome)}`:esc(OUTCOME[x.outcome]||x.outcome)}${x.evidence_note?` · <span class="small" data-topic-evidence-retry>${esc(x.evidence_note)}</span>`:''}${x.outcome==='parent_check'?`（题库核对：${VERDICT[x.taxonomy_verdict]}；复核结果：${x.deeptutor.is_correct==null?'未判定':x.deeptutor.is_correct?'对':'错'}）`:''}</p>`).join('')}
 // 此前待核作答：同一错题、同一依据下较早几轮里有待核题的诊断（state最多只回最近5轮），只读列出原题、原答、当时判定与原因；不进新一轮会话，这里不能作答。
 function priorHTML(p,st){const d=st.diagnoses.find(x=>x.basis==='current'),old=st.diagnoses.filter(x=>x!==d&&x.basis==='current'&&x.items.some(i=>i.evidence_note));
  return old.length?`<section class="topic-prior" data-topic-prior><h4>此前待核作答（只读）</h4>${old.map(x=>`<ol class="topic-done">${x.items.map(i=>itemLine(p,i,false)).join('')}</ol>`).join('')}<p class="small muted">只列最近5轮诊断里有待核题的几轮；更早的作答仍保留在原记录里，这里不显示。现在要做的是上面的新一轮。</p></section>`:''}
 function diagHTML(p,st,linked){return roundHTML(p,st,linked)+(p.graph&&p.E?priorHTML(p,st):'')}
 function roundHTML(p,st,linked){const d=st.diagnoses.find(x=>x.basis==='current');p.view=null;
  // 一个主操作：开始诊断 / 继续诊断 / 独立再试；重新诊断（旧作答保留为历史）退为文字按钮放最后。
  const startBtn=d?`<button type="button" class="topic-quiet" data-topic-start="${esc(linked.topic_id)}">重新诊断这个知识点</button>`:`<button type="button" class="primary" data-topic-start="${esc(linked.topic_id)}">开始诊断（最多8题，可随时暂停）</button>`;
  if(!d||!p.graph)return `<div class="topic-actions">${startBtn}</div>`;
  const s=restore(p.E,p.graph,d);
  // 有待核题、之后的题却是按它当时的判定续出的：旧会话不能安全重放。保留全部历史并标明待核，不再据原判定选题或给线索；只给显式的“重新诊断这个知识点”（新的提交编号，旧记录不动）。
  if(!s&&d.items.some(i=>i.replay_result))return `<p class="small muted">已做 ${d.items.length}/${d.opts.limit} 题</p><ol class="topic-done">${d.items.map(i=>itemLine(p,i,false)).join('')}</ol>${retryLines(p,d)}<p class="small" data-topic-unsafe>这轮里有题目当时的判定现在待家长核对，之后的题是按那次判定续出的，不能再安全接着推算；以上原作答和记录都保留，不再据此选题或给线索。可以“重新诊断这个知识点”开始新的一轮。</p><div class="topic-actions">${startBtn.replace('class="topic-quiet"','class="primary"')}</div>`;
  if(!s)return '<p class="error">保存的作答与当前知识包版本对不上，原作答保留；请联系家长核对知识包版本。</p>';
  // 打开（含冷重开）只读已保存的作答：只有这次在面板里显式开始/继续/作答（p.live）才出下一题，出题前先登记“已出示”。
  const item=d.items.length<d.opts.limit?p.E.nextItem(p.graph,s):null,offer=d.retry_offer,asking=item&&p.live===d.id&&(d.state!=='paused'||p.resume);
  let h=`<p class="small muted">已做 ${d.items.length}/${d.opts.limit} 题${d.state==='paused'&&!p.resume?' · 已暂停，随时可继续':''}</p>${item&&!asking&&d.state!=='paused'?'<p class="small muted" data-topic-cold>这里只显示已保存的作答；点“继续诊断”才出下一题。</p>':''}`;
  const idle=!(offer?.fresh)&&!asking;
  if(d.items.length)h+=`<ol class="topic-done">${d.items.map(i=>itemLine(p,i,idle)).join('')}</ol>`;
  h+=retryLines(p,d);
  // 当前操作只有一个：新题再试 > 诊断下一题 > 小结与下一步。题目先登记“已出示”才显示。
  if(offer?.fresh){p.view={mode:'retry',qid:offer.qid,diag:d.id};const q=p.E.questionById(p.graph,offer.qid);return h+(q?`<p><b>独立再试一道新题</b> <span class="small muted">先别看说明；提交后才判定</span></p>${st.original_identity?.status==='unidentified'?'<p class="small" data-topic-original-unknown>原错题的题面没能与知识包题目逐字对上：如果这道题其实就是原错题，请不要把它算作独立再试。</p>':''}${questionHTML(p,q,'retry')}`:'<p class="error">新题不在当前知识包里，请刷新。</p>')}
  if(offer&&!offer.fresh)h+='<p class="small">上次出示的新题后来又在别处出现过，不再算独立；可以换一道没见过的。</p>';
  if(asking){p.view={mode:'answer',qid:item.question.id,diag:d.id,item,session:s};
   if(!d.shown.includes(item.question.id)){const k=d.id+':'+item.question.id;if(p.shownTried!==k){p.autoShow=k;return h+'<p class="small" data-topic-showing>正在出题…</p>'}return h+'<div class="topic-actions"><button type="button" class="primary" data-topic-show>出下一题</button></div>'}
   return h+`<p class="small muted">第${d.items.length+1}题 · ${esc(p.graph.byId[item.topicId]?.name||item.topicId)}</p>${questionHTML(p,item.question,'answer')}`}
  if(d.items.some(i=>i.evidence_note))h+='<p class="small" data-topic-evidence-summary>有题目当时的判定现在待家长核对；核对前，本轮线索不算结论。</p>';
  const lines=summaryLines(p.graph,s,p.E),tested=lines.filter(l=>!l.inferred),inferred=lines.filter(l=>l.inferred);
  if(tested.length)h+=`<ul class="topic-list" data-topic-summary>${tested.map(l=>`<li>${esc(l.name)} · ${esc(l.label)}${l.asked?` · 问过${l.asked}题`:''}</li>`).join('')}</ul>`;
  if(inferred.length)h+=`<p class="small muted" data-topic-inferred>另有${inferred.length}个先修点未直接测，只是图谱推断（不算掌握）：${esc(inferred.slice(0,3).map(l=>l.name).join('、'))}${inferred.length>3?'等':''}</p>`;
  h+=item?'':'<p class="small">这轮诊断结束。上面只是本轮线索，不写成掌握；先看答错题的说明，再独立做一道新题。</p>';
  if(p.noNew===d.id)h+='<p class="small" data-topic-no-new>这个知识点已没有这孩子历次都没见过的新题；不标为独立复测。</p>';
  if(!st.deeptutor?.available&&d.items.length)h+=`<p class="small muted">${esc(st.deeptutor?.message||'')}</p>`;
  return h+`<div class="topic-actions">${item?'<button type="button" class="primary" data-topic-resume>继续诊断</button>':''}${d.items.length&&p.noNew!==d.id?`<button type="button"${item?'':' class="primary"'} data-topic-retry>独立再试一道新题</button>`:''}${startBtn}</div>`}
 function staleHTML(st){const old=st.diagnoses.filter(d=>d.basis!=='current');if(!old.length&&!st.links.some(l=>l.basis==='basis_changed'))return '';
  const n=old.reduce((k,d)=>k+d.items.length+d.retries.length,0),pending=old.some(d=>d.void?.state==='pending'),voided=old.some(d=>d.void?.state==='voided'),unsettled=old.some(d=>d.void?.state==='unsettled');
  return `<p class="small" data-topic-stale>原错题更正过：之前的知识点和诊断依据已失效${n?`，${n}条作答作为历史保留，不当作当前结果`:''}${voided?'；DeepTutor里的旧作答已作废':''}${pending?'；DeepTutor旧作答待作废（判定组件不可用，重新确认知识点或开始新诊断时再试）':''}${unsettled?'；DeepTutor里的旧作答还没作废，不当作当前结果（重新确认知识点或开始新诊断时作废）':''}。请按更正后的题重新确认。</p>`}
 // 家庭复习：家长在这道原错题上明确批准一次复习，存进同一日历（同孩、原错题、已确认知识点或无、原作业或独立错题、当时依据）。
 function reviewHTML(p,st,topicId){const rs=st.reviews||[],r=p.review||{};
  return `<section class="topic-review" data-topic-review-box><p class="topic-head"><b>家庭复习</b> <span class="small muted">家长安排，不是老师布置的作业</span></p>${rs.length?`<ul class="topic-list" data-topic-reviews>${rs.map(x=>`<li data-topic-review="${esc(x.id)}"><span><b>${esc(x.day)}</b> ${esc(x.title)} · ${esc(REVIEW_STATUS[x.status]||x.status)}${x.basis!=='current'?' · <span class="small" data-topic-review-history>原错题之后更正过：这条按当时的题安排，请核对</span>':''}</span></li>`).join('')}</ul>`:'<p class="small muted" data-topic-reviews-none>还没有安排家庭复习。</p>'}<div class="topic-row"><input type="date" form="topic-diagnosis-none" data-topic-review-day aria-label="复习日期" value="${esc(r.day||'')}"><button type="button" class="primary" data-topic-review-save${r.day?'':' disabled'}>批准并放进日历</button></div><p class="small muted">${topicId?'关联这道错题和已确认的知识点':'知识点还没确认：复习只关联这道错题'}${st.task?' · 原作业：'+esc(st.task.title):' · 独立错题，没有原作业'}。完成复习只记这次安排，不改老师作业，也不算掌握。</p></section>`}
 function draw(p){const st=p.state;let h='<p class="topic-head"><b>知识点诊断</b> <span class="small muted">数学</span></p>';
  if(st&&!st.pack?.installed)h+=`<p class="small" data-topic-pack-missing>${esc(st.pack?.message||'知识包未安装')}；原错题、短引导和每日待办照常可用。</p>`;
  else if(st){const current=st.links.filter(l=>l.basis==='current').at(-1),topic=current?.state==='confirmed'&&st.topics?.[current.topic_id];h+=staleHTML(st);
   if(topic)h+=`<p class="small" data-topic-linked data-topic-id="${esc(current.topic_id)}">知识点：<b>${esc(topic.name)}</b> <span class="muted">${esc(topic.chapter||'')}</span></p>`+diagHTML(p,st,current);else h+=linkHTML(p,st,current)}
  if(st?.record){const current=st.links.filter(l=>l.basis==='current').at(-1);h=(p.box.closest?.('dialog.record-topic')?'':`<p class="small" data-topic-record="${esc(st.record.id)}">原错题：${esc(st.record.day||'')} ${esc(st.record.title||'')}</p>`)+h+reviewHTML(p,st,current?.state==='confirmed'&&st.topics?.[current.topic_id]?current.topic_id:'')}
  h+=`<p class="small" data-topic-status role="status">${esc(p.message)}</p>${p.pending&&!p.busy?'<button type="button" data-topic-resend>重试保存</button>':''}${st?.pack?.installed?'<p class="topic-source small muted" data-topic-source>知识点和练习题来自开源知识包 cn-math-taxonomy（CC BY-NC 4.0）· AI 初稿，未经教师审核 · 诊断只是线索，一次做对不等于掌握</p>':''}`;
  p.box.innerHTML=h;p.box.classList.toggle('is-busy',!!p.busy);bind(p);
  if(p.autoShow&&!p.busy&&!p.pending&&p.view?.mode==='answer'){const [did,qid]=[p.view.diag,p.view.qid];p.shownTried=p.autoShow;p.autoShow=null;send(p,'/api/topic/diagnosis/mark',{child_id:p.child_id,record_id:p.record_id,diagnosis_id:did,action:'shown',mode:'diagnosis',qid},()=>'')}}
 function bind(p){const b=p.box,base={child_id:p.child_id,record_id:p.record_id},v=p.view;
  b.querySelectorAll('[data-topic-input]').forEach(x=>{const k=x.dataset.topicInput;x.addEventListener(x.type==='radio'?'change':'input',()=>{p.draft[k]=x.value});x.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();(x.closest('[data-topic-form]')?.querySelector('[data-topic-submit]')||b.querySelector('[data-topic-search]'))?.click()}})});
  if(p.busy){b.querySelectorAll('button,input').forEach(x=>x.disabled=true);return}
  b.querySelector('[data-topic-resend]')?.addEventListener('click',()=>send(p,p.pending.path,p.pending.body,p.pending.done));
  b.querySelector('[data-topic-review-day]')?.addEventListener('change',e=>{p.review={...(p.review||{}),day:e.target.value};draw(p)});
  // 批准＝点这一次；同一草稿保留同一编号，回执丢失时“重试保存”原样再发，服务端按编号与内容只存一份。
  b.querySelector('[data-topic-review-save]')?.addEventListener('click',()=>{const st=p.state,r=p.review||{};if(!r.day||!st?.record)return;r.id??=hex();p.review=r;
   const cur=st.links.filter(l=>l.basis==='current').at(-1),topic=cur?.state==='confirmed'&&st.topics?.[cur.topic_id]?cur.topic_id:'';
   send(p,'/api/calendar/save',{id:r.id,version:0,child_ids:[p.child_id],title:reviewTitle(st.record.title),category:'study',day:r.day,start_time:'',end_time:'',location:'',note:topic?'知识点：'+st.topics[topic].name:'',status:'confirmed',repeat:'none',until:'',
    review:{child_id:p.child_id,record_id:p.record_id,topic_id:topic,task_id:st.task?.id||'',basis:st.record.basis}},()=>{p.review={};return '家庭复习已放进日历（家长安排，不是老师作业）'})});
  // 查找用输入框里的新词（不带年级）；点年级沿用上次的词，只看那一年级（“全部”取消）。只读，不链接。
  const find=async grade=>{const query=grade===undefined?String(p.draft.search||'').trim():p.search?.query;if(!query)return;try{p.search={query,...await post('/api/topic/search',{...base,query,...(grade==null?{}:{grade})})};p.message=''}catch(x){p.message=x.message}draw(p)};
  b.querySelector('[data-topic-search]')?.addEventListener('click',()=>find());
  b.querySelectorAll('[data-topic-grade]').forEach(x=>x.onclick=()=>find(x.dataset.topicGrade===''?null:Number(x.dataset.topicGrade)));
  b.querySelectorAll('[data-topic-confirm]').forEach(x=>x.onclick=()=>send(p,'/api/topic/link',{...base,topic_id:x.dataset.topicConfirm,state:'confirmed',request_id:key()},()=>{p.search=null;return '知识点已确认；可以开始诊断'}));
  b.querySelectorAll('[data-topic-mark]').forEach(x=>x.onclick=()=>send(p,'/api/topic/link',{...base,state:x.dataset.topicMark,request_id:key()},()=>{p.search=null;return '已记下；请回原题和原材料核对'}));
  b.querySelector('[data-topic-start]')?.addEventListener('click',e=>send(p,'/api/topic/diagnosis/start',{...base,topic_id:e.target.dataset.topicStart,request_id:key()},v=>{p.resume=false;p.noNew=null;p.live=(v?.diagnoses||[]).find(x=>x.basis==='current')?.id;return ''}));
  b.querySelector('[data-topic-resume]')?.addEventListener('click',()=>{p.resume=true;p.live=p.state?.diagnoses?.find(x=>x.basis==='current')?.id;draw(p)});
  b.querySelector('[data-topic-show]')?.addEventListener('click',()=>{if(v)send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:v.diag,action:'shown',mode:'diagnosis',qid:v.qid},()=>'')});
  const d=p.state?.diagnoses?.find(x=>x.basis==='current');if(!d)return;
  b.querySelector('[data-topic-pause]')?.addEventListener('click',()=>send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'pause'},()=>{p.resume=false;return '已暂停：保存的作答都在，下次打开从这里继续'}));
  b.querySelectorAll('[data-topic-help]').forEach(x=>x.onclick=()=>send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'help_explanation',seq:Number(x.dataset.topicHelp)},()=>'说明已打开：这题记为“看过说明”'));
  b.querySelector('[data-topic-retry]')?.addEventListener('click',()=>{const it=retryItem(p.E,p.raw,p.graph,d,seenQids(p.state));if(!it){p.noNew=d.id;draw(p);return}
   send(p,'/api/topic/diagnosis/mark',{...base,diagnosis_id:d.id,action:'shown',mode:'retry',qid:it.question.id},()=>'')});
  const answer=(kind,text)=>{const it=v.item,j=judge(p.E,it.question,kind,text),s=p.E.applyAnswer(p.graph,v.session,it.topicId,j.engine,{text});
   send(p,'/api/topic/diagnosis/answer',{...base,diagnosis_id:d.id,seq:d.items.length+1,topic_id:it.topicId,qid:it.question.id,kind,answer:text,verdict:j.verdict,engine_result:j.engine,session:s,summary:p.E.summarize(p.graph,s)},v=>{delete p.draft['answer:'+it.question.id];const got=(v?.diagnoses||[]).find(x=>x.id===d.id)?.items?.find(x=>x.seq===d.items.length+1);return got?.evidence_note?'已保存。当时判定：'+VERDICT[j.verdict]+' · '+got.evidence_note:VERDICT[j.verdict]})};
  b.querySelectorAll('[data-topic-kind]').forEach(x=>x.onclick=()=>answer(x.dataset.topicKind,''));
  b.querySelector('[data-topic-submit]')?.addEventListener('click',()=>{if(!v)return;const k=v.mode+':'+v.qid,t=String(p.draft[k]||'').trim();if(!t){p.message='请先写答案或选一项';draw(p);return}
   if(v.mode==='answer')return answer('answer',t);
   const q=p.E.questionById(p.graph,v.qid),rid=p.keys[d.id+':'+v.qid]??=key();
   send(p,'/api/topic/diagnosis/retry',{...base,diagnosis_id:d.id,qid:q.id,answer:t,verdict:judge(p.E,q,'answer',t).verdict,request_id:rid},()=>{delete p.draft[k];return '这次再试已保存，结果见上方'})})}
 // 未保存：保存中或回执不明（有“重试保存”），或当前显示的作答/新题框里还没提交的原答；搜索词和空框不算。接页面原有 beforeunload 判断（原生重开网页前也读它）。
 function hasUnsaved(){return Object.values(panels).some(p=>p.busy||!!p.pending||!!p.box?.isConnected&&[...p.box.querySelectorAll('[data-topic-input]')].some(x=>/^(answer|retry):/.test(x.dataset.topicInput||'')&&(x.type==='radio'?x.checked:String(x.value||'').trim()!=='')))}
 if(typeof window!=='undefined'&&window.addEventListener)window.addEventListener('beforeunload',e=>{if(hasUnsaved()){e.preventDefault();e.returnValue=''}});
 document.addEventListener('click',e=>{const b=e.target.closest('[data-topic-open]');if(b)open(b.closest('[data-topic-diagnosis]'))});
 return {...logic,slot,open,hasUnsaved};
});
