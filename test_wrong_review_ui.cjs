// Disposable synthetic family only. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL,
// FAMILY_TEST_PYTHON and WRONG_UI_PROOF_DIR; no real accounts or model calls.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const net = require('node:net');
const fs = require('node:fs/promises');
const path = require('node:path');
const {setTimeout: delay} = require('node:timers/promises');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function eventually(check, label, timeout = 12000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) { if (await check()) return; await delay(50); }
  throw Error('Timed out: ' + label);
}

async function server() {
  const socket = net.createServer();
  socket.listen(0, '127.0.0.1');
  await once(socket, 'listening');
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  const env = {...process.env};
  for (const k of Object.keys(env)) if (k.startsWith('FAMILY_')) delete env[k];
  const launch = `import app, runpy, sys
app.family_llm.configuration=lambda *a,**k:('https://example.invalid','synthetic')
import family_wrong_questions as fwq
def annotate(images, subject_hint='', timeout=90, **kw):
    assert 1 <= len(images) <= 3
    return {'pages': [
      {'page': 1, 'regions': [
        {'kind':'layout','box':{'x':10,'y':5,'w':900,'h':70},'label':'卷头','text':'虚构数学小测','answer':'','correction':'','uncertain':False},
        {'kind':'wrong_item','box':{'x':30,'y':200,'w':700,'h':120},'label':'第2题','text':'42 - 17 =','answer':'35','correction':'25','uncertain':False},
        {'kind':'wrong_item','box':{'x':30,'y':430,'w':690,'h':120},'label':'第4题','text':'81 ÷ 9 =','answer':'8','correction':'9','uncertain':True,'topic_hint':'整除','error_hint':'商算错'},
      ]},
      {'page': 2, 'regions': [
        {'kind':'wrong_item','box':{'x':40,'y':500,'w':400,'h':150},'label':'第3题','text':'chuāng wài','answer':'窗处','correction':'窗外','uncertain':True},
      ]}], 'uncertainties': ['第2页转写请对照原图']}
fwq.annotate_pages = annotate
sys.argv = ['demo.py', '--port', sys.argv[1]]
runpy.run_path('demo.py', run_name='__main__')`;
  const child = spawn(process.env.FAMILY_TEST_PYTHON || 'python3', ['-c', launch, String(port)],
    {cwd: __dirname, env, stdio: ['ignore', 'pipe', 'pipe']});
  let err = '';
  child.stdout.resume();
  child.stderr.on('data', b => err += String(b));
  const url = 'http://127.0.0.1:' + port + '/';
  const stop = async () => {
    if (child.exitCode !== null || child.signalCode !== null) return;
    const end = once(child, 'exit');
    child.kill('SIGINT');
    await Promise.race([end, delay(2500)]);
    if (child.exitCode === null && child.signalCode === null) { child.kill('SIGKILL'); await end; }
  };
  try {
    await eventually(async () => {
      if (child.exitCode !== null) throw Error(err || 'Demo exited');
      try { return (await fetch(url, {signal: AbortSignal.timeout(400)})).ok; } catch { return false; }
    }, 'synthetic server');
    return {url, stop};
  } catch (e) { await stop(); throw e; }
}

const png = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64');

