// Synthetic calendar UI checks. No family API, external service or persistent data.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {readFileSync}=require('node:fs'),{randomUUID}=require('node:crypto');
const source=readFileSync(__dirname+'/calendar.js','utf8');
const clean=x=>JSON.parse(JSON.stringify(x));
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function harness(){
 const elements=new Map(),handlers={},h={calls:[],notices:[],renders:0};
 const names=['id','version','title','category','day','start_time','end_time','location','note','status','repeat','until','repeat_monthdays'];
 const get=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,open:false,classList:{toggle(){}},setAttribute(){},addEventListener(){},showModal(){this.open=true},close(){this.open=false},focus(){h.focus=id},select(){this.selectionStart=0;this.selectionEnd=this.value.length},setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end},reset(){},querySelectorAll(){return[]},elements:Object.fromEntries(names.map(n=>[n,{value:'',disabled:false}]))});return elements.get(id)};
 h.reply=async()=>({ok:true,status:200,json:async()=>({events:[],timetables:[],source_error:''})});
 const ctx=vm.createContext({data:{today:'2026-09-08',token:'synthetic-first-token',children:[{id:'child-a',name:'小溪'},{id:'child-b',name:'小岚'}],tasks:[]},page:'calendar',child:'',window:{addEventListener(){}},document:{addEventListener(k,f){const prior=handlers[k];handlers[k]=e=>{prior?.(e);f(e)}},querySelectorAll(){return[]}},$:get,esc:escape,sourceCoverageHTML:()=>'<div data-synthetic-source-state>虚构读取状态</div>',endpoint:p=>'/family/'+p.replace(/^\//,''),status:t=>t.update.status,taskDismissed:t=>['不参加','不适用'].includes(t.update.status),taskStatusLabel:v=>v==='不适用'?'无需处理':v,render:()=>h.renders++,toast:s=>h.notices.push(s),crypto:{randomUUID},AbortController,setTimeout,clearTimeout,apiFetch:async(p,o)=>{h.calls.push({path:p,...o});return h.reply(p,o)},load:async()=>{},FormData:class{constructor(){return Object.entries(Object.fromEntries(names.map(n=>[n,get('#calendarForm').elements[n].value])))} }});
 Object.assign(ctx,{URL,location:{href:'https://family.example/family/?child=child-a#week'},navigator:{clipboard:{async writeText(value){h.copied=value}}}});
 const app=readFileSync(__dirname+'/app.js','utf8');vm.runInContext(app.slice(app.indexOf('function exactTaskDay('),app.indexOf('function todayChildHTML(')),ctx);
 vm.runInContext(source,ctx);ctx.calendarHTML();Object.assign(h,{ctx,get,state:()=>vm.runInContext('calendarState',ctx),pending:()=>vm.runInContext('calendarPending',ctx),click:handlers.click});return h;
}
const event=(extra={})=>({id:'a'.repeat(32),version:1,child_ids:['child-a','child-b'],title:'虚构共同阅读',category:'family',day:'2026-09-12',series_day:'2026-09-05',start_time:'',end_time:'',location:'',note:'',status:'tentative',repeat:'weekly',until:'',editable:true,source:'',task_id:'',...extra});
test('date navigation crosses month/year and leap day without local timezone shifts',()=>{
 const h=harness();assert.equal(h.ctx.calendarMonday('2027-01-01'),'2026-12-28');assert.equal(h.ctx.calendarAdd('2024-02-28',1),'2024-02-29');assert.equal(h.ctx.calendarAdd('2026-12-31',1),'2027-01-01');
 h.ctx.calendarNavigate('2027-01-03');assert.deepEqual(clean(h.ctx.calendarDays()),['2026-12-28','2026-12-29','2026-12-30','2026-12-31','2027-01-01','2027-01-02','2027-01-03']);
});
test('shared activities appear once per selected child; read-only schools link to current task',()=>{
 const h=harness(),s=h.state(),items=[event(),event({id:'b'.repeat(32),child_ids:['child-b']})];s.childID='child-a';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,1);s.childID='child-b';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,2);s.childID='';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,2);
 h.ctx.data.tasks=[{id:'X1',child:'小溪',update:{status:'不适用'}}];const html=h.ctx.calendarEventHTML(event({id:'source:x',task_id:'X1',editable:false,status:'confirmed'}));assert.match(html,/核对原事项/);assert.match(html,/小溪：无需处理/);assert.match(html,/calendar-confirmed/);assert.doesNotMatch(html,/小岚：无需处理|学校已取消/);assert.doesNotMatch(html,/data-calendar-edit/);h.ctx.data.tasks[0].update.status='不参加';assert.match(h.ctx.calendarEventHTML(event({task_id:'X1'})),/小溪：不参加/);h.ctx.data.tasks[0].child='未知归属';assert.doesNotMatch(h.ctx.calendarEventHTML(event({task_id:'X1'})),/家庭决定|：不参加/);
});
test('source/title fields are escaped and the selected day keeps missing timetable explicit',()=>{
 const h=harness();h.state().result={events:[],timetables:[],source_error:''};assert.match(h.ctx.calendarAgendaHTML(),/当天课表尚未提供/);assert.match(h.ctx.calendarAgendaHTML(),/2026-09-08/);
 const html=h.ctx.calendarEventHTML(event({title:'<img src=x onerror="bad()">',note:'<script>bad()</script>',source:'"<&',status:'cancelled'}));assert.doesNotMatch(html,/<img|<script>/);assert.match(html,/已取消/);assert.match(html,/&lt;img/);assert.match(html,/时间未填写/);
});
test('preparation stays outside collapsed metadata, even without a source',()=>{
 const h=harness(),note='先领取材料\n带上水杯和已经签字的回执',html=h.ctx.calendarEventHTML(event({note,source:'虚构通知'}));
 assert.ok(html.indexOf('class="source calendar-requirements"')<html.indexOf('<details>'));
 assert.ok(html.indexOf(note)<html.indexOf('<details>'));
 assert.ok(html.indexOf('出处：虚构通知')>html.indexOf('<details>'));
 assert.match(html,/2026-09-12/);
 const ordinary=h.ctx.calendarEventHTML(event({note,repeat:'none',source:''}));assert.match(ordinary,/calendar-requirements/);assert.doesNotMatch(ordinary,/<details>/);
 assert.match(h.ctx.calendarEventHTML(event({note:'',source:''})),/起点 2026-09-05/,'weekly rules remain reachable without a source');
});
test('editing a weekly instance starts at the series date and weekend suggestions only open a tentative draft',async()=>{
 const h=harness();h.ctx.calendarOpen(event());assert.equal(h.get('#calendarForm').elements.day.value,'2026-09-05');assert.match(h.get('#calendarEditNote').textContent,/修改未单独处理的重复日期/);assert.equal(h.calls.length,0);
 h.get('#calendarWeekendDay').value='2026-09-13';const b={dataset:{calendarDraft:'运动'},hasAttribute(){return false}};await h.click({target:{closest:()=>b}});assert.equal(h.get('#calendarForm').elements.day.value,'2026-09-13');assert.equal(h.get('#calendarForm').elements.status.value,'tentative');assert.equal(h.calls.length,0);
});
test('a late response from a previous week cannot replace the selected week',async()=>{
 const h=harness(),pending=[];h.reply=()=>new Promise(resolve=>pending.push(resolve));const first=h.ctx.calendarRead();h.ctx.calendarNavigate('2026-09-15');const second=h.ctx.calendarRead();
 pending[1]({ok:true,json:async()=>({events:[event({title:'new week'})],timetables:[],source_error:''})});await second;
 pending[0]({ok:true,json:async()=>({events:[event({title:'old week'})],timetables:[],source_error:''})});await first;assert.equal(h.state().result.events[0].title,'new week');assert.equal(h.state().range,'2026-09-14/2026-09-20');
});
test('lost save response preserves body and id; after token refresh retry uses the same body',async()=>{
 const h=harness(),payload={id:'a'.repeat(32),version:0,child_ids:['child-a'],title:'虚构散步'};h.reply=async()=>{throw Error('lost reply')};await assert.rejects(h.ctx.calendarRequest(payload));const body=h.calls[0].body;assert.equal(h.pending(),body);
 h.reply=async()=>({ok:false,status:403,json:async()=>({error:'synthetic auth expired'})});await assert.rejects(h.ctx.calendarRequest({...payload,title:'must not replace pending'}));assert.equal(h.pending(),body);
 // Closing the dialog leaves the pending operation intact. Global load updates data.token.
 h.get('#calendarDialog').close();h.ctx.data.token='synthetic-refreshed-token';h.reply=async()=>({ok:true,status:200,json:async()=>({event:{id:payload.id,version:1}})});await h.ctx.calendarRequest(payload);
 assert.ok(h.calls.every(c=>c.body===body));assert.equal(h.calls.at(-1).headers['X-Family-Token'],'synthetic-refreshed-token');assert.equal(h.pending(),null);
});
test('a definite validation/conflict response permits correction and failed reads can be retried',async()=>{
 const h=harness();for(const status of [400,409]){h.reply=async()=>({ok:false,status,json:async()=>({error:'synthetic rejection'})});await assert.rejects(h.ctx.calendarRequest({id:'a'.repeat(32),version:0}));assert.equal(h.pending(),null)}
 h.reply=async()=>{throw Error('synthetic unavailable')};await h.ctx.calendarRead();assert.match(h.state().error,/unavailable/);h.ctx.calendarInvalidate();h.reply=async()=>({ok:true,json:async()=>({events:[],timetables:[],source_error:'synthetic source gap'})});await h.ctx.calendarRead();assert.equal(h.state().error,'');assert.match(h.ctx.calendarAgendaHTML(),/synthetic source gap/);
});
test('phone subscription keeps HTTPS deployment prefix without page filters or credentials',async()=>{
 const h=harness();h.ctx.location.href='https://synthetic-user:synthetic-password@family.example/family/?child=child-a#week';
 h.ctx.calendarSyncOpen();assert.equal(h.get('#calendarSyncURL').value,'https://family.example/family/calendar.ics');assert.equal(h.get('#calendarSyncAddress').hidden,false);
 await h.ctx.calendarSyncCopy();assert.equal(h.copied,'https://family.example/family/calendar.ics');assert.match(h.get('#calendarSyncStatus').textContent,/已复制/);assert.equal(h.calls.length,0,'opening/copying does not download or modify calendars');
 h.ctx.location.href='http://127.0.0.1:8765/';h.ctx.calendarSyncOpen();assert.equal(h.get('#calendarSyncURL').value,'');assert.equal(h.get('#calendarSyncAddress').hidden,true);assert.equal(h.get('#calendarSyncCopy').disabled,true);assert.match(h.get('#calendarSyncStatus').textContent,/已登录的 HTTPS/);
 h.copied=null;await h.ctx.calendarSyncCopy();assert.equal(h.copied,null,'loopback secure context is still not a mobile HTTPS source');
});
test('clipboard failure selects the address, but an old failure cannot take focus after reopening',async()=>{
 const h=harness();h.ctx.calendarSyncOpen();h.ctx.navigator.clipboard=undefined;await h.ctx.calendarSyncCopy();
 const field=h.get('#calendarSyncURL');assert.equal(h.focus,'#calendarSyncURL');assert.equal(field.selectionStart,0);assert.equal(field.selectionEnd,field.value.length);assert.match(h.get('#calendarSyncStatus').textContent,/手动复制/);assert.equal(h.get('#calendarSyncCopy').disabled,false);
 let reject;h.ctx.navigator.clipboard={writeText:()=>new Promise((_,r)=>reject=r)};const pending=h.ctx.calendarSyncCopy();assert.equal(h.get('#calendarSyncCopy').disabled,true);
 h.get('#calendarSyncDialog').close();h.ctx.calendarSyncOpen();h.focus='new-dialog-focus';const message=h.get('#calendarSyncStatus').textContent;reject(Error('synthetic denied'));await pending;
 assert.equal(h.focus,'new-dialog-focus');assert.equal(h.get('#calendarSyncStatus').textContent,message);assert.equal(h.get('#calendarSyncCopy').disabled,false);
});

