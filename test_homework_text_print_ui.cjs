// Synthetic loopback demo only: the real TXT -> DOCX / preparation / queue / ownership path.
// Office and page-count fixtures inspect real generated DOCX, then return one fixed PDF.
// No real model, Office process, printer, household data or external request is allowed.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON,
// HOMEWORK_TEXT_PRINT_PROOF_DIR (output directory must be supplied by the caller).
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {createHash}=require('node:crypto'),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
async function eventually(fn,label){for(let n=0;n<250;n++){if(await fn())return;await delay(40)}throw Error('Timed out: '+label)}
async function fit(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no page overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
 assert.equal(await page.locator('iframe').count(),0,'no iframe');
}
async function proof(page,name){
 if(!process.env.HOMEWORK_TEXT_PRINT_PROOF_DIR)return;
 const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.HOMEWORK_TEXT_PRINT_PROOF_DIR,{recursive:true});
 await page.screenshot({path:path.join(process.env.HOMEWORK_TEXT_PRINT_PROOF_DIR,name+'.png'),fullPage:true});
}
const fixture=String.raw`
import runpy,sys,copy,json,tempfile,os,io,zipfile,base64,hashlib
import xml.etree.ElementTree as ET
bootstrap=tempfile.TemporaryDirectory(prefix='synthetic-text-print-bootstrap-')
os.environ['FAMILY_DATA']=bootstrap.name;os.environ['FAMILY_PRINT_SOFFICE']='synthetic-office-never-executed'
import app,family_print
converter=family_print.PrintStore._convert;scope_guard=app.homework_print_sources;office_guard=family_print.office_check
office_calls=[];responses=[];model_calls=[];process_calls=[];failed_teacher=False
paper='\ufeffQUESTION_ONLY_CANARY：虚构文字卷\r\n第1题：2+3=?。孩子作答：5。\r\n\r\n第2题： 6-2=? <核对> & 保留空格。\r\n孩子作答：\t3。\r\n'
teacher='TEACHER_ONLY_CANARY：仅给家长的教师参考\n虚构文字卷第1题：5；第2题：4。\n不要把本页答案当作孩子作答。'
expected=dict(question=paper.lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n'),teacher=teacher)
png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC')
fixed_pdf=family_print.image_pdf(png)
def blocked_model(*args,**kwargs):
 model_calls.append('unexpected');raise AssertionError('Synthetic TXT printing must never call a model')
def blocked_process(*args,**kwargs):
 process_calls.append('unexpected');raise AssertionError('Synthetic TXT printing must never start Office or a printer process')
def controlled_office(data,suffix,directory,soffice,**kwargs):
 global failed_teacher
 assert app.DATA.name.startswith('family-demo-') and suffix=='.docx' and soffice=='synthetic-office-never-executed'
 assert family_print.PrintStore._convert is converter and family_print.office_check is office_guard
 with zipfile.ZipFile(io.BytesIO(data)) as archive:
  assert set(archive.namelist())=={'[Content_Types].xml','_rels/.rels','word/document.xml'}
  assert all(info.date_time==(1980,1,1,0,0,0) for info in archive.infolist())
  root=ET.fromstring(archive.read('word/document.xml'))
 namespace='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
 paragraphs=[''.join((node.text or '') if node.tag==namespace+'t' else '\t' if node.tag==namespace+'tab' else '' for node in p.iter()) for p in root.iter(namespace+'p')]
 assert all(t.get('{http://www.w3.org/XML/1998/namespace}space')=='preserve' for t in root.iter(namespace+'t'))
 text='\n'.join(paragraphs);role='question' if 'QUESTION_ONLY_CANARY' in text else 'teacher'
 assert paragraphs==expected[role].split('\n'),'TXT paragraphs, blanks, tabs and escaped text must survive unchanged'
 assert ('TEACHER_ONLY_CANARY' not in text if role=='question' else 'QUESTION_ONLY_CANARY' not in text)
 assert '家长参考答案与辅导指南' not in text,'original TXT must not receive generated-guide headings'
 call=dict(role=role,suffix=suffix,text=text,paragraphs=paragraphs,docx_sha256=hashlib.sha256(data).hexdigest(),failed=False)
 office_calls.append(call)
 if role=='teacher' and not failed_teacher:
  failed_teacher=True;call['failed']=True
  raise family_print.PrintError('虚构教师TXT转换失败；请保留原件并重试','synthetic_conversion_failed',503)
 return fixed_pdf
def controlled_pages(store,path):
 assert path.read_bytes()==fixed_pdf;return 1
app.family_llm._chat_json=blocked_model
family_print.office_convert=controlled_office;family_print.PrintStore._page_count=controlled_pages
family_print.bounded_process=blocked_process;family_print.subprocess.run=blocked_process
app.printer_config=lambda:dict(printers=[dict(name='Synthetic_Printer',label='虚构打印机',color=False,duplex=False)],error='')
reply=app.Handler.reply
def observe_reply(self,code,body,*args,**kwargs):
 if self.path=='/api/print/homework':responses.append(dict(status=code,body=copy.deepcopy(body)))
 return reply(self,code,body,*args,**kwargs)
app.Handler.reply=observe_reply
get=app.Handler.do_GET
def fixture_get(self):
 if self.path!='/__fixture/text-print':return get(self)
 assert app.DATA.name.startswith('family-demo-') and app.homework_print_sources is scope_guard
 assert family_print.PrintStore._convert is converter and family_print.office_check is office_guard
 with app.connect_read_only() as c:
  tables={}
  for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
   name=row['name'];rows=[{k:(v.hex() if isinstance(v,bytes) else v) for k,v in dict(r).items()} for r in c.execute('SELECT * FROM "'+name.replace('"','""')+'"')]
   tables[name]=sorted(rows,key=lambda r:json.dumps(r,sort_keys=True))
  uploads=[dict(id=r['id'],sha256=hashlib.sha256((app.DATA/'uploads'/r['id']).read_bytes()).hexdigest()) for r in c.execute('SELECT id FROM uploads ORDER BY id')]
 return self.reply(200,dict(synthetic_only=True,real_converter=True,real_scope_guard=True,real_office_guard=True,
                          model_calls=model_calls,process_calls=process_calls,office_calls=office_calls,responses=responses,
                          paper=paper,teacher=teacher,tables=tables,upload_bytes=uploads))
app.Handler.do_GET=fixture_get;sys.argv=['demo.py','--port',sys.argv[1]]
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
 try{await eventually(async()=>{if(error)throw error;if(proc.exitCode!==null)throw Error('Demo exited: '+stderr);try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo startup');return {url,stop}}
 catch(e){await stop();throw e}
}
const business=tables=>Object.fromEntries(Object.entries(tables).filter(([name])=>!['print_preparations','print_jobs'].includes(name)));
(async()=>{
 let browser,server,page;const results=[];
 try{
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440]){
   server=await startServer();const read=async path=>{const r=await fetch(server.url+path);assert.equal(r.status,200);return r.json()},state=()=>read('api/state'),audit=()=>read('__fixture/text-print');
   const errors=[],foreign=[],forbidden=[],bodies=[],replies=[],posts=[];let loseReceipt=false;
   page=await browser.newPage({viewport:{width,height:850}});page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
   await page.route('**/*',async route=>{const r=route.request(),url=new URL(r.url());if(url.origin!==new URL(server.url).origin){foreign.push(r.url());return route.abort()}if(r.method()==='POST'&&url.pathname.startsWith('/api/print/')&&url.pathname!=='/api/print/homework'){forbidden.push(url.pathname);return route.abort()}await route.continue()});
   await page.route('**/api/print/homework',async route=>{bodies.push(route.request().postDataJSON());const response=await route.fetch();replies.push({status:response.status(),body:await response.json()});if(loseReceipt&&response.ok()){loseReceipt=false;return route.fulfill({status:503,json:{error:'虚构已入队后的回执丢失，请沿原编号重试'}})}await route.fulfill({response})});
   await page.goto(server.url,{waitUntil:'load'});await page.locator('[data-homework-new]').first().waitFor();await page.locator('[data-homework-new]').first().click();
   const title='虚构TXT作业打印 '+width,entry=page.locator('#homeworkInputDialog'),item=entry.locator('[data-homework-item="0"]');
   await item.locator('[name=title]').fill(title);await item.locator('[name=goal]').fill('保留本卷题干和实际作答，教师参考单独交给家长。');await item.locator('[type=submit]').click();await entry.locator('.homework-saved').waitFor();await entry.locator('[data-homework-close]').click();
   let value=await state();const task=value.tasks.find(t=>t.title===title);assert(task);const child=task.child,content=await audit(),qName='synthetic-question-'+width+'.txt',tName='synthetic-teacher-'+width+'.txt';
   await page.locator('[data-task="'+task.id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();await page.locator('#taskForm [name=note]').fill('PARENT_NOTE_ONLY_CANARY：虚构原作答说明；打印不修改作答或完成状态。');
   for(const [name,text] of [[qName,content.paper],[tName,content.teacher]]){await page.locator('#fileInput').setInputFiles({name,mimeType:'text/plain',buffer:Buffer.from(text)});await page.locator('#pendingUploads').getByRole('link',{name,exact:true}).waitFor()}
   await page.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'original TXT answer saved');
   value=await state();const original=value.records.find(r=>r.source==='事项:'+task.id),question=value.uploads.find(u=>u.name===qName),teacher=value.uploads.find(u=>u.name===tName);assert(original&&question&&teacher);assert.deepEqual(original.attachments,[question.id,teacher.id]);
   assert.equal(await page.locator('#taskDialog [data-print-upload="'+question.id+'"]').count(),1,'the original TXT has its real print entry');await fit(page);await proof(page,'original-txt-'+width);
   const post=async(path,body,status=200)=>{const r=await fetch(server.url+path,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':value.token},body:JSON.stringify(body)});assert.equal(r.status,status);return r.json()};
   const upload=async(name,text)=>{const r=await fetch(server.url+'api/upload',{method:'POST',headers:{'Content-Type':'text/plain','X-Family-Token':value.token,'X-File-Name':encodeURIComponent(name)},body:Buffer.from(text)});assert.equal(r.status,200);return (await r.json()).attachment};
   const outside=[];for(const [who,label] of [[child,'同孩另一项'],[value.children.find(c=>c.name!==child).name,'另一孩子']]){
    const other=(await post('api/task/new',{child:who,title:'虚构隔离资料 '+label,category:'homework',action:'只属于这项作业',due:value.today})).task,file=await upload('synthetic-foreign-'+outside.length+'.txt','FOREIGN_ONLY_CANARY：'+label);
    await post('api/record',{child:who,day:value.today,category:'学习进展',title:'虚构其他原作答',source:'事项:'+other.id,note:'独立原件',attachments:[file.id]});outside.push(file);
   }
   outside.push(await upload('synthetic-unbound.txt','UNBOUND_ONLY_CANARY：未关联任何作业'));
   const oldAI=await upload('作业批改参考-'+original.id+'.txt','AI_RESULT_ONLY_CANARY：这只是上一轮虚构检查意见。');
   await post('api/record',{child,day:value.today,category:'学习进展',title:'虚构旧检查意见',source:'事项:'+task.id,note:'旧AI意见保留为后续记录。',attachments:[oldAI.id],related_record_id:original.id,followup_kind:'作业检查'});outside.push(oldAI);
   await page.locator('#taskDialog [data-close=taskDialog]').click();await page.reload({waitUntil:'load'});value=await state();const baseline=await audit();
   const scoped=await read('api/print/homework/materials?task_id='+task.id);assert.deepEqual(scoped.files.map(f=>f.source.id).sort(),[question.id,teacher.id].sort(),'same task only; old AI never becomes question/reference');
   const source=file=>({type:'upload',id:file.id}),template={task_id:task.id,request_key:'synthetic-scope-'+width,question_sources:[source(question)],guide_source:source(teacher),guide_text:'',printer:'Synthetic_Printer',question_confirmed:true,guide_confirmed:true};
   let guards=0;for(const file of outside)for(const role of ['question','teacher']){
    const body={...template,request_key:'synthetic-scope-'+width+'-'+guards++,question_sources:[source(role==='question'?file:question)],guide_source:source(role==='teacher'?file:teacher)};
    const rejected=await post('api/print/homework',body,403);assert.match(rejected.error,/当前作业|原件|检查意见/);const after=await audit();assert.deepEqual(after.tables,baseline.tables,'foreign/unbound/AI rejected before any write');assert.deepEqual(after.office_calls,[]);
   }
   const openPrint=async()=>{await page.locator('[data-query-target="task:'+task.id+'"] [data-homework-print]').click();await page.locator('#homeworkPrintDialog[open]').waitFor()};await openPrint();
   const form=page.locator('#homeworkPrintForm'),qValue=JSON.stringify(source(question)),tValue=JSON.stringify(source(teacher));
   for(const name of ['question_source','guide_source'])assert.deepEqual((await form.locator('[name='+name+'] option').evaluateAll(xs=>xs.map(x=>x.value).filter(Boolean))).sort(),[qValue,tValue].sort(),'TXT offered through the actual selectors');
   await form.locator('[name=question_source]').selectOption(qValue);await form.locator('[name=guide_source]').selectOption(tValue);await form.locator('[name=printer]').selectOption('Synthetic_Printer');await form.locator('[name=question_confirmed]').check();await form.locator('[name=guide_confirmed]').check();
   const key=await form.evaluate(f=>f.dataset.requestKey);await fit(page);await proof(page,'txt-role-selection-'+width);await form.locator('[type=submit]').click();
   await eventually(async()=>replies.length===1&&/虚构教师TXT转换失败/.test(await page.locator('#homeworkPrintError').innerText())&&await form.locator('[type=submit]').isEnabled(),'real conversion failure');
   assert.equal(replies[0].status,503);const failed=await audit();assert.equal(failed.tables.print_jobs.length,0,'a failed reference conversion queues neither part');assert.equal(failed.tables.print_preparations.length,1);assert.deepEqual(failed.office_calls.map(c=>[c.role,c.failed]),[['question',false],['teacher',true]]);
   assert.deepEqual(business(failed.tables),business(baseline.tables));assert.deepEqual(failed.upload_bytes,baseline.upload_bytes);assert.equal(await form.locator('[name=question_source]').inputValue(),qValue);assert.equal(await form.locator('[name=guide_source]').inputValue(),tValue);await fit(page);await proof(page,'conversion-failure-'+width);
   const reopen=async()=>{await page.locator('#homeworkPrintDialog [data-close]').click();await page.reload({waitUntil:'load'});await openPrint();assert.equal(await form.evaluate(f=>f.dataset.requestKey),key);assert.equal(await form.locator('[name=question_source]').inputValue(),qValue);assert.equal(await form.locator('[name=guide_source]').inputValue(),tValue);await form.locator('[name=printer]').selectOption('Synthetic_Printer')};
   await reopen();assert.deepEqual((await audit()).tables,failed.tables,'reopening a failed draft is read only');loseReceipt=true;await form.locator('[type=submit]').click();
   await eventually(async()=>replies.length===2&&/虚构已入队后的回执丢失/.test(await page.locator('#homeworkPrintError').innerText())&&await form.locator('[type=submit]').isEnabled(),'lost receipt after real enqueue');assert.equal(replies[1].status,200);
   const queued=await audit(),jobs=replies[1].body.jobs;assert.equal(queued.tables.print_jobs.length,2);assert.equal(queued.tables.print_preparations.length,2);assert.equal(jobs.questions.length,1);assert.notEqual(jobs.question.id,jobs.guide.id);assert.equal(jobs.question.id,jobs.questions[0].id);
   assert.equal(jobs.question.name,qName);assert.equal(jobs.guide.name,tName);assert.equal(jobs.question.source_sha256,hash(Buffer.from(content.paper)));assert.equal(jobs.guide.source_sha256,hash(Buffer.from(content.teacher)));
   for(const job of [jobs.question,jobs.guide]){assert.equal(job.status,'queued');assert.equal(job.cups_job_id,'');assert.equal(job.printer,'Synthetic_Printer')}
   const prepared=queued.tables.print_preparations.map(r=>JSON.parse(r.body));for(const [file,job] of [[question,jobs.question],[teacher,jobs.guide]]){const prep=prepared.find(p=>p.id===job.preparation_id);assert.deepEqual(prep.source,source(file));assert.equal(prep.name,file.name);assert.equal(prep.source_sha256,job.source_sha256)}
   assert.deepEqual(queued.office_calls.map(c=>[c.role,c.failed]),[['question',false],['teacher',true],['teacher',false]]);assert.equal(queued.office_calls[1].docx_sha256,queued.office_calls[2].docx_sha256,'retry uses identical generated reference DOCX');assert.deepEqual(business(queued.tables),business(baseline.tables));assert.deepEqual(queued.upload_bytes,baseline.upload_bytes);await fit(page);await proof(page,'lost-queue-receipt-'+width);
   await reopen();assert.deepEqual((await audit()).tables,queued.tables);await form.locator('[type=submit]').click();await eventually(async()=>replies.length===3&&!await page.locator('#homeworkPrintDialog').evaluate(d=>d.open),'same request recovers the existing queue receipt');
   assert.deepEqual(replies.map(r=>r.status),[503,200,200]);assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[1],bodies[2]);assert.equal(bodies[2].request_key,key);assert.deepEqual(replies[2].body.jobs,jobs);assert.deepEqual((await audit()).tables,queued.tables,'receipt retry adds no preparation, job or business row');
   await page.locator('.print-job').first().waitFor();assert.equal(await page.locator('.print-job').count(),2);assert.match(await page.locator('.print-progress').innerText(),/等待家中电脑领取/);assert(await page.locator('.print-choice').filter({hasText:qName}).count());assert(await page.locator('.print-choice').filter({hasText:tName}).count());await fit(page);await proof(page,'separate-queued-txt-'+width);
   await page.locator('nav [data-page=home]').click();await page.locator('[data-task="'+task.id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();assert.equal(await page.locator('#taskForm [name=id]').inputValue(),task.id);assert.equal(await page.locator('#taskForm [name=status]').inputValue(),'待跟进');
   const finalState=await state();assert.deepEqual(finalState.tasks,value.tasks);assert.deepEqual(finalState.records,value.records);assert.deepEqual(finalState.uploads,value.uploads);assert.deepEqual(finalState.records.find(r=>r.id===original.id),original);
   for(const [file,text] of [[question,content.paper],[teacher,content.teacher]]){assert(await page.locator('#taskFeedbackHistory').getByRole('link',{name:file.name,exact:true}).count());const r=await fetch(server.url+'upload/'+file.id);assert.equal(r.status,200);assert.deepEqual(Buffer.from(await r.arrayBuffer()),Buffer.from(text),'uploaded original bytes remain unchanged')}
   const final=await audit();assert.deepEqual(final.tables,queued.tables);assert.deepEqual(final.upload_bytes,baseline.upload_bytes);assert.deepEqual(final.model_calls,[]);assert.deepEqual(final.process_calls,[]);assert.equal(final.real_converter,true);assert.equal(final.real_scope_guard,true);assert.equal(final.real_office_guard,true);assert.equal(final.responses.length,guards+3);assert.deepEqual(errors,[]);assert.deepEqual(foreign,[]);assert.deepEqual(forbidden,[]);
   const counts={};for(const path of posts)counts[path]=(counts[path]||0)+1;assert.deepEqual(counts,{'/api/study/item':1,'/api/upload':2,'/api/task/feedback':1,'/api/print/homework':3});await fit(page);await proof(page,'original-reopened-'+width);
   results.push({width,synthetic_only:true,office_fixture:true,generated_docx:final.office_calls,scope_rejections:guards,conversion_failures:1,job_ids:[jobs.question.id,jobs.guide.id],same_request_retry:true,original_record_id:original.id,actual_model_calls:0,actual_print_calls:0});
   await page.close();page=null;await server.stop();server=null;
  }
  if(process.env.HOMEWORK_TEXT_PRINT_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.HOMEWORK_TEXT_PRINT_PROOF_DIR,{recursive:true});await fs.writeFile(path.join(process.env.HOMEWORK_TEXT_PRINT_PROOF_DIR,'result.json'),JSON.stringify(results,null,2))}
  console.log(JSON.stringify({ok:true,synthetic_only:true,results}));
 }finally{if(page)await page.close().catch(()=>{});if(browser)await browser.close().catch(()=>{});if(server)await server.stop()}
})().catch(error=>{console.error(error.stack||error);process.exitCode=1});
