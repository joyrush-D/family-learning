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
 const ctx=vm.createContext({data:{today:'2026-09-08',token:'synthetic-first-token',children:[{id:'child-a',name:'小溪'},{id:'child-b',name:'小岚'}],tasks:[]},page:'calendar',child:'小溪',currentChild:()=>ctx.data.children.find(c=>c.name===ctx.child),selectChild:id=>{const selected=ctx.data.children.find(c=>c.id===id);if(!selected)return false;ctx.child=selected.name;return true},window:{addEventListener(){}},document:{addEventListener(k,f){const prior=handlers[k];handlers[k]=e=>{prior?.(e);f(e)}},querySelectorAll(){return[]}},$:get,esc:escape,sourceCoverageHTML:()=>'<div data-synthetic-source-state>虚构读取状态</div>',currentSources:()=>[],currentSourceStatus:()=> '最近读取成功',endpoint:p=>'/family/'+p.replace(/^\//,''),status:t=>t.update.status,taskDismissed:t=>['不参加','不适用'].includes(t.update.status),taskStatusLabel:v=>v==='不适用'?'无需处理':v,taskReviewDue:t=>!!t?.focus?.review_on&&t.focus.mode!=='next'&&t.focus.review_on<='2026-09-08',render:()=>h.renders++,toast:s=>h.notices.push(s),crypto:{randomUUID},AbortController,setTimeout,clearTimeout,apiFetch:async(p,o)=>{h.calls.push({path:p,...o});return h.reply(p,o)},load:async()=>{},FormData:class{constructor(){return Object.entries(Object.fromEntries(names.map(n=>[n,get('#calendarForm').elements[n].value])))} }});
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
 const h=harness(),s=h.state(),items=[event(),event({id:'b'.repeat(32),child_ids:['child-b']})];h.ctx.child='小溪';s.childID='child-a';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,1);h.ctx.child='小岚';s.childID='child-b';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,2);h.ctx.child='未知档案';s.childID='invalid-child';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,0,'invalid child cannot expand the view to all children');
 h.ctx.data.tasks=[{id:'X1',child:'小溪',update:{status:'不适用'}}];const html=h.ctx.calendarEventHTML(event({id:'source:x',task_id:'X1',editable:false,status:'confirmed'}));assert.match(html,/核对原事项/);assert.match(html,/小溪：无需处理/);assert.match(html,/calendar-confirmed/);assert.doesNotMatch(html,/小岚：无需处理|学校已取消/);assert.doesNotMatch(html,/data-calendar-edit/);h.ctx.data.tasks[0].update.status='不参加';assert.match(h.ctx.calendarEventHTML(event({task_id:'X1'})),/小溪：不参加/);h.ctx.data.tasks[0].child='未知归属';assert.doesNotMatch(h.ctx.calendarEventHTML(event({task_id:'X1'})),/家庭决定|：不参加/);
});
test('calendar has no all-children choice and new plans start with the current child',()=>{
 const h=harness();assert.doesNotMatch(h.ctx.calendarHTML(),/data-calendar-child=""/);assert.match(h.ctx.calendarHTML(),/data-calendar-child="child-a" aria-pressed="true"/);h.ctx.calendarOpen();assert.match(h.get('#calendarChildChoices').innerHTML,/value="child-a" checked/);assert.doesNotMatch(h.get('#calendarChildChoices').innerHTML,/value="child-b" checked/);h.ctx.selectChild('child-b');h.ctx.calendarOpen();assert.match(h.get('#calendarChildChoices').innerHTML,/value="child-b" checked/);assert.doesNotMatch(h.get('#calendarChildChoices').innerHTML,/value="child-a" checked/);assert.equal(h.calls.length,0,'opening an arrangement never saves it');
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
 assert.deepEqual(ids('已完成'),['done','study-parent','event-done']);assert.deepEqual(ids('已搁置'),['declined','ignored','archived','event-cancelled']);assert.deepEqual(ids('已逾期'),['late','planned-late']);assert.deepEqual(ids('计划'),['planned-late','deadline-priority','weekly']);assert.deepEqual(ids('Wish'),['wish']);assert.ok(ids('Inbox').includes('planned-late'));assert.ok(ids('Inbox').includes('study-child'));assert.equal(ids('全部').length,rows.length-1);assert.equal(JSON.stringify(rows),before,'filters do not alter completion or plans');
 assert.equal(h.ctx.taskBoxes()['已完成'].some(x=>x.id==='sibling'),false,'all filters respect the current child');h.ctx.child='小岚';assert.deepEqual(clean(h.ctx.taskBoxes()['已完成']).map(x=>x.id),['sibling']);h.ctx.child='未知档案';assert.equal(h.ctx.taskBoxes()['全部'].length,0,'invalid child cannot expose another child tasks');
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
 assert.ok(html.indexOf('要做什么')<html.indexOf('操作建议'));assert.ok(html.indexOf('虚构成果目标')<html.indexOf('虚构可选做法'));
});

