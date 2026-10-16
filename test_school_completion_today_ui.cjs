// Synthetic Today check for own-original completion days. Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON, TODAY_UI_PROOF_DIR. No production URL, model or device calls.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');

async function eventually(check,label,timeout=10000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function demoServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');
 const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const url='http://127.0.0.1:'+port+'/',env={...process.env};
 for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});
 let failure;child.on('error',e=>failure=e);child.stdout.resume();child.stderr.resume();
 const stop=async()=>{if(failure||child.exitCode!==null||child.signalCode!==null)return;const exited=once(child,'exit');child.kill('SIGINT');await Promise.race([exited,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await exited}};
 try{await eventually(async()=>{if(failure)throw failure;if(child.exitCode!==null)throw Error('Synthetic demo exited');try{return (await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'temporary demo startup');return {url,stop}}catch(e){await stop();throw e}
}

(async()=>{
 let server,browser;
 try{
  server=await demoServer();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const base=await(await fetch(server.url+'api/state')).json(),first=base.children[0],today='2026-10-07';
  const task=(id,title,action,complete_on,due_on)=>({id,child:first.name,title,due:due_on,original_status:'待跟进',source:'虚构班级群',action,history:[],
   agenda:{category:'homework',published_on:today,published_at:today+'T19:00:00+08:00',due_on,due_kind:'deadline',complete_on,scheduled_on:'',box:'inbox'}});
  const tasks=[task('RECITE','语文：背诵《秋夜》第2自然段','背诵《秋夜》第2自然段。\n明天早读接受抽查。',today,'2026-10-08'),
   task('COPY','英语：抄写Unit 3单词两遍','今晚把Unit 3单词每个抄写两遍。\n明天交。',today,'2026-10-08'),
   task('ORAL','数学：完成口算本第8页','口算本第8页全部完成。\n明天交给课代表。','','2026-10-08')];
  const state={...base,today,tasks,agent:{...base.agent,items:[]},today_calendar:{inbox:tasks.map(t=>({id:t.id,task_id:t.id,kind:'task',child_ids:[first.id],title:t.title,closed:false,status:'待跟进',agenda:t.agenda})),agenda:[],events:[],timetables:[],source_error:''}};
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.route('**/api/state',route=>route.fulfill({json:state}));
    for(const pass of ['open','reopen']){
     if(pass==='open')await p.goto(server.url,{waitUntil:'load'});else await p.reload({waitUntil:'load'});
     await eventually(async()=>await p.locator('body[data-page="home"] #task-group-homework').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','Today ready');
     const todayGroup=p.locator('#task-group-homework'),card=(scope,id)=>scope.locator('[data-query-target="task:'+id+'"]');
     assert.match(await todayGroup.locator('h2').innerText(),/今日作业 · 2/,'today and tonight work is counted once each');
     for(const id of ['RECITE','COPY']){
      assert.equal(await card(p,id).count(),1,id+' appears once');assert.equal(await card(todayGroup,id).isVisible(),true,id+' is directly in Today');
      assert.match(await card(todayGroup,id).locator('.agenda-dates').innerText(),/今天完成：2026-10-07[\s\S]*截止：2026-10-08/,id+' shows both roles in the first layer');
     }
     assert.equal(await card(todayGroup,'ORAL').count(),0,'only a handback day is not guessed as today');
     assert.match(await p.locator('.today-recent-homework').innerText(),/数学：完成口算本第8页[\s\S]*截止：2026-10-08/);
     assert.doesNotMatch(await card(p,'ORAL').locator('.agenda-dates').innerText(),/完成：/);
     assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');
    }
    if(process.env.TODAY_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.TODAY_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.TODAY_UI_PROOF_DIR,'completion-today-'+width+'.png'),fullPage:true})}
    assert.deepEqual(errors,[]);
   }finally{await p.close()}
  }
  // H01 as the app itself saved it (run_once -> stored task -> state/calendar snapshot), not hand-written agenda data.
  const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
  const file=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'school-h01-')),'state.json');
  const made=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_school_completion_today.py','--saved-h01-state',file],{cwd:__dirname,stdio:['ignore','ignore','inherit']});
  const [code]=await once(made,'exit');assert.equal(code,0,'saved H01 state');
  const saved=JSON.parse(fs.readFileSync(file,'utf8'));assert.equal(saved.tasks.length,1,'one saved task');
  const h01=saved.tasks[0];assert.equal(h01.due,'2026-10-20');
  for(const width of [360,1440])for(const [day,inToday,label] of [['2026-10-16',false,/完成：2026-10-18[\s\S]*截止：2026-10-20/],['2026-10-18',true,/今天完成：2026-10-18[\s\S]*截止：2026-10-20/],['2026-10-20',true,/完成：2026-10-18[\s\S]*截止：2026-10-20/]]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.route('**/api/state',route=>route.fulfill({json:{...base,children:saved.children,today:day,tasks:saved.tasks,agent:{...base.agent,items:[]},today_calendar:saved.saved_calendars[day]}}));
    await p.goto(server.url,{waitUntil:'load'});
    await eventually(async()=>await p.locator('body[data-page="home"] #task-group-homework').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','Today ready '+day);
    const card=scope=>scope.locator('[data-query-target="task:'+h01.id+'"]');
    assert.equal(await card(p).count(),1,day+' the saved task appears once');
    assert.equal(await card(p.locator('#task-group-homework')).count(),inToday?1:0,day+' first-layer Today only on its work and handback days');
    assert.match(await card(p).locator('.agenda-dates').innerText(),label,day+' both roles with the original handback due');
    assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');
    assert.deepEqual(errors,[]);
   }finally{await p.close()}
  }
  console.log('PASS: own today/tonight work is in Today once with its completion and handback days; handback-only work stays in other homework');
  console.log('PASS: saved H01 is in Today once on 2026-10-18 (work) and 2026-10-20 (handback), not on 2026-10-16');
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e);process.exit(1)});
