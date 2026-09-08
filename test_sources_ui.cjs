// Run as test_startup_ui.cjs with PLAYWRIGHT_MODULE / PLAYWRIGHT_CHANNEL.
// Only demo.py's disposable family and intercepted synthetic sources; no POSTs.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=8000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function demoServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let failure;proc.on('error',e=>failure=e);proc.stdout.resume();proc.stderr.resume();
 const stop=async()=>{if(failure||proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 const url='http://127.0.0.1:'+port+'/';try{await eventually(async()=>{if(failure)throw failure;if(proc.exitCode!==null)throw Error('Synthetic demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'demo');return{url,stop}}catch(e){await stop();throw e}
}
async function checkWidth(p,label){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label+' page overflow');assert.equal(await p.locator('[data-source-card]').evaluateAll(cards=>cards.some(el=>el.scrollWidth>el.clientWidth)),false,label+' card overflow')}
async function sources(p){await p.locator('nav [data-page="sources"]').click();await eventually(async()=>await p.locator('#content h1').innerText()==='来源与附件','sources page')}

(async()=>{
 let server,browser;const checks=[],proofDir=path.join(__dirname,'private/check-20260908/source-followup/ui');
 try{
  server=await demoServer();const base=await(await fetch(server.url+'api/state')).json(),first=base.children[0].name,second=base.children[1].name;
  const stringGap='<img src="/source-test-xss" onerror="window.__sourceXss=1"> 虚构图片尚未核对';
  const objectGap='<script>window.__sourceXss=2</script> 虚构长链接 '+('synthetic-path-without-spaces/').repeat(16);
  const sync={
   'qq:synthetic-history':{name:'虚构QQ群 <b>原名</b>',child:first,collection_status:'awaiting_login',method:'GUI',last_checked:'2026-08-01 08:00:00',last_attempt:'2026-09-01 18:00:00',last_error:'虚构登录未完成 <svg onload="window.__sourceXss=3">',incremental_new_records:7,incremental_count_note:'虚构历史 GUI 登记，不是今天读取。',full_content_complete:false,pending_content:[stringGap,{kind:'image',local_id:101,gap:objectGap},null,17,[],{}]},
   'wechat:synthetic-zero':{name:'虚构零新增群',child:second,incremental_new_records:0,full_content_complete:false,pending_content:[]},
   'wechat:synthetic-missing':{name:'虚构未知覆盖群',child:first,pending_content:{unexpected:'synthetic'}},
   'wechat:synthetic-scanned':{name:'虚构扫描群',child:second,fetched_local_records:3,full_content_complete:true,pending_content:[]},
   'wechat:synthetic-bad-count':{name:'虚构未知数量群',incremental_new_records:-1,fetched_local_records:'5',pending_content:[]},
   'wechat:synthetic-bad-entry':null,
   'wechat:synthetic-failed':{name:'虚构失败群',child:first,last_error:'虚构请求失败',incremental_new_records:7},
  };
  const task=(id,child,title,status='待跟进')=>({id,child,title,due:'虚构日期',action:'虚构要求',source:'虚构来源',original_status:status,update:{status},history:[]});
  let current={...base,sync,sync_error:'',tasks:[task('source-first',first,'虚构甲待办'),task('source-second',second,'虚构乙待办'),task('source-done',first,'虚构已完成事项','已完成')]};
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});const p=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],mutations=[],external=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(req.method()!=='GET'){mutations.push(req.method()+' '+url.pathname);return route.abort()}if(url.origin!==new URL(server.url).origin){external.push(url.origin);return route.abort()}if(url.pathname==='/api/state')return route.fulfill({json:current});return route.continue()});
  // Capture the actual object handed to the app, so DOM interactions cannot
  // silently rewrite source history even if the network fixture stays intact.
  await p.addInitScript(()=>{const original=Response.prototype.json;Response.prototype.json=async function(){const value=await original.call(this);if(new URL(this.url).pathname==='/api/state')window.__sourceInput={value,before:JSON.stringify({sync:value.sync,sync_error:value.sync_error,tasks:value.tasks})};return value}});
  await p.goto(server.url,{waitUntil:'domcontentloaded'});await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','home ready');await sources(p);
  const card=key=>p.locator('[data-source-card="'+key+'"]'),qq=card('qq:synthetic-history');
  assert.equal(await qq.locator('[data-source-status]').innerText(),'接入待验证');assert.match(await qq.locator('[data-source-count]').innerText(),/历史增量登记：7 条/);assert.match(await qq.innerText(),/尚待验证/);assert.match(await qq.innerText(),/虚构登录未完成 <svg/);assert.equal(/本轮新增|读取方式：.*GUI|当前.*GUI|已离线/.test(await qq.innerText()),false);
  assert.equal(await card('wechat:synthetic-failed').locator('[data-source-status]').innerText(),'最近读取未成功');assert.match(await card('wechat:synthetic-failed').innerText(),/虚构请求失败/);
  checks.push('awaiting-login QQ retains historical 7 and failure without claiming a current GUI read; failed source is explicit');
  const gaps=qq.locator('[data-source-gaps]');assert.equal(await gaps.getAttribute('open'),null);await gaps.locator('summary').click();assert.notEqual(await gaps.getAttribute('open'),null);const items=gaps.locator('li');assert.equal(await items.count(),6);assert.equal(await items.nth(0).innerText(),stringGap);assert.match(await items.nth(1).innerText(),/图片 · 消息 101/);assert.ok((await items.nth(1).innerText()).includes(objectGap));for(const n of [2,3,4])assert.match(await items.nth(n).innerText(),/说明格式异常/);assert.match(await items.nth(5).innerText(),/具体缺口尚未说明/);
  assert.equal(await p.locator('.source-cards img,.source-cards script,.source-cards svg,.source-cards b').count(),0);assert.equal(await p.evaluate(()=>window.__sourceXss),undefined);assert.equal(await p.locator('[data-source-card=""]').count(),1);assert.match(await p.locator('[data-source-card=""]').innerText(),/来源记录格式异常/);
  checks.push('native pending details expand; string, object, malformed entries and source names are escaped and isolated');
  for(const key of ['wechat:synthetic-zero','wechat:synthetic-missing','wechat:synthetic-scanned','wechat:synthetic-bad-count'])await card(key).locator('[data-source-gaps] > summary').click();
  assert.match(await card('wechat:synthetic-zero').locator('[data-source-count]').innerText(),/历史增量登记：0 条/);
  for(const key of ['wechat:synthetic-zero','wechat:synthetic-missing','wechat:synthetic-bad-count'])assert.match(await card(key).locator('[data-source-gaps]').innerText(),/不能据此认定全部内容已读/);
  for(const key of ['wechat:synthetic-missing','wechat:synthetic-bad-count'])assert.match(await card(key).locator('[data-source-count]').innerText(),/消息数量未记录/);
  assert.match(await card('wechat:synthetic-scanned').locator('[data-source-count]').innerText(),/3 条；不代表完整历史/);assert.match(await card('wechat:synthetic-scanned').locator('[data-source-gaps]').innerText(),/完整历史范围仍以来源说明为准/);
  checks.push('zero, absent and invalid counts never turn missing content into complete coverage');
  await fs.mkdir(proofDir,{recursive:true});
  for(const width of [360,1440]){
   await p.setViewportSize({width,height:1000});await checkWidth(p,String(width));await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:path.join(proofDir,'synthetic-sources-'+width+'.png'),fullPage:true});
   // Start with another view: a source shortcut must reset both child and tab.
   await p.locator('nav [data-page="tasks"]').click();await p.locator('[data-view="全部"]').click();await sources(p);
   for(const [key,name,title] of [['qq:synthetic-history',first,'虚构甲待办'],['wechat:synthetic-zero',second,'虚构乙待办']]){
    await card(key).locator('[data-source-tasks]').click();assert.equal(await p.locator('#childFilter').inputValue(),name);assert.equal(await p.locator('[data-view="待跟进"]').getAttribute('aria-pressed'),'true');assert.deepEqual(await p.locator('.checklist .task h3').allTextContents(),[title]);await checkWidth(p,'tasks '+width);await sources(p);
   }
   // Restore expanded source content for the next viewport.
   await p.locator('[data-source-gaps]').evaluateAll(details=>details.forEach(d=>{d.open=true}));
  }
  checks.push('360 and 1440 layouts fit; each source opens only that child pending checklist without writing');
  assert.equal(await p.evaluate(()=>JSON.stringify({sync:window.__sourceInput.value.sync,sync_error:window.__sourceInput.value.sync_error,tasks:window.__sourceInput.value.tasks})===window.__sourceInput.before),true);
  current={...current,sync:{},sync_error:'虚构来源状态损坏 <img src=x onerror="window.__sourceXss=4">'};await p.locator('#refresh').click();await eventually(()=>p.locator('[data-source-error]').isVisible(),'explicit damaged source state');assert.match(await p.locator('[data-source-error]').innerText(),/虚构来源状态损坏 <img/);assert.equal((await p.locator('#content').innerText()).includes('还没有保存的消息来源'),false);await p.locator('nav [data-page="tasks"]').click();assert.ok(await p.locator('.task').count()>0,'source error leaves saved tasks usable');await sources(p);
  current={...current,sync:{},sync_error:''};await p.locator('#refresh').click();await eventually(async()=>(await p.locator('#content').innerText()).includes('还没有保存的消息来源'),'real empty source state');assert.equal(await p.locator('[data-source-error]').count(),0);
  checks.push('damaged source metadata stays explicit while basic records work; valid empty source list is separate');
  assert.deepEqual(errors,[]);assert.deepEqual(mutations,[]);assert.deepEqual(external,[]);assert.equal(await p.evaluate(()=>window.__sourceXss),undefined);
  const proof={checkedAt:new Date().toISOString(),passed:checks.length,checks,syntheticOnly:true,mutationRequests:0,externalRequests:0,sourceInputUnchanged:true,realPhoneTested:false};await fs.writeFile(path.join(proofDir,'ui-proof.json'),JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof,null,2));
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
