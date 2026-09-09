// Disposable empty household only; no family data, accounts, model calls, or collectors.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(50)}throw Error('Timed out: '+label)}
async function server(environment={}){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 Object.assign(env,environment);
 const launch=`import app, tempfile, shutil, sys
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='synthetic-empty-settings-') as tmp:
    source=app.ROOT
    app.ROOT=Path(tmp);app.DATA=app.ROOT/'private';app.DATA.mkdir();app.DB=app.DATA/'family.sqlite3'
    for name in set(app.STATIC.values())|{'child.html','child.js','child.css'}:
        target=app.ROOT/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
    app.prepare_assets()
    server=app.ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1])),app.Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()`;
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',launch,String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let err='';child.stdout.resume();child.stderr.on('data',b=>err+=String(b));
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(child.exitCode!==null||child.signalCode!==null)return;const end=once(child,'exit');child.kill('SIGINT');await Promise.race([end,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await end}};
 try{await eventually(async()=>{if(child.exitCode!==null)throw Error(err||'Server exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'empty household server');return{url,stop}}catch(e){await stop();throw e}
}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');assert.equal(await p.locator('.settings-view button:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'44px touch buttons')}
async function proof(p,name){if(process.env.SETTINGS_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.SETTINGS_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.SETTINGS_UI_PROOF_DIR,name+'.png'),fullPage:false})}}
async function partialModelEnvironment(browser,width){
 const key='SYNTHETIC-ENV-ONLY-KEY-CANARY',app=await server({FAMILY_LLM_API_KEY:key});
 const p=await browser.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 const read=async route=>{const response=await fetch(app.url+route);assert.equal(response.status,200);return response.json()};
 try{
  await p.goto(app.url);await p.locator('.settings-view h1').waitFor();
  assert.equal(await p.locator('.settings-view h1').innerText(),'先认识你的家庭');
  const form=p.locator('[data-settings-form="model"]'),card=p.locator('.settings-view .card').filter({has:form});
  const initial=await read('api/settings');
  assert.equal(initial.model.origin,'environment','incomplete environment configuration stays environment-managed');
  assert.equal(initial.model.configured,false);
  for(const name of ['base_url','model','api_key'])assert.equal(await form.locator('[name="'+name+'"]').isDisabled(),true,'environment-managed '+name+' is disabled');
  assert.equal(await form.locator('[type="submit"]').isDisabled(),true);assert.equal(await p.locator('[data-settings-test]').isDisabled(),true);
  assert.equal(await form.locator('[name="api_key"]').inputValue(),'');
  assert.equal(JSON.stringify(initial).includes(key),false);assert.equal(JSON.stringify(await read('api/state')).includes(key),false);assert.equal((await p.content()).includes(key),false);
  // Model failure must not stop the independent manual setup path.
  const child=p.locator('[data-settings-form="child"]');await child.locator('[name="name"]').fill('虚构配置检查孩子');await child.locator('[name="grade"]').fill('四年级');await child.locator('[type="submit"]').click();
  await eventually(async()=>await p.locator('.settings-child').count()===1,'manual child setup works with incomplete model environment');
  const saved=await read('api/settings');assert.equal(saved.children[0].name,'虚构配置检查孩子');assert.equal(saved.children.length,1);
  assert.equal(saved.model.origin,'environment');assert.equal(saved.model.configured,false);
  for(const name of ['base_url','model','api_key'])assert.equal(await form.locator('[name="'+name+'"]').isDisabled(),true);
  assert.equal(await form.locator('[name="api_key"]').inputValue(),'');assert.equal(JSON.stringify(saved).includes(key),false);assert.equal(JSON.stringify(await read('api/state')).includes(key),false);assert.equal((await p.content()).includes(key),false);
  await card.evaluate(el=>el.scrollIntoView({block:'start'}));await fit(p);
  const visibleErrors=await card.locator('.error:visible,[role="alert"]:visible').allTextContents();
  const evidence={width,scenario:'api-key-only-environment',model:{origin:saved.model.origin,configured:saved.model.configured,error:saved.model.error},visibleModelErrors:visibleErrors,environmentControlsDisabled:true,keyNotReturned:true,manualChildSetup:true,noOverflow:true,pageErrors:errors};
  await proof(p,'settings-partial-environment-'+width);
  if(process.env.SETTINGS_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.SETTINGS_UI_PROOF_DIR,'settings-partial-environment-'+width+'.json'),JSON.stringify(evidence,null,2)+'\n')}
  assert.deepEqual(errors,[]);
  assert.ok(typeof initial.model.error==='string'&&initial.model.error.trim(),'an API-key-only deployment must expose a nonempty model configuration error');
  assert.ok(typeof saved.model.error==='string'&&saved.model.error.trim(),'configuration error survives manual child setup');
  assert.ok(visibleErrors.some(text=>text.trim()&&text.includes(saved.model.error)),'the model card visibly displays the configuration error');
  return evidence;
 }finally{await p.close();await app.stop()}
}
(async()=>{
 let browser;const results=[];
 try{
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440])results.push(await partialModelEnvironment(browser,width));
  for(const width of [360,1440]){
   const app=await server(),p=await browser.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
   const read=async()=>await(await fetch(app.url+'api/settings')).json();
   const post=async(path,body)=>{const state=await(await fetch(app.url+'api/state')).json();const response=await fetch(app.url+path,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(body)});const value=await response.json();assert.equal(response.ok,true,JSON.stringify(value));return value};
   const form=name=>p.locator('[data-settings-form="'+name+'"]');
   try{
    await p.goto(app.url);await p.locator('.settings-view h1').waitFor();assert.equal(await p.locator('.settings-view h1').innerText(),'先认识你的家庭');await fit(p);await proof(p,'settings-empty-'+width);
    await form('child').locator('[name="name"]').fill('虚构星星');await form('child').locator('[name="grade"]').fill('四年级');
    const keys=[];let drop=true;
    const lost=async route=>{keys.push(route.request().postDataJSON().request_key);if(drop){drop=false;const response=await route.fetch();assert.equal(response.ok(),true);await route.abort('failed')}else await route.continue()};
    await p.route('**/api/settings/child',lost);await form('child').locator('[type="submit"]').click();await eventually(async()=>/输入已保留/.test(await p.locator('#settingsStatus').innerText()),'lost child response retained');
    assert.equal(await form('child').locator('[name="name"]').inputValue(),'虚构星星');await form('child').locator('[type="submit"]').click();await eventually(async()=>await p.locator('.settings-child').count()===1,'one child after retry');await p.unroute('**/api/settings/child',lost);assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);assert.equal((await read()).children.length,1);
    await p.getByText('＋ 添加孩子',{exact:true}).click();await form('child').locator('[name="name"]').fill('虚构小宇');await form('child').locator('[name="grade"]').fill('初一');await form('child').locator('[type="submit"]').click();await eventually(async()=>await p.locator('.settings-child').count()===2,'second child');
    await p.locator('[data-profile="child-2"]').click();const profile=p.locator('#profileForm');await profile.locator('[name="name"]').fill('虚构新称呼');await profile.locator('[name="reason"]').fill('虚构称呼更正');await profile.locator('[type="submit"]').click();await eventually(async()=>await p.locator('.settings-child').filter({hasText:'虚构新称呼'}).count()===1,'rename shown in settings');
    async function addGroup(platform,id,name,child){await p.getByText('＋ 绑定一个群',{exact:true}).click();const f=form('source-new');await f.locator('[name="platform"]').selectOption(platform);await f.locator('[name="child_id"]').selectOption(child);await f.locator('[name="name"]').fill(name);await f.locator('[name="id"]').fill(id);await f.locator('[name="consent"]').check();await f.locator('[type="submit"]').click();await eventually(async()=>await p.locator('.settings-source').filter({hasText:name}).count()===1,'group '+name)}
    await addGroup('wechat','100000001@chatroom','虚构主班级群','child-1');await addGroup('wechat','100000002@chatroom','虚构兴趣群','child-1');await addGroup('qq','200000001','虚构中学群','child-2');
    assert.equal((await read()).sources.filter(x=>x.child_id==='child-1').length,2);assert.equal((await read()).sources[0].cursor,'0');
    await form('agent').locator('[name="enabled"]').check();await form('agent').locator('[type="submit"]').click();await eventually(async()=>(await read()).enabled,'agent enabled');
    const group=p.locator('.settings-source').filter({hasText:'虚构兴趣群'});await group.locator('summary').click();await group.locator('[name="enabled"]').uncheck();await group.locator('[type="submit"]').click();await eventually(async()=>!(await read()).sources.find(x=>x.name==='虚构兴趣群').enabled,'group disabled');
    // A model draft must survive saving another form and a concurrent configuration refresh.
    await form('model').locator('[name="base_url"]').fill('http://127.0.0.1:32123/v1');await form('model').locator('[name="model"]').fill('synthetic-model');await form('model').locator('[name="api_key"]').fill('SYNTHETIC-UI-KEY');
    // Another parent changes the top-level switch while this tab edits a source.
    const current=p.locator('.settings-source').filter({hasText:'虚构主班级群'});await current.locator('summary').click();await current.locator('[name="name"]').fill('虚构未丢失备注');
    let state=await read();const rows=state.sources.map(({id,platform,child_id,name,enabled})=>({id,platform,child_id,name,enabled}));await post('api/settings/sources',{revision:state.revision,enabled:false,sources:rows});
    await current.locator('[type="submit"]').click();await p.locator('[data-settings-conflict]').waitFor();assert.equal(await current.locator('[name="name"]').inputValue(),'虚构未丢失备注');await p.locator('[data-settings-conflict]').click();await eventually(async()=>await p.locator('[data-settings-conflict]').count()===0,'CAS reload redraw complete');assert.equal(await current.locator('[name="name"]').inputValue(),'虚构未丢失备注');assert.equal(await form('agent').locator('[name="enabled"]').isChecked(),false,'untouched switch displays the other parent latest value');await current.locator('[type="submit"]').click();await eventually(async()=>(await read()).sources.some(x=>x.name==='虚构未丢失备注'),'CAS reload preserves draft');assert.equal((await read()).enabled,false,'does not undo concurrent switch');await eventually(async()=>await p.locator('.settings-source header strong').filter({hasText:'虚构未丢失备注'}).count()===1,'saved source redraw complete');
    assert.equal(await form('model').locator('[name="base_url"]').inputValue(),'http://127.0.0.1:32123/v1','other form URL draft survives source save');assert.equal(await form('model').locator('[name="model"]').inputValue(),'synthetic-model','other form model draft survives source save');assert.equal(await form('model').locator('[name="api_key"]').inputValue(),'SYNTHETIC-UI-KEY','unsaved key draft survives source save');assert.equal((await read()).model.configured,false,'retained draft was not submitted implicitly');await form('model').locator('[type="submit"]').click();await eventually(async()=>(await read()).model.has_api_key,'model saved');await eventually(async()=>await form('model').locator('[name="api_key"]').inputValue()==='','key is cleared from form');assert.ok(!JSON.stringify(await read()).includes('SYNTHETIC-UI-KEY'));assert.ok(!await p.locator('body').innerText().then(text=>text.includes('SYNTHETIC-UI-KEY')));
    await p.locator('.settings-start').click();await eventually(async()=>await p.locator('.settings-view').count()===0,'leave settings');await p.getByRole('button',{name:'家庭设置',exact:true}).click();await p.locator('.settings-view').waitFor();await eventually(async()=>await p.locator('.settings-source').count()===3,'return to saved settings');await fit(p);await proof(p,'settings-saved-'+width);
    await p.reload();await p.getByRole('button',{name:'家庭设置',exact:true}).click();await p.locator('.settings-view').waitFor();assert.equal(await form('model').locator('[name="api_key"]').inputValue(),'');assert.equal((await read()).children.length,2);assert.deepEqual(errors,[]);
    results.push({width,emptyFirstRun:true,childRetryNoDuplicate:true,rename:true,multipleGroups:true,sourceAndAgentToggles:true,casPreservesInput:true,untouchedFieldsRefresh:true,otherFormDraftPreserved:true,keyNotReturned:true,persistentAcrossPages:true,noOverflow:true});
   }finally{await p.close();await app.stop()}
  }
  console.log(JSON.stringify({passed:results.length,syntheticOnly:true,realPhone:false,checks:results},null,2));
 }finally{await browser?.close()}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
