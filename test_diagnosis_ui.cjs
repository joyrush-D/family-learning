// Synthetic real-HTTP journey for the wrong-question loop (③ diagnosis → ④ redo → ⑤ re-check), incl. the Agent's background diagnosis. PLAYWRIGHT_MODULE / PLAYWRIGHT_CHANNEL supported.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
// Model stub: names knowledge points only from the refs it was given; an independent re-check on a fresh item counts against the weakness.
const SERVER=port=>`import sys,json,runpy,tempfile,datetime as dt,family_llm,app,family_agent,family_diagnosis
from pathlib import Path
from types import SimpleNamespace
def model(messages,schema,name,*args,**kwargs):
 value=json.loads(messages[-1]['content'])
 if name!='family_diagnosis':raise family_llm.LLMDraftError('synthetic: unexpected model task '+name)
 recs=value['records'];wrong=[r['ref'] for r in recs if r['kind']=='wrong_question'];exam=[r['ref'] for r in recs if r['kind']=='exam']
 fresh=[r['ref'] for r in recs if r.get('followup')=='复测' and r.get('assistance')=='独立尝试' and r.get('practice_relation')=='相近的新题或新片段']
 if value['subject']=='语文':return dict(knowledge_components=[dict(name='比喻句的本体与喻体',error_type='概念混淆',misconception='把喻体当成本体',status='待验证',evidence=wrong[:1],suggestion='请孩子指出“像”前后各是什么')],summary='先分清本体和喻体',uncertainties=[])
 if value['subject']=='英语':return dict(knowledge_components=[dict(name='ea/ee 拼写',error_type='形近混淆',misconception='待核对',status='待验证',evidence=wrong[:1],suggestion='请孩子先读出单词再拼写')],summary='先核对 ea/ee',uncertainties=[])
 return dict(knowledge_components=[dict(name='两位数进位加法',error_type='进位漏加',misconception='个位满十没有向十位进一',status='有反证' if fresh else '有支持',evidence=wrong+fresh+['record:99999'],suggestion='用小棒摆一摆满十进一'),dict(name='读题',error_type='',misconception='待核对',status='待验证',evidence=exam,suggestion='')],summary='先解决进位漏加',uncertainties=['第5题字迹较淡'])
family_llm._chat_json=model
prepare=app.prepare_assets
def seed():
 prepare()
 today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date();day=lambda n:(today-dt.timedelta(days=n)).isoformat()
 for n,subject,title,note in [(10,'数学','数学错题：第3题','题面：27+8=？\\n学生原答：315\\n可见订正/正确答案：35'),(9,'数学','数学错题：第5题','题面：46+7=？\\n学生原答：413\\n可见订正/正确答案：53'),(2,'语文','语文错题：比喻句','题面：找出比喻句的本体\\n学生原答：月亮\\n可见订正/正确答案：小船')]:
  app.save_record(dict(child='示例星星',day=day(n),category='学习进展',subject=subject,title=title,note=note,source=family_diagnosis.WRONG_SOURCE))
 app.save_record(dict(child='示例星星',day=day(9),category='成绩',subject='数学',title='虚构单元小测',note='进位加法两题出错',score=72,total=100))
 # 数学 was diagnosed eight days ago, so its 7-day re-check is due today; one Agent tick turns it into a reminder
 # and, in the background, diagnoses 语文 (错题 but no diagnosis yet). 英语 arrives after that tick.
 family_diagnosis.diagnose(SimpleNamespace(connect=app.connect,profiles=app.profiles),'child-1','数学',now=dt.datetime.combine(today-dt.timedelta(days=8),dt.time(10)))
 (app.DATA/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[])))
 original=app.ROOT
 with tempfile.TemporaryDirectory(prefix='synthetic-diagnosis-worker-') as folder:
  app.ROOT=Path(folder)
  try:
   for name in ('家庭运行规则.md','消息来源.md','学习与成长.md','跟踪台账.md'):(app.ROOT/name).write_text(app.read(name))
   family_agent.run_once(app)
  finally:app.ROOT=original
 app.save_record(dict(child='示例星星',day=day(0),category='学习进展',subject='英语',title='英语错题：拼写',note='题面：听写 seat\\n学生原答：set\\n可见订正/正确答案：seat',source=family_diagnosis.WRONG_SOURCE))
app.prepare_assets=seed
sys.argv=['demo.py','--port','${port}']
runpy.run_path('demo.py',run_name='__main__')`;
async function start(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 const server=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',SERVER(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});server.stdout.resume();server.stderr.on('data',d=>process.env.DIAGNOSIS_UI_DEBUG&&process.stderr.write(d));
 const url='http://127.0.0.1:'+port+'/';for(let i=0;i<150;i++){try{if((await fetch(url)).ok)return {server,url}}catch{}await wait(80)}
 server.kill();throw Error('synthetic server did not start');
}
(async()=>{let server,browser;try{
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});let checks=0;
 for(const width of [360,1440]){
  const started=await start();server=started.server;const url=started.url;
  const p=await browser.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>{errors.push(e.message);console.error('browser error',e.message)});
  const state=async()=>(await p.request.get(url+'api/state')).json(),goals=async()=>(await p.request.get(url+'api/goals')).json();
  const noOverflow=async label=>assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label+' fits '+width);
  const proof=async(name,target=p)=>{if(process.env.DIAGNOSIS_UI_PROOF_DIR){await fs.mkdir(process.env.DIAGNOSIS_UI_PROOF_DIR,{recursive:true});await target.screenshot({path:path.join(process.env.DIAGNOSIS_UI_PROOF_DIR,name+'-'+width+'.png'),...(target===p?{fullPage:true}:{})})}};
  const seeded=await state(),byTitle=t=>seeded.records.find(r=>r.title===t).id,first=byTitle('数学错题：第3题'),second=byTitle('数学错题：第5题');
  // Agent reminders (更多 → 助手跟进): the due re-check names its evidence and offers the two real next steps, not just "seen".
  await p.goto(url);await p.locator('body[data-page="home"] [data-task-all="homework"]').waitFor();
  await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="agent"]').click();
  const reminder=p.locator('[data-agent-item]').filter({hasText:'到期复测：数学 · 两位数进位加法'});await reminder.waitFor();
  assert.match(await reminder.innerText(),/不代表已经掌握/);
  await reminder.getByText('查看依据',{exact:true}).click();assert.match(await reminder.innerText(),/数学错题：第5题[\s\S]*数学错题：第3题|数学错题：第3题[\s\S]*数学错题：第5题/);
  assert.equal(await reminder.getByRole('button',{name:'记录复测结果',exact:true}).count(),1);
  await noOverflow('today reminder');await proof('today-reminder',reminder);
  await reminder.getByRole('button',{name:'查看错题诊断',exact:true}).click();checks++;
  // The reminder opens this child's profile at the diagnosis section.
  const profile=p.locator('[data-child-profile]'),section=profile.locator('[data-profile-diagnosis]');await section.waitFor();
  assert(await profile.evaluate(d=>d.open),'profile opens at the diagnosis');assert(await section.evaluate(e=>document.activeElement===e),'focus lands on the diagnosis section');
  assert.match(await profile.locator('summary').innerText(),/到期复测 1/);
  const due=section.locator('[data-diagnosis-due]');assert.match(await due.innerText(),/到期复测 · 1[\s\S]*数学 · 两位数进位加法 · 进位漏加/);
  const math=section.locator('[data-diagnosis-subject="数学"]'),chinese=section.locator('[data-diagnosis-subject="语文"]'),english=section.locator('[data-diagnosis-subject="英语"]');
  assert.match(await math.innerText(),/错题 2 条 · 诊断于[\s\S]*先解决进位漏加/);assert.equal(await math.locator('[data-diagnosis-stale]').count(),0);
  const carry=math.locator('[data-diagnosis-kc="两位数进位加法"]');assert.equal(await carry.locator('[data-kc-status]').innerText(),'有支持');
  assert.match(await carry.innerText(),/可能的误解：个位满十没有向十位进一[\s\S]*可以这样核对：用小棒摆一摆满十进一[\s\S]*已到复测日/);
  assert.equal(await carry.locator('[data-goal-record]').count(),2,'only the real cited records are listed; the invented ref is dropped');assert.doesNotMatch(await carry.innerText(),/99999/);
  assert.equal(await math.locator('[data-diagnosis-kc="读题"] [data-kc-status]').innerText(),'待验证');assert.match(await math.innerText(),/待核对：第5题字迹较淡/);
  assert.match(await chinese.innerText(),/比喻句的本体与喻体 · 概念混淆[\s\S]*待验证/,'the Agent diagnosed 语文 in the background');assert.doesNotMatch(await chinese.innerText(),/尚未诊断/);
  assert.match(await english.innerText(),/已有 1 条错题，尚未诊断/);assert.match(await english.locator('[data-diagnosis-auto]').innerText(),/助手会在后台检查时更新诊断/);
  await noOverflow('diagnosis section');assert.equal(await section.locator('button').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'diagnosis controls stay touchable');await proof('diagnosis',section);checks++;
  // A cited record opens as the editable original.
  await carry.locator(`[data-goal-record="${first}"]`).click();await p.locator('#recordDialog[open]').waitFor();
  assert.match(await p.locator('#recordForm [name="note"]').inputValue(),/题面：27\+8=？/);await p.locator('#recordDialog').evaluate(d=>d.close());checks++;
  // Parent-triggered diagnosis: a failed call keeps everything and can be retried.
  let failed=false;await p.route('**/api/diagnosis/run',async route=>{if(!failed){failed=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构模型暂时不可用'})})}else await route.continue()});
  await english.getByRole('button',{name:'诊断这科错题',exact:true}).click();await p.getByText(/虚构模型暂时不可用。错题原记录仍在，可以稍后重试。/).waitFor();
  assert.match(await english.innerText(),/尚未诊断/);await english.getByRole('button',{name:'诊断这科错题',exact:true}).click();
  await p.getByText(/诊断已更新/).waitFor();await p.unroute('**/api/diagnosis/run');
  assert.match(await english.innerText(),/ea\/ee 拼写 · 形近混淆[\s\S]*待验证/);assert.equal(await english.locator('[data-diagnosis-auto]').count(),0);assert(await profile.evaluate(d=>d.open),'the profile stays open across refresh');checks++;
  // ④ Re-work the latest cited mistake as an unshared, answer-safe guided draft; a second tap reopens it.
  await carry.getByRole('button',{name:'让孩子重做这道错题',exact:true}).click();await p.getByText(/已准备重做草稿（未分享）/).waitFor();
  const guided=async()=>(await(await p.request.post(url+'api/guided/state',{headers:{'X-Family-Token':(await state()).token},data:{}})).json()).sessions.filter(s=>s.related_record_id===second);
  let drafts=await guided();assert.equal(drafts.length,1);assert.deepEqual([drafts[0].question_text,drafts[0].reference_text,drafts[0].shared,drafts[0].reference_checked],['46+7=？','53',false,false]);
  await p.reload();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();await profile.waitFor();await profile.locator('summary').click();
  await carry.getByRole('button',{name:'让孩子重做这道错题',exact:true}).click();await p.getByText(/这道错题已有未分享的重做草稿/).waitFor();assert.equal((await guided()).length,1,'no duplicate draft after reload');
  await carry.getByRole('button',{name:/去“一起学习”核对并分享/}).click();await p.locator('[data-guided-session]').filter({hasText:'订正 · 数学错题：第5题'}).waitFor();checks++;
  // ⑤ Record the re-check against the original mistake, then re-diagnose: the stale notice and the due re-check clear.
  await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();await profile.waitFor();if(!await profile.evaluate(d=>d.open))await profile.locator('summary').click();
  await due.getByRole('button',{name:'记录复测结果',exact:true}).click();await p.locator('#recordDialog[open]').waitFor();
  const form=p.locator('#recordForm');assert.equal(await form.locator('[name="related_record_id"]').inputValue(),String(second));assert.equal(await form.locator('[name="followup_kind"]').inputValue(),'复测');
  await form.locator('[name="note"]').fill('虚构复测：新题 38+5=43，自己做对，说出满十进一。');await form.locator('[name="assistance"]').selectOption('独立尝试');await form.locator('[name="practice_relation"]').selectOption('相近的新题或新片段');
  await form.getByRole('button',{name:'保存记录',exact:true}).click();await p.locator('#recordDialog').waitFor({state:'hidden'});
  await math.locator('[data-diagnosis-stale]').waitFor();assert.match(await math.innerText(),/诊断之后有新的错题、考试、复测或更正[\s\S]*助手会在后台检查时更新诊断/);
  await math.getByRole('button',{name:'结合最新记录重新诊断',exact:true}).click();await p.getByText(/诊断已更新/).waitFor();
  assert.equal(await carry.locator('[data-kc-status]').innerText(),'有反证');assert.equal(await math.locator('[data-diagnosis-stale]').count(),0);assert.equal(await math.locator('[data-diagnosis-auto]').count(),0);
  assert.equal(await section.locator('[data-diagnosis-due]').count(),0);assert.doesNotMatch(await profile.locator('summary').innerText(),/到期复测/);
  const after=(await goals()).diagnosis['child-1'];assert.deepEqual(after.due,[]);assert.equal(after.subjects.find(s=>s.subject==='数学').diagnosis.knowledge_components[0].review_on,'');
  assert.deepEqual((await goals()).diagnosis['child-2'].subjects,[],'another child sees none of this');
  await noOverflow('after re-diagnosis');await proof('rediagnosed',section);checks++;
  assert.deepEqual(errors,[]);await p.close();server.kill();await once(server,'exit');server=null;
 }
 console.log(`PASS: ${checks} wrong-question diagnosis checks at 360/1440 (reminder, profile, background diagnosis, evidence, retry, redo draft, re-check, re-diagnosis)`);
}catch(error){console.error(error);process.exitCode=1}finally{await browser?.close();server?.kill()}})();
