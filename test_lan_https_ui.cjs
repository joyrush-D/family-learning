// Home-network HTTPS through the app's own TLS listener and family certificate.
// Synthetic family, disposable certificate, fake microphone; no phone, model or production URL.
// PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, LAN_HTTPS_UI_PROOF_DIR.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),https=require('node:https');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const host='family-mac.local',password='synthetic-lan-https-password-123';
async function eventually(check,label,ms=10000){const end=Date.now()+ms;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function service(){
 const tmp=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'family-lan-https-ui-'))),env={...process.env};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];env.FAMILY_DATA=path.join(tmp,'private');
 const code=`import json, threading, app, family_access, family_tls
app.read=lambda name: '| child-1 | 示例孩子 | 未填写 | 10岁 | 四年级 |\\n' if name=='家庭运行规则.md' else '# 虚构测试资料\\n'
app.connect().close();app.prepare_assets()
family_tls.issue(app.DATA,['${host}','192.168.50.2'])
secure=app.TLSServer(('127.0.0.1',0),app.Handler,family_tls.server_context(app.DATA))
plain=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
config=family_access.make_config('https://${host}:%d'%secure.server_port,'parent','${password}')
p=app.DATA/'access.json';p.write_text(json.dumps(config));p.chmod(0o600)
threading.Thread(target=plain.serve_forever,daemon=True).start()
print(secure.server_port,plain.server_port,flush=True)
try:secure.serve_forever()
except KeyboardInterrupt:pass
finally:secure.server_close();plain.server_close()
`;
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',code],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let output='',failure='';
 proc.stdout.on('data',x=>output+=String(x));proc.stderr.on('data',x=>failure+=String(x));proc.on('error',e=>failure=e.message);
 const stop=async()=>{if(proc.exitCode===null&&proc.signalCode===null){const exit=once(proc,'exit');proc.kill('SIGINT');await Promise.race([exit,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await exit}}await fs.rm(tmp,{recursive:true,force:true})};
 try{await eventually(()=>{if(proc.exitCode!==null)throw Error(failure||'Synthetic server exited');return /^\d+ \d+\n/.test(output)},'synthetic TLS server');const [securePort,plainPort]=output.trim().split(' ').map(Number);const ca=await fs.readFile(path.join(tmp,'private/tls/ca.crt'));return{securePort,plainPort,ca,stop}}catch(e){await stop();throw e}
}
function fetchTLS(port,ca,pathname,headers={}){return new Promise((resolve,reject)=>{
 const req=https.request({host:'127.0.0.1',port,servername:host,path:pathname,ca,headers:{host:host+':'+port,...headers}},r=>{const chunks=[];r.on('data',x=>chunks.push(x));r.on('end',()=>resolve({status:r.statusCode,headers:r.headers,body:Buffer.concat(chunks)}))});
 req.on('error',reject);req.end();
})}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page fits viewport');assert.equal(await p.locator('dialog[open]').evaluateAll(xs=>xs.some(x=>x.scrollWidth>x.clientWidth)),false,'dialog fits viewport')}
async function proof(p,name){if(process.env.LAN_HTTPS_UI_PROOF_DIR){await fs.mkdir(process.env.LAN_HTTPS_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.LAN_HTTPS_UI_PROOF_DIR,name+'.png')})}}
(async()=>{
 let server,browser;const results=[];
 try{
  server=await service();const origin='https://'+host+':'+server.securePort,home=origin+'/';
  // The family CA verifies the listener outside the browser; the browser maps the .local name to loopback and uses a fake microphone.
  const ca=await fetchTLS(server.securePort,server.ca,'/family-ca.crt');assert.equal(ca.status,200);assert.equal(ca.headers['content-type'],'application/x-x509-ca-cert');assert.equal(ca.body.equals(server.ca),true,'phones download the same CA the listener uses');
  assert.equal((await fetchTLS(server.securePort,server.ca,'/api/state')).status,401,'no family data before login');
  assert.equal((await fetchTLS(server.securePort,server.ca,'/api/state',{'x-forwarded-for':'203.0.113.9'})).status,403,'forwarded requests are not home network clients');
  browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP '+host+' 127.0.0.1','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'],...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const read=async()=>await(await fetch('http://127.0.0.1:'+server.plainPort+'/api/state')).json();
  for(const width of [390,1440]){
   const context=await browser.newContext({viewport:{width,height:844},ignoreHTTPSErrors:true,permissions:['microphone']}),errors=[],requests=[];
   context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));context.on('request',r=>requests.push(r.url()));
   const p=await context.newPage();
   try{
    await p.goto(home+'#lan');await eventually(()=>p.locator('#loginForm').isVisible(),'login page over the family certificate');
    assert.equal(p.url(),origin+'/login#lan');assert.equal(await p.evaluate(()=>window.isSecureContext),true,'a trusted home certificate gives a secure context');
    assert.equal(await p.locator('#certificateHint').isVisible(),true,'home HTTPS shows how to install the certificate');
    assert.equal(await p.locator('#certificateLink').getAttribute('href'),'./family-ca.crt');await fit(p);await proof(p,'login-'+width);
    await p.locator('#username').fill('parent');await p.locator('#password').fill(password);await p.locator('#loginSubmit').click();
    await eventually(()=>p.locator('body[data-page="home"] [data-task-all="todo"]').isVisible(),'authenticated home');
    const cookie=(await context.cookies(home)).find(x=>x.name==='family_parent_session');assert.ok(cookie&&cookie.secure&&cookie.httpOnly&&cookie.sameSite==='Lax');assert.equal(cookie.path,'/');
    assert.equal(await p.evaluate(()=>typeof crypto.randomUUID==='function'&&!!navigator.mediaDevices?.getUserMedia&&!!window.MediaRecorder),true,'recording APIs exist on the home HTTPS page');
    // Browser recording: a real MediaRecorder clip uploads as an original through the family certificate.
    const uploadsBefore=(await read()).uploads.length;
    await p.locator('nav [data-page="more"]').click();await p.locator('#content [data-capture]').click();await eventually(()=>p.locator('#recordDialog').isVisible(),'record dialog');
    await p.locator('#recordAudio').click();await eventually(async()=>/正在录音/.test(await p.locator('#uploadStatus').innerText()),'microphone recording started');await fit(p);await proof(p,'recording-'+width);
    await delay(1500);await p.locator('#recordAudio').click();
    await eventually(async()=>/原件已保存/.test(await p.locator('#uploadStatus').innerText()),'recording uploaded',20000);
    const state=await read();assert.equal(state.uploads.length,uploadsBefore+1,'one uploaded original');assert.match(state.uploads[0].name,/^语音-.*\.(webm|m4a|ogg)$/);
    assert.equal(await p.locator('#pendingUploads [data-detach]').count(),1,'the clip is attached to the draft record');
    await p.locator('#recordForm [data-close="recordDialog"]').click().catch(()=>{});
    // Calendar subscription: the address is offered because the page itself is HTTPS.
    await p.locator('nav [data-page="calendar"]').click();await eventually(()=>p.locator('.calendar-tools').isVisible(),'calendar tools');
    await p.locator('.calendar-tools>summary').click();await p.locator('[data-calendar-sync]').click();await eventually(()=>p.locator('#calendarSyncDialog').isVisible(),'sync dialog');
    assert.equal(await p.locator('#calendarSyncURL').inputValue(),origin+'/calendar.ics');assert.equal(await p.locator('#calendarSyncCopy').isEnabled(),true);
    assert.match(await p.locator('#calendarSyncStatus').innerText(),/复制地址后/);await fit(p);await proof(p,'calendar-sync-'+width);
    const ics=await fetchTLS(server.securePort,server.ca,'/calendar.ics',{authorization:'Basic '+Buffer.from('parent:'+password).toString('base64')});assert.equal(ics.status,200);assert.match(ics.body.toString(),/BEGIN:VCALENDAR/);
    await p.locator('#calendarSyncDialog [data-close="calendarSyncDialog"]').click();
    // Saved state survives reopening, and logout ends the session on this device only.
    await p.reload();await eventually(()=>p.locator('body[data-page="home"] [data-task-all="todo"]').isVisible(),'home after reload keeps the session');
    assert.equal((await read()).uploads.length,uploadsBefore+1);
    await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="sources"]').click();await eventually(async()=>/语音-/.test(await p.locator('#content').innerText()),'the recorded original is listed under pending materials after reopening');await fit(p);await proof(p,'reopened-'+width);
    await p.locator('nav [data-page="more"]').click();await p.locator('[data-parent-logout]').click();await p.locator('#parentLogoutConfirm').click();await eventually(()=>p.locator('#loginForm').isVisible(),'logout landing');
    assert.equal((await fetchTLS(server.securePort,server.ca,'/api/state',{cookie:'family_parent_session='+cookie.value})).status,401,'logged-out session is rejected');
    assert.equal(requests.some(url=>!url.startsWith(origin)),false,'the page talks only to the home entry');
    assert.deepEqual(errors,[]);results.push({width,secureContext:true,certificateHint:true,secureCookie:true,browserRecordingUploaded:true,calendarSubscriptionOffered:true,calendarAuthenticated:true,reloadKeepsData:true,logout:true,pageErrors:0});
   }catch(error){await proof(p,'failure-'+width).catch(()=>{});throw error}finally{await context.close()}
  }
  console.log(JSON.stringify({passed:results.length,results,loopbackHTTPUnchanged:(await read()).children.length===1,syntheticOnly:true,realPhoneTested:false,realCAInstallTested:false},null,2));
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
