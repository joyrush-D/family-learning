// Synthetic real-HTTP parent journey. PLAYWRIGHT_MODULE / PLAYWRIGHT_CHANNEL supported.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{let server,browser;try{
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 server=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',`import sys,json,runpy,family_llm,app,family_agent,tempfile
from pathlib import Path
from test_goals import synthetic_plan
def model(messages,schema,name,*args,**kwargs):
 if name=='family_wrong_questions_annotate':
  return dict(pages=[dict(page=1,regions=[dict(kind='wrong_item',box=dict(x=100,y=120,w=300,h=90),label='第3题',text='27 + 8 = ?',answer='35',correction='正确 35',uncertain=False),dict(kind='layout',box=dict(x=0,y=0,w=1000,h=60),label='卷头',text='数学小测',answer='',correction='',uncertain=False)])],uncertainties=['第3题字迹较淡，请核对'])
 value=json.loads(messages[-1]['content'])
 if name=='family_agent_selection':
  e=value['evidence'][0]
  return dict(proposals=[dict(title_quote=e['text'],focus='school',due='',learning_subject='语文',learning_goal_id='',evidence=[dict(ref=e['ref'])])])
 if name=='family_agent_plan':return dict(proposal=None)
 result=synthetic_plan(value)
 if value.get('learning_goal',{}).get('title','').startswith('虚构画像范围'):
  result['proposal']['hypotheses'][0].update(reason='虚构范围判断',support=[value['evidence'][-1]['ref']])
 teacher=next((e for e in value['evidence'] if e.get('source_kind')=='teacher_record'),None)
 if teacher:result['proposal']['evidence']=[dict(ref=teacher['ref'],quote=teacher['text'][:30])]
 return result
family_llm._chat_json=model
family_llm.configuration=lambda *a,**k:None
prepare=app.prepare_assets
def seed():
 prepare()
 (app.DATA/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[dict(id='synthetic-ui-class',platform='wechat',child_id='child-2',name='虚构课堂',cursor='0',enabled=True)])))
 stamp=family_agent._now().isoformat()
 app.agent_store().ingest(dict(source_id='synthetic-ui-class',expected_cursor='0',cursor='1',checked_at=stamp,last_message_time=stamp,error='',messages=[dict(id='1',time=stamp,kind='text',sender='虚构发布者',text='语文观察：任选一种顺序介绍文具，说出用途和真实细节。',unread=False)]))
 original=app.ROOT
 with tempfile.TemporaryDirectory(prefix='synthetic-ui-worker-') as folder:
  app.ROOT=Path(folder)
  try:
   for name in ('家庭运行规则.md','消息来源.md','学习与成长.md','跟踪台账.md'):(app.ROOT/name).write_text(app.read(name))
   family_agent.run_once(app)
  finally:app.ROOT=original
