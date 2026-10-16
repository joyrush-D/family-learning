// Disposable synthetic family only. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON and ORAL_DATES_UI_PROOF_DIR.
// Explicit teacher complete/handback days through the real shared parent/child manual capture; any model call fails the run.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const fs=require('node:fs/promises'),path=require('node:path');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=12000){const until=Date.now()+timeout;while(Date.now()<until){if(await check())return;await delay(50)}throw Error('Timed out: '+label)}
async function server(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 const launch=`import app, runpy, sys
app.family_llm.configuration=lambda *a,**k:('https://example.invalid','synthetic')
def model(*a,**k): raise AssertionError('manual teacher days must not call a model')
app.family_llm._chat_json=model
app.family_llm.transcribe_audio=model
sys.argv=['demo.py','--port',sys.argv[1]]
runpy.run_path('demo.py',run_name='__main__')`;
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',launch,String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let err='';child.stdout.resume();child.stderr.on('data',b=>err+=String(b));
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(child.exitCode!==null||child.signalCode!==null)return;const end=once(child,'exit');child.kill('SIGINT');await Promise.race([end,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await end}};
 try{await eventually(async()=>{if(child.exitCode!==null)throw Error(err||'Demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'synthetic server');return{url,stop,err:()=>err}}catch(e){await stop();throw e}
}
const shift=(day,n)=>{const d=new Date(day+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)};
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal spill');assert.equal(await p.locator('dialog[open]').evaluateAll(xs=>xs.some(x=>x.scrollWidth>x.clientWidth)),false,'dialog fits')}
async function proof(p,name){if(process.env.ORAL_DATES_UI_PROOF_DIR){await fs.mkdir(process.env.ORAL_DATES_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.ORAL_DATES_UI_PROOF_DIR,name+'.png'),fullPage:false})}}
// One 503 before any write, then one committed save whose receipt is lost; both retries resend the same key and payload.
async function saveThroughFailures(page,dialog,form,count){
 const bodies=[];let phase=0;
 await page.route('**/api/study/item',async r=>{bodies.push(r.request().postData());phase++;
  if(phase===1)return r.fulfill({status:503,json:{error:'虚构首次保存不可用'}});
  if(phase===2){await r.fetch();return r.fulfill({status:503,json:{error:'虚构保存回执丢失'}})}
  return r.continue()});
 await form.locator('[type="submit"]').click();await eventually(async()=>/首次保存不可用/.test(await dialog.innerText()),'first 503 shown');
 assert.equal(await count(),0,'503 before write leaves zero business writes');
 await form.locator('[type="submit"]').click();await eventually(async()=>/回执丢失/.test(await dialog.innerText()),'lost receipt shown');
 assert.equal(await count(),1,'committed once before the lost receipt');
 await form.locator('[type="submit"]').click();await dialog.locator('.homework-saved').waitFor();await page.unroute('**/api/study/item');
 assert.equal(bodies.length,3);assert.equal(new Set(bodies).size,1,'same request key and original payload on every retry');assert.equal(await count(),1,'one task only');
 return JSON.parse(bodies[0]);
}
(async()=>{
 let host,browser;const checks=[];
 try{
  host=await server();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const initial=await(await fetch(host.url+'api/state')).json(),who=initial.children[0],other=initial.children[1],day=initial.today;
  const post=async(route,body)=>{const r=await fetch(host.url+'api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':initial.token},body:JSON.stringify(body)});const result=await r.json();assert.ok(r.ok,JSON.stringify(result));return result};
  const study=async(id=who.id)=>(await(await fetch(host.url+'api/study?'+new URLSearchParams({child_id:id,day}))).json()).items;
  const titled=title=>async()=>(await study()).filter(i=>i.title===title).length;
  await post('child-access/study',{child_id:who.id,enabled:true});
  for(const width of [360,1440]){
   const complete=shift(day,2),handback=shift(day,width===360?5:6),title='语文：虚构小练3 '+width,words='语小练3 周'+width+'前做完，之后交';
   const p=await browser.newPage({viewport:{width,height:900}}),errors=[];let drafts=0;p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
   await p.route('**/api/study/draft',r=>{drafts++;return r.continue()});
   try{
    await p.goto(host.url);await p.locator('[data-homework-new="'+who.id+'"]').click();
    const d=p.locator('#homeworkInputDialog'),form=d.locator('[data-homework-item="0"]');
    await form.locator('[name="title"]').fill(title);await form.locator('[name="goal"]').fill('小练习册第3页全部完成');
    await form.locator('[name="complete_on"]').fill(complete);await form.locator('[name="handback_on"]').fill(handback);
    await d.locator('[data-homework-original] > summary').click();await d.locator('[name="text"]').fill(words);
    assert.match(await d.innerText(),/老师要求完成日/);assert.match(await d.innerText(),/老师要求交回日/);await fit(p);await proof(p,'parent-form-'+width);
    // Close and reopen keeps the unsaved explicit days with the title and standard.
    await d.locator('[data-homework-close]').click();await p.locator('[data-homework-new="'+who.id+'"]').click();
    assert.equal(await form.locator('[name="complete_on"]').inputValue(),complete);assert.equal(await form.locator('[name="handback_on"]').inputValue(),handback);
    assert.equal(await form.locator('[name="title"]').inputValue(),title);
    const sent=await saveThroughFailures(p,d,form,titled(title));
    assert.deepEqual([sent.report.complete_on,sent.report.handback_on,sent.report.text,sent.day],[complete,handback,words,day]);
    assert.match(await d.locator('.homework-saved').innerText(),new RegExp('老师完成日：'+complete+' · 交回日：'+handback));await fit(p);await proof(p,'parent-saved-'+width);
    const saved=(await study()).find(i=>i.title===title);assert.deepEqual([saved.day,saved.report.complete_on,saved.report.handback_on,saved.report.text,saved.report.goal],[day,complete,handback,words,'小练习册第3页全部完成']);
    // Reload: Today reads the same saved days with teacher labels, never as the recording day.
    await p.reload();await p.locator('body').getByText(title).first().waitFor();
    const state=await(await fetch(host.url+'api/state')).json(),task=state.tasks.find(t=>t.title===title);
    assert.deepEqual([task.agenda.complete_on,task.agenda.due_on,task.agenda.due_kind,task.agenda.scheduled_on],[complete,handback,'handback',day]);
    const other_items=await study(other.id);assert.equal(other_items.filter(i=>i.title===title).length,0,'current child only');
    await proof(p,'parent-today-reopen-'+width);
    if(width===1440){
     // The parent corrects one teacher day and clears the other on the same saved item through the existing edit form.
     const later=shift(day,9);await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="study"]').click();await p.locator('[data-study-ready]').waitFor();
     const row=p.locator('[data-study-item]').filter({hasText:title});await row.locator('[data-study-editor="item"]').click();const edit=p.locator('[data-study-form="item"]');
     assert.equal(await edit.locator('[name="complete_on"]').inputValue(),complete);assert.equal(await edit.locator('[name="handback_on"]').inputValue(),handback);
     await edit.locator('[name="handback_on"]').fill(later);await edit.locator('[name="complete_on"]').fill('');await proof(p,'parent-correct-'+width);await edit.locator('[type="submit"]').click();
     await eventually(async()=>(await study()).find(i=>i.title===title).report.handback_on===later,'correction saved');
     const fixed=(await study()).find(i=>i.title===title);
     assert.deepEqual([fixed.id,fixed.report.complete_on,fixed.report.text,fixed.report.date_history.length,fixed.report.date_history[0].handback_on],[saved.id,'',words,1,handback]);
     const again=(await(await fetch(host.url+'api/state')).json()).tasks.find(t=>t.title===title);
     assert.deepEqual([again.agenda.complete_on,again.agenda.due_on,again.agenda.due_kind,again.agenda.scheduled_on],['',later,'handback',day]);
     assert.equal((await study()).filter(i=>i.title===title).length,1,'same one item after correction');
    }
    assert.equal(drafts,0,'manual flow sends no model request');assert.deepEqual(errors,[]);
    checks.push({width,role:'parent',closeReopenDraft:true,first503ZeroWrite:true,lostReceiptSameKey:true,oneTask:true,reloadSameDays:true,agenda:{complete_on:complete,due_on:handback,due_kind:'handback',scheduled_on:day},draftRequests:drafts});
   }catch(e){await proof(p,'parent-failure-'+width);throw e}finally{await p.close()}
   const invitation=await post('child-access/invite',{child_id:who.id});
   const context=await browser.newContext({viewport:{width,height:900}}),c=await context.newPage(),childErrors=[];let childDrafts=0;c.on('pageerror',e=>childErrors.push(e.message));c.on('dialog',d=>d.accept());
   await c.route('**/api/child/study/draft',r=>{childDrafts++;return r.continue()});
   try{
    const childTitle='数学：虚构孩子口算 '+width,childHandback=shift(day,3);
    await c.goto(host.url+'child/#invite='+encodeURIComponent(invitation.invite));await c.locator('#study-add').waitFor();await c.locator('#study-report-material').click();
    const d=c.locator('#homeworkInputDialog');await d.locator('[data-homework-manual]').click();const form=d.locator('[data-homework-item="0"]');
    await form.locator('[name="title"]').fill(childTitle);await form.locator('[name="goal"]').fill('口算本第8页');await form.locator('[name="handback_on"]').fill(childHandback);await form.locator('[name="reviewed"]').check();
    assert.match(await d.innerText(),/老师说哪天交/);await fit(c);await proof(c,'child-form-'+width);
    await d.locator('[data-homework-close]').click();await c.locator('#study-report-material').click();
    assert.equal(await form.locator('[name="handback_on"]').inputValue(),childHandback);assert.equal(await form.locator('[name="complete_on"]').inputValue(),'');
    const sent=await saveThroughFailures(c,d,form,titled(childTitle));
    assert.deepEqual([sent.report.complete_on,sent.report.handback_on,sent.day],['',childHandback,day]);
    assert.match(await d.locator('.homework-saved').innerText(),new RegExp('老师完成日：未填 · 交回日：'+childHandback));await fit(c);await proof(c,'child-saved-'+width);
    await c.reload();await c.locator('#study-add').waitFor();
    const saved=(await study()).find(i=>i.title===childTitle);assert.deepEqual([saved.day,saved.report.complete_on,saved.report.handback_on,saved.report.actor,saved.report.confirmed_at],[day,'',childHandback,'child','']);
    const state=await(await fetch(host.url+'api/state')).json(),task=state.tasks.find(t=>t.title===childTitle);
    assert.deepEqual([task.agenda.complete_on,task.agenda.due_on,task.agenda.due_kind,task.agenda.scheduled_on],['',childHandback,'handback',day]);
    await proof(c,'child-reopen-'+width);assert.equal(childDrafts,0);assert.deepEqual(childErrors,[]);
    checks.push({width,role:'child',closeReopenDraft:true,first503ZeroWrite:true,lostReceiptSameKey:true,oneTask:true,reloadSameDays:true,blankCompleteStaysUnknown:true,notConfirmedOrCompleted:true,draftRequests:childDrafts});
   }catch(e){await proof(c,'child-failure-'+width);throw e}finally{await context.close()}
  }
  console.log(JSON.stringify({browser:browser.version(),checks}));
 }finally{await browser?.close();await host?.stop()}
})().catch(e=>{console.error(e);process.exitCode=1});
