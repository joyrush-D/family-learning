// Synthetic loopback demo only: the Today homework print dialog when a requirement is corrected after the two checks.
// Real page -> real app.py / PrintStore in an isolated demo directory with fictional PNG originals and fictional words.
// No model, print bridge, printer or Office process, household data or external request. Screenshots (viewport only)
// are written only when the caller sets HOMEWORK_PRINT_BASIS_PROOF_DIR. Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON.
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const net=require('node:net'),path=require('node:path'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const PNG=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC','base64');
const NOTICE=/作业要求或归属已更新：原选文件、参考文字和打印编号已保留/,PRINTER='Synthetic_Printer';
async function eventually(fn,label){for(let n=0;n<250;n++){if(await fn())return;await delay(40)}throw Error('Timed out: '+label)}
async function proof(page,name){if(process.env.HOMEWORK_PRINT_BASIS_PROOF_DIR)await page.screenshot({path:path.join(process.env.HOMEWORK_PRINT_BASIS_PROOF_DIR,name+'.png')})}
const fixture=String.raw`
import runpy,os,tempfile,base64
bootstrap=tempfile.TemporaryDirectory(prefix='synthetic-print-basis-bootstrap-')
os.environ['FAMILY_DATA']=bootstrap.name;os.environ['FAMILY_PRINT_SOFFICE']='synthetic-office-never-executed'
import app,family_print
fixed_pdf=family_print.image_pdf(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC'))
office=[];claims=[]
def controlled_office(data,suffix,directory,soffice,**kwargs):
 assert app.DATA.name.startswith('family-demo-') and suffix=='.docx' and soffice=='synthetic-office-never-executed'
 office.append(suffix);return fixed_pdf
def no_bridge(*args,**kwargs):
 claims.append(1);raise AssertionError('the synthetic acceptance never runs a print bridge')
family_print.office_convert=controlled_office;family_print.PrintStore._page_count=lambda self,path:1;family_print.PrintStore.claim=no_bridge
app.printer_config=lambda:dict(printers=[dict(name='Synthetic_Printer',label='虚构打印机',color=False,duplex=False)],error='')
original_get=app.Handler.do_GET
def do_GET(self):
 if self.path.startswith('/__fixture/correct?task_id='):
  assert app.DATA.name.startswith('family-demo-')
  # The saved effects of a confirmed school correction: new requirement words plus the appended original message.
  with app.connect() as c:
   n=c.execute('UPDATE manual_tasks SET source=source||?,title=?,action=? WHERE id=?',('\n\nmessage:synthetic-group:12\n虚构更正：只做第1至3题',
     '数学：练习改做第1至3题','只做第1至3题，交回日不变。',self.path.split('=',1)[1])).rowcount;c.commit()
  return self.reply(200,dict(updated=n))
 if self.path=='/__fixture/print-jobs':
  with app.print_store()._db() as c:
   jobs=[dict(id=r['id'],status=r['status']) for r in c.execute('SELECT id,status FROM print_jobs ORDER BY rowid')]
   preparations=c.execute('SELECT COUNT(*) FROM print_preparations').fetchone()[0]
  return self.reply(200,dict(jobs=jobs,preparations=preparations,claims=len(claims),office=len(office)))
 return original_get(self)
app.Handler.do_GET=do_GET
import sys;sys.argv=['demo.py','--port',sys.argv[1]]
try:runpy.run_path('demo.py',run_name='__main__')
finally:bootstrap.cleanup()
`;
async function startServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture,String(port)],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});
 let error,stderr='';proc.on('error',e=>error=e);proc.stderr.on('data',s=>stderr=(stderr+s).slice(-12000));
 const stop=async()=>{if(error||proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await Promise.race([done,delay(2500)])}};
 const url='http://127.0.0.1:'+port+'/';
 try{await eventually(async()=>{if(error)throw error;if(proc.exitCode!==null)throw Error('Demo exited: '+stderr);try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo startup');return {url,stop,stderr:()=>stderr}}
 catch(e){await stop();throw e}
}
(async()=>{
 let browser,server,page;const results=[];
 try{
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440]){
   server=await startServer();
   const read=async p=>{const r=await fetch(server.url+p);const out=await r.json();assert.equal(r.status,200,p+' '+JSON.stringify(out));return out};
   const value=await read('api/state'),child=value.children[0].name;
   const post=async(p,body)=>{const r=await fetch(server.url+p,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':value.token},body:JSON.stringify(body)});const out=await r.json();assert.equal(r.status,200,p+' '+JSON.stringify(out));return out};
   const homework=async(title,name)=>{
    const task=(await post('api/task/new',{child,title,category:'homework',action:'完成练习第1至5题。',due:value.today})).task;
    const r=await fetch(server.url+'api/upload',{method:'POST',headers:{'Content-Type':'image/png','X-Family-Token':value.token,'X-File-Name':encodeURIComponent(name)},body:PNG});assert.equal(r.status,200);const file=(await r.json()).attachment;
    await post('api/record',{child,day:value.today,category:'学习进展',title:'虚构题目原件',source:'事项:'+task.id,note:'虚构题目原件',attachments:[file.id]});return {task,file:{...file,name}}};
   const first=await homework('数学：完成练习三第1至5题','虚构练习三-原要求1至5题.png'),second=await homework('数学：完成练习四第1至5题','虚构练习四-原要求1至5题.png');
   const audit=()=>read('__fixture/print-jobs'),basisOf=async id=>(await read('api/print/homework/materials?task_id='+id)).print_basis;
   page=await browser.newPage({viewport:{width,height:width<500?780:900}});page.setDefaultTimeout(10000);
   const errors=[],bodies=[],statuses=[];let fail503=false,dropReceipt=false,entry='home';page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/print/homework',async route=>{bodies.push(route.request().postDataJSON());
    if(fail503){fail503=false;statuses.push(503);return route.fulfill({status:503,json:{error:'虚构：打印服务暂时无法连接',code:'storage_unavailable'}})}
    const response=await route.fetch(),json=await response.json();statuses.push(response.status());
    if(dropReceipt&&response.ok()){dropReceipt=false;return route.fulfill({status:503,json:{error:'虚构：回执在返回途中丢失'}})}
    return route.fulfill({status:response.status(),json})});
   const dialog=page.locator('#homeworkPrintDialog'),form=page.locator('#homeworkPrintForm');
   const go=()=>page.goto(server.url,{waitUntil:'load'}),isOpen=()=>dialog.evaluate(d=>d.open);
   const open=async id=>{
    let button=page.locator('[data-homework-print="'+id+'"]').first();
    try{await button.waitFor({state:'visible',timeout:4000})}catch{entry='tasks';await page.locator('nav [data-page="tasks"]').first().click();await button.waitFor({state:'visible'})}
    await button.click();await page.locator('#homeworkPrintDialog[open]').waitFor();
   };
   const close=async()=>{await dialog.locator('[data-close="homeworkPrintDialog"]').click();await eventually(async()=>!await isOpen(),'dialog closed')};
   const view=()=>page.evaluate(()=>{const d=document.querySelector('#homeworkPrintDialog'),f=d.querySelector('form'),n=document.querySelector('#homeworkPrintBasis'),v=d.getBoundingClientRect(),r=n.getBoundingClientRect();
    return {title:document.querySelector('#homeworkPrintTask').textContent,notice:n.hidden?'':n.textContent,
     visible:!n.hidden&&r.height>0&&r.top>=Math.max(0,v.top)&&r.bottom<=Math.min(innerHeight,v.bottom),scrolled:d.scrollTop+f.scrollTop,
     question:f.elements.question_source.selectedOptions[0]?.textContent||'',guide:f.elements.guide_text.value,key:f.dataset.requestKey,
     checks:[f.elements.question_confirmed.checked,f.elements.guide_confirmed.checked],error:document.querySelector('#homeworkPrintError').textContent,
     notices:(d.innerText.match(/要求或归属已更新/g)||[]).length,overflow:document.documentElement.scrollWidth>innerWidth+1}});
   const fill=async(work,words)=>{await form.locator('[name=question_source]').selectOption({label:work.file.name});await form.locator('[name=guide_text]').fill(words);
    await form.locator('[name=question_confirmed]').check();await form.locator('[name=guide_confirmed]').check();await form.locator('[name=printer]').selectOption(PRINTER)};
   const row={width};const words='虚构家长参考：请做第1至5题。';
   // 1. A saved, unchanged draft restores exactly; no notice.
   await go();await open(first.task.id);await fill(first,words);const key=(await view()).key;assert.match(key,/^[A-Za-z0-9_-]{8,128}$/);await close();
   await open(first.task.id);let seen=await view();
   assert.deepEqual([seen.question,seen.guide,seen.key,seen.checks,seen.notice,seen.notices],[first.file.name,words,key,[true,true],'',0],'an unchanged saved draft restores as it was');
   await proof(page,'unchanged-'+width);await close();
   // 2. Teacher correction then refresh: one notice under the new title, in view on open; checks off; file, words and number kept.
   const oldBasis=await basisOf(first.task.id);assert.equal((await read('__fixture/correct?task_id='+first.task.id)).updated,1);const basis=await basisOf(first.task.id);assert.notEqual(basis,oldBasis);
   await go();await open(first.task.id);seen=await view();
   assert.match(seen.title,/练习改做第1至3题/);assert.match(seen.notice,NOTICE);assert.equal(seen.visible,true,'notice visible on open without scrolling');assert.equal(seen.scrolled,0);
   assert.deepEqual([seen.question,seen.guide,seen.key,seen.checks,seen.notices,seen.overflow],[first.file.name,words,key,[false,false],1,false]);
   assert.doesNotMatch(seen.error,/要求或归属已更新/,'the basis notice is not repeated at the bottom');
   row.corrected_open={title:seen.title,notice:seen.notice,visible:seen.visible,checks:seen.checks,bottom_error:seen.error};await proof(page,'corrected-open-'+width);await close();
   // 3. Closing without re-checking, a refresh, or one check alone keeps the notice.
   await open(first.task.id);seen=await view();assert.deepEqual([seen.visible,seen.checks,seen.scrolled],[true,[false,false],0],'still there and in view after close/reopen');await close();
   await go();await open(first.task.id);seen=await view();assert.equal(seen.visible,true,'still there after refresh');
   await form.locator('[name=question_confirmed]').check();await close();await open(first.task.id);seen=await view();
   assert.deepEqual([seen.visible,seen.checks,seen.key,seen.guide],[true,[true,false],key,words],'one check alone does not release it');
   row.reopened_without_recheck={visible:seen.visible,checks:seen.checks,same_number:seen.key===key};
   // 4. Both checks made again on the new version release it, and it stays released.
   await form.locator('[name=guide_confirmed]').check();assert.equal((await view()).notice,'');await close();
   await open(first.task.id);seen=await view();assert.deepEqual([seen.notice,seen.checks,seen.key],['',[true,true],key]);await proof(page,'rechecked-'+width);
   // 5. A failure before the server and a lost receipt keep the same number; the retry reads the same two jobs back.
   await form.locator('[name=printer]').selectOption(PRINTER);
   fail503=true;await form.locator('[type=submit]').click();await eventually(async()=>/虚构：打印服务暂时无法连接/.test((await view()).error),'503 shown');
   assert.equal(await isOpen(),true);assert.equal((await audit()).jobs.length,0);
   dropReceipt=true;await form.locator('[type=submit]').click();await eventually(async()=>/回执在返回途中丢失/.test((await view()).error),'lost receipt shown');
   const queued=(await audit()).jobs;assert.equal(queued.length,2);
   await form.locator('[type=submit]').click();await eventually(async()=>!await isOpen(),'retry accepted');
   assert.deepEqual((await audit()).jobs,queued,'the same original number never queues twice');
   assert.deepEqual([...new Set(bodies.map(b=>b.request_key))],[key]);assert.deepEqual([...new Set(bodies.map(b=>b.confirmed_basis))],[basis]);
   row.retry={statuses:[...statuses],jobs:queued.length};
   // 6. A correction while the dialog is open: 409 queues nothing, keeps the draft and notice, never restores the checks.
   await go();await open(second.task.id);await fill(second,'虚构家长参考：练习四。');const key2=(await view()).key,before=await audit();
   assert.equal((await read('__fixture/correct?task_id='+second.task.id)).updated,1);
   await form.locator('[type=submit]').click();await eventually(async()=>/尚未打印/.test((await view()).notice),'409 notice');
   seen=await view();assert.equal(statuses.at(-1),409);assert.deepEqual([seen.visible,seen.checks,seen.notices,seen.error],[true,[false,false],1,'']);
   assert.deepEqual(await audit(),before,'nothing prepared or queued with the old checks');await proof(page,'open-409-'+width);
   await close();await go();await open(second.task.id);seen=await view();
   assert.deepEqual([seen.visible,seen.checks,seen.key,seen.guide],[true,[false,false],key2,'虚构家长参考：练习四。'],'after 409 and reopen the checks stay off and the notice stays');
   assert.match(seen.notice,NOTICE);assert.match(seen.title,/练习改做第1至3题/);await proof(page,'after-409-reopen-'+width);
   await form.locator('[name=question_confirmed]').check();await form.locator('[name=guide_confirmed]').check();await form.locator('[name=printer]').selectOption(PRINTER);
   await form.locator('[type=submit]').click();await eventually(async()=>!await isOpen(),'new version printed');
   const after=await audit();assert.equal(after.jobs.length,4);assert.equal(after.claims,0);assert.equal(bodies.at(-1).confirmed_basis,await basisOf(second.task.id));
   assert.deepEqual(errors,[]);row.after_409={jobs:after.jobs.length,print_bridge_claims:after.claims};row.entry=entry;
   results.push(row);await page.close();page=null;await server.stop();server=null;
  }
  console.log(JSON.stringify({ok:true,synthetic_only:true,actual_model_calls:0,actual_print_calls:0,results},null,1));
 }catch(error){if(page)await proof(page,'failure').catch(()=>{});console.error(error);if(server)console.error(server.stderr());process.exitCode=1}
 finally{if(page)await page.close().catch(()=>{});if(server)await server.stop();if(browser)await browser.close()}
})();
