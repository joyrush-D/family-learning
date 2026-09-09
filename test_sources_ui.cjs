// Run as test_startup_ui.cjs with PLAYWRIGHT_MODULE / PLAYWRIGHT_CHANNEL.
// Only demo.py's disposable family and intercepted synthetic sources; no POSTs. Optional SOURCES_UI_PROOF_DIR.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=8000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function demoServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let failure;proc.on('error',e=>failure=e);proc.stdout.resume();proc.stderr.resume();
 const stop=async()=>{if(failure||proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 const url='http://127.0.0.1:'+port+'/';try{await eventually(async()=>{if(failure)throw failure;if(proc.exitCode!==null)throw Error('Synthetic demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'demo');return{url,stop}}catch(e){await stop();throw e}
}
async function checkWidth(p,label){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label+' page overflow');assert.equal(await p.locator('[data-source-card]').evaluateAll(cards=>cards.some(el=>el.scrollWidth>el.clientWidth)),false,label+' card overflow')}
async function sources(p){await p.locator('nav [data-page="more"]').click();await p.locator('#content [data-page="sources"]').click();await eventually(async()=>await p.locator('#content h1').innerText()==='来源与附件','sources page')}

(async()=>{
 let server,browser;const checks=[],proofDir=process.env.SOURCES_UI_PROOF_DIR||path.join(__dirname,'private/check-20260908/source-followup/ui');
 try{
  server=await demoServer();const base=await(await fetch(server.url+'api/state')).json(),first=base.children[0].name,second=base.children[1].name;
  const stringGap='<img src="/source-test-xss" onerror="window.__sourceXss=1"> 虚构图片尚未核对';
  const objectGap='<script>window.__sourceXss=2</script> 虚构长链接 '+('synthetic-path-without-spaces/').repeat(16);
  const sync={
   'qq:synthetic-history':{name:'虚构QQ群 <b>原名</b>',child:first,collection_status:'awaiting_login',method:'GUI',last_checked:'2026-08-01 08:00:00',last_attempt:'2026-09-01 18:00:00',last_error:'虚构登录未完成 <svg onload="window.__sourceXss=3">',incremental_new_records:7,incremental_count_note:'虚构历史 GUI 登记，不是今天读取。',full_content_complete:false,pending_content:[stringGap,{kind:'image',local_id:101,gap:objectGap},null,17,[],{}]},
   'wechat:current-school':{name:'虚构旧历史同ID',child:first,incremental_new_records:2,full_content_complete:false,pending_content:[]},
   'wechat:synthetic-zero':{name:'虚构零新增群',child:second,incremental_new_records:0,full_content_complete:false,pending_content:[]},
   'wechat:synthetic-missing':{name:'虚构未知覆盖群',child:first,pending_content:{unexpected:'synthetic'}},
   'wechat:synthetic-scanned':{name:'虚构扫描群',child:second,fetched_local_records:3,full_content_complete:true,pending_content:[]},
   'wechat:synthetic-bad-count':{name:'虚构未知数量群',incremental_new_records:-1,fetched_local_records:'5',pending_content:[]},
   'wechat:synthetic-bad-entry':null,
   'wechat:synthetic-failed':{name:'虚构失败群',child:first,last_error:'虚构请求失败',incremental_new_records:7},
  };
  const task=(id,child,title,status='待跟进')=>({id,child,title,due:'虚构日期',action:'虚构要求',source:'虚构来源',original_status:status,update:{status},history:[]});
  const recent=new Date(Date.now()-5*60*1000).toISOString(),stale=new Date(Date.now()-60*60*1000).toISOString();
  const sourceStates=[
   {id:'wechat:current-school',platform:'wechat',name:'虚构当前学校群',child_id:base.children[0].id,child:'虚构旧归属名',enabled:true,last_attempt:recent,last_success:recent,last_message_time:recent,error:'',unread_count:3},
   {id:'wechat:current-reading',platform:'wechat',name:'虚构新增阅读群',child_id:base.children[0].id,child:'虚构旧阅读归属',enabled:true,last_attempt:stale,last_success:stale,last_message_time:stale,error:'',unread_count:0},
   {id:'wechat:current-failed',platform:'wechat',name:'虚构当前失败群 <svg onload="window.__sourceXss=5">',child_id:base.children[1].id,child:'虚构旧失败归属',enabled:true,last_attempt:recent,last_success:'not-a-date',last_message_time:recent,error:'虚构读取失败 <img src=x onerror="window.__sourceXss=6">',unread_count:-1},
   {id:'qq:current-disabled',platform:'qq',name:'虚构停用QQ',child_id:base.children[1].id,child:'虚构旧停用归属',enabled:false,last_attempt:recent,last_success:recent,last_message_time:recent,error:'',unread_count:'5'},
  ];
  let current={...base,sync,sync_error:'',tasks:[task('source-first',first,'虚构甲待办'),task('source-second',second,'虚构乙待办'),task('source-done',first,'虚构已完成事项','已完成')],agent:{...base.agent,enabled:true,state:'ready',sources:sourceStates}};
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});const p=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],mutations=[],external=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(req.method()!=='GET'){mutations.push(req.method()+' '+url.pathname);return route.abort()}if(url.origin!==new URL(server.url).origin){external.push(url.origin);return route.abort()}if(url.pathname==='/api/state')return route.fulfill({json:current});if(url.pathname==='/api/agent')return route.fulfill({json:current.agent});return route.continue()});
  // Capture the actual object handed to the app, so DOM interactions cannot
  // silently rewrite source history even if the network fixture stays intact.
  await p.addInitScript(()=>{const original=Response.prototype.json;Response.prototype.json=async function(){const value=await original.call(this);if(new URL(this.url).pathname==='/api/state')window.__sourceInput={value,before:JSON.stringify({sync:value.sync,sync_error:value.sync_error,tasks:value.tasks,children:value.children,agent:value.agent})};return value}});
  await p.goto(server.url,{waitUntil:'domcontentloaded'});await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','home ready');
  assert.match(await p.locator('[data-source-coverage]').innerText(),/QQ.*虚构停用QQ.*已暂停，不同步新消息/);
  assert.match(await p.locator('[data-source-coverage]').innerText(),/读取未成功，新消息可能未收录/);
  assert.equal(await p.locator('[data-source-coverage] img,[data-source-coverage] svg,[data-source-coverage] script').count(),0);
  await sources(p);
  const currentCard=id=>p.locator('[data-current-source="'+id+'"]'),card=key=>p.locator('[data-source-card="'+key+'"]'),qq=card('qq:synthetic-history');
  assert.equal(await p.locator('[data-current-source]').count(),4);
  assert.equal(await currentCard('wechat:current-school').locator('[data-current-source-status]').innerText(),'最近读取成功');
  assert.equal(await currentCard('wechat:current-reading').locator('[data-current-source-status]').innerText(),'读取待核对');
  assert.equal(await currentCard('wechat:current-failed').locator('[data-current-source-status]').innerText(),'最近读取未成功');
  assert.equal(await currentCard('qq:current-disabled').locator('[data-current-source-status]').innerText(),'已停用');
  assert.match(await currentCard('wechat:current-school').innerText(),/3 条已保存消息含未读图片、附件或截断内容/);
  for(const id of ['wechat:current-reading','wechat:current-failed','qq:current-disabled'])assert.equal(await currentCard(id).locator('[data-current-source-unread]').count(),0);
  assert.match(await currentCard('wechat:current-failed').innerText(),/虚构读取失败 <img/);assert.equal(await currentCard('wechat:current-failed').locator('img,script,svg').count(),0);assert.equal(await p.evaluate(()=>window.__sourceXss),undefined);
  assert.match(await currentCard('wechat:current-school').innerText(),/示例星星/);assert.doesNotMatch(await currentCard('wechat:current-school').innerText(),/虚构旧归属名/);
  checks.push('current four-source cards show bounded status, timestamps, unread evidence and child ownership by ID; current errors are escaped');
  const history=p.locator('details[data-source-history]');assert.equal(await history.count(),1);assert.equal(await history.getAttribute('open'),null);await history.locator(':scope > summary').click();assert.notEqual(await history.getAttribute('open'),null);assert.match(await card('wechat:current-school').innerText(),/虚构旧历史同ID/);assert.match(await currentCard('wechat:current-school').innerText(),/虚构当前学校群/);
  checks.push('historical source records stay in their explicit details section and cannot replace current records with the same ID');
  assert.equal(await qq.locator('[data-source-status]').innerText(),'接入待验证');assert.match(await qq.locator('[data-source-count]').innerText(),/历史增量登记：7 条/);assert.match(await qq.innerText(),/尚待验证/);assert.match(await qq.innerText(),/虚构登录未完成 <svg/);assert.equal(/本轮新增|读取方式：.*GUI|当前.*GUI|已离线/.test(await qq.innerText()),false);
  assert.equal(await card('wechat:synthetic-failed').locator('[data-source-status]').innerText(),'最近读取未成功');assert.match(await card('wechat:synthetic-failed').innerText(),/虚构请求失败/);
  checks.push('awaiting-login QQ retains historical 7 and failure without claiming a current GUI read; failed source is explicit');
  const gaps=qq.locator('[data-source-gaps]');assert.equal(await gaps.getAttribute('open'),null);await gaps.locator('summary').click();assert.notEqual(await gaps.getAttribute('open'),null);const items=gaps.locator('li');assert.equal(await items.count(),6);assert.equal(await items.nth(0).innerText(),stringGap);assert.match(await items.nth(1).innerText(),/图片 · 消息 101/);assert.ok((await items.nth(1).innerText()).includes(objectGap));for(const n of [2,3,4])assert.match(await items.nth(n).innerText(),/说明格式异常/);assert.match(await items.nth(5).innerText(),/具体缺口尚未说明/);
  assert.equal(await p.locator('.source-cards img,.source-cards script,.source-cards svg,.source-cards b').count(),0);assert.equal(await p.evaluate(()=>window.__sourceXss),undefined);assert.equal(await p.locator('[data-source-card=""]').count(),1);assert.match(await p.locator('[data-source-card=""]').innerText(),/来源记录格式异常/);
  checks.push('native pending details expand; string, object, malformed entries and source names are escaped and isolated');
  for(const key of ['wechat:synthetic-zero','wechat:synthetic-missing','wechat:synthetic-scanned','wechat:synthetic-bad-count'])await card(key).locator('[data-source-gaps] > summary').click();
  assert.match(await card('wechat:synthetic-zero').locator('[data-source-count]').innerText(),/历史增量登记：0 条/);
  for(const key of ['wechat:synthetic-zero','wechat:synthetic-missing','wechat:synthetic-bad-count'])assert.match(await card(key).locator('[data-source-gaps]').innerText(),/不能据此认定全部内容已读/);
  for(const key of ['wechat:synthetic-missing','wechat:synthetic-bad-count'])assert.match(await card(key).locator('[data-source-count]').innerText(),/消息数量未记录/);
  assert.match(await card('wechat:synthetic-scanned').locator('[data-source-count]').innerText(),/3 条；不代表完整历史/);assert.match(await card('wechat:synthetic-scanned').locator('[data-source-gaps]').innerText(),/完整历史范围仍以来源说明为准/);
  checks.push('zero, absent and invalid counts never turn missing content into complete coverage');
  await currentCard('wechat:current-reading').locator('[data-source-tasks]').click();assert.equal(await p.locator('#childFilter').inputValue(),first);assert.equal(await p.locator('[data-view="待跟进"]').getAttribute('aria-pressed'),'true');await sources(p);
  await p.locator('nav [data-page="more"]').click();await p.locator('#content [data-page="agent"]').click();await eventually(async()=>await p.locator('#content h1').innerText()==='成长助手','agent page');const agentSources=p.locator('.agent-status [data-current-source]');assert.equal(await agentSources.count(),4);assert.equal(await agentSources.filter({has: p.locator('[data-current-source-status]')}).count(),4);await sources(p);
  checks.push('agent full status reuses the same four current source cards without an extra request');
  await fs.mkdir(proofDir,{recursive:true});
  await p.locator('details[data-source-history] > summary').click();
  for(const width of [360,1440]){
   await p.setViewportSize({width,height:1000});await checkWidth(p,String(width));await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:path.join(proofDir,'synthetic-sources-'+width+'.png'),fullPage:true});
   // Start with another view: a source shortcut must reset both child and tab.
   await p.locator('nav [data-page="tasks"]').click();await p.locator('[data-view="全部"]').click();await sources(p);await p.locator('details[data-source-history] > summary').click();
   for(const [key,name,title] of [['qq:synthetic-history',first,'虚构甲待办'],['wechat:synthetic-zero',second,'虚构乙待办']]){
    await card(key).locator('[data-source-tasks]').click();assert.equal(await p.locator('#childFilter').inputValue(),name);assert.equal(await p.locator('[data-view="待跟进"]').getAttribute('aria-pressed'),'true');assert.deepEqual(await p.locator('.checklist .task h3').allTextContents(),[title]);await checkWidth(p,'tasks '+width);await sources(p);await p.locator('details[data-source-history] > summary').click();
   }
   // Restore expanded source content for the next viewport.
   await p.locator('[data-source-gaps]').evaluateAll(details=>details.forEach(d=>{d.open=true}));
  }
  checks.push('360 and 1440 layouts fit; each source opens only that child pending checklist without writing');
  current={...current,children:current.children.map(c=>c.id===base.children[0].id?{...c,name:'虚构甲改名'}:c)};await p.locator('#refresh').click();await eventually(async()=>await p.locator('[data-current-source="wechat:current-school"]').count()===1,'renamed current source');await sources(p);assert.match(await currentCard('wechat:current-school').innerText(),/虚构甲改名/);assert.doesNotMatch(await currentCard('wechat:current-school').innerText(),/虚构旧归属名/);assert.equal(await currentCard('wechat:current-school').locator('[data-source-tasks]').getAttribute('data-source-tasks'),'虚构甲改名');checks.push('renaming a child updates current source ownership by stable child ID');
  current={...current,agent:{...current.agent,sources:current.agent.sources.map(s=>s.id==='wechat:current-reading'?{...s,last_success:'invalid-time'}:s)}};await p.locator('#refresh').click();await eventually(async()=>await p.locator('[data-current-source="wechat:current-reading"] [data-current-source-status]').innerText()==='读取待核对','invalid current source time');
  current={...current,agent:{...current.agent,sources:current.agent.sources.map(s=>s.id==='wechat:current-reading'?{...s,last_success:'',error:''}:s)}};await p.locator('#refresh').click();await eventually(async()=>await p.locator('[data-current-source="wechat:current-reading"] [data-current-source-status]').innerText()==='尚未读取','unread current source');checks.push('invalid and missing last-success timestamps stay unknown rather than becoming successful');
  assert.equal(await p.evaluate(()=>JSON.stringify({sync:window.__sourceInput.value.sync,sync_error:window.__sourceInput.value.sync_error,tasks:window.__sourceInput.value.tasks,children:window.__sourceInput.value.children,agent:window.__sourceInput.value.agent})===window.__sourceInput.before),true);
  current={...current,sync:{},sync_error:'虚构来源状态损坏 <img src=x onerror="window.__sourceXss=4">'};await p.locator('#refresh').click();await p.locator('details[data-source-history] > summary').click();await eventually(()=>p.locator('[data-source-error]').isVisible(),'explicit damaged source state');assert.match(await p.locator('[data-source-error]').innerText(),/虚构来源状态损坏 <img/);assert.equal((await p.locator('#content').innerText()).includes('还没有保存的消息来源'),false);await p.locator('nav [data-page="tasks"]').click();assert.ok(await p.locator('.task').count()>0,'source error leaves saved tasks usable');await sources(p);
  current={...current,sync:{},sync_error:'',agent:{...current.agent,sources:[]}};await p.locator('#refresh').click();await eventually(async()=>(await p.locator('#content').innerText()).includes('还没有保存的消息来源'),'real empty source state');assert.equal(await p.locator('[data-source-error]').count(),0);assert.notEqual(await p.locator('details[data-source-history]').getAttribute('open'),null);
  checks.push('damaged source metadata stays explicit while basic records work; valid empty source list is separate');
  const home=async(sources,changes={})=>{
   const stamp=new Date().toISOString();current={...current,sync:{},sync_error:'',agent:{...current.agent,enabled:true,state:'ready',last_error:'',last_run:stamp,sources,...changes}};
   await p.locator('nav [data-page="home"]').click();await p.locator('#refresh').click();
   await eventually(()=>p.evaluate(stamp=>window.__sourceInput?.value.agent.last_run===stamp,stamp),'latest home coverage');
  };
  const healthy={...sourceStates[0],unread_count:0,last_success:new Date().toISOString()},disabledQQ=sourceStates[3];
  const gradeConcern={id:'synthetic-grade-concern',kind:'care',child_id:base.children[1].id,state:'pending',title:'虚构英语学习跟进',body:'家长先和孩子核对这次英语困难，选一道愿意回看的题；记录卡点和实际帮助，再约定是否继续。',plan:{goal:'了解一个具体卡点',why_now:'虚构家长新增成绩观察',estimated_minutes:10,review_on:base.today},evidence:[{ref:'record:synthetic-grade-concern',text:'虚构家长成绩观察；不是实际家庭数据。'}]};
  const followups=[gradeConcern,{id:'synthetic-review',kind:'review',child_id:base.children[1].id,state:'pending',title:'虚构到期回看',body:'先核对孩子实际反馈，再决定下一步。',evidence:[]},{id:'synthetic-school',kind:'school',child_id:base.children[1].id,state:'pending',title:'虚构学校提醒',body:'虚构要求',evidence:[]}];
  for(const width of [360,1440]){
   await p.setViewportSize({width,height:1000});await home([healthy,disabledQQ]);const notice=p.locator('[data-source-coverage]');
   assert.equal(await notice.count(),1);const text=await notice.innerText();assert.ok(text.includes(second));assert.match(text,/QQ.*虚构停用QQ.*已暂停，不同步新消息/);assert.doesNotMatch(text,/虚构当前学校群/);
   const box=await notice.boundingBox();assert.ok(box&&box.y>=0&&box.y+box.height<1000,'coverage is visible without scrolling '+width);await checkWidth(p,'home QQ '+width);
   await p.screenshot({path:path.join(proofDir,'synthetic-home-coverage-'+width+'.png'),fullPage:true});await notice.click();await eventually(async()=>await p.locator('#content h1').innerText()==='来源与附件','coverage opens existing source page');
   assert.equal(await currentCard('qq:current-disabled').locator('[data-current-source-status]').innerText(),'已停用');
   await p.locator('nav [data-page="more"]').click();await p.locator('#content [data-page="agent"]').click();
   assert.match(await p.locator('.agent-status > div').first().innerText(),/后台整理：已完成本轮整理/);assert.match(await p.locator('.agent-status [data-source-coverage]').innerText(),/QQ.*已暂停，不同步新消息/);
   await home([{...healthy,unread_count:3}]);assert.match(await notice.innerText(),/3 条消息含未读内容/);assert.doesNotMatch(await notice.innerText(),/暂停|读取未成功|尚无成功/);await checkWidth(p,'home unread '+width);
   await home([{...sourceStates[1],last_success:''},sourceStates[2]]);assert.match(await notice.innerText(),/尚无成功读取记录/);assert.match(await notice.innerText(),/读取未成功/);assert.ok((await notice.innerText()).includes('<svg onload='));assert.equal(await notice.locator('img,svg,script').count(),0);await checkWidth(p,'home unknown and escaped '+width);
   await home([healthy],{enabled:false,state:'disabled'});assert.match(await notice.innerText(),/采集已暂停，不同步新消息/);
   await home([healthy],{state:'error',last_error:'虚构模型整理失败'});assert.equal(await notice.count(),0,'processing failure does not mislabel successful source reads');
   await home([],{enabled:false,state:'disabled'});assert.equal(await notice.count(),0,'manual family without sources has no source fault');assert.equal(await p.locator('[data-today-child]').count(),current.children.length);
   await home([],{items:followups});const owner=p.locator('[data-today-child="'+base.children[1].id+'"]'),other=p.locator('[data-today-child="'+base.children[0].id+'"]'),care=owner.locator('[data-agent-item="synthetic-grade-concern"]');
   assert.match(await owner.locator('.agent-child').innerText(),/需要核对与跟进 · 3/);assert.equal(await care.locator(':scope > p').innerText(),gradeConcern.body);assert.equal(await care.locator('[data-agent-accept]').innerText(),'核对并安排');assert.equal(await other.locator('[data-agent-item]').count(),0);
   assert.deepEqual(await owner.locator('[data-agent-item]').evaluateAll(xs=>xs.map(x=>x.dataset.agentItem)),['synthetic-grade-concern','synthetic-review']);assert.equal(await owner.locator('.agent-child [data-page="agent"]').count(),1);await checkWidth(p,'home learning follow-up '+width);
   await owner.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(proofDir,'synthetic-home-learning-followup-'+width+'.png'),fullPage:true});
   await care.locator('[data-agent-accept]').click();assert.equal(await p.locator('#agentForm textarea[name="body"]').inputValue(),gradeConcern.body);assert.equal(await p.locator('#agentForm input[name="id"]').inputValue(),gradeConcern.id);assert.equal(await p.locator('#agentForm button[type="submit"]').innerText(),'确认安排');await p.locator('[data-close="agentDialog"]').click();
  }
  await home([],{enabled:false,state:'error',last_error:'虚构来源状态不可读'});assert.match(await p.locator('[data-source-coverage]').innerText(),/学校信息状态暂时无法核对/);
  assert.equal(await p.evaluate(()=>JSON.stringify({sync:window.__sourceInput.value.sync,sync_error:window.__sourceInput.value.sync_error,tasks:window.__sourceInput.value.tasks,children:window.__sourceInput.value.children,agent:window.__sourceInput.value.agent})===window.__sourceInput.before),true);
  checks.push('360/1440 homepage names the affected child/platform/group; disabled QQ stays visible beside healthy sources and ready processing; source link reuses existing page');
  checks.push('unread content, failed or never-successful reads, paused collection and manual/no-source households remain distinct; homepage errors and names are escaped');
  checks.push('360/1440 grade-concern care and review appear only under their child with full action and existing confirmation form; at most two reminders and remaining-reminders link retained');
  assert.deepEqual(errors,[]);assert.deepEqual(mutations,[]);assert.deepEqual(external,[]);assert.equal(await p.evaluate(()=>window.__sourceXss),undefined);
  const proof={checkedAt:new Date().toISOString(),passed:checks.length,checks,syntheticOnly:true,mutationRequests:0,externalRequests:0,sourceInputUnchanged:true,realPhoneTested:false};await fs.writeFile(path.join(proofDir,'ui-proof.json'),JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof,null,2));
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
