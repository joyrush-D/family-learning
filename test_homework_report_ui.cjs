// Disposable synthetic family only. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON and HOMEWORK_UI_PROOF_DIR; no real accounts, model, or device calls.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=12000){const until=Date.now()+timeout;while(Date.now()<until){if(await check())return;await delay(50)}throw Error('Timed out: '+label)}
async function server(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 // Exercise real HTTP/storage in demo.py's temporary directory with a synthetic model.
 const launch=`import app, runpy, sys, json
app.family_llm.configuration=lambda *a,**k:('https://example.invalid','synthetic')
def model(messages,schema,name,*args,**kwargs):
    if name!='family_homework_draft': raise AssertionError('Only synthetic report model allowed')
    raw=json.loads(messages[-1]['content'][0]['text'])
    if not raw.get('explanation'): return dict(items=[],uncertainties=['小练3含义不明确，请补充孩子解释'])
    return dict(items=[dict(title='数学：完成小练习册第3页',subject='数学',goal='完成第3页',excerpt='数小练3'),dict(title='语文：朗读第二段',subject='语文',goal='朗读第二段',excerpt='语读第二段')],uncertainties=[])
app.family_llm._chat_json=model
app.family_llm.transcribe_audio=lambda *a,**k:'虚构听写原话：语文朗读第二段'
sys.argv=['demo.py','--port',sys.argv[1]]
runpy.run_path('demo.py',run_name='__main__')`;
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',launch,String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let err='';child.stdout.resume();child.stderr.on('data',b=>err+=String(b));
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(child.exitCode!==null||child.signalCode!==null)return;const end=once(child,'exit');child.kill('SIGINT');await Promise.race([end,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await end}};
 try{await eventually(async()=>{if(child.exitCode!==null)throw Error(err||'Demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'synthetic server');return{url,stop}}catch(e){await stop();throw e}
}
const fs=require('node:fs/promises'),path=require('node:path');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXioAAAAASUVORK5CYII=','base64');
function wav(){const b=Buffer.alloc(44+3200);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(3200,40);return b}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('dialog[open]').evaluateAll(xs=>xs.some(x=>x.scrollWidth>x.clientWidth)),false)}
async function proof(p,name){if(process.env.HOMEWORK_UI_PROOF_DIR){await fs.mkdir(process.env.HOMEWORK_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.HOMEWORK_UI_PROOF_DIR,name+'.png')})}}
async function openParent(p,url){await p.goto(url);await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="study"]').click();await p.locator('[data-study-ready]').waitFor();}
(async()=>{
 let host,browser;const checks=[];
 try{
  host=await server();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const race=await browser.newPage();await race.goto(host.url);
  await race.evaluate(async()=>{
   const old=window.MediaRecorder,original=navigator.mediaDevices.getUserMedia,waiters=[],recorders=[];
   navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>waiters.push(resolve));
   window.MediaRecorder=class{static isTypeSupported(){return true}constructor(stream){this.stream=stream;this.mimeType='audio/webm';recorders.push(this)}start(){this.state='recording'}stop(){this.state='inactive';this.onstop?.()}};
   const options=()=>({key:'synthetic-race',child_name:'示例',day:'2026-09-13',fileURL:()=>'',upload:()=>Promise.reject(Error('unused'))}),tick=()=>new Promise(r=>setTimeout(r,0));
   const makeStream=()=>{const track={stopped:false,stop(){this.stopped=true}};return{track,getTracks:()=>[track]}};
   try{
    FamilyHomework.open(options());document.querySelector('[data-homework-record]').click();FamilyHomework.clear();
    FamilyHomework.open(options());document.querySelector('[data-homework-record]').click();const stale=makeStream(),active=makeStream();waiters[1](active);await tick();waiters[0](stale);await tick();
    if(!stale.track.stopped||active.track.stopped)throw Error('Late permission crossed capture identity');
    const prior=recorders[0];FamilyHomework.clear();FamilyHomework.open(options());document.querySelector('[data-homework-record]').click();const next=makeStream();waiters[2](next);await tick();await prior.onstop();
    if(next.track.stopped||document.querySelector('[data-homework-record]').textContent!=='结束录音')throw Error('Old stop cleared current recorder');
   }finally{FamilyHomework.clear();window.MediaRecorder=old;navigator.mediaDevices.getUserMedia=original}
  });await race.close();checks.push({captureIdentity:true,lateMicrophonePermission:true,lateRecorderStop:true,syntheticDevice:true});
  const initial=await(await fetch(host.url+'api/state')).json(),who=initial.children[0],other=initial.children[1],day=initial.today;
  const read=async()=>await(await fetch(host.url+'api/state')).json();
  const post=async(route,body)=>{const r=await fetch(host.url+'api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':initial.token},body:JSON.stringify(body)});const result=await r.json();assert.ok(r.ok,JSON.stringify(result));return result};
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
   try{
    await p.goto(host.url);await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="settings"]').click();await p.locator('[data-child-access]').first().waitFor();await fit(p);await proof(p,'settings-entry-'+width);
    await openParent(p,host.url);await p.locator('[data-homework-capture]').click();const d=p.locator('#homeworkInputDialog');
    if(width===360)await p.evaluate(()=>Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true}));await d.locator('[name="text"]').fill('虚构登记 '+width+'：数小练3；语读第二段');
    await p.route('**/api/upload',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构上传失败'})}));
    await d.locator('[data-homework-files]').first().setInputFiles({name:'synthetic-notebook.png',mimeType:'image/png',buffer:png});await d.locator('[data-homework-retry-file]').waitFor();assert.match(await d.innerText(),/虚构上传失败/);await p.unroute('**/api/upload');await d.locator('[data-homework-retry-file]').click();await eventually(async()=>!await d.locator('[data-homework-retry-file]').count(),'upload retry');
    await d.locator('[data-homework-draft]').click();await d.locator('.homework-uncertainties').waitFor();assert.equal(await d.locator('[data-homework-item]').count(),0,'ambiguous abbreviation does not create an assignment');
    await d.locator('[name="explanation"]').fill('小练3是小练习册第3页，不是三遍。');
    await p.route('**/api/study/draft',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构整理暂不可用'})}));await d.locator('[data-homework-draft]').click();await eventually(async()=>/虚构整理暂不可用/.test(await d.innerText()),'model error is visible');assert.match(await d.locator('[name="text"]').inputValue(),/数小练3/);await p.unroute('**/api/study/draft');await d.locator('[data-homework-draft]').click();await eventually(async()=>await d.locator('[data-homework-item]').count()===2,'two draft assignments');
    const form=d.locator('[data-homework-item="0"]'),title='数学：虚构登记核对 '+width;await form.locator('[name="title"]').fill(title);await form.locator('[name="goal"]').fill('完成第3页，家长核对题号');await form.locator('[name="reviewed"]').check();await form.locator('[name="reviewed"]').uncheck();await d.locator('[data-homework-close]').click();await p.locator('[data-homework-capture]').click();assert.equal(await form.locator('[name="reviewed"]').isChecked(),false,'unchecked review survives repaint');p.removeAllListeners('dialog');p.once('dialog',q=>q.dismiss());await d.locator('[data-homework-edit-source]').click();assert.equal(await form.locator('[name="title"]').inputValue(),title,'cancel discard preserves edited candidates');p.on('dialog',q=>q.accept());await form.locator('[name="reviewed"]').check();await fit(p);await proof(p,'parent-draft-'+width);
    let lost=false;await p.route('**/api/study/item',async route=>{if(!lost){lost=true;await route.fetch();await route.abort('failed')}else await route.continue()});await form.locator('[type="submit"]').click();await eventually(async()=>lost&&await form.locator('[type="submit"]').isEnabled(),'uncertain save can retry');assert.equal(await form.locator('[name="title"]').isDisabled(),true);await p.unroute('**/api/study/item');await form.locator('[type="submit"]').click();await eventually(async()=>await d.locator('.homework-saved').count()===1,'one saved report');assert.equal((await read()).tasks.filter(t=>t.title===title).length,1);
    await d.locator('[data-homework-close]').click();await p.locator('nav [data-page="home"]').click();await p.locator('[data-query-target^="task:"]').filter({hasText:title}).waitFor();
    await openParent(p,host.url);const saved=p.locator('[data-study-item]').filter({hasText:title});await saved.waitFor();await saved.locator('.study-report summary').click();assert.match(await saved.innerText(),/不是三遍/);assert.equal(await saved.locator('.study-report a').count(),1);await fit(p);await proof(p,'parent-saved-'+width);
    await p.locator('[data-study-child]').selectOption(other.id);await eventually(async()=>await p.locator('[data-study-child]').inputValue()===other.id,'other child selected');await eventually(async()=>!await p.locator('[data-study-item]').filter({hasText:title}).count(),'original report not in sibling');
    assert.deepEqual(errors,[]);checks.push({width,parent:true,ambiguousNeedsExplanation:true,uploadRetry:true,modelFailureRetry:true,lostSaveRetry:true,oneTask:true,todayVisible:true,reopen:true,originalPreserved:true,childIsolation:true});
   }catch(e){await proof(p,'parent-failure-'+width);throw e}finally{await p.close()}
   await post('child-access/study',{child_id:who.id,enabled:true});const invitation=await post('child-access/invite',{child_id:who.id});
   const context=await browser.newContext({viewport:{width,height:900}}),c=await context.newPage(),childErrors=[];c.on('pageerror',e=>childErrors.push(e.message));c.on('dialog',d=>d.accept());
   const parent=await browser.newPage({viewport:{width,height:900}});parent.on('dialog',d=>d.accept());
   try{
    await c.goto(host.url+'child/#invite='+encodeURIComponent(invitation.invite));await c.locator('#study-add').waitFor();await c.locator('#study-report-material').click();const d=c.locator('#homeworkInputDialog');
    await d.locator('[data-homework-files]').first().setInputFiles({name:'synthetic-voice.wav',mimeType:'audio/wav',buffer:wav()});await d.locator('[data-homework-transcribe]').waitFor();await d.locator('[data-homework-transcribe]').click();await d.locator('[data-homework-transcript]').waitFor();assert.equal(await d.locator('[name="text"]').inputValue(),'','transcript is not silently confirmed');await d.locator('[data-homework-transcript]').fill('虚构原话：语读第二段');await d.locator('[data-homework-close]').click();await c.locator('#study-report-material').click();assert.equal(await d.locator('[data-homework-transcript]').inputValue(),'虚构原话：语读第二段','edited transcript survives repaint');await d.locator('[data-homework-use-transcript]').click();await d.locator('[name="explanation"]').fill('我说的是语文课文的第二段。');await d.locator('[data-homework-manual]').click();
    const title='语文：虚构孩子报功课 '+width,form=d.locator('[data-homework-item="0"]');await form.locator('[name="title"]').fill(title);await form.locator('[name="goal"]').fill('朗读课文第二段');await form.locator('[name="reviewed"]').check();await form.locator('[type="submit"]').click();await d.locator('.homework-saved').waitFor();await d.locator('[data-homework-close]').click();
    const card=c.locator('[data-study-item]').filter({hasText:title});await card.waitFor();await card.locator('.study-report summary').click();assert.match(await card.innerText(),/虚构原话/);await fit(c);await proof(c,'child-report-'+width);
    let task=(await read()).tasks.find(t=>t.title===title);assert.ok(task.homework_report.needs_review);assert.notEqual(task.update?.status,'已完成');
    await parent.goto(host.url);const todayCard=parent.locator('[data-query-target="task:'+task.id+'"]');await todayCard.getByRole('button',{name:'核对报来的功课'}).click();const review=parent.locator('[data-study-item="'+task.id+'"]');await review.locator('.study-report summary').click();await review.locator('[data-study-action="confirm_report"]').click();await eventually(async()=>!(await read()).tasks.find(t=>t.id===task.id).homework_report.needs_review,'parent confirmed requirements');
    task=(await read()).tasks.find(t=>t.id===task.id);assert.notEqual(task.update?.status,'已完成','review is not completion');await fit(parent);await proof(parent,'parent-reviewed-'+width);
    await c.reload();await c.locator('#study-add').waitFor();const reopened=c.locator('[data-study-item="'+task.id+'"]');await reopened.locator('.study-report summary').click();assert.match(await reopened.innerText(),/家长已核对要求/);assert.equal(await reopened.locator('.study-report a').count(),1);
    await c.locator('#study-report-material').click();await d.locator('[name="text"]').fill('虚构尚未保存的原话');let releaseDraft,held=false;const gate=new Promise(r=>releaseDraft=r);await c.route('**/child/api/study/draft',async route=>{held=true;await gate;await route.continue()});await d.locator('[data-homework-draft]').click();await eventually(()=>held,'draft in flight before revoke');await post('child-access/study',{child_id:who.id,enabled:false});await c.evaluate(()=>document.getElementById('refresh').click());await c.locator('#child-study').waitFor({state:'hidden'});assert.equal(await c.locator('#homeworkInputDialog').evaluate(el=>!el.open&&el.childElementCount===0),true,'revoke clears existing capture draft');const deniedDraft=c.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/child/api/study/draft'));releaseDraft();assert.equal((await deniedDraft).status(),403);await c.unroute('**/child/api/study/draft');const cs=await(await context.request.get(host.url+'child/api/state')).json();const denied=await context.request.post(host.url+'child/api/study/draft',{headers:{'X-Child-CSRF':cs.csrf},data:{day,text:'虚构撤销后尝试',explanation:'',attachments:[]}});assert.equal(denied.status(),403);
    assert.deepEqual(childErrors,[]);checks.push({width,child:true,audioOriginal:true,transcriptReviewed:true,manualWithoutModel:true,parentReviewFromToday:true,reviewIsNotCompletion:true,reopen:true,accessRevoked:true});
   }catch(e){await proof(c,'child-failure-'+width);await proof(parent,'review-failure-'+width);throw e}finally{await context.close();await parent.close()}
  }
  const result={passed:checks.length,syntheticOnly:true,realPhone:false,realModels:false,checks};if(process.env.HOMEWORK_UI_PROOF_DIR)await fs.writeFile(path.join(process.env.HOMEWORK_UI_PROOF_DIR,'passed.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{await browser?.close();await host?.stop()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
