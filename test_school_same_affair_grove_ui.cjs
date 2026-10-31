'use strict';
// Current grove entry (calendar.js), status mismatch: the fixture (SEMANTIC_UI_FIXTURE, run with --status-mismatch) proves one
// affair whose canonical copy is completed and the member pending. At 360/1440 the row and detail must not assert completion,
// must state the uncertainty, keep print entry and sources; no model call.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const python=process.env.PYTHON||'python3',fixture=process.env.SEMANTIC_UI_FIXTURE;
async function eventually(check,label,timeout=10000){const end=Date.now()+timeout;for(;;){try{if(await check())return}catch(e){}if(Date.now()>end)throw Error('timed out: '+label);await new Promise(r=>setTimeout(r,100))}}
function start(){
  const child=spawn(python,['-I',fixture,__dirname,'--status-mismatch'],{stdio:['ignore','pipe','inherit']});
  return new Promise((resolve,reject)=>{let text='';child.stdout.on('data',d=>{text+=d;const i=text.indexOf('\n');if(i>=0)resolve({child,meta:JSON.parse(text.slice(0,i))})});child.on('exit',c=>reject(Error('fixture exited '+c)))});
}
(async()=>{
  assert(fixture,'set SEMANTIC_UI_FIXTURE to the fictional fixture script');
  const {child,meta}=await start();const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  try{
    for(const [width,height] of [[360,800],[1440,900]]){
      const page=await browser.newPage({viewport:{width,height}});
      await page.goto(meta.url);
      await eventually(async()=>await page.locator('#content').getAttribute('data-ready')==='true','home ready at '+width);
      const row=page.locator(`.grove-row[data-today-task="${meta.canonical}"]`);
      await eventually(async()=>await row.count()===1,'one grove row for the affair at '+width);
      assert.equal(await page.locator(`.grove-row[data-today-task="${meta.member}"]`).count(),0,'the member is not a second row');
      const box=row.locator(`input[data-check="${meta.canonical}"]`);
      assert.equal(await box.isChecked(),false,'the uncertain affair is not shown completed');
      assert.match(await box.getAttribute('aria-label'),/^确认完成/,'no 撤销完成 on an uncertain affair');
      assert.match(await row.locator('[data-same-affair="uncertain"]').innerText(),/已标记/,'row states the completion uncertainty');
      await row.locator('[data-grove-open]').click();
      const detail=page.locator('#groveDetail');
      await eventually(async()=>await detail.locator('[data-same-affair="uncertain"]').count()===1,'detail states the uncertainty at '+width);
      assert.equal(await detail.locator('[data-task-restore]').count(),0,'no restore action that would rewrite the completed copy');
      assert.ok(await detail.locator('[data-homework-print]').count()>=1,'print entry stays available');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow at '+width);
      await page.close();
    }
  }finally{await browser.close();child.kill('SIGTERM')}
  console.log('PASS: grove status-mismatch affair at 360/1440');
})().catch(e=>{console.error(e);process.exit(1)});
