// Frozen, wholly synthetic three-task workflow. This script never uses a household URL.
// Required: SCHOOL_FROZEN_VALIDATION_DIR, SCHOOL_FROZEN_PROOF_DIR.
// The validation directory must contain effective-instructions-replay-v4-fixture,
// frozen-input-and-truth.json and effective-instructions-replay-v4-result.json.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');

const AS_OF='2026-10-04',FIXED_TIME='2026-10-04T10:00:00+08:00';
const replayStage=process.env.SCHOOL_FROZEN_REPLAY_STAGE||'effective-instructions-replay-v4';
assert.match(replayStage,/^effective-instructions-replay-v[0-9]+$/);
const fixtureName=replayStage+'-fixture',resultName=replayStage+'-result.json';
function required(name){assert(process.env[name],name+' must identify the synthetic acceptance material');return path.resolve(process.env[name])}
async function eventually(check,label){for(let n=0;n<250;n++){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function readJSON(file){return JSON.parse(await fs.readFile(file,'utf8'))}
async function digest(file){return crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex')}
async function ordinaryFile(file){const stat=await fs.lstat(file);assert(stat.isFile()&&!stat.isSymbolicLink(),'Only an ordinary synthetic file is allowed: '+file)}
async function ready(page){await eventually(async()=>await page.locator('body[data-page=home] #task-group-homework').isVisible()&&await page.locator('#content').getAttribute('data-ready')==='true','real Today entry ready')}
async function fit(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page has no horizontal overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'open dialogs have no horizontal overflow');
}

// Fail before writing anywhere unless the selected input proves the prescribed synthetic case.
async function inputs(){
 const base=required('SCHOOL_FROZEN_VALIDATION_DIR'),proof=required('SCHOOL_FROZEN_PROOF_DIR');
 const fixture=path.join(base,fixtureName);
 assert(path.isAbsolute(proof)&&proof!==base&&proof!==fixture&&!proof.startsWith(fixture+path.sep),'proofs need a separate synthetic output directory outside the frozen fixture');
 const truthPath=path.join(base,'frozen-input-and-truth.json'),resultPath=path.join(base,resultName);
 await ordinaryFile(truthPath);await ordinaryFile(resultPath);
 const truth=await readJSON(truthPath),result=await readJSON(resultPath);
 assert.equal(truth.as_of,AS_OF);assert.equal(truth.child,'虚构孩子甲');assert.equal(truth.source_id,'synthetic-school-20261004');
 assert.equal(truth.expected_count,3);assert.equal(truth.messages.length,4);assert.equal(truth.truth.length,3);
 assert.deepEqual(truth.messages.map(m=>m.id),['m1','m2','m3','m4']);
 assert.equal(truth.document.name,'材料01.docx');assert.equal(truth.document.message_id,'m2');
 assert.equal(result.tasks.length,3);assert.equal(result.production_business_writes,0);assert.equal(result.truth_unchanged,true);
 const observation=result.tasks.find(t=>t.title.includes('观察单')),reading=result.tasks.find(t=>t.title.includes('朗读')),admin=result.tasks.find(t=>t.title.includes('紧急联系电话'));
 assert(observation&&reading&&admin);assert.equal(observation.due,AS_OF);assert.equal(reading.due,AS_OF);assert.equal(admin.due,'2026-10-05');
 assert(result.tasks.every(t=>t.child===truth.child&&t.original_status==='待跟进'));
 const item=result.items.find(i=>i.task_id===observation.id),plan=JSON.parse(item.plan);
 const uploadIDs=[...new Set(plan.school_original_action.anchors.flatMap(a=>a.upload_ids))];assert.equal(uploadIDs.length,1);
 assert.match(uploadIDs[0],/^[a-f0-9]{32}$/);
 const allowed=['家庭运行规则.md','private/family.sqlite3','private/agent.json','private/uploads/'+uploadIDs[0]];
 // Copy only the named files. Unexpected files (including model.json) never enter the server.
 async function inventory(dir,prefix=''){
  const found=[];for(const entry of await fs.readdir(dir,{withFileTypes:true})){
   assert(!entry.isSymbolicLink(),'Synthetic fixture contains a symlink');const relative=prefix+entry.name;
   if(entry.isDirectory())found.push(...await inventory(path.join(dir,entry.name),relative+'/'));
   else{assert(entry.isFile(),'Synthetic fixture contains a non-file');found.push(relative)}
  }return found.sort();
 }
 assert.deepEqual(await inventory(fixture),allowed.slice().sort(),'fixture must contain only the frozen database, source config, family rule and DOCX');
 const hashes={};for(const relative of allowed){await ordinaryFile(path.join(fixture,relative));hashes[relative]=await digest(path.join(fixture,relative))}
 hashes['frozen-input-and-truth.json']=await digest(truthPath);hashes[resultName]=await digest(resultPath);
 await fs.mkdir(proof,{recursive:true});assert(!(await fs.lstat(proof)).isSymbolicLink(),'proof directory cannot be a symlink');
 return {base,proof,fixture,allowed,hashes,truth,result,observation,reading,admin,uploadID:uploadIDs[0]};
}

async function syntheticServer(input){
 const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'family-frozen-workflow-')));
 let child;
 try{
  for(const relative of input.allowed){const to=path.join(directory,relative);await fs.mkdir(path.dirname(to),{recursive:true});await fs.copyFile(path.join(input.fixture,relative),to)}
  const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
  const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_')||/^(OPENAI|ANTHROPIC|AZURE_OPENAI|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY)/.test(key))delete env[key];
  env.FAMILY_DATA=path.join(directory,'private');env.PYTHONDONTWRITEBYTECODE='1';
  // Freeze the shared datetime module before importing application modules. app.ROOT
  // remains the candidate source; app.read reads only the copied synthetic rule.
  const setup=String.raw`import sys,os,json,datetime as dt,sqlite3,socket
from pathlib import Path
from urllib.parse import urlparse
root=Path(sys.argv[1]);port=int(sys.argv[2]);source=Path(sys.argv[3]).resolve()
assert root.name.startswith('family-frozen-workflow-') and Path(os.environ['FAMILY_DATA'])==root/'private'
RealDateTime,RealDate=dt.datetime,dt.date
zone=dt.timezone(dt.timedelta(hours=8));fixed=RealDateTime(2026,10,4,10,0,tzinfo=zone)
class FrozenDateTime(RealDateTime):
    @classmethod
    def now(cls,tz=None):
        value=fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
        return cls(value.year,value.month,value.day,value.hour,value.minute,value.second,value.microsecond,tzinfo=value.tzinfo,fold=value.fold)
    @classmethod
    def today(cls):return cls.now()
    @classmethod
    def utcnow(cls):return cls.now(dt.timezone.utc).replace(tzinfo=None)
    def date(self):return FrozenDate(self.year,self.month,self.day)
class FrozenDate(RealDate):
    @classmethod
    def today(cls):return cls(2026,10,4)
dt.datetime,dt.date=FrozenDateTime,FrozenDate
tables=('manual_tasks','task_updates','task_history','uploads','agent_sources','agent_messages','agent_message_attachments','agent_message_drafts','agent_message_pages','agent_media','agent_pdf_material','agent_jobs','agent_items','agent_runtime')
def rows():
    c=sqlite3.connect((root/'private/family.sqlite3').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:
        available={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {table:sorted([dict(r) for r in c.execute('SELECT * FROM '+table)],key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False)) for table in tables if table in available}
    finally:c.close()
baseline=rows();assert len(baseline['manual_tasks'])==3 and len(baseline['agent_messages'])==4
import app
assert app.DATA==root/'private' and app.DB==root/'private/family.sqlite3' and app.ROOT==source
rule=(root/'家庭运行规则.md').read_text();assert '虚构孩子甲' in rule and '虚构孩子乙' in rule
docs={'家庭运行规则.md':rule,'跟踪台账.md':'','消息来源.md':'仅冻结的虚构学校群；不采集任何客户端。','学习与成长.md':'虚构技术验收；不代表孩子实际完成或掌握。'}
app.read=lambda name:docs.get(name,'')
assert not (app.DATA/'model.json').exists()
blocked=dict(model=0,collection=0,printing=0,unexpected_post=0,network=0)
def deny_model(*args,**kwargs):
    blocked['model']+=1;raise AssertionError('No model boundary is authorized in frozen workflow acceptance')
app.family_llm._chat_json=deny_model
app.printer_config=lambda:dict(printers=[],error='')
real_connect=socket.socket.connect
def local_connect(sock,address):
    if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
        blocked['network']+=1;raise AssertionError('No external network in frozen acceptance')
    return real_connect(sock,address)
socket.socket.connect=local_connect
get,post=app.Handler.do_GET,app.Handler.do_POST
def frozen_get(self):
    route=urlparse(self.path).path
    if route=='/__fixture/frozen-integrity':
        current=rows()
        with app.connect_read_only() as c:
            records=[dict(r) for r in c.execute('SELECT * FROM records ORDER BY id')]
            names={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            print_jobs=c.execute('SELECT COUNT(*) FROM print_jobs').fetchone()[0] if 'print_jobs' in names else 0
            usage=c.execute('SELECT COUNT(*) FROM llm_usage_ledger').fetchone()[0] if 'llm_usage_ledger' in names else 0
        return self.reply(200,dict(synthetic_only=True,as_of='2026-10-04',server_time=fixed.isoformat(),source_root=str(app.ROOT),isolated_data=str(app.DATA),baseline=baseline,current=current,records=records,blocked=blocked,print_jobs=print_jobs,usage_rows=usage))
    if route.startswith('/api/print') and route not in ('/api/print/homework/materials','/api/print/homework/sources'):
        blocked['printing']+=1;return self.reply(409,dict(error='Printing is excluded from this synthetic workflow'))
    return get(self)
def frozen_post(self):
    route=urlparse(self.path).path
    if route.startswith('/api/print'):blocked['printing']+=1
    elif route.startswith('/api/agent/collector'):blocked['collection']+=1
    elif route not in ('/api/task/feedback','/api/wrong/save','/api/record'):blocked['unexpected_post']+=1
    else:return post(self)
    return self.reply(409,dict(error='Only existing synthetic feedback, wrong-item and correction saves are authorized'))
app.Handler.do_GET,app.Handler.do_POST=frozen_get,frozen_post
app.prepare_assets()
server=app.ThreadingHTTPServer(('127.0.0.1',port),app.Handler)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close()
`;
  let failure,logs='';child=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',setup,directory,String(port),__dirname],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});
  child.on('error',error=>failure=error);for(const stream of [child.stdout,child.stderr])stream.on('data',bytes=>logs=(logs+bytes.toString()).slice(-20000));
  const stop=async()=>{try{if(!failure&&child.exitCode===null&&child.signalCode===null){const exited=once(child,'exit');child.kill('SIGINT');await Promise.race([exited,delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await exited}}}finally{await fs.rm(directory,{recursive:true,force:true})}};
  const url='http://127.0.0.1:'+port+'/';
  try{await eventually(async()=>{if(failure)throw failure;if(child.exitCode!==null)throw Error('Synthetic server exited: '+logs);try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated frozen server startup');return {url,directory,stop}}catch(error){await stop();throw error}
 }catch(error){if(!child)await fs.rm(directory,{recursive:true,force:true});throw error}
}

async function jsonAt(host,route){const response=await fetch(host.url+route);assert.equal(response.status,200,route+' is readable');return response.json()}
function integrity(value,input){
 assert.equal(value.synthetic_only,true);assert.equal(value.as_of,AS_OF);assert.equal(value.server_time,FIXED_TIME);assert.equal(value.source_root,__dirname);
 assert(path.basename(path.dirname(value.isolated_data)).startsWith('family-frozen-workflow-'));
 assert.deepEqual(value.current,value.baseline,'all frozen source, task, attachment and accepted decision rows are unchanged');
 assert.deepEqual(value.blocked,{model:0,collection:0,printing:0,unexpected_post:0,network:0});assert.equal(value.print_jobs,0);assert.equal(value.usage_rows,0);
 const messages=value.current.agent_messages;assert.equal(messages.length,4);
 for(const expected of input.truth.messages){const row=messages.find(m=>m.id===expected.id);assert.equal(row.source_id,input.truth.source_id);const payload=JSON.parse(row.payload);assert.equal(payload.text,expected.text);assert.equal(payload.time,expected.time);assert.equal(payload.unread,expected.id==='m2')}
}

// The first attempt never reaches the server. The second is the exact same numbered body.
async function zeroWriteRetry(page,host,route,button,error,success){
 const before=await jsonAt(host,'__fixture/frozen-integrity'),bodies=[],results=[];
 await page.route('**'+route,async request=>{
  bodies.push(request.request().postDataJSON());
  if(bodies.length===1)return request.fulfill({status:503,json:{error:'虚构503：未写入，请使用原编号重试'}});
  const response=await request.fetch(),value=await response.json();assert.equal(response.status(),200,JSON.stringify(value));results.push(value);return request.fulfill({response,json:value});
 });
 try{
  await button.click();await eventually(error,'zero-write 503 is visible');
  const failed=await jsonAt(host,'__fixture/frozen-integrity');assert.deepEqual(failed.records,before.records,'503 created or changed no record');assert.deepEqual(failed.current,before.current,'503 changed no frozen source, task or attachment row');assert.equal(failed.print_jobs,before.print_jobs);assert.equal(failed.usage_rows,before.usage_rows);assert.deepEqual(failed.blocked,before.blocked);
  await button.click();await eventually(success,'same numbered retry succeeds');
 }finally{await page.unroute('**'+route)}
 assert.equal(bodies.length,2);assert.deepEqual(bodies[1],bodies[0]);assert(bodies[0].request_key);
 const saved=results[0],id=route==='/api/wrong/save'?saved.saved?.[0]?.id:saved.record_id??saved.id;
 assert(Number.isInteger(id));assert.equal((await jsonAt(host,'__fixture/frozen-integrity')).records.length,before.records.length+1);
 return {record_id:id,request_key:bodies[0].request_key,attempts:2,zero_write_failure:true};
}

(async()=>{
 let input,browser,host,page;const checks=[];
 try{
  input=await inputs();browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440]){
   host=await syntheticServer(input);const context=await browser.newContext({viewport:{width,height:850},timezoneId:'Asia/Shanghai'});
   await context.addInitScript(stamp=>{const OriginalDate=Date;class FrozenDate extends OriginalDate{constructor(...args){super(...(args.length?args:[stamp]))}static now(){return stamp}}globalThis.Date=FrozenDate},Date.parse(FIXED_TIME));
   page=await context.newPage();const errors=[],unexpected=[],requests=[];page.on('pageerror',error=>errors.push(error.message));
   await context.route('**/*',async request=>{const url=new URL(request.request().url());requests.push({method:request.request().method(),path:url.pathname});if(url.origin!==new URL(host.url).origin){unexpected.push(url.origin+url.pathname);return request.abort()}return request.continue()});
   const state=await jsonAt(host,'api/state'),before=await jsonAt(host,'__fixture/frozen-integrity');integrity(before,input);
   assert.equal(state.today,AS_OF);assert.equal(state.tasks.length,3);assert.equal(state.records.length,0);assert.equal(state.printing.jobs.length,0);assert.equal(state.llm.configured,false);
   const expectedTasks=input.result.tasks.slice().sort((a,b)=>a.id.localeCompare(b.id)),rawTasks=before.current.manual_tasks.slice().sort((a,b)=>a.id.localeCompare(b.id));assert.deepEqual(rawTasks,expectedTasks,'frozen replay tasks are copied without changes');
   const observation=state.tasks.find(t=>t.id===input.observation.id),reading=state.tasks.find(t=>t.id===input.reading.id),admin=state.tasks.find(t=>t.id===input.admin.id);
   assert.equal(observation.agenda.category,'homework');assert.equal(reading.agenda.category,'homework');assert.equal(admin.agenda.category,'todo');assert.equal(admin.agenda.due_on,'2026-10-05');
   for(const task of [observation,reading]){assert.match(task.title,/语文/);assert.equal(task.agenda.due_on,AS_OF)}
   for(const text of ['第2–4自然段','两遍','给家长听','不用录音','不用上传'])assert(reading.action.includes(text),'reading retains its exact frozen requirement: '+text);
   for(const text of ['A、B栏仍必做','C栏改为选做','不做C栏也算完成观察单','语文本','两个描写桥的词语','三句完整的话','位置','外形','用途','不得照抄参考句','不用打印或上传'])assert(observation.action.includes(text),'observation retains its full frozen completion standard: '+text);
   assert.doesNotMatch(observation.action,/补发|稍后附件|更正10月3日|其余要求和原期限不变/,'transport and correction provenance stays in the original source');assert.equal(observation.action.split('C栏改为选做').length-1,1,'effective C condition appears only once');
   await page.goto(host.url);await ready(page);assert.equal(await page.evaluate(()=>new Date().toISOString()),new Date(FIXED_TIME).toISOString());
   const card=id=>page.locator('[data-query-target="task:'+id+'"]'),homework=page.locator('#task-group-homework'),todos=page.locator('#task-group-todo');
   assert.deepEqual((await homework.locator('[data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask))).sort(),[observation.id,reading.id].sort());
   assert.deepEqual(await todos.locator('[data-today-task]').evaluateAll(xs=>xs.map(x=>x.dataset.todayTask)),[admin.id]);
   assert.match(await homework.locator('h2').innerText(),/今日作业 · 2/);assert.match(await card(admin.id).innerText(),/2026-10-05/);
   for(const task of [observation,reading,admin]){assert.equal(await card(task.id).isVisible(),true);assert.equal(await card(task.id).locator('[data-check]').isChecked(),false)}
   await fit(page);await page.screenshot({path:path.join(input.proof,'frozen-today-'+width+'.png'),fullPage:true});

   const original=page.locator('#schoolOriginalDialog'),materialChecks=[];
   // This administrative message has no material-action anchors. Its existing
   // read-only original API proves it has no file; only the learning tasks have
   // a scoped-material UI contract in this frozen replay.
   const adminOriginal=await jsonAt(host,'api/agent/message?'+new URLSearchParams({child_id:'child-1',source_id:input.truth.source_id,message_id:'m3'}));
   assert.deepEqual(adminOriginal.attachments,[]);assert.equal(adminOriginal.message.text,input.truth.messages.find(m=>m.id==='m3').text);materialChecks.push({task_id:admin.id,message_id:'m3',attachment_count:0,inspection:'existing read-only original API'});
   for(const [task,message,attachment] of [[reading,'m1',false],[observation,'m2',true]]){
    const button=card(task.id).locator('[data-school-original-ref="message:'+input.truth.source_id+':'+message+'"]:visible').first();
    await button.click();await original.locator('[data-task-material-scope=action]').waitFor();
    assert.equal(await original.locator('.task-record-files a[href="/upload/'+input.uploadID+'"]').count(),attachment?1:0,'only the observation sheet has its DOCX');
    assert.equal(await original.locator('.task-record-files a').count(),attachment?1:0,'no other-task attachment appears');
    await fit(page);materialChecks.push({task_id:task.id,message_id:message,attachment_count:attachment?1:0});
    if(attachment){await page.screenshot({path:path.join(input.proof,'frozen-original-'+width+'.png')});await original.locator('[data-school-task-source]').click();await original.getByRole('heading',{name:'老师完整原消息',exact:true}).waitFor();await eventually(async()=>await original.locator('blockquote.source').innerText()===input.truth.messages.find(m=>m.id===message).text,'complete original notice remains verbatim');await original.locator('[data-school-task-source]').click();await original.locator('[data-task-material-scope=action]').waitFor()}
    await original.locator('[data-school-original-close]').click();
   }
   const openObservation=async()=>{await card(observation.id).locator('[data-task="'+observation.id+'"]:visible').first().click();await page.locator('#taskDialog[open]').waitFor();assert.equal(await page.locator('#taskForm [name=id]').inputValue(),observation.id);assert.equal(await page.locator('#taskRequirement').innerText(),observation.action)};
   await openObservation();
   const feedbackNote='虚构作答：A栏写“古老、坚固”。B栏写“桥在小镇的河上。”“桥有弯弯的桥面。”“这座桥像一条连接两岸的纽带。”C栏未做（老师已改为选做）；B栏第三句照抄参考，需要订正。';
   await page.locator('#taskForm [name=note]').fill(feedbackNote);
   const feedback=await zeroWriteRetry(page,host,'/api/task/feedback',page.locator('#saveTaskFeedback'),async()=>/虚构503/.test(await page.locator('#taskError').innerText()),async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()));
   const wrong=page.locator('#taskFeedbackHistory [data-task-wrong-form="'+feedback.record_id+'"]');await wrong.locator(':scope > summary').click();assert.equal(await wrong.locator('[data-task-wrong-photo]').count(),0);
   await wrong.locator('[data-wrong-field=label]').fill('观察单B栏第三句');await wrong.locator('[data-wrong-field=text]').fill('用自己的话写完整一句说明桥的用途，不得照抄参考句。');await wrong.locator('[data-wrong-field=answer]').fill('这座桥像一条连接两岸的纽带。');await wrong.locator('[data-wrong-field=correction]').fill('这座桥让两岸的人能够过河。');
   const wrongSaved=await zeroWriteRetry(page,host,'/api/wrong/save',wrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await wrong.innerText()),async()=>/错题已保存在这份作业下/.test(await page.locator('#taskFeedbackStatus').innerText()));
   const wrongCard=page.locator('#taskFeedbackHistory .task-feedback-record').filter({has:page.locator('[data-record="'+wrongSaved.record_id+'"]')});await wrongCard.locator('[data-followup]').click();await page.locator('#recordDialog[open]').waitFor();
   const form=page.locator('#recordForm'),correctionNote='虚构订正：B栏第三句改为“这座桥让两岸的人能够过河。”已对照不要照抄的要求；未判断掌握，独立复测待做。';
   assert.equal(await form.locator('[name=followup_kind]').inputValue(),'订正');assert.equal(await form.locator('[name=related_record_id]').inputValue(),String(wrongSaved.record_id));await form.locator('[name=note]').fill(correctionNote);
   const correction=await zeroWriteRetry(page,host,'/api/record',form.locator('[type=submit]'),async()=>/虚构503/.test(await page.locator('#recordError').innerText()),async()=>!await page.locator('#recordDialog').evaluate(x=>x.open));
   assert.equal(await page.locator('#taskDialog').evaluate(x=>x.open),false,'starting correction closed the original task without discarding its saved feedback');await openObservation();await page.locator('#taskDialog [data-close=taskDialog]').click();assert.equal(await page.locator('#taskDialog').evaluate(x=>x.open),false);await page.reload();await ready(page);await openObservation();
   await page.locator('#taskFeedbackHistory').getByText(feedbackNote,{exact:true}).waitFor();await page.locator('#taskFeedbackHistory').getByText(correctionNote,{exact:true}).waitFor();await eventually(async()=>/观察单B栏第三句/.test(await page.locator('#taskFeedbackHistory .task-feedback-record').filter({has:page.locator('[data-record="'+wrongSaved.record_id+'"]')}).innerText()),'saved wrong item reopens under original homework');
   assert.match(await card(observation.id).locator('[data-task="'+observation.id+'"]:visible').first().innerText(),/查看\/补充反馈/);await fit(page);await page.screenshot({path:path.join(input.proof,'frozen-reopened-'+width+'.png')});
   const after=await jsonAt(host,'api/state'),savedIntegrity=await jsonAt(host,'__fixture/frozen-integrity');integrity(savedIntegrity,input);
   assert.deepEqual(after.tasks,state.tasks,'feedback, wrong item and correction leave all three canonical tasks unchanged');assert.equal(after.records.length,3);
   const savedFeedback=after.records.find(r=>r.id===feedback.record_id),savedWrong=after.records.find(r=>r.id===wrongSaved.record_id),savedCorrection=after.records.find(r=>r.id===correction.record_id);
   assert.equal(savedFeedback.note,feedbackNote);assert.equal(savedWrong.related_record_id,feedback.record_id);assert.equal(savedCorrection.related_record_id,wrongSaved.record_id);assert.equal(savedCorrection.followup_kind,'订正');assert.equal(savedCorrection.note,correctionNote);
   assert.equal(savedFeedback.source,'事项:'+observation.id);for(const record of [savedWrong,savedCorrection])assert.equal(record.linked_task_id,observation.id);
   for(const record of [savedFeedback,savedWrong,savedCorrection]){assert.equal(record.child,input.truth.child);assert.equal(record.day,AS_OF)}
   assert.equal(after.records.some(r=>[reading.id,admin.id].includes(r.linked_task_id)||[reading.id,admin.id].some(id=>r.source==='事项:'+id)),false);assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);assert.equal(requests.some(r=>r.path.startsWith('/api/print')&&!['/api/print/homework/materials','/api/print/homework/sources'].includes(r.path)||r.path.startsWith('/api/agent/collector')),false);
   const check={width,scope:'frozen synthetic replay database through existing product UI; no real model, collection or printing',as_of:AS_OF,today_homework:[observation.id,reading.id],tomorrow_parent_task:admin.id,materialChecks,feedback,wrong:wrongSaved,correction,source_rows_preserved:true,other_tasks_unchanged:true,integrity:savedIntegrity};checks.push(check);
   await fs.writeFile(path.join(input.proof,'frozen-workflow-'+width+'.json'),JSON.stringify(check,null,2));await context.close();page=null;await host.stop();host=null;
  }
  for(const [relative,hash] of Object.entries(input.hashes)){const file=relative.startsWith('private/')||relative==='家庭运行规则.md'?path.join(input.fixture,relative):path.join(input.base,relative);assert.equal(await digest(file),hash,'frozen input remains byte-identical: '+relative)}
  await fs.writeFile(path.join(input.proof,'frozen-workflow-result.json'),JSON.stringify({synthetic_only:true,as_of:AS_OF,real_model_calls:0,collection_calls:0,printing_calls:0,production_business_writes:0,frozen_hashes:input.hashes,checks},null,2));
  console.log('Frozen school workflow: 360/1440 Today, scoped DOCX, zero-write retry, feedback → wrong item → correction → reopen; sources and other tasks preserved.');
 }catch(error){
  if(input&&page&&!page.isClosed()){await page.screenshot({path:path.join(input.proof,'frozen-failure.png')}).catch(()=>{});await fs.writeFile(path.join(input.proof,'frozen-failure.json'),JSON.stringify({error:String(error),checks},null,2))}
  throw error;
 }finally{try{if(browser)await Promise.race([browser.close(),delay(5000)])}finally{await host?.stop()}}
})().catch(error=>{console.error(error);process.exitCode=1});
