// Disposable synthetic demo only. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON and RECORD_LINK_UI_PROOF_DIR. No family account or model calls.
const assert=require('node:assert/strict'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises'),{randomUUID}=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function demoServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let error='';proc.stdout.resume();proc.stderr.on('data',b=>error+=String(b));proc.on('error',e=>error=e.message);
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{await eventually(async()=>{if(proc.exitCode!==null)throw Error(error||'Demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo');return{url,stop}}catch(e){await stop();throw e}
}
const fs=require('node:fs/promises'),path=require('node:path');(async()=>{let browser,server;const checks=[];try{
 server=await demoServer();const url=server.url;browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 for(const width of [360,1440]){
  const context=await browser.newContext({viewport:{width,height:900}}),p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  const read=async()=>fetch(url+'api/state').then(r=>r.json());let state=await read();const kid=state.children[0].name;
  const post=async(route,body)=>{const r=await fetch(url+route,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(body)});const out=await r.json();assert(r.ok,JSON.stringify(out));return out};
  const task=async(child,title)=>(await post('api/task/new',{request_key:randomUUID(),child,title,box:'inbox',category:'homework',due:state.today,action:'虚构：核对原有材料'})).task;
  const a=await task(kid,'虚构听写甲 '+width),b=await task(kid,'虚构听写乙 '+width),other=await task(state.children[1].name,'另一孩子任务 '+width);
  await post('api/task',{id:a.id,status:'已完成',note:'虚构：已经核对完成'});
  const raw=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=','base64');
  const up=await fetch(url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'X-File-Name':'synthetic-sheet.png'},body:raw}).then(r=>r.json());
  const saved=await post('api/record',{child:kid,day:state.today,category:'学习进展',subject:'英语',title:'虚构独立错题 '+width,note:'虚构原答：yestoday',source:'试卷 / 作业核对',attachments:[up.attachment.id],transcript:'虚构核对转写',transcript_state:'已核对'}),id=saved.record_id;
  state=await read();const before=state.records.find(r=>r.id===id),taskBefore=state.tasks.find(t=>t.id===a.id).update;
  await p.goto(url);await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');
  const openRecord=async()=>{await p.locator('nav [data-page=more]').click();await p.locator('.more-links [data-page=growth]').click();await p.locator('[data-record="'+id+'"]').first().click();await p.locator('#recordDialog[open]').waitFor()};
  await openRecord();const select=p.locator('#recordTaskSelect'),save=p.locator('#saveRecordTaskLink'),status=p.locator('#recordTaskLinkStatus');
  assert.equal(await select.locator('option[value="'+other.id+'"]').count(),0);assert.equal(await select.inputValue(),'');
  await p.locator('#recordForm [name=note]').fill('未保存的家长补充');await select.selectOption(a.id);
  await p.locator('#recordForm [type=submit]').click();assert.match(await p.locator('#recordError').innerText(),/任务选择尚未保存/);assert(await p.locator('#recordDialog').evaluate(x=>x.open));
  const bodies=[];let attempt=0;await p.route('**/api/record/task-link',async r=>{bodies.push(r.request().postDataJSON());if(++attempt===1){await r.fetch();return r.abort('failed')}return r.continue()});
  await save.click();await eventually(async()=>/结果尚未核对/.test(await status.innerText()),'lost reply');assert(await select.isDisabled());assert(await p.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented}));await p.keyboard.press('Escape');assert(await p.locator('#recordDialog').evaluate(x=>x.open));
  await p.locator('#recordForm [type=submit]').click();assert.match(await p.locator('#recordError').innerText(),/任务关联保存结果尚未核对/);
  await save.click();await eventually(async()=>/任务关联已保存/.test(await status.innerText()),'same request retry');assert.deepEqual(bodies[0],bodies[1]);await p.unroute('**/api/record/task-link');
  assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'未保存的家长补充');state=await read();let record=state.records.find(r=>r.id===id);assert.equal(record.note,before.note);assert.equal(record.source,before.source);assert.deepEqual(record.attachments,before.attachments);assert.equal(record.transcript,before.transcript);assert.deepEqual(state.tasks.find(t=>t.id===a.id).update,taskBefore);
  // Another parent changes the link while this form remains open: preserve the local choice and text.
  await post('api/record/task-link',{record_id:id,child:kid,task_id:b.id,expected_linked_at:record.linked_task_at});await select.selectOption('');await save.click();await eventually(async()=>/别处更改/.test(await status.innerText()),'conflict');assert.equal(await select.inputValue(),'');assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'未保存的家长补充');
  await p.locator('#refreshRecordTaskLink').click();await eventually(async()=>/已读取当前关联/.test(await status.innerText()),'refresh link');assert.match(await p.locator('#recordTaskCurrent').innerText(),new RegExp(b.title));assert.equal(await select.inputValue(),'');
  await save.click();await eventually(async()=>/关联已解除/.test(await status.innerText()),'unlink');record=(await read()).records.find(r=>r.id===id);assert.equal(record.linked_task_id,'');assert(record.linked_task_at);
  // Session expiry keeps the chosen target and the ordinary record draft, then explicit retry succeeds.
  await select.selectOption(a.id);await p.route('**/api/record/task-link',r=>r.fulfill({status:401,json:{error:'虚构登录已过期'}}));await save.click();await p.locator('#parentLoginDialog[open]').waitFor();assert.equal(await select.inputValue(),a.id);await p.keyboard.press('Escape');await p.unroute('**/api/record/task-link');await save.click();await eventually(async()=>/任务关联已保存/.test(await status.innerText()),'login retry');
  await p.locator('#recordForm [type=submit]').click();await eventually(()=>p.locator('#recordDialog').evaluate(x=>!x.open),'ordinary content save');await p.reload();await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');await openRecord();assert.equal(await select.inputValue(),a.id);assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'未保存的家长补充');await p.keyboard.press('Escape');
  // Same task shows the original record, image, transcript and provenance; no duplicate or task completion changes.
  await p.locator('nav [data-page=home]').click();await p.locator('[data-task-all="homework"]').click();await p.locator('[data-task-box="已完成"]').click();await p.locator('[data-task="'+a.id+'"]').first().click();
  const history=p.locator('#taskFeedbackHistory');assert.match(await history.innerText(),/虚构核对转写/);assert.match(await history.innerText(),/试卷 \/ 作业核对/);assert.equal(await history.locator('img').count(),1);assert.equal(await history.locator('[data-task-feedback-edit]').count(),0);
  await history.locator('[data-record="'+id+'"]').click();assert(await p.locator('#recordDialog').evaluate(x=>x.open));assert.equal(await select.inputValue(),a.id);
  assert.equal(await p.locator('#recordDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  if(process.env.RECORD_LINK_UI_PROOF_DIR){await fs.mkdir(process.env.RECORD_LINK_UI_PROOF_DIR,{recursive:true});await p.locator('#recordTaskLink').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.RECORD_LINK_UI_PROOF_DIR,'record-link-'+width+'.png')})}
  // New task stays inside the same record; no inference from its title, date or note.
  await select.selectOption('');await save.click();await eventually(async()=>/关联已解除/.test(await status.innerText()),'unlink before explicit new task');
  await p.locator('#recordTaskCreate > summary').click();
  const title=p.locator('#recordTaskTitle'),due=p.locator('#recordTaskDue'),create=p.locator('#createRecordTask');
  assert.equal(await title.inputValue(),'');assert.equal(await due.inputValue(),'');assert.equal(await p.locator('#recordTaskCategory').inputValue(),'');
  await create.click();assert.match(await status.innerText(),/请填写新事项标题/);
  const wantedTitle='虚构：两处听写再核对 '+width;await title.fill(wantedTitle);await p.locator('#recordTaskCategory').selectOption('homework');await p.locator('#recordTaskAction').fill('家长明确：先读再写两处');
  await p.locator('#recordForm [name=note]').fill('虚构：这段原记录补充仍未保存');
  await p.locator('#recordForm [type=submit]').click();assert.match(await p.locator('#recordError').innerText(),/新事项草稿尚未保存/);
  // The other parent links first: rejection leaves both drafts, then explicit refresh and unlink allow a new choice.
  record=(await read()).records.find(r=>r.id===id);await post('api/record/task-link',{record_id:id,child:kid,task_id:b.id,expected_linked_at:record.linked_task_at});
  await create.click();await eventually(async()=>/已关联事项/.test(await status.innerText()),'create conflict');assert.equal(await title.inputValue(),wantedTitle);
  await p.locator('#refreshRecordTaskLink').click();await eventually(async()=>/已读取当前关联/.test(await status.innerText()),'create conflict refresh');assert(await create.isDisabled());assert.equal(await title.inputValue(),wantedTitle);
  await select.selectOption('');await save.click();await eventually(async()=>/关联已解除/.test(await status.innerText()),'explicit unlink keeps new draft');assert.equal(await title.inputValue(),wantedTitle);
  // Expired login preserves the exact creation request; a subsequent real write loses its reply, then replays once.
  let createAttempt=0;const requests=[];await p.route('**/api/record/task-create',async r=>{requests.push(r.request().postDataJSON());createAttempt++;if(createAttempt===1)return r.fulfill({status:401,json:{error:'虚构登录过期'}});if(createAttempt===2){await r.fetch();return r.abort('failed')}return r.continue()});
  const beforeCreate=await read();await create.click();await p.locator('#parentLoginDialog[open]').waitFor();await p.keyboard.press('Escape');assert(await title.isDisabled());assert(await save.isDisabled());
  await create.click();await eventually(async()=>/结果尚未核对/.test(await status.innerText()),'create lost reply');await p.keyboard.press('Escape');assert(await p.locator('#recordDialog').evaluate(x=>x.open));
  if(process.env.RECORD_LINK_UI_PROOF_DIR){await p.locator('#recordTaskCreate').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.RECORD_LINK_UI_PROOF_DIR,'record-create-pending-'+width+'.png')})}
  await create.click();await eventually(async()=>/新事项与关联已保存/.test(await status.innerText()),'create replay success');await p.unroute('**/api/record/task-create');assert.deepEqual(requests[0],requests[1]);assert.deepEqual(requests[1],requests[2]);
  state=await read();const made=state.tasks.find(t=>t.title===wantedTitle);assert(made);assert.equal(state.tasks.length,beforeCreate.tasks.length+1);assert.equal(state.records.length,beforeCreate.records.length);assert.equal(made.child,kid);assert.equal(made.due,'无明确截止');assert(!made.update);assert.equal(made.original_status,'待跟进');
  record=state.records.find(r=>r.id===id);assert.equal(record.linked_task_id,made.id);assert.equal(record.source,before.source);assert.deepEqual(record.attachments,before.attachments);assert.equal(record.transcript,before.transcript);assert.equal(record.note,'未保存的家长补充');assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'虚构：这段原记录补充仍未保存');
  assert.equal(await title.inputValue(),'');assert.equal(await select.inputValue(),made.id);assert.equal(await p.locator('#recordDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  await p.locator('#recordForm [type=submit]').click();await eventually(()=>p.locator('#recordDialog').evaluate(x=>!x.open),'save original after create');await p.reload();await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');await openRecord();assert.equal(await select.inputValue(),made.id);assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'虚构：这段原记录补充仍未保存');await p.keyboard.press('Escape');
  await p.locator('nav [data-page=home]').click();await p.locator('[data-task="'+made.id+'"]').first().click();assert.equal(await p.locator('#taskFeedbackHistory [data-record="'+id+'"]').count(),1);assert.equal(await p.locator('#taskFeedbackHistory img').count(),1);await p.keyboard.press('Escape');
  state=await read();assert.equal(state.records.filter(r=>r.id===id).length,1);assert.deepEqual(state.tasks.find(t=>t.id===a.id).update,taskBefore);assert.deepEqual(errors,[]);await context.close();checks.push(width+': same-child link, lost-reply retry, conflict refresh/unlink, login expiry, draft preservation, original task readback, explicit new task, conflict refresh, login/lost-reply retries, preserved drafts and layout');
 }
 console.log(JSON.stringify({passed:true,checks,syntheticOnly:true,realPhoneTested:false}));
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e.stack||e);process.exitCode=1});
