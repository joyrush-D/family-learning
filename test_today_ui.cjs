// Synthetic homepage checks. Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON, TODAY_UI_PROOF_DIR. No production URL, model or device calls.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');

async function eventually(check,label,timeout=10000){
 const end=Date.now()+timeout;
 while(Date.now()<end){if(await check())return;await delay(40)}
 throw Error('Timed out: '+label);
}
async function demoServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');
 const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const url='http://127.0.0.1:'+port+'/',env={...process.env};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const processChild=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});
 let failure;processChild.on('error',e=>failure=e);processChild.stdout.resume();processChild.stderr.resume();
 const stop=async()=>{if(failure||processChild.exitCode!==null||processChild.signalCode!==null)return;const exited=once(processChild,'exit');processChild.kill('SIGINT');await Promise.race([exited,delay(2500)]);if(processChild.exitCode===null&&processChild.signalCode===null){processChild.kill('SIGKILL');await exited}};
 try{await eventually(async()=>{if(failure)throw failure;if(processChild.exitCode!==null)throw Error('Synthetic demo exited');try{return (await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'temporary demo startup');return {url,stop}}catch(e){await stop();throw e}
}
async function ready(p){await eventually(async()=>await p.locator('body[data-page="home"] #task-group-homework').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','today homework and todos ready')}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');assert.equal(await p.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'open form has no horizontal overflow')}
async function proof(p,name){if(process.env.TODAY_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.TODAY_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.TODAY_UI_PROOF_DIR,name+'.png'),fullPage:false})}}
function fixtures(base){
 const first=base.children[0],second=base.children[1],today='2026-09-08';
 const task=(id,due,extra={})=>({id,child:first.name,title:'虚构任务 '+id,due,original_status:'待跟进',source:'虚构学校通知',action:'虚构要求',history:[],agenda:{category:'homework',published_on:today,due_on:/^2026-09-\d\d$/.test(due)?due:'',scheduled_on:'',box:'inbox'},...extra});
 const tasks=[task('TODAY',today),task('PAST','2026-09-07'),task('FUTURE','2026-09-09'),task('UNKNOWN','下周再核对'),task('INVALID','2026-02-30'),
  task('DONE',today,{update:{status:'已完成'}}),task('NA',today,{update:{status:'不适用'}}),task('DECLINED',today,{update:{status:'不参加'}}),task('ARCHIVE',today,{original_status:'已归档'}),task('LINK','尚未明确'),task('CANCEL-LINK','日期未定'),task('SIBLING',today,{child:second.name}),task('ADMIN',today,{agenda:{category:'todo',published_on:'',due_on:'',scheduled_on:'',box:'inbox'}}),task('WISH','',{focus:{box:'wish'},agenda:{category:'todo',published_on:'',due_on:'',scheduled_on:'',box:'wish'}}),task('PLANNED','',{agenda:{category:'todo',published_on:today,due_on:'',scheduled_on:'2026-09-09',box:'inbox'}})];
 const event=(id,extra={})=>({id,title:'虚构安排 '+id,day:today,child_ids:[first.id],status:'confirmed',category:'school',start_time:'08:00',task_id:'',...extra});
 const events=[event('shared',{child_ids:[first.id,second.id],category:'family'}),event('unlinked'),event('cancelled',{status:'cancelled'})];
 const reading=(id,state,planned_on=today)=>({id,child_id:first.id,child:first.name,book:'虚构阅读 '+id,state,planned_on,attachments:[]});
 const inbox=tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',child_ids:[t.child===first.name?first.id:second.id],closed:['已完成','不适用','不参加','已归档'].includes(t.update?.status||t.original_status),agenda:t.agenda}));
 inbox.push({id:'synthetic-school',kind:'school',child_ids:[first.id],closed:false,agenda:{category:'homework',published_on:today,due_on:'',scheduled_on:'',box:'inbox'}});
 return {...base,today,tasks,agent:{...base.agent,items:['school','care','review'].map(kind=>({id:'synthetic-'+kind,kind,child_id:first.id,state:'pending',title:'虚构提醒 '+kind,body:'虚构待核对内容',evidence:[]}))},today_calendar:{inbox,agenda:[],events,timetables:[{id:'synthetic-table',child_id:first.id,day:today,title:'虚构课表',source:'虚构课表原件',sessions:[{slot:'第一节',title:'虚构数学'},{slot:'第二节',title:'虚构语文'}]}],source_error:''},
  reading:{...base.reading,tasks:[reading('draft','草案'),reading('paused','暂停'),reading('finished','已完成'),reading('today-reading','进行中'),reading('more','需补充'),reading('past-reading','进行中','2026-09-07'),reading('parent-review','待确认',''),reading('future-reading','进行中','2026-09-09'),reading('undated-reading','进行中','')]}};
}

