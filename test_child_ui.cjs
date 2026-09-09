// Run: PLAYWRIGHT_MODULE=/path/to/playwright PLAYWRIGHT_CHANNEL=chrome node test_child_ui.cjs
// Isolated synthetic demo, including a /family/ proxy. Never uses household data.
const assert=require('node:assert/strict');
const http=require('node:http');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises');
const {randomUUID}=require('node:crypto');
const fs=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const secretNote='SYNTHETIC_PARENT_PRIVATE_NOTE',otherBook='SYNTHETIC_OTHER_CHILD_BOOK';
async function eventually(check,label,timeout=10000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function listen(server){server.listen(0,'127.0.0.1');await once(server,'listening');return server.address().port}
async function launchDemo(){
 const reserve=http.createServer(),port=await listen(reserve);await new Promise(r=>reserve.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];env.FAMILY_CHILD_COOKIE_PATH='/family/child/';
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let failed=null;child.on('error',e=>failed=e);child.stdout.resume();child.stderr.resume();
 const stop=async()=>{if(child.exitCode!==null||child.signalCode!==null)return;const done=once(child,'exit');child.kill('SIGINT');await Promise.race([done,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await done}};
 let proxy;
 try{
  await eventually(async()=>{if(failed)throw failed;if(child.exitCode!==null)throw Error('Demo exited');try{return (await fetch('http://127.0.0.1:'+port+'/api/state')).ok}catch{return false}},'demo ready');
  proxy=http.createServer((req,res)=>{
   if(!req.url.startsWith('/family/')){res.writeHead(404).end();return}
   const upstream=http.request({hostname:'127.0.0.1',port,path:req.url.slice('/family'.length),method:req.method,headers:{...req.headers,host:'localhost:'+port}},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res)});
   upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end()});req.pipe(upstream);
  });
  const publicPort=await listen(proxy);return {url:'http://127.0.0.1:'+publicPort+'/family/',stop:async()=>{proxy.closeAllConnections?.();await new Promise(r=>proxy.close(r));await stop()}};
 }catch(e){if(proxy)proxy.close();await stop();throw e}
}
async function inviteOrigins(context,local){
 // HTTPS here is an intercepted synthetic origin, never a real TLS or phone check.
 const remote='https://synthetic-family.example',fallback='https://configured-child.example/family/child/';
 for(const prefix of ['/family/','/']){
  const p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  let offered=fallback,issued='';
  try{
   await p.route(remote+'/**',async route=>{const url=new URL(route.request().url());assert.ok(url.pathname.startsWith(prefix));await route.fulfill({response:await route.fetch({url:local+url.pathname.slice(prefix.length)+url.search})})});
   await p.route('**/api/child-access/invite',async route=>{const response=await route.fetch({url:local+'api/child-access/invite'}),body=await response.json();assert.equal(response.status(),200);issued=body.invite;await route.fulfill({response,json:{...body,entry_url:offered}})});
   const open=async url=>{await p.goto(url);await p.locator('[data-child-access="child-1"]').click();await p.locator('[data-child-invite="child-1"]').waitFor()};
   const generate=async()=>{await p.locator('[data-child-invite="child-1"]').click();await eventually(async()=>await p.locator('#childInviteLink').count()&&!!await p.locator('#childInviteLink').inputValue(),'origin-specific invitation');return new URL(await p.locator('#childInviteLink').inputValue())};
   await open(remote+prefix+'?view=synthetic#old');const same=await generate();
   assert.equal(same.origin,remote,'HTTPS ignores a different configured backend host');assert.equal(same.pathname,prefix+'child/','current deployment prefix is used exactly once');assert.equal(same.search,'');assert.equal(same.hash,'#invite='+encodeURIComponent(issued));
   if(prefix==='/family/'){
    await open(local);const configured=await generate();assert.equal(configured.origin,new URL(fallback).origin);assert.equal(configured.pathname,'/family/child/');assert.equal(configured.search,'');assert.equal(configured.hash,'#invite='+encodeURIComponent(issued),'HTTP fallback keeps the invite in the fragment');
    offered='https://synthetic-user:synthetic-password@configured-child.example/family/child/?unsafe=1';await p.locator('[data-child-invite="child-1"]').click();await eventually(async()=>/入口地址无法核对/.test(await p.locator('#childAccessError').innerText()),'invalid fallback rejected');assert.equal(await p.locator('#childInviteLink').count(),0,'invalid fallback never receives the invite');
   }
   assert.deepEqual(errors,[]);
  }finally{await p.close()}
 }
}
(async()=>{
 let server,browser;const checks=[],contexts=[];
 try{
  server=await launchDemo();browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'],...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const parentContext=await browser.newContext({viewport:{width:1440,height:980}});contexts.push(parentContext);const parent=await parentContext.newPage();
  await inviteOrigins(parentContext,server.url);checks.push('synthetic HTTPS uses current origin and root or /family prefix; HTTP accepts only valid configured fallback; invitation stays in fragment');
  let parentState=await (await fetch(server.url+'api/state')).json();
  async function parentAPI(action,obj){const r=await fetch(server.url+'api/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':parentState.token},body:JSON.stringify(obj)});const value=await r.json();assert.equal(r.status,200,value.error);return value}
  async function reading(action,obj){return (await parentAPI('reading/'+action,{request_key:randomUUID(),child_id:'child-1',...obj})).task}
  let task=await reading('create',{book:'小小森林探索记',edition:'虚构测试版',scope:'第一段：观察一片叶子',method:'讲述或画图',criteria:'说出一个发现，再举一个自己观察到的细节',stamps:2});
  task=await reading('start',{id:task.id,version:task.version,note:secretNote});
  let other=await reading('create',{child_id:'child-2',book:otherBook,scope:'仅另一位孩子可见',method:'文字',criteria:'自己的想法',stamps:3});
  await reading('start',{child_id:'child-2',id:other.id,version:other.version,note:secretNote});
  // Use the same isolated app to check action requirements before opening any detail.
  const shots=process.env.CHILD_UI_SCREENSHOTS; if(shots)await fs.mkdir(shots,{recursive:true});
  const inspect=await parentContext.newPage(),calendarNote='虚构准备：带上水杯与已签字回执\n先到服务台领取材料',calendarTitle='虚构周末观察';
  await parentAPI('calendar/save',{id:randomUUID().replaceAll('-',''),version:0,child_ids:['child-1'],title:calendarTitle,category:'activity',day:parentState.today,start_time:'16:00',end_time:'17:00',location:'虚构活动中心二楼服务台旁集合',note:calendarNote,status:'confirmed',repeat:'weekly',until:parentState.today});
  const visibleRequirement=async(locator,text)=>{assert.equal(await locator.isVisible(),true,text+' visible without expansion');assert.equal(await locator.evaluate(el=>el.closest('details')===null),true,text+' outside details');assert.match(await locator.innerText(),new RegExp(text));};
  for(const width of [360,1440]){
   await inspect.setViewportSize({width,height:900});await inspect.goto(server.url);await eventually(()=>inspect.locator('[data-page="calendar"]').first().isVisible(),'inspection page ready');await inspect.locator('[data-page="calendar"]').first().click();
   const event=inspect.locator('.calendar-event').filter({has:inspect.getByRole('heading',{name:calendarTitle,exact:true})});await eventually(()=>event.isVisible(),'calendar requirements visible');
   await visibleRequirement(event.locator('.calendar-requirements'),'带上水杯与已签字回执');assert.equal(await event.locator('.calendar-requirements').innerText(),calendarNote);await visibleRequirement(event.locator('.calendar-time'),'16:00');await visibleRequirement(event.locator('.calendar-location'),'活动中心');assert.equal(await event.locator('details').getAttribute('open'),null);assert.equal(await inspect.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'calendar action layout '+width);
   if(shots)await inspect.screenshot({path:path.join(shots,'synthetic-calendar-'+width+'.png'),fullPage:true});
   await inspect.goto(server.url);await eventually(()=>inspect.locator('[data-page="reading"]').first().isVisible(),'reading entry ready');await inspect.locator('[data-page="reading"]').first().click();const book=inspect.locator('[data-reading-target="'+task.id+'"]');await eventually(()=>book.isVisible(),'parent reading requirements visible');
   await visibleRequirement(book.locator('.reading-method'),task.method);await visibleRequirement(book.locator('.reading-criteria'),task.criteria);assert.equal(await book.locator(':scope > .book-body > details').getAttribute('open'),null);assert.equal(await inspect.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'parent reading action layout '+width);if(shots)await inspect.screenshot({path:path.join(shots,'synthetic-parent-reading-'+width+'.png'),fullPage:true});
  }
  await inspect.close();checks.push('calendar preparation, time and place plus parent reading criteria are visible outside details at 360 / 1440 widths');
  await parent.goto(server.url);await eventually(()=>parent.locator('[data-child-access="child-1"]').isVisible(),'parent access button');
  await parent.locator('[data-child-access="child-1"]').click();await eventually(()=>parent.locator('[data-child-invite="child-1"]').isVisible(),'parent access dialog');
  assert.equal(await parent.locator('[data-child-share="'+task.id+'"]').isChecked(),false,'tasks default private');
  await parent.locator('[data-child-invite="child-1"]').click();await eventually(async()=>!!await parent.locator('#childInviteLink').inputValue(),'one-use invite');
  const invite=await parent.locator('#childInviteLink').inputValue();assert.match(invite,/\/family\/child\/#invite=/);
  const childContext=await browser.newContext({viewport:{width:400,height:860},permissions:['microphone']});contexts.push(childContext);const child=await childContext.newPage(),errors=[],requests=[];
  child.on('pageerror',e=>errors.push(e.message));child.on('request',r=>requests.push({url:r.url(),method:r.method()}));
  await child.route('**/child/api/login',async route=>{const response=await route.fetch();assert.equal(response.status(),200);await route.abort('failed')});
  await child.goto(invite);await eventually(()=>child.locator('#journey').isVisible(),'child invite login');
  await child.unroute('**/child/api/login');assert.equal(new URL(child.url()).hash,'');assert.match(await child.locator('#books').innerText(),/还没有与你分享/);assert.equal(await child.evaluate(()=>document.cookie),'');
  assert.equal(await child.evaluate(()=>localStorage.length+sessionStorage.length),0,'child keeps no browser-storage login');
  const cookies=await childContext.cookies();assert.ok(cookies.length&&cookies.every(c=>c.httpOnly&&c.sameSite==='Strict'&&c.path==='/family/child/'));
  await parent.locator('[data-child-share="'+task.id+'"]').click();await eventually(()=>parent.locator('[data-child-share="'+task.id+'"]').isChecked(),'explicit share');
  await child.locator('#refresh').click();await eventually(()=>child.locator('[data-open="'+task.id+'"]').isVisible(),'shared task appears');
  const shared=await (await childContext.request.get(server.url+'child/api/state')).json();assert.equal(shared.tasks.length,1);assert.equal(JSON.stringify(shared).includes(secretNote),false);assert.equal(JSON.stringify(shared).includes(otherBook),false);assert.equal('history' in shared.tasks[0],false);assert.equal('parent_note' in shared.tasks[0],false);
  assert.equal(await child.locator('[data-reading-action],[data-child-access],[data-page]').count(),0,'child has no parent controls');assert.equal(await child.locator('#earned').innerText(),'0');
  const childBook=child.locator('.book').filter({has:child.locator('[data-open="'+task.id+'"]')});await visibleRequirement(childBook.locator('.reading-method'),task.method);await visibleRequirement(childBook.locator('.reading-criteria'),task.criteria);
  checks.push('parent selects explicit sharing, one-use fragment invitation, lost login response recovery and child-only state');
  await child.locator('[data-open="'+task.id+'"]').click();await child.locator('#work-text').fill('我发现叶片的纹路像一条条分叉的小路。');
  await child.locator('#rest').click();assert.match(await child.locator('#notice').innerText(),/没有标记完成/);await child.locator('[data-open="'+task.id+'"]').click();assert.match(await child.locator('#work-text').inputValue(),/分叉的小路/);
  let uploadFailure=true;
  await child.route('**/child/api/upload',async r=>{if(uploadFailure){uploadFailure=false;await r.abort('failed')}else await r.continue()});
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=','base64');
  await child.locator('#photo').setInputFiles({name:'虚构叶片.png',mimeType:'image/png',buffer:png});await eventually(()=>child.locator('[data-retry]').isVisible(),'failed upload retains original');
  await child.locator('[data-retry]').click();await eventually(()=>child.locator('#attachments img').isVisible(),'photo retry succeeds');await child.unroute('**/child/api/upload');
  await child.locator('#record').click();await eventually(async()=>/停止录音/.test(await child.locator('#record').innerText()),'fake microphone recording');await delay(220);await child.locator('#record').click();await eventually(()=>child.locator('#attachments audio').isVisible(),'audio original uploaded');
  const before=await child.locator('#work-text').inputValue();let submitBodies=[],drop=true;
  await child.route('**/child/api/submit',async route=>{submitBodies.push(route.request().postDataJSON());if(drop){drop=false;const response=await route.fetch();assert.equal(response.status(),200);await route.abort('failed')}else await route.continue()});
  await child.locator('#submit').click();await eventually(async()=>/结果还未确认/.test(await child.locator('#work-status').innerText()),'lost response acknowledged');assert.equal(await child.locator('#work-text').inputValue(),before);assert.equal(await child.locator('#work-text').getAttribute('readonly'),'');
  await child.locator('#submit').click();await eventually(async()=>/作品交好了/.test(await child.locator('#work-status').innerText()),'same submission retried');assert.deepEqual(submitBodies[0],submitBodies[1]);await child.unroute('**/child/api/submit');
  parentState=await (await fetch(server.url+'api/state')).json();task=parentState.reading.tasks.find(t=>t.id===task.id);assert.equal(task.state,'待确认');assert.equal(task.attachments.length,2);assert.equal(task.history.filter(h=>h.action==='submit').length,1);assert.equal(task.award,null);
  checks.push('rest preserves draft, failed photo upload retries, fake microphone saves original, lost submission response retries once');
  await parent.locator('[data-close="readingDialog"]').last().click();await parent.locator('#refresh').click();await eventually(()=>parent.locator('[data-page="reading"]').first().isVisible(),'parent refreshed');await parent.locator('[data-page="reading"]').first().click();
  await eventually(()=>parent.locator('[data-reading-action="confirm"][data-id="'+task.id+'"]').isVisible(),'parent sees child submission');await parent.locator('[data-reading-action="confirm"][data-id="'+task.id+'"]').click();await parent.locator('#readingActionForm textarea').fill('虚构检查：看过图与录音，已找到自己的观察细节。');await parent.locator('#readingActionForm [type="submit"]').click();await eventually(async()=>!(await parent.locator('#readingDialog').isVisible()),'parent confirmation saved');
  await child.locator('#refresh').click();await eventually(async()=>await child.locator('#earned').innerText()==='2','actual award reaches child');assert.equal(await child.locator('#work-form').isVisible(),false);assert.match(await child.locator('#saved-work').innerText(),/已获得 2 枚/);
  checks.push('parent reads current submitted work and confirms through UI; child refresh sees actual award');
  // Make a new allowed revision and exercise the stale agreement branch.
  parentState=await (await fetch(server.url+'api/state')).json();task=parentState.reading.tasks.find(t=>t.id===task.id);task=await reading('request_more',{id:task.id,version:task.version,reason:secretNote});await child.locator('#refresh').click();await eventually(()=>child.locator('#work-form').isVisible(),'supplement allowed');
  await child.locator('#work-text').fill('新的观察文字仍然是我自己写的。');task=await reading('edit',{id:task.id,version:task.version,book:task.book,edition:task.edition,scope:'改为观察另一片叶子',method:task.method,criteria:task.criteria,source_task_id:'',planned_on:'',stamps:task.stamps,reason:secretNote});
  await child.locator('#submit').click();await eventually(()=>child.getByRole('button',{name:'已看过新约定，保留作品继续'}).isVisible(),'version conflict explained');assert.match(await child.locator('#work-text').inputValue(),/我自己写的/);assert.match(await child.locator('#agreement').innerText(),/另一片叶子/);await child.getByRole('button',{name:'已看过新约定，保留作品继续'}).click();await child.locator('#submit').click();await eventually(async()=>/作品交好了/.test(await child.locator('#work-status').innerText()),'explicit revised agreement submit');
  checks.push('version conflict keeps own text and requires acknowledging updated agreement');

  for(const width of [360,400,1440]){
   await child.setViewportSize({width,height:900});await child.locator('#back').click();await visibleRequirement(childBook.locator('.reading-method'),task.method);await visibleRequirement(childBook.locator('.reading-criteria'),task.criteria);assert.equal(await child.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'camp width '+width);if(shots){await child.evaluate(()=>scrollTo(0,0));await child.screenshot({path:path.join(shots,'synthetic-camp-'+width+'.png'),fullPage:true})}
   await child.locator('[data-open="'+task.id+'"]').click();assert.equal(await child.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'work width '+width);if(shots){await child.evaluate(()=>scrollTo(0,0));await child.screenshot({path:path.join(shots,'synthetic-work-'+width+'.png'),fullPage:true})}
  }
  checks.push('360 / 400 / 1440 CSS pixel camp and submission layouts have no horizontal overflow');
  await child.clock.install();await child.route('**/child/api/state',()=>{});await child.locator('#refresh').click();await child.clock.fastForward(13000);await eventually(async()=>/超时/.test(await child.locator('#notice').innerText()),'state timeout visible');await child.unroute('**/child/api/state');await child.locator('#refresh').click();await eventually(async()=>await child.locator('#notice').innerText()==='','state timeout recovers');await child.clock.resume();
  await parent.goto(server.url);await parent.locator('[data-child-access="child-1"]').click();await eventually(()=>parent.locator('[data-child-share="'+task.id+'"]').isVisible(),'parent access reopened');await parent.locator('[data-child-share="'+task.id+'"]').click();await eventually(async()=>!(await parent.locator('[data-child-share="'+task.id+'"]').isChecked()),'unshare saved');await child.locator('#refresh').click();await eventually(()=>child.locator('#journey').isVisible(),'unshared task closes');assert.equal(await child.locator('[data-open]').count(),0);
  await parent.locator('[data-child-revoke="child-1"]').click();await eventually(async()=>/已停用/.test(await parent.locator('#childInviteResult').innerText()),'revoke saved');await child.locator('#refresh').click();await eventually(()=>child.locator('#login').isVisible(),'revoked session loses access');
  assert.equal((await childContext.request.get(server.url+'child/api/state')).status(),401);assert.equal(requests.some(r=>new URL(r.url).pathname.startsWith('/family/api/')),false,'child UI never requests parent APIs');assert.deepEqual(errors,[]);
  checks.push('bounded state timeout recovers; unsharing and session revocation remove child access');
  await parentAPI('child-access/share',{child_id:'child-2',task_id:other.id,shared:true});
  const secondInvite=await parentAPI('child-access/invite',{child_id:'child-2'});
  await child.locator('#invite').fill(secondInvite.invite);await child.locator('#login button').click();await eventually(()=>child.locator('[data-open="'+other.id+'"]').isVisible(),'second child on same page');
  const allDOM=await child.evaluate(()=>document.body.textContent+'\n'+[...document.querySelectorAll('input,textarea')].map(e=>e.value).join('\n'));
  assert.equal(allDOM.includes('小小森林探索记'),false,'old child book is removed, not hidden');assert.equal(allDOM.includes('新的观察文字仍然是我自己写的'),false,'old child draft is removed');assert.equal(allDOM.includes(secretNote),false);
  checks.push('same-page child identity change clears prior child text, attachment and agreement DOM');
  const fallback=await childContext.newPage();await fallback.route('**/child/child.js',r=>r.fulfill({status:503,contentType:'text/javascript',body:''}));await fallback.goto(server.url+'child/');assert.equal(await fallback.locator('#refresh').isVisible(),true);await fallback.unroute('**/child/child.js');await fallback.locator('#refresh').click();await eventually(()=>fallback.locator('[data-open="'+other.id+'"]').isVisible(),'native reload recovers unavailable script');await fallback.close();
  checks.push('native reload control works even when child script fails to load');
  console.log(JSON.stringify({passed:checks.length,checks,syntheticOnly:true,realMicrophone:false,phoneHardwareTested:false,screenshots:shots||null},null,2));
 }finally{for(const c of contexts)await c.close();await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
