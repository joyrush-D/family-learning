// 「一起成长」日清单 · 家庭安排（plan_lines）展示断言（headless Chrome，全虚构数据）。
// 直接可跑：不依赖具体标题/文案，期望值全部从 /api/day 的 payload 取。
// 校验真实 DOM：
//   清单卡：卡内存在 [data-grove-plan="1"] 标签，且其后的 [data-grove-plan-lines] 逐行文本 === payload 的 plan_lines；
//          标签措辞 = facts 里 role=scheduled 的 value ?「家庭安排（计划 <value>）」:「家庭安排」；要求块不含家庭安排句子。
//   详情：  section[data-grove-plan-lines] 的 h3 与标签同措辞，li 逐条 === plan_lines；要求小节不含家庭安排句子。
// 另断言：正文无「。；」「；；」、无横向溢出、无 pageerror、无写请求；360/1440 各存整页与详情截图、卡片 txt。
// 用法：
//   PLAYWRIGHT_MODULE=<playwright 绝对路径> SURFACE_BASE=http://127.0.0.1:PORT \
//   SURFACE_OUT=<证据目录> node assert_plan_lines_ui.cjs
// 可选：SURFACE_WIDTHS=360,1440（默认）、PLAYWRIGHT_CHANNEL=chrome（默认 chrome）。
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const BASE = (process.env.SURFACE_BASE || 'http://127.0.0.1:8766').replace(/\/$/, '');
const OUT = process.env.SURFACE_OUT || '/tmp/plan-lines-ui';
const WIDTHS = (process.env.SURFACE_WIDTHS || '360,1440').split(',').map(Number);
const CHILD_ID = process.env.SURFACE_CHILD_ID || '';
const CHANNEL = process.env.PLAYWRIGHT_CHANNEL || 'chrome';

const failures = [];
function ok(cond, msg) { if (!cond) failures.push(msg); else console.log('ok   - ' + msg); }
const squash = s => String(s == null ? '' : s).replace(/\u00a0/g, ' ').replace(/\r/g, '').trim();
const linesOf = s => squash(s).split('\n').map(x => x.trim()).filter(Boolean);

async function fetchJson(p) {
  const r = await fetch(BASE + p);
  if (!r.ok) throw new Error(`GET ${p} -> ${r.status}`);
  return r.json();
}

function planLabelOf(item) {
  const f = (Array.isArray(item.facts) ? item.facts : []).find(x => x && x.role === 'scheduled');
  const v = f ? squash(f.value) : '';
  return v ? `家庭安排（计划 ${v}）` : '家庭安排';
}

