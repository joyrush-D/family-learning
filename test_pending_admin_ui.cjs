// Disposable synthetic backend + browser journey; no family records, models or devices.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON,
// PENDING_ADMIN_UI_PROOF_DIR. Only the temporary loopback server is contacted.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');

async function eventually(check,label,timeout=10000){
 const end=Date.now()+timeout;
 while(Date.now()<end){if(await check())return;await delay(40)}
 throw Error('Timed out: '+label);
}
async function fit(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no page overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
}
async function ready(page){
 await eventually(async()=>await page.locator('body[data-page="home"] #task-group-todo').isVisible()&&await page.locator('#content').getAttribute('data-ready')==='true','today is ready');
}
async function proof(page,name){
 if(!process.env.PENDING_ADMIN_UI_PROOF_DIR)return;
 const fs=require('node:fs/promises'),path=require('node:path');
 await fs.mkdir(process.env.PENDING_ADMIN_UI_PROOF_DIR,{recursive:true});
 await page.screenshot({path:path.join(process.env.PENDING_ADMIN_UI_PROOF_DIR,name+'.png'),fullPage:true});
}

const fixture=String.raw`
import tempfile,os,json,datetime
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='synthetic-pending-admin-ui-') as folder:
 os.environ['FAMILY_DATA']=folder
 import app,family_agent,family_task_focus
 app.DATA=Path(folder).resolve();app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例甲 | — | 9岁 | 三年级 |\n| child-2 | 示例乙 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 now=datetime.datetime.now(family_agent.TZ)
 old=now-datetime.timedelta(days=3);newer=now-datetime.timedelta(days=1);future=now+datetime.timedelta(days=2)
 sources=[dict(id='synthetic-admin',platform='wechat',child_id='child-1',name='虚构行政通知群',cursor='',enabled=True),
          dict(id='synthetic-sibling',platform='wechat',child_id='child-2',name='虚构另一孩子通知群',cursor='',enabled=True)]
 (app.DATA/'agent.json').write_text(json.dumps(dict(enabled=True,sources=sources)),encoding='utf-8')
 store=app.agent_store()
 entries=[('A','synthetic-admin',old.isoformat(),'虚构家长回执 A','请家长核对虚构活动回执并签字。','虚构行政通知 A：请家长核对活动回执并签字。截止日期另行通知。\n原文末尾核对标记：ADMIN_ORIGINAL_A_END。'),
          ('B','synthetic-admin',newer.isoformat(),'虚构材料登记 B','请家长核对虚构材料登记。','虚构行政通知 B：请家长核对材料登记。截止日期尚未提供。'),
          ('C','synthetic-admin','','虚构日期未知通知 C','请家长核对虚构联系方式。','虚构行政通知 C：请家长核对联系方式。发送日期与截止日期均未知。'),
          ('FUTURE','synthetic-admin',future.isoformat(),'FUTURE_PUBLICATION_CANARY','请家长核对将来才发布的通知。','虚构将来行政通知，尚未到发布日期。'),
          ('DISMISSED','synthetic-admin',old.isoformat(),'DISMISSED_NOTICE_CANARY','虚构已忽略学校事项。','虚构已忽略行政通知。'),
          ('REFERENCE','synthetic-admin',old.isoformat(),'REFERENCE_NOTICE_CANARY','虚构参考说明，没有行动。','虚构行政资料说明。'),
          ('SIBLING','synthetic-sibling',old.isoformat(),'SIBLING_NOTICE_CANARY','请另一孩子的家长核对独立回执。','虚构另一孩子的行政通知。')]
 for source in sources:
  messages=[dict(id=key,time=time,kind='text',sender='虚构通知人',sender_id='synthetic-publisher',text=text,unread=False)
            for key,sid,time,title,goal,text in entries if sid==source['id']]
  store.ingest(dict(source_id=source['id'],expected_cursor='',cursor='synthetic-page-1',checked_at=now.isoformat(),last_message_time=now.isoformat(),messages=messages,error=''))
 for key,sid,time,title,goal,text in entries:
  child_id='child-2' if sid=='synthetic-sibling' else 'child-1'
  # Legacy review rows intentionally have no generated snapshot or current policy.
  # They may be accepted manually; visibility never changes their pending state.
  brief=dict(title=title,goal=goal,state='reference' if key=='REFERENCE' else 'review',purpose='admin',reason='日期或执行信息待家长核对。')
  store._save('synthetic-admin:'+key,'synthetic-fixture',[dict(child_id=child_id,kind='school',title=title,body=goal,due='',
              evidence=[dict(ref='message:'+sid+':'+key,text=text)],plan=dict(school_task=brief))],now)
  if key=='DISMISSED':
   with store._db() as c:ident=c.execute('SELECT id FROM agent_items WHERE job_id=?',('synthetic-admin:'+key,)).fetchone()[0]
   store.act(dict(id=ident,action='dismiss'))
 for label,state in [('DONE','已完成'),('DECLINED','不参加'),('NA','不适用')]:
  task=app.new_task(dict(child='示例甲',title=label+'_TASK_CANARY',category='todo',action='虚构已关闭行政事项。'))
  app.save_task(dict(id=task['id'],status=state,note='虚构家长已明确作出处理决定。'))
 app.new_task(dict(child='示例甲',title='WISH_TASK_CANARY',category='todo',box='wish',action='虚构尚未安排的心愿。'))
 planned=app.new_task(dict(child='示例甲',title='FUTURE_PLAN_CANARY',category='todo',action='虚构仅安排在未来的行政事项。'))
 family_task_focus.save(app,dict(id=planned['id'],version=1,request_key='synthetic-admin-future-plan',mode='next',next_action='',waiting_for='',review_on='',scheduled_on=future.date().isoformat()))
 store._runtime('ready',now)
 app.prepare_assets()
 server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_PENDING_ADMIN_PORT'])),app.Handler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
`;

