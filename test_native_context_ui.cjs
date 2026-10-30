// Visible native context-safety acceptance. Run only on a separate test Mac, with fictional data.
// The actual WorkspaceStore, SwiftUI controls and mouse/key driver are used; no selection or store action is set here.
// The fixture is the headless context test's in-process HTTP backend. It accepts no POSTs.
if (process.argv.includes('--help')) { console.log('On a separate test Mac: node test_native_context_ui.cjs --allow-visible-test-window'); process.exit(0); }
if (!process.argv.includes('--allow-visible-test-window')) { console.error('Visible test is opt-in; use a separate test Mac.'); process.exit(2); }
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const out=process.env.NATIVE_CONTEXT_OUT||fs.mkdtempSync(path.join(os.tmpdir(),'grove-context-'));fs.mkdirSync(out,{recursive:true});
(async()=>{
 const app=process.env.ROOT_NATIVE_QA_APP||execFileSync('sh',[path.join(__dirname,'packaging/macos/build.sh'),path.join(out,'build')],{encoding:'utf8'}).trim().split('\n').pop();
 const sock=net.createServer();sock.listen(0,'127.0.0.1');await once(sock,'listening');const port=sock.address().port;await new Promise(r=>sock.close(r));
 const origin=`http://127.0.0.1:${port}`,env0={...process.env};for(const k of Object.keys(env0))if(k.startsWith('FAMILY_'))delete env0[k];
 const fixtureCode=`import sys,test_native_context as f
class Fixture(f.Backend):
 def do_GET(self):
  if self.path in ('/__fixture/fail','/__fixture/ok'):
   f.Backend.state['fail']=int(self.path.endswith('/fail'))
   return self.reply(200,f.Backend.state)
  if self.path=='/': return self.reply(200,{'fixture':True,'app.bundle.js':'fictional identity marker'})
  return super().do_GET()
f.ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1])),Fixture).serve_forever()`;
 const fixture=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-B','-c',fixtureCode,String(port)],{cwd:__dirname,env:env0,stdio:['ignore','ignore','inherit']});
 let proc;
 try {
  for(let n=0;;n++){try{if((await fetch(origin+'/',{signal:AbortSignal.timeout(500)})).ok)break}catch{}if(n>200)throw Error('fictional backend not ready');await delay(50)}
  const steps=[];
  for(const width of [900,1440]){
   const a=(name,step)=>steps.push({name:width+' '+name,...step});
   a('reset server',{native:'fixture_get',path:'/__fixture/ok'});a('child A',{key:'1',modifiers:['command']});a('today',{key:'t',modifiers:['command']});
   a('initial list',{find_text:'虚构数学作业甲',timeout:12});a('initial row',{click:'row-FICTION-A1'});a('initial detail',{until:'detail-title',contains:'虚构数学作业甲'});
   a('width',{width,native:'snapshot'});a('fail reads',{native:'fixture_get',path:'/__fixture/fail'});
   a('same context reload',{key:'r',modifiers:['command']});a('same context error',{until:'load-error',contains:'虚构后台暂时读不到'});
   a('same context detail kept',{until:'detail-title',contains:'虚构数学作业甲'});
   a('child B failure',{key:'2',modifiers:['command']});a('child B error',{until:'load-error',contains:'虚构后台暂时读不到'});
   a('no A under B',{find_text:'虚构数学作业甲',absent:true,timeout:2});a('no old detail',{until:'detail-title',absent:true});
   a('oral shortcut disabled',{key:'n',modifiers:['command']});a('no wrong oral sheet',{native:'state'});a('child B failed screen',{native:'snapshot'});
   a('return A while failing',{key:'1',modifiers:['command']});a('return known A',{find_text:'虚构数学作业甲',timeout:12});
   a('next day failure',{key:']',modifiers:['command']});a('requested date',{until:'day-title',contains:'2026-11-05'});
   a('next day error',{until:'load-error',contains:'虚构后台暂时读不到'});a('no previous day items',{find_text:'虚构数学作业甲',absent:true,timeout:2});
   a('no old day detail',{until:'detail-title',absent:true});a('failed day screen',{native:'snapshot'});
   a('restore reads',{native:'fixture_get',path:'/__fixture/ok'});a('retry',{click:'load-retry'});
   a('new day correct list',{find_text:'虚构数学作业甲·后一天',timeout:12});a('new day row',{click:'row-FICTION-A2'});a('new day correct detail',{until:'detail-title',contains:'虚构数学作业甲·后一天'});
   a('child B success',{key:'2',modifiers:['command']});a('B correct list',{find_text:'虚构语文作业乙·后一天',timeout:12});
   a('A absent after B success',{find_text:'虚构数学作业甲',absent:true,timeout:2});a('B row',{click:'row-FICTION-B3'});
   a('B correct detail',{until:'detail-title',contains:'虚构语文作业乙·后一天'});a('recovered screen',{native:'snapshot'});
  }
  const stepFile=path.join(out,'steps.json'),shots=path.join(out,'shots');fs.writeFileSync(stepFile,JSON.stringify(steps));fs.mkdirSync(shots,{recursive:true});
  const env={...env0,FAMILY_DESKTOP_SUPPORT_DIR:fs.mkdtempSync(path.join(os.tmpdir(),'grove-context-support-')),FAMILY_DESKTOP_TEST_ORIGIN:origin,
   FAMILY_DESKTOP_TEST_SETUP_INPUTS:JSON.stringify([origin]),FAMILY_DESKTOP_TEST_SURFACE:'native',FAMILY_DESKTOP_TEST_NATIVE_STEPS:stepFile,FAMILY_DESKTOP_TEST_SNAPSHOT_DIR:shots,FAMILY_DESKTOP_SMOKE_HOLD:'1'};
  proc=spawn(path.join(app,'Contents/MacOS/YiqiChengzhang'),['--smoke-test'],{env,stdio:['ignore','pipe','pipe']});let text='',terminated=false;
  proc.stdout.on('data',d=>{text+=d;fs.appendFileSync(path.join(out,'native.jsonl'),d);for(const line of text.split('\n')){try{const x=JSON.parse(line);if(!terminated&&x.state==='native_loaded'&&x.steps.some(s=>s.result.ok===false)){terminated=true;proc.kill('SIGTERM')}}catch{}}});
  proc.stderr.on('data',d=>fs.appendFileSync(path.join(out,'native.stderr.log'),d));
  const done=once(proc,'exit'),timer=setTimeout(()=>proc.kill('SIGKILL'),180000),[code]=await done;clearTimeout(timer);
  const final=text.split('\n').flatMap(s=>{try{return [JSON.parse(s)]}catch{return []}}).find(x=>x.state==='native_loaded');assert.ok(final,'driver completed');
  assert.deepEqual(final.steps.filter(s=>s.result.ok===false),[],'all real controls and visible assertions pass');assert.equal(final.steps.length,steps.length);assert.equal(code,0,'App exits normally');
  for(const width of [900,1440]) {const s=final.steps.find(s=>s.name===width+' no wrong oral sheet').result;assert.equal(s.child,'child-2');assert.equal(s.sheet,'');assert.equal(s.summary,'');assert.ok(s.error);}
  const counters=await (await fetch(origin+'/control')).json();assert.equal(counters.posts,0,'read-failure acceptance never writes a business record');
  assert.equal(final.isolation.support_is_default,false);const result={ok:true,app_exit:code,steps:steps.length,posts:0,all_fictional:true,widths:[900,1440],shots:fs.readdirSync(shots)};
  fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 } finally {
  if(proc&&proc.exitCode===null)proc.kill('SIGTERM');if(fixture.exitCode===null){const d=once(fixture,'exit');fixture.kill('SIGINT');await Promise.race([d,delay(2000)]);if(fixture.exitCode===null)fixture.kill('SIGKILL');}
 }
})().catch(e=>{console.error(e);process.exit(1)});
