// 十八渠道演示：360/1440 UI 测量（切换两个孩子；记录首卡位置、清单高度、截断/溢出/写请求）。
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const BASE = (process.env.SURFACE_BASE || 'http://127.0.0.1:8783').replace(/\/$/, '');
const OUT = process.env.SURFACE_OUT || '/tmp/g4-children';
const CHANNEL = process.env.PLAYWRIGHT_CHANNEL || 'chrome';
const DAY = process.env.SURFACE_DAY || '';
const SIZES = (process.env.SURFACE_SIZES || '360x800,1440x900').split(',').map(s => s.split('x').map(Number));
const fs = require('fs');
const path = require('path');
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const state = await (await fetch(BASE + '/api/state')).json();
  const children = state.children || [];
  const browser = await chromium.launch({ channel: CHANNEL, headless: true });
  const report = {};
  for (const [w, h] of SIZES) {
    for (const child of children) {
      const tag = `w${w}-${child.id}`;
      const page = await browser.newPage({ viewport: { width: w, height: h } });
      const errors = [];
      page.on('pageerror', e => errors.push(String(e)));
      const writes = [];
      page.on('request', request => {
        if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes.push(request.method() + ' ' + request.url());
      });
      await page.goto(BASE + '/', { waitUntil: 'networkidle' });
      await page.waitForSelector('body[data-page="home"]', { timeout: 20000 });
      await page.waitForFunction(() => document.querySelector('#content')?.dataset.ready === 'true', { timeout: 20000 });
      // 十八渠道快照冻结在 2026-11-04：先点周条上的那一天，再切孩子（切孩子不会丢掉已选日期）。
      if (DAY) {
        const dayBtn = page.locator(`.grove-day[data-grove-day="${DAY}"]`);
        if (await dayBtn.count()) {
          try { await dayBtn.first().click({ timeout: 4000 }); await page.waitForTimeout(900); }
          catch (error) { errors.push('switch-day ' + String(error).slice(0, 80)); }
        } else {
          errors.push('no-day-button ' + DAY);
        }
      }
      // 切换孩子（顶部胶囊按钮），确保截的是该孩子的清单。
      const switcher = page.getByText(child.name, { exact: true }).first();
      if (await switcher.count()) {
        try { await switcher.click({ timeout: 3000 }); } catch (error) { errors.push('switch ' + String(error).slice(0, 80)); }
      }
      await page.waitForTimeout(700);
      const metrics = await page.evaluate(() => {
        const allRows = [...document.querySelectorAll('.grove-row')];
        const rows = allRows.filter(el => el.getBoundingClientRect().height > 1);
        const bottom = el => el.getBoundingClientRect().bottom + window.scrollY;
        const tops = rows.map(el => el.getBoundingClientRect().top + window.scrollY);
        const bottoms = rows.map(bottom);
        const trunc = [];
        const overflow = [];
        for (const el of document.querySelectorAll('.grove-row *')) {
          const cs = getComputedStyle(el);
          if ((cs.webkitLineClamp && cs.webkitLineClamp !== 'none' && el.scrollHeight > el.clientHeight + 1) ||
              (cs.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1)) {
            trunc.push((el.textContent || '').trim().slice(0, 60));
          }
        }
        for (const el of document.querySelectorAll('body *')) {
          const r = el.getBoundingClientRect();
          if (r.width && r.right > document.documentElement.clientWidth + 1) { overflow.push(el.className || el.tagName); if (overflow.length > 5) break; }
        }
        const bannerEl = [...document.querySelectorAll('body *')].find(el => {
          const text = (el.textContent || '').trim();
          const rect = el.getBoundingClientRect();
          return text.includes('消息读取有缺口') && rect.height > 20 && rect.height < 220;
        });
        const current = (document.querySelector('.grove-hero, h1')?.innerText || '').slice(0, 40);
        return {
          rowCount: rows.length,
          hiddenRowCount: allRows.length - rows.length,
          viewport: { w: innerWidth, h: innerHeight },
          firstRowTop: tops[0] ?? null,
          rowTops: tops,
          lastRowBottom: bottoms.length ? bottoms[bottoms.length - 1] : null,
          screensToLastRow: bottoms.length ? bottoms[bottoms.length - 1] / innerHeight : null,
          docH: document.documentElement.scrollHeight,
          screensTotal: document.documentElement.scrollHeight / innerHeight,
          gapBanner: bannerEl ? { height: bannerEl.getBoundingClientRect().height, text: (bannerEl.textContent || '').trim().slice(0, 60) } : null,
          overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 || overflow.length > 0,
          overflowEls: overflow,
          trunc,
          heading: current,
          cards: rows.map(r => (r.innerText || '').replace(/\n+/g, ' | ').slice(0, 160)),
          selectedDay: document.querySelector('.grove-day[aria-selected="true"]')?.dataset.groveDay || null,
          upcomingLine: (document.querySelector('.grove-upcoming')?.innerText || '').replace(/\n+/g, ' ').slice(0, 200) || null
        };
      });
      await page.screenshot({ path: path.join(OUT, `${tag}-home-full.png`), fullPage: true });
      fs.writeFileSync(path.join(OUT, `${tag}-home.txt`), metrics.cards.join('\n'));
      let detail = null;
      try {
        await page.locator('.grove-row').first().click({ timeout: 3000 });
        await page.waitForTimeout(500);
        detail = await page.evaluate(() => {
          const el = document.querySelector('#groveDetail') || document.querySelector('.grove-detail');
          return el ? (el.innerText || '').replace(/\n+/g, ' | ').slice(0, 400) : null;
        });
        await page.screenshot({ path: path.join(OUT, `${tag}-detail.png`), fullPage: true });
      } catch (error) {
        detail = 'no detail: ' + String(error).slice(0, 120);
      }
      report[tag] = { ...metrics, detail, errors, writes };
      await page.close();
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'g4-report.json'), JSON.stringify(report, null, 2));
  for (const [tag, value] of Object.entries(report)) {
    const screens = value.screensToLastRow == null ? '?' : value.screensToLastRow.toFixed(2);
    console.log(`${tag}: heading=${value.heading} day=${value.selectedDay || '?'} rows=${value.rowCount} firstTop=${value.firstRowTop == null ? '?' : value.firstRowTop.toFixed(2)} listScreens=${screens} gapBanner=${value.gapBanner ? value.gapBanner.height : 0} overflowX=${value.overflowX} trunc=${value.trunc.length} writes=${value.writes.length} errors=${value.errors.length}`);
  }
})();
