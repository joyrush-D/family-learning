// 原图框题（wrong-notebook image-crop.ts）360 触屏/1440 鼠标验收。Disposable synthetic demo only; no model, printer or family data.
// Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL (default chrome), FAMILY_TEST_PYTHON and WRONG_REGIONS_UI_PROOF_DIR.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const {randomUUID,createHash}=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=__dirname,out=process.env.WRONG_REGIONS_UI_PROOF_DIR||fs.mkdtempSync(path.join(require('node:os').tmpdir(),'synthetic-wrong-regions-'));fs.mkdirSync(out,{recursive:true});
async function until(f,label){for(let n=0;n<180;n++){if(await f())return;await delay(50)}throw Error('Timed out: '+label)}
let proc,browser,last,report={source:'committed-candidate-acceptance',product_model_calls:0,production_access:false,widths:[]};
(async()=>{try{
 const sock=net.createServer();sock.listen(0,'127.0.0.1');await once(sock,'listening');const port=sock.address().port;await new Promise(r=>sock.close(r));
 const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['demo.py','--port',String(port)],{cwd:root,env,stdio:['ignore','pipe','pipe']});
 let logs='';proc.stdout.on('data',b=>logs+=b);proc.stderr.on('data',b=>logs+=b);
 const base=`http://127.0.0.1:${port}/`,read=async()=>{const r=await fetch(base+'api/state');assert(r.ok);return r.json()};
 await until(async()=>{try{return(await fetch(base)).ok}catch{return false}},'synthetic demo listening');
 browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true});
 for(const width of [360,1440]){
  let state=await read(),child=state.children[0].name;
  const post=async(p,body)=>{const r=await fetch(base+p,{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':state.token},body:JSON.stringify(body)});const v=await r.json();assert.equal(r.status,200,JSON.stringify(v));return v};
  const task=(await post('api/task/new',{request_key:randomUUID(),child,title:'虚构数学框题 '+width,category:'homework',box:'inbox',due:state.today,action:'核对第2题原作答'})).task;
  const p=await browser.newPage({viewport:{width,height:900},hasTouch:width===360});last=p;const errors=[];p.on('pageerror',e=>errors.push(e.message));
  const mod=fs.readFileSync(path.join(root,'vendor/wrong-notebook/image-crop.js'),'utf8');
  report.upstream_js_sha256=createHash('sha256').update(mod).digest('hex');
  const names=['toSafeImageSrc','regionFromPoints','cropImageRegions'];let instrumented=mod;
  for(const name of names)instrumented=instrumented.replace(new RegExp('(export (?:async )?function '+name+'\\([^)]*\\)[^{]*\\{)'),`$1 globalThis.__rootCropCalls??={};globalThis.__rootCropCalls['${name}']=(globalThis.__rootCropCalls['${name}']||0)+1;`);
  await p.route('**/vendor/wrong-notebook/image-crop.js',r=>r.fulfill({contentType:'text/javascript',body:instrumented}));
  await p.goto(base);await p.locator(`[data-task="${task.id}"]`).first().click();
  const photo=Buffer.from((await p.evaluate(()=>{const c=document.createElement('canvas');c.width=600;c.height=300;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,600,300);g.fillStyle='#111';g.font='25px sans-serif';g.fillText('SYNTHETIC / NOT FAMILY DATA',20,40);g.fillText('1. 3+4=7',20,100);g.fillText('2. 42-17=35',20,220);return c.toDataURL('image/png')})).split(',')[1],'base64');
  await p.locator('#taskForm [name=note]').fill('虚构原作答：第2题35');await p.locator('#cameraInput').setInputFiles({name:'synthetic-frame-'+width+'.png',mimeType:'image/png',buffer:photo});await p.locator('#pendingUploads img').waitFor();
  await p.locator('#saveTaskFeedback').click();await until(async()=>/反馈已保存/.test(await p.locator('#taskFeedbackStatus').innerText()),'answer saved');
  state=await read();const original=state.records.find(r=>r.source==='事项:'+task.id),originalUpload=original.attachments[0],uploadCount=state.uploads.length;
  assert.deepEqual(Buffer.from(await(await fetch(base+'upload/'+originalUpload)).arrayBuffer()),photo);
  let form=p.locator(`[data-task-wrong-form="${original.id}"]`);await form.locator(':scope>summary').click();
  await form.locator('[data-task-wrong-frame-open]').click();await form.locator('[data-task-wrong-stage] img').waitFor();
  const img=form.locator('[data-task-wrong-stage] img');await img.scrollIntoViewIfNeeded();const b=await img.boundingBox();assert(b&&b.width>0);
  const x1=b.x+b.width*.1,y1=b.y+b.height*.55,x2=b.x+b.width*.85,y2=b.y+b.height*.9;
  if(width===360){const c=await p.context().newCDPSession(p);await c.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x1,y:y1}]});await c.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x2,y:y2}]});await c.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await c.detach()}
  else {await p.mouse.move(x1,y1);await p.mouse.down();await p.mouse.move(x2,y2,{steps:5});await p.mouse.up()}
  await form.locator('[data-task-wrong-crop] img').waitFor();
  const region=await form.evaluate(el=>el.taskWrongRegion);assert(region&&region.width>0&&region.height>0);
  await form.locator('[data-wrong-field=label]').fill('第2题');await form.locator('[data-wrong-field=answer]').fill('35');await form.locator('[data-wrong-field=correction]').fill('25');
  await p.screenshot({path:path.join(out,`frame-${width}.png`),fullPage:true});
  const before=await read(),bodies=[];let n=0;
  await p.route('**/api/wrong/save',async r=>{bodies.push(r.request().postDataJSON());n++;if(n===1)return r.fulfill({status:503,json:{error:'虚构未写入'}});const res=await r.fetch();if(res.status()!==200){report.server_rejection={status:res.status(),body:await res.text()};return r.fulfill({response:res})}if(n===2)return r.abort('failed');return r.fulfill({response:res})});
  await form.locator('[data-task-wrong-save]').click();await until(async()=>/结果尚未核对/.test(await form.locator('[data-task-wrong-status]').innerText()),'failure keeps draft');assert.equal((await read()).records.length,before.records.length);
  await form.locator('[data-task-wrong-frame-open]').click();assert.match(await form.locator('[data-task-wrong-frame-status]').innerText(),/已锁定/);await form.locator('[data-task-wrong-frame-clear]').click();assert.deepEqual(await form.evaluate(el=>el.taskWrongRegion),region,'unknown receipt cannot change or clear the frame');assert(await form.locator('[data-wrong-field=answer]').isDisabled());
  await form.locator('[data-task-wrong-save]').click();await until(async()=>/结果尚未核对/.test(await form.locator('[data-task-wrong-status]').innerText()),'lost receipt keeps number');assert.equal((await read()).records.length,before.records.length+1);
  await form.locator('[data-task-wrong-save]').click();await until(async()=>/错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()),'retry saved one');await p.unroute('**/api/wrong/save');
  assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[1],bodies[2]);
  state=await read();const wrong=state.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===task.id);assert.equal(wrong.length,1);assert(wrong[0].wrong_region.current);assert.equal(state.uploads.length,uploadCount);assert.deepEqual(wrong[0].attachments,[originalUpload]);assert.equal(wrong[0].related_record_id,original.id);
  assert.deepEqual(Buffer.from(await(await fetch(base+'upload/'+originalUpload)).arrayBuffer()),photo);
  const calls=await p.evaluate(()=>globalThis.__rootCropCalls);for(const name of names)assert(calls[name]>0,'actual original module invoked: '+name);
  // Reload uses the unmodified vendored module and rebuilds the crop from the stored original.
  await p.unroute('**/vendor/wrong-notebook/image-crop.js');await p.reload();await p.locator(`[data-task="${task.id}"]`).first().click();await p.locator(`[data-wrong-region-crop="${wrong[0].id}"] img`).waitFor();
  assert(!await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),'no page horizontal overflow');
  await p.screenshot({path:path.join(out,`reopen-${width}.png`),fullPage:true});
  assert.deepEqual(errors,[]);report.widths.push({width,touch:width===360,region,upstream_calls:calls,one_saved_wrong:true,uploads_unchanged:true,original_bytes_unchanged:true,three_identical_attempts:true,reopen_from_unmodified_module:true});await p.close();
 }
 report.pass=true;console.log(JSON.stringify(report));
 }catch(e){report.pass=false;report.error=e.stack;if(last&&!last.isClosed())await last.screenshot({path:path.join(out,'FAILURE.png'),fullPage:true}).catch(()=>{});throw e}
 finally{fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(report,null,2));await browser?.close();if(proc&&proc.exitCode===null){proc.kill('SIGINT');await Promise.race([once(proc,'exit'),delay(1500)]);if(proc.exitCode===null)proc.kill('SIGKILL')}}
})().catch(e=>{console.error(e);process.exitCode=1});
