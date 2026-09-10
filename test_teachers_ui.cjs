// Only synthetic, in-memory API data. No household services, accounts, model calls or collectors.
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {once}=require('node:events');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fixture=()=>({children:[{id:'child-a',name:'虚构孩子甲'},{id:'child-b',name:'虚构孩子乙'}],sources:[{id:'source-a',name:'虚构课堂群',child_id:'child-a',platform:'qq',enabled:false}],source_error:'',teachers:[
 {id:'TEACH-A',version:1,display_name:'虚构甲老师',subject:'语文',child_ids:['child-a'],source_ids:['source-a'],public_url:'https://school.example/teaching',archived:false,public_info:{url:'https://school.example/teaching',status:'changed',text:'公开教学摘录：先解释自己的思路。<img src=x onerror="window.injected=true">',last_attempt:'2026-09-01T12:00:00+08:00',last_success:'2026-09-01T12:00:00+08:00',changed_at:'2026-09-01T12:00:00+08:00'}},
 {id:'TEACH-B',version:1,display_name:'虚构乙老师',subject:'数学',child_ids:['child-b'],source_ids:[],public_url:'',archived:false,public_info:{status:'unconfigured'}}],observations:[
 {id:'TEACHOBS-A',version:1,teacher_id:'TEACH-A',day:'2026-09-01',kind:'praise',target:'other_students',child_id:'',behavior:'表扬先说明思路再回答的行为 <img src=x onerror="window.injected=true">',teacher_reason:'有依据地表达',parent_note:'可以和孩子商量练习口述思路',source_id:'source-a',message_id:'',source_url:'',status:'active'}]});