test('inbox separates completion, dismissal and known-date overdue without changing records',()=>{
 const h=harness(),row=(id,extra={})=>({id,kind:'task',status:'待跟进',closed:false,child_ids:['child-a'],agenda:{category:'todo',box:'inbox',due_on:'',scheduled_on:''},...extra});
 const dated=(id,due,scheduled='')=>row(id,{agenda:{category:'todo',box:'inbox',due_on:due,scheduled_on:scheduled}});
 const rows=[row('open'),dated('late','2026-09-07'),dated('today','2026-09-08'),dated('future','2026-09-09'),dated('planned-late','','2026-09-07'),dated('deadline-priority','2026-09-10','2026-09-07'),dated('invalid','2026-02-30'),dated('unknown','稍后核对'),row('done',{closed:true,status:'已完成'}),row('declined',{closed:true,status:'不参加'}),row('ignored',{closed:true,status:'不适用'}),row('archived',{closed:true,status:'已归档'}),row('wish',{agenda:{box:'wish',due_on:'2026-09-01',scheduled_on:'2026-09-02'}}),row('study-parent',{kind:'study',closed:true,result:'完成',result_actor:'parent'}),row('study-child',{kind:'study',result:'完成',result_actor:'child'}),row('event-done',{kind:'event',closed:true,event:{status:'completed'}}),row('event-cancelled',{kind:'event',closed:true,event:{status:'cancelled'}}),{...dated('weekly','','2026-09-01'),kind:'event',event:{repeat:'weekly',status:'confirmed'}},row('sibling',{closed:true,status:'已完成',child_ids:['child-b']})];
 h.ctx.data.today_calendar={inbox:rows};const before=JSON.stringify(rows),boxes=clean(h.ctx.taskBoxes()),ids=name=>boxes[name].map(x=>x.id);
 assert.deepEqual(ids('已完成'),['done','study-parent','event-done','sibling']);assert.deepEqual(ids('已搁置'),['declined','ignored','archived','event-cancelled']);assert.deepEqual(ids('已逾期'),['late','planned-late']);assert.deepEqual(ids('计划'),['planned-late','deadline-priority','weekly']);assert.deepEqual(ids('Wish'),['wish']);assert.ok(ids('Inbox').includes('planned-late'));assert.ok(ids('Inbox').includes('study-child'));assert.equal(ids('全部').length,rows.length);assert.equal(JSON.stringify(rows),before,'filters do not alter completion or plans');
 h.ctx.child='小溪';assert.equal(h.ctx.taskBoxes()['已完成'].some(x=>x.id==='sibling'),false,'all filters respect child ownership');
});

