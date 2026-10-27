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
  // T02 as the real run_once saved it in a disposable Store, read through the real app HTTP server on 2026-11-04; the page
  // writes nothing. Tomorrow's PE rope reads its lesson's 安排日 (no 截止/交回/完成/计划), tonight's English keeps its own day.
  // T06's text saved beside it (date only, not the whole T06: its attachment stays unread) reads the same 安排日 with its own words.
  {
   const probe=net.createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');const port=probe.address().port;await new Promise(r=>probe.close(r));
   const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
   const t02=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_daily_list_frozen.py','--serve-t02',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});
   let err='';t02.stdout.resume();t02.stderr.on('data',b=>err=(err+b).slice(-4000));
   const url='http://127.0.0.1:'+port+'/';
   try{
    await eventually(async()=>{if(t02.exitCode!==null)throw Error('T02 Store server exited: '+err);try{return (await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'T02 Store server',30000);
    assert.equal((await(await fetch(url+'api/state')).json()).today,'2026-11-04','served as of the contract day');
    for(const width of [360,1440]){
     const p=await browser.newPage({viewport:{width,height:820}}),errors=[],writes=[];
     p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()!=='GET')writes.push(r.method()+' '+r.url())});
     try{
      for(const pass of ['open','reopen','list','calendar']){
       if(pass==='open')await p.goto(url,{waitUntil:'load'});else if(pass==='reopen')await p.reload({waitUntil:'load'});
       if(pass!=='calendar')await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','T02 '+pass+' ready');
       if(pass==='list'){await p.locator('nav [data-page="tasks"]').click();await p.locator('[data-task-box="全部"]').click();await eventually(async()=>/所有作业与待办/.test(await p.locator('#content h1').first().innerText()),'T02 all homework and todo')}
       if(pass==='calendar')await p.locator('nav [data-page="calendar"]').click();
       const cards=async()=>p.locator('.agenda-dates').evaluateAll(xs=>xs.filter(x=>x.offsetParent!==null).map(x=>{const c=x.closest('[data-query-target]')||x.parentElement;return {card:c.innerText,dates:x.innerText,group:x.closest('.subject-group')?.querySelector('.task-group-heading h2')?.innerText||''}}));
       let all=[],rope=[],english=[],sheet=[];
       await eventually(async()=>{all=await cards();rope=all.filter(c=>/跳绳/.test(c.card));english=all.filter(c=>/Unit 5/.test(c.card));sheet=all.filter(c=>/实验观察表/.test(c.card));return rope.length>0&&sheet.length>0&&(pass==='calendar'||english.length>0)},'T02 '+pass+' '+width+' cards');
       if(pass!=='calendar')assert.equal(sheet.length,1,pass+' '+width+' one T06 sheet card');
       for(const c of sheet){
        assert.match(c.dates,/安排日：2026-11-05/,pass+' '+width+' the sheet reads its class day');
        assert.doesNotMatch(c.dates,/截止|老师要求交回|老师检查|完成：|计划：/,pass+' '+width+' sheet: no deadline, handback, check, completion or made-up plan');
        if(pass!=='calendar')assert.match(c.card,/今晚不填/,'its own not-tonight words kept');
        assert.doesNotMatch(c.group+'\n'+c.card,/跳绳|Unit 5|英语/,pass+' '+width+' the sheet keeps only its own words');
       }
       assert.deepEqual(all.filter(c=>/训练/.test(c.card)&&!/跳绳/.test(c.card)),[],pass+' '+width+' no training item is generated');
       for(const c of rope){
        assert.match(c.dates,/安排日：2026-11-05/,pass+' '+width+' the rope reads its lesson day');
        assert.doesNotMatch(c.dates,/截止|老师要求交回|老师检查|完成：|计划：/,pass+' '+width+' no deadline, handback, check, completion or made-up plan');
        assert.match(c.card,/体育/);assert.match(c.card,/不要求在家训练/,'its own no-training condition kept as said');
        assert.doesNotMatch(c.group+'\n'+c.card,/Unit 5|英语/,pass+' '+width+' rope keeps only its own words and is not under English');
       }
       for(const c of english){
        assert.doesNotMatch(c.dates,/2026-11-05|安排日/,pass+' '+width+' English never borrows 11/5');assert.match(c.dates,/2026-11-04/);
        if(pass!=='calendar')assert.match(c.group,/英语/,pass+' '+width+' English under its own subject heading');assert.doesNotMatch(c.card,/跳绳/,pass+' '+width+' English keeps only its own words');
       }
       assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');
       if(process.env.TODAY_UI_PROOF_DIR&&['open','calendar'].includes(pass)){const pth=require('node:path');await require('node:fs/promises').mkdir(process.env.TODAY_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:pth.join(process.env.TODAY_UI_PROOF_DIR,'t02-'+pass+'-'+width+'.png'),fullPage:true})}
      }
      assert.deepEqual(errors,[]);assert.deepEqual(writes,[],'reading the list and calendar writes nothing');
     }finally{await p.close()}
    }
   }finally{if(t02.exitCode===null&&t02.signalCode===null){const end=once(t02,'exit');t02.kill('SIGINT');await Promise.race([end,delay(2500)]);if(t02.exitCode===null&&t02.signalCode===null){t02.kill('SIGKILL');await end}}}
   console.log('PASS: T02 saved by run_once and served over HTTP: the PE rope reads 安排日：2026-11-05, English keeps 2026-11-04, open/reopen/list/calendar at 360 and 1440');
  }
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
     await eventually(async()=>await p.locator('body[data-page="home"] #task-groups').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','Today ready');
     const todayGroup=p.locator('#task-groups .subject-item[data-category="homework"][data-today]'),card=(scope,id)=>scope.locator('[data-query-target="task:'+id+'"]');
     assert.equal(await todayGroup.evaluateAll(xs=>xs.filter(x=>x.dataset.kind!=='school').length),2,'today and tonight work is counted once each');
     for(const id of ['RECITE','COPY']){
      assert.equal(await card(p,id).count(),1,id+' appears once');assert.equal(await card(todayGroup,id).isVisible(),true,id+' is directly in Today');
      assert.match(await card(todayGroup,id).locator('.agenda-dates').innerText(),/今天完成：2026-10-07[\s\S]*截止：2026-10-08/,id+' shows both roles in the first layer');
     }
     assert.equal(await card(todayGroup,'ORAL').count(),0,'only a handback day is not guessed as today');
     assert.match(await p.locator('#task-groups .subject-item[data-category="homework"]:not([data-today])').filter({hasText:'数学：完成口算本第8页'}).innerText(),/截止：2026-10-08/);
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
  for(const width of [360,1440])for(const [day,inToday,label] of [['2026-10-16',false,/完成：2026-10-18[\s\S]*老师要求交回：2026-10-20/],['2026-10-18',true,/今天完成：2026-10-18[\s\S]*老师要求交回：2026-10-20/],['2026-10-20',true,/完成：2026-10-18[\s\S]*老师要求交回：2026-10-20/]]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.route('**/api/state',route=>route.fulfill({json:{...base,children:saved.children,today:day,tasks:saved.tasks,agent:{...base.agent,items:[]},today_calendar:saved.saved_calendars[day]}}));
    await p.goto(server.url,{waitUntil:'load'});
    await eventually(async()=>await p.locator('body[data-page="home"] #task-groups').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','Today ready '+day);
    const card=scope=>scope.locator('[data-query-target="task:'+h01.id+'"]');
    assert.equal(await card(p).count(),1,day+' the saved task appears once');
    assert.equal(await card(p.locator('#task-groups .subject-item[data-category="homework"][data-today]')).count(),inToday?1:0,day+' first-layer Today only on its work and handback days');
    // H01: “2026年10月20日早读交回语文老师” names handing it back that day, so 10/20 is the teacher's handback, not a deadline.
    const h01Dates=await card(p).locator('.agenda-dates').innerText();assert.match(h01Dates,label,day+' both roles with the original handback due');
    assert.doesNotMatch(h01Dates,/截止|计划：/,day+' no deadline or made-up plan');
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
  // Each own 10/20 role as its teacher wrote it: “明天早上交”(31, 32) and “明天早上让孩子交给班主任”(35) hand it back,
  // “明天早读检查记录本”(34) is the teacher's check, “明天来校带…科学课用”(35) is the science lesson's arrangement.
  const role={'星芽':'老师要求交回','数格':'老师要求交回','Unit 4':'老师检查','回执':'老师要求交回','塑料瓶':'安排日'},roleGaps=[];
  const roleOf=(where,key,dates)=>{if(!new RegExp(role[key]+'：2026-10-20').test(dates)||/截止/.test(dates))roleGaps.push(where+' '+key+' wants '+role[key]+'：2026-10-20, shows '+dates.replace(/\s+/g,' '))};
  const teacher={'星芽':'虚构语文许老师','数格':'虚构数学魏老师','Unit 4':'虚构英语乔老师','回执':'虚构班主任温老师','塑料瓶':'虚构班主任温老师'};
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.route('**/api/state',route=>route.fulfill({json:{...base,children:flash.children,sources:flash.sources,today:'2026-10-19',tasks:flash.tasks,records:flash.records,agent:{...flash.agent,items:[]},today_calendar:flash.saved_calendar}}));
    for(const pass of ['open','reopen','list']){
     if(pass==='open')await p.goto(server.url,{waitUntil:'load'});else await p.reload({waitUntil:'load'});
     await eventually(async()=>await p.locator('body[data-page="home"] #task-groups').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','Flash27 Today ready');
     if(pass==='list'){await p.locator('nav [data-page="tasks"]').click();await p.locator('[data-task-box="全部"]').click();await eventually(async()=>/所有作业与待办/.test(await p.locator('#content h1').first().innerText()),'all homework and todo list')}
     else{
      assert.equal(await p.locator('#task-groups .subject-item[data-category="homework"][data-today]:not([data-kind="school"])').count(),3);assert.equal(await p.locator('#task-groups .subject-item[data-category="todo"]:not([data-kind="school"])').count(),2);
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
      if(key==='塑料瓶')assert.doesNotMatch(dates,/完成：/,'the bottle borrows no completion day');else assert.match(dates,/完成：2026-10-19[\s\S]*2026-10-20/,key+' completion day before its 10/20');
      assert.doesNotMatch(dates,/计划：/,key+' no made-up parent plan');roleOf('Flash27 '+pass+' '+width,key,dates);
      // Bringing the bottle to science class is that day's arrangement (the frozen T02 meaning), still no handback or deadline.
      if(key==='塑料瓶'){assert.match(dates,/安排日：2026-10-20/,'the bottle reads its science lesson day');assert.doesNotMatch(dates,/截止|老师要求交回/,'the bottle is no deadline or handback')}
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
     await eventually(async()=>await p.locator('body[data-page="home"] #task-groups').isVisible()&&await p.locator('#content').getAttribute('data-ready')==='true','recovered Today ready');
     if(pass==='list'){await p.locator('nav [data-page="tasks"]').click();await p.locator('[data-task-box="全部"]').click();await eventually(async()=>/所有作业与待办/.test(await p.locator('#content h1').first().innerText()),'all homework and todo list')}
     else{assert.equal(await p.locator('#task-groups .subject-item[data-category="homework"][data-today]:not([data-kind="school"])').count(),3);assert.equal(await p.locator('#task-groups .subject-item[data-category="todo"]:not([data-kind="school"])').count(),2)}
     for(const [key,want] of Object.entries(recoveredLines)){
      const card=p.locator('[data-query-target="task:'+rid[key]+'"]'),saved=recovered.tasks.find(t=>t.id===rid[key]);
      assert.equal(await card.count(),1,key+' one card');assert.equal(await card.locator('h3').innerText(),saved.title);
      assert.deepEqual(await card.locator('.task-requirement li, p.task-requirement').allInnerTexts(),want,pass+' '+width+' '+key+' recovered card lines');
      const text=await card.innerText();assert.match(text,new RegExp(teacher[key]));
      if(key==='Unit 4'){assert.equal(text.split('英语：').length-1,1,'the subject label only in the heading');const dates=await card.locator('.agenda-dates').innerText();assert.match(dates,/完成：2026-10-19[\s\S]*2026-10-20/);roleOf('recovered '+pass+' '+width,key,dates)}
     }
     assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');
    }
    if(process.env.TODAY_UI_PROOF_DIR){await p.goto(server.url,{waitUntil:'load'});await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','proof ready');await p.screenshot({path:path.join(process.env.TODAY_UI_PROOF_DIR,'recovered-today-'+width+'.png'),fullPage:true})}
    assert.deepEqual(errors,[]);
   }finally{await p.close()}
  }
  console.log('PASS: own today/tonight work is in Today once with its completion and handback days; handback-only work stays in other homework');
  console.log('PASS: saved H01 is in Today once on 2026-10-18 (work) and 2026-10-20 (handback), not on 2026-10-16');
  // Run to the end at both widths first; a 10/20 shown other than its teacher's own role then fails here, listed in full.
  assert.deepEqual(roleGaps,[],'each 10/20 reads its teacher-stated role');
  console.log('PASS: saved Flash27 day shows each own condition once under its title with its date roles, teacher and originals, open/reopen/list at 360 and 1440');
  console.log('PASS: the R09 recovered English paragraph reads as its own sentences under its title, the other four as before, open/reopen/list at 360 and 1440');
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e);process.exit(1)});