async function fit(p) {
  assert.equal(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
}
async function proof(p, name) {
  if (process.env.WRONG_UI_PROOF_DIR) {
    await fs.mkdir(process.env.WRONG_UI_PROOF_DIR, {recursive: true});
    await p.screenshot({path: path.join(process.env.WRONG_UI_PROOF_DIR, name + '.png'), fullPage: true});
  }
}

(async () => {
  let browser;
  const checks = [];
  try {
    browser = await chromium.launch({headless: true,
      ...(process.env.PLAYWRIGHT_CHANNEL ? {channel: process.env.PLAYWRIGHT_CHANNEL} : {})});
    for (const width of [360, 1440]) {
      // 每个宽度使用独立的临时家庭与演示服务，避免上传池和记录跨轮累积。
      const host = await server();
      const p = await browser.newPage({viewport: {width, height: 900}});
      const errors = [];
      p.on('pageerror', e => errors.push(e.message));
      try {
        await p.goto(host.url);
        await p.locator('nav [data-page="more"]').click();
        await p.locator('.more-links [data-page="wrong"]').click();
        await p.locator('[data-wrong-annotate]').waitFor();
        await fit(p);

        // 未选孩子不能标注
        await p.locator('[data-wrong-annotate]').click();
        await eventually(async () => /请先选择孩子/.test(await p.locator('[data-wrong-error]').innerText()), 'child required');

        const initial = await (await fetch(host.url + 'api/state')).json();
        const childName = initial.children[0].name;
        await p.locator('[data-wrong-child]').selectOption({label: childName});

        // 上传两张合成照片（真实 /api/upload）
        await p.locator('[data-wrong-pick]').setInputFiles([
          {name: 'synthetic-1.png', mimeType: 'image/png', buffer: png},
          {name: 'synthetic-2.png', mimeType: 'image/png', buffer: png},
        ]);
        await eventually(async () => await p.locator('[data-wrong-pool] input:checked').count() === 2,
          'two uploaded photos auto-selected');
        const checked = await p.locator('[data-wrong-pool] input:checked').count();
        assert.equal(checked, 2, 'new uploads auto-selected');
        await fit(p);
        await proof(p, 'wrong-upload-' + width);

        // 模型失败时提示且不丢选择
        await p.route('**/api/wrong/annotate', r => r.fulfill({status: 503,
          contentType: 'application/json', body: JSON.stringify({error: '虚构标注暂不可用'})}));
        await p.locator('[data-wrong-annotate]').click();
        await eventually(async () => /虚构标注暂不可用/.test(await p.locator('[data-wrong-error]').innerText()),
          'annotate failure shown');
        await p.unroute('**/api/wrong/annotate');

        // 真实（合成）标注：3 个错题卡、3 个错题红框 + 1 个版面绿框
        await p.locator('[data-wrong-annotate]').click();
        await eventually(async () => await p.locator('.wrong-item').count() === 3, 'three wrong-item cards');
        assert.equal(await p.locator('.wrong-box').count(), 4, 'boxes for all regions');
        assert.match(await p.locator('.wrong-uncertain').innerText(), /对照原图/);
        assert.equal(await p.locator('[data-wrong-keep]:checked').count(), 3, 'all kept by default');
        await fit(p);
        await proof(p, 'wrong-annotated-' + width);

        // 编辑题面、取消一条勾选
        const first = p.locator('.wrong-item').first();
        await first.locator('[data-wrong-field="text"]').fill('42 - 17 = （家长已核对）');
        await first.locator('[data-wrong-keep]').uncheck();
        await p.locator('.wrong-item').nth(1).locator('[data-wrong-field="note"]').fill('先让孩子讲错在哪');

        const kept = p.locator('.wrong-item').nth(1), last = p.locator('.wrong-item').nth(2);
        assert.equal(await kept.locator('[data-wrong-field="topic_hint"]').inputValue(), '整除');
        assert.equal(await kept.locator('[data-wrong-field="error_hint"]').inputValue(), '商算错');
        assert.equal(await last.locator('[data-wrong-field="topic_hint"]').inputValue(), '', 'old untagged model response');
        await kept.locator('[data-wrong-field="topic_hint"]').fill('除法口诀');
        await kept.locator('[data-wrong-field="error_hint"]').fill('口诀混淆');
        for (const field of ['topic_hint', 'error_hint']) {
          await last.locator('[data-wrong-field="'+field+'"]').fill('删除这个候选');
          await last.locator('[data-wrong-field="'+field+'"]').fill('');
        }
        // 各字段合法但整条过长：后一条失败不能使前一条被保存，原输入须保留。
        await last.locator('[data-wrong-field="text"]').fill('题'.repeat(2000));
        await last.locator('[data-wrong-field="answer"]').fill('答'.repeat(1000));
        await last.locator('[data-wrong-field="correction"]').fill('正'.repeat(1000));
        await p.locator('[data-wrong-save]').click();
        await eventually(async () => /第2条错题总内容超过4000字/.test(await p.locator('[data-wrong-save-error]').innerText()), 'whole batch rejected');
        assert.equal((await (await fetch(host.url+'api/state')).json()).records.filter(r=>r.source==='错题照片核对').length, 0);
        assert.equal(await last.locator('[data-wrong-field="text"]').inputValue(), '题'.repeat(2000));
        assert.equal(await last.locator('[data-wrong-field="correction"]').inputValue(), '正'.repeat(1000));
        assert.equal(await kept.locator('[data-wrong-field="topic_hint"]').inputValue(), '除法口诀');
        assert.equal(await last.locator('[data-wrong-field="error_hint"]').inputValue(), '');
        await fit(p);
        const errorBox = await p.locator('[data-wrong-save-error]').boundingBox();
        assert(errorBox && errorBox.y >= 0 && errorBox.y < 900, 'save error visible beside submit');
        await proof(p, 'wrong-length-error-' + width);
        await last.locator('[data-wrong-field="text"]').fill('chuāng wài');
        await last.locator('[data-wrong-field="answer"]').fill('窗处');
        await last.locator('[data-wrong-field="correction"]').fill('窗外');

        // 保存勾选的 2 条
        p.once('dialog', d => d.dismiss());
        await p.locator('[data-wrong-save]').click();
        await eventually(async () => await p.locator('.wrong-saved').count() === 1, 'saved notice');
        await eventually(async () => {
          const state = await (await fetch(host.url + 'api/state')).json();
          const recs = state.records.filter(r => r.source === '错题照片核对');
          return recs.length === 2 &&
                 recs.every(r => r.category === '学习进展' && r.attachments.length === 1) &&
                 recs.some(r => /家长已核对/.test(r.note)) &&
                 recs.some(r => /先让孩子讲错在哪/.test(r.note));
        }, 'two review records persisted');
        await fit(p);
        await proof(p, 'wrong-saved-' + width);
        assert.equal(await p.locator('.wrong-saved [data-record]').count(),2);
        await p.locator('.wrong-saved [data-record]').first().click();
        await p.locator('#recordDialog[open]').waitFor();
        assert.equal(await p.locator('#recordTaskLink').isVisible(),true);
        assert.equal(await p.locator('#recordForm [name=source]').inputValue(),'错题照片核对');
        await p.keyboard.press('Escape');

        const persisted = (await (await fetch(host.url+'api/state')).json()).records.filter(r=>r.source==='错题照片核对');
        const tagged = persisted.find(r=>r.title.includes('第4题'));
        assert(tagged.note.includes('知识点（家长核对）：除法口诀'));
        assert(tagged.note.includes('错误类型（家长核对）：口诀混淆'));
        assert(!persisted.find(r=>r.title.includes('第3题')).note.includes('（家长核对）'));
        await p.reload();
        await p.locator('nav [data-page="more"]').click();
        await p.locator('.more-links [data-page="growth"]').click();
        await p.locator('[data-record="'+tagged.id+'"]').click();
        assert.equal(await p.locator('#recordForm [name="note"]').inputValue(), tagged.note);
        await fit(p);
        await proof(p, 'wrong-reopened-' + width);
        assert.deepEqual(errors, []);
        checks.push({width, parentReview: true, upload: true, failureRetry: true,
          boxesAndCards: true, editAndDrop: true, candidateEditClear: true, wholeBatchLengthGuard: true, persisted: true, reopen: true, noOverflow: true});
        await p.close();
      } catch (e) {
        await proof(p, 'wrong-failure-' + width);
        await p.close();
        throw e;
      } finally {
        await host.stop();
      }
    }
    console.log(JSON.stringify(checks));
  } finally {
    if (browser) await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