// Optional real-browser check: node test_calendar_ui.js --browser
// Reuses test_calendar_draft_ui.cjs's disposable demo startup. HTTPS is a routed
// synthetic origin; this tests the UI, not TLS, Basic Auth or an actual iPhone.
if(process.argv.includes('--browser'))test('phone subscription dialog works at mobile and desktop widths',async()=>{
 const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright'),net=require('node:net');
 const {spawn}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises'),fs=require('node:fs/promises'),path=require('node:path');
 async function eventually(check,label){const end=Date.now()+12000;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let error='',browser;
 proc.stdout.resume();proc.stderr.on('data',x=>error+=String(x));proc.on('error',e=>error=e.message);
 const local='http://127.0.0.1:'+port+'/',remote='https://family-calendar.example/family/',results=[];
 const proof=async(p,name)=>{if(process.env.CALENDAR_SYNC_UI_PROOF_DIR){await fs.mkdir(process.env.CALENDAR_SYNC_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.CALENDAR_SYNC_UI_PROOF_DIR,name+'.png')})}};
 try{
  await eventually(async()=>{if(proc.exitCode!==null||error)throw Error(error||'Demo exited');try{return(await fetch(local,{signal:AbortSignal.timeout(500)})).ok}catch{return false}},'synthetic demo ready');
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:900}}),errors=[],unexpected=[];
   try{
    p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()!=='GET'||new URL(r.url()).pathname.endsWith('/calendar.ics'))unexpected.push(r.method()+' '+new URL(r.url()).pathname)});
    await p.route('https://family-calendar.example/**',async r=>{const u=new URL(r.request().url());assert.ok(u.pathname.startsWith('/family/'));await r.fulfill({response:await r.fetch({url:local+u.pathname.slice('/family/'.length)+u.search})})});
    await p.addInitScript(()=>{window.__copied=[];window.__copyDenied=false;Object.defineProperty(navigator,'clipboard',{configurable:true,value:{async writeText(text){if(window.__copyDenied)throw Error('synthetic clipboard rejection');window.__copied.push(text)}}})});
    const dialog=p.locator('#calendarSyncDialog'),address=p.locator('#calendarSyncURL'),copy=p.locator('#calendarSyncCopy'),entry=p.locator('[data-calendar-sync]');
    const fit=async()=>{assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page fits '+width);assert.equal(await dialog.evaluate(x=>x.scrollWidth>x.clientWidth),false,'dialog fits '+width);assert.equal(await dialog.locator('button:visible,summary:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'44px dialog controls '+width)};
    const open=async()=>{await entry.focus();await p.keyboard.press('Enter');await eventually(()=>dialog.isVisible(),'subscription dialog')};
    await p.goto(remote+'?child=example#week');await eventually(()=>p.locator('body[data-page="home"] #task-group-homework').isVisible(),'synthetic home');await p.locator('nav [data-page="calendar"]').click();await p.locator('.calendar-tools > summary').click();await eventually(()=>entry.isVisible(),'calendar settings');
    await open();assert.equal(await address.inputValue(),remote+'calendar.ics');assert.equal(await address.getAttribute('readonly'),'');assert.equal(await p.locator('#calendarSyncHelp').getAttribute('open'),null);assert.equal(await p.locator('#calendarSyncStatus').getAttribute('role'),'status');await fit();await proof(p,'https-'+width);
    await copy.click();assert.deepEqual(await p.evaluate(()=>window.__copied),[remote+'calendar.ics']);assert.match(await p.locator('#calendarSyncStatus').innerText(),/已复制/);
    await p.evaluate(()=>window.__copyDenied=true);await copy.click();await eventually(async()=>/手动复制/.test(await p.locator('#calendarSyncStatus').innerText()),'manual copy fallback');
    assert.equal(await address.evaluate(x=>document.activeElement===x&&x.selectionStart===0&&x.selectionEnd===x.value.length),true,'failed copy selects whole URL');await fit();await proof(p,'manual-copy-'+width);
    await p.locator('#calendarSyncHelp summary').click();assert.match(await dialog.innerText(),/夫妻各自订阅/);assert.match(await dialog.innerText(),/不是 Apple／iCloud 密码/);assert.match(await dialog.innerText(),/不保证即时/);await fit();await proof(p,'help-'+width);
    await p.keyboard.press('Escape');await eventually(async()=>!await dialog.isVisible(),'Escape closes dialog');assert.equal(await entry.evaluate(x=>document.activeElement===x),true,'Escape restores opener focus');
    await open();assert.equal(await p.locator('#calendarSyncHelp').getAttribute('open'),null);await p.locator('[data-close="calendarSyncDialog"]').click();await eventually(async()=>!await dialog.isVisible(),'shared close handler');assert.equal(await entry.evaluate(x=>document.activeElement===x),true,'close button restores opener focus');
    await p.goto(local);await eventually(()=>p.locator('body[data-page="home"] #task-group-homework').isVisible(),'HTTP home');await p.locator('nav [data-page="calendar"]').click();await p.locator('.calendar-tools > summary').click();await eventually(()=>entry.isVisible(),'HTTP calendar settings');await open();
    assert.equal(await p.locator('#calendarSyncAddress').isVisible(),false);assert.equal(await address.inputValue(),'');assert.equal(await copy.isDisabled(),true);assert.match(await p.locator('#calendarSyncStatus').innerText(),/已登录的 HTTPS/);await fit();await proof(p,'http-'+width);
    assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[],'subscription setup never fetches ICS or posts data');results.push({width,httpsSubpath:true,copyAndFallback:true,nativeCloseAndFocus:true,noOverflow:true,httpUnavailable:true,pageErrors:0});
   }finally{await p.close()}
  }
  console.log(JSON.stringify({calendarSyncUI:results,syntheticOnly:true,clipboardStubbed:true,httpsRoutedToLocalDemo:true,phoneAuthenticationTested:false}));
 }finally{
  await browser?.close();if(proc.exitCode===null&&proc.signalCode===null){const ended=once(proc,'exit');proc.kill('SIGINT');await Promise.race([ended,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await ended}}
 }
});

