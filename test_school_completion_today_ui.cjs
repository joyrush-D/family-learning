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
  // The fictional Flash27 day as run_once saved it (7 originals, 3 homework + 2 todo): each card reads title, its own
  // conditions once and its date roles; the saved words, teacher, originals, gap and missing timetable stay.
  const flashFile=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'school-flash27-')),'state.json');
  const flashMade=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_school_completion_today.py','--saved-flash27-state',flashFile],{cwd:__dirname,stdio:['ignore','ignore','inherit']});
  const [flashCode]=await once(flashMade,'exit');assert.equal(flashCode,0,'saved Flash27 state');
  const flash=JSON.parse(fs.readFileSync(flashFile,'utf8')),ids=flash.flash27_ids;assert.equal(flash.tasks.length,5,'five saved actions');
  const lines={'星芽':['答案写在练习册上。','今晚完成，明天早上交练习册。'],'数格':['第34页第4题要把计算过程写完整，写在原题下面即可。','今晚完成，明天早上交练习册。'],
   'Unit 4':['听录音跟读 Unit 4 A day at the lake 两遍。','读完请家长在记录本上签字。','今晚完成，明天早读检查记录本。'],
   '回执':['《秋季校园开放日回执》今晚请家长签字。','明天早上让孩子交给班主任。'],'塑料瓶':['明天来校带一个空透明塑料瓶，科学课用。']};
  const teacher={'星芽':'虚构语文许老师','数格':'虚构数学魏老师','Unit 4':'虚构英语乔老师','回执':'虚构班主任温老师','塑料瓶':'虚构班主任温老师'};
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.route('**/api/state',route=>route.fulfill({json:{...base,children:flash.children,sources:flash.sources,today:'2026-10-19',tasks:flash.tasks,records:flash.records,agent:{...flash.agent,items:[]},today_calendar:flash.saved_calendar}}));
    for(const pass of ['open','reopen','list']){
     if(pass==='open')await p.goto(server.url,{waitUntil:'load'});else await p.reload({waitUntil:'load'});
     await eventually(async()=>await p.locator('body[data-page="home"] #task-group-homework').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','Flash27 Today ready');
     if(pass==='list'){await p.locator('[data-task-all="homework"]').click();await eventually(async()=>/所有作业与待办/.test(await p.locator('#content h1').first().innerText()),'all homework and todo list')}
     else{
      assert.match(await p.locator('#task-group-homework h2').innerText(),/今日作业 · 3/);assert.match(await p.locator('#task-group-todo h2').innerText(),/要办的事 · 2/);
      assert.match(await p.locator('#today-courses').innerText(),/当天课表尚未提供/,'the missing timetable stays said');
     }
     for(const [key,want] of Object.entries(lines)){
      const card=p.locator('[data-query-target="task:'+ids[key]+'"]'),saved=flash.tasks.find(t=>t.id===ids[key]);
      assert.equal(await card.count(),1,key+' one card');
      assert.equal(await card.locator('h3').innerText(),saved.title,key+' title as saved');
      assert.deepEqual(await card.locator('.task-requirement li, p.task-requirement').allInnerTexts(),want,pass+' '+width+' '+key+' each own condition once');
      const text=await card.innerText();
      assert.doesNotMatch(text,/提交要求/,key+' no restated handback line');
      // Only where the first saved line is the title itself; the bottle's line overlaps its title in part and stays whole.
      if(['星芽','数格'].includes(key))assert.equal(text.split(saved.title.replace(/^[^：]+：/,'')).length-1,1,key+' the title words appear once');
      assert.match(text,new RegExp(teacher[key]),key+' teacher kept by the originals');
      const dates=await card.locator('.agenda-dates').innerText();
      assert.match(dates,/发布：2026-10-19 1\d:\d\d/,key+' publication time');
      if(key==='塑料瓶')assert.doesNotMatch(dates,/完成：/,'the bottle borrows no completion day');else assert.match(dates,/完成：2026-10-19[\s\S]*截止：2026-10-20/,key+' completion and handback/check days');
      assert.match(dates,/截止：2026-10-20/);
     }
     assert.deepEqual(await p.locator('[data-query-target="task:'+ids['数格']+'"] [data-school-original-ref]').allInnerTexts(),['原件 1','原件 2'],'both math originals');
     assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');
    }
    if(process.env.TODAY_UI_PROOF_DIR){await p.reload({waitUntil:'load'});await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','proof ready');await p.screenshot({path:path.join(process.env.TODAY_UI_PROOF_DIR,'flash27-today-'+width+'.png'),fullPage:true})}
    assert.deepEqual(errors,[]);
   }finally{await p.close()}
  }
  // The R09 recovered day: English 34 saved as one paragraph by the ordinary run_once reread of a fixed reply (mocked
  // transport). Its card reads its own sentences under its title; the four other cards read as above.
  const recoveredFile=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'school-recovered-')),'state.json');
  const recoveredMade=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_school_completion_today.py','--saved-recovered-state',recoveredFile],{cwd:__dirname,stdio:['ignore','ignore','inherit']});
  const [recoveredCode]=await once(recoveredMade,'exit');assert.equal(recoveredCode,0,'saved recovered state');
  const recovered=JSON.parse(fs.readFileSync(recoveredFile,'utf8')),rid=recovered.recovered_ids,paragraph='英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。';
  assert.equal(recovered.tasks.find(t=>t.id===rid['Unit 4']).action,paragraph,'the saved paragraph as the reread stored it');
  const recoveredLines={...lines,'Unit 4':['听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。','今晚完成，明天早读检查记录本。']};
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.route('**/api/state',route=>route.fulfill({json:{...base,children:recovered.children,sources:recovered.sources,today:'2026-10-19',tasks:recovered.tasks,records:recovered.records,agent:{...recovered.agent,items:[]},today_calendar:recovered.saved_calendar}}));
    for(const pass of ['open','reopen','list']){
     if(pass==='open')await p.goto(server.url,{waitUntil:'load'});else await p.reload({waitUntil:'load'});
     await eventually(async()=>await p.locator('body[data-page="home"] #task-group-homework').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','recovered Today ready');
     if(pass==='list'){await p.locator('[data-task-all="homework"]').click();await eventually(async()=>/所有作业与待办/.test(await p.locator('#content h1').first().innerText()),'all homework and todo list')}
     else{assert.match(await p.locator('#task-group-homework h2').innerText(),/今日作业 · 3/);assert.match(await p.locator('#task-group-todo h2').innerText(),/要办的事 · 2/)}
     for(const [key,want] of Object.entries(recoveredLines)){
      const card=p.locator('[data-query-target="task:'+rid[key]+'"]'),saved=recovered.tasks.find(t=>t.id===rid[key]);
      assert.equal(await card.count(),1,key+' one card');assert.equal(await card.locator('h3').innerText(),saved.title);
      assert.deepEqual(await card.locator('.task-requirement li, p.task-requirement').allInnerTexts(),want,pass+' '+width+' '+key+' recovered card lines');
      const text=await card.innerText();assert.match(text,new RegExp(teacher[key]));
      if(key==='Unit 4'){assert.equal(text.split('英语：').length-1,1,'the subject label only in the heading');assert.match(await card.locator('.agenda-dates').innerText(),/完成：2026-10-19[\s\S]*截止：2026-10-20/)}
     }
     assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');
    }
    if(process.env.TODAY_UI_PROOF_DIR){await p.goto(server.url,{waitUntil:'load'});await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','proof ready');await p.screenshot({path:path.join(process.env.TODAY_UI_PROOF_DIR,'recovered-today-'+width+'.png'),fullPage:true})}
    assert.deepEqual(errors,[]);
   }finally{await p.close()}
  }
  console.log('PASS: own today/tonight work is in Today once with its completion and handback days; handback-only work stays in other homework');
  console.log('PASS: saved H01 is in Today once on 2026-10-18 (work) and 2026-10-20 (handback), not on 2026-10-16');
  console.log('PASS: saved Flash27 day shows each own condition once under its title with its date roles, teacher and originals, open/reopen/list at 360 and 1440');
  console.log('PASS: the R09 recovered English paragraph reads as its own sentences under its title, the other four as before, open/reopen/list at 360 and 1440');
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e);process.exit(1)});
