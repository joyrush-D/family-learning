// Real native acceptance of the Mac SwiftUI workbench: builds the app from the committed sources into a fresh directory, serves
// Root's frozen fictional whole day through the real app server (test_daily_list_whole_day.py --serve-actual) behind a test-only
// parent login (the loopback fixture alone admits every local request): the real login page and login.js, an HttpOnly host-only
// session cookie and server-side expiry on demand. The app runs in --smoke-test with its own support directory and a
// non-persistent web data store (the user's default cookies are never read). Every step finds a control through the app's
// accessibility tree or its probe anchor, scrolls its real scroll view to it when needed and posts a real mouse or key event
// there (no DOM for the workbench, no store action called directly); text checks accept only text shown in the window.
// Then the server's own saved rows are read back: one feedback per request despite a lost reply, a failed send and an expired
// session (login from the open sheet, the same draft and request retried by hand), the wrong note and its correction on the
// same task, the oral addition source-signed with its subject and words each in its own field and its teacher date unknown,
// and nothing on the other child.
// The fixture is imported rather than run as a script: a system Python 3.9 misreads that file's long UTF-8 lines as a script.
// Usage: node test_native_workspace.cjs   Optional: FAMILY_TEST_PYTHON, NATIVE_WORKSPACE_OUT (keeps build, logs, screenshots).
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),http=require('node:http'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const out=process.env.NATIVE_WORKSPACE_OUT||fs.mkdtempSync(path.join(os.tmpdir(),'grove-native-'));fs.mkdirSync(out,{recursive:true});
async function freePort(){const s=net.createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p}
// Test-only parent login in front of the fixture; every other request passes through unchanged (the app's own CSRF and guards).
function loginProxy(appPort,user,password){
 const sessions=new Set(),seen=[];
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1'),chunks=[];req.on('data',d=>chunks.push(d));
  req.on('end',()=>{
   const body=Buffer.concat(chunks),sid=(req.headers.cookie||'').split(';').map(s=>s.trim()).filter(s=>s.startsWith('family_parent_session=')).map(s=>s.slice(22))[0]||'';
   let key='';if(req.method==='POST'){try{key=JSON.parse(body.toString()).request_key||''}catch{}}
   const note=status=>seen.push({method:req.method,path:url.pathname,status,key});
   const json=(code,obj,headers={})=>{note(code);res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',...headers});res.end(JSON.stringify(obj))};
   if(url.pathname==='/__fixture/expire'){sessions.clear();return json(200,{ok:true})}
   if(url.pathname==='/api/parent/login'&&req.method==='POST'){let o={};try{o=JSON.parse(body.toString())}catch{}
    if(req.headers['x-family-login']!=='1'||o.username!==user||o.password!==password)return json(401,{error:'用户名或密码不正确'});
    const id=crypto.randomBytes(32).toString('base64url');sessions.add(id);
    return json(200,{ok:true},{'Set-Cookie':`family_parent_session=${id}; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600`})}
   if(url.pathname==='/api/parent/logout'&&req.method==='POST'){sessions.delete(sid);return json(200,{ok:true},{'Set-Cookie':'family_parent_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'})}
   // The app serves its login page only for configured hosts, never for this loopback fixture: serve the repository's own
   // login.html and login.js here under the app's CSP, so the real form and script do the login.
   if(req.method==='GET'&&(url.pathname==='/login'||url.pathname==='/login.js')){const js=url.pathname==='/login.js';note(200);
    res.writeHead(200,{'Content-Type':js?'text/javascript; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
     'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"});
    return res.end(fs.readFileSync(path.join(__dirname,js?'login.js':'login.html')))}
   // Pages and scripts load for anyone (the page asks for login itself); data and uploads need the session.
   if((url.pathname.startsWith('/api/')||url.pathname.startsWith('/upload'))&&!sessions.has(sid))return json(401,{error:'需要登录'});
   const up=http.request({host:'127.0.0.1',port:appPort,method:req.method,path:req.url,headers:req.headers},r=>{note(r.statusCode);res.writeHead(r.statusCode,r.headers);r.pipe(res)});
   up.on('error',()=>{note(502);if(!res.headersSent)res.writeHead(502);res.end()});up.end(body)})});
 return {server,seen};
}
(async()=>{
 const app=execFileSync('sh',[path.join(__dirname,'packaging/macos/build.sh'),path.join(out,'build')],{encoding:'utf8'}).trim().split('\n').pop();
 const port=await freePort(),fixtureOrigin=`http://127.0.0.1:${port}`,USER='fictional-parent',PASS='fictional-'+crypto.randomUUID(),auth=loginProxy(port,USER,PASS);
 const env0={...process.env};for(const k of Object.keys(env0))if(k.startsWith('FAMILY_'))delete env0[k];
 const fixture=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-B','-c','import sys,test_daily_list_whole_day as w;w.serve_actual(int(sys.argv[1]))',String(port)],{cwd:__dirname,env:env0,stdio:['ignore','ignore','inherit']});
 const stopFixture=async()=>{auth.server.close();if(fixture.exitCode!==null)return;const d=once(fixture,'exit');fixture.kill('SIGINT');await Promise.race([d,delay(3000)]);if(fixture.exitCode===null)fixture.kill('SIGKILL')};
 try{
  auth.server.listen(0,'127.0.0.1');await once(auth.server,'listening');const origin=`http://127.0.0.1:${auth.server.address().port}`;
  for(let n=0;;n++){try{if((await fetch(fixtureOrigin+'/',{signal:AbortSignal.timeout(500)})).ok)break}catch{}if(n>400)throw Error('fixture not up');await delay(50)}
  const day=async(child)=>(await (await fetch(fixtureOrigin+'/api/day'+(child?'?child_id='+encodeURIComponent(child):''))).json());
  const first=await day(''),children=first.children;assert.ok(children.length>=2,'two fictional children');
  const views=await Promise.all(children.map(c=>day(c.id))),count=v=>v.groups.flatMap(g=>g.items).length;
  const mine=views.reduce((a,b)=>count(b)>count(a)?b:a),other=views.find(v=>v.child_id!==mine.child_id);
  const childIndex=children.findIndex(c=>c.id===mine.child_id),otherIndex=children.findIndex(c=>c.id===other.child_id);
  const item=mine.groups.flatMap(g=>g.items).find(i=>i.kind==='task'&&/跟读/.test(i.title))||mine.groups.flatMap(g=>g.items).find(i=>i.kind==='task');
  const math=mine.groups.flatMap(g=>g.items).find(i=>(i.facts||[]).some(f=>f.state==='next_morning')),tomorrow=math&&math.facts.find(f=>f.state==='next_morning');
  assert.ok(math,'the fixture has an item due tomorrow');
  const NOTE1='虚构反馈一：跟读已完成，家长听过。',NOTE2='虚构反馈二：照片没加，只写文字。',ORAL='虚构口头：背诵Unit 7课文',WRONG='虚构第3题',NOTE3='虚构反馈三：登录过期后重新登录，同一份草稿再保存。';
  const steps=[
   // Initial login from the workbench: the service's own login page in a login window; the window closes and the list reloads.
   {name:'login needed',until:'login-needed',timeout:20},{name:'login open',click:'login-open'},{name:'web login',native:'web_login'},
   {name:'list',until:'list-summary',contains:'共',timeout:20},{name:'login state',native:'state'},
   {name:'pick child',key:String(childIndex+1),modifiers:['command']},
   {name:'row',click:'row-'+item.id},{name:'detail',until:'detail-title',contains:item.title.slice(0,4)},
   {name:'wide',width:1440,native:'snapshot'},
   {name:'feedback open',click:'feedback-new'},{name:'feedback sheet',until:'feedback-note'},
   {name:'focus note',click:'feedback-note'},{name:'type note',type:NOTE1},
   {name:'esc stays',key:'\u001b',code:53},{name:'still dirty',native:'dirty'},
   {name:'lose reply',faults:['drop_reply']},{name:'save 1',click:'sheet-save'},
   {name:'unknown receipt',until:'sheet-status',contains:'不确定是否已保存'},
   {name:'draft-safe close/quit',native:'close_attempts'},
   {name:'retry same request',click:'sheet-save'},{name:'saved 1',find_text:NOTE1,timeout:15},
   {name:'feedback again',click:'feedback-new'},{name:'focus 2',click:'feedback-note'},{name:'type 2',type:NOTE2},
   {name:'fail send',faults:['fail_before_send']},{name:'save 2',click:'sheet-save'},
   {name:'not sent',until:'sheet-status',contains:'没有保存'},{name:'retry 2',click:'sheet-save'},{name:'saved 2',find_text:NOTE2,timeout:15},
   // The session expires on the server while a draft is open: the open sheet offers the login itself; the same draft and request are retried by hand.
   {name:'feedback 3',click:'feedback-new'},{name:'focus 3',click:'feedback-note'},{name:'type 3',type:NOTE3,into:'feedback-note'},
   {name:'expire',native:'fixture_get',path:'/__fixture/expire'},{name:'save 3',click:'sheet-save'},
   {name:'relogin asked',until:'sheet-login'},{name:'expired state',native:'state'},{name:'relogin',click:'sheet-login'},{name:'web relogin',native:'web_login'},
   {name:'relogged',until:'sheet-status',contains:'已重新登录',timeout:15},{name:'relogged state',native:'state'},
   {name:'retry 3',click:'sheet-save'},{name:'saved 3',find_text:NOTE3,timeout:15},
   {name:'wrong open',click_prefix:'wrong-new-'},{name:'wrong label',click:'wrong-label'},{name:'type wrong',type:WRONG},
   {name:'save wrong',click:'sheet-save'},{name:'wrong saved',find_text:WRONG,timeout:15},
   {name:'correct open',click_prefix:'wrong-correct-'},{name:'correct note',click:'correction-note'},{name:'type correction',type:'虚构：已订正。'},
   {name:'save correction',click:'sheet-save'},{name:'corrected',find_text:'已订正',timeout:15},
   {name:'detail snapshot',native:'snapshot'},
   {name:'reopen',native:'reopen'},{name:'reopened feedback',find_text:NOTE1,timeout:15},{name:'reopened correction',find_text:'已订正',timeout:15},
   {name:'oral open',key:'n',modifiers:['command']},{name:'oral sheet',until:'oral-subject'},
   // In the order a parent fills it: each string must land in its own field, exactly (the old focus binding pulled both into the subject).
   {name:'oral subject',click:'oral-subject'},{name:'type subject',type:'英语',into:'oral-subject'},
   {name:'oral what',click:'oral-what'},{name:'type what',type:ORAL,into:'oral-what'},{name:'oral snapshot',native:'snapshot'},
   {name:'save oral',click:'sheet-save'},{name:'oral listed',find_text:ORAL,timeout:15},
   {name:'other child',key:String(otherIndex+1),modifiers:['command']},{name:'other state',native:'state'},
   {name:'isolation',find_text:NOTE1,absent:true,timeout:8},
   {name:'back',key:String(childIndex+1),modifiers:['command']},
   {name:'next day',key:']',modifiers:['command']},{name:'next state',native:'state'},
   {name:'today',key:'t',modifiers:['command']},{name:'today state',native:'state'},
   // A tomorrow date is shown as 明天+its own role word, never an invented 明早.
   {name:'tomorrow row',click:'row-'+math.id},{name:'tomorrow words',until:'fact-'+tomorrow.role,contains:tomorrow.label+' 明天'},{name:'no invented morning',find_text:'明早',absent:true,timeout:3},
   {name:'narrow',width:900,native:'snapshot'},
   {name:'web tools for the same task',click:'row-'+item.id},{name:'check entry',click:'check-web'},{name:'web state',native:'state'}];
  const stepsFile=path.join(out,'native-steps.json');fs.writeFileSync(stepsFile,JSON.stringify(steps));
  const shots=path.join(out,'shots');fs.mkdirSync(shots,{recursive:true});
  const support=fs.mkdtempSync(path.join(os.tmpdir(),'grove-native-support-'));
  const env={...env0,FAMILY_DESKTOP_SUPPORT_DIR:support,FAMILY_DESKTOP_TEST_ORIGIN:origin,FAMILY_DESKTOP_TEST_SETUP_INPUTS:JSON.stringify([origin]),
   FAMILY_DESKTOP_TEST_SURFACE:'native',FAMILY_DESKTOP_TEST_LOGIN:JSON.stringify([USER,PASS]),FAMILY_DESKTOP_TEST_NATIVE_STEPS:stepsFile,FAMILY_DESKTOP_TEST_SNAPSHOT_DIR:shots,FAMILY_DESKTOP_SMOKE_HOLD:'1'};
  const proc=spawn(path.join(app,'Contents/MacOS/YiqiChengzhang'),['--smoke-test'],{env,stdio:['ignore','pipe','pipe']});
  let text='';proc.stdout.on('data',d=>{text+=d;fs.appendFileSync(path.join(out,'native.jsonl'),d)});proc.stderr.on('data',d=>fs.appendFileSync(path.join(out,'native.stderr.log'),d));
  const done=once(proc,'exit');const killer=setTimeout(()=>proc.kill('SIGKILL'),420000);const [code]=await done;clearTimeout(killer);
  const lines=text.split('\n').filter(Boolean).map(l=>{try{return JSON.parse(l)}catch{return {raw:l}}});
  const final=lines.find(l=>l.state==='native_loaded');
  assert.ok(final,'native run finished: '+lines.slice(-3).map(l=>JSON.stringify(l).slice(0,400)).join('\n'));
  const failed=final.steps.filter(s=>s.result.ok===false);assert.deepEqual(failed,[],'native steps');
  const r=Object.fromEntries(final.steps.map(s=>[s.name,s.result]));
  assert.equal(r['still dirty'].dirty,true,'Esc on a dirty sheet keeps editing');
  assert.match(r['list'].text,/以后安排 2/);assert.ok(!/以后交|明早/.test(r['list'].text),'no invented handback or morning in the summary: '+r['list'].text);
  assert.equal(r['login state'].login_required,false);assert.equal(r['login state'].login_window,false,'the login window closed itself after login');
  assert.equal(r['expired state'].login_required,true);assert.ok(r['expired state'].sheet.startsWith('feedback-'));assert.equal(r['expired state'].dirty,true);
  assert.equal(r['relogged state'].sheet,r['expired state'].sheet,'the same sheet stayed open through the login');assert.equal(r['relogged state'].dirty,true,'its draft stayed');
  assert.equal(r['relogged state'].login_window,false);assert.equal(r['relogged state'].login_required,false);
  assert.equal(r['type subject'].field,'英语');assert.equal(r['type what'].field,ORAL,'each oral string only in its own field');
  assert.ok(lines.filter(l=>l.state==='login_opened').length>=2&&lines.filter(l=>l.state==='login_returned').length>=2,'two logins, each back on the same workbench');
  const posts=auth.seen.filter(s=>s.method==='POST'&&s.path==='/api/task/feedback'),refused=posts.filter(s=>s.status===401);
  assert.equal(refused.length,1,'the expired session refused one feedback post before any write');
  const later=posts.slice(posts.indexOf(refused[0])+1);assert.ok(later.length===1&&later[0].key===refused[0].key&&later[0].status<300,'one manual retry, same request key: '+JSON.stringify(later));
  const leave=r['draft-safe close/quit'];
  assert.equal(leave.dirty,true);assert.equal(leave.window_open_after_close,true);
  assert.equal(leave.quit_key_posted,true,'a real Command-Q was posted to the active sheet');
  assert.equal(leave.quit_key_window,true,'the quit shortcut reached the app own key window');
  assert.equal(leave.window_open_after_quit,true);assert.equal(leave.still_dirty,true,'Command-Q did not discard the draft');
  // A native modal may stop Command-Q before applicationShouldTerminate. Never invent its callback;
  // the subsequent real retry and exact saved-note/key readback below still have to pass.
  assert.ok(['cancelled','none'].includes(leave.quit_reply),'the app did not approve termination: '+leave.quit_reply);
  assert.ok(final.events.some(e=>e.discard_prompt),'the discard prompt defaulted to keep editing');
  assert.equal(r['other state'].child,other.child_id);assert.notEqual(r['next state'].day,r['today state'].day);assert.equal(r['today state'].day,first.today);
  assert.equal(r['web state'].web_visible,true,'the existing check entry opens the same task in the web tools');
  assert.equal(final.isolation.support_is_default,false);
  // The server's own rows: one record per request, wrong note and correction on the same task, oral addition signed, other child untouched.
  const after=await day(mine.child_id),row=after.groups.flatMap(g=>g.items).concat(after.closed.flatMap(g=>g.items)).find(i=>i.id===item.id);
  assert.deepEqual(row.records.map(x=>x.note).filter(n=>n.startsWith('虚构反馈')),[NOTE1,NOTE2,NOTE3]);
  assert.equal(row.wrong.length,1);assert.ok(row.wrong[0].title.includes(WRONG));assert.equal(row.wrong[0].state,'已订正');
  assert.equal(row.closed,false,'words and wrong notes never mark the task done');
  const oral=after.groups.flatMap(g=>g.items).find(i=>i.title.includes(ORAL));assert.ok(oral,'oral addition listed');
  assert.equal(oral.origin,'oral');assert.equal(oral.subject,'英语');assert.equal(oral.facts.find(f=>f.role==='due').known,false,'teacher date stays unknown');
  const theirs=await day(other.child_id);assert.ok(!JSON.stringify(theirs).includes('虚构'),'nothing reached the other child');
  console.log(JSON.stringify({ok:true,app_exit:code,steps:final.steps.length,out,shots:fs.readdirSync(shots)}));
 }finally{await stopFixture()}
})().catch(e=>{console.error(e);process.exit(1)});