test('today and inbox group legacy undated tasks without reopening closed items or showing future plans',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.taskHTML=t=>`<article>${t.title}</article>`;h.ctx.taskView='Inbox';
 const row=(id,category,extra={})=>({id,task_id:id,kind:'task',child_ids:['child-a'],closed:false,agenda:{category,box:'inbox',scheduled_on:'',published_on:'',...extra}});
 const rows=[row('assignment','homework'),row('undated-admin','todo'),row('legacy-admin',''),{...row('closed','homework'),closed:true},row('future-plan','todo',{scheduled_on:'2026-09-15'}),row('future-notice','homework',{published_on:'2026-09-15'}),{...row('other-child','todo'),child_ids:['child-b']}];
 d.tasks=rows.map(x=>({id:x.id,title:x.id,child:x.child_ids[0]==='child-a'?'小溪':'小岚',focus:{box:'inbox'}}));d.today_calendar={inbox:rows,agenda:[],events:[],timetables:[]};h.ctx.child='小溪';
 const today=h.ctx.todayTasksHTML();assert.match(today,/今日作业 · 0/);assert.match(today,/要办的事 · 2/);assert.match(today,/其他未完成作业 · 1/);assert.doesNotMatch(today,/today-backlog/);for(const id of ['undated-admin','legacy-admin']){assert.match(today,new RegExp('<article>'+id+'</article>'));assert.ok(today.indexOf('<article>'+id+'</article>')<today.indexOf('today-backlog'),'undated administration is visible before the backlog')};assert.doesNotMatch(today,/<article>(?:closed|future-plan|future-notice|other-child)<\/article>|待分类/);
 const inbox=h.ctx.taskInboxHTML();assert.match(inbox,/课内作业 · 2/);assert.match(inbox,/待办事项 · 3/);assert.match(inbox,/<article>future-plan<\/article>/);assert.doesNotMatch(inbox,/<article>closed<\/article>|待分类/);
 rows[0].closed=true;assert.match(h.ctx.todayTasksHTML(),/今日作业 · 0/);
});
test('today counts only current dated work and marks source gaps without changing the inbox',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.taskHTML=t=>`<article>${t.title}</article>`;
 const row=(id,when={})=>({id,task_id:id,kind:'task',child_ids:['child-a'],closed:false,agenda:{category:'homework',box:'inbox',published_on:'2026-09-02',due_on:'',scheduled_on:'',...when}});
 const rows=[row('today',{due_on:d.today}),row('old'),row('future',{due_on:'2026-09-22'})];
 d.tasks=rows.map(x=>({id:x.id,title:x.id,child:'小溪'}));d.today_calendar={inbox:rows,events:[],timetables:[]};
 h.ctx.currentSources=()=>[{child_id:'child-a',unread_count:2,enabled:true}];h.ctx.currentSourceStatus=()=> '最近读取成功';
 const html=h.ctx.todayTasksHTML();assert.match(html,/今日作业 · 1/);assert.match(html,/其他未完成作业 · 2/);assert.doesNotMatch(html,/today-backlog/);assert.match(html,/部分消息原件尚未读全。/);assert.doesNotMatch(html,/data-collection-check/);assert.equal(h.ctx.taskBoxes().Inbox.length,3);
 h.ctx.currentSourceStatus=()=> '最近读取未成功';assert.match(h.ctx.todayTasksHTML(),/消息读取有缺口，作业可能缺项。/);assert.match(h.ctx.todayTasksHTML(),/data-collection-check/);
 h.ctx.child='小岚';assert.doesNotMatch(h.ctx.todayTasksHTML(),/作业可能缺项|原件尚未读全/);
});
test('agent-classified homework appears with homework while notices stay separate',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';
 h.ctx.agendaItemHTML=x=>`<article data-notice="${x.id}">${x.title}</article>`;
 const school=(id,published,category='homework')=>({id,kind:'school',child_ids:['child-a'],title:id,closed:false,agenda:{category,box:'inbox',published_on:published,due_on:'',scheduled_on:''}});
 const rows=[school('older','2026-09-02'),school('yesterday-a','2026-09-07'),school('yesterday-b','2026-09-07'),school('today-notice',d.today,'todo'),school('unknown','')];
 d.today_calendar={inbox:rows,events:[],timetables:[]};h.ctx.child='小溪';
 const html=h.ctx.todayTasksHTML(),recent=html.split('id="task-group-todo"')[1]?.split('</section>')[0],homework=html.split('today-recent-homework">')[1]?.split('</section>')[0],backlog=html.split('today-backlog">')[1]?.split('</details>')[0];
 assert.match(html,/今日作业 · 0/);assert.match(homework,/待核对 4/);assert.match(recent,/待核对 1/);
 for(const id of ['older','yesterday-b','yesterday-a'])assert.match(homework,new RegExp('data-notice="'+id+'"'));
 assert.match(recent,/data-notice="today-notice"/);assert.doesNotMatch(recent,/yesterday-a|yesterday-b|older|unknown/);
 assert.match(homework,/data-notice="unknown"/);assert.doesNotMatch(backlog,/data-notice="older"|data-notice="unknown"/);
 assert.equal((html.match(/data-notice="yesterday-a"/g)||[]).length,1);
});