app.prepare_assets=seed
sys.argv=['demo.py','--port','${port}']
runpy.run_path('demo.py',run_name='__main__')`],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});server.stdout.resume();server.stderr.resume();
 const url='http://127.0.0.1:'+port+'/';let ready=false;for(let i=0;i<100;i++){try{if((await fetch(url)).ok){ready=true;break}}catch{}await wait(80)}assert(ready,'demo started');
 browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});let checks=0;
 for(const width of [360,1440]){
  const p=await browser.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>{errors.push(e.message);console.error('browser error',e.message)});await p.goto(url);await p.locator('body[data-page="home"] [data-task-all="homework"]').waitFor();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();await p.locator('[data-goal-form="create"]').waitFor({state:'attached'});
  const create=p.locator('[data-goal-form="create"]');await create.locator('xpath=ancestor::details').evaluate(e=>e.open=true);
  await create.getByLabel('阶段目标',{exact:true}).fill('虚构英语目标 '+width);await create.getByLabel('科目',{exact:true}).fill('英语');await create.getByLabel('目前实际表现',{exact:true}).fill('家长观察：有时猜答案，尚未核对原因。');await create.getByText('补充学校要求或已有材料 · 可选',{exact:true}).click();await create.getByLabel('学校要求 / 考试范围',{exact:true}).fill('虚构老师要求：任选一种说明顺序，介绍文具的用途；未给截止。');await create.getByLabel('家里已有的材料、App、设备',{exact:true}).fill('已有课本和学习机，具体题目待核对');let createLost=false;await p.route('**/api/goals/action',async route=>{if(route.request().postDataJSON().action==='create'&&!createLost){createLost=true;await route.fetch();await route.abort('failed')}else await route.continue()});await create.getByRole('button',{name:'保存学习目标'}).click();await p.getByText(/结果未确认，请点原按钮重试/).waitFor();assert(await p.locator('[data-goal-child-select="child-2"]').isDisabled());await p.locator('[data-goal-retry]').click();await p.unroute('**/api/goals/action');
  await p.locator('[data-goal-form="feedback"]').waitFor();assert(await p.getByText('记下原话或作答就可以，不需要判断原因。保存后，Agent会结合反馈提出下一步。',{exact:true}).isVisible());await p.getByRole('heading',{name:'虚构英语目标 '+width,exact:true}).waitFor();assert(await p.getByText('确认建议后，这里会显示家长审核过的计划。',{exact:true}).isVisible());await p.locator('#goal-school-requirement summary').click();assert.match(await p.locator('#goal-school-requirement').innerText(),/任选一种说明顺序/);checks++;
  await p.locator('[data-goal-action="evaluate"]').click();await p.locator('[data-goal-form="approve"]').waitFor();await p.getByText('为什么这样安排 · 判断与依据',{exact:true}).click();await p.getByText('本次引用原文',{exact:true}).click();await p.getByRole('link',{name:'本次学校要求',exact:true}).click();assert(await p.locator('#goal-school-requirement').evaluate(e=>e.open));checks++;
  const manual=p.locator('[data-goal-form="manual"]');await manual.locator('xpath=ancestor::details').evaluate(e=>e.open=true);await manual.getByLabel('家长怎么带着做、怎么问孩子').fill('用已有课本的一道题，听孩子说出选择的理由；困了就结束。');await manual.getByLabel('怎样核对独立掌握').fill('下次用相近题观察能否独立解释，不用完成次数代替掌握。');await manual.getByLabel('一次预计分钟').fill('8');await manual.getByRole('button',{name:'确认计划并安排'}).click();
  await p.locator('[data-goal-task]').waitFor();const original=await p.locator('[data-goal-task]').getAttribute('data-goal-task');assert(original);checks++;
  const feedback=p.locator('[data-goal-form="feedback"]');await feedback.getByLabel('孩子怎么答的、用了什么帮助、用时和感受').fill('虚构反馈：练了八分钟，需要少量提示；孩子愿意口头讲。');await feedback.getByLabel('信息来源').selectOption('家长转述孩子');await feedback.getByLabel('获得的帮助').locator('xpath=ancestor::details').evaluate(e=>e.open=true);await feedback.getByLabel('获得的帮助').selectOption('少量提示');await feedback.locator('input[type="file"]').setInputFiles({name:'synthetic-evidence.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQ0AAAAASUVORK5CYII=','base64')});
  // Simulate a lost response after the server has saved the exact request.
  let intercepted=false;await p.route('**/api/goals/action',async route=>{const body=route.request().postDataJSON();if(body.action==='feedback'&&!intercepted){intercepted=true;await route.fetch();if(width===360)await route.abort('failed');else await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'Synthetic failure after save'})})}else await route.continue()});
  await feedback.getByRole('button',{name:'保存反馈'}).click();await p.getByText(/结果未确认，请点原按钮重试/).waitFor();assert(await feedback.getByLabel('孩子怎么答的、用了什么帮助、用时和感受').isDisabled());await feedback.getByRole('button',{name:'保存反馈'}).click();await p.getByText('虚构反馈：练了八分钟，需要少量提示；孩子愿意口头讲。',{exact:true}).waitFor();assert.equal(await p.locator('[id^="goal-record-"] > [data-goal-record]').count(),1);assert.equal(await p.getByRole('link',{name:'查看原件',exact:true}).count(),1);const originalURL=await p.getByRole('link',{name:'查看原件',exact:true}).getAttribute('href');assert.equal((await p.request.get(new URL(originalURL,url).href)).status(),200);checks++;
  const recordTrigger=await p.locator('[id^="goal-record-"] > [data-goal-record]').elementHandle();await recordTrigger.click();await p.locator('#recordDialog[open]').waitFor();assert(await recordTrigger.evaluate(e=>e.isConnected),'opening a source preserves the current goal panel');assert.match(await p.locator('#recordForm [name="note"]').inputValue(),/虚构反馈/);await p.locator('#recordDialog').evaluate(d=>d.close());checks++;
  const manual2=p.locator('[data-goal-form="manual"]');await manual2.locator('xpath=ancestor::details').evaluate(e=>e.open=true);await manual2.getByLabel('家长怎么带着做、怎么问孩子').fill('保留口头解释，缩为五分钟，先问孩子想从哪一道开始。');await manual2.getByRole('button',{name:'确认并更新原计划'}).click();await p.getByText('保留口头解释，缩为五分钟，先问孩子想从哪一道开始。',{exact:true}).first().waitFor();assert.equal(await p.locator('[data-goal-task]').getAttribute('data-goal-task'),original);checks++;
  const beforeDecision=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.task_id===original);const preDecisionTeacher=await p.request.post(url+'api/goals/action',{headers:{'X-Family-Token':(await(await p.request.get(url+'api/state')).json()).token},data:{action:'feedback',id:beforeDecision.id,request_key:'synthetic-predecision-teacher-'+width,day:new Date(Date.now()+8*3600000).toISOString().slice(0,10),source:'老师反馈',note:'虚构旧老师结果：这条先于下一次判断确认，不能冒充确认后的新结果。'}});assert.equal(preDecisionTeacher.status(),200,await preDecisionTeacher.text());
  await p.locator('[data-goal-action="evaluate"]').click();await p.locator('[data-goal-form="approve"]').waitFor();assert(await p.locator('[data-goal-next-step]').isVisible());
  if(process.env.GOALS_UI_PROOF_DIR){await fs.mkdir(process.env.GOALS_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'next-step-'+width+'.png'),fullPage:true})}await p.getByText('调整这份建议 · 可选',{exact:true}).click();await p.locator('[data-goal-form="approve"]').getByLabel('家长怎么带着做、怎么问孩子').fill('旧建议的修改不能混入新建议');await feedback.getByLabel('孩子怎么答的、用了什么帮助、用时和感受').fill('补充一条改变依据的反馈');await feedback.getByRole('button',{name:'保存反馈'}).click();await p.locator('[data-goal-form="approve"]').waitFor({state:'detached'});await p.locator('[data-goal-action="evaluate"]').click();await p.locator('[data-goal-form="approve"]').waitFor();assert.doesNotMatch(await p.locator('[data-goal-form="approve"]').getByLabel('家长怎么带着做、怎么问孩子').inputValue(),/旧建议的修改/);await p.getByText('为什么这样安排 · 判断与依据',{exact:true}).click();assert.match(await p.locator('[data-goal-proposal]').innerText(),/待验证/);await p.locator('[data-goal-form="approve"]').getByRole('button',{name:'确认并更新原计划'}).click();await p.locator('[data-goal-proposal]').getByText('没有新的待审核建议。',{exact:true}).waitFor();assert.equal(await p.locator('[data-goal-task]').getAttribute('data-goal-task'),original);checks++;
  await p.locator('[data-goal-action="pause"]').click();await p.getByText('已暂缓自动分析，反馈仍可保存。').waitFor();const pausedManual=p.locator('[data-goal-form="manual"]');await pausedManual.locator('xpath=ancestor::details').evaluate(e=>e.open=true);await pausedManual.getByLabel('家长怎么带着做、怎么问孩子').fill('暂缓期间只整理下次可能怎么做');await pausedManual.getByRole('button',{name:'确认并更新原计划'}).click();await p.getByText('已暂缓自动分析，反馈仍可保存。').waitFor();await p.locator('[data-goal-action="resume"]').click();await p.locator('[data-goal-action="pause"]').waitFor();checks++;
  await p.locator('[data-word-check] > summary').click();const wordForm=p.locator('[data-goal-form="word"]');await wordForm.getByLabel('本次单词',{exact:true}).fill('pen');await wordForm.getByLabel('本次中文义或语境',{exact:true}).fill('用于写字的笔');
  // Browser speech events are synthetic: no household audio or external speech service.
  await p.evaluate(()=>{const target=new EventTarget();window.__speech={voices:[{name:'Remote English',lang:'en-US',localService:false}],calls:[],fail:false,cancels:0};Object.assign(target,{getVoices:()=>window.__speech.voices,speak:u=>{window.__speech.calls.push({text:u.text,voice:u.voice,rate:u.rate});setTimeout(()=>window.__speech.fail?u.onerror?.({error:'synthetic'}):u.onend?.(),10)},cancel:()=>window.__speech.cancels++});Object.defineProperty(window,'speechSynthesis',{value:target,configurable:true});window.SpeechSynthesisUtterance=class{constructor(text){this.text=text}}});
  await wordForm.getByText('只听声音来核对',{exact:true}).click();await wordForm.getByRole('button',{name:'开始听题',exact:true}).click();await wordForm.getByText(/请沿用材料填写2至6个/).waitFor();assert.equal(await p.locator('[data-word-listen-dialog]').count(),0);
  await wordForm.locator('[name="listen_choices"]').fill('笔\n书\n桌子');await wordForm.getByRole('button',{name:'开始听题',exact:true}).click();const listen=p.locator('[data-word-listen-dialog]');await listen.waitFor();assert(await listen.getByRole('button',{name:'播放声音'}).isDisabled());assert(await listen.getByText(/没有可用的本地声音/).isVisible());assert.doesNotMatch(await listen.innerHTML(),/\bpen\b|用于写字的笔|虚构英语目标/);assert.doesNotMatch(await p.locator('body').ariaSnapshot(),/\bpen\b|用于写字的笔|虚构英语目标/);assert(await listen.locator('button[type="submit"]').isDisabled());assert.equal(await p.evaluate(()=>speechSynthesis.getVoices().length),1);
  await p.evaluate(()=>{window.__speech.voices.push({name:'Local English',lang:'en-GB',localService:true},{name:'本地中文',lang:'zh-CN',localService:true});speechSynthesis.dispatchEvent(new Event('voiceschanged'))});assert.equal(await listen.getByLabel('声音').locator('option').count(),1);assert.equal(await listen.getByLabel('声音').inputValue(),'0');await p.keyboard.press('Escape');assert(await listen.isVisible());
  await p.evaluate(()=>window.__speech.fail=true);await listen.getByRole('button',{name:'播放声音'}).click();await listen.getByText(/播放未完成，请重试/).waitFor();assert(await listen.locator('button[type="submit"]').isDisabled());
  await p.evaluate(()=>window.__speech.fail=false);await listen.getByRole('button',{name:'播放声音'}).click();await listen.getByText(/播放完成，可以作答/).waitFor();await listen.getByLabel('书',{exact:true}).check();if(process.env.GOALS_UI_PROOF_DIR)await listen.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'listen-choice-'+width+'.png')});await listen.getByRole('button',{name:'记下回答',exact:true}).click();assert.equal(await wordForm.locator('[name="note"]').inputValue(),'');await listen.getByRole('button',{name:'家长核对并带回记录'}).click();await listen.waitFor({state:'detached'});assert.equal(await wordForm.locator('[name="word_result_hear_meaning"]').inputValue(),'结果待核对');assert.match(await wordForm.locator('[name="note"]').inputValue(),/实际回答：书/);checks++;
  for(const mode of ['hear_spelling','hear_chinese_spelling']){await wordForm.locator('[name="listen_mode"]').selectOption(mode);await wordForm.getByRole('button',{name:'开始听题',exact:true}).click();await listen.waitFor();assert.doesNotMatch(await listen.innerText(),/pen|用于写字的笔/);const box=listen.getByLabel('写下听到的英文');assert(await box.isDisabled());assert.equal(await box.getAttribute('spellcheck'),'false');await listen.getByRole('button',{name:'播放声音'}).click();await listen.getByText(/播放完成，可以作答/).waitFor();assert.deepEqual(await p.evaluate(()=>({text:__speech.calls.at(-1).text,local:__speech.calls.at(-1).voice.localService})),{text:mode==='hear_spelling'?'pen':'用于写字的笔',local:true});await box.fill(mode==='hear_spelling'?'pan':'pen');if(process.env.GOALS_UI_PROOF_DIR)await listen.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'listen-'+mode+'-'+width+'.png')});await listen.getByRole('button',{name:'记下回答',exact:true}).click();await listen.getByRole('button',{name:'家长核对并带回记录'}).click();await listen.waitFor({state:'detached'});assert.equal(await wordForm.locator('[name="word_result_'+mode+'"]').inputValue(),'结果待核对');checks++}
  assert.match(await wordForm.locator('[name="note"]').inputValue(),/同次页面使用中已经听过本词/);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await wordForm.locator('[name="word_result_hear_spelling"]').selectOption('本次独立答对');await wordForm.getByRole('button',{name:'保存本词核对',exact:true}).click();await p.getByText(/本页已重复听过这个词/).waitFor();await wordForm.locator('[name="word_result_hear_spelling"]').selectOption('答错');checks++;
  await wordForm.getByLabel('本次条件',{exact:true}).selectOption({label:'首次核对'});await wordForm.locator('[name="word_result_hear_meaning"]').selectOption({label:'答错'});await wordForm.locator('[name="word_result_read_meaning"]').selectOption({label:'本次独立答对'});await wordForm.getByLabel('原始作答、选项、用时和感受 · 可选',{exact:true}).fill((await wordForm.locator('[name="note"]').inputValue())+'\n虚构核对：只听选择书，看到词形选择笔。');assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);if(process.env.GOALS_UI_PROOF_DIR)await p.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'word-check-'+width+'.png'),fullPage:true});let wordLost=false;await p.route('**/api/goals/action',async route=>{const body=route.request().postDataJSON();if(body.word_check&&!wordLost){wordLost=true;await route.fetch();await route.abort('failed')}else await route.continue()});await wordForm.getByRole('button',{name:'保存本词核对'}).click();await p.getByText(/结果未确认，请点原按钮重试/).waitFor();assert(await p.locator('[data-goal-child-select="child-2"]').isDisabled());await p.locator('[data-goal-retry]').click();await p.unroute('**/api/goals/action');await p.getByText(/听英文 → 选中文：答错/).waitFor();const wordSnapshot=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.task_id===original);assert.match(wordSnapshot.current_plan_confirmed_at,/^\d{4}-\d{2}-\d{2}T/);assert.equal(wordSnapshot.records.filter(r=>r.note.includes('【单词分项核对')).length,1);assert.match(wordSnapshot.records.at(-1).note,/看中文 → 说英文：未测/);assert.match(wordSnapshot.records.at(-1).note,/实际回答：pan/);assert.match(wordSnapshot.records.at(-1).note,/听中文 → 拼英文：结果待核对/);assert.equal(wordSnapshot.task_id,original);checks++;
  // Browse separate senses and dates, preserving an unfinished new check and current originals.
  const history=p.locator('[data-word-history]');await history.waitFor();
  assert.equal(await history.locator('[data-word-history-select] option').count(),1);
  assert.match(await history.locator('tr').filter({has:p.getByRole('rowheader',{name:'听英文 → 选中文',exact:true})}).innerText(),/答错/);
  const historyAuth=(await(await p.request.get(url+'api/state')).json()).token;
  const priorDay=new Date(Date.now()+8*3600000-86400000).toISOString().slice(0,10);
  const historyCheck={word:'pen',meaning:'用于写字的笔',material:'虚构昨日材料',phase:'刚练过或看过答案',results:{hear_meaning:'提示后答对'}};
  const historyPost=async(check,suffix)=>{const r=await p.request.post(url+'api/goals/action',{headers:{'X-Family-Token':historyAuth},data:{action:'feedback',id:wordSnapshot.id,request_key:'synthetic-word-history-'+width+'-'+suffix,day:priorDay,source:'家长观察',note:'',word_check:check}});assert.equal(r.status(),200,await r.text());return (await r.json()).record_id};
  const oldWordId=await historyPost(historyCheck,'earlier');await historyPost({...historyCheck,meaning:'围栏'},'other-sense');
  const reopenWordHistory=async()=>{await p.reload();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();const choice=p.locator(`[data-goal-select="${wordSnapshot.id}"][aria-pressed]`);if(await choice.count())await choice.click();await p.locator('[data-word-check] > summary').click();await history.waitFor()};
  await reopenWordHistory();
  const sense=history.getByRole('combobox',{name:'查看已核对的词',exact:true});assert.equal(await sense.locator('option').count(),2);
  const draftWord=p.locator('[data-goal-form="word"] [name="word"]');await draftWord.fill('pencil');
  await sense.selectOption(JSON.stringify(['pen','用于写字的笔']));assert.equal(await history.locator('thead [data-goal-record]').count(),2);
  assert.match(await history.locator('tr').filter({has:p.getByRole('rowheader',{name:'听英文 → 选中文',exact:true})}).innerText(),/答错[\s\S]*提示后答对/);
  await sense.selectOption(JSON.stringify(['pen','围栏']));assert.equal(await history.locator('thead [data-goal-record]').count(),1);assert.equal(await draftWord.inputValue(),'pencil');
  await sense.selectOption(JSON.stringify(['pen','用于写字的笔']));assert.equal(await draftWord.inputValue(),'pencil');checks++;
  await history.locator(`[data-goal-record="${oldWordId}"]`).click();await p.locator('#recordDialog[open]').waitFor();
  const corrected=p.locator('#recordForm [name="note"]');assert.match(await corrected.inputValue(),/虚构昨日材料/);
  await corrected.fill((await corrected.inputValue()).replace('听英文 → 选中文：提示后答对','听英文 → 选中文：答错'));
  let correctionFailed=false;await p.route('**/api/record',async route=>{if(!correctionFailed){correctionFailed=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Synthetic word correction failure'})})}else await route.continue()});
  await p.locator('#recordForm').getByRole('button',{name:'保存记录',exact:true}).click();await p.locator('#recordError').getByText('Synthetic word correction failure',{exact:true}).waitFor();assert.match(await corrected.inputValue(),/听英文 → 选中文：答错/);
  await p.locator('#recordForm').getByRole('button',{name:'保存记录',exact:true}).click();await p.locator('#recordDialog').waitFor({state:'hidden'});await p.unroute('**/api/record');await p.getByText('已保存到家庭记录',{exact:true}).waitFor();
  await history.locator('tr').filter({has:p.getByRole('rowheader',{name:'听英文 → 选中文',exact:true})}).getByRole('cell',{name:'答错',exact:true}).nth(1).waitFor();
  assert.equal(await draftWord.inputValue(),'pencil','source correction preserves pending word input');
  await draftWord.fill('');await reopenWordHistory();await sense.selectOption(JSON.stringify(['pen','用于写字的笔']));
  const persistedWords=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===wordSnapshot.id);assert.equal(persistedWords.word_history.checks.find(c=>c.id===oldWordId).results.hear_meaning,'答错');assert.equal(persistedWords.current_plan.action,wordSnapshot.current_plan.action);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'word history scroll is contained');
  assert.equal(await history.locator('button,select').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'history controls remain touchable');
  assert.equal(await history.locator('tbody tr').first().locator('th').evaluate(e=>{e.before(document.createTextNode('\n'));return getComputedStyle(e).position}),'sticky','whitespace does not change element first-child matching');
  const historyScroll=history.locator('.word-history-scroll');await historyScroll.evaluate(e=>e.scrollLeft=e.scrollWidth);assert.ok(await history.locator(`[data-goal-record="${oldWordId}"]`).evaluate(e=>e.getBoundingClientRect().right<=innerWidth),'older attempt reachable within viewport');await historyScroll.evaluate(e=>e.scrollLeft=0);
  await history.scrollIntoViewIfNeeded();if(process.env.GOALS_UI_PROOF_DIR)await history.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'word-history-'+width+'.png')});checks++;
  // Per-direction status follows the stated rule; a word checked 9 days ago with one independent answer becomes an interval-retest candidate the parent can pick, never a scheduled task.
  assert.match(await history.locator('[data-word-status]').innerText(),/听英文 → 选中文.*最近答错/,'latest result per direction is shown, not a mastery rate');
  const progressTrend=history.locator('[data-word-status] [data-progress-trend]').first();assert.ok(await progressTrend.count()>=1,'a per-direction progress trajectory tag renders');assert.match(await progressTrend.innerText(),/进展：(改善|持平|退步)/,'progress shows an observed first-to-latest change, not a rate');assert.match(await history.locator('[data-word-status]').innerText(),/首末对照/,'progress is labelled as first-to-latest, not a trend judgment');checks++;
  assert.equal(await history.locator('[data-word-retest-list]').count(),0,'wrong or recent answers are not retest candidates');
  const nineDaysAgo=new Date(Date.now()+8*3600000-9*86400000).toISOString().slice(0,10);
  const bookPost=await p.request.post(url+'api/goals/action',{headers:{'X-Family-Token':historyAuth},data:{action:'feedback',id:wordSnapshot.id,request_key:'synthetic-word-retest-'+width,day:nineDaysAgo,source:'家长观察',note:'',word_check:{word:'book',meaning:'书',material:'虚构词表',phase:'首次核对',results:{read_meaning:'本次独立答对'}}}});assert.equal(bookPost.status(),200,await bookPost.text());
  await reopenWordHistory();await draftWord.fill('pencil');
  const candidate=history.locator('[data-word-retest-list] button');assert.equal(await candidate.count(),1);assert.match(await candidate.innerText(),/book · 书 · 看英文 → 选中文 · /);
  assert.equal(await draftWord.inputValue(),'pencil','listing candidates does not touch the unsaved check');
  const tasksBefore=(await(await p.request.get(url+'api/state')).json()).tasks.length;
  const retestForm=p.locator('[data-goal-form="word"]');
  if(!await retestForm.locator('details').evaluate(d=>d.open))await retestForm.getByText('只听声音来核对',{exact:true}).click();
  await retestForm.locator('[name="meaning"]').fill('旧词义');await retestForm.locator('[name="note"]').fill('旧词回答');await retestForm.locator('[name="listen_choices"]').fill('旧选项甲\n旧选项乙');
  await retestForm.locator('[name="word_result_read_meaning"]').selectOption('本次独立答对');
  p.once('dialog',d=>d.dismiss());await candidate.click();assert.equal(await draftWord.inputValue(),'pencil');assert.equal(await retestForm.locator('[name="note"]').inputValue(),'旧词回答');
  p.once('dialog',d=>d.accept());await candidate.click();
  assert.equal(await draftWord.inputValue(),'book');assert.equal(await p.locator('[data-goal-form="word"] [name="meaning"]').inputValue(),'书');assert.equal(await p.locator('[data-goal-form="word"] [name="phase"]').inputValue(),'间隔后复测');
  assert.deepEqual(await retestForm.locator('select[name^="word_result_"]').evaluateAll(xs=>[...new Set(xs.map(x=>x.value))]),['未测']);
  for(const name of ['note','material','listen_choices'])assert.equal(await retestForm.locator(`[name="${name}"]`).inputValue(),'','old word evidence is not carried into the retest');
  assert.match(await history.locator('[data-word-status]').innerText(),/看英文 → 选中文.*一次独立答对.*可以间隔复测/);
  assert.equal((await(await p.request.get(url+'api/state')).json()).tasks.length,tasksBefore,'no task or plan is created by picking a candidate');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'candidate list fits the viewport');
  assert.equal(await history.locator('button,select').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'candidate buttons remain touchable');
  if(process.env.GOALS_UI_PROOF_DIR)await history.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'word-retest-'+width+'.png')});
  await draftWord.fill('');checks++;
  // Read-only child profile: aggregates the child's reached-independence directions (and any judgments) with links to the original record.
  const profSeed=(day,check,suf)=>p.request.post(url+'api/goals/action',{headers:{'X-Family-Token':historyAuth},data:{action:'feedback',id:wordSnapshot.id,request_key:'synthetic-profile-'+width+'-'+suf,day,source:'家长观察',note:'',word_check:check}});
  const pDay=n=>new Date(Date.now()+8*3600000-n*86400000).toISOString().slice(0,10);
  assert.equal((await profSeed(pDay(16),{word:'torch',meaning:'手电',material:'虚构',phase:'首次核对',results:{meaning_spelling:'答错'}},'s0')).status(),200);
  assert.equal((await profSeed(pDay(1),{word:'torch',meaning:'手电',material:'虚构',phase:'间隔后复测',results:{meaning_spelling:'本次独立答对'}},'s1')).status(),200);
  await reopenWordHistory();
  const profile=p.locator('[data-child-profile]');assert.equal(await profile.count(),1,'child profile renders for a child with a goal');
  await profile.locator('summary').click();assert.match(await profile.innerText(),/我们目前怎么理解TA/);
  assert.match(await profile.locator('[data-profile-reached]').innerText(),/torch · 手电[\s\S]*已达间隔独立/,'reached-independence direction is summarised in the profile');
  assert.equal(await profile.locator('[data-profile-recheck]').count(),0,'an older unreviewed teacher result is not labelled as post-judgment');
  // Record layers keep source labels; approved plans are not evidence of execution.
  // A teacher evaluation recorded after the judgment closes the loop: it is flagged for judgment recheck.
  const teacherEval=await p.request.post(url+'api/goals/action',{headers:{'X-Family-Token':historyAuth},data:{action:'feedback',id:wordSnapshot.id,request_key:'synthetic-teachereval-'+width,day:pDay(0),source:'老师反馈',note:'老师说这次单元测验拼写扣分偏多，建议多练 ea/ee。'}});assert.equal(teacherEval.status(),200,await teacherEval.text());
  await reopenWordHistory();await profile.locator('summary').click();
  assert.match(await profile.locator('[data-profile-recheck]').innerText(),/老师说这次单元测验拼写扣分偏多[\s\S]*老师反馈/,'a post-judgment teacher result is flagged for recheck');
  assert.match(await profile.locator('[data-profile-reports]').innerText(),/虚构反馈/,'parent-report records are layered in the profile');
  assert.ok(await profile.locator('[data-profile-methods]').count()>=1,'the approved plan is listed');
  assert.match(await profile.innerText(),/已确认的计划/);assert.doesNotMatch(await profile.innerText(),/试过的方法|事实与外部证据/);
  // A goal confirmed more than once shows how our judgment changed across confirmations (R26 memory).
  assert.ok(await profile.locator('[data-profile-evolution]').count()>=1,'a re-confirmed goal shows its judgment evolution');
  assert.match(await profile.locator('[data-profile-evolution]').first().innerText(),/判断的演化[\s\S]*现判断|现判断/,'the evolution view marks the current judgment against prior ones');
  const rowFix=profile.locator('[data-profile-reports] [data-goal-record]').first();assert.match(await rowFix.innerText(),/更正/);
  await rowFix.click();await p.locator('#recordDialog[open]').waitFor();assert.match(await p.locator('#recordForm [name="note"]').inputValue(),/虚构反馈/,'correcting from the profile opens the editable original record');await p.locator('#recordDialog').evaluate(d=>d.close());
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'child profile fits the viewport');
  if(process.env.GOALS_UI_PROOF_DIR)await profile.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'child-profile-'+width+'.png')});checks++;
  // Equal word/direction across goals must not silently discard another goal's contrary evidence.
  let profileRequest=0;const profilePost=async value=>{const r=await p.request.post(url+'api/goals/action',{headers:{'X-Family-Token':historyAuth},data:{request_key:'synthetic-profile-extra-'+width+'-'+(++profileRequest),...value}});assert.equal(r.status(),200,await r.text());return r.json()};
  const secondProfile=(await profilePost({action:'create',child_id:wordSnapshot.child_id,title:'虚构画像范围 '+width,subject:'英语',baseline:'另一材料下的表现，独立核对。'})).id;
  for(const [ago,result] of [[16,'本次独立答对'],[1,'答错']])await profilePost({action:'feedback',id:secondProfile,day:pDay(ago),source:'家长观察',note:'',word_check:{word:'torch',meaning:'手电',material:'另一份虚构材料',phase:'首次核对',results:{meaning_spelling:result}}});
  await profilePost({action:'evaluate',id:secondProfile});
  let pg=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===secondProfile);assert.ok(pg.pending);await profilePost({action:'approve',id:pg.id,expected_version:pg.version,context_hash:pg.context_hash,proposal_id:pg.pending.id});
  const childProfileBefore=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===secondProfile);const originalProfileRecord=childProfileBefore.hypotheses_detail[0].support.find(ref=>ref.startsWith('record:'));assert.ok(originalProfileRecord,'fixture has an actual cited record');
  await profilePost({action:'feedback',id:secondProfile,day:pDay(0),source:'家长观察',note:'虚构新增反馈：需要重新核对旧判断。'});
  await reopenWordHistory();if(!(await profile.evaluate(d=>d.open)))await profile.locator('summary').click();
  assert.match(await profile.locator('[data-profile-reached]').innerText(),/torch · 手电/);assert.match(await profile.locator('[data-profile-attention]').innerText(),/torch · 手电[\s\S]*退步/,'same word retains both goal scopes');
  const profileJudgment=profile.locator('[data-profile-judgment]').filter({hasText:'虚构画像范围 '+width});assert.match(await profileJudgment.innerText(),/依据已变化，旧判断待重新评估/);assert.match(await profile.innerText(),/首末对照不代表连续趋势/);checks++;
  const profileOriginalID=originalProfileRecord.slice(7);await profileJudgment.locator('[data-goal-record="'+profileOriginalID+'"]').click();await p.locator('#recordDialog[open]').waitFor();
  assert.equal(await p.locator('#recordForm [name="id"]').inputValue(),profileOriginalID);assert.match(await p.locator('#recordForm [name="note"]').inputValue(),/单词：torch/);
  const canonicalNote=await p.locator('#recordForm [name="note"]').inputValue();await p.locator('#recordForm [name="note"]').fill(canonicalNote.replace('看中文 → 拼英文：答错','看中文 → 拼英文：提示后答对'));
  let profileRecordLost=false;await p.route('**/api/record',async route=>{if(!profileRecordLost){profileRecordLost=true;await route.fetch();await route.fulfill({status:503,json:{error:'虚构画像原记录回执丢失'}})}else await route.continue()});
  await p.locator('#recordForm [type="submit"]').click();await p.locator('#recordError').getByText('虚构画像原记录回执丢失',{exact:true}).waitFor();assert.match(await p.locator('#recordForm [name="note"]').inputValue(),/看中文 → 拼英文：提示后答对/);
  await p.locator('#recordForm [type="submit"]').click();await p.locator('#recordDialog').waitFor({state:'hidden'});await p.unroute('**/api/record');
  await reopenWordHistory();if(!(await profile.evaluate(d=>d.open)))await profile.locator('summary').click();
  const correctedProfile=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===secondProfile);assert.equal(correctedProfile.records.filter(r=>r.id===Number(profileOriginalID)).length,1);assert.equal(correctedProfile.word_history.words.find(w=>w.word==='torch').directions.meaning_spelling.status,'提示后答对');assert.deepEqual(correctedProfile.current_plan,childProfileBefore.current_plan);checks++;
  const scopedLine=profile.locator('[data-profile-attention] li').filter({hasText:'虚构画像范围 '+width});assert.match(await scopedLine.innerText(),/提示后答对/);
  await scopedLine.locator('[data-goal-select="'+secondProfile+'"]').click();await p.getByRole('heading',{name:'虚构画像范围 '+width,exact:true}).waitFor();
  await p.locator('[data-goal-child-select="child-2"]').click();assert.doesNotMatch(await p.locator('#goalsRoot').innerText(),/虚构画像范围/,'sibling profile does not leak evidence');
  await p.locator('[data-goal-child-select="'+wordSnapshot.child_id+'"]').click();await p.locator('[data-goal-select="'+wordSnapshot.id+'"][aria-pressed]').click();if(!(await history.isVisible()))await p.locator('[data-word-check] > summary').click();await history.waitFor();
  if(!(await profile.evaluate(d=>d.open)))await profile.locator('summary').click();assert.match(await profile.locator('[data-profile-attention]').innerText(),/虚构画像范围/);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);if(process.env.GOALS_UI_PROOF_DIR)await profile.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'child-profile-reviewed-'+width+'.png')});checks++;
  const edit=p.locator('[data-goal-form="edit"]');await edit.getByLabel('目前实际表现').evaluate(e=>{for(let p=e.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true});await edit.getByLabel('目前实际表现').fill('家长保留的修改内容');
  const live=await(await p.request.get(url+'api/goals')).json(),target=live.goals.find(g=>g.task_id===original),auth=await(await p.request.get(url+'api/state')).json();const other=await p.request.post(url+'api/goals/action',{headers:{'X-Family-Token':auth.token},data:{action:'edit',id:target.id,expected_version:target.version,request_key:'synthetic-other-parent-'+width,curriculum:'另一位家长刚核对的教材'}});assert.equal(other.status(),200);
  await edit.getByRole('button',{name:'保存背景更正'}).click();await edit.locator('[data-goal-rebase]').waitFor();assert.equal(await edit.getByLabel('目前实际表现').inputValue(),'家长保留的修改内容');await edit.locator('[data-goal-rebase]').click();assert.equal(await edit.getByLabel('年级与教材版本').inputValue(),'另一位家长刚核对的教材');await edit.getByRole('button',{name:'保存背景更正'}).click();await edit.locator('[data-goal-rebase]').waitFor({state:'detached'});checks++;
  // Existing task feedback must reach this goal without re-entering it as a separate record.
  await p.locator('nav [data-page="home"]').click();await p.locator('[data-task-all="todo"]').click();
  await p.locator(`[data-query-target="task:${original}"] [data-task]`).click();
  const taskForm=p.locator('#taskForm'),taskNote='虚构作业反馈：孩子说困了，今天先停；看过讲解才说出第一点。';
  await taskForm.locator('[name="status"]').selectOption('进行中');await taskForm.locator('[name="note"]').fill(taskNote);
  let taskFailed=false;await p.route('**/api/task',async route=>{if(!taskFailed){taskFailed=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Synthetic task save failure'})})}else await route.continue()});
  await taskForm.getByRole('button',{name:'保存状态'}).click();await p.locator('#taskError').getByText('Synthetic task save failure',{exact:true}).waitFor();assert.equal(await taskForm.locator('[name="note"]').inputValue(),taskNote);
  const [taskReply]=await Promise.all([p.waitForResponse(r=>r.url().endsWith('/api/task')),taskForm.getByRole('button',{name:'保存状态'}).click()]);assert.equal(taskReply.status(),200,await taskReply.text());await p.locator('#taskDialog').waitFor({state:'hidden'});await p.unroute('**/api/task');
  await p.reload();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();
  await p.locator(`[data-goal-task="${original}"]`).first().waitFor();await p.locator('[data-goal-task-feedback] .source').getByText(taskNote,{exact:true}).waitFor();
  const savedGoal=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.task_id===original);assert.equal(savedGoal.task_feedback.length,1);assert.match(savedGoal.records.find(r=>r.id===wordSnapshot.word_history.checks[0].id).note,/实际回答：pan/);assert.equal(savedGoal.records.some(r=>r.note===taskNote),false);
  await p.locator('[data-goal-action="evaluate"]').click();await p.locator('[data-goal-form="approve"]').waitFor();await p.getByText('为什么这样安排 · 判断与依据',{exact:true}).click();await p.getByText('本次引用原文',{exact:true}).click();
  await p.getByRole('link',{name:'作业反馈',exact:true}).first().click();assert.equal(await p.locator('[data-goal-task-feedback] .source').innerText(),taskNote);
  assert.equal((await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.task_id===original).current_plan.action,savedGoal.current_plan.action);
  if(process.env.GOALS_UI_PROOF_DIR)await p.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'task-feedback-'+width+'.png'),fullPage:true});checks++;
  // The approved task feedback remains a real citation after newer notes exceed the model window.
  await p.locator('[data-goal-form="approve"]').getByRole('button',{name:'确认并更新原计划'}).click();await p.locator('[data-goal-reviewed-evidence]').waitFor({state:'attached'});
  const confirmedMemoryPlan=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===savedGoal.id).current_plan;const memoryAuth=await(await p.request.get(url+'api/state')).json();
  for(let i=0;i<30;i++){const r=await p.request.post(url+'api/task',{headers:{'X-Family-Token':memoryAuth.token},data:{id:original,status:'进行中',note:'后续日常反馈 '+i}});assert.equal(r.status(),200)}
  await p.reload();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();const memorySelect=p.locator(`[data-goal-select="${savedGoal.id}"][aria-pressed]`);if(await memorySelect.count())await memorySelect.click();
  const reviewed=p.locator('[data-goal-reviewed-evidence]');await reviewed.locator('summary').click();assert.match(await reviewed.innerText(),/以下是当时的引用/);assert.ok((await reviewed.locator('blockquote').innerText()).startsWith('虚构作业反馈'));
  await reviewed.getByRole('link',{name:'作业反馈',exact:true}).click();const retained=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===savedGoal.id);assert.equal(retained.task_feedback.length,24);assert.ok(retained.task_feedback.some(h=>h.text===taskNote));assert.deepEqual(retained.current_plan,confirmedMemoryPlan);
  assert.equal(await reviewed.locator('summary,a').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false,'reviewed evidence controls remain touchable');
  await reviewed.scrollIntoViewIfNeeded();if(process.env.GOALS_UI_PROOF_DIR)await p.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'reviewed-memory-'+width+'.png'),fullPage:false});checks++;
  // A parent records a requirement once; the existing goal reads it and tracks correction/withdrawal.
  await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="teachers"]').click();
  await p.locator('[data-teacher-select="new"]').click();await p.locator('[data-teacher-form="profile"]').waitFor();
  const teacherProfile=p.locator('[data-teacher-form="profile"]');
  await teacherProfile.getByLabel('老师称呼').fill('虚构英语教师 '+width);await teacherProfile.getByLabel('科目',{exact:true}).fill('英语');
  await teacherProfile.locator('[name="child_ids"][value="child-1"]').check();
  let releaseTeacherRefresh,teacherRefreshSeen,teacherRefreshDone;const refreshGate=new Promise(r=>releaseTeacherRefresh=r),refreshStarted=new Promise(r=>teacherRefreshSeen=r),refreshFinished=new Promise(r=>teacherRefreshDone=r);
  await p.route('**/api/teachers',async route=>{teacherRefreshSeen();await refreshGate;await route.continue();teacherRefreshDone()});
  await teacherProfile.getByRole('button',{name:'保存档案',exact:true}).click();await refreshStarted;
  try{assert(await p.locator('[data-teacher-form="observation"] [name="behavior"]').isDisabled(),'save must remain locked until its own refresh finishes')}finally{releaseTeacherRefresh()}
  await refreshFinished;await p.unroute('**/api/teachers');
  const teacherForm=p.locator('[data-teacher-form="observation"]');await teacherForm.waitFor();
  const requirement='从课本任选两句，说出时间线索。<img src=x onerror="window.teacherInjected=true">';
  await teacherForm.getByLabel('原话或观察到的具体行为').fill(requirement);await teacherForm.getByRole('button',{name:'保存记录',exact:true}).click();
  await p.locator('.teacher-behavior').getByText(requirement,{exact:true}).waitFor().catch(async e=>{console.error('teacher save diagnostic',await p.locator('#teachersStatus').innerText(),await p.locator('.teacher-records').innerText());throw e});
  const teacherState=await(await p.request.get(url+'api/teachers')).json(),teacherSaved=teacherState.teachers.find(t=>t.display_name==='虚构英语教师 '+width),teacherObservation=teacherState.observations.find(o=>o.teacher_id===teacherSaved.id);
  const reopenTeacherGoal=async()=>{await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();const b=p.locator(`[data-goal-select="${savedGoal.id}"][aria-pressed]`);if(await b.count())await b.click();await p.locator('#goal-school-requirement summary').click()};
  await reopenTeacherGoal();const teacherCard=p.locator('[data-goal-teacher-requirement]');await teacherCard.getByText(requirement,{exact:true}).waitFor();
  assert.equal(await p.evaluate(()=>window.teacherInjected),undefined);assert.equal(await teacherCard.locator('img').count(),0);
  await p.locator('[data-goal-action="evaluate"]').click();await p.locator('[data-goal-form="approve"]').waitFor();
  await p.getByText('为什么这样安排 · 判断与依据',{exact:true}).click();await p.getByText('本次引用原文',{exact:true}).click();await p.getByRole('link',{name:'本次学校要求',exact:true}).first().click();
  assert(await p.locator('#goal-school-requirement').evaluate(e=>e.open));assert.equal(await teacherCard.locator('button').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false);
  if(process.env.GOALS_UI_PROOF_DIR)await teacherCard.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'teacher-requirement-'+width+'.png')});
  await teacherCard.getByRole('button',{name:'查看 / 更正老师记录',exact:true}).click();await p.locator(`[data-teacher-edit="${teacherObservation.id}"]`).click();
  await teacherForm.getByLabel('原话或观察到的具体行为').fill('更正：只选一句，不用抄写。');
  let teacherFailed=false;await p.route('**/api/teachers/observation',async route=>{if(!teacherFailed){teacherFailed=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Synthetic teacher save failure'})})}else await route.continue()});
  await teacherForm.getByRole('button',{name:'保存更正',exact:true}).click();await p.getByText(/Synthetic teacher save failure/).waitFor();assert.equal(await teacherForm.getByLabel('原话或观察到的具体行为').inputValue(),'更正：只选一句，不用抄写。');
  await p.locator('[data-teacher-retry]').click();await p.locator('.teacher-behavior').getByText('更正：只选一句，不用抄写。',{exact:true}).waitFor();await p.unroute('**/api/teachers/observation');
  await p.reload();await reopenTeacherGoal();await teacherCard.getByText('更正：只选一句，不用抄写。',{exact:true}).waitFor();
  const correctedTeacherGoal=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===savedGoal.id);assert(correctedTeacherGoal.pending_stale);assert.deepEqual(correctedTeacherGoal.current_plan,confirmedMemoryPlan);
  await teacherCard.getByRole('button',{name:'查看 / 更正老师记录',exact:true}).click();await p.locator(`[data-teacher-edit="${teacherObservation.id}"]`).click();await teacherForm.locator('[name="status"]').selectOption('withdrawn');await teacherForm.getByRole('button',{name:'保存更正',exact:true}).click();await p.locator('.teacher-withdrawn').getByText('更正：只选一句，不用抄写。',{exact:true}).waitFor();
  await reopenTeacherGoal();assert.equal(await teacherCard.count(),0);assert.equal((await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===savedGoal.id).teacher_requirements.length,0);checks++;
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');assert.deepEqual(errors,[]);
  await p.locator('[data-goal-child-select="child-2"]').click();const autoGoal=(await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.school_messages?.length);assert(autoGoal);const autoSelect=p.locator(`[data-goal-select="${autoGoal.id}"][aria-pressed]`);if(await autoSelect.count())await autoSelect.click();await p.getByRole('heading',{name:autoGoal.title,exact:true}).waitFor();await p.locator('#goal-school-requirement summary').click();assert(await p.getByText('Agent从群消息自动关联 · 适用性待核对',{exact:true}).isVisible());assert.match(await p.locator('#goal-school-requirement').innerText(),/任选一种顺序介绍文具/);await p.getByRole('button',{name:'查看原消息与原件',exact:true}).click();await p.locator('#schoolOriginalDialog[open] blockquote').waitFor();assert.match(await p.locator('#schoolOriginalDialog').innerText(),/虚构发布者/);
  // Archive the saved original without retyping a message ID; retry and reopen keep one record.
  const teacherAuth=await(await p.request.get(url+'api/state')).json(),taskCountBefore=teacherAuth.tasks.length,recordCountBefore=teacherAuth.records.length;
  const profileReply=await p.request.post(url+'api/teachers/profile',{headers:{'X-Family-Token':teacherAuth.token},data:{request_key:'synthetic-message-teacher-'+width,display_name:'虚构通知教师 '+width,subject:'语文',child_ids:['child-2'],source_ids:['synthetic-ui-class']}});assert.equal(profileReply.status(),200);const messageTeacher=(await profileReply.json()).teacher;
  const originalDialog=p.locator('#schoolOriginalDialog');await originalDialog.locator('[data-school-teacher-open]').click();
  const messageForm=originalDialog.locator('[data-school-teacher-form]');await messageForm.waitFor();
  assert.equal(await messageForm.locator('[name="teacher_id"]').inputValue(),'');assert.equal(await messageForm.locator('[name="target"]').inputValue(),'');
  assert.equal(await messageForm.locator(`[name="teacher_id"] option[value="${teacherSaved.id}"]`).count(),0,'another child teacher is not offered');
  assert.equal(await messageForm.locator('[name="quote"]').inputValue(),autoGoal.school_messages[0].text);
  await messageForm.locator('[name="teacher_id"]').selectOption(messageTeacher.id);await messageForm.locator('[name="target"]').selectOption('class');
  assert.equal(await originalDialog.evaluate(d=>d.scrollWidth>d.clientWidth),false);assert.equal(await messageForm.locator('button,input,select').evaluateAll(xs=>xs.some(x=>x.getBoundingClientRect().height<44)),false);if(process.env.GOALS_UI_PROOF_DIR)await p.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'message-teacher-form-'+width+'.png'),fullPage:false});
  let lostTeacherReply=true;const teacherRequests=[];
  await p.route('**/api/teachers/message',async route=>{teacherRequests.push(route.request().postDataJSON());if(lostTeacherReply){lostTeacherReply=false;const r=await route.fetch();assert.equal(r.status(),200);await route.abort('connectionreset')}else await route.continue()});
  await messageForm.locator('[type="submit"]').click();await originalDialog.locator('[data-school-teacher-retry]:not([disabled])').waitFor();assert.equal(await messageForm.locator('[name="quote"]').inputValue(),autoGoal.school_messages[0].text);
  await originalDialog.locator('[data-school-original-close]').click();await p.getByRole('button',{name:'查看原消息与原件',exact:true}).click();await messageForm.waitFor();assert.equal(await messageForm.locator('[name="teacher_id"]').inputValue(),messageTeacher.id);assert.equal(await messageForm.locator('[name="quote"]').inputValue(),autoGoal.school_messages[0].text);
  await originalDialog.locator('[data-school-teacher-retry]').click();await originalDialog.locator('[data-school-teacher-saved]').waitFor();assert.deepEqual(teacherRequests[0],teacherRequests[1]);await p.unroute('**/api/teachers/message');
  const archivedTeacher=await(await p.request.get(url+'api/teachers')).json(),messageObservations=archivedTeacher.observations.filter(o=>o.teacher_id===messageTeacher.id);assert.equal(messageObservations.length,1);const messageObservation=messageObservations[0];assert.equal(messageObservation.message_id,'1');assert.equal(messageObservation.scope_child_id,'child-2');
  assert.equal((await(await p.request.get(url+'api/state')).json()).tasks.length,taskCountBefore);assert.equal((await(await p.request.get(url+'api/state')).json()).records.length,recordCountBefore);
  assert.equal(await originalDialog.evaluate(d=>d.scrollWidth>d.clientWidth),false);if(process.env.GOALS_UI_PROOF_DIR)await p.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'message-teacher-saved-'+width+'.png'),fullPage:false});
  await originalDialog.locator('[data-school-teacher-profile]').click();await p.locator(`[data-teacher-observation="${messageObservation.id}"]`).waitFor();
  assert.equal(await p.locator(`[data-teacher-select="${messageTeacher.id}"]`).getAttribute('aria-pressed'),'true');
  await p.reload();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();await p.locator('[data-goal-child-select="child-2"]').click();const sourceGoalSelect=p.locator(`[data-goal-select="${autoGoal.id}"][aria-pressed]`);if(await sourceGoalSelect.count())await sourceGoalSelect.click();await p.locator('#goal-school-requirement summary').click();
  assert.ok((await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===autoGoal.id).teacher_requirements.some(o=>o.teacher_id===messageTeacher.id&&o.message_id==='1'));
  await p.getByRole('button',{name:'查看原消息与原件',exact:true}).click();await originalDialog.locator('[data-school-teacher-open]').click();await messageForm.waitFor();await messageForm.locator('[name="teacher_id"]').selectOption(messageTeacher.id);await messageForm.locator('[name="target"]').selectOption('class');await messageForm.locator('[type="submit"]').click();await originalDialog.getByText('这条消息已有记录，保留现有更正与撤回状态。',{exact:true}).waitFor();assert.equal((await(await p.request.get(url+'api/teachers')).json()).observations.filter(o=>o.teacher_id===messageTeacher.id).length,1);
  await p.locator('[data-school-original-close]').click();checks++;

  const schoolItem=autoGoal.school_messages[0].item_id;await p.locator('nav [data-page="more"]').click();await p.locator('[data-page="agent"]').click();for(const attr of ['data-agent-accept','data-school-record-agent','data-agent-dismiss'])assert(await p.locator(`[${attr}="${schoolItem}"]`).isVisible());await p.locator(`[data-agent-accept="${schoolItem}"]`).click();await p.locator('#agentDialog[open]').waitFor();await p.locator('[data-close="agentDialog"]').click();
  if(width===360){
   await p.locator(`[data-school-record-agent="${schoolItem}"]`).click();await p.locator('#recordDialog[open]').waitFor();
   await p.locator('#recordForm [name="category"]').selectOption('课程进度');await p.locator('#recordForm [name="subject"]').fill('语文');
   await p.locator('#recordForm [name="day"]').fill('2026-09-01');await p.locator('#recordForm [name="title"]').fill('虚构学校通知转课程进度');
   assert(await p.locator('#recordForm [name="source"]').isDisabled());await p.locator('#recordForm [type="submit"]').click();await p.locator('#recordDialog').waitFor({state:'hidden'});await p.locator('body[data-page="learning"]').waitFor();
   const saved=(await(await p.request.get(url+'api/state')).json()).records.filter(r=>r.title==='虚构学校通知转课程进度');assert.equal(saved.length,1);assert.equal(saved[0].category,'课程进度');assert.match(saved[0].source,/^message:/);
   await p.locator('nav [data-page="more"]').click();await p.locator('[data-page="agent"]').click();await p.locator(`[data-school-record-agent="${schoolItem}"]`).click();await p.locator('body[data-page="learning"]').waitFor();assert.equal(await p.locator('#recordDialog[open]').count(),0);
   assert.equal((await(await p.request.get(url+'api/state')).json()).records.filter(r=>r.source===saved[0].source).length,1);
   await p.locator('nav [data-page="more"]').click();await p.locator('[data-page="agent"]').click();checks++;
  }
  await p.locator(`[data-goal-id="${autoGoal.id}"]`).first().click();await p.getByRole('heading',{name:autoGoal.title,exact:true}).waitFor();checks++;
  if(process.env.GOALS_UI_PROOF_DIR){await fs.mkdir(process.env.GOALS_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'goals-'+width+'.png'),fullPage:true})}
  await p.locator('[data-goal-child-select="child-2"]').click();assert.equal(await p.locator('[data-goal-task]').count(),0);checks++;
  // Records alone must show a correctable profile, without an approved judgment or plan.
  for(let i=0;i<7;i++)await profilePost({action:'feedback',id:autoGoal.id,day:pDay(i),source:i===0?'老师反馈':'家长观察',note:'虚构分层记录 '+width+' '+i});
  await p.reload();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();await p.locator('[data-goal-child-select="child-2"]').click();
  const layerProfile=p.locator('[data-child-profile]');await layerProfile.waitFor();await layerProfile.locator('summary').click();
  assert.equal(await layerProfile.locator('[data-profile-judgment],[data-profile-methods]').count(),0);
  assert.match(await layerProfile.innerText(),/来源与成绩仍需核对/);assert.doesNotMatch(await layerProfile.innerText(),/事实与外部证据|试过的方法/);
  const layerRow=layerProfile.locator('[data-profile-facts] li').filter({hasText:'虚构分层记录 '+width+' 0'});await layerRow.waitFor();assert.match(await layerRow.innerText(),/老师反馈/);
  const layerRecord=await layerRow.locator('[data-goal-record]').getAttribute('data-goal-record');
  await layerRow.locator('[data-goal-record]').click();await p.locator('#recordDialog[open]').waitFor();
  await p.locator('#recordForm [name="note"]').fill('虚构更正：尚未核对原件 '+width);await p.locator('#recordForm [name="category"]').selectOption('成绩');await p.locator('#recordForm [name="subject"]').fill('数学');await p.locator('#recordForm [name="score"]').fill('7');await p.locator('#recordForm [name="total"]').fill('10');await p.locator('#recordForm [name="source"]').selectOption('家长观察');
  let layerLost=true;const layerWrites=[];await p.route('**/api/record',async route=>{layerWrites.push(route.request().postDataJSON());if(layerLost){layerLost=false;assert.equal((await route.fetch()).status(),200);await route.abort('connectionreset')}else await route.continue()});
  await p.locator('#recordForm [type="submit"]').click();await p.locator('#recordForm [type="submit"]:not([disabled])').waitFor();assert(await p.locator('#recordDialog[open]').isVisible());assert.equal(await p.locator('#recordForm [name="note"]').inputValue(),'虚构更正：尚未核对原件 '+width);
  await p.locator('#recordForm [type="submit"]').click();await p.locator('#recordDialog').waitFor({state:'hidden'});await p.unroute('**/api/record');assert.equal(layerWrites.length,2);assert.deepEqual(layerWrites[0],layerWrites[1]);
  await p.reload();await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="goals"]').click();await p.locator('[data-goal-child-select="child-2"]').click();await layerProfile.locator('summary').click();
  const correctedRow=layerProfile.locator('[data-profile-facts] li').filter({hasText:'虚构更正：尚未核对原件 '+width});assert.equal(await correctedRow.count(),1);assert.match(await correctedRow.innerText(),/7\/10[\s\S]*数学 · 家长观察/);
  assert.equal(await layerProfile.locator('[data-profile-reports] > li').count(),6);assert.match(await layerProfile.innerText(),/每类最多显示最近6条/);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const layerSaved=(await(await p.request.get(url+'api/state')).json()).records.filter(r=>String(r.id)===layerRecord);assert.equal(layerSaved.length,1);assert.equal(layerSaved[0].note,'虚构更正：尚未核对原件 '+width);
  assert.equal((await(await p.request.get(url+'api/goals')).json()).goals.find(g=>g.id===autoGoal.id).current_plan,null);
  if(process.env.GOALS_UI_PROOF_DIR)await layerProfile.screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'profile-layers-corrected-'+width+'.png')});checks++;
  // Wrong-question photo review: upload -> annotate (mocked draft) -> boxes+form -> save as 错题 record.
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQ0AAAAASUVORK5CYII=','base64');
  await p.locator('[data-goal-wrongq]').click();await p.locator('#wrongQDialog[open]').waitFor();
  await p.locator('#wrongQDialog [data-wq-files]').first().setInputFiles({name:'错题.png',mimeType:'image/png',buffer:png});
  await p.locator('#wrongQDialog').getByText('已上传',{exact:false}).waitFor();
  await p.locator('[data-wq-annotate]').click();
  await p.locator('#wrongQDialog [data-wq-item]').first().waitFor();
  assert.ok(await p.locator('#wrongQDialog .wq-box.wq-wrong_item').count()>=1,'a wrong_item box is drawn over the photo');
  assert.equal(await p.locator('#wrongQDialog [data-wq-item]').count(),1,'one wrong_item drafted for review');
  assert.equal(await p.locator('#wrongQDialog [data-wq-item] [data-wq-field="text"]').inputValue(),'27 + 8 = ?','transcription is editable');
  assert.match(await p.locator('#wrongQDialog').innerText(),/模型提示需核对/,'uncertainties surfaced');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'wrong-question dialog fits the viewport');
  if(process.env.GOALS_UI_PROOF_DIR)await p.locator('#wrongQDialog').screenshot({path:path.join(process.env.GOALS_UI_PROOF_DIR,'wrong-question-review-'+width+'.png')});
  await p.locator('[data-wq-save]').click();await p.getByText(/已保存 \d+ 道错题/).waitFor();
  const wq=(await(await p.request.get(url+'api/state')).json()).records.filter(r=>r.category==='错题');
  assert.ok(wq.length>=1,'a 错题 record was saved');  // both widths share one backend
  const mine=wq.find(r=>/题面：27 \+ 8/.test(r.note));assert.ok(mine,'saved 错题 carries the reviewed transcription');assert.equal(mine.attachments.length,1,'original photo attached');
  checks++;
  await p.close();
 }
 console.log(JSON.stringify({passed:true,checks,viewports:[360,1440],synthetic_only:true}));
}finally{if(browser)await browser.close();if(server){server.kill('SIGINT');await Promise.race([once(server,'exit'),wait(2000)]);if(server.exitCode===null)server.kill('SIGKILL')}}})().catch(e=>{console.error(e);process.exitCode=1});
