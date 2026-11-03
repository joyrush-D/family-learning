// Native acceptance of the Mac batch photo import (PRD 5.1 M1): fictional pages only, fixed raw model replies that still pass the
// real annotate/grouping/review validators, the product backend round (family_agent.run_once) on the demo data, the real app
// server behind a test-only parent login. Faults: client side via the app's own --smoke-test faults (drop_reply,
// fail_before_send); server side via this proxy (one failed batch list GET, one 401 original image GET).
// Usage on a separate test Mac:  node test_photo_batch_native.cjs --allow-visible-test-window
// Headless contract check only (no app, no window):  node test_photo_batch_native.cjs --server-only
// The system picker and drag-in cannot be automated: picks are the app's test-declared files (not a system picker proof).
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),http=require('node:http'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events'),{setTimeout:delay}=require('node:timers/promises');
const visible=process.argv.includes('--allow-visible-test-window'),serverOnly=process.argv.includes('--server-only');
if(!visible&&!serverOnly){console.error('Pass --allow-visible-test-window on a separate test Mac, or --server-only for the headless contract.');process.exit(2)}
const out=process.env.PHOTO_NATIVE_OUT||fs.mkdtempSync(path.join(os.tmpdir(),'photo-native-'));fs.mkdirSync(out,{recursive:true});
const PNG_HEX='89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000100ffff03000006000557bfab440000000049454e44ae426082';
const page=tag=>Buffer.concat([Buffer.from(PNG_HEX,'hex'),Buffer.from('synthetic-'+tag)]);
async function freePort(){const s=net.createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p}
const LAUNCH=`import app, base64, json, runpy, sys, threading, time
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
    while True:
        time.sleep(0.4)
        if 'family-demo-' not in str(app.DATA): continue
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
(async()=>{
 const port=await freePort(),USER='fictional-parent',PASS='fictional-'+crypto.randomUUID(),auth=proxy(port,USER,PASS);
 const env0={...process.env};for(const k of Object.keys(env0))if(k.startsWith('FAMILY_'))delete env0[k];
 const fixture=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-B','-c',LAUNCH,String(port)],{cwd:__dirname,env:env0,stdio:['ignore','ignore','pipe']});let errors='';fixture.stderr.on('data',b=>errors+=b);
 const stop=async()=>{auth.server.close();if(fixture.exitCode!==null)return;const d=once(fixture,'exit');fixture.kill('SIGINT');await Promise.race([d,delay(3000)]);if(fixture.exitCode===null)fixture.kill('SIGKILL')};
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
   console.log(JSON.stringify({server_only:true,batch:b1.id,versions:2,wrong_located:wrong.length,create_requests:creates.length,create_keys:1,stale_append:409}));return;
  }
  const app=execFileSync('sh',[path.join(__dirname,'packaging/macos/build.sh'),path.join(out,'build')],{encoding:'utf8'}).trim().split('\n').pop();
  const steps=[
   {name:'wrong notebook',click:'mode-wrong'},{name:'import entry',until:'photo-import'},
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
   {name:'reopen cold',native:'reopen'},{name:'wrong notebook again',click:'mode-wrong'},{name:'batch kept',find_text:'数学 · 虚构数学练习',timeout:20},
   {name:'append',pick:[files[3]]},{name:'add photo',click_prefix:'photo-append-'},{name:'appended',until:'photo-notice',contains:'已补进同一批',timeout:20},
   {name:'narrow 900',width:900,native:'snapshot'},
   {name:'other child',key:'2',modifiers:['command']},{name:'isolation',find_text:'虚构数学练习',absent:true,timeout:8},{name:'back',key:'1',modifiers:['command']}];
  const stepsFile=path.join(out,'photo-native-steps.json');fs.writeFileSync(stepsFile,JSON.stringify(steps,null,1));
  const shots=path.join(out,'shots');fs.mkdirSync(shots,{recursive:true});const support=fs.mkdtempSync(path.join(os.tmpdir(),'photo-native-support-'));
  const env={...env0,FAMILY_DESKTOP_SUPPORT_DIR:support,FAMILY_DESKTOP_TEST_ORIGIN:origin,FAMILY_DESKTOP_TEST_SETUP_INPUTS:JSON.stringify([origin]),
   FAMILY_DESKTOP_TEST_SURFACE:'native',FAMILY_DESKTOP_TEST_LOGIN:JSON.stringify([USER,PASS]),FAMILY_DESKTOP_TEST_NATIVE_STEPS:stepsFile,FAMILY_DESKTOP_TEST_SNAPSHOT_DIR:shots,FAMILY_DESKTOP_SMOKE_HOLD:'1'};
  const proc=spawn(path.join(app,'Contents/MacOS/YiqiChengzhang'),['--smoke-test'],{env,stdio:['ignore','pipe','pipe']});let text='';proc.stdout.on('data',b=>text+=b);proc.stderr.on('data',b=>text+=b);
  const [code]=await once(proc,'exit');fs.writeFileSync(path.join(out,'app.log'),text);assert.equal(code,0,'native steps failed; see '+out);
  const creates=auth.seen.filter(s=>s.path==='/api/photo-batch/create'&&s.status===200);assert.equal(new Set(creates.map(s=>s.key)).size,1,'one batch key across the lost receipt and the refused second import');
  console.log(JSON.stringify({native:true,out,creates:creates.length}));
 }finally{await stop()}
})().catch(e=>{console.error(e);process.exit(1)});
