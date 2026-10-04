// Disposable synthetic family only: one saved answer photo -> explicit AI draft -> reviewed feedback.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(fn,label){for(let n=0;n<250;n++){if(await fn())return;await delay(40)}throw Error('Timed out: '+label)}
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
 assert.equal((await read()).records.length,before.records.length+1);return {record_id:id(results[1]),request_key:bodies[0].request_key};
}
async function server(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 // The fault stays in this disposable demo process; no worker or household printer is started.
 const setup=`import runpy,sys,json,copy
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
import app
cause_raw=dict(items=[dict(label='虚构甲卷第1题',question='虚构甲卷第1题：2+3=?',student_answer='4',answer='教师参考：5',judgment='incorrect',question_kind='objective',error_reason='卷面作答4与核对答案5不同。',possible_cause='',steps='先独立重算2+3，再对照核对答案。',uncertainty='')],coverage='仅虚构甲卷第1题，其余未检查。')
cause_calls=[]
validator=app.family_llm.homework_reference_draft
def mock_chat(messages,schema,name,timeout,**kwargs):
    assert app.DATA.name.startswith('family-demo-') and name=='family_homework_reference'
    content=messages[-1]['content']
    texts=[part['text'] for part in content if part.get('type')=='text']
    assert any('虚构错因独立校验' in text and '2+3' in text for text in texts)
    assert any('教师参考原文' in text and '2+3=5' in text for text in texts)
    assert any('原作答家长说明' in text and '最终作答4' in text for text in texts)
    assert sum(part.get('type')=='image_url' for part in content)==1
    cause_calls.append(dict(raw=copy.deepcopy(cause_raw)))
    return cause_calls[-1]['raw']
def traced_validator(*args,**kwargs):
    result=validator(*args,**kwargs)
    assert cause_calls[-1]['raw']==cause_raw
    cause_calls[-1]['validated']=copy.deepcopy(result)
    return result
app.family_llm._chat_json=mock_chat
app.family_llm.homework_reference_draft=traced_validator
unit_cases={}
def unit_fixture(width):
    assert app.DATA.name.startswith('family-demo-') and width in (360,1440)
    agent=app.family_agent
    if width in unit_cases:
        result=unit_cases[width]
        with app.connect_read_only() as c:
            assert [dict(r) for r in c.execute('SELECT * FROM agent_messages WHERE source_id=? ORDER BY id',(result['source_id'],))]==result['messages']
            assert dict(c.execute('SELECT * FROM agent_sources WHERE id=?',(result['source_id'],)).fetchone())==result['source']
            assert dict(c.execute('SELECT * FROM agent_items WHERE id=?',(result['original_id'],)).fetchone())==result['accepted_after']
        return result
    from test_agent import school_proposal
    now=app.dt.datetime.now(agent.TZ);due=(now.date()+app.dt.timedelta(days=1)).isoformat()
    source=dict(id='synthetic-unit-'+str(width),platform='wechat',child_id='child-1',name='虚构Unit来源 '+str(width),cursor='',enabled=True)
    path=app.DATA/'agent.json';config=json.loads(path.read_text()) if path.exists() else dict(enabled=True,sources=[])
    config['enabled']=True;config['sources'].append(source);path.write_text(json.dumps(config))
    store=app.agent_store();calls=[]
    def task(ident):
        with app.connect_read_only() as c:return copy.deepcopy(next(t for t in app.tasks(c) if t['id']==ident))
    def classify(index,text,title,change='new',target='',deadline=''):
        with store._db() as c:
            prior=c.execute('SELECT cursor FROM agent_sources WHERE id=?',(source['id'],)).fetchone()
        message=dict(id=str(index),time=now.isoformat(),kind='text',sender='虚构英语老师',sender_id='synthetic-unit-teacher-'+str(width),text=text,unread=False)
        store.ingest(dict(source_id=source['id'],expected_cursor=prior['cursor'] if prior else '',cursor=str(index),checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[message]))
        with store._db() as c:
            before_messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages WHERE source_id=? ORDER BY id',(source['id'],))]
            before_source=dict(c.execute('SELECT * FROM agent_sources WHERE id=?',(source['id'],)).fetchone())
        ref='message:'+source['id']+':'+str(index)
        evidence=[dict(message,ref=ref,publisher=agent._publisher(source['id'],message),content_incomplete=False)]
        raw=dict(proposals=[school_proposal(title_quote=text,due=deadline,evidence=[dict(ref=ref)],learning_subject='英语',task_title=title,task_goal=text,task_state='ready',task_reason='虚构明确原文。',task_change=change,task_target_id=target,task_purpose='learning')])
        def fixed(messages,schema,name,*args,**kwargs):
            assert name=='family_agent_selection';calls.append(dict(index=index,name=name,raw=copy.deepcopy(raw)));return copy.deepcopy(raw)
        with patch.object(agent.family_llm,'_chat_json',side_effect=fixed):
            items=agent._select('school',evidence,school_goals=[],school_tasks=agent.school_targets(app,store,'child-1'),as_of=now.date().isoformat())
        assert len(items)==1
        items[0].update(child_id='child-1',kind='school')
        if items[0]['plan'].get('school_learning'):items[0]['plan']['school_messages']=[dict(source_id=source['id'],message_id=str(index))]
        key='synthetic-unit:'+str(width)+':'+str(index);store._save(key,'fixed-model-raw',items,now)
        with store._db() as c:
            row=dict(c.execute('SELECT * FROM agent_items WHERE job_id=?',(key,)).fetchone())
            assert [dict(r) for r in c.execute('SELECT * FROM agent_messages WHERE source_id=? ORDER BY id',(source['id'],))]==before_messages
            assert dict(c.execute('SELECT * FROM agent_sources WHERE id=?',(source['id'],)).fetchone())==before_source
        return row
    original_text='Unit30课文读两遍，朗读录音上传班级作业区，明天完成。'
    original=classify(1,original_text,'英语：Unit30朗读 '+str(width),deadline=due)
    task_id=store.act(dict(id=original['id'],action='accept'))['task_id'];original_task=task(task_id)
    with store._db() as c:accepted_before=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone());count_before=c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]
    wrong=classify(2,'只补Unit3朗读：上传录音后确认上传成功。','英语：Unit3朗读补充',change='append',target=task_id)
    wrong_brief=json.loads(wrong['plan'])['school_task']
    assert wrong_brief['state']=='review' and not wrong_brief.get('target_basis') and not wrong_brief.get('input_basis'),'Unit3 must not append to Unit30'
    assert task(task_id)==original_task,'wrong Unit changed the canonical task'
    with store._db() as c:
        assert dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())==accepted_before
        assert c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]==count_before
    correct_text='只补Unit 30朗读：上传录音后确认上传成功。'
    correct=classify(3,correct_text,'英语：Unit 30朗读补充',change='append',target=task_id);brief=json.loads(correct['plan'])['school_task']
    assert brief['state']=='ready' and brief.get('target_basis') and brief.get('input_basis'),'same Unit with spacing must stay eligible'
    with store._db() as c:
        final_messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages WHERE source_id=? ORDER BY id',(source['id'],))];final_source=dict(c.execute('SELECT * FROM agent_sources WHERE id=?',(source['id'],)).fetchone())
    with patch.object(agent,'_now',return_value=now):saved=agent.apply_school_change(app,store,agent._school_append_request(correct,brief),school_auto=True)
    final_task=task(task_id);assert saved['task_id']==task_id and final_task['title']==original_task['title'] and final_task['agenda']['due_on']==due
    assert final_task['action']==original_task['action']+chr(10)+'补充要求：'+correct_text
    with store._db() as c:
        accepted_after=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())
        for key in ('id','state','task_id','child_id','title','body','evidence','due','created'):assert accepted_after[key]==accepted_before[key]
        before_plan=json.loads(accepted_before['plan']);after_plan=json.loads(accepted_after['plan'])
        for key,value in before_plan.items():
            if key!='school_messages':assert after_plan[key]==value
        old_links=before_plan.get('school_messages',[])
        assert after_plan.get('school_messages',[])[:len(old_links)]==old_links
        if before_plan.get('school_learning'):assert after_plan['school_messages'][len(old_links):]==[dict(source_id=source['id'],message_id='3')]
        assert len(after_plan.get('school_changes',[]))==1 and after_plan['school_changes'][0]['item_id']==correct['id']
        assert c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]==count_before
        assert dict(c.execute('SELECT * FROM agent_items WHERE id=?',(wrong['id'],)).fetchone())==wrong
        assert [dict(r) for r in c.execute('SELECT * FROM agent_messages WHERE source_id=? ORDER BY id',(source['id'],))]==final_messages
        assert dict(c.execute('SELECT * FROM agent_sources WHERE id=?',(source['id'],)).fetchone())==final_source
    result=dict(synthetic_only=True,shared_guard=True,real_model_calls=0,task_id=task_id,title=final_task['title'],action=final_task['action'],due=due,source_id=source['id'],original_ref='message:'+source['id']+':1',original_text=original_text,original_id=original['id'],wrong_id=wrong['id'],correct_id=correct['id'],wrong_state=wrong_brief['state'],correct_state=brief['state'],calls=calls,messages=final_messages,source=final_source,accepted_before=accepted_before,accepted_after=accepted_after,classification_preserved_sources=True,wrong_preserved_canonical=True,accepted_original_preserved=True)
    unit_cases[width]=result;return result
get=app.Handler.do_GET
def fixture_get(self):
    if self.path=='/__fixture/cause-validator':
        assert app.DATA.name.startswith('family-demo-')
        return self.reply(200,dict(synthetic_only=True,shared_validator=True,real_model_calls=0,calls=cause_calls))
    if urlparse(self.path).path=='/__fixture/unit-identity':
        query=parse_qs(urlparse(self.path).query)
        if set(query)!={'width'} or query['width'] not in (['360'],['1440']):return self.reply(400,dict(error='虚构宽度不正确'))
        try:return self.reply(200,unit_fixture(int(query['width'][0])))
        except AssertionError as error:return self.reply(500,dict(error='Unit fixture: '+str(error),synthetic_only=True,real_model_calls=0))
    return get(self)
app.Handler.do_GET=fixture_get
original=app.family_print.PrintStore._convert
app.printer_config=lambda:dict(printers=[dict(name='Synthetic_Printer',label='虚构打印机',color=False,duplex=False)],error='')
def unlink_after_conversion(store,data,name,directory):
    result=original(store,data,name,directory)
    if name.startswith('synthetic-recovery-original-A-'):
        assert app.DATA.name.startswith('family-demo-')
        with app.connect_read_only() as c:
            ids={r['id'] for r in c.execute('SELECT id FROM uploads WHERE name=?',(name,))}
            records=[dict(r) for r in c.execute('SELECT * FROM records') if ids.intersection(json.loads(r['attachments']))]
        for r in records:
            app.save_record(dict(id=r['id'],child=r['child'],day=r['day'],category=r['category'],title=r['title'],source=r['source'],note='Synthetic material unlinked while preparing',attachments=[]))
    return result
app.family_print.PrintStore._convert=unlink_after_conversion
sys.argv=['demo.py','--port',sys.argv[1]]
runpy.run_path('demo.py',run_name='__main__')`;
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',setup,String(port)],{cwd:__dirname,env,stdio:'ignore'}),url='http://127.0.0.1:'+port+'/';
 await eventually(async()=>{try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'demo startup');
 return {url,stop:async()=>{if(proc.exitCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2000)]);if(proc.exitCode===null){proc.kill('SIGKILL');await done}}};
}
(async()=>{let host,browser,lastPage;try{
 host=await server();browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=','base64');
 for(const width of [360,1440]){
  let state=await(await fetch(host.url+'api/state')).json();const child=state.children[0].name,title='虚构作业核对 '+width;
  const p=await browser.newPage({viewport:{width,height:850}}),errors=[];lastPage=p;p.on('pageerror',e=>errors.push(e.message));
  let baselineLoads=0;
  if(process.env.PRINT_SCOPE_BASELINE_APP_JS)await p.route('**/app.bundle.js',async r=>{
   const fs=require('node:fs/promises'),path=require('node:path'),response=await r.fetch(),bundle=await response.text(),current=await fs.readFile(path.join(__dirname,'app.js'),'utf8'),baseline=await fs.readFile(process.env.PRINT_SCOPE_BASELINE_APP_JS,'utf8');
   assert(bundle.startsWith('(()=>{\n'+current),'the baseline replaces the application actually loaded by the page');baselineLoads++;
   return r.fulfill({contentType:'text/javascript',body:'(()=>{\n'+baseline+bundle.slice('(()=>{\n'.length+current.length)});
  });
  await p.route('**/api/state',async route=>{const response=await route.fetch(),value=await response.json();value.printing={...value.printing,printers:[{name:'Synthetic_Printer',label:'虚构打印机',color:false,duplex:false}]};await route.fulfill({response,json:value})});
  await p.goto(host.url);
  if(process.env.PRINT_SCOPE_BASELINE_APP_JS)assert.equal(baselineLoads,1,'old application was actually loaded');
  await p.locator('[data-homework-new]').first().click();const entry=p.locator('#homeworkInputDialog');await entry.waitFor();assert.match(await entry.innerText(),/记作业/);
  const item=entry.locator('[data-homework-item="0"]');assert.equal(await item.locator('[name=title]').isVisible(),true,'parent can enter one homework directly');assert.equal(await entry.locator('[data-homework-original]').evaluate(x=>x.open),false,'source capture stays optional');await entry.locator('[data-homework-original] > summary').click();await entry.locator('[name=text]').fill('虚构老师原话：核对一页阅读题');
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.HOMEWORK_QUICK_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'quick-entry-'+width+'.png')})}
  let draftCalls=0;await p.route('**/api/study/draft',r=>{draftCalls++;return r.fulfill({status:503,json:{error:'虚构模型不可用'}})});
  await item.locator('[name=title]').fill(title);await entry.locator('[data-homework-close]').click();await p.locator('[data-homework-new]').first().click();assert.equal(await item.locator('[name=title]').inputValue(),title,'quick entry survives closing and reopening');await item.locator('[name=goal]').fill('先作答再核对');assert.equal(await item.locator('[name=reviewed]').count(),0,'parent save is the explicit confirmation without a duplicate checkbox');await item.locator('[type=submit]').click();await entry.locator('.homework-saved').waitFor();assert.equal(draftCalls,0,'manual entry does not require the model');await p.unroute('**/api/study/draft');await entry.locator('[data-homework-manual]').click();assert.equal(await entry.locator('[data-homework-item]').count(),1,'unused empty candidate is visible');await entry.locator('[data-homework-close]').click();await p.locator('[data-homework-new]').first().click();assert.equal(await entry.locator('.homework-saved').count(),0,'a later capture starts a new session');assert.equal(await entry.locator('[data-homework-item="0"] [name=title]').isVisible(),true);assert.equal(await entry.locator('[name=text]').inputValue(),'','a new task does not inherit the previous original');assert.equal(await entry.locator('[data-homework-original]').evaluate(x=>x.open),false);await entry.locator('[data-homework-close]').click();
  state=await(await fetch(host.url+'api/state')).json();const id=state.tasks.find(t=>t.title===title)?.id;assert(id,'homework entry creates the task');await p.locator('[data-query-target="task:'+id+'"]').waitFor();
  assert.match(await p.locator('[data-query-target="task:'+id+'"] [data-task="'+id+'"]:visible').first().innerText(),/提交作业反馈/);
  await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskDialog[open]').waitFor();
  assert.equal(await p.locator('#taskStatusDetails').evaluate(x=>x.open),false,'status update stays secondary');
  await p.locator('#taskForm [name=note]').fill('虚构未保存反馈');
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'close dismissal keeps unsaved feedback');
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构未保存反馈');
  await p.locator('#taskForm [name=note]').fill('');
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-answer.png',mimeType:'image/png',buffer:png});await p.locator('#pendingUploads img').waitFor();
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'close dismissal keeps unsaved photo');
  assert.equal(await p.locator('#pendingUploads img').count(),1);
  await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'photo feedback saved');
  assert.match(await p.locator('[data-query-target="task:'+id+'"] [data-task="'+id+'"]:visible').first().innerText(),/查看\/补充反馈/,'today confirms saved feedback in the same task');
  assert(await p.locator('[data-query-target="task:'+id+'"] [data-homework-print]').isVisible(),'separate question/reference printing is directly visible');
  const preparation={id:'b'.repeat(32),pdf_sha256:'c'.repeat(64),page_count:1,preview_url:'/api/print/preview/'+'b'.repeat(32)},keysPrint=[];
  await p.route('**/api/print/prepare',r=>r.fulfill({json:{preparation}}));
  await p.route('**/api/print/enqueue',r=>{keysPrint.push(r.request().postDataJSON().idempotency_key);return keysPrint.length===1?r.fulfill({status:503,json:{error:'虚构打印回执丢失'}}):r.fulfill({json:{job:{id:'d'.repeat(32),status:'queued'}}})});
  const printButton=p.locator('#taskFeedbackHistory [data-print-upload]').first();
  await p.locator('#taskForm [name=note]').fill('打印时保留的未保存反馈');
  await printButton.click();await eventually(async()=>await printButton.isEnabled(),'print failure releases button');assert.equal(keysPrint.length,1);
  await printButton.click();await eventually(async()=>/已提交打印/.test(await printButton.innerText()),'one original print retry acknowledged');
  assert.equal(keysPrint[0],keysPrint[1],'print retry keeps its request number');assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'打印时保留的未保存反馈');
  await printButton.click();assert.equal(keysPrint.length,2,'repeated click does not enqueue twice');
  await p.unroute('**/api/print/prepare');await p.unroute('**/api/print/enqueue');await p.locator('#taskForm [name=note]').fill('');

  // Printing must follow this exact homework, not the family's global file list.
  const post=async(path,body)=>{const r=await fetch(host.url+path,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(body)});assert.equal(r.status,200);return r.json()};
  const otherTasks=[];
  for(const [owner,label] of [[state.children[0].name,'同孩其他作业'],[state.children[1].name,'另一孩子作业']]){
   const t=(await post('api/task/new',{child:owner,title:'虚构'+label+' '+width,category:'homework',action:'独立核对这份卷',due:state.today})).task;
   const response=await fetch(host.url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'Content-Type':'image/png','X-File-Name':encodeURIComponent('虚构'+label+'原件.png')},body:png});assert.equal(response.status,200);const {attachment:upload}=await response.json();
   await post('api/task/feedback',{task_id:t.id,child:owner,day:state.today,attachments:[upload.id],request_key:'synthetic-print-other-'+width+'-'+otherTasks.length});
   otherTasks.push({task:t,upload});
  }
  await p.keyboard.press('Escape');await p.reload();await p.locator('[data-query-target="task:'+id+'"] [data-homework-print]').click();
  const printForm=p.locator('#homeworkPrintForm');await p.locator('#homeworkPrintDialog[open]').waitFor();
  const options=await printForm.locator('[name=question_source] option').allTextContents();
  assert(options.includes('synthetic-answer.png'),'the original saved answer remains selectable');
  assert(options.every(x=>!x.includes('另一孩子')&&!x.includes('同孩其他作业')),'printing candidates contain no other child or task');
  assert.equal(await printForm.locator('[name=guide_source] option').allTextContents().then(xs=>xs.some(x=>/另一孩子|同孩其他作业/.test(x))),false,'reference candidates follow the same original task');
  await printForm.locator('[name=question_source]').selectOption({label:'synthetic-answer.png'});await printForm.locator('[name=guide_text]').fill('虚构家长参考：题目和答案分别打印。');
  await printForm.locator('[name=question_confirmed]').check();await printForm.locator('[name=guide_confirmed]').check();
  const originalPrintKey=await printForm.evaluate(f=>f.dataset.requestKey);
  await p.locator('#homeworkPrintDialog [data-close]').click();
  let reads=0;await p.route('**/api/print/homework/materials?*',r=>++reads===1?r.fulfill({status:503,json:{error:'虚构资料读取失败'}}):r.continue());
  await p.locator('[data-query-target="task:'+id+'"] [data-homework-print]').click();await eventually(async()=>/虚构资料读取失败/.test(await p.locator('#toast').innerText()),'read failure stays retryable');
  assert.equal(await p.locator('#homeworkPrintDialog').evaluate(x=>x.open),false,'failed scoped read never falls back to global files');
  await p.locator('[data-query-target="task:'+id+'"] [data-homework-print]').click();await p.locator('#homeworkPrintDialog[open]').waitFor();await p.unroute('**/api/print/homework/materials?*');
  assert.equal(await printForm.locator('[name=guide_text]').inputValue(),'虚构家长参考：题目和答案分别打印。');assert.equal(await printForm.evaluate(f=>f.dataset.requestKey),originalPrintKey,'read failure preserves the draft and request number');
  await p.locator('#homeworkPrintDialog [data-close]').click();
  await p.evaluate(({task,other})=>{const key='family-homework-print:v1:'+new URL('.',location.href).pathname+':'+task,saved=JSON.parse(sessionStorage.getItem(key));saved.question_source=JSON.stringify({type:'upload',id:other});sessionStorage.setItem(key,JSON.stringify(saved))},{task:id,other:otherTasks[1].upload.id});
  await p.locator('[data-query-target="task:'+id+'"] [data-homework-print]').click();await p.locator('#homeworkPrintDialog[open]').waitFor();
  assert.match(await p.locator('#homeworkPrintError').innerText(),/原选择有资料现在无法核对/);assert.equal(await printForm.locator('[name=guide_text]').inputValue(),'虚构家长参考：题目和答案分别打印。');
  let paired=0,generated=0;const pairBodies=[];
  await p.route('**/api/print/homework/draft',r=>{generated++;return r.fulfill({status:503,json:{error:'不应调用'}})});
  await p.route('**/api/print/homework',r=>{
    paired++;pairBodies.push(r.request().postDataJSON());
    return paired===1?r.fulfill({status:503,json:{error:'虚构配对回执丢失'}}):r.fulfill({json:{jobs:{questions:[{id:'e'.repeat(32)}],guide:{id:'f'.repeat(32)}}}});
  });
  await p.locator('#homeworkDraftButton').click();await printForm.locator('[type=submit]').evaluate(x=>x.click());assert.equal(generated,0);assert.equal(paired,0,'unavailable saved source cannot be sent to printing');
  await printForm.locator('[name=question_source]').selectOption({label:'synthetic-answer.png'});await printForm.locator('[name=question_confirmed]').check();await printForm.locator('[name=guide_confirmed]').check();
  assert.equal(await p.locator('#homeworkPrintError').innerText(),'','explicitly reselecting an owned source clears the stale unavailable-source warning');
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'scoped-print-'+width+'.png')})}
  await printForm.locator('[type=submit]').click();await eventually(async()=>/虚构配对回执丢失/.test(await p.locator('#homeworkPrintError').innerText()),'pair failure retained');
  await p.locator('#homeworkPrintDialog [data-close]').click();await p.reload();await p.locator('[data-query-target="task:'+id+'"] [data-homework-print]').click();await p.locator('#homeworkPrintDialog[open]').waitFor();
  assert.equal(await printForm.evaluate(f=>f.dataset.requestKey),originalPrintKey,'unknown print receipt survives reopening');
  await printForm.locator('[type=submit]').click();await eventually(async()=>!await p.locator('#homeworkPrintDialog').evaluate(x=>x.open),'pair retry saved');assert.deepEqual(pairBodies[1],pairBodies[0]);assert.equal(pairBodies[0].task_id,id);
  await p.unroute('**/api/print/homework');await p.unroute('**/api/print/homework/draft');await p.locator('nav [data-page=home]').click();await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskDialog[open]').waitFor();

   { // Exercise real preparation + HTTP ownership failure + changed file + lost queue receipt.
   const priorPrintIds=(await (await fetch(host.url+'api/print/jobs')).json()).jobs.map(j=>j.id).sort();
   const recoveryTask=(await post('api/task/new',{child,title:'虚构打印恢复 '+width,category:'homework',action:'核对同一作业的资料',due:state.today})).task;
   const validPng=require('node:child_process').spawnSync(process.env.FAMILY_TEST_PYTHON||'python3',['-c','from test_print import png; import sys; sys.stdout.buffer.write(png())'],{cwd:__dirname,env:{...process.env},encoding:null});
   assert.equal(validPng.status,0,'synthetic original is created without a model');
   async function recoveryUpload(name){const response=await fetch(host.url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'Content-Type':'image/png','X-File-Name':encodeURIComponent(name)},body:validPng.stdout});assert.equal(response.status,200);return (await response.json()).attachment}
   const originalA=await recoveryUpload('synthetic-recovery-original-A-'+width+'.png'),originalB=await recoveryUpload('synthetic-recovery-original-B-'+width+'.png'),reference=await recoveryUpload('synthetic-recovery-reference-'+width+'.png');
   const recordBody={child,day:state.today,category:'学习进展',title:'虚构待打印原件',source:'事项:'+recoveryTask.id,note:'原件由家长核对',attachments:[originalA.id,reference.id]};
   const ordinary=(await post('api/record',recordBody)).record_id;
   await p.keyboard.press('Escape');await p.reload();await p.locator('[data-query-target="task:'+recoveryTask.id+'"] [data-homework-print]').click();await p.locator('#homeworkPrintDialog[open]').waitFor();
   await printForm.locator('[name=question_source]').selectOption(JSON.stringify({type:'upload',id:originalA.id}));await printForm.locator('[name=guide_source]').selectOption(JSON.stringify({type:'upload',id:reference.id}));await printForm.locator('[name=question_confirmed]').check();await printForm.locator('[name=guide_confirmed]').check();
   const recoveryKey=await printForm.evaluate(f=>f.dataset.requestKey),recoveryBodies=[],recoveryStatuses=[];
   let loseQueueReceipt=false;
   await p.route('**/api/print/homework',async route=>{recoveryBodies.push(route.request().postDataJSON());const response=await route.fetch();recoveryStatuses.push(response.status());if(loseQueueReceipt&&response.ok()){loseQueueReceipt=false;return route.fulfill({status:503,json:{error:'虚构真实入队后的回执丢失'}})}return route.fulfill({response})});
   await printForm.locator('[type=submit]').click();await eventually(async()=>/归属|原作业|核对|关联/.test(await p.locator('#homeworkPrintError').innerText())&&await printForm.locator('[type=submit]').isEnabled(),'ownership rejected after preparation');
   assert.deepEqual(recoveryStatuses,[403],'the real current-source guard rejected printing');assert.deepEqual((await (await fetch(host.url+'api/print/jobs')).json()).jobs.map(j=>j.id).sort(),priorPrintIds,'prepared A never entered the print queue');
   await post('api/record',{...recordBody,id:ordinary,note:'家长换成新原件B',attachments:[originalB.id,reference.id]});
   await p.locator('#homeworkPrintDialog [data-close]').click();await p.reload();await p.locator('[data-query-target="task:'+recoveryTask.id+'"] [data-homework-print]').click();await p.locator('#homeworkPrintDialog[open]').waitFor();
   assert.equal(await printForm.evaluate(f=>f.dataset.requestKey),recoveryKey,'failed prepared-only request survives reopening');
   assert.match(await p.locator('#homeworkPrintError').innerText(),/原选择有资料现在无法核对/);await printForm.locator('[name=question_source]').selectOption(JSON.stringify({type:'upload',id:originalB.id}));await printForm.locator('[name=guide_source]').selectOption(JSON.stringify({type:'upload',id:reference.id}));await printForm.locator('[name=question_confirmed]').check();await printForm.locator('[name=guide_confirmed]').check();
   loseQueueReceipt=true;await printForm.locator('[type=submit]').click();await eventually(async()=>/虚构真实入队后的回执丢失/.test(await p.locator('#homeworkPrintError').innerText()),'new original B prepared and queued by the real backend');
   assert.deepEqual(recoveryStatuses,[403,200]);const realQueued=(await (await fetch(host.url+'api/print/jobs')).json()).jobs;assert.equal(realQueued.filter(j=>!priorPrintIds.includes(j.id)).length,2,'B and reference are separate jobs');
   await p.locator('#homeworkPrintDialog [data-close]').click();await p.reload();await p.locator('[data-query-target="task:'+recoveryTask.id+'"] [data-homework-print]').click();await p.locator('#homeworkPrintDialog[open]').waitFor();
   assert.equal(await printForm.evaluate(f=>f.dataset.requestKey),recoveryKey);await printForm.locator('[type=submit]').click();await eventually(async()=>!await p.locator('#homeworkPrintDialog').evaluate(x=>x.open),'original queue keys recover a lost receipt');
   const retriedJobs=(await (await fetch(host.url+'api/print/jobs')).json()).jobs;assert.deepEqual(retriedJobs.map(j=>j.id).sort(),realQueued.map(j=>j.id).sort(),'retry never duplicates a submitted part');assert.deepEqual(recoveryBodies[2],recoveryBodies[1]);assert.equal(recoveryBodies[0].request_key,recoveryBodies[1].request_key);
   await p.unroute('**/api/print/homework');await p.locator('nav [data-page=home]').click();await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskDialog[open]').waitFor();
   }
   const printIdsBeforeChecks=(await (await fetch(host.url+'api/print/jobs')).json()).jobs.map(j=>j.id).sort();

  const wrong=p.locator('#taskFeedbackHistory [data-task-wrong-form]').first();await wrong.locator(':scope > summary').click();
  await wrong.locator('[data-wrong-field="label"]').fill('第2题');await wrong.locator('[data-wrong-field="answer"]').fill('C');await wrong.locator('[data-wrong-field="correction"]').fill('B');
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'unsaved wrong answer stays with homework');
  let wrongCalls=0;await p.route('**/api/wrong/save',r=>{wrongCalls++;return wrongCalls===1?r.fulfill({status:503,json:{error:'虚构保存失败'}}):r.continue()});
  await wrong.locator('[data-task-wrong-save]').click();await eventually(async()=>/结果尚未核对/.test(await wrong.innerText()),'unknown wrong-item result retained');
  assert.equal(await wrong.locator('[data-wrong-field="answer"]').inputValue(),'C');
  await wrong.locator('[data-task-wrong-save]').click();await eventually(async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),'wrong-item retry saved');await p.unroute('**/api/wrong/save');
  state=await(await fetch(host.url+'api/state')).json();const wrongRecords=state.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===id);assert.equal(wrongRecords.length,1,'retry creates one wrong item');
  assert.equal(wrongRecords[0].related_record_id,state.records.find(r=>r.source==='事项:'+id).id,'wrong item points to the original answer');
  assert.equal(wrongRecords[0].attachments[0],state.records.find(r=>r.source==='事项:'+id).attachments[0],'saved photo is reused');
  assert.equal(state.tasks.find(t=>t.id===id).update,null,'recording a wrong answer does not complete homework');
  assert.equal(await p.locator('#taskFeedbackHistory [data-homework-review]').count(),1,'wrong-item record does not start a second AI review');
  await p.keyboard.press('Escape');await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskFeedbackHistory').getByText('作业错题', {exact:false}).first().waitFor();
  const wrongCard=p.locator('#taskFeedbackHistory .task-feedback-record').filter({has:p.locator('[data-record="'+wrongRecords[0].id+'"]')});
  await p.locator('#taskForm [name=note]').fill('虚构未保存的新反馈');p.once('dialog',d=>d.dismiss());
  await wrongCard.locator('[data-followup]').click();assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'correction does not discard unsaved feedback');
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构未保存的新反馈');await p.locator('#taskForm [name=note]').fill('');
  await wrongCard.locator('[data-followup]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false,'correction opens from the original homework');
  const correctionForm=p.locator('#recordForm');assert.equal(await correctionForm.locator('[name=followup_kind]').inputValue(),'订正');
  await correctionForm.locator('[name=note]').fill('虚构：孩子独立订正后仍需换题核对');
  let discardPrompts=0;const keepDraft=d=>{discardPrompts++;d.dismiss()};p.on('dialog',keepDraft);
  await p.locator('#recordDialog [data-close="recordDialog"]').click();assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'cancel keeps unsaved correction');
  await p.keyboard.press('Escape');assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'Escape keeps unsaved correction');
  assert.equal(discardPrompts,2,'both exits ask before discarding correction');p.off('dialog',keepDraft);
  assert.equal(await correctionForm.locator('[name=note]').inputValue(),'虚构：孩子独立订正后仍需换题核对');
  assert(await p.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented}),'refresh protects unsaved correction');
  let releaseReceipt;const heldReceipt=new Promise(resolve=>releaseReceipt=resolve);
  const keys=[];await p.route('**/api/record',async route=>{const body=route.request().postDataJSON();keys.push(body.request_key);if(keys.length===1){await route.fetch();await heldReceipt;await route.fulfill({status:503,json:{error:'虚构回执丢失'}})}else await route.continue()});
  await correctionForm.locator('[type=submit]').click();await eventually(async()=>await correctionForm.getAttribute('data-saving')==='yes','correction save in flight');
  await p.locator('#recordDialog [data-close="recordDialog"]').click();assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'unknown save result cannot be discarded');
  await p.keyboard.press('Escape');assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'Escape cannot discard an in-flight correction');
  releaseReceipt();await eventually(async()=>/虚构回执丢失/.test(await p.locator('#recordError').innerText()),'correction receipt lost');
  await correctionForm.locator('[type=submit]').click();await eventually(async()=>!(await p.locator('#recordDialog').evaluate(x=>x.open)),'same correction retry saved');await p.unroute('**/api/record');
  assert.equal(keys.length,2);assert(keys[0]&&keys[0]===keys[1],'retry reuses one request key');
  state=await(await fetch(host.url+'api/state')).json();const corrected=state.records.filter(r=>r.related_record_id===wrongRecords[0].id&&r.followup_kind==='订正');
  assert.equal(corrected.length,1,'lost receipt does not duplicate correction');assert.equal(corrected[0].linked_task_id,id,'correction stays on original homework');
  assert.equal(state.tasks.find(t=>t.id===id).update,null,'correction does not complete homework');
  await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskFeedbackHistory').getByText('孩子独立订正后仍需换题核对').waitFor();
  const panel=p.locator('#taskFeedbackHistory [data-homework-review]').first(),firstAnswerId=Number(await panel.getAttribute('data-homework-review'));await panel.locator(':scope > details > summary').click();assert.equal(await panel.locator(':scope > details').evaluate(x=>x.open),true,'saved photo exposes review');assert.equal(await panel.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').count(),1);
  let calls=0;await p.route('**/api/print/homework/draft',r=>{calls++;const body=r.request().postDataJSON();assert.equal(body.question_sources.length,1);return calls===1?r.fulfill({status:503,json:{error:'虚构模型暂不可用'}}):r.fulfill({json:{draft:{text:'虚构第1题：卷面C，参考B；先找原文依据。',items:1,wrong_items:1,unknown_items:0,coverage:'仅此一页'},question_sha256:'a'.repeat(64)}})});
  assert.match(await p.locator('#taskTitle').innerText(),new RegExp(state.tasks.find(t=>t.id===id).child),'feedback keeps child context');assert.equal(await p.locator('#taskRequirement').innerText(),state.tasks.find(t=>t.id===id).action||'具体要求尚未填写');
  assert.ok((await p.locator('#taskFeedbackHistory h3').boundingBox()).y<(await p.locator('#taskFeedbackFormHeading').boundingBox()).y,'saved work appears before a new blank feedback');assert.equal(await p.locator('.task-saved-originals').count(),0,'answer originals no longer add a disclosure layer');assert.equal(await p.locator('#taskFeedbackHistory [data-feedback-kind=answer] > .upload-item img').first().isVisible(),true,'saved answer photos are directly visible');
  assert.equal(calls,0,'opening saved feedback must not call model');await panel.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').check();await panel.locator('[data-homework-review-run]').click();await eventually(async()=>/虚构模型暂不可用/.test(await panel.innerText()),'model failure retained');
  await panel.locator('[data-homework-review-run]').click();await panel.locator('[data-homework-review-result] textarea').waitFor();assert.equal(calls,2);
  await panel.locator('[data-homework-review-result] textarea').fill('家长核对：第1题卷面C，依据原文应选B。先自己定位关键词，再独立重答。');
  let rerunPrompted=false;const dismissRerun=d=>{rerunPrompted=true;d.dismiss()};p.on('dialog',dismissRerun);
  await panel.locator('[data-homework-review-run]').click();p.off('dialog',dismissRerun);
  assert.equal(rerunPrompted,true,'recheck asks before keeping an edited previous opinion');assert.equal(calls,2,'declined regeneration does not call model');
  assert.match(await panel.locator('[data-homework-review-result] textarea').inputValue(),/家长核对：第1题/);
  p.once('dialog',d=>d.accept());await panel.locator('[data-homework-review-run]').click();await eventually(async()=>calls===3&&await panel.locator('[data-homework-review-previous] textarea').count()===1,'explicit regeneration retains the previous opinion');
  await panel.locator('[data-homework-review-result] textarea').fill('家长核对：第1题卷面C，依据原文应选B。先自己定位关键词，再独立重答。');
  await panel.locator('[data-homework-review-apply]').click();assert.match(await panel.innerText(),/请对照原题核对/);
  await panel.locator('[data-homework-review-confirm]').check();await panel.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').uncheck();
  await panel.locator('[data-homework-review-apply]').click();assert.match(await panel.innerText(),/所选资料、用途、页码或补充已变化/);
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'','changed photo selection cannot stage an old review');
  await panel.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').check();
  let releaseUpload,uploadCalls=0;await p.route('**/api/upload',async route=>{if(++uploadCalls===1)return route.fulfill({status:503,json:{error:'虚构上传失败'}});await new Promise(resolve=>releaseUpload=resolve);await route.continue()});
  await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>/虚构上传失败/.test(await panel.innerText()),'review text upload failure');
  assert.equal(await panel.locator('[data-homework-review-result] textarea').isEnabled(),true,'failed upload restores editable draft');
  assert.equal(await panel.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').isEnabled(),true,'failed upload restores photo choice');
  const applying=panel.locator('[data-homework-review-apply]').click();await eventually(async()=>!!releaseUpload,'review text upload pending');
  assert.equal(await panel.locator('[data-homework-review-result] textarea').isDisabled(),true,'review text cannot change during upload');
  assert.equal(await panel.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').isDisabled(),true,'review photo selection cannot change during upload');
  await p.locator('#taskForm [name=note]').fill('虚构：上传期间补写的观察');
  releaseUpload();await applying;await p.unroute('**/api/upload');
  await eventually(async()=>/请点下方|反馈输入.*变化/.test(await panel.innerText()),'concurrent review upload settled');
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构：上传期间补写的观察','upload completion keeps concurrent parent input');
  assert.match(await panel.innerText(),/反馈输入.*变化/);
  await p.locator('#taskForm [name=note]').fill('');
  await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await panel.innerText()),'review staged after explicit retry');
  assert.match(await p.locator('#taskForm [name=note]').inputValue(),/家长核对的作业批改参考/);
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'review draft stays after declining discard');
  await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'review feedback saved');
  state=await(await fetch(host.url+'api/state')).json();const records=state.records.filter(r=>r.source==='事项:'+id);assert.equal(records.length,2);assert.equal(state.tasks.find(t=>t.id===id).update,null,'grading must not complete homework');
  const photo=records.find(r=>r.id===firstAnswerId).attachments[0],review=records.find(r=>r.note.includes('批改参考'));assert(review.attachments.includes(photo));const report=review.attachments.find(a=>a!==photo);assert.equal(state.uploads.find(a=>a.id===report).mime,'text/plain; charset=utf-8');
  const secondAnswer=await fetch(host.url+'api/task/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({task_id:id,child,day:state.today,request_key:'synthetic-second-answer-'+width,attachments:[photo],note:'虚构第二份独立作答'})});assert.equal(secondAnswer.status,200);const secondAnswerId=(await secondAnswer.json()).record_id;state=await(await fetch(host.url+'api/state')).json();records.push(state.records.find(r=>r.id===secondAnswerId));
  await p.keyboard.press('Escape');await p.reload();await p.locator('[data-task="'+id+'"]').first().click();assert.equal(await p.locator('#taskFeedbackHistory [data-feedback-kind=check] .task-record-files > summary').count(),0,'saved check originals are direct, without another disclosure');await p.locator('#taskFeedbackHistory [data-feedback-kind=check]').first().getByText('作业批改参考', {exact:false}).first().waitFor();
  const firstReview=p.locator('#taskFeedbackHistory [data-homework-review]').nth(0),otherReview=p.locator('#taskFeedbackHistory [data-homework-review]').nth(1);assert.equal(await p.locator('#taskFeedbackHistory [data-homework-review]').count(),2);
  await firstReview.locator(':scope > details').evaluate(x=>x.open=true);await firstReview.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first().check();await firstReview.locator('[data-homework-review-run]').click();await firstReview.locator('[data-homework-review-result] textarea').waitFor();await firstReview.locator('[data-homework-review-result] textarea').fill('');
  await otherReview.locator(':scope > details').evaluate(x=>x.open=true);await otherReview.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first().check();await otherReview.locator('[data-homework-review-run]').click();await otherReview.locator('[data-homework-review-result] textarea').waitFor();
  await otherReview.locator('[data-homework-review-result] textarea').fill('另一份尚未保存的批改意见');
  await p.locator('#taskForm [name=note]').fill('另一条独立反馈');
  let savePrompted=false;const dismissSave=d=>{savePrompted=true;d.dismiss()};p.on('dialog',dismissSave);
  await p.locator('#saveTaskFeedback').click();p.off('dialog',dismissSave);
  assert.equal(savePrompted,true,'saving another feedback asks before discarding a separate AI draft');
  assert.equal(await otherReview.locator('[data-homework-review-result] textarea').inputValue(),'另一份尚未保存的批改意见');
  state=await(await fetch(host.url+'api/state')).json();assert.equal(state.records.filter(r=>r.source==='事项:'+id).length,3,'declined save changes neither answer nor saved opinion');
  await p.locator('#taskForm [name=note]').fill('');
  p.once('dialog',d=>d.dismiss());await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'every feedback review draft requires discard confirmation');
  p.once('dialog',d=>d.dismiss());await p.locator('[data-task-feedback-edit]').first().click();
  assert.equal(await otherReview.locator('[data-homework-review-result] textarea').inputValue(),'另一份尚未保存的批改意见','switch dismissal keeps the other review draft');
  p.once('dialog',d=>d.accept());await p.locator('[data-task-feedback-edit]').first().click();
  await p.locator('#taskForm [name=note]').fill('另一条尚未保存的反馈更正');
  p.once('dialog',d=>d.dismiss());await p.locator('[data-task-feedback-edit]').last().click();
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'另一条尚未保存的反馈更正','switch dismissal keeps edited feedback');
  const switchedId=Number(await p.locator('[data-task-feedback-edit]').last().getAttribute('data-task-feedback-edit'));
  p.once('dialog',d=>d.accept());await p.locator('[data-task-feedback-edit]').last().click();
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),records.find(r=>r.id===switchedId).note,'explicit discard switches to another saved feedback');
  await p.locator('#taskDialog [data-close="taskDialog"]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false,'unchanged feedback closes without warning');
  await p.locator('[data-task="'+id+'"]').first().click();await p.locator('[data-task-feedback-edit]').first().click();
  await p.locator('#taskForm [name=note]').fill('虚构更正但未保存');
  p.once('dialog',d=>d.dismiss());await p.keyboard.press('Escape');
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'Escape dismissal keeps edited feedback');
  p.once('dialog',d=>d.accept());await p.keyboard.press('Escape');
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false,'explicit discard closes');
  await p.locator('[data-task="'+id+'"]').first().click();
  const finalReview=p.locator('#taskFeedbackHistory [data-homework-review]').first();await finalReview.locator(':scope > details').evaluate(x=>x.open=true);
  await finalReview.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first().check();await finalReview.locator('[data-homework-review-run]').click();
  await finalReview.locator('[data-homework-review-result] textarea').waitFor();
  await finalReview.locator('[data-homework-review-result] textarea').fill('家长尚未采纳的独立批改草稿');
  await p.locator('#taskForm [name=note]').fill('虚构另一条实际反馈');
  let acceptedPrompt=false;p.once('dialog',d=>{acceptedPrompt=true;d.accept()});await p.locator('#saveTaskFeedback').click();
  assert.equal(acceptedPrompt,true,'explicit approval allows saving separate feedback');
  await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'separate feedback saved');
  state=await(await fetch(host.url+'api/state')).json();assert.equal(state.records.filter(r=>r.source==='事项:'+id).length,4);
  assert.equal(await finalReview.locator('[data-homework-review-result] textarea').inputValue(),'家长尚未采纳的独立批改草稿','saving separate feedback retains the current unsaved answer review draft');
  assert.equal(state.records.find(r=>r.note==='虚构另一条实际反馈')?.child,child);assert.equal(state.tasks.find(t=>t.id===id).update,null);
  const source=state.records.find(r=>r.id===firstAnswerId);await p.locator('#taskFeedbackHistory [data-homework-review="'+source.id+'"] > details').evaluate(x=>x.open=true);
  const stale=p.locator('#taskFeedbackHistory [data-homework-review="'+source.id+'"]');await stale.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first().check();if(await stale.locator('[data-homework-review-result] textarea:not(:disabled)').count()&&await stale.locator('[data-homework-review-result] textarea').inputValue())p.once('dialog',d=>d.accept());await stale.locator('[data-homework-review-run]').click();await stale.locator('[data-homework-review-result] textarea').waitFor();await stale.locator('[data-homework-review-confirm]').check();await stale.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await stale.innerText()),'review staged before concurrent correction');
  const correction=await fetch(host.url+'api/task/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({task_id:id,child,record_id:source.id,expected_created:source.created,note:'虚构最终作答后来更正'})});assert.equal(correction.status,200);
  p.once('dialog',d=>d.accept());await p.locator('#saveTaskFeedback').click();await eventually(async()=>/原作答已在别处更正/.test(await p.locator('#taskError').innerText()),'stale review rejected');
  state=await(await fetch(host.url+'api/state')).json();assert.equal(state.records.filter(r=>r.source==='事项:'+id).length,4,'rejected review leaves no new record');
  p.once('dialog',d=>d.accept());await p.locator('#taskDialog [data-close="taskDialog"]').click();await p.reload();await p.locator('[data-task="'+id+'"]').first().click();
  const fresh=p.locator('#taskFeedbackHistory [data-homework-review="'+source.id+'"]');await fresh.locator(':scope > details').evaluate(x=>x.open=true);await fresh.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first().check();await fresh.locator('[data-homework-review-run]').click();await fresh.locator('[data-homework-review-result] textarea').waitFor();await fresh.locator('[data-homework-review-confirm]').check();await fresh.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await fresh.innerText()),'fresh review staged');await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'fresh review saved');
  state=await(await fetch(host.url+'api/state')).json();assert.equal(state.records.filter(r=>r.source==='事项:'+id).length,5,'fresh review links to corrected answer');
  const textOnly=state.records.find(r=>r.note==='虚构另一条实际反馈'),textWrong=p.locator('#taskFeedbackHistory [data-task-wrong-form="'+textOnly.id+'"]');
  await textWrong.locator(':scope > summary').click();assert.equal(await textWrong.locator('[data-task-wrong-photo]').count(),0,'written feedback does not require a photo');
  await textWrong.locator('[data-wrong-field="label"]').fill('第3个词');await textWrong.locator('[data-wrong-field="answer"]').fill('窗处');await textWrong.locator('[data-wrong-field="correction"]').fill('窗外');
  const otherWrong=p.locator('#taskFeedbackHistory [data-task-wrong-form="'+source.id+'"]');await otherWrong.locator(':scope > summary').click();await otherWrong.locator('[data-wrong-field="label"]').fill('另一份未保存草稿');
  await textWrong.locator('[data-task-wrong-save]').click();assert.match(await textWrong.innerText(),/另一份作答还有未保存的错题/);
  await otherWrong.locator('[data-wrong-field="label"]').fill('');
  await textWrong.locator('[data-task-wrong-save]').click();await eventually(async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),'manual text-only wrong item saved');
  state=await(await fetch(host.url+'api/state')).json();assert.equal(state.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===id).length,2);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);await p.reload();
  assert.match(await p.locator('[data-query-target="task:'+id+'"] [data-task="'+id+'"]:visible').first().innerText(),/查看\/补充反馈/,'reopened today retains saved-feedback state');assert.deepEqual(errors,[]);
  await p.unroute('**/api/print/homework/draft');
  const photos=[];for(let n=0;n<5;n++){const r=await fetch(host.url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'X-File-Name':'synthetic-complete-'+n+'.png','Content-Type':'application/octet-stream'},body:png});assert.equal(r.status,200);photos.push((await r.json()).attachment.id)}
  const pdf=Buffer.from(await(await fetch(host.url+'attachment/'+encodeURIComponent('演示练习.pdf'))).arrayBuffer());
  const pdfUpload=await fetch(host.url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'X-File-Name':'synthetic-teacher-reference.pdf','Content-Type':'application/octet-stream'},body:pdf});assert.equal(pdfUpload.status,200);const reference=(await pdfUpload.json()).attachment.id;
  const original=await fetch(host.url+'api/task/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({task_id:id,child,day:state.today,request_key:'synthetic-complete-review-'+width,attachments:[...photos,reference],note:'虚构完整题目与独立作答'})});assert.equal(original.status,200);const originalRecord=(await original.json()).record_id;
  await p.reload();await p.locator('[data-task="'+id+'"]').first().click();
  const whole=p.locator('#taskFeedbackHistory [data-homework-review="'+originalRecord+'"]');await whole.locator(':scope > details > summary').click();
  assert.equal(await whole.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').count(),6);assert.equal(await whole.locator('[data-homework-review-pages]').count(),1,'saved teacher PDF supports explicit page selection');
  for(const photo of photos)await whole.locator(' :scope > details > .homework-review-material [data-homework-review-photo][value="'+photo+'"]').check();
  // Display-contract reply only: the fixture PDF stays unselected, so this request did not read 11 pages.
  // Actual 11-page selection is checked in test_homework_review.py and the separate private UI audit.
  const partialCoverage='题目/孩子作答《虚构显示契约.pdf》：共11页，本次第1-7页；未读取页：8-11。';
  const completeReviewText='虚构：第1题表达不完整，缺少题目要求的具体特点；参考PDF未参与。\n实际读取范围（程序核对）：\n'+partialCoverage;
  let completeCalls=0;await p.route('**/api/print/homework/draft',r=>{const body=r.request().postDataJSON();assert.equal(body.purpose,'review');assert.deepEqual(body.question_sources.map(x=>x.id),photos);completeCalls++;return completeCalls===1?r.fulfill({status:503,json:{error:'虚构完整批改暂不可用'}}):r.fulfill({json:{draft:{text:completeReviewText,items:1,wrong_items:1,unknown_items:0,coverage:'五张所选照片；参考PDF未参与\n实际读取范围：'+partialCoverage,questions:[{label:'第1题',judgment:'incorrect',student_answer:'很好',answer:'写出具体特点',error_reason:'缺少题目要求的具体特点'}]},question_sha256:'b'.repeat(64)}})});
  await whole.locator('[data-homework-review-run]').click();await eventually(async()=>/虚构完整批改暂不可用/.test(await whole.innerText()),'five-image review failure keeps originals');
  assert.equal(await whole.locator(' :scope > details > .homework-review-material [data-homework-review-photo]:checked').count(),5);
  await whole.locator('[data-homework-review-run]').click();await whole.locator('[data-homework-review-result] textarea').waitFor({state:'attached'});assert.equal(completeCalls,2);
  const visibleCoverage=whole.locator('[data-homework-review-coverage]');assert.equal(await visibleCoverage.isVisible(),true);assert.ok((await visibleCoverage.innerText()).includes(partialCoverage),'known total, selected and unread PDF pages are visible without opening the full opinion');
  assert.equal(await whole.locator('[data-homework-review-result] textarea').evaluate(x=>x.closest('details').open),false,'structured questions keep the complete opinion collapsed');assert.equal(await whole.locator('[data-homework-review-result] textarea').isVisible(),false);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await whole.locator('[data-homework-review-result]').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'complete-review-'+width+'.png')})}
  await whole.locator('[data-homework-review-confirm]').check();await whole.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await whole.innerText()),'five-image review staged');await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'five-image basis feedback saved');
  state=await(await fetch(host.url+'api/state')).json();const full=state.records.find(r=>r.note.includes('原作答反馈 #'+originalRecord+'。'));assert(full&&photos.every(x=>full.attachments.includes(x)));assert(!full.attachments.includes(reference),'unused teacher PDF is not claimed as grading basis');assert.deepEqual(state.printing.jobs.map(j=>j.id).sort(),printIdsBeforeChecks,'checking homework never prints');
  await p.reload();await p.locator('[data-task="'+id+'"]').first().click();await eventually(async()=>await p.locator('[data-saved-homework-review="'+full.id+'"] [data-saved-review-text]').innerText()===completeReviewText,'saved five-image opinion and partial range reopen as visible text');assert.equal(await p.locator('[data-saved-homework-review="'+full.id+'"] [data-saved-review-text]').isVisible(),true);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);assert.deepEqual(errors,[]);
  await p.unroute('**/api/print/homework/draft');
  // Reuse saved synthetic answers and their sibling PDF; no extra records affect the checks above.
  const delayedRecords=[source.id,secondAnswerId],sourcesPattern='**/api/print/homework/sources?**';
  for(const outcome of ['failure','success']){
   const sourceGates=new Map();let releaseDraft,releaseUpload,lateCalls=0,uploadPending=false;
   const draftGate=new Promise(resolve=>releaseDraft=resolve),uploadGate=new Promise(resolve=>releaseUpload=resolve);
   await p.route(sourcesPattern,async route=>{
    const recordId=Number(new URL(route.request().url()).searchParams.get('record_id'));
    if(!delayedRecords.includes(recordId))return route.continue();
    const response=await route.fetch(),value=await response.json();
    assert(value.sources.some(a=>a.id===reference),'both saved answers can reuse the sibling teacher PDF');
    await new Promise(resolve=>sourceGates.set(recordId,resolve));await route.fulfill({response,json:value});
   });
   await p.route('**/api/print/homework/draft',async route=>{
    const body=route.request().postDataJSON();assert.equal(body.record_id,source.id);assert.equal(body.question_sources.length,1);assert.deepEqual(body.reference_sources,[]);lateCalls++;
    await draftGate;
    return outcome==='failure'?route.fulfill({status:503,json:{error:'虚构迟到资料检查失败'}}):route.fulfill({json:{draft:{text:'虚构迟到资料检查成功；本次仅核对原作答。',items:1,wrong_items:0,unknown_items:1,coverage:'仅此一页'},question_sha256:'e'.repeat(64)}});
   });
   if(outcome==='success')await p.route('**/api/upload',async route=>{uploadPending=true;await uploadGate;await route.continue()});
   try{
    await p.reload();await p.locator('[data-task="'+id+'"]').first().click();
    const latePanels=delayedRecords.map(recordId=>p.locator('#taskFeedbackHistory [data-homework-review="'+recordId+'"]'));
    for(const latePanel of latePanels){await latePanel.locator(':scope > details').evaluate(x=>x.open=true);await latePanel.locator('[data-homework-review-sources]').evaluate(x=>x.parentElement.open=true)}
    await eventually(async()=>sourceGates.size===2,'both source responses held before generation');
    const originalChoice=latePanels[0].locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first();
    await originalChoice.check();await latePanels[0].locator('[data-homework-review-run]').click();await eventually(async()=>lateCalls===1,'generation started before sources return');
    sourceGates.get(source.id)();if(outcome==='failure')sourceGates.get(secondAnswerId)();
    const returnedPanels=outcome==='failure'?latePanels:[latePanels[0]];
    for(const latePanel of returnedPanels)await latePanel.locator('[data-homework-review-sources] [data-review-source="'+reference+'"]').waitFor();
    assert.equal(await latePanels[0].locator('[data-homework-review-run]').isDisabled(),true,'source responses arrive while generation is still pending');
    releaseDraft();await eventually(async()=>await latePanels[0].locator('[data-homework-review-run]').isEnabled(),'generation releases busy controls after '+outcome);
    const reviewText=latePanels[0].locator('[data-homework-review-result] textarea');
    if(outcome==='failure'){assert.match(await latePanels[0].innerText(),/虚构迟到资料检查失败/);assert.equal(await reviewText.count(),0)}else{await reviewText.waitFor();await reviewText.fill('虚构：迟到资料恢复后仍保留已编辑批改草稿')}
    const checkEditable=async latePanel=>{
     const material=latePanel.locator('[data-homework-review-sources] [data-review-source="'+reference+'"]'),choice=material.locator('[data-homework-review-photo]'),role=material.locator('[data-homework-review-role]'),pages=material.locator('[data-homework-review-pages]');
     for(const control of [choice,role,pages])assert.equal(await control.isEnabled(),true,'late source controls restored after '+outcome);
     await choice.check();await material.locator('details').evaluate(x=>x.open=true);await role.selectOption('reference');await pages.fill('1');
     assert.equal(await choice.isChecked(),true);assert.equal(await role.inputValue(),'reference');assert.equal(await pages.inputValue(),'1');await choice.uncheck();
    };
    for(const latePanel of returnedPanels)await checkEditable(latePanel);
    if(outcome==='success'){
     await latePanels[0].locator('[data-homework-review-confirm]').check();await latePanels[0].locator('[data-homework-review-apply]').click();await eventually(async()=>uploadPending,'review text upload started before sibling sources return');
     sourceGates.get(secondAnswerId)();const siblingMaterial=latePanels[1].locator('[data-homework-review-sources] [data-review-source="'+reference+'"]');await siblingMaterial.waitFor();
     assert.equal(await siblingMaterial.locator('[data-homework-review-photo]').isDisabled(),true,'sibling source freezes during review text upload');
     releaseUpload();await eventually(async()=>/请点下方/.test(await latePanels[0].innerText()),'review text upload completed');await checkEditable(latePanels[1]);
    }
    assert.equal(await originalChoice.isChecked(),true,'late sources keep the selected original answer');
    if(outcome==='success'){assert.equal(await reviewText.inputValue(),'虚构：迟到资料恢复后仍保留已编辑批改草稿');p.once('dialog',d=>d.accept())}
    await p.locator('#taskDialog [data-close="taskDialog"]').click();assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false);
   }finally{releaseDraft();releaseUpload();for(const release of sourceGates.values())release();await p.unroute(sourcesPattern);await p.unroute('**/api/print/homework/draft');if(outcome==='success')await p.unroute('**/api/upload')}
  }
  // Calibration-only regression: fixed model raw, real shared validator and real save endpoints.
  // The synthetic image is readable fixture material; this does not test OCR or model accuracy.
  const readCause=async()=>await(await fetch(host.url+'api/state')).json();state=await readCause();
  const causeTask=(await post('api/task/new',{child,title:'虚构错因独立校验 '+width,category:'homework',action:'虚构错因独立校验：虚构甲卷第1题，2+3=?，对照本卷教师参考核对最终作答。',due:state.today})).task;
  const openCause=async()=>{await p.locator('nav [data-page=tasks]').click();await p.locator('body[data-page=tasks] #task-group-homework').waitFor();await p.locator('[data-task-box=Inbox]').click();await p.locator('#content [data-task="'+causeTask.id+'"]:visible').first().click();await p.locator('#taskDialog[open]').waitFor()};
  const sheet=await browser.newPage({viewport:{width:500,height:240}});
  await sheet.setContent('<html><body style="font:24px sans-serif;background:white;color:black"><h2>SYNTHETIC PAPER A</h2><p>Question 1: 2 + 3 = ?</p><p>Student final answer: 4</p></body></html>');
  const causeImage=await sheet.screenshot();await sheet.close();await p.reload();await openCause();
  await p.locator('#taskForm [name=note]').fill('虚构甲卷第1题，完整题面2+3=?，孩子最终作答4。');
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-cause-answer-'+width+'.png',mimeType:'image/png',buffer:causeImage});await p.locator('#pendingUploads img').waitFor();
  const teacherName='synthetic-cause-teacher-'+width+'.txt';
  await p.locator('#fileInput').setInputFiles({name:teacherName,mimeType:'text/plain',buffer:Buffer.from('虚构甲卷第1题：2+3=5。\n')});await p.locator('#pendingUploads').getByRole('link',{name:teacherName,exact:true}).waitFor();
  const causeOriginal=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  state=await readCause();const originalCauseRecord=state.records.find(r=>r.id===causeOriginal.record_id),causeSources=originalCauseRecord.attachments.map(id=>state.uploads.find(a=>a.id===id));
  const causePhoto=causeSources.find(a=>a.mime==='image/png'),causeTeacher=causeSources.find(a=>a.name===teacherName);assert(causePhoto&&causeTeacher);
  const causePanel=p.locator('#taskFeedbackHistory [data-homework-review="'+causeOriginal.record_id+'"]');if(!await causePanel.locator(':scope > details').evaluate(x=>x.open))await causePanel.locator(':scope > details > summary').click();
  await causePanel.locator('[data-review-source="'+causePhoto.id+'"] [data-homework-review-photo]').check();
  const teacherRow=causePanel.locator('[data-review-source="'+causeTeacher.id+'"]');await teacherRow.waitFor();assert.equal(await teacherRow.locator('[data-homework-review-role]').inputValue(),'reference');await teacherRow.locator('[data-homework-review-photo]').check();
  const validatorBefore=await(await fetch(host.url+'__fixture/cause-validator')).json();let causeReply,causeRequest;
  await p.route('**/api/print/homework/draft',async route=>{causeRequest=route.request().postDataJSON();const response=await route.fetch();assert.equal(response.status(),200);causeReply=await response.json();await route.fulfill({response,json:causeReply})});
  await causePanel.locator('[data-homework-review-run]').click();await eventually(async()=>!!causeReply,'real validator response');await p.unroute('**/api/print/homework/draft');
  assert.deepEqual(causeRequest.question_sources,[{type:'upload',id:causePhoto.id}]);assert.deepEqual(causeRequest.reference_sources,[{type:'upload',id:causeTeacher.id}]);assert.deepEqual(causeRequest.previous_sources,[]);
  assert.equal(causeReply.draft.items,1);assert.equal(causeReply.draft.wrong_items,1);assert.equal(causeReply.draft.unknown_items,0);
  const causeQuestion=causeReply.draft.questions[0];assert.equal(causeQuestion.judgment,'incorrect');assert.equal(causeQuestion.question,'虚构甲卷第1题：2+3=?');assert.equal(causeQuestion.student_answer,'4');assert.equal(causeQuestion.answer,'教师参考：5');assert.equal(causeQuestion.possible_cause,'');assert.equal(causeQuestion.uncertainty,'');assert(causeQuestion.error_reason&&causeQuestion.steps);
  const validatorAfter=await(await fetch(host.url+'__fixture/cause-validator')).json();assert(validatorAfter.synthetic_only&&validatorAfter.shared_validator);assert.equal(validatorAfter.real_model_calls,0);assert.equal(validatorAfter.calls.length,validatorBefore.calls.length+1);assert.deepEqual(validatorAfter.calls.at(-1).validated,causeReply.draft);assert.equal(validatorAfter.calls.at(-1).raw.items[0].possible_cause,'');assert.equal(validatorAfter.calls.at(-1).raw.items[0].question_kind,'objective');
  await eventually(async()=>/1题 · 1题需订正 · 0题未判定/.test(await causePanel.locator('[data-homework-review-status]').innerText()),'verified error survives unknown cause');assert.match(await causePanel.locator('.homework-review-questions').innerText(),/需要订正/);
  assert.equal((await readCause()).records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===causeTask.id).length,0,'AI draft does not automatically create a wrong item');
  await causePanel.locator('[data-homework-review-confirm]').check();await causePanel.locator('[data-homework-review-apply]').click();await eventually(async()=>/请点下方/.test(await causePanel.innerText()),'validated result staged for explicit save');
  const causeReview=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  state=await readCause();const savedCauseReview=state.records.find(r=>r.id===causeReview.record_id);assert.equal(savedCauseReview.related_record_id,causeOriginal.record_id);assert.equal(savedCauseReview.followup_kind,'作业检查');
  assert.equal(state.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===causeTask.id).length,0,'saving a reviewed opinion still does not create a wrong item automatically');
  const causeWrong=p.locator('#taskFeedbackHistory [data-task-wrong-form="'+causeOriginal.record_id+'"]');await causeWrong.locator(':scope > summary').click();
  await causeWrong.locator('[data-wrong-field=label]').fill('虚构甲卷第1题');await causeWrong.locator('[data-wrong-field=text]').fill('2+3=?');await causeWrong.locator('[data-wrong-field=answer]').fill('4');await causeWrong.locator('[data-wrong-field=correction]').fill('5');
  const causeWrongSaved=await threeAttemptSave(p,'/api/wrong/save',causeWrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await causeWrong.innerText()),async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  const causeWrongCard=p.locator('#taskFeedbackHistory .task-feedback-record').filter({has:p.locator('[data-record="'+causeWrongSaved.record_id+'"]')});await causeWrongCard.locator('[data-followup]').click();await p.locator('#recordDialog[open]').waitFor();
  const causeCorrectionForm=p.locator('#recordForm'),causeCorrectionNote='虚构：第1题已订正为5；错因未确认，独立复测待做。';assert.equal(await causeCorrectionForm.locator('[name=followup_kind]').inputValue(),'订正');assert.equal(await causeCorrectionForm.locator('[name=related_record_id]').inputValue(),String(causeWrongSaved.record_id));await causeCorrectionForm.locator('[name=note]').fill(causeCorrectionNote);
  const causeCorrection=await threeAttemptSave(p,'/api/record',causeCorrectionForm.locator('[type=submit]'),async()=>/虚构/.test(await p.locator('#recordError').innerText()),async()=>!await p.locator('#recordDialog').evaluate(x=>x.open),readCause);
  await p.reload();await openCause();await p.locator('#taskFeedbackHistory').getByText(causeCorrectionNote,{exact:false}).waitFor();
  const reopenedCause=p.locator('[data-saved-homework-review="'+causeReview.record_id+'"] [data-saved-review-text]');await eventually(async()=>await reopenedCause.innerText()===causeReply.draft.text,'real calibrated opinion reopens unchanged');assert.match(await reopenedCause.innerText(),/卷面作答：4/);assert.match(await reopenedCause.innerText(),/教师参考：5/);
  state=await readCause();const finalWrong=state.records.find(r=>r.id===causeWrongSaved.record_id),finalCorrection=state.records.find(r=>r.id===causeCorrection.record_id);assert.equal(finalWrong.related_record_id,causeOriginal.record_id);assert.equal(finalCorrection.related_record_id,finalWrong.id);for(const r of [finalWrong,finalCorrection]){assert.equal(r.child,child);assert.equal(r.linked_task_id,causeTask.id)}assert.equal(finalCorrection.followup_kind,'订正');assert.equal(state.tasks.find(t=>t.id===causeTask.id).update,null);assert.deepEqual(state.printing.jobs.map(j=>j.id).sort(),printIdsBeforeChecks);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'cause-validator-'+width+'.json'),JSON.stringify({scope:'mock raw through real shared validator; not OCR/model accuracy',request:causeRequest,validator:validatorAfter.calls.at(-1),feedback:causeReview,wrong:causeWrongSaved,correction:causeCorrection},null,2));await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'cause-reopened-'+width+'.png')})}
  // Unit identity uses mock raw selection through the real shared guard and automatic-save transaction.
  await p.locator('#taskDialog [data-close="taskDialog"]').click();assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false);
  const unitResponse=await fetch(host.url+'__fixture/unit-identity?width='+width),unit=await unitResponse.json();assert.equal(unitResponse.status,200,JSON.stringify(unit));
  assert(unit.synthetic_only&&unit.shared_guard&&unit.classification_preserved_sources&&unit.wrong_preserved_canonical&&unit.accepted_original_preserved);assert.equal(unit.real_model_calls,0);assert.equal(unit.calls.length,3);assert.equal(unit.wrong_state,'review');assert.equal(unit.correct_state,'ready');assert.match(unit.title,/Unit30/);assert.match(unit.action,/只补Unit 30朗读/);assert(!unit.action.includes('只补Unit3朗读'));
  const readUnit=readCause,openUnit=async()=>{await p.locator('nav [data-page=tasks]').click();await p.locator('body[data-page=tasks] #task-group-homework').waitFor();await p.locator('[data-task-box=Inbox]').click();await p.locator('#content [data-task="'+unit.task_id+'"]:visible').first().click();await p.locator('#taskDialog[open]').waitFor()};
  await p.reload();await openUnit();assert.equal(await p.locator('#taskRequirement').innerText(),unit.action);assert.match(await p.locator('#taskTitle').innerText(),/Unit30/);
  const unitFeedbackNote='虚构Unit30反馈：保留原朗读要求，第1个词读音需订正。';await p.locator('#taskForm [name=note]').fill(unitFeedbackNote);
  await p.locator('#taskDialog [data-school-original-ref="'+unit.original_ref+'"]:visible').first().click();await p.locator('#schoolOriginalDialog[open]').waitFor();await eventually(async()=> (await p.locator('#schoolOriginalDialog').innerText()).includes(unit.original_text),'Unit original message loaded');
  await p.locator('#schoolOriginalDialog [data-school-original-close]').click();assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true);assert.equal(await p.locator('#taskForm [name=note]').inputValue(),unitFeedbackNote,'original-message preview preserves this task feedback draft');
  const unitBefore=await readUnit(),unitTaskBefore=unitBefore.tasks.find(t=>t.id===unit.task_id);assert.equal(unitTaskBefore.update,null);assert.equal(unitTaskBefore.agenda.due_on,unit.due);assert(unitTaskBefore.source.includes(unit.original_ref)&&unitTaskBefore.source.includes('message:'+unit.source_id+':3'));assert(!unitTaskBefore.source.includes('message:'+unit.source_id+':2'));
  const unitFeedback=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readUnit);
  const unitWrong=p.locator('#taskFeedbackHistory [data-task-wrong-form="'+unitFeedback.record_id+'"]');await unitWrong.locator(':scope > summary').click();assert.equal(await unitWrong.locator('[data-task-wrong-photo]').count(),0);
  await unitWrong.locator('[data-wrong-field=label]').fill('Unit30第1个词读音');await unitWrong.locator('[data-wrong-field=answer]').fill('读音A（虚构）');await unitWrong.locator('[data-wrong-field=correction]').fill('读音B（虚构）');
  const unitWrongSaved=await threeAttemptSave(p,'/api/wrong/save',unitWrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await unitWrong.innerText()),async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),readUnit);
  const unitWrongCard=p.locator('#taskFeedbackHistory .task-feedback-record').filter({has:p.locator('[data-record="'+unitWrongSaved.record_id+'"]')});await unitWrongCard.locator('[data-followup]').click();await p.locator('#recordDialog[open]').waitFor();
  const unitForm=p.locator('#recordForm'),unitCorrectionNote='虚构Unit30订正：第1个词重读，后续独立复测待做。';assert.equal(await unitForm.locator('[name=followup_kind]').inputValue(),'订正');assert.equal(await unitForm.locator('[name=related_record_id]').inputValue(),String(unitWrongSaved.record_id));await unitForm.locator('[name=note]').fill(unitCorrectionNote);
  const unitCorrection=await threeAttemptSave(p,'/api/record',unitForm.locator('[type=submit]'),async()=>/虚构/.test(await p.locator('#recordError').innerText()),async()=>!await p.locator('#recordDialog').evaluate(x=>x.open),readUnit);
  await p.reload();await openUnit();assert.equal(await p.locator('#taskRequirement').innerText(),unit.action);await p.locator('#taskFeedbackHistory').getByText(unitFeedbackNote,{exact:false}).waitFor();await p.locator('#taskFeedbackHistory').getByText(unitCorrectionNote,{exact:false}).waitFor();await p.locator('#taskFeedbackHistory').getByText('Unit30第1个词读音',{exact:false}).waitFor();
  const unitAfter=await readUnit();assert.deepEqual(unitAfter.tasks.find(t=>t.id===unit.task_id),unitTaskBefore,'feedback, wrong item and correction do not complete or alter the canonical school task');assert.equal(unitAfter.records.length,unitBefore.records.length+3);assert.deepEqual(unitAfter.printing.jobs.map(j=>j.id).sort(),printIdsBeforeChecks);
  const unitWrongRecord=unitAfter.records.find(r=>r.id===unitWrongSaved.record_id),unitCorrectionRecord=unitAfter.records.find(r=>r.id===unitCorrection.record_id);assert.equal(unitWrongRecord.related_record_id,unitFeedback.record_id);assert.equal(unitCorrectionRecord.related_record_id,unitWrongSaved.record_id);for(const r of [unitWrongRecord,unitCorrectionRecord]){assert.equal(r.child,child);assert.equal(r.linked_task_id,unit.task_id)}assert.equal(unitCorrectionRecord.followup_kind,'订正');
  const unitRepeated=await fetch(host.url+'__fixture/unit-identity?width='+width);assert.equal(unitRepeated.status,200);assert.deepEqual(await unitRepeated.json(),unit,'repeated fixture reads preserve source rows, accepted decision and the same task identifier');assert.equal((await(await fetch(host.url+'__fixture/cause-validator')).json()).calls.length,validatorAfter.calls.length,'manual Unit flow adds no homework model call');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'unit-identity-'+width+'.json'),JSON.stringify({scope:'mock raw school selection through real shared guard and auto-save; not model accuracy',fixture:unit,feedback:unitFeedback,wrong:unitWrongSaved,correction:unitCorrection},null,2));await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'unit-reopened-'+width+'.png')})}
  assert.deepEqual(errors,[]);await p.close();
 }
 console.log('Homework feedback AI review: 360/1440 save, retry, reopen, task status and source preserved');
}catch(error){
 if(process.env.HOMEWORK_QUICK_PROOF_DIR&&lastPage&&!lastPage.isClosed()){
  const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.HOMEWORK_QUICK_PROOF_DIR,{recursive:true});
  await lastPage.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'failure.png')});
  await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'failure-state.json'),JSON.stringify(await lastPage.evaluate(()=>({page:document.body.dataset.page,ready:document.querySelector('#content')?.dataset.ready,selected:[...document.querySelectorAll('[data-child-filter][aria-pressed=true]')].map(x=>x.dataset.childFilter),tasks:[...document.querySelectorAll('[data-task]')].map(x=>x.dataset.task),text:document.body.innerText})),null,2));
 }
 throw error;
}finally{try{if(browser){let closed=false;await Promise.race([browser.close().then(()=>closed=true),delay(5000)]);if(!closed)console.error('Synthetic browser cleanup timed out; server cleanup still runs')}}finally{await host?.stop()}}})().catch(e=>{console.error(e);process.exitCode=1});