test('agent accepted details contain only the current child after switching',()=>{
 const h=harness(),core=readFileSync(__dirname+'/app.js','utf8');h.ctx.data.agent={items:[{id:'accepted-a',state:'accepted',child_id:'child-a'},{id:'accepted-b',state:'accepted',child_id:'child-b'}]};
 Object.assign(h.ctx,{schoolInboxHTML:()=>'',agentStatusHTML:()=>'',agentPending:()=>[],agentItemHTML:x=>`<article data-test-accepted="${x.id}"></article>`,empty:()=>''});vm.runInContext(core.slice(core.indexOf('function agentPageHTML()'),core.indexOf('async function agentAction(')),h.ctx);
 let html=h.ctx.agentPageHTML();assert.match(html,/最近加入的待办与依据/);assert.match(html,/data-test-accepted="accepted-a"/);assert.doesNotMatch(html,/data-test-accepted="accepted-b"/);
 h.ctx.selectChild('child-b');html=h.ctx.agentPageHTML();assert.match(html,/data-test-accepted="accepted-b"/);assert.doesNotMatch(html,/data-test-accepted="accepted-a"/);
});

test('each selected child unfinished school homework stays visible across days',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.agendaItemHTML=x=>`<article data-notice="${x.id}">${x.title}</article>`;
 const row=(id,day,kind='school',owner='child-a',due='')=>({id,task_id:kind==='task'?id:'',kind,child_ids:[owner],title:id,closed:false,agenda:{category:'homework',box:'inbox',published_on:day,due_on:due,scheduled_on:''}});
 const rows=[row('due-today','2026-09-02','task','child-a',d.today),row('collected-undated','2026-09-07','task'),...Array.from({length:5},(_,n)=>row('same-day-'+n,'2026-09-07')),row('older','2026-09-02'),row('sibling','2026-09-06','task','child-b')];
 d.tasks=rows.filter(x=>x.kind==='task').map(x=>({id:x.id,title:x.title,source:'Agent建议:synthetic-school',child:x.child_ids[0]==='child-a'?'小溪':'小岚'}));d.today_calendar={inbox:rows,events:[],timetables:[]};
 const html=h.ctx.todayTasksHTML(),recent=html.split('today-recent-homework">')[1]?.split('</section>')[0]||'',backlog=html.split('today-backlog">')[1]?.split('</details>')[0]||'';
 assert.match(html,/今日作业 · 1/);
 for(const id of ['older','collected-undated','same-day-0','same-day-1','same-day-2','same-day-3','same-day-4']){assert.match(recent,new RegExp('data-notice="'+id+'"'));assert.equal((html.match(new RegExp('data-notice="'+id+'"','g'))||[]).length,1)}
 assert.doesNotMatch(backlog,/data-notice="older"/);assert.doesNotMatch(recent,/data-notice="due-today"/);
 assert.doesNotMatch(html,/data-notice="sibling"/);h.ctx.child='小岚';const sibling=h.ctx.todayTasksHTML();assert.equal((sibling.match(/data-notice="sibling"/g)||[]).length,1);assert.doesNotMatch(sibling,/data-notice="collected-undated"|data-notice="same-day-\d"|data-notice="due-today"|data-notice="older"/);
});

