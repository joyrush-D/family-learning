// Disposable synthetic family only: one saved answer photo -> explicit AI draft -> reviewed feedback.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(fn,label){for(let n=0;n<250;n++){if(await fn())return;await delay(40)}throw Error('Timed out: '+label)}
async function server(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:'ignore'}),url='http://127.0.0.1:'+port+'/';
 await eventually(async()=>{try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'demo startup');
 return {url,stop:async()=>{if(proc.exitCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2000)]);if(proc.exitCode===null){proc.kill('SIGKILL');await done}}};
}
(async()=>{let host,browser;try{
 host=await server();browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=','base64');
 for(const width of [360,1440]){
  let state=await(await fetch(host.url+'api/state')).json();const child=state.children[0].name,title='虚构作业核对 '+width;
  const p=await browser.newPage({viewport:{width,height:850}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(host.url);
  await p.locator('[data-homework-new]').first().click();const entry=p.locator('#homeworkInputDialog');await entry.waitFor();assert.match(await entry.innerText(),/记作业/);
  await entry.locator('[name=text]').fill('虚构作业原话：今天核对一页阅读题');await entry.locator('[data-homework-manual]').click();const item=entry.locator('[data-homework-item="0"]');await item.locator('[name=title]').fill(title);await item.locator('[name=goal]').fill('先作答再核对');await item.locator('[name=reviewed]').check();await item.locator('[type=submit]').click();await entry.locator('.homework-saved').waitFor();await entry.locator('[data-homework-close]').click();
  state=await(await fetch(host.url+'api/state')).json();const id=state.tasks.find(t=>t.title===title)?.id;assert(id,'homework entry creates the task');await p.locator('[data-query-target="task:'+id+'"]').waitFor();
  await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskDialog[open]').waitFor();
  assert.equal(await p.locator('#taskStatusDetails').evaluate(x=>x.open),false,'status update stays secondary');
  await p.locator('#taskForm [name=note]').fill('虚构未保存反馈');
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'close dismissal keeps unsaved feedback');
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构未保存反馈');
  await p.locator('#taskForm [name=note]').fill('');
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-answer.png',mimeType:'image/png',buffer:png});await p.locator('#pendingUploads img').waitFor();
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'close dismissal keeps unsaved photo');
  assert.equal(await p.locator('#pendingUploads img').count(),1);
  await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'photo feedback saved');
  const panel=p.locator('#taskFeedbackHistory [data-homework-review]').first();assert.equal(await panel.locator('details').evaluate(x=>x.open),true,'saved photo exposes review');assert.equal(await panel.locator('[data-homework-review-photo]').count(),1);
  let calls=0;await p.route('**/api/print/homework/draft',r=>{calls++;const body=r.request().postDataJSON();assert.equal(body.question_sources.length,1);return calls===1?r.fulfill({status:503,json:{error:'虚构模型暂不可用'}}):r.fulfill({json:{draft:{text:'虚构第1题：卷面C，参考B；先找原文依据。',items:1,wrong_items:1,unknown_items:0,coverage:'仅此一页'},question_sha256:'a'.repeat(64)}})});
  assert.equal(calls,0,'opening saved feedback must not call model');await panel.locator('[data-homework-review-photo]').check();await panel.locator('[data-homework-review-run]').click();await eventually(async()=>/虚构模型暂不可用/.test(await panel.innerText()),'model failure retained');
  await panel.locator('[data-homework-review-run]').click();await panel.locator('[data-homework-review-result] textarea').waitFor();assert.equal(calls,2);
  await panel.locator('[data-homework-review-result] textarea').fill('家长核对：第1题卷面C，依据原文应选B。先自己定位关键词，再独立重答。');
  await panel.locator('[data-homework-review-apply]').click();assert.match(await panel.innerText(),/请对照原题核对/);
  await panel.locator('[data-homework-review-confirm]').check();await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await panel.innerText()),'review staged');
  assert.match(await p.locator('#taskForm [name=note]').inputValue(),/家长核对的作业批改参考/);
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'review draft stays after declining discard');
  await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'review feedback saved');
  state=await(await fetch(host.url+'api/state')).json();const records=state.records.filter(r=>r.source==='事项:'+id);assert.equal(records.length,2);assert.equal(state.tasks.find(t=>t.id===id).update,null,'grading must not complete homework');
  const photo=records[0].attachments[0],review=records.find(r=>r.note.includes('批改参考'));assert(review.attachments.includes(photo));const report=review.attachments.find(a=>a!==photo);assert.equal(state.uploads.find(a=>a.id===report).mime,'text/plain; charset=utf-8');
  await p.keyboard.press('Escape');await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskFeedbackHistory').getByText('作业批改参考', {exact:false}).first().waitFor();
  await p.locator('[data-task-feedback-edit]').first().click();
  await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false,'unchanged feedback closes without warning');
  await p.locator('[data-task="'+id+'"]').first().click();await p.locator('[data-task-feedback-edit]').first().click();
  await p.locator('#taskForm [name=note]').fill('虚构更正但未保存');
  p.once('dialog',d=>d.dismiss());await p.keyboard.press('Escape');
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'Escape dismissal keeps edited feedback');
  p.once('dialog',d=>d.accept());await p.keyboard.press('Escape');
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false,'explicit discard closes');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);assert.deepEqual(errors,[]);await p.close();
 }
 console.log('Homework feedback AI review: 360/1440 save, retry, reopen, task status and source preserved');
}finally{await browser?.close();await host?.stop()}})().catch(e=>{console.error(e);process.exitCode=1});
