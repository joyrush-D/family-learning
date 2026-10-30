// Real native acceptance of correcting a feedback sheet's chosen photos/PDFs without losing the typed note. Builds the Mac app from
// the committed sources into a fresh directory and serves Root's frozen fictional whole day (test_daily_list_whole_day.py
// serve_actual) through the real app server, behind a pass-through recorder that keeps each upload's returned attachment ID and
// each feedback post's request key. Every workbench step is a real mouse or key event on the built SwiftUI view (as in
// test_native_workspace.cjs). Limit: the macOS file chooser itself is not driven. Each "pick" step hands the next click on
// 选择照片或 PDF… a declared fictional file list (or a cancel) through the sheet's own picker-result handler, only in
// --smoke-test; this is not a system file chooser test. Then the server's own rows are read back: one feedback with exactly the
// kept attachment and the exact note despite an upload failure, a send failure and a lost reply; the removed file's uploaded
// original unchanged; a text-only feedback; the wrong note and its correction on the same task; nothing on the other child.
// Usage: node test_native_feedback_files.cjs --allow-visible-test-window   Optional: FAMILY_TEST_PYTHON, NATIVE_FEEDBACK_FILES_OUT (keeps build, logs, screenshots).
// A visible native test is opt-in. Ordinary test discovery or a local invocation must never open a window.
if (process.argv.includes('--help')) {
 console.log('Use on a separate test Mac: node test_native_feedback_files.cjs --allow-visible-test-window');process.exit(0);
}
if (!process.argv.includes('--allow-visible-test-window')) {
 console.error('This opens a test window. Use a separate test Mac and pass --allow-visible-test-window explicitly.');process.exit(2);
}
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),http=require('node:http');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const out=process.env.NATIVE_FEEDBACK_FILES_OUT||fs.mkdtempSync(path.join(os.tmpdir(),'grove-feedback-files-'));fs.mkdirSync(out,{recursive:true});
async function freePort(){const s=net.createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p}
// Pass-through only: requests and replies are unchanged; POST replies are kept for the read-back below.
function recorder(appPort){
 const seen=[];
 const server=http.createServer((req,res)=>{
  const chunks=[];req.on('data',d=>chunks.push(d));
  req.on('end',()=>{
   const body=Buffer.concat(chunks),route=req.url.split('?')[0];let sent=null;
   if(req.method==='POST'&&route==='/api/task/feedback'){try{sent=JSON.parse(body.toString())}catch{}}
   const up=http.request({host:'127.0.0.1',port:appPort,method:req.method,path:req.url,headers:req.headers},r=>{
    const back=[];r.on('data',d=>back.push(d));
    r.on('end',()=>{const reply=Buffer.concat(back);
     if(req.method==='POST'){let obj={};try{obj=JSON.parse(reply.toString())}catch{}
      seen.push({path:route,status:r.statusCode,attachment:(obj.attachment&&obj.attachment.id)||'',sent})}
     res.writeHead(r.statusCode,r.headers);res.end(reply)})});
   up.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end()});up.end(body)})});
 return {server,seen};
}
(async()=>{
 const app=execFileSync('sh',[path.join(__dirname,'packaging/macos/build.sh'),path.join(out,'build')],{encoding:'utf8'}).trim().split('\n').pop();
 const port=await freePort(),fixtureOrigin=`http://127.0.0.1:${port}`,rec=recorder(port);
 const env0={...process.env};for(const k of Object.keys(env0))if(k.startsWith('FAMILY_'))delete env0[k];
 const fixture=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-B','-c','import sys,test_daily_list_whole_day as w;w.serve_actual(int(sys.argv[1]))',String(port)],{cwd:__dirname,env:env0,stdio:['ignore','ignore','inherit']});
 const stopFixture=async()=>{rec.server.close();if(fixture.exitCode!==null)return;const d=once(fixture,'exit');fixture.kill('SIGINT');await Promise.race([d,delay(3000)]);if(fixture.exitCode===null)fixture.kill('SIGKILL')};
 try{
  rec.server.listen(0,'127.0.0.1');await once(rec.server,'listening');const origin=`http://127.0.0.1:${rec.server.address().port}`;
  for(let n=0;;n++){try{if((await fetch(fixtureOrigin+'/',{signal:AbortSignal.timeout(500)})).ok)break}catch{}if(n>400)throw Error('fixture not up');await delay(50)}
  const day=async(child)=>(await (await fetch(fixtureOrigin+'/api/day'+(child?'?child_id='+encodeURIComponent(child):''))).json());
  const first=await day(''),children=first.children;assert.ok(children.length>=2,'two fictional children');
  const views=await Promise.all(children.map(c=>day(c.id))),count=v=>v.groups.flatMap(g=>g.items).length;
  const mine=views.reduce((a,b)=>count(b)>count(a)?b:a),other=views.find(v=>v.child_id!==mine.child_id);
  const childIndex=children.findIndex(c=>c.id===mine.child_id);
  const item=mine.groups.flatMap(g=>g.items).find(i=>i.kind==='task'&&/跟读/.test(i.title))||mine.groups.flatMap(g=>g.items).find(i=>i.kind==='task');
  // Fictional attachments only: a 1×1 PNG and a one-line PDF.
  const files=path.join(out,'fictional-files');fs.mkdirSync(files,{recursive:true});
  const A=path.join(files,'虚构作答-第1页.png'),B=path.join(files,'虚构作答-第2页.pdf'),nA=path.basename(A),nB=path.basename(B);
  fs.writeFileSync(A,Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==','base64'));
  fs.writeFileSync(B,'%PDF-1.4\n% fictional answer page\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n');
  const NOTE='虚构反馈：第1页已检查，第2页选错了要去掉。',TEXT='虚构文字反馈：只写文字，不加照片。',WRONG='虚构第5题',FIX='虚构：已订正第5题。';
  const steps=[
   {name:'list',until:'list-summary',contains:'共',timeout:20},
   {name:'pick child',key:String(childIndex+1),modifiers:['command']},
   {name:'row',click:'row-'+item.id},{name:'detail',until:'detail-title',contains:item.title.slice(0,4)},
   // The parent types the note first, then chooses two files.
   {name:'feedback open',click:'feedback-new'},{name:'feedback sheet',until:'feedback-note'},
   {name:'focus note',click:'feedback-note'},{name:'type note',type:NOTE,into:'feedback-note'},
   {name:'declare two files',pick:[A,B]},{name:'choose files',click:'feedback-photo'},
   {name:'first file',until:'feedback-file-0',contains:nA},{name:'second file',until:'feedback-file-1',contains:nB},
   // A cancelled picker keeps what was chosen.
   {name:'declare cancel',pick:null},{name:'cancel picker',click:'feedback-photo'},
   {name:'kept first',until:'feedback-file-0',contains:nA},{name:'kept second',until:'feedback-file-1',contains:nB},
   // Remove the wrong one: the other file and the exact note stay.
   {name:'remove second',click:'feedback-file-remove-1'},{name:'second gone',until:'feedback-file-1',absent:true},
   {name:'first stays',until:'feedback-file-0',contains:nA},{name:'note stays',until:'feedback-note',contains:NOTE},
   {name:'one file wide',width:1440,native:'snapshot'},
   // Reselect it; Esc on the dirty sheet still keeps editing.
   {name:'declare reselect',pick:[B]},{name:'reselect',click:'feedback-photo'},{name:'reselected',until:'feedback-file-1',contains:nB},
   {name:'esc stays',key:'\u001b',code:53},{name:'still dirty',native:'dirty'},
   // A definitive upload failure keeps everything editable.
   {name:'upload not sent',faults:['fail_before_send']},{name:'save 1',click:'sheet-save'},
   {name:'upload failed',until:'sheet-status',contains:'没有保存'},{name:'note after upload failure',until:'feedback-note',contains:NOTE},
   {name:'files after upload failure',until:'feedback-file-1',contains:nB},
   // Both files upload, then the feedback itself is not sent: both are uploaded but not submitted.
   {name:'feedback not sent',faults:['none','none','fail_before_send']},{name:'save 2',click:'sheet-save'},
   {name:'save failed',until:'sheet-status',contains:'没有保存'},{name:'note after save failure',until:'feedback-note',contains:NOTE},
   // Remove the uploaded-but-unsubmitted one (its stored original is left alone), then lose the reply and retry by hand.
   {name:'remove uploaded',click:'feedback-file-remove-1'},{name:'uploaded gone',until:'feedback-file-1',absent:true},
   {name:'kept uploaded first',until:'feedback-file-0',contains:nA},
   {name:'narrow sheet',width:900,native:'snapshot'},
   {name:'lose reply',faults:['drop_reply']},{name:'save 3',click:'sheet-save'},
   {name:'unknown receipt',until:'sheet-status',contains:'不确定是否已保存'},{name:'unknown state',native:'state'},
   {name:'retry same request',click:'sheet-save'},{name:'saved',find_text:NOTE,timeout:15},{name:'saved state',native:'state'},
   // Ordinary text-only feedback: the empty selection says so plainly.
   {name:'text open',click:'feedback-new'},{name:'empty selection',until:'feedback-files-empty'},
   {name:'text focus',click:'feedback-note'},{name:'type text',type:TEXT,into:'feedback-note'},
   {name:'text snapshot',width:1440,native:'snapshot'},
   {name:'text save',click:'sheet-save'},{name:'text saved',find_text:TEXT,timeout:15},
   // The adjacent wrong-question and correction journey on the same task.
   {name:'wrong open',click_prefix:'wrong-new-'},{name:'wrong label',click:'wrong-label'},{name:'type wrong',type:WRONG},
   {name:'save wrong',click:'sheet-save'},{name:'wrong saved',find_text:WRONG,timeout:15},
   {name:'correct open',click_prefix:'wrong-correct-'},{name:'correct note',click:'correction-note'},{name:'type correction',type:FIX},
   {name:'save correction',click:'sheet-save'},{name:'corrected',find_text:'已订正',timeout:15},
   {name:'reopen',native:'reopen'},{name:'reopened feedback',find_text:NOTE,timeout:15},{name:'reopened text',find_text:TEXT,timeout:15},
   {name:'reopened state',native:'state'},{name:'reopened snapshot',width:1440,native:'snapshot'}];
  const stepsFile=path.join(out,'native-steps.json');fs.writeFileSync(stepsFile,JSON.stringify(steps));
  const shots=path.join(out,'shots');fs.mkdirSync(shots,{recursive:true});
  const support=fs.mkdtempSync(path.join(os.tmpdir(),'grove-feedback-files-support-'));
  const env={...env0,FAMILY_DESKTOP_SUPPORT_DIR:support,FAMILY_DESKTOP_TEST_ORIGIN:origin,FAMILY_DESKTOP_TEST_SETUP_INPUTS:JSON.stringify([origin]),
   FAMILY_DESKTOP_TEST_SURFACE:'native',FAMILY_DESKTOP_TEST_NATIVE_STEPS:stepsFile,FAMILY_DESKTOP_TEST_SNAPSHOT_DIR:shots,FAMILY_DESKTOP_SMOKE_HOLD:'1'};
  const proc=spawn(path.join(app,'Contents/MacOS/YiqiChengzhang'),['--smoke-test'],{env,stdio:['ignore','pipe','pipe']});
  let text='',stoppedForFailure=false;
  // The driver has already stopped and recorded a failed step. Reap only this runner's fictional App,
  // including a still-open draft sheet, instead of waiting five/seven minutes for the watchdog.
  function stopFinishedFailedRun(){
   if(stoppedForFailure)return;
   for(const line of text.split('\n')){
    let state;try{state=JSON.parse(line)}catch{continue}
    if(state.state==='native_loaded'&&state.steps.some(s=>s.result?.ok===false)){
     stoppedForFailure=true;if(proc.exitCode===null)proc.kill('SIGTERM');return;
    }
   }
  }
  proc.stdout.on('data',d=>{text+=d;fs.appendFileSync(path.join(out,'native.jsonl'),d);stopFinishedFailedRun()});proc.stderr.on('data',d=>fs.appendFileSync(path.join(out,'native.stderr.log'),d));
  const done=once(proc,'exit');const killer=setTimeout(()=>proc.kill('SIGKILL'),300000);const [code]=await done;clearTimeout(killer);
  const lines=text.split('\n').filter(Boolean).map(l=>{try{return JSON.parse(l)}catch{return {raw:l}}});
  fs.writeFileSync(path.join(out,'recorded-posts.json'),JSON.stringify(rec.seen,null,1));
  const final=lines.find(l=>l.state==='native_loaded');
  assert.ok(final,'native run finished: '+lines.slice(-3).map(l=>JSON.stringify(l).slice(0,400)).join('\n'));
  const failed=final.steps.filter(s=>s.result.ok===false);assert.deepEqual(failed,[],'native steps');
  assert.equal(code,0,'the successful native test App must exit normally');
  const r=Object.fromEntries(final.steps.map(s=>[s.name,s.result]));
  for(const k of ['note stays','note after upload failure','note after save failure'])assert.equal(r[k].text,NOTE,k+': exactly the typed note');
  assert.equal(r['first stays'].text,nA);assert.equal(r['kept uploaded first'].text,nA);
  assert.equal(r['still dirty'].dirty,true,'Esc on a dirty sheet keeps editing');
  assert.ok(r['unknown state'].sheet.startsWith('feedback-')&&r['unknown state'].dirty===true,'an unknown receipt keeps the sheet and its input');
  assert.equal(r['saved state'].sheet,'','saving closes the sheet');assert.equal(r['reopened state'].selection,item.id,'reopened on the same task');
  // Each file uploaded once; only the kept one was submitted, twice with one request key (lost reply, then the manual retry).
  const uploads=rec.seen.filter(s=>s.path==='/api/upload');
  assert.equal(uploads.length,2,'each chosen file uploaded once: '+JSON.stringify(uploads));const [idA,idB]=uploads.map(u=>u.attachment);
  assert.ok(idA&&idB&&idA!==idB&&uploads.every(u=>u.status===200));
  const posts=rec.seen.filter(s=>s.path==='/api/task/feedback'&&s.sent&&s.sent.note===NOTE);
  assert.equal(posts.length,2,'the lost reply and one manual retry reached the server: '+JSON.stringify(posts));
  assert.ok(posts.every(p=>p.status===200&&p.sent.request_key===posts[0].sent.request_key),'the same request key');
  assert.ok(posts.every(p=>JSON.stringify(p.sent.attachments)===JSON.stringify([idA])),'only the kept file was submitted');
  // The server's own rows, reopened under the same child and task.
  const after=await day(mine.child_id),row=after.groups.flatMap(g=>g.items).concat(after.closed.flatMap(g=>g.items)).find(i=>i.id===item.id);
  const saved=row.records.filter(x=>x.note===NOTE);assert.equal(saved.length,1,'one feedback despite two failures and a lost reply');
  assert.deepEqual(saved[0].attachments,[idA],'exactly the intended attachment');
  const plain=row.records.filter(x=>x.note===TEXT);assert.equal(plain.length,1);assert.deepEqual(plain[0].attachments,[]);
  assert.equal(row.wrong.length,1);assert.ok(row.wrong[0].title.includes(WRONG));assert.equal(row.wrong[0].state,'已订正');
  assert.equal(row.closed,false,'words and wrong notes never mark the task done');
  // Removing a file from the sheet never deletes or changes a stored original.
  for(const [id,file] of [[idA,A],[idB,B]]){const got=await fetch(fixtureOrigin+'/upload/'+id);assert.equal(got.status,200,'stored original '+id);
   assert.ok(Buffer.from(await got.arrayBuffer()).equals(fs.readFileSync(file)),'stored original unchanged: '+path.basename(file))}
  const theirs=JSON.stringify(await day(other.child_id));assert.ok(!theirs.includes(NOTE)&&!theirs.includes(TEXT)&&!theirs.includes(WRONG),'nothing reached the other child');
  assert.equal(final.isolation.support_is_default,false);
  console.log(JSON.stringify({ok:true,app_exit:code,steps:final.steps.length,out,shots:fs.readdirSync(shots),picker:'declared fictional files through the sheet picker handler; system file chooser not driven'}));
 }finally{await stopFixture()}
})().catch(e=>{console.error(e);process.exit(1)});
