// Synthetic browser + real authentication API. No household account or production URL.
// PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, PARENT_LOGIN_UI_PROOF_DIR.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),http=require('node:http'),vm=require('node:vm');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const origin='https://family.example.test',home=origin+'/family/',password='synthetic-parent-password-123';
async function eventually(check,label,ms=10000){const end=Date.now()+ms;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function service(){
 const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'family-login-ui-')),env={...process.env};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];env.FAMILY_DATA=tmp;
 const code=`import json, app, family_access
app.read=lambda name: '| child-1 | 示例孩子 | 未填写 | 10岁 | 四年级 |\\n' if name=='家庭运行规则.md' else '# 虚构测试资料\\n'
config=family_access.make_config('https://family.example.test/family','parent','synthetic-parent-password-123')
p=app.DATA/'access.json';p.write_text(json.dumps(config));p.chmod(0o600)
app.connect().close();app.prepare_assets()
class TestHandler(app.Handler):
 def do_GET(self):
  if self.path=='/__synthetic_rotate' and self.headers.get('Host','').startswith('127.0.0.1:'):
   app.TOKEN=app.secrets.token_urlsafe(32)
   with app.connect() as c:c.execute('DELETE FROM parent_sessions')
   return self.reply(200,{'ok':True})
  if self.path=='/__synthetic_rotate_token' and self.headers.get('Host','').startswith('127.0.0.1:'):
   app.TOKEN=app.secrets.token_urlsafe(32)
   return self.reply(200,{'ok':True})
  return super().do_GET()
s=app.ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
print(s.server_port,flush=True)
try:s.serve_forever()
except KeyboardInterrupt:pass
finally:s.server_close()
`;
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',code],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let output='',failure='';
 proc.stdout.on('data',x=>output+=String(x));proc.stderr.on('data',x=>failure+=String(x));proc.on('error',e=>failure=e.message);
 const stop=async()=>{if(proc.exitCode===null&&proc.signalCode===null){const exit=once(proc,'exit');proc.kill('SIGINT');await Promise.race([exit,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await exit}}await fs.rm(tmp,{recursive:true,force:true})};
 try{await eventually(()=>{if(proc.exitCode!==null||failure&&!proc.pid)throw Error(failure||'Synthetic server exited');return /^\d+\n/.test(output)},'synthetic server');return{port:Number(output.trim()),stop}}catch(e){await stop();throw e}
}
function forward(port,request){return new Promise((resolve,reject)=>{
 const url=new URL(request.url()),headers={...request.headers(),'host':'family.example.test','x-forwarded-proto':'https','x-forwarded-for':'127.0.0.1','accept-encoding':'identity'};
 delete headers['content-length'];const body=request.postDataBuffer();if(body)headers['content-length']=String(body.length);
 const req=http.request({host:'127.0.0.1',port,path:url.pathname.slice('/family'.length)+url.search,method:request.method(),headers},r=>{
  const chunks=[];r.on('data',x=>chunks.push(x));r.on('error',reject);r.on('end',()=>{
   const out={};for(const [k,v]of Object.entries(r.headers))if(!['content-length','transfer-encoding','connection'].includes(k)&&v!==undefined)out[k]=Array.isArray(v)?v.join('\n'):String(v);
   resolve({status:r.statusCode,headers:out,body:Buffer.concat(chunks)});
  });
 });req.on('error',reject);req.end(body);
})}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page fits viewport');assert.equal(await p.locator('dialog[open]').evaluateAll(xs=>xs.some(x=>x.scrollWidth>x.clientWidth)),false,'dialog fits viewport')}
async function proof(p,name){if(process.env.PARENT_LOGIN_UI_PROOF_DIR){await fs.mkdir(process.env.PARENT_LOGIN_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.PARENT_LOGIN_UI_PROOF_DIR,name+'.png')})}}
async function login(p,value=password){await p.locator('#username').fill('parent');await p.locator('#password').fill(value);await p.locator('#loginSubmit').click()}
async function apiFetchChecks(){
 const source=await fs.readFile(path.join(__dirname,'app.js'),'utf8'),end=source.indexOf('\nlet data,');assert.ok(end>0);
 const old='a'.repeat(43),next='b'.repeat(43),third='c'.repeat(43),options={method:'POST',headers:{'X-Family-Token':'stale-mounted-token'}};
 const setup=fetcher=>{const calls=[],context={URL,Headers,location:{href:home},data:{token:old},showParentLogin:()=>{},fetch:async(url,init)=>{calls.push({url,init});return fetcher()}};vm.createContext(context);vm.runInContext(source.slice(0,end)+'\nglobalThis.checkFetch=apiFetch;',context);return{context,calls}};
 const raw=new Response(JSON.stringify({code:'csrf_expired',token:next}),{status:403}),good=setup(()=>raw);
 assert.equal(await good.context.checkFetch('/api/study/item',options),raw);assert.equal(good.context.data.token,next);assert.equal(good.calls.length,1,'recovery does not replay or fetch state');assert.equal(good.calls[0].init.headers.get('X-Family-Token'),old,'mounted token is updated before sending');assert.equal((await raw.json()).code,'csrf_expired','original response remains readable');
 for(const body of [{code:'forbidden',token:next},{token:next},{code:'csrf_expired',token:'bad'}, {code:'csrf_expired',token:'!'.repeat(43)},{code:'csrf_expired',token:12}]){
  const item=setup(()=>new Response(JSON.stringify(body),{status:403}));await item.context.checkFetch('/api/study/item',options);assert.equal(item.context.data.token,old,'ordinary or malformed errors cannot replace token');
 }
 const malformed=setup(()=>new Response('not json',{status:403}));assert.equal(await(await malformed.context.checkFetch('/api/study/item',options)).text(),'not json');assert.equal(malformed.context.data.token,old);
 const noHeader=setup(()=>new Response(JSON.stringify({code:'csrf_expired',token:next}),{status:403}));await noHeader.context.checkFetch('/api/state');assert.equal(noHeader.context.data.token,old,'a response without a CSRF request cannot replace token');
 let finish;const late=setup(()=>new Promise(resolve=>finish=resolve)),pending=late.context.checkFetch('/api/study/item',options);late.context.data.token=next;finish(new Response(JSON.stringify({code:'csrf_expired',token:third}),{status:403}));await pending;assert.equal(late.context.data.token,next,'late response cannot overwrite newer token');
 return {ordinary403Ignored:true,malformedTokenIgnored:true,lateResponseIgnored:true,responseStillReadable:true,noAutomaticRequests:true};
}
(async()=>{
 let server,browser;const results=[],fetchBoundaries=await apiFetchChecks();
 try{
  server=await service();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const read=async()=>await(await fetch('http://127.0.0.1:'+server.port+'/api/state')).json();
  for(const width of [360,1440]){
   const context=await browser.newContext({viewport:{width,height:820}}),errors=[],studyRequests=[];let writes=0,studyWrites=0,loginRequests=0,stateReads=0,holdLogin=false,heldLogin=null,failState=false;
   context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));
   await context.route('**/*',async route=>{
    try{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==origin||!url.pathname.startsWith('/family/'))return route.abort('blockedbyclient');
    assert.equal(['username','password','token'].some(key=>url.searchParams.has(key)),false,'no credentials in URL');
    if(url.pathname==='/family/api/record'&&request.method()==='POST')writes++;
    if(url.pathname==='/family/api/study/item'&&request.method()==='POST')studyWrites++;
    if(url.pathname==='/family/api/state')stateReads++;
    if(url.pathname==='/family/api/parent/login'){
     if(holdLogin){heldLogin=route;return}
     loginRequests++;assert.equal(request.method(),'POST');assert.equal(request.headers()['origin'],origin);assert.equal(request.headers()['x-family-login'],'1');
     assert.deepEqual(Object.keys(request.postDataJSON()).sort(),['password','username']);
    }
    const headers=await request.allHeaders();
    const response=await forward(server.port,{headers:()=>headers,url:()=>request.url(),method:()=>request.method(),postDataBuffer:()=>request.postDataBuffer()});
    if(url.pathname==='/family/api/study/item'&&request.method()==='POST')studyRequests.push({status:response.status,request:request.postDataJSON(),response:JSON.parse(response.body.toString())});
    if(failState&&url.pathname==='/family/api/state'&&response.status===200){failState=false;await route.fulfill({status:503,json:{error:'虚构临时读取失败'}})}else await route.fulfill(response);
    }catch(error){errors.push(error.message);await route.abort('failed').catch(()=>{})}
   });
   const p=await context.newPage();
   try{
    // Chrome route fulfillment does not intercept the next request after a redirect.
    // Verify the real redirect separately, then navigate the public login destination.
    const redirect=await forward(server.port,{headers:()=>({accept:'text/html'}),url:()=>home,method:()=> 'GET',postDataBuffer:()=>null});
    assert.equal(redirect.status,303);assert.equal(redirect.headers.location,'/family/login');
    await p.goto(home+'login#synthetic-place');await eventually(()=>p.locator('#loginForm').isVisible(),'public login');
    assert.equal(p.url(),home+'login#synthetic-place');await fit(p);
    assert.equal(await p.locator('#password').getAttribute('autocomplete'),'current-password');
    await p.locator('#showPassword').click();assert.equal(await p.locator('#password').getAttribute('type'),'text');
    await p.locator('#showPassword').click();assert.equal(await p.locator('#password').getAttribute('type'),'password');
    await login(p,'synthetic-wrong-password');await eventually(async()=>/账号或密码不正确/.test(await p.locator('#loginStatus').innerText()),'wrong password');
    assert.equal(await p.locator('#username').inputValue(),'parent');await fit(p);
    await login(p);await eventually(()=>p.locator('.today-dashboard').isVisible(),'authenticated home');
    assert.equal(p.url(),home+'#synthetic-place');
    const cookie=(await context.cookies(home)).find(x=>x.name==='family_parent_session');
    assert.ok(cookie&&cookie.secure&&cookie.httpOnly&&cookie.sameSite==='Lax');assert.equal(cookie.path,'/family/');assert.ok(cookie.expires-Date.now()/1000>604700);
    assert.deepEqual(await p.evaluate(()=>({local:localStorage.length,session:sessionStorage.length})),{local:0,session:0});
    const before=(await read()).records.length;
    await p.locator('#add').click();await p.locator('#recordForm [name="title"]').fill('虚构未保存记录 '+width);await p.locator('#recordForm [name="note"]').fill('虚构草稿，登录过期也要保留。');
    await context.addCookies([{name:'family_parent_session',value:'synthetic-expired',domain:'family.example.test',path:'/family/',secure:true,httpOnly:true,sameSite:'Lax'}]);
    await p.locator('#recordForm [type="submit"]').click();await eventually(()=>p.locator('#parentLoginDialog').isVisible(),'expired login prompt');
    await eventually(async()=>await p.locator('#recordForm').getAttribute('data-saving')===null,'failed request completed');
    assert.equal((await read()).records.length,before);assert.equal(writes,1);assert.equal(await p.locator('#recordForm [name="title"]').inputValue(),'虚构未保存记录 '+width);
    await fit(p);
    failState=true;await p.locator('#parentLoginForm [name="username"]').fill('parent');await p.locator('#parentLoginPassword').fill(password);await p.locator('#parentLoginSubmit').click();
    await eventually(async()=>await p.locator('#parentLoginSubmit').innerText()==='重试连接','accepted login with temporary state failure');assert.equal(await p.locator('#parentLoginPassword').inputValue(),'');
    await p.locator('#parentLoginSubmit').click();await eventually(async()=>!(await p.locator('#parentLoginDialog').isVisible()),'inline login resumes original page');
    assert.equal(context.pages().length,1,'re-login needs no new tab');assert.equal(p.url(),home+'#synthetic-place');
    assert.equal(await p.locator('#recordDialog').isVisible(),true);assert.equal(await p.locator('#recordForm [name="title"]').inputValue(),'虚构未保存记录 '+width);assert.equal(await p.locator('#recordForm [name="note"]').inputValue(),'虚构草稿，登录过期也要保留。');
    assert.equal(writes,1,'login never replays a mutation');assert.equal((await read()).records.length,before);
    await p.locator('#recordForm [type="submit"]').click();await eventually(async()=>!(await p.locator('#recordDialog').isVisible()),'explicit retry saved');assert.equal(writes,2);assert.equal((await read()).records.length,before+1);
    // Study retains its mounted token. A web restart changes TOKEN; shared apiFetch must refresh it.
    await p.locator('nav [data-page="study"]').click();await eventually(()=>p.locator('[data-study-ready]').isVisible(),'study ready');
    if(await p.locator('.study-add').getAttribute('open')===null)await p.locator('.study-add>summary').click();
    // A real restart keeps the parent session. Only the CSRF token changes.
    const csrfTitle='虚构连接恢复的作业 '+width,studyForm=p.locator('[data-study-form="new"]');
    await studyForm.locator('[name="title"]').fill(csrfTitle);await studyForm.locator('[name="planned_minutes"]').fill('9');await studyForm.evaluate(el=>el.dataset.syntheticIdentity='keep-this-form');
    const cookieBefore=(await context.cookies(home)).find(c=>c.name==='family_parent_session').value;
    assert.equal((await fetch('http://127.0.0.1:'+server.port+'/__synthetic_rotate_token')).ok,true);
    assert.equal(await p.evaluate(async()=>{const response=await fetch('./api/state');return response.status}),200,'parent session stays valid after token-only rotation');
    const readsBefore=stateReads,postsBefore=studyWrites,requestsBefore=studyRequests.length;
    await studyForm.locator('[type="submit"]').click();await eventually(async()=>studyRequests.length===requestsBefore+1&&await p.locator('[data-study-retry]').isEnabled(),'explicit CSRF retry is offered');
    assert.equal(await p.locator('#studyStatus').evaluate(el=>[...el.childNodes].filter(node=>node.nodeType===Node.TEXT_NODE).map(node=>node.textContent).join('')),'尚未保存，填写已保留。请重试保存。','CSRF rejection is a confirmed non-write');
    assert.equal(studyRequests[requestsBefore].status,403);assert.equal(studyRequests[requestsBefore].response.code,'csrf_expired');assert.equal(studyWrites,postsBefore+1,'no automatic replay');assert.equal(stateReads,readsBefore,'no global state refresh');
    assert.equal(await studyForm.getAttribute('data-synthetic-identity'),'keep-this-form','no global or local form redraw');assert.equal(await studyForm.locator('[name="title"]').inputValue(),csrfTitle);assert.equal(await studyForm.locator('[name="planned_minutes"]').inputValue(),'9');
    assert.equal(await p.locator('#parentLoginDialog').isVisible(),false,'valid cookie needs no login dialog');assert.equal((await context.cookies(home)).find(c=>c.name==='family_parent_session').value,cookieBefore);
    assert.equal(await p.locator('[data-study-retry]').evaluate(el=>{const rect=el.getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight&&rect.left>=0&&rect.right<=innerWidth}),true,'failed save brings retry into the viewport without test scrolling');
    assert.equal(await p.locator('[data-study-retry]').evaluate(el=>document.activeElement===el),true,'retry receives focus after unlocking');
    await fit(p);await p.locator('#toast').waitFor({state:'hidden'});await proof(p,'csrf-retry-'+width);
    await p.locator('[data-study-retry]').click();await eventually(async()=>studyRequests.length===requestsBefore+2&&await p.locator('.study-item h3').filter({hasText:csrfTitle}).count()===1,'explicit original request saved once');
    assert.equal(studyRequests[requestsBefore+1].status,200);assert.deepEqual(studyRequests[requestsBefore+1].request,studyRequests[requestsBefore].request,'request key and body are unchanged');assert.ok(studyRequests[requestsBefore].request.request_key);assert.equal(studyWrites,postsBefore+2);
    const savedSnapshot=await p.evaluate(async()=>{const response=await fetch('./api/study?'+new URLSearchParams({child_id:document.querySelector('[data-study-child]').value,day:document.querySelector('[data-study-date]').value}));return response.json()});assert.equal(savedSnapshot.items.filter(x=>x.title===csrfTitle).length,1,'exactly one persisted study item');
    if(await p.locator('.study-add').getAttribute('open')===null)await p.locator('.study-add>summary').click();
    const sessionWrites=studyWrites;
    await p.locator('[data-study-form="new"] [name="title"]').fill('虚构保留的作业 '+width);await p.locator('[data-study-form="new"] [name="planned_minutes"]').fill('12');
    assert.equal((await fetch('http://127.0.0.1:'+server.port+'/__synthetic_rotate')).ok,true);
    await p.locator('[data-study-form="new"] [type="submit"]').click();await eventually(()=>p.locator('#parentLoginDialog').isVisible(),'mounted token session expired');
    await p.locator('#parentLoginForm [name="username"]').fill('parent');await p.locator('#parentLoginPassword').fill(password);await p.locator('#parentLoginSubmit').click();await eventually(async()=>!(await p.locator('#parentLoginDialog').isVisible()),'restored after token rotation');
    assert.equal(await p.locator('[data-study-form="new"] [name="title"]').inputValue(),'虚构保留的作业 '+width);
    assert.equal(studyWrites,sessionWrites+1,'mounted operation is not automatically replayed');
    const retry=p.locator('[data-study-retry]');if(await retry.count())await retry.click();else await p.locator('[data-study-form="new"] [type="submit"]').click();
    await eventually(async()=>await p.locator('.study-item h3').filter({hasText:'虚构保留的作业 '+width}).count()===1,'mounted old token replaced before explicit retry');
    await p.locator('nav [data-page="more"]').click();await p.locator('[data-parent-logout]').click();await fit(p);
    await p.locator('#parentLogoutConfirm').click();await eventually(()=>p.locator('#loginForm').isVisible(),'logout landing');assert.equal(p.url(),home+'login#synthetic-place');
    assert.equal((await context.cookies(home)).find(x=>x.name==='family_parent_session').value,'logged-out');
    const denied=await forward(server.port,{headers:()=>({accept:'application/json',cookie:'family_parent_session=logged-out'}),url:()=>home+'api/state',method:()=> 'GET',postDataBuffer:()=>null});
    assert.equal(denied.status,401,'logged out cannot read family records');
    assert.equal(loginRequests,4);holdLogin=true;await p.clock.install();await login(p);await eventually(()=>!!heldLogin,'synthetic held login');await p.clock.runFor(15001);
    await eventually(async()=>/超时/.test(await p.locator('#loginStatus').innerText()),'login timeout is readable');assert.equal(await p.locator('#loginSubmit').isEnabled(),true);await heldLogin.abort().catch(()=>{});heldLogin=null;
    assert.deepEqual(errors,[]);results.push({width,realAPI:true,mountPrefix:true,secureCookie:true,wrongPassword:true,draftPreserved:true,inlineLogin:true,stateFailureRetry:true,noAutomaticReplay:true,explicitRetrySaved:true,mountedTokenRefreshed:true,cookieValidTokenRotation:true,sameRequestKeyAndBody:true,noRecoveryRender:true,retryVisibleAndFocused:true,singlePersistedItem:true,logout:true,timeout:true,pageErrors:0});
   }finally{await context.close()}
  }
  const local=await browser.newPage();await local.goto('http://127.0.0.1:'+server.port+'/');await eventually(()=>local.locator('.today-dashboard').isVisible(),'loopback home');await local.locator('nav [data-page="more"]').click();assert.equal(await local.locator('[data-parent-logout]').count(),0);await local.close();
  console.log(JSON.stringify({passed:results.length,results,fetchBoundaries,loopbackUnauthenticated:true,syntheticOnly:true,phoneHardwareTested:false},null,2));
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
