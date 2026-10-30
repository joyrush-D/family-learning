// Recognised school change review: replays three recorded fictional model replies through the real school path; no real family, CLI or model calls.
// Without TEST_SCHOOL_CHANGE_PORT the Python fixture only prints what it saved, so the replay can be checked without a browser.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),path=require('node:path'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const recorded= require(process.env.SCHOOL_CHANGE_REPLAY||path.join(__dirname,'test_school_change_replay.json'));
assert.equal(recorded.all_fictional,true);
const CLOCK=Date.parse(recorded.as_of+'T18:30:00+08:00');
async function until(check,label){for(let i=0;i<200;i++){if(await check())return;await delay(50)}throw Error(label)}
async function proof(page,name){if(process.env.SCHOOL_CHANGE_PROOF_DIR){const fs=require('node:fs/promises');await fs.mkdir(process.env.SCHOOL_CHANGE_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.SCHOOL_CHANGE_PROOF_DIR,name+'.png')})}}
const fixture=String.raw`
import tempfile,os,json,datetime
from pathlib import Path
from unittest.mock import patch
with tempfile.TemporaryDirectory(prefix='synthetic-school-change-ui-') as tmp:
 os.environ['FAMILY_DATA']=tmp
 replay=json.loads(Path(os.environ.get('SCHOOL_CHANGE_REPLAY','test_school_change_replay.json')).read_text(encoding='utf-8'))
 assert replay['all_fictional'] is True
 fixed=datetime.datetime.fromisoformat(replay['as_of']+'T18:30:00+08:00')
 class FrozenDate(datetime.date):
  @classmethod
  def today(cls):return cls(fixed.year,fixed.month,fixed.day)
 class FrozenDateTime(datetime.datetime):
  @classmethod
  def now(cls,tz=None):
   value=fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
   return cls(value.year,value.month,value.day,value.hour,value.minute,value.second,tzinfo=value.tzinfo)
  def date(self):return FrozenDate(self.year,self.month,self.day)
 datetime.datetime,datetime.date=FrozenDateTime,FrozenDate
 import app,family_agent,family_llm
 app.DATA=Path(tmp).resolve();app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 source=replay['source_id']
 (app.DATA/'agent.json').write_text(json.dumps({'enabled':True,'sources':[
  {'id':source,'platform':'wechat','child_id':'child-1','name':'虚构班级','cursor':'','enabled':True},
  {'id':'synthetic-extra','platform':'wechat','child_id':'child-1','name':'虚构补充通知','cursor':'','enabled':True},
  {'id':'sibling-group','platform':'wechat','child_id':'child-2','name':'虚构另一班级','cursor':'','enabled':True}]}))
 store=app.agent_store()
 recorded_task=replay['replies'][1]['proposals'][0]['task_target_id'];ids={};calls=[]
 def model(messages,schema,name,timeout,*,data_path=None):
  request=json.loads(messages[-1]['content'])
  refs={row.get('ref') for row in request.get('evidence',[]) if isinstance(row,dict)}
  for reply in replay['replies']:
   if reply['proposals'][0]['evidence'][0]['ref'] in refs:
    reply=json.loads(json.dumps(reply))
    # Only identifiers this fixture generates itself are mapped; recorded wording, dates and change kinds stay unchanged.
    for row in reply['proposals']:
     row['task_target_id']=ids.get(row['task_target_id'],row['task_target_id']);row['learning_goal_id']=ids.get(row['learning_goal_id'],row['learning_goal_id'])
    calls.append(reply['proposals'][0]['evidence'][0]['ref']);return reply
  raise family_llm.LLMUnavailable('not part of the fixed replay')
 day=replay['as_of'];runs=[];target=''
 for i,(ident,text,sent) in enumerate(zip(replay['message_ids'],replay['texts'],replay['send_times'])):
  stamp=datetime.datetime.fromisoformat(day+'T'+sent+':00+08:00')
  store.ingest(dict(source_id=source,expected_cursor=replay['message_ids'][i-1] if i else '',cursor=ident,checked_at=stamp.isoformat(),last_message_time=stamp.isoformat(),error='',
   messages=[dict(id=ident,time=stamp.isoformat(),kind='text',sender=replay['sender'],sender_id=replay['sender_id'],text=text,unread=False)]))
  # This fixture tests school changes, not family-document reminders or growth-plan generation.
  with patch.object(family_llm,'_chat_json',side_effect=model),patch.object(family_agent.family_review,'read_candidates',return_value=([],[])),patch('family_goals.Store.run',return_value=dict(used=0,failed=0,created=0,children=set())),patch.object(family_agent,'_plan_learning',return_value=None):
   runs.append(family_agent.run_once(app,stamp+datetime.timedelta(minutes=2)))
  assert runs[-1]['failed']==0,runs[-1]
  if i==0:
   first=next(x for x in store.snapshot()['items'] if any(e.get('ref')=='message:'+source+':'+ident for e in x.get('evidence',[])))
   target=first.get('task_id') or store.act(dict(id=first['id'],action='accept'))['task_id'];ids[recorded_task]=target
   goal=replay['replies'][1]['proposals'][0]['learning_goal_id']
   with app.connect() as c:
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'learning_goals' in tables:
     row=c.execute("SELECT id FROM learning_goals WHERE child_id='child-1' ORDER BY rowid DESC LIMIT 1").fetchone()
     if row:ids[goal]=row[0]
   app.save_task(dict(id=target,status='待跟进',note=replay['feedback']))
 # After the replay no request may reach any model.
 family_llm._chat_json=lambda *a,**k:(_ for _ in ()).throw(family_llm.LLMUnavailable('synthetic fixture: no model calls'))
 now=datetime.datetime.now(family_agent.TZ);later=(now.date()+datetime.timedelta(days=2)).isoformat()
 extra=[('missing','数学：更正的原事项已不存在','更正：口算第2页改做第1行。'),('sibling','数学：另一孩子的练习三','只做1至3题。'),('new','语文：读第3课两遍','语文第3课朗读两遍，明天在家完成。')]
 store.ingest(dict(source_id='synthetic-extra',expected_cursor='',cursor='e3',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[dict(id='e'+str(n),time=now.isoformat(),kind='text',sender='虚构老师乙',text=text,unread=False) for n,(kind,title,text) in enumerate(extra,1)]))
 store.ingest(dict(source_id='sibling-group',expected_cursor='',cursor='1',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[dict(id='1',time=now.isoformat(),kind='text',sender='虚构老师丙',text='SIBLING练习三：完成第1至5题。',unread=False)]))
 def brief(title,goal,change,target_id,state):return dict(title=title,goal=goal,advice='',state=state,reason='虚构的学校变更依据',change=change,target_id=target_id,policy=family_agent.SCHOOL_TASK_POLICY)
 store._save('sibling:1','fixture',[dict(child_id='child-2',kind='school',title='数学：完成练习三第1至5题',body='SIBLING练习三：完成第1至5题。',due=later,evidence=[dict(ref='message:sibling-group:1',text='SIBLING练习三：完成第1至5题。')],plan=dict(school_task=brief('数学：完成练习三第1至5题','SIBLING练习三：完成第1至5题。','new','','ready')))],now)
 with store._db() as c:sibling_item=c.execute("SELECT id FROM agent_items WHERE job_id='sibling:1'").fetchone()[0]
 sibling=store.act(dict(id=sibling_item,action='accept'))['task_id']
 for n,(kind,title,text) in enumerate(extra,1):
  change,target_id,state=dict(missing=('update','AGENT-missing-target','review'),sibling=('update',sibling,'review'),new=('new','','ready'))[kind]
  store._save('extra:'+kind,'fixture',[dict(child_id='child-1',kind='school',title=title,body=text,due=later if kind=='new' else '',evidence=[dict(ref='message:synthetic-extra:e'+str(n),text=text)],plan=dict(school_task=brief(title,text,change,target_id,state)))],now)
 if 'TEST_SCHOOL_CHANGE_PORT' not in os.environ:
  shot=app.state() if hasattr(app,'state') else None
  with app.connect() as c:tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
  items=store.snapshot()['items']
  print(json.dumps(dict(calls=calls,runs=runs,target=target,sibling=sibling,ids=ids,
   items=[dict(id=x['id'],child=x['child_id'],state=x['state'],title=x['title'],due=x.get('due'),task_id=x.get('task_id'),change=(x.get('plan') or {}).get('school_task',{}).get('change'),target_id=(x.get('plan') or {}).get('school_task',{}).get('target_id'),brief_state=(x.get('plan') or {}).get('school_task',{}).get('state'),reason=(x.get('plan') or {}).get('school_task',{}).get('reason')) for x in items],
   tasks=[{k:r[k] for k in r if k in ('id','child','title','action','status','note','due','source','school_origin')} for r in tasks]),ensure_ascii=False,default=str,indent=1))
 else:
  app.prepare_assets()
  server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_SCHOOL_CHANGE_PORT'])),app.Handler)
  try:server.serve_forever()
  except KeyboardInterrupt:pass
  finally:server.server_close()
`;
module.exports={fixture};
async function inView(page,locator,label){const box=await locator.boundingBox(),{height,width}=page.viewportSize();assert.ok(box&&box.y>=0&&box.x>=0&&box.y+box.height<=height&&box.x+box.width<=width,label+' is inside the initial viewport: '+JSON.stringify(box));assert.equal(await locator.evaluate(b=>{const r=b.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit===b||b.contains(hit)}),true,label+' is not covered')}
async function fits(page){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no document overflow');assert.equal(await page.locator('dialog[open]').evaluateAll(items=>items.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow')}
// A recognised change bound to this child's own original task: summary first, no selector, confirm and close reachable without scrolling.
async function boundSummary(page,label){const dialog=page.locator('#agentDialog');assert.equal(await dialog.evaluate(d=>d.scrollTop),0);
 assert.equal(await dialog.locator('select:visible').count(),0,label+': no visible selector');assert.equal(await dialog.locator('input:visible,textarea:visible').count(),0,label+': no edit field before 修改本次整理');
 await inView(page,dialog.locator('#agentForm [type="submit"]'),label+' confirm');await inView(page,dialog.locator('[data-close="agentDialog"]'),label+' close');
 assert.equal(await dialog.locator('h2').innerText(),'核对学校变更');assert.equal(await dialog.locator('[data-school-change-edit]').isVisible(),true);await fits(page)}
