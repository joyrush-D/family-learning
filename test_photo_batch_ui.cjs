// Batch photo import, Web entry (PRD 5.1 W1). Disposable synthetic family only; fixed raw model replies pass the real
// annotate/grouping/review validators. The backend round is the product's own family_agent.run_once on the demo data.
// Optional PLAYWRIGHT_MODULE, FAMILY_TEST_PYTHON and PHOTO_BATCH_UI_PROOF_DIR; no real accounts, files or model calls.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const net = require('node:net');
const fs = require('node:fs/promises');
const path = require('node:path');
const {setTimeout: delay} = require('node:timers/promises');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const PNG_HEX = '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000100ffff03000006000557bfab440000000049454e44ae426082';
const page_bytes = tag => Buffer.concat([Buffer.from(PNG_HEX, 'hex'), Buffer.from('synthetic-' + tag)]);

async function eventually(check, label, timeout = 20000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) { if (await check()) return; await delay(100); }
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
  const launch = `import app, base64, json, runpy, sys, threading, time
import family_agent, family_llm, family_photo_batch as fpb, family_wrong_questions as fwq
family_llm.configuration = lambda *a, **k: ('https://example.invalid', 'synthetic')
PNG = bytes.fromhex('${PNG_HEX}')
TAGS = {PNG + b'synthetic-' + t.encode(): t for t in ('m1', 'm2', 'c1')}
def ev(subject, title, printed):
    return dict(subject=subject, subject_basis='题面内容', title=title, printed_page=printed, first_label='第1题', last_label='第5题',
                head='虚构开头', tail='虚构结尾', page_kind='answered', readability='clear')
def reg(label, y):
    return dict(kind='wrong_item', box=dict(x=100, y=y, w=600, h=150), label=label, text='虚构题面', answer='35', correction='', uncertain=False)
PAGES = {'m1': (ev('数学', '虚构数学练习', '1'), [reg('第2题', 200)]), 'm2': (ev('数学', '虚构数学练习', '2'), [reg('第4题', 400)]),
         'c1': (ev('语文', '虚构语文小测', '1'), [reg('第2题', 300)])}
failed_group = []
def item(label, question, said, ref, judgment, reason='', uncertainty=''):
    return dict(label=label, question=question, student_answer=said, answer=ref, judgment=judgment, error_reason=reason,
                possible_cause='', steps='按参考订正' if judgment == 'incorrect' else '', uncertainty=uncertainty, question_kind='objective')
def fake(messages, schema, name, timeout=60, *, data_path=None):
    tags = [TAGS[base64.b64decode(p['image_url']['url'].split(',', 1)[1])] for m in messages if isinstance(m['content'], list)
            for p in m['content'] if p.get('type') == 'image_url']
    if name == fwq.TASK_NAME:
        return dict(pages=[dict(page=i, regions=PAGES[t][1], evidence=PAGES[t][0]) for i, t in enumerate(tags, 1)], uncertainties=[])
    if name == fpb.GROUP_TASK:
        if not failed_group:
            failed_group.append(1)
            raise family_llm.LLMDraftError('虚构：组卷请求暂时失败')
        return dict(papers=[dict(subject='数学', title='虚构数学练习', basis='同标题、印刷页码1–2',
                                 pages=[dict(page_id='p03', order=1, role='answered'), dict(page_id='p01', order=2, role='answered')]),
                            dict(subject='语文', title='虚构语文小测', basis='语文题面', pages=[dict(page_id='p02', order=1, role='answered')])],
                    pending=[], same_pages=[])
    if name != 'family_homework_reference':
        raise family_llm.LLMDraftError('虚构：本测试不提供其他模型任务')
    items = ([item('第2题', '看拼音写词语 chuāng wài', '窗处', '窗外', 'incorrect', '“外”写成“处”')] if 'c1' in tags else
             [item('第2题', '42 - 17 =', '35', '25', 'incorrect', '退位减法算错'), item('第4题', '81 ÷ 9 =', '9', '9', 'correct'),
              item('第5题', '虚构应用题', '', '12', 'unknown', uncertainty='答题格空白')])
    return dict(items=items, coverage='虚构覆盖', question_labels=[i['label'] for i in items])
family_llm._chat_json = fake
def backend():
    # The product backend round as its LaunchAgent runs it, only once the demo has switched to its temporary data.
    while True:
        time.sleep(0.4)
        if 'family-demo-' not in str(app.DATA): continue
        try: family_agent.run_once(app)
        except Exception as error: print('round error', repr(error), file=sys.stderr, flush=True)
threading.Thread(target=backend, daemon=True).start()
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
    return {url, stop, errors: () => err};
  } catch (e) { await stop(); throw e; }
}

async function fit(p) {
  assert.equal(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'no horizontal overflow');
}
async function proof(p, name) {
  if (!process.env.PHOTO_BATCH_UI_PROOF_DIR) return;
  await fs.mkdir(process.env.PHOTO_BATCH_UI_PROOF_DIR, {recursive: true});
  await p.screenshot({path: path.join(process.env.PHOTO_BATCH_UI_PROOF_DIR, name + '.png'), fullPage: true});
}
async function openWrong(p) {
  await p.locator('nav [data-page="more"]').click();
  await p.locator('.more-links [data-page="wrong"]').click();
  await p.locator('[data-batch-pick]').waitFor({state: 'attached'});
}
const batchView = (p, id) => p.evaluate(async id => (await (await fetch('/api/photo-batch?id=' + id)).json()), id);

(async () => {
  let browser;
  const checks = [];
  try {
    browser = await chromium.launch({headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined});
    for (const width of [360, 1440]) {
      const host = await server();
      const p = await browser.newPage({viewport: {width, height: 900}});
      try {
        await p.goto(host.url);
        await openWrong(p);
        assert.equal(await p.locator('[data-wrong-annotate]').count(), 1, 'the single-photo review stays available');
        await fit(p);
        // The first registration receipt is lost after the server stored it; the page asks again with the same key.
        let lost = 0;
        await p.route('**/api/photo-batch/create', async route => {
          if (lost++) return route.continue();
          const response = await route.fetch();
          await response.body();
          return route.abort('connectionreset');
        });
        await p.locator('[data-batch-pick]').setInputFiles(['m2', 'c1', 'm1'].map(t => ({name: t + '.png', mimeType: 'image/png', buffer: page_bytes(t)})));
        await eventually(async () => /同一提交标识/.test(await p.locator('[data-batch-status]').innerText()), 'lost receipt re-queried with the same key');
        assert.equal(lost, 2, 'one lost receipt, one same-key query');
        assert.equal(await p.locator('.pb-batch').count(), 1, 'no second batch');
        // The backend round hits the fictional grouping failure: kept, not retried, continued explicitly.
        await eventually(async () => await p.locator('[data-batch-continue]').count() === 1, 'failed step offered to continue');
        assert.match(await p.locator('.pb-failed').innerText(), /组卷请求暂时失败/);
        await p.locator('[data-batch-continue]').click();
        await eventually(async () => await p.locator('.pb-batch[data-batch-state="done"] .pb-paper').count() === 2, 'per-paper results', 30000);
        const id = await p.locator('.pb-batch').getAttribute('data-batch-id');
        const math = p.locator('.pb-paper').filter({hasText: '数学 · 虚构数学练习'});
        const chinese = p.locator('.pb-paper').filter({hasText: '语文 · 虚构语文小测'});
        assert.match(await math.innerText(), /2页 · AI判错1处 · 疑似0处 · 未判定1题 · 与参考一致1题/);
        assert.match(await math.innerText(), /没有错题不代表全卷正确/);
        assert.match(await chinese.innerText(), /AI判错1处/);
        const done = await batchView(p, id);
        assert.deepEqual(done.papers.find(x => x.subject === '数学').pages.map(x => x.page_id), ['p03', 'p01'], 'model page order, not import order');
        const calls = done.progress.calls;
        assert.equal(calls, 5, '1 read + failed group + group + 2 checks');
        // Open the math wrong question: the original image with its whole-question box, original answer, basis, AI signature.
        const question = math.locator('.pb-q[data-state="wrong"]');
        await question.locator('[data-batch-open]').click();
        await question.locator('[data-batch-box]').waitFor();
        const body = await question.innerText();
        for (const text of ['原答 35', '参考 25', '依据 退位减法算错', '署名：AI判断，未经老师或家长核定', '已记入错题（AI判断）']) assert.ok(body.includes(text), text);
        assert.match(await question.locator('[data-batch-box]').getAttribute('style'), /left:10%;top:20%;width:60%;height:15%/);
        assert.equal(await math.locator('.pb-q[data-state="unknown"]').count(), 1, 'the blank answer stays unknown');
        await fit(p);
        await proof(p, 'photo-batch-result-' + width);
        // 订正 through the original follow-up chain, then reopen the same paper after a reload.
        await question.locator('[data-followup]').click();
        await p.locator('#recordDialog[open]').waitFor();
        assert.match(await p.locator('#relationTitle').innerText(), /数学错题：第2题/);
        await p.locator('#recordForm [name="note"]').fill('虚构订正：重新计算个位，得25');
        await p.locator('#recordForm button[type="submit"].primary').click();
        await eventually(async () => await p.locator('#recordDialog[open]').count() === 0, 'correction saved');
        await p.reload();
        await openWrong(p);
        const again = p.locator('.pb-paper').filter({hasText: '数学 · 虚构数学练习'}).locator('.pb-q[data-state="wrong"]');
        await again.locator('[data-batch-open]').click();
        await eventually(async () => /订正 \d{4}-\d{2}-\d{2}/.test(await again.innerText()), 'the correction shows on the reopened paper');
        await again.locator('[data-batch-box]').waitFor();
        await delay(1500);
        assert.equal((await batchView(p, id)).progress.calls, calls, 'reopening and refreshing make no model call');
        await fit(p);
        await proof(p, 'photo-batch-reopened-' + width);
        assert.doesNotMatch(host.errors(), /round error/, host.errors());
        checks.push({width, batch: id, calls, papers: 2, lost_receipt_requery: true, continued_failed_step: true, correction_reopened: true});
        await p.close();
      } catch (e) {
        await proof(p, 'photo-batch-failure-' + width);
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
