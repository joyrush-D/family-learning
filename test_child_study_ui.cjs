// Run: PLAYWRIGHT_MODULE=/path/to/playwright PLAYWRIGHT_CHANNEL=chrome node test_child_ui.cjs
// Isolated synthetic demo, including a /family/ proxy. Never uses household data.
const assert=require('node:assert/strict');
const http=require('node:http');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises');
const {randomUUID}=require('node:crypto');
const fs=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const secretNote='SYNTHETIC_PARENT_PRIVATE_NOTE',otherBook='SYNTHETIC_OTHER_CHILD_BOOK';
async function eventually(check,label,timeout=10000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function listen(server){server.listen(0,'127.0.0.1');await once(server,'listening');return server.address().port}
async function launchDemo(){
 const reserve=http.createServer(),port=await listen(reserve);await new Promise(r=>reserve.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];env.FAMILY_CHILD_COOKIE_PATH='/family/child/';
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let failed=null;child.on('error',e=>failed=e);child.stdout.resume();child.stderr.resume();
 const stop=async()=>{if(child.exitCode!==null||child.signalCode!==null)return;const done=once(child,'exit');child.kill('SIGINT');await Promise.race([done,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await done}};
 let proxy;
 try{
  await eventually(async()=>{if(failed)throw failed;if(child.exitCode!==null)throw Error('Demo exited');try{return (await fetch('http://127.0.0.1:'+port+'/api/state')).ok}catch{return false}},'demo ready');
  proxy=http.createServer((req,res)=>{
   if(!req.url.startsWith('/family/')){res.writeHead(404).end();return}
   const upstream=http.request({hostname:'127.0.0.1',port,path:req.url.slice('/family'.length),method:req.method,headers:{...req.headers,host:'localhost:'+port}},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res)});
   upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end()});req.pipe(upstream);
  });
  const publicPort=await listen(proxy);return {url:'http://127.0.0.1:'+publicPort+'/family/',stop:async()=>{proxy.closeAllConnections?.();await new Promise(r=>proxy.close(r));await stop()}};
 }catch(e){if(proxy)proxy.close();await stop();throw e}
}
(async()=>{
 let server,browser;const contexts=[],checks=[],shots=process.env.CHILD_STUDY_UI_PROOF_DIR;
 try{
  server=await launchDemo();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  if(shots)await fs.mkdir(shots,{recursive:true});
  const parentContext=await browser.newContext({viewport:{width:1440,height:980}});contexts.push(parentContext);const parent=await parentContext.newPage();
  const initial=await(await fetch(server.url+'api/state')).json(),who=initial.children[0].id,other=initial.children[1].id,day=initial.today;
  const post=async(route,body)=>{const r=await fetch(server.url+'api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':initial.token},body:JSON.stringify(body)});const v=await r.json();assert.equal(r.status,200,v.error);return v};
  const read=async(id=who)=>await(await fetch(server.url+'api/study?'+new URLSearchParams({child_id:id,day}))).json();
  const parentItem=async(title,id=who)=>post('study/item',{child_id:id,day,request_key:randomUUID(),version:0,title,planned_minutes:15});
  await parentItem(otherBook,other);
  await parent.goto(server.url);await parent.locator('nav [data-page="more"]').click();await parent.locator('.more-links [data-page="settings"]').click();await parent.locator('[data-child-access="'+who+'"]').click();const share=parent.locator('[data-child-study="'+who+'"]');await share.waitFor();assert.equal(await share.isChecked(),false);
  await parent.locator('[data-child-invite="'+who+'"]').click();await eventually(async()=>!!await parent.locator('#childInviteLink').inputValue(),'invite');
  const invite=await parent.locator('#childInviteLink').inputValue(),childContext=await browser.newContext({viewport:{width:360,height:900}});contexts.push(childContext);const child=await childContext.newPage(),errors=[];child.on('pageerror',e=>errors.push(e.message));
  await child.goto(invite);await child.locator('#journey').waitFor();let cs=await(await childContext.request.get(server.url+'child/api/state')).json();assert.equal(cs.study_enabled,false);
  let denied=await childContext.request.post(server.url+'child/api/study/state',{data:{day},headers:{'X-Child-CSRF':cs.csrf}});assert.equal(denied.status(),403);
  await share.click();await eventually(()=>share.isChecked(),'parent grants daily homework');await child.locator('#refresh').click();await child.locator('#study-tab').click();await child.locator('#study-add').waitFor();
  cs=await(await childContext.request.get(server.url+'child/api/state')).json();assert.equal(cs.study_enabled,true);
  const own=await(await childContext.request.post(server.url+'child/api/study/state',{data:{day},headers:{'X-Child-CSRF':cs.csrf}})).json();assert.equal(JSON.stringify(own).includes(otherBook),false);assert.equal('available_tasks' in own,false);assert.equal('week' in own,false);
  checks.push('parent explicitly enables homework; session-scoped state excludes other child and parent task inbox');
  await parent.locator('[data-close="readingDialog"]').last().click();
  for(const width of [360,1440]){
   await child.setViewportSize({width,height:900});const title='虚构自主功课 '+width,add=child.locator('#study-add');
   await add.locator('[name="title"]').fill(title);await add.locator('[name="planned_minutes"]').fill('20');await add.locator('[name="subject"]').fill('数学');await add.locator('[type="submit"]').click();
   await eventually(async()=>(await read()).items.some(i=>i.title===title),'child reports homework');let item=(await read()).items.find(i=>i.title===title);const id=item.id,row=child.locator('#study-items [data-study-item="'+id+'"]');await row.waitFor();
   await row.locator('[data-study-action="start"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).status==='running','starts timer');await delay(120);
   await row.locator('[data-study-action="pause"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).status==='paused','pause persists');
   await row.locator('[data-study-edit="finish"]').click();let edit=child.locator('#study-edit-form');await edit.locator('[value="需要帮助"]').check();await edit.locator('[name="actual_minutes"]').fill('12');await edit.locator('[name="assistance"]').selectOption('少量提示');await edit.locator('[name="note"]').fill('虚构反馈：最后一题读不懂，想先一起看题目。');
   if(width===360){
    let lost=true;const bodies=[];await child.route('**/child/api/study/action',async r=>{bodies.push(r.request().postDataJSON());if(lost){lost=false;assert.equal((await r.fetch()).status(),200);await r.abort('failed')}else await r.continue()});
    await edit.locator('[type="submit"]').click();const retry=child.getByRole('button',{name:'核对并重试这次保存'});await retry.waitFor();assert.match(await edit.locator('[name="note"]').inputValue(),/想先一起/);await retry.click();await eventually(async()=>(await read()).items.find(i=>i.id===id).result==='需要帮助','retry original result');await retry.waitFor({state:'hidden'});assert.deepEqual(bodies[0],bodies[1]);await child.unroute('**/child/api/study/action');
   }else await edit.locator('[type="submit"]').click();
   await eventually(async()=>(await read()).items.find(i=>i.id===id).result_actor==='child','child provenance');await row.getByText('需要帮助',{exact:false}).first().waitFor();
   await parent.goto(server.url);await parent.locator('nav [data-page="more"]').click();await parent.locator('.more-links [data-page="study"]').click();await parent.locator('select[data-study-child]').selectOption(who);await parent.locator('[data-study-ready]').waitFor();const parentRow=parent.locator('[data-study-item="'+id+'"]');await parentRow.getByText('孩子自述',{exact:false}).waitFor();assert.match(await parentRow.innerText(),/想先一起看题目/);
   if(width===360){
    await row.locator('[data-study-edit="item"]').click();edit=child.locator('#study-edit-form');await edit.locator('[name="planned_minutes"]').fill('35');item=(await read()).items.find(i=>i.id===id);
    await post('study/item',{child_id:who,day,id,version:item.version,request_key:randomUUID(),planned_minutes:25});await edit.locator('[type="submit"]').click();const ack=child.getByRole('button',{name:'已核对新状态，保留输入继续'});await ack.waitFor();assert.equal(await edit.locator('[name="planned_minutes"]').inputValue(),'35');await ack.click();await edit.locator('[type="submit"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).planned_minutes===35,'conflict preserves child draft');
   }
   await row.locator('[data-study-action="start"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).status==='running','resume after help');await row.locator('[data-study-edit="finish"]').click();edit=child.locator('#study-edit-form');await edit.locator('[value="完成"]').check();await edit.locator('[name="actual_minutes"]').fill('18');await edit.locator('[type="submit"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).result==='完成','self-reported complete');
   item=(await read()).items.find(i=>i.id===id);assert.equal(item.source_task_status,'待跟进','child cannot close school task');assert.equal(item.result_actor,'child');
   assert.equal(await child.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'child fits '+width);assert.equal(await child.locator('#child-study button:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'44px child controls');
   await child.evaluate(()=>scrollTo(0,0));if(shots)await child.screenshot({path:path.join(shots,'synthetic-child-study-'+width+'.png'),fullPage:true});
   await parent.goto(server.url);await parent.locator('nav [data-page="more"]').click();await parent.locator('.more-links [data-page="study"]').click();await parent.locator('select[data-study-child]').selectOption(who);await parent.locator('[data-study-ready]').waitFor();const confirmButton=parentRow.getByRole('button',{name:'核对孩子的结果'});assert.equal(await confirmButton.evaluate(el=>el.classList.contains('primary')),true,'child self-report uses the primary review action');assert.match(await parent.locator('.study-budget').innerText(),/孩子自述，待家长核对/,'budget identifies child self-report awaiting review');const completed=parent.locator('[data-study-item]').filter({hasText:'家长已确认'});if(await completed.count()){const ids=await parent.locator('[data-study-item]').evaluateAll(nodes=>nodes.map(node=>node.dataset.studyItem));const completedIDs=await completed.evaluateAll(nodes=>nodes.map(node=>node.dataset.studyItem));assert.ok(ids.indexOf(String(id))<ids.indexOf(String(completedIDs[0])),'current child self-report precedes parent-confirmed work');}await confirmButton.click();const confirm=parent.locator('[data-study-form="finish"]');assert.equal(await confirm.locator('[value="完成"]').isChecked(),true);await confirm.getByRole('button',{name:'核对并保存'}).click();
   await eventually(async()=>(await read()).items.find(i=>i.id===id).result_actor==='parent','parent confirms');item=(await read()).items.find(i=>i.id===id);assert.equal(item.source_task_status,'已完成');
   await child.locator('#refresh').click();await eventually(async()=>await row.locator('[data-study-action],[data-study-edit]').count()===0,'confirmed item read only');assert.match(await row.innerText(),/家长已确认/);
   await parent.evaluate(()=>scrollTo(0,0));if(shots)await parent.screenshot({path:path.join(shots,'synthetic-parent-study-'+width+'.png'),fullPage:true});
   checks.push(width+'px: report, estimate, timer, help, self-report, parent confirmation, refresh and layout');
  }
  // The same five fictional teacher requirements (the saved Flash27 words) entered by the parent's existing entries: a
  // task each, then 作业计时 adds it to the child's day; nothing is arranged for the child automatically.
  const teacherItems=[['语文：完成《星芽阅读练习册》第28页第1、2题','完成《星芽阅读练习册》第28页第1、2题。\n答案写在练习册上。\n今晚完成，明天早上交。\n提交要求：明天早上交练习册。',['答案写在练习册上。','今晚完成，明天早上交练习册。']],
   ['数学：完成《数格练习册》第34页第1—4题','完成《数格练习册》第34页第1—4题。\n第34页第4题要把计算过程写完整，写在原题下面即可。\n今晚完成，明天早上交。\n提交要求：明天早上交练习册。',['第34页第4题要把计算过程写完整，写在原题下面即可。','今晚完成，明天早上交练习册。']],
   ['英语：跟读Unit 4两遍并家长签字','听录音跟读 Unit 4 A day at the lake 两遍。\n读完请家长在记录本上签字。\n今晚完成，明天早读检查记录本。',['听录音跟读 Unit 4 A day at the lake 两遍。','读完请家长在记录本上签字。','今晚完成，明天早读检查记录本。']],
   ['交《秋季校园开放日回执》','《秋季校园开放日回执》今晚请家长签字。\n明天早上让孩子交给班主任。',['《秋季校园开放日回执》今晚请家长签字。','明天早上让孩子交给班主任。']],
   ['科学：带一个空透明塑料瓶','明天来校带一个空透明塑料瓶，科学课用。',['明天来校带一个空透明塑料瓶，科学课用。']]];
  const before=(await read()).items.length,teacherIDs=[];
  for(const [title,action] of teacherItems){const made=await post('task/new',{child:initial.children[0].name,title,action,due:'2026-10-20',request_key:randomUUID().replaceAll('-','')});const added=await post('study/item',{child_id:who,day,request_key:randomUUID(),version:0,task_id:made.task.id,planned_minutes:20});teacherIDs.push(added.item?.id||(await read()).items.find(i=>i.task_id===made.task.id).id)}
  assert.equal((await read()).items.length,before+5,'only the five the parent added');
  // The same entry with the parent's own next step (记一件事 advice -> focus.next_action): one identical to the saved
  // action (not the title) is that action and reads once, as before; a different next step keeps both.
  const nextItems=[['英语：抄写Unit 4单词','把Unit 4单词每个抄写两遍。\n明天早读交抄写本。',null,['把Unit 4单词每个抄写两遍。','明天早读交抄写本。']],
   ['数学：完成口算本第8页','口算本第8页全部完成。\n明天交给课代表。','先做前两行，做完请家长看一眼。',['口算本第8页全部完成。','明天交给课代表。']]],nextIDs=[];
  for(const [title,action,next] of nextItems){const made=await post('task/new',{child:initial.children[0].name,title,action,advice:next??action,due:'2026-10-20',request_key:randomUUID().replaceAll('-','')});const added=await post('study/item',{child_id:who,day,request_key:randomUUID(),version:0,task_id:made.task.id,planned_minutes:15});nextIDs.push(added.item?.id||(await read()).items.find(i=>i.task_id===made.task.id).id)}
  assert.equal((await read()).items.length,before+7,'and only the two with a next step');
  for(const width of [360,1440])for(const pass of ['open','reopen']){
   await child.setViewportSize({width,height:900});if(pass==='open')await child.locator('#refresh').click();else{await child.reload();await child.locator('#study-tab').click()}
   for(const [i,[title,action,want]] of teacherItems.entries()){
    const card=child.locator('#study-items [data-study-item="'+teacherIDs[i]+'"]');await card.waitFor();
    assert.equal(await card.locator('h3').innerText(),title,width+' '+pass+' child card title as saved');
    assert.deepEqual(await card.locator('.study-requirement-lines li, p.study-requirement-lines').allInnerTexts(),want,width+' '+pass+' '+title+' each own condition once');
    const text=await card.innerText();assert.doesNotMatch(text,/提交要求/);
    if(i<2)assert.equal(text.split(title.replace(/^[^：]+：/,'')).length-1,1,title+' title words once');
    assert.equal((await read()).items.find(x=>x.id===teacherIDs[i]).source_task_action,action,'saved words unchanged');
   }
   for(const [i,[title,action,next,want]] of nextItems.entries()){
    const card=child.locator('#study-items [data-study-item="'+nextIDs[i]+'"]');await card.waitFor();const saved=(await read()).items.find(x=>x.id===nextIDs[i]);
    assert.equal(await card.locator('h3').innerText(),title);assert.equal(saved.source_task_action,action,'saved action unchanged');assert.equal(saved.source_task_next_action,next??action,'the parent\'s saved next step');
    assert.deepEqual(await card.locator('.study-requirement-lines li, p.study-requirement-lines').allInnerTexts(),want,width+' '+pass+' '+title+' the action\'s own lines');
    const text=await card.innerText();
    for(const line of want)assert.equal(text.split(line).length-1,1,width+' '+pass+' '+title+' reads once: '+line);
    if(next===null){assert.equal(text.split('要做：').length-1,1,title+' one requirement');assert.doesNotMatch(text,/要求：/,title+' an identical next step is no second copy')}
    else{assert.equal(text.split('要做：'+next).length-1,1,title+' the different next step stays');assert.equal(text.split('要求：').length-1,1,title+' and the action stays below it')}
   }
   assert.equal(await child.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'child fits '+width);assert.equal(await child.locator('#child-study button:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'44px child controls');
   if(shots&&pass==='reopen'){await child.evaluate(()=>scrollTo(0,0));await child.screenshot({path:path.join(shots,'synthetic-child-teacher-items-'+width+'.png'),fullPage:true})}
  }
  checks.push('five teacher requirements added by the parent read title, own conditions once and keep the saved words on the child card at 360/1440 and after reopen');
  checks.push('a parent next step identical to the saved action reads once; a different next step and the action both stay, at 360/1440 and after reopen');
  await parent.goto(server.url);await parent.locator('nav [data-page="more"]').click();await parent.locator('.more-links [data-page="settings"]').click();await parent.locator('[data-child-access="'+who+'"]').click();await parent.locator('[data-child-study="'+who+'"]').click();await eventually(async()=>!(await(await fetch(server.url+'api/child-access')).json()).children.find(c=>c.child_id===who).study_enabled,'study access removed');await child.locator('#refresh').click();await child.locator('#child-study').waitFor({state:'hidden'});assert.equal((await child.locator('#study-items').textContent()).includes('虚构自主功课'),false,'study DOM removed');assert.equal(await child.locator('#journey').isVisible(),true,'reading entrance remains');
  assert.deepEqual(errors,[]);checks.push('revoke daily homework removes its data while reading entrance stays usable');
  console.log(JSON.stringify({passed:checks.length,checks,syntheticOnly:true,actualPhoneTested:false,screenshots:shots||null},null,2));
 }finally{for(const c of contexts)await c.close();await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
