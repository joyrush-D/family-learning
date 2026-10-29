// Root's second actual reply for the fictional 2026-11-04 whole day (ACTUAL-SELECTION-TITLE.json), saved by the real
// run_once -> Store with the child's own oral addition through study, read on the real single-child list at 360/1440.
// The classroom dictation keeps only its teacher's own words in its title and main card; the evening read-aloud keeps its
// Unit 7 range, 3遍 and 不用抄写; the reference reading is no task. One fictional feedback from the read-aloud's own entry
// survives a 503 and a lost reply as one record, reopens after close and reload, and never reaches the dictation or the
// other child. The fixture (test_daily_list_whole_day.py --serve-actual) calls no model and uses no household path,
// collector, printer or device; only that fixture process is stopped at the end. The same run then reads an earlier
// release's saved list (--serve-actual-saved: the reply saved with the sibling guards off, both borrowings kept in its rows)
// through the current reader: the same checks, the saved rows untouched.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, DAILY_ACTUAL_SCOPE_UI_PROOF_DIR (fictional screenshots).
const assert=require('node:assert/strict'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check,label,tries=250){for(let n=0;n<tries;n++){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function proof(page,name){const dir=process.env.DAILY_ACTUAL_SCOPE_UI_PROOF_DIR;if(!dir)return;const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(dir,{recursive:true});await page.screenshot({path:path.join(dir,name+'.png'),fullPage:true})}
async function fixture(mode){
 const sock=net.createServer();sock.listen(0,'127.0.0.1');await once(sock,'listening');const port=sock.address().port;await new Promise(r=>sock.close(r));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_daily_list_whole_day.py',mode,String(port)],{cwd:__dirname,env,stdio:['ignore','ignore','inherit']}),url=`http://127.0.0.1:${port}/`;
 const stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(3000)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{await until(async()=>{assert.equal(proc.exitCode,null,'the fixture exited early');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'fixture up',750)}catch(e){await stop();throw e}
 return {url,stop};
}
// The frozen whole-day truth: anchor in its own title, words its row keeps, subject, the day it shows (null: tonight's own).
const DAY5=/11月0?5日|11-05|11\/0?5|周四|星期四|明天/,DAY9=/11月0?9日|11-09|11\/0?9|周一|星期一/;
const ITEMS=[['晚照',['《晚照》','2遍','签字'],'语文',DAY5],['练习册第12页',['12','2','4','计算过程'],'数学',DAY5],
 ['跟读',['Unit 7','3','10','3遍','不用抄写'],'英语',null],['英语课听写',['听写'],'英语',DAY5],
 ['单词听写本',['《单词听写本》','不用在家练习'],'英语',DAY5],['出游回执',['出游回执','勾选','参加或不参加','签名','交回'],'',DAY9],
 ['订正课堂练习第5、6题',['错因'],'数学',null]];
const BORROWED=['Unit','第3至10','第3–10','10个','今晚','范围'],NOTE='虚构反馈：第5个单词跟读时重音不稳，再练一遍';
(async()=>{let server,browser;try{
 browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 for(const mode of ['--serve-actual','--serve-actual-saved']){server=await fixture(mode);const tag=mode.slice(15)||'new';
 const state=async()=>(await(await fetch(server.url+'api/state')).json());
 const first=await state(),a=first.children.find(c=>c.id==='child-1'),b=first.children.find(c=>c.id!=='child-1');
 assert(a&&b,'two fictional children');assert.equal(first.today,'2026-11-04','the frozen fictional day');
 const mine=first.tasks.filter(t=>t.child===a.name);assert.equal(mine.length,7,mine.map(t=>t.title).join(' | '));
 const task=anchor=>{const found=mine.filter(t=>t.title.includes(anchor));assert.equal(found.length,1,anchor+': '+mine.map(t=>t.title).join(' | '));return found[0]};
 const read=task('跟读'),dictation=task('英语课听写'),ids=ITEMS.map(([anchor])=>task(anchor).id);
 for(const word of ['Unit','单词','第3','10','跟读','今晚'])assert(!dictation.title.includes(word),'the dictation title borrows '+word+': '+dictation.title);
 assert.equal(first.tasks.filter(t=>t.child===b.name&&ids.includes(t.id)).length,0,'the other child has none of these');
 const records=async id=>(await state()).records.filter(r=>r.source==='事项:'+id),before=JSON.stringify(dictation);
 for(const width of [360,1440]){
  const p=await browser.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
  const ready=async()=>{await until(async()=>await p.locator('body[data-page=home] #task-groups').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','real list ready');
   await p.locator(`[data-child-filter="${a.id}"]`).first().click();await until(async()=>await p.locator(`[data-query-target="task:${read.id}"]`).count()>0,'single child list')};
  const row=id=>p.locator(`[data-query-target="task:${id}"]`).first();
  // The main card without any original/detail block: the 503 original does say 跟读, that detail is not this item's requirement.
  const main=id=>row(id).evaluate(r=>{const c=r.cloneNode(true);c.querySelectorAll('details,blockquote,[data-original],.original,.origin').forEach(n=>n.remove());return c.textContent});
  await p.goto(server.url);await ready();
  for(const [anchor,keep,subject,day] of ITEMS){
   const id=task(anchor).id,text=await row(id).innerText();assert(await row(id).isVisible(),anchor+' is listed');
   for(const word of keep)assert(text.includes(word),`${width} ${anchor} keeps ${word}: ${text}`);
   if(subject)assert(text.includes(subject),`${width} ${anchor} shows ${subject}`);
   if(day)assert.match(text,day,`${width} ${anchor} shows its day`);
   if(anchor!=='订正课堂练习第5、6题')assert.match(text,/虚构\S{0,4}(老师|班主任)|16:0[0-5]/,`${width} ${anchor} shows its own teacher original`);
  }
  const card=await main(dictation.id);for(const word of BORROWED)assert(!card.includes(word),`${width} the dictation card borrows ${word}: ${card}`);
  assert.equal(await p.locator('[data-query-target^="task:"]').filter({hasText:'海边小记'}).count(),0,'the reference reading is no task');
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),width+' no horizontal overflow');await proof(p,`actual-scope-list-${tag}-${width}`);
  const entry=()=>row(read.id).locator(`[data-task="${read.id}"]`).first();
  if(width===360){
   // From the read-aloud's own entry: 1 refused before any write (503), 2 saved but the reply lost, 3 the same request replays.
   await entry().click();await until(async()=>(await p.locator('#taskTitle').innerText()).includes(read.title),'its own dialog');
   await p.locator('#taskForm [name=note]').fill(NOTE);const keys=[];let attempts=0;
   await p.route('**/api/task/feedback',async route=>{attempts++;keys.push(route.request().postDataJSON().request_key);
    if(attempts===1)return route.fulfill({status:503,json:{error:'虚构服务暂不可写'}});
    if(attempts===2){const response=await route.fetch();assert(response.ok);return route.abort('failed')}
    return route.continue()});
   await p.locator('#saveTaskFeedback').click();await until(async()=>(await p.locator('#taskError').innerText()).trim()!=='','503 shown');
   assert.equal((await records(read.id)).length,0,'the 503 wrote nothing');assert.equal(await p.locator('#taskForm [name=note]').inputValue(),NOTE,'the draft stays');
   await p.locator('#saveTaskFeedback').click();await until(async()=>/保存结果尚未核对/.test(await p.locator('#taskError').innerText()),'lost reply shown');
   await p.locator('#saveTaskFeedback').click();await until(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'saved');
   await p.unroute('**/api/task/feedback');assert.equal(new Set(keys).size,1,'one request key across 503, lost reply and retry');
  }
  const saved=await records(read.id);assert.equal(saved.length,1,'one feedback on the server');assert(saved[0].note.includes(NOTE));
  assert.equal((await records(dictation.id)).length,0,'the dictation gets no feedback');
  assert.equal(JSON.stringify((await state()).tasks.find(t=>t.id===dictation.id)),before,'the dictation is not changed or completed');
  // Refresh, then open, close and reopen: the same original read-aloud task with its one saved feedback.
  await p.reload();await ready();
  for(let n=0;n<2;n++){
   assert.equal((await entry().innerText()).trim(),'查看/补充反馈');await entry().click();
   await until(async()=>(await p.locator('#taskFeedbackHistory').innerText()).includes(NOTE),'saved feedback reopens');
   assert.equal(await p.locator('#taskForm').evaluate(f=>f.elements.id.value),read.id,'the same original task');
   await p.keyboard.press('Escape');await until(async()=>!(await p.locator('#taskDialog').evaluate(d=>d.open)),'dialog closed');
  }
  assert.equal((await records(read.id)).length,1,'reopening adds nothing');await proof(p,`actual-scope-feedback-${tag}-${width}`);
  await p.locator(`[data-child-filter="${b.id}"]`).first().click();
  await until(async()=>{for(const id of ids)if(await p.locator(`[data-query-target="task:${id}"]`).count())return false;return true},'the other child sees none');
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),width+' other child: no horizontal overflow');
  assert.deepEqual(errors,[]);await p.close();
 }
 await server.stop();server=null;console.log('PASS '+tag)}
 console.log('PASS: actual title reply, new and earlier-saved, at 360/1440: 7 own tasks, dictation title/card own words, read-aloud range, 503/lost reply one feedback, reopen, child isolation');
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>console.log('TERMINAL exit='+(process.exitCode||0)));