test('task inbox does not replace attachment inbox in the shared bundle',()=>{
 const core=readFileSync(__dirname+'/app.js','utf8'),calendar=readFileSync(__dirname+'/calendar.js','utf8');
 assert.match(core,/html=taskInboxHTML\(\)/);assert.match(core,/function inboxHTML\(\)/);
 assert.match(calendar,/function taskInboxHTML\(\)/);assert.doesNotMatch(calendar,/function inboxHTML\(\)/);
});

test('today lists undated homework, excludes wishes, and inbox boxes retain the same task',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.taskHTML=t=>`<article>${t.title}</article>`;h.ctx.taskClosed=t=>false;h.ctx.taskActionHTML=t=>t.action;h.ctx.taskView='Inbox';
 d.tasks=[{id:'todo',title:'虚构未定期作业',child:'小溪',focus:{box:'inbox'}},{id:'wish',title:'虚构心愿',action:'想留下的成果',child:'小溪',focus:{box:'wish'}}];
 d.today_calendar={inbox:d.tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',child_ids:['child-a'],closed:false,agenda:{category:'homework',box:t.focus.box,scheduled_on:''}})),agenda:[],events:[]};
 const today=h.ctx.todayTasksHTML();assert.match(today,/虚构未定期作业/);assert.doesNotMatch(today,/虚构心愿/);
 assert.equal(h.ctx.taskBoxes().Wish.length,1);assert.equal(h.ctx.taskBoxes().Inbox.length,1);
 h.ctx.taskView='Wish';const wish=h.ctx.taskInboxHTML();assert.match(wish,/转成计划/);assert.doesNotMatch(wish,/type="checkbox"/);
 h.ctx.child='小岚';assert.equal(h.ctx.taskBoxes().Wish.length,0);
});
test('task card puts completion goal before optional advice',()=>{
 const core=readFileSync(__dirname+'/app.js','utf8'),start=core.indexOf('function taskActionHTML'),end=core.indexOf('function taskHTML',start),ctx=vm.createContext({esc:escape,taskFocus:t=>t.focus,taskReviewDue:()=>false});
 vm.runInContext(core.slice(start,end),ctx);const html=ctx.taskActionHTML({action:'虚构成果目标',focus:{mode:'next',next_action:'虚构可选做法'}});
 assert.ok(html.indexOf('完成目标')<html.indexOf('操作建议'));assert.ok(html.indexOf('虚构成果目标')<html.indexOf('虚构可选做法'));
});

