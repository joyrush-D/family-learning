// The list's compact progress line at 360/1440 through the existing task feedback entry: a no-write 503 and a lost reply
// keep one request; a later correction gives a 409 that opens the latest record without a duplicate; an explicit link
// shows on the same row; the other child sees nothing; the same row's 查看/补充反馈 reopens the saved feedback. Demo data only.
const assert=require('node:assert/strict'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises'),{randomUUID}=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check){for(let n=0;n<250;n++){if(await check())return;await delay(40)}throw Error('Timed out')}
async function proof(page,name){if(process.env.DAILY_PROGRESS_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.DAILY_PROGRESS_UI_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.DAILY_PROGRESS_UI_PROOF_DIR,name+'.png'),fullPage:true})}}
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
  const state=await(await fetch(server.url+'api/state')).json(),[a,b]=state.children,headers={'Content-Type':'application/json','X-Family-Token':state.token};
  const post=(path,body)=>fetch(server.url+path,{method:'POST',headers,body:JSON.stringify(body)}),feedback=async()=>(await(await fetch(server.url+'api/state')).json()).records.filter(r=>r.source==='事项:'+id);
  const made=await post('api/task/new',{request_key:randomUUID(),child:a.name,title:`虚构数学练习 ${width}`,category:'homework',box:'inbox',due:state.today,action:'完成练习册第12页第2至4题，写出计算过程'});
  assert(made.ok);const id=(await made.json()).task.id,p=await browser.newPage({viewport:{width,height:850}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(server.url);
  const line=()=>p.locator(`[data-task-progress="${id}"]`);
  assert.equal(await line().count(),0,'nothing saved: the original row only');
  await p.locator(`[data-task="${id}"]`).first().click();await p.locator('#taskForm [name=note]').fill('第3题进位错了');
  // 1: refused before any write (503); 2: saved but its reply is lost; 3: the same request again replays the one record.
  const keys=[];let attempts=0;
  await p.route('**/api/task/feedback',async route=>{
   attempts++;keys.push(route.request().postDataJSON().request_key);
   if(attempts===1)return route.fulfill({status:503,json:{error:'虚构服务暂不可写'}});
   if(attempts===2){const response=await route.fetch();assert(response.ok);return route.abort('failed')}
   return route.continue();
  });
  await p.locator('#saveTaskFeedback').click();await until(async()=>(await p.locator('#taskError').innerText()).trim()!=='');
  assert.equal((await feedback()).length,0,'the 503 wrote nothing');assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'第3题进位错了','the draft stays');
  await p.locator('#saveTaskFeedback').click();await until(async()=>/保存结果尚未核对/.test(await p.locator('#taskError').innerText()));
  await p.locator('#saveTaskFeedback').click();await until(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()));
  assert.equal(new Set(keys).size,1,'one request key across the 503, the lost reply and the retry');assert.equal((await feedback()).length,1,'no duplicate');
  await until(async()=>await line().count()>0&&/进展：反馈1条/.test(await line().first().innerText()));
  assert.doesNotMatch(await line().first().innerText(),/线索|错题/,'no clue or wrong record is made up');
  // A later correction by another parent before the lost reply is resent: 409, the latest record opens, still no duplicate.
  await p.unroute('**/api/task/feedback');await p.locator('#taskForm [name=note]').fill('第4题也要订正');let second=0;
  await p.route('**/api/task/feedback',async route=>{
   if(++second!==1)return route.continue();
   const response=await route.fetch(),saved=await response.json();assert(response.ok);
   const record=(await feedback()).find(r=>r.id===saved.record_id);
   const corrected=await post('api/task/feedback',{task_id:id,child:a.name,record_id:record.id,expected_created:record.created,day:record.day,category:record.category,note:'虚构另一位家长已更正',attachments:record.attachments});assert(corrected.ok,await corrected.text());
   await route.abort('failed');
  });
  await p.locator('#saveTaskFeedback').click();await until(async()=>/保存结果尚未核对/.test(await p.locator('#taskError').innerText()));
  await p.locator('#saveTaskFeedback').click();await until(async()=>/已打开最新记录|后来又被更正/.test(await p.locator('#taskFeedbackStatus').innerText()));
  assert.equal((await feedback()).length,2,'the 409 replay adds no third record');await p.unroute('**/api/task/feedback');
  // An explicit link of this child's wrong record shows on the same row; the other child's record cannot be linked.
  const wrong=await(await post('api/record',{child:a.name,day:state.today,category:'学习进展',subject:'数学',title:`数学错题：第3题 ${width}`,note:'进位漏写',source:'错题照片核对'})).json();
  const foreign=await(await post('api/record',{child:b.name,day:state.today,category:'学习进展',subject:'数学',title:`数学错题：第3题 ${width}`,note:'进位漏写',source:'错题照片核对'})).json();
  const linked=await(await post('api/record/task-link',{record_id:wrong.record_id,child:a.name,task_id:id})).json();
  assert.deepEqual([linked.task.progress.feedback,linked.task.progress.wrong],[2,1],'the link reply carries the new line');
  assert.equal((await post('api/record/task-link',{record_id:foreign.record_id,child:b.name,task_id:id})).status,409,'another child\'s record is refused');
  await p.reload();await until(async()=>await line().count()>0);const text=await line().first().innerText();
  assert.match(text,/^进展：反馈2条 · 错题1道$/);assert(text.length<=40,'one compact line');
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal overflow');await proof(p,`progress-${width}`);
  // The same row's existing entry reopens this task's saved feedback, with its voice/photo/text entry still there.
  const entry=p.locator(`[data-query-target="task:${id}"] [data-task="${id}"]`).first();assert.equal((await entry.innerText()).trim(),'查看/补充反馈');
  await entry.click();await until(async()=>/虚构另一位家长已更正/.test(await p.locator('#taskFeedbackHistory').innerText()));assert(await p.locator('#taskForm [name=note]').isEnabled());
  await p.keyboard.press('Escape');
  // The other child's list never shows this row or its line.
  await p.locator(`[data-child-filter="${b.id}"]`).first().click();await until(async()=>await p.locator(`[data-query-target="task:${id}"]`).count()===0);
  assert.equal(await line().count(),0);
  assert.deepEqual(errors,[]);await p.close();
 }
 console.log('PASS: 360/1440 compact progress, 503/lost reply one request, 409 latest record, explicit link, child isolation, same-row entry');
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e);process.exitCode=1});
