// 已被 assert_plan_lines_ui.cjs 取代（2026-11-04 16:0x）：本脚本硬编码了 surface 播种的语文家庭安排句子
//   （「林老师布置的那项朗读」）和 SURFACE_EXPECT_PLAN_DATE，只适用于本任务的种子数据；
//   换一份 payload 会误报“家庭安排不在清单卡里”。通用校验请用同目录 assert_plan_lines_ui.cjs
//   （期望值全部从 /api/day 取，校验 [data-grove-plan="1"] + [data-grove-plan-lines] 与详情 section li 逐条相等）。
// 一起成长 · 日清单展示修复的网页验收（headless Chrome，全虚构数据）。
// 用法：
//   PLAYWRIGHT_MODULE=<playwright> SURFACE_BASE=http://127.0.0.1:8791 \
//   SURFACE_OUT=<证据目录>/after SURFACE_FAKE_PLAN=1 node verify_ui.cjs
//   - SURFACE_FAKE_PLAN=1：把 /api/state 响应里「家庭安排（计划 …）：…」从 lines 拆到 plan_lines，
//     用于投影（projection）尚未落地时先验收客户端契约；投影落地后用默认值 0 对真实 payload 复核。
//   - SURFACE_EXPECT_CLEAN=1：要求正文不含「提交要求：」「补充要求：」（投影落地后的契约）。
// 产物：<OUT>/wNNN-home-full.png（整页）、wNNN-card-<i>-<title>.txt（每张卡 innerText）、report.json、断言日志。
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const BASE = process.env.SURFACE_BASE || 'http://127.0.0.1:8791';
const OUT = process.env.SURFACE_OUT || '/tmp/surface-after';
const WIDTHS = (process.env.SURFACE_WIDTHS || '360,1440').split(',').map(Number);
const FAKE_PLAN = process.env.SURFACE_FAKE_PLAN === '1';
const EXPECT_CLEAN = process.env.SURFACE_EXPECT_CLEAN === '1';
const SEED_TITLES = (process.env.SURFACE_SEED_TITLES || '英语：完成《每日练习》|语文：朗读《风经过小巷》第2、3自然段|数学：完成《每日练习》第26页第1—3题').split('|');
// 计划日（item.facts 里 role=scheduled 的 value）：有值时家庭安排标签必须写成「家庭安排（计划 <日期>）」。
const PLAN_DATE = process.env.SURFACE_EXPECT_PLAN_DATE || '';
const PLAN_LABEL = PLAN_DATE ? `家庭安排（计划 ${PLAN_DATE}）` : '家庭安排';

const failures = [];
const notes = [];
function ok(cond, msg) { if (!cond) failures.push(msg); else console.log('ok   - ' + msg); }
function note(msg) { notes.push(msg); console.log('note - ' + msg); }

async function getState() {
  const r = await fetch(BASE + '/api/state');
  return await r.json();
}

// 仅用于投影未落地时的客户端契约演练：把家庭安排那一行从 lines 挪进 plan_lines（保留原句去掉「家庭安排（计划…）：」外壳）。
function applyFakePlan(state) {
  const moved = [];
  for (const child of state.children || []) {
    const view = state.today_view?.[child.id];
    if (!view || !Array.isArray(view.groups)) continue;
    for (const g of view.groups) for (const it of g.items || []) {
      const lines = Array.isArray(it.lines) ? it.lines : [];
      const plan = lines.filter(l => /^家庭安排（计划 [^）]*）：/.test(l));
      if (!plan.length) continue;
      it.lines = lines.filter(l => !plan.includes(l));
      it.plan_lines = plan.map(l => l.replace(/^家庭安排（计划 [^）]*）：\s*/, '')).filter(Boolean);
      moved.push({ id: it.id, title: it.title, plan_lines: it.plan_lines });
    }
  }
  return moved;
}

function fakeRoute(state) {
  return JSON.stringify(state);
}

function planIsExpected(state) {
  if (FAKE_PLAN) return true;
  for (const child of state.children || []) {
    const view = state.today_view?.[child.id];
    for (const g of view?.groups || []) for (const it of g.items || []) if (Array.isArray(it.plan_lines) && it.plan_lines.length) return true;
  }
  return false;
}

