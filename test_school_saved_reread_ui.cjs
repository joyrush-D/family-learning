// Synthetic SR02/SR06 check of the original single-child entry after a saved-batch audit. Optional: PLAYWRIGHT_MODULE,
// PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON, SR06_PROOF_DIR. No production URL, model or device calls.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
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
 try{await eventually(async()=>{
 let server,browser;
 try{
  // The state the app itself saved: exact old source seed -> new natural run_once audit (synthetic reply) -> snapshot.
  const file=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'school-sr02-')),'state.json');
  const made=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['test_school_saved_reread.py','--saved-sr02-state',file],{cwd:__dirname,stdio:['ignore','ignore','inherit']});
  const [code]=await once(made,'exit');assert.equal(code,0,'saved SR02 state');
  const saved=JSON.parse(fs.readFileSync(file,'utf8')),sr=saved.sr02,items=saved.agent.items;
  const oldTask=saved.tasks.find(t=>t.id===sr.old_task),found=items.filter(i=>i.id!==sr.old_item&&i.body.includes(sr.second));
  assert.equal(found.length,1,'one saved item for the missing action');assert.equal(oldTask.action,sr.old_action,'old task unchanged');
  const added=found[0],newTask=saved.tasks.find(t=>t.id&&t.id===added.task_id);
  server=await demoServer();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const base=await(await fetch(server.url+'api/state')).json();
  console.log('browser',browser.browserType().name(),browser.version(),'added item state',added.state,'new task',Boolean(newTask));
  for(const width of [360,1440]){
   const p=await browser.newPage({viewport:{width,height:820}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.route('**/api/state',route=>route.fulfill({json:{...base,children:saved.children,today:'2026-10-17',tasks:saved.tasks,agent:{...base.agent,...saved.agent},today_calendar:saved.saved_calendar}}));
    for(const pass of ['open','reopen']){
     if(pass==='open')await p.goto(server.url,{waitUntil:'load'});else await p.reload({waitUntil:'load'});
     await eventually(async()=>await p.locator('#content').getAttribute('data-ready')==='true','home ready '+width+' '+pass);
     const text=await p.locator('#content').innerText();
     assert.equal(await p.locator('[data-query-target="task:'+oldTask.id+'"]').count(),1,'the accepted old task appears once');
     assert.match(await p.locator('[data-query-target="task:'+oldTask.id+'"]').innerText(),/材料领取登记单/);
     assert.doesNotMatch(await p.locator('[data-query-target="task:'+oldTask.id+'"]').innerText(),/秋游安全告知书/,'the old task is not shown as updated with the new action');
     const shown=newTask?p.locator('[data-query-target="task:'+newTask.id+'"]'):p.locator('[data-agent-item="'+added.id+'"]');
     assert.equal(await shown.count(),1,'the missing action appears once ('+(newTask?'task':'pending item')+')');
     assert.match(await shown.innerText(),/秋游安全告知书/);
     assert.equal((text.match(/秋游安全告知书/g)||[]).length>=1,true);
     assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');
     if(process.env.SR06_PROOF_DIR){fs.mkdirSync(process.env.SR06_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.SR06_PROOF_DIR,'sr02-'+width+'-'+pass+'.png'),fullPage:true})}
    }
    assert.deepEqual(errors,[]);
   }finally{await p.close()}
  }
  console.log('PASS: SR02 audit result in the original entry at 360/1440, open and reopen: old task once and unchanged, the missing action once, no overflow');
 }finally{await browser?.close();await server?.stop()}
})().catch(e=>{console.error(e);process.exit(1)});