(async()=>{
 let server,browser;const checks=[];
 try{
  server=await demoServer();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const read=async()=>await(await fetch(server.url+'api/state')).json();
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[],resources=[];
   p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>resources.push(new URL(r.url()).pathname));
   try{
    const state=fixtures(await read()),homework=p.locator('#task-group-homework'),todos=p.locator('#task-group-todo');
    const card=id=>p.locator('[data-query-target="task:'+id+'"]');
    await p.route('**/api/state',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(state)}));
    await p.goto(server.url,{waitUntil:'load'});await ready(p);await fit(p);
    assert.deepEqual(await homework.locator('[data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask).sort()),['CANCEL-LINK','FUTURE','INVALID','LINK','PAST','SIBLING','TODAY','UNKNOWN']);
    assert.deepEqual(await todos.locator('[data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask)),['ADMIN']);
    for(const id of ['DONE','NA','DECLINED','ARCHIVE','WISH','PLANNED'])assert.equal(await card(id).count(),0,'closed items, wishes and future plans omitted: '+id);
    for(const id of ['PAST','FUTURE','UNKNOWN','INVALID','CANCEL-LINK'])assert.equal(await card(id).isVisible(),true,'unfinished deadline/undated tasks stay visible: '+id);
    assert.equal(await card('LINK').count(),1,'one task is not duplicated');
    assert.match(await card('PAST').innerText(),/逾期/);assert.match(await card('ADMIN').innerText(),/发布：待核对/);
    assert.match(await homework.locator('h2').innerText(),/今日作业 · 8.*待核对 1/);assert.equal(await p.locator('[data-agent-item] [data-check]').count(),0,'unconfirmed notifications cannot be completed');
    assert.deepEqual(await p.locator('[data-agent-item]').evaluateAll(xs=>xs.map(x=>x.dataset.agentItem)),['synthetic-school']);
    const shared=p.locator('[data-query-target="calendar:shared:'+state.today+'"]');assert.equal(await shared.count(),1);assert.match(await shared.innerText(),new RegExp(state.children[0].name+'、'+state.children[1].name));
    assert.equal(await p.locator('.calendar-cancelled').count(),0);assert.equal(await p.locator('.calendar-event [data-check]').count(),0,'calendar-only events do not invent task completion');
    await p.locator('.calendar-timetable summary').click();assert.match(await p.locator('.calendar-timetable').innerText(),/虚构数学[\s\S]*虚构语文/);
    assert.deepEqual(await p.locator('nav [data-page]').evaluateAll(xs=>xs.map(x=>x.dataset.page)),['home','calendar','tasks','more']);
    assert.deepEqual(await p.locator('nav [data-page]').allTextContents(),['今天','日历','收集箱','更多']);
    assert.equal(await p.locator('[data-task-box]').count(),0,'collection tabs belong to inbox');
    assert.equal(await p.locator('#growthWorld,.universe').count(),0);assert.equal(resources.some(x=>/growth-world\.js|three\.(core|module)/.test(x)),false,'homepage never requests Three.js');
    await p.evaluate(()=>scrollTo(0,0)); // The timetable check above scrolled below the initial screen.
    const firstTask=card('TODAY'),position=await firstTask.locator('h3').boundingBox();
    assert.ok(position&&position.y>=0&&position.y+position.height<(width===360?560:820),'first task is on first screen');
    assert.equal(await firstTask.locator('.task-requirement').isVisible(),true);assert.equal(await firstTask.locator('details .task-requirement').count(),0,'goal is not hidden');
    assert.equal(await firstTask.locator('[data-study-task-add]').innerText(),'作业计时');assert.equal(await firstTask.locator('[data-task-decisions]').isVisible(),true);
    assert.equal(await firstTask.locator('.checkhit,button:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'44px actions');
    await p.locator('#childFilter').selectOption(state.children[1].name);assert.equal(await card('SIBLING').isVisible(),true);assert.equal(await card('TODAY').count(),0);assert.equal(await p.locator('[data-agent-item]').count(),0);assert.equal(await shared.count(),1);
    await p.locator('#childFilter').selectOption('');
    await proof(p,'today-'+width);
    for(const [page,title] of [['learning','学习任务与进展'],['growth','成长记录'],['reading','把一本书，变成一段旅程。'],['care','陪伴建议与反馈'],['agent','成长助手'],['print','家庭打印站'],['sources','来源与附件']]){
     await p.locator('nav [data-page="more"]').click();await p.locator('#content [data-page="'+page+'"]').click();
     assert.equal(await p.locator('#content h1').innerText(),title,'more opens '+page);assert.equal(await p.locator('nav [data-page="more"]').getAttribute('class'),'active');await fit(p);
    }
    assert.deepEqual(errors,[]);
    checks.push({width,kind:'classification',homeworkAndTodo:true,deadlinesCarryForward:true,wishesAndFuturePlansExcluded:true,pendingSeparate:true,childIsolation:true,sharedCalendar:true,fourNavigationItems:true,moreEntriesReachable:true,noThree:true,taskTop:position.y,noOverflow:true});
   }finally{await p.close()}

   // These writes go to the disposable demo's real API. No response fixture is active.
   const current=await read(),who=current.children[0],other=current.children[1],title='虚构首页勾选 '+width;
   const response=await fetch(server.url+'api/task/new',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':current.token},body:JSON.stringify({child:who.name,title,due:current.today,source:'虚构测试通知',action:'虚构要求'})});
   assert.equal(response.ok,true);const task=(await read()).tasks.find(t=>t.title===title);assert.ok(task);
   const formPage=await browser.newPage({viewport:{width,height:820}}),formErrors=[],posts=[];
   formPage.on('pageerror',e=>formErrors.push(e.message));formPage.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
   try{
    await formPage.goto(server.url,{waitUntil:'load'});await ready(formPage);await fit(formPage);
    // A rejected save must keep the task visible and restore its unchecked state.
    await formPage.route('**/api/task',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构保存失败，请重试'})}));
    await formPage.locator('[data-today-task="'+task.id+'"] [data-check]').click();
    await eventually(async()=>await formPage.locator('[data-today-task="'+task.id+'"]').getAttribute('aria-busy')==='false','failed save restored');
    assert.equal(await formPage.locator('[data-today-task="'+task.id+'"] [data-check]').isChecked(),false);
    assert.notEqual((await read()).tasks.find(t=>t.id===task.id).update?.status,'已完成');
    await formPage.unroute('**/api/task');posts.length=0;
    let releaseSave;const heldSave=new Promise(resolve=>releaseSave=resolve);let saveHeld=false,stateReads=0;
    await formPage.route('**/api/task',async route=>{saveHeld=true;await heldSave;await route.continue()});
    await formPage.route('**/api/state',async route=>{stateReads++;await route.abort('failed')});
    const checkbox=formPage.locator('[data-today-task="'+task.id+'"] [data-check]');
    try{
     await checkbox.click();await eventually(()=>saveHeld,'save held for slow network');
     assert.equal(await checkbox.isChecked(),true,'click remains visibly selected while saving');
     assert.equal(await formPage.locator('[data-today-task="'+task.id+'"]').getAttribute('aria-busy'),'true');
     assert.match(await formPage.locator('[data-today-task="'+task.id+'"]').innerText(),/正在保存/);
     assert.notEqual((await read()).tasks.find(t=>t.id===task.id).update?.status,'已完成','pending is not committed');
     await proof(formPage,'task-saving-'+width);
    }finally{releaseSave()}
    await eventually(async()=>await formPage.locator('[data-today-task="'+task.id+'"]').count()===0&&(await read()).tasks.find(t=>t.id===task.id).update?.status==='已完成','checkbox saved to real demo API');
    assert.equal(stateReads,0,'confirmed task renders without reloading all family data');
    await formPage.unroute('**/api/task');await formPage.unroute('**/api/state');
    await formPage.reload({waitUntil:'load'});await ready(formPage);assert.equal(await formPage.locator('[data-today-task="'+task.id+'"]').count(),0);
    await formPage.locator('#childFilter').selectOption(other.name);await formPage.locator('nav [data-page="more"]').click();await formPage.locator('[data-capture]').click();await eventually(()=>formPage.locator('#recordDialog').isVisible(),'record feedback for selected child');
    const form=formPage.locator('#recordForm');assert.equal(await form.locator('[name="child"]').inputValue(),other.name);assert.equal(await form.locator('[name="category"]').inputValue(),'学习进展');
    const recordTitle='虚构首页学习记录 '+width,recordNote='虚构观察：能说出思路，最后一步仍需要提示。';
    await form.locator('[name="title"]').fill(recordTitle);await form.locator('[name="note"]').fill(recordNote);await fit(formPage);await proof(formPage,'today-capture-'+width);
    await form.locator('[type="submit"]').click();await eventually(async()=>!(await formPage.locator('#recordDialog').isVisible())&&(await read()).records.some(r=>r.title===recordTitle),'manual learning record saved');
    await formPage.reload({waitUntil:'load'});await ready(formPage);
    const saved=(await read()).records.filter(r=>r.title===recordTitle);assert.equal(saved.length,1);assert.equal(saved[0].child,other.name);assert.equal(saved[0].category,'学习进展');assert.equal(saved[0].note,recordNote);
    assert.equal(posts.filter(x=>x==='/api/task').length,1);assert.equal(posts.filter(x=>x==='/api/record').length,1);assert.deepEqual(formErrors,[]);
    checks.push({width,kind:'persistent-interactions',checkboxPersists:true,immediatePendingState:true,failedSaveRestored:true,postSaveFullStateRequests:stateReads,selectedChildCorrect:true,manualRecordSavedOnce:true,noOverflow:true,pageErrors:0});
   }finally{await formPage.close()}

   // Explicit dismissal uses the same disposable API and never fabricates completion.
   const before=await read(),newTask=async(child,title)=>{
    const response=await fetch(server.url+'api/task/new',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':before.token},body:JSON.stringify({child,title,due:before.today,source:'虚构测试通知',action:'虚构可选安排'})});
    assert.equal(response.ok,true);return (await response.json()).task;
   };
   const decline=await newTask(who.name,'虚构可选活动 '+width),ignore=await newTask(who.name,'虚构重复事项 '+width),sibling=await newTask(other.name,'虚构另一孩子事项 '+width);
   const baseline=await read(),otherBefore=baseline.tasks.filter(t=>t.child===other.name),d=await browser.newPage({viewport:{width,height:820}}),dismissErrors=[],writes=[];
   d.on('pageerror',e=>dismissErrors.push(e.message));d.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/task')writes.push(r.postDataJSON())});
   const card=id=>d.locator('[data-query-target="task:'+id+'"]'),open=async id=>{
    await d.locator('[data-task-decisions="'+id+'"]').click();await eventually(()=>d.locator('#taskDecisionDialog').isVisible(),'explicit task decision');
   },choose=async(status,note='')=>{
    await d.locator('#taskDecisionForm [name="status"][value="'+status+'"]').check();await d.locator('#taskDecisionForm [name="note"]').fill(note);
   },save=()=>d.locator('#taskDecisionForm [type="submit"]').click(),goTasks=async()=>{
    await d.locator('nav [data-page="tasks"]').click();await eventually(()=>d.locator('[data-task-box="已结束"]').isVisible(),'inbox history ready');
   },readTask=async id=>(await read()).tasks.find(t=>t.id===id);
   try{
    await d.goto(server.url,{waitUntil:'load'});await ready(d);await open(decline.id);
    assert.equal(await d.locator('#taskDecisionForm [name="status"]:checked').count(),0,'dismissal requires an explicit choice');
    const postCount=writes.length;await save();assert.equal(writes.length,postCount,'empty choice never writes');
    await choose('不参加','虚构反馈：这次想休息');await fit(d);await proof(d,'dismiss-choice-'+width);await save();
    await eventually(async()=>!(await d.locator('#taskDecisionDialog').isVisible())&&!(await card(decline.id).count())&&(await readTask(decline.id)).update?.status==='不参加','declined item removed from today');
    assert.equal(await card(sibling.id).count(),1,'other child remains visible');
    await d.reload({waitUntil:'load'});await ready(d);assert.equal(await card(decline.id).count(),0,'dismiss persists after refresh');
    await goTasks();assert.equal(await card(decline.id).count(),0,'dismissal is no longer active');assert.equal((await readTask(decline.id)).update.status,'不参加','dismissal is not completion');
    await d.locator('[data-task-box="已结束"]').click();assert.equal(await card(decline.id).count(),1);assert.equal(await card(decline.id).locator('[data-check]').count(),0,'dismissed card cannot be accidentally checked complete');
    assert.match(await card(decline.id).innerText(),/不参加/);await fit(d);await proof(d,'dismissed-'+width);
    await card(decline.id).locator('[data-task-restore]').click();await eventually(async()=>!(await card(decline.id).count())&&(await readTask(decline.id)).update?.status==='待跟进','restore returns to active');
    await d.locator('[data-task-box="Inbox"]').click();assert.equal(await card(decline.id).count(),1);assert.equal(await card(decline.id).locator('[data-check]').count(),1);

    // A lost reply must preserve the choice and retry the same change without duplicate history.
    await open(ignore.id);await choose('不适用');let dropped=false;
    await d.route('**/api/task',async route=>{if(!dropped&&route.request().postDataJSON().id===ignore.id){dropped=true;await route.fetch();await route.abort('failed')}else await route.continue()});
    await save();await eventually(async()=>dropped&&(await readTask(ignore.id)).update?.status==='不适用'&&await d.locator('#taskDecisionForm [type="submit"]').isEnabled(),'lost reply leaves retry available');
    assert.equal(await d.locator('#taskDecisionDialog').isVisible(),true);assert.equal(await d.locator('#taskDecisionForm [name="status"]:checked').inputValue(),'不适用');
    const committed=await readTask(ignore.id);await d.unroute('**/api/task');await save();
    await eventually(async()=>!(await d.locator('#taskDecisionDialog').isVisible()),'same dismissal retry reconciled');
    assert.deepEqual((await readTask(ignore.id)).history,committed.history,'lost response retry adds no duplicate history');
    await d.locator('[data-task-box="已结束"]').click();assert.match(await card(ignore.id).innerText(),/无需处理/);assert.equal(await card(ignore.id).locator('[data-check]').count(),0);

    // A second parent changing the task wins over this stale form; keep its draft for review.
    await d.locator('[data-task-box="Inbox"]').click();await open(decline.id);await choose('不参加','虚构保留的选择');
    const fresh=await readTask(decline.id),external=await fetch(server.url+'api/task',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':before.token},body:JSON.stringify({id:decline.id,status:'进行中',note:'虚构另一家长更新',expected_updated:fresh.update?.updated||''})});
    assert.equal(external.ok,true);await save();await eventually(()=>d.locator('#taskDecisionForm [type="submit"]').isEnabled(),'conflict form ready');
    assert.equal(await d.locator('#taskDecisionDialog').isVisible(),true);assert.equal(await d.locator('#taskDecisionForm [name="status"]:checked').inputValue(),'不参加');
    assert.equal(await d.locator('#taskDecisionForm [name="note"]').inputValue(),'虚构保留的选择');assert.equal((await readTask(decline.id)).update.status,'进行中','stale form cannot override another parent');
    assert.match(await d.locator('#taskDecisionDialog').innerText(),/已更新|已变化|核对|冲突/);await fit(d);await proof(d,'dismiss-conflict-'+width);
    await d.locator('#taskDecisionReload').click();await eventually(async()=>/进行中/.test(await d.locator('#taskDecisionCurrent').innerText()),'read latest task without losing decision');
    assert.equal(await d.locator('#taskDecisionForm [name="status"]:checked').inputValue(),'不参加');assert.equal(await d.locator('#taskDecisionForm [name="note"]').inputValue(),'虚构保留的选择');
    await d.locator('#taskDecisionForm [name="note"]').fill('虚构核对新状态后的选择');await save();
    await eventually(async()=>!(await d.locator('#taskDecisionDialog').isVisible())&&(await readTask(decline.id)).update.status==='不参加','explicit fresh choice succeeds');
    const after=await read();assert.deepEqual(after.records,baseline.records,'dismissal creates no learning records');assert.deepEqual(after.rewards,baseline.rewards,'dismissal grants no growth reward');assert.deepEqual(after.reading,baseline.reading,'dismissal never changes reading awards');
    assert.deepEqual(after.tasks.filter(t=>t.child===other.name),otherBefore,'other child tasks unchanged');assert.ok(writes.length>=5&&writes.every(w=>typeof w.expected_updated==='string'),'every dismissal and restore carries its observed task version');assert.deepEqual(dismissErrors,[]);
    checks.push({width,kind:'dismissal',explicitChoice:true,dismissAndRestore:true,persistent:true,noCompletionCheckbox:true,noLearningOrRewards:true,otherChildUnchanged:true,lostReplyRetryIdempotent:true,conflictPreservesDraft:true,noOverflow:true,pageErrors:0});
   }finally{await d.close()}
  }
  const result={passed:checks.length,syntheticOnly:true,realPhone:false,checks};
  if(process.env.TODAY_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.TODAY_UI_PROOF_DIR,'today-ui-passed.json'),JSON.stringify(result,null,2)+'\n')}
  console.log(JSON.stringify(result,null,2));
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
