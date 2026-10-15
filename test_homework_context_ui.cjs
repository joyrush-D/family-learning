// Real isolated demo/Handler and browser: one family-entered homework, two TXT files whose roles the parent chooses, the program's
// inspection states in the live check and its saved text, a zero-write save retry, then the reopened check led by what needs attention.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const original=fs.readFileSync(path.join(__dirname,'test_homework_text_ui.cjs'),'utf8');
let fixture=/const fixture=String.raw`([\s\S]*?)`;/m.exec(original)[1];
fixture=fixture.replace(/^paper=.*$/m,String.raw`paper='虚构柳叶卷\n一、看拼音写词语。\n1. chūn tiān（ ）\n孩子作答：春天\n2. huā duǒ（ ）\n孩子作答：花朵\n3. péng yǒu（ ）\n孩子作答：明友\n二、选择正确答案。\n1. 1+1=? A.1 B.2 C.3\n孩子作答：\n2. 2+2=? A.3 B.4 C.5\n孩子作答：A\n3. 3+3=? A.5 B.6 C.7\n孩子作答：B\n'`);
fixture=fixture.replace(/^teacher=.*$/m,String.raw`teacher='教师参考答案\n虚构柳叶卷\n一、看拼音写词语。\n1. 春天\n2. 花朵\n3. 朋友\n'`);
// The model returns five of six questions: the sixth is a proved omission, and the empty fourth is checked against its closed text field.
const model=String.raw`def model(messages,schema,name,timeout,**kwargs):
 assert app.DATA.name.startswith('family-demo-') and name=='family_homework_reference' and len(calls)<2
 texts=[p['text'] for p in messages[-1]['content'] if p.get('type')=='text']
 q=[t for t in texts if t.startswith('题目/孩子作答原文')];r=[t for t in texts if t.startswith('教师参考原文')]
 assert len(q)==1 and len(r)==1
 assert json.loads(q[0][q[0].index('['):])==[dict(name='synthetic-context-paper.txt',text=paper)]
 assert json.loads(r[0][r[0].index('['):])==[dict(name='synthetic-context-teacher.txt',text=teacher)]
 L=lambda a,b:'虚构柳叶卷 第%d大题 第%d题'%(a,b)
 def item(label,text,student,answer,judgment,error='',uncertainty=''):
  return dict(label=label,question=text,student_answer=student,answer=answer,judgment=judgment,question_kind='objective',error_reason=error,possible_cause='',steps='',uncertainty=uncertainty)
 raw=dict(question_labels=[L(1,1),L(1,2),L(1,3),L(2,1),L(2,2)],coverage='仅本次全虚构资料。',items=[
  item(L(1,1),'chūn tiān（ ）','春天','教师参考：春天','correct'),item(L(1,2),'huā duǒ（ ）','花朵','教师参考：花朵','correct'),
  item(L(1,3),'péng yǒu（ ）','明友','教师参考：朋友','incorrect','孩子写成“明友”，教师参考为“朋友”。'),
  item(L(2,1),'1+1=? A.1 B.2 C.3','','AI自行推导：B','unknown',uncertainty='孩子未作答，仍须核对。'),
  item(L(2,2),'2+2=? A.3 B.4 C.5','A','AI自行推导：B','incorrect','2+2=4，应选B，孩子选了A。')])
 calls.append(dict(phase='context',raw=raw,original=copy.deepcopy(raw)))
 return raw
`;
fixture=fixture.replace(/^def model\([\s\S]*?(?=app.family_llm._chat_json=model)/m,model);
const L=(a,b)=>`虚构柳叶卷 第${a}大题 第${b}题`;
// Like test_homework_text_ui.cjs, the page's own function source is read from the shipped files and run unchanged.
const appSource=fs.readFileSync(path.join(__dirname,'app.js'),'utf8'),calendarSource=fs.readFileSync(path.join(__dirname,'calendar.js'),'utf8');
const between=(source,start,end)=>{const i=source.indexOf(start),j=source.indexOf(end,i);assert(i>=0&&j>i,start);return source.slice(i,j)};
const savedSource=between(appSource,'function savedHomeworkReviewParts(text){','\nasync function loadSavedHomeworkReview');
const {agendaDateHTML,taskFamilyEntry}=new Function('esc','data',between(calendarSource,'function agendaDueLabel(','function agendaItemHTML(')+between(appSource,'function taskFamilyEntry(','\nfunction taskReviewDue(')+';return {agendaDateHTML,taskFamilyEntry}')(x=>String(x),{today:'2026-10-15'});
async function until(fn,label){const end=Date.now()+12000;while(Date.now()<end){if(await fn())return;await delay(80)}throw Error(label)}
async function start(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture,String(port)],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let err='',receipt;
 child.stderr.on('data',b=>err=(err+b).slice(-10000));const terminal=once(child,'exit').then(([code,signal])=>({code,signal})),url='http://127.0.0.1:'+port+'/';
 const stop=async()=>{
  if(receipt)return receipt;let forced=false;if(child.exitCode===null&&child.signalCode===null)child.kill('SIGINT');
  let ended=await Promise.race([terminal,delay(3000).then(()=>null)]);
  if(!ended){forced=true;child.kill('SIGKILL');ended=await Promise.race([terminal,delay(2000).then(()=>null)])}
  assert(ended,'owned demo child must be reaped');const closed=await new Promise(resolve=>{const s=net.connect({host:'127.0.0.1',port});s.on('connect',()=>{s.destroy();resolve(false)});s.on('error',()=>resolve(true));s.setTimeout(500,()=>{s.destroy();resolve(false)})});
  receipt={pid:child.pid,...ended,forced,port_closed:closed};assert(closed,'owned demo port must be closed');return receipt;
 };
 try{await until(async()=>{if(child.exitCode!==null)throw Error(err);try{return (await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'demo startup');return {url,stop}}
 catch(e){await stop();throw e}
}
(async()=>{let browser,server,page;const proof=process.env.HOMEWORK_CONTEXT_PROOF_DIR,results=[];const shot=async(name,target)=>{if(!proof)return;fs.mkdirSync(proof,{recursive:true});if(target)await target.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(proof,name+'.png')})};try{
 browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--no-default-browser-check']});
 for(const width of [360,1440]){
  server=await start();const state=async()=>(await fetch(server.url+'api/state')).json(),audit=async()=>(await fetch(server.url+'__fixture/text')).json();
  page=await browser.newPage({viewport:{width,height:850}});page.setDefaultTimeout(12000);const errors=[],foreign=[],bad=[],dialogs=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{dialogs.push(d.message());d.dismiss()});
  await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url());if(u.origin!==new URL(server.url).origin){foreign.push(r.url());return route.abort()}if(r.method()==='POST'&&u.pathname.startsWith('/api/print/')&&!['/api/print/homework/draft','/api/print/homework/catalog'].includes(u.pathname)){bad.push(u.pathname);return route.abort()}return route.continue()});
  const fit=async()=>assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1&&[...document.querySelectorAll('dialog[open]')].every(d=>d.scrollWidth<=d.clientWidth+1)),'no horizontal overflow');
  await page.goto(server.url);
  // Publication: a school item (message, accepted origin or a free-text school source) keeps "待核对"; only a family entry without a date omits it.
  const dates={school:agendaDateHTML({published_on:''},'2026-10-15',taskFamilyEntry({source:'Agent建议:x\nmessage:s:1',school_origin:true,agenda:{}})),
   message:agendaDateHTML({published_on:''},'2026-10-15',taskFamilyEntry({source:'message:s:1',agenda:{publications:[{ref:'message:s:1'}]}})),
   freeText:agendaDateHTML({published_on:''},'2026-10-15',taskFamilyEntry({source:'虚构学校通知',agenda:{}})),
   family:agendaDateHTML({published_on:'',due_on:''},'2026-10-15',taskFamilyEntry({source:'家长录入',agenda:{}})),
   familyDated:agendaDateHTML({published_on:'2026-10-14'},'2026-10-15',taskFamilyEntry({source:'家长录入',agenda:{}})),
   familyLinked:taskFamilyEntry({source:'家长录入',agenda:{publications:[{ref:'message:s:1'}]}})};
  for(const key of ['school','message','freeText'])assert.match(dates[key],/发布：待核对/,key);
  assert.doesNotMatch(dates.family,/发布/);assert.match(dates.family,/截止待核对/);assert.match(dates.familyDated,/发布：2026-10-14/);assert.equal(dates.familyLinked,false);
  await page.locator('[data-homework-new]').first().click();const entry=page.locator('#homeworkInputDialog'),row=entry.locator('[data-homework-item="0"]'),title='虚构两大题六题 '+width;
  await row.locator('[name=title]').fill(title);await row.locator('[name=goal]').fill('完成两大题六题，检查后保留待补题。');await row.locator('[type=submit]').click();await entry.locator('.homework-saved').waitFor();await entry.locator('[data-homework-close]').click();
  let value=await state();const task=value.tasks.find(t=>t.title===title);assert(task);assert(['家长录入','家庭放学后录入'].includes(task.source),'a family entry: '+task.source);
  const card=page.locator('[data-query-target="task:'+task.id+'"]').first();await card.waitFor();assert.doesNotMatch(await card.locator('.agenda-dates').innerText(),/发布/,'a family entry shows no publication to check');
  await card.locator('[data-task="'+task.id+'"]').first().click();
  const content=await audit();for(const [name,text] of [['synthetic-context-paper.txt',content.paper],['synthetic-context-teacher.txt',content.teacher]]){await page.locator('#fileInput').setInputFiles({name,mimeType:'text/plain',buffer:Buffer.from(text)});await page.locator('#pendingUploads').getByRole('link',{name,exact:true}).waitFor()}
  await page.locator('#taskForm [name=note]').fill('虚构两大题六题的原作答；教师只提供第一大题参考。');await page.locator('#saveTaskFeedback').click();await until(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'original saved');
  value=await state();const answer=value.records.find(r=>r.source==='事项:'+task.id&&!r.related_record_id);assert(answer);const paper=value.uploads.find(x=>x.name==='synthetic-context-paper.txt'),teacher=value.uploads.find(x=>x.name==='synthetic-context-teacher.txt');
  const panel=()=>page.locator('[data-homework-review="'+answer.id+'"]'),role=a=>panel().locator('[data-homework-review-role="'+a.id+'"]'),pick=a=>panel().locator('[data-homework-review-photo][value="'+a.id+'"]'),note=()=>panel().locator('[data-homework-material-note]'),status=()=>panel().locator('[data-homework-review-status]');
  await panel().waitFor();if(!await panel().locator(':scope > details').evaluate(x=>x.open))await panel().locator(':scope > details > summary').click();await until(async()=>await note().count()===1,'materials read');
  // Roles: no file is pre-assigned by type or name, and neither is selected.
  for(const a of [paper,teacher]){assert.equal(await role(a).inputValue(),'',a.name+' has no guessed role');assert.deepEqual(await role(a).locator('option').evaluateAll(xs=>xs.map(x=>x.value)),['','question','reference','previous']);assert.equal(await pick(a).isChecked(),false)}
  assert.equal(await note().innerText(),'没有更多已关联资料。如有老师参考，可在“追加一次作答 / 反馈”上传保存后，在这里选用。');
  await pick(paper).check();await pick(teacher).check();await until(async()=>/2 份用途未定/.test(await note().innerText()),'undecided note');assert.equal(await role(paper).getAttribute('aria-invalid'),'true');
  await shot('context-'+width+'-roles-undecided',panel().locator('[data-homework-review-photo][value="'+teacher.id+'"]'));await fit();
  await panel().locator('[data-homework-review-run]').click();await until(async()=>/请先为已选资料选择用途/.test(await status().innerText()),'undecided run stops');
  await panel().locator('[data-homework-batch-load]').click();await until(async()=>/请先为已选资料选择用途/.test(await status().innerText()),'undecided catalog stops');
  assert.equal((await audit()).calls.length,0,'an undecided role reaches no model');assert.equal(await panel().locator('[data-homework-review-result] textarea').count(),0);
  await role(paper).selectOption('question');await until(async()=>/1 份用途未定/.test(await note().innerText()),'one undecided');await role(teacher).selectOption('reference');
  await until(async()=>await note().innerText()==='没有更多已关联资料；老师参考已在上方选用。','reference selected note');assert.equal(await status().innerText(),'','the role reminder clears once every selected file has a role');assert.equal(await role(paper).getAttribute('aria-invalid'),null);await shot('context-'+width+'-roles-chosen',note());
  // Live check: the program's inspection names the missing question and the proved blank; nothing else claims a blank or illegible answer.
  await panel().locator('[data-homework-review-run]').click();await until(async()=>await panel().locator('[data-homework-review-result] textarea').count()===1,'draft');
  const result=panel().locator('[data-homework-review-result]'),rows=result.locator('.homework-question'),q=label=>rows.filter({has:page.locator('h4',{hasText:label})});
  assert.equal(await result.locator('.homework-review-counts').innerText(),'6题 · 2题需订正 · 2题未判定（其中1题尚未检查）。');assert.equal(await rows.count(),6);
  const missing=await q(L(2,3)).innerText(),blank=await q(L(2,1)).innerText();
  assert.equal(await q(L(2,3)).getAttribute('data-inspection'),'not_checked');assert.match(missing,/本题尚未检查，待补查/);assert.doesNotMatch(missing,/孩子作答|参考内容|需补充资料/);assert.match(missing,/待核原因：原件《synthetic-context-paper.txt》第14行明确列出本题/);
  assert.match(blank,/孩子作答：原件作答栏留空（程序核对《synthetic-context-paper.txt》第11行）/);assert.match(blank,/待核原因：孩子未作答，仍须核对。/);
  assert.match(await q(L(1,3)).innerText(),/孩子作答：明友/);assert.doesNotMatch(await result.innerText(),/未能辨认|空答|需补充资料/);
  const generated=await result.locator('textarea').inputValue(),reply=(await audit()).responses.at(-1).body.draft;assert.equal(generated,reply.text);
  assert.equal(reply.questions.find(x=>x.label===L(2,1)).student_answer,'');assert.deepEqual(reply.questions.find(x=>x.label===L(2,3)).inspection,{state:'not_checked',basis:'source_inventory',document:'synthetic-context-paper.txt',line:14});
  for(const line of ['卷面作答：本题尚未检查，待补查','卷面作答：原件作答栏留空（程序核对《synthetic-context-paper.txt》第11行）'])assert(generated.split('\n').includes(line),line);
  await shot('context-'+width+'-live-missing',q(L(2,3)));await fit();
  // The scope area itself is photographed: the validator's facts and each material as short rows below the questions and the next step.
  {const scope=result.locator(':scope > .homework-review-scope').first();assert.equal(await scope.locator('.homework-review-read').count(),2,'one row per material');assert.equal(await scope.locator('.homework-review-redundant').count(),1,'the count above is not shown twice');assert.equal(await scope.locator('.homework-review-redundant').evaluate(x=>x.getBoundingClientRect().width),0);await scope.evaluate(x=>x.scrollIntoView({block:'start'}));await shot('context-'+width+'-live-scope');await fit()}
  // Save: a 503 writes nothing and keeps the draft; the retry saves once and keeps the parent's roles on the redrawn answer.
  let fault=1;await page.route('**/api/task/feedback',async route=>{if(fault===1){fault=0;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构保存失败，零写'})})}return route.continue()});
  await panel().locator('[data-homework-review-confirm]').check();await panel().locator('[data-homework-review-apply]').click();await until(async()=>/已填入反馈/.test(await status().innerText()),'fill');
  const checks=async()=>(await state()).records.filter(r=>r.related_record_id===answer.id&&r.followup_kind==='作业检查').length;
  await page.locator('#saveTaskFeedback').click();await until(async()=>await page.locator('#taskError').innerText()!=='','save failure kept');assert.equal(await checks(),0,'503 writes nothing');
  await page.locator('#saveTaskFeedback').click();await until(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'check saved');assert.equal(await checks(),1);
  await until(async()=>await note().count()===1,'materials reread');assert.equal(await role(paper).inputValue(),'question');assert.equal(await role(teacher).inputValue(),'reference');
  // Reopen: the saved check leads with questions to correct and to check, in original order, above its unchanged complete text.
  await page.locator('[data-close="taskDialog"]').click();await page.reload();await page.locator('[data-query-target="task:'+task.id+'"] [data-task="'+task.id+'"]').first().click();
  const saved=page.locator('[data-saved-homework-review]').first(),text=saved.locator('[data-saved-review-text]'),focus=saved.locator('[data-saved-review-focus]');
  await until(async()=>(await text.textContent()).length>0,'saved check read');assert.equal(await text.textContent(),generated.trim(),'the saved text reads back verbatim');
  assert.equal(await focus.isVisible(),true);assert.equal(await focus.evaluate(x=>getComputedStyle(x).position),'static','the summary stays in the check, never over the close bar');const groups=await focus.locator('.saved-review-focus-row').evaluateAll(xs=>xs.map(x=>[x.querySelector('strong').textContent,[...x.querySelectorAll('button')].map(b=>b.textContent)]));
  assert.deepEqual(groups,[['需订正 2 题',['第1大题 第3题','第2大题 第2题']],['待补查 2 题',['第2大题 第1题','第2大题 第3题']]]);
  assert(Math.min(...await focus.locator('button').evaluateAll(xs=>xs.map(x=>x.getBoundingClientRect().height)))>=44,'touch targets');
  await shot('context-'+width+'-reopened-focus',focus);await fit();
  // The saved scope shows the same rows; its coverage count equals the exact count line above it, so it stays in the text but is shown once.
  {const scope=text.locator('.saved-review-scope').first();assert.equal(await scope.locator('.saved-review-scope-read').count(),2);assert.match(await scope.locator('.saved-review-redundant').textContent(),/^本次\d+题，\d+题仍未判定。$/);assert.equal(await scope.locator('.saved-review-scope-count').count(),0);assert.equal(await text.locator('.saved-review-summary').isVisible(),true);await scope.evaluate(x=>x.scrollIntoView({block:'start'}));await shot('context-'+width+'-reopened-scope');await fit()}
  await focus.getByRole('button',{name:'查看 '+L(2,3),exact:true}).click();
  // The located question opens at the top of the dialog, so its lines are readable above the close bar.
  assert.deepEqual(await page.evaluate(()=>{const x=document.activeElement,r=x.getBoundingClientRect(),d=x.closest('dialog').getBoundingClientRect();return [x.className,x.textContent,r.top>=d.top&&r.top<=d.top+80]}),['saved-review-question',L(2,3),true]);await shot('context-'+width+'-reopened-located');
  // Only a text that parses exactly gets the summary; an edited or older text shows its complete text alone.
  const strict=await page.evaluate(([source,texts])=>{const {savedHomeworkReviewParts,savedHomeworkReviewFocus}=new Function(source+';return {savedHomeworkReviewParts,savedHomeworkReviewFocus}')();return texts.map(t=>{const panel=document.createElement('section');panel.innerHTML='<div data-saved-review-focus hidden></div>';const parts=savedHomeworkReviewParts(t),nodes=parts.map(p=>{if(!p.kind)return p.text;const s=document.createElement('span');s.textContent=p.text;return s});savedHomeworkReviewFocus(panel,parts,nodes);return panel.querySelector('[data-saved-review-focus]').hidden})},[savedSource,[generated,generated.replace(/\n\n虚构柳叶卷 第2大题 第3题 · 未判定\n[^]*?(?=\n\n标)/,''),generated.replace('本次核对6题：','本次核对6题，'),generated.replace('卷面作答：明友','卷面作答：明友\n家长补充：看错了')]]);
  assert.deepEqual(strict,[false,true,true,true]);
  // The saved text comes back without the program's own checks: an answer line edited into a program state's wording keeps the same
  // summary, and a text with no questions shows its complete text alone instead of failing to read.
  const neutral='本次核对1题：需订正0题，与参考一致0题，未判定1题。\n\n虚构照片卷 第1题 · 未判定\n题面：读取本题原作答。\n卷面作答：未能确认\n参考答案：待核对\n不确定：照片中的内容本次无法确认。\n\n请对照原题核对后保存；本轮结果不代表作业已完成或已经掌握。',none='本次核对0题：需订正0题，与参考一致0题，未判定0题。';
  const edited=await page.evaluate(([source,texts])=>{const {savedHomeworkReviewParts,savedHomeworkReviewFocus}=new Function(source+';return {savedHomeworkReviewParts,savedHomeworkReviewFocus}')();const node=p=>{if(!p.kind)return p.text;const s=document.createElement('span');if(p.parts)s.append(...p.parts.map(node));else s.textContent=p.text;return s};return texts.map(t=>{const panel=document.createElement('section');panel.innerHTML='<div data-saved-review-focus hidden></div><div data-saved-review-text></div>';try{const parts=savedHomeworkReviewParts(t),nodes=parts.map(node);panel.querySelector('[data-saved-review-text]').replaceChildren(...nodes);savedHomeworkReviewFocus(panel,parts,nodes)}catch(e){return {error:e.message}}const nav=panel.querySelector('[data-saved-review-focus]');return {hidden:nav.hidden,verbatim:panel.querySelector('[data-saved-review-text]').textContent===t,rows:[...nav.querySelectorAll('.saved-review-focus-row')].map(x=>[x.querySelector('strong').textContent,...[...x.querySelectorAll('button')].map(b=>b.textContent+'|'+b.getAttribute('aria-label'))])}})},[savedSource,[neutral,neutral.replace('卷面作答：未能确认','卷面作答：原件作答栏留空（程序核对《虚构照片.png》第1行）'),neutral.replace('卷面作答：未能确认','卷面作答：本题尚未检查，待补查'),none,none+'\n\n请对照原题核对后保存；本轮结果不代表作业已完成或已经掌握。']]);
  const one={hidden:false,verbatim:true,rows:[['待补查 1 题','虚构照片卷 第1题|查看 虚构照片卷 第1题']]},alone={hidden:true,verbatim:true,rows:[]};
  assert.deepEqual(edited,[one,one,one,alone,alone]);
  // The saved check is offered to this answer only as the previous round.
  if(!await panel().locator(':scope > details').evaluate(x=>x.open))await panel().locator(':scope > details > summary').click();await until(async()=>await panel().locator('[data-homework-review-sources] [data-review-source]').count()===1,'saved check offered');
  assert.deepEqual(await panel().locator('[data-homework-review-sources] select option').evaluateAll(xs=>xs.map(x=>x.value)),['previous']);
  const final=await audit();assert.equal(final.calls.length,1);assert(final.calls.every(c=>JSON.stringify(c.raw)===JSON.stringify(c.original)));
  assert.deepEqual(final.tables.task_updates,content.tables.task_updates,'checking does not mark the task completed');assert.deepEqual(errors,[]);assert.deepEqual(foreign,[]);assert.deepEqual(bad,[]);assert.deepEqual(dialogs,[]);
  results.push({width,commit:process.env.HOMEWORK_CONTEXT_COMMIT,model_fixed_returns:1,real_models:0,family_entry_publication_omitted:true,school_publication_kept:true,roles_explicit:true,undecided_zero_model:true,inspection_live:true,save_503_zero_write:true,reopen_focus:groups,saved_text_states_not_promoted:true,zero_question_text_alone:true,verbatim_text:true,page_errors:errors,foreign_requests:foreign});
  await page.close();page=null;results.at(-1).owned_demo_terminal=await server.stop();server=null;
 }
 if(proof)fs.writeFileSync(path.join(proof,'result.json'),JSON.stringify(results,null,2)+'\n');console.log(JSON.stringify(results));
}catch(e){if(page&&proof)await shot('failure').catch(()=>{});console.error(e.stack);process.exitCode=1}finally{if(page)await page.close().catch(()=>{});if(server)await server.stop();if(browser)await browser.close().catch(()=>{})}})();
