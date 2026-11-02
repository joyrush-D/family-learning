// P3: the same homework with no saved feedback → a direct hand-noted / whole-photo wrong item → correction → reopen, from the real home-list entry.
// Disposable synthetic family only. Optional PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON and DIRECT_WRONG_UI_PROOF_DIR; no model calls.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {randomUUID} = require('node:crypto');
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
async function fit(p) { assert.equal(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth), false); }
async function proof(p, name) {
  if (!process.env.DIRECT_WRONG_UI_PROOF_DIR) return;
  await fs.mkdir(process.env.DIRECT_WRONG_UI_PROOF_DIR, {recursive: true});
  await p.screenshot({path: path.join(process.env.DIRECT_WRONG_UI_PROOF_DIR, name + '.png'), fullPage: true});
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? {channel: process.env.PLAYWRIGHT_CHANNEL} : {})});
    for (const width of [360, 1440]) {
      const host = await server();
      const p = await browser.newPage({viewport: {width, height: 900}});
      const errors = [];
      p.on('pageerror', e => errors.push(e.message));
      try {
        const state = async () => (await fetch(host.url + 'api/state')).json();
        const first = await state(), [a, b] = first.children;
        const make = async (child, title) => {
          const r = await fetch(host.url + 'api/task/new', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Family-Token': first.token},
            body: JSON.stringify({request_key: randomUUID(), child, title, category: 'homework', box: 'inbox', due: first.today, action: '完成虚构口算第1至5题'})});
          assert.equal(r.status, 200); return (await r.json()).task.id;
        };
        const id = await make(a.name, `虚构同名口算 ${width}`), sibling = await make(b.name, `虚构同名口算 ${width}`);
        const wrongOf = async () => (await state()).records.filter(r => r.source === '错题照片核对');
        assert.equal((await state()).records.length, 0, 'no feedback is pre-made');

        await p.goto(host.url);
        const chip = p.locator(`[data-child-filter="${a.id}"]`);
        if (await chip.count() && await chip.first().getAttribute('aria-pressed') !== 'true') await chip.first().click();
        await p.locator(`[data-task="${id}"]`).first().click();
        await p.locator('#taskDialog[open]').waitFor();
        let panel = p.locator('[data-task-wrong-form="direct"]');
        await panel.locator('summary').click();
        await panel.locator('[data-task-wrong-save="direct"]').click();
        await eventually(async () => /至少写/.test(await panel.locator('[data-task-wrong-status]').innerText()), 'an empty item is refused');
        assert.equal((await wrongOf()).length, 0);

        // Text only, original answer known, correction unknown; the first reply is lost after the server saved it.
        await panel.locator('[data-wrong-field="label"]').fill('第3题');
        await panel.locator('[data-wrong-field="answer"]').fill('45');
        let calls = 0;
        await p.route('**/api/wrong/save', async route => { if (calls++ === 0) { await route.fetch(); return route.abort('failed'); } return route.continue(); });
        await panel.locator('[data-task-wrong-save="direct"]').click();
        await eventually(async () => /结果尚未核对/.test(await panel.locator('[data-task-wrong-status]').innerText()), 'a lost receipt keeps the same request');
        assert.equal((await wrongOf()).length, 1, 'the server saved once');
        await panel.locator('[data-task-wrong-save="direct"]').click();
        await eventually(async () => /错题已保存在这份作业下/.test(await p.locator('#taskFeedbackStatus').innerText()), 'the retry confirms the same record');
        await p.unroute('**/api/wrong/save');
        let wrong = await wrongOf();
        assert.equal(wrong.length, 1, 'the same key stores one item');
        assert.deepEqual([wrong[0].linked_task_id, wrong[0].related_record_id ?? null, wrong[0].attachments], [id, null, []]);
        assert.equal((await state()).records.length, 1, 'no placeholder feedback');
        const textItem = wrong[0];

        // One whole photo with only a question number.
        panel = p.locator('[data-task-wrong-form="direct"]');
        await panel.locator('summary').click();
        await panel.locator('[data-task-wrong-file]').setInputFiles({name: 'synthetic-direct.png', mimeType: 'image/png', buffer: png});
        await panel.locator('[data-wrong-field="label"]').fill('第5题');
        await panel.locator('[data-task-wrong-save="direct"]').click();
        await eventually(async () => (await wrongOf()).length === 2, 'the photo item is saved');
        wrong = await wrongOf();
        const photoItem = wrong.find(r => r.id !== textItem.id);
        assert.equal(photoItem.attachments.length, 1);
        assert.deepEqual([photoItem.linked_task_id, photoItem.related_record_id ?? null, !!photoItem.wrong_region], [id, null, false]);
        assert.equal((await state()).uploads.filter(u => u.name === 'synthetic-direct.png').length, 1, 'one original');
        assert.match(await p.locator('#taskFeedbackHistory').innerText(), /第3题[\s\S]*|第5题/);
        await fit(p);
        await proof(p, `direct-wrong-${width}`);

        // Correction from the same card inherits the original task.
        await p.locator(`#taskFeedbackHistory [data-followup="${textItem.id}"]`).first().click();
        await p.locator('#recordDialog[open]').waitFor();
        await p.locator('#recordForm [name=note]').fill('虚构：孩子订正为35。');
        await p.locator('#recordForm button[type=submit]').first().click();
        await eventually(async () => (await state()).records.some(r => r.followup_kind === '订正'), 'the correction is saved');
        const correction = (await state()).records.find(r => r.followup_kind === '订正');
        assert.deepEqual([correction.related_record_id, correction.linked_task_id], [textItem.id, id]);

        // Reopen: same task, same records; the other child's same-named homework stays empty.
        await p.reload();
        await p.locator(`[data-task="${id}"]`).first().click();
        await p.locator('#taskDialog[open]').waitFor();
        const history = await p.locator('#taskFeedbackHistory').innerText();
        for (const text of ['第3题', '第5题', '虚构：孩子订正为35。']) assert.ok(history.includes(text), text);
        assert.equal((await state()).records.filter(r => r.linked_task_id === sibling).length, 0);
        assert.equal((await state()).records.length, 3);
        await fit(p);
        await proof(p, `direct-wrong-reopen-${width}`);
        assert.deepEqual(errors, []);
      } finally { await p.close(); await host.stop(); }
    }
    console.log('direct wrong UI: 360/1440 passed');
  } finally { if (browser) await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
