// The whole fictional 2026-11-04 day (r291's six school items and the child's own oral correction) served by
// test_source_failure_contract.py with one more QQ source of the same child, read through the real collector round and
// Store.ingest on the served day's own clock (its WeChat source read at 20:00): --serve-failed: QQ natural success 18:30,
// then 19:05 one read failed with the QQ reader's fixed code qq_endpoint_refused; --serve-recovered: then 19:40 one more
// natural success on the same old cursor. The browser is held at that clock (20:00:30) and every source of this child is
// checked by its own state. At 360/1440 on the current home (calendar.js todayTasksHTML): all seven own tasks stay listed;
// the failed read shows .today-source-gap "消息读取有缺口，作业可能缺项。", never that there is no homework; after recovery
// that read gap is gone while the WeChat source's unread-original gap stays as it is. Through the real nav (更多 → 消息来源与
// 附件, no 检查最新消息 click, no collection request) each source card shows its own status and only the fixed reason. One
// feedback from the follow-reading survives one 503 with its draft and the same request key, then reopens once after reload;
// the dictation and the other child get nothing. All requests stay on this fixture server; it calls no model and no real
// service; only it is stopped at the end. Not run on M4 (no Node there): Root runs it. Needs Playwright page.clock (>=1.45).
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, SOURCE_FAILURE_UI_PROOF_DIR (fictional screenshots).
const assert=require('node:assert/strict'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check,label,tries=250){for(let n=0;n<tries;n++){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function proof(page,name){const dir=process.env.SOURCE_FAILURE_UI_PROOF_DIR;if(!dir)return;const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(dir,{recursive:true});await page.screenshot({path:path.join(dir,name+'.png'),fullPage:true})}
async function fixture(mode){
 const sock=net.createServer();sock.listen(0,'127.0.0.1');await once(sock,'listening');const port=sock.address().port;await new Promise(r=>sock.close(r));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_source_failure_contract.py',mode,String(port)],{cwd:__dirname,env,stdio:['ignore','ignore','inherit']}),url=`http://127.0.0.1:${port}/`;
 const stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(3000)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{await until(async()=>{assert.equal(proc.exitCode,null,'the fixture exited early');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'fixture up',750)}catch(e){await stop();throw e}
 return {url,stop};
}
const DAY='2026-11-04',CLOCK=Date.parse('2026-11-04T20:00:30+08:00'),QQ='qq:10002';
const READ_GAP='消息读取有缺口，作业可能缺项。',ORIGINAL_GAP='部分消息原件尚未读全。';
const REASON='本机QQ接口未接受连接；本次未同步新消息，上次成功记录保留。',NOTE='虚构反馈：来源读取未成功时也能保存这条反馈';
const LEAK=/FICTIONAL|\/Users\/|token|stderr|qq_endpoint|cli_read_failed|10002|20001/,CLAIM=/没有作业|无作业|今天没有|扫码|登录|过期/;
// Fresh by app.js currentSourceStatus at the held clock: no error, read before it, next read not overdue by 5 minutes.
const fresh=s=>!s.error&&Date.parse(s.last_success)<=CLOCK&&CLOCK<=Date.parse(s.next_collection_at)+5*60*1000;
(async()=>{let server,browser;try{
 browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 for(const mode of ['--serve-failed','--serve-recovered']){server=await fixture(mode);const failed=mode==='--serve-failed',tag=failed?'failed':'recovered';
 const state=async()=>(await(await fetch(server.url+'api/state')).json());
 const first=await state(),a=first.children.find(c=>c.id==='child-1'),b=first.children.find(c=>c.id!=='child-1');
 assert(a&&b,'two fictional children');assert.equal(first.today,DAY,'the frozen fictional day');
 const mine=first.tasks.filter(t=>t.child===a.name);assert.equal(mine.length,7,'six school items and the oral one: '+mine.map(t=>t.title).join(' | '));
 const read=mine.find(t=>t.title.includes('跟读')),dictation=mine.find(t=>t.title.includes('参加课堂听写'));assert(read&&dictation,'the follow-reading and the dictation');
 // Every source of this child by its own state at the one clock: only the QQ read failed, and only in the failed mode.
 const own=first.agent.sources.filter(s=>s.child_id===a.id),qq=own.find(s=>s.id===QQ);
 assert(qq&&qq.platform==='qq'&&own.length===2,'the WeChat source of the day and the added QQ source: '+own.map(s=>s.id));
 assert.equal(qq.error,failed?REASON:'',tag+' the fixed reason only');assert.equal(qq.cursor,'100',tag+' the old cursor stays');assert(qq.last_success,tag+' last success kept');
 assert.equal(qq.collection_check.requested_at,'',tag+' no parent check is pending');
 const expected=Object.fromEntries(own.map(s=>[s.id,s.id===QQ&&failed?'最近读取未成功':'最近读取成功']));
 for(const s of own)if(expected[s.id]==='最近读取成功')assert(fresh(s),`${tag} ${s.id} is fresh at the held clock: ${JSON.stringify(s)}`);
 const originals=own.some(s=>s.unread_count>0);
 assert.doesNotMatch(JSON.stringify(first.agent.sources),/FICTIONAL|\/Users\/fictional/,'no command output or path in the state');
 const records=async id=>(await state()).records.filter(r=>r.source==='事项:'+id),before=JSON.stringify(dictation);
 for(const width of [360,1440]){
  const p=await browser.newPage({viewport:{width,height:900}}),errors=[],external=[],posts=[];p.on('pageerror',e=>errors.push(e.message));
  assert(p.clock,'Playwright page.clock is required to hold the fictional clock');await p.clock.setFixedTime(CLOCK);
  await p.route(u=>!u.href.startsWith(server.url),r=>{external.push(r.request().url());return r.abort()});
  p.on('request',r=>{if(r.method()!=='GET')posts.push(new URL(r.url()).pathname)});
  const row=id=>p.locator(`[data-query-target="task:${id}"]`).first();
  const ready=async()=>{await until(async()=>await p.locator('body[data-page=home] #task-groups').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','real list ready');
   await p.locator(`[data-child-filter="${a.id}"]`).first().click();await until(async()=>await p.locator(`[data-query-target="task:${read.id}"]`).count()>0,'single child list')};
  const gap=async()=>await p.locator('.today-source-gap').count()?(await p.locator('.today-source-gap').first().innerText()).trim():'';
  await p.goto(server.url);await ready();
  for(const t of mine)assert(await row(t.id).isVisible(),`${width} ${tag} ${t.title} stays listed`);
  const said=await gap();
  if(failed)assert(said.includes(READ_GAP),`${width} the read gap on today: ${said}`);
  else{assert(!said.includes(READ_GAP),`${width} recovered: no read gap: ${said}`);assert.equal(said.includes(ORIGINAL_GAP),originals,`${width} recovered: the unread-original gap stays as it is: ${said}`)}
  assert.doesNotMatch(said,CLAIM,`${width} ${tag} the gap claims nothing unproven: ${said}`);
  const body=await p.locator('body').innerText();assert.doesNotMatch(body,/FICTIONAL|\/Users\/|qq_endpoint|cli_read_failed/,`${width} ${tag} no reader output on today`);
  assert.doesNotMatch(body,/没有作业|无作业|今天没有作业/,`${width} ${tag} today never says there is no homework`);
  assert(await row(read.id).locator('[data-school-original-ref]').count()>0,`${width} the follow-reading keeps its own school original`);
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width} ${tag} no horizontal overflow`);await proof(p,`source-failure-today-${tag}-${width}`);
  // The real nav: 更多 → 消息来源与附件; never 检查最新消息, which would queue a collection request.
  const more=p.locator('nav [data-page="more"]');let shown=null;for(let i=0;i<await more.count();i++)if(await more.nth(i).isVisible()){shown=more.nth(i);break}
  assert(shown,`${width} a visible 更多 in the nav`);await shown.click();
  const link=p.locator('#content [data-page="sources"]:not([data-collection-check])').first();await until(()=>link.isVisible(),'更多 → 消息来源与附件');await link.click();
  await until(async()=>await p.locator('[data-current-source]').count()===own.length,'the sources page with this child\'s sources');
  for(const s of own){
   const card=p.locator(`[data-current-source="${s.id}"]`);assert(await card.isVisible(),`${width} ${s.id} card`);
   const text=await card.innerText();assert.equal((await card.locator('[data-current-source-status]').innerText()).trim(),expected[s.id],`${width} ${tag} ${s.id} status`);
   if(s.id===QQ&&failed)assert(text.includes(REASON),`${width} the fixed reason: ${text}`);
   else assert.equal(await card.locator('.error[role=status]').count(),s.error?1:0,`${width} ${tag} ${s.id} error as stored`);
   if(s.id===QQ&&!failed)assert(!text.includes('本机QQ接口'),`${width} recovered card: ${text}`);
   assert.doesNotMatch(text,LEAK,`${width} ${tag} ${s.id} card: ${text}`);assert.doesNotMatch(text,CLAIM,`${width} ${tag} ${s.id} card: ${text}`);
  }
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width} ${tag} sources: no horizontal overflow`);await proof(p,`source-failure-sources-${tag}-${width}`);
  await p.goto(server.url);await ready();
  const entry=()=>row(read.id).locator(`[data-task="${read.id}"]`).first();
  if(width===360){
   // From the follow-reading's own entry: 1 refused before any write (503), 2 the same request saves.
   await entry().click();await until(async()=>(await p.locator('#taskTitle').innerText()).includes(read.title),'its own dialog');
   await p.locator('#taskForm [name=note]').fill(NOTE);const keys=[];let attempts=0;
   await p.route('**/api/task/feedback',async route=>{attempts++;keys.push(route.request().postDataJSON().request_key);
    if(attempts===1)return route.fulfill({status:503,json:{error:'虚构服务暂不可写'}});return route.continue()});
   await p.locator('#saveTaskFeedback').click();await until(async()=>(await p.locator('#taskError').innerText()).trim()!=='','503 shown');
   assert.equal((await records(read.id)).length,0,'the 503 wrote nothing');assert.equal(await p.locator('#taskForm [name=note]').inputValue(),NOTE,'the draft stays');
   await p.locator('#saveTaskFeedback').click();await until(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'saved');
   await p.unroute('**/api/task/feedback');assert.equal(attempts,2,'one 503 and one retry');assert.equal(new Set(keys).size,1,'one request key across the 503 and the retry');
  }
  const saved=await records(read.id);assert.equal(saved.length,1,`${width} ${tag} one feedback on the server`);assert(saved[0].note.includes(NOTE));
  assert.equal((await records(dictation.id)).length,0,'the dictation gets no feedback');
  assert.equal(JSON.stringify((await state()).tasks.find(t=>t.id===dictation.id)),before,'the dictation is not changed or completed');
  await p.reload();await ready();
  for(let n=0;n<2;n++){
   assert.equal((await entry().innerText()).trim(),'查看/补充反馈');await entry().click();
   await until(async()=>(await p.locator('#taskFeedbackHistory').innerText()).includes(NOTE),'saved feedback reopens');
   assert.equal(await p.locator('#taskForm').evaluate(f=>f.elements.id.value),read.id,'the same original task');
   await p.keyboard.press('Escape');await until(async()=>!(await p.locator('#taskDialog').evaluate(d=>d.open)),'dialog closed');
  }
  assert.equal((await records(read.id)).length,1,'reopening adds nothing');await proof(p,`source-failure-feedback-${tag}-${width}`);
  await p.locator(`[data-child-filter="${b.id}"]`).first().click();
  await until(async()=>{for(const t of mine)if(await p.locator(`[data-query-target="task:${t.id}"]`).count())return false;return true},'the other child sees none');
  assert.equal(await p.locator('.today-source-gap').count(),0,`${width} the other child (no source of its own) gets no gap from this child's source`);
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width} other child: no horizontal overflow`);
  assert.deepEqual(external,[],'no request left the fixture server');
  assert(!posts.some(x=>/collect|check/.test(x)),`${width} no collection request: ${posts}`);
  assert.deepEqual(errors,[]);await p.close();
 }
 const last=(await state()).agent.sources.find(s=>s.id===QQ);
 assert.deepEqual([last.cursor,last.error,last.collection_check.requested_at],['100',failed?REASON:'',''],tag+' the source is unchanged by the browser');
 await server.stop();server=null;console.log('PASS '+tag)}
 console.log('PASS: source failure on the whole day at 360/1440 on one fictional clock: 7 own tasks on today, read gap only while the QQ read failed, each source card its own status and fixed reason through 更多, one 503 then one feedback reopened, child isolation, no external or collection request');
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>console.log('TERMINAL exit='+(process.exitCode||0)));
