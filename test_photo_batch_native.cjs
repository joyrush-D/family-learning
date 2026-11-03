// Native acceptance of the Mac batch photo import (PRD 5.1 M1): fictional pages only, fixed raw model replies that still pass the
// real annotate/grouping/review validators, the product backend round (family_agent.run_once) on the demo data, the real app
// server behind a test-only parent login. Faults: client side via the app's own --smoke-test faults (drop_reply,
// fail_before_send); server side via this proxy (one failed batch list GET, one 401 original image GET).
// Usage on a separate test Mac:  node test_photo_batch_native.cjs --allow-visible-test-window
// Headless contract check only (no app, no window):  node test_photo_batch_native.cjs --server-only
// Guard self-test (no app, no window):  node test_photo_batch_native.cjs --self-test
// Store contract (real Swift Store/Client compiled with the macOS SDK, loopback fixture, no NSApplication or window, no POST):
//   node test_photo_batch_native.cjs --store-contract   (optional PHOTO_POSITIVE_PNG: a fictional PNG served on the successful re-read)
// Evidence labels: the pages are synthetic 1x1 placeholder PNGs (no real photo pixels or box placement is proven), the
// "reopen" step is the app's in-memory view remount (not a cold process restart), and picks are test-declared files (not
// the system picker or drag-in). Real 900/1440 photos and cold App restarts are Root's independent evidence.
// Safety: PHOTO_NATIVE_OUT must be a new directory (existing, symlinked, root-level or in-repository paths are refused);
// the build goes only into that directory; every spawned process is this run's own and is stopped by its handle on
// success, failure or the PHOTO_NATIVE_DEADLINE_MS deadline; the fixture refuses child processes, external network and
// any SQLite but its own fictional one, and has a bounded lifetime and fixed-reply budget.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),http=require('node:http'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const visible=process.argv.includes('--allow-visible-test-window'),serverOnly=process.argv.includes('--server-only'),selfTest=process.argv.includes('--self-test'),storeContract=process.argv.includes('--store-contract');
const refuse=reason=>{console.error('refused: '+reason);process.exit(2)};
if([visible,serverOnly,selfTest,storeContract].filter(Boolean).length!==1)refuse('pass exactly one of --allow-visible-test-window (separate test Mac), --server-only, --self-test or --store-contract');
const DEADLINE_MS=Number(process.env.PHOTO_NATIVE_DEADLINE_MS)||(visible?600000:120000);
function exists(p){try{fs.lstatSync(p);return true}catch{return false}}
// A new, exclusive output directory: never an existing path or symlink, never under a symlinked parent, never the filesystem
// root level, the home directory or inside this repository. Created non-recursively, so a concurrent creator makes it fail.
function exclusiveOut(){
 const given=process.env.PHOTO_NATIVE_OUT;
 if(!given)return fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()),'photo-native-'));
 const target=path.resolve(given),parent=path.dirname(target),repo=fs.realpathSync(__dirname),home=fs.realpathSync(os.homedir());
 if(exists(target))refuse('output path already exists (or is a symlink): '+target);
 let real;try{real=fs.realpathSync(parent)}catch{refuse('output parent does not exist: '+parent)}
 if(real!==parent)refuse('output parent is or passes through a symlink: '+parent);
 if(parent===path.parse(target).root||target===home||target===repo||target.startsWith(repo+path.sep))refuse('dangerous output location: '+target);
 fs.mkdirSync(target,{mode:0o700});return target;
}
const out=selfTest?null:exclusiveOut();
const owned=[];let appSpawned=false;
function spawnOwned(name,cmd,args,opts){const proc=spawn(cmd,args,opts);owned.push({name,proc,signal:name==='fixture'?'SIGINT':'SIGTERM'});if(name==='app')appSpawned=true;return proc}
// Stop only this run's own children, by their handles: polite signal, bounded wait, then SIGKILL and a bounded wait.
async function stopOwned(){
 for(const {proc,signal} of [...owned].reverse()){
  if(proc.exitCode!==null||proc.signalCode!==null)continue;
  const ended=once(proc,'exit');proc.kill(signal);await Promise.race([ended,delay(4000)]);
  if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await Promise.race([ended,delay(3000)])}
 }
 return owned.map(({name,proc})=>({name,pid:proc.pid,exit:proc.exitCode,signal:proc.signalCode,ended:proc.exitCode!==null||proc.signalCode!==null}));
}
let finishing=null;
async function finish(code,status,summary={}){
 if(finishing)return finishing;
 finishing=(async()=>{
  clearTimeout(deadlineTimer);const children=await stopOwned();
  const terminal={status,code,app_spawned:appSpawned,deadline_ms:DEADLINE_MS,children,...summary};
  if(out)fs.writeFileSync(path.join(out,'TERMINAL.json'),JSON.stringify(terminal,null,1));
  console.log(JSON.stringify(terminal));process.exit(code);
 })();
 return finishing;
}
const deadlineTimer=setTimeout(()=>finish(3,'deadline',{error:'deadline '+DEADLINE_MS+' ms reached; own children stopped'}),DEADLINE_MS);
const PNG_HEX='89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000100ffff03000006000557bfab440000000049454e44ae426082';
const page=tag=>Buffer.concat([Buffer.from(PNG_HEX,'hex'),Buffer.from('synthetic-'+tag)]);
async function freePort(){const s=net.createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p}
const LAUNCH=`import atexit, json, os, signal, sys, threading, time
LIFETIME, STATUS, MAX_REPLIES = float(sys.argv[2]), sys.argv[3], 40
blocked, state = [], dict(fixed_replies=0, rounds=0)
def audit(event, args):
    if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.spawn', 'os.exec', 'os.fork', 'os.forkpty', 'pty.spawn'):
        blocked.append(event); raise PermissionError('fixture: no child processes')
    if event in ('socket.connect', 'socket.bind') and isinstance(args[1], tuple) and args[1] and args[1][0] not in ('127.0.0.1', '::1', 'localhost'):
        blocked.append(event); raise PermissionError('fixture: loopback only')
    if event == 'sqlite3.connect' and str(args[0]) != ':memory:' and 'family-demo-' not in str(args[0]):
        blocked.append(event); raise PermissionError('fixture: only its own fictional SQLite')
sys.addaudithook(audit)
atexit.register(lambda: open(STATUS, 'w').write(json.dumps(dict(state, blocked=blocked, provider_calls=0))))
def end_of_life():
    os.kill(os.getpid(), signal.SIGINT); time.sleep(5); os._exit(4)
life = threading.Timer(LIFETIME, end_of_life); life.daemon = True; life.start()
import app, base64, runpy
import family_agent, family_llm, family_photo_batch as fpb, family_wrong_questions as fwq
family_llm.configuration = lambda *a, **k: ('https://example.invalid', 'synthetic')
PNG = bytes.fromhex('${PNG_HEX}')
TAGS = {PNG + b'synthetic-' + t.encode(): t for t in ('m1', 'm2', 'c1', 'm3')}
def ev(subject, title, printed, first, last):
    return dict(subject=subject, subject_basis='题面内容', title=title, printed_page=printed, first_label=first, last_label=last,
                head='虚构开头', tail='虚构结尾', page_kind='answered', readability='clear')
def reg(label, y):
    return dict(kind='wrong_item', box=dict(x=100, y=y, w=600, h=150), label=label, text='虚构题面', answer='35', correction='', uncertain=False)
PAGES = {'m1': (ev('数学', '虚构数学练习', '1', '第2题', '第2题'), [reg('第2题', 200)]), 'm2': (ev('数学', '虚构数学练习', '2', '第4题', '第4题'), []),
         'c1': (ev('语文', '虚构语文小测', '1', '第2题', '第2题'), [reg('第2题', 300)]), 'm3': (ev('数学', '虚构数学练习', '3', '第6题', '第6题'), [])}
failed = []
def item(label, said, ref, judgment, reason=''):
    return dict(label=label, question='虚构题面', student_answer=said, answer=ref, judgment=judgment, error_reason=reason, possible_cause='',
                steps='按参考订正' if judgment == 'incorrect' else '', uncertainty='', question_kind='objective')
def fake(messages, schema, name, timeout=60, *, data_path=None):
    state['fixed_replies'] += 1
    if state['fixed_replies'] > MAX_REPLIES:
        raise family_llm.LLMDraftError('fixture: fixed reply budget exhausted')
    tags = [TAGS[base64.b64decode(p['image_url']['url'].split(',', 1)[1])] for m in messages if isinstance(m['content'], list)
            for p in m['content'] if p.get('type') == 'image_url']
    if name == fwq.TASK_NAME:
        return dict(pages=[dict(page=i, regions=PAGES[t][1], evidence=PAGES[t][0]) for i, t in enumerate(tags, 1)], uncertainties=[])
    if name == fpb.GROUP_TASK:
        if not failed:
            failed.append(1); raise family_llm.LLMDraftError('虚构：组卷请求暂时失败')
        ids = [p['page_id'] for p in json.loads(messages[1]['content'].split('：', 1)[1])['pages']]
        math = [p for p in ('p03', 'p01', 'p04') if p in ids]
        return dict(papers=[dict(subject='数学', title='虚构数学练习', basis='同标题、印刷页码连续', pages=[dict(page_id=p, order=i, role='answered') for i, p in enumerate(math, 1)]),
                            dict(subject='语文', title='虚构语文小测', basis='语文题面', pages=[dict(page_id='p02', order=1, role='answered')])], pending=[], same_pages=[])
    if name != 'family_homework_reference':
        raise family_llm.LLMDraftError('虚构：本测试不提供其他模型任务')
    if 'c1' in tags:
        items = [item('第2题', '窗处', '窗外', 'incorrect', '“外”写成“处”')]
    else:
        items = [item('第2题', '35', '25', 'incorrect', '退位减法算错'), item('第4题', '9', '9', 'correct')] + ([item('第6题', '7', '7', 'correct')] if 'm3' in tags else [])
    return dict(items=items, coverage='虚构覆盖', question_labels=[i['label'] for i in items])
family_llm._chat_json = fake
def backend():
    stop = time.time() + LIFETIME
    while time.time() < stop and state['rounds'] < 600:
        time.sleep(0.4)
        if 'family-demo-' not in str(app.DATA): continue
        state['rounds'] += 1
        try: family_agent.run_once(app)
        except Exception as error: print('round error', repr(error), file=sys.stderr, flush=True)
threading.Thread(target=backend, daemon=True).start()
sys.argv = ['demo.py', '--port', sys.argv[1]]
runpy.run_path('demo.py', run_name='__main__')`;
// Test-only parent login and server-side faults in front of the fixture; every other request passes through unchanged.
function proxy(appPort,user,password){
 const sessions=new Set(),seen=[],faults=[];
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1'),chunks=[];req.on('data',d=>chunks.push(d));
  req.on('end',()=>{
   const body=Buffer.concat(chunks),sid=(req.headers.cookie||'').split(';').map(s=>s.trim()).filter(s=>s.startsWith('family_parent_session=')).map(s=>s.slice(22))[0]||'';
   let key='';if(req.method==='POST'){try{key=JSON.parse(body.toString()).request_key||''}catch{}}
   const json=(code,obj,headers={})=>{seen.push({method:req.method,path:url.pathname,status:code,key});res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',...headers});res.end(JSON.stringify(obj))};
   if(url.pathname==='/__fixture/fault'){faults.push(url.searchParams.get('kind'));return json(200,{ok:true,faults})}
   if(url.pathname==='/api/parent/login'&&req.method==='POST'){let o={};try{o=JSON.parse(body.toString())}catch{}
    if(req.headers['x-family-login']!=='1'||o.username!==user||o.password!==password)return json(401,{error:'用户名或密码不正确'});
    const id=crypto.randomBytes(32).toString('base64url');sessions.add(id);return json(200,{ok:true},{'Set-Cookie':`family_parent_session=${id}; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600`})}
   if(req.method==='GET'&&(url.pathname==='/login'||url.pathname==='/login.js')){const js=url.pathname==='/login.js';seen.push({method:'GET',path:url.pathname,status:200,key:''});
    res.writeHead(200,{'Content-Type':js?'text/javascript; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-store'});return res.end(fs.readFileSync(path.join(__dirname,js?'login.js':'login.html')))}
   if((url.pathname.startsWith('/api/')||url.pathname.startsWith('/upload'))&&!sessions.has(sid))return json(401,{error:'需要登录'});
   const take=kind=>{const i=faults.indexOf(kind);if(i<0)return false;faults.splice(i,1);return true};
   if(req.method==='GET'&&url.pathname==='/api/photo-batches'&&take('list_503'))return json(503,{error:'虚构：读取暂时失败'});
   if(req.method==='GET'&&url.pathname.startsWith('/upload/')&&take('image_401'))return json(401,{error:'需要登录'});
   const up=http.request({host:'127.0.0.1',port:appPort,method:req.method,path:req.url,headers:req.headers},r=>{seen.push({method:req.method,path:url.pathname,status:r.statusCode,key});res.writeHead(r.statusCode,r.headers);r.pipe(res)});
   up.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end()});up.end(body)})});
 return {server,seen,faults};
}
async function eventually(check,label,timeout=30000){const until=Date.now()+timeout;while(Date.now()<until){if(await check())return;await delay(200)}throw Error('Timed out: '+label)}
async function guards(){
 // Each case is this file in a child process: refusals must happen before any spawn; the deadline must stop the own fixture.
 const run=(args,env)=>new Promise(resolve=>{const p=spawnOwned('self-test-child',process.execPath,[__filename,...args],{env:{...process.env,...env},stdio:['ignore','pipe','pipe']});
  let text='';p.stdout.on('data',b=>text+=b);p.stderr.on('data',b=>text+=b);p.on('exit',code=>resolve({code,text}))});
 const base=fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()),'photo-native-guard-')),results=[];
 const existing=path.join(base,'existing');fs.mkdirSync(existing);const link=path.join(base,'link');fs.symlinkSync(existing,link);
 for(const [name,args,env] of [['no mode',[],{}],['existing out',['--server-only'],{PHOTO_NATIVE_OUT:existing}],['symlink out',['--server-only'],{PHOTO_NATIVE_OUT:link}],
   ['symlinked parent',['--server-only'],{PHOTO_NATIVE_OUT:path.join(link,'new')}],['inside repository',['--server-only'],{PHOTO_NATIVE_OUT:path.join(__dirname,'photo-native-out')}]]){
  const r=await run(args,env);assert.equal(r.code,2,name+': '+r.text);assert.match(r.text,/refused/,name);results.push(name);
 }
 assert.equal(exists(path.join(__dirname,'photo-native-out')),false,'nothing created inside the repository');
 const late=path.join(base,'deadline');const r=await run(['--server-only'],{PHOTO_NATIVE_OUT:late,PHOTO_NATIVE_DEADLINE_MS:'2500'});
 assert.equal(r.code,3,'deadline exit: '+r.text);const terminal=JSON.parse(fs.readFileSync(path.join(late,'TERMINAL.json'),'utf8'));
 assert.equal(terminal.status,'deadline');assert.equal(terminal.app_spawned,false);assert.ok(terminal.children.length>0&&terminal.children.every(c=>c.ended),'deadline stopped its own fixture');
 for(const c of terminal.children){let alive=true;try{process.kill(c.pid,0)}catch{alive=false}assert.equal(alive,false,'pid '+c.pid+' gone')}
 results.push('deadline terminal');fs.rmSync(base,{recursive:true,force:true});
 return finish(0,'passed',{self_test:results});
}
const CONTRACT=`import AppKit
import Foundation
@main struct PhotoImageRecoveryContract {
 @MainActor static func main() async {
  let store = WorkspaceStore(client: WorkspaceClient(origin: ServiceOrigin.parse(CommandLine.arguments[1])!, ephemeral: true))
  await store.load()
  var checks: [String: Bool] = [:]
  let first = await store.photoImage("QA-recover-original")
  checks["image_failure_reports_recovery"] = first == nil && !store.photoRecovery.isEmpty
  await store.loadPhotoBatches()
  checks["list_success_keeps_image_recovery"] = !store.photoRecovery.isEmpty && store.photoProblems.keys.contains("image:QA-recover-original")
  await store.refreshPhotos()
  let image = store.photoImages["QA-recover-original"]
  checks["explicit_retry_reads_same_image"] = image != nil && store.photoRecovery.isEmpty && store.photoProblems.isEmpty
  let size = image?.representations.first.map { [$0.pixelsWide, $0.pixelsHigh] } ?? []
  let report: [String: Any] = ["checks": checks, "pixels": size, "windows": NSApp == nil ? 0 : -1]
  print(String(decoding: try! JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]), as: UTF8.self))
  exit(checks.values.allSatisfy { $0 } ? 0 : 1)
 }
}`;
const FIXTURE=`import hashlib, json, sys, threading
sys.dont_write_bytecode = True
import test_native_context as t
png = open(sys.argv[2], 'rb').read() if len(sys.argv) > 2 and sys.argv[2] else None
counts = dict(image_reads=0, list_reads=0, posts=0, served_sha256='')
original_get, original_post = t.Backend.do_GET, t.Backend.do_POST
def do_get(self):
    if self.path.startswith('/api/photo-batches'):
        counts['list_reads'] += 1; return self.reply(200, {'child_id': 'child-1', 'batches': []})
    if self.path == '/upload/QA-recover-original':
        counts['image_reads'] += 1
        if counts['image_reads'] == 1: return self.reply(503, {'error': '虚构：这张原图暂不可用'})
        counts['served_sha256'] = hashlib.sha256(png).hexdigest()
        self.send_response(200); self.send_header('Content-Type', 'image/png'); self.send_header('Content-Length', str(len(png))); self.end_headers(); self.wfile.write(png); return
    return original_get(self)
def do_post(self):
    counts['posts'] += 1; return original_post(self)
t.Backend.do_GET, t.Backend.do_POST = do_get, do_post
server = t.ThreadingHTTPServer(('127.0.0.1', 0), t.Backend)
threading.Thread(target=server.serve_forever, daemon=True).start()
print(json.dumps(dict(port=server.server_address[1])), flush=True)
sys.stdin.readline()
print(json.dumps(counts), flush=True)
server.shutdown()`;
async function storeRun(){
 const png=process.env.PHOTO_POSITIVE_PNG?path.resolve(process.env.PHOTO_POSITIVE_PNG):path.join(out,'positive.png');
 if(!process.env.PHOTO_POSITIVE_PNG)fs.writeFileSync(png,Buffer.from(PNG_HEX,'hex'));
 const sdk=execFileSync('/usr/bin/xcrun',['--sdk','macosx','--show-sdk-path'],{encoding:'utf8'}).trim(),src=path.join(__dirname,'packaging/macos/Sources');
 fs.writeFileSync(path.join(out,'contract.swift'),CONTRACT);
 const env={};for(const [k,v] of Object.entries(process.env))if(!/^(FAMILY_|OPENAI|ANTHROPIC|ARK_|DOUBAO|VOLC|TYPESAFE)|API_KEY|TOKEN|SECRET|PASSWORD|PROXY/i.test(k))env[k]=v;env.SDKROOT=sdk;env.TMPDIR=out;
 execFileSync('/usr/bin/xcrun',['--sdk','macosx','swiftc','-swift-version','5','-parse-as-library','-target','arm64-apple-macos13.0',
  ...['DesktopPolicy.swift','WorkspaceAPI.swift','Workspace.swift'].map(n=>path.join(src,n)),path.join(out,'contract.swift'),'-o',path.join(out,'contract')],{cwd:out,env,stdio:['ignore','ignore','pipe']});
 const fixture=spawnOwned('fixture',process.env.FAMILY_TEST_PYTHON||'python3',['-B','-c',FIXTURE,'',png],{cwd:__dirname,env,stdio:['pipe','pipe','pipe']});
 let lines='';fixture.stdout.on('data',b=>lines+=b);await eventually(async()=>lines.includes('port'),'fixture port',20000);
 const port=JSON.parse(lines.split('\n')[0]).port;
 const run=spawnOwned('contract',path.join(out,'contract'),['http://127.0.0.1:'+port],{cwd:out,env,stdio:['ignore','pipe','pipe']});
 let text='';run.stdout.on('data',b=>text+=b);run.stderr.on('data',b=>text+=b);const [code]=await once(run,'exit');
 fixture.stdin.end('done\n');await eventually(async()=>lines.split('\n').filter(Boolean).length>=2,'fixture counts',10000);
 const counts=JSON.parse(lines.split('\n').filter(Boolean)[1]),report=JSON.parse(text.trim().split('\n').pop());
 const sha=crypto.createHash('sha256').update(fs.readFileSync(png)).digest('hex');
 assert.equal(code,0,'contract checks: '+text);assert.equal(counts.posts,0,'no POST');assert.equal(counts.image_reads,2,'one failed read and one explicit re-read of the same image');
 assert.equal(counts.served_sha256,sha,'the re-read served exactly the fictional PNG');
 return finish(0,'passed',{store_contract:true,checks:report.checks,pixels:report.pixels,http:counts,png_sha256:sha,windows:0,provider_calls:0});
}
(async()=>{
 if(selfTest)return guards();
 if(storeContract)return storeRun();
 const port=await freePort(),USER='fictional-parent',PASS='fictional-'+crypto.randomUUID(),auth=proxy(port,USER,PASS);
 // No real model, data, account or proxy settings reach the children; any data fallback points inside this run's directory.
 const env0={};for(const [k,v] of Object.entries(process.env))if(!/^(FAMILY_|OPENAI|ANTHROPIC|ARK_|DOUBAO|VOLC|TYPESAFE)|API_KEY|TOKEN|SECRET|PASSWORD|PROXY/i.test(k))env0[k]=v;
 env0.FAMILY_DATA=path.join(out,'no-household-data');
 const status=path.join(out,'fixture-status.json'),lifetime=Math.max(1,Math.floor(DEADLINE_MS/1000));
 const fixture=spawnOwned('fixture',process.env.FAMILY_TEST_PYTHON||'python3',['-B','-c',LAUNCH,String(port),String(lifetime),status],{cwd:__dirname,env:env0,stdio:['ignore','ignore','pipe']});let errors='';fixture.stderr.on('data',b=>errors+=b);
 const stop=async()=>{auth.server.close();return stopOwned()};
 try{
  auth.server.listen(0,'127.0.0.1');await once(auth.server,'listening');const origin=`http://127.0.0.1:${auth.server.address().port}`;
  await eventually(async()=>{try{return (await fetch(`http://127.0.0.1:${port}/`)).ok}catch{return false}},'fixture server');
  const files=['m2','c1','m1','m3'].map(t=>{const f=path.join(out,t+'.png');fs.writeFileSync(f,page(t));return f});
  if(serverOnly){
   // The same contract the native steps rely on, over HTTP through the same proxy (no app, no window).
   const login=await fetch(origin+'/api/parent/login',{method:'POST',headers:{'X-Family-Login':'1','Content-Type':'application/json'},body:JSON.stringify({username:USER,password:PASS})});
   const cookie=login.headers.get('set-cookie').split(';')[0];const state=await (await fetch(origin+'/api/state',{headers:{cookie}})).json();
   const H={cookie,'X-Family-Token':state.token},child=state.children[0].id,other=state.children[1].id,key='pbnative'+crypto.randomUUID().replace(/-/g,'');
   const post=async(p,b)=>{const r=await fetch(origin+p,{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify(b)});return [r.status,await r.json()]};
   const ids=[];for(const [i,f] of files.slice(0,3).entries()){const r=await fetch(origin+'/api/upload',{method:'POST',headers:{...H,'X-File-Name':encodeURIComponent(path.basename(f)),'X-Request-Key':key+'-'+i,'Content-Type':'application/octet-stream'},body:fs.readFileSync(f)});ids.push((await r.json()).attachment.id)}
   const [c1,b1]=await post('/api/photo-batch/create',{child_id:child,request_key:key,uploads:ids});const [c2,b2]=await post('/api/photo-batch/create',{child_id:child,request_key:key,uploads:ids});
   assert.equal(c1,200);assert.equal(b2.replayed,true,'lost create receipt: same key reads back the same batch');assert.equal(b2.id,b1.id);
   const view=async()=>{const r=await fetch(origin+'/api/photo-batch?id='+b1.id,{headers:H});return r.json()};
   await eventually(async()=>(await view()).can_continue,'failed grouping kept for an explicit continue');
   const before=(await view()).progress.calls;await delay(1500);assert.equal((await view()).progress.calls,before,'no automatic retry');
   assert.equal((await post('/api/photo-batch/continue',{batch_id:b1.id,version:1}))[0],200);
   await eventually(async()=>(await view()).state==='done','done after continue');
   let v=await view();assert.deepEqual(v.papers.map(p=>p.subject).sort(),['数学','语文']);const wrong=v.papers.flatMap(p=>p.questions).filter(q=>q.state==='wrong');
   assert.equal(wrong.length,2);assert.ok(wrong.every(q=>q.box&&q.record_id),'two wrongs with boxes and original records');
   await fetch(origin+'/__fixture/fault?kind=list_503');assert.equal((await fetch(origin+'/api/photo-batches?child_id='+child,{headers:H})).status,503);
   assert.equal((await fetch(origin+'/api/photo-batches?child_id='+child,{headers:H})).status,200,'read-back after a failed GET');
   await fetch(origin+'/__fixture/fault?kind=image_401');assert.equal((await fetch(origin+'/upload/'+wrong[0].upload_id,{headers:H})).status,401);
   assert.equal((await fetch(origin+'/upload/'+wrong[0].upload_id,{headers:H})).status,200,'image read-back after 401');
   const add=(await fetch(origin+'/api/upload',{method:'POST',headers:{...H,'X-File-Name':'m3.png','X-Request-Key':key+'-add-0','Content-Type':'application/octet-stream'},body:fs.readFileSync(files[3])}).then(r=>r.json())).attachment.id;
   const [ca,va]=await post('/api/photo-batch/append',{batch_id:b1.id,version:1,request_key:key+'-add',uploads:[add]});assert.equal(ca,200);assert.equal(va.version,2);assert.equal(va.id,b1.id,'append keeps the same batch');
   const [cs]=await post('/api/photo-batch/append',{batch_id:b1.id,version:1,request_key:key+'-add2',uploads:[add]});assert.equal(cs,409,'a stale version is refused');
   await eventually(async()=>(await view()).state==='done','version 2 done');
   const others=await (await fetch(origin+'/api/photo-batches?child_id='+other,{headers:H})).json();assert.deepEqual(others.batches,[],'other child sees nothing');
   const creates=auth.seen.filter(s=>s.path==='/api/photo-batch/create');assert.equal(new Set(creates.map(s=>s.key)).size,1,'one create key');
   assert.doesNotMatch(errors,/round error/,errors);
   const children=await stop();const fixed=JSON.parse(fs.readFileSync(status,'utf8'));
   assert.equal(appSpawned,false,'server-only never starts the App');assert.ok(children.every(c=>c.ended),'own children ended');
   assert.deepEqual(fixed.blocked,[],'no blocked process/network/SQLite attempt');assert.equal(fixed.provider_calls,0);assert.ok(fixed.fixed_replies>0);
   return finish(0,'passed',{server_only:true,batch:b1.id,versions:2,wrong_located:wrong.length,create_requests:creates.length,create_keys:1,stale_append:409,
    fixed_replies:fixed.fixed_replies,provider_calls:0,images:'synthetic_1x1_placeholder_png',pixel_or_box_placement_verified:false});
  }
  const app=execFileSync('sh',[path.join(__dirname,'packaging/macos/build.sh'),path.join(out,'build')],{encoding:'utf8'}).trim().split('\n').pop();
  const steps=[
   {name:'wrong notebook',click:'mode-错题本'},{name:'import entry',until:'photo-import'},
   {name:'pick 3 mixed out of order',pick:files.slice(0,3)},{name:'first upload fails',faults:['fail_before_send']},{name:'import',click:'photo-import'},
   {name:'upload failure kept',until:'photo-notice',contains:'前0张原件已保存'},{name:'create receipt lost',faults:['drop_reply']},{name:'retry same',click:'photo-retry'},
   {name:'unknown receipt',until:'photo-notice',contains:'同一提交重试'},{name:'no discard for a sent draft',find_text:'放弃这次导入',absent:true,timeout:3},
   {name:'second import refused',pick:files.slice(0,3)},{name:'import again',click:'photo-import'},{name:'refused',until:'photo-notice',contains:'登记回执还没确认'},
   {name:'retry same key',click:'photo-retry'},{name:'replayed',until:'photo-notice',contains:'没有重复登记'},
   {name:'continue offered',click_prefix:'photo-continue-',timeout:40},{name:'two papers',find_text:'语文 · 虚构语文小测',timeout:40},
   {name:'open math',click_prefix:'photo-paper-paper-p03'},{name:'box shown',until:'photo-box',contains:'100,200,600,150',timeout:15},
   {name:'original answer apart',find_text:'原答（孩子写的）'},{name:'AI signature',find_text:'署名：AI判断'},{name:'result 1440',native:'snapshot'},
   {name:'open record',click_prefix:'photo-open-record-'},{name:'correct',click_prefix:'wrong-correct-'},{name:'note',click:'correction-note'},{name:'type',type:'虚构：重算得25。'},
   {name:'save correction',click:'sheet-save'},{name:'corrected',find_text:'重算得25',timeout:15},
   {name:'reopen in-memory view (not a cold process restart)',native:'reopen'},{name:'wrong notebook again',click:'mode-错题本'},{name:'batch kept',find_text:'数学 · 虚构数学练习',timeout:20},
   {name:'append',pick:[files[3]]},{name:'add photo',click_prefix:'photo-append-'},{name:'appended',until:'photo-notice',contains:'已补进同一批',timeout:20},
   {name:'narrow 900',width:900,native:'snapshot'},
   {name:'other child',key:'2',modifiers:['command']},{name:'isolation',find_text:'虚构数学练习',absent:true,timeout:8},{name:'back',key:'1',modifiers:['command']}];
  const stepsFile=path.join(out,'photo-native-steps.json');fs.writeFileSync(stepsFile,JSON.stringify(steps,null,1));
  const shots=path.join(out,'shots');fs.mkdirSync(shots);const support=path.join(out,'support');fs.mkdirSync(support,{mode:0o700});
  if(new URL(origin).hostname!=='127.0.0.1'||!auth.server.listening)throw Error('fixture origin is not a bound loopback server; refusing to launch');
  const env={...env0,FAMILY_DESKTOP_SUPPORT_DIR:support,FAMILY_DESKTOP_TEST_ORIGIN:origin,FAMILY_DESKTOP_TEST_SETUP_INPUTS:JSON.stringify([origin]),
   FAMILY_DESKTOP_TEST_SURFACE:'native',FAMILY_DESKTOP_TEST_LOGIN:JSON.stringify([USER,PASS]),FAMILY_DESKTOP_TEST_NATIVE_STEPS:stepsFile,FAMILY_DESKTOP_TEST_SNAPSHOT_DIR:shots,FAMILY_DESKTOP_SMOKE_HOLD:'1'};
  const proc=spawnOwned('app',path.join(app,'Contents/MacOS/YiqiChengzhang'),['--smoke-test'],{env,stdio:['ignore','pipe','pipe']});let text='';proc.stdout.on('data',b=>text+=b);proc.stderr.on('data',b=>text+=b);
  const [code]=await once(proc,'exit');fs.writeFileSync(path.join(out,'app.log'),text);assert.equal(code,0,'native steps failed; see '+out);
  const creates=auth.seen.filter(s=>s.path==='/api/photo-batch/create'&&s.status===200);assert.equal(new Set(creates.map(s=>s.key)).size,1,'one batch key across the lost receipt and the refused second import');
  return finish(0,'passed',{native:true,out,creates:creates.length,reopen:'in_memory_view_remount',cold_app_restart_verified:false,
   images:'synthetic_1x1_placeholder_png',pixel_or_box_placement_verified:false,picker:'test_declared_files',system_picker_or_drag_verified:false});
 }finally{await stop()}
})().catch(e=>{console.error(e);return finish(1,'failed',{error:String(e&&e.stack||e)})});
