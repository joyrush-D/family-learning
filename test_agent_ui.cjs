// Synthetic browser + real local API checks; no real family, CLI or model calls.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check,label){for(let i=0;i<200;i++){if(await check())return;await delay(50)}throw Error(label)}
async function fits(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no document overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(items=>items.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
 assert.equal(await page.locator('[data-school-record-agent]:visible,[data-school-record-task]:visible,#recordForm button:visible').evaluateAll(items=>items.some(b=>b.getBoundingClientRect().height<40)),false,'school learning actions are usable touch targets');
}
async function openTaskRecordFromCard(page,id){
 const button=page.locator('[data-school-record-task="'+id+'"]'),details=page.locator('.task-more').filter({has:button});
 if(await details.count()&&await details.getAttribute('open')===null)await details.locator(':scope > summary').click();
 await button.click();
}
async function proof(page,name){if(process.env.AGENT_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.AGENT_UI_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.AGENT_UI_PROOF_DIR,name+'.png')})}}
const fixture=String.raw`
import tempfile,os,json,datetime,io,struct,zlib
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='synthetic-agent-ui-') as tmp:
 os.environ['FAMILY_DATA']=tmp
 import app,family_agent
 app.DATA=Path(tmp).resolve();app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 today=datetime.datetime.now(family_agent.TZ).date().isoformat()
 app.save_record(dict(child='示例小宇',day=today,category='学习进展',title='虚构阅读尝试',note='还需要一次提示',subject='语文',source='家长观察'))
 app.save_record(dict(child='示例星星',day=today,category='学习进展',title='虚构时间管理依据',note='最近记录显示需要一次提示',subject='数学',source='家长观察'))
 app.save_record(dict(child='示例小宇',day=today,category='学习进展',title='SIBLING_SAME_SOURCE_CANARY',note='另一孩子的同来源记录，不能代替当前孩子。',source='message:synthetic:0'))
 (app.DATA/'agent.json').write_text(json.dumps({'enabled':True,'sources':[{'id':'synthetic','platform':'wechat','child_id':'child-1','name':'虚构原件通知','cursor':'','enabled':True}]}))
 store=app.agent_store();now=datetime.datetime.now(family_agent.TZ)
 def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 pixels=b''.join(b'\x00'+bytes([30+(row%2)*40,120,220,255])*96 for row in range(64))
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',96,64,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
 existing_upload=app.save_upload(io.BytesIO(png),len(png),'synthetic-existing.png')
 messages=[dict(id=str(i),time=now.isoformat(),kind='image',sender='虚构老师',text='虚构老师通知：请准备观察材料。<img src=x onerror=alert(1)>',unread=True) for i in range(4)]
 for width in (360,1440): messages.append(dict(id='image:'+str(width),time=now.isoformat(),kind='image',sender='虚构老师',text='虚构图片消息说明：原件内容尚未读取。',unread=True));messages.append(dict(id='original:'+str(width),time=now.isoformat(),kind='image',sender='虚构老师',text='虚构原件关联通知 '+str(width)+'：请核对图片附件内容。',unread=True))
 for width in (360,1440): messages.append(dict(id='draft:'+str(width),time=now.isoformat(),kind='image',sender='虚构老师',text='虚构听写原件，数值尚未知。',unread=True))
 store.ingest(dict(source_id='synthetic',expected_cursor='',cursor='cursor-1',checked_at=now.isoformat(),last_message_time=now.isoformat(),messages=messages,error=''))
 for i in range(4):
  store._save('school:'+str(i),'fixture',[dict(child_id='child-1',kind='school',title='虚构学校准备 '+str(i),body='核对后准备观察材料。',due=today,evidence=[{'ref':'message:synthetic:'+str(i),'text':'虚构老师通知：请准备观察材料。<img src=x onerror=alert(1)>'}])],now)
 store._save('record:1','fixture',[dict(child_id='child-2',kind='care',title='虚构学习跟进',body='请孩子讲讲自己的想法。',record_id=1,evidence=[{'ref':'record:1','text':'还需要一次提示'}])],now)
 for width in (360,1440):
  store._save('care:planned:'+str(width),'fixture',[dict(child_id='child-1',kind='care',title='虚构时间管理小动作 '+str(width),body='今晚用计时器完成一轮数学练习。',record_id=2,plan={'goal':'把数学练习拆成一轮可完成的小步骤','why_now':'最近记录显示需要一次提示','estimated_minutes':25,'review_on':today},evidence=[{'ref':'record:2','text':'最近记录显示需要一次提示'}])],now)
  image_title='待核对：[image：内容未读取，仅保留消息说明]'
  store._save('school:image:'+str(width),'fixture',[dict(child_id='child-1',kind='school',title=image_title,body='genericbody',due=today,evidence=[{'ref':'message:synthetic:image:'+str(width),'text':'虚构图片消息说明：原件内容尚未读取。'}])],now)
  store._save('school:original:'+str(width),'fixture',[dict(child_id='child-1',kind='school',title='虚构原件关联通知 '+str(width),body='请核对图片附件内容。',due=today,evidence=[{'ref':'message:synthetic:original:'+str(width),'text':'虚构原件关联通知 '+str(width)+'：请核对图片附件内容。'}])],now)
 with store._db() as c:
  for width in (360,1440): c.execute("INSERT INTO agent_media(source_id,message_id,state,attempts,error) VALUES ('synthetic',?,'error',1,'process_timeout')",('original:'+str(width),))
 from unittest.mock import patch
 import family_media,family_llm
 for width in (360,1440):
  store.message_attachment(dict(child_id='child-1',source_id='synthetic',message_id='draft:'+str(width),attachment_id=existing_upload['id'],action='attach'),dict)
  store._save('school:draft:'+str(width),'fixture',[dict(child_id='child-1',kind='school',title='虚构原件草稿 '+str(width),body='请核对实际表现。',evidence=[{'ref':'message:synthetic:draft:'+str(width),'text':'虚构听写原件'}])],now)
 with patch.object(family_llm,'extract_draft',return_value=dict(title='虚构听写记录',subject='英语',score=None,total=None,note='图片目标行标记F；不能换算成0分。<img src=x onerror=alert(1)>',uncertainties=['错词尚未提供'])):
  for _ in (360,1440): assert family_media.prepare_draft(store,now)==dict(used=1,failed=0)
 # Fully read repeated notifications use the same task and preserve a parent's closed decision.
 cfg=json.loads((app.DATA/'agent.json').read_text())
 for name in ('copy-a','copy-b'):cfg['sources'].append(dict(id=name,platform='wechat',child_id='child-1',name='虚构重复通知群 '+name,cursor='',enabled=True))
 (app.DATA/'agent.json').write_text(json.dumps(cfg))
 for name in ('copy-a','copy-b'):
  store.ingest(dict(source_id=name,expected_cursor='',cursor='page-1',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[dict(id=str(width),time=now.isoformat(),kind='text',sender='示例老师',text='虚构同日通知 '+str(width)+'：明天带观察记录。',unread=False) for width in (360,1440)]))
 for width in (360,1440):
  for name in ('copy-a','copy-b'):
   title='虚构同日重复事项 '+str(width)
   item=dict(child_id='child-1',kind='school',title=title,body='带一份观察记录。',due=today,evidence=[dict(ref='message:'+name+':'+str(width),text='虚构同日通知 '+str(width)+'：明天带观察记录。')],plan=dict(school_task=dict(title=title,goal='带一份观察记录。',advice='',state='ready',reason='明确学校安排',policy=family_agent.SCHOOL_TASK_POLICY)))
   key='copy:'+name+':'+str(width);store._save(key,'fixture',[item],now)
   if name=='copy-a':
    with store._db() as c:ident=c.execute('SELECT id FROM agent_items WHERE job_id=?',(key,)).fetchone()[0]
    task=store.act(dict(id=ident,action='accept'))['task_id']
    app.save_task(dict(id=task,status='不适用',note='虚构家长已确认不需处理。'))
 # Later teacher corrections/cancellations remain pending until a parent reconciles the original task.
 change_messages=[]
 for width in (360,1440):
  for kind,text in [('before','完成三点观察并画图。'),('update','更正：只写两点观察，不用画图。'),('cancel','取消本次观察记录。')]:
   change_messages.append(dict(id=kind+str(width),time=now.isoformat(),kind='text',sender='虚构老师',text=text,unread=False))
 store.ingest(dict(source_id='copy-a',expected_cursor='page-1',cursor='page-2',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=change_messages))
 for width in (360,1440):
  target=''
  for kind in ('before','update','cancel'):
   text=next(m['text'] for m in change_messages if m['id']==kind+str(width))
   brief=dict(title='虚构通知变更 '+kind+' '+str(width),goal=text,advice='',state='ready' if kind=='before' else 'review',reason='学校要求有变化',change='new' if kind=='before' else kind,target_id=target,policy=family_agent.SCHOOL_TASK_POLICY)
   key='change:'+kind+str(width)
   store._save(key,'fixture',[dict(child_id='child-1',kind='school',title=brief['title'],body=text,due=today if kind=='before' else '',evidence=[dict(ref='message:copy-a:'+kind+str(width),text=text)],plan=dict(school_task=brief))],now)
   if kind=='before':
    with store._db() as c:ident=c.execute('SELECT id FROM agent_items WHERE job_id=?',(key,)).fetchone()[0]
    target=store.act(dict(id=ident,action='accept'))['task_id']
    app.save_task(dict(id=target,status='待跟进',note='虚构家长反馈：已口述一部分。'))
    study=app.study_store();study.save_item(dict(child_id='child-1',day=today,request_key='school-change-study-'+str(width),task_id=target,planned_minutes=10))
 for width in (360,1440):
  exam=app.new_task(dict(child='示例星星',title='虚构英语单元测验 '+str(width),due=today,source='message:copy-a:before'+str(width)))
  store._save('exam-review:'+exam['id']+':'+today,'fixture',[dict(child_id='child-1',kind='review',title='记录考试结果：'+exam['title'],body='保存结果后请在事项确认完成；没参加可选择不参加。',task_id=exam['id'],due=today,evidence=[dict(ref='task:'+exam['id'],text=exam['title'])],plan=dict(exam_result_pending=True))],now)
 store._runtime('ready',now)
 app.prepare_assets()
 server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_AGENT_PORT'])),app.Handler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
`;
(async()=>{let proc,browser;try{
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));const url='http://127.0.0.1:'+port+'/',env={...process.env,TEST_AGENT_PORT:String(port)};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let errors='';proc.stderr.on('data',b=>{errors+=b;if(process.env.AGENT_UI_PROOF_DIR){const fs=require('node:fs'),path=require('node:path');fs.mkdirSync(process.env.AGENT_UI_PROOF_DIR,{recursive:true});fs.appendFileSync(path.join(process.env.AGENT_UI_PROOF_DIR,'server-stderr.txt'),b)}});proc.on('error',e=>errors+=e.message);
 await until(async()=>{if(proc.exitCode!==null)throw Error(errors);try{return(await fetch(url)).ok}catch{return false}},'server startup');const state=async()=>await(await fetch(url+'api/state')).json();
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
 for(const width of [360,1440]){
  const page=await browser.newPage({viewport:{width,height:820}}),pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));await page.goto(url);try{await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor()}catch(error){await proof(page,'startup-failed-'+width);throw Error('Synthetic startup: '+(await page.locator('body').innerText()).slice(-1600)+'; '+pageErrors.join('; '))}
  assert.equal(await page.locator('[data-today-child="child-2"] [data-agent-item]').count(),0,'care reminders stay off the school summary');assert.equal(await page.locator('[data-today-child="child-1"] [data-followup="1"]').count(),0);
  await fits(page);
  const changeBefore=await state(),changeTask=changeBefore.tasks.find(t=>t.title==='虚构通知变更 before '+width),changedItem=changeBefore.agent.items.find(i=>i.title==='虚构通知变更 update '+width),cancelItem=changeBefore.agent.items.find(i=>i.title==='虚构通知变更 cancel '+width);
  const openChange=async id=>{await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('[data-agent-accept="'+id+'"]').click();await page.locator('#agentDialog').waitFor()};
  await openChange(changedItem.id);assert.equal(await page.locator('[name="school_mode"]').inputValue(),'update');assert.equal(await page.locator('[name="target_id"]').inputValue(),changeTask.id);const targetOptions=await page.locator('[name="target_id"] option').evaluateAll(xs=>xs.map(x=>x.value).filter(Boolean));assert.ok(targetOptions.every(id=>changeBefore.tasks.find(t=>t.id===id)?.school_origin));assert.equal(await page.locator('#agentForm [name="due"]').inputValue(),changeTask.agenda.due_on);
  assert.ok((await page.locator('[data-school-current]').innerText()).includes('完成三点观察并画图'));await fits(page);await proof(page,'school-change-review-'+width);
  // Another parent's new feedback must be read and reviewed before saving this draft.
  const changeToken=changeBefore.token;const conflictReply=await page.request.post(url+'api/task',{headers:{'X-Family-Token':changeToken},data:{id:changeTask.id,status:'已完成',note:'虚构另一位家长补充了帮助情况。'}});assert.equal(conflictReply.status(),200);
  await page.locator('#agentForm [type="submit"]').click();await until(async()=>/原事项已有新的安排或反馈/.test(await page.locator('#agentError').innerText()),'school change conflict');assert.equal(await page.locator('#agentForm [name="body"]').inputValue(),changedItem.body);
  await page.locator('[data-school-change-refresh]').click();await until(async()=>/已读取最新记录/.test(await page.locator('#agentError').innerText()),'school change refresh');
  await page.route('**/api/agent/action',async route=>{const response=await route.fetch();assert.equal(response.status(),200);await route.fulfill({status:503,json:{error:'虚构变更回执丢失'}})},{times:1});
  await page.locator('#agentForm [type="submit"]').click();await until(async()=>/虚构变更回执丢失/.test(await page.locator('#agentError').innerText()),'school change receipt lost');
  await page.locator('#agentForm [type="submit"]').click();await page.locator('#agentDialog').waitFor({state:'hidden'});await page.reload();await page.locator('nav [data-page="tasks"]').waitFor();
  const changeAfter=await state(),sameChangeTask=changeAfter.tasks.find(t=>t.id===changeTask.id);assert.equal(changeAfter.tasks.length,changeBefore.tasks.length);assert.equal(sameChangeTask.action,changedItem.body);assert.equal(sameChangeTask.agenda.due_on,changeTask.agenda.due_on);assert.equal(sameChangeTask.update.note,'虚构另一位家长补充了帮助情况。');assert.match(sameChangeTask.source,new RegExp('message:copy-a:update'+width));
  assert.equal(sameChangeTask.school_completion_needs_review,true);await page.locator('nav [data-page="tasks"]').click();await page.locator('[data-task-box="全部"]').click();await page.locator('[data-query-target="task:'+changeTask.id+'"] [data-school-completion-review]').waitFor();
  const resume=await page.request.post(url+'api/task',{headers:{'X-Family-Token':changeToken},data:{id:changeTask.id,status:'待跟进',note:'虚构家长核对新要求，继续跟进。'}});assert.equal(resume.status(),200);await page.reload();await page.locator('nav [data-page="tasks"]').waitFor();assert.equal((await state()).tasks.find(t=>t.id===changeTask.id).school_completion_needs_review,false);
  const studyBefore=await(await fetch(url+'api/study?child_id=child-1&day='+changeBefore.today)).json(),studyItem=studyBefore.items.find(i=>i.task_id===changeTask.id);assert.ok(studyItem);
  const started=await page.request.post(url+'api/study/action',{headers:{'X-Family-Token':changeToken},data:{child_id:'child-1',day:changeBefore.today,id:studyItem.id,version:studyItem.version,action:'start',request_key:'school-change-start-'+width}});assert.equal(started.status(),200);
  await openChange(cancelItem.id);assert.equal(await page.locator('[name="school_mode"]').inputValue(),'cancel');await page.locator('#agentForm [type="submit"]').click();await page.locator('#agentDialog').waitFor({state:'hidden'});await page.reload();await page.locator('nav [data-page="tasks"]').waitFor();
  const cancelled=(await state()).tasks.find(t=>t.id===changeTask.id);assert.equal(cancelled.update.status,'不适用');const stopped=(await(await fetch(url+'api/study?child_id=child-1&day='+changeBefore.today)).json()).items.find(i=>i.id===studyItem.id);assert.equal(stopped.running_since,null);assert.equal(stopped.status,'paused');assert.ok(cancelled.history.some(h=>h.note==='虚构另一位家长补充了帮助情况。'));
  await page.locator('nav [data-page="tasks"]').click();await page.locator('[data-task-box="已搁置"]').click();const changeCard=page.locator('[data-query-target="task:'+changeTask.id+'"]');await changeCard.waitFor();await changeCard.locator('.task-more > summary').click();assert.equal(await changeCard.locator('[data-school-original-ref]').count(),3);await fits(page);await proof(page,'school-change-saved-'+width);await page.locator('[data-task-box="全部"]').click();await page.locator('nav [data-page="home"]').click();
  const duplicateTitle='虚构同日重复事项 '+width,copyBefore=await state(),copyTask=copyBefore.tasks.find(t=>t.title===duplicateTitle);
  const copyItem=copyBefore.agent.items.find(i=>i.title===duplicateTitle&&i.state==='pending');assert.ok(copyTask&&copyItem);
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();
  await page.locator('[data-agent-accept="'+copyItem.id+'"]').click();await page.locator('#agentDialog').waitFor();
  await page.route('**/api/agent/action',async route=>{const response=await route.fetch();assert.equal(response.status(),200);await route.fulfill({status:503,json:{error:'虚构重复通知回执丢失'}})},{times:1});
  await page.locator('#agentForm [type="submit"]').click();await until(async()=>/虚构重复通知回执丢失/.test(await page.locator('#agentError').innerText()),'duplicate receipt unknown');
  assert.equal(await page.locator('#agentForm [name="title"]').inputValue(),duplicateTitle);
  await page.locator('#agentForm [type="submit"]').click();await page.locator('#agentDialog').waitFor({state:'hidden'});
  await until(async()=>/相同通知已收集，保留原事项及处理状态/.test(await page.locator('#toast').innerText()),'duplicate acknowledgement');await fits(page);await proof(page,'school-duplicate-'+width);
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  const copyAfter=await state(),sameTask=copyAfter.tasks.find(t=>t.id===copyTask.id);
  assert.equal(copyAfter.tasks.length,copyBefore.tasks.length);assert.equal(copyAfter.tasks.filter(t=>t.title===duplicateTitle).length,1);
  assert.deepEqual(sameTask.update,copyTask.update);assert.deepEqual(sameTask.history,copyTask.history);
  assert.equal(copyAfter.agent.items.find(i=>i.id===copyItem.id).task_id,copyTask.id);
  assert.match(sameTask.source,new RegExp('message:copy-a:'+width));assert.match(sameTask.source,new RegExp('message:copy-b:'+width));
  assert.deepEqual(copyAfter.records,copyBefore.records);
  await page.locator('nav [data-page="tasks"]').click();await page.locator('[data-task-box="已搁置"]').click();const copyCard=page.locator('[data-query-target="task:'+copyTask.id+'"]');await copyCard.waitFor();
  const copyDetails=copyCard.locator('.task-more');if(await copyDetails.getAttribute('open')===null)await copyDetails.locator(':scope > summary').click();
  assert.equal(await copyCard.locator('[data-school-original-ref]').count(),2);
  for(const source of ['copy-a','copy-b']){
   const response=page.waitForResponse(r=>r.url().includes('/api/agent/message?')&&r.request().method()==='GET');
   await copyCard.locator('[data-school-original-ref="message:'+source+':'+width+'"]').click();
   const reply=await response;assert.equal(reply.status(),200);const view=await reply.json();assert.equal(view.source_id,source);assert.equal(view.message_id,String(width));assert.equal(view.child_id,'child-1');
   await page.locator('#schoolOriginalDialog').waitFor();assert.match(await page.locator('#schoolOriginalDialog').innerText(),/明天带观察记录/);await fits(page);
   await page.locator('[data-school-original-close]').click();
  }
  await proof(page,'school-duplicate-origins-'+width);await page.locator('[data-task-box="全部"]').click();await page.locator('nav [data-page="home"]').click();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  const imageTitle='待核对：[image：内容未读取，仅保留消息说明]';await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();let imageState=await state(),imageItem=imageState.agent.items.find(x=>x.kind==='school'&&x.state==='pending'&&x.title===imageTitle);assert.ok(imageItem,'image placeholder school item is pending');const imageCard=page.locator('[data-agent-item="'+imageItem.id+'"]');assert.equal(await imageCard.locator('h3').innerText(),'原件内容待核对');assert.equal(await imageCard.locator('[data-agent-accept]').innerText(),'补充具体要求');await imageCard.locator('[data-agent-accept]').click();await page.locator('#agentDialog').waitFor();const imageForm=page.locator('#agentForm');assert.equal(await imageForm.locator('[name="title"]').inputValue(),'');assert.equal(await imageForm.locator('[name="body"]').inputValue(),'');assert.equal(await imageForm.locator('[name="title"]').getAttribute('required'),'');assert.equal(await imageForm.locator('[name="body"]').getAttribute('required'),'');assert.match(await imageForm.innerText(),/原件内容尚未读取，请先核对并填写具体事项。也可以明确安排先核对原件。/);await imageForm.locator('details > summary').click();assert.match(await imageForm.innerText(),/虚构图片消息说明：原件内容尚未读取/);const imageRecordsBefore=imageState.records.length,imageTasksBefore=imageState.tasks.length;await imageForm.locator('[name="title"]').fill('虚构核对后的具体事项 '+width);await imageForm.locator('[name="body"]').fill('虚构明确动作：先核对图片原件，再按通知准备材料。');await imageForm.locator('[type="submit"]').click();await until(async()=>!(await page.locator('#agentDialog').isVisible()),'image placeholder accepted');const imageAfter=await state(),acceptedImage=imageAfter.agent.items.find(x=>x.id===imageItem.id),imageTask=imageAfter.tasks.find(t=>t.title==='虚构核对后的具体事项 '+width);assert.equal(acceptedImage.state,'accepted');assert.ok(imageTask,'accepted image source creates school task');assert.equal(imageAfter.records.length,imageRecordsBefore,'accepting image source creates no learning record');assert.equal(imageAfter.tasks.length,imageTasksBefore+1,'accepting image source creates exactly one task');assert.match(imageTask.source,/message:synthetic:image:/);assert.equal(imageTask.original_status,'待跟进');await page.locator('[data-page="tasks"]').first().click();const imageFollowup=page.locator('[data-query-target="task:'+imageTask.id+'"]');await imageFollowup.waitFor();assert.equal(imageTask.agenda.category,'todo','checking an original is school administration');assert.equal(await imageFollowup.locator('[data-study-task-add]').count(),0,'administration does not become homework');assert.equal(await imageFollowup.locator('[data-task="'+imageTask.id+'"]').count(),1,'accepted school administration can be followed up');await page.locator('[data-page="home"]').first().click();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  // Original-message review is scoped to one child and one message; it must not create a learning fact.
  const originalRef='message:synthetic:original:'+width,original=(await state()).agent.items.find(x=>x.kind==='school'&&x.state==='pending'&&x.evidence?.some(e=>e.ref===originalRef));assert.ok(original,'synthetic original-message school item is pending');const originalBase=await state(),existing=originalBase.uploads.find(x=>x.name==='synthetic-existing.png'),originalIDs={child_id:'child-1',source_id:'synthetic',message_id:'original:'+width};assert.ok(existing,'unlinked existing image is available');
  const readOriginal=async childID=>{const query=new URLSearchParams({...originalIDs,child_id:childID}),response=await fetch(url+'api/agent/message?'+query);return {status:response.status,value:await response.json()}};
  const changeOriginal=async (attachmentID,action)=>{const response=await fetch(url+'api/agent/message/attachment',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':originalBase.token},body:JSON.stringify({...originalIDs,attachment_id:attachmentID,action})});return {status:response.status,value:await response.json()}};
  // The existing original -> editable record journey consumes a prepared draft, without model calls on open.
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();
  const draftButton=page.locator('[data-school-original-ref="message:synthetic:draft:'+width+'"]').first();await draftButton.click();
  const draftDialog=page.locator('#schoolOriginalDialog');await draftDialog.locator('[data-school-material-draft]').waitFor();
  assert.match(await draftDialog.locator('[data-school-material-draft]').innerText(),/不能换算成0分/);assert.equal(await draftDialog.locator('[data-school-material-draft] img').count(),0);await fits(page);await proof(page,'school-material-draft-'+width);
  const beforeDraft=await state();await draftDialog.locator('[data-school-material-record]').click();await page.locator('#recordDialog').waitFor();
  const draftForm=page.locator('#recordForm');assert.equal(await draftForm.locator('[name="child"]').inputValue(),'示例星星');assert.equal(await draftForm.locator('[name="day"]').inputValue(),'');assert.equal(await draftForm.locator('[name="subject"]').inputValue(),'英语');assert.equal(await draftForm.locator('[name="score"]').inputValue(),'');assert.equal(await draftForm.locator('[name="source"]').inputValue(),'message:synthetic:draft:'+width);assert.match(await draftForm.locator('[name="note"]').inputValue(),/待核对/);assert.equal((await state()).records.length,beforeDraft.records.length);
  await draftForm.locator('[name="day"]').fill(beforeDraft.today);await draftForm.locator('[name="note"]').fill('虚构家长核对：原表只有F，具体错误还未核实。');
  let draftFailed=false;await page.route('**/api/record',async route=>{if(!draftFailed){draftFailed=true;return route.fulfill({status:503,json:{error:'虚构保存失败'}})}return route.continue()});
  await draftForm.locator('[type="submit"]').click();await until(async()=>/虚构保存失败/.test(await page.locator('#recordError').innerText()),'draft save failure preserves form');assert.match(await draftForm.locator('[name="note"]').inputValue(),/虚构家长核对/);
  await draftForm.locator('[type="submit"]').click();await page.locator('#recordDialog').waitFor({state:'hidden'});await page.unroute('**/api/record');
  let savedDraft=(await state()).records.filter(r=>r.source==='message:synthetic:draft:'+width);assert.equal(savedDraft.length,1);assert.deepEqual(savedDraft[0].attachments,[existing.id]);assert.equal(savedDraft[0].score,null);assert.equal(savedDraft[0].child,'示例星星');assert.deepEqual((await state()).tasks,beforeDraft.tasks,'a draft record does not complete or create tasks');
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('[data-school-original-ref="message:synthetic:draft:'+width+'"]').first().click();await page.locator('[data-school-material-draft]').waitFor();await page.locator('[data-school-material-record]').click();await until(async()=>!(await page.locator('#recordDialog').isVisible()),'existing record is reopened rather than recreated');await until(async()=>/虚构家长核对/.test(await page.locator('#content').innerText()),'saved record reopened');assert.equal((await state()).records.filter(r=>r.source==='message:synthetic:draft:'+width).length,1);await fits(page);await proof(page,'school-material-record-'+width);
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();
  const originalRecordsBefore=(await state()).records; // The preceding draft journey explicitly saved one record.
  let originalView=await readOriginal('child-1');assert.equal(originalView.status,200);assert.equal(originalView.value.child_id,'child-1');assert.equal(originalView.value.source_id,'synthetic');assert.equal(originalView.value.message_id,'original:'+width);assert.equal(originalView.value.message.unread,true);assert.deepEqual(originalView.value.attachments,[]);const wrongChild=await readOriginal('child-2');assert.notEqual(wrongChild.status,200,'another child cannot read this message');
  const originalCard=page.locator('[data-agent-item="'+original.id+'"]'),originalButton=originalCard.locator('[data-school-original-ref="'+originalRef+'"][data-school-original-child="child-1"]');await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();await originalButton.waitFor();await originalButton.click();const originalDialog=page.locator('#schoolOriginalDialog');await originalDialog.waitFor();const originalFiles=originalDialog.locator('[data-school-original-files]'),originalSelect=originalDialog.locator('[name="attachment_id"]');await originalFiles.waitFor({state:'attached'});await originalSelect.waitFor();assert.equal(await originalFiles.count(),1);assert.ok(await originalSelect.locator('option[value="'+existing.id+'"]').count(),'existing original is selectable');await fits(page);assert.equal(await originalDialog.locator('[data-school-media-note]').innerText(),'自动取图未启用。上次读取原图超时。可在下面补充原件。');await proof(page,'school-original-open-'+width);
  await originalSelect.selectOption(existing.id);await originalDialog.locator('[data-school-original-attach]').click();await until(async()=>originalDialog.locator('[data-school-original-detach="'+existing.id+'"]').isVisible(),'existing original attached');originalView=await readOriginal('child-1');assert.deepEqual(originalView.value.attachments.map(x=>x.id),[existing.id]);assert.equal(originalView.value.message.unread,true);assert.equal(await originalDialog.locator('[data-school-media-note]').count(),0,'a manually supplied original clears the missing-original notice');const afterExisting=await state();assert.deepEqual(afterExisting.records,originalRecordsBefore);assert.deepEqual(afterExisting.rewards,originalBase.rewards);const linkedImage=originalFiles.locator('img').first();await linkedImage.waitFor();await until(async()=>linkedImage.evaluate(img=>img.complete&&img.naturalWidth===96&&img.naturalHeight===64),'linked existing image decoded');
  const duplicate=await changeOriginal(existing.id,'attach');assert.equal(duplicate.status,200);assert.deepEqual(duplicate.value.attachments.map(x=>x.id),[existing.id],'repeated association stays one link');await originalDialog.locator('[data-school-original-detach="'+existing.id+'"]').click();await until(async()=>!(await originalDialog.locator('[data-school-original-detach="'+existing.id+'"]').count()),'existing original detached');assert.equal(await originalDialog.locator('[data-school-media-note]').innerText(),'已停止自动关联，可手动补充。');originalView=await readOriginal('child-1');assert.deepEqual(originalView.value.attachments,[]);assert.ok((await state()).uploads.some(x=>x.id===existing.id),'detaching leaves uploaded file available');assert.equal(originalView.value.message.unread,true);
  const uploadCalls=[],attachmentCalls=[],newPNG=Buffer.from(await (await fetch(url+'upload/'+existing.id)).arrayBuffer());await page.route('**/api/upload',async route=>{uploadCalls.push(route.request().headers()['x-file-name']||'');await route.continue()});await page.route('**/api/agent/message/attachment',async route=>{attachmentCalls.push(route.request().postDataJSON());if(attachmentCalls.length===1)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构原件关联暂时失败'})});await route.continue()});await originalDialog.locator('[data-school-original-upload]').setInputFiles({name:'synthetic-message-'+width+'.png',mimeType:'image/png',buffer:newPNG});await until(async()=>originalDialog.locator('[data-school-original-retry]').isVisible(),'association retry is offered');assert.equal(uploadCalls.length,1,'failed association does not retry upload');const uploaded=(await state()).uploads.find(x=>x.name==='synthetic-message-'+width+'.png');assert.ok(uploaded,'uploaded original survives association failure');assert.equal(attachmentCalls.length,1);await originalDialog.locator('[data-school-original-retry]').click();await until(async()=>originalDialog.locator('[data-school-original-detach="'+uploaded.id+'"]').isVisible(),'uploaded original association retried');assert.equal(uploadCalls.length,1,'retry reuses uploaded id');assert.equal(attachmentCalls.length,2);assert.equal(attachmentCalls[1].attachment_id,uploaded.id);originalView=await readOriginal('child-1');assert.deepEqual(originalView.value.attachments.map(x=>x.id),[uploaded.id]);assert.equal(originalView.value.message.unread,true);const uploadedImage=originalFiles.locator('img').first();await uploadedImage.waitFor();await until(async()=>uploadedImage.evaluate(img=>img.complete&&img.naturalWidth===96&&img.naturalHeight===64),'linked uploaded image decoded');await fits(page);await proof(page,'school-original-retry-'+width);
  await originalDialog.locator('[data-school-original-detach="'+uploaded.id+'"]').click();await until(async()=>!(await originalDialog.locator('[data-school-original-detach="'+uploaded.id+'"]').count()),'uploaded original detached');originalView=await readOriginal('child-1');assert.deepEqual(originalView.value.attachments,[]);assert.ok((await state()).uploads.some(x=>x.id===uploaded.id),'detached upload remains in整理资料');assert.deepEqual((await state()).records,originalRecordsBefore);const lostName='synthetic-lost-response-'+width+'.png',lostUploadCalls=[];await page.route('**/api/upload',async route=>{lostUploadCalls.push(route.request().headers()['x-file-name']||'');const response=await route.fetch();await route.abort('connectionreset')});await originalDialog.locator('[data-school-original-upload]').setInputFiles({name:lostName,mimeType:'image/png',buffer:newPNG});await until(async()=>originalDialog.locator('[name="attachment_id"] option').filter({hasText:lostName}).count().then(n=>n===1),'saved upload returns after lost receipt');assert.equal(lostUploadCalls.length,1,'lost upload receipt does not cause a second upload');const lostUploaded=(await state()).uploads.find(x=>x.name===lostName);assert.ok(lostUploaded,'lost upload remains available');assert.deepEqual((await state()).records,originalRecordsBefore);await originalDialog.locator('[name="attachment_id"]').selectOption(lostUploaded.id);await originalDialog.locator('[data-school-original-attach]').click();await until(async()=>originalDialog.locator('[data-school-original-detach="'+lostUploaded.id+'"]').isVisible(),'saved upload can be associated after lost receipt');assert.equal(lostUploadCalls.length,1);await originalDialog.locator('[data-school-original-detach="'+lostUploaded.id+'"]').click();await until(async()=>!(await originalDialog.locator('[data-school-original-detach="'+lostUploaded.id+'"]').count()),'lost upload detached');await page.unroute('**/api/upload');await page.unroute('**/api/agent/message/attachment');await originalDialog.locator('[data-school-original-close]').click();await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();const restored=page.locator('[data-agent-item="'+original.id+'"]');await restored.waitFor();assert.equal(await restored.locator('[data-school-original-ref="'+originalRef+'"][data-school-original-child="child-1"]').count(),1,'detached message returns to整理');await fits(page);await proof(page,'school-original-restored-'+width);
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();const before=await state(),school=before.agent.items.find(x=>x.kind==='school'&&x.state==='pending'&&!x.needs_task_details&&/^虚构学校准备 /.test(x.title)),schoolID=school?.id,sourceButton=page.locator('[data-agent-item="'+schoolID+'"] [data-school-record-agent]').first(),ref=school?.evidence?.[0]?.ref;assert.ok(school&&schoolID&&ref,'normal school source remains pending after placeholder acceptance')
  assert.ok(school&&school.kind==='school');
  // A malformed source cannot fall through to the general form's default child.
  await sourceButton.evaluate(b=>b.setAttribute('data-school-record-agent',''));
  await page.locator('[data-school-record-agent=""]').click();await delay(150);
  assert.equal(await page.locator('#recordDialog').isVisible(),false,'empty source ID never opens a default-child record');
  assert.equal((await state()).records.length,before.records.length);
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();
  await page.locator('[data-school-record-agent="'+schoolID+'"]').click();await page.locator('#recordDialog').waitFor();
  const record=page.locator('#recordForm');
  assert.equal(await record.locator('[name="child"]').inputValue(),'示例星星');
  assert.equal(await record.locator('[name="category"]').inputValue(),'学习进展');
  assert.deepEqual(await record.locator('[name="category"]').evaluate(select=>[...select.options].map(option=>option.value)),['学习进展','课程进度','成绩'],'school material preserves progress, curriculum and score choices');
  assert.equal(await record.locator('[name="source"]').inputValue(),ref);
  assert.equal(await record.locator('[name="day"]').inputValue(),'','notification due is not the actual learning date');
  assert.equal(await record.locator('[name="related_record_id"]').inputValue(),'');
  assert.equal(await record.locator('[name="followup_kind"]').inputValue(),'');
  assert.equal(await record.locator('[name="assistance"]').inputValue(),'');
  const material=await record.locator('[name="note"]').inputValue();
  assert.match(material,/虚构老师通知：请准备观察材料/);assert.match(material,/待核对/);assert.ok(material.includes('<img src=x onerror=alert(1)>'));
  assert.equal(await page.locator('#recordDialog img').count(),0);
  assert.equal((await state()).records.length,before.records.length,'opening a school source does not fabricate a learning fact');
  await record.locator('[name="day"]').fill(before.today);await record.locator('[name="note"]').fill(material+'\n虚构家长补记：实际表现还要听孩子说明。');
  const attempts=[];let recordPhase=0;
  await page.route('**/api/record',async route=>{
   attempts.push(route.request().postDataJSON());recordPhase++;
   if(recordPhase===1)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构学校记录网络故障'})});
   if(recordPhase===2){const response=await route.fetch();assert.equal(response.status(),200);return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构学校记录回执丢失'})})}
   await route.continue();
  });
  await record.locator('[type="submit"]').click();await until(async()=>/虚构学校记录网络故障/.test(await page.locator('#recordError').innerText()),'school save failure visible');
  assert.equal((await state()).records.length,before.records.length);assert.equal(await record.locator('[name="source"]').inputValue(),ref);assert.match(await record.locator('[name="note"]').inputValue(),/虚构家长补记/);
  await fits(page);await proof(page,'school-record-retry-'+width);
  await record.locator('[type="submit"]').click();await until(async()=>/虚构学校记录回执丢失/.test(await page.locator('#recordError').innerText()),'lost receipt visible');
  assert.equal((await state()).records.filter(r=>r.child==='示例星星'&&r.source===ref).length,1,'unknown response already saved exactly once');
  await record.locator('[type="submit"]').click();await until(async()=>!(await page.locator('#recordDialog').isVisible()),'same source request retried');await page.unroute('**/api/record');
  assert.equal(attempts.length,3);assert.ok(attempts[0].request_key);assert.deepEqual(attempts[1],attempts[0]);assert.deepEqual(attempts[2],attempts[0]);
  let current=await state();const schoolRecord=current.records.find(r=>r.child==='示例星星'&&r.source===ref);assert.ok(schoolRecord);
  assert.equal(current.records.length,before.records.length+1);assert.deepEqual(current.tasks,before.tasks,'school record does not create or complete a task');
  const learning=()=>page.locator('[data-learning-case="'+schoolRecord.id+'"]');await until(()=>learning().isVisible(),'saved school record stays in its learning case');
  assert.equal((await page.locator('.learning-journeys').innerText()).includes('SIBLING_SAME_SOURCE_CANARY'),false,'same source from a sibling cannot be selected or shown as this child case');
  assert.doesNotMatch(await learning().innerText(),/尚无复测|还没有复测|订正 0|复测 0/,'ordinary school context does not force a correction/retest path');
  await proof(page,'school-learning-case-'+width);
  await page.locator('[data-page="home"]').first().click();await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();
  const first=page.locator('[data-agent-accept="'+schoolID+'"]');await first.click();await page.locator('#agentDialog').waitFor();await page.locator('#agentForm [name="title"]').fill('虚构家长核对 '+width);await page.locator('#agentForm [name="body"]').fill('带一本笔记本');
  await page.route('**/api/agent/action',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构网络暂不可用'})}),{times:1});
  await page.locator('#agentForm [type="submit"]').click();await until(()=>page.locator('#agentError').textContent().then(t=>t.includes('虚构网络')),'failed save visible');assert.equal(await page.locator('#agentForm [name="body"]').inputValue(),'带一本笔记本');
  assert.equal(await page.locator('#agentDialog').evaluate(d=>d.scrollWidth>d.clientWidth),false);
  await proof(page,'agent-form-'+width);
  await page.locator('#agentForm [type="submit"]').click();await until(()=>page.locator('#agentDialog').isVisible().then(v=>!v),'saved');await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  const saved=await state();assert.equal(saved.tasks.filter(t=>t.title==='虚构家长核对 '+width).length,1);assert.equal(saved.tasks.find(t=>t.title==='虚构家长核对 '+width).child,'示例星星');
  const acceptedTask=saved.tasks.find(t=>t.title==='虚构家长核对 '+width);
  await page.locator('[data-page="tasks"]').first().click();await openTaskRecordFromCard(page,acceptedTask.id);await until(()=>learning().isVisible(),'accepted task opens existing same-source learning case');
  assert.equal(await page.locator('#recordDialog').isVisible(),false);assert.equal((await state()).records.filter(r=>r.child==='示例星星'&&r.source===ref).length,1);
  await learning().locator('[data-followup-kind="补充观察"]').click();await page.locator('#recordDialog').waitFor();
  assert.ok((await record.locator('[name="category"]').evaluate(select=>[...select.options].map(option=>option.value))).includes('家长观察'),'ordinary followup restores the full record categories');
  assert.equal(await record.locator('[name="child"]').inputValue(),'示例星星');assert.equal(await record.locator('[name="related_record_id"]').inputValue(),String(schoolRecord.id));assert.equal(await record.locator('[name="followup_kind"]').inputValue(),'补充观察');
  await record.locator('[name="day"]').fill(saved.today);await record.locator('[name="title"]').fill('虚构孩子解释 '+width);await record.locator('[name="note"]').fill('孩子说想先画出观察到的形状；这次没有核对是否完成。');
  await record.locator('[type="submit"]').click();await until(async()=>!(await page.locator('#recordDialog').isVisible()),'child explanation appended');
  current=await state();const observation=current.records.find(r=>r.title==='虚构孩子解释 '+width);assert.equal(observation.related_record_id,schoolRecord.id);assert.equal(observation.child,schoolRecord.child);assert.equal(observation.followup_kind,'补充观察');assert.deepEqual(current.tasks.find(t=>t.id===acceptedTask.id),acceptedTask);
  // A second source begins from an existing task so all task feedback must carry over.
  const pendingSchool=current.agent.items.find(x=>x.kind==='school'&&x.state==='pending'&&!x.needs_task_details&&/^虚构学校准备 /.test(x.title)),token=current.token;assert.ok(pendingSchool,'a normal pending school source remains for task feedback');
  const accept=await fetch(url+'api/agent/action',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':token},body:JSON.stringify({id:pendingSchool.id,action:'accept',title:'虚构已反馈事项 '+width,body:'核对原通知，和孩子商量观察材料。'})});assert.equal(accept.status,200);const secondTaskID=(await accept.json()).task_id,secondRef=pendingSchool.evidence[0].ref;
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await page.locator('[data-page="tasks"]').first().click();
  for(const [status,note] of [['待跟进','虚构第一条反馈：还要核对当天安排。'],['进行中','虚构第二条反馈：孩子想先画图，请听他解释。']]){
   await page.locator('[data-task="'+secondTaskID+'"]').click();await page.locator('#taskDialog').waitFor();await page.locator('#taskForm [name="status"]').selectOption(status);await page.locator('#taskForm [name="note"]').fill(note);await page.locator('#taskForm [type="submit"]').click();await until(async()=>!(await page.locator('#taskDialog').isVisible()),'task feedback saved');
  }
  const taskBeforeRecord=(await state()).tasks.find(t=>t.id===secondTaskID);
  await openTaskRecordFromCard(page,secondTaskID);await page.locator('#recordDialog').waitFor();
  assert.equal(await record.locator('[name="source"]').inputValue(),secondRef);assert.equal(await record.locator('[name="child"]').inputValue(),'示例星星');assert.equal(await record.locator('[name="day"]').inputValue(),'');
  const feedback=await record.locator('[name="note"]').inputValue();assert.match(feedback,/虚构老师通知：请准备观察材料/);assert.match(feedback,/虚构第一条反馈/);assert.match(feedback,/虚构第二条反馈/);assert.match(feedback,/待核对/);assert.doesNotMatch(feedback,/已经完成|已经掌握|孩子未做|孩子没有做/);
  await record.locator('[name="day"]').fill(current.today);await fits(page);await proof(page,'school-task-material-'+width);
  await page.route('**/api/record',async route=>{const response=await route.fetch();assert.equal(response.status(),200);await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构关闭前回执未知'})})},{times:1});
  await record.locator('[type="submit"]').click();await until(async()=>/虚构关闭前回执未知/.test(await page.locator('#recordError').innerText()),'task-source receipt unknown');
  await page.locator('[data-close="recordDialog"]').click();await openTaskRecordFromCard(page,secondTaskID);
  const afterUnknown=await state(),taskRecord=afterUnknown.records.find(r=>r.child==='示例星星'&&r.source===secondRef);assert.ok(taskRecord);await until(()=>page.locator('[data-learning-case="'+taskRecord.id+'"]').isVisible(),'fresh state recovers an unknown saved receipt into existing case');
  assert.equal(await page.locator('#recordDialog').isVisible(),false);assert.equal(afterUnknown.records.filter(r=>r.child==='示例星星'&&r.source===secondRef).length,1);assert.deepEqual(afterUnknown.tasks.find(t=>t.id===secondTaskID),taskBeforeRecord);
  await page.locator('[data-page="home"]').first().click();await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();
  await page.locator('[data-followup="1"]').click();await page.locator('#recordDialog').waitFor();assert.equal(await page.locator('#recordForm [name="child"]').inputValue(),'示例小宇');assert.equal(await page.locator('#recordForm [name="related_record_id"]').inputValue(),'1');await page.locator('[data-close="recordDialog"]').click();
  await page.locator('.agent-status details summary').click();assert.equal(await page.locator('.agent-item img').count(),0);assert.match(await page.locator('.agent-status').innerText(),/上次整理/);
  await fits(page);await proof(page,'agent-'+width);
  // Planned care is a separate synthetic item: approval edits are visible, retry keeps the same form/id, and defer keeps a parent-chosen date.
  const planned=page.locator('[data-agent-item]').filter({hasText:'虚构时间管理小动作 '+width});await planned.scrollIntoViewIfNeeded();await proof(page,'planned-care-'+width);assert.match(await planned.innerText(),/具体动作|目标：|为什么现在：|25 分钟/);const plannedID=await planned.getAttribute('data-agent-item');await planned.locator('[data-agent-accept]').click();await page.locator('#agentDialog').waitFor();assert.equal(await page.locator('#agentForm [name="review_on"]').inputValue(),current.today);await page.locator('#agentForm [name="title"]').fill('虚构已核对的时间安排 '+width);await page.locator('#agentForm [name="body"]').fill('19:00 开始，完成一轮后记录实际分钟数');await page.locator('#agentForm [name="estimated_minutes"]').fill('30');await page.route('**/api/agent/action',async r=>{try{await r.fetch()}catch(e){console.error('Synthetic server request failed:',errors.slice(-2500))}await r.abort('connectionreset')},{times:1});await page.locator('#agentForm [type="submit"]').click();await until(()=>page.locator('#agentError').textContent().then(t=>Boolean(t)),'planned care failure visible');assert.equal(await page.locator('#agentForm [name="body"]').inputValue(),'19:00 开始，完成一轮后记录实际分钟数');await page.locator('#agentForm [type="submit"]').click();await until(()=>page.locator('#agentDialog').isVisible().then(v=>!v),'planned care accepted');await page.unroute('**/api/agent/action');let plannedState=await state();assert.equal(plannedState.agent.items.filter(x=>x.id===plannedID).length,1);const plannedTask=plannedState.tasks.find(t=>t.title==='虚构已核对的时间安排 '+width);assert.ok(plannedTask);const plannedGroup=page.locator('details.card').filter({hasText:'虚构已核对的时间安排 '+width});if(await plannedGroup.getAttribute('open')===null)await plannedGroup.locator(':scope > summary').click();
  const acceptedPlanned=page.locator('[data-agent-item="'+plannedID+'"]');await acceptedPlanned.locator('[data-goal-id="'+plannedID+'"]').click();
  const manualPlan=page.locator('[data-goal-form="manual"]');await manualPlan.waitFor({state:'attached'});const manualSection=manualPlan.locator('xpath=ancestor::details[1]');if(await manualSection.getAttribute('open')===null)await manualSection.locator(':scope > summary').click();
  const deferredDate=new Date(Date.parse(current.today+'T12:00:00Z')+7*86400000).toISOString().slice(0,10),competingDate=new Date(Date.parse(current.today+'T12:00:00Z')+5*86400000).toISOString().slice(0,10);
  await manualPlan.locator('[name="review_on"]').fill(deferredDate);
  const goalsNow=await(await fetch(url+'api/goals')).json(),currentGoal=goalsNow.goals.find(g=>g.id===plannedID);assert.ok(currentGoal);assert.equal(currentGoal.task_id,plannedTask.id);
  const competingPlan=Object.fromEntries(['title','goal','action','resource','mastery_check','estimated_minutes','review_on'].map(k=>[k,currentGoal.current_plan[k]??(k==='estimated_minutes'?null:'')]));competingPlan.review_on=competingDate;
  const competing=await fetch(url+'api/goals/action',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':token},body:JSON.stringify({id:plannedID,action:'manual',expected_version:currentGoal.version,context_hash:currentGoal.context_hash,request_key:'synthetic-competing-plan-'+width,plan:competingPlan})});assert.equal(competing.status,200,await competing.text());
  await manualPlan.locator('[type="submit"]').click();await manualPlan.locator('[data-goal-rebase]').waitFor();assert.equal(await manualPlan.locator('[name="review_on"]').inputValue(),deferredDate,'conflict preserves the proposed date');assert.match(await manualPlan.innerText(),new RegExp(competingDate));
  await manualPlan.locator('[data-goal-rebase]').click();assert.equal(await manualPlan.locator('[name="review_on"]').inputValue(),deferredDate);await fits(page);
  await manualPlan.locator('[type="submit"]').click();await until(async()=>{const g=(await(await fetch(url+'api/goals')).json()).goals.find(g=>g.id===plannedID);return g.current_plan.review_on===deferredDate},'current goal changes original plan review date');
  const deferredState=await state();assert.equal(deferredState.agent.items.find(x=>x.id===plannedID).plan.approved.review_on,deferredDate);assert.equal(deferredState.tasks.filter(t=>t.id===plannedTask.id).length,1);
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('#content h1').waitFor();const reopenedGroup=page.locator('details.card').filter({hasText:'虚构已核对的时间安排 '+width});if(await reopenedGroup.getAttribute('open')===null)await reopenedGroup.locator(':scope > summary').click();const reopenedPlan=page.locator('[data-agent-item="'+plannedID+'"]');assert.match(await reopenedPlan.innerText(),new RegExp(deferredDate));await fits(page);await proof(page,'planned-care-deferred-'+width);
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();
  const examState=await state(),exam=examState.tasks.find(t=>t.title==='虚构英语单元测验 '+width),examReminder=examState.agent.items.find(i=>i.task_id===exam.id&&i.plan?.exam_result_pending),examCard=page.locator('[data-agent-item="'+examReminder.id+'"]');
  await examCard.getByRole('button',{name:'记录考试结果',exact:true}).click();await page.locator('#recordDialog').waitFor();
  const examForm=page.locator('#recordForm');assert.equal(await examForm.locator('[name="child"]').inputValue(),'示例星星');assert.equal(await examForm.locator('[name="day"]').inputValue(),'');
  await examForm.locator('[name="day"]').fill(examState.today);await examForm.locator('[name="category"]').selectOption('成绩');await examForm.locator('[name="subject"]').fill('英语');await examForm.locator('[name="score"]').fill('60');await examForm.locator('[name="total"]').fill('100');await examForm.locator('[name="note"]').fill('虚构结果：拼写需要一次提示。');await fits(page);await proof(page,'exam-result-form-'+width);
  await page.route('**/api/record',async route=>{const reply=await route.fetch();assert.equal(reply.status(),200);await route.fulfill({status:503,json:{error:'虚构考试记录回执丢失'}})},{times:1});
  await examForm.locator('[type="submit"]').click();await until(async()=>/虚构考试记录回执丢失/.test(await page.locator('#recordError').innerText()),'exam result retry');assert.equal(await examForm.locator('[name="score"]').inputValue(),'60');
  await examForm.locator('[type="submit"]').click();await page.locator('#recordDialog').waitFor({state:'hidden'});
  const examSaved=await state(),examRecords=examSaved.records.filter(r=>r.source==='事项:'+exam.id);assert.equal(examRecords.length,1);assert.equal(examRecords[0].score,60);assert.notEqual(examSaved.tasks.find(t=>t.id===exam.id).update?.status,'已完成');
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await examCard.locator('[data-task]').click();await page.locator('#taskDialog').waitFor();
  await page.locator('#taskForm [name="status"]').selectOption('已完成');await page.locator('#taskForm [name="note"]').fill('虚构家长确认：已核对结果。');await page.locator('#taskForm [type="submit"]').click();await page.locator('#taskDialog').waitFor({state:'hidden'});assert.equal(await examCard.count(),0,'closed exam disappears immediately');
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();assert.equal(await examCard.count(),0,'closed exam stays hidden after reload');await fits(page);await proof(page,'exam-result-closed-'+width);
  assert.deepEqual(pageErrors,[]);await page.close();
 }
 const p=await browser.newPage();await p.goto(url);await p.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await p.locator('nav [data-page="more"]').click();await p.locator('#content [data-page="agent"]').click();await p.locator('#content h1').waitFor();const recordsBeforeDismiss=(await state()).records.length;const pendingCare=(await state()).agent.items.find(x=>x.kind==='care'&&x.state==='pending');assert.ok(pendingCare);await p.locator('[data-agent-item="'+pendingCare.id+'"] [data-agent-dismiss]').click();await until(async()=>!(await state()).agent.items.some(x=>x.kind==='care'&&x.state==='pending'),'dismiss saved');assert.equal((await state()).records.length,recordsBeforeDismiss,'acknowledgement does not fabricate child feedback');await p.close();
 console.log(JSON.stringify({passed:true,examRecordRetryAndClose:true,widths:[360,1440],realAPI:true,syntheticOnly:true,formRetry:true,childBinding:true,escapedEvidence:true,acknowledgementNotFeedback:true,schoolSourceEntry:true,actualDayNotGuessed:true,taskFeedbackPreserved:true,sameSourceSameCase:true,observationSameChain:true,stableRecordRetry:true,closedUnknownReceiptRecovered:true,recordDoesNotChangeTask:true,emptySourceNoDefaultChild:true,ordinarySchoolEventNoForcedRetest:true,plannedCareLostReceipt:true,plannedCareConcurrentDeferral:true,preparedImageDraft:true,letterGradeNotNumeric:true,imageDraftEditableAndLinked:true,draftSaveRetryAndReopen:true,duplicateNoticePreservesDecision:true,allDuplicateOriginsReadable:true,schoolChangesParentConfirmed:true,schoolChangeConflictAndRetry:true,cancelKeepsHistory:true,cancelStopsStudy:true,oldCompletionNotNewMastery:true}));
}finally{if(browser)await browser.close();if(proc&&proc.exitCode===null){proc.kill('SIGINT');await once(proc,'exit')}}})().catch(e=>{console.error(e);process.exitCode=1});