async function startServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');
 const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const url='http://127.0.0.1:'+port+'/',env={...process.env};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 env.TEST_PENDING_ADMIN_PORT=String(port);
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});
 let error,stderr='';proc.on('error',e=>error=e);proc.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-12000)});
 const stop=async()=>{
  if(error||proc.exitCode!==null||proc.signalCode!==null)return;
  const exited=once(proc,'exit');proc.kill('SIGINT');await Promise.race([exited,delay(2500)]);
  if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await Promise.race([exited,delay(2500)])}
 };
 try{
  await eventually(async()=>{
   if(error)throw error;if(proc.exitCode!==null)throw Error('Synthetic server exited: '+stderr);
   try{return (await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}
  },'isolated server startup');
  return {url,stop};
 }catch(e){await stop();throw e}
}
const titles={A:'虚构家长回执 A',B:'虚构材料登记 B',C:'虚构日期未知通知 C',SIBLING:'SIBLING_NOTICE_CANARY'};
const item=(state,key)=>state.agent.items.find(x=>x.title===titles[key]);
const taskStatus=task=>task.update?.status||task.original_status;

(async()=>{
 let browser,server,page;const checks=[];
 try{
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440]){
   server=await startServer();
   const read=async()=>await(await fetch(server.url+'api/state',{signal:AbortSignal.timeout(5000)})).json();
   const baseline=await read(),a=item(baseline,'A'),b=item(baseline,'B'),c=item(baseline,'C'),sibling=item(baseline,'SIBLING');
   assert.ok(a&&b&&c&&sibling,'synthetic pending rows exist in the real backend');
   const row=id=>baseline.today_calendar.inbox.find(x=>x.id===id),ref=a.evidence[0].ref;
   assert.equal(row(a.id).agenda.category,'todo');assert.equal(row(a.id).agenda.due_on,'');
   assert.ok(row(a.id).agenda.published_on<row(b.id).agenda.published_on,'A is older than B');
   assert.equal(row(c.id).agenda.published_on,'','C publication is genuinely unknown');
   let hideNewer=true;const errors=[],foreign=[],writes=[],originalReads=[],accepts=[];
   page=await browser.newPage({viewport:{width,height:820}});page.setDefaultTimeout(10000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('request',request=>{if(request.method()==='POST')writes.push(new URL(request.url()).pathname)});
   await page.route('**/*',async route=>{
    if(new URL(route.request().url()).origin!==new URL(server.url).origin){foreign.push(route.request().url());return route.abort()}
    await route.continue();
   });
   // Only B is hidden, to reproduce a new saved notice arriving after the first view.
   // All visible rows, reads and successful writes come from the temporary backend.
   await page.route('**/api/state',async route=>{
    const response=await route.fetch(),value=await response.json();
    if(hideNewer){value.agent.items=value.agent.items.filter(x=>x.id!==b.id);for(const key of ['inbox','agenda'])value.today_calendar[key]=value.today_calendar[key].filter(x=>x.id!==b.id)}
    await route.fulfill({response,json:value});
   });
   await page.route('**/api/agent/message?*',async route=>{
    const identity=Object.fromEntries(new URL(route.request().url()).searchParams);originalReads.push(identity);
    if(originalReads.length===1)return route.fulfill({status:503,json:{error:'虚构原消息读取暂时失败'}});
    await route.continue();
   });
   await page.route('**/api/agent/action',async route=>{
    const body=route.request().postDataJSON();accepts.push(body);
    if(accepts.length===1)return route.fulfill({status:503,json:{error:'虚构确认保存暂时失败'}});
    await route.continue();
   });
   await page.goto(server.url,{waitUntil:'load'});await ready(page);
   const todos=page.locator('#task-group-todo'),notice=id=>page.locator('#school-review-'+id),card=id=>page.locator('[data-today-task="'+id+'"]');
   const pending=async ids=>{
    assert.deepEqual((await todos.locator('[data-agent-item]').evaluateAll(xs=>xs.map(x=>x.dataset.agentItem))).sort(),[...ids].sort(),'all eligible pending admin notices are in the existing direct list');
    for(const id of ids){assert.equal(await notice(id).isVisible(),true);assert.equal(await notice(id).evaluate(x=>!!x.closest('details')),false,'pending notice needs no backlog expansion');assert.equal(await notice(id).locator('[data-check]').count(),0,'pending notice cannot be completed')}
    assert.equal(await todos.locator('.review-link').innerText(),'待核对 '+ids.length);
   };
   const guards=async()=>{
    const visible=await page.locator('#content').innerText();
    for(const marker of ['FUTURE_PUBLICATION_CANARY','DISMISSED_NOTICE_CANARY','REFERENCE_NOTICE_CANARY','DONE_TASK_CANARY','DECLINED_TASK_CANARY','NA_TASK_CANARY','WISH_TASK_CANARY','FUTURE_PLAN_CANARY','SIBLING_NOTICE_CANARY'])assert.equal(visible.includes(marker),false,'today guards stay intact: '+marker);
   };
   await pending([a.id,c.id]);await guards();await fit(page);
   assert.match(await todos.locator('h2').innerText(),/要办的事 · 0/);
   assert.equal(await page.locator('.today-sections a[href="#task-group-todo"]').innerText(),'要办的事 0','pending notices do not count as confirmed tasks');
   assert.match(await notice(a.id).locator('.agenda-dates').innerText(),new RegExp('发布：'+row(a.id).agenda.published_on));
   assert.match(await notice(c.id).locator('.agenda-dates').innerText(),/发布：待核对/);
   assert.match(await notice(a.id).locator('.agenda-dates').innerText(),/截止待核对/);
   assert.equal(await notice(a.id).locator('.school-publication-context').innerText(),'虚构通知人');
   assert.equal(writes.length,0,'opening today never accepts or completes pending notices');
   await proof(page,'initial-pending-admin-'+width);
   hideNewer=false;await page.reload({waitUntil:'load'});await ready(page);
   await pending([a.id,b.id,c.id]);await guards();await fit(page);
   assert.match(await notice(a.id).locator('.agenda-dates').innerText(),new RegExp(row(a.id).agenda.published_on),'newer B does not relabel A publication');
   const unchanged=await read();assert.deepEqual(unchanged.tasks,baseline.tasks);assert.deepEqual(unchanged.agent.items,baseline.agent.items);assert.equal(writes.length,0,'B arrival is read-only');
   await proof(page,'newer-arrival-retains-older-'+width);

   await notice(a.id).locator('[data-school-original-ref]').click();
   const original=page.locator('#schoolOriginalDialog');await eventually(async()=>/虚构原消息读取暂时失败/.test(await original.innerText()),'original read error has arrived');await original.locator('[data-school-original-retry]').waitFor();
   assert.match(await original.innerText(),/虚构原消息读取暂时失败/);await fit(page);
   const identity={source_id:'synthetic-admin',message_id:'A',child_id:'child-1'};
   assert.deepEqual(originalReads,[identity],'first read targets the older original');
   await original.locator('[data-school-original-retry]').click();
   await eventually(async()=>await original.locator('blockquote.source').count()===1,'older original retry loads');
   assert.deepEqual(originalReads,[identity,identity],'retry keeps the original message and child identity');
   assert.equal(await original.locator('blockquote.source').textContent(),a.evidence[0].text,'the complete old original is shown');
   const originalDay=row(a.id).agenda.published_on;assert.match(await original.innerText(),new RegExp(Number(originalDay.slice(5,7))+'/'+Number(originalDay.slice(8,10))),'original dialog retains the sender time in its existing month/day format');await fit(page);await proof(page,'old-original-retry-'+width);
   await original.locator('[data-school-original-close]').click();

   await notice(a.id).locator('[data-agent-accept]').click();
   const form=page.locator('#agentForm');await page.locator('#agentDialog[open]').waitFor();
   assert.equal(await form.locator('[name=id]').inputValue(),a.id);assert.equal(await form.locator('[name=due]').inputValue(),'');
   const title='虚构家长回执 A（人工核对）',goal='家长已核对完整原通知，请签字后保留这份虚构回执。',advice='虚构可选建议：签字前核对项目。';
   await form.locator('[name=title]').fill(title);await form.locator('[name=body]').fill(goal);await form.locator('[name=advice]').fill(advice);await fit(page);
   const beforeFailure=await read();await form.locator('[type=submit]').click();
   await eventually(async()=>/虚构确认保存暂时失败/.test(await page.locator('#agentError').innerText()),'503 is shown without closing the form');
   assert.equal(await page.locator('#agentDialog[open]').count(),1);assert.equal(await form.locator('[name=title]').inputValue(),title);assert.equal(await form.locator('[name=body]').inputValue(),goal);assert.equal(await form.locator('[name=advice]').inputValue(),advice);assert.equal(await form.locator('[name=due]').inputValue(),'');
   const afterFailure=await read();assert.deepEqual(afterFailure.tasks,beforeFailure.tasks,'failed acceptance writes zero tasks');assert.deepEqual(afterFailure.agent.items,beforeFailure.agent.items,'failed acceptance preserves every pending decision');assert.deepEqual(afterFailure.records,beforeFailure.records);await fit(page);await proof(page,'accept-failure-input-preserved-'+width);
   await form.locator('[type=submit]').click();
   await eventually(async()=>await page.locator('#agentDialog[open]').count()===0&&await todos.locator('[data-today-task]').count()===1,'retry saves through the real backend');
   assert.equal(accepts.length,2);assert.deepEqual(accepts[1],accepts[0],'retry submits the same manual confirmation');
   assert.equal(accepts[1].id,a.id);assert.equal(accepts[1].action,'accept');assert.equal(accepts[1].school_new,true);assert.equal(accepts[1].due,'');
   const saved=await read(),accepted=item(saved,'A'),task=saved.tasks.find(x=>x.id===accepted.task_id);
   assert.equal(saved.tasks.length,baseline.tasks.length+1,'manual acceptance creates exactly one task');
   assert.equal(accepted.state,'accepted');assert.equal(accepted.plan.school_task.state,'review','manual acceptance preserves the legacy reading state');assert.equal(accepted.plan.school_task.auto_added,false);assert.equal(accepted.plan.school_task.purpose,'admin');
   assert.equal(task.child,'示例甲');assert.equal(task.title,title);assert.equal(task.action,goal);assert.equal(task.advice,advice);assert.equal(task.school_origin,true);assert.equal(task.due,'无明确截止','empty manual due uses the established storage contract');assert.equal(task.agenda.due_on,'');assert.equal(task.agenda.published_on,row(a.id).agenda.published_on);assert.equal(task.agenda.category,'todo');assert.equal(taskStatus(task),'待跟进');assert.equal(task.history.length,0);
   assert.equal(task.source,'Agent建议:'+a.id+'\n'+ref+'\n'+a.evidence[0].text,'manual task preserves its proposal, original reference and complete source text');
   await pending([b.id,c.id]);assert.equal(await notice(a.id).count(),0);assert.equal(await card(task.id).isVisible(),true);assert.equal(await card(task.id).locator('[data-check]').isChecked(),false);
   assert.match(await todos.locator('h2').innerText(),/要办的事 · 1/);assert.equal(await page.locator('.today-sections a[href="#task-group-todo"]').innerText(),'要办的事 1');
   await page.reload({waitUntil:'load'});await ready(page);await pending([b.id,c.id]);await guards();await fit(page);
   assert.equal(await card(task.id).isVisible(),true,'the same saved undated task stays directly visible after reopening');
   assert.equal(await card(task.id).locator('.task-owner').innerText(),'示例甲');assert.equal(await card(task.id).locator('[data-school-original-ref]').getAttribute('data-school-original-ref'),ref);assert.equal(await card(task.id).locator('[data-school-original-ref]').getAttribute('data-school-original-child'),'child-1');
   await card(task.id).locator('[data-school-original-ref]').click();
   await eventually(async()=>/本项资料范围/.test(await original.innerText()),'legacy task material scope stays protected');
   await original.locator('[data-school-task-source]').click();await eventually(async()=>await original.locator('blockquote.source').count()===1,'complete original remains available from the saved task');
   assert.equal(await original.locator('blockquote.source').textContent(),a.evidence[0].text);assert.deepEqual(originalReads.at(-1),identity);await fit(page);await original.locator('[data-school-original-close]').click();

   await card(task.id).locator('[data-task="'+task.id+'"]').click();await page.locator('#taskDialog[open]').waitFor();
   assert.equal(await page.locator('#taskForm [name=id]').inputValue(),task.id);assert.equal(await page.locator('#taskRequirement').innerText(),goal);
   const feedback='虚构家长反馈：已核对回执项目，签字尚未完成。';
   await page.locator('#taskForm [name=note]').fill(feedback);await page.locator('#saveTaskFeedback').click();
   await eventually(async()=>/反馈已保存；事项状态未改变/.test(await page.locator('#taskFeedbackStatus').innerText()),'same-task feedback is saved');
   const withFeedback=await read(),record=withFeedback.records.find(r=>r.source==='事项:'+task.id);
   assert.ok(record);assert.equal(record.child,'示例甲');assert.equal(record.note,feedback);assert.equal(record.category,'家长观察');assert.equal(withFeedback.records.filter(r=>r.source==='事项:'+task.id).length,1);assert.equal(taskStatus(withFeedback.tasks.find(t=>t.id===task.id)),'待跟进','feedback never implies completion');assert.equal(withFeedback.tasks.find(t=>t.id===task.id).source,task.source);await fit(page);
   await page.locator('#taskDialog [data-close=taskDialog]').click();await page.reload({waitUntil:'load'});await ready(page);
   await card(task.id).locator('[data-task="'+task.id+'"]').click();await page.locator('#taskDialog[open]').waitFor();
   assert.equal(await page.locator('#taskForm [name=id]').inputValue(),task.id);assert.ok((await page.locator('#taskFeedbackHistory').innerText()).includes(feedback),'saved feedback reopens on the same task');assert.equal(await page.locator('#taskForm [name=status]').inputValue(),'待跟进');await fit(page);await proof(page,'saved-task-feedback-reopen-'+width);await page.locator('#taskDialog [data-close=taskDialog]').click();
   await page.locator('[data-child-filter="child-2"]').click();await pending([sibling.id]);assert.equal(await card(task.id).count(),0);
   for(const id of [a.id,b.id,c.id])assert.equal(await notice(id).count(),0,'switching child isolates the original admin notices');
   assert.equal(await todos.locator('[data-today-task]').count(),0);assert.equal(await notice(sibling.id).locator('[data-school-original-ref]').getAttribute('data-school-original-child'),'child-2');await fit(page);
   await page.locator('[data-child-filter="child-1"]').click();await pending([b.id,c.id]);assert.equal(await card(task.id).isVisible(),true);assert.equal(await notice(sibling.id).count(),0);await guards();await fit(page);
   const final=await read();assert.equal(final.tasks.length,baseline.tasks.length+1);assert.equal(final.records.filter(r=>r.source==='事项:'+task.id).length,1);assert.equal(final.tasks.find(t=>t.id===task.id).source,task.source);for(const key of ['B','C','SIBLING'])assert.equal(item(final,key).state,'pending');assert.deepEqual(writes,['/api/agent/action','/api/agent/action','/api/task/feedback'],'the journey performs only the explicit confirmation retry and one feedback save');assert.deepEqual(errors,[]);assert.deepEqual(foreign,[],'no external requests');
   checks.push(width+'px old/new/unknown admin, original retry, zero-write acceptance retry, saved task/feedback and child isolation');
   await page.close();page=null;await server.stop();server=null;
  }
  console.log(checks.join('\n'));
 }catch(error){if(page)try{await proof(page,'failure-'+page.viewportSize().width)}catch{}throw error}
 finally{
  if(page)await Promise.race([page.close().catch(()=>{}),delay(3000)]);
  if(server)await server.stop();
  if(browser)await Promise.race([browser.close().catch(()=>{}),delay(5000)]);
 }
})().catch(error=>{console.error(error);process.exitCode=1});
