// Disposable synthetic family; no household data, external model, collection or printer.
// Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, SCENARIOS_UI_PROOF_DIR.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises'),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs/promises'),path=require('node:path');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXioAAAAASUVORK5CYII=','base64');
async function eventually(check,label){const until=Date.now()+12000;while(Date.now()<until){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function server(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const launch="import app,runpy,sys\napp.family_llm._chat_json=lambda *a,**k: {'items':[dict(label='第1题',question='',student_answer='C',answer='教师参考：B',judgment='incorrect',error_reason='与教师参考不同',possible_cause='原因待孩子解释',steps='先独立重答，再核对参考',uncertainty='')],'coverage':'仅按明确题号比较参考；原题要求未核'}\nsys.argv=['demo.py','--port',sys.argv[1]]\nrunpy.run_path('demo.py',run_name='__main__')";
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',launch,String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let error='';child.stdout.resume();child.stderr.on('data',b=>error+=b);
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(child.exitCode!==null||child.signalCode!==null)return;const exited=once(child,'exit');child.kill('SIGINT');await Promise.race([exited,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await exited}};
 try{await eventually(async()=>{if(child.exitCode!==null)throw Error(error||'Demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'synthetic server');return{url,stop}}catch(e){await stop();throw e}
}
async function ready(p){await p.locator('#task-group-homework').waitFor();await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','home ready')}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('dialog[open]').evaluateAll(xs=>xs.some(x=>x.scrollWidth>x.clientWidth)),false)}
async function proof(p,name){if(process.env.SCENARIOS_UI_PROOF_DIR){await fs.mkdir(process.env.SCENARIOS_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.SCENARIOS_UI_PROOF_DIR,name+'.png')})}}
function daily(base){
 const day='2026-09-28',kids=base.children;
 const task=(id,title,due,owner=kids[0])=>({id,title,child:owner.name,due,action:'虚构要求：'+title,original_status:'待跟进',history:[],source:'message:synthetic-admin-'+owner.id+':'+id,agenda:{category:'todo',box:'inbox',published_on:'2026-09-27',due_on:due,scheduled_on:''}});
 const tasks=[task('sign','虚构回执签字','2026-09-27'),task('print','虚构打印两页回执',''),task('stamp','虚构材料盖章','2026-09-29',kids[1])];
 const notices=kids.flatMap((kid,k)=>Array.from({length:4},(_,n)=>({id:'admin-'+k+'-'+n,kind:'school',child_id:kid.id,state:'pending',title:'虚构办理通知 '+k+'-'+n,body:'虚构要求：核对材料后交回。',evidence:[],plan:{school_task:{state:'review',purpose:'admin',title:'虚构办理通知 '+k+'-'+n,goal:'虚构要求：核对材料后交回。',reason:'虚构适用条件仍待核对。'}}})));
 const inbox=[...tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',title:t.title,child_ids:[kids.find(k=>k.name===t.child).id],closed:false,status:'待跟进',agenda:t.agenda})),...notices.map((n,i)=>({id:n.id,kind:'school',title:n.title,child_ids:[n.child_id],closed:false,status:'待核对',agenda:{category:'todo',box:'inbox',published_on:i<4?'2026-09-27':'2026-09-26',published_at:(i<4?'2026-09-27':'2026-09-26')+'T'+String(12+i%4).padStart(2,'0')+':00:00+08:00',due_on:'',scheduled_on:''}}))];
 return {...base,today:day,tasks,records:[],agent:{...base.agent,sources:kids.map(k=>({id:'synthetic-admin-'+k.id,child_id:k.id,platform:'qq',name:'虚构学校群',enabled:true})),items:notices},today_calendar:{inbox,agenda:[],events:[],timetables:kids.map((k,i)=>({id:'table-'+i,child_id:k.id,day,title:'虚构当天课表',sessions:[{slot:'第一节',title:'虚构数学 '+i},{slot:'第二节',title:'虚构语文 '+i}]})),source_error:''}};
}
(async()=>{
 let host,browser;const checks=[];
 try{
  host=await server();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const read=async()=>await(await fetch(host.url+'api/state')).json(),base=await read(),pdf=Buffer.from(await(await fetch(host.url+'attachment/'+encodeURIComponent('演示练习.pdf'))).arrayBuffer());
  assert.equal(pdf.subarray(0,5).toString(),'%PDF-','use the disposable demo PDF');
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:850}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
   try{
    const state=daily(base);await p.route('**/api/state',r=>r.fulfill({json:state}));await p.goto(host.url);await ready(p);
    const todo=p.locator('#task-group-todo');assert.match(await todo.locator('h2').innerText(),/要办的事 · 3[\s\S]*待核对 8/);
    for(const id of ['sign','print','stamp']){const card=todo.locator('[data-query-target="task:'+id+'"]');assert.equal(await card.isVisible(),true);assert.equal(await card.locator('[data-school-original-ref]').isVisible(),true,'administrative original stays directly visible')}
    assert.match(await todo.locator('[data-query-target="task:sign"]').innerText(),/逾期 · 截止：2026-09-27/);
    assert.match(await todo.locator('[data-query-target="task:print"]').innerText(),/截止待核对/);
    assert.match(await todo.locator('[data-query-target="task:stamp"]').innerText(),/截止：2026-09-29/);
    for(const notice of state.agent.items){assert.equal(await todo.locator('[data-agent-item="'+notice.id+'"]').isVisible(),true,'all four notices for each child remain visible');assert.equal(await p.locator('[data-agent-item="'+notice.id+'"]').count(),1)}
    assert.equal(await todo.locator('[data-agent-item] [data-check]').count(),0,'unreviewed notices cannot be completed');
    for(const table of state.today_calendar.timetables){const card=p.locator('[data-query-target="timetable:'+table.id+':'+state.today+'"]');assert.equal(await card.locator('ol').isVisible(),true,'courses need no expansion');assert.equal(await card.evaluate(x=>x.open),true)}
    await fit(p);await proof(p,'daily-'+width);
    for(const [k,kid] of state.children.entries()){
     await p.locator('[data-child-filter="'+kid.id+'"]').click();assert.equal(await todo.locator('[data-agent-item]').count(),4);
     for(const id of [0,1,2,3])assert.equal(await todo.locator('[data-agent-item="admin-'+k+'-'+id+'"]').isVisible(),true);
     assert.equal(await todo.locator('[data-agent-item^="admin-'+(1-k)+'-"]').count(),0,'other child notices are omitted');assert.equal(await p.locator('#today-courses .calendar-timetable').count(),1);
    }
    await p.reload();await ready(p);assert.equal(await todo.locator('[data-agent-item]').count(),8,'new session shows all children latest notices');assert.deepEqual(errors,[]);checks.push({width,dailyAdministration:true,eightNotices:true,coursesVisible:true,childIsolation:true});
   }catch(e){await proof(p,'daily-failure-'+width);throw e}finally{await p.close()}
   const q=await browser.newPage({viewport:{width,height:850}}),manualErrors=[];q.on('pageerror',e=>manualErrors.push(e.message));q.on('dialog',d=>d.accept());let modelCalls=0;
   await q.route('**/api/study/draft',r=>{modelCalls++;return r.fulfill({status:503,json:{error:'Manual scenario must not invoke a model'}})});
   await q.route('**/api/print/homework/draft',r=>{modelCalls++;return r.fulfill({status:503,json:{error:'Manual scenario must not invoke a model'}})});
   try{
    const owner=base.children[0],other=base.children[1],title='虚构电子卷与照片 '+width,goal='完成虚构第1题，保留原题供核对。';await q.goto(host.url);await ready(q);await q.locator('[data-homework-new="'+owner.id+'"]').click();
    const entry=q.locator('#homeworkInputDialog'),form=entry.locator('[data-homework-item="0"]');
    assert.equal(await entry.locator('[data-homework-original]').evaluate(x=>x.open),false);assert.equal(await entry.locator('.homework-materials').isVisible(),true,'trial sheet upload is a primary entry');assert.match(await entry.locator('.homework-materials').innerText(),/上传试卷 \/ 参考答案[\s\S]*拍试卷/);
    assert.equal(await form.locator('[name=reviewed]').count(),0);assert.equal(await form.locator('[name=subject]').isVisible(),false);assert.equal(await form.locator('[name=planned_minutes]').isVisible(),false);
    assert.match(await entry.locator('[data-homework-files]').first().getAttribute('accept'),/application\/pdf/);await form.locator('[name=title]').fill(title);await form.locator('[name=goal]').fill(goal);
    let uploads=0;await q.route('**/api/upload',r=>++uploads===1?r.fulfill({status:503,json:{error:'虚构上传失败'}}):r.continue());
    await entry.locator('[data-homework-files]').first().setInputFiles({name:'synthetic-paper.pdf',mimeType:'application/pdf',buffer:pdf});await entry.locator('[data-homework-retry-file]').waitFor();
    assert.equal(await form.locator('[name=title]').inputValue(),title);assert.equal(await form.locator('[name=goal]').inputValue(),goal);await form.locator('[type=submit]').click();assert.match(await entry.innerText(),/先完成或移除未成功的上传/);assert.equal((await read()).tasks.filter(t=>t.title===title).length,0,'failed upload does not create a partial task');
    await entry.locator('[data-homework-close]').click();await q.locator('[data-homework-new="'+owner.id+'"]').click();assert.equal(await form.locator('[name=title]').inputValue(),title);assert.equal(await form.locator('[name=goal]').inputValue(),goal);assert.equal(await entry.locator('[data-homework-retry-file]').count(),1,'failed PDF survives close and reopen');
    await entry.locator('[data-homework-retry-file]').click();await eventually(async()=>!await entry.locator('[data-homework-retry-file]').count(),'PDF retry');
    await entry.locator('[data-homework-files]').first().setInputFiles({name:'synthetic-question.png',mimeType:'image/png',buffer:png});await eventually(async()=>await entry.locator('.homework-files small').count()===2&&await entry.locator('.homework-files small').allTextContents().then(x=>x.every(t=>t==='原件已保存')),'two saved originals');
    await fit(q);await proof(q,'new-materials-'+width);await form.locator('[type=submit]').click();await entry.locator('.homework-saved').waitFor();await entry.locator('[data-homework-close]').click();await q.unroute('**/api/upload');
    const tasks=(await read()).tasks.filter(t=>t.title===title);assert.equal(tasks.length,1);const task=tasks[0];assert.equal(task.child,owner.name);assert.notEqual(task.update?.status,'已完成');
    const study=await(await fetch(host.url+'api/study?'+new URLSearchParams({child_id:owner.id,day:base.today}))).json(),saved=study.items.find(i=>i.task_id===task.id);assert.ok(saved);assert.equal(saved.report.attachments.length,2);const ids=saved.report.attachments;
    await q.reload();await ready(q);const card=q.locator('[data-query-target="task:'+task.id+'"]');assert.equal(await card.count(),1);assert.equal(await card.locator('.task-requirement').innerText(),goal);await card.locator('[data-task="'+task.id+'"]').click();
    await q.locator('#cameraInput').setInputFiles({name:'synthetic-answer.png',mimeType:'image/png',buffer:png});await q.locator('#pendingUploads img').waitFor();await q.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await q.locator('#taskFeedbackStatus').innerText()),'answer saved');
    const panel=q.locator('#taskFeedbackHistory [data-homework-review]').first();await panel.waitFor();await eventually(async()=>await panel.locator('[data-homework-review-sources] [data-review-source]').count()===2,'same task reported material sources');
    await panel.locator('details:has(> [data-homework-review-sources]) > summary').click();for(const id of ids)assert.equal(await panel.locator('[data-homework-review-sources] [data-review-source="'+id+'"]').isVisible(),true,'PDF/photo remain selectable for this task after reload');
    await fit(q);await proof(q,'same-task-materials-'+width);await q.locator('#taskDialog [data-close="taskDialog"]').click();await q.reload();await ready(q);await q.locator('[data-query-target="task:'+task.id+'"] [data-task="'+task.id+'"]').click();
    const reopened=q.locator('#taskFeedbackHistory [data-homework-review]').first();await eventually(async()=>await reopened.locator('[data-homework-review-sources] [data-review-source]').count()===2,'reopened task retains source identities');for(const id of ids)assert.equal(await reopened.locator('[data-review-source="'+id+'"]').count(),1);// Later teacher reference: independent feedback, reused for the original saved answer.
    const referenceUpload=await fetch(host.url+'api/upload',{method:'POST',headers:{'X-Family-Token':base.token,'X-File-Name':'synthetic-teacher.txt','Content-Type':'application/octet-stream'},body:Buffer.from('第1题 B')});assert.equal(referenceUpload.status,200);const teacher=(await referenceUpload.json()).attachment;
    const refSave=await fetch(host.url+'api/task/feedback',{method:'POST',headers:{'X-Family-Token':base.token,'Content-Type':'application/json'},body:JSON.stringify({task_id:task.id,child:owner.name,day:base.today,attachments:[teacher.id],request_key:'synthetic-later-teacher-'+width})});assert.equal(refSave.status,200);
    await q.locator('#taskDialog [data-close="taskDialog"]').click();await q.reload();await ready(q);await q.locator('[data-query-target="task:'+task.id+'"] [data-task="'+task.id+'"]').click();
    const check=q.locator('#taskFeedbackHistory [data-homework-review]').first();await eventually(async()=>await check.locator('[data-review-source="'+teacher.id+'"]').count()===1,'later teacher is available to original answer');
    await check.locator(':scope > details').evaluate(x=>x.open=true);await check.locator(':scope > details > .homework-review-material [data-homework-review-photo]').first().check();await check.locator('details:has(> [data-homework-review-sources])').evaluate(x=>x.open=true);
    const txt=check.locator('[data-review-source="'+teacher.id+'"]');await txt.locator('[data-homework-review-photo]').check();assert.equal(await txt.locator('[data-homework-review-role]').inputValue(),'reference','TXT with charset is explicitly reference');
    const paperSource=check.locator('[data-review-source="'+ids[0]+'"]');await paperSource.locator('[data-homework-review-photo]').check();await paperSource.locator('details').evaluate(x=>x.open=true);await paperSource.locator('[data-homework-review-role]').selectOption('reference');await paperSource.locator('[data-homework-review-pages]').fill('1');
    await q.unroute('**/api/print/homework/draft');await check.locator('[data-homework-review-run]').click();await check.locator('.homework-review-questions summary').waitFor();assert.match(await check.innerText(),/第1题 · 需要订正/);assert.match(await check.innerText(),/教师参考：B/);
    assert.equal(await check.locator('[data-homework-review-result] > details').evaluate(x=>x.open),false,'long text stays secondary');await proof(q,'reference-check-'+width);
    await check.locator('[data-homework-review-confirm]').check();await check.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await check.innerText()),'reference check staged');await q.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await q.locator('#taskFeedbackStatus').innerText()),'reference basis saved');
    await q.locator('#taskDialog [data-close="taskDialog"]').click();await q.reload();await ready(q);await q.locator('[data-query-target="task:'+task.id+'"] [data-task="'+task.id+'"]').click();assert.match(await q.locator('#taskFeedbackHistory').innerText(),/原作答反馈 #/);await q.locator('#taskDialog [data-close="taskDialog"]').click();
    await q.locator('[data-child-filter="'+other.id+'"]').click();assert.equal(await q.locator('[data-query-target="task:'+task.id+'"]').count(),0,'same material task is absent for the other child');
    const otherStudy=await(await fetch(host.url+'api/study?'+new URLSearchParams({child_id:other.id,day:base.today}))).json();assert.equal(otherStudy.items.some(i=>i.task_id===task.id),false);assert.equal(modelCalls,0);assert.deepEqual(manualErrors,[]);checks.push({width,parentPDFAndPhoto:true,uploadFailurePreservesDraft:true,retry:true,savedOnce:true,reopenSameTaskSources:true,noModel:true,childIsolation:true});
   }catch(e){await proof(q,'manual-failure-'+width);throw e}finally{await q.close()}
  }
  const result={passed:checks.length,syntheticOnly:true,realPhone:false,realModels:false,checks};if(process.env.SCENARIOS_UI_PROOF_DIR)await fs.writeFile(path.join(process.env.SCENARIOS_UI_PROOF_DIR,'passed.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{await browser?.close();await host?.stop()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