test('today and inbox group legacy undated tasks without reopening closed items or showing future plans',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.taskHTML=t=>`<article>${t.title}</article>`;h.ctx.taskView='Inbox';
 const row=(id,category,extra={})=>({id,task_id:id,kind:'task',child_ids:['child-a'],closed:false,agenda:{category,box:'inbox',scheduled_on:'',published_on:'',...extra}});
 const rows=[row('assignment','homework'),row('undated-admin','todo'),row('legacy-admin',''),{...row('closed','homework'),closed:true},row('future-plan','todo',{scheduled_on:'2026-09-15'}),row('future-notice','homework',{published_on:'2026-09-15'}),{...row('other-child','todo'),child_ids:['child-b']}];
 d.tasks=rows.map(x=>({id:x.id,title:x.id,child:x.child_ids[0]==='child-a'?'小溪':'小岚',focus:{box:'inbox'}}));d.today_calendar={inbox:rows,agenda:[],events:[],timetables:[]};h.ctx.child='小溪';
 const today=h.ctx.todayTasksHTML();assert.match(today,/今日作业 · 1/);assert.match(today,/待办事项 · 2/);assert.match(today,/undated-admin|legacy-admin/);assert.doesNotMatch(today,/<article>(?:closed|future-plan|future-notice|other-child)<\/article>|待分类/);
 const inbox=h.ctx.taskInboxHTML();assert.match(inbox,/课内作业 · 2/);assert.match(inbox,/待办事项 · 3/);assert.match(inbox,/<article>future-plan<\/article>/);assert.doesNotMatch(inbox,/<article>closed<\/article>|待分类/);
 rows[0].closed=true;assert.match(h.ctx.todayTasksHTML(),/今日作业 · 0/);
});