test('recent homework keeps each child confirmed work before their missing details without duplication',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.agendaItemHTML=x=>`<article data-notice="${x.id}">${x.title}</article>`;
 const row=(id,kind,owner,hour)=>({id,task_id:kind==='task'?id:'',kind,child_ids:[owner],title:id,closed:false,agenda:{category:'homework',box:'inbox',published_on:'2026-09-07',published_at:`2026-09-07T${hour}:00:00+08:00`,due_on:'',scheduled_on:''}});
 const confirmed=['confirmed-a','confirmed-b'],pending=['pending-a-18','pending-a-17'];
 const rows=[row(confirmed[0],'task','child-a','20'),row(confirmed[1],'task','child-b','19'),row(pending[0],'school','child-a','18'),row(pending[1],'school','child-a','17')];
 d.tasks=rows.filter(x=>x.kind==='task').map(x=>({id:x.id,title:x.title,source:'Agent建议:synthetic-school',child:x.child_ids[0]==='child-a'?'小溪':'小岚'}));d.today_calendar={inbox:rows,events:[],timetables:[]};
 const html=h.ctx.todayTasksHTML();assert.match(html,/today-recent-homework/);assert.match(html,/今日作业 · 0/);
 for(const id of [confirmed[0],...pending])assert.equal((html.match(new RegExp('data-notice="'+id+'"','g'))||[]).length,1,'each recent homework for this child appears once: '+id);assert.doesNotMatch(html,/data-notice="confirmed-b"/);
 for(const missing of pending)assert.ok(html.indexOf('data-notice="'+confirmed[0]+'"')<html.indexOf('data-notice="'+missing+'"'),'confirmed work stays ahead of the selected child missing details');
 h.ctx.child='小岚';const filtered=h.ctx.todayTasksHTML();assert.equal((filtered.match(/data-notice="confirmed-b"/g)||[]).length,1,'filtering the second child retains their recent homework');assert.doesNotMatch(filtered,/data-notice="confirmed-a"|data-notice="pending-a-18"|data-notice="pending-a-17"/);
});

