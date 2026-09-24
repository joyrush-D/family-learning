// Disposable synthetic demo only. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON and TASK_MEDIA_UI_PROOF_DIR. No family account or model calls.
const assert=require('node:assert/strict'),net=require('node:net');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events');
const {setTimeout:delay}=require('node:timers/promises'),{randomUUID}=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function eventually(check,label,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await check())return;await delay(40)}throw Error('Timed out: '+label)}
async function demoServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 env.FAMILY_HOST='family.localhost';env.FAMILY_USER='synthetic-parent';
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',`import app, json, runpy
base=app.ThreadingHTTPServer
class Server(base):
 def __init__(self,*args,**kwargs):
  app.DATA=app.DATA.resolve();app.DB=app.DATA/'family.sqlite3'
  (app.DATA/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[])))
  super().__init__(*args,**kwargs)
app.ThreadingHTTPServer=Server
runpy.run_path('demo.py',run_name='__main__')`,'--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let error='';proc.stdout.resume();proc.stderr.on('data',b=>error+=String(b));proc.on('error',e=>error=e.message);
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{await eventually(async()=>{if(proc.exitCode!==null)throw Error(error||'Demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo');return{url,stop}}catch(e){await stop();throw e}
}
const fs=require('node:fs/promises'),path=require('node:path');
(async()=>{let browser,server;const checks=[];try{
 const videoBytes=execFileSync('ffmpeg',['-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=10','-t','1','-c:v','libx264','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],{timeout:15000});
 server=await demoServer();const url=server.url,origin=url.replace('127.0.0.1','family.localhost');
 const real=route=>route.fetch({url:route.request().url().replace('family.localhost','127.0.0.1'),headers:{...route.request().headers(),host:new URL(origin).host}});
 browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
 for(const width of [360,1440]){
  const context=await browser.newContext({viewport:{width,height:900},permissions:['microphone'],extraHTTPHeaders:{'Tailscale-User-Login':'synthetic-parent'}}),p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  const read=async()=>fetch(url+'api/state').then(r=>r.json());let state=await read();
  const post=async(route,body)=>{const r=await fetch(url+route,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(body)});const j=await r.json();assert(r.ok,JSON.stringify(j));return j};
  const made=await post('api/task/new',{request_key:randomUUID(),child:state.children[0].name,title:'虚构听写 '+width,box:'inbox',category:'homework',due:state.today,action:'核对一个听写词'}),id=made.task.id;
  await p.route('**/api/state',async r=>{const response=await real(r);const d=await response.json();d.asr={...d.asr,configured:true};await r.fulfill({response,json:d})});
  let asrAttempts=0;await p.route('**/api/transcribe',r=>++asrAttempts===1?r.fulfill({status:503,json:{error:'虚构转写失败'}}):r.fulfill({json:{text:'虚构：第三个词听不出来'}}));
  await p.goto(origin);await p.locator('[data-task="'+id+'"]').first().waitFor();
  const open=async()=>{await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskDialog[open]').waitFor()};
  const save=p.locator('#saveTaskFeedback');await open();
  assert.equal(await p.locator('#taskForm #recordAudio').count(),1);assert.equal(await p.locator('#recordForm #recordAudio').count(),0);
  await p.locator('#recordAudio').click();await eventually(async()=>/结束/.test(await p.locator('#recordAudio').innerText()),'recording');await delay(450);await p.locator('#recordAudio').click();
  await p.locator('#pendingUploads audio').waitFor();await eventually(()=>save.isEnabled(),'audio uploaded');
  await p.locator('#transcribeButton').click();await eventually(async()=>/虚构转写失败/.test(await p.locator('#draftStatus').innerText()),'ASR failure retained');assert.equal(await p.locator('#pendingUploads audio').count(),1);
  await p.locator('#transcribeButton').click();await p.locator('#taskTranscriptFields:visible').waitFor();
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'');
  await p.locator('#taskTranscript').fill('虚构核对：第三个词听不清');await p.locator('#taskTranscriptState').selectOption('已核对');
  let attempts=0,bodies=[];await p.route('**/api/task/feedback',async r=>{bodies.push(r.request().postDataJSON());attempts++;if(attempts===1){await real(r);return r.abort('failed')}if(attempts===2)return r.fulfill({status:403,json:{code:'csrf_expired',token:state.token,error:'虚构会话校验更新'}});return r.continue()});
  await save.click();await eventually(async()=>/保存结果尚未核对/.test(await p.locator('#taskError').innerText()),'lost reply');
  assert.equal(await p.locator('#taskTranscript').isDisabled(),true);await p.keyboard.press('Escape');assert(await p.locator('#taskDialog').evaluate(x=>x.open));
  state=await read();let feedback=state.records.filter(r=>r.source==='事项:'+id);assert.equal(feedback.length,1);assert.equal(state.tasks.find(t=>t.id===id).update,null);
  await save.click();await eventually(async()=>/虚构会话校验更新/.test(await p.locator('#taskError').innerText()),'csrf after lost reply');assert.equal(await p.locator('#taskTranscript').isDisabled(),true);
  await save.click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'retry saved');await p.unroute('**/api/task/feedback');assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[0],bodies[2]);assert.equal(await p.locator('#transcribeButton').isDisabled(),true);
  assert.equal(await p.locator('#taskFeedbackHistory audio').count(),1);assert.match(await p.locator('#taskFeedbackHistory').innerText(),/第三个词听不清/);
  const media=p.locator('#taskFeedbackHistory audio');await media.evaluate(a=>a.load());await eventually(()=>media.evaluate(a=>a.readyState>=1),'audio can play');
  await p.keyboard.press('Escape');await p.reload();await p.locator('nav [data-page="calendar"]').click();await open();assert.match(await p.locator('#taskFeedbackHistory').innerText(),/已核对/);
  await p.locator('[data-task-feedback-edit]').first().click();await p.locator('#taskForm [name=note]').fill('虚构：这是家长补充的原话');assert.equal(await p.locator('#pendingUploads [data-detach]').count(),0);
  await save.click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'correction saved');
  state=await read();feedback=state.records.filter(r=>r.source==='事项:'+id);assert.equal(feedback.length,1);assert.equal(feedback[0].transcript,'虚构核对：第三个词听不清');assert.equal(feedback[0].note,'虚构：这是家长补充的原话');
  const history=await fetch(url+'api/record/history/'+feedback[0].id).then(r=>r.json());assert(history.history.length>=1);
  // The existing state-only path is still explicit and functional.
  await p.locator('#taskForm [name=status]').selectOption('已完成');await p.locator('#taskForm [name=note]').fill('虚构：本次作业已核对');await p.locator('#taskForm [type=submit]').click();await eventually(()=>p.locator('#taskDialog').evaluate(x=>!x.open),'status saved');
  state=await read();assert.equal(state.tasks.find(t=>t.id===id).update.status,'已完成');
  // Reopen from completed items, append an original-only feedback without reopening the assignment.
  await p.locator('nav [data-page="home"]').click();await p.locator('[data-task-all="homework"]').click();await p.locator('[data-task-box="已完成"]').click();await open();
  await p.evaluate(()=>{window.savedRecorder=window.MediaRecorder;window.MediaRecorder=undefined});await p.locator('#recordAudio').click();assert.match(await p.locator('#uploadStatus').innerText(),/上传已有录音/);await p.evaluate(()=>{window.MediaRecorder=window.savedRecorder;delete window.savedRecorder});
  const wav=Buffer.alloc(44+3200);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(3200,40);
  let uploadAttempts=0;await p.route('**/api/upload',r=>++uploadAttempts===1?r.fulfill({status:503,json:{error:'虚构上传失败'}}):r.continue());
  await p.locator('#fileInput').setInputFiles({name:'synthetic-feedback.wav',mimeType:'audio/wav',buffer:wav});await p.locator('#retryUpload:visible').waitFor();await save.click();assert.match(await p.locator('#taskError').innerText(),/未上传成功/);
  await p.locator('#retryUpload').click();await p.locator('#pendingUploads audio').waitFor();await eventually(()=>save.isEnabled(),'retry upload');await p.unroute('**/api/upload');
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-photo.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=','base64')});await p.locator('#pendingUploads img').waitFor();await eventually(()=>save.isEnabled(),'photo uploaded');
  await p.route('**/api/task/feedback',r=>r.fulfill({status:401,json:{error:'虚构登录已过期'}}));await save.click();await p.locator('#parentLoginDialog[open]').waitFor();assert.equal(await p.locator('#pendingUploads audio').count(),1);assert.equal(await p.locator('#pendingUploads img').count(),1);await p.keyboard.press('Escape');assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true);await p.unroute('**/api/task/feedback');
  await save.click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'completed feedback saved');
  state=await read();assert.equal(state.tasks.find(t=>t.id===id).update.status,'已完成');feedback=state.records.filter(r=>r.source==='事项:'+id);assert.equal(feedback.length,2);assert(feedback.some(r=>r.note===''&&r.transcript===''&&r.attachments.length===2));
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  // A video-only observation stays on the completed task, without ASR or a mastery claim.
  const asrBeforeVideo=asrAttempts;let videoUploads=0;
  await p.route('**/api/upload',r=>++videoUploads===1?r.fulfill({status:503,json:{error:'虚构视频上传失败'}}):r.continue());
  await p.locator('#videoInput').setInputFiles({name:'synthetic-video.mp4',mimeType:'audio/mpeg',buffer:videoBytes});
  await p.locator('#retryUpload:visible').waitFor();await save.click();assert.match(await p.locator('#taskError').innerText(),/未上传成功/);
  await p.locator('#retryUpload').click();await p.locator('#pendingUploads video').waitFor();await eventually(()=>save.isEnabled(),'video uploaded');await p.unroute('**/api/upload');
  assert.equal(await p.locator('#pendingUploads audio').count(),0);assert.equal(await p.locator('#transcribeButton').isDisabled(),true);
  const play=async locator=>{await eventually(()=>locator.evaluate(v=>v.readyState>=1),'video metadata');await locator.evaluate(async v=>{v.muted=true;await v.play()});await eventually(()=>locator.evaluate(v=>v.currentTime>0.1),'video decoded');await locator.evaluate(v=>{v.pause();v.currentTime=0.5});await eventually(()=>locator.evaluate(v=>!v.seeking&&v.currentTime>=0.5),'video seek')};
  await play(p.locator('#pendingUploads video'));let videoSaves=0;const videoBodies=[];
  await p.route('**/api/task/feedback',async r=>{videoBodies.push(r.request().postDataJSON());if(++videoSaves===1){await real(r);return r.abort('failed')}return r.continue()});
  await save.click();await eventually(async()=>/保存结果尚未核对/.test(await p.locator('#taskError').innerText()),'video lost reply');
  assert.equal(await p.locator('#videoInput').isDisabled(),true);assert.equal(await p.locator('#pendingUploads video').count(),1);
  await save.click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'video feedback saved');await p.unroute('**/api/task/feedback');assert.deepEqual(videoBodies[0],videoBodies[1]);
  await p.keyboard.press('Escape');await open();await p.locator('#taskFeedbackHistory video').waitFor();await play(p.locator('#taskFeedbackHistory video'));
  state=await read();feedback=state.records.filter(r=>r.source==='事项:'+id);assert.equal(feedback.length,3);const videoRecord=feedback.find(r=>r.attachments.some(a=>state.uploads.find(u=>u.id===a)?.mime==='video/mp4'));
  assert(videoRecord);assert.equal(videoRecord.note,'');assert.equal(videoRecord.transcript,'');assert.equal(state.tasks.find(t=>t.id===id).update.status,'已完成');assert.equal(asrAttempts,asrBeforeVideo);
  // Same-page read of the background video observation draft: synthetic GET states, no model call, no task or record change.
  const panel=p.locator('[data-video-draft="'+videoRecord.id+'"]'),recordsBefore=JSON.stringify(state.records),taskBefore=JSON.stringify(state.tasks.find(t=>t.id===id));
  assert.equal(await panel.count(),1);assert.equal(/内容尚未分析/.test(await p.locator('#taskFeedbackHistory').innerText()),false);assert.match(await panel.innerText(),/查看画面观察/);
  const uploadID=videoRecord.attachments.find(a=>state.uploads.find(u=>u.id===a)?.mime==='video/mp4'),views=[],getURLs=[];
  const video=extra=>({record_id:videoRecord.id,task_id:id,basis:'task_feedback',audience:'parent',read_only:true,explanation:'',videos:[{upload_id:uploadID,job_id:'video:'+videoRecord.id,...extra}]});
  const videoRoute=u=>u.pathname==='/api/record/video';await p.route(videoRoute,async r=>{getURLs.push(r.request().url());const next=views.shift();if(typeof next==='function')return next(r);if(!next)return r.continue();return r.fulfill(next)});
  views.push({json:video({state:'ready',explanation:'仅供家长对照原视频核对；未评估声音，不代表完成或掌握。',updated:'2026-09-22 08:00',duration_seconds:1,draft:{observations:[{start_seconds:0,end_seconds:1,text:'<b>虚构</b>孩子在纸上写字'}],uncertainties:['<img src=x onerror="window.__xss=1">看不清第二行'],audio_assessed:false}})});
  await panel.locator('[data-video-draft-load]').click();await eventually(async()=>/画面观察（待家长核对）/.test(await panel.innerText()),'ready draft');
  let text=await panel.innerText();assert.match(text,/0:00–0:01/);assert.match(text,/<b>虚构<\/b>孩子在纸上写字/);assert.match(text,/看不清第二行/);assert.match(text,/声音未评估/);assert.match(text,/不代表完成或掌握/);assert.match(text,/2026-09-22 08:00/);
  assert.equal(await panel.locator('b, img').count(),0);assert.equal(await p.evaluate(()=>window.__xss),undefined);assert.equal(await p.locator('#taskFeedbackHistory video').count(),1);assert.equal(await panel.locator('[data-video-draft-retry]').count(),0);
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await fs.mkdir(process.env.TASK_MEDIA_UI_PROOF_DIR,{recursive:true});await panel.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'task-video-ready-'+width+'.png')})}
  views.push({json:video({state:'ready',draft:{observations:[],uncertainties:[],audio_assessed:true}})});
  await panel.locator('[data-video-draft-load]').click();await eventually(async()=>/这次没有整理出/.test(await panel.innerText()),'unexpected audio flag does not invent support');assert.match(await panel.innerText(),/声音未评估/);assert.equal(/声音已评估/.test(await panel.innerText()),false);
  views.push({json:video({state:'pending',explanation:'Agent将在后台整理这份任务视频的画面观察；结果只供家长核对，不会改动任务或学习记录。'})});
  await panel.locator('[data-video-draft-load]').click();await eventually(async()=>/后台尚未整理完成/.test(await panel.innerText()),'pending draft');assert.equal(await panel.locator('[data-video-draft-retry]').count(),0);assert.equal(await panel.locator('[data-video-state="pending"]').count(),1);
  views.push({json:video({state:'error',explanation:'虚构后台整理失败',attempts:2,exhausted:true})});
  await panel.locator('[data-video-draft-load]').click();await eventually(async()=>/虚构后台整理失败/.test(await panel.innerText()),'error draft');assert.match(await panel.innerText(),/已尝试2次/);
  let retries=0;const retryBodies=[];await p.route('**/api/agent/action',async r=>{retryBodies.push(r.request().postDataJSON());if(++retries===1)return r.abort('failed');return r.fulfill({json:{ok:true,state:'retry_pending'}})});
  await panel.locator('[data-video-draft-retry]').click();await eventually(async()=>/网络中断/.test(await panel.innerText()),'retry network failure kept');assert.equal(await panel.locator('[data-video-draft-retry]').count(),1);assert.match(await panel.innerText(),/虚构后台整理失败|网络中断/);
  await panel.locator('[data-video-draft-retry]').click();await eventually(async()=>/已安排后台重试/.test(await panel.innerText()),'retry queued');await p.unroute('**/api/agent/action');
  assert.deepEqual(retryBodies,[{action:'retry',id:'video:'+videoRecord.id},{action:'retry',id:'video:'+videoRecord.id}]);
  // 401 while reading: login dialog opens, the unsaved note stays, the task dialog stays open.
  await p.locator('#taskForm [name=note]').fill('虚构未保存反馈');views.push({status:401,json:{error:'虚构登录已过期'}});
  await panel.locator('[data-video-draft-load]').click();await p.locator('#parentLoginDialog[open]').waitFor();await p.keyboard.press('Escape');assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true);assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构未保存反馈');await eventually(async()=>/重新登录/.test(await panel.innerText()),'401 kept with retry');assert.equal(await panel.locator('[data-video-draft-load]').count(),1);
  // Reopen reads fresh: a reply still in flight from the previous open must not fill the new panel.
  let release;views.push(r=>new Promise(res=>{release=()=>res(r.fulfill({json:video({state:'ready',explanation:'过期',updated:'x',duration_seconds:1,draft:{observations:[{start_seconds:0,end_seconds:1,text:'过期回执'}],uncertainties:[],audio_assessed:false}})}))}));
  await panel.locator('[data-video-draft-load]').click();await eventually(async()=>/正在读取/.test(await panel.innerText()),'in flight');
  await p.locator('#taskForm [name=note]').fill('');await p.keyboard.press('Escape');await open();assert.match(await panel.innerText(),/查看画面观察/);release();await delay(400);
  assert.equal(/过期回执/.test(await p.locator('#taskFeedbackHistory').innerText()),false);assert.match(await panel.innerText(),/查看画面观察/);
  // The isolated demo answers the real GET without a model call; it never shows a ready draft here.
  await panel.locator('[data-video-draft-load]').click();await eventually(async()=>!/查看画面观察|正在读取/.test(await panel.innerText()),'real demo read');assert.equal(await panel.locator('[data-video-state="ready"]').count(),0);assert.equal(await panel.locator('[data-video-draft-load]').count(),1);
  assert(getURLs.length>=6&&getURLs.every(u=>new URL(u).searchParams.get('record_id')===String(videoRecord.id)),JSON.stringify(getURLs));
  state=await read();assert.equal(JSON.stringify(state.records),recordsBefore);assert.equal(JSON.stringify(state.tasks.find(t=>t.id===id)),taskBefore);await p.locator('#taskFeedbackHistory video').waitFor();
  // #23 Explicit parent review of the listed observations: nothing pre-selected, POST only on click with the exact token and indices, server echo shown, lost reply/401/409 kept honest, revoke explicit, stale reply isolated, records and task unchanged.
  const tokenA='a'.repeat(64),tokenB='b'.repeat(64),obsA=[{start_seconds:0,end_seconds:1,text:'<i>虚构</i>第一条：孩子在写字'},{start_seconds:1,end_seconds:2,text:'虚构第二条：孩子翻页'}];
  const unconfirmed={state:'unconfirmed',label:'家长已核对的视频观察',explanation:'家长尚未核对这份视频观察，或已撤回核对；只有家长明确选择后才算核对。',audio_assessed:false};
  const ready=(token,review,extra)=>video({state:'ready',explanation:'仅供家长对照原视频核对；未评估声音，不代表完成或掌握。',updated:'2026-09-23 08:00',duration_seconds:2,token,draft:{observations:obsA,uncertainties:['虚构看不清'],audio_assessed:false},review,...extra});
  const confirmedReview=selected=>({state:'confirmed',id:7,reviewed_at:'2026-09-23 08:05',label:'家长已核对的视频观察',explanation:'家长选定了这些画面观察作为自己核对过的内容；未评估声音，不代表完成或掌握，不会自动改动任务、学习记录或计划。',audio_assessed:false,selected,observations:selected.map(i=>obsA[i]),uncertainties:['虚构看不清'],duration_seconds:2});
  const echo=(token,action,review)=>({record_id:videoRecord.id,upload_id:uploadID,task_id:id,token,id:7,action,reviewed_at:'2026-09-23 08:05',repeated:false,review});
  const reviewBodies=[],reviewPlan=[],reviewRoute=u=>u.pathname==='/api/record/video/review';
  await p.route(reviewRoute,async r=>{reviewBodies.push(r.request().postDataJSON());const next=reviewPlan.shift();if(typeof next==='function')return next(r);return r.fulfill(next||{status:500,json:{error:'虚构未计划的核对请求'}})});
  const boxes=panel.locator('[data-video-obs]'),confirm=panel.locator('[data-video-review-confirm]'),revoke=panel.locator('[data-video-review-revoke]'),load=()=>panel.locator('[data-video-draft-load]').first().click();
  views.push({json:video({state:'ready',draft:{observations:obsA,uncertainties:[],audio_assessed:false}})});await load();await eventually(async()=>/第一条/.test(await panel.innerText()),'legacy ready without token or review');
  assert.equal(await boxes.count(),0);assert.equal(await confirm.count(),0);assert.equal(await panel.locator('i').count(),0);
  views.push({json:ready(tokenA,unconfirmed)});await load();await eventually(async()=>/尚未核对/.test(await panel.innerText()),'unconfirmed shown');
  assert.equal(await boxes.count(),2);assert.equal(await panel.locator('[data-video-obs]:checked').count(),0);assert.equal(await confirm.isDisabled(),true);assert.equal(await revoke.count(),0);assert.equal(await panel.locator('i').count(),0);
  assert(await boxes.evaluateAll(xs=>xs.every(x=>x.getBoundingClientRect().width<=24&&x.getBoundingClientRect().height<=24&&x.closest('label').getBoundingClientRect().height>=44)),'compact checkbox and tappable label');
  await boxes.nth(1).check();assert.equal(await confirm.isEnabled(),true);await boxes.nth(1).uncheck();assert.equal(await confirm.isDisabled(),true);await boxes.nth(0).check();await boxes.nth(1).check();await boxes.nth(0).uncheck();
  await p.locator('#taskForm [name=note]').fill('虚构核对期间未保存的反馈');
  reviewPlan.push(r=>r.abort('failed'));await confirm.click();await eventually(async()=>/尚未收到回执/.test(await panel.innerText()),'review lost reply');
  assert.equal(await boxes.nth(1).isChecked(),true);assert.equal(await boxes.nth(1).isDisabled(),true);assert.match(await confirm.innerText(),/重试/);assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),0);
  reviewPlan.push({status:401,json:{error:'虚构登录已过期'}});await confirm.click();await p.locator('#parentLoginDialog[open]').waitFor();await p.keyboard.press('Escape');assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true);
  await eventually(async()=>/重新登录/.test(await panel.innerText()),'review 401 kept');assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构核对期间未保存的反馈');assert.equal(await boxes.nth(1).isChecked(),true);assert.equal(await boxes.nth(1).isEnabled(),true);assert.equal(await confirm.isEnabled(),true);
  // 401 again, recovered through the real login form with a synthetic /api/parent/login reply: no automatic resubmit, unsaved note, pending photo and selection kept, then an explicit retry. A synthetic family.localhost origin exercises the actual login branch while all API traffic remains local.
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-review-photo.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=','base64')});await p.locator('#pendingUploads img').waitFor();
  const loginBodies=[];await p.route('**/api/parent/login',r=>{loginBodies.push(r.request().postDataJSON());return r.fulfill({json:{ok:true}})});
  reviewPlan.push({status:401,json:{error:'虚构登录已过期'}});await confirm.click();await p.locator('#parentLoginDialog[open]').waitFor();await eventually(async()=>/重新登录/.test(await panel.innerText()),'second review 401 kept');const beforeLogin=reviewBodies.length;
  await p.locator('#parentLoginForm [name=username]').fill('虚构家长');await p.locator('#parentLoginForm [name=password]').fill('虚构口令');await p.locator('#parentLoginSubmit').click();
  await eventually(async()=>!(await p.locator('#parentLoginDialog').evaluate(x=>x.open)),'login restored from the real form');assert.deepEqual(loginBodies,[{username:'虚构家长',password:'虚构口令'}]);
  await p.unroute('**/api/parent/login');assert.equal(await p.locator('#taskDialog').evaluate(x=>x.open),true);assert.equal(reviewBodies.length,beforeLogin);assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),0);
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构核对期间未保存的反馈');assert.equal(await p.locator('#pendingUploads img').count(),1);assert.equal(await boxes.nth(1).isChecked(),true);assert.equal(await boxes.nth(1).isEnabled(),true);assert.equal(await confirm.isEnabled(),true);
  reviewPlan.push({json:echo(tokenA,'confirm',confirmedReview([1]))});await confirm.click();await eventually(async()=>/已核对1条/.test(await panel.innerText()),'confirm echoed');
  assert.equal(reviewBodies.length,4);assert.deepEqual(reviewBodies[0],{record_id:videoRecord.id,upload_id:uploadID,expected_token:tokenA,action:'confirm',selected:[1]});assert.deepEqual(reviewBodies[1],reviewBodies[0]);assert.deepEqual(reviewBodies[2],reviewBodies[0]);assert.deepEqual(reviewBodies[3],reviewBodies[0]);assert.equal(await p.locator('#pendingUploads img').count(),1);
  assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),1);assert.match(await panel.innerText(),/第二条：孩子翻页/);assert.match(await panel.innerText(),/声音未评估/);assert.equal(await revoke.count(),1);assert.equal(await panel.locator('[data-video-obs]:checked').count(),0);assert.equal(await confirm.isDisabled(),true);
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await panel.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'task-video-review-'+width+'.png')})}
  await boxes.nth(0).check();reviewPlan.push({status:409,json:{error:'页面上的视频观察已不是当前版本；请刷新后重新核对。',code:'token_stale'}});await confirm.click();
  await eventually(async()=>/不是当前版本/.test(await panel.innerText()),'stale token refused');assert.equal(reviewBodies.length,5);assert.equal(reviewBodies[4].expected_token,tokenA);assert.deepEqual(reviewBodies[4].selected,[0]);
  assert.equal(await boxes.nth(0).isChecked(),true);assert.equal(await boxes.nth(0).isEnabled(),true);assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),1);assert.match(await panel.innerText(),/已核对1条/);
  views.push({json:ready(tokenB,unconfirmed,{updated:'2026-09-23 09:00'})});await load();await eventually(async()=>/尚未核对/.test(await panel.innerText()),'new version unconfirmed');
  assert.equal(await panel.locator('[data-video-obs]:checked').count(),0);assert.equal(await revoke.count(),0);assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),0);assert.equal(reviewBodies.length,5);
  views.push({json:ready(tokenB,confirmedReview([0,1]))});await load();await eventually(async()=>/已核对2条/.test(await panel.innerText()),'confirmed from GET');assert.equal(await panel.locator('[data-video-obs]:checked').count(),0);
  reviewPlan.push({json:echo(tokenB,'revoke',{...unconfirmed,revoked_at:'2026-09-23 09:10'})});await revoke.click();await eventually(async()=>/已撤回核对/.test(await panel.innerText()),'revoke echoed');
  assert.deepEqual(reviewBodies[5],{record_id:videoRecord.id,upload_id:uploadID,expected_token:tokenB,action:'revoke',selected:[]});assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),0);assert.match(await panel.innerText(),/尚未核对/);assert.match(await panel.innerText(),/2026-09-23 09:10/);
  let releaseReview;reviewPlan.push(r=>new Promise(res=>{releaseReview=()=>res(r.fulfill({json:echo(tokenB,'confirm',confirmedReview([0]))}))}));
  await boxes.nth(0).check();await confirm.click();await eventually(()=>!!releaseReview,'review in flight');assert.equal(await boxes.nth(0).isDisabled(),true);
  await p.locator('#taskForm [name=note]').fill('');await p.keyboard.press('Escape');await open();assert.match(await panel.innerText(),/查看画面观察/);releaseReview();await delay(400);
  assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),0);assert.match(await panel.innerText(),/查看画面观察/);
  views.push({json:ready(tokenB,confirmedReview([0]))});await load();await eventually(async()=>/已核对1条/.test(await panel.innerText()),'reopen shows the current GET review');assert.match(await panel.innerText(),/第一条：孩子在写字/);assert.equal(await panel.locator('i').count(),0);assert.equal(await revoke.count(),1);
  // #23 follow-up: a reply from an older panel instance (success or 409) must not erase the newer lost-reply request for the same record/upload after close and reopen. The newer request stays locked and is retried verbatim even if the locked boxes drift; nothing confirms or revokes automatically.
  const drift=async(on,off)=>{await boxes.nth(on).evaluate(el=>{el.checked=true});await boxes.nth(off).evaluate(el=>{el.checked=false})};
  let releaseOld=null;reviewPlan.push(r=>new Promise(res=>{releaseOld=()=>res(r.fulfill({json:echo(tokenB,'revoke',{...unconfirmed,revoked_at:'2026-09-23 09:20'})}))}));
  await revoke.click();await eventually(()=>!!releaseOld,'old revoke in flight');assert.equal(reviewBodies.length,8);
  await p.keyboard.press('Escape');await open();assert.match(await panel.innerText(),/查看画面观察/);
  views.push({json:ready(tokenB,unconfirmed,{updated:'2026-09-23 09:30'})});await load();await eventually(async()=>/尚未核对/.test(await panel.innerText()),'reopened unconfirmed');assert.equal(reviewBodies.length,8);assert.equal(await revoke.count(),0);
  await p.locator('#taskForm [name=note]').fill('虚构重开后未保存的反馈');reviewPlan.push(r=>r.abort('failed'));await boxes.nth(1).check();await confirm.click();await eventually(async()=>/尚未收到回执/.test(await panel.innerText()),'newer confirm lost reply');
  const lostConfirm={record_id:videoRecord.id,upload_id:uploadID,expected_token:tokenB,action:'confirm',selected:[1]};assert.equal(reviewBodies.length,9);assert.deepEqual(reviewBodies[8],lostConfirm);
  const newerStatus=await panel.locator('[data-video-review-status]').innerText();releaseOld();await delay(400);
  assert.equal(await panel.locator('[data-video-review="confirmed"]').count(),0);assert.equal(await panel.locator('[data-video-review-status]').innerText(),newerStatus);assert.match(await panel.innerText(),/尚未收到回执/);assert.equal(reviewBodies.length,9);
  assert.equal(await boxes.nth(1).isChecked(),true);assert.equal(await boxes.nth(1).isDisabled(),true);assert.equal(await boxes.nth(0).isDisabled(),true);assert.match(await confirm.innerText(),/重试/);assert.equal(await revoke.count(),0);
  await drift(0,1);reviewPlan.push({json:echo(tokenB,'confirm',confirmedReview([1]))});await confirm.click();await eventually(async()=>/已核对1条/.test(await panel.innerText()),'newer request retried verbatim after the old success');
  assert.equal(reviewBodies.length,10);assert.deepEqual(reviewBodies[9],lostConfirm);assert.match(await panel.innerText(),/第二条：孩子翻页/);assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'虚构重开后未保存的反馈');assert.equal(await revoke.count(),1);assert.equal(await panel.locator('[data-video-obs]:checked').count(),0);
  releaseOld=null;reviewPlan.push(r=>new Promise(res=>{releaseOld=()=>res(r.fulfill({status:409,json:{error:'页面上的视频观察已不是当前版本；请刷新后重新核对。',code:'token_stale'}}))}));
  await revoke.click();await eventually(()=>!!releaseOld,'old revoke in flight again');assert.equal(reviewBodies.length,11);
  await p.locator('#taskForm [name=note]').fill('');await p.keyboard.press('Escape');await open();assert.match(await panel.innerText(),/查看画面观察/);
  views.push({json:ready(tokenB,unconfirmed,{updated:'2026-09-23 09:40'})});await load();await eventually(async()=>/尚未核对/.test(await panel.innerText()),'reopened unconfirmed again');assert.equal(reviewBodies.length,11);
  reviewPlan.push(r=>r.abort('failed'));await boxes.nth(0).check();await confirm.click();await eventually(async()=>/尚未收到回执/.test(await panel.innerText()),'newer confirm lost reply before the old 409');
  const lostConfirm2={...lostConfirm,selected:[0]};assert.equal(reviewBodies.length,12);assert.deepEqual(reviewBodies[11],lostConfirm2);
  releaseOld();await delay(400);
  assert.equal(/不是当前版本/.test(await panel.innerText()),false);assert.match(await panel.innerText(),/尚未收到回执/);assert.equal(await boxes.nth(0).isChecked(),true);assert.equal(await boxes.nth(0).isDisabled(),true);assert.match(await confirm.innerText(),/重试/);assert.equal(reviewBodies.length,12);
  await drift(1,0);reviewPlan.push({json:echo(tokenB,'confirm',confirmedReview([0]))});await confirm.click();await eventually(async()=>/已核对1条/.test(await panel.innerText()),'newer request retried verbatim after the old 409');
  assert.equal(reviewBodies.length,13);assert.deepEqual(reviewBodies[12],lostConfirm2);assert.match(await panel.innerText(),/第一条：孩子在写字/);assert.equal(await panel.locator('[data-video-obs]:checked').count(),0);assert.equal(await revoke.count(),1);
  await p.unroute(reviewRoute);assert.equal(reviewBodies.length,13);
  state=await read();assert.equal(JSON.stringify(state.records),recordsBefore);assert.equal(JSON.stringify(state.tasks.find(t=>t.id===id)),taskBefore);

  // Explicit video transcription uses independent original fingerprint even while visual observations are pending.
  const fingerprint='c'.repeat(64),nextFingerprint='d'.repeat(64),transcribeBodies=[],transcribePlan=[];
  const transcriptView=(fp=fingerprint)=>video({state:'pending',transcription_fingerprint:fp});
  const transcriptReply=(fp=fingerprint,text='<b>虚构视频文字</b>')=>({record_id:videoRecord.id,upload_id:uploadID,task_id:id,transcription_fingerprint:fp,state:'pending_review',saved:false,text,audio:{audio_start_seconds:0.125,pcm_seconds:1.75,provided_seconds:2},speakers_distinguished:false,audio_assessed:false});
  const transcriptRoute=u=>u.pathname==='/api/record/video/transcribe';
  await p.route(transcriptRoute,async r=>{transcribeBodies.push(r.request().postDataJSON());const next=transcribePlan.shift();assert(next,'unexpected automatic transcription');return typeof next==='function'?next(r):r.fulfill(next)});
  const transcribe=panel.locator('[data-video-transcribe]'),transcriptInput=panel.locator('[data-video-transcript-text]'),applyTranscript=panel.locator('[data-video-transcript-apply]');
  views.push({json:transcriptView()});await load();await transcribe.waitFor();assert.equal(transcribeBodies.length,0);
  await p.locator('#taskForm [name=note]').fill('不能覆盖的未保存文字');
  await p.locator('#cameraInput').setInputFiles({name:'synthetic-transcript-photo.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=','base64')});await p.locator('#pendingUploads img').waitFor();
  transcribePlan.push(r=>r.abort('failed'));await transcribe.click();await eventually(async()=>/再次点击可能再次转写/.test(await panel.innerText()),'transcription lost response is not auto replayed');await delay(250);assert.equal(transcribeBodies.length,1);assert.equal(await p.locator('#pendingUploads img').count(),1);
  transcribePlan.push({status:401,json:{error:'虚构登录失效'}});await transcribe.click();await p.locator('#parentLoginDialog[open]').waitFor();
  await p.route('**/api/parent/login',r=>r.fulfill({json:{ok:true}}));await p.locator('#parentLoginForm [name=username]').fill('虚构家长');await p.locator('#parentLoginForm [name=password]').fill('虚构口令');await p.locator('#parentLoginSubmit').click();await eventually(()=>p.locator('#parentLoginDialog').evaluate(x=>!x.open),'transcription login restored');await p.unroute('**/api/parent/login');await delay(250);assert.equal(transcribeBodies.length,2);
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'不能覆盖的未保存文字');assert.equal(await p.locator('#pendingUploads img').count(),1);
  transcribePlan.push({status:409,json:{error:'虚构版本变化'}});await transcribe.click();await eventually(()=>transcribe.isDisabled(),'409 requires GET');assert.match(await panel.innerText(),/刷新/);
  views.push({json:transcriptView(nextFingerprint)});await load();await eventually(()=>transcribe.isEnabled(),'new fingerprint ready');assert.equal(transcribeBodies.length,3);
  let releaseTranscript;transcribePlan.push(r=>new Promise(resolve=>{releaseTranscript=()=>resolve(r.fulfill({json:transcriptReply(nextFingerprint)}))}));await transcribe.click();await eventually(()=>!!releaseTranscript,'one request in flight');assert.equal(await transcribe.isDisabled(),true);assert.equal(await panel.locator('[data-video-draft-load]').isDisabled(),true);
  releaseTranscript();await transcriptInput.waitFor();assert.equal(transcribeBodies.length,4);assert.deepEqual(transcribeBodies[3],{record_id:videoRecord.id,upload_id:uploadID,expected_fingerprint:nextFingerprint});
  assert.equal(await transcriptInput.inputValue(),'<b>虚构视频文字</b>');assert.equal(await panel.locator('b').count(),0);assert.match(await panel.innerText(),/0.125 秒/);assert.match(await panel.innerText(),/1.75 秒/);assert.match(await panel.innerText(),/未分说话人/);assert.match(await panel.innerText(),/未评估声音或发音/);
  await applyTranscript.click();assert.match(await panel.innerText(),/现有输入未覆盖/);assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'不能覆盖的未保存文字');assert.equal(await p.locator('#pendingUploads img').count(),1);
  // Close drops unsaved UI draft, but an older response cannot modify the newly reopened panel.
  await p.keyboard.press('Escape');await open();views.push({json:transcriptView()});await load();
  releaseTranscript=null;transcribePlan.push(r=>new Promise(resolve=>{releaseTranscript=()=>resolve(r.fulfill({json:transcriptReply()}))}));await transcribe.click();await eventually(()=>!!releaseTranscript,'old transcript in flight');await p.keyboard.press('Escape');await open();
  views.push({json:transcriptView()});await load();transcribePlan.push(r=>r.abort('failed'));await transcribe.click();await eventually(async()=>/回执未收到/.test(await panel.innerText()),'new panel lost response');const retained=await panel.innerText();releaseTranscript();await delay(300);assert.equal(await panel.innerText(),retained);assert.equal(await transcriptInput.count(),0);assert.equal(transcribeBodies.length,6);
  transcribePlan.push({json:transcriptReply()});await transcribe.click();await transcriptInput.waitFor();await transcriptInput.fill('虚构：经家长核对的视频文字');
  // A changed original between response and apply refuses before filling any record field.
  views.push({json:transcriptView(nextFingerprint)});await applyTranscript.click();await eventually(async()=>/版本已变化/.test(await panel.innerText()),'apply rereads original');assert.equal(await p.locator('#taskTranscript').inputValue(),'');
  views.push({json:transcriptView()});await applyTranscript.click();await eventually(async()=>/尚未保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'explicit same-record fill');
  assert.equal(await p.locator('#taskTranscript').inputValue(),'虚构：经家长核对的视频文字');assert.equal(await p.locator('#taskTranscriptState').inputValue(),'已核对');assert.equal(await save.innerText(),'保存反馈更正');state=await read();assert.equal(state.records.find(r=>r.id===videoRecord.id).transcript,'');
  let correctionAttempts=0;await p.route('**/api/task/feedback',r=>++correctionAttempts===1?r.fulfill({status:503,json:{error:'虚构保存失败'}}):r.continue());
  await save.click();await eventually(async()=>/虚构保存失败/.test(await p.locator('#taskError').innerText()),'transcription correction failure');assert.equal(await p.locator('#taskTranscript').inputValue(),'虚构：经家长核对的视频文字');await save.click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'transcription correction retry');await p.unroute('**/api/task/feedback');
  await p.keyboard.press('Escape');await open();state=await read();const savedVideo=state.records.find(r=>r.id===videoRecord.id);assert.equal(savedVideo.transcript,'虚构：经家长核对的视频文字');assert.deepEqual(savedVideo.attachments,videoRecord.attachments);assert.equal(savedVideo.note,videoRecord.note);assert.equal(state.records.length,JSON.parse(recordsBefore).length);assert.equal(JSON.stringify(state.tasks.find(t=>t.id===id)),taskBefore);
  // Do not silently overwrite the original transcript or another record's correction; preserve a same-record unsaved note.
  await p.locator('[data-task-feedback-edit="'+videoRecord.id+'"]').click();await p.locator('#taskForm [name=note]').fill('更正中未保存的备注');
  views.push({json:transcriptView()});await load();transcribePlan.push({json:transcriptReply(fingerprint,'第二份核对文字')});await transcribe.click();await transcriptInput.waitFor();await applyTranscript.click();assert.match(await panel.innerText(),/原转写未覆盖/);assert.equal(await p.locator('#taskTranscript').inputValue(),savedVideo.transcript);
  await panel.locator('[data-video-transcript-replace]').check();views.push({json:transcriptView()});await applyTranscript.click();await eventually(async()=>await p.locator('#taskTranscript').inputValue()==='第二份核对文字','explicit replacement');assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'更正中未保存的备注');
  assert.equal(transcribeBodies.length,8);assert.equal(asrAttempts,asrBeforeVideo);assert.equal((await read()).records.find(r=>r.id===videoRecord.id).transcript,savedVideo.transcript);
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await p.locator('#taskTranscript').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'video-transcript-'+width+'.png')})}
  await p.unroute(transcriptRoute);
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await fs.mkdir(process.env.TASK_MEDIA_UI_PROOF_DIR,{recursive:true});await p.locator('#taskFeedbackHistory video').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'task-video-'+width+'.png')})}
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await fs.mkdir(process.env.TASK_MEDIA_UI_PROOF_DIR,{recursive:true});await p.locator('#taskDialog').evaluate(x=>x.scrollTop=0);await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'task-feedback-'+width+'.png')})}
  // #23 linked independent record: the transcription entry exists only inside a saved record explicitly linked to the same child's task; unlinked or other-child records get no entry and no call.
  const linkedBodies=[],linkedPlan=[],asrBeforeLinked=asrAttempts;
  await p.route(transcriptRoute,async r=>{linkedBodies.push(r.request().postDataJSON());const next=linkedPlan.shift();assert(next,'unexpected automatic linked transcription');return typeof next==='function'?next(r):r.fulfill(next)});
  state=await read();const kid=state.children[0].name,otherKid=(state.children.find(c=>c.name!==kid)||state.children[0]).name;
  const lupload=await fetch(url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'X-File-Name':'synthetic-linked.mp4'},body:videoBytes}).then(r=>r.json());assert(lupload.attachment,JSON.stringify(lupload));const lup=lupload.attachment.id;
  const ltask=(await post('api/task/new',{request_key:randomUUID(),child:kid,title:'虚构关联事项 '+width,box:'inbox',category:'homework',due:state.today,action:'虚构'})).task;
  const lr=(await post('api/record',{child:kid,day:state.today,category:'学习进展',subject:'英语',title:'虚构独立视频记录 '+width,note:'原说明',source:'试卷 / 作业核对',attachments:[lup],transcript:'旧转写',transcript_state:'已核对'})).record_id;
  await post('api/record/task-link',{record_id:lr,child:kid,task_id:ltask.id,expected_linked_at:''});
  const oupload=await fetch(url+'api/upload',{method:'POST',headers:{'X-Family-Token':state.token,'X-File-Name':'synthetic-unlinked.mp4'},body:videoBytes}).then(r=>r.json());assert(oupload.attachment,JSON.stringify(oupload));
  const ur=(await post('api/record',{child:otherKid,day:state.today,category:'学习进展',subject:'英语',title:'虚构未关联视频 '+width,note:'未关联说明',source:'家长观察',attachments:[oupload.attachment.id]})).record_id;
  state=await read();const linkedBefore=JSON.stringify(state.records.find(r=>r.id===lr)),recordCount=state.records.length,tasksBefore=JSON.stringify(state.tasks.map(t=>[t.id,t.update]));
  const lfp=(await fetch(url+'api/record/video?record_id='+lr).then(r=>r.json())).videos[0].transcription_fingerprint,lfp2=lfp,lv=(fp,taskId=ltask.id)=>({json:{record_id:lr,task_id:taskId,basis:'record',audience:'parent',read_only:true,explanation:'',videos:[{upload_id:lup,job_id:'video:'+lr,state:'pending',transcription_fingerprint:fp}]}});
  const lreply=(fp,text,taskId=ltask.id)=>({record_id:lr,upload_id:lup,task_id:taskId,transcription_fingerprint:fp,state:'pending_review',saved:false,text,audio:{audio_start_seconds:0,pcm_seconds:1,provided_seconds:1},speakers_distinguished:false,audio_assessed:false});
  const lf=p.locator('#recordForm'),lpanel=p.locator('#recordVideoPanel'),ltranscribe=lpanel.locator('[data-video-transcribe]'),lload=lpanel.locator('[data-video-draft-load]'),ltext=lpanel.locator('[data-video-transcript-text]'),lapply=lpanel.locator('[data-video-transcript-apply]');
  const openRecordAgain=async id=>{await p.locator('[data-record="'+id+'"]').first().click();await p.locator('#recordDialog[open]').waitFor()};
  const openRecord=async id=>{await p.reload();await p.waitForFunction(()=>document.querySelector('#content')?.dataset.ready==='true');await p.locator('nav [data-page="more"]').click();await p.locator('.more-links [data-page="growth"]').click();await openRecordAgain(id)};
  const closeRecord=async()=>{await p.keyboard.press('Escape');await eventually(()=>p.locator('#recordDialog').evaluate(x=>!x.open),'record dialog closed')};
  // Unlinked record of another child with the same subject: no entry, no GET, no POST.
  const getBefore=getURLs.length;await openRecord(ur);assert.match(await lpanel.innerText(),/明确关联同一孩子的事项/);assert.equal(await lload.count(),0);assert.equal(await ltranscribe.count(),0);assert.equal(await lf.locator('[name=transcript]').isVisible(),false);await closeRecord();
  assert.equal(getURLs.length,getBefore);assert.equal(linkedBodies.length,0);
  // Linked record: GET reads the fingerprint without ASR; an unsaved link change blocks the request; exact single POST per explicit click; lost reply and real-form 401 are never replayed; 409 needs a fresh GET.
  await openRecord(lr);assert.equal(await lf.locator('[name=transcript]').inputValue(),'旧转写');assert.equal(await lf.locator('[name=transcript]').isDisabled(),true);
  views.push(lv(lfp));await lload.click();await ltranscribe.waitFor();assert.equal(linkedBodies.length,0);assert.equal(asrAttempts,asrBeforeLinked);
  await lf.locator('[name=note]').fill('未保存的说明草稿');
  await p.locator('#recordTaskSelect').selectOption('');await ltranscribe.click();await eventually(async()=>/孩子或关联正在更改/.test(await lpanel.innerText()),'unsaved link change blocks transcription');assert.equal(linkedBodies.length,0);await p.locator('#recordTaskSelect').selectOption(ltask.id);
  linkedPlan.push(r=>r.abort('failed'));await ltranscribe.click();await eventually(async()=>/再次点击可能再次转写/.test(await lpanel.innerText()),'linked lost reply not replayed');await delay(250);assert.equal(linkedBodies.length,1);assert.deepEqual(linkedBodies[0],{record_id:lr,upload_id:lup,expected_fingerprint:lfp});
  linkedPlan.push({status:401,json:{error:'虚构登录失效'}});await ltranscribe.click();await p.locator('#parentLoginDialog[open]').waitFor();
  await p.route('**/api/parent/login',r=>r.fulfill({json:{ok:true}}));await p.locator('#parentLoginForm [name=username]').fill('虚构家长');await p.locator('#parentLoginForm [name=password]').fill('虚构口令');await p.locator('#parentLoginSubmit').click();await eventually(()=>p.locator('#parentLoginDialog').evaluate(x=>!x.open),'linked login restored');await p.unroute('**/api/parent/login');await delay(250);
  assert.equal(linkedBodies.length,2);assert.equal(await p.locator('#recordDialog').evaluate(x=>x.open),true);assert.equal(await lf.locator('[name=note]').inputValue(),'未保存的说明草稿');assert.equal(await p.locator('#pendingUploads video').count(),1);
  linkedPlan.push({status:409,json:{error:'虚构版本变化'}});await ltranscribe.click();await eventually(()=>ltranscribe.isDisabled(),'linked 409 requires GET');assert.match(await lpanel.innerText(),/刷新/);
  views.push(lv(lfp2));await lload.click();await eventually(()=>ltranscribe.isEnabled(),'linked new fingerprint');assert.equal(linkedBodies.length,3);
  linkedPlan.push({json:lreply(lfp2,'<b>虚构关联视频文字</b>')});await ltranscribe.click();await ltext.waitFor();assert.equal(linkedBodies.length,4);assert.deepEqual(linkedBodies[3],{record_id:lr,upload_id:lup,expected_fingerprint:lfp2});
  assert.equal(await ltext.inputValue(),'<b>虚构关联视频文字</b>');assert.equal(await lpanel.locator('b').count(),0);assert.match(await lpanel.innerText(),/未分说话人/);assert.match(await lpanel.innerText(),/未评估声音或发音/);
  // The existing transcript needs explicit replacement consent; apply rereads the fingerprint and fills only this record's correction field, nothing is saved yet.
  await lapply.click();await eventually(async()=>/原转写未覆盖/.test(await lpanel.innerText()),'linked replacement consent');assert.equal(await lf.locator('[name=transcript]').inputValue(),'旧转写');
  await lpanel.locator('[data-video-transcript-replace]').check();views.push(lv(lfp2));await lapply.click();await eventually(async()=>await lf.locator('[name=transcript]').inputValue()==='<b>虚构关联视频文字</b>','linked explicit apply');
  assert.equal(await lf.locator('[name=transcript_state]').inputValue(),'已核对');assert.equal(await lf.locator('[name=note]').inputValue(),'未保存的说明草稿');assert.equal(await p.locator('#pendingUploads video').count(),1);assert.equal(JSON.stringify((await read()).records.find(r=>r.id===lr)),linkedBefore);
  // Another parent relinks the record; the local unlink save hits 409 and reading the current link keeps the unsaved reviewed text, marks it stale (待核对) and never saves it for the new link on its own.
  const task2=(await post('api/task/new',{request_key:randomUUID(),child:kid,title:'虚构第二事项 '+width,box:'inbox',category:'homework',due:state.today,action:'虚构'})).task;
  await post('api/record/task-link',{record_id:lr,child:kid,task_id:task2.id,expected_linked_at:(await read()).records.find(r=>r.id===lr).linked_task_at});
  await p.locator('#recordTaskSelect').selectOption('');await p.locator('#saveRecordTaskLink').click();await p.locator('#refreshRecordTaskLink:visible').waitFor();await p.locator('#refreshRecordTaskLink').click();await eventually(async()=>/已读取当前关联/.test(await p.locator('#recordTaskLinkStatus').innerText()),'linked read current link');
  assert.equal(await lf.locator('[name=transcript]').inputValue(),'<b>虚构关联视频文字</b>');assert.equal(await lf.locator('[name=transcript]').isDisabled(),false);assert.equal(await lf.locator('[name=transcript_state]').inputValue(),'待核对');assert.equal(await lpanel.locator('[data-video-transcript-stale]').count(),1);assert.match(await lpanel.innerText(),/重新核对/);
  assert.equal(await lf.locator('[name=note]').inputValue(),'未保存的说明草稿');assert.equal(await ltext.count(),0);assert.equal(linkedBodies.length,4);assert.equal(JSON.stringify((await read()).records.find(r=>r.id===lr)).includes('虚构关联视频文字'),false);
  // Same-record save: failure keeps input and original, retry succeeds, reopen reads back the same record; note, media, source, child and the current link are preserved; no task status changes.
  await p.locator('#recordTaskSelect').selectOption(task2.id);await lf.locator('[name=transcript_state]').selectOption('已核对');
  await lf.locator('[type=submit]').click();await eventually(async()=>/转写草稿保留/.test(await p.locator('#recordError').innerText()),'stale guard prevents saved reviewed text on new link');assert.equal((await read()).records.find(r=>r.id===lr).transcript,'旧转写');
  const lfp3=(await fetch(url+'api/record/video?record_id='+lr).then(r=>r.json())).videos[0].transcription_fingerprint;
  views.push(lv(lfp3,task2.id));await lload.click();linkedPlan.push({json:lreply(lfp3,'<b>虚构关联视频文字</b>',task2.id)});await ltranscribe.click();await ltext.waitFor();await lpanel.locator('[data-video-transcript-replace]').check();views.push(lv(lfp3,task2.id));await lapply.click();await eventually(async()=>/已填入本条记录/.test(await lpanel.locator('[data-video-transcript-status]').innerText()),'new link explicitly reviewed');assert.equal(await lf.locator('[name=transcript_state]').inputValue(),'已核对');assert.equal(await lpanel.locator('[data-video-transcript-stale]').count(),0);
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await lpanel.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'linked-transcript-review-'+width+'.png')})}

  let recordSaves=0;const recordRoute=u=>u.pathname==='/api/record';await p.route(recordRoute,r=>{const body=r.request().postDataJSON();assert.equal(body.id,lr);assert.deepEqual(body.video_transcript_guard,{upload_id:lup,expected_fingerprint:lfp3});return ++recordSaves===1?r.fulfill({status:503,json:{error:'虚构保存失败'}}):r.continue()});
  await lf.locator('[type=submit]').click();await eventually(async()=>/虚构保存失败/.test(await p.locator('#recordError').innerText()),'linked save failure retained');
  assert.equal(await lf.locator('[name=transcript]').inputValue(),'<b>虚构关联视频文字</b>');assert.equal(await lf.locator('[name=note]').inputValue(),'未保存的说明草稿');assert.equal(await p.locator('#pendingUploads video').count(),1);
  await lf.locator('[type=submit]').click();await eventually(()=>p.locator('#recordDialog').evaluate(x=>!x.open),'linked save retry');await p.unroute(recordRoute);assert.equal(recordSaves,2);
  state=await read();const savedLinked=state.records.find(r=>r.id===lr),originalLinked=JSON.parse(linkedBefore);
  assert.equal(savedLinked.transcript,'<b>虚构关联视频文字</b>');if('transcript_state' in savedLinked)assert.equal(savedLinked.transcript_state,'已核对');assert.equal(savedLinked.note,'未保存的说明草稿');assert.deepEqual(savedLinked.attachments,originalLinked.attachments);assert.equal(savedLinked.source,originalLinked.source);assert.equal(savedLinked.child,originalLinked.child);assert.equal(savedLinked.linked_task_id,task2.id);
  assert.equal(state.records.length,recordCount);assert.equal(JSON.stringify(state.tasks.filter(t=>t.id!==task2.id).map(t=>[t.id,t.update])),tasksBefore);assert.equal(state.tasks.find(t=>t.id===task2.id).update,null);
  const unlinkedAfter=state.records.find(r=>r.id===ur);assert.equal(unlinkedAfter.note,'未关联说明');assert.equal(unlinkedAfter.transcript||'','');
  // Reopen reads back the saved record; an older in-flight reply cannot reach the reopened panel; a locally removed video cannot be transcribed; closing without saving changes nothing.
  await openRecord(lr);assert.equal(await lf.locator('[name=transcript]').inputValue(),'<b>虚构关联视频文字</b>');assert.equal(await lf.locator('[name=transcript]').isDisabled(),true);assert.equal(await lpanel.locator('[data-video-transcript-stale]').count(),0);
  views.push(lv(lfp2,task2.id));await lload.click();await ltranscribe.waitFor();
  let releaseLinked=null;linkedPlan.push(r=>new Promise(res=>{releaseLinked=()=>res(r.fulfill({json:lreply(lfp2,'过期关联回执',task2.id)}))}));await ltranscribe.click();await eventually(()=>!!releaseLinked,'linked reply in flight');
  await closeRecord();await openRecordAgain(lr);views.push(lv(lfp2,task2.id));await lload.click();await ltranscribe.waitFor();releaseLinked();await delay(300);
  assert.equal(await ltext.count(),0);assert.equal(await lf.locator('[name=transcript]').inputValue(),'<b>虚构关联视频文字</b>');assert.equal(linkedBodies.length,6);
  // Changing the local child while ASR is in flight makes the old reply unusable, even though the server's saved record did not change.
  await lf.locator('[name=child]').selectOption(otherKid);await ltranscribe.click();assert.equal(linkedBodies.length,6);await lf.locator('[name=child]').selectOption(kid);
  let releaseChild=null;linkedPlan.push(r=>new Promise(res=>{releaseChild=()=>res(r.fulfill({json:lreply(lfp2,'过期孩子回执',task2.id)}))}));await ltranscribe.click();await eventually(()=>!!releaseChild,'child-change reply in flight');await lf.locator('[name=child]').selectOption(otherKid);releaseChild();await eventually(async()=>/孩子、关联或原件选择已变化/.test(await lpanel.innerText()),'changed-child reply discarded');assert.equal(await ltext.count(),0);assert.equal(await lf.locator('[name=transcript]').inputValue(),'<b>虚构关联视频文字</b>');await lf.locator('[name=child]').selectOption(kid);
  const detach=p.locator('#pendingUploads [data-detach]');assert.equal(await detach.count(),1);{await detach.first().click();await eventually(async()=>await p.locator('#pendingUploads video').count()===0,'video removed locally');await ltranscribe.click();await eventually(async()=>/已从本条记录移除/.test(await lpanel.innerText()),'removed video not transcribed');assert.equal(linkedBodies.length,7);checks.push(width+': removed-video transcription refused')}
  await closeRecord();state=await read();assert.deepEqual(state.records.find(r=>r.id===lr).attachments,originalLinked.attachments);assert.equal(state.records.find(r=>r.id===lr).transcript,'<b>虚构关联视频文字</b>');assert.equal(asrAttempts,asrBeforeLinked);assert.equal(state.records.length,recordCount);
  await p.unroute(transcriptRoute);
  checks.push(width+': linked independent record: unlinked/other-child same-subject record has no entry and zero GET/POST; explicit link GET without ASR; unsaved link change blocks the request; exact single POST; lost reply and real login form 401 not replayed with note and video kept; 409 needs fresh GET; escaped text with audio boundaries; explicit replacement consent; apply rereads fingerprint; relink by another parent + local 409 + read current link keeps unsaved reviewed text marked 待核对 with stale notice, nothing saved; save failure keeps input, retry saves same record with note/media/source/child/link preserved, reopen reads back; stale in-flight reply isolated after close/reopen; removed video refused; close without saving changes nothing');
  await p.keyboard.press('Escape');await p.locator('nav [data-page="more"]').click();await p.locator('[data-capture]').first().click();assert.equal(await p.locator('#recordForm #recordAudio').count(),1);assert.equal(await p.locator('#pendingUploads audio').count(),0);assert.equal(await p.locator('#draftButton').isVisible(),true);await p.keyboard.press('Escape');assert.deepEqual(errors,[]);
  checks.push(width+': explicit video transcription while visual pending, exact fingerprint POST, zero auto replay after loss or real login, 409 refresh, busy lock, stale close/reopen response, escaped editable text and audio range, unsaved media/note protection, apply rereads version, same-record save failure/retry/reopen and explicit overwrite consent; real recorder/upload/playback, separate transcript and ASR failure, Today/Calendar/Inbox entry, lost-reply and expired-CSRF retry, correction, state-only completion, completed-task media-only feedback, failed upload retry, microphone fallback and photo, login-expiry input retention, shared normal-record capture and layout; video-only upload retry, actual playback/seek, lost-reply retry and reopen without completion or ASR; same-page video observation draft: ready/pending/error shown as text only, retry queued with failure retained, 401 keeps unsaved note, stale reply isolated on reopen, real demo read, task and records unchanged; explicit parent video review: no pre-selection, confirm disabled until ticked, exact token and indices posted, lost reply retried verbatim, 401 keeps note and selection, server echo with revoke, 409 keeps input without claiming the new version, refresh shows new version unconfirmed, explicit revoke echoed, in-flight reply isolated after reopen, reopen reads current GET review, escaped text, records and task unchanged; older in-flight reply (success or 409) after reopen leaves the newer lost-reply request locked and retried verbatim, real login form 401 recovery keeps note, pending photo and selection with an explicit retry');await context.close();
 }
 console.log(JSON.stringify({passed:true,checks,syntheticOnly:true,realPhoneTested:false}));
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e.stack||e);process.exitCode=1});