const entries=[];
async function openChange(page,id){await page.locator('nav [data-page="home"]').click();const button=page.locator('#content [data-agent-accept="'+id+'"]');
 await until(async()=>await button.count()>0,'the current Today entry must contain this notice: '+id);entries.push('today:'+id);
 const details=button.first().locator('xpath=ancestor::details[1]');if(await details.count()&&await details.getAttribute('open')===null)await details.locator(':scope > summary').click();
 await button.first().click();await page.locator('#agentDialog[open]').waitFor()}
async function closeDialog(page){await page.locator('#agentDialog [data-close="agentDialog"]').click();await page.locator('#agentDialog').waitFor({state:'hidden'})}
if(require.main===module)(async()=>{let proc,browser;try{
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));const url='http://127.0.0.1:'+port+'/',env={...process.env,TEST_SCHOOL_CHANGE_PORT:String(port),SCHOOL_CHANGE_REPLAY:path.join(__dirname,'test_school_change_replay.json')};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let errors='';proc.stderr.on('data',b=>errors+=b);proc.on('error',e=>errors+=e.message);
 await until(async()=>{if(proc.exitCode!==null)throw Error(errors);try{return(await fetch(url)).ok}catch{return false}},'server startup');const state=async()=>await(await fetch(url+'api/state')).json();
 const before=await state(),child=before.children.find(c=>c.id==='child-1'),sibling=before.children.find(c=>c.id==='child-2');
 const byRef=ref=>before.agent.items.find(i=>i.state==='pending'&&(i.evidence||[]).some(e=>e.ref===ref)),update=byRef('message:synthetic-group:12'),cancel=byRef('message:synthetic-group:13');
 assert.equal(update.plan.school_task.change,'update');assert.equal(cancel.plan.school_task.change,'cancel');assert.equal(cancel.plan.school_task.target_id,update.plan.school_task.target_id);
 const target=before.tasks.find(t=>t.id===update.plan.school_task.target_id);assert.equal(target.child,child.name);assert.ok(target.school_origin);assert.equal(target.update.note,'做了第1题');assert.match(target.action,/第1至5题/);assert.equal(target.agenda.due_on,'2026-11-05');
 const siblingTask=before.tasks.find(t=>t.child===sibling.name&&t.school_origin),missing=before.agent.items.find(i=>i.title==='数学：更正的原事项已不存在'),crossChild=before.agent.items.find(i=>i.title==='数学：另一孩子的练习三'),fresh=before.agent.items.find(i=>i.title==='语文：读第3课两遍');
 assert.ok(siblingTask&&missing&&crossChild&&fresh);assert.equal(crossChild.plan.school_task.target_id,siblingTask.id);
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
 const calls=[];
 // 1440 first: the summary, 修改本次整理 and explicit fallbacks send nothing.
 const desk=await browser.newPage({viewport:{width:1440,height:900}}),pageErrors=[];desk.on('pageerror',e=>pageErrors.push(e.message));await desk.route('**/api/agent/action',async route=>{calls.push(route.request().postDataJSON());await route.continue()});
 await desk.clock.setFixedTime(CLOCK);await desk.goto(url);await desk.locator('body[data-page="home"]').waitFor();
 await openChange(desk,update.id);await boundSummary(desk,'1440 update');const deskForm=desk.locator('#agentForm');
 const shownBody=await deskForm.locator('[name="body"]').inputValue();assert.match(shownBody,/只做第1至3题/);assert.equal((await deskForm.locator('[data-school-change-body]').innerText()).trim(),shownBody.trim(),'the complete requirement is shown, not hidden with the editor');
 const current=await deskForm.locator('[data-school-current]').innerText();assert.match(current,/第1至5题/);assert.match(current,/做了第1题/);assert.match(current,new RegExp('原日期（'+(target.agenda.due_kind==='handback'?'老师要求交回':'截止')+'）：2026-11-05'));
 assert.match(await deskForm.locator('[data-school-change-due]').innerText(),/日期不变：2026-11-05/);assert.equal(await deskForm.locator('[type="submit"]').innerText(),'确认更正原事项');assert.equal(await deskForm.locator('[data-close="agentDialog"]').innerText(),'关闭');
 assert.equal(await deskForm.locator('[name="school_mode"]').inputValue(),'update');assert.equal(await deskForm.locator('[name="target_id"]').inputValue(),target.id);await proof(desk,'school-change-summary-1440');
 await deskForm.locator('[data-school-change-edit]').click();assert.equal(await deskForm.locator('select:visible').count(),2,'修改本次整理 opens the original editor');for(const name of ['title','body','due'])assert.equal(await deskForm.locator('[name="'+name+'"]').isVisible(),true);
 assert.equal(await deskForm.locator('[data-school-change-summary]').isVisible(),false);assert.equal(await deskForm.locator('[name="due"]').inputValue(),'2026-11-05');await inView(desk,deskForm.locator('[type="submit"]'),'1440 editor confirm stays reachable');
 const editedTitle=(await deskForm.locator('[name="title"]').inputValue())+'（家长核对）',editedBody=shownBody+'\n家长核对：第1题已完成。',editAttempts=[];
 await deskForm.locator('[name="title"]').fill(editedTitle);await deskForm.locator('[name="body"]').fill(editedBody);
 const refuseEdit=async route=>{editAttempts.push(route.request().postDataJSON());await route.fulfill({status:503,json:{error:'虚构编辑保存失败'}})};
 await desk.route('**/api/agent/action',refuseEdit);await deskForm.locator('[type="submit"]').click();await until(async()=>/虚构编辑保存失败/.test(await desk.locator('#agentError').innerText()),'edited save failed without a write');
 assert.equal(editAttempts.length,1);assert.equal(editAttempts[0].title,editedTitle);assert.equal(editAttempts[0].body,editedBody);assert.equal(editAttempts[0].due,'2026-11-05');assert.equal(editAttempts[0].target_id,target.id);
 assert.equal(await deskForm.locator('[name="title"]').inputValue(),editedTitle);assert.equal(await deskForm.locator('[name="body"]').inputValue(),editedBody);assert.equal((await state()).tasks.find(t=>t.id===target.id).focus.version,0,'refused edit leaves the original unchanged');
 await inView(desk,desk.locator('#agentError'),'1440 edited save error stays visible');await inView(desk,deskForm.locator('[type="submit"]'),'1440 edited retry stays reachable');await proof(desk,'school-change-edit-1440');await desk.unroute('**/api/agent/action',refuseEdit);await closeDialog(desk);
 await openChange(desk,cancel.id);await boundSummary(desk,'1440 cancel');assert.match(await deskForm.innerText(),/取消依据/);assert.equal(await deskForm.locator('[type="submit"]').innerText(),'确认学校取消');await closeDialog(desk);
 for(const item of [missing,crossChild]){await openChange(desk,item.id);assert.equal(await deskForm.locator('select:visible').count(),2,'unknown or other-child target keeps the explicit choice');assert.equal(await deskForm.locator('[name="target_id"]').inputValue(),'');assert.equal(await deskForm.locator('[type="submit"]').isDisabled(),true,'no silent new task or other target');
  const options=await deskForm.locator('[name="target_id"] option').evaluateAll(xs=>xs.map(x=>x.value).filter(Boolean));assert.ok(options.includes(target.id));assert.ok(!options.includes(siblingTask.id),'other child task is never offered');await closeDialog(desk)}
 assert.equal(calls.length,0,'reading, editing and closing send no request');
 await openChange(desk,fresh.id);assert.equal(await deskForm.locator('h2').innerText(),'核对学校待办');assert.equal(await deskForm.locator('[data-school-change-open]').isVisible(),true);assert.equal(await deskForm.locator('[name="title"]').isVisible(),true);assert.equal(await deskForm.locator('[type="submit"]').innerText(),'加入待办');
 await deskForm.locator('[type="submit"]').click();await desk.locator('#agentDialog').waitFor({state:'hidden'});assert.equal(calls.length,1);assert.equal(calls[0].action,'accept');assert.equal(calls[0].school_new,true);
 const afterNew=await state();assert.equal(afterNew.tasks.length,before.tasks.length+1,'ordinary new school task flow still adds one task');assert.equal(pageErrors.length,0,pageErrors.join('; '));
 // 360: update with a lost receipt, retry, reopen; then cancel.
 const phone=await browser.newPage({viewport:{width:360,height:900}}),phoneErrors=[];phone.on('pageerror',e=>phoneErrors.push(e.message));const sent=[];let loseReceipt=false;await phone.route('**/api/agent/action',async route=>{sent.push(route.request().postDataJSON());if(!loseReceipt)return route.continue();loseReceipt=false;const response=await route.fetch();assert.equal(response.status(),200);await route.fulfill({status:503,json:{error:'虚构变更回执丢失'}})});
 await phone.clock.setFixedTime(CLOCK);await phone.goto(url);await phone.locator('body[data-page="home"]').waitFor();await openChange(phone,update.id);await boundSummary(phone,'360 update');await proof(phone,'school-change-summary-360');const form=phone.locator('#agentForm');
 loseReceipt=true;await form.locator('[type="submit"]').click();await until(async()=>/虚构变更回执丢失/.test(await phone.locator('#agentError').innerText()),'lost receipt shown');await inView(phone,phone.locator('#agentError'),'360 error');await inView(phone,form.locator('[type="submit"]'),'360 retry');await proof(phone,'school-change-lost-receipt-360');
 await form.locator('[type="submit"]').click();await phone.locator('#agentDialog').waitFor({state:'hidden'});
 assert.equal(sent.length,2);assert.deepEqual(Object.keys(sent[0]).sort(),['action','change','due','expected_updated','body','id','target_id','target_updated','target_version','title'].sort());assert.deepEqual(sent[1],sent[0],'the retry repeats the same request');
 assert.equal(sent[0].action,'school_change');assert.equal(sent[0].change,'update');assert.equal(sent[0].target_id,target.id);assert.equal(sent[0].due,'2026-11-05');
 await phone.reload();await phone.locator('body[data-page="home"]').waitFor();const changed=await state(),same=changed.tasks.find(t=>t.id===target.id);
 assert.equal(changed.tasks.length,afterNew.tasks.length,'update creates no copy');assert.equal(same.action,sent[0].body);assert.equal(same.agenda.due_on,'2026-11-05');assert.equal(same.update.note,'做了第1题');assert.match(same.source,/message:synthetic-group:12/);
 assert.notEqual(changed.agent.items.find(i=>i.id===update.id).state,'pending');assert.equal(await phone.locator('[data-agent-accept="'+update.id+'"]').count(),0,'a saved change is not offered again');
 await openChange(phone,cancel.id);await boundSummary(phone,'360 cancel');await form.locator('[type="submit"]').click();await phone.locator('#agentDialog').waitFor({state:'hidden'});await phone.reload();await phone.locator('body[data-page="home"]').waitFor();
 const cancelled=await state(),stopped=cancelled.tasks.find(t=>t.id===target.id);assert.equal(cancelled.tasks.length,changed.tasks.length);assert.equal(stopped.update.status,'不适用');assert.ok((stopped.history||[]).some(h=>h.note==='做了第1题'),'earlier feedback stays in history');
 const pickStable=t=>({title:t.title,action:t.action,update:t.update,due:t.agenda?.due_on});assert.deepEqual(pickStable(cancelled.tasks.find(t=>t.id===siblingTask.id)),pickStable(siblingTask),'the other child task is untouched');assert.equal(sent.length,3);assert.equal(sent[2].change,'cancel');
 // Switching to the other child never shows this child's change.
 await phone.locator('nav [data-page="more"]').click();await phone.locator('#content [data-page="agent"]').click();const childPick=phone.locator('[data-school-inbox-child]');
 if(await childPick.count()){await childPick.first().selectOption('child-2');await until(async()=>!(await phone.locator('#content').innerText()).includes('只做第1至3题'),'other child view excludes this change')}else entries.push('no-child-picker-on-agent-page');
 assert.equal(phoneErrors.length,0,phoneErrors.join('; '));console.log(JSON.stringify({ok:true,entries}))
}finally{await browser?.close();proc?.kill('SIGINT')}})().catch(e=>{console.error(e);console.error('entries',JSON.stringify(entries));process.exit(1)});