test('a due review stays visible today even when the task is planned for a later day',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.taskHTML=t=>`<article>${t.title}</article>`;
 d.tasks=[{id:'review',title:'虚构今日回看',focus:{mode:'later',review_on:d.today}},{id:'future',title:'虚构未来回看',focus:{mode:'later',review_on:'2026-09-12'}}];
 d.today_calendar={inbox:d.tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',child_ids:['child-a'],closed:false,agenda:{category:'todo',box:'inbox',published_on:'2026-09-01',due_on:'',scheduled_on:'2026-09-15'}})),events:[],timetables:[]};
 const html=h.ctx.todayTasksHTML();assert.match(html,/今天回看 · 1/);assert.match(html,/<article>虚构今日回看<\/article>/);assert.doesNotMatch(html,/虚构未来回看/);assert.equal((html.match(/<article>虚构今日回看<\/article>/g)||[]).length,1);
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
 const ctx=vm.createContext({data:{children:[{id:'child-a',name:'虚构孩子'}],tasks:[]},esc:escape,agendaDateHTML:h.ctx.agendaDateHTML,schoolOriginalButtons:()=>''});vm.runInContext(core.slice(core.indexOf('function requirementHTML('),core.indexOf('function taskFocus(')),ctx);vm.runInContext(core.slice(start,end),ctx);
 const title='待核对：阅读要求\n'+('很长的虚构原通知。'.repeat(40)),item={id:'synthetic-school',kind:'school',child_id:'child-a',state:'pending',title,body:'请核对这条通知是否适用',evidence:[{text:'<script>unsafe</script>',ref:'synthetic:notice'}]};
 const html=ctx.agentItemHTML(item,{compact:true,agenda:{category:'todo',published_on:'2026-09-08'}});
 assert.match(html,/通知 · 有信息待补充/);assert.match(html,/<h3>阅读要求<\/h3>/);assert.match(html,/发布：2026-09-08/);assert.match(html,/data-agent-accept="synthetic-school"/);assert.doesNotMatch(html,/type="checkbox"|<script>/);assert.match(html,/&lt;script/);assert.ok(html.includes(escape(title)),'full source title is preserved in the original notification');
 const goal='1. 阅读虚构课文\n2. 写出三句话\n3. '+('很长的虚构具体要求'.repeat(30))+'\n4. 带回原卷核对',ready={...item,plan:{school_task:{state:'ready',title:'语文：阅读与写作',goal,reason:'虚构老师要求'}}};
 const readyHTML=ctx.agentItemHTML(ready,{compact:true,agenda:{category:'homework'}});assert.match(readyHTML,/作业 · 已整理/);assert.match(readyHTML,/加入事项/);assert.doesNotMatch(readyHTML,/展开完整要求/);assert.equal((readyHTML.match(/<li>/g)||[]).length,4,'all saved requirements are directly visible');for(const line of goal.split('\n'))assert.ok(readyHTML.includes('<li>'+escape(line)+'</li>'),'long and fourth requirements remain complete without expansion');
});

test('week overview includes every day, preserves child/status boundaries and deduplicates linked study',()=>{
 const h=harness(),state=h.state();state.week='2026-09-07';state.day='2026-09-08';state.range='2026-09-07/2026-09-13';
 const task={id:'synthetic-work',task_id:'synthetic-work',kind:'task',day:'2026-09-08',title:'<b>虚构作业</b>',child_ids:['child-a'],status:'不参加',closed:true,agenda:{category:'homework'}};
 state.result={agenda:[task],study:[{id:'linked',task_id:task.id,child_ids:task.child_ids,day:task.day,title:'不应重复的计时项',kind:'study'},{id:'oral',task_id:'',child_ids:['child-a'],day:'2026-09-09',title:'虚构口头作业',kind:'study',result:'完成',result_actor:'child'}],events:[event({title:'虚构周末安排'})],timetables:[]};
 let html=h.ctx.calendarWeekHTML();assert.equal((html.match(/data-calendar-column=/g)||[]).length,7);assert.match(html,/虚构周末安排/);assert.match(html,/&lt;b&gt;虚构作业&lt;\/b&gt;/);assert.doesNotMatch(html,/<b>虚构作业|不应重复的计时项|data-check=/);assert.match(html,/不参加/);assert.match(html,/完成 · 孩子自述/);
 assert.equal(h.ctx.calendarStudyStatus({status:'running'}),'正在计时');assert.equal(h.ctx.calendarStudyStatus({status:'paused'}),'已暂停');
 h.ctx.child='小岚';state.childID='child-b';html=h.ctx.calendarWeekHTML();assert.doesNotMatch(html,/虚构作业|虚构口头作业/);assert.match(html,/虚构周末安排/);
 state.range='2026-09-08/2026-09-08';assert.doesNotMatch(h.ctx.calendarWeekHTML(),/暂无已收录安排/,'a one-day cache is not a complete empty week');
});

test('refresh after a save preserves the loaded week while explicitly fetching fresh data',async()=>{
 const h=harness();await h.ctx.calendarRead();const cached=h.state().result;h.ctx.calendarInvalidate(true);assert.equal(h.state().result,cached);assert.equal(h.state().dirty,true);const calls=h.calls.length;await h.ctx.calendarRead();assert.equal(h.calls.length,calls+1);assert.equal(h.state().dirty,false);h.ctx.calendarInvalidate();assert.equal(h.state().result,null);
});


