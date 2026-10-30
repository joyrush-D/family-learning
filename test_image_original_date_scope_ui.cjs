// Root's fictional English teacher image (503: an unread image message whose caption only points to the image, both
// requirements only in the image) and its three actual product replies, replayed as fixed inputs by
// test_image_original_date_scope.py (--serve-image: newly saved; --serve-image-saved: the earlier release's saved
// follow-reading held without a day, then the bounded no-model restore). Either serves the whole fictional 2026-11-04 day:
// six school items and the child's own oral math correction saved through study (one request saved twice, one task).
// Read at 360/1440 on the real single-child list: seven own tasks; each school item with its own day and teacher original;
// the evening follow-reading and the next-day classroom dictation both cite the same 503 and neither takes the other's
// words or range; the oral item keeps its requirement, day and the child's own origin, with no teacher original. The
// follow-reading's own original button opens its material with the 503 image (loaded at the fixture PNG's natural size,
// read back byte for byte as it), and 返回列表 closes it back to the list. One feedback from the follow-reading's own entry
// survives a 503 and a lost reply as one record, reopens after close and reload, and never reaches the dictation or the
// other child. The fixture calls no model and uses no household path, collector, printer or device; only that fixture
// process is stopped at the end. Not run on M4 (no Node there).
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, IMAGE_DATE_SCOPE_UI_PROOF_DIR (fictional screenshots).
const assert=require('node:assert/strict'),net=require('node:net'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
// The public fixture's fictional PNG: the bytes and IHDR size the opened original must show.
const FIX=require('./test_image_original_date_scope.json'),PNG=Buffer.from(FIX.image_png_base64,'base64');
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
assert.equal(sha(PNG),FIX.image_source.sha256,'the fixture PNG');assert.equal(PNG.toString('latin1',12,16),'IHDR','a PNG header');
const SIZE=[PNG.readUInt32BE(16),PNG.readUInt32BE(20)];
async function until(check,label,tries=250){for(let n=0;n<tries;n++){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function proof(page,name){const dir=process.env.IMAGE_DATE_SCOPE_UI_PROOF_DIR;if(!dir)return;const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(dir,{recursive:true});await page.screenshot({path:path.join(dir,name+'.png'),fullPage:true})}
async function fixture(mode){
 const sock=net.createServer();sock.listen(0,'127.0.0.1');await once(sock,'listening');const port=sock.address().port;await new Promise(r=>sock.close(r));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_image_original_date_scope.py',mode,String(port)],{cwd:__dirname,env,stdio:['ignore','ignore','inherit']}),url=`http://127.0.0.1:${port}/`;
 const stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(3000)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{await until(async()=>{assert.equal(proc.exitCode,null,'the fixture exited early');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'fixture up',750)}catch(e){await stop();throw e}
 return {url,stop};
}
// The frozen whole-day truth: anchor in its own title, words its row keeps, subject, the day it shows (null: tonight's own).
const DAY='2026-11-04',DAY5=/11月0?5日|11-05|11\/0?5|周四|星期四|明天/,DAY9=/11月0?9日|11-09|11\/0?9|周一|星期一/;
const ITEMS=[['晚照',['《晚照》','2遍','签字'],'语文',DAY5],['练习册第12页',['12','2','4','计算过程'],'数学',DAY5],
 ['跟读',['Unit 7','3','10','3遍','不用抄写'],'英语',null],["参加课堂听写",['听写'],'英语',DAY5],
 ['单词听写本',['《单词听写本》','不用在家练习'],'英语',DAY5],['出游回执',['出游回执','勾选','参加或不参加','签名','交回'],'',DAY9]];
// The child's own oral addition (no teacher original): anchor, words its row keeps, subject.
const ORAL=['订正课堂练习第5、6题',['第5、6题','错因'],'数学'],TEACHER=/虚构\S{0,4}(老师|班主任)|16:0[0-5]/;
const BORROWED=['Unit','第3至10','第3–10','10个','今晚','范围'],NOTE='虚构反馈：第5个单词跟读时重音不稳，再练一遍';
(async()=>{let server,browser;try{
 browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 for(const mode of ['--serve-image','--serve-image-saved']){server=await fixture(mode);const tag=mode.slice(14)||'new';
 const state=async()=>(await(await fetch(server.url+'api/state')).json());
 const first=await state(),a=first.children.find(c=>c.id==='child-1'),b=first.children.find(c=>c.id!=='child-1');
 assert(a&&b,'two fictional children');assert.equal(first.today,DAY,'the frozen fictional day');
 const mine=first.tasks.filter(t=>t.child===a.name);assert.equal(mine.length,7,'six school items and the oral one: '+mine.map(t=>t.title).join(' | '));
 const task=anchor=>{const found=mine.filter(t=>t.title.includes(anchor));assert.equal(found.length,1,anchor+': '+mine.map(t=>t.title).join(' | '));return found[0]};
 const read=task('跟读'),dictation=task("参加课堂听写"),oral=task(ORAL[0]),ids=[...ITEMS.map(([anchor])=>task(anchor).id),oral.id];
 assert.equal(new Set(ids).size,7,'seven distinct tasks');
 for(const word of ['Unit','单词','第3','10','跟读','今晚'])assert(!dictation.title.includes(word),'the dictation title borrows '+word+': '+dictation.title);
 // Saved twice with one request: one oral task of this child on its own day, from the child's own report, citing no teacher.
 const origin=String(oral.source||'');
 assert(origin.includes('孩子自述')&&!origin.split('\n').some(r=>r.startsWith('message:')),'the child\'s own report: '+origin);
 assert(!oral.school_origin&&!(oral.agenda?.publications||[]).length,'the oral correction cites no teacher original');
 assert([oral.agenda?.complete_on,oral.agenda?.due_on,oral.agenda?.scheduled_on].includes(DAY),'the oral correction is on its own day: '+JSON.stringify(oral.agenda));
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
   assert.match(text,TEACHER,`${width} ${anchor} shows its own teacher original`);
  }
  const oralText=await row(oral.id).innerText();assert(await row(oral.id).isVisible(),`${width} the oral correction is listed`);
  for(const word of [...ORAL[1],ORAL[2]])assert(oralText.includes(word),`${width} the oral correction keeps ${word}: ${oralText}`);
  assert.doesNotMatch(oralText,TEACHER,`${width} the oral correction shows no teacher original: ${oralText}`);
  assert.equal(await row(oral.id).locator('[data-school-original-ref]').count(),0,`${width} the oral correction has no original button`);
  const card=await main(dictation.id);for(const word of BORROWED)assert(!card.includes(word),`${width} the dictation card borrows ${word}: ${card}`);
  assert.equal(await p.locator('[data-query-target^="task:"]').filter({hasText:'海边小记'}).count(),0,'the reference reading is no task');
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),width+' no horizontal overflow');await proof(p,`image-date-scope-list-${tag}-${width}`);
  // The image original opens from the follow-reading's own original button (app.js openSchoolOriginal/paintSchoolOriginal):
  // its material shows the 503 image, loaded at its natural size and read back as the fixture PNG; 返回列表 closes it.
  const openers=row(read.id).locator('[data-school-original-ref]');assert(await openers.count()>0,`${width} the follow-reading has its own original button`);
  if(!await openers.first().isVisible())await row(read.id).locator('details:has([data-school-original-ref])>summary').first().click();
  await openers.first().click();
  const dialog=p.locator('#schoolOriginalDialog'),shown=dialog.locator('img[src*="upload/"]'),said=async e=>{throw Error(e.message+': '+await dialog.innerText())};
  await until(async()=>await dialog.count()>0&&await dialog.evaluate(d=>d.open),'the original opens');
  await until(async()=>await shown.count()>0,'its image').catch(said);
  assert.equal(await shown.count(),1,`${width} one image: the 503 original`);
  assert((await dialog.locator('h2').first().innerText()).includes(read.title),`${width} the follow-reading's own material`);
  await shown.scrollIntoViewIfNeeded();await until(()=>shown.evaluate(i=>i.complete&&i.naturalWidth>0),'the image loads').catch(said);
  assert.deepEqual(await shown.evaluate(i=>[i.naturalWidth,i.naturalHeight]),SIZE,`${width} the image at its natural size`);
  const bytes=Buffer.from(await p.evaluate(async src=>{const r=await fetch(src);if(!r.ok)throw Error('upload '+r.status);return [...new Uint8Array(await r.arrayBuffer())]},await shown.evaluate(i=>i.currentSrc||i.src)));
  assert.equal(sha(bytes),FIX.image_source.sha256,`${width} the shown original is the fixture PNG byte for byte`);await proof(p,`image-original-${tag}-${width}`);
  await dialog.locator('[data-school-original-close]').first().click();
  await until(async()=>!(await dialog.evaluate(d=>d.open)),'back to the list');assert(await row(read.id).isVisible(),`${width} the list is back`);
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
  assert.equal((await records(read.id)).length,1,'reopening adds nothing');await proof(p,`image-date-scope-feedback-${tag}-${width}`);
  await p.locator(`[data-child-filter="${b.id}"]`).first().click();
  await until(async()=>{for(const id of ids)if(await p.locator(`[data-query-target="task:${id}"]`).count())return false;return true},'the other child sees none');
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),width+' other child: no horizontal overflow');
  assert.deepEqual(errors,[]);await p.close();
 }
 await server.stop();server=null;console.log('PASS '+tag)}
 console.log('PASS: image whole day, new and earlier-saved, at 360/1440: 7 own tasks (6 school, 1 oral), the follow-reading image opened from its own item at its natural size and fixture bytes, dictation own words, 503/lost reply one feedback, reopen, child isolation');
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>console.log('TERMINAL exit='+(process.exitCode||0)));
