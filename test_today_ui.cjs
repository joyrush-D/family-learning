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
async function selectedChild(p,children,selected){assert.equal(await p.locator('[data-child-filter=""]').count(),0,'there is no all-children choice');assert.equal(await p.locator('.child-filters [data-child-filter]').count(),children.length);assert.deepEqual(await p.locator('.child-filters [aria-pressed="true"]').evaluateAll(xs=>xs.map(x=>x.dataset.childFilter)),[selected.id],'exactly the selected child is active')}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');assert.equal(await p.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'open form has no horizontal overflow')}
async function proof(p,name,fullPage=false){if(process.env.TODAY_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.TODAY_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.TODAY_UI_PROOF_DIR,name+'.png'),fullPage})}}
function fixtures(base){
 const first=base.children[0],second=base.children[1],today='2026-09-08';
 const task=(id,due,extra={})=>({id,child:first.name,title:'虚构任务 '+id,due,original_status:'待跟进',source:'虚构学校通知',action:'虚构要求',history:[],agenda:{category:'homework',published_on:today,due_on:/^2026-09-\d\d$/.test(due)?due:'',scheduled_on:'',box:'inbox'},...extra});
 const tasks=[task('TODAY',today),task('PAST','2026-09-07'),task('FUTURE','2026-09-09'),task('UNKNOWN','下周再核对'),task('INVALID','2026-02-30'),
  task('DONE',today,{update:{status:'已完成'}}),task('NA',today,{update:{status:'不适用'}}),task('DECLINED',today,{update:{status:'不参加'}}),task('ARCHIVE',today,{original_status:'已归档'}),task('LINK','尚未明确'),task('CANCEL-LINK','日期未定'),task('SIBLING',today,{child:second.name}),task('ADMIN',today,{title:'虚构家长事务：打印签字回执',agenda:{category:'todo',published_on:'',due_on:'',scheduled_on:'',box:'inbox'}}),task('WISH','',{focus:{box:'wish'},agenda:{category:'todo',published_on:'',due_on:'',scheduled_on:'',box:'wish'}}),task('PLANNED','',{agenda:{category:'todo',published_on:today,due_on:'',scheduled_on:'2026-09-09',box:'inbox'}})];
 const event=(id,extra={})=>({id,title:'虚构安排 '+id,day:today,child_ids:[first.id],status:'confirmed',category:'school',start_time:'08:00',task_id:'',...extra});
 const events=[event('shared',{child_ids:[first.id,second.id],category:'family'}),event('unlinked'),event('cancelled',{status:'cancelled'})];
 const reading=(id,state,planned_on=today)=>({id,child_id:first.id,child:first.name,book:'虚构阅读 '+id,state,planned_on,attachments:[]});
 const inbox=tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',status:t.update?.status||t.original_status,child_ids:[t.child===first.name?first.id:second.id],closed:['已完成','不适用','不参加','已归档'].includes(t.update?.status||t.original_status),agenda:t.agenda}));
 inbox.push({id:'synthetic-school',kind:'school',child_ids:[first.id],closed:false,agenda:{category:'homework',published_on:today,due_on:'2026-09-09',scheduled_on:'',box:'inbox'}});
 return {...base,today,tasks,agent:{...base.agent,items:['school','care','review'].map(kind=>({id:'synthetic-'+kind,kind,child_id:first.id,state:'pending',title:'虚构提醒 '+kind,body:'虚构待核对内容',plan:kind==='school'?{school_task:{state:'review',reason:'需要核对是否参加这次活动。'}}:{},evidence:[]}))},today_calendar:{inbox,agenda:[],events,timetables:[{id:'synthetic-table',child_id:first.id,day:today,title:'虚构课表',source:'虚构课表原件',sessions:[{slot:'第一节',title:'虚构数学'},{slot:'第二节',title:'虚构语文'}]}],source_error:''},
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
    state.attachments=['虚构题目.png','虚构题目续页.png','虚构答案.pdf'];state.printing={printers:[{name:'Synthetic_Printer',label:'虚构打印机',color:false,duplex:false}],jobs:[]};
    state.agent.sources.push({id:'synthetic-audio',child_id:state.children[0].id,name:'虚构学校群',enabled:true});state.tasks.find(t=>t.id==='TODAY').source='message:synthetic-audio:dictation';
    const publication={ref:'message:synthetic-audio:dictation',sender:'示例周老师',source_name:'虚构学校群 <甲班>'};
    state.tasks.find(t=>t.id==='TODAY').agenda.publications=[publication];
    state.tasks.find(t=>t.id==='TODAY').action="完成第1–3题。\n第4题选做。\n对照老师答案检查。\n请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。请读完整要求。最后请家长签字。";
    state.today_calendar.inbox.find(i=>i.id==='synthetic-school').agenda.publications=[publication];
    state.tasks.find(t=>t.id==='SIBLING').agenda.publications=[publication];state.tasks.find(t=>t.id==='SIBLING').source=publication.ref;
    state.agent.items.find(i=>i.id==='synthetic-school').title='待核对：⚠️重要通知⚠️\n\n请准备虚构活动材料。';
    state.agent.items.find(i=>i.id==='synthetic-school').evidence=[{ref:'message:synthetic-audio:dictation',quote:'虚构老师原话'}];
    state.agent.items.push({id:'synthetic-reference',kind:'school',child_id:state.children[0].id,state:'pending',title:'虚构成绩表说明',body:'第一列表示课堂默写记录。',evidence:[],plan:{school_task:{state:'reference',reason:'这段内容解释列标题，没有新作业。'}}});
    const card=id=>p.locator('[data-query-target="task:'+id+'"]');
    await p.route('**/api/state',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(state)}));
    await p.route('**/api/agent/message?*',r=>{const ids=Object.fromEntries(new URL(r.request().url()).searchParams);return r.fulfill({json:{...ids,source_name:publication.source_name,message:{id:ids.message_id,sender:publication.sender,time:'2026-09-08T08:30:00+08:00',text:'虚构老师原话'},attachments:[]}})});
    let sourceChecks=0;
    await p.route('**/api/agent/collector/check',r=>{sourceChecks++;assert.deepEqual(r.request().postDataJSON(),{});return r.fulfill({status:width===360?503:200,json:width===360?{error:'虚构后台暂不可用'}:{ok:true}})});
    await p.goto(server.url,{waitUntil:'load'});await ready(p);await fit(p);await selectedChild(p,state.children,state.children[0]);
    const original=card('TODAY').locator(':scope > .checkrow .taskbody > .task-actions > .toolbar [data-school-original-ref]');assert(await original.isVisible(),'homework source is visible before expanding details');assert.match(await original.innerText(),/查看作业原件/);
    assert.equal(await original.locator('.school-publication-context').innerText(),'示例周老师');assert.doesNotMatch(await original.innerText(),/虚构学校群|甲班|发言人：/,'class and group names are not in the default action');
    state.tasks.find(t=>t.id==='TODAY').agenda.publications=[{...publication,sender:'   '}];await p.reload({waitUntil:'load'});await ready(p);
    assert.equal(await original.locator('.school-publication-context').innerText(),'发布者未记录','whitespace names do not imply a recorded publisher');
    state.tasks.find(t=>t.id==='TODAY').agenda.publications=[publication];
    await p.reload({waitUntil:'load'});await ready(p);assert.equal(await original.locator('.school-publication-context').isVisible(),true,'reopened daily task retains its saved publication context');
    const sourceRefs=[publication.ref,...[2,3,4].map(i=>'message:synthetic-audio:extra-'+i)],currentTask=state.tasks.find(t=>t.id==='TODAY');
    currentTask.source=sourceRefs.join('\n');currentTask.agenda.publications=sourceRefs.map(ref=>({...publication,ref}));
    await p.reload({waitUntil:'load'});await ready(p);await fit(p);
    const sourceGroup=card('TODAY').locator('.school-original-group');assert.equal(await sourceGroup.locator('.school-publication-context').count(),1);assert.equal(await sourceGroup.locator('.school-publication-context').innerText(),'示例周老师');
    assert.deepEqual(await sourceGroup.locator('[data-school-original-ref]').evaluateAll(xs=>xs.map(x=>x.dataset.schoolOriginalRef)),sourceRefs,'each saved original remains directly reachable');
    await sourceGroup.locator('[data-school-original-ref]').nth(2).click();await eventually(async()=>/虚构老师原话/.test(await p.locator('#schoolOriginalDialog').innerText()),'third original in compact group');await p.locator('#schoolOriginalDialog [data-school-original-close]').click();
    await p.reload({waitUntil:'load'});await ready(p);assert.equal(await sourceGroup.locator('[data-school-original-ref]').count(),4,'reopen preserves all four source entries');await proof(p,'compact-originals-'+width);
    currentTask.source=publication.ref;currentTask.agenda.publications=[publication];await p.reload({waitUntil:'load'});await ready(p);
    assert.deepEqual(await homework.locator('[data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask)),['TODAY']);
    assert.equal(await card('SIBLING').count(),0,'the first screen only shows the default child');
    for(const id of ['TODAY','SIBLING']){const task=state.tasks.find(t=>t.id===id),owner=state.children.find(c=>c.name===task.child);await p.locator('[data-child-filter="'+owner.id+'"]').click();await selectedChild(p,state.children,owner);assert.equal(await homework.locator('[data-homework-child]').count(),1,'only the selected child has a homework group');assert.equal(await card(id).locator('.task-owner').textContent(),task.child);assert.equal(await card(id).locator('xpath=ancestor::*[@data-homework-child][1]').getAttribute('data-homework-child'),owner.id,'task list belongs to the visibly selected child without repeating their name in every row');assert.equal(await card(id).evaluate(x=>!!x.closest('.task-list')),true,'homework stays in the task list');assert.equal(await card(id).locator('.task-next').isVisible(),false,'optional advice stays secondary while full requirement is visible');if(task.action.includes('\n')){assert.deepEqual(await card(id).locator('.task-requirement li').allTextContents(),task.action.split('\n'));assert.equal(await card(id).locator('.requirement-full').count(),0,'checking and signing requirements need no expansion')}else assert.equal(await card(id).locator('.task-requirement').innerText(),task.action);assert.equal(await card(id).locator('.primary').evaluate(x=>getComputedStyle(x).color),'rgb(13, 43, 44)','primary homework action has dark text on light background')}
    await p.locator('[data-child-filter="'+state.children[0].id+'"]').click();
    assert.deepEqual(await todos.locator('[data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask)),['ADMIN']);assert.equal(await card('ADMIN').isVisible(),true,'undated administration is visible without expanding the backlog');
    assert.equal(await card('ADMIN').evaluate(x=>!!x.closest('.task-list')),true,'administration uses the same task list');
    assert.equal(await card('ADMIN').getByRole('button',{name:'准备打印',exact:true}).count(),1);assert.equal(await card('ADMIN').getByRole('button',{name:'反馈进展',exact:true}).count(),1,'printing administration retains the same-task feedback entry');await card('ADMIN').getByRole('button',{name:'反馈进展',exact:true}).click();await p.locator('#taskDialog[open]').waitFor();assert.equal(await p.locator('#taskForm [name=id]').inputValue(),'ADMIN');assert.equal(await p.locator('#taskRequirement').innerText(),state.tasks.find(t=>t.id==='ADMIN').action);await p.locator('#taskDialog [data-close=taskDialog]').click();await p.locator('#taskDialog[open]').waitFor({state:'detached'});
    assert.match(await p.locator('.today-source-gap').innerText(),/消息读取有缺口，作业可能缺项。/);
    await p.locator('.today-source-gap [data-collection-check]').click();
    await eventually(async()=>await p.locator('body').getAttribute('data-page')==='sources','today source check opens receipts');
    assert.equal(sourceChecks,1,'one parent click requests exactly one original-background check');
    await eventually(async()=>width===360?/请求结果未确认/.test(await p.locator('[data-collection-notice]').innerText()):/只有原后台回执成功才算本次检查完成/.test(await p.locator('[data-collection-notice]').innerText()),'source check result or explicit failure');
    await p.locator('[data-collection-result]').click();assert.equal(sourceChecks,1,'updating receipts does not resubmit collection');
    await p.locator('nav [data-page="home"]').click();await ready(p);
    state.agent.enabled=true;state.agent.sources=[{id:'synthetic-audio',platform:'qq',child_id:state.children[0].id,name:'虚构学校群',enabled:true,last_success:new Date().toISOString(),last_attempt:new Date().toISOString(),next_collection_at:new Date(Date.now()+30*60*1000).toISOString(),unread_count:3,error:''}];
    await p.reload({waitUntil:'load'});await ready(p);
    assert.match(await p.locator('.today-source-gap').innerText(),/部分消息原件尚未读全。/);
    assert.equal(await p.locator('.today-source-gap [data-collection-check]').count(),0,'historical original gaps do not request another collection');
    await fit(p);await proof(p,'today-saved-original-gap-'+width);
    await p.locator('.today-source-gap [data-page="sources"]').click();assert.equal(sourceChecks,1);
    assert.match(await p.locator('[data-current-source="synthetic-audio"] [data-current-source-unread]').innerText(),/累计 3 条消息在采集时含图片、附件或截断内容；这不是待同步新消息数/);
    await fit(p);await proof(p,'source-saved-original-gap-'+width);
    await p.locator('nav [data-page="home"]').click();await ready(p);await fit(p);
    assert.match(await p.locator('.today-recent-homework h2').innerText(),/其他未完成作业 · 7/);
    assert.equal(await p.locator('.today-backlog').count(),0,'unknown dates do not collapse unfinished homework');
    for(const id of ['DONE','NA','DECLINED','ARCHIVE','WISH','PLANNED'])assert.equal(await card(id).count(),0,'closed items, wishes and future plans omitted: '+id);
    for(const id of ['PAST','FUTURE','UNKNOWN','INVALID','CANCEL-LINK'])assert.equal(await card(id).isVisible(),true,'unfinished deadline/undated tasks stay directly visible: '+id);
    assert.equal(await card('LINK').count(),1,'one task is not duplicated');
    assert.match(await card('PAST').innerText(),/逾期/);assert.match(await card('ADMIN').innerText(),/发布：待核对/);
    assert.match(await homework.locator('h2').innerText(),/今日作业 · 1/);assert.equal(await p.locator('[data-agent-item] [data-check]').count(),0,'unconfirmed notifications cannot be completed');
    const review=p.locator('.today-recent-homework #school-review-synthetic-school'),reviewLink=p.locator('.today-recent-homework .review-link');
    assert.ok((await card('TODAY').boundingBox()).y<(await review.boundingBox()).y,'confirmed homework stays before pending school work');
    assert.ok((await reviewLink.boundingBox()).height>=44,'pending review link is touch sized');await reviewLink.click();assert.equal(await review.evaluate(x=>document.activeElement===x),true,'pending review link focuses the notice');assert.notEqual(await review.evaluate(x=>getComputedStyle(x).outlineStyle),'none','focused notice remains visible to keyboard users');
    assert.deepEqual(await p.locator('[data-agent-item]').evaluateAll(xs=>xs.map(x=>x.dataset.agentItem)),['synthetic-school']);
    const notice=p.locator('[data-agent-item="synthetic-school"]'),gap=notice.locator('[data-school-review-gap]'),noticeDetails=notice.locator('.task-more');assert.equal(await gap.isVisible(),true,'specific unresolved issue is visible without expansion');assert.match(await gap.innerText(),/需要核对是否参加这次活动。/);assert.equal(await gap.evaluate(x=>!!x.closest('details')),false,'uncertainty must not be hidden in secondary details');assert.equal(await noticeDetails.evaluate(x=>x.open),false,'source explanations stay secondary');await noticeDetails.locator(':scope > summary').click();assert.doesNotMatch(await noticeDetails.innerText(),/需要核对是否参加这次活动。/,'the same gap is not repeated');await noticeDetails.locator(':scope > summary').click();
    assert.equal(await p.locator('[data-agent-item="synthetic-school"] h3').innerText(),'请准备虚构活动材料。');
    assert.match(await review.locator('.review-badge').innerText(),/作业 · 有信息待补充/,'newly posted homework remains visibly unconfirmed even when due later');
    assert.equal(await review.locator('[data-school-original-ref]').isVisible(),true,'parent can open the saved original without expanding secondary operations');
    assert.equal(await review.locator('.school-publication-context').innerText(),'示例周老师','pending and collected school tasks share publication context');
    await review.locator('[data-school-original-ref]').click();assert.equal(await p.locator('#schoolOriginalDialog').isVisible(),true);await eventually(async()=>/虚构老师原话/.test(await p.locator('#schoolOriginalDialog').innerText()),'saved original loaded');assert.match(await p.locator('#schoolOriginalDialog').innerText(),/虚构学校群 <甲班>/,'exact group remains in original details');assert.equal(await p.locator('#schoolOriginalDialog 甲班').count(),0,'group names are escaped text');await p.locator('#schoolOriginalDialog [data-school-original-close]').click();
    assert.match(await p.locator('[data-agent-item="synthetic-school"] details').textContent(),/⚠️重要通知⚠️/,'original heading is retained');
    assert.equal(await p.locator('#today-courses h2').innerText(),'今日课程与安排');const shared=p.locator('[data-query-target="calendar:shared:'+state.today+'"]');assert.equal(await shared.count(),1);assert.match(await shared.innerText(),new RegExp(state.children[0].name+'、'+state.children[1].name));
    assert.equal(await p.locator('.calendar-cancelled').count(),0);assert.equal(await p.locator('.calendar-event [data-check]').count(),0,'calendar-only events do not invent task completion');
    assert.equal(await p.locator('.calendar-timetable').evaluate(x=>x.open),true,'today lessons are expanded before any interaction');assert.equal(await p.locator('.calendar-timetable ol').isVisible(),true);assert.match(await p.locator('.calendar-timetable').innerText(),/虚构数学[\s\S]*虚构语文/);
    assert.equal(await p.locator('#today-courses').evaluate(x=>x.classList.contains('task-list')),true,'today courses use the same list section');assert.deepEqual(await p.locator('.calendar-timetable li strong').allTextContents(),['虚构数学','虚构语文']);const lessonBoxes=await p.locator('.calendar-timetable li').evaluateAll(xs=>xs.map(x=>({top:x.getBoundingClientRect().top,bottom:x.getBoundingClientRect().bottom})));assert.ok(lessonBoxes.every((x,i)=>!i||x.top>=lessonBoxes[i-1].bottom),'today courses stay one lesson per row');
    assert.deepEqual(await p.locator('nav [data-page]').evaluateAll(xs=>xs.map(x=>x.dataset.page)),['home','calendar','tasks','more']);
    assert.deepEqual(await p.locator('nav [data-page]').allTextContents(),['今天','日历','收集箱','更多']);
    assert.equal(await p.locator('[data-task-box]').count(),0,'collection tabs belong to inbox');
    assert.equal(await p.locator('#growthWorld,.universe').count(),0);assert.equal(resources.some(x=>/growth-world\.js|three\.(core|module)/.test(x)),false,'homepage never requests Three.js');
    await p.evaluate(()=>scrollTo(0,0)); // The timetable check above scrolled below the initial screen.
    const firstTask=card('TODAY'),position=await firstTask.locator('h3').boundingBox(),viewportHeight=await p.evaluate(()=>innerHeight);
    assert.ok(position&&position.y>=0&&position.y+position.height<viewportHeight-60,'first confirmed task stays on the first screen');
    assert.equal(await firstTask.locator('.task-requirement').isVisible(),true);assert.equal(await firstTask.locator('details .task-requirement').count(),0,'goal is not hidden');
    assert.equal(await firstTask.locator('.tasktools [data-task]').first().innerText(),'提交作业反馈');assert.equal(await firstTask.locator('[data-study-task-add]').textContent(),'作业计时');assert.equal(await firstTask.locator('[data-task-decisions]').isVisible(),false);await firstTask.locator('.task-more > summary').click();assert.equal(await firstTask.locator('[data-task-decisions]').isVisible(),true);await firstTask.locator('.task-more > summary').click();
    assert.equal(await firstTask.locator('.checkhit,button:visible,summary:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'44px actions');
    await p.locator('[data-child-filter="'+state.children[1].id+'"]').click();await selectedChild(p,state.children,state.children[1]);assert.equal(await card('SIBLING').isVisible(),true);assert.equal(await card('TODAY').count(),0);assert.equal(await p.locator('[data-agent-item]').count(),0);assert.equal(await shared.count(),1);
    assert.equal(await card('SIBLING').locator('.school-publication-context,[data-school-original-ref]').count(),0,'a publication for another child is not rendered');
    await p.locator('nav [data-page="tasks"]').click();await p.locator('nav [data-page="home"]').click();await ready(p);await selectedChild(p,state.children,state.children[1]);assert.equal(await card('TODAY').count(),0,'returning to today keeps the child selection');assert.equal(await card('SIBLING').isVisible(),true);
    await p.reload({waitUntil:'load'});await ready(p);await selectedChild(p,state.children,state.children[1]);assert.equal(await card('SIBLING').isVisible(),true);assert.equal(await card('TODAY').count(),0,'reload does not return to all children');
    await p.locator('[data-child-filter="'+state.children[0].id+'"]').click();
    assert.equal(await p.locator('#childFilter').count(),0);await selectedChild(p,state.children,state.children[0]);assert.equal(await p.locator('[data-child-filter="'+state.children[0].id+'"]').evaluate(x=>x===document.activeElement),true,'child choice preserves keyboard focus');assert.equal(await p.locator('.child-filters button').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false);
    await proof(p,'today-'+width);
    await p.locator('[data-task-all="homework"]').click();assert.equal(await p.locator('[data-task-box="全部"]').getAttribute('aria-pressed'),'true');for(const id of ['DONE','PAST','FUTURE','PLANNED','NA','DECLINED'])assert.equal(await card(id).count(),1,'all dates and decisions remain reachable: '+id);assert.equal(await homework.evaluate(x=>document.activeElement===x),true);
    await p.locator('[data-child-filter="'+state.children[1].id+'"]').click();assert.equal(await card('SIBLING').count(),1);assert.equal(await card('DONE').count(),0);await p.locator('nav [data-page="home"]').click();await ready(p);await selectedChild(p,state.children,state.children[1]);await p.locator('[data-child-filter="'+state.children[0].id+'"]').click();await p.locator('[data-task-all="todo"]').click();assert.equal(await todos.evaluate(x=>document.activeElement===x),true);assert.equal(await card('PLANNED').count(),1);assert.equal(await p.locator('[data-agent-item="synthetic-school"] h3').innerText(),'请准备虚构活动材料。');await fit(p);await proof(p,'all-items-'+width);
    await p.locator('nav [data-page="tasks"]').click();await p.locator('[data-task-box="已搁置"]').click();for(const id of ['NA','DECLINED','ARCHIVE']){assert.equal(await card(id).locator('[data-check]').count(),0,'closed non-completion has no completion checkbox');assert.equal(await card(id).locator('[data-task-restore]').isVisible(),true)}await p.locator('[data-task-box="已完成"]').click();assert.equal(await card('DONE').count(),1);assert.equal(await card('DECLINED').count(),0);assert.equal(await card('NA').count(),0);await proof(p,'completed-'+width);
    await p.locator('[data-task-box="已逾期"]').click();assert.equal(await card('PAST').count(),1);assert.equal(await card('INVALID').count(),0);assert.equal(await card('DONE').count(),0);await proof(p,'overdue-'+width);await fit(p);
    await p.locator('[data-task-box="Wish"]').click();assert.equal(await card('WISH').count(),1);await p.locator('[data-child-filter="'+state.children[1].id+'"]').click();assert.equal(await card('WISH').count(),0);assert.equal(await p.locator('[data-task-box="Wish"]').getAttribute('aria-pressed'),'true');await p.locator('[data-child-filter="'+state.children[0].id+'"]').click();await fit(p);await proof(p,'wish-'+width);

    for(const [page,title] of [['learning','学习任务与进展'],['growth','成长记录'],['reading','把一本书，变成一段旅程。'],['care','陪伴建议与反馈'],['agent','成长助手'],['print','家庭打印站'],['sources','来源与附件']]){
     await p.locator('nav [data-page="more"]').click();await p.locator('#content [data-page="'+page+'"]').click();
     if(page==='agent'){const ref=p.locator('[data-agent-item="synthetic-reference"]');assert.match(await ref.innerText(),/资料要点/);assert.match(await ref.innerText(),/参考说明 · 这段内容解释列标题，没有新作业。/);assert.equal(await ref.locator('[data-check]').count(),0);await proof(p,'school-reference-'+width)}
     assert.equal(await p.locator('#content h1').innerText(),title,'more opens '+page);assert.equal(await p.locator('nav [data-page="more"]').getAttribute('class'),'active');if(['learning','growth','reading'].includes(page)){await selectedChild(p,state.children,state.children[0]);await p.locator('[data-child-filter="'+state.children[1].id+'"]').click();await selectedChild(p,state.children,state.children[1]);await p.locator('[data-child-filter="'+state.children[0].id+'"]').click()}await fit(p);
    }
    assert.deepEqual(errors,[]);
    let printAttempts=0,draftCalls=0;const printBodies=[];
    await p.route('**/api/print/homework/materials?task_id=TODAY',r=>r.fulfill({json:{task:{id:'TODAY',child:state.children[0].name},files:['虚构题目.png','虚构题目续页.png'].map(name=>({name,source:{type:'attachment',name}})),school_error:''}}));
    await p.route('**/api/print/homework/draft',r=>{assert.equal(r.request().postDataJSON().task_id,'TODAY');draftCalls++;return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({draft:{text:'虚构第1题：卷面C，参考B；先找原文依据。',items:1,wrong_items:1,unknown_items:0,coverage:'一页'},question_sha256:'a'.repeat(64)})})});
    await p.route('**/api/print/homework',async route=>{printBodies.push(route.request().postDataJSON());printAttempts++;
      await route.fulfill({status:printAttempts===1?503:200,contentType:'application/json',body:JSON.stringify(printAttempts===1?{error:'虚构打印失败'}:{jobs:{question:{id:'1'.repeat(32)},questions:printBodies.at(-1).question_sources.map((_,n)=>({id:String(n+1).repeat(32)})),guide:{id:'2'.repeat(32)}}})})});
    await p.locator('nav [data-page="home"]').click();
    await p.locator('[data-child-filter="'+state.children[0].id+'"]').click();
    await p.locator('[data-query-target="task:TODAY"] details.task-more').evaluate(x=>x.open=true);await p.locator('[data-query-target="task:TODAY"] [data-homework-print]').click();
    const printForm=p.locator('#homeworkPrintForm');await p.locator('#homeworkPrintDialog[open]').waitFor();await printForm.locator('[name="question_source"]').selectOption({label:'虚构题目.png'});
    await printForm.locator('details summary').click();await printForm.locator('[name="question_source_2"]').selectOption({label:'虚构题目续页.png'});
    await p.locator('#homeworkDraftButton').click();await eventually(async()=>await printForm.locator('[name="guide_text"]').inputValue()==='虚构第1题：卷面C，参考B；先找原文依据。','draft filled');
    assert.match(await p.locator('#homeworkDraftStatus').innerText(),/1道可能错题、0道未判定/);
    await p.reload();await ready(p);await p.locator('[data-query-target="task:TODAY"] details.task-more').evaluate(x=>x.open=true);await p.locator('[data-query-target="task:TODAY"] [data-homework-print]').click();
    await p.locator('#homeworkPrintDialog[open]').waitFor();assert.equal(await printForm.locator('[name="guide_text"]').inputValue(),'虚构第1题：卷面C，参考B；先找原文依据。');assert.equal(draftCalls,1,'reopen never calls the model again');
    assert.equal(await printForm.locator('[name="question_source_2"]').inputValue().then(Boolean),true,'ordered second page survives reopen');
    await p.locator('#homeworkDraftButton').click();assert.equal(draftCalls,1,'existing parent draft is not overwritten or recharged');
    assert.match(await p.locator('#homeworkDraftStatus').innerText(),/已有参考文字/);
    await printForm.locator('[name="question_source_2"]').selectOption('');
    assert.equal(await printForm.evaluate(f=>f.dataset.questionSha),'a'.repeat(64),'changing pages keeps old fingerprint so the backend rejects stale reference');
    await printForm.locator('[name="question_source_2"]').selectOption({label:'虚构题目续页.png'});
    await printForm.locator('[name="question_confirmed"]').check();await printForm.locator('[name="guide_confirmed"]').check();await fit(p);
    await proof(p,'homework-print-dialog-'+width);
    await printForm.locator('[type="submit"]').click();await eventually(async()=>await printForm.locator('[type="submit"]').isEnabled(),'failed pair remains editable');
    assert.match(await p.locator('#homeworkPrintError').innerText(),/虚构打印失败/);
    await printForm.locator('[type="submit"]').click();await eventually(async()=>!await p.locator('#homeworkPrintDialog').isVisible(),'pair retried');
    assert.equal(printAttempts,2);assert.equal(printBodies[0].request_key,printBodies[1].request_key);
    assert.equal(printBodies[0].guide_source,null);assert.equal(printBodies[0].question_sources.length,2);assert.equal(printBodies[0].expected_question_sha256,'a'.repeat(64));assert.equal(await p.locator('body').getAttribute('data-page'),'print');
    let releaseDraft;
    await p.unroute('**/api/print/homework/draft');
    await p.route('**/api/print/homework/draft',async route=>{await new Promise(resolve=>releaseDraft=resolve);await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({draft:{text:'迟到的模型草稿',items:1,wrong_items:0,unknown_items:1},question_sha256:'b'.repeat(64)})})});
    await p.locator('nav [data-page="home"]').click();await p.locator('[data-query-target="task:TODAY"] details.task-more').evaluate(x=>x.open=true);await p.locator('[data-query-target="task:TODAY"] [data-homework-print]').click();
    await printForm.locator('[name="question_source"]').selectOption({label:'虚构题目.png'});
    await p.locator('#homeworkDraftButton').click();await eventually(async()=>!!releaseDraft,'delayed draft request');
    await printForm.locator('[name="guide_text"]').fill('家长在等待期间填写的参考');releaseDraft();
    await eventually(async()=>/本次草稿未覆盖/.test(await p.locator('#homeworkDraftStatus').innerText()),'late reply ignored');
    assert.equal(await printForm.locator('[name="guide_text"]').inputValue(),'家长在等待期间填写的参考');
    checks.push({width,kind:'classification',homeworkAndTodo:true,deadlinesCarryForward:true,wishesAndFuturePlansExcluded:true,pendingSeparate:true,childIsolation:true,defaultSingleChild:true,noAllChildren:true,childPersistsAcrossNavigationAndReload:true,taskLists:true,sharedCalendar:true,fourNavigationItems:true,moreEntriesReachable:true,noThree:true,taskTop:position.y,noOverflow:true,pairRetry:true});
   }finally{await p.close()}

   // Collected homework with no known date stays in the list; one notice can contain several distinct original files.
   const listPage=await browser.newPage({viewport:{width,height:820}}),listState=fixtures(await read()),first=listState.children[0],second=listState.children[1];
   const listSource='synthetic-list-'+width,listRef='message:'+listSource+':shared-notice',listErrors=[],requests=[];
   const listTask=(id,owner=first,when={})=>({id,child:owner.name,title:'虚构数学练习 '+id,due:'',original_status:'待跟进',source:'Agent建议:synthetic-origin-'+id+'\n'+listRef,school_origin:true,action:'完成第1至3题。\n第4题选做；每题写出过程。',history:[],focus:{mode:'next',box:'inbox'},agenda:{category:'homework',box:'inbox',published_on:'',due_on:'',scheduled_on:'',...when}});
   listState.tasks=[...Array.from({length:5},(_,n)=>listTask('LIST-'+n)),listTask('LIST-SIBLING',second),listTask('LIST-FUTURE',first,{scheduled_on:'2026-09-09'})];
   listState.agent.items=[];listState.agent.sources=[{id:listSource,child_id:first.id,name:'虚构班级',enabled:true}];
   listState.today_calendar={inbox:listState.tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',child_ids:[t.child===first.name?first.id:second.id],title:t.title,closed:false,status:'待跟进',agenda:t.agenda})),agenda:[],events:[],timetables:[]};
   const originalFiles=Array.from({length:5},(_,n)=>({id:String(n+1).repeat(32),name:'虚构练习-'+n+'.pdf',mime:'application/pdf',size:20}));
   let failure=true,unscoped=false,wrongTask=false,malformed=false,hold=false,releaseRead=null,lateDone=false;
   const originalView=ids=>{const task=listState.tasks.find(t=>t.id===ids.task_id),n=task?Number(task.id.slice(-1)):null;return {...ids,source_name:'虚构班级',message:{id:ids.message_id,kind:'text',sender:'示例老师',time:'',text:'五份虚构练习分别完成；独立要求及原件保留。'},attachments:task&&!unscoped?[originalFiles[n]]:originalFiles,unavailable_attachment_ids:[],pages:[],pdf_material:null,material_draft:null,...(task?{task_id:wrongTask?'wrong-task':task.id,...(!unscoped?{action_material:{scoped:true,quotes:malformed?[]:[{text:task.action,upload_ids:[originalFiles[n].id],pages:[]}]}}:{})}:{})}};
   try{
    listPage.on('pageerror',e=>listErrors.push(e.message));
    await listPage.route('**/api/state',route=>route.fulfill({json:listState}));
    await listPage.route('**/api/agent/message?*',async route=>{const ids=Object.fromEntries(new URL(route.request().url()).searchParams);requests.push(ids);const body=originalView(ids);if(hold){await new Promise(resolve=>releaseRead=resolve);await route.fulfill({json:body});lateDone=true;return}if(failure){failure=false;return route.fulfill({status:503,json:{error:'虚构本项资料读取失败'}})}return route.fulfill({json:body})});
    await listPage.goto(server.url,{waitUntil:'load'});await ready(listPage);await selectedChild(listPage,listState.children,first);
    const listCard=id=>listPage.locator('[data-query-target="task:'+id+'"]'),listDialog=listPage.locator('#schoolOriginalDialog');
    assert.match(await listPage.locator('#task-group-homework h2').innerText(),/今日作业 · 0/);assert.match(await listPage.locator('.today-recent-homework h2').innerText(),/其他未完成作业 · 5/);
    for(let n=0;n<5;n++){assert.equal(await listCard('LIST-'+n).isVisible(),true);assert.equal(await listCard('LIST-'+n).count(),1);assert.match(await listCard('LIST-'+n).innerText(),/发布：待核对[\s\S]*截止待核对/);assert.equal(await listCard('LIST-'+n).locator('.task-requirement').innerText(),'完成第1至3题。\n第4题选做；每题写出过程。')}
    assert.equal(await listCard('LIST-SIBLING').count(),0);assert.equal(await listCard('LIST-FUTURE').count(),0);assert.equal(await listPage.locator('.today-backlog').count(),0);await fit(listPage);await proof(listPage,'all-date-unknown-homework-'+width,true);
    const openMaterial=()=>listCard('LIST-0').locator('[data-school-original-ref]').click(),retry=listDialog.locator('[data-school-original-retry]'),closeList=()=>listDialog.locator('[data-school-original-close]').click();
    await openMaterial();await listDialog.getByText(/虚构本项资料读取失败/).waitFor();assert.equal(await listDialog.locator('.task-record-files').count(),0);await retry.click();await listDialog.locator('[data-task-material-scope="action"]').waitFor();
    assert.equal(requests[0].task_id,'LIST-0');assert.deepEqual(requests[0],requests[1]);assert.equal(await listDialog.locator('.task-record-files a').count(),1);assert.match(await listDialog.innerText(),/虚构练习-0.pdf/);assert.doesNotMatch(await listDialog.innerText(),/虚构练习-[1-4].pdf/);await fit(listPage);await proof(listPage,'list-material-retry-'+width);
    await listDialog.locator('[data-school-task-source]').click();await listDialog.getByRole('heading',{name:'老师完整原消息',exact:true}).waitFor();await eventually(async()=>await listDialog.locator('.task-record-files a').count()===5,'explicit full notice');assert.equal(requests.at(-1).task_id,undefined);await listDialog.locator('[data-school-task-source]').click();await listDialog.locator('[data-task-material-scope="action"]').waitFor();assert.equal(await listDialog.locator('.task-record-files a').count(),1);await closeList();
    await listPage.reload({waitUntil:'load'});await ready(listPage);await openMaterial();await listDialog.locator('[data-task-material-scope="action"]').waitFor();assert.equal(await listDialog.locator('.task-record-files a').count(),1);assert.equal(await listPage.locator('.today-recent-homework [data-today-task]').count(),5);await fit(listPage);await proof(listPage,'list-material-reopened-'+width);await closeList();
    for(const bad of ['unscoped','wrong-task','malformed']){unscoped=bad==='unscoped';wrongTask=bad==='wrong-task';malformed=bad==='malformed';await openMaterial();await listDialog.getByText(/本项资料(?:范围尚未核明|依据暂时无法核对)/).waitFor();assert.equal(await listDialog.locator('.task-record-files a').count(),0,'unverified full-notice response never becomes this task material');unscoped=false;wrongTask=false;malformed=false;await retry.click();await listDialog.locator('[data-task-material-scope="action"]').waitFor();await closeList()}
    // The detail entry must enforce the same scope as the list, even for an old successful unscoped reply.
    const taskDetail=listPage.locator('#taskDialog'),taskResources=taskDetail.locator('#taskSchoolResources'),feedbackNote=taskDetail.locator('#taskForm [name="note"]');
    unscoped=true;await listCard('LIST-0').locator('[data-task]').click();await taskResources.getByText(/本项资料范围尚未核明/).waitFor();
    assert.equal(await taskResources.locator('.task-record-files a').count(),0,'legacy whole-notice originals are not this task materials');
    assert.doesNotMatch(await taskResources.innerText(),/虚构练习-[0-4].pdf/);assert.equal(requests.at(-1).task_id,'LIST-0');
    await feedbackNote.fill('虚构未保存反馈保留');await taskResources.getByRole('button',{name:'查看老师完整原消息',exact:true}).click();
    await listDialog.getByRole('heading',{name:'老师原消息',exact:true}).waitFor();await eventually(async()=>await listDialog.locator('.task-record-files a').count()===5,'full source from detail is explicit');
    assert.equal(requests.at(-1).task_id,undefined);await listDialog.locator('[data-school-original-close]').click();assert.equal(await feedbackNote.inputValue(),'虚构未保存反馈保留');
    unscoped=false;await taskResources.getByRole('button',{name:'重试读取资料',exact:true}).click();await taskResources.locator('[data-task-material-scope="action"]').waitFor();
    assert.equal(await taskResources.locator('.task-record-files a').count(),1);assert.doesNotMatch(await taskResources.innerText(),/虚构练习-[1-4].pdf/);assert.equal(await feedbackNote.inputValue(),'虚构未保存反馈保留');
    await fit(listPage);await proof(listPage,'task-original-scope-retry-'+width);await feedbackNote.fill('');await taskDetail.locator('[data-close="taskDialog"]').click();
    await listPage.reload({waitUntil:'load'});await ready(listPage);await listCard('LIST-0').locator('[data-task]').click();await taskResources.locator('[data-task-material-scope="action"]').waitFor();assert.equal(await taskResources.locator('.task-record-files a').count(),1);await taskDetail.locator('[data-close="taskDialog"]').click();
    hold=true;await openMaterial();await eventually(()=>!!releaseRead,'pending list material');await closeList();await listPage.locator('[data-child-filter="'+second.id+'"]').click();await selectedChild(listPage,listState.children,second);releaseRead();await eventually(()=>lateDone,'late prior child response settled');assert.equal(await listDialog.isVisible(),false);assert.equal(await listCard('LIST-SIBLING').isVisible(),true);assert.equal(await listCard('LIST-0').count(),0);assert.doesNotMatch(await listPage.locator('#content').innerText(),/虚构练习-0.pdf/);await fit(listPage);await proof(listPage,'list-material-late-child-switch-'+width);assert.deepEqual(listErrors,[]);
    checks.push({width,kind:'homework-list-material',allDateUnknownVisible:true,fiveAssignmentsOnce:true,noInventedDeadline:true,futurePlanExcluded:true,scopedDefault:true,completeSourceExplicit:true,failedReadRetry:true,unscopedRejected:true,wrongTaskRejected:true,malformedScopeRetry:true,reopen:true,lateChildReplyIgnored:true,noOverflow:true});
   }finally{await listPage.close()}

   // A backfilled school notice keeps its original publication day; processing order must not bury recent notices.
   const orderState=fixtures(await read()),owner=orderState.children[0],baseTask=orderState.tasks.find(t=>t.id==='TODAY'),school=orderState.agent.items.find(x=>x.kind==='school');
   orderState.today='2026-09-28';
   const orderTask=(id,published,due='')=>({...baseTask,id,title:'虚构事项 '+id,source:'Agent建议:synthetic-school',due,agenda:{...baseTask.agenda,published_on:published,due_on:due}});
   orderState.tasks=[orderTask('OLD','2026-09-02'),orderTask('DUE-OLD','2026-09-20','2026-09-20'),orderTask('DUE-RECENT','2026-09-22','2026-09-27'),orderTask('DUE-TODAY','2026-09-27','2026-09-28'),orderTask('DUE-NEXT','2026-09-27','2026-09-29')];
   orderState.tasks.push({...orderTask('REVIEW-HOMEWORK','2026-09-02'),focus:{mode:'later',review_on:orderState.today,box:'inbox'}});
   const published=['2026-09-02','2026-09-20','2026-09-22','2026-09-27','2026-09-27'];
   orderState.agent.items=published.map((day,n)=>({...school,id:'notice-'+n,title:'虚构学校消息 '+n,child_id:owner.id}));
   orderState.today_calendar={inbox:[...orderState.tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',child_ids:[owner.id],title:t.title,agenda:t.agenda,status:'待跟进',closed:false})),...published.map((day,n)=>({id:'notice-'+n,task_id:'',kind:'school',child_ids:[owner.id],title:'虚构学校消息 '+n,agenda:{category:'todo',published_on:day,published_at:n===3?'2026-09-27T08:00:00+08:00':n===4?'2026-09-27T18:00:00+08:00':'',due_on:'',scheduled_on:'',box:'inbox'},status:'待核对',closed:false}))],agenda:[],events:[],timetables:[],source_error:''};
   const orderPage=await browser.newPage({viewport:{width,height:820}});
   try{
    await orderPage.route('**/api/state',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(orderState)}));
    await orderPage.goto(server.url,{waitUntil:'load'});await ready(orderPage);
    const taskOrder=()=>orderPage.locator('#task-group-homework [data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask));
    const earlierTasks=()=>orderPage.locator('.today-backlog [data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask));
    const recentNoticeOrder=()=>orderPage.locator('#task-group-todo [data-agent-item]').evaluateAll(xs=>xs.map(x=>x.dataset.agentItem));
    const olderNoticeOrder=()=>orderPage.locator('.today-backlog [data-agent-item]').evaluateAll(xs=>xs.map(x=>x.dataset.agentItem));
    assert.deepEqual(await taskOrder(),['DUE-TODAY']);
    assert.equal(await orderPage.locator('.today-reviews [data-today-task="REVIEW-HOMEWORK"]').isVisible(),true);assert.equal(await orderPage.locator('[data-today-task="REVIEW-HOMEWORK"]').count(),1,'one original homework appears once when its review is due');
    assert.deepEqual(await earlierTasks(),[]);
    for(const id of ['DUE-RECENT','DUE-OLD','OLD'])assert.equal(await orderPage.locator('.today-recent-homework [data-today-task="'+id+'"]').isVisible(),true,'unfinished school homework from older days is exposed');
    assert.match(await orderPage.locator('#task-group-homework h2').innerText(),/今日作业 · 1/,'pending notices do not become confirmed homework');
    assert.deepEqual(await recentNoticeOrder(),['notice-4','notice-3']);
    assert.deepEqual(await olderNoticeOrder(),['notice-2','notice-1','notice-0']);
    assert.match(await orderPage.locator('#task-group-todo').innerText(),/2026-09-27 18:00/);
    await orderPage.locator('#task-group-todo').scrollIntoViewIfNeeded();
    await proof(orderPage,'recent-school-review-'+width);
    await fit(orderPage);await orderPage.reload({waitUntil:'load'});await ready(orderPage);
    assert.deepEqual(await taskOrder(),['DUE-TODAY'],'current-day count persists after reload');
    assert.equal(await orderPage.locator('.today-reviews [data-today-task="REVIEW-HOMEWORK"]').isVisible(),true);assert.equal(await orderPage.locator('[data-today-task="REVIEW-HOMEWORK"]').count(),1,'direct review stays single after reopening');
    assert.deepEqual(await earlierTasks(),[],'unfinished school homework remains outside the folded backlog');
    for(const id of ['DUE-RECENT','DUE-OLD','OLD'])assert.equal(await orderPage.locator('.today-recent-homework [data-today-task="'+id+'"]').isVisible(),true,'older unfinished homework survives reload');
    assert.deepEqual(await recentNoticeOrder(),['notice-4','notice-3'],'recent source order persists after reload');
    assert.deepEqual(await olderNoticeOrder(),['notice-2','notice-1','notice-0'],'older source remains available after reload');
    assert.equal(await orderPage.locator('.today-recent-homework [data-today-task="DUE-NEXT"]').isVisible(),true,'received work is visible separately from work due today');
    const undated=orderTask('COLLECTED-UNDATED','2026-09-27');orderState.tasks.push(undated);
    orderState.today_calendar.inbox.push({id:undated.id,task_id:undated.id,kind:'task',child_ids:[owner.id],title:undated.title,agenda:undated.agenda,status:'待跟进',closed:false});
    for(let n=0;n<5;n++){
     const id='same-day-homework-'+n;orderState.agent.items.push({...school,id,title:'虚构英语练习 '+n,child_id:owner.id,plan:{school_task:{purpose:'learning',state:'review'}}});
     orderState.today_calendar.inbox.push({id,kind:'school',child_ids:[owner.id],title:'虚构英语练习 '+n,agenda:{category:'homework',published_on:'2026-09-27',published_at:'2026-09-27T17:00:00+08:00',due_on:'',scheduled_on:'',box:'inbox'},status:'待核对',closed:false});
    }
    await orderPage.reload({waitUntil:'load'});await ready(orderPage);
    assert.deepEqual(await taskOrder(),['DUE-TODAY']);assert.match(await orderPage.locator('#task-group-homework h2').innerText(),/今日作业 · 1/);
    const received=orderPage.locator('.today-recent-homework');assert.match(await received.locator('h2').innerText(),/其他未完成作业 · 10/);
    assert.equal(await received.locator('[data-today-task="COLLECTED-UNDATED"]').isVisible(),true);
    for(let n=0;n<5;n++){const candidate=received.locator('[data-agent-item="same-day-homework-'+n+'"]');assert.equal(await candidate.isVisible(),true,'all work from the same sending day is exposed');assert.equal(await candidate.locator('[data-check]').count(),0,'unresolved work cannot be marked complete')}
    assert.equal(await orderPage.locator('[data-today-task="COLLECTED-UNDATED"]').count(),1);
    await fit(orderPage);await received.scrollIntoViewIfNeeded();await proof(orderPage,'all-received-homework-'+width);
    await orderPage.reload({waitUntil:'load'});await ready(orderPage);assert.equal(await orderPage.locator('.today-recent-homework [data-agent-item]').count(),5,'same-day homework stays available after reopening');
    checks.push({width,kind:'today-business-sort',confirmedDates:true,backfilledNoticeDates:true,reload:true,noOverflow:true});
   }finally{await orderPage.close()}

   // These writes go to the disposable demo's real API. No response fixture is active.
   const current=await read(),who=current.children[0],other=current.children[1],title='虚构数学作业 '+width;
   const response=await fetch(server.url+'api/task/new',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':current.token},body:JSON.stringify({child:who.name,title,due:current.today,source:'虚构测试通知',action:'虚构要求'})});
   assert.equal(response.ok,true);const task=(await read()).tasks.find(t=>t.title===title);assert.ok(task);
   const formPage=await browser.newPage({viewport:{width,height:820}}),formErrors=[],posts=[];
   formPage.on('pageerror',e=>formErrors.push(e.message));formPage.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
   try{
    await formPage.goto(server.url,{waitUntil:'load'});await ready(formPage);await fit(formPage);
    // Preserve the school task -> timer -> result -> original task journey.
    await formPage.locator('[data-query-target="task:'+task.id+'"] details.task-more').evaluate(x=>x.open=true);await formPage.locator('[data-study-task-add="'+task.id+'"]').click();await eventually(()=>formPage.locator('[data-study-ready]').isVisible(),'task opens timer');assert.equal(await formPage.locator('nav [data-page="more"]').getAttribute('class'),'active');
    const add=formPage.locator('[data-study-form="new"]');await eventually(async()=>await add.locator('[name="task_id"]').inputValue()===task.id,'source selected');assert.equal(await add.locator('[name="title"]').inputValue(),title);await add.locator('[name="planned_minutes"]').fill('10');await add.locator('[type="submit"]').click();
    const studyRead=async()=>await(await fetch(server.url+'api/study?child_id='+who.id+'&day='+current.today)).json();await eventually(async()=>(await studyRead()).items.some(x=>x.task_id===task.id),'study item saved');const studyID=(await studyRead()).items.find(x=>x.task_id===task.id).id,study=formPage.locator('[data-study-item="'+studyID+'"]');
    await study.locator('[data-study-action="start"]').click();await eventually(async()=>(await studyRead()).items.find(x=>x.id===studyID).status==='running','timer started');await study.locator('[data-study-action="pause"]').click();await eventually(async()=>(await studyRead()).items.find(x=>x.id===studyID).status==='paused','timer paused');
    await study.locator('[data-study-editor="finish"]').click();const finish=formPage.locator('[data-study-form="finish"]');await finish.locator('[value="需要帮助"]').check();await finish.locator('[name="actual_minutes"]').fill('8');await finish.locator('summary').click();await finish.locator('[name="note"]').fill('虚构反馈：最后一题需要提示');await finish.locator('[type="submit"]').click();await eventually(async()=>(await studyRead()).items.find(x=>x.id===studyID).result==='需要帮助','partial result saved');
    assert.notEqual((await read()).tasks.find(t=>t.id===task.id).update?.status,'已完成','needs help never completes source task');await study.locator('[data-study-task]').click();await eventually(()=>formPage.locator('[data-query-target="task:'+task.id+'"]').isVisible(),'source task reachable from timer');await formPage.locator('nav [data-page="home"]').click();await ready(formPage);
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
    await formPage.locator('nav [data-page="tasks"]').click();await formPage.locator('[data-task-box="已完成"]').click();assert.equal(await formPage.locator('[data-query-target="task:'+task.id+'"] [data-check]').isChecked(),true,'saved completion remains in completed box after reload');
    await formPage.locator('[data-child-filter="'+other.id+'"]').click();await formPage.locator('nav [data-page="more"]').click();await formPage.locator('[data-capture]').click();await eventually(()=>formPage.locator('#recordDialog').isVisible(),'record feedback for selected child');
    const form=formPage.locator('#recordForm');assert.equal(await form.locator('[name="child"]').inputValue(),other.name);assert.equal(await form.locator('[name="category"]').inputValue(),'学习进展');
    const recordTitle='虚构首页学习记录 '+width,recordNote='虚构观察：能说出思路，最后一步仍需要提示。';
    await form.locator('[name="title"]').fill(recordTitle);await form.locator('[name="note"]').fill(recordNote);await fit(formPage);await proof(formPage,'today-capture-'+width);
    await form.locator('[type="submit"]').click();await eventually(async()=>!(await formPage.locator('#recordDialog').isVisible())&&(await read()).records.some(r=>r.title===recordTitle),'manual learning record saved');
    await formPage.reload({waitUntil:'load'});await ready(formPage);
    const saved=(await read()).records.filter(r=>r.title===recordTitle);assert.equal(saved.length,1);assert.equal(saved[0].child,other.name);assert.equal(saved[0].category,'学习进展');assert.equal(saved[0].note,recordNote);
    assert.equal(posts.filter(x=>x==='/api/task').length,1);assert.equal(posts.filter(x=>x==='/api/record').length,1);assert.deepEqual(formErrors,[]);
    checks.push({width,kind:'persistent-interactions',checkboxPersists:true,immediatePendingState:true,failedSaveRestored:true,postSaveFullStateRequests:stateReads,selectedChildCorrect:true,manualRecordSavedOnce:true,timerAndResultSourceJourney:true,noOverflow:true,pageErrors:0});
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
    await d.locator('[data-query-target="task:'+id+'"] .task-more > summary').click();await d.locator('[data-task-decisions="'+id+'"]').click();await eventually(()=>d.locator('#taskDecisionDialog').isVisible(),'explicit task decision');
   },choose=async(status,note='')=>{
    await d.locator('#taskDecisionForm [name="status"][value="'+status+'"]').check();await d.locator('#taskDecisionForm [name="note"]').fill(note);
   },save=()=>d.locator('#taskDecisionForm [type="submit"]').click(),goTasks=async()=>{
    await d.locator('nav [data-page="tasks"]').click();await eventually(()=>d.locator('[data-task-box="已搁置"]').isVisible(),'inbox history ready');
   },readTask=async id=>(await read()).tasks.find(t=>t.id===id);
   try{
    await d.goto(server.url,{waitUntil:'load'});await ready(d);await open(decline.id);
    assert.equal(await d.locator('#taskDecisionForm > p.small.muted').innerText(),'移到收集箱“已搁置”，保留出处和决定，随时可以恢复。这里的选择不会向学校发送消息。');
    assert.equal(await d.locator('#taskDecisionForm [name="status"]:checked').count(),0,'dismissal requires an explicit choice');
    const postCount=writes.length;await save();assert.equal(writes.length,postCount,'empty choice never writes');
    await choose('不参加','虚构反馈：这次想休息');await fit(d);await proof(d,'dismiss-choice-'+width);await save();
    await eventually(async()=>!(await d.locator('#taskDecisionDialog').isVisible())&&!(await card(decline.id).count())&&(await readTask(decline.id)).update?.status==='不参加','declined item removed from today');
    assert.equal(await card(sibling.id).count(),0,'other child is absent from the selected child list');await d.locator('[data-child-filter="'+other.id+'"]').click();assert.equal(await card(sibling.id).isVisible(),true,'other child task remains reachable and unchanged');await d.locator('[data-child-filter="'+who.id+'"]').click();
    await d.reload({waitUntil:'load'});await ready(d);assert.equal(await card(decline.id).count(),0,'dismiss persists after refresh');
    await goTasks();assert.equal(await card(decline.id).count(),0,'dismissal is no longer active');assert.equal((await readTask(decline.id)).update.status,'不参加','dismissal is not completion');
    await d.locator('[data-task-box="已完成"]').click();assert.equal(await card(decline.id).count(),0,'declined is never completed');await d.locator('[data-task-box="已搁置"]').click();assert.equal(await card(decline.id).count(),1);assert.equal(await card(decline.id).locator('[data-check]').count(),0,'dismissed card cannot be accidentally checked complete');
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
    await d.locator('[data-task-box="已搁置"]').click();assert.match(await card(ignore.id).innerText(),/无需处理/);assert.equal(await card(ignore.id).locator('[data-check]').count(),0);

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

   // Real calendar saves and a week overview, including another day and both children.
   const w=await browser.newPage({viewport:{width,height:820}}),weekErrors=[];w.on('pageerror',e=>weekErrors.push(e.message));
   try{
    const state=await read(),date=new Date(state.today+'T12:00:00Z');date.setUTCDate(date.getUTCDate()-((date.getUTCDay()+6)%7));const monday=date.toISOString().slice(0,10);date.setUTCDate(date.getUTCDate()+5);const saturday=date.toISOString().slice(0,10),title='虚构周末观察 '+width;date.setUTCDate(date.getUTCDate()+1);const sunday=date.toISOString().slice(0,10);
    await w.goto(server.url);await ready(w);await w.locator('nav [data-page="calendar"]').click();await eventually(async()=>await w.locator('[data-calendar-column]').count()===7,'seven populated day columns');await fit(w);
    // Weekly timetable uses the same collapsed, ordered list as day details.
    const lessons=[{slot:'第一节',title:'虚构语文'},{slot:'第二节',title:'虚构数学'},{slot:'第三节',title:'虚构英语'}];
    await w.route('**/api/calendar?*',async route=>{const response=await route.fetch(),body=await response.json();body.timetables.push({id:'synthetic-week-table',day:state.today,child_id:state.children[0].id,title:'虚构课表',sessions:lessons});await route.fulfill({response,json:body})});
    await w.reload();await ready(w);await w.locator('nav [data-page="calendar"]').click();
    const table=w.locator('[data-calendar-column="'+state.today+'"] .calendar-timetable');await table.waitFor();
    assert.equal(await table.evaluate(e=>e.open),false,'week timetable starts collapsed');
    await table.locator('summary').click();assert.deepEqual(await table.locator('li strong').allTextContents(),lessons.map(x=>x.title));
    const boxes=await table.locator('li').evaluateAll(xs=>xs.map(x=>({top:x.getBoundingClientRect().top,bottom:x.getBoundingClientRect().bottom})));
    assert.ok(boxes.every((x,i)=>!i||x.top>=boxes[i-1].bottom),'one lesson per row in original order');await table.locator('li').last().scrollIntoViewIfNeeded();await fit(w);await proof(w,'week-timetable-open-'+width);
    await table.locator('summary').click();assert.equal(await table.evaluate(e=>e.open),false);await proof(w,'week-timetable-closed-'+width);
    await w.unroute('**/api/calendar?*');await w.reload();await ready(w);await w.locator('nav [data-page="calendar"]').click();await eventually(async()=>await w.locator('[data-calendar-column]').count()===7,'real week reloaded');
    await w.locator('[data-calendar-new]').click();const form=w.locator('#calendarForm');await form.locator('[name="title"]').fill(title);await form.locator('[name="day"]').fill(saturday);await form.locator('[name="start_time"]').fill('16:30');await form.locator('[name="status"]').selectOption('confirmed');
    const children=form.locator('input[name="child_ids"]');for(const c of await children.all())await c.uncheck();await form.locator('input[name="child_ids"][value="'+state.children[0].id+'"]').check();
    await w.route('**/api/calendar/save',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构保存失败'})}));await form.locator('[type="submit"]').click();await eventually(()=>form.locator('[type="submit"]').isEnabled(),'failed plan preserves form');assert.equal(await form.locator('[name="title"]').inputValue(),title);assert.match(await w.locator('#calendarFormError').innerText(),/失败/);await w.unroute('**/api/calendar/save');await form.locator('[type="submit"]').click();await eventually(async()=>!await w.locator('#calendarDialog').isVisible(),'plan saved');
    const tile=()=>w.locator('[data-calendar-column="'+saturday+'"] .calendar-week-item').filter({hasText:title});await eventually(()=>tile().isVisible(),'Saturday plan visible without selecting Saturday');assert.equal(await w.locator('[data-calendar-column]').count(),7);await fit(w);const selectedColumn=await w.locator('.calendar-day-heading[aria-pressed="true"]').boundingBox();assert.ok(selectedColumn.x<width&&selectedColumn.x+selectedColumn.width>0,'selected date actually lies inside the viewport');if(width===360)assert.ok(await w.locator('.calendar-week-scroll').evaluate(x=>x.scrollLeft)>0,'mobile week moves to selected date');await proof(w,'week-'+width);
    await w.locator('[data-calendar-child="'+state.children[1].id+'"]').click();assert.equal(await tile().count(),0);await w.locator('[data-calendar-child="'+state.children[0].id+'"]').click();assert.equal(await tile().count(),1);await tile().scrollIntoViewIfNeeded();
    // Playwright may scroll again for click actionability. Measure at the actual gesture,
    // before application handlers run, so its preparatory scroll is not blamed on selection.
    await w.evaluate(()=>document.addEventListener('pointerdown',()=>{window.calendarScrollBeforeSelection=document.querySelector('.calendar-week-scroll').scrollLeft},{capture:true,once:true}));
    await tile().click();const beforeScroll=await w.evaluate(()=>window.calendarScrollBeforeSelection);assert.equal(typeof beforeScroll,'number');assert.equal(await w.locator('.calendar-week-scroll').evaluate(x=>x.scrollLeft),beforeScroll,'day selection preserves horizontal position');assert.match(await w.locator('#calendarDayDetails').innerText(),new RegExp(saturday));assert.equal(await w.locator('#calendarDayDetails').evaluate(x=>document.activeElement===x),true);assert.equal(await w.locator('.agenda-groups .calendar-event').filter({hasText:title}).count(),1);
    await w.reload();await ready(w);await w.locator('nav [data-page="calendar"]').click();await eventually(()=>tile().isVisible(),'saved plan survives reopen');
    await w.route('**/api/calendar?*',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构日历暂不可读'})}));await w.locator('[data-calendar-shift="7"]').click();await eventually(()=>w.locator('[data-calendar-retry]').isVisible(),'failed week read has retry');assert.equal(await w.locator('[data-calendar-column]').count(),0,'failed new week is not presented as empty success');await w.unroute('**/api/calendar?*');await w.locator('[data-calendar-retry]').click();await eventually(async()=>await w.locator('[data-calendar-column]').count()===7,'week retry restored');await w.locator('[data-calendar-shift="-7"]').click();await eventually(()=>tile().isVisible(),'prior week preserved');await fit(w);
    await tile().click();const savedPlan=w.locator('.agenda-groups .calendar-event').filter({hasText:title}),complete=savedPlan.locator('[data-calendar-complete]');await complete.scrollIntoViewIfNeeded();const beforeComplete=await savedPlan.boundingBox();await complete.click();assert.equal(await form.locator('[name="status"]').inputValue(),'completed');await form.locator('[type="submit"]').click();await eventually(async()=>await w.locator('[data-calendar-column]').count()===7&&await savedPlan.locator('.calendar-status').innerText()==='已完成','calendar completion read back');const afterComplete=await savedPlan.boundingBox();assert.ok(Math.abs(afterComplete.y-beforeComplete.y)<120,'calendar completion keeps the working card in place');assert.equal(await savedPlan.evaluate(x=>x===document.activeElement),true,'completed card retains keyboard focus');
    // A recurring plan has distinct daily times but remains one editable series.
    const repeatTitle='虚构循环阅读 '+width;
    await w.locator('[data-calendar-new]').click();await form.locator('[name="title"]').fill(repeatTitle);await form.locator('[name="day"]').fill(monday);await form.locator('[name="start_time"]').fill('07:00');await form.locator('[name="end_time"]').fill('07:10');await form.locator('[name="repeat"]').selectOption('weekly');await form.locator('[name="until"]').fill(sunday);
    assert.deepEqual(await form.locator('[name="repeat_weekday"]:checked').evaluateAll(xs=>xs.map(x=>x.value)),['1']);const tuesday=new Date(monday+'T12:00:00Z');tuesday.setUTCDate(tuesday.getUTCDate()+1);await form.locator('[name="day"]').fill(tuesday.toISOString().slice(0,10));assert.deepEqual(await form.locator('[name="repeat_weekday"]:checked').evaluateAll(xs=>xs.map(x=>x.value)),['2']);await form.locator('[name="day"]').fill(monday);
    for(const day of await form.locator('[name="repeat_weekday"]').all())await day.uncheck();for(const day of ['1','3','5'])await form.locator('[name="repeat_weekday"][value="'+day+'"]').check();
    await form.locator('[name="day"]').fill(tuesday.toISOString().slice(0,10));assert.deepEqual(await form.locator('[name="repeat_weekday"]:checked').evaluateAll(xs=>xs.map(x=>x.value)),['1','3','5']);tuesday.setUTCDate(tuesday.getUTCDate()+1);assert.match(await w.locator('#calendarRepeatNote').innerText(),new RegExp('首次日期：'+tuesday.toISOString().slice(0,10)));await form.locator('[name="day"]').fill(monday);
    for(const c of await form.locator('[name="child_ids"]').all())await c.uncheck();await form.locator('[name="child_ids"][value="'+state.children[0].id+'"]').check();
    await w.locator('#calendarAddTime').click();await form.locator('[data-slot-start]').fill('19:00');await form.locator('[data-slot-end]').fill('19:10');await fit(w);await proof(w,'repeat-form-'+width);
    let lost=false;await w.route('**/api/calendar/save',async route=>{if(!lost){lost=true;await route.fetch();await route.abort('failed')}else await route.continue()});await form.locator('[type="submit"]').click();await eventually(async()=>lost&&await form.locator('[type="submit"]').isEnabled(),'repeat save can reconcile lost reply');assert.equal(await form.locator('[data-slot-start]').inputValue(),'19:00');await w.unroute('**/api/calendar/save');await form.locator('[type="submit"]').click();await eventually(async()=>!await w.locator('#calendarDialog').isVisible(),'repeat retry saved');
    const readRepeat=async()=>{const r=await(await fetch(server.url+'api/calendar?start='+monday+'&end='+sunday)).json();return r.events.filter(e=>e.title===repeatTitle)};
    let repeats=await readRepeat();assert.equal(repeats.length,6);assert.equal(new Set(repeats.map(e=>e.series_id||e.id)).size,1);const extraID=repeats.find(e=>e.start_time==='19:00').id;
    await w.reload();await ready(w);await w.locator('nav [data-page="calendar"]').click();await eventually(async()=>await w.locator('[data-calendar-column]').count()===7,'repeat visible after reopen');await w.locator('[data-calendar-child="'+state.children[1].id+'"]').click();assert.equal(await w.locator('.calendar-week-item').filter({hasText:repeatTitle}).count(),0);await w.locator('[data-calendar-child="'+state.children[0].id+'"]').click();assert.equal(await w.locator('.calendar-week-item').filter({hasText:repeatTitle}).count(),6);
    await w.locator('[data-calendar-day="'+monday+'"][data-calendar-detail]').first().click();const extraCard=w.locator('.agenda-groups [data-calendar-edit="'+extraID+'"]');await extraCard.click();assert.equal(await form.locator('.is-selected-slot').evaluate(x=>document.activeElement===x),true);assert.match(await form.locator('.is-selected-slot [data-slot-label]').innerText(),/时段 2.*正在修改/);await proof(w,'repeat-edit-'+width);assert.equal(await form.locator('[name="start_time"]').inputValue(),'07:00','editing an extra slot preserves the primary time');assert.deepEqual(await form.locator('[name="repeat_weekday"]:checked').evaluateAll(xs=>xs.map(x=>x.value)),['1','3','5']);await form.locator('[data-slot-start]').fill('19:30');await form.locator('[data-slot-end]').fill('19:40');await form.locator('[type="submit"]').click();await eventually(async()=>!await w.locator('#calendarDialog').isVisible(),'repeat edit saved');repeats=await readRepeat();assert.equal(repeats.find(e=>e.start_time==='19:30').id,extraID);assert.equal(repeats.length,6);await fit(w);await proof(w,'repeat-week-'+width);
    for(const [mode,count] of [['daily',7],['weekends',2],['monthly',3]]){
     await w.locator('[data-calendar-new]').click();const name='虚构重复方式 '+mode+' '+width;await form.locator('[name="title"]').fill(name);await form.locator('[name="day"]').fill(monday);await form.locator('[name="repeat"]').selectOption(mode);await form.locator('[name="until"]').fill(sunday);
     if(mode==='monthly')await form.locator('[name="repeat_monthdays"]').fill([0,2,4].map(n=>{const d=new Date(monday+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.getUTCDate()}).join('、'));
     await form.locator('[type="submit"]').click();await eventually(async()=>!await w.locator('#calendarDialog').isVisible(),'saved '+mode);
     const rows=(await(await fetch(server.url+'api/calendar?start='+monday+'&end='+sunday)).json()).events.filter(e=>e.title===name);assert.equal(rows.length,count,mode+' exact day count');assert.ok(rows.every(e=>e.start_time===''&&e.repeat===mode),'no invented clocks for '+mode);
    }
    checks.push({width,kind:'repeat-plan',customWeekdays:true,defaultFollowsDate:true,explicitWeekdaysPreserved:true,selectedSlotFocused:true,dailyWeekendMonthly:true,twoTimes:true,lostReplyRetry:true,reopen:true,oneSeries:true,extraSlotEditPreservesPrimary:true,stableSlotIDs:true,childIsolation:true,noOverflow:true});
    assert.deepEqual(weekErrors,[]);checks.push({width,kind:'week-calendar',sevenDays:true,otherDayVisible:true,saveRetry:true,reopen:true,childIsolation:true,dayDetails:true,readRetry:true,noOverflow:true});
   }catch(e){await proof(w,'week-failure-'+width);console.error(await w.locator('#content').innerText());throw e}finally{await w.close()}
  }
  const result={passed:checks.length,syntheticOnly:true,realPhone:false,checks};
  if(process.env.TODAY_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.TODAY_UI_PROOF_DIR,'today-ui-passed.json'),JSON.stringify(result,null,2)+'\n')}
  console.log(JSON.stringify(result,null,2));
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
