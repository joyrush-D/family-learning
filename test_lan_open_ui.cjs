// Disposable family only: no-login LAN UI, real HTTP saves, public authentication unchanged.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const lan='http://192.168.50.2:8765',publicOrigin='https://family.example.test';
async function wait(f){for(let i=0;i<200;i++){if(await f())return;await delay(50)}throw Error('Timed out')}
(async()=>{let proc,browser;const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'family-lan-open-'));
try{
const env={...process.env};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];Object.assign(env,{FAMILY_DATA:tmp,FAMILY_LAN_URL:lan,FAMILY_LAN_NO_LOGIN:'1'});
proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',`import app,json,family_access
app.read=lambda name: '| child-1 | 示例孩子 | 未填写 | 10岁 | 四年级 |\\n' if name=='家庭运行规则.md' else '# 虚构测试资料\\n'
p=app.DATA/'access.json';p.write_text(json.dumps(family_access.make_config('https://family.example.test/family','parent','synthetic-password-123')));p.chmod(0o600)
app.connect().close();app.prepare_assets()
s=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);print(s.server_port,flush=True);s.serve_forever()`],{cwd:__dirname,env,stdio:['ignore','pipe','pipe']});
let out='',err='';proc.stdout.on('data',b=>out+=b);proc.stderr.on('data',b=>err+=b);await wait(()=>{if(proc.exitCode!==null)throw Error(err);return /^\d+/.test(out)});const port=Number(out.trim());
browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
for(const width of [360,1440]){
const c=await browser.newContext({viewport:{width,height:900}});await c.route('**/*',async route=>{
const r=route.request(),u=new URL(r.url());if(![lan,publicOrigin].includes(u.origin))return route.abort();const headers={...r.headers(),host:u.host};delete headers['content-length'];if(u.origin===publicOrigin)headers['x-forwarded-proto']='https';
const result=await new Promise((resolve,reject)=>{const q=http.request({host:'127.0.0.1',port,path:u.pathname.replace(/^\/family\//,'/')+u.search,method:r.method(),headers},res=>{let parts=[];res.on('data',b=>parts.push(b));res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body:Buffer.concat(parts)}))});q.on('error',reject);q.end(r.postDataBuffer())});await route.fulfill(result);
});const p=await c.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
await p.goto(lan);await p.locator('#task-group-homework').waitFor();assert.equal((await c.cookies()).length,0);
await p.locator('[data-page=calendar]').first().click();await p.locator('[data-calendar-new]').click();const f=p.locator('#calendarForm');await f.locator('[name=title]').fill('虚构免登录计划'+width);await f.locator('[name=child_ids]').first().check();await p.locator('#calendarSave').click();await p.locator('#calendarDialog').waitFor({state:'hidden'});
await p.reload();await p.locator('#task-group-homework').waitFor();await p.locator('[data-page=calendar]').first().click();await p.getByText('虚构免登录计划'+width,{exact:true}).first().waitFor();
assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);assert.equal((await c.cookies()).length,0);
if(process.env.LAN_OPEN_UI_PROOF_DIR){await fs.mkdir(process.env.LAN_OPEN_UI_PROOF_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.LAN_OPEN_UI_PROOF_DIR,'lan-'+width+'.png')})}
// Redirect boundary is covered by test_access; Chrome routing skips redirected requests.
await p.goto(publicOrigin+'/family/login');await p.locator('input[type=password]').waitFor();assert.equal(await p.locator('#task-group-homework').count(),0);await c.close();console.log('PASS no-login save/reopen; public login retained:',width);
}
}finally{if(browser)await browser.close();if(proc)proc.kill('SIGTERM');await fs.rm(tmp,{recursive:true,force:true})}})().catch(e=>{console.error(e);process.exitCode=1});
