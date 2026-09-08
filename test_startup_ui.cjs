// Run: node test_startup_ui.cjs. Requires Playwright and an installed browser.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, STARTUP_UI_PROOF_DIR.
// --keyboard-static-only runs just the keyboard regression; its POSTs use the disposable demo.
// Uses demo.py's temporary, synthetic family. No production URLs or real devices.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');

async function eventually(check,label,timeout=8000){
 const end=Date.now()+timeout;
 while(Date.now()<end){if(await check())return;await delay(40)}
 throw Error('Timed out: '+label);
}
async function unusedPort(){const s=net.createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const port=s.address().port;await new Promise(resolve=>s.close(resolve));return port}
async function demoServer(){
 const port=await unusedPort(),url='http://127.0.0.1:'+port+'/',env={...process.env};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});
 let failed=null;child.on('error',e=>{failed=e});child.stdout.resume();child.stderr.resume();
 const stop=async()=>{if(failed||child.exitCode!==null||child.signalCode!==null)return;const exited=once(child,'exit');child.kill('SIGINT');await Promise.race([exited,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await exited}};
 try{await eventually(async()=>{if(failed)throw failed;if(child.exitCode!==null)throw Error('Synthetic demo exited before startup');try{return (await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'synthetic demo server');return {url,stop}}catch(e){await stop();throw e}
}
const fixtureGlobals=`let page='fixture-page'; let data={source:'fixture-only'}; const basePath='fixture-base'; window.__startupFixture=()=>({page,data,basePath});`;
async function newPage(browser,width=400){
 const p=await browser.newPage({viewport:{width,height:820}}),errors=[],posts=[];
 p.on('pageerror',e=>errors.push(e.message));
 p.on('request',r=>{if(r.method()!=='GET')posts.push(r.method()+' '+new URL(r.url()).pathname)});
 // A real parser-inserted script creates global lexical bindings. Playwright's
 // addInitScript wrapper would not reproduce a top-level declaration collision.
 await p.route('**/__startup-global-fixture.js',r=>r.fulfill({contentType:'text/javascript',body:fixtureGlobals}));
 await p.route(url=>url.pathname==='/',async r=>{const response=await r.fetch(),html=await response.text();await r.fulfill({response,body:html.replace('<head>','<head><script src="./__startup-global-fixture.js"></script>')})});
 return {p,errors,posts};
}
async function homeReady(p){await eventually(async()=>await p.locator('.today-dashboard').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','ready home with today agenda')}
async function checkIsolation(p){
 const result=await p.evaluate(()=>({original:window.__startupFixture(),leaked:['load','render','esc','apiFetch','readingHomeHTML','calendarHomeHTML'].filter(k=>typeof window[k]!=='undefined')}));
 assert.deepEqual(result.original,{page:'fixture-page',data:{source:'fixture-only'},basePath:'fixture-base'});assert.deepEqual(result.leaked,[]);
}
async function checkWidth(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal page overflow')}
async function retryLink(p){
 // Static recovery must work even when the application bundle never executes.
 const choices=p.locator('[data-startup-retry]');
 let found=null;await eventually(async()=>{for(let i=0;i<await choices.count();i++){const x=choices.nth(i);if(await x.isVisible()){found=x;return true}}return false},'visible startup recovery control');return found;
}

async function keyboardStaticChecks(browser,url){
 const checks=[];
 for(const width of [360,1440]){
  const {p,errors,posts}=await newPage(browser,width);let release;
  try{
   await p.emulateMedia({reducedMotion:'reduce'});
   await p.addInitScript(()=>{window.__blockedWebGL=0;const get=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){if(/webgl/i.test(type)){window.__blockedWebGL++;return null}return get.call(this,type,...args)}});
   const read=async()=>await(await fetch(url+'api/state')).json();
   const focused=selector=>p.evaluate(s=>document.activeElement?.matches(s),selector);
   const tabTo=async(selector,reverse=false)=>{for(let i=0;i<80;i++){if(await focused(selector))return;await p.keyboard.press(reverse?'Shift+Tab':'Tab')}throw Error('Not keyboard reachable: '+selector)};
   const fit=async()=>{await checkWidth(p);assert.equal(await p.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'dialog fits '+width)};
   await p.goto(url,{waitUntil:'domcontentloaded'});await homeReady(p);assert.equal(await p.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches&&window.__blockedWebGL===0),true,'today does not need WebGL');await fit();
   // Explicit starting focus only; subsequent inputs and activations are actual keys.
   await p.locator('nav [data-page="tasks"]').focus();await p.keyboard.press('Enter');
   await tabTo('[data-new-task]');await p.keyboard.press('Enter');await eventually(()=>p.locator('#newTaskDialog').isVisible(),'new task dialog');
   await tabTo('#newTaskForm [type="submit"]');await p.keyboard.press('Enter');assert.equal(await focused('#newTaskForm [name="title"]'),true,'required field receives focus');await fit();
   await p.keyboard.press('Shift+Tab');assert.equal(await focused('#newTaskForm [name="child"]'),true);await p.keyboard.press('Tab');
   const title='虚构键盘待办 '+width,note='虚构键盘反馈：已核对要求。';await p.keyboard.insertText(title);await tabTo('#newTaskForm [name="due"]');await p.keyboard.insertText('虚构下周');await tabTo('#newTaskForm [type="submit"]');await p.keyboard.press('Enter');
   await eventually(async()=>!(await p.locator('#newTaskDialog').isVisible())&&(await read()).tasks.some(t=>t.title===title),'new task persisted');await eventually(()=>focused('[data-new-task]'),'new task opener restored after render');await fit();
   const task=(await read()).tasks.find(t=>t.title===title),checkbox='[data-check="'+task.id+'"]',feedback='[data-task="'+task.id+'"]';
   // Hold only this synthetic write: a second Space must not enqueue another update.
   let held=0;const gate=new Promise(resolve=>release=resolve);await p.route('**/api/task',async route=>{if(route.request().method()==='POST'&&held++===0)await gate;await route.continue()});
   await tabTo(checkbox);await p.keyboard.press('Space');await eventually(()=>held===1,'held checkbox request');assert.equal(await focused(checkbox),true);assert.equal(await p.locator(checkbox).getAttribute('aria-disabled'),'true');await p.keyboard.press('Space');assert.equal(posts.filter(x=>x==='POST /api/task').length,1,'busy checkbox refuses duplicate');release();
   await eventually(async()=>(await read()).tasks.find(t=>t.id===task.id).update?.status==='已完成'&&await p.locator(checkbox).count()===0,'checked task persisted and filtered');await eventually(()=>focused('[data-view="待跟进"][aria-pressed="true"]'),'removed checkbox returns to current filter');await p.unroute('**/api/task');
   await tabTo('[data-view="已完成"]');await p.keyboard.press('Enter');assert.equal(await focused('[data-view="已完成"]'),true,'filter retains keyboard focus');await tabTo(feedback);await p.keyboard.press('Enter');await eventually(()=>p.locator('#taskDialog').isVisible(),'feedback dialog');
   // Default selected status is sufficient; native select popup driving is not claimed.
   await tabTo('#taskForm [name="note"]');await p.keyboard.insertText(note);await fit();await tabTo('#taskForm [type="submit"]');await p.keyboard.press('Enter');
   await eventually(async()=>!(await p.locator('#taskDialog').isVisible())&&(await read()).tasks.find(t=>t.id===task.id).update?.note===note,'feedback persisted');await eventually(()=>focused(feedback),'feedback opener restored after render');
   await p.keyboard.press('Enter');await eventually(()=>p.locator('#taskDialog').isVisible(),'reopened feedback');assert.equal(await p.locator('#taskForm [name="status"]').inputValue(),'已完成');await p.keyboard.press('Escape');await eventually(async()=>!(await p.locator('#taskDialog').isVisible()),'Escape closes feedback');assert.equal(await focused(feedback),true,'Escape returns to opener');await fit();
   const saved=(await read()).tasks.find(t=>t.id===task.id);assert.equal(saved.update.note,note);assert.ok(saved.history.length>=2);assert.deepEqual(errors,[]);
   checks.push({width,webGLDisabled:true,reducedMotion:true,keyboard:['Tab','Shift+Tab','Enter','Space','Escape','insertText'],requiredErrorFocus:true,savedTaskAndFeedback:true,saveFocusRestored:true,removedCheckboxFocusRestored:true,busyDuplicateRefused:true,escapeFocusRestored:true,noOverflow:true,pageErrors:0,syntheticWrites:posts});
  }finally{release?.();await p.close()}
 }
 const proof={checkedAt:new Date().toISOString(),syntheticOnly:true,realDevice:false,selectPopupDriving:false,checks};
 if(process.env.STARTUP_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.STARTUP_UI_PROOF_DIR,{recursive:true});await fs.writeFile(path.join(process.env.STARTUP_UI_PROOF_DIR,'keyboard-static-passed.json'),JSON.stringify(proof,null,2)+'\n')}
 return checks.map(c=>'keyboard task/feedback focus, required error, Escape and static '+c.width+'px layout');
}

(async()=>{
 let server,browser;const passed=[];
 try{
  server=await demoServer();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  if(process.argv.includes('--keyboard-static-only')){const checks=await keyboardStaticChecks(browser,server.url);console.log(JSON.stringify({passed:checks.length,checks,syntheticOnly:true,onlyNewKeyboardChecks:true},null,2));return}
  {
   // Routing disables Chromium's HTTP cache; use an untouched page for this check.
   const p=await browser.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
   const sizes=()=>p.evaluate(()=>performance.getEntriesByType('resource').filter(x=>/\.(js|css)$/.test(new URL(x.name).pathname)).map(x=>({path:new URL(x.name).pathname,transfer:x.transferSize,decoded:x.decodedBodySize})));
   try{
    await p.goto(server.url,{waitUntil:'load'});await homeReady(p);const first=await sizes();
    await p.reload({waitUntil:'load'});await homeReady(p);const warm=await sizes();
    assert.ok(first.some(x=>x.path==='/app.bundle.js'&&x.transfer>1000));
    assert.ok(warm.some(x=>x.path==='/app.bundle.js'));
    assert.ok(warm.every(x=>x.transfer<=500),'warm reload revalidates without redownloading static bodies: '+JSON.stringify({first,warm}));
    if(process.env.STARTUP_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.STARTUP_UI_PROOF_DIR,{recursive:true});await fs.writeFile(path.join(process.env.STARTUP_UI_PROOF_DIR,'static-cache-passed.json'),JSON.stringify({syntheticOnly:true,first,warm},null,2)+'\n')}
    assert.deepEqual(errors,[]);passed.push('warm reload reuses compressed static resources and renders current state');
   }finally{await p.close()}
  }
  for(const width of [360,400,1440]){
   const {p,errors,posts}=await newPage(browser,width);
   try{await p.goto(server.url,{waitUntil:'domcontentloaded'});await homeReady(p);await checkWidth(p);await checkIsolation(p);await p.locator('nav [data-page="calendar"]').click();await eventually(()=>p.locator('.calendar-week-grid').isVisible(),'calendar agenda');assert.equal(await p.locator('.calendar-day:visible').count(),width<=850?1:7);await checkWidth(p);await checkIsolation(p);assert.deepEqual(errors,[]);assert.deepEqual(posts,[]);passed.push('global-name collision, homepage/calendar and '+width+'px layout')}finally{await p.close()}
  }
  {
   const {p,errors,posts}=await newPage(browser);let held=0;
   await p.route('**/vendor/three.core.min.js',()=>{held++});
   try{await p.goto(server.url,{waitUntil:'domcontentloaded'});await homeReady(p);assert.equal(held,0,'today does not request Three');assert.deepEqual(errors,[]);assert.deepEqual(posts,[]);passed.push('homepage works without requesting Three')}finally{await p.close()}
  }
  for(const mode of ['503','pending']){
   const {p,posts}=await newPage(browser);let held=0;
   await p.clock.install();
   await p.route('**/app.bundle.js',async route=>{held++;if(mode==='503')await route.fulfill({status:503,contentType:'text/javascript',body:'/* synthetic bundle unavailable */'})});
   try{await p.goto(server.url,{waitUntil:'commit'});await eventually(()=>held===1,'blocked application bundle');await p.clock.fastForward(21000);await eventually(()=>p.locator('[data-startup-error]').isVisible(),'explicit bundle startup failure');const message=await p.locator('[data-startup-error]').innerText();assert.match(message,mode==='503'?/页面程序未能加载|页面加载超时/:/页面加载超时/);const retry=await retryLink(p);assert.equal(await p.locator('.calendar-entry').count(),0);await p.unroute('**/app.bundle.js');await retry.click();await homeReady(p);await checkIsolation(p);assert.deepEqual(posts,[]);passed.push('bundle '+mode+' exposes usable recovery and reload succeeds')}finally{await p.close()}
  }
  {
   const {p,errors,posts}=await newPage(browser);let held=0;
   await p.clock.install();await p.route('**/api/state',()=>{held++});
   try{await p.goto(server.url,{waitUntil:'domcontentloaded'});await eventually(()=>held===1,'pending initial state');await p.clock.fastForward(13000);await eventually(async()=>/超时/.test(await p.locator('#content').innerText()),'explicit state timeout');await p.unroute('**/api/state');await p.locator('#refresh').click();await homeReady(p);await checkIsolation(p);assert.deepEqual(errors,[]);assert.deepEqual(posts,[]);passed.push('initial state timeout is explicit and refresh recovers')}finally{await p.close()}
  }
  passed.push(...await keyboardStaticChecks(browser,server.url));
  console.log(JSON.stringify({passed:passed.length,checks:passed,syntheticOnly:true,keyboardWritesOnlyDisposableDemo:true},null,2));
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
