'use strict';
// Grouped same-affair web flow at 360/1440 on the fictional fixture (SEMANTIC_UI_FIXTURE=path of the reviewed fixture script,
// which takes this source directory and forbids model calls): one affair in the list, the member's saved feedback and both
// originals in the grouped task, a wrong from the member's feedback sent under that record's own task, no overflow.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const python=process.env.PYTHON||'python3',fixture=process.env.SEMANTIC_UI_FIXTURE;
async function eventually(check,label,timeout=10000){const end=Date.now()+timeout;for(;;){try{if(await check())return}catch(e){}if(Date.now()>end)throw Error('timed out: '+label);await new Promise(r=>setTimeout(r,100))}}
function start(){
  const child=spawn(python,['-I',fixture,__dirname],{stdio:['ignore','pipe','inherit']});
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
      assert.equal(await page.locator(`#task-groups [data-task="${meta.member}"]`).count(),0,'the member is not a second row');
      await page.locator(`#task-groups [data-task="${meta.canonical}"]`).first().click();
      const history=page.locator('#taskFeedbackHistory');
      await eventually(async()=>(await history.innerText()).includes(meta.note.slice(0,10)),'member feedback shown in the grouped affair');
      assert.match(await page.locator('#taskFeedbackIntro').innerText(),/已保存/,'saved count includes the member record');
      await eventually(async()=>await page.locator('#taskSchoolResources .task-school-resource').count()===meta.refs.length,'every member original listed');
      const form=history.locator('[data-task-wrong-form]').first();
      assert.ok(await form.count()>=1,'the member\'s ordinary saved feedback offers its wrong form');
      {
        await form.locator(':scope > summary').click();
        await form.locator('[data-wrong-field="label"]').fill('第2处发音');await form.locator('[data-wrong-field="answer"]').fill('虚构原答');
        await form.locator('[data-wrong-field="correction"]').fill('虚构订正');
        const request=page.waitForRequest(r=>r.url().endsWith('/api/wrong/save'));
        await form.locator('button').last().click();
        assert.equal(JSON.parse((await request).postData()).task_id,meta.member,'wrong saved under the record\'s own task');
      }
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow at '+width);
      await page.close();
    }
  }finally{await browser.close();child.kill('SIGTERM')}
  console.log('PASS: grouped same affair web flow at 360/1440');
})().catch(e=>{console.error(e);process.exit(1)});