test('source health and goal citations keep the same child while a save is unresolved',()=>{
 const h=harness();h.ctx.data.agent={sources:[{child_id:'child-a',name:'虚构甲群',platform:'qq',enabled:true,error:'synthetic'},{child_id:'child-b',name:'虚构乙群',platform:'qq',enabled:true,error:'synthetic'}]};
 const core=readFileSync(__dirname+'/app.js','utf8');h.ctx.currentSources=()=>h.ctx.data.agent.sources;vm.runInContext(core.slice(core.indexOf('function currentSourceStatus('),core.indexOf('function currentSourceCardsHTML(')),h.ctx);
 assert.match(h.ctx.sourceCoverageHTML(),/虚构甲群/);assert.doesNotMatch(h.ctx.sourceCoverageHTML(),/虚构乙群/);h.ctx.selectChild('child-b');assert.match(h.ctx.sourceCoverageHTML(),/虚构乙群/);assert.doesNotMatch(h.ctx.sourceCoverageHTML(),/虚构甲群/);
 const app=readFileSync(__dirname+'/app.js','utf8'),handlers=[],ctx=vm.createContext({document:{addEventListener:(_,f)=>handlers.push(f)},data:{children:[{id:'child-a'},{id:'child-b'}]},page:'study',render(){throw Error('A rejected child switch must not repaint a different goal')},window:{scrollTo(){}},selectChild:()=>false});
 vm.runInContext(app.slice(app.indexOf("let goalChildID=''"),app.indexOf("document.addEventListener('click',e=>{const b=e.target.closest('[data-goal-teacher]')")),ctx);
 for(const handler of handlers)handler({target:{closest:selector=>({dataset:selector==='[data-goal-id]'?{goalId:'synthetic-goal-b',goalChild:'child-b'}:{diagnosisChild:'child-b'}})}});
 assert.equal(vm.runInContext('page',ctx),'study');assert.equal(vm.runInContext('goalSelectedID',ctx),'');assert.equal(vm.runInContext('goalFocus',ctx),'');
});

test('unfinished school homework remains exposed across publication days without changing dates',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.agendaItemHTML=x=>'<article data-notice="'+x.id+'">'+x.title+'</article>';
 const row=(id,day,extra={})=>({id,kind:'school',child_ids:['child-a'],title:id,closed:false,agenda:{category:'homework',box:'inbox',published_on:day,due_on:'',scheduled_on:''},...extra});
 const rows=[row('older-undated','2026-09-02'),row('newer-undated','2026-09-07'),row('older-overdue','2026-09-03',{agenda:{category:'homework',box:'inbox',published_on:'2026-09-03',due_on:'2026-09-04',scheduled_on:''}}),row('closed','2026-09-02',{closed:true}),row('sibling','2026-09-03',{child_ids:['child-b']})];
 d.today_calendar={inbox:rows,events:[],timetables:[]};h.ctx.child='小溪';
 const html=h.ctx.todayTasksHTML(),received=html.split('today-recent-homework">')[1]?.split('</section>')[0]||'';
 for(const id of ['older-undated','newer-undated','older-overdue']){assert.match(received,new RegExp('data-notice="'+id+'"'));assert.equal((html.match(new RegExp('data-notice="'+id+'"','g'))||[]).length,1)}
 assert.doesNotMatch(html,/data-notice="closed"|data-notice="sibling"/);assert.match(html,/今日作业 · 0/);
 assert.equal(rows[0].agenda.published_on,'2026-09-02');assert.equal(rows[0].agenda.due_on,'');assert.equal(rows[2].agenda.due_on,'2026-09-04');
});

test('unfinished school homework due for review appears once in the direct review list',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.taskHTML=t=>'<article>'+t.title+'</article>';
 d.tasks=[{id:'review-homework',title:'虚构作业订正回看',source:'Agent建议:synthetic-school',focus:{mode:'later',review_on:d.today},child:'小溪'}];
 d.today_calendar={inbox:[{id:'review-homework',task_id:'review-homework',kind:'task',child_ids:['child-a'],closed:false,agenda:{category:'homework',box:'inbox',published_on:'2026-09-02',due_on:'',scheduled_on:''}}],events:[],timetables:[]};
 const html=h.ctx.todayTasksHTML();assert.match(html,/今天回看 · 1/);assert.match(html,/<article>虚构作业订正回看<\/article>/);
 assert.doesNotMatch(html.split('today-recent-homework">')[1]?.split('</section>')[0]||'',/虚构作业订正回看/);
 assert.equal((html.match(/<article>虚构作业订正回看<\/article>/g)||[]).length,1,'one original homework must not appear twice');
 assert.match(html,/今日作业 · 0/);assert.equal(d.tasks[0].focus.review_on,d.today);
});

