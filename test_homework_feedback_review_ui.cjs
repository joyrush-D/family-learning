// Disposable synthetic family only: one saved answer photo -> explicit AI draft -> reviewed feedback.
const assert=require('node:assert/strict');
// The served bundle keeps app helpers private, so compare the page with the exact scope display helper from app.js.
const scopeText=require('node:vm').runInNewContext(/^function homeworkReviewScopeText\(.*\n(?:.*\n)*?\}$/m.exec(require('node:fs').readFileSync(require('node:path').join(__dirname,'app.js'),'utf8'))[0]+'\nhomeworkReviewScopeText');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
// The stage line under the count, the note under the fill button and the right-hand save status, read together with the count.
const reviewStage=panel=>panel.evaluate(el=>{const result=el.querySelector('[data-homework-review-result]');return {stage:result.querySelector('.homework-review-stage')?.textContent??null,hint:result.querySelector('.homework-review-next>p')?.textContent??null,questions:!!result.querySelector('.homework-review-questions'),counts:result.querySelector('.homework-review-counts')?.textContent??null,status:document.querySelector('#taskFeedbackStatus').textContent}});
// After filling, the unsaved note and the original save button must both be whole, at least 12px clear (outside the button's focus ring), where a parent can see them: the viewport, the modal task dialog and every clipping ancestor inside it, above its sticky close bar.
const savePairView=page=>page.evaluate(()=>{const nodes=['#taskFeedbackStatus','#saveTaskFeedback'].map(s=>document.querySelector(s)),dialog=document.querySelector('#taskDialog'),box={top:0,left:0,bottom:innerHeight,right:innerWidth};
 for(let x=nodes[1].parentElement;x&&x!==dialog.parentElement;x=x.parentElement){const s=getComputedStyle(x);if(x===dialog||s.overflowX!=='visible'||s.overflowY!=='visible'){const r=x.getBoundingClientRect(),top=r.top+x.clientTop,left=r.left+x.clientLeft;box.top=Math.max(box.top,top);box.left=Math.max(box.left,left);box.bottom=Math.min(box.bottom,top+x.clientHeight);box.right=Math.min(box.right,left+x.clientWidth)}}
 const bar=dialog.querySelector(':scope>form>.actions');if(bar&&!bar.contains(nodes[1])&&getComputedStyle(bar).position==='sticky')box.bottom=Math.min(box.bottom,bar.getBoundingClientRect().top);
 const style=getComputedStyle(nodes[1]),ring=style.outlineStyle==='none'?0:parseFloat(style.outlineWidth)+Math.max(0,parseFloat(style.outlineOffset)||0),gap=12,rects=nodes.map((n,i)=>{const r=n.getBoundingClientRect(),e=i?ring:0;return {top:r.top-e,left:r.left-e,bottom:r.bottom+e,right:r.right+e}});
 return {box,rects,ring,gap,focus:document.activeElement?.id,modal:dialog.matches(':modal'),inside:dialog.matches(':modal')&&nodes.every(n=>dialog.contains(n))&&rects.every(r=>r.bottom>r.top&&r.top>=box.top+gap-.5&&r.left>=box.left+gap-.5&&r.bottom<=box.bottom-gap+.5&&r.right<=box.right-gap+.5)}});
