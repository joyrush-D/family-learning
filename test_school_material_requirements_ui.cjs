// Synthetic browser + real local API checks: an ordinary (non-PDF) school draft shows each original's own requirements.
// Fictional children, notices and pictures only; drafts come from the real preparation path with a fixed stand-in reply,
// then every model, print and write path is forbidden while the pages are read. Set MATERIAL_PROOF_DIR outside the checkout.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),fs=require('node:fs/promises'),path=require('node:path'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const proofDir=process.env.MATERIAL_PROOF_DIR||'';
async function until(check,label){for(let i=0;i<200;i++){if(await check())return;await delay(50)}throw Error(label)}
async function fits(page){
 const sizes=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth,dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>({width:d.clientWidth,scroll:d.scrollWidth,left:d.getBoundingClientRect().left,right:d.getBoundingClientRect().right}))}));
 assert(sizes.page<=sizes.viewport,'no document overflow '+JSON.stringify(sizes));for(const d of sizes.dialogs)assert(d.scroll<=d.width+1&&d.left>=-1&&d.right<=sizes.viewport+1,'no dialog overflow '+JSON.stringify(sizes));
}
async function shot(page,name,target){if(!proofDir)return;if(target)await target.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(proofDir,name+'.png')})}
const fixture=String.raw`
import tempfile,os,json,datetime,io,struct,zlib
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
with tempfile.TemporaryDirectory(prefix='synthetic-material-requirements-') as tmp:
 os.environ['FAMILY_DATA']=tmp
 import app,family_agent,family_llm,family_media
 app.DATA=Path(tmp).resolve();app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 (app.DATA/'agent.json').write_text(json.dumps({'enabled':True,'sources':[{'id':'synthetic','platform':'wechat','child_id':'child-1','name':'虚构班级通知','cursor':'','enabled':True},{'id':'sibling','platform':'wechat','child_id':'child-2','name':'虚构另一孩子群','cursor':'','enabled':True}]}))
 store=app.agent_store();now=datetime.datetime.now(family_agent.TZ);today=now.date().isoformat()
 def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 def png(r,g,b): return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',96,64,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\x00'+bytes([r,g,b,255])*96 for _ in range(64))))+chunk(b'IEND',b'')
 files=[('eng','虚构英语练习单-正面.png',(40,120,220)),('eng','虚构英语练习单-老师附注.png',(220,160,40)),('math','虚构数学口算单.png',(60,180,90)),('scope','虚构科学观察单.png',(150,80,200)),('canary','虚构另一孩子资料.png',(200,60,60))]
 uploads={name:app.save_upload(io.BytesIO(png(*rgb)),len(png(*rgb)),name) for _,name,rgb in files}
 def message(ident,text): return dict(id=ident,time=now.isoformat(),kind='image',sender='虚构老师',text=text,unread=True)
 store.ingest(dict(source_id='synthetic',expected_cursor='',cursor='c1',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[message('eng','虚构英语：练习单与老师附注见图。'),message('math','虚构数学：口算单见图。'),message('scope','虚构科学：观察单见图。')]))
 store.ingest(dict(source_id='sibling',expected_cursor='',cursor='c1',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[message('canary','虚构另一孩子：资料见图。')]))
 for ident,name,_ in files:
  store.message_attachment(dict(child_id='child-2' if ident=='canary' else 'child-1',source_id='sibling' if ident=='canary' else 'synthetic',message_id=ident,attachment_id=uploads[name]['id'],action='attach'),dict)
 # Fixed per-original stand-in replies: line breaks, a teacher note and an optional question stay in the stored requirements.
 content={
  '虚构英语练习单-正面.png':dict(title='英语练习单',note='图片为英语练习单正面：Unit 2课文与第1–4题。',uncertainties=[],requirements=['朗读Unit 2课文两遍。\n完成练习第1–3题。','第4题选做，不做不扣分。']),
  '虚构英语练习单-老师附注.png':dict(title='老师附注',note='图片为老师手写附注。',uncertainties=['签字栏位置看不清'],requirements=['老师附注：练习单单面打印。\n完成后先自查，再请家长签字。']),
  '虚构数学口算单.png':dict(title='数学口算单',note='图片为数学口算单。',uncertainties=[],requirements=['完成口算第1–20题，限时10分钟。']),
  '虚构科学观察单.png':dict(title='科学观察单',note='图片为科学观察记录单。',uncertainties=[],requirements=['SCOPE_CANARY 连续三天记录豆芽高度。']),
  '虚构另一孩子资料.png':dict(title='另一孩子资料',note='另一孩子的原件。',uncertainties=[],requirements=['CANARY_OTHER_CHILD 背诵第9课。'])}
 by_id={uploads[name]['id']:value for name,value in content.items()}
 def model(text,images,**kw):
  assert kw.get('school_material') is True and len(images)==len(kw['original_ids'])
  return dict(originals=[dict(upload_id=i,**by_id[i]) for i in kw['original_ids']])
 with patch.object(family_llm,'extract_draft',side_effect=model) as prepared:
  for _ in range(4): assert family_media.prepare_draft(store,now)==dict(used=1,failed=0)
  assert family_media.prepare_draft(store,now)==dict(used=0,failed=0)
 assert prepared.call_count==4
 tasks=dict(
  eng=app.new_task(dict(child='示例星星',title='虚构英语练习单作业',action='按老师原件完成英语练习单。',due=today,source='message:synthetic:eng',request_key='synthetic-material-eng-0001'))['id'],
  math=app.new_task(dict(child='示例星星',title='虚构数学口算作业',action='按老师原件完成数学口算。',due=today,source='message:synthetic:math',request_key='synthetic-material-math-001'))['id'])
 # An accepted school task without a saved original scope: its task material must stay rejected.
 store._save('scope:fixture','fixture',[dict(child_id='child-1',kind='school',title='虚构科学观察作业',body='按原件完成科学观察。',due=today,evidence=[dict(ref='message:synthetic:scope',text='虚构科学：观察单见图。')],plan=dict(school_task=dict(title='虚构科学观察作业',goal='按原件完成科学观察。',advice='',state='ready',reason='虚构固定夹具',purpose='learning',policy=family_agent.SCHOOL_TASK_POLICY)))],now)
 with store._db() as c: ident=c.execute('SELECT id FROM agent_items WHERE job_id=?',('scope:fixture',)).fetchone()[0]
 tasks['scope']=store.act(dict(id=ident,action='accept'))['task_id']
 store._runtime('ready',now)
 printer=patch.object(app.family_print.PrintStore,'enqueue',side_effect=AssertionError('printing forbidden')).start()
 drafts=patch.object(family_llm,'extract_draft',side_effect=AssertionError('model forbidden')).start()
 chats=patch.object(family_llm,'_chat_json',side_effect=AssertionError('model forbidden')).start()
 patch('socket.create_connection',side_effect=AssertionError('outbound network forbidden')).start()
 posts=[]
 proof=dict(today=today,tasks=tasks,uploads={name:u['id'] for name,u in uploads.items()},content=content)
 class Handler(app.Handler):
  def log_message(self,*args):pass
  def do_GET(self):
   if self.path=='/__fixture/proof':return self.reply(200,dict(proof,posts=posts,model_calls=drafts.call_count+chats.call_count,print_attempts=printer.call_count))
   return super().do_GET()
  def do_POST(self):
   posts.append(urlparse(self.path).path);return self.reply(503,dict(error='synthetic reading test forbids writes'))
 app.prepare_assets()
 server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_AGENT_PORT'])),Handler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
`;
(async()=>{let proc,browser,lastPage;const record={synthetic_only:true,widths:[]};try{
 if(proofDir){const source=await fs.realpath(__dirname);await fs.mkdir(proofDir,{recursive:true});const target=await fs.realpath(proofDir);assert(target!==source&&!target.startsWith(source+path.sep),'proof stays outside the checkout')}
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));const url='http://127.0.0.1:'+port+'/',env={...process.env,TEST_AGENT_PORT:String(port),PYTHONDONTWRITEBYTECODE:'1'};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let errors='';proc.stderr.on('data',b=>{errors+=b});proc.on('error',e=>errors+=e.message);
 await until(async()=>{if(proc.exitCode!==null)throw Error(errors);try{return(await fetch(url)).ok}catch{return false}},'server startup');
 const state=async()=>await(await fetch(url+'api/state')).json(),fx=await(await fetch(url+'__fixture/proof')).json();
 const expected=names=>names.map(name=>({upload_id:fx.uploads[name],name,...fx.content[name]}));
 const ENG=expected(['虚构英语练习单-正面.png','虚构英语练习单-老师附注.png']).sort((a,b)=>a.upload_id<b.upload_id?-1:1),MATH=expected(['虚构数学口算单.png']);
 const words=list=>list.flatMap(o=>o.requirements.flatMap(r=>r.split('\n')));
 const engWords=words(ENG),mathWords=words(MATH),canaries=['SCOPE_CANARY','CANARY_OTHER_CHILD'];
 // Each original's own requirements appear verbatim (line breaks rendered) under that upload ID, before its background note.
 async function originals(scope,want,forbidden,label){
  assert.deepEqual(await scope.locator('[data-school-draft-original]').evaluateAll(xs=>xs.map(x=>x.dataset.schoolDraftOriginal)),want.map(o=>o.upload_id),label+': one group per returned original, in order');
  for(const o of want){
   const group=scope.locator('[data-school-draft-original="'+o.upload_id+'"]'),items=group.locator('[data-school-draft-requirement]');
   assert.equal(await group.locator('h4').innerText(),want.length>1?o.name+' · '+o.title:o.name,label+': group names its own file');
   assert.deepEqual(await items.evaluateAll(xs=>xs.map(x=>x.textContent)),o.requirements,label+': requirements verbatim');
   for(const [i,item] of (await items.all()).entries()){
    assert.equal(await item.isVisible(),true,label+': requirement directly visible');assert.equal(await item.evaluate(x=>!!x.closest('details:not([open])')),false,label+': not folded');
    assert.equal(await item.evaluate(x=>getComputedStyle(x).whiteSpace),'pre-wrap');assert.equal((await item.innerText()).split('\n').length,o.requirements[i].split('\n').length,label+': line breaks rendered');
   }
   const note=group.locator('p.small.muted').filter({hasText:o.note});assert.equal(await note.count(),1,label+': note kept as background');
   assert.equal(await group.evaluate((g,text)=>{const ps=[...g.querySelectorAll('p')],n=ps.findIndex(p=>p.textContent===text);return ps.slice(n).every(p=>!p.hasAttribute('data-school-draft-requirement'))},o.note),true,label+': requirements come before the background note');
   if(o.uncertainties.length)assert.match(await group.innerText(),new RegExp('待补充：'+o.uncertainties.join('；')));
   const text=await group.innerText();for(const other of want.filter(x=>x!==o).flatMap(x=>x.requirements.flatMap(r=>r.split('\n'))))assert(!text.includes(other),label+': '+o.name+' does not hold another original\'s requirement '+other);
  }
  const all=await scope.innerText();for(const word of forbidden)assert(!all.includes(word),label+': excludes '+word);
 }
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
 const before=await state(),facts=s=>JSON.stringify([s.tasks.map(t=>[t.id,t.title,t.action,t.status,t.update,t.due]),s.records]);
 for(const id of Object.values(fx.tasks)){const t=before.tasks.find(x=>x.id===id);assert(t,'fixture task '+id);assert.equal(t.update,null,'no completion state before reading')}
 assert.equal(before.tasks.find(t=>t.id===fx.tasks.scope).school_origin,true);assert.notEqual(before.tasks.find(t=>t.id===fx.tasks.eng).school_origin,true);
 for(const width of [360,1440]){
  const page=await browser.newPage({viewport:{width,height:820}}),pageErrors=[],external=[];lastPage=page;page.on('pageerror',e=>pageErrors.push(e.message));
  await page.route('**/*',route=>{const u=route.request().url();if(u.startsWith(url)||u.startsWith('data:')||u.startsWith('blob:'))return route.continue();external.push(u);return route.abort()});
  const responses=[];page.on('response',async r=>{const u=new URL(r.url());if(u.pathname==='/api/agent/message')responses.push({query:Object.fromEntries(u.searchParams),status:r.status(),body:await r.json().catch(()=>null)})});
  const card=id=>page.locator('#content [data-query-target="task:'+id+'"]'),dialog=page.locator('#schoolOriginalDialog'),task=page.locator('#taskDialog'),resources=task.locator('#taskSchoolResources');
  const home=async()=>{await page.locator('body[data-page="home"]').waitFor();const filter=page.locator('[data-child-filter="child-1"]');if(await filter.count())await filter.first().click();await card(fx.tasks.eng).waitFor()};
  const fromToday=async(id,ref)=>{await card(id).locator('[data-school-original-ref="'+ref+'"]').first().click();await page.locator('#schoolOriginalDialog[open]').waitFor()};
  const closeOriginal=async()=>{await dialog.locator('[data-school-original-close]').click();await until(async()=>!(await dialog.isVisible()),'original closed')};
  const feedback=async id=>{await card(id).locator('[data-task="'+id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();assert.equal(await page.locator('#taskForm [name=id]').inputValue(),id)};
  const closeTask=async()=>{await task.locator('[data-close="taskDialog"]').click();await until(async()=>!(await task.isVisible()),'task closed')};
  const apiDraft=messageID=>{const r=responses.filter(x=>x.query.message_id===messageID&&!x.query.task_id).at(-1);assert(r&&r.status===200,'real API view for '+messageID);return r.body.material_draft};
  const sameAsAPI=(d,want)=>{assert.equal(d.state,'ready');assert.equal(d.kind,'school_material');assert.deepEqual(d.draft.originals.map(o=>[o.upload_id,o.requirements]),want.map(o=>[o.upload_id,o.requirements]),'UI groups equal the returned originals')};
  await page.goto(url);await home();
  // 1. Today -> the same homework's original notice.
  await fromToday(fx.tasks.eng,'message:synthetic:eng');const draft=dialog.locator('[data-school-material-draft]');await draft.locator('[data-school-draft-original]').first().waitFor();
  sameAsAPI(apiDraft('eng'),ENG);await originals(draft,ENG,[...mathWords,...canaries],'today original '+width);assert.match(await draft.innerText(),/已整理的学校原件/);assert.equal(await draft.locator('[data-school-material-record]').count(),0);
  await fits(page);await shot(page,'1-today-original-'+width,draft.locator('[data-school-draft-original]').first());
  // 2. Close and reopen.
  await closeOriginal();await fromToday(fx.tasks.eng,'message:synthetic:eng');await draft.locator('[data-school-draft-original]').first().waitFor();await originals(draft,ENG,[...mathWords,...canaries],'reopened original '+width);await closeOriginal();
  // 3. Feedback material of the same homework.
  await feedback(fx.tasks.eng);await resources.locator('[data-task-material-state="ready"] [data-school-draft-original]').first().waitFor();sameAsAPI(apiDraft('eng'),ENG);
  await originals(resources,ENG,[...mathWords,...canaries],'feedback material '+width);assert.match(await resources.innerText(),/不是孩子作答或已完成/);assert.match(await resources.innerText(),new RegExp('老师原件 · 2 份'));
  await fits(page);await shot(page,'3-feedback-material-'+width,resources.locator('[data-school-draft-original]').first());
  // 4. The teacher original from the feedback panel.
  await resources.getByRole('button',{name:'查看老师原消息'}).click();await dialog.locator('[data-task-material-state="ready"] [data-school-draft-original]').first().waitFor();
  await originals(dialog,ENG,[...mathWords,...canaries],'feedback original '+width);assert.equal(await dialog.locator('[data-print-upload],[data-school-original-upload],[data-school-original-attach]').count(),0);
  await fits(page);await shot(page,'4-feedback-original-'+width,dialog.locator('[data-school-draft-original]').last());await closeOriginal();await closeTask();
  // 5. Refresh and reopen both entries.
  await page.reload();await home();await feedback(fx.tasks.eng);await resources.locator('[data-task-material-state="ready"] [data-school-draft-original]').first().waitFor();await originals(resources,ENG,[...mathWords,...canaries],'refreshed feedback '+width);await closeTask();
  await fromToday(fx.tasks.eng,'message:synthetic:eng');await draft.locator('[data-school-draft-original]').first().waitFor();await originals(draft,ENG,[...mathWords,...canaries],'refreshed original '+width);await closeOriginal();
  // Another homework of the same child keeps only its own original.
  await fromToday(fx.tasks.math,'message:synthetic:math');await draft.locator('[data-school-draft-original]').first().waitFor();sameAsAPI(apiDraft('math'),MATH);await originals(draft,MATH,[...engWords,...canaries],'math original '+width);await closeOriginal();
  await feedback(fx.tasks.math);await resources.locator('[data-task-material-state="ready"] [data-school-draft-original]').first().waitFor();await originals(resources,MATH,[...engWords,...canaries],'math feedback '+width);await shot(page,'6-math-feedback-'+width,resources.locator('[data-school-draft-original]').first());await closeTask();
  // A school task without a saved original scope stays rejected; no whole-message material is shown in its place.
  await fromToday(fx.tasks.scope,'message:synthetic:scope');await until(async()=>/本项资料范围尚未核明/.test(await dialog.innerText()),'scoped task material rejected');
  assert.equal(await dialog.locator('[data-school-draft-original],[data-school-draft-requirement],[data-task-material-state]').count(),0);assert(!(await dialog.innerText()).includes('SCOPE_CANARY'),'rejected scope shows no fallback requirement');
  const scoped=responses.filter(x=>x.query.message_id==='scope'&&x.query.task_id===fx.tasks.scope).at(-1);assert.equal(scoped?.status,409,'backend rejects the unscoped task view');
  await fits(page);await shot(page,'7-scope-rejected-'+width);await closeOriginal();
  await feedback(fx.tasks.scope);await until(async()=>/本项资料范围尚未核明/.test(await resources.innerText()),'scoped feedback material rejected');
  assert.equal(await resources.locator('[data-school-draft-original],[data-school-draft-requirement],[data-task-material-state]').count(),0);assert(!(await resources.innerText()).includes('SCOPE_CANARY'));await closeTask();
  // The other child sees none of these tasks.
  const other=page.locator('[data-child-filter="child-2"]');if(await other.count()){await other.first().click();for(const id of Object.values(fx.tasks))assert.equal(await card(id).count(),0);const text=await page.locator('#content').innerText();for(const word of [...engWords,...mathWords])assert(!text.includes(word),'other child view excludes '+word)}
  assert.deepEqual(pageErrors,[]);assert.deepEqual(external,[]);
  record.widths.push({width,stages:['today-original','close-reopen','feedback-material','feedback-original','refresh-reopen'],isolation:['eng','math'],scope_rejected:true,api_views:responses.length});
  await page.close();lastPage=null;
 }
 const after=await state(),runtime=await(await fetch(url+'__fixture/proof')).json();
 assert.equal(facts(after),facts(before),'reading never changes task actions, completion or records');
 assert.deepEqual(runtime.posts,[],'no write request while reading');assert.equal(runtime.model_calls,0);assert.equal(runtime.print_attempts,0);
 Object.assign(record,{status:'passed',posts:runtime.posts,model_calls:runtime.model_calls,print_attempts:runtime.print_attempts,tasks:fx.tasks,uploads:fx.uploads});
 console.log('school material requirements: 360/1440 today/reopen/feedback/original/refresh, isolation and scope rejection passed (synthetic only)');
}catch(error){record.status='failed';record.error=error.message;if(lastPage&&proofDir)await lastPage.screenshot({path:path.join(proofDir,'failure.png'),fullPage:true}).catch(()=>{});throw error}
finally{if(proofDir)await fs.writeFile(path.join(proofDir,'proof.json'),JSON.stringify(record,null,2)).catch(()=>{});if(browser)await browser.close();if(proc){proc.kill('SIGINT');await Promise.race([once(proc,'exit'),delay(2000)]);if(proc.exitCode===null)proc.kill('SIGKILL')}}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