test('completion acknowledges both today and inbox without reloading all data',async()=>{
 const core=readFileSync(__dirname+'/app.js','utf8'),start=core.indexOf('async function postTask'),end=core.indexOf("document.addEventListener('change'",start),task={id:'synthetic-task',update:{status:'已完成',updated:'2026-09-12T18:00:00+08:00'}};
 const data={tasks:[{id:task.id}],today_calendar:{inbox:[{task_id:task.id,closed:false}],agenda:[{task_id:task.id,closed:false}]}};
 const invalidated=[];const ctx=vm.createContext({data,page:'calendar',stateLoadSequence:0,AbortSignal,apiFetch:async()=>({ok:true,json:async()=>({task})}),status:t=>t.update.status,taskClosed:t=>t.update.status==='已完成',window:{FamilyCalendar:{invalidate(keep){invalidated.push(keep)}}},load:async()=>{throw Error('Unneeded full reload')}});
 vm.runInContext(core.slice(start,end),ctx);await ctx.postTask({id:task.id,status:'已完成'});assert.ok(data.today_calendar.inbox[0].closed);assert.ok(data.today_calendar.agenda[0].closed);assert.deepEqual(invalidated,[true]);
});

test('timetable text preserves day and slot and refuses ambiguous rows',()=>{const h=harness(),week=h.ctx.timetableWeek('周一 第一节 语文\n星期三 下午第一节 英语');assert.deepEqual(clean(week),[{weekday:1,sessions:[{slot:'第一节',title:'语文'}]},{weekday:3,sessions:[{slot:'下午第一节',title:'英语'}]}]);assert.equal(h.ctx.timetableLines(week),'周一｜第一节｜语文\n周三｜下午第一节｜英语');assert.deepEqual(clean(h.ctx.timetableWeek(h.ctx.timetableLines(week))),clean(week));assert.throws(()=>h.ctx.timetableWeek('语文 数学 英语'),/每行/)});

