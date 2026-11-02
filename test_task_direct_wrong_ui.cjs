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

// The current home list: the visible Grove row opens its detail, whose own action opens the task (no hidden old page, no direct calls).
async function openFromGrove(p, title, id) {
  const d = p.locator('#groveDetail');
  if (!await d.getByRole('heading', {name: title}).first().isVisible().catch(() => false))
    await p.locator('article.grove-row').filter({hasText: title}).first().locator('[data-grove-open]').click();
  await d.getByRole('heading', {name: title}).first().waitFor();
  await d.locator(`[data-task="${id}"]`).first().click();
  await p.locator('#taskDialog[open]').waitFor();
}
const shiftDay = (day, n) => new Date(Date.parse(day + 'T12:00:00Z') + n * 86400000).toISOString().slice(0, 10);

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
        // The demo family already holds its own records: they stay exactly as they were and never count toward this chain.
        const view = r => JSON.stringify([r.id, r.child, r.day, r.source, r.title, r.note, r.attachments, r.linked_task_id ?? '', r.related_record_id ?? null, r.followup_kind ?? '']);
        const prior = first.records.map(view);
        const make = async (child, title) => {
          const r = await fetch(host.url + 'api/task/new', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Family-Token': first.token},
            body: JSON.stringify({request_key: randomUUID(), child, title, category: 'homework', box: 'inbox', due: first.today, action: '完成虚构口算第1至5题'})});
          assert.equal(r.status, 200); return (await r.json()).task.id;
        };
        const title = `虚构同名口算 ${width}`, id = await make(a.name, title), sibling = await make(b.name, title);
        const linked = async taskId => (await state()).records.filter(r => r.linked_task_id === taskId || r.source === '事项:' + taskId);
        const wrongOf = async () => (await linked(id)).filter(r => r.source === '错题照片核对');
        assert.deepEqual(await linked(id), [], 'the target homework has no pre-made feedback or other record');
        const taskBefore = (await state()).tasks.find(t => t.id === id);
        const recordDay = first.today;  // the family server's today, never the browser clock

        await p.goto(host.url);
        const chip = p.locator(`[data-child-filter="${a.id}"]`);
        if (await chip.count() && await chip.first().getAttribute('aria-pressed') !== 'true') await chip.first().click();
        // The browser's own clock now reads another day; the record day must still be the family server's today.
        await p.clock.setFixedTime(new Date(`${shiftDay(first.today, 2)}T12:00:00+08:00`));
        assert.notEqual(await p.evaluate(() => new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Shanghai'}).format(new Date())), recordDay);
        await openFromGrove(p, title, id);
        let panel = p.locator('[data-task-wrong-form="direct"]');
        await panel.locator('summary').click();
        assert.ok((await panel.locator('[data-task-wrong-day]').innerText()).includes('记录日：' + recordDay), 'the record day is shown as Shanghai today');
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
        assert.deepEqual([wrong[0].linked_task_id, wrong[0].related_record_id ?? null, wrong[0].attachments, wrong[0].day], [id, null, [], recordDay]);
        assert.equal((await linked(id)).length, 1, 'no placeholder feedback on the target homework');
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
        assert.deepEqual([photoItem.linked_task_id, photoItem.related_record_id ?? null, !!photoItem.wrong_region, photoItem.day], [id, null, false, recordDay]);
        assert.equal((await state()).uploads.filter(u => u.name === 'synthetic-direct.png').length, 1, 'one original');
        const shown = await p.locator('#taskFeedbackHistory').innerText();
        assert.ok(shown.includes('第3题') && shown.includes('第5题'), 'both items show under the same homework');
        await fit(p);
        await proof(p, `direct-wrong-${width}`);

        // Correction from the same card inherits the original task.
        await p.locator(`#taskFeedbackHistory [data-followup="${textItem.id}"]`).first().click();
        await p.locator('#recordDialog[open]').waitFor();
        // Shared uploadFiles on the correction form: the first reply is lost after the server saved the original.
        const uploadKeys = [];
        let uploadCalls = 0;
        await p.route('**/api/upload', async route => {
          uploadKeys.push(route.request().headers()['x-request-key'] || '');
          if (uploadCalls++ === 0) { await route.fetch(); return route.abort('failed'); }
          return route.continue();
        });
        const correctionPhoto = {name: 'synthetic-correction.png', mimeType: 'image/png', buffer: png};
        await p.locator('#fileInput').setInputFiles(correctionPhoto);
        await eventually(async () => await p.locator('#retryUpload').isVisible(), 'a lost upload reply offers a retry');
        const savedOnce = (await state()).uploads.filter(u => u.name === 'synthetic-correction.png').map(u => u.id);
        assert.equal(savedOnce.length, 1, 'the server saved the original once');
        await p.locator('#retryUpload').click();
        await eventually(async () => !(await p.locator('#retryUpload').isVisible()), 'the retry settles');
        assert.deepEqual((await state()).uploads.filter(u => u.name === 'synthetic-correction.png').map(u => u.id), savedOnce, 'the retry returns the same original');
        assert.equal(uploadKeys.length, 2);
        assert.match(uploadKeys[0], /^[A-Za-z0-9_-]{16,64}$/);
        assert.equal(uploadKeys[1], uploadKeys[0], 'the retry of the same failed file reuses its request key');
        // A new, independent selection of the same name and bytes is a different original with a different key.
        await p.locator('#fileInput').setInputFiles(correctionPhoto);
        await eventually(async () => (await state()).uploads.filter(u => u.name === 'synthetic-correction.png').length === 2, 'a new selection is a new original');
        assert.equal(uploadKeys.length, 3);
        assert.notEqual(uploadKeys[2], uploadKeys[0]);
        await p.unroute('**/api/upload');
        await p.locator('#recordForm [name=note]').fill('虚构：孩子订正为35。');
        await p.locator('#recordForm button[type=submit]').first().click();
        await eventually(async () => (await linked(id)).some(r => r.followup_kind === '订正' && r.related_record_id === textItem.id), 'the correction is saved');
        const correction = (await linked(id)).find(r => r.followup_kind === '订正' && r.related_record_id === textItem.id);
        assert.deepEqual([correction.related_record_id, correction.linked_task_id], [textItem.id, id]);

        // Reopen: same task, same records; the other child's same-named homework stays empty; demo records untouched.
        await p.clock.setFixedTime(new Date());
        await p.reload();
        await openFromGrove(p, title, id);
        const history = await p.locator('#taskFeedbackHistory').innerText();
        for (const text of ['第3题', '第5题', '虚构：孩子订正为35。']) assert.ok(history.includes(text), text);
        assert.deepEqual(await linked(sibling), []);
        const final = await state();
        for (const kept of prior) assert.ok(final.records.some(r => view(r) === kept), 'demo record kept: ' + kept.slice(0, 60));
        assert.deepEqual(final.records.filter(r => !prior.includes(view(r))).map(r => r.id).sort((x, y) => x - y),
          [textItem.id, photoItem.id, correction.id].sort((x, y) => x - y), 'only the two wrong items and one correction are new');
        const taskAfter = final.tasks.find(t => t.id === id);
        for (const key of ['child', 'title', 'due', 'original_status', 'update']) assert.deepEqual(taskAfter[key], taskBefore[key], key);
        await fit(p);
        await proof(p, `direct-wrong-reopen-${width}`);
        assert.deepEqual(errors, []);
      } finally { await p.close(); await host.stop(); }
    }
    console.log('direct wrong UI: 360/1440 passed');
  } finally { if (browser) await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
