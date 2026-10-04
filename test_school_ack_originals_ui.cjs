// Synthetic software acceptance only; no model, collector, household data or printer.
// Set SCHOOL_ACK_PROOF_DIR outside the checkout. Run only after committing this file.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const fs=require('node:fs/promises');
const path=require('node:path');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const proofDir=process.env.SCHOOL_ACK_PROOF_DIR;

async function eventually(fn,label){
 const until=Date.now()+10000;
 while(Date.now()<until){if(await fn())return;await delay(40)}
 throw Error('Timed out: '+label);
}
async function server(){
 const env={...process.env,PYTHONDONTWRITEBYTECODE:'1'};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const setup=String.raw`import copy,datetime as dt,io,json,struct,sys,zlib
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from test_school_ack_originals import SchoolAckOriginalTests
import family_agent as agent
import family_media

fixture=SchoolAckOriginalTests(methodName='runTest');fixture.setUp()
try:
    app,store=fixture.app,fixture.store
    source_root=Path.cwd().resolve()
    assert app.ROOT!=source_root and app.DATA.is_relative_to(app.ROOT)
    # ROOT reads only synthetic documents. Static assets point at this candidate.
    (app.ROOT/'家庭运行规则.md').write_text('| child-1 | 虚构甲 | — | 10岁 | 四年级 |\n| child-2 | 虚构乙 | — | 13岁 | 初一 |\n')
    for name in set(app.STATIC.values())|set(app.BUNDLE):
        original=source_root/name
        assert original.is_file()
        link=app.ROOT/name;link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to(original)
    now=dt.datetime.now(agent.TZ).replace(hour=8,minute=0,second=0,microsecond=0)
    fixture.now=fixture.fixture.now=now
    today=now.date().isoformat()
    clock=fixture.stack.enter_context(patch.object(agent,'_now',return_value=now))
    # Every outbound connection is forbidden; serving loopback HTTP needs none.
    fixture.stack.enter_context(patch('socket.create_connection',side_effect=AssertionError('outbound network forbidden')))
    values=fixture._input(kind='image',unread=True)
    first=agent.run_once(app,now)
    assert first['failed']==0 and first['created']==1
    fixture.model.assert_not_called()
    with store._db() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
        assert len(rows)==1
        pending=rows[0]
        assert pending['state']=='pending' and pending['due']=='' and not pending['task_id']
        assert json.loads(pending['plan'])['school_task']['state']=='review'
        assert 'school_history_job' not in json.loads(pending['plan'])
        assert c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==0

    # A valid, generated PNG and a prepared fictional reading receipt; no vision call.
    def chunk(kind,body):
        return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+bytes([30,60,90,255])*2)*2))+chunk(b'IEND',b'')
    upload=app.save_upload(io.BytesIO(png),len(png),'synthetic-school-original.png')
    identity=dict(child_id='child-1',source_id=fixture.source['id'],message_id=values[0]['id'])
    store.message_attachment(dict(identity,attachment_id=upload['id'],action='attach'),dict)
    title='英语：Unit 2朗读与第8页练习'
    requirements='英语：朗读Unit 2课文两遍；完成练习册第8页。'+today+'完成，不必录音。'
    with store._db() as c:
        source,message=store._message_context(c,identity)
        value=family_media.draft_input(store,c,source,message)
        original=dict(upload_id=upload['id'],title=title,note=requirements,requirements=[requirements],uncertainties=[])
        draft=dict(kind='school_material',**agent.family_llm.validate_school_material(dict(originals=[original]),original_ids=value['original_ids']))
        c.execute('INSERT INTO agent_message_drafts VALUES(?,?,?,?,?)',(source['id'],message['id'],value['fingerprint'],json.dumps(draft,ensure_ascii=False),now.isoformat()))
        before_messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages')]
        before_sources=[dict(r) for r in c.execute('SELECT * FROM agent_sources')]
    ready=dict(title=title,goal=requirements,advice='',state='ready',reason='虚构完整原件要求明确。',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id='')
    calls=[]
    def fixed(messages,schema,name,*args,**kwargs):
        context=json.loads(messages[-1]['content'])
        assert name=='family_school_task' and kwargs.get('data_path')==app.DATA
        assert context['candidate_id']==pending['id'] and context['child_id']=='child-1' and context['as_of']==today
        parts=[p for p in context['original_parts'] if p.get('upload_ids')]
        assert len(parts)==1 and parts[0]['upload_ids']==[upload['id']] and parts[0]['text']==requirements
        assert parts[0]['ref']=='message:'+identity['source_id']+':'+identity['message_id']
        result=fixture.fixture._original_reply(pending['id'],ready)
        result['actions'][0]['due']=today
        calls.append(dict(name=name,candidate_id=pending['id'],upload_id=upload['id']))
        return copy.deepcopy(result)
    fixture.model.side_effect=fixed
    refreshed=agent._refresh_school(app,store,now,1)
    assert refreshed==dict(used=1,failed=0,created=1) and fixture.model.call_count==1
    fixture.model.side_effect=AssertionError('no further model calls allowed')
    assert agent._refresh_school(app,store,now+dt.timedelta(minutes=1),1)==dict(used=0,failed=0,created=0)
    with store._db() as c:
        accepted=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(pending['id'],)).fetchone())
        assert accepted['state']=='accepted' and accepted['title']==title and accepted['due']==today
        assert c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==0
        assert [dict(r) for r in c.execute('SELECT * FROM agent_messages')]==before_messages
        assert [dict(r) for r in c.execute('SELECT * FROM agent_sources')]==before_sources
        task=next(t for t in app.tasks(c) if t['id']==accepted['task_id'])
        assert task['child']=='虚构甲' and task['action']==requirements and task['agenda']['due_on']==today
    proof=dict(synthetic_only=True,real_model_calls=0,collector_calls=0,printer_calls=0,
        candidate_id=pending['id'],task_id=accepted['task_id'],title=title,requirements=requirements,today=today,
        identity=identity,upload_id=upload['id'],caption=values[0]['text'],initial=dict(state=pending['state'],due=pending['due'],confirmed_tasks=0,records=0),
        final=dict(state=accepted['state'],due=accepted['due'],confirmed_tasks=1,records=0),mock_calls=calls,messages_and_sources_preserved=True)
    class Handler(app.Handler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/__fixture/proof':return self.reply(200,proof)
            return super().do_GET()
        def do_POST(self):
            if urlparse(self.path).path!='/api/task/feedback':return self.reply(503,dict(error='synthetic test forbids model, collection and print actions'))
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
 proc.stdout.on('data',b=>{output=(output+b).slice(-4000)});
 proc.stderr.on('data',b=>{diagnostic=(diagnostic+b).slice(-12000)});
 proc.on('error',e=>{spawnError=e});
 const stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2000)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{
  await eventually(async()=>{if(spawnError)throw spawnError;if(proc.exitCode!==null)throw Error('Synthetic server failed: '+diagnostic);return /READY http:\/\/127\.0\.0\.1:\d+\//.test(output)},'isolated HTTP startup');
  return {url:output.match(/READY (http:\/\/127\.0\.0\.1:\d+\/)/)[1],stop};
 }catch(error){await stop();throw error}
}
async function json(url,options={}){
 const response=await fetch(url,{...options,signal:AbortSignal.timeout(5000)});
 assert.equal(response.status,200,'real local HTTP success: '+new URL(url).pathname);
 return response.json();
}
async function noOverflow(page){
 const sizes=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth,dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>({width:d.clientWidth,scroll:d.scrollWidth,left:d.getBoundingClientRect().left,right:d.getBoundingClientRect().right}))}));
 assert(sizes.page<=sizes.viewport+1,JSON.stringify(sizes));
 for(const d of sizes.dialogs)assert(d.scroll<=d.width+1&&d.left>=-1&&d.right<=sizes.viewport+1,JSON.stringify(sizes));
}
async function screenshot(page,name){await noOverflow(page);await page.screenshot({path:path.join(proofDir,name),fullPage:true})}

(async()=>{
 let host,browser,lastPage;
 const proof={synthetic_only:true,status:'running',real_model_calls:0,collector_calls:0,printer_calls:0,widths:[]};
 try{
  assert(proofDir,'SCHOOL_ACK_PROOF_DIR is required');await fs.mkdir(proofDir,{recursive:true});
  host=await server();proof.intake=await json(host.url+'__fixture/proof');
  browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  for(const width of [360,1440]){
   const page=await browser.newPage({viewport:{width,height:850},timezoneId:'Asia/Shanghai'});lastPage=page;page.setDefaultTimeout(10000);
   const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',route=>{const url=route.request().url();if(url.startsWith(host.url)||url.startsWith('data:')||url.startsWith('blob:'))return route.continue();external.push(url);return route.abort()});
   const read=()=>json(host.url+'api/state'),item=proof.intake,id=item.task_id;
   let state=await read();assert.equal(state.today,item.today);assert.equal(state.tasks.length,1);
   await page.goto(host.url,{waitUntil:'domcontentloaded',timeout:15000});
   await page.locator('[data-child-filter="child-1"]').click();
   const card=page.locator('[data-query-target="task:'+id+'"]');await card.waitFor();
   assert.match(await card.innerText(),/Unit 2/);assert.match(await card.innerText(),/第8页/);assert.match(await card.innerText(),/两遍/);assert.match(await card.innerText(),/不必录音/);
   assert.equal(await card.locator('[data-school-original-child]').first().getAttribute('data-school-original-child'),'child-1');
   await screenshot(page,'today-'+width+'.png');
   await card.locator('[data-school-original-ref]').first().click();
   const original=page.locator('#schoolOriginalDialog');await page.locator('#schoolOriginalDialog[open]').waitFor();
   await original.locator('img[src$="'+item.upload_id+'"]').waitFor();
   await eventually(()=>original.locator('img').first().evaluate(i=>i.complete&&i.naturalWidth>0),'synthetic original pixels');
   await original.locator('[data-school-task-source]').click();
   await eventually(async()=>await original.locator('blockquote').textContent()===item.caption,'original acknowledgement retained');
   assert.equal(await original.locator('a[href$="'+item.upload_id+'"]').count(),1);
   const [popup]=await Promise.all([page.waitForEvent('popup'),original.locator('a[href$="'+item.upload_id+'"]').click()]);
   await popup.waitForLoadState('domcontentloaded');assert.equal(popup.url(),host.url+'upload/'+item.upload_id);await popup.close();
   await screenshot(page,'original-'+width+'.png');await original.locator('[data-school-original-close]').click();
   await card.locator('[data-task="'+id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();
   assert.equal(await page.locator('#taskForm [name=id]').inputValue(),id);
   assert.match(await page.locator('#taskTitle').innerText(),/虚构甲/);
   assert.equal(await page.locator('#taskRequirement').innerText(),item.requirements);
   const note='虚构反馈 '+width+'：已朗读一遍，练习尚未做；完成情况待核对。';
   await page.locator('#taskForm [name=note]').fill(note);
   const before=await read(),bodies=[],receipts=[];
   await page.route('**/api/task/feedback',async route=>{
    bodies.push(route.request().postDataJSON());
    if(bodies.length===1)return route.fulfill({status:503,json:{error:'虚构未写入失败'}});
    const response=await route.fetch({timeout:5000}),value=await response.json();assert.equal(response.status(),200);receipts.push(value);
    return bodies.length===2?route.fulfill({status:503,json:{error:'虚构写入成功但回执丢失'}}):route.fulfill({response,json:value});
   });
   const save=page.locator('#saveTaskFeedback'),error=page.locator('#taskError');
   await save.click();await eventually(async()=>/虚构未写入失败/.test(await error.innerText())&&await save.isEnabled(),'503 no-write retry');
   assert.deepEqual((await read()).records,before.records);assert.equal(await page.locator('#taskForm [name=note]').inputValue(),note);
   await save.click();await eventually(async()=>/虚构写入成功但回执丢失/.test(await error.innerText())&&await save.isEnabled(),'lost receipt retained');
   assert.equal((await read()).records.length,before.records.length+1);await screenshot(page,'feedback-retry-'+width+'.png');
   await save.click();await eventually(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'same numbered retry saved');
   await page.unroute('**/api/task/feedback');assert.equal(bodies.length,3);assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[1],bodies[2]);
   assert.equal(bodies[0].task_id,id);assert.equal(bodies[0].child,'虚构甲');assert(bodies[0].request_key);assert.equal(receipts[0].record_id,receipts[1].record_id);assert.equal(receipts[1].replayed,true);
   state=await read();const saved=state.records.find(r=>r.id===receipts[1].record_id);
   assert.equal(state.records.length,before.records.length+1);assert.equal(saved.source,'事项:'+id);assert.equal(saved.child,'虚构甲');assert.equal(saved.note,note);
   assert.deepEqual(state.tasks,before.tasks,'ordinary feedback does not complete or replace the original task');
   await page.locator('#taskDialog [data-close="taskDialog"]').click();await page.reload();await card.waitFor();
   await card.locator('[data-task="'+id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();
   assert.equal(await page.locator('#taskForm [name=id]').inputValue(),id);assert.match(await page.locator('#taskFeedbackHistory').innerText(),new RegExp('虚构反馈 '+width));
   assert.equal(await page.locator('#taskFeedbackHistory [data-task-feedback-edit="'+saved.id+'"]').count(),1);
   await screenshot(page,'feedback-reopen-'+width+'.png');await page.locator('#taskDialog [data-close="taskDialog"]').click();
   await page.locator('[data-child-filter="child-2"]').click();assert.equal(await card.count(),0);assert.equal(await page.locator('#content [data-school-original-ref]').count(),0);await noOverflow(page);
   const wrongOriginal=await fetch(host.url+'api/agent/message?'+new URLSearchParams({...item.identity,child_id:'child-2'}),{signal:AbortSignal.timeout(5000)});assert.equal(wrongOriginal.status,403);
   const cross=await fetch(host.url+'api/task/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify({...bodies[0],child:'虚构乙',request_key:'synthetic-cross-child-'+width}),signal:AbortSignal.timeout(5000)});assert.equal(cross.status,409);
   assert.deepEqual((await read()).records,state.records,'cross-child requests wrote nothing');
   await page.locator('[data-child-filter="child-1"]').click();await card.waitFor();assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
   proof.widths.push({width,task_id:id,record_id:saved.id,request_key:bodies[0].request_key,retry_posts:3,no_write_503:true,lost_receipt_replayed:true,reopened_same_task:true,cross_child_rejected:true,no_horizontal_overflow:true});
   await page.close();lastPage=null;
  }
  proof.status='passed';console.log('school acknowledgement originals: 360/1440 passed (synthetic only)');
 }catch(error){proof.status='failed';proof.error=error.message;if(lastPage&&proofDir)await lastPage.screenshot({path:path.join(proofDir,'failure.png'),fullPage:true}).catch(()=>{});throw error}
 finally{if(proofDir)await fs.writeFile(path.join(proofDir,'proof.json'),JSON.stringify(proof,null,2));if(browser)await browser.close();if(host)await host.stop()}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
