// Synthetic browser + real local API checks; no real family, CLI or model calls.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check,label){for(let i=0;i<200;i++){if(await check())return;await delay(50)}throw Error(label)}
const fixture=String.raw`
import tempfile,os,json,datetime
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='synthetic-agent-ui-') as tmp:
 os.environ['FAMILY_DATA']=tmp
 import app,family_agent
 app.DATA=Path(tmp);app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 today=datetime.datetime.now(family_agent.TZ).date().isoformat()
 app.save_record(dict(child='示例小宇',day=today,category='学习进展',title='虚构阅读尝试',note='还需要一次提示',subject='语文',source='家长观察'))
 (app.DATA/'agent.json').write_text(json.dumps({'enabled':True,'sources':[]}))
 store=app.agent_store();now=datetime.datetime.now(family_agent.TZ)
 for i in range(2):
  store._save('school:'+str(i),'fixture',[dict(child_id='child-1',kind='school',title='虚构学校准备 '+str(i),body='核对后准备观察材料。',due=today,evidence=[{'ref':'message:synthetic:'+str(i),'text':'虚构老师通知：请准备观察材料。<img src=x onerror=alert(1)>'}])],now)
 store._save('record:1','fixture',[dict(child_id='child-2',kind='care',title='虚构学习跟进',body='请孩子讲讲自己的想法。',record_id=1,evidence=[{'ref':'record:1','text':'还需要一次提示'}])],now)
 store._runtime('ready',now)
 app.prepare_assets()
 server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_AGENT_PORT'])),app.Handler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
`;
(async()=>{let proc,browser;try{
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));const url='http://127.0.0.1:'+port+'/',env={...process.env,TEST_AGENT_PORT:String(port)};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let errors='';proc.stderr.on('data',b=>errors+=b);proc.on('error',e=>errors+=e.message);
 await until(async()=>{if(proc.exitCode!==null)throw Error(errors);try{return(await fetch(url)).ok}catch{return false}},'server startup');const state=async()=>await(await fetch(url+'api/state')).json();
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
 for(const width of [360,1440]){
  const page=await browser.newPage({viewport:{width,height:820}}),pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));await page.goto(url);await page.locator('.today-dashboard').waitFor();
  assert.equal(await page.locator('[data-today-child="child-2"] [data-agent-item]').count(),1);assert.equal(await page.locator('[data-today-child="child-1"] [data-followup]').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const first=page.locator('[data-agent-accept]').first();await first.click();await page.locator('#agentDialog').waitFor();await page.locator('#agentForm [name="title"]').fill('虚构家长核对 '+width);await page.locator('#agentForm [name="body"]').fill('带一本笔记本');
  await page.route('**/api/agent/action',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构网络暂不可用'})}),{times:1});
  await page.locator('#agentForm [type="submit"]').click();await until(()=>page.locator('#agentError').textContent().then(t=>t.includes('虚构网络')),'failed save visible');assert.equal(await page.locator('#agentForm [name="body"]').inputValue(),'带一本笔记本');
  assert.equal(await page.locator('#agentDialog').evaluate(d=>d.scrollWidth>d.clientWidth),false);
  if(process.env.AGENT_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.AGENT_UI_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.AGENT_UI_PROOF_DIR,'agent-form-'+width+'.png')})}
  await page.locator('#agentForm [type="submit"]').click();await until(()=>page.locator('#agentDialog').isVisible().then(v=>!v),'saved');await page.reload();await page.locator('.today-dashboard').waitFor();
  const saved=await state();assert.equal(saved.tasks.filter(t=>t.title==='虚构家长核对 '+width).length,1);assert.equal(saved.tasks.find(t=>t.title==='虚构家长核对 '+width).child,'示例星星');
  await page.locator('[data-today-child="child-2"] [data-followup]').click();await page.locator('#recordDialog').waitFor();assert.equal(await page.locator('#recordForm [name="child"]').inputValue(),'示例小宇');assert.equal(await page.locator('#recordForm [name="related_record_id"]').inputValue(),'1');await page.locator('[data-close="recordDialog"]').click();
  await page.locator('[data-page="agent"]').first().click();await page.locator('.agent-status details summary').click();assert.equal(await page.locator('.agent-item img').count(),0);assert.match(await page.locator('.agent-status').innerText(),/上次整理/);
  if(process.env.AGENT_UI_PROOF_DIR){const path=require('node:path');await page.screenshot({path:path.join(process.env.AGENT_UI_PROOF_DIR,'agent-'+width+'.png')})}
  assert.deepEqual(pageErrors,[]);await page.close();
 }
 const p=await browser.newPage();await p.goto(url);await p.locator('.today-dashboard').waitFor();await p.locator('[data-agent-dismiss]').first().click();await until(async()=>!(await state()).agent.items.some(x=>x.kind==='care'&&x.state==='pending'),'dismiss saved');assert.equal((await state()).records.length,1,'acknowledgement does not fabricate child feedback');await p.close();
 console.log(JSON.stringify({passed:true,widths:[360,1440],realAPI:true,syntheticOnly:true,formRetry:true,childBinding:true,escapedEvidence:true,acknowledgementNotFeedback:true}));
}finally{if(browser)await browser.close();if(proc&&proc.exitCode===null){proc.kill('SIGINT');await once(proc,'exit')}}})().catch(e=>{console.error(e);process.exitCode=1});