async function runWidth(browser, width, childId, day, planItems) {
  const tag = 'w' + width;
  const errors = [];
  const writes = [];
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', req => { if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method()) && req.url().startsWith(BASE)) writes.push(req.method() + ' ' + req.url()); });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForSelector('body[data-page="home"]', { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector('#content')?.dataset.ready === 'true', { timeout: 20000 });
  await page.waitForTimeout(400);

  const bodyText = await page.locator('body').innerText();
  fs.writeFileSync(path.join(OUT, `${tag}-content.txt`), await page.locator('#content').innerText());
  ok(!/。；/.test(bodyText), `${tag} 正文不出现「。；」`);
  ok(!/；；/.test(bodyText), `${tag} 正文不出现「；；」`);

  const cards = [];
  const rows = page.locator('.grove-row:visible');
  const rowCount = await rows.count();
  for (let i = 0; i < rowCount; i++) {
    const el = rows.nth(i);
    const title = await el.locator('.grove-title').innerText().catch(() => '');
    cards.push({ i, id: await el.getAttribute('data-subject-item'), title, text: await el.innerText() });
  }
  ok(planItems.length > 0, `${tag} /api/day 里存在 plan_lines 非空的事项（共 ${planItems.length} 条）`);

  for (const item of planItems) {
    const want = item.plan_lines.map(squash).filter(Boolean);
    const label = planLabelOf(item);
    // 重设计后卡片标题去掉了「科目：」前缀，按 item.id 定位（行元素保留 data-subject-item）。
    const row = page.locator(`.grove-row[data-subject-item="${item.id}"]`).first();
    if (!(await row.count())) { failures.push(`${tag} 找不到「${item.title}」的清单卡（data-subject-item=${item.id}）`); continue; }

    const planSpan = row.locator('[data-grove-plan-lines]');
    const meta = row.locator('[data-grove-plan="1"]');
    ok(await meta.count() === 1, `${tag}「${item.title}」清单卡有 [data-grove-plan="1"] 标签`);
    ok(await planSpan.count() === 1, `${tag}「${item.title}」清单卡有 [data-grove-plan-lines] 块`);
    if (await meta.count() && await planSpan.count()) {
      const gotLabel = squash(await meta.first().innerText());
      const gotPlan = linesOf(await planSpan.first().innerText());
      ok(gotLabel === label, `${tag}「${item.title}」家庭安排标签 = 「${label}」（实得「${gotLabel}」）`);
      ok(JSON.stringify(gotPlan) === JSON.stringify(want), `${tag}「${item.title}」清单卡家庭安排逐行 = payload（实得 ${JSON.stringify(gotPlan)}，期望 ${JSON.stringify(want)}）`);
      const req = row.locator('.grove-points');
      const reqText = await req.count() ? await req.first().innerText() : '';
      const leak = want.find(l => squash(reqText).includes(l));
      ok(!leak, `${tag}「${item.title}」要求块不含家庭安排句子${leak ? '（漏出：' + leak + '）' : ''}`);
    }

    // 详情：独立小节在要求列表之后，逐条 li === payload。
    await row.locator('[data-grove-open]').click();
    await page.waitForTimeout(350);
    const detail = page.locator('#groveDetail');
    const section = detail.locator('section[data-grove-plan-lines]');
    ok(await section.count() >= 1, `${tag} 详情有 section[data-grove-plan-lines] 独立小节`);
    if (await section.count()) {
      const h3 = squash(await section.first().locator('h3').first().innerText().catch(() => ''));
      const lis = (await section.first().locator('li').allInnerTexts()).map(squash).filter(Boolean);
      ok(h3 === label, `${tag} 详情小节标题 = 「${label}」（实得「${h3}」）`);
      ok(JSON.stringify(lis) === JSON.stringify(want), `${tag} 详情家庭安排 li 逐条 = payload（实得 ${JSON.stringify(lis)}，期望 ${JSON.stringify(want)}）`);
      const reqSection = detail.locator('section.grove-detail-steps').first();
      const reqText = await reqSection.count() ? await reqSection.innerText() : '';
      const leak = want.find(l => squash(reqText).includes(l));
      ok(!leak, `${tag} 详情要求小节不含家庭安排句子${leak ? '（漏出：' + leak + '）' : ''}`);
    }
    fs.writeFileSync(path.join(OUT, `${tag}-plan-detail-${item.id}.txt`), await detail.innerText());
    await page.screenshot({ path: path.join(OUT, `${tag}-plan-detail-${item.id}.png`), fullPage: true });
    const back = page.locator('[data-grove-back]:visible');
    if (await back.count()) { await back.first().click(); await page.waitForTimeout(250); }
  }

  // 反证：plan_lines 为空的事项不应该出现家庭安排块（拿今天可见的紧凑卡抽查前几张）。
  for (const c of cards) {
    if (c.text.includes('家庭安排') && !planItems.some(p => p.id === c.id)) {
      failures.push(`${tag} 卡片「${c.title}」出现了家庭安排但 payload 里没有对应 plan_lines（${c.id}）`);
    }
  }

  await page.screenshot({ path: path.join(OUT, `${tag}-home-full.png`), fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  ok(!overflow, `${tag} 无横向溢出`);
  ok(errors.length === 0, `${tag} 无 pageerror${errors.length ? '：' + errors.join(' | ') : ''}`);
  ok(writes.length === 0, `${tag} 无写请求${writes.length ? '：' + writes.join(' | ') : ''}`);

  fs.writeFileSync(path.join(OUT, `${tag}-report.json`), JSON.stringify({ width, planItems: planItems.map(p => ({ id: p.id, title: p.title, plan_lines: p.plan_lines, label: planLabelOf(p) })), cards, overflow, errors, writes, failures }, null, 2));
  await page.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const state = await fetchJson('/api/state');
  const children = Array.isArray(state.children) ? state.children : [];
  const child = CHILD_ID ? children.find(c => c.id === CHILD_ID || c.name === CHILD_ID) : children[0];
  if (!child) throw new Error('没有孩子（/api/state.children 为空）');
  const day = await fetchJson(`/api/day?child_id=${encodeURIComponent(child.id)}&day=${encodeURIComponent(state.today || '')}`);
  fs.writeFileSync(path.join(OUT, 'payload-day.json'), JSON.stringify(day, null, 2));
  const planItems = [];
  for (const g of day.groups || []) for (const it of g.items || []) if (Array.isArray(it.plan_lines) && it.plan_lines.length) planItems.push(it);
  console.log(`payload: child=${child.id} today=${state.today} plan_items=${planItems.length}`);

  const browser = await chromium.launch({ headless: true, channel: CHANNEL });
  for (const width of WIDTHS) await runWidth(browser, width, child.id, day, planItems);
  await browser.close();

  const summary = { base: BASE, child: child.id, today: state.today, planItems: planItems.length, failures };
  fs.writeFileSync(path.join(OUT, 'assertions.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  if (failures.length) { console.error('ASSERTIONS FAILED: ' + failures.length); process.exit(1); }
  console.log('ASSERTIONS PASSED');
})().catch(e => { console.error('FAIL', e); process.exit(2); });
