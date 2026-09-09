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
  await parent.goto(server.url);await parent.locator('[data-child-access="'+who+'"]').click();const share=parent.locator('[data-child-study="'+who+'"]');await share.waitFor();assert.equal(await share.isChecked(),false);
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
   await parent.goto(server.url);await parent.locator('[data-study-child="'+who+'"]').click();await parent.locator('[data-study-ready]').waitFor();const parentRow=parent.locator('[data-study-item="'+id+'"]');await parentRow.getByText('孩子自述',{exact:false}).waitFor();assert.match(await parentRow.innerText(),/想先一起看题目/);
   if(width===360){
    await row.locator('[data-study-edit="item"]').click();edit=child.locator('#study-edit-form');await edit.locator('[name="planned_minutes"]').fill('35');item=(await read()).items.find(i=>i.id===id);
    await post('study/item',{child_id:who,day,id,version:item.version,request_key:randomUUID(),planned_minutes:25});await edit.locator('[type="submit"]').click();const ack=child.getByRole('button',{name:'已核对新状态，保留输入继续'});await ack.waitFor();assert.equal(await edit.locator('[name="planned_minutes"]').inputValue(),'35');await ack.click();await edit.locator('[type="submit"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).planned_minutes===35,'conflict preserves child draft');
   }
   await row.locator('[data-study-action="start"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).status==='running','resume after help');await row.locator('[data-study-edit="finish"]').click();edit=child.locator('#study-edit-form');await edit.locator('[value="完成"]').check();await edit.locator('[name="actual_minutes"]').fill('18');await edit.locator('[type="submit"]').click();await eventually(async()=>(await read()).items.find(i=>i.id===id).result==='完成','self-reported complete');
   item=(await read()).items.find(i=>i.id===id);assert.equal(item.source_task_status,'待跟进','child cannot close school task');assert.equal(item.result_actor,'child');
   assert.equal(await child.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'child fits '+width);assert.equal(await child.locator('#child-study button:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'44px child controls');
   await child.evaluate(()=>scrollTo(0,0));if(shots)await child.screenshot({path:path.join(shots,'synthetic-child-study-'+width+'.png'),fullPage:true});
   await parent.goto(server.url);await parent.locator('[data-study-child="'+who+'"]').click();await parent.locator('[data-study-ready]').waitFor();const confirmButton=parentRow.getByRole('button',{name:'核对孩子的结果'});assert.equal(await confirmButton.evaluate(el=>el.classList.contains('primary')),true,'child self-report uses the primary review action');assert.match(await parent.locator('.study-budget').innerText(),/孩子自述，待家长核对/,'budget identifies child self-report awaiting review');const completed=parent.locator('[data-study-item]').filter({hasText:'家长已确认'});if(await completed.count()){const ids=await parent.locator('[data-study-item]').evaluateAll(nodes=>nodes.map(node=>node.dataset.studyItem));const completedIDs=await completed.evaluateAll(nodes=>nodes.map(node=>node.dataset.studyItem));assert.ok(ids.indexOf(String(id))<ids.indexOf(String(completedIDs[0])),'current child self-report precedes parent-confirmed work');}await confirmButton.click();const confirm=parent.locator('[data-study-form="finish"]');assert.equal(await confirm.locator('[value="完成"]').isChecked(),true);await confirm.getByRole('button',{name:'核对并保存'}).click();
   await eventually(async()=>(await read()).items.find(i=>i.id===id).result_actor==='parent','parent confirms');item=(await read()).items.find(i=>i.id===id);assert.equal(item.source_task_status,'已完成');
   await child.locator('#refresh').click();await eventually(async()=>await row.locator('[data-study-action],[data-study-edit]').count()===0,'confirmed item read only');assert.match(await row.innerText(),/家长已确认/);
   await parent.evaluate(()=>scrollTo(0,0));if(shots)await parent.screenshot({path:path.join(shots,'synthetic-parent-study-'+width+'.png'),fullPage:true});
   checks.push(width+'px: report, estimate, timer, help, self-report, parent confirmation, refresh and layout');
  }
  await parent.goto(server.url);await parent.locator('[data-child-access="'+who+'"]').click();await parent.locator('[data-child-study="'+who+'"]').click();await eventually(async()=>!(await(await fetch(server.url+'api/child-access')).json()).children.find(c=>c.child_id===who).study_enabled,'study access removed');await child.locator('#refresh').click();await child.locator('#child-study').waitFor({state:'hidden'});assert.equal((await child.locator('#study-items').textContent()).includes('虚构自主功课'),false,'study DOM removed');assert.equal(await child.locator('#journey').isVisible(),true,'reading entrance remains');
  assert.deepEqual(errors,[]);checks.push('revoke daily homework removes its data while reading entrance stays usable');
  console.log(JSON.stringify({passed:checks.length,checks,syntheticOnly:true,actualPhoneTested:false,screenshots:shots||null},null,2));
 }finally{for(const c of contexts)await c.close();await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
