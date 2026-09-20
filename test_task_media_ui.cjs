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
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});let error='';proc.stdout.resume();proc.stderr.on('data',b=>error+=String(b));proc.on('error',e=>error=e.message);
 const url='http://127.0.0.1:'+port+'/',stop=async()=>{if(proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await done}};
 try{await eventually(async()=>{if(proc.exitCode!==null)throw Error(error||'Demo exited');try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo');return{url,stop}}catch(e){await stop();throw e}
}
const fs=require('node:fs/promises'),path=require('node:path');
(async()=>{let browser,server;const checks=[];try{
 const videoBytes=execFileSync('ffmpeg',['-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=10','-t','1','-c:v','libx264','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],{timeout:15000});
 server=await demoServer();const url=server.url;
 browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
 for(const width of [360,1440]){
  const context=await browser.newContext({viewport:{width,height:900},permissions:['microphone']}),p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  const read=async()=>fetch(url+'api/state').then(r=>r.json());let state=await read();
  const post=async(route,body)=>{const r=await fetch(url+route,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(body)});const j=await r.json();assert(r.ok,JSON.stringify(j));return j};
  const made=await post('api/task/new',{request_key:randomUUID(),child:state.children[0].name,title:'虚构听写 '+width,box:'inbox',category:'homework',due:state.today,action:'核对一个听写词'}),id=made.task.id;
  await p.route('**/api/state',async r=>{const response=await r.fetch();const d=await response.json();d.asr={...d.asr,configured:true};await r.fulfill({response,json:d})});
  let asrAttempts=0;await p.route('**/api/transcribe',r=>++asrAttempts===1?r.fulfill({status:503,json:{error:'虚构转写失败'}}):r.fulfill({json:{text:'虚构：第三个词听不出来'}}));
  await p.goto(url);await p.locator('[data-task="'+id+'"]').first().waitFor();
  const open=async()=>{await p.locator('[data-task="'+id+'"]').first().click();await p.locator('#taskDialog[open]').waitFor()};
  const save=p.locator('#saveTaskFeedback');await open();
  assert.equal(await p.locator('#taskForm #recordAudio').count(),1);assert.equal(await p.locator('#recordForm #recordAudio').count(),0);
  await p.locator('#recordAudio').click();await eventually(async()=>/结束/.test(await p.locator('#recordAudio').innerText()),'recording');await delay(450);await p.locator('#recordAudio').click();
  await p.locator('#pendingUploads audio').waitFor();await eventually(()=>save.isEnabled(),'audio uploaded');
  await p.locator('#transcribeButton').click();await eventually(async()=>/虚构转写失败/.test(await p.locator('#draftStatus').innerText()),'ASR failure retained');assert.equal(await p.locator('#pendingUploads audio').count(),1);
  await p.locator('#transcribeButton').click();await p.locator('#taskTranscriptFields:visible').waitFor();
  assert.equal(await p.locator('#taskForm [name=note]').inputValue(),'');
  await p.locator('#taskTranscript').fill('虚构核对：第三个词听不清');await p.locator('#taskTranscriptState').selectOption('已核对');
  let attempts=0,bodies=[];await p.route('**/api/task/feedback',async r=>{bodies.push(r.request().postDataJSON());attempts++;if(attempts===1){await r.fetch();return r.abort('failed')}if(attempts===2)return r.fulfill({status:403,json:{code:'csrf_expired',token:state.token,error:'虚构会话校验更新'}});return r.continue()});
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
  await p.route('**/api/task/feedback',async r=>{videoBodies.push(r.request().postDataJSON());if(++videoSaves===1){await r.fetch();return r.abort('failed')}return r.continue()});
  await save.click();await eventually(async()=>/保存结果尚未核对/.test(await p.locator('#taskError').innerText()),'video lost reply');
  assert.equal(await p.locator('#videoInput').isDisabled(),true);assert.equal(await p.locator('#pendingUploads video').count(),1);
  await save.click();await eventually(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'video feedback saved');await p.unroute('**/api/task/feedback');assert.deepEqual(videoBodies[0],videoBodies[1]);
  await p.keyboard.press('Escape');await open();await p.locator('#taskFeedbackHistory video').waitFor();await play(p.locator('#taskFeedbackHistory video'));
  state=await read();feedback=state.records.filter(r=>r.source==='事项:'+id);assert.equal(feedback.length,3);const videoRecord=feedback.find(r=>r.attachments.some(a=>state.uploads.find(u=>u.id===a)?.mime==='video/mp4'));
  assert(videoRecord);assert.equal(videoRecord.note,'');assert.equal(videoRecord.transcript,'');assert.equal(state.tasks.find(t=>t.id===id).update.status,'已完成');assert.equal(asrAttempts,asrBeforeVideo);
  assert.match(await p.locator('#taskFeedbackHistory').innerText(),/内容尚未分析/);
  assert.equal(await p.locator('#taskDialog').evaluate(x=>x.scrollWidth>x.clientWidth),false);
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await fs.mkdir(process.env.TASK_MEDIA_UI_PROOF_DIR,{recursive:true});await p.locator('#taskFeedbackHistory video').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'task-video-'+width+'.png')})}
  if(process.env.TASK_MEDIA_UI_PROOF_DIR){await fs.mkdir(process.env.TASK_MEDIA_UI_PROOF_DIR,{recursive:true});await p.locator('#taskDialog').evaluate(x=>x.scrollTop=0);await p.screenshot({path:path.join(process.env.TASK_MEDIA_UI_PROOF_DIR,'task-feedback-'+width+'.png')})}
  await p.keyboard.press('Escape');await p.locator('nav [data-page="more"]').click();await p.locator('[data-capture]').first().click();assert.equal(await p.locator('#recordForm #recordAudio').count(),1);assert.equal(await p.locator('#pendingUploads audio').count(),0);assert.equal(await p.locator('#draftButton').isVisible(),true);await p.keyboard.press('Escape');assert.deepEqual(errors,[]);
  checks.push(width+': real recorder/upload/playback, separate transcript and ASR failure, Today/Calendar/Inbox entry, lost-reply and expired-CSRF retry, correction, state-only completion, completed-task media-only feedback, failed upload retry, microphone fallback and photo, login-expiry input retention, shared normal-record capture and layout; video-only upload retry, actual playback/seek, lost-reply retry and reopen without completion or ASR');await context.close();
 }
 console.log(JSON.stringify({passed:true,checks,syntheticOnly:true,realPhoneTested:false}));
}finally{await browser?.close();await server?.stop()}})().catch(e=>{console.error(e.stack||e);process.exitCode=1});
