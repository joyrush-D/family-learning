// Compare explicit same-child record links; never classify mastery from note text.
function learningCases(records, selectedChild='') {
 const rows=records.filter(r=>r&&(!selectedChild||r.child===selectedChild)),byChild=new Map();
 for(const r of rows){const k=String(r.child)+'\0'+r.id;if(!byChild.has(k))byChild.set(k,[]);byChild.get(k).push(r)}
 const groups=new Map();
 const validID=n=>Number.isInteger(n)&&n>0;
 const parentOf=r=>{const found=byChild.get(String(r.child)+'\0'+r.related_record_id);return found?.length===1?found[0]:null};
 // ponytail: household-sized records walk explicit ancestry; cache roots if long chains become slow.
 for(const r of rows){
  if(!['成绩','学习进展'].includes(r.category)&&!r.related_record_id&&!r.followup_kind)continue;
  let current=r,problem='',seen=new Set(),trail=[r];
  while(current.related_record_id){
   if(seen.has(current)){problem='关联链有循环，已单独展示；起点待核对。';current=r;trail=[r];break}seen.add(current);
   if(!validID(current.related_record_id)){problem='关联编号无法核对，未与其他记录合并。';break}
   const next=parentOf(current);
   if(!next){problem='关联记录缺失、归属不同或编号不唯一；起点待核对。';break}
   current=next;trail.push(current);
  }
  if(!problem&&current.followup_kind&&!current.related_record_id)problem='这条跟进尚未关联起始或上一次记录，不能做前后比较。';
  const identity=byChild.get(String(r.child)+'\0'+r.id);
  if(!validID(r.id)||identity?.length!==1){problem='这条记录的编号无法唯一核对，已单独展示。';current=r;trail=[r]}
  if(!groups.has(current))groups.set(current,{root:current,items:new Set([current]),issues:new Set(),parents:new Map()});
  const group=groups.get(current);for(const item of trail)group.items.add(item);if(problem)group.issues.add(problem);
 }
 return [...groups.values()].map(g=>{
  const items=[g.root,...[...g.items].filter(r=>r!==g.root).sort((a,b)=>String(a.day).localeCompare(String(b.day))||a.id-b.id)];
  for(const r of items){const parent=parentOf(r);if(parent&&g.items.has(parent)&&parent!==r)g.parents.set(r,parent)}
  return {...g,items,issues:[...g.issues]};
 }).sort((a,b)=>String(b.items.at(-1)?.day).localeCompare(String(a.items.at(-1)?.day))||b.root.id-a.root.id);
}
function learningDateGap(day,other) {
 const parsed=value=>{if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;const stamp=Date.parse(value+'T00:00:00Z');return Number.isFinite(stamp)&&new Date(stamp).toISOString().slice(0,10)===value?stamp:null};
 const first=parsed(day),second=parsed(other);return first===null||second===null?null:(first-second)/86400000;
}
function learningEvidenceNotes(r,parent) {
 const notes=[],retest=['复测','独立复测'].includes(r.followup_kind),gap=parent?learningDateGap(r.day,parent.day):null;
 if(retest){
  if(!r.assistance)notes.push('帮助情况未记录，不能仅凭“复测”或旧名称“独立复测”判断独立完成。');
  if(!r.practice_relation)notes.push('与关联记录的材料关系未记录，能否比较仍待核对。');
  if(gap===0)notes.push('两条记录在同一天，不能据此判断隔一段时间后的表现。');
  if(r.practice_relation==='同一道题或同一片段')notes.push('记录为同一道题或同一片段，不能据此判断对新材料的迁移。');
  if(r.practice_relation==='范围或难度不同')notes.push('记录的范围或难度不同，不能直接比较表现高低。');
  if(r.assistance==='独立尝试'&&r.practice_relation==='相近的新题或新片段')notes.push('记录了独立尝试相近新材料；这一次记录仍不足以认定稳定掌握。');
 }
 if(gap!==null&&gap<0)notes.push('本条记录日期早于关联记录，日期顺序需要核对。');
 return notes;
}
function learningIsPractice(g){return g.items.some(r=>r.category==='成绩'||['订正','复测','独立复测'].includes(r.followup_kind))}
function learningBrief(value,limit=150){const text=String(value||'').trim();return text.length>limit?text.slice(0,limit)+'…':text}
function learningJourneysHTML() {
 const cases=learningCases(data.records||[],child),missing=cases.filter(g=>g.items.some(r=>r.followup_kind==='订正')&&!g.items.some(r=>['复测','独立复测'].includes(r.followup_kind))).length;
 const idCounts=new Map();for(const r of data.records||[])idCounts.set(r.id,(idCounts.get(r.id)||0)+1);
 const canEdit=r=>Number.isInteger(r.id)&&r.id>0&&idCounts.get(r.id)===1;
 const rowHTML=(r,g,index)=>{
  const parent=g.parents.get(r),gap=parent?learningDateGap(r.day,parent.day):null,notes=learningEvidenceNotes(r,parent);
  const stage=index===0?(r.followup_kind&&!r.related_record_id?r.followup_kind+' · 未关联':g.issues.length?'起点待核对':'原始记录'):(r.followup_kind||'跟进类型未记录');
  const ids=Array.isArray(r.attachments)?r.attachments:[],missingFiles=ids.filter(id=>!(data.uploads||[]).some(a=>a.id===id));
  return `<article class="learning-step" data-learning-record="${esc(r.id)}"><div class="learning-stage"><span>${esc(stage)}</span><time>${esc(r.day||'日期未记录')}</time></div><div class="learning-step-body"><h4>${esc(r.title||'标题未记录')}</h4>${parent?`<p class="learning-reference">直接关联：${esc(parent.title||'标题未记录')} · ${esc(parent.day||'日期未记录')}<br>${gap===null?'两条记录的日期差无法核对。':`与关联记录的日期差：${esc(gap)} 天${gap<0?'（本条日期较早，需核对）':''}。`}</p>`:r.related_record_id?'<p class="learning-reference">原关联目前不能完整核对。</p>':''}<p class="source">${esc(r.note||'尚未填写当时的具体表现。')}</p><dl class="learning-facts">${learningIsPractice(g)||r.score!==null&&r.score!==undefined?`<div><dt>原记录分数</dt><dd>${r.score===null||r.score===undefined?'未记录':esc(r.score)+' / '+esc(r.total??'满分未记录')}</dd></div>`:''}${learningIsPractice(g)||r.assistance?`<div><dt>记录的帮助</dt><dd>${esc(r.assistance||'未记录')}</dd></div>`:''}${learningIsPractice(g)||r.practice_relation?`<div><dt>与关联记录相比</dt><dd>${esc(r.practice_relation||'材料关系未记录')}</dd></div>`:''}<div><dt>记录来源</dt><dd>${esc(r.source||'未记录')}</dd></div></dl>${r.comparison_note?`<p class="source learning-comparison"><strong>比较说明</strong><br>${esc(r.comparison_note)}</p>`:''}${notes.map(n=>`<p class="learning-limit">${esc(n)}</p>`).join('')}<details class="learning-originals"><summary>查看这条记录的原件 · ${ids.length} 份</summary>${recordUploads({...r,attachments:ids})}${missingFiles.length?`<p class="learning-limit">${missingFiles.length} 份原件当前缺少元数据，不能打开核对。</p>`:''}${!ids.length?'<p class="small muted">这条记录尚未关联原件。</p>':''}</details>${canEdit(r)&&!String(r.source||'').startsWith('短引导尝试:')?`<button type="button" data-record="${esc(r.id)}">更正这条记录</button>`:''}</div></article>`;
 };
 return `<section class="card learning-journeys" aria-labelledby="learning-journeys-title"><div class="learning-journeys-heading"><div><h2 id="learning-journeys-title">从已有记录继续</h2></div><div class="learning-count"><strong>${cases.length}</strong><span>条学习线索</span></div></div>${missing?`<p class="learning-next">${missing} 条线索已有订正，尚无复测记录。可以在下一次实际尝试后补记。</p>`:''}<div class="learning-case-list">${cases.map(g=>{
  const correction=g.items.filter(r=>r.followup_kind==='订正').length,retests=g.items.filter(r=>['复测','独立复测'].includes(r.followup_kind)),observations=g.items.filter(r=>r.followup_kind==='补充观察').length;
  const root=g.root,practice=learningIsPractice(g),latest=g.items.at(-1),summary=practice?(retests.length?`有 ${retests.length} 条复测记录，请展开核对当时帮助和材料关系。`:correction?`有 ${correction} 条订正记录，尚无复测记录。`:'可以记录这次尝试与所需帮助，再决定是否需要订正或复测。'):learningBrief(root.note||'可以补充实际情况、孩子的说法与后续核对结果。',100);
  return `<article class="learning-case" data-learning-case="${esc(root.id)}"><div class="learning-case-top"><span class="chip">${esc(root.child)}${root.subject?' · '+esc(root.subject):''}</span><span class="small muted">${esc(root.day||'日期待核对')}</span></div><h3>${esc(root.title||'标题未记录')}</h3><div class="learning-route" aria-label="这条线索已记录的步骤"><span>起始记录</span>${practice?`<span aria-hidden="true">→</span><span>订正 ${correction}</span><span aria-hidden="true">→</span><span>复测 ${retests.length}</span>`:''}${observations?`<span aria-hidden="true">→</span><span>补充观察 ${observations}</span>`:''}</div><p class="learning-case-summary">${esc(summary)}</p>${!practice&&latest!==root?`<p class="learning-case-summary"><strong>最近补充 · ${esc(latest.day)}<br>${esc(latest.title)}</strong><br>${esc(learningBrief(latest.note,100))}</p>`:''}${g.issues.map(s=>`<p class="learning-limit">${esc(s)}</p>`).join('')}<details class="learning-compare"><summary>${practice?'展开对照':'查看原文与跟进'} · ${g.items.length} 条记录</summary><p class="small muted">${practice?'每条跟进针对下方注明的直接关联记录。日期差仅来自记录日期，不代表实际教学或练习间隔。':'保留各方当时的说法；补充观察不会覆盖原记录，也不自动判定完成情况。'}</p><div class="learning-steps">${g.items.map((r,i)=>rowHTML(r,g,i)).join('')}</div></details>${canEdit(root)?`<div class="learning-actions">${practice?`<button type="button" data-guided-new="${esc(root.id)}">一起试这题</button><button type="button" data-followup="${esc(root.id)}" data-followup-kind="订正">记一次订正</button><button type="button" data-followup="${esc(root.id)}" data-followup-kind="复测">记一次复测</button>`:''}<button type="button" data-followup="${esc(root.id)}" data-followup-kind="补充观察">补充观察</button>${practice?'':`<button type="button" data-guided-new="${esc(root.id)}">准备学习任务</button><details><summary>记录练习表现</summary><button type="button" data-followup="${esc(root.id)}" data-followup-kind="订正">记一次订正</button><button type="button" data-followup="${esc(root.id)}" data-followup-kind="复测">记一次复测</button></details>`}</div>`:''}</article>`;
 }).join('')||empty('还没有学习记录。可以先在上方新建学习任务，实际尝试后再记录表现。')}</div><p class="small muted learning-footnote">这些是已填写的过程记录，不自动核实实际情况，也不据分数、记录数量或一次尝试判定掌握。</p></section>`;
}