// Shared task-list contract: known completion steps stay visible; group names stay in the original-message view.
function taskListTextHarness(){
 const app=readFileSync(__dirname+'/app.js','utf8'),ctx=vm.createContext({esc:escape,schoolMessageIdentity:(ref,child)=>/^message:synthetic:/.test(ref)&&child==='child-a'});
 vm.runInContext(app.slice(app.indexOf('function requirementHTML('),app.indexOf('function taskFocus(')),ctx);
 vm.runInContext(app.slice(app.indexOf('function schoolOriginalButtons('),app.indexOf('// Show the saved preparation beside its task.')),ctx);
 return ctx;
}
test('complete requirements keep signing and checking visible without truncation',()=>{
 const h=taskListTextHarness(),long='请读完整要求。'.repeat(24)+'最后请家长签字。',text='完成第1–3题。\n第4题选做。\n对照老师答案检查。\n'+long,html=h.requirementHTML(text);
 for(const line of text.split('\n'))assert.ok(html.includes('<li>'+escape(line)+'</li>'),'each saved requirement is directly visible');
 assert.doesNotMatch(html,/<details|展开完整要求|…/);
 assert.ok(h.requirementHTML('<script>虚构文本</script>').includes('&lt;script&gt;虚构文本&lt;/script&gt;'));
});
test('publisher context omits class and group names but preserves original reference',()=>{
 const h=taskListTextHarness(),publication={ref:'message:synthetic:one',sender:'示例周老师 <昵称>',source_name:'虚构学校群 <甲班>'},html=h.schoolOriginalButtons([publication.ref],'child-a','查看作业原件',[publication]);
 assert.ok(html.includes('示例周老师 &lt;昵称&gt;'));assert.doesNotMatch(html,/发言人：|虚构学校群|甲班/);
 assert.ok(html.includes('data-school-original-ref="message:synthetic:one"'));
 assert.equal(publication.source_name,'虚构学校群 <甲班>','saved source metadata is unchanged');
 assert.ok(h.schoolOriginalButtons([publication.ref],'child-a','查看作业原件',[{...publication,sender:'   '}]).includes('发布者未记录'));
 assert.equal(h.schoolOriginalButtons([publication.ref],'child-b','查看作业原件',[publication]),'','other child source is not exposed');
});
test('multiple originals show publisher once while keeping each message entry',()=>{
 const h=taskListTextHarness(),refs=['one','two','three','four'].map(x=>'message:synthetic:'+x),publications=refs.map(ref=>({ref,sender:'示例英语发布者',source_name:'虚构班级'})),html=h.schoolOriginalButtons(refs,'child-a','查看作业原件',publications);
 assert.equal((html.match(/class="school-publication-context"/g)||[]).length,1,'one visible publication context for the saved nicknames');
 assert.ok(html.includes('school-original-group'));
 for(let i=0;i<refs.length;i++){assert.ok(html.includes('data-school-original-ref="'+refs[i]+'"'));assert.ok(html.includes('>原件 '+(i+1)+'</button>'));assert.ok(html.includes('第 '+(i+1)+' 条查看作业原件'));}
 assert.equal(h.schoolOriginalButtons(refs,'child-b','查看作业原件',publications),'','other child remains excluded');
 assert.equal(publications.length,4,'display grouping does not change saved source relations');
 assert.doesNotMatch(html,/虚构班级|发言人：/);
});


