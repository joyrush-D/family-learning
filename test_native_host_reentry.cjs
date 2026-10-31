// Opt-in real native regression for showing the Mac workbench again in the same window: the in-process reload that stands in for
// reopening the App (native 'reopen') and returning from the web tools with ⌘0 and with the native “← 返回清单” bar above the web page
// (a real posted click; the page's own unsaved check keeps the page unless discard is chosen). After each, two real posted mouse clicks on two
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
  // The bottom row: with full standards the rows are tall, so the system list has not built it until it is scrolled to.
  const Z=[...all].reverse().find(i=>i.id!==A.id);
  const click=(name,t)=>({name,click:'row-'+t.id,required:false}),state=name=>({name,native:'state'}),cmd=(name,k)=>({name,key:k,modifiers:['command']});
  const steps=[
   {name:'list',until:'list-summary',contains:'共',timeout:20},cmd('pick child',String(childIndex+1)),{name:'picked',until:'list-summary',contains:'共',timeout:10},
   // The click helper itself works before any re-entry.
   click('before swap A',A),click('before swap B',B),
   // In-process reload (as if the App were reopened): the store is thrown away and the same child/day reread from the backend.
   // A window restored from an old small saved frame (set like a restored frame, below the minimum): reopening the workbench widens it.
   {name:'small saved frame',native:'saved_frame',frame_width:360,required:false},
   {name:'reload',native:'reopen'},{name:'reloaded list',until:'list-summary',contains:'共',timeout:15,required:false},
   state('before reload 1'),click('reload click 1',A),state('before reload 2'),click('reload click 2',C),
   // The real web tools entry (⌘E) and the real way back to the workbench (⌘0).
   cmd('web tools','e'),{name:'web load',find_text:'\u0000never shown',timeout:4,required:false},state('web state'),
   // The web tools' own snapshot (the -window.png keeps the native back bar), then the web tools at the 360 phone width; ⌘0 must widen back.
   {name:'web shot',native:'snapshot',required:false},{name:'web 360 shot',width:360,native:'snapshot',required:false},state('web 360'),
   cmd('workbench','0'),{name:'returned list',until:'list-summary',contains:'共',timeout:15,required:false},
   state('before return 1'),click('return click 1',D),state('before return 2'),click('return click 2',E),state('final'),
   // The native “← 返回清单” bar outside the web content: a real posted click. A page that reports unsaved input (its own beforeunload
   // protocol, the same check ⌘0 uses) is kept by default; only an explicit discard returns. The same child, day and selected item come back.
   cmd('web tools 2','e'),{name:'web load 2',find_text:'\u0000never shown',timeout:4,required:false},state('web state 2'),
   {name:'hold-web',find_text:'\u0000never shown',timeout:4,required:false},
   {name:'web draft',web_step:{js:"window.addEventListener('beforeunload',e=>{e.preventDefault();e.returnValue=''});return {ok:true}"},required:false},
   {name:'back kept',click:'web-back',required:false},{name:'kept wait',find_text:'\u0000never shown',timeout:1.5,required:false},state('after back kept'),
   {name:'discard',native:'discard_next',required:false},{name:'back discard',click:'web-back',required:false},
   {name:'back list',until:'list-summary',contains:'共',timeout:15,required:false},state('after back'),
   click('after back click',A),state('after back select'),
   // Visual evidence at the two acceptance widths (the window's own snapshot; a real window capture is taken outside during each hold).
   {name:'shot-1440',native:'snapshot',width:1440,height:900,required:false},{name:'hold-1440',find_text:'\u0000never shown',timeout:6,required:false},
   {name:'shot-900',native:'snapshot',width:900,height:860,required:false},{name:'hold-900',find_text:'\u0000never shown',timeout:6,required:false},
   {name:'feedback open',click:'feedback-new',required:false},state('feedback sheet'),
   // Nothing typed: Esc closes the sheet without a prompt or a write, so the app can quit normally at the end.
   {name:'feedback close',key:'\u001b',code:53,required:false},{name:'close wait',find_text:'\u0000never shown',timeout:1,required:false},state('sheet closed'),
   state('before bottom'),click('bottom row',Z),
   {name:'final shot',native:'snapshot',required:false}];
  fs.writeFileSync(path.join(out,'steps.json'),JSON.stringify(steps,null,1));const shots=path.join(out,'shots');fs.mkdirSync(shots,{recursive:true});
  const env={...env0,FAMILY_DESKTOP_SUPPORT_DIR:fs.mkdtempSync(path.join(os.tmpdir(),'grove-reentry-support-')),FAMILY_DESKTOP_TEST_ORIGIN:origin,FAMILY_DESKTOP_TEST_SETUP_INPUTS:JSON.stringify([origin]),
   FAMILY_DESKTOP_TEST_SURFACE:'native',FAMILY_DESKTOP_TEST_NATIVE_STEPS:path.join(out,'steps.json'),FAMILY_DESKTOP_TEST_SNAPSHOT_DIR:shots,FAMILY_DESKTOP_SMOKE_HOLD:'1'};
  const p=spawn(path.join(app,'Contents/MacOS/YiqiChengzhang'),['--smoke-test'],{env,stdio:['ignore','pipe','pipe']});let text='';
  p.stdout.on('data',d=>{text+=d;fs.appendFileSync(path.join(out,'native.jsonl'),d)});p.stderr.on('data',d=>fs.appendFileSync(path.join(out,'native.stderr.log'),d));
  const kill=setTimeout(()=>p.kill('SIGTERM'),240000);const [code]=await once(p,'exit');clearTimeout(kill);
  const fin=text.split('\n').filter(Boolean).map(l=>{try{return JSON.parse(l)}catch{return {}}}).find(l=>l.state==='native_loaded');
  assert.ok(fin,'the app reported its native steps (exit '+code+')');
  const r=Object.fromEntries(fin.steps.map(s=>[s.name,s.result])),bad=[];
  const pairs=[['before swap A','',A],['before swap B','',B],['reload click 1','before reload 1',A],['reload click 2','before reload 2',C],['return click 1','before return 1',D],['return click 2','before return 2',E],['bottom row','before bottom',Z]];
  const summary=pairs.map(([n,before,t])=>({click:n,target:t.id,selected_before:before?(r[before]||{}).selection:null,ok:(r[n]||{}).ok===true&&(r[n]||{}).selected===t.id,error:(r[n]||{}).error||''}));
  const ra=r['after back']||{},rk=r['after back kept']||{},ev=fin.events||[];
  const width=n=>({w:(r[n]||{}).window_width,min:(r[n]||{}).min_width,content_min:(r[n]||{}).content_min_width,drag_clamp:(r[n]||{}).drag_clamp,surface:(r[n]||{}).surface});
  fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({app_exit:code,summary,reload:r['reload'],web:r['web state'],returned:r['before return 1'],
   back:{web:r['web state 2'],kept_click:r['back kept'],kept:rk,discard_click:r['back discard'],after:ra,select:r['after back click'],feedback:r['feedback sheet'],prompts:ev.filter(e=>e.discard_prompt)},
   widths:Object.fromEntries(['small saved frame','before reload 1','web 360','before return 1','after back','final'].map(n=>[n,width(n)])),bottom:r['bottom row'],web_shot:r['web shot']},null,1));
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
  if((r['web state 2']||{}).surface!=='web')bad.push('⌘E did not open the web tools the second time');
  if((r['back kept']||{}).ok!==true)bad.push('the native ← 返回清单 button above the web tools was not found or not clicked ('+((r['back kept']||{}).error||'')+')');
  if(!(rk.surface==='web'&&rk.web_visible===true))bad.push('← 返回清单 left a web page with unsaved input without asking');
  if(!ev.some(e=>e.discard_prompt==='回到工作台'&&e.choice==='继续编辑'))bad.push('← 返回清单 did not ask before leaving unsaved web input');
  if(!ev.some(e=>e.discard_prompt==='回到工作台'&&e.choice==='放弃'))bad.push('the explicit discard was not asked');
  if(!(ra.surface==='native'&&ra.native_visible===true&&ra.child===mine.child_id&&ra.day===(r['final']||{}).day&&ra.selection===E.id))bad.push('← 返回清单 did not return to the same child, day and selected item');
  if(!((r['after back click']||{}).ok===true&&(r['after back click']||{}).selected===A.id))bad.push('after ← 返回清单 a real click did not select another item');
  if((r['feedback sheet']||{}).sheet!=='feedback-'+A.id)bad.push('after ← 返回清单 the feedback sheet did not open for the newly selected item');
  if((r['sheet closed']||{}).sheet!=='')bad.push('Esc did not close the untouched feedback sheet');
  if(!((r['small saved frame']||{}).window_width<900))bad.push('the small saved-frame step did not narrow the window (not a real test)');
  for(const n of ['before reload 1','before return 1','after back','final'])if(!((r[n]||{}).window_width>=900&&(r[n]||{}).drag_clamp>=900))bad.push(n+': the native workbench is narrower than its usable width '+JSON.stringify(width(n)));
  if(!((r['web 360']||{}).surface==='web'&&(r['web 360']||{}).window_width<=400&&(r['web 360']||{}).drag_clamp<=400))bad.push('the web tools could not stay at the 360 phone width '+JSON.stringify(width('web 360')));
  if((r['web shot']||{}).ok!==true)bad.push('no snapshot of the web tools with the back bar');
  assert.deepEqual(bad,[],bad.join('\n'));
  assert.equal(code,0,'app exit');
  console.log('native host re-entry: real clicks select unselected rows after reload and after web tools → workbench');
 }finally{await stopFixture()}
})().catch(e=>{console.error(e);process.exit(1)});