test('daily UI keeps collection navigation in inbox and pending notifications distinct',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.taskHTML=t=>`<article>${t.title}</article>`;h.ctx.taskView='Inbox';
 d.today_calendar={inbox:[],agenda:[],events:[],timetables:[]};
 assert.doesNotMatch(h.ctx.todayTasksHTML(),/data-task-box=/);assert.doesNotMatch(h.ctx.calendarHTML(),/data-task-box=/);
 assert.match(h.ctx.taskInboxHTML(),/data-task-box="Wish"/);assert.match(h.ctx.todayTasksHTML(),/href="#task-group-todo"/);
 const pending=id=>({id,kind:'school',child_ids:['child-a'],title:'虚构待核对要求',agenda:{category:'homework'}}),confirmed={id:'synthetic-confirmed',task_id:'synthetic-confirmed',kind:'task',child_ids:['child-a'],agenda:{category:'homework'}};d.tasks=[{id:confirmed.id,title:'虚构已确认作业'}];
 const grouped=h.ctx.taskGroupsHTML([pending('synthetic-pending'),confirmed,pending('synthetic-pending-2'),pending('synthetic-pending-3')],'今日作业');assert.match(grouped,/今日作业 · 1/);assert.match(grouped,/href="#school-review-synthetic-pending">待核对 3/);assert.match(grouped,/id="school-review-synthetic-pending" data-query-target="school-review:synthetic-pending" tabindex="-1"/);assert.ok(grouped.indexOf('虚构已确认作业')<grouped.indexOf('id="school-review-synthetic-pending"'),'confirmed work remains visible before a long review queue');
 const core=readFileSync(__dirname+'/app.js','utf8'),start=core.indexOf('function agentItemHTML'),end=core.indexOf('function agentChildHTML',start);
 const ctx=vm.createContext({data:{children:[{id:'child-a',name:'虚构孩子'}],tasks:[]},esc:escape,agendaDateHTML:h.ctx.agendaDateHTML,schoolOriginalButtons:()=>''});vm.runInContext(core.slice(start,end),ctx);
 const title='待核对：阅读要求\n'+('很长的虚构原通知。'.repeat(40)),item={id:'synthetic-school',kind:'school',child_id:'child-a',state:'pending',title,body:'请核对这条通知是否适用',evidence:[{text:'<script>unsafe</script>',ref:'synthetic:notice'}]};
 const html=ctx.agentItemHTML(item,{compact:true,agenda:{published_on:'2026-09-08'}});
 assert.match(html,/待核对通知/);assert.match(html,/<h3>阅读要求<\/h3>/);assert.match(html,/发布：2026-09-08/);assert.match(html,/data-agent-accept="synthetic-school"/);assert.doesNotMatch(html,/type="checkbox"|<script>/);assert.match(html,/&lt;script/);assert.ok(html.includes(escape(title)),'full source title is preserved in the original notification');
});

