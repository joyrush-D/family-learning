// Opt-in real native regression for showing the Mac workbench again in the same window: the in-process reload that stands in for
// reopening the App (native 'reopen') and returning from the web tools with ⌘0. After each, two real posted mouse clicks on two
// different list rows that are not the current selection must each select exactly that row, so a first-click-only failure is
// told apart from a persistent one. Builds the app from the committed sources, serves Root's frozen fictional whole day
// (test_daily_list_whole_day.serve_actual, imported, not run as a script) and runs the app in --smoke-test with its own support
// directory. Nothing calls the store's select or sets a table selection: each row step posts a real down/up at the row's middle and
// reads the store's selection back; the state step before each click proves the target was not already selected.
// It opens a visible test window: run it only on a separate test Mac, never on a Mac a parent is using.
// Usage: node test_native_host_reentry.cjs --allow-visible-test-window   Optional: FAMILY_TEST_PYTHON, NATIVE_HOST_REENTRY_OUT.
if(process.argv.includes('--help')){console.log('On a separate test Mac: node test_native_host_reentry.cjs --allow-visible-test-window');process.exit(0)}
if(!process.argv.includes('--allow-visible-test-window')){console.error('Visible test is opt-in; use a separate test Mac.');process.exit(2)}
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const out=process.env.NATIVE_HOST_REENTRY_OUT||fs.mkdtempSync(path.join(os.tmpdir(),'grove-reentry-'));fs.mkdirSync(out,{recursive:true});
async function freePort(){const s=net.createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p}
(async()=>{
 const app=execFileSync('sh',[path.join(__dirname,'packaging/macos/build.sh'),path.join(out,'build')],{encoding:'utf8'}).trim().split('\n').pop();
 const port=await freePort(),origin=`http://127.0.0.1:${port}`;
 const env0={...process.env};for(const k of Object.keys(env0))if(k.startsWith('FAMILY_'))delete env0[k];
 const fixture=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-B','-c','import sys,test_daily_list_whole_day as w;w.serve_actual(int(sys.argv[1]))',String(port)],{cwd:__dirname,env:env0,stdio:['ignore','ignore','inherit']});
 const stopFixture=async()=>{if(fixture.exitCode!==null)return;const d=once(fixture,'exit');fixture.kill('SIGINT');await Promise.race([d,delay(3000)]);if(fixture.exitCode===null)fixture.kill('SIGKILL')};
 try{
  for(let n=0;;n++){try{if((await fetch(origin+'/',{signal:AbortSignal.timeout(500)})).ok)break}catch{}if(n>400)throw Error('fixture not up');await delay(50)}
  const day=async c=>(await (await fetch(origin+'/api/day'+(c?'?child_id='+encodeURIComponent(c):''))).json());
  const children=(await day('')).children;assert.ok(children.length>=2,'two fictional children');
  const views=await Promise.all(children.map(c=>day(c.id))),count=v=>v.groups.flatMap(g=>g.items).length;
  const mine=views.reduce((a,b)=>count(b)>count(a)?b:a),childIndex=children.findIndex(c=>c.id===mine.child_id),all=mine.groups.flatMap(g=>g.items);
  const A=all.find(i=>i.kind==='task'&&/跟读/.test(i.title))||all.find(i=>i.kind==='task');
  const B=all.find(i=>i.id!==A.id&&(i.facts||[]).some(f=>f.state==='next_morning'))||all.find(i=>i.id!==A.id&&i.kind==='task');
  const rest=[...all.filter(i=>i.kind==='task'),...all.filter(i=>i.kind!=='task')].filter(i=>i.id!==A.id&&i.id!==B.id);
  assert.ok(rest.length>=3,'the fictional day has at least five list rows');const [C,D,E]=rest;
  const click=(name,t)=>({name,click:'row-'+t.id,required:false}),state=name=>({name,native:'state'}),cmd=(name,k)=>({name,key:k,modifiers:['command']});
  const steps=[
   {name:'list',until:'list-summary',contains:'共',timeout:20},cmd('pick child',String(childIndex+1)),{name:'picked',until:'list-summary',contains:'共',timeout:10},
   // The click helper itself works before any re-entry.
   click('before swap A',A),click('before swap B',B),
   // In-process reload (as if the App were reopened): the store is thrown away and the same child/day reread from the backend.
   {name:'reload',native:'reopen'},{name:'reloaded list',until:'list-summary',contains:'共',timeout:15,required:false},
   state('before reload 1'),click('reload click 1',A),state('before reload 2'),click('reload click 2',C),
   // The real web tools entry (⌘E) and the real way back to the workbench (⌘0).
   cmd('web tools','e'),{name:'web load',find_text:'\u0000never shown',timeout:4,required:false},state('web state'),
   cmd('workbench','0'),{name:'returned list',until:'list-summary',contains:'共',timeout:15,required:false},
   state('before return 1'),click('return click 1',D),state('before return 2'),click('return click 2',E),state('final'),
   {name:'final shot',native:'snapshot',required:false}];
  fs.writeFileSync(path.join(out,'steps.json'),JSON.stringify(steps,null,1));const shots=path.join(out,'shots');fs.mkdirSync(shots,{recursive:true});
  const env={...env0,FAMILY_DESKTOP_SUPPORT_DIR:fs.mkdtempSync(path.join(os.tmpdir(),'grove-reentry-support-')),FAMILY_DESKTOP_TEST_ORIGIN:origin,FAMILY_DESKTOP_TEST_SETUP_INPUTS:JSON.stringify([origin]),
   FAMILY_DESKTOP_TEST_SURFACE:'native',FAMILY_DESKTOP_TEST_NATIVE_STEPS:path.join(out,'steps.json'),FAMILY_DESKTOP_TEST_SNAPSHOT_DIR:shots,FAMILY_DESKTOP_SMOKE_HOLD:'1'};
  const p=spawn(path.join(app,'Contents/MacOS/YiqiChengzhang'),['--smoke-test'],{env,stdio:['ignore','pipe','pipe']});let text='';
  p.stdout.on('data',d=>{text+=d;fs.appendFileSync(path.join(out,'native.jsonl'),d)});p.stderr.on('data',d=>fs.appendFileSync(path.join(out,'native.stderr.log'),d));
  const kill=setTimeout(()=>p.kill('SIGTERM'),150000);const [code]=await once(p,'exit');clearTimeout(kill);
  const fin=text.split('\n').filter(Boolean).map(l=>{try{return JSON.parse(l)}catch{return {}}}).find(l=>l.state==='native_loaded');
  assert.ok(fin,'the app reported its native steps (exit '+code+')');
  const r=Object.fromEntries(fin.steps.map(s=>[s.name,s.result])),bad=[];
  const pairs=[['before swap A','',A],['before swap B','',B],['reload click 1','before reload 1',A],['reload click 2','before reload 2',C],['return click 1','before return 1',D],['return click 2','before return 2',E]];
  const summary=pairs.map(([n,before,t])=>({click:n,target:t.id,selected_before:before?(r[before]||{}).selection:null,ok:(r[n]||{}).ok===true&&(r[n]||{}).selected===t.id,error:(r[n]||{}).error||''}));
  fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({app_exit:code,summary,reload:r['reload'],web:r['web state'],returned:r['before return 1']},null,1));
  for(const s of summary)console.log(s.click.padEnd(16),s.ok?'selected':'NOT SELECTED',s.error);
  if(!(r['picked']||{}).ok)bad.push('the list did not load for the fictional child');
  for(const s of summary){
   if(s.selected_before!==null&&s.selected_before===s.target)bad.push(s.click+': target was already selected (not a real test)');
   if(!s.ok)bad.push(s.click+': a real click on an unselected row did not select it ('+s.error+')');
  }
  if(!((r['reload']||{}).ok&&(r['reload']||{}).selection===B.id))bad.push('reload did not reread the same day with the kept selection');
  if(!((r['web state']||{}).surface==='web'&&(r['web state']||{}).web_visible===true))bad.push('⌘E did not show the web tools');
  if(!((r['before return 1']||{}).surface==='native'&&(r['before return 1']||{}).native_visible===true&&(r['before return 1']||{}).child===mine.child_id))bad.push('⌘0 did not return to the same child on the native workbench');
  if((r['final']||{}).child!==mine.child_id)bad.push('the child changed');
  assert.deepEqual(bad,[],bad.join('\n'));
  assert.equal(code,0,'app exit');
  console.log('native host re-entry: real clicks select unselected rows after reload and after web tools → workbench');
 }finally{await stopFixture()}
})().catch(e=>{console.error(e);process.exit(1)});