async function run(browser,width){
 let state=fixture(),failure='',writes=0,lastBody=null;const keys=new Map();
 const server=http.createServer(async(req,res)=>{
  const send=(code,body)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(body))};
  if(req.url==='/api/teachers'){send(200,state);return}
  if(req.url.startsWith('/api/teachers/')){
   let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw);lastBody=body;
   if(failure==='auth'){failure='';send(401,{error:'请重新登录'});return}
   if(failure==='conflict'){failure='';const at=state.observations.findIndex(x=>x.id===body.id);state.observations[at]={...state.observations[at],behavior:'另一位家长已补充的具体行为',version:2};send(409,{error:'记录已被更新'});return}
   const kind=req.url.endsWith('profile')?'teacher':'observation',list=kind==='teacher'?'teachers':'observations';
   if(keys.has(body.request_key)){send(200,keys.get(body.request_key));return}
   const item={...body,id:body.id||'SYNTHETIC-'+(++writes),version:body.version+1};delete item.request_key;
   if(body.id)writes++;
   const at=state[list].findIndex(x=>x.id===item.id);if(at<0)state[list].unshift(item);else state[list][at]=item;
   const result={ok:true,[kind]:item};keys.set(body.request_key,result);
   if(failure==='lost'){failure='';res.writeHead(200,{'Content-Type':'application/json'});res.end('{');return}
   send(200,result);return;
  }
  if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/ui.css"><link rel="stylesheet" href="/teachers.css"><body style="padding:16px"><div id="root"></div><script src="/teachers.js"></script><script>window.mount=id=>FamilyTeachers.mount({root:document.querySelector("#root"),apiFetch:(...args)=>fetch(...args),token:"synthetic",teacherId:id});mount();</script>');return}
  if(['/ui.css','/teachers.css','/teachers.js'].includes(req.url)){res.setHeader('Content-Type',req.url.endsWith('.js')?'application/javascript':'text/css');res.end(fs.readFileSync(path.join(__dirname,req.url)));return}
  res.writeHead(404);res.end();
 });server.listen(0,'127.0.0.1');await once(server,'listening');
 const page=await browser.newPage({viewport:{width,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const profile=()=>page.locator('[data-teacher-form="profile"]'),form=()=>page.locator('[data-teacher-form="observation"]'),status=()=>page.locator('#teachersStatus');
 const settled=()=>page.waitForFunction(()=>!document.querySelector('[data-teacher-retry]')&&document.querySelector('#teachersStatus').textContent.includes('已保存'));
 try{
  await page.goto('http://127.0.0.1:'+server.address().port+'/');await page.locator('[data-teacher-observation]').waitFor();
  assert.match(await page.locator('.teacher-records').innerText(),/老师说明的理由：[\s\S]*有依据地表达/);
  assert.match(await page.locator('.teacher-records').innerText(),/家长理解 · 待核对/);
  assert.equal(await page.locator('img').count(),0);assert.equal(await page.evaluate(()=>window.injected),undefined);
  assert.match(await page.locator('.teacher-public').innerText(),/资料曾更新/);
  await page.locator('.teacher-profile summary').click();await profile().locator('[name="display_name"]').fill('虚构未保存称呼');
  await page.locator('[data-teacher-select="TEACH-B"]').click();await page.locator('[data-teacher-select="TEACH-A"]').click();assert.equal(await profile().locator('[name="display_name"]').inputValue(),'虚构未保存称呼');
  await page.locator('.teacher-write summary').click();await form().locator('[name="kind"]').selectOption('praise');await form().locator('[name="target"]').selectOption('other_students');
  await form().locator('[name="behavior"]').fill('虚构记录：独立订正并说明原因');await form().locator('[name="teacher_reason"]').fill('老师原话：解释清楚');await form().locator('[name="parent_note"]').fill('家长待核对想法');
  assert.equal(await form().locator('[data-teacher-own]').isVisible(),false);assert.equal(await form().locator('[name="other_student_name"]').count(),0);
  await page.evaluate(()=>{FamilyTeachers.leave();document.querySelector('#root').innerHTML='另一页';mount()});await form().waitFor();assert.equal(await form().locator('[name="behavior"]').inputValue(),'虚构记录：独立订正并说明原因');
  failure='auth';await form().locator('[type="submit"]').click();await page.locator('[data-teacher-retry]:not([disabled])').waitFor();const originalKey=lastBody.request_key;assert.equal(await form().locator('[name="behavior"]').inputValue(),'虚构记录：独立订正并说明原因');
  await page.locator('[data-teacher-retry]').click();await settled();assert.equal(lastBody.request_key,originalKey);assert.equal(lastBody.child_id,'');assert.equal(writes,1);assert.equal(await profile().locator('[name="display_name"]').inputValue(),'虚构未保存称呼');
  await page.locator('.teacher-write summary').click();await form().locator('[name="behavior"]').fill('虚构丢失答复检查');failure='lost';await form().locator('[type="submit"]').click();await page.locator('[data-teacher-retry]:not([disabled])').waitFor();const lostKey=lastBody.request_key;
  await page.locator('[data-teacher-retry]').click();await settled();assert.equal(lastBody.request_key,lostKey);assert.equal(writes,2);assert.equal(state.observations.filter(x=>x.behavior==='虚构丢失答复检查').length,1);
  await page.locator('[data-teacher-edit="TEACHOBS-A"]').click();await form().locator('[name="behavior"]').fill('虚构本机更正草稿');failure='conflict';await form().locator('[type="submit"]').click();await page.locator('[data-teacher-conflict]').waitFor();
  await page.locator('[data-teacher-conflict]').click();await page.locator('[data-teacher-accept-version]').waitFor();assert.equal(await form().locator('[name="behavior"]').inputValue(),'虚构本机更正草稿');assert.match(await page.locator('.teacher-records').innerText(),/另一位家长已补充/);
  await page.locator('[data-teacher-accept-version]').click();assert.equal(await form().getAttribute('data-version'),'2');await form().locator('[name="status"]').selectOption('withdrawn');await form().locator('[type="submit"]').click();await settled();assert.equal(lastBody.status,'withdrawn');assert.equal(lastBody.version,2);
  await page.evaluate(()=>{FamilyTeachers.leave();mount('TEACH-B')});await page.waitForFunction(()=>document.querySelector('[data-teacher-select="TEACH-B"]')?.getAttribute('aria-pressed')==='true');assert.equal(await page.locator('[data-teacher-observation]').count(),0);
  await page.locator('[data-teacher-select="TEACH-A"]').click();await page.locator('.teacher-profile').evaluate(el=>el.open=true);await profile().locator('[data-teacher-discard]').click();assert.equal(await profile().locator('[name="display_name"]').inputValue(),'虚构甲老师');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'viewport fits');
  assert.equal(await page.locator('.teachers-view button:visible,.teachers-view summary:visible').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'touch targets');
  assert.deepEqual(errors,[]);
  if(process.env.TEACHERS_UI_PROOF_DIR){fs.mkdirSync(process.env.TEACHERS_UI_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.TEACHERS_UI_PROOF_DIR,'teachers-'+width+'.png'),fullPage:true})}
  return {width,draftsAcrossTeachersAndPages:true,authRetry:true,lostReplyDeduplicated:true,conflictChecked:true,correctionAndWithdrawal:true,teacherCitationSelection:true,otherStudentNameAbsent:true,escapedEvidence:true,noOverflow:true};
 }finally{await page.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
}
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});try{const result=[];for(const width of [360,1440])result.push(await run(browser,width));console.log(JSON.stringify({passed:true,synthetic:true,checks:result},null,2))}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
