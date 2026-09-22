// Synthetic 360/1440 browser check for the read-only page fragment in the 原通知与原件 dialog: real local API,
// fake page fetch, no family data, model, message CLI or network. Addresses are followed by ASCII . ; " and a comma after an
// internal .html so the trimmed address (same rule as the server's _page_link) is what gets offered and requested. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON and PAGE_UI_PROOF_DIR. Run: node test_message_page_ui.cjs
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check,label){for(let i=0;i<200;i++){if(await check())return;await delay(50)}throw Error(label)}
async function fits(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no document overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(items=>items.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
 assert.equal(await page.locator('[data-school-page-read]:visible').evaluateAll(items=>items.some(b=>b.getBoundingClientRect().height<40)),false,'page read buttons are usable touch targets');
}
async function proof(page,name){if(process.env.PAGE_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.PAGE_UI_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.PAGE_UI_PROOF_DIR,name+'.png'),fullPage:true})}}
const LONG_TAIL='a'.repeat(600);
const fixture=String.raw`
import tempfile,os,json,datetime,io,struct,zlib
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='synthetic-page-ui-') as tmp:
 os.environ['FAMILY_DATA']=tmp
 os.environ['FAMILY_HOST']='family.test';os.environ['FAMILY_USER']='synthetic-parent'
 import app,family_agent,family_teacher_public
 app.DATA=Path(tmp).resolve();app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 (app.DATA/'agent.json').write_text(json.dumps({'enabled':True,'sources':[{'id':'synthetic','platform':'wechat','child_id':'child-1','name':'虚构链接通知群','cursor':'','enabled':True}]}))
 store=app.agent_store();now=datetime.datetime.now(family_agent.TZ);today=now.date().isoformat()
 calls=[]
 def fake_fetch(url,*args,**kwargs):
  calls.append(url)
  if '/flaky/' in url and calls.count(url)==1: raise OSError('synthetic first failure')
  text='虚构公开页面正文 第%d次抓取 <b>不是HTML</b> <img src=x onerror=alert(1)>\n第二行 & 转义 %s'%(calls.count(url),url)
  if '/n/' in url: text+='\n'+'长'*300
  return dict(url=url,text=text,text_truncated='/n/' in url,content_type='text/html',fetched_at=now.isoformat())
 family_teacher_public.fetch_page=fake_fetch
 def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 pixels=b''.join(b'\x00'+bytes([30+(row%2)*40,120,220,255])*96 for row in range(64))
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',96,64,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
 attached=app.save_upload(io.BytesIO(png),len(png),'synthetic-attached.png');spare=app.save_upload(io.BytesIO(png),len(png),'synthetic-spare.png')
 messages=[]
 for width in (360,1440):
  base='https://school.example.invalid/'
  texts={'link':'各位家长，请查看 '+base+'notice/'+str(width)+'.html, 另见 http://plain.example.invalid/x/'+str(width)+' 和 '+base+'n/'+str(width)+'/'+'a'*600+' 谢谢。<img src=x onerror=alert(1)>',
   'other':'虚构第二条通知 '+str(width)+'：'+base+'other/'+str(width)+'.',
   'flaky':'虚构重试通知 '+str(width)+'：'+base+'flaky/'+str(width)+';',
   'iso':'虚构隔离通知 '+str(width)+'："'+base+'iso/'+str(width)+'"'}
  for key,text in texts.items(): messages.append(dict(id=key+':'+str(width),time=now.isoformat(),kind='text',sender='虚构老师',text=text,unread=True))
 store.ingest(dict(source_id='synthetic',expected_cursor='',cursor='cursor-1',checked_at=now.isoformat(),last_message_time=now.isoformat(),messages=messages,error=''))
 for m in messages:
  key,width=m['id'].split(':')
  store._save('school:'+m['id'],'fixture',[dict(child_id='child-1',kind='school',title='虚构'+key+'通知 '+width,body='请核对通知里的网址。',due=today,evidence=[{'ref':'message:synthetic:'+m['id'],'text':m['text']}])],now)
  if key=='other': store.message_attachment(dict(child_id='child-1',source_id='synthetic',message_id=m['id'],attachment_id=attached['id'],action='attach'),dict)
 store._runtime('ready',now)
 app.prepare_assets()
 server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_AGENT_PORT'])),app.Handler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
`;
(async()=>{let proc,browser;try{
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));const url='http://127.0.0.1:'+port+'/',env={...process.env,TEST_AGENT_PORT:String(port)};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let errors='';proc.stderr.on('data',b=>{errors+=b});proc.on('error',e=>errors+=e.message);
 await until(async()=>{if(proc.exitCode!==null)throw Error(errors);try{return(await fetch(url)).ok}catch{return false}},'server startup');
 const state=async()=>await(await fetch(url+'api/state')).json();
 browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP family.test 127.0.0.1'],...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
 for(const width of [360,1440]){
  const page=await browser.newPage({viewport:{width,height:820},extraHTTPHeaders:{'Tailscale-User-Login':'synthetic-parent'}}),pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
  const posts=[];page.on('request',r=>{if(r.url().includes('/api/agent/message/page')&&r.method()==='POST')posts.push(r.postDataJSON())});
  await page.goto('http://family.test:'+port+'/');await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  const st=await state(),items=Object.fromEntries(['link','other','flaky','iso'].map(k=>[k,st.agent.items.find(x=>x.title==='虚构'+k+'通知 '+width)]));
  for(const k of Object.keys(items))assert(items[k],'fixture item '+k);
  const attached=st.uploads.find(x=>x.name==='synthetic-attached.png'),spare=st.uploads.find(x=>x.name==='synthetic-spare.png');assert(attached&&spare,'fixture uploads');
  const base='https://school.example.invalid/',LINK=base+'notice/'+width+'.html',LONG=base+'n/'+width+'/'+LONG_TAIL,OTHER=base+'other/'+width,FLAKY=base+'flaky/'+width,ISO=base+'iso/'+width,HTTP='http://plain.example.invalid/x/'+width;
  const dialog=page.locator('#schoolOriginalDialog'),readButton=u=>dialog.locator('[data-school-page-read="'+u+'"]'),row=u=>dialog.locator('[data-school-page="'+u+'"]'),rowText=u=>row(u).locator('[data-school-page-text]').innerText();
  const pageReply=()=>page.waitForResponse(r=>r.url().includes('/api/agent/message/page')&&r.request().method()==='POST');
  const open=async key=>{const ref=items[key].evidence[0].ref;await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();const got=page.waitForResponse(r=>r.url().includes('/api/agent/message?')&&r.request().method()==='GET');await page.locator('[data-agent-item] [data-school-original-ref="'+ref+'"]').first().click();await got;await dialog.locator('[data-school-original-close]:enabled').waitFor()};
  const close=async()=>{await dialog.locator('[data-school-original-close]').click();await until(async()=>!(await page.locator('#schoolOriginalDialog[open]').count()),'dialog closed')};
  // 1. Opening the notice lists the complete addresses, sends no page read and keeps everything as text.
  await open('link');
  assert.equal(posts.length,0,'opening the notice sends no page read');
  assert.match(await dialog.innerText(),/各位家长，请查看/);
  assert.equal(await dialog.locator('img,b').count(),0,'message text is escaped, not rendered');
  assert.match(await dialog.locator('blockquote.source').first().innerText(),/<img src=x onerror=alert\(1\)>/);
  assert.equal(await dialog.locator('[data-school-page-read]').count(),2,'only the two complete https addresses get a read button');
  assert.equal(await readButton(LONG).count(),1,'the full long address is offered, never a 500-character cut');
  assert.equal(await readButton(LINK).count(),1,'the dot inside the address is kept while the trailing comma is not part of it');
  assert.equal(await dialog.locator('[data-school-page="'+LINK+',"]').count(),0,'trailing ASCII punctuation is never offered as part of the address');
  assert.equal(await readButton(HTTP).count(),0,'http stays as original text');assert.match(await row(HTTP).innerText(),/未读取，保持原文/);
  assert.equal(await dialog.locator('[data-school-page-text]').count(),0,'nothing is shown as read before a click');
  await fits(page);await proof(page,'page-links-'+width);
  // 2. One click on the long address reads it once; the fragment shows time, truncation and escaped HTML.
  let reply=pageReply();await readButton(LONG).click();let body=await(await reply).json();
  assert.deepEqual(posts.at(-1),{child_id:'child-1',source_id:'synthetic',message_id:'link:'+width,url:LONG},'exact identity and the untruncated url');
  assert.equal(body.cached,false);assert.equal(body.page.text_truncated,true);assert.equal(body.page.original_url,LONG);
  await row(LONG).locator('[data-school-page-text]').waitFor();
  let text=await rowText(LONG);assert.match(text,/第1次抓取/);assert.match(text,/<b>不是HTML<\/b>/);assert.match(text,/第二行 & 转义/);
  assert.equal(await dialog.locator('img,b').count(),0,'remote html is never inserted');
  const meta=await row(LONG).locator('[data-school-page-meta]').innerText();assert.match(meta,/读取于 \d/);assert.match(meta,/超过6000字/);
  assert.match(await row(LONG).innerText(),/已读取网页片段/);
  assert.equal(await readButton(LONG).count(),0,'no refresh once cached');assert.equal(await dialog.locator('[data-school-original-close]:enabled').count(),1);
  await fits(page);await proof(page,'page-long-'+width);
  // 3. Repeated clicks during one pending read send exactly one request.
  reply=pageReply();
  await dialog.evaluate((d,sel)=>{d.querySelector(sel).click();d.querySelector(sel)?.click();d.querySelector(sel)?.click()},'[data-school-page-read="'+LINK+'"]');
  body=await(await reply).json();await delay(250);
  assert.equal(posts.filter(p=>p.url===LINK).length,1,'a pending read is not sent twice');assert.equal(body.cached,false);
  await row(LINK).locator('[data-school-page-text]').waitFor();assert.match(await rowText(LINK),/第1次抓取/);
  // 4. Close, reopen and reload: the saved fragments come back through GET only.
  const postsBefore=posts.length;await close();await open('link');
  assert.equal(posts.length,postsBefore,'reopening reads the cache through GET only');
  assert.match(await rowText(LONG),/第1次抓取/);assert.match(await rowText(LINK),/第1次抓取/);assert.equal(await dialog.locator('[data-school-page-read]').count(),0);
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await open('link');
  assert.match(await rowText(LINK),/第1次抓取/);assert.equal(posts.length,postsBefore);await close();
  // 5. 401 opens the login dialog and keeps the retry for the same address; a lost reply is retried and served from the cache.
  await open('other');
  assert.equal(await readButton(OTHER).count(),1,'trailing period dropped from the address');assert.equal(await row(OTHER+'.').count(),0,'address with its trailing period is never offered');
  assert.equal(await dialog.locator('[data-school-original-detach="'+attached.id+'"]').count(),1,'attached original present');
  await dialog.locator('[name="attachment_id"]').selectOption(spare.id);
  await page.route('**/api/teachers',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({teachers:[{id:'synthetic-teacher',display_name:'虚构老师',subject:'语文',child_ids:['child-1'],source_ids:['synthetic'],archived:false}]})}));
  await dialog.locator('[data-school-teacher-open]').click();
  const teacherForm=dialog.locator('[data-school-teacher-form]');await teacherForm.waitFor();
  await teacherForm.locator('[name="teacher_id"]').selectOption('synthetic-teacher');
  await teacherForm.locator('[name="target"]').selectOption('class');
  await teacherForm.locator('[name="quote"]').fill('家长尚未保存的老师要求草稿');
  const teacherFields=await teacherForm.evaluate(f=>Object.fromEntries(new FormData(f)));

  await page.route('**/api/agent/message/page',route=>route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:'请先登录家长账号'})}),{times:1});
  await readButton(OTHER).click();await page.locator('#parentLoginDialog[open]').waitFor();
  await until(async()=>(await readButton(OTHER).count())===1&&/重试读取这个网址/.test(await readButton(OTHER).innerText()),'retry for the same address after 401');
  assert.match(await row(OTHER).innerText(),/请先登录家长账号.*保留/);
  assert.equal(await dialog.locator('[data-school-original-detach="'+attached.id+'"]').count(),1,'attached original stays after 401');
  assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),spare.id,'unsaved selection stays after 401');
  await page.route('**/api/parent/login',async route=>{
   assert.deepEqual(route.request().postDataJSON(),{username:'synthetic-parent',password:'synthetic-password'});
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})});
  },{times:1});
  await page.locator('#parentLoginForm [name=username]').fill('synthetic-parent');
  await page.locator('#parentLoginForm [name=password]').fill('synthetic-password');
  await page.locator('#parentLoginSubmit').click();
  await page.locator('#parentLoginDialog').waitFor({state:'hidden'});
  assert.deepEqual(await teacherForm.evaluate(f=>Object.fromEntries(new FormData(f))),teacherFields,'login form recovery preserves teacher draft');
  await page.route('**/api/agent/message/page',async route=>{await route.fetch({url:route.request().url().replace('family.test','127.0.0.1'),headers:{...route.request().headers(),host:'family.test:'+port}});await route.abort('connectionreset')},{times:1});
  await readButton(OTHER).click();
  await until(async()=>/重试读取这个网址/.test(await row(OTHER).innerText()),'retry after a lost reply');
  assert.equal(await dialog.locator('[data-school-page-text]').count(),0,'a lost reply shows nothing as read');
  reply=pageReply();await readButton(OTHER).click();body=await(await reply).json();
  assert.equal(body.cached,true,'the lost reply was saved server-side; the retry hits the cache without a second fetch');
  await row(OTHER).locator('[data-school-page-text]').waitFor();assert.match(await rowText(OTHER),/第1次抓取/);assert.match(await row(OTHER).innerText(),/之前保存的网页片段/);
  assert.equal(posts.filter(p=>p.url===OTHER).length,3);assert.equal(posts.some(p=>/[.;"]$/.test(p.url)),false,'no request ever carries trailing punctuation');
  assert.equal(await dialog.locator('[data-school-original-detach="'+attached.id+'"]').count(),1,'attached original stays after reading');
  assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),spare.id,'unsaved selection stays after reading');
  assert.deepEqual(await teacherForm.evaluate(f=>Object.fromEntries(new FormData(f))),teacherFields,'teacher draft survives 401, lost receipt and successful page retry');
  await fits(page);await proof(page,'page-other-'+width);await close();
  // 6. A server-side fetch failure keeps the notice and allows a retry of the same address.
  await open('flaky');
  assert.equal(await readButton(FLAKY).count(),1,'trailing semicolon dropped from the address');
  reply=pageReply();await readButton(FLAKY).click();assert.equal((await reply).status(),502);
  await until(async()=>/重试读取这个网址/.test(await row(FLAKY).innerText()),'server failure keeps retry');
  assert.match(await row(FLAKY).innerText(),/网页暂未读取成功/);assert.equal(await dialog.locator('[data-school-page-text]').count(),0);
  reply=pageReply();await readButton(FLAKY).click();body=await(await reply).json();assert.equal(body.cached,false);
  await row(FLAKY).locator('[data-school-page-text]').waitFor();assert.match(await rowText(FLAKY),/第2次抓取/);await close();
  // 7. A late reply for one notice never lands in another notice's panel; the saved fragment is still there on reopen.
  await open('iso');
  assert.equal(await readButton(ISO).count(),1,'closing ASCII quote dropped from the address');
  let release;const held=new Promise(r=>release=r);
  await page.route('**/api/agent/message/page',async route=>{await held;await route.continue()},{times:1});
  await readButton(ISO).click();await until(async()=>(await readButton(ISO).count())===0||await readButton(ISO).isDisabled(),'read pending');
  await page.evaluate(()=>document.querySelector('#schoolOriginalDialog').close());
  await open('link');const linkText=await dialog.innerText();
  release();await delay(500);
  assert.equal(await row(ISO).count(),0,'late reply from another notice never lands in the current panel');
  assert.equal(await dialog.innerText(),linkText,'current panel unchanged by the late reply');
  await close();await open('iso');
  assert.match(await rowText(ISO),/第1次抓取/);assert.equal(posts.filter(p=>p.url===ISO).length,1);
  await fits(page);await close();
  assert.deepEqual(pageErrors,[],'no page errors');await page.close();
 }
 console.log(JSON.stringify({passed:true,widths:[360,1440],realAPI:true,syntheticOnly:true,zeroPostOnOpen:true,fullLongLink:true,escapedFragment:true,cacheOnReopen:true,doubleClickGuard:true,loginRecovery:true,lostReplyCached:true,serverFailureRetry:true,staleReplyIsolated:true,originalsAndSelectionKept:true,trailingPunctuationTrimmed:true}));
}catch(error){console.error(error);process.exitCode=1}finally{if(browser)await browser.close();if(proc&&proc.exitCode===null){proc.kill('SIGINT');await Promise.race([once(proc,'exit'),delay(3000)]);if(proc.exitCode===null)proc.kill('SIGKILL')}}})();
