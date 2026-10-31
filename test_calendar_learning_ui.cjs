// Web home acceptance of the calendar-led day over test_calendar_learning's fictional week, served by the real app server
// (test_native_calendar_learning.py --fixture). Headless Chromium at 1440 and 360: the three entries, the week strip (a click
// on a day is one GET /api/day; a week step; back to today), the server's lessons/plans with the task time on its own row,
// child switching, the wrong book with the original task, learning evidence with topic basis and the course record apart,
// the way back to the original task, a confirmed topic link shown by name as linked and pending diagnosis, a wrong record
// without a task opened and corrected through the existing record entries (saved, then read again on a new page), 44px
// targets and no sideways scroll. Waits are selector based: the page's CSP has no unsafe-eval and stays that way.
// CALENDAR_FIXTURE_TAXONOMY_DIR=<fixed e0f931b pack> makes names the pack's own. No model, household data or login is used.
// Usage: FAMILY_TEST_PYTHON=python3.12 PLAYWRIGHT_MODULE=/path/to/playwright [CHROMIUM_EXECUTABLE=/path] node test_calendar_learning_ui.cjs [out-dir]
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
let T='cnm_010';const out=process.argv[2]||fs.mkdtempSync(path.join(require('node:os').tmpdir(),'calendar-learning-ui-'));fs.mkdirSync(out,{recursive:true});
(async()=>{
 const env={...Object.fromEntries(Object.entries(process.env).filter(([k])=>!k.startsWith('FAMILY_'))),FAMILY_NATIVE_CALENDAR_FIXTURE:'1'};
 const server=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-B',path.join(__dirname,'test_native_calendar_learning.py'),'--fixture'],{cwd:__dirname,env,stdio:['ignore','pipe','inherit']});
 const info=await new Promise((ok,bad)=>{let buf='';server.stdout.on('data',d=>{buf+=d;if(buf.includes('\n'))ok(JSON.parse(buf.split('\n')[0]))});server.on('exit',c=>bad(Error('fixture exited '+c)))});
 if(info.pack_installed)T='有理数的加法法则';
 const browser=await chromium.launch(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{});const report={commit:process.env.CANDIDATE||'',checks:[]};const ok=(name,extra={})=>report.checks.push({name,ok:true,...extra});
 try{
  for(const width of [1440,360]){
   const page=await browser.newPage({viewport:{width,height:width>900?900:780}});const days=[];
   page.on('request',r=>{if(new URL(r.url()).pathname==='/api/day')days.push(r.url())});
   await page.goto(info.url+'/');await page.waitForSelector('.grove-tabs');
   const sel=d=>`[data-grove-day="${d}"]`;
   await page.waitForSelector(sel('2026-10-28')+'[aria-pressed="true"]');
   const courses=page.locator('#today-courses');
   assert.match(await courses.innerText(),/第3节[\s\S]*英语/);assert.match(await courses.innerText(),/18:00–18:30[\s\S]*虚构钢琴课/);
   assert.doesNotMatch(await page.locator('.grove').innerText(),/虚构乙的活动|虚构数学作业时段/);
   assert.equal((await page.locator('[data-today-task="T01"] [data-plan-time]').innerText()).trim(),'日程 19:00–19:40');ok('today: server schedule, task time on its row',{width});
   if(width===1440)await page.screenshot({path:path.join(out,`web-calendar-${width}.png`),fullPage:false});
   const box=await page.locator(sel('2026-10-26')).boundingBox();assert.ok(box.width>=44&&box.height>=44,JSON.stringify(box));
   for(const b of await page.locator('.grove-tabs button').all()){const r=await b.boundingBox();assert.ok(r.height>=44,'tab height')}
   await page.locator(sel('2026-10-26')).click();await page.waitForSelector(sel('2026-10-26')+'[aria-pressed="true"]');
   await page.locator('#today-courses',{hasText:'16:00–17:00'}).waitFor();
   assert.equal(days.length,1,days.join(' '));ok('one GET /api/day for another day',{width,requests:days.length});
   await page.locator('[data-grove-week="7"]').click();await page.waitForSelector(sel('2026-11-02')+'[aria-pressed="true"]');
   assert.equal(await page.locator('[data-grove-week-title]').innerText(),'11月2日 – 11月8日');
   await page.locator('.grove-list-head [data-grove-day="2026-10-28"]').click();await page.waitForSelector(sel('2026-10-28')+'[aria-pressed="true"]');ok('week step and back to today',{width});
   await page.locator('[data-child-filter="child-2"]').click();await page.locator('#today-courses',{hasText:'乙的英语'}).waitFor();
   assert.doesNotMatch(await page.locator('.grove').innerText(),/虚构钢琴课|虚构加法错题/);ok('child switch keeps one child',{width});
   await page.locator('[data-child-filter="child-1"]').click();await page.waitForSelector('[data-today-task="T01"]');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true,'no sideways scroll on calendar');
   if(width===360)await page.screenshot({path:path.join(out,`web-calendar-${width}.png`),fullPage:true});
   await page.locator('[data-grove-tab="wrong"]').click();const wrong=page.locator(`[data-wrong-record="${info.ids.w1}"]`);await wrong.waitFor();
   assert.match(await wrong.innerText(),/学生原答：-13[\s\S]*原作业：虚构数学作业：有理数加法/);
   assert.equal(await page.locator(`[data-wrong-record="${info.ids.w2}"] [data-grove-wrong-task]`).count(),0);
   assert.match(await page.locator(`[data-wrong-record="${info.ids.w2}"]`).innerText(),/已订正[\s\S]*|未关联原作业/);
   const lone=page.locator(`[data-wrong-record="${info.ids.w2}"]`);
   for(const b of await lone.locator('button').all()){const r=await b.boundingBox();assert.ok(r.height>=44&&r.width>=44,'wrong-book button '+JSON.stringify(r))}
   if(width===360){// below the text the status stays one line and the actions wrap whole, not squeezed into each other
    const rows=await page.evaluate(()=>[...document.querySelectorAll('.grove-wrong')].map(row=>{const one=el=>{const r=document.createRange();r.selectNodeContents(el);return r.getBoundingClientRect().height<parseFloat(getComputedStyle(el).fontSize)*1.8};
     const side=row.querySelector('.grove-wrong-side'),card=row.getBoundingClientRect();return {id:row.dataset.wrongRecord,chip:one(side.querySelector('.grove-chip')),buttons:[...side.querySelectorAll('button')].map(one),
      below:side.getBoundingClientRect().top>=row.querySelector('.grove-wrong-body').getBoundingClientRect().bottom-1,inside:[...side.children].every(c=>{const b=c.getBoundingClientRect();return b.left>=card.left-1&&b.right<=card.right+1})}}));
    assert.ok(rows.length>=3&&rows.some(r=>r.buttons.length===2),JSON.stringify(rows));
    for(const r of rows)assert.deepEqual(r,{id:r.id,chip:true,buttons:r.buttons.map(()=>true),below:true,inside:true},'360 wrong-book status and actions '+JSON.stringify(rows));
    ok('status on one line and actions below the text at 360',{width,rows:rows.length});
   }
   await lone.locator(`[data-grove-wrong-record-open="${info.ids.w2}"]`).click();await page.waitForSelector('#recordDialog[open]');
   assert.equal(await page.locator('#recordForm [name="title"]').inputValue(),'虚构默写错字');await page.keyboard.press('Escape');await page.locator('#recordDialog').waitFor({state:'hidden'});
   ok('wrong record without a task opens its own record',{width});
   const w3=page.locator(`[data-wrong-record="${info.ids.w3}"]`);
   if(width===1440){
    assert.match(await w3.innerText(),/未关联原作业[\s\S]*待订正/);
    await w3.locator(`[data-grove-wrong-correct="${info.ids.w3}"]`).click();await page.waitForSelector('#recordDialog[open]');
    assert.match(await page.locator('#relationTitle').innerText(),/虚构关联未诊断错题/);assert.equal(await page.locator('#recordForm [name="followup_kind"]').inputValue(),'订正');
    await page.locator('#recordForm [name="note"]').fill('虚构：已改正为 5');await page.locator('#recordForm button[type="submit"]').click();await page.locator('#recordDialog').waitFor({state:'hidden',timeout:15000});
    await page.reload();await page.waitForSelector('.grove-tabs');await page.locator('[data-grove-tab="wrong"]').click();await w3.waitFor();
   }
   assert.match(await w3.innerText(),/已订正/);ok('correction saved once through the record entry and read again on a new page',{width});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true,'no sideways scroll on wrong book');
   await page.screenshot({path:path.join(out,`web-wrongbook-${width}.png`),fullPage:width===360});ok('wrong book with original task',{width});
   await page.locator('[data-grove-tab="learning"]').click();const card=page.locator(`[data-learning-record="${info.ids.w1}"]`);await card.waitFor();
   const text=await card.innerText();
   for(const want of ['历史 '+T,'知识点 '+T,T+' · 2026-10-28 · 答了2题，其中1题看过说明','有帮助，不算独立','2026-10-29 · 独立作答 · 对 · 孩子原答 -3','不等于掌握'])assert.ok(text.includes(want),want+' in '+text);
   assert.equal(await card.locator('[data-topic-state="linked"]').count(),0,'a diagnosed topic is not repeated by its link');
   const linked=page.locator(`[data-learning-record="${info.ids.w3}"]`),ltext=await linked.innerText();
   for(const want of ['已关联 '+T+' · 待诊断','已关联知识点',T+' · 2026-10-29 · 家长确认关联，待诊断','关联不等于掌握'])assert.ok(ltext.includes(want),want+' in '+ltext);
   assert.equal(await linked.locator('[data-topic-state="diagnosed"]').count(),0);assert.doesNotMatch(ltext,/答了|新题再试/);
   await linked.scrollIntoViewIfNeeded();await linked.screenshot({path:path.join(out,`web-learning-linked-${width}.png`)});ok('linked topic by name, pending diagnosis',{width,topic:T});
   assert.match(await page.locator('[data-learning-subject="数学"] .grove-course').innerText(),/虚构课堂：有理数加法[\s\S]*出处：家长转述/);
   assert.doesNotMatch(await page.locator('.grove').innerText(),/%|已掌握/);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true,'no sideways scroll on learning');
   await page.screenshot({path:path.join(out,`web-learning-${width}.png`),fullPage:width===360});ok('learning evidence and course record apart',{width});
   await page.locator(`[data-learning-task="${info.ids.w1}"]`).click();await page.waitForSelector('dialog[open]');
   assert.match(await page.locator('dialog[open]').innerText(),/虚构数学作业：有理数加法/);ok('back to the original task',{width});
   await page.keyboard.press('Escape');await page.close();
  }
  report.passed=true;
 }catch(e){report.passed=false;report.error=String(e.stack||e).slice(0,3000);process.exitCode=1}
 finally{await browser.close();server.kill('SIGINT');fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(report,null,1));console.log(JSON.stringify(report).slice(0,2500))}
})();