async function runWidth(browser, width, state, planExpected, seedTitles) {
  const tag = 'w' + width;
  const errors = [];
  const writes = [];
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', req => { if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method()) && req.url().startsWith(BASE)) writes.push(req.method() + ' ' + req.url()); });
  if (FAKE_PLAN) {
    await page.route('**/api/state', async route => route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: fakeRoute(state) }));
    await page.route('**/api/day**', async route => {
      // 日清单首页不读 /api/day；这里兜底只在真实请求时放行（不伪造跨日数据）。
      route.continue();
    });
  }
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForSelector('body[data-page="home"]', { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector('#content')?.dataset.ready === 'true', { timeout: 20000 });
  await page.waitForTimeout(400);

  await page.screenshot({ path: path.join(OUT, `${tag}-home-full.png`), fullPage: true });

  const bodyText = await page.locator('body').innerText();
  const contentText = await page.locator('#content').innerText();
  fs.writeFileSync(path.join(OUT, `${tag}-content.txt`), contentText);

  ok(!/。；/.test(bodyText), `${tag} 正文不出现「。；」机械拼接`);
  ok(!/；；/.test(bodyText), `${tag} 正文不出现「；；」重复分隔符`);
  for (const t of seedTitles) ok(contentText.includes(t), `${tag} 今天的清单包含播种标题：${t}`);

  // 每张卡另存 innerText（只存今天清单里的行卡，不含隐藏分区）。
  const rows = page.locator('.grove-row:visible');
  const rowCount = await rows.count();
  const cards = [];
  for (let i = 0; i < rowCount; i++) {
    const el = rows.nth(i);
    const text = await el.innerText();
    const title = await el.locator('.grove-title').innerText().catch(() => '');
    cards.push({ i, title, text });
    const safe = String(title || 'card').replace(/[^\p{Script=Han}A-Za-z0-9]+/gu, '-').slice(0, 40);
    fs.writeFileSync(path.join(OUT, `${tag}-card-${i}-${safe}.txt`), text);
  }
  const seededRows = cards.filter(c => seedTitles.some(t => c.text.includes(t)));
  ok(seededRows.length === seedTitles.length, `${tag} 播种的 ${seedTitles.length} 张卡都在清单里（实得 ${seededRows.length} 张，共 ${rowCount} 张可见卡）`);

  if (EXPECT_CLEAN) {
    ok(!contentText.includes('提交要求：'), `${tag} 正文不含「提交要求：」`);
    ok(!contentText.includes('补充要求：'), `${tag} 正文不含「补充要求：」`);
  } else {
    note(`${tag} 未要求「提交要求/补充要求」清零（投影未落地时旧 payload 仍带这些行）`);
  }

  // 家庭安排：要求正文里不能混进家庭安排；作为独立块（列表卡小标签 + 详情独立小节）出现。
  const planCards = cards.filter(c => c.text.includes('林老师布置的那项朗读'));
  if (planExpected) {
    ok(planCards.length >= 1, `${tag} 家庭安排出现在清单卡片里`);
    for (const c of planCards) {
      const planText = await rows.nth(c.i).locator('[data-grove-plan-lines]').innerText().catch(() => '');
      const requirement = await rows.nth(c.i).locator('.grove-lines:not([data-grove-plan-lines])').innerText().catch(() => '');
      ok(planText.includes('林老师布置的那项朗读'), `${tag} 家庭安排卡有自己的 ${'[data-grove-plan-lines]'} 块`);
      const planLabel = await rows.nth(c.i).locator('[data-grove-plan="1"]').innerText().catch(() => '');
      ok(planLabel === PLAN_LABEL, `${tag} 列表块标签写作「${PLAN_LABEL}」（实得「${planLabel}」）`);
      ok(!requirement.includes('林老师布置的那项朗读'), `${tag} 家庭安排卡的要求段里没有家庭安排句子`);
      // 打开这一项的详情：独立小节在要求列表之后。
      await rows.nth(c.i).locator('[data-grove-open]').click();
      await page.waitForTimeout(300);
      const detail = page.locator('#groveDetail');
      ok(await detail.locator('[data-grove-plan-lines]').count() > 0, `${tag} 详情有「家庭安排」独立小节`);
      fs.writeFileSync(path.join(OUT, `${tag}-plan-detail.txt`), await detail.innerText());
      await page.screenshot({ path: path.join(OUT, `${tag}-plan-detail.png`), fullPage: true });
      const detailText = await detail.innerText();
      ok(/家庭安排/.test(detailText), `${tag} 详情的小节标题写「家庭安排」`);
      const detailLabel = await detail.locator('[data-grove-plan-lines] h3').innerText().catch(() => '');
      ok(detailLabel === PLAN_LABEL, `${tag} 详情小节标题写作「${PLAN_LABEL}」（实得「${detailLabel}」）`);
      const reqSection = await detail.locator('section', { hasText: '要做什么与完成标准' }).innerText().catch(() => '');
      ok(!reqSection.includes('林老师布置的那项朗读'), `${tag} 详情的要求小节里没有家庭安排句子`);
      const back = page.locator('[data-grove-back]:visible');
      if (await back.count()) { await back.first().click(); await page.waitForTimeout(250); }
    }
  } else {
    note(`${tag} payload 尚无 plan_lines，家庭安排独立块未演练（等投影落地后用真实 payload 复核）`);
  }

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  ok(!overflow, `${tag} 无横向溢出`);
  ok(errors.length === 0, `${tag} 无 pageerror${errors.length ? '：' + errors.join(' | ') : ''}`);
  ok(writes.length === 0, `${tag} 无写请求${writes.length ? '：' + writes.join(' | ') : ''}`);

  const report = { base: BASE, width, tag, fakePlan: FAKE_PLAN, rowCount, cards: cards.map(c => ({ title: c.title, text: c.text })), overflow, errors, writes };
  fs.writeFileSync(path.join(OUT, `${tag}-report.json`), JSON.stringify(report, null, 2));
  await page.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const state = await getState();
  const moved = FAKE_PLAN ? applyFakePlan(state) : [];
  if (FAKE_PLAN) fs.writeFileSync(path.join(OUT, 'fake-plan-lines.json'), JSON.stringify(moved, null, 2));
  const planExpected = planIsExpected(state);
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  for (const width of WIDTHS) await runWidth(browser, width, state, planExpected, SEED_TITLES);
  await browser.close();
  const summary = { base: BASE, fakePlan: FAKE_PLAN, expectClean: EXPECT_CLEAN, planExpected, planDate: PLAN_DATE, failures, notes };
  fs.writeFileSync(path.join(OUT, 'assertions.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  if (failures.length) { console.error('ASSERTIONS FAILED: ' + failures.length); process.exit(1); }
  console.log('ASSERTIONS PASSED');
})().catch(e => { console.error('FAIL', e); process.exit(2); });