async function eventually(fn,label){for(let n=0;n<250;n++){if(await fn())return;await delay(40)}throw Error('Timed out: '+label)}
function assertDraftReceipt(validated,draft){
 const {continuation,...fields}=draft;assert.deepEqual(validated,fields);
 assert.match(continuation.scope_sha256,/^[a-f0-9]{64}$/);
 assert.deepEqual(continuation.pending_labels,draft.questions.filter(q=>q.judgment==='unknown').map(q=>q.label));
}
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
 const setup=`import runpy,sys,json,copy,hashlib
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
import app
cause_raw=dict(items=[dict(label='虚构甲卷第1题',question='虚构甲卷第1题：2+3=?',student_answer='4',answer='教师参考：5',judgment='incorrect',question_kind='objective',error_reason='卷面作答4与核对答案5不同。',possible_cause='',steps='先独立重算2+3，再对照核对答案。',uncertainty='')],coverage='仅虚构甲卷第1题，其余未检查。')
consistency_raw=dict(items=[
    dict(label='虚构乙卷第1题',question='虚构乙卷第1题：2+3=?',student_answer='',answer='教师参考：5',judgment='unknown',question_kind='objective',error_reason='',possible_cause='',steps='',uncertainty='答题格空白，未能确认作答。'),
    dict(label='虚构乙卷第2题',question='虚构乙卷第2题：6-2=?',student_answer='3',answer='教师参考：4',judgment='incorrect',question_kind='objective',error_reason='作答3与教师参考4不同。',possible_cause='',steps='',uncertainty=''),
    dict(label='虚构乙卷第3题',question='虚构乙卷第3题：1+1=?',student_answer='2',answer='教师参考：2',judgment='correct',question_kind='objective',error_reason='',possible_cause='',steps='',uncertainty=''),
    dict(label='虚构乙卷第4题',question='虚构选择题：选择正确字母。',student_answer='C',answer='教师参考：B',judgment='correct',question_kind='objective',error_reason='',possible_cause='',steps='',uncertainty='')],
    coverage='第1题正确；作文未提供，超出本批材料。',comparison='后补老师参考后，第1题保持正确，整卷检查完成。')
cause_calls=[]
origin_calls=[]
coverage_calls=[]
validator=app.family_llm.homework_reference_draft
def mock_chat(messages,schema,name,timeout,**kwargs):
    assert app.DATA.name.startswith('family-demo-') and name=='family_homework_reference'
    content=messages[-1]['content']
    texts=[part['text'] for part in content if part.get('type')=='text']
    if any('虚构漏题覆盖' in text for text in texts):
        assert 'question_labels' in schema['required'] and schema['properties']['question_labels']['maxItems']==25
        assert any('题目/孩子作答原文' in text and '孩子作答5' in text and '孩子作答3' in text for text in texts)
        assert any('教师参考原文' in text and '第1题5' in text and '第2题4' in text for text in texts)
        first=dict(label='虚构甲卷第1题',question='2+3=?',student_answer='5',answer='教师参考：5',judgment='correct',question_kind='objective',error_reason='',possible_cause='',steps='',uncertainty='')
        raw=dict(question_labels=['虚构甲卷第1题','虚构甲卷第2题'],items=[first],coverage='第1、2题均正确，全卷已经核对完成。',comparison='第1、2题均正确，全卷已经核对完成。')
        if any(text.startswith('家长本次补充') and '再次漏列' in text for text in texts):
            raw['question_labels']=[first['label']]
        if any(text.startswith('家长本次补充') and '补查第2题' in text for text in texts):
            assert any(text.startswith('上一轮待复核意见原文') and '虚构甲卷第2题' in text and '未判定' in text for text in texts)
            raw['items'].append(dict(first,label='虚构甲卷第2题',question='6-2=?',student_answer='3',answer='教师参考：4',judgment='incorrect',error_reason='孩子作答3与教师参考4不同。'))
        coverage_calls.append(dict(raw=raw,original=copy.deepcopy(raw),texts=texts,image_count=sum(part.get('type')=='image_url' for part in content)))
        return raw
    if any('虚构来源身份' in text for text in texts):
        raw=copy.deepcopy(cause_raw)
        raw['items'][0].update(label='虚构身份甲卷第1题',question='虚构身份甲卷第1题：2+3=?')
        raw['coverage']='仅虚构身份甲卷第1题，未检查其余题目。'
        if any(text.startswith('上一轮待复核意见原文') for text in texts):
            raw['comparison']='复核原照片和教师原参考后，仍需订正第1题；旧AI意见仅供对照。'
        origin_calls.append(dict(raw=raw,original=copy.deepcopy(raw),texts=texts,image_count=sum(part.get('type')=='image_url' for part in content)))
        return raw
    if any('虚构结论一致' in text for text in texts):
        raw=consistency_raw
        assert any('教师参考原文' in text and '2+3=5' in text and '6-2=4' in text and '第4题B' in text for text in texts)
        assert any('原作答家长说明' in text and '第1题空白' in text for text in texts)
    else:
        raw=cause_raw
        assert any('虚构错因独立校验' in text and '2+3' in text for text in texts)
        assert any('教师参考原文' in text and '2+3=5' in text for text in texts)
        assert any('原作答家长说明' in text and '最终作答4' in text for text in texts)
    assert sum(part.get('type')=='image_url' for part in content)==1
    cause_calls.append(dict(raw=copy.deepcopy(raw),original=copy.deepcopy(raw)))
    return cause_calls[-1]['raw']
def traced_validator(*args,**kwargs):
    if '虚构漏题覆盖' in kwargs.get('task_action',''):
        result=validator(*args,**kwargs)
        assert coverage_calls[-1]['raw']==coverage_calls[-1]['original']
        coverage_calls[-1]['validated']=copy.deepcopy(result)
        return result
    if '虚构来源身份' in kwargs.get('task_action',''):
        result=validator(*args,**kwargs)
        call=origin_calls[-1]
        assert call['raw']==call['original']
        call['inputs']=dict(images=[dict(mime=image['mime'],sha256=hashlib.sha256(image['data']).hexdigest()) for image in args[0]],
            reference_image_count=len(kwargs.get('reference_images',())),question_documents=copy.deepcopy(kwargs.get('question_documents',())),
            reference_documents=copy.deepcopy(kwargs.get('reference_documents',())),previous_documents=copy.deepcopy(kwargs.get('previous_documents',())),
            previous_text=kwargs.get('previous_text',''),task_action=kwargs['task_action'],answer_note=kwargs.get('answer_note',''))
        call['validated']=copy.deepcopy(result)
        return result
    result=validator(*args,**kwargs)
    assert cause_calls[-1]['raw']==cause_calls[-1]['original']
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
    def classify(index,text,title,change='new',target='',deadline='',goal=''):
        with store._db() as c:
            prior=c.execute('SELECT cursor FROM agent_sources WHERE id=?',(source['id'],)).fetchone()
        message=dict(id=str(index),time=now.isoformat(),kind='text',sender='虚构英语老师',sender_id='synthetic-unit-teacher-'+str(width),text=text,unread=False)
        store.ingest(dict(source_id=source['id'],expected_cursor=prior['cursor'] if prior else '',cursor=str(index),checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[message]))
        with store._db() as c:
            before_messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages WHERE source_id=? ORDER BY id',(source['id'],))]
            before_source=dict(c.execute('SELECT * FROM agent_sources WHERE id=?',(source['id'],)).fetchone())
        ref='message:'+source['id']+':'+str(index)
        evidence=[dict(message,ref=ref,publisher=agent._publisher(source['id'],message),content_incomplete=False)]
        raw=dict(proposals=[school_proposal(title_quote=text,due=deadline,evidence=[dict(ref=ref)],learning_subject='英语',task_title=title,task_goal=goal or text,task_state='ready',task_reason='虚构明确原文。',task_change=change,task_target_id=target,task_purpose='learning')])
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
    original_goal='Unit30课文读两遍，朗读录音上传班级作业区，明天完成。'
    original_text='谁有英语课本照片，发一下。'+original_goal
    original=classify(1,original_text,'英语：Unit30朗读 '+str(width),deadline=due,goal=original_goal)
    with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('ready school action auto-collects without another model')):
        agent._refresh_school(app,store,now,0)
    with store._db() as c:accepted=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())
    assert accepted['state']=='accepted' and json.loads(accepted['plan'])['school_task']['auto_added']
    task_id=accepted['task_id'];original_task=task(task_id)
    assert original_task['action']==original_goal and '谁有' not in original_task['title']+original_task['action'],'mixed resource prefix cannot overwrite homework'
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
    if self.path=='/__fixture/question-coverage':
        assert app.DATA.name.startswith('family-demo-')
        return self.reply(200,dict(synthetic_only=True,shared_validator=True,real_model_calls=0,calls=coverage_calls))
    if self.path=='/__fixture/cause-validator':
        assert app.DATA.name.startswith('family-demo-')
        return self.reply(200,dict(synthetic_only=True,shared_validator=True,real_model_calls=0,calls=cause_calls))
    if self.path=='/__fixture/review-origin':
        assert app.DATA.name.startswith('family-demo-')
        with app.connect_read_only() as c:
            records=[dict(r) for r in c.execute('SELECT id,source,linked_task_id,related_record_id,followup_kind,attachments,review_output_ids FROM records ORDER BY id')]
        return self.reply(200,dict(synthetic_only=True,shared_validator=True,real_model_calls=0,calls=origin_calls,records=records))
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
  // The record draft button needs a configured model, so the fixture state says so from the first load; every draft below is a fictional /api/draft receipt, with no model call.
  await p.route('**/api/state',async route=>{const response=await route.fetch(),value=await response.json();value.printing={...value.printing,printers:[{name:'Synthetic_Printer',label:'虚构打印机',color:false,duplex:false}]};value.llm={...value.llm,configured:true};await route.fulfill({response,json:value})});
  await p.goto(host.url);
  // The 1×1 PNG stays a format fixture; screenshots show a clearly fictional sheet drawn by the page's own canvas. The fake models never read either.
  const answerSheet=Buffer.from((await p.evaluate(()=>{const c=document.createElement('canvas');c.width=720;c.height=480;const g=c.getContext('2d');g.fillStyle='#fffdf6';g.fillRect(0,0,720,480);g.fillStyle='#1d2733';g.font='bold 30px sans-serif';g.fillText('虚构练习卷 · 界面测试样例',40,62);g.font='24px sans-serif';[['1. 3 + 4 = ?','原答：7'],['2. 选出表示“昨天”的词','原答：C'],['3. 12 的一半是多少？','原答：6']].forEach(([q,a],i)=>{g.fillText(q,40,140+i*76);g.fillText(a,500,140+i*76)});g.fillStyle='#b4232c';g.fillText('教师参考（虚构）：第2题 B',40,388);g.font='18px sans-serif';g.fillStyle='#6b7280';g.fillText('非真实作业 · 仅用于界面截图',40,446);return c.toDataURL('image/png')})).split(',')[1],'base64');
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
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-answer.png',mimeType:'image/png',buffer:answerSheet});await p.locator('#pendingUploads img').waitFor();
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
  await p.keyboard.press('Escape');await p.locator('[data-task="'+id+'"]').first().click();
  // Fictional review: under the "错题" heading the link line read "关联记录 · 错题：第2题 · 作业错题"; it now names the item once, and the saved title, source and homework link stay as they were.
  const wrongCard=p.locator('#taskFeedbackHistory .task-feedback-record').filter({has:p.locator('[data-record="'+wrongRecords[0].id+'"]')});await wrongCard.waitFor();
  assert.equal(await wrongCard.locator('.task-record-heading strong').innerText(),'错题');assert.equal(await wrongCard.locator('p.muted').filter({hasText:'关联记录'}).innerText(),'关联记录 · '+wrongRecords[0].title.replace(/^错题：/,''),'wrong-item link line names the item once');
  const savedWrong=(await(await fetch(host.url+'api/state')).json()).records.find(r=>r.id===wrongRecords[0].id);assert.deepEqual([savedWrong.title,savedWrong.source,savedWrong.linked_task_id],[wrongRecords[0].title,'错题照片核对',id],'the shorter line leaves the saved wrong item unchanged');
  // Fictional 360 report: help level and feedback date each got about 125px, cutting "未记录 / 不确定" and the date's last digit.
  assert.equal(await p.getByRole('dialog',{name:child+' · '+title}).count(),1,'feedback dialog is named after the original homework');
  await p.locator('#taskFeedbackDay').scrollIntoViewIfNeeded();
  const fit=await p.evaluate(()=>[['#taskAssistance','未记录 / 不确定'],['#taskFeedbackDay','2026-10-07']].map(([selector,text])=>{const e=document.querySelector(selector),s=getComputedStyle(e),c=document.createElement('canvas').getContext('2d');c.font=s.font;return {selector,visible:!!e.offsetParent,have:e.clientWidth,need:Math.ceil(c.measureText(text).width+parseFloat(s.paddingLeft)+parseFloat(s.paddingRight)+28)}}));
  console.log('feedback-fit',width,JSON.stringify(fit));for(const f of fit)if(f.visible)assert(f.have>=f.need,f.selector+' is readable in full at '+width+': '+JSON.stringify(f));assert(fit[1].visible,'feedback date is visible');
  // Fictional 1440 review: the focused title looked like an input, the two linked-record buttons touched, and "录一段语音" was larger than its row.
  const feedbackLook=await p.evaluate(()=>{const t=document.querySelector('#taskTitle'),row=document.querySelector('#taskFeedbackHistory .task-link-actions:has([data-followup])'),[a,b]=['[data-record]','[data-followup]'].map(s=>row.querySelector(s).getBoundingClientRect());return {focused:document.activeElement===t,outline:getComputedStyle(t).outlineStyle,gap:Math.max(b.left-a.right,b.top-a.bottom),sizes:[...document.querySelectorAll('#taskForm .capture-actions>*')].map(x=>getComputedStyle(x).fontSize)}});
  assert(feedbackLook.focused&&feedbackLook.outline==='none','programmatic focus stays on the plain title without an input-like box');assert(feedbackLook.gap>=6,'linked-record buttons are spaced: '+feedbackLook.gap);assert.equal(new Set(feedbackLook.sizes).size,1,'capture buttons share one size: '+feedbackLook.sizes);
  if(process.env.CORRECTION_PROOF_DIR)await p.screenshot({path:require('node:path').join(process.env.CORRECTION_PROOF_DIR,'task-feedback'+'-'+width+'.png')});
  await p.locator('#taskForm [name=note]').fill('虚构未保存的新反馈');p.once('dialog',d=>d.dismiss());
  await wrongCard.locator('[data-followup]').click();assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true,'correction does not discard unsaved feedback');
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构未保存的新反馈');await p.locator('#taskForm [name=note]').fill('');
  await wrongCard.locator('[data-followup]').click();
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),false,'correction opens from the original homework');
  const correctionForm=p.locator('#recordForm');assert.equal(await correctionForm.locator('[name=followup_kind]').inputValue(),'订正');
  // Fictional report: the correction opened as "记下一个成长瞬间" with child/type/subject and media help before the wrong item.
  assert.equal(await p.getByRole('dialog',{name:'记订正 / 复测 '+title}).count(),1,'correction dialog is named after the original homework');
  assert.equal(await p.evaluate(()=>document.activeElement?.id),'recordDialogTitle','correction opens on its heading');
  assert.equal(await p.locator('#recordFollowupTask').innerText(),title);assert.match(wrongRecords[0].title,/^错题：./,'fixture item keeps its saved prefix');
  // Fictional review: the item row read "错题　错题：第2题" and the new title "跟进：错题：第2题"; only the shown name and the new title drop the prefix.
  const itemName=wrongRecords[0].title.replace(/^错题：/,'');assert.equal(await p.locator('#recordFollowupItem').innerText(),itemName);assert.equal(await correctionForm.locator('[name=title]').inputValue(),'跟进：'+itemName,'new correction title carries one prefix');
  for(const selector of ['[name=child]','[name=category]','[name=subject]','#relationTitle'])assert.equal(await correctionForm.locator(selector).isVisible(),false,selector+' is fixed by the original item');
  assert.deepEqual(await correctionForm.evaluate(f=>{const d=new FormData(f);return [d.get('child'),d.get('subject'),d.get('related_record_id')]}),[child,wrongRecords[0].subject,String(wrongRecords[0].id)],'fixed values are still submitted');
  // Fictional review: kind and date each took a full-width row, photo entry sat below the optional help fields, 1440 showed no save button, and at 360 the bar covered the help select with the next label showing under it.
  const formBox=await p.evaluate(()=>Object.fromEntries(['#recordFollowupContext','[name=followup_kind]','[name=day]','[name=title]','[name=note]','.capture','.capture .filebutton','[name=assistance]','[name=source]','.actions'].map(s=>{const r=document.querySelector('#recordDialog '+s).getBoundingClientRect();return [s,{top:r.top,bottom:r.bottom,left:r.left,right:r.right}]})));
  const readingOrder=['#recordFollowupContext','[name=followup_kind]','[name=title]','[name=note]','.capture','[name=assistance]','[name=source]'];for(let i=1;i<readingOrder.length;i++)assert(formBox[readingOrder[i-1]].bottom<=formBox[readingOrder[i]].top+1,'correction reading order '+JSON.stringify(formBox));
  // Fictional final review at 1440: "转写已上传语音" touched "整理文字 / 图片草稿", both larger than the photo row, and "学生原答：C" sat outside the label/value columns.
  const captureTools=()=>p.evaluate(()=>{const q=s=>document.querySelector('#recordDialog '+s),c=q('.capture').getBoundingClientRect(),[a,b]=['#transcribeButton','#draftButton'].map(s=>q(s).getBoundingClientRect());return {gap:Math.max(b.left-a.right,b.top-a.bottom),sizes:['.capture .filebutton','#transcribeButton','#draftButton'].map(s=>getComputedStyle(q(s)).fontSize),heights:[a.height,b.height],inside:[a,b].every(r=>r.left>=c.left-0.5&&r.right<=c.right+0.5)}});
  const tools=await captureTools();assert(tools.gap>=7.5&&tools.heights.every(h=>h>=44)&&tools.inside,'transcribe and draft are spaced, tappable and inside the photo box: '+JSON.stringify(tools));assert.deepEqual(tools.sizes,['14px','14px','14px'],'transcribe and draft match the photo row');
  const contextColumns=await p.evaluate(()=>['#recordFollowupTask','#recordFollowupItem','#recordFollowupNote strong'].map(s=>document.querySelector(s).getBoundingClientRect().left));assert(Math.max(...contextColumns)-Math.min(...contextColumns)<=1,'context values share one column: '+contextColumns);
  assert.deepEqual(await p.locator('#recordFollowupNote').evaluate(x=>[...x.children].map(c=>c.textContent)),['学生原答','C'],'answer row splits into label and value');
  const kindBox=formBox['[name=followup_kind]'],dayBox=formBox['[name=day]'];if(width>=1000)assert(Math.abs(kindBox.top-dayBox.top)<2&&kindBox.right<dayBox.left,'desktop kind and date share a row');else assert(kindBox.bottom<=dayBox.top&&dayBox.bottom<=formBox['[name=title]'].top,'narrow kind and date stack in order');
  assert(formBox['.capture'].top-formBox['[name=note]'].bottom<48,'photo entry sits right below the note');assert(formBox['[name=note]'].bottom<=formBox['.actions'].top,'the note is clear of the save bar on the first screen');assert(formBox['.actions'].bottom<=850,'save is on the first screen');
  if(width>=1000)assert(formBox['.capture .filebutton'].bottom<=formBox['.actions'].top,'desktop shows photo entry above the save bar on the first screen');
  assert.match(await p.locator('#recordForm .capture .muted.small').innerText(),/^拍下订正后的卷面或复测结果/,'capture help is short for a correction');
  const correctionFit=await p.evaluate(()=>[...document.querySelectorAll('#recordDialog :is([name=followup_kind],[name=day],[name=assistance],[name=practice_relation],[name=source])')].map(e=>{const s=getComputedStyle(e),c=document.createElement('canvas').getContext('2d');c.font=s.font;return {name:e.name,have:e.clientWidth,need:Math.ceil(c.measureText(e.tagName==='SELECT'?e.selectedOptions[0].text:'2026-10-07').width+parseFloat(s.paddingLeft)+parseFloat(s.paddingRight)+28)}}));
  for(const f of correctionFit)assert(f.have>=f.need,f.name+' reads in full at '+width+': '+JSON.stringify(f));
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.querySelector('#recordDialog').scrollWidth<=document.querySelector('#recordDialog').clientWidth),true,'correction has no horizontal overflow');
  if(process.env.CORRECTION_PROOF_DIR)await p.screenshot({path:require('node:path').join(process.env.CORRECTION_PROOF_DIR,'correction'+'-'+width+'.png')});
  // Each control scrolled into view lies wholly above the save bar and takes the tap; the strip under the bar shows and takes nothing else.
  const covered=await p.evaluate(()=>{const d=document.querySelector('#recordDialog'),bar=d.querySelector('.actions'),edge=d.getBoundingClientRect(),under=document.elementFromPoint(edge.left+edge.width/2,edge.bottom-4),out=bar.contains(under)?[]:['under bar: '+(under?.name||under?.id||under?.tagName)];
   for(const e of d.querySelectorAll('#recordForm :is(select,input:not([type=hidden]),textarea,button,summary)')){if(bar.contains(e)||!e.getClientRects().length)continue;const target=e.type==='file'?e.closest('.filebutton'):e;target.scrollIntoView({block:'nearest'});const r=target.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(r.bottom>bar.getBoundingClientRect().top+1||!target.contains(hit))out.push(e.name||e.id||e.textContent.trim().slice(0,12))}
   d.scrollTop=0;return out});
  assert.deepEqual(covered,[],'correction controls clear of the save bar at '+width);
  await p.keyboard.press('Tab');assert.equal(await p.evaluate(()=>document.activeElement?.name),'followup_kind','Tab moves from the heading to correction kind');
  await correctionForm.locator('[name=note]').fill('虚构：孩子独立订正后仍需换题核对');
  let discardPrompts=0;const keepDraft=d=>{discardPrompts++;d.dismiss()};p.on('dialog',keepDraft);
  await p.locator('#recordDialog [data-close="recordDialog"]').click();assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'cancel keeps unsaved correction');
  await p.keyboard.press('Escape');assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'Escape keeps unsaved correction');
  assert.equal(discardPrompts,2,'both exits ask before discarding correction');p.off('dialog',keepDraft);
  assert.equal(await correctionForm.locator('[name=note]').inputValue(),'虚构：孩子独立订正后仍需换题核对');
  assert(await p.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented}),'refresh protects unsaved correction');
  // Fictional review: a draft with another subject and a score rewrote the hidden subject and category of a fixed correction.
  const draftBodies=[];await p.route('**/api/draft',route=>{const body=route.request().postDataJSON();draftBodies.push(body);return route.fulfill({json:{child_id:body.child_id,child_name:child,draft:{title:'虚构草稿：第2题订正',subject:'虚构其他科目',score:88,total:100,note:'虚构：孩子独立订正后仍需换题核对；草稿另写了分数。',uncertainties:[]}}})});
  await p.locator('#draftButton').click();await p.locator('#applyDraft').waitFor();assert.equal(await p.locator('#applyDraft').innerText(),'填入标题和详情，继续核对');await p.locator('#applyDraft').click();
  assert.deepEqual(await correctionForm.evaluate(f=>['title','child','subject','category','score','total','related_record_id'].map(k=>f.elements[k].value)),['虚构草稿：第2题订正',child,wrongRecords[0].subject,'学习进展','','',String(wrongRecords[0].id)],'draft fills title and note only');
  assert.equal(await p.locator('#scoreFields').isVisible(),false,'a draft score does not open score fields in a correction');assert.match(await p.locator('#draftStatus').innerText(),/科目和类型仍按原错题，草稿里的科目或分数未填入/);
  assert.equal(await p.locator('#recordFollowupOwner').innerText(),[child,wrongRecords[0].subject].filter(Boolean).join(' · ')+' · 保存后留在这份作业下，不改作业状态','fixed context above matches what is submitted');
  let releaseReceipt;const heldReceipt=new Promise(resolve=>releaseReceipt=resolve);
  const keys=[],correctionBodies=[];await p.route('**/api/record',async route=>{const body=route.request().postDataJSON();keys.push(body.request_key);correctionBodies.push(body);if(keys.length===1){await route.fetch();await heldReceipt;await route.fulfill({status:503,json:{error:'虚构回执丢失'}})}else await route.continue()});
  await correctionForm.locator('[type=submit]').click();await eventually(async()=>await correctionForm.getAttribute('data-saving')==='yes','correction save in flight');
  await p.locator('#recordDialog [data-close="recordDialog"]').click();assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'unknown save result cannot be discarded');
  await p.keyboard.press('Escape');assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true,'Escape cannot discard an in-flight correction');
  releaseReceipt();await eventually(async()=>/虚构回执丢失/.test(await p.locator('#recordError').innerText()),'correction receipt lost');
  await correctionForm.locator('[type=submit]').click();await eventually(async()=>!(await p.locator('#recordDialog').evaluate(x=>x.open)),'same correction retry saved');await p.unroute('**/api/record');
  assert.equal(keys.length,2);assert(keys[0]&&keys[0]===keys[1],'retry reuses one request key');
  for(const body of correctionBodies){assert.deepEqual([body.child,body.category,body.subject,body.title,body.related_record_id,body.followup_kind],[child,'学习进展',wrongRecords[0].subject,'虚构草稿：第2题订正',wrongRecords[0].id,'订正'],'correction keeps fixed child, subject and original link');assert(!body.score&&!body.total,'no draft score is submitted with a correction')}
  await p.evaluate(()=>document.querySelector('#add').click());assert.equal(await p.locator('#recordDialogTitle').innerText(),'记下一个成长瞬间','general record leaves correction mode');
  assert.equal(await p.locator('#recordFollowupContext').isVisible(),false);assert.equal(await correctionForm.locator('[name=child]').isVisible(),true);assert.equal(await p.getByRole('dialog',{name:'记下一个成长瞬间'}).count(),1);
  assert(await p.evaluate(()=>document.querySelector('#recordForm .capture').getBoundingClientRect().top<document.querySelector('#recordForm [name=child]').getBoundingClientRect().top),'general record keeps capture first');
  assert.match(await p.locator('#recordForm .capture .muted.small').innerText(),/原件先保存，可稍后补充记录/,'general record restores the full capture help');assert.equal(await p.evaluate(()=>document.querySelector('#recordKindRow').nextElementSibling.id),'relationFields','general record restores the kind row');
  const generalTools=await captureTools();assert(generalTools.gap>=7.5&&generalTools.heights.every(h=>h>=44)&&generalTools.inside,'general record keeps transcribe and draft spaced and tappable: '+JSON.stringify(generalTools));assert.deepEqual(generalTools.sizes,['14px','14px','14px'],'general record keeps one button size');
  // An ordinary record still takes the draft's subject, score and category.
  await correctionForm.locator('[name=child]').selectOption(child);await p.locator('#draftButton').click();await p.locator('#applyDraft').waitFor();assert.equal(await p.locator('#applyDraft').innerText(),'填入表单，继续核对');await p.locator('#applyDraft').click();
  assert.deepEqual(await correctionForm.evaluate(f=>['subject','category','score','total'].map(k=>f.elements[k].value)),['虚构其他科目','成绩','88','100'],'general record keeps the old draft fill');assert.equal(await p.locator('#scoreFields').isVisible(),true);
  await p.unroute('**/api/draft');assert.deepEqual(draftBodies.map(b=>b.child_id),Array(2).fill(state.children.find(c=>c.name===child).id),'both drafts were requested for the original child');p.once('dialog',d=>d.accept());
  await p.locator('#recordDialog [data-close="recordDialog"]').click();assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),false);
  state=await(await fetch(host.url+'api/state')).json();const corrected=state.records.filter(r=>r.related_record_id===wrongRecords[0].id&&r.followup_kind==='订正');
  assert.equal(corrected.length,1,'lost receipt does not duplicate correction');assert.equal(corrected[0].linked_task_id,id,'correction stays on original homework');assert.equal(state.records.find(r=>r.id===wrongRecords[0].id).title,wrongRecords[0].title,'the saved wrong item keeps its title');
  assert.deepEqual([corrected[0].child,corrected[0].subject,corrected[0].category],[child,wrongRecords[0].subject,'学习进展'],'saved correction keeps the wrong item owner');assert(corrected[0].score==null&&corrected[0].total==null,'saved correction carries no draft score');
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
  await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>/虚构上传失败/.test(await panel.innerText()),'review text upload failure');{const v=await reviewStage(panel);assert.deepEqual([v.stage,v.hint],[v.questions?'检查意见待核对，尚未保存':null,'先保存文字原件并填入，仍需保存这次反馈。'],'a failed text upload keeps the pending stage and its note')}
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
  await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await panel.innerText()),'review staged after explicit retry');{const v=await reviewStage(panel);assert.deepEqual(v,{stage:v.questions?'检查意见已填入，尚未保存':null,hint:'检查意见已填入，尚未保存；请保存这次反馈。',questions:v.questions,counts:v.counts,status:'检查意见已填入，尚未保存；请保存这次反馈。'},'photo review filled: the stage line, the next-step note and the save status agree')}{const view=await savePairView(p);assert(view.inside,'photo review filled: the unsaved note and the original save button are whole and at least 12px inside the viewport, the task dialog and its clipping ancestors, above a sticky close bar: '+JSON.stringify(view))}
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
  const stale=p.locator('#taskFeedbackHistory [data-homework-review="'+source.id+'"]');await stale.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first().check();if(await stale.locator('[data-homework-review-result] textarea:not(:disabled)').count()&&await stale.locator('[data-homework-review-result] textarea').inputValue())p.once('dialog',d=>d.accept());await stale.locator('[data-homework-review-run]').click();await stale.locator('[data-homework-review-result] textarea').waitFor();await stale.locator('[data-homework-review-confirm]').check();await stale.locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await stale.innerText()),'review staged before concurrent correction');
  const correction=await fetch(host.url+'api/task/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({task_id:id,child,record_id:source.id,expected_created:source.created,note:'虚构最终作答后来更正'})});assert.equal(correction.status,200);
  p.once('dialog',d=>d.accept());await p.locator('#saveTaskFeedback').click();await eventually(async()=>/原作答已在别处更正/.test(await p.locator('#taskError').innerText()),'stale review rejected');
  state=await(await fetch(host.url+'api/state')).json();assert.equal(state.records.filter(r=>r.source==='事项:'+id).length,4,'rejected review leaves no new record');
  p.once('dialog',d=>d.accept());await p.locator('#taskDialog [data-close="taskDialog"]').click();await p.reload();await p.locator('[data-task="'+id+'"]').first().click();
  const fresh=p.locator('#taskFeedbackHistory [data-homework-review="'+source.id+'"]');await fresh.locator(':scope > details').evaluate(x=>x.open=true);await fresh.locator(' :scope > details > .homework-review-material [data-homework-review-photo]').first().check();await fresh.locator('[data-homework-review-run]').click();await fresh.locator('[data-homework-review-result] textarea').waitFor();await fresh.locator('[data-homework-review-confirm]').check();await fresh.locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await fresh.innerText()),'fresh review staged');await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'fresh review saved');
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
  await whole.locator('[data-homework-review-confirm]').check();await whole.locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await whole.innerText()),'five-image review staged');await p.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'five-image basis feedback saved');
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
     await choice.check();assert.equal(await role.isVisible(),true,'the late source role is visible in its row');assert.equal(await pages.isVisible(),true,'the late PDF shows its page numbers in its row');await role.selectOption('reference');await pages.fill('1');
     assert.equal(await choice.isChecked(),true);assert.equal(await role.inputValue(),'reference');assert.equal(await pages.inputValue(),'1');await choice.uncheck();
    };
    for(const latePanel of returnedPanels)await checkEditable(latePanel);
    if(outcome==='success'){
     await latePanels[0].locator('[data-homework-review-confirm]').check();await latePanels[0].locator('[data-homework-review-apply]').click();await eventually(async()=>uploadPending,'review text upload started before sibling sources return');
     sourceGates.get(secondAnswerId)();const siblingMaterial=latePanels[1].locator('[data-homework-review-sources] [data-review-source="'+reference+'"]');await siblingMaterial.waitFor();
     assert.equal(await siblingMaterial.locator('[data-homework-review-photo]').isDisabled(),true,'sibling source freezes during review text upload');
     releaseUpload();await eventually(async()=>/已填入反馈，尚未保存/.test(await latePanels[0].innerText()),'review text upload completed');await checkEditable(latePanels[1]);
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
  const validatorAfter=await(await fetch(host.url+'__fixture/cause-validator')).json();assert(validatorAfter.synthetic_only&&validatorAfter.shared_validator);assert.equal(validatorAfter.real_model_calls,0);assert.equal(validatorAfter.calls.length,validatorBefore.calls.length+1);assertDraftReceipt(validatorAfter.calls.at(-1).validated,causeReply.draft);assert.equal(validatorAfter.calls.at(-1).raw.items[0].possible_cause,'');assert.equal(validatorAfter.calls.at(-1).raw.items[0].question_kind,'objective');
  await eventually(async()=>/1题 · 1题需订正 · 0题未判定/.test(await causePanel.locator('[data-homework-review-result] .homework-review-counts').innerText()),'verified error survives unknown cause');assert.match(await causePanel.locator('.homework-review-questions').innerText(),/需要订正/);
  assert.equal((await readCause()).records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===causeTask.id).length,0,'AI draft does not automatically create a wrong item');
  await causePanel.locator('[data-homework-review-confirm]').check();await causePanel.locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await causePanel.innerText()),'validated result staged for explicit save');
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
  const conciseOpinion=await reopenedCause.innerText();assert(conciseOpinion.startsWith('本次核对1题：需订正1题，与参考一致0题，未判定0题。'));assert.equal(conciseOpinion.split('卷面作答：').length-1,1);assert(!conciseOpinion.includes('可能原因（待问孩子）：'));assert(conciseOpinion.includes(causeQuestion.error_reason)&&conciseOpinion.includes(causeQuestion.steps));
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
  await p.reload();await openUnit();assert.equal(await p.locator('#taskRequirement').innerText(),unit.action);await p.locator('#taskFeedbackHistory').getByText(unitFeedbackNote,{exact:true}).waitFor();await p.locator('#taskFeedbackHistory').getByText(unitCorrectionNote,{exact:true}).waitFor();await eventually(async()=> (await p.locator('#taskFeedbackHistory .task-feedback-record').filter({has:p.locator('[data-record="'+unitWrongSaved.record_id+'"]')}).innerText()).includes('Unit30第1个词读音'),'saved Unit wrong item title visible');
  const unitAfter=await readUnit();assert.deepEqual(unitAfter.tasks.find(t=>t.id===unit.task_id),unitTaskBefore,'feedback, wrong item and correction do not complete or alter the canonical school task');assert.equal(unitAfter.records.length,unitBefore.records.length+3);assert.deepEqual(unitAfter.printing.jobs.map(j=>j.id).sort(),printIdsBeforeChecks);
  const unitWrongRecord=unitAfter.records.find(r=>r.id===unitWrongSaved.record_id),unitCorrectionRecord=unitAfter.records.find(r=>r.id===unitCorrection.record_id);assert.equal(unitWrongRecord.related_record_id,unitFeedback.record_id);assert.equal(unitCorrectionRecord.related_record_id,unitWrongSaved.record_id);for(const r of [unitWrongRecord,unitCorrectionRecord]){assert.equal(r.child,child);assert.equal(r.linked_task_id,unit.task_id)}assert.equal(unitCorrectionRecord.followup_kind,'订正');
  const unitRepeated=await fetch(host.url+'__fixture/unit-identity?width='+width);assert.equal(unitRepeated.status,200);assert.deepEqual(await unitRepeated.json(),unit,'repeated fixture reads preserve source rows, accepted decision and the same task identifier');assert.equal((await(await fetch(host.url+'__fixture/cause-validator')).json()).calls.length,validatorAfter.calls.length,'manual Unit flow adds no homework model call');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'unit-identity-'+width+'.json'),JSON.stringify({scope:'mock raw school selection through real shared guard and auto-save; not model accuracy',fixture:unit,feedback:unitFeedback,wrong:unitWrongSaved,correction:unitCorrection},null,2));await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'unit-reopened-'+width+'.png')})}
  // Contradictory teacher material uses the same real validator and save/read path.
  // Only the model transport is fixed; no actual OCR, model call or household write.
  await p.locator('#taskDialog [data-close="taskDialog"]').click();state=await readCause();
  const consistencyTask=(await post('api/task/new',{child,title:'虚构结论一致 '+width,category:'homework',action:'虚构结论一致：逐题核对乙卷三题及教师参考，冲突题不判错。',due:state.today})).task;
  const openConsistency=async()=>{await p.locator('nav [data-page=tasks]').click();await p.locator('body[data-page=tasks] #task-group-homework').waitFor();await p.locator('[data-task-box=Inbox]').click();await p.locator('#content [data-task="'+consistencyTask.id+'"]:visible').first().click();await p.locator('#taskDialog[open]').waitFor()};
  const consistencySheet=await browser.newPage({viewport:{width:500,height:330}});
  await consistencySheet.setContent('<html><body style="font:22px sans-serif;background:white;color:black"><h2>SYNTHETIC PAPER B</h2><p>Q1: 2 + 3 = ? Student: ______</p><p>Q2: 6 - 2 = ? Student: 3</p><p>Q3: 1 + 1 = ? Student: 2</p><p>Q4: Choose A, B, C or D. Student: C</p></body></html>');
  const consistencyImage=await consistencySheet.screenshot();await consistencySheet.close();await p.reload();await openConsistency();
  await p.locator('#taskForm [name=note]').fill('虚构乙卷四题，第1题空白，其他最终作答3、2、C。');
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-consistency-answer-'+width+'.png',mimeType:'image/png',buffer:consistencyImage});await p.locator('#pendingUploads img').waitFor();
  const consistencyTeacherName='synthetic-consistency-teacher-'+width+'.txt';
  await p.locator('#fileInput').setInputFiles({name:consistencyTeacherName,mimeType:'text/plain',buffer:Buffer.from('虚构乙卷 第1题：2+3=5。\n第2题：6-2=4。\n第3题：1+1=2。\n第4题B。\n')});await p.locator('#pendingUploads').getByRole('link',{name:consistencyTeacherName,exact:true}).waitFor();
  const consistencyOriginal=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  state=await readCause();const consistencyRecord=state.records.find(r=>r.id===consistencyOriginal.record_id),consistencySources=consistencyRecord.attachments.map(id=>state.uploads.find(a=>a.id===id));
  const consistencyPhoto=consistencySources.find(a=>a.mime==='image/png'),consistencyTeacher=consistencySources.find(a=>a.name===consistencyTeacherName);assert(consistencyPhoto&&consistencyTeacher);
  const consistencyPanel=p.locator('#taskFeedbackHistory [data-homework-review="'+consistencyOriginal.record_id+'"]');if(!await consistencyPanel.locator(':scope > details').evaluate(x=>x.open))await consistencyPanel.locator(':scope > details > summary').click();
  await consistencyPanel.locator('[data-review-source="'+consistencyPhoto.id+'"] [data-homework-review-photo]').check();await consistencyPanel.locator('[data-review-source="'+consistencyTeacher.id+'"] [data-homework-review-photo]').check();
  const consistencyCallsBefore=(await(await fetch(host.url+'__fixture/cause-validator')).json()).calls.length;let consistencyReply,consistencyRequest;
  await p.route('**/api/print/homework/draft',async route=>{consistencyRequest=route.request().postDataJSON();const response=await route.fetch();assert.equal(response.status(),200);consistencyReply=await response.json();await route.fulfill({response,json:consistencyReply})});
  try{await consistencyPanel.locator('[data-homework-review-run]').click();await eventually(async()=>!!consistencyReply,'real consistency validator response')}finally{await p.unroute('**/api/print/homework/draft')}
  const consistentDraft=consistencyReply.draft,staleCoverage='第1题正确；作文未提供，超出本批材料。',staleComparison='后补老师参考后，第1题保持正确，整卷检查完成。';
  assert.equal(consistentDraft.items,4);assert.equal(consistentDraft.wrong_items,1);assert.equal(consistentDraft.unknown_items,2);assert.deepEqual(consistentDraft.questions.map(q=>q.judgment),['unknown','incorrect','correct','unknown']);
  const contradictoryChoice=consistentDraft.questions[3];assert.equal(contradictoryChoice.student_answer,'C');assert.equal(contradictoryChoice.answer,'教师参考：B');assert.match(contradictoryChoice.uncertainty,/判定矛盾/);for(const key of ['error_reason','possible_cause','steps'])assert.equal(contradictoryChoice[key],'');
  assert.equal(consistentDraft.questions[0].answer,'教师参考：5');assert.equal(consistentDraft.questions[0].student_answer,'');assert.match(consistentDraft.questions[0].uncertainty,/答题格空白/);assert.equal(consistentDraft.questions[0].steps,'');assert.equal(consistentDraft.questions[1].steps,'');assert.equal(consistentDraft.questions[1].possible_cause,'');
  for(const text of [consistentDraft.text,consistentDraft.coverage,consistentDraft.comparison]){assert(!text.includes(staleCoverage));assert(!text.includes(staleComparison))}assert.match(consistentDraft.coverage,/2题仍未判定/);assert.deepEqual(consistentDraft.unverified_model_summary,{coverage:staleCoverage,comparison:staleComparison});assert.match(consistentDraft.coverage,/未列入本次逐题结果的题目和资料范围仍未检查/);assert.equal(consistentDraft.text.split('虚构乙卷第1题').length-1,2);
  const consistencyTrace=await(await fetch(host.url+'__fixture/cause-validator')).json();assert(consistencyTrace.synthetic_only&&consistencyTrace.shared_validator);assert.equal(consistencyTrace.real_model_calls,0);assert.equal(consistencyTrace.calls.length,consistencyCallsBefore+1);assertDraftReceipt(consistencyTrace.calls.at(-1).validated,consistentDraft);assert.deepEqual(consistencyTrace.calls.at(-1).raw,consistencyTrace.calls.at(-1).original);assert.equal(consistencyTrace.calls.at(-1).raw.coverage,staleCoverage);
  await eventually(async()=>/4题 · 1题需订正 · 2题未判定/.test(await consistencyPanel.locator('[data-homework-review-result] .homework-review-counts').innerText()),'mixed final grades visible');assert.match(await consistencyPanel.locator('.homework-review-questions').innerText(),/未判定/);
  const choiceRow=consistencyPanel.locator('.homework-question').filter({hasText:'虚构乙卷第4题'});assert.equal(await choiceRow.count(),1);assert.match(await choiceRow.innerText(),/孩子作答：C/);assert.match(await choiceRow.innerText(),/教师参考：B/);assert.match(await choiceRow.innerText(),/判定矛盾/);
  // Check the automatic landing before any test-driven scrolling. A DOM-visible
  // heading below the viewport is not a useful first result on a phone.
  const consistencyResult=consistencyPanel.locator('[data-homework-review-result]');
  const landing=await consistencyResult.evaluate(el=>{
   const count=el.querySelector('.homework-review-counts'),first=el.querySelector('.homework-question h4'),coverage=el.querySelector('[data-homework-review-coverage]'),dialog=el.closest('dialog');
   const box=n=>{if(!n)return null;const r=n.getBoundingClientRect();return {top:r.top,bottom:r.bottom}};
   return {firstClass:el.firstElementChild?.className,counts:count?.textContent,count:box(count),first:box(first),coverage:box(coverage),dialog:box(dialog),height:innerHeight,width:innerWidth};
  });
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'result-landing-'+width+'.json'),JSON.stringify(landing,null,2));await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'result-landing-'+width+'.png')})}
  assert.equal(landing.width,width);assert.equal(landing.firstClass,'homework-review-questions','question results must precede the full scope and comparison');
  assert.equal(landing.counts,'4题 · 1题需订正 · 2题未判定。');
  for(const r of [landing.count,landing.first]){assert(r,'counts and first question have visible geometry');assert(r.top>=Math.max(0,landing.dialog.top)&&r.bottom<=Math.min(landing.height,landing.dialog.bottom),'automatic landing shows the counts and first question without another scroll')}
  assert(landing.first.bottom<landing.coverage.top,'complete scope stays below the structured question results');
  // The page shows the exact app.js helper's view of the raw validator text; the raw stays on the element, and every source name and boundary stays visible.
  {const shown=consistencyPanel.locator('[data-homework-review-coverage]'),raw=consistentDraft.coverage,text=await shown.innerText(),view=scopeText(raw,consistentDraft.comparison,consistentDraft.text);assert.equal(await shown.getAttribute('data-homework-review-coverage'),raw);assert.equal(text,view.coverage);assert.doesNotMatch(text,/。；|本次检查范围：本次/);for(const fact of [...raw.match(/《[^》]+》/g)||[],'2题仍未判定','仍未检查','尚未核明'])if(raw.includes(fact))assert(text.includes(fact),'scope keeps '+fact);assert.match(text,/2题仍未判定/);
   const note=consistencyResult.locator(':scope > .note'),noteText=await note.innerText();assert.equal(await note.getAttribute('data-homework-review-comparison'),consistentDraft.comparison);assert.equal(noteText,view.comparison);assert.doesNotMatch(noteText,/本次复核：本次/)}
  assert.equal(await consistencyPanel.locator('[data-homework-review-status]').innerText(),'','the count is shown once, not repeated in the status line');assert.match(await consistencyResult.locator('.homework-review-stage').innerText(),/检查意见待核对，尚未保存/);for(const t of await consistencyResult.locator('.homework-reference').allInnerTexts())assert.doesNotMatch(t,/参考答案：|^[^：\n]*：(教师参考|AI自行推导)：/,'one source label per reference');
  assert.equal(await consistencyResult.evaluate(el=>{const q=el.querySelector('.homework-review-questions'),n=el.querySelector('.homework-review-next'),c=el.querySelector('[data-homework-review-coverage]');return !!(q&&n&&c&&q.compareDocumentPosition(n)&Node.DOCUMENT_POSITION_FOLLOWING&&n.compareDocumentPosition(c)&Node.DOCUMENT_POSITION_FOLLOWING)&&[...el.querySelectorAll('button,summary,.print-file-check')].filter(x=>x.getClientRects().length).every(x=>x.getBoundingClientRect().height>=44)}),true,'the two-step action follows the questions, before the visible scope, with 44px targets');
  assert.equal(await consistencyResult.locator('textarea').inputValue(),consistentDraft.text,'layout never reconstructs or truncates the saved review');
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){await p.screenshot({path:require('node:path').join(process.env.HOMEWORK_QUICK_PROOF_DIR,'consistency-draft-'+width+'.png')})}
  await consistencyPanel.locator('[data-homework-review-confirm]').check();await consistencyPanel.locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await consistencyPanel.innerText()),'consistent result staged for explicit save');{const v=await reviewStage(consistencyPanel);assert.deepEqual(v,{stage:'检查意见已填入，尚未保存',hint:'检查意见已填入，尚未保存；请保存这次反馈。',questions:true,counts:'4题 · 1题需订正 · 2题未判定。',status:'检查意见已填入，尚未保存；请保存这次反馈。'},'consistency review filled: the stage line, note and save status agree, and unknown questions stay unknown')}{const view=await savePairView(p);assert(view.inside,'consistency review filled: the unsaved note and the original save button are whole and at least 12px inside the viewport, the task dialog and its clipping ancestors, above a sticky close bar: '+JSON.stringify(view))}
  const consistencyReview=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  state=await readCause();assert.equal(state.records.find(r=>r.id===consistencyReview.record_id).related_record_id,consistencyOriginal.record_id);assert.equal(state.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===consistencyTask.id).length,0,'unknown and sound error remain explicit decisions, no automatic wrong item');
  const consistencyWrong=p.locator('#taskFeedbackHistory [data-task-wrong-form="'+consistencyOriginal.record_id+'"]');await consistencyWrong.locator(':scope > summary').click();await consistencyWrong.locator('[data-wrong-field=label]').fill('虚构乙卷第2题');await consistencyWrong.locator('[data-wrong-field=text]').fill('6-2=?');await consistencyWrong.locator('[data-wrong-field=answer]').fill('3');await consistencyWrong.locator('[data-wrong-field=correction]').fill('4');
  const consistencyWrongSaved=await threeAttemptSave(p,'/api/wrong/save',consistencyWrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await consistencyWrong.innerText()),async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  const consistencyWrongCard=p.locator('#taskFeedbackHistory .task-feedback-record').filter({has:p.locator('[data-record="'+consistencyWrongSaved.record_id+'"]')});await consistencyWrongCard.locator('[data-followup]').click();await p.locator('#recordDialog[open]').waitFor();const consistencyCorrectionNote='虚构乙卷第2题订正为4；第1题仍待核对教师依据。';await p.locator('#recordForm [name=note]').fill(consistencyCorrectionNote);
  const consistencyCorrection=await threeAttemptSave(p,'/api/record',p.locator('#recordForm [type=submit]'),async()=>/虚构/.test(await p.locator('#recordError').innerText()),async()=>!await p.locator('#recordDialog').evaluate(x=>x.open),readCause);
  await p.reload();await openConsistency();await p.locator('#taskFeedbackHistory').getByText(consistencyCorrectionNote,{exact:false}).waitFor();const reopenedConsistency=p.locator('[data-saved-homework-review="'+consistencyReview.record_id+'"] [data-saved-review-text]');await eventually(async()=>await reopenedConsistency.innerText()===consistentDraft.text,'consistent mixed result reopens unchanged');
  assert.match(await reopenedConsistency.innerText(),/需订正1题，与参考一致1题，未判定2题/);assert.match(await reopenedConsistency.innerText(),/虚构乙卷第4题 · 未判定/);assert.match(await reopenedConsistency.innerText(),/判定矛盾/);assert(!(await reopenedConsistency.innerText()).includes(staleComparison));state=await readCause();const consistencyFinalWrong=state.records.find(r=>r.id===consistencyWrongSaved.record_id),consistencyFinalCorrection=state.records.find(r=>r.id===consistencyCorrection.record_id);assert.equal(consistencyFinalWrong.related_record_id,consistencyOriginal.record_id);assert.equal(consistencyFinalCorrection.related_record_id,consistencyFinalWrong.id);for(const r of [consistencyFinalWrong,consistencyFinalCorrection]){assert.equal(r.child,child);assert.equal(r.linked_task_id,consistencyTask.id)}assert.equal(state.tasks.find(t=>t.id===consistencyTask.id).update,null);assert.deepEqual(state.printing.jobs.map(j=>j.id).sort(),printIdsBeforeChecks);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'consistency-validator-'+width+'.json'),JSON.stringify({scope:'fixed synthetic raw through real shared validator; not model accuracy',request:consistencyRequest,validator:consistencyTrace.calls.at(-1),feedback:consistencyReview,wrong:consistencyWrongSaved,correction:consistencyCorrection},null,2));await reopenedConsistency.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'consistency-reopened-'+width+'.png')})}

  // A returned correct item must not hide another identified question. Save the
  // gap, reopen it, then actually recheck the second question under the same task.
  await p.locator('#taskDialog [data-close="taskDialog"]').click();state=await readCause();
  const coverageTask=(await post('api/task/new',{child,title:'虚构漏题覆盖 '+width,category:'homework',action:'虚构漏题覆盖：检查甲卷两题，第2题不得漏查。',due:state.today})).task;
  const openCoverage=async()=>{await p.locator('nav [data-page=tasks]').click();await p.locator('body[data-page=tasks] #task-group-homework').waitFor();await p.locator('[data-task-box=Inbox]').click();await p.locator('#content [data-task="'+coverageTask.id+'"]:visible').first().click();await p.locator('#taskDialog[open]').waitFor()};
  await p.reload();await openCoverage();await p.locator('#taskForm [name=note]').fill('虚构甲卷，孩子第1题作答5，第2题作答3。');
  const coverageAnswerName='synthetic-paper-a-answer.txt',coverageTeacherName='synthetic-paper-a-teacher.txt';
  for(const [name,text] of [[coverageAnswerName,'虚构甲卷\n第1题 2+3，孩子作答5。\n第2题 6-2，孩子作答3。'],[coverageTeacherName,'虚构甲卷\n第1题5。\n第2题4。']]){
   await p.locator('#fileInput').setInputFiles({name,mimeType:'text/plain',buffer:Buffer.from(text)});await p.locator('#pendingUploads').getByRole('link',{name,exact:true}).waitFor();
  }
  const coverageOriginal=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  state=await readCause();const coverageRecord=state.records.find(r=>r.id===coverageOriginal.record_id),coverageInputs=coverageRecord.attachments.map(id=>state.uploads.find(a=>a.id===id));
  const coverageAnswer=coverageInputs.find(a=>a.name===coverageAnswerName),coverageTeacher=coverageInputs.find(a=>a.name===coverageTeacherName);
  const coveragePanel=()=>p.locator('#taskFeedbackHistory [data-homework-review="'+coverageOriginal.record_id+'"]');
  async function selectCoverage(previous){
   if(!await coveragePanel().locator(':scope > details').evaluate(x=>x.open))await coveragePanel().locator(':scope > details > summary').click();
   for(const [id,role] of [[coverageAnswer.id,'question'],[coverageTeacher.id,'reference'],...(previous?[[previous,'previous']]:[])]){
    const choice=coveragePanel().locator('[data-review-source="'+id+'"]');await choice.locator('[data-homework-review-photo]').check();
    assert.equal(await choice.locator('details').count(),0,'the source role sits directly in its row');
    await choice.locator('[data-homework-review-role]').selectOption(role);
   }
  }
  await selectCoverage();const coverageTraceBefore=(await(await fetch(host.url+'__fixture/question-coverage')).json()).calls.length;
  await p.route('**/api/print/homework/draft',r=>r.fulfill({status:503,json:{error:'虚构模型失败，原件保留'}}));await coveragePanel().locator('[data-homework-review-run]').click();await eventually(async()=>/虚构模型失败/.test(await coveragePanel().innerText()),'coverage model failure retained');await p.unroute('**/api/print/homework/draft');
  assert.equal((await(await fetch(host.url+'__fixture/question-coverage')).json()).calls.length,coverageTraceBefore);
  await coveragePanel().locator('[data-homework-review-run]').click();await eventually(async()=>/2题 · 0题需订正 · 1题未判定/.test(await coveragePanel().locator('[data-homework-review-result] .homework-review-counts').innerText()),'omitted second question becomes visible');
  const missingRow=coveragePanel().locator('[data-homework-review-result] .homework-question').filter({hasText:'虚构甲卷第2题'});assert.equal(await missingRow.count(),1);assert.match(await missingRow.innerText(),/未返回逐题检查结果/);assert.match(await missingRow.innerText(),/孩子作答：未能辨认/);
  const coverageGapText=await coveragePanel().locator('[data-homework-review-result] textarea').inputValue();assert(!coverageGapText.includes('第1、2题均正确'));assert(coverageGapText.includes('虚构甲卷第2题'));
  await coveragePanel().locator('[data-homework-review-instruction]').fill('虚构再次漏列第2题：仍须保留待补查。');
  p.once('dialog',d=>d.accept());await coveragePanel().locator('[data-homework-review-run]').click();await eventually(async()=>/上一轮此题仍未判定/.test(await coveragePanel().innerText()),'unsaved same-scope pending survives omitted inventory');
  assert.equal(await coveragePanel().locator('[data-homework-review-result] .homework-question').count(),2);assert.match(await coveragePanel().locator('[data-homework-review-result] .homework-review-counts').innerText(),/1题未判定/);
  const unsavedPending=JSON.parse(await coveragePanel().locator('[data-homework-review-result]').getAttribute('data-continuation'));assert.deepEqual(unsavedPending.pending_labels,['虚构甲卷第2题']);
  const coveragePendingText=await coveragePanel().locator('[data-homework-review-result] textarea').inputValue();
  for(const [status,error] of [[503,'虚构补查模型失败'],[422,'本次题目与上一轮待补题合计超过25项']]){
   const beforeFailedRecheck=(await(await fetch(host.url+'__fixture/question-coverage')).json()).calls.length;
   await p.route('**/api/print/homework/draft',r=>r.fulfill({status,json:{error}}));
   try{p.once('dialog',d=>d.accept());await coveragePanel().locator('[data-homework-review-run]').click();await eventually(async()=>(await coveragePanel().locator('[data-homework-review-status]').innerText()).includes(error),'failed recheck keeps known pending draft');
    assert.equal(await coveragePanel().locator('[data-homework-review-result] textarea').inputValue(),coveragePendingText);
    assert.deepEqual(JSON.parse(await coveragePanel().locator('[data-homework-review-result]').getAttribute('data-continuation')),unsavedPending);
    assert.equal((await(await fetch(host.url+'__fixture/question-coverage')).json()).calls.length,beforeFailedRecheck);
   }finally{await p.unroute('**/api/print/homework/draft')}
  }
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){await missingRow.scrollIntoViewIfNeeded();await p.screenshot({path:require('node:path').join(process.env.HOMEWORK_QUICK_PROOF_DIR,'question-coverage-gap-'+width+'.png')})}
  await coveragePanel().locator('[data-homework-review-confirm]').check();await coveragePanel().locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await coveragePanel().innerText()),'gap staged for save');
  const coverageGapSaved=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  await p.reload();await openCoverage();const savedGap=p.locator('[data-saved-homework-review="'+coverageGapSaved.record_id+'"] [data-saved-review-text]');await eventually(async()=>await savedGap.innerText()===coveragePendingText,'missing question remains visible on reopen');
  state=await readCause();const coverageOutputs=JSON.parse(state.records.find(r=>r.id===coverageGapSaved.record_id).review_output_ids);assert.equal(coverageOutputs.length,1);const coveragePrevious=coverageOutputs[0];assert.match(coveragePrevious,/^[a-f0-9]{32}$/);await selectCoverage(coveragePrevious);await coveragePanel().locator('[data-homework-review-instruction]').fill('虚构再次漏列第2题：保存重开后仍须补查。');
  await coveragePanel().locator('[data-homework-review-run]').click();await eventually(async()=>/上一轮此题仍未判定/.test(await coveragePanel().innerText()),'saved same-scope checklist survives model omitting the item and inventory');
  assert.equal(await coveragePanel().locator('[data-homework-review-result] .homework-question').count(),2);assert.match(await coveragePanel().locator('[data-homework-review-result] .homework-review-counts').innerText(),/1题未判定/);
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){await coveragePanel().locator('[data-homework-review-result]').scrollIntoViewIfNeeded();await p.screenshot({path:require('node:path').join(process.env.HOMEWORK_QUICK_PROOF_DIR,'recheck-pending-'+width+'.png')})}
  await coveragePanel().locator('[data-homework-review-instruction]').fill('虚构补查第2题，按教师参考核对3与4。');
  p.once('dialog',d=>d.accept());await coveragePanel().locator('[data-homework-review-run]').click();await eventually(async()=>/2题 · 1题需订正 · 0题未判定/.test(await coveragePanel().locator('[data-homework-review-result] .homework-review-counts').innerText()),'second question actually rechecked');
  const checkedRow=coveragePanel().locator('[data-homework-review-result] .homework-question').filter({hasText:'虚构甲卷第2题'});assert.match(await checkedRow.innerText(),/孩子作答：3/);assert.match(await checkedRow.innerText(),/教师参考：4/);assert.match(await checkedRow.innerText(),/孩子作答3与教师参考4不同/);
  const coverageCheckedText=await coveragePanel().locator('[data-homework-review-result] textarea').inputValue();await coveragePanel().locator('[data-homework-review-confirm]').check();await coveragePanel().locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await coveragePanel().innerText()),'second result staged');
  const coverageCheckedSaved=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  const coverageWrong=p.locator('#taskFeedbackHistory [data-task-wrong-form="'+coverageOriginal.record_id+'"]');await coverageWrong.locator(':scope > summary').click();for(const [name,value] of [['label','虚构甲卷第2题'],['text','6-2=?'],['answer','3'],['correction','4']])await coverageWrong.locator('[data-wrong-field='+name+']').fill(value);
  const coverageWrongSaved=await threeAttemptSave(p,'/api/wrong/save',coverageWrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await coverageWrong.innerText()),async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  const coverageWrongCard=p.locator('#taskFeedbackHistory .task-feedback-record').filter({has:p.locator('[data-record="'+coverageWrongSaved.record_id+'"]')});await coverageWrongCard.locator('[data-followup]').click();await p.locator('#recordDialog[open]').waitFor();const coverageCorrectionNote='虚构甲卷第2题订正：6-2=4，回原题核对。';await p.locator('#recordForm [name=note]').fill(coverageCorrectionNote);
  const coverageCorrection=await threeAttemptSave(p,'/api/record',p.locator('#recordForm [type=submit]'),async()=>/虚构/.test(await p.locator('#recordError').innerText()),async()=>!await p.locator('#recordDialog').evaluate(x=>x.open),readCause);
  await p.reload();await openCoverage();await p.locator('#taskFeedbackHistory').getByText(coverageCorrectionNote,{exact:false}).waitFor();const reopenedCoverage=p.locator('[data-saved-homework-review="'+coverageCheckedSaved.record_id+'"] [data-saved-review-text]');await eventually(async()=>await reopenedCoverage.innerText()===coverageCheckedText,'second check saved under original task');
  state=await readCause();for(const id of [coverageGapSaved.record_id,coverageCheckedSaved.record_id,coverageWrongSaved.record_id,coverageCorrection.record_id]){const r=state.records.find(x=>x.id===id);assert.equal(r.child,child);assert.equal(r.linked_task_id,coverageTask.id)}assert.equal(state.tasks.find(t=>t.id===coverageTask.id).update,null);assert.deepEqual(state.printing.jobs.map(j=>j.id).sort(),printIdsBeforeChecks);
  const coverageTrace=await(await fetch(host.url+'__fixture/question-coverage')).json();assert.equal(coverageTrace.calls.length,coverageTraceBefore+4);assert(coverageTrace.calls.slice(-4).every(call=>JSON.stringify(call.raw)===JSON.stringify(call.original)));
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'question-coverage-'+width+'.json'),JSON.stringify({scope:'synthetic identified question omitted, saved, reopened and actually rechecked; real HTTP/shared validator; zero actual model or business calls',validator:coverageTrace.calls.slice(-2),original:coverageOriginal,gap:coverageGapSaved,checked:coverageCheckedSaved,wrong:coverageWrongSaved,correction:coverageCorrection},null,2));await reopenedCoverage.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'question-coverage-reopened-'+width+'.png')})}
  // Isolated origin regression: real HTTP creates F(Q,S,P), then ordinary R2
  // reuses that exact P. Only fixed synthetic model raw bypasses the transport.
  await p.locator('#taskDialog [data-close="taskDialog"]').click();state=await readCause();
  const readOrigin=async()=>await(await fetch(host.url+'__fixture/review-origin')).json(),originBefore=await readOrigin();
  const originTask=(await post('api/task/new',{child,title:'虚构来源身份 '+width,category:'homework',action:'虚构来源身份 '+width+'：甲卷第1题2+3=?，按教师原参考复核最终作答4。',due:state.today})).task;
  const originUpload=async(name,mime,buffer)=>{const response=await fetch(host.url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'Content-Type':mime,'X-File-Name':encodeURIComponent(name)},body:buffer});assert.equal(response.status,200);return (await response.json()).attachment};
  const originFeedback=async(key,attachments,note,extra={})=>post('api/task/feedback',{task_id:originTask.id,child,day:state.today,request_key:'synthetic-origin-ui-'+width+'-'+key,attachments,note,...extra});
  const originPhoto=await originUpload('synthetic-origin-ui-answer-'+width+'.png','image/png',causeImage);
  const originOriginal=await originFeedback('original',[originPhoto.id],'虚构身份甲卷第1题，完整题面2+3=?，最终作答4。');
  const originName='作业批改参考-'+originOriginal.record_id+'.txt',originTeacherText='虚构身份甲卷第1题教师原参考：2+3=5。';
  const originTeacher=await originUpload(originName,'text/plain',Buffer.from(originTeacherText));
  const originTeacherRecord=await originFeedback('teacher',[originTeacher.id],'虚构教师原参考资料，按附件原文核对。');
  const originInitial=await post('api/print/homework/draft',{purpose:'review',task_id:originTask.id,record_id:originOriginal.record_id,expected_created:originOriginal.feedback.created,question_sources:[{type:'upload',id:originPhoto.id}],reference_sources:[{type:'upload',id:originTeacher.id}]});
  const originOpinion=await originUpload(originName,'text/plain',Buffer.from(originInitial.draft.text));assert.notEqual(originOpinion.id,originTeacher.id);assert.equal(originOpinion.name,originTeacher.name,'same filename does not identify the teacher or generated result');
  const originFormal=await originFeedback('formal',[originPhoto.id,originTeacher.id,originOpinion.id],'家长核对的作业批改参考；完整逐题意见见文字附件。原作答反馈 #'+originOriginal.record_id+'。',{review_basis:originInitial.review_basis});
  const originR2=await originFeedback('reattached',[originPhoto.id,originOpinion.id],'虚构身份甲卷第1题最终作答4；重挂原照片与上一轮AI意见。');
  let originTrace=await readOrigin();assert(originTrace.synthetic_only&&originTrace.shared_validator);assert.equal(originTrace.real_model_calls,0);assert.equal(originTrace.calls.length,originBefore.calls.length+1);
  const originFormalRow=originTrace.records.find(r=>r.id===originFormal.record_id);assert.equal(originFormalRow.followup_kind,'作业检查');assert.equal(originFormalRow.related_record_id,originOriginal.record_id);assert.deepEqual(JSON.parse(originFormalRow.review_output_ids),[originOpinion.id],'formal output binding excludes the retained same-name teacher TXT');
  const originSources=await(await fetch(host.url+'api/print/homework/sources?task_id='+originTask.id+'&record_id='+originR2.record_id)).json();assert.equal(originSources.created,originR2.feedback.created);
  assert.equal(originSources.sources.find(a=>a.id===originOpinion.id).origin,'review_result');assert.equal(originSources.sources.find(a=>a.id===originTeacher.id).origin,'same_task');assert.deepEqual((await readOrigin()).records,originTrace.records,'source listing does not rewrite original bindings');
  const openOrigin=async()=>{await p.locator('nav [data-page=tasks]').click();await p.locator('body[data-page=tasks] #task-group-homework').waitFor();await p.locator('[data-task-box=Inbox]').click();await p.locator('#content [data-task="'+originTask.id+'"]:visible').first().click();await p.locator('#taskDialog[open]').waitFor()};
  const originPanel=()=>p.locator('#taskFeedbackHistory [data-homework-review="'+originR2.record_id+'"]');
  const originRows=()=>({photo:originPanel().locator('[data-review-source="'+originPhoto.id+'"]'),teacher:originPanel().locator('[data-review-source="'+originTeacher.id+'"]'),previous:originPanel().locator('[data-review-source="'+originOpinion.id+'"]')});
  const checkOriginChoices=async()=>{const rows=originRows();await rows.teacher.waitFor();await eventually(async()=>JSON.stringify(await rows.previous.locator('[data-homework-review-role] option').evaluateAll(xs=>xs.map(x=>x.value)))==='["previous"]','reattached output exposes only the previous-opinion role');assert.deepEqual(await rows.previous.locator('[data-homework-review-role] option').allTextContents(),['上次 AI 检查 · 供复核']);assert((await rows.teacher.locator('[data-homework-review-role] option').evaluateAll(xs=>xs.map(x=>x.value))).includes('reference'));return rows};
  await p.reload();await openOrigin();await originPanel().locator(':scope > details > summary').click();const originChoices=await checkOriginChoices();
  await originChoices.photo.locator('[data-homework-review-photo]').check();await originChoices.teacher.locator('[data-homework-review-photo]').check();await originChoices.previous.locator('[data-homework-review-photo]').check();
  for(const [row,role] of [[originChoices.teacher,'reference'],[originChoices.previous,'previous']]){assert.equal(await row.locator('[data-homework-review-role]').isVisible(),true,'the source role is visible in its row');await row.locator('[data-homework-review-role]').selectOption(role)}
  const originDraftBodies=[];let originReply;
  await p.route('**/api/print/homework/draft',async route=>{originDraftBodies.push(route.request().postDataJSON());if(originDraftBodies.length===1)return route.fulfill({status:503,json:{error:'虚构来源身份检查暂不可用'}});const response=await route.fetch();assert.equal(response.status(),200);originReply=await response.json();await route.fulfill({response,json:originReply})});
  try{
   await originPanel().locator('[data-homework-review-run]').click();await eventually(async()=>/虚构来源身份检查暂不可用/.test(await originPanel().innerText()),'origin draft 503 keeps saved originals');
   assert.equal((await readOrigin()).calls.length,originBefore.calls.length+1);assert.deepEqual((await readOrigin()).records,originTrace.records);
   for(const row of Object.values(originChoices))assert.equal(await row.locator('[data-homework-review-photo]').isChecked(),true,'draft failure retains each selected input');
   assert.equal(await originChoices.teacher.locator('[data-homework-review-role]').inputValue(),'reference');assert.equal(await originChoices.previous.locator('[data-homework-review-role]').inputValue(),'previous');
   await originPanel().locator('[data-homework-review-run]').click();await eventually(async()=>!!originReply,'origin recheck reaches the real shared validator');
  }finally{await p.unroute('**/api/print/homework/draft')}
  assert.equal(originDraftBodies.length,2);assert.deepEqual(originDraftBodies[0],originDraftBodies[1]);const originRequest=originDraftBodies[1];
  assert.equal(originRequest.record_id,originR2.record_id);assert.deepEqual(originRequest.question_sources,[{type:'upload',id:originPhoto.id}]);assert.deepEqual(originRequest.reference_sources,[{type:'upload',id:originTeacher.id}]);assert.deepEqual(originRequest.previous_sources,[{type:'upload',id:originOpinion.id}]);
  originTrace=await readOrigin();assert.equal(originTrace.calls.length,originBefore.calls.length+2);const originCall=originTrace.calls.at(-1),originInputs=originCall.inputs;
  assert.deepEqual(originInputs.images,[{mime:'image/png',sha256:require('node:crypto').createHash('sha256').update(causeImage).digest('hex')}]);assert.equal(originInputs.reference_image_count,0);assert.deepEqual(originInputs.question_documents,[]);assert.deepEqual(originInputs.reference_documents,[{name:originName,text:originTeacherText}]);assert.deepEqual(originInputs.previous_documents,[{name:originName,text:originInitial.draft.text}]);assert.equal(originInputs.previous_text,'');assert.equal(originInputs.answer_note,originR2.feedback.note);
  assert.equal(originCall.image_count,1);assert(originCall.texts.some(text=>text.startsWith('教师参考原文')&&text.includes(originTeacherText)));assert(!originCall.texts.filter(text=>text.startsWith('教师参考原文')).some(text=>text.includes(originInitial.draft.text)));assert(originCall.texts.some(text=>text.startsWith('上一轮待复核意见原文')&&text.includes('不是教师参考')));assertDraftReceipt(originCall.validated,originReply.draft);assert.deepEqual(originCall.raw,originCall.original);
  await eventually(async()=>/1题 · 1题需订正 · 0题未判定/.test(await originPanel().locator('[data-homework-review-result] .homework-review-counts').innerText()),'reattached result supports explicit previous-opinion recheck');assert.match(originReply.draft.comparison,/旧AI意见不作答案依据/);assert.match(originReply.draft.unverified_model_summary.comparison,/旧AI意见仅供对照/);
  await originPanel().locator('[data-homework-review-confirm]').check();await originPanel().locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await originPanel().innerText()),'origin recheck stages a new result');
  const originSaved=await threeAttemptSave(p,'/api/task/feedback',p.locator('#saveTaskFeedback'),async()=>/虚构/.test(await p.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),readCause);
  state=await readCause();const originSavedRecord=state.records.find(r=>r.id===originSaved.record_id),originSavedOutputs=originSavedRecord.attachments.filter(id=>![originPhoto.id,originTeacher.id,originOpinion.id].includes(id));assert.equal(originSavedOutputs.length,1);assert.equal(originSavedRecord.followup_kind,'作业检查');assert.equal(originSavedRecord.related_record_id,originR2.record_id);assert.equal(originSavedRecord.linked_task_id,originTask.id);assert.equal(originSavedRecord.child,child);assert(originSavedRecord.attachments.includes(originTeacher.id));
  const originAfterSave=await readOrigin();assert.deepEqual(JSON.parse(originAfterSave.records.find(r=>r.id===originSaved.record_id).review_output_ids),originSavedOutputs);assert.deepEqual(originAfterSave.records.find(r=>r.id===originFormal.record_id),originFormalRow);assert.deepEqual(originAfterSave.records.find(r=>r.id===originTeacherRecord.record_id),originTrace.records.find(r=>r.id===originTeacherRecord.record_id));assert.equal(originAfterSave.calls.length,originBefore.calls.length+2,'save and lost-receipt retry add no model call');
  await p.reload();await openOrigin();const reopenedOrigin=p.locator('[data-saved-homework-review="'+originSaved.record_id+'"] [data-saved-review-text]');await eventually(async()=>await reopenedOrigin.innerText()===originReply.draft.text,'origin recheck reopens its complete saved opinion under R2');
  await originPanel().locator(':scope > details > summary').click();await checkOriginChoices();const originReopenedSources=await(await fetch(host.url+'api/print/homework/sources?task_id='+originTask.id+'&record_id='+originR2.record_id)).json();for(const id of [originOpinion.id,...originSavedOutputs])assert.equal(originReopenedSources.sources.find(a=>a.id===id).origin,'review_result');assert.equal(originReopenedSources.sources.find(a=>a.id===originTeacher.id).origin,'same_task');assert.deepEqual((await readOrigin()).records,originAfterSave.records);assert.equal((await readOrigin()).calls.length,originBefore.calls.length+2);assert.equal((await(await fetch(host.url+'__fixture/cause-validator')).json()).calls.length,consistencyTrace.calls.length,'isolated origin fixture does not change prior model assertions');
  state=await readCause();assert.equal(state.tasks.find(t=>t.id===originTask.id).update,null);assert.equal(state.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===originTask.id).length,0);assert.deepEqual(state.printing.jobs.map(j=>j.id).sort(),printIdsBeforeChecks);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.HOMEWORK_QUICK_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'review-origin-'+width+'.json'),JSON.stringify({scope:'synthetic same-name teacher and AI output; real HTTP, shared validator, browser save/retry/reopen; not model accuracy',original:originOriginal.record_id,formal:originFormal.record_id,reattached:originR2.record_id,photo:originPhoto.id,teacher:originTeacher.id,previous:originOpinion.id,request:originRequest,validator:originCall,feedback:originSaved,output_ids:originSavedOutputs,sources:originReopenedSources},null,2));await reopenedOrigin.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.HOMEWORK_QUICK_PROOF_DIR,'review-origin-reopened-'+width+'.png')})}
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
