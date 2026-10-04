// Disposable synthetic demo only. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON and RECORD_LINK_UI_PROOF_DIR. No family account or model calls.
const assert=require('node:assert/strict'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises'),{randomUUID}=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function threeAttemptSave(page,path,button,error,success,read){
 const bodies=[],results=[],before=await read();
 await page.route('**'+path,async route=>{
  bodies.push(route.request().postDataJSON());
  if(bodies.length===1)return route.fulfill({status:503,json:{error:'虚构未写入失败'}});
  const response=await route.fetch(),value=await response.json();assert.equal(response.status(),200);results.push(value);
  return bodies.length===2?route.fulfill({status:503,json:{error:'虚构写入成功但回执丢失'}}):route.fulfill({response,json:value});
 });
 try{
  await button.click();await eventually(error,'no-write failure');assert.deepEqual((await read()).records,before.records);
  await button.click();await eventually(error,'lost receipt retained');assert.equal((await read()).records.length,before.records.length+1);
  await button.click();await eventually(success,'same numbered retry saved');
 }finally{await page.unroute('**'+path)}
 assert.equal(bodies.length,3);assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[1],bodies[2]);assert(bodies[0].request_key);
 const id=value=>path==='/api/wrong/save'?value.saved?.[0]?.id:value.record_id??value.id;
 assert(Number.isInteger(id(results[1])));assert.equal(id(results[0]),id(results[1]));assert.equal(path==='/api/wrong/save'?results[1].saved?.[0]?.existing:results[1].replayed,true);
 assert.equal((await read()).records.length,before.records.length+1);return {record_id:id(results[1]),request_key:bodies[0].request_key,bodies};
}
async function demoServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 // Fixed raw goes through the existing validator in the disposable demo; no external model is reachable.
 const setup=`import runpy,sys,copy
import app
raw=dict(items=[dict(label='虚构第1题',question='虚构第1题：拼写表示昨天的英语单词。',student_answer='yestoday',answer='AI自行推导：yesterday',judgment='incorrect',question_kind='objective',error_reason='原图最终作答yestoday与核对拼写yesterday不同。',possible_cause='',steps='先独立回忆拼写，再对照yesterday核对。',uncertainty='')],coverage='仅虚构原图第1题；其余题未检查。',comparison='本轮仅核对原图第1题，未判定其他题或掌握。')
calls=[]
validator=app.family_llm.homework_reference_draft
def mock_chat(messages,schema,name,timeout,**kwargs):
    assert app.DATA.name.startswith('family-demo-') and name=='family_homework_reference'
    content=messages[-1]['content'];texts=[part['text'] for part in content if part.get('type')=='text']
    widths=[width for width in (360,1440) if any('虚构关联作答检查 '+str(width) in text for text in texts)]
    assert len(widths)==1 and sum(part.get('type')=='image_url' for part in content)==1
    width=widths[0];attempt=1+sum(call['width']==width for call in calls)
    entry=dict(width=width,attempt=attempt,failed=attempt==1);calls.append(entry)
    if attempt==1:raise app.family_llm.LLMDraftError('虚构模型暂时失败，请重试')
    assert attempt==2,'the fixed sample must not be called again'
    entry['raw']=copy.deepcopy(raw);return entry['raw']
def traced_validator(*args,**kwargs):
    result=validator(*args,**kwargs)
    assert calls[-1]['raw']==raw
    calls[-1]['validated']=copy.deepcopy(result);return result
app.family_llm._chat_json=mock_chat
app.family_llm.homework_reference_draft=traced_validator
get=app.Handler.do_GET
def fixture_get(self):
    if self.path=='/__fixture/linked-review-validator':
        assert app.DATA.name.startswith('family-demo-')
        return self.reply(200,dict(synthetic_only=True,shared_validator=True,real_model_calls=0,calls=calls))
    return get(self)
app.Handler.do_GET=fixture_get
sys.argv=['demo.py','--port',sys.argv[1]]
runpy.run_path('demo.py',run_name='__main__')`;
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',setup,String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let error='';proc.stdout.resume();proc.stderr.on('data',b=>error+=String(b));proc.on('error',e=>error=e.message);
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{await eventually(async()=>{if(proc.exitCode!==null)throw Error(error||'Demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo');return{url,stop}}catch(e){await stop();throw e}
}
const fs=require('node:fs/promises'),path=require('node:path');(async()=>{let browser,server;const checks=[];try{
 server=await demoServer();const url=server.url;browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 for(const width of [360,1440]){
  const context=await browser.newContext({viewport:{width,height:900}}),p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  const read=async()=>fetch(url+'api/state').then(r=>r.json());let state=await read();const kid=state.children[0].name;
  const post=async(route,body)=>{const r=await fetch(url+route,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(body)});const out=await r.json();assert(r.ok,JSON.stringify(out));return out};
  const task=async(child,title)=>(await post('api/task/new',{request_key:randomUUID(),child,title,box:'inbox',category:'homework',due:state.today,action:'虚构：核对原有材料'})).task;
  const a=await task(kid,'虚构听写甲 '+width),b=await task(kid,'虚构听写乙 '+width),other=await task(state.children[1].name,'另一孩子任务 '+width);
  await post('api/task',{id:a.id,status:'已完成',note:'虚构：已经核对完成'});
  const sheet=await context.newPage();await sheet.setViewportSize({width:560,height:260});
  await sheet.setContent('<html><body style="font:24px sans-serif;background:white;color:black"><h2>SYNTHETIC ANSWER</h2><p>Question 1: Spell the word meaning the day before today.</p><p>Student final answer: yestoday</p></body></html>');
  const raw=await sheet.screenshot();await sheet.close();
  const up=await fetch(url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'X-File-Name':'synthetic-sheet.png'},body:raw}).then(r=>r.json());
  const saved=await post('api/record',{child:kid,day:state.today,category:'学习进展',subject:'英语',title:'虚构独立错题 '+width,note:'虚构原答：yestoday',source:'试卷 / 作业核对',attachments:[up.attachment.id],transcript:'虚构核对转写',transcript_state:'已核对'}),id=saved.record_id;
  state=await read();const before=state.records.find(r=>r.id===id),taskBefore=state.tasks.find(t=>t.id===a.id).update;
  await p.goto(url);await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');
  const openRecord=async()=>{await p.locator('nav [data-page=more]').click();await p.locator('.more-links [data-page=growth]').click();await p.locator('[data-record="'+id+'"]').first().click();await p.locator('#recordDialog[open]').waitFor()};
  await openRecord();const select=p.locator('#recordTaskSelect'),save=p.locator('#saveRecordTaskLink'),status=p.locator('#recordTaskLinkStatus');
  assert.equal(await select.locator('option[value="'+other.id+'"]').count(),0);assert.equal(await select.inputValue(),'');
  await p.locator('#recordForm [name=note]').fill('未保存的家长补充');await select.selectOption(a.id);
  await p.locator('#recordForm [type=submit]').click();assert.match(await p.locator('#recordError').innerText(),/任务选择尚未保存/);assert(await p.locator('#recordDialog').evaluate(x=>x.open));
  const bodies=[];let attempt=0;await p.route('**/api/record/task-link',async r=>{bodies.push(r.request().postDataJSON());if(++attempt===1){await r.fetch();return r.abort('failed')}return r.continue()});
  await save.click();await eventually(async()=>/结果尚未核对/.test(await status.innerText()),'lost reply');assert(await select.isDisabled());assert(await p.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented}));await p.keyboard.press('Escape');assert(await p.locator('#recordDialog').evaluate(x=>x.open));
  await p.locator('#recordForm [type=submit]').click();assert.match(await p.locator('#recordError').innerText(),/任务关联保存结果尚未核对/);
  await save.click();await eventually(async()=>/任务关联已保存/.test(await status.innerText()),'same request retry');assert.deepEqual(bodies[0],bodies[1]);await p.unroute('**/api/record/task-link');
  assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'未保存的家长补充');state=await read();let record=state.records.find(r=>r.id===id);assert.equal(record.note,before.note);assert.equal(record.source,before.source);assert.deepEqual(record.attachments,before.attachments);assert.equal(record.transcript,before.transcript);assert.deepEqual(state.tasks.find(t=>t.id===a.id).update,taskBefore);
  // Another parent changes the link while this form remains open: preserve the local choice and text.
  await post('api/record/task-link',{record_id:id,child:kid,task_id:b.id,expected_linked_at:record.linked_task_at});await select.selectOption('');await save.click();await eventually(async()=>/别处更改/.test(await status.innerText()),'conflict');assert.equal(await select.inputValue(),'');assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'未保存的家长补充');
  await p.locator('#refreshRecordTaskLink').click();await eventually(async()=>/已读取当前关联/.test(await status.innerText()),'refresh link');assert.match(await p.locator('#recordTaskCurrent').innerText(),new RegExp(b.title));assert.equal(await select.inputValue(),'');
  await save.click();await eventually(async()=>/关联已解除/.test(await status.innerText()),'unlink');record=(await read()).records.find(r=>r.id===id);assert.equal(record.linked_task_id,'');assert(record.linked_task_at);
  // Session expiry keeps the chosen target and the ordinary record draft, then explicit retry succeeds.
  await select.selectOption(a.id);await p.route('**/api/record/task-link',r=>r.fulfill({status:401,json:{error:'虚构登录已过期'}}));await save.click();await p.locator('#parentLoginDialog[open]').waitFor();assert.equal(await select.inputValue(),a.id);await p.keyboard.press('Escape');await p.unroute('**/api/record/task-link');await save.click();await eventually(async()=>/任务关联已保存/.test(await status.innerText()),'login retry');
  await p.locator('#recordForm [type=submit]').click();await eventually(()=>p.locator('#recordDialog').evaluate(x=>!x.open),'ordinary content save');await p.reload();await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');await openRecord();assert.equal(await select.inputValue(),a.id);assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'未保存的家长补充');await p.keyboard.press('Escape');
  // Same task shows the original record, image, transcript and provenance; no duplicate or task completion changes.
  const openOriginalTask=async()=>{await p.locator('nav [data-page=home]').click();await p.locator('[data-task-all="homework"]').click();await p.locator('[data-task-box="已完成"]').click();await p.locator('[data-task="'+a.id+'"]').first().click();await p.locator('#taskDialog[open]').waitFor()};
  await openOriginalTask();
  const history=p.locator('#taskFeedbackHistory');assert.match(await history.innerText(),/虚构核对转写/);assert.match(await history.innerText(),/试卷 \/ 作业核对/);assert.equal(await history.locator('img').count(),1);assert.equal(await history.locator('[data-task-feedback-edit]').count(),0);
  assert.equal(await history.locator('[data-homework-review="'+id+'"]').count(),1,'explicitly linked ordinary answer is checkable from the same homework');
  assert.equal(await history.locator('[data-task-wrong-form="'+id+'"]').count(),1,'explicitly linked ordinary answer keeps the wrong-item entry');
  // The same saved ordinary answer uses the real review validator, feedback, wrong-item and correction endpoints.
  // This verifies the linked workflow, not OCR, actual model accuracy or a child's learning result.
  const linkedBefore=await read(),linkedAnswer=linkedBefore.records.find(r=>r.id===id),printIds=linkedBefore.printing.jobs.map(j=>j.id).sort();
  const panel=history.locator('[data-homework-review="'+id+'"]'),instruction='虚构关联作答检查 '+width+'：仅检查原图第1题，保留未检查范围。';
  await panel.locator(':scope > details > summary').click();await panel.locator('[data-review-source="'+up.attachment.id+'"] [data-homework-review-photo]').check();await panel.locator('[data-homework-review-instruction]').fill(instruction);
  const reviewRequests=[],reviewReplies=[];await p.route('**/api/print/homework/draft',async route=>{reviewRequests.push(route.request().postDataJSON());const response=await route.fetch(),out=await response.json();reviewReplies.push({status:response.status(),out});await route.fulfill({response,json:out})});
  await panel.locator('[data-homework-review-run]').click();await eventually(async()=>/虚构模型暂时失败/.test(await panel.locator('[data-homework-review-status]').innerText()),'mock model failure retained');
  assert.equal(await panel.locator('[data-homework-review-instruction]').inputValue(),instruction);assert(await panel.locator('[data-homework-review-photo]').first().isChecked());assert.equal(await panel.locator('[data-homework-review-result] textarea').count(),0);assert.deepEqual((await read()).records,linkedBefore.records);
  const failedValidator=await fetch(url+'__fixture/linked-review-validator').then(r=>r.json());assert(failedValidator.synthetic_only&&failedValidator.shared_validator);assert.equal(failedValidator.real_model_calls,0);assert.equal(failedValidator.calls.filter(c=>c.width===width).length,1,'failed model is not automatically retried');assert.equal(failedValidator.calls.at(-1).failed,true);
  await panel.locator('[data-homework-review-run]').click();await eventually(async()=>/1题 · 1题需订正 · 0题未判定/.test(await panel.locator('[data-homework-review-status]').innerText()),'explicit retry through shared validator');await p.unroute('**/api/print/homework/draft');
  assert.equal(reviewRequests.length,2);assert.deepEqual(reviewRequests[0],reviewRequests[1]);assert.equal(reviewReplies[0].status,503);assert.equal(reviewReplies[1].status,200);
  const reply=reviewReplies[1].out;assert.equal(reviewRequests[1].task_id,a.id);assert.equal(reviewRequests[1].record_id,id);assert.equal(reviewRequests[1].expected_created,linkedAnswer.created);assert.deepEqual(reviewRequests[1].question_sources,[{type:'upload',id:up.attachment.id}]);assert.deepEqual(reviewRequests[1].reference_sources,[]);
  assert.equal(reply.review_basis.record_id,id);assert.equal(reply.review_basis.created,linkedAnswer.created);assert.equal(reply.draft.questions[0].judgment,'incorrect');assert.equal(reply.draft.questions[0].student_answer,'yestoday');assert.equal(reply.draft.questions[0].answer,'AI自行推导：yesterday');assert.equal(reply.draft.questions[0].possible_cause,'');assert.match(reply.draft.coverage,/其余题未检查/);
  const validated=await fetch(url+'__fixture/linked-review-validator').then(r=>r.json());assert.equal(validated.real_model_calls,0);assert.equal(validated.calls.filter(c=>c.width===width).length,2);assert.deepEqual(validated.calls.at(-1).validated,reply.draft);assert.equal(validated.calls.at(-1).raw.items[0].student_answer,'yestoday');assert.match(await panel.locator('.homework-review-questions').innerText(),/需要订正/);
  assert.deepEqual((await read()).records,linkedBefore.records,'the model draft does not create records');
  await panel.locator('[data-homework-review-confirm]').check();await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await panel.innerText()),'linked review staged for explicit feedback save');
  const reviewed=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),read);
  state=await read();const reviewedRecord=state.records.find(r=>r.id===reviewed.record_id);assert.equal(reviewedRecord.related_record_id,id);assert.equal(reviewedRecord.followup_kind,'作业检查');assert.equal(reviewedRecord.source,'事项:'+a.id);assert.equal(reviewed.bodies[0].review_basis.record_id,id);assert.deepEqual(state.records.find(r=>r.id===id),linkedAnswer,'saving a check keeps the ordinary source, created version, words, photo and link');assert.equal(state.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===a.id).length,0,'saved checking opinion does not automatically create a wrong item');
  const wrong=history.locator('[data-task-wrong-form="'+id+'"]');await wrong.locator(':scope > summary').click();await wrong.locator('[data-wrong-field=label]').fill('虚构第1题');await wrong.locator('[data-wrong-field=text]').fill('拼写表示昨天的英语单词。');await wrong.locator('[data-wrong-field=answer]').fill('yestoday');await wrong.locator('[data-wrong-field=correction]').fill('yesterday');
  const wrongSaved=await threeAttemptSave(p,'/api/wrong/save',wrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await wrong.innerText()),async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),read);
  assert.equal(wrongSaved.bodies[0].feedback_record_id,id);assert.equal(wrongSaved.bodies[0].feedback_created,linkedAnswer.created);assert.equal(wrongSaved.bodies[0].feedback_linked_at,linkedAnswer.linked_task_at,'linked ordinary answers carry the exact link decision version');assert.equal(wrongSaved.bodies[0].task_id,a.id);assert.equal(wrongSaved.bodies[0].items[0].attachment,up.attachment.id);
  const wrongCard=history.locator('.task-feedback-record').filter({has:p.locator('[data-record="'+wrongSaved.record_id+'"]')});await wrongCard.locator('[data-followup]').click();await p.locator('#recordDialog[open]').waitFor();
  const correctionForm=p.locator('#recordForm'),correctionNote='虚构关联作答订正 '+width+'：已将yestoday订正为yesterday，独立复测待做。';assert.equal(await correctionForm.locator('[name=followup_kind]').inputValue(),'订正');assert.equal(await correctionForm.locator('[name=related_record_id]').inputValue(),String(wrongSaved.record_id));await correctionForm.locator('[name=note]').fill(correctionNote);
  const correction=await threeAttemptSave(p,'/api/record',correctionForm.locator('[type=submit]'),async()=>/虚构/.test(await p.locator('#recordError').innerText()),async()=>!await p.locator('#recordDialog').evaluate(x=>x.open),read);
  await p.reload();await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');await openOriginalTask();await history.getByText(correctionNote,{exact:false}).waitFor();
  const reopenedReview=history.locator('[data-saved-homework-review="'+reviewed.record_id+'"] [data-saved-review-text]');await eventually(async()=>await reopenedReview.innerText()===reply.draft.text,'linked check reopens unchanged');assert.match(await reopenedReview.innerText(),/yestoday/);assert.match(await reopenedReview.innerText(),/yesterday/);
  state=await read();const wrongRecord=state.records.find(r=>r.id===wrongSaved.record_id),correctionRecord=state.records.find(r=>r.id===correction.record_id);assert.equal(wrongRecord.related_record_id,id);assert.equal(correctionRecord.related_record_id,wrongRecord.id);assert.equal(correctionRecord.followup_kind,'订正');for(const r of [wrongRecord,correctionRecord]){assert.equal(r.child,kid);assert.equal(r.linked_task_id,a.id)}assert.equal(state.records.length,linkedBefore.records.length+3);assert.deepEqual(state.records.find(r=>r.id===id),linkedAnswer);assert.deepEqual(state.tasks.find(t=>t.id===a.id).update,taskBefore);assert.deepEqual(state.printing.jobs.map(j=>j.id).sort(),printIds);
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  if(process.env.RECORD_LINK_UI_PROOF_DIR){await fs.mkdir(process.env.RECORD_LINK_UI_PROOF_DIR,{recursive:true});await fs.writeFile(path.join(process.env.RECORD_LINK_UI_PROOF_DIR,'linked-review-'+width+'.json'),JSON.stringify({scope:'mock raw through real validator and linked original workflow; not actual model or OCR accuracy',requests:reviewRequests,validator:validated.calls.filter(c=>c.width===width),reviewed,wrongSaved,correction,original:state.records.find(r=>r.id===id)},null,2));await p.screenshot({path:path.join(process.env.RECORD_LINK_UI_PROOF_DIR,'linked-review-reopened-'+width+'.png')})}
  // A changed association invalidates a fresh save based on the old link, even though the answer bytes and created version remain unchanged.
  await post('api/record/task-link',{record_id:id,child:kid,task_id:b.id,expected_linked_at:linkedAnswer.linked_task_at});const afterRelink=await read();
  const staleWrong={...wrongSaved.bodies[0],request_key:randomUUID().replaceAll('-','')},staleResponse=await fetch(url+'api/wrong/save',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(staleWrong)}),staleResult=await staleResponse.json();assert.equal(staleResponse.status,409);assert.equal(staleResult.code,'wrong_feedback_changed');assert.deepEqual((await read()).records,afterRelink.records,'stale linked wrong-item save writes nothing');
  const moved=afterRelink.records.find(r=>r.id===id);assert.equal(moved.created,linkedAnswer.created);assert.equal(moved.source,linkedAnswer.source);assert.deepEqual(moved.attachments,linkedAnswer.attachments);await post('api/record/task-link',{record_id:id,child:kid,task_id:a.id,expected_linked_at:moved.linked_task_at});
  await p.reload();await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');await openOriginalTask();
  const callsAfter=await fetch(url+'__fixture/linked-review-validator').then(r=>r.json());assert.equal(callsAfter.calls.filter(c=>c.width===width).length,2,'saving, correction, reopening and stale-link rejection add no model calls');assert.equal(callsAfter.real_model_calls,0);
  await history.locator('[data-record="'+id+'"]').click();assert(await p.locator('#recordDialog').evaluate(x=>x.open));assert.equal(await select.inputValue(),a.id);
  assert.equal(await p.locator('#recordDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  if(process.env.RECORD_LINK_UI_PROOF_DIR){await fs.mkdir(process.env.RECORD_LINK_UI_PROOF_DIR,{recursive:true});await p.locator('#recordTaskLink').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.RECORD_LINK_UI_PROOF_DIR,'record-link-'+width+'.png')})}
  // New task stays inside the same record; no inference from its title, date or note.
  await select.selectOption('');await save.click();await eventually(async()=>/关联已解除/.test(await status.innerText()),'unlink before explicit new task');
  await p.locator('#recordTaskCreate > summary').click();
  const title=p.locator('#recordTaskTitle'),due=p.locator('#recordTaskDue'),create=p.locator('#createRecordTask');
  assert.equal(await title.inputValue(),'');assert.equal(await due.inputValue(),'');assert.equal(await p.locator('#recordTaskCategory').inputValue(),'');
  await create.click();assert.match(await status.innerText(),/请填写新事项标题/);
  const wantedTitle='虚构：两处听写再核对 '+width;await title.fill(wantedTitle);await p.locator('#recordTaskCategory').selectOption('homework');await p.locator('#recordTaskAction').fill('家长明确：先读再写两处');
  await p.locator('#recordForm [name=note]').fill('虚构：这段原记录补充仍未保存');
  await p.locator('#recordForm [type=submit]').click();assert.match(await p.locator('#recordError').innerText(),/新事项草稿尚未保存/);
  // The other parent links first: rejection leaves both drafts, then explicit refresh and unlink allow a new choice.
  record=(await read()).records.find(r=>r.id===id);await post('api/record/task-link',{record_id:id,child:kid,task_id:b.id,expected_linked_at:record.linked_task_at});
  await create.click();await eventually(async()=>/已关联事项/.test(await status.innerText()),'create conflict');assert.equal(await title.inputValue(),wantedTitle);
  await p.locator('#refreshRecordTaskLink').click();await eventually(async()=>/已读取当前关联/.test(await status.innerText()),'create conflict refresh');assert(await create.isDisabled());assert.equal(await title.inputValue(),wantedTitle);
  await select.selectOption('');await save.click();await eventually(async()=>/关联已解除/.test(await status.innerText()),'explicit unlink keeps new draft');assert.equal(await title.inputValue(),wantedTitle);
  // Expired login preserves the exact creation request; a subsequent real write loses its reply, then replays once.
  let createAttempt=0;const requests=[];await p.route('**/api/record/task-create',async r=>{requests.push(r.request().postDataJSON());createAttempt++;if(createAttempt===1)return r.fulfill({status:401,json:{error:'虚构登录过期'}});if(createAttempt===2){await r.fetch();return r.abort('failed')}return r.continue()});
  const beforeCreate=await read();await create.click();await p.locator('#parentLoginDialog[open]').waitFor();await p.keyboard.press('Escape');assert(await title.isDisabled());assert(await save.isDisabled());
  await create.click();await eventually(async()=>/结果尚未核对/.test(await status.innerText()),'create lost reply');await p.keyboard.press('Escape');assert(await p.locator('#recordDialog').evaluate(x=>x.open));
  if(process.env.RECORD_LINK_UI_PROOF_DIR){await p.locator('#recordTaskCreate').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.RECORD_LINK_UI_PROOF_DIR,'record-create-pending-'+width+'.png')})}
  await create.click();await eventually(async()=>/新事项与关联已保存/.test(await status.innerText()),'create replay success');await p.unroute('**/api/record/task-create');assert.deepEqual(requests[0],requests[1]);assert.deepEqual(requests[1],requests[2]);
  state=await read();const made=state.tasks.find(t=>t.title===wantedTitle);assert(made);assert.equal(state.tasks.length,beforeCreate.tasks.length+1);assert.equal(state.records.length,beforeCreate.records.length);assert.equal(made.child,kid);assert.equal(made.due,'无明确截止');assert(!made.update);assert.equal(made.original_status,'待跟进');
  record=state.records.find(r=>r.id===id);assert.equal(record.linked_task_id,made.id);assert.equal(record.source,before.source);assert.deepEqual(record.attachments,before.attachments);assert.equal(record.transcript,before.transcript);assert.equal(record.note,'未保存的家长补充');assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'虚构：这段原记录补充仍未保存');
  assert.equal(await title.inputValue(),'');assert.equal(await select.inputValue(),made.id);assert.equal(await p.locator('#recordDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  await p.locator('#recordForm [type=submit]').click();await eventually(()=>p.locator('#recordDialog').evaluate(x=>!x.open),'save original after create');await p.reload();await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');await openRecord();assert.equal(await select.inputValue(),made.id);assert.equal(await p.locator('#recordForm [name=note]').inputValue(),'虚构：这段原记录补充仍未保存');await p.keyboard.press('Escape');
  await p.locator('nav [data-page=tasks]').click();await p.locator('[data-task-box="Inbox"]').click();const linkedTask=p.locator('[data-task="'+made.id+'"]:visible').first();assert.match(await linkedTask.innerText(),/查看\/补充反馈/,'linked original is visible from the same task');await linkedTask.click();assert.equal(await p.locator('#taskFeedbackHistory [data-record="'+id+'"]').count(),1);assert.equal(await p.locator('#taskFeedbackHistory img').count(),1);await p.keyboard.press('Escape');
  state=await read();assert.equal(state.records.filter(r=>r.id===id).length,1);assert.deepEqual(state.tasks.find(t=>t.id===a.id).update,taskBefore);assert.deepEqual(errors,[]);await context.close();checks.push(width+': same-child link, lost-reply retry, conflict refresh/unlink, login expiry, draft preservation, linked ordinary answer through shared review validator, model failure/explicit retry, feedback/wrong-item/correction no-write and lost-receipt numbered retries, saved original and opinion reopen, stale-link zero-write rejection, explicit new task, conflict refresh, login/lost-reply retries, preserved drafts and layout');
 }
 console.log(JSON.stringify({passed:true,checks,syntheticOnly:true,sharedValidatorMockRaw:true,realModelCalls:0,realPhoneTested:false}));
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e.stack||e);process.exitCode=1});