test('week overview includes every day, preserves child/status boundaries and deduplicates linked study',()=>{
 const h=harness(),state=h.state();state.week='2026-09-07';state.day='2026-09-08';state.range='2026-09-07/2026-09-13';
 const task={id:'synthetic-work',task_id:'synthetic-work',kind:'task',day:'2026-09-08',title:'<b>虚构作业</b>',child_ids:['child-a'],status:'不参加',closed:true,agenda:{category:'homework'}};
 state.result={agenda:[task],study:[{id:'linked',task_id:task.id,child_ids:task.child_ids,day:task.day,title:'不应重复的计时项',kind:'study'},{id:'oral',task_id:'',child_ids:['child-a'],day:'2026-09-09',title:'虚构口头作业',kind:'study',result:'完成',result_actor:'child'}],events:[event({title:'虚构周末安排'})],timetables:[]};
 let html=h.ctx.calendarWeekHTML();assert.equal((html.match(/data-calendar-column=/g)||[]).length,7);assert.match(html,/虚构周末安排/);assert.match(html,/&lt;b&gt;虚构作业&lt;\/b&gt;/);assert.doesNotMatch(html,/<b>虚构作业|不应重复的计时项|data-check=/);assert.match(html,/不参加/);assert.match(html,/完成 · 孩子自述/);
 assert.equal(h.ctx.calendarStudyStatus({status:'running'}),'正在计时');assert.equal(h.ctx.calendarStudyStatus({status:'paused'}),'已暂停');
 state.childID='child-b';html=h.ctx.calendarWeekHTML();assert.doesNotMatch(html,/虚构作业|虚构口头作业/);assert.match(html,/虚构周末安排/);
 state.range='2026-09-08/2026-09-08';assert.doesNotMatch(h.ctx.calendarWeekHTML(),/暂无已收录安排/,'a one-day cache is not a complete empty week');
});

test('refresh after a save preserves the loaded week while explicitly fetching fresh data',async()=>{
 const h=harness();await h.ctx.calendarRead();const cached=h.state().result;h.ctx.calendarInvalidate(true);assert.equal(h.state().result,cached);assert.equal(h.state().dirty,true);const calls=h.calls.length;await h.ctx.calendarRead();assert.equal(h.calls.length,calls+1);assert.equal(h.state().dirty,false);h.ctx.calendarInvalidate();assert.equal(h.state().result,null);
});
