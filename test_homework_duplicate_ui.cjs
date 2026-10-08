// Synthetic loopback demo only. No household data, real model, printer or external requests.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON,
// HOMEWORK_DUPLICATE_PROOF_DIR (screenshots/result are written only when supplied by the caller).
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(fn,label){for(let n=0;n<250;n++){if(await fn())return;await delay(40)}throw Error('Timed out: '+label)}
async function fit(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no page overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
 assert.equal(await page.locator('iframe').count(),0,'no iframe');
}
async function proof(page,name){
 if(!process.env.HOMEWORK_DUPLICATE_PROOF_DIR)return;
 const fs=require('node:fs/promises'),path=require('node:path');
 await fs.mkdir(process.env.HOMEWORK_DUPLICATE_PROOF_DIR,{recursive:true});
 await page.screenshot({path:path.join(process.env.HOMEWORK_DUPLICATE_PROOF_DIR,name+'.png'),fullPage:true});
}
const fixture=String.raw`
import runpy,sys,copy,json,tempfile,os
bootstrap=tempfile.TemporaryDirectory(prefix='synthetic-duplicate-bootstrap-')
os.environ['FAMILY_DATA']=bootstrap.name
import app
calls=[];responses=[]
validator=app.family_llm.homework_reference_draft
def question(label,judgment,answer='5',student='5',text='2+3=?'):
 return dict(label=label,question=text,student_answer=student,answer='教师参考：'+answer,judgment=judgment,
             question_kind='objective',error_reason='作答与教师参考不同。' if judgment=='incorrect' else '',possible_cause='',steps='',uncertainty='')
variants=[
 dict(items=[question('虚构甲卷第1题','correct'),question('虚构甲卷第1题','incorrect',student='4')],coverage='仅本次原件。'),
 dict(items=[question('','correct'),question('','incorrect',student='4')],coverage='仅本次原件。'),
 dict(items=[question('虚构甲卷第1题','correct'),question('虚构乙卷第1题','incorrect',answer='4',student='3',text='6-2=?')],coverage='仅虚构甲卷与乙卷各第1题；其他题未检查。')]
def model(messages,schema,name,timeout,**kwargs):
 assert app.DATA.name.startswith('family-demo-') and name=='family_homework_reference'
 assert app.family_llm.homework_reference_draft is validator
 content=messages[-1]['content'];texts=[p['text'] for p in content if p.get('type')=='text']
 assert sum(p.get('type')=='image_url' for p in content)==1
 assert any('教师参考原文' in text and '甲卷第1题：5' in text and '乙卷第1题：4' in text for text in texts)
 assert any('原作答家长说明' in text and '最终作答5、3' in text for text in texts)
 assert len(calls)<3,'only three explicit checks are allowed'
 raw=copy.deepcopy(variants[len(calls)]);calls.append(dict(raw=raw,original=copy.deepcopy(raw)))
 return raw
app.family_llm._chat_json=model
reply=app.Handler.reply
def observe_reply(self,code,body,*args,**kwargs):
 if self.path=='/api/print/homework/draft':responses.append(dict(status=code,body=copy.deepcopy(body)))
 return reply(self,code,body,*args,**kwargs)
app.Handler.reply=observe_reply
get=app.Handler.do_GET
def fixture_get(self):
 if self.path!='/__fixture/duplicate':return get(self)
 assert app.DATA.name.startswith('family-demo-') and app.family_llm.homework_reference_draft is validator
 assert all(call['raw']==call['original'] for call in calls),'the real validator must preserve raw model replies'
 with app.connect_read_only() as c:
  tables={}
  for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
   name=row['name'];escaped=name.replace('"','""')
   rows=[{k:(v.hex() if isinstance(v,bytes) else v) for k,v in dict(r).items()} for r in c.execute('SELECT * FROM "'+escaped+'"')]
   tables[name]=sorted(rows,key=lambda r:json.dumps(r,sort_keys=True))
 return self.reply(200,dict(synthetic_only=True,real_model_calls=0,shared_validator=True,raw_unchanged=True,
                          calls=calls,responses=responses,rejected=sum(r['status']==503 for r in responses),
                          valid=sum(r['status']==200 for r in responses),tables=tables))
app.Handler.do_GET=fixture_get
sys.argv=['demo.py','--port',sys.argv[1]]
try:runpy.run_path('demo.py',run_name='__main__')
finally:bootstrap.cleanup()
`;
async function startServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');
 const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture,String(port)],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});
 let error,stderr='';proc.on('error',e=>error=e);proc.stderr.on('data',s=>stderr=(stderr+s).slice(-12000));
 const stop=async()=>{
  if(error||proc.exitCode!==null||proc.signalCode!==null)return;
  const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);
  if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await Promise.race([done,delay(2500)])}
 };
 const url='http://127.0.0.1:'+port+'/';
 try{await eventually(async()=>{if(error)throw error;if(proc.exitCode!==null)throw Error('Demo exited: '+stderr);try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo startup');return {url,stop}}
 catch(e){await stop();throw e}
}
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC','base64');
(async()=>{
 let browser,server,page;const results=[];
 try{
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440]){
   server=await startServer();const read=async path=>{const r=await fetch(server.url+path);assert.equal(r.status,200);return r.json()},state=()=>read('api/state'),audit=()=>read('__fixture/duplicate');
   const errors=[],foreign=[],forbidden=[],posts=[],checkBodies=[],checkResponses=[];
   page=await browser.newPage({viewport:{width,height:850}});page.setDefaultTimeout(10000);
   page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==new URL(server.url).origin){foreign.push(request.url());return route.abort()}
    if(request.method()==='POST'&&url.pathname.startsWith('/api/print/')&&url.pathname!=='/api/print/homework/draft'){forbidden.push(url.pathname);return route.abort()}
    await route.continue();
   });
   await page.route('**/api/print/homework/draft',async route=>{
    checkBodies.push(route.request().postDataJSON());const response=await route.fetch();
    checkResponses.push({status:response.status(),body:await response.json()});await route.fulfill({response});
   });
   await page.goto(server.url,{waitUntil:'load'});await page.locator('[data-homework-new]').first().waitFor();
   const title='虚构两卷题号核对 '+width;await page.locator('[data-homework-new]').first().click();
   const entry=page.locator('#homeworkInputDialog'),item=entry.locator('[data-homework-item="0"]');
   await item.locator('[name=title]').fill(title);await item.locator('[name=goal]').fill('按明确卷别分别核对，完成状态由家长另行确认。');
   await item.locator('[type=submit]').click();await entry.locator('.homework-saved').waitFor();await entry.locator('[data-homework-close]').click();
   let value=await state();const task=value.tasks.find(t=>t.title===title),child=task.child;assert(task);
   await page.locator('[data-task="'+task.id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();
   const note='虚构甲卷与乙卷各第1题，最终作答5、3；仅核这两题。',teacher='synthetic-duplicate-teacher-'+width+'.txt';
   await page.locator('#taskForm [name=note]').fill(note);
   await page.locator('#cameraInput').setInputFiles({name:'synthetic-duplicate-answer-'+width+'.png',mimeType:'image/png',buffer:png});await page.locator('#pendingUploads img').waitFor();
   await page.locator('#fileInput').setInputFiles({name:teacher,mimeType:'text/plain',buffer:Buffer.from('虚构甲卷第1题：5。\n虚构乙卷第1题：4。\n')});await page.locator('#pendingUploads').getByRole('link',{name:teacher,exact:true}).waitFor();
   await page.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'original answer and teacher saved');
   value=await state();const original=value.records.find(r=>r.source==='事项:'+task.id),before=value;
   assert.equal(original.note,note);assert.equal(original.child,child);assert.equal(original.attachments.length,2);
   const files=original.attachments.map(id=>value.uploads.find(a=>a.id===id)),photo=files.find(a=>a.mime==='image/png'),reference=files.find(a=>a.name===teacher);assert(photo&&reference);
   const panel=page.locator('[data-homework-review="'+original.id+'"]');
   if(!await panel.locator(':scope > details').evaluate(e=>e.open))await panel.locator(':scope > details > summary').click();
   const photoRow=panel.locator('[data-review-source="'+photo.id+'"]'),referenceRow=panel.locator('[data-review-source="'+reference.id+'"]');
   await photoRow.locator('[data-homework-review-photo]').check();await referenceRow.locator('[data-homework-review-photo]').check();assert.equal(await referenceRow.locator('[data-homework-review-role]').inputValue(),'reference');
   const baseline=await audit(),run=panel.locator('[data-homework-review-run]');
   for(let attempt=1;attempt<=2;attempt++){
    await run.click();await eventually(async()=>checkResponses.length===attempt&&/重复/.test(await panel.locator('[data-homework-review-status]').innerText())&&await run.isEnabled(),'real duplicate refusal '+attempt);
    assert.equal(checkResponses[attempt-1].status,503);assert.match(checkResponses[attempt-1].body.error,/重复/);assert.equal(checkResponses[attempt-1].body.draft,undefined);
    assert.equal(await panel.locator('.homework-question,[data-homework-review-result] textarea,[data-homework-review-apply]').count(),0,'refusal exposes no per-question result or adoption');
    assert.equal(await photoRow.locator('[data-homework-review-photo]').isChecked(),true);assert.equal(await referenceRow.locator('[data-homework-review-photo]').isChecked(),true);assert.equal(await referenceRow.locator('[data-homework-review-role]').inputValue(),'reference');
    assert.equal(await page.locator('#taskForm [name=note]').inputValue(),'');const current=await state();assert.deepEqual(current.records,before.records);assert.deepEqual(current.uploads,before.uploads);assert.deepEqual(current.tasks,before.tasks);
    const evidence=await audit();assert.deepEqual(evidence.tables,baseline.tables,'real 503 preserves every SQLite row');assert.equal(evidence.calls.length,attempt);assert.equal(evidence.rejected,attempt);assert.equal(evidence.valid,0);assert.equal(evidence.raw_unchanged,true);
    await fit(page);await proof(page,'duplicate-refusal-'+attempt+'-'+width);
   }
   assert.equal(checkBodies[0].purpose,'review');assert.equal(checkBodies[0].task_id,task.id);assert.equal(checkBodies[0].record_id,original.id);assert.equal(checkBodies[0].expected_created,original.created);
   assert.deepEqual(checkBodies[0].question_sources,[{type:'upload',id:photo.id}]);assert.deepEqual(checkBodies[0].reference_sources,[{type:'upload',id:reference.id}]);assert.deepEqual(checkBodies[0].previous_sources,[]);
   assert.deepEqual(checkBodies[1],checkBodies[0],'explicit retry retains identical selection and answer version');
   await run.click();await panel.locator('.homework-question').first().waitFor();assert.equal(checkResponses.length,3);assert.deepEqual(checkBodies[2],checkBodies[0]);
   const valid=checkResponses[2];assert.equal(valid.status,200);assert.equal(valid.body.draft.items,2);assert.equal(valid.body.draft.wrong_items,1);assert.equal(valid.body.draft.unknown_items,0);
   assert.deepEqual(valid.body.draft.questions.map(q=>[q.label,q.judgment]),[['虚构甲卷第1题','correct'],['虚构乙卷第1题','incorrect']]);
   assert.deepEqual(await panel.locator('.homework-question h4').allTextContents(),['虚构甲卷第1题 · 与答案一致','虚构乙卷第1题 · 需要订正']);assert.match(await panel.locator('.homework-review-counts').innerText(),/2题 · 1题需订正 · 0题未判定/);
   assert.deepEqual((await audit()).tables,baseline.tables,'valid draft is also read-only');assert.deepEqual((await state()).records,before.records);
   assert.equal(await panel.locator('[data-homework-review-confirm]').isChecked(),false);await fit(page);await proof(page,'distinct-volumes-draft-'+width);
   const text=await panel.locator('[data-homework-review-result] textarea').inputValue();assert.match(text,/与参考一致1题/);
   await panel.locator('[data-homework-review-confirm]').check();await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>await panel.locator('[data-homework-review-result] .homework-review-stage').first().innerText()==='检查意见已填入，尚未保存','parent adopts without saving feedback');assert.match(await panel.locator('[data-homework-review-status]').innerText(),/尚未保存/);assert.equal(await page.locator('#saveTaskFeedback').isEnabled(),true,'the original save button stays available');const adoptedState=await state();assert.deepEqual(adoptedState.tasks,before.tasks,'filling is not task completion');assert.notEqual(adoptedState.tasks.find(t=>t.id===task.id).update?.status,'已完成');
   assert.deepEqual((await state()).records,before.records,'adoption alone creates no feedback');const saveBefore=await audit(),saveBodies=[],saveReplies=[];
   await page.route('**/api/task/feedback',async route=>{
    saveBodies.push(route.request().postDataJSON());if(saveBodies.length===1)return route.fulfill({status:503,json:{error:'虚构反馈零写入503'}});
    const response=await route.fetch();assert.equal(response.status(),200);saveReplies.push(await response.json());
    return saveBodies.length===2?route.fulfill({status:503,json:{error:'虚构反馈已写入但回执丢失'}}):route.fulfill({response});
   });
   const save=page.locator('#saveTaskFeedback');await save.click();await eventually(async()=>/虚构反馈零写入503/.test(await page.locator('#taskError').innerText()),'zero-write save failure');assert.deepEqual((await audit()).tables,saveBefore.tables);
   await save.click();await eventually(async()=>/虚构反馈已写入但回执丢失/.test(await page.locator('#taskError').innerText()),'lost receipt after actual save');assert.equal((await state()).records.length,before.records.length+1);
   await save.click();await eventually(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'same numbered save retry');await page.unroute('**/api/task/feedback');
   assert.equal(saveBodies.length,3);assert.deepEqual(saveBodies[1],saveBodies[0]);assert.deepEqual(saveBodies[2],saveBodies[0]);assert.ok(saveBodies[0].request_key);assert.equal(saveReplies[1].replayed,true);assert.equal(saveReplies[1].record_id,saveReplies[0].record_id);
   value=await state();const saved=value.records.find(r=>r.id===saveReplies[1].record_id);assert.equal(saved.related_record_id,original.id);assert.equal(saved.followup_kind,'作业检查');assert.equal(saved.child,child);assert.equal(saved.source,'事项:'+task.id);
   assert(saved.attachments.includes(photo.id)&&saved.attachments.includes(reference.id));assert.deepEqual(value.records.find(r=>r.id===original.id),original);assert.deepEqual(value.tasks,before.tasks);assert.equal(value.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===task.id).length,0);assert.equal(value.records.filter(r=>r.source==='事项:'+task.id).length,2);
   for(const source of [photo,reference])assert.deepEqual(value.uploads.find(a=>a.id===source.id),source);const savedTables=(await audit()).tables;
   await page.locator('#taskDialog [data-close=taskDialog]').click();await page.reload({waitUntil:'load'});await page.locator('[data-task="'+task.id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();
   const savedText=page.locator('[data-saved-homework-review="'+saved.id+'"] [data-saved-review-text]');await eventually(async()=>await savedText.textContent()===text,'saved check text reopens exactly');
   assert.equal(await page.locator('#taskForm [name=id]').inputValue(),task.id);assert.equal(await page.locator('#taskForm [name=status]').inputValue(),'待跟进');assert.equal(await page.locator('[data-feedback-kind=answer] > .upload-item img').isVisible(),true);assert.equal(await page.locator('[data-homework-review]').count(),1);
   const reopened=await state();assert.deepEqual(reopened.records,value.records);assert.deepEqual(reopened.uploads,value.uploads);assert.deepEqual(reopened.tasks,before.tasks);assert.deepEqual((await audit()).tables,savedTables,'reopening writes no SQLite row');
   const final=await audit();assert.equal(final.calls.length,3);assert.equal(final.rejected,2);assert.equal(final.valid,1);assert.equal(final.raw_unchanged,true);assert.equal(final.shared_validator,true);assert.equal(final.real_model_calls,0);assert.deepEqual(final.responses,checkResponses);
   assert.deepEqual(errors,[]);assert.deepEqual(foreign,[]);assert.deepEqual(forbidden,[]);assert.deepEqual(posts,['/api/study/item','/api/upload','/api/upload','/api/task/feedback','/api/print/homework/draft','/api/print/homework/draft','/api/print/homework/draft','/api/upload','/api/task/feedback','/api/task/feedback','/api/task/feedback']);await fit(page);await proof(page,'saved-check-reopened-'+width);
   results.push({width,synthetic_only:true,model_calls:0,checks:3,rejected:2,valid:1,raw_unchanged:true,same_number_save_retry:true,all_rows_preserved_on_rejection:true,task_id:task.id,original_record_id:original.id,check_record_id:saved.id});
   await page.close();page=null;await server.stop();server=null;
  }
  if(process.env.HOMEWORK_DUPLICATE_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_DUPLICATE_PROOF_DIR,'result.json'),JSON.stringify(results,null,2)+'\n')}
  console.log(JSON.stringify(results,null,2));
 }catch(error){if(page)try{await proof(page,'failure-'+page.viewportSize().width)}catch{}throw error}
 finally{if(page)await Promise.race([page.close().catch(()=>{}),delay(3000)]);if(server)await server.stop();if(browser)await Promise.race([browser.close().catch(()=>{}),delay(5000)])}
})().catch(error=>{console.error(error);process.exitCode=1});