test('all-date-unknown collected homework is exposed once for the selected child',()=>{
 const h=harness(),d=h.ctx.data;h.ctx.filters=()=>'';h.ctx.agendaItemHTML=x=>`<article data-notice="${x.id}">${x.title}</article>`;
 const row=(id,owner='child-a',when={})=>({id,task_id:id,kind:'task',child_ids:[owner],title:id,closed:false,agenda:{category:'homework',box:'inbox',published_on:'',due_on:'',scheduled_on:'',...when}});
 const rows=[...Array.from({length:8},(_,n)=>row('unknown-'+n)),row('other-child','child-b'),row('future-family','child-a',{scheduled_on:'2026-09-15'})];
 d.tasks=rows.map(x=>({id:x.id,title:x.title,source:'Agent建议:synthetic-school',child:x.child_ids[0]==='child-a'?'小溪':'小岚'}));d.today_calendar={inbox:rows,events:[],timetables:[]};
 const before=JSON.stringify(d),html=h.ctx.todayTasksHTML(),recent=html.split('today-recent-homework">')[1]?.split('</section>')[0]||'';
 assert.match(html,/今日作业 · 0/);assert.match(recent,/其他未完成作业 · 8/);
 for(let n=0;n<8;n++)assert.equal((recent.match(new RegExp('data-notice="unknown-'+n+'"','g'))||[]).length,1);
 assert.doesNotMatch(html,/today-backlog|data-notice="other-child"|data-notice="future-family"/);assert.equal(JSON.stringify(d),before,'display never invents dates or changes work');
});

test('list materials request the exact task and reject unscoped or wrong-task originals',async()=>{
 const h=harness(),c=h.ctx,core=readFileSync(__dirname+'/app.js','utf8'),ref='message:synthetic-class:notice';
 const task={id:'synthetic-task',child:'小溪',school_origin:true,source:'Agent建议:synthetic-item\n'+ref};c.data.tasks=[task];
 Object.assign(c,{schoolOriginal:null,schoolOriginalPending:()=>false,paintSchoolOriginal:()=>{},AbortSignal,URLSearchParams});
 vm.runInContext(core.slice(core.indexOf('function verifySchoolOriginal('),core.indexOf('// One click reads one address')),c);
 const value=(extra={})=>({child_id:'child-a',source_id:'synthetic-class',message_id:'notice',message:{id:'notice'},attachments:[{id:'synthetic-own-file'}],task_id:task.id,action_material:{scoped:true},...extra});
 const state=()=>c.schoolOriginal={identity:{child_id:'child-a',source_id:'synthetic-class',message_id:'notice'},taskMaterialID:task.id,taskMaterialSource:task.source,view:null,busy:false,fullSource:false};
 let s=state(),calls=[];c.apiFetch=async path=>{calls.push(path);return{ok:true,json:async()=>value()}};await c.readSchoolOriginal();
 assert.equal(new URL(calls[0],'https://synthetic.invalid').searchParams.get('task_id'),task.id);assert.equal(s.view.task_id,task.id);
 for(const response of [value({task_id:'other-task'}),value({action_material:undefined})]){s=state();c.apiFetch=async()=>({ok:true,json:async()=>response});await c.readSchoolOriginal();assert.equal(s.view,null);assert.match(s.error,/本项资料范围尚未核明/)}
 s=state();c.apiFetch=async()=>({ok:false,json:async()=>({error:'虚构读取失败'})});await c.readSchoolOriginal();assert.equal(s.view,null);assert.match(s.error,/虚构读取失败/);c.apiFetch=async()=>({ok:true,json:async()=>value()});await c.readSchoolOriginal();assert.equal(s.error,'');assert.equal(s.view.task_id,task.id);
 s=state();s.fullSource=true;c.apiFetch=async path=>{assert.equal(new URL(path,'https://synthetic.invalid').searchParams.has('task_id'),false);return{ok:true,json:async()=>value({task_id:undefined,action_material:undefined,attachments:[{id:'own'},{id:'other'}]})}};await c.readSchoolOriginal();assert.equal(s.view.attachments.length,2,'full source is an explicit separate view');
 let release;s=state();c.apiFetch=()=>new Promise(resolve=>release=resolve);const read=c.readSchoolOriginal();c.child='小岚';release({ok:true,json:async()=>value()});await read;assert.equal(s.view,null,'late reply cannot cross into the next child');
 c.child='小溪';s=state();c.apiFetch=()=>new Promise(resolve=>release=resolve);const changed=c.readSchoolOriginal();task.source='Agent建议:changed';release({ok:true,json:async()=>value()});await changed;assert.equal(s.view,null,'changed task source rejects the prior material');
});
