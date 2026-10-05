// A lost save reply followed by a later correction must not trap the parent in a permanent retry lock.
const assert=require('node:assert/strict'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises'),{randomUUID}=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check){for(let n=0;n<250;n++){if(await check())return;await delay(40)}throw Error('Timed out')}
async function demo(){
 const sock=net.createServer();sock.listen(0,'127.0.0.1');await once(sock,'listening');const port=sock.address().port;await new Promise(r=>sock.close(r));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:'ignore'}),url=`http://127.0.0.1:${port}/`;
 await until(async()=>{try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}});
 return {url,stop:async()=>{if(proc.exitCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2000)]);if(proc.exitCode===null){proc.kill('SIGKILL');await done}}};
}
(async()=>{let server,browser;try{
 server=await demo();browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 for(const width of [360,1440]){
  const state=await(await fetch(server.url+'api/state')).json(),child=state.children[0].name;
  const made=await fetch(server.url+'api/task/new',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({request_key:randomUUID(),child,title:`虚构重试作业 ${width}`,category:'homework',box:'inbox',due:state.today,action:'核对作答'})});
  assert(made.ok);const id=(await made.json()).task.id,p=await browser.newPage({viewport:{width,height:850}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(server.url);await p.locator(`[data-task="${id}"]`).first().click();
  await p.locator('#taskForm [name=note]').fill('虚构首次反馈');let attempts=0;
  await p.route('**/api/task/feedback',async route=>{
   attempts++;
   if(attempts!==1)return route.continue();
   const response=await route.fetch(),saved=await response.json();assert(response.ok);
   const record=(await(await fetch(server.url+'api/state')).json()).records.find(r=>r.id===saved.record_id);assert(record);
   const corrected=await fetch(server.url+'api/task/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({task_id:id,child,record_id:record.id,expected_created:record.created,day:record.day,category:record.category,note:'虚构另一位家长已更正',attachments:record.attachments})});assert(corrected.ok,await corrected.text());
   await route.abort('failed');
  });
  await p.locator('#saveTaskFeedback').click();await until(async()=>/保存结果尚未核对/.test(await p.locator('#taskError').innerText()));
  assert(await p.locator('#taskForm [name=note]').isDisabled());
  await p.route('**/api/state',route=>route.fulfill({status:503,json:{error:'虚构状态暂不可读'}}));
  await p.locator('#saveTaskFeedback').click();await until(async()=>/家庭记录暂时无法读取/.test(await p.locator('#taskError').innerText()));
  assert(await p.locator('#taskForm [name=note]').isDisabled(),'unverified result keeps the draft locked');
  await p.unroute('**/api/state');await p.locator('#saveTaskFeedback').click();
  await until(async()=>/已打开最新记录/.test(await p.locator('#taskFeedbackStatus').innerText()));
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构另一位家长已更正');assert(await p.locator('#taskForm [name=note]').isEnabled());
  assert.equal((await(await fetch(server.url+'api/state')).json()).records.filter(r=>r.source==='事项:'+id).length,1);
  assert.deepEqual(errors,[]);await p.reload();await p.locator(`[data-task="${id}"]`).first().click();assert.match(await p.locator('#taskFeedbackHistory').innerText(),/另一位家长已更正/);await p.close();
 }
 console.log('PASS: 360/1440 lost reply, later correction, verified unlock and reopen');
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e);process.exitCode=1});
