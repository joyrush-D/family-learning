// Synthetic software acceptance only; no real model, collector, household data or printer.
// Set SCHOOL_NATIVE_PROOF_DIR outside the checkout. Run only after committing this file.
// Both ordinary notice forms say today; a separate fixed-receipt control checks
// that an undated reading never borrows the exercise's date.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const fs=require('node:fs/promises');
const path=require('node:path');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const proofDir=process.env.SCHOOL_NATIVE_PROOF_DIR;

async function eventually(fn,label){
 const until=Date.now()+10000;
 while(Date.now()<until){if(await fn())return;await delay(40)}
 throw Error('Timed out: '+label);
}
// Same three-attempt contract as the homework feedback journey: no write, lost
// receipt after the real write, then replay of the unchanged submission number.
async function threeAttemptSave(page,endpoint,button,error,success,read,onLost=async()=>{}){
 const bodies=[],receipts=[],before=await read();
 await page.route('**'+endpoint,async route=>{
  bodies.push(route.request().postDataJSON());
  if(bodies.length===1)return route.fulfill({status:503,json:{error:'虚构未写入失败'}});
  const response=await route.fetch({timeout:5000}),value=await response.json();assert.equal(response.status(),200);receipts.push(value);
  return bodies.length===2?route.fulfill({status:503,json:{error:'虚构写入成功但回执丢失'}}):route.fulfill({response,json:value});
 });
 try{
  await button.click();await eventually(async()=>await error()&&await button.isEnabled(),'503 no-write retry');assert.deepEqual((await read()).records,before.records);
  await button.click();await eventually(async()=>await error()&&await button.isEnabled(),'lost receipt retained');assert.equal((await read()).records.length,before.records.length+1);await onLost();
  await button.click();await eventually(success,'same numbered retry saved');
 }finally{await page.unroute('**'+endpoint)}
 assert.equal(bodies.length,3);assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[1],bodies[2]);assert(bodies[0].request_key);
 const id=value=>endpoint==='/api/wrong/save'?value.saved?.[0]?.id:value.record_id??value.id;
 assert(Number.isInteger(id(receipts[1])));assert.equal(id(receipts[0]),id(receipts[1]));assert.equal(endpoint==='/api/wrong/save'?receipts[1].saved?.[0]?.existing:receipts[1].replayed,true);
 assert.equal((await read()).records.length,before.records.length+1);
 return {record_id:id(receipts[1]),request_key:bodies[0].request_key,retry_posts:3,no_write_503:true,lost_receipt_replayed:true,body:bodies[0]};
}
async function server(form){
 const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',SCHOOL_NATIVE_NOTICE_FORM:form};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const setup=String.raw`import copy,datetime as dt,json,os
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from test_school_native_coverage import SchoolNativeCoverageTests
from test_agent import school_proposal
import family_agent as agent

fixture=SchoolNativeCoverageTests(methodName='runTest');fixture.setUp()
try:
    app,store=fixture.app,fixture.store
    source_root=Path.cwd().resolve()
    assert app.ROOT!=source_root and app.DATA.is_relative_to(app.ROOT)
    assert app.ROOT.name.startswith('synthetic-agent-')
    (app.ROOT/'家庭运行规则.md').write_text('| child-1 | 虚构甲 | — | 10岁 | 四年级 |\n| child-2 | 虚构乙 | — | 13岁 | 初一 |\n')
    for name in set(app.STATIC.values())|set(app.BUNDLE):
        original=source_root/name
        assert original.is_file()
        link=app.ROOT/name;link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to(original)
    now=dt.datetime.now(agent.TZ).replace(hour=8,minute=0,second=0,microsecond=0)
    fixture.now=fixture.fixture.now=now;today=now.date().isoformat()
    fixture.stack.enter_context(patch.object(agent,'_now',side_effect=lambda value=None:value or now))
    fixture.stack.enter_context(patch('socket.create_connection',side_effect=AssertionError('outbound network forbidden')))
    fixture.stack.enter_context(patch('subprocess.run',side_effect=AssertionError('external CLI forbidden')))
    fixture.stack.enter_context(patch('subprocess.Popen',side_effect=AssertionError('external CLI forbidden')))
    printer=fixture.stack.enter_context(patch.object(app.family_print.PrintStore,'enqueue',side_effect=AssertionError('printing forbidden')))
    app.printer_config=lambda:dict(printers=[],error='')
    form=os.environ['SCHOOL_NATIVE_NOTICE_FORM'];assert form in ('numbered','semicolon')
    notice=('英语，今天完成：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题。' if form=='numbered' else
            '英语作业：朗读Unit 2课文两遍，今天完成；完成练习卷第1–3题，今天完成。')
    texts=[notice,
           '补充英语练习卷：单面打印；完成后自查并请家长签字；第4题选做。']
    payload,refs=fixture._ingest(texts,publishers=['synthetic-teacher-1','synthetic-teacher-1'])
    reading=school_proposal(title_quote='朗读Unit 2课文两遍',due=today,evidence=[dict(ref=refs[0])],
        learning_subject='英语',task_title='英语：朗读Unit 2课文',task_goal='朗读Unit 2课文两遍。',
        task_state='ready',task_reason='原文第一项明确。',task_purpose='learning')
    exercise=school_proposal(title_quote='完成练习卷第1–3题',due=today,evidence=[dict(ref=ref) for ref in refs],
        learning_subject='英语',task_title='英语：完成练习卷',
        task_goal='完成练习卷第1–3题。',
        task_state='ready',task_reason='同一稳定发布者补充本项标准。',task_purpose='learning')
    date_text='英语作业：朗读Unit 2课文两遍。完成练习卷第1–3题，今天交。'
    date_ref='message:'+fixture.source['id']+':synthetic-date-control'
    date_evidence=[dict(ref=date_ref,text=date_text,time=now.isoformat(),kind='text',content_incomplete=False,
        attachments=[],publisher='synthetic-teacher-1')]
    date_reply=dict(proposals=[dict(reading,due=today,evidence=[dict(ref=date_ref)]),
                              dict(exercise,due=today,evidence=[dict(ref=date_ref)])])
    with patch.object(agent.family_llm,'_chat_json',return_value=date_reply) as date_model:
        date_items=agent._select('school',date_evidence,school_goals=[],as_of=today,data_path=app.DATA)
    assert date_model.call_count==1 and len(date_items)==2
    date_reading=next(i for i in date_items if reading['title_quote'] in i['body'])
    date_exercise=next(i for i in date_items if exercise['title_quote'] in i['body'])
    assert date_reading['due']=='' and '今天交' not in date_reading['body']
    assert date_exercise['due']==today and '今天交' in date_exercise['body']
    date_control=dict(original=date_text,items=date_items,mock_receipts=1,
        scope='selection-only negative control; undated reading cannot borrow the exercise deadline')
    incomplete=dict(reading,evidence=[dict(ref=ref) for ref in refs])
    replies=[dict(proposals=[incomplete]),dict(proposals=[reading,exercise])]
    fixture._use_replies(payload,replies);fixed=fixture.model.side_effect;calls=[]
    def traced_reply(messages,schema,name,*args,**kwargs):
        context=json.loads(messages[-1]['content'])
        actions=context['required_native_actions']
        assert len(actions)==2 and reading['title_quote'] in actions[0]['quote'] and exercise['title_quote'] in actions[1]['quote']
        assert actions[0]['quote'] in notice and actions[1]['quote'] in notice
        assert actions[0]['supplements']==[] and [s['quote'] for s in actions[1]['supplements']]==[texts[1]]
        assert actions[0]['publisher'] and actions[0]['publisher']==actions[1]['publisher']
        reply=fixed(messages,schema,name,*args,**kwargs)
        calls.append(dict(name=name,as_of=context['as_of'],required_native_actions=copy.deepcopy(actions),reply=copy.deepcopy(reply)))
        return reply
    fixture.model.side_effect=traced_reply
    first=agent.run_once(app,now);fixture._assert_rejected_batch(payload,first)
    with store._db() as c:
        failed_job=dict(c.execute("SELECT id,attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone())
        original_sources=[dict(r) for r in c.execute('SELECT * FROM agent_sources')]
    delayed=agent.run_once(app,now+dt.timedelta(minutes=1));assert fixture.model.call_count==1
    recovered=agent.run_once(app,now+dt.timedelta(minutes=6))
    assert recovered['failed']==0 and recovered['processed']==2 and fixture.model.call_count==2
    with store._db() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        assert len(rows)==2 and all(r['state']=='accepted' and r['due']==today for r in rows)
        reading_row=next(r for r in rows if reading['title_quote'] in r['body'])
        exercise_row=next(r for r in rows if exercise['title_quote'] in r['body'])
        assert reading_row['id']!=exercise_row['id'] and reading_row['task_id']!=exercise_row['task_id']
        for clause in (exercise['title_quote'],'单面打印','完成后自查并请家长签字','第4题选做'):
            assert clause in exercise_row['body'] and clause not in reading_row['body']
        assert reading['title_quote'] not in exercise_row['body']
        tasks={r['id']:dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
        assert set(tasks)=={r['task_id'] for r in rows}
        items=[]
        for role,row,wanted_refs in (('reading',reading_row,refs[:1]),('exercise',exercise_row,refs)):
            plan=json.loads(row['plan']);anchors=plan['school_original_action']['anchors'];task=tasks[row['task_id']]
            assert [e['ref'] for e in json.loads(row['evidence'])]==wanted_refs
            assert [a['ref'] for a in anchors]==wanted_refs and all(a['upload_ids']==[] and a['pages']==[] for a in anchors)
            expected_anchors=[dict(ref=refs[0],upload_ids=[],pages=[],quote=calls[-1]['required_native_actions'][0 if role=='reading' else 1]['quote'])]
            if role=='exercise':expected_anchors.append(dict(ref=refs[1],upload_ids=[],pages=[],quote=texts[1]))
            assert anchors==expected_anchors,'anchors must be literal clauses for this outcome, never the whole mixed notice'
            assert (task['title'],task['action'],task['child'],task['due'],task['original_status'])==(row['title'],row['body'],'虚构甲',today,'待跟进')
            assert len(row['title'])<=40 and not any(s in row['title'] for s in ('单面打印','自查','签字'))
            assert '选做' not in row['title'] or (row['title'].endswith('（第4题选做）') and row['title'].count('选做')==1)
            items.append(dict(role=role,item_id=row['id'],task_id=row['task_id'],title=row['title'],requirements=row['body'],anchors=anchors))
        assert [r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')]==[1,1]
        assert [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]==payload['messages']
        assert [dict(r) for r in c.execute('SELECT * FROM agent_sources')]==original_sources
        done_job=dict(c.execute("SELECT id,attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone())
        assert (done_job['attempts'],done_job['done'],done_job['error'],done_job['next_try'])==(2,1,'','')
        assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0]==0
        saved_items=[dict(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')]
        saved_tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
    replay=agent.run_once(app,now+dt.timedelta(minutes=7))
    assert replay['processed']==replay['created']==0 and fixture.model.call_count==2
    with store._db() as c:
        assert [dict(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')]==saved_items
        assert [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]==saved_tasks
    fixture.model.side_effect=AssertionError('no further model receipt allowed')
    proof=dict(synthetic_only=True,real_model_calls=0,collector_calls=0,printer_calls=0,
        form=form,today=today,child='虚构甲',source_id=fixture.source['id'],messages=payload['messages'],items=items,date_control=date_control,
        first=first,failed_job=failed_job,delayed=delayed,recovered=recovered,done_job=done_job,replay=replay,
        mock_calls=calls,originals_preserved=True,source_cursor_preserved=True,
        scope='ordinary numbered and same-paragraph outcomes; literal exercise standards; fixed receipts are not model accuracy')
    class Handler(app.Handler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/__fixture/proof':
                return self.reply(200,dict(proof,model_receipts=fixture.model.call_count,print_attempts=printer.call_count))
            return super().do_GET()
        def do_POST(self):
            if urlparse(self.path).path not in ('/api/task/feedback','/api/wrong/save','/api/record'):
                return self.reply(503,dict(error='synthetic test forbids model, collection and print actions'))
            return super().do_POST()
    app.prepare_assets()
    http=app.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    print('READY http://127.0.0.1:'+str(http.server_address[1])+'/',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:http.server_close()
finally:fixture.doCleanups()
`;
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'/opt/homebrew/opt/python@3.11/bin/python3.11',['-c',setup],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});
 let output='',diagnostic='',spawnError;
 proc.stdout.on('data',b=>{output=(output+b).slice(-4000)});proc.stderr.on('data',b=>{diagnostic=(diagnostic+b).slice(-12000)});proc.on('error',e=>{spawnError=e});
 const stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2000)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{
  await eventually(async()=>{if(spawnError)throw spawnError;if(proc.exitCode!==null)throw Error('Synthetic server failed: '+diagnostic);return /READY http:\/\/127\.0\.0\.1:\d+\//.test(output)},'isolated HTTP startup');
  return {url:output.match(/READY (http:\/\/127\.0\.0\.1:\d+\/)/)[1],stop};
 }catch(error){await stop();throw error}
}
async function json(url,options={}){
 const response=await fetch(url,{...options,signal:AbortSignal.timeout(5000)});assert.equal(response.status,200,'real local HTTP success: '+new URL(url).pathname);return response.json();
}
async function noOverflow(page){
 const sizes=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth,dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>({width:d.clientWidth,scroll:d.scrollWidth,left:d.getBoundingClientRect().left,right:d.getBoundingClientRect().right}))}));
 assert(sizes.page<=sizes.viewport+1,JSON.stringify(sizes));for(const d of sizes.dialogs)assert(d.scroll<=d.width+1&&d.left>=-1&&d.right<=sizes.viewport+1,JSON.stringify(sizes));
}
async function screenshot(page,name){await noOverflow(page);await page.screenshot({path:path.join(proofDir,page.noticeForm+'-'+name),fullPage:true})}

(async()=>{
 let host,browser,lastPage,proofReady=false;
 const proof={synthetic_only:true,status:'running',real_model_calls:0,collector_calls:0,printer_calls:0,scenarios:[],widths:[],ui_boundary:'scoped quotes are checked in real API responses; current UI does not directly display those anchors; complete original message remains complete'};
 try{
  assert(proofDir,'SCHOOL_NATIVE_PROOF_DIR is required');const sourcePath=await fs.realpath(__dirname),proofPath=path.resolve(proofDir);assert(proofPath!==sourcePath&&!proofPath.startsWith(sourcePath+path.sep),'proof must stay outside the checkout');await fs.mkdir(proofDir,{recursive:true});const actualProofPath=await fs.realpath(proofDir);assert(actualProofPath!==sourcePath&&!actualProofPath.startsWith(sourcePath+path.sep),'proof symlink must stay outside the checkout');proofReady=true;
  browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  for(const form of ['numbered','semicolon']){
  host=await server(form);proof.intake=await json(host.url+'__fixture/proof');proof.scenarios.push({form,intake:proof.intake});assert.equal(proof.intake.model_receipts,2);assert.equal(proof.intake.print_attempts,0);
  for(const width of [360,1440]){
   const page=await browser.newPage({viewport:{width,height:850},timezoneId:'Asia/Shanghai'});lastPage=page;page.noticeForm=form;page.setDefaultTimeout(10000);
   const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',route=>{const url=route.request().url();if(url.startsWith(host.url)||url.startsWith('data:')||url.startsWith('blob:'))return route.continue();external.push(url);return route.abort()});
   const read=()=>json(host.url+'api/state'),items=proof.intake.items,reading=items.find(i=>i.role==='reading'),exercise=items.find(i=>i.role==='exercise');
   const card=id=>page.locator('#content [data-query-target="task:'+id+'"]');
   const home=async()=>{await page.locator('nav [data-page=home]').click();await page.locator('[data-child-filter="child-1"]').click();await card(reading.task_id).waitFor();await card(exercise.task_id).waitFor()};
   const openExercise=async()=>{await home();await card(exercise.task_id).locator('[data-task="'+exercise.task_id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();assert.equal(await page.locator('#taskForm [name=id]').inputValue(),exercise.task_id);assert.equal(await page.locator('#taskRequirement').innerText(),exercise.requirements)};
   let state=await read();assert.equal(state.today,proof.intake.today);assert.equal(state.tasks.length,2);assert.deepEqual(state.tasks.map(t=>t.id).sort(),items.map(i=>i.task_id).sort());
   for(const item of items){const task=state.tasks.find(t=>t.id===item.task_id);assert.equal(task.school_origin,true);assert.equal(task.child,'虚构甲');assert.equal(task.action,item.requirements);assert.equal(task.agenda.due_on,proof.intake.today);assert.equal(task.agenda.category,'homework');assert.equal(task.update,null)}
   await page.goto(host.url,{waitUntil:'domcontentloaded',timeout:15000});await home();
   assert.equal(await page.locator('#content [data-today-task]').count(),2,'today shows two independent school tasks for the selected child');
   assert.match(await card(reading.task_id).innerText(),/朗读Unit 2课文两遍/);assert(!(await card(reading.task_id).innerText()).includes('练习卷'));
   for(const clause of ['完成练习卷第1–3题','单面打印','完成后自查并请家长签字','第4题选做'])assert((await card(exercise.task_id).innerText()).includes(clause));assert(!(await card(exercise.task_id).innerText()).includes('朗读'));
   for(const item of items){const title=await card(item.task_id).locator('h3').innerText();assert.equal(title,item.title);assert(title.length<=40&&!/单面打印|自查|签字/.test(title),'main list title stays short while the body retains standards');assert(!title.includes('选做')||(title.endsWith('（第4题选做）')&&title.split('选做').length===2),'only the compact optional-question boundary belongs in the title')}
   await screenshot(page,'today-'+width+'.png');
   const scopedViews=[];
   for(const item of items){
    const details=card(item.task_id).locator(':scope .task-reference');await details.locator(':scope > summary').click();assert.equal(await details.evaluate(x=>x.open),true);
    for(const anchor of item.anchors){
     const messageID=anchor.ref.slice(anchor.ref.lastIndexOf(':')+1),request=page.waitForResponse(r=>{const url=new URL(r.url());return url.pathname==='/api/agent/message'&&url.searchParams.get('task_id')===item.task_id&&url.searchParams.get('message_id')===messageID});
     await card(item.task_id).locator('[data-school-original-ref="'+anchor.ref+'"]').first().click();const response=await request;assert.equal(response.status(),200);const scoped=await response.json();
     assert.equal(scoped.task_id,item.task_id);assert.equal(scoped.action_material.scoped,true);assert.deepEqual(scoped.action_material.quotes,item.anchors.filter(a=>a.ref===anchor.ref).map(a=>({text:a.quote,upload_ids:a.upload_ids,pages:a.pages})));assert.deepEqual(scoped.attachments,[]);scopedViews.push({task_id:item.task_id,message_id:messageID,quotes:scoped.action_material.quotes});
     const original=page.locator('#schoolOriginalDialog');await page.locator('#schoolOriginalDialog[open]').waitFor();await original.locator('[data-task-material-scope=action]').waitFor();
     await original.locator('[data-school-task-source]').click();const raw=proof.intake.messages.find(m=>m.id===messageID);await eventually(async()=>await original.locator('blockquote').textContent()===raw.text,'complete teacher original stays complete');
     assert.equal(scoped.message.text,raw.text);if(item.role==='reading')assert((await original.locator('blockquote').innerText()).includes('完成练习卷'),'complete source is not a fabricated reading-only quote');
     if(item.role==='exercise'&&messageID===proof.intake.messages[1].id)await screenshot(page,'exercise-original-'+width+'.png');
     await original.locator('[data-school-original-close]').click();
    }
    await card(item.task_id).locator('[data-task="'+item.task_id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();assert.equal(await page.locator('#taskRequirement').innerText(),item.requirements);
    await eventually(async()=>await page.locator('#taskSchoolResources [data-task-material-scope=action]').count()===item.anchors.length,'same task resources use their own scoped originals');await noOverflow(page);await page.locator('#taskDialog [data-close="taskDialog"]').click();
   }
   const before=await read();await openExercise();const note='虚构练习反馈 '+width+'：第1题原答4，另核参考5；第2–3题和第4题选做尚未核对。';await page.locator('#taskForm [name=note]').fill(note);
   const feedback=await threeAttemptSave(page,'/api/task/feedback',page.locator('#saveTaskFeedback'),async()=>/虚构/.test(await page.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),read,()=>screenshot(page,'feedback-retry-'+width+'.png'));
   assert.equal(feedback.body.task_id,exercise.task_id);assert.equal(feedback.body.child,'虚构甲');state=await read();const saved=state.records.find(r=>r.id===feedback.record_id);assert.equal(saved.source,'事项:'+exercise.task_id);assert.equal(saved.note,note);assert.equal(saved.child,'虚构甲');assert.deepEqual(state.tasks,before.tasks,'ordinary progress never completes or replaces either school task');
   await page.locator('#taskDialog [data-close="taskDialog"]').click();await page.reload();await openExercise();await page.locator('#taskFeedbackHistory').getByText(note,{exact:true}).waitFor();assert.equal(await page.locator('[data-task-feedback-edit="'+feedback.record_id+'"]').count(),1);
   const wrong=page.locator('#taskFeedbackHistory [data-task-wrong-form="'+feedback.record_id+'"]');await wrong.locator(':scope > summary').click();await wrong.locator('[data-wrong-field=label]').fill('虚构练习卷第1题');await wrong.locator('[data-wrong-field=text]').fill('虚构第1题：2+3=?');await wrong.locator('[data-wrong-field=answer]').fill('4');await wrong.locator('[data-wrong-field=correction]').fill('5');
   const wrongSaved=await threeAttemptSave(page,'/api/wrong/save',wrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await wrong.innerText()),async()=>/错题已保存在这份作业下/.test(await page.locator('#taskFeedbackStatus').innerText()),read);
   const wrongCard=page.locator('#taskFeedbackHistory .task-feedback-record').filter({has:page.locator('[data-record="'+wrongSaved.record_id+'"]')});await wrongCard.locator('[data-followup]').click();await page.locator('#recordDialog[open]').waitFor();const correctionForm=page.locator('#recordForm'),correctionNote='虚构练习订正 '+width+'：第1题改为5；其余题与朗读均未据此判完成。';assert.equal(await correctionForm.locator('[name=followup_kind]').inputValue(),'订正');assert.equal(await correctionForm.locator('[name=related_record_id]').inputValue(),String(wrongSaved.record_id));await correctionForm.locator('[name=note]').fill(correctionNote);
   const correction=await threeAttemptSave(page,'/api/record',correctionForm.locator('[type=submit]'),async()=>/虚构/.test(await page.locator('#recordError').innerText()),async()=>!await page.locator('#recordDialog').evaluate(x=>x.open),read);
   await page.reload();await openExercise();await page.locator('#taskFeedbackHistory').getByText(correctionNote,{exact:false}).waitFor();await page.locator('#taskFeedbackHistory').getByText(note,{exact:true}).waitFor();state=await read();const finalWrong=state.records.find(r=>r.id===wrongSaved.record_id),finalCorrection=state.records.find(r=>r.id===correction.record_id);assert.equal(finalWrong.related_record_id,feedback.record_id);assert.equal(finalCorrection.related_record_id,finalWrong.id);assert.equal(finalCorrection.followup_kind,'订正');for(const r of [finalWrong,finalCorrection]){assert.equal(r.child,'虚构甲');assert.equal(r.linked_task_id,exercise.task_id)}assert.deepEqual(state.tasks,before.tasks,'feedback, wrong item and correction preserve both original school tasks');assert.equal(state.records.length,before.records.length+3);assert.deepEqual(state.printing.jobs,[]);
   await screenshot(page,'exercise-reopen-'+width+'.png');await page.locator('#taskDialog [data-close="taskDialog"]').click();await page.locator('[data-child-filter="child-2"]').click();for(const item of items)assert.equal(await card(item.task_id).count(),0);assert.equal(await page.locator('#content [data-school-original-ref]').count(),0);await noOverflow(page);
   const cross=await fetch(host.url+'api/task/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({...feedback.body,child:'虚构乙',request_key:'synthetic-native-other-child-'+width}),signal:AbortSignal.timeout(5000)});assert.equal(cross.status,409);assert.deepEqual((await read()).records,state.records);
   await page.locator('[data-child-filter="child-1"]').click();for(const item of items)await card(item.task_id).waitFor();assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
   const runtime=await json(host.url+'__fixture/proof');assert.equal(runtime.model_receipts,2);assert.equal(runtime.print_attempts,0);assert.deepEqual(runtime.mock_calls,proof.intake.mock_calls);
   proof.widths.push({form,width,school_task_ids:items.map(i=>i.task_id),scoped_views:scopedViews,exercise_task_id:exercise.task_id,feedback,wrong:wrongSaved,correction,reopened_same_task:true,reading_untouched:true,cross_child_rejected:true,no_horizontal_overflow:true});
   await page.close();lastPage=null;
  }
  await host.stop();host=null;
  }
  proof.status='passed';console.log('school action inventory: both notice forms at 360/1440 passed (synthetic only)');
 }catch(error){proof.status='failed';proof.error=error.message;if(lastPage&&proofReady)await lastPage.screenshot({path:path.join(proofDir,'failure.png'),fullPage:true}).catch(()=>{});throw error}
 finally{if(proofReady)await fs.writeFile(path.join(proofDir,'proof.json'),JSON.stringify(proof,null,2));if(browser)await browser.close();if(host)await host.stop()}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
