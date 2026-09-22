// Synthetic browser + real local API checks for the PDF page-group panel in the school original dialog; no real family, CLI or model calls.
// The backend fixture links real synthetic 11-page PDFs and runs family_pdf_material.prepare with a stand-in model (and poppler stand-in when absent).
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check,label){for(let i=0;i<200;i++){if(await check())return;await delay(50)}throw Error(label)}
async function fits(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no document overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(items=>items.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
 assert.equal(await page.locator('#schoolOriginalDialog button:visible').evaluateAll(items=>items.some(b=>b.getBoundingClientRect().height<40)),false,'dialog actions are usable touch targets');
}
async function proof(page,name){if(process.env.AGENT_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.AGENT_UI_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.AGENT_UI_PROOF_DIR,name+'.png')})}}
const fixture=String.raw`
import tempfile,os,json,datetime,io,struct,zlib,base64,contextlib,hashlib
from pathlib import Path
from unittest.mock import patch
with tempfile.TemporaryDirectory(prefix='synthetic-pdf-ui-') as tmp:
 os.environ['FAMILY_DATA']=tmp
 os.environ['FAMILY_HOST']='family.test';os.environ['FAMILY_USER']='synthetic-parent'
 import app,family_agent,family_llm,family_pdf,family_pdf_material,family_qq_capture,test_pdf
 app.DATA=Path(tmp).resolve();app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 (app.DATA/'agent.json').write_text(json.dumps({'enabled':True,'sources':[{'id':'synthetic','platform':'wechat','child_id':'child-1','name':'虚构班级通知','cursor':'','enabled':True},{'id':'qq:123456','platform':'qq','child_id':'child-1','name':'虚构QQ资料群','cursor':'','enabled':True}]}))
 store=app.agent_store();now=datetime.datetime.now(family_agent.TZ)
 def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 pixels=b''.join(b'\x00'+bytes([30+(row%2)*40,120,220,255])*96 for row in range(64))
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',96,64,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
 app.save_upload(io.BytesIO(png),len(png),'synthetic-existing.png')
 PDF=test_pdf.build_pdf(11);(app.DATA/'uploads').mkdir(exist_ok=True)
 def renderer():
  if test_pdf.TOOLS_AVAILABLE: return contextlib.nullcontext()
  stack=contextlib.ExitStack();stack.enter_context(patch.object(family_pdf.shutil,'which',lambda name:'/synthetic/'+name));stack.enter_context(patch.object(family_pdf,'_run',test_pdf.fake_run_factory(page_count=11)));return stack
 def model(text,images,**kw):
  pages=json.loads(text)['original_pdf']['pages']
  return dict(title='虚构页组 '+'-'.join(str(p) for p in pages),note='题目与参考答案为老师材料，未见孩子作答。<img src=x onerror=alert(1)>',uncertainties=['发送日期未知 <b>'])
 step=[0]
 def rounds(n,fail=False):
  for _ in range(n):
   step[0]+=1
   with renderer(),patch.object(family_llm,'extract_draft',**({'side_effect':family_llm.LLMDraftError('合成模型超时')} if fail else {'side_effect':model})):
    assert family_pdf_material.prepare(store,now+datetime.timedelta(minutes=step[0]))==dict(used=1,failed=int(fail)),'pdf round'
 for width in (360,1440):
  for kind,done,failed in (('ready',4,False),('error',1,True),('unknown',0,False)):
   text='截图本机文字识别（可能有误，请对照原图）：\n虚构学校PDF资料 '+kind+' '+str(width)+'：附练习卷。'
   reply=family_qq_capture.save_fragment(store,dict(source_id='qq:123456',child_id='child-1',captured_at=now.isoformat(),text=text,png=base64.b64encode(png).decode()))
   ident=reply['message_id'];ref='message:qq:123456:'+ident
   store._save('pdf:'+kind+':'+str(width),'fixture',[dict(child_id='child-1',kind='school',title='虚构PDF资料 '+kind+' '+str(width),body='核对原要求',evidence=[dict(ref=ref,text=text)])],now)
   upload_id=hashlib.md5((kind+str(width)).encode()).hexdigest();(app.DATA/'uploads'/upload_id).write_bytes(PDF)
   with store._db() as c: c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',(upload_id,'虚构练习卷-'+kind+'-'+str(width)+'.pdf',len(PDF),'application/pdf',now.isoformat()))
   store.message_attachment(dict(child_id='child-1',source_id='qq:123456',message_id=ident,attachment_id=upload_id,action='attach'),dict)
   rounds(done)
   if failed: rounds(1,True)
 store.ingest(dict(source_id='synthetic',expected_cursor='',cursor='cursor-1',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[dict(id='notice-'+str(w),time=now.isoformat(),kind='text',sender='虚构老师',text='虚构老师通知 '+str(w)+'：请核对所附练习卷。',unread=True) for w in (360,1440)]))
 for w in (360,1440): store._save('notice-'+str(w),'fixture',[dict(child_id='child-1',kind='school',title='虚构文字通知 '+str(w),body='核对原要求',evidence=[dict(ref='message:synthetic:notice-'+str(w),text='虚构老师通知 '+str(w)+'：请核对所附练习卷。')])],now)
 store._runtime('ready',now)
 app.prepare_assets()
 server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_AGENT_PORT'])),app.Handler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
`;
(async()=>{let proc,browser;try{
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));const url='http://127.0.0.1:'+port+'/',origin='http://family.test:'+port+'/',env={...process.env,TEST_AGENT_PORT:String(port)};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let errors='';proc.stderr.on('data',b=>{errors+=b});proc.on('error',e=>errors+=e.message);
 await until(async()=>{if(proc.exitCode!==null)throw Error(errors);try{return(await fetch(url)).ok}catch{return false}},'server startup');const state=async()=>await(await fetch(url+'api/state')).json();
 const readView=async identity=>await(await fetch(url+'api/agent/message?'+new URLSearchParams(identity))).json();
 browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP family.test 127.0.0.1'],...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
 for(const width of [360,1440]){
  const page=await browser.newPage({viewport:{width,height:820},extraHTTPHeaders:{'Tailscale-User-Login':'synthetic-parent'}}),pageErrors=[],alerts=[];page.on('pageerror',e=>pageErrors.push(e.message));page.on('dialog',async d=>{alerts.push(d.message());await d.dismiss()});
  await page.goto(origin);await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  const before=await state(),facts=s=>JSON.stringify([s.tasks,s.records,s.agent.items.map(x=>[x.id,x.state])]),factsBefore=facts(before);
  const item=kind=>before.agent.items.find(x=>x.title==='虚构PDF资料 '+kind+' '+width),ref=kind=>item(kind).evidence[0].ref,identity=kind=>({child_id:'child-1',source_id:'qq:123456',message_id:ref(kind).slice('message:qq:123456:'.length)});
  const existing=before.uploads.find(x=>x.name==='synthetic-existing.png');
  const dialog=page.locator('#schoolOriginalDialog'),panel=dialog.locator('[data-school-pdf-material]'),batches=dialog.locator('[data-school-pdf-batch]'),refresh=dialog.locator('[data-school-pdf-refresh]'),retry=dialog.locator('[data-school-pdf-retry]');
  const open=async ref=>{await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('[data-agent-item] [data-school-original-ref="'+ref+'"]').first().click();await dialog.locator('[data-school-original-files]').waitFor()};
  const close=async()=>{await dialog.locator('[data-school-original-close]').click();await until(async()=>!(await dialog.isVisible()),'dialog closed')};
  const isMessage=u=>u.pathname==='/api/agent/message';
  // Routed replies that still need the real server go through node, so the family.test host is rewritten the way test_message_page_ui.cjs does.
  const real=route=>route.fetch({url:route.request().url().replace('family.test','127.0.0.1'),headers:{...route.request().headers(),host:'family.test:'+port}});
  const linked=async kind=>{const v=await readView(identity(kind)),pdf=v.pdf_material?.upload_id||null,ids=v.attachments.map(a=>a.id);return{pdf,screenshot:ids.find(id=>id!==pdf)||null,ids:[...ids].sort()}};
  const detachIDs=async()=>(await dialog.locator('[data-school-original-detach]').evaluateAll(items=>items.map(b=>b.dataset.schoolOriginalDetach))).sort();
  await page.route('**/api/parent/login',async route=>{assert.deepEqual(route.request().postDataJSON(),{username:'synthetic-parent',password:'synthetic-password'});await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})})});
  const login=async()=>{await page.locator('#parentLoginDialog[open]').waitFor();await page.locator('#parentLoginForm [name=username]').fill('synthetic-parent');await page.locator('#parentLoginForm [name=password]').fill('synthetic-password');await page.locator('#parentLoginSubmit').click();await page.locator('#parentLoginDialog').waitFor({state:'hidden'})};
  // 1. Linked PDF whose total is still unknown: no page count is implied, the old "PDF unsupported" note is not shown beside it.
  await open(ref('unknown'));await panel.waitFor();let text=await panel.innerText();
  assert.match(text,/总页数尚未核对/);assert.doesNotMatch(text,/全部 \d+ 页已整理/);assert.doesNotMatch(text,/未读页/);assert.equal(await batches.count(),0);
  assert.doesNotMatch(await dialog.innerText(),/尚不支持自动整理/,'old PDF-unsupported note is hidden when pdf_material is present');
  assert.equal(await dialog.locator('[data-school-material-record],[data-school-material-draft],[data-school-material-status]').count(),0);
  assert.equal(await retry.count(),0);const unknownLinks=await linked('unknown');assert.equal(typeof unknownLinks.pdf,'string');assert.equal(typeof unknownLinks.screenshot,'string','the fragment screenshot is linked beside the PDF');assert.equal(unknownLinks.ids.length,2);assert.deepEqual(await detachIDs(),unknownLinks.ids,'PDF original and the fragment screenshot both stay linked and removable');
  await fits(page);await proof(page,'school-pdf-unknown-'+width);await close();
  // 2. 11 pages with pages 1-3 saved and a failed later batch: processed and unread pages are explicit, drafts are escaped.
  await open(ref('error'));await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'error');
  assert.match(text,/已整理 3 \/ 11 页/);assert.match(text,/未读页：4、5、6、7、8、9、10、11（共 8 页）/);assert.match(text,/暂未成功/);assert.match(text,/虚构练习卷-error-\d+\.pdf/);
  assert.equal(await batches.count(),1);assert.match(await batches.first().innerText(),/第 1、2、3 页[\s\S]*虚构页组 1-2-3[\s\S]*未见孩子作答。<img src=x onerror=alert\(1\)>[\s\S]*待核对：发送日期未知 <b>/);
  assert.equal(await dialog.locator('[data-school-pdf-batch] img,[data-school-pdf-batch] b').count(),0,'draft text is escaped');assert.equal(alerts.length,0);
  assert.equal(await dialog.locator('[data-school-material-record]').count(),0,'typed PDF drafts never offer a learning record');
  await fits(page);await proof(page,'school-pdf-error-'+width);
  // Retry: a failed attempt keeps the groups and can be retried; a double click queues exactly one retry; nothing is rendered or modelled.
  const actionCalls=[];await page.route('**/api/agent/action',async route=>{actionCalls.push(route.request().postDataJSON());if(actionCalls.length===1)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构重试暂时失败'})});await delay(300);await route.continue()});
  await retry.click();await until(async()=>/虚构重试暂时失败/.test(await panel.innerText()),'failed retry reported');
  assert.equal(await batches.count(),1,'failed retry keeps processed groups');assert.equal(await retry.isEnabled(),true,'retry stays available after failure');
  await retry.dispatchEvent('click');await retry.dispatchEvent('click');
  await until(async()=>/已安排后台重试/.test(await panel.innerText()),'retry queued');assert.equal(actionCalls.length,2,'double click sends one retry');
  assert.deepEqual(actionCalls[1],{action:'retry',id:(await readView(identity('error'))).pdf_material.job_id});assert.equal(await batches.count(),1);
  await page.unroute('**/api/agent/action');
  await refresh.click();await until(async()=>/独立Agent将按每轮最多3页/.test(await panel.innerText()),'refresh reads the queued state');
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'pending');assert.equal(await retry.count(),0);assert.equal(await batches.count(),1);assert.match(await panel.innerText(),/已整理 3 \/ 11 页/);
  assert.equal((await readView(identity('error'))).pdf_material.processed_pages.join(','),'1,2,3','queueing a retry does not process pages');
  // Network failure and 401 keep the shown progress and the original selection.
  await dialog.locator('[name="attachment_id"]').selectOption(existing.id);
  const dropped=route=>route.abort('connectionreset');await page.route(isMessage,dropped);
  await refresh.click();await until(async()=>/已显示的进度和填写内容保留/.test(await panel.innerText()),'network failure reported');
  assert.equal(await batches.count(),1);assert.match(await panel.innerText(),/已整理 3 \/ 11 页/);assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),existing.id,'selection survives a failed refresh');
  await page.unroute(isMessage,dropped);
  const denied=route=>route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:'请先登录'})});await page.route(isMessage,denied);
  await refresh.click();await until(async()=>/请先重新登录/.test(await panel.innerText()),'401 reported');
  assert.equal(await batches.count(),1,'401 keeps shown progress');assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),existing.id);
  await page.unroute(isMessage,denied);await login();
  await refresh.click();await until(async()=>/已读取最新进度/.test(await panel.innerText()),'refresh recovers');assert.equal(await batches.count(),1);
  // A late reply never lands in another dialog: the dialog stays open while a read is in flight, and reopening starts clean.
  const slow=async route=>{await delay(400);await route.continue()};await page.route(isMessage,slow);
  await refresh.click();assert.equal(await dialog.locator('[data-school-original-close]').isDisabled(),true);await page.keyboard.press('Escape');assert.equal(await dialog.isVisible(),true,'busy dialog cannot be closed');
  await until(async()=>/已读取最新进度/.test(await panel.innerText()),'slow reply lands in the same dialog');await page.unroute(isMessage,slow);
  // A reply held for a dialog that was force-closed is dropped: the notice opened meanwhile stays exactly as it was (pattern from test_message_page_ui.cjs).
  let release;const held=new Promise(r=>release=r);await page.route(isMessage,async route=>{await held;await route.continue()},{times:1});
  await refresh.click();await until(async()=>/正在读取最新进度/.test(await panel.innerText()),'refresh held');
  await page.evaluate(()=>document.querySelector('#schoolOriginalDialog').close());
  await open(ref('unknown'));await panel.waitFor();const unknownText=await dialog.innerText();assert.equal(await batches.count(),0);
  release();await delay(500);
  assert.equal(await dialog.innerText(),unknownText,'late reply for the force-closed notice never lands in the current dialog');assert.equal(await batches.count(),0,'error groups never leak into the unknown notice');assert.equal(await dialog.locator('[data-school-original-close]').isEnabled(),true);
  await close();await open(ref('unknown'));await panel.waitFor();assert.doesNotMatch(await panel.innerText(),/已读取最新进度|已安排后台重试/,'reopened dialog carries no old notice');assert.equal(await batches.count(),0);await close();
  // 3. Complete 11 pages: four groups, completeness only from the backend, still there after reload.
  await open(ref('ready'));await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'ready');assert.match(text,/全部 11 页已整理/);assert.doesNotMatch(text,/未读页|暂未成功/);assert.equal(await batches.count(),4);assert.equal(await retry.count(),0);
  assert.match(await batches.nth(3).innerText(),/第 10、11 页[\s\S]*虚构页组 10-11/);await fits(page);await proof(page,'school-pdf-ready-'+width);await close();
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await open(ref('ready'));await panel.waitFor();assert.equal(await batches.count(),4);assert.match(await panel.innerText(),/全部 11 页已整理/);
  // Withdrawn authorization (fictional GET reply) hides the old groups; a real re-read restores them; detaching the PDF removes the panel.
  const withdrawn=async route=>{const body=await(await real(route)).json();body.pdf_material={state:'unavailable',kind:'school_material',explanation:'虚构撤权说明 <img src=x onerror=alert(1)>'};await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})};
  await page.route(isMessage,withdrawn);await refresh.click();await until(async()=>/虚构撤权说明/.test(await panel.innerText()),'unavailable state shown');
  assert.equal(await batches.count(),0,'old groups are cleared on unavailable');assert.equal(await retry.count(),0);assert.equal(await panel.locator('img').count(),0);const readyLinks=await linked('ready');assert.equal(readyLinks.ids.length,2,'fragment screenshot and PDF are both linked');assert.deepEqual(await detachIDs(),readyLinks.ids,'both originals stay listed');
  await page.unroute(isMessage,withdrawn);await refresh.click();await until(async()=>await batches.count()===4,'real re-read restores groups');
  const readyUpload=readyLinks.pdf;assert.equal((await readView(identity('ready'))).pdf_material.upload_id,readyUpload);
  await dialog.locator('[data-school-original-detach="'+readyUpload+'"]').click();await until(async()=>await panel.count()===0,'detached PDF removes the panel');
  assert.equal((await readView(identity('ready'))).pdf_material,null);assert.deepEqual(await detachIDs(),[readyLinks.screenshot],'the fragment screenshot stays linked after the PDF is detached');assert.deepEqual((await readView(identity('ready'))).attachments.map(a=>a.id),[readyLinks.screenshot]);assert.doesNotMatch(await dialog.innerText(),/还没有关联原件/,'one original remains, so the empty note is not shown');
  await dialog.locator('[name="attachment_id"]').selectOption(readyUpload);await dialog.locator('[data-school-original-attach]').click();await until(async()=>await batches.count()===4,'re-linked PDF continues from saved groups');assert.deepEqual(await detachIDs(),readyLinks.ids,'both originals are linked again');await close();
  // 4. Text notice without a PDF: a real open shows no panel. A fictional reply installed before the next open carries a pending PDF plus a stale ready untyped draft: the PDF panel shows escaped name/title and the old draft (with its learning-record entry) is suppressed entirely. The teacher draft survives refresh, 401, login recovery and the real null reply that hides the panel.
  const notice=before.agent.items.find(x=>x.title==='虚构文字通知 '+width);await open(notice.evidence[0].ref);assert.equal(await panel.count(),0);await close();
  const staleDraft={state:'ready',draft:{title:'虚构旧图片草稿 <b>',subject:'语文',score:null,total:null,note:'虚构旧说明',uncertainties:[]},explanation:''};
  const fictionalPDF={state:'pending',kind:'school_material',upload_id:'x',name:'虚构<练习卷>.pdf',job_id:'pdf:fictional',page_count:11,processed_pages:[1,2,3],pending_pages:[4,5,6,7,8,9,10,11],complete:false,batches:[{pages:[1,2,3],draft:{title:'虚构<标题>',note:'虚构说明',uncertainties:[]},updated:'2026-01-01T00:00:00+08:00'}],explanation:'虚构等待说明'};
  const fictional=async route=>{const body=await(await real(route)).json();body.material_draft=staleDraft;body.pdf_material=fictionalPDF;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})};
  const generic=async route=>{const body=await(await real(route)).json();body.material_draft=staleDraft;body.pdf_material=null;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})};
  await page.route('**/api/teachers',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({teachers:[{id:'synthetic-teacher',display_name:'虚构老师',subject:'语文',child_ids:['child-1'],source_ids:['synthetic'],archived:false}]})}));
  await page.route(isMessage,fictional);await open(notice.evidence[0].ref);await panel.waitFor();
  assert.match(await panel.innerText(),/虚构等待说明/);assert.match(await panel.innerText(),/虚构<练习卷>\.pdf[\s\S]*已整理 3 \/ 11 页[\s\S]*虚构<标题>/);assert.equal(await panel.locator('img,b').count(),0);
  assert.equal(await dialog.locator('[data-school-material-draft],[data-school-material-record],[data-school-material-status]').count(),0,'a stale ready untyped draft is suppressed entirely while pdf_material is present');assert.doesNotMatch(await dialog.innerText(),/虚构旧图片草稿|核对并填入学习记录/,'no learning-record consumer beside a typed PDF');
  await dialog.locator('[data-school-teacher-open]').click();const teacherForm=dialog.locator('[data-school-teacher-form]');await teacherForm.waitFor();
  await teacherForm.locator('[name="teacher_id"]').selectOption('synthetic-teacher');await teacherForm.locator('[name="target"]').selectOption('class');await teacherForm.locator('[name="quote"]').fill('家长尚未保存的老师要求草稿');
  const teacherFields=await teacherForm.evaluate(f=>Object.fromEntries(new FormData(f))),teacherNow=async()=>await teacherForm.evaluate(f=>Object.fromEntries(new FormData(f)));assert.equal(teacherFields.quote,'家长尚未保存的老师要求草稿');
  await refresh.click();await until(async()=>/已读取最新进度/.test(await panel.innerText()),'fictional refresh');assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives a refresh');
  await page.unroute(isMessage,fictional);await page.route(isMessage,denied);await refresh.click();await until(async()=>/请先重新登录/.test(await panel.innerText()),'401 on the text notice');
  assert.equal(await panel.count(),1,'401 keeps the shown PDF panel');assert.equal(await dialog.locator('[data-school-material-record]').count(),0);assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives 401');
  await page.unroute(isMessage,denied);await login();assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives the login recovery');
  await refresh.click();await until(async()=>await panel.count()===0,'real null reply hides the panel');
  assert.match(await dialog.locator('[data-school-original-status]').innerText(),/没有可整理的PDF原件/);assert.equal(await dialog.locator('[data-school-material-draft],[data-school-material-record]').count(),0,'the fictional stale draft leaves with the real reply');assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives the real null refresh');await close();
  // Without a PDF the same generic ready draft still shows with its learning-record entry, so the guard only applies while pdf_material is present.
  await page.route(isMessage,generic);await open(notice.evidence[0].ref);assert.equal(await panel.count(),0);
  await until(async()=>await dialog.locator('[data-school-material-draft]').count()===1,'generic draft shows without a PDF');assert.equal(await dialog.locator('[data-school-material-record]').count(),1);assert.equal(await dialog.locator('[data-school-material-draft] b').count(),0,'generic draft is escaped');assert.match(await dialog.innerText(),/虚构旧图片草稿 <b>/);
  await page.unroute(isMessage,generic);await close();
  assert.equal(facts(await state()),factsBefore,'no task, record or item changed');assert.deepEqual(pageErrors,[]);assert.deepEqual(alerts,[]);
  await page.close();
 }
 console.log('pdf material ui checks passed');
}finally{if(browser)await browser.close();if(proc&&proc.exitCode===null)proc.kill('SIGINT')}})().catch(e=>{console.error(e);process.exit(1)});
