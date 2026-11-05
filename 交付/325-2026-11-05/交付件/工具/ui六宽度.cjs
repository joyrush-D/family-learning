const { chromium } = require(process.env.PLAYWRIGHT_MODULE);
const path = require('node:path'), fs = require('node:fs');
const OUT = process.env.OUT || '/Users/joyrush/Documents/deepseek-harness/default-workspace/work/surface-evidence/ui3';
const BASE = process.env.BASE || 'http://127.0.0.1:8801/?child_id=child-1';
const failures = [];
const check = (cond, name, extra) => { if (!cond) failures.push(extra === undefined ? name : name + ' :: ' + JSON.stringify(extra)); };

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const report = { base: BASE, widths: [], failures };
  for (const [width, height] of [[1440, 860], [1200, 860], [1024, 900], [768, 900], [390, 844], [360, 780]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    const errors = [], requests = [];
    page.on('pageerror', e => errors.push(String(e.message || e)));
    page.on('request', r => { if (r.method() !== 'GET') requests.push(r.method() + ' ' + r.url()); });
    await page.goto(BASE, { waitUntil: 'load' });
    await page.waitForFunction(() => document.querySelector('#content')?.dataset.ready === 'true' && document.querySelector('#groveListTitle'));
    await page.waitForTimeout(450);
    const payload = await page.evaluate(async () => {
      const child = new URL(location.href).searchParams.get('child_id') || 'child-1';
      const r = await fetch('/api/day?child_id=' + encodeURIComponent(child));
      return r.json();
    });
    const norm = s => String(s || '').replace(/^[^：:\n]{1,12}[：:]/, '').trim();
    const todayTitles = [];
    for (const g of [...(payload.groups || []), ...(payload.undated || [])]) {
      for (const it of (g.items || [])) if (it.today) todayTitles.push(norm(it.title));
    }
    const m = await page.evaluate(() => {
      const R = e => { if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), bottom: Math.round(r.bottom) }; };
      const q = s => document.querySelector(s);
      const mode = q('.grove')?.dataset.layout || document.querySelector('.grove')?.getAttribute('data-layout');
      const scrollEl = q('.grove-board-scroll');
      const rows = [...document.querySelectorAll('#task-groups article.grove-row')];
      const rowTitles = rows.map(r => [r.className, (r.querySelector('.grove-title') || r).innerText.split('\n')[0]]);
      const sr = scrollEl ? scrollEl.getBoundingClientRect() : { top: 0, bottom: innerHeight };
      const fullRows = rows.filter(r => { const b = r.getBoundingClientRect(); return b.top > -1 && b.bottom <= sr.bottom + 1 && b.height > 1; }).length;
      const later = q('.grove-col.is-later');
      const done = q('.grove-col.is-done');
      const cancel = q('#groveCancelled');
      const cols = [...document.querySelectorAll('.grove-col')].map(c => R(c));
      const fixedNavs = [...document.querySelectorAll('nav')].filter(n => getComputedStyle(n).position === 'fixed').map(n => n.getAttribute('aria-label'));
      const tabs = q('.grove-tabs'), week = q('.grove-week');
      const heads = [...document.querySelectorAll('.grove-col-head, .grove-col > h2, .grove-col > h3')].map(h => h.innerText.replace(/\s+/g, ' ').trim());
      const badges = [...rows].map(r => [...r.querySelectorAll('.grove-badge')].map(b => b.innerText.trim()));
      const rowFacts = [...rows].map(r => [...r.querySelectorAll('.grove-chips [data-fact]')].map(f => f.getAttribute('data-fact') + ':' + f.innerText.trim()));
      return {
        mode, docW: document.documentElement.scrollWidth, vw: innerWidth, docH: Math.round(document.documentElement.scrollHeight),
        noHScroll: document.documentElement.scrollWidth <= innerWidth + 2,
        aside: R(q('aside')), main: R(q('main')), board: R(q('.grove-board')), detail: R(q('#groveDetail')), rail: R(q('#groveRailData')),
        cols, rowCount: rows.length, fullRows, firstRow: R(rows[0]),
        bar: R(q('.grove-list-head.grove-bar')), kids: R(q('.grove-bar-kids')), chipsRow: R(q('.grove-chips-row')),
        fixedNavs, tabs: R(tabs), week: R(week), courses: R(q('#today-courses')),
        tabsAboveWeek: !!(tabs && week && tabs.getBoundingClientRect().bottom <= week.getBoundingClientRect().top + 1),
        heads,
        laterTitles: later ? [...later.querySelectorAll('.grove-title')].map(t => t.innerText.trim()) : null,
        cancelledHidden: cancel ? cancel.hidden : null,
        cancelledTitles: cancel ? [...cancel.querySelectorAll('.grove-title')].map(t => t.innerText.trim()) : null,
        badges, rowFacts, rowTitles,
        planBlocks: document.querySelectorAll('[data-grove-plan="1"]').length,
      };
    });
    const taps = await page.evaluate(() => {
      const list = (sel) => {
        const es = [...document.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
        return es.slice(0, 6).map(e => { const r = e.getBoundingClientRect(); return { text: e.innerText.replace(/\s+/g, ' ').trim().slice(0, 18), w: Math.round(r.width), h: Math.round(r.height) }; });
      };
      return {
        childChips: list('.grove-bar-kids .child-filters button'),
        pills: list('.grove-tabs button'),
        dayBtn: list('.grove-bar-daybtn'),
        openBtns: list('[data-grove-open]'),
        completeBtns: list('[data-grove-complete]'),
        backBtns: list('[data-grove-back]'),
        headerH: (() => { const b = document.querySelector('.grove-list-head.grove-bar'); return b ? Math.round(b.getBoundingClientRect().height) : null; })(),
      };
    });
    m.tapTargets = taps;
    m.headerH = taps.headerH;
    await page.screenshot({ path: path.join(OUT, 'w' + width + '-list.png') });
    await page.screenshot({ path: path.join(OUT, 'w' + width + '-list-full.png'), fullPage: true });
    check(m.noHScroll, width + ' no horizontal scroll', { docW: m.docW, vw: m.vw });
    check(m.badges.every(b => b.length <= 5), width + ' badges<=4+more', m.badges);
    if (width === 1024) check(m.chipsRow && m.chipsRow.h > 20, '1024 medium chips row', m.chipsRow);
    check((m.rowTitles ? m.rowTitles.filter(x => todayTitles.includes(norm(x[1]))).length : m.rowCount) === 5, width + ' five today cards', m.rowCount);
    check(m.laterTitles !== null && m.laterTitles.length === 0, width + ' cancelled not in later column', m.laterTitles);
    check(m.cancelledHidden === true, width + ' cancelled section hidden by default', m.cancelledHidden);
    if (width >= 1200) check(m.firstRow && m.firstRow.y <= 120, width + ' first today card top<=120', m.firstRow && m.firstRow.y);
    if (width >= 1200) { const mv = await page.evaluate(() => { const n = document.querySelector('aside nav button[data-page="more"]'); const r = n.getBoundingClientRect(); return { bottom: Math.round(r.bottom), vh: innerHeight }; }); check(mv.bottom <= mv.vh - 4, width + ' rail nav more fully visible', mv); }
    else check(m.firstRow && m.firstRow.y <= (width >= 900 ? 360 : 360), width + ' first today card top (phone/medium)', m.firstRow && m.firstRow.y);
    if (width === 1440) {
      check(m.fullRows >= 5, '1440 five today cards fully visible', m.fullRows);
      check(m.aside && Math.abs(m.aside.w - 212) <= 1, '1440 rail 212', m.aside);
      check(m.detail && Math.abs(m.detail.w - 424) <= 2, '1440 detail 424', m.detail);
      check(m.board && m.board.w > 700, '1440 board flex width', m.board);
      check(m.heads[0] === '今天要做 5', '1440 today col head', m.heads[0]);
      await page.locator('[data-grove-set="cancelled"]').first().click();
      await page.waitForTimeout(300);
      const cancel = await page.evaluate(() => { const c = document.querySelector('#groveCancelled'); return { hidden: c.hidden, titles: [...c.querySelectorAll('.grove-later-title')].map(t => t.innerText.trim()), visible: c.getBoundingClientRect().height > 0 }; });
      check(cancel.hidden === false && cancel.visible && cancel.titles.length === 1, '1440 cancelled set reveals cancelled card', cancel);
    }
    if (width === 390) {
      const hb = m.chipsRow ? m.chipsRow.bottom : (m.kids ? m.kids.bottom : null);
      check(hb !== null && hb <= 150, '390 header+chips<=150', hb);
    }
    if (width === 360) {
      check(m.fixedNavs.length === 1 && m.fixedNavs[0] === '主导航', '360 only nav fixed', m.fixedNavs);
      const lastCard = await page.evaluate(() => { const rows = [...document.querySelectorAll('#task-groups article.grove-row')]; const r = rows[rows.length - 1].getBoundingClientRect(); return { bottom: Math.round(r.bottom) }; });
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.waitForTimeout(250);
      const bottom = await page.evaluate(() => { const bar = document.querySelector('.grove-phone-bar'); const nav = document.querySelector('nav[aria-label="主导航"]').getBoundingClientRect(); const rows = [...document.querySelectorAll('#task-groups article.grove-row')]; const last = rows[rows.length - 1].getBoundingClientRect(); const add = document.querySelector('.grove-chips-row [data-homework-new]'); const later = document.querySelector('.grove-bar.is-phone .grove-bar-later'); return { bar: bar ? Math.round(bar.getBoundingClientRect().height) : 0, navTop: Math.round(nav.top), lastBottom: Math.round(last.bottom), lastTop: Math.round(last.top), addH: add ? Math.round(add.getBoundingClientRect().height) : 0, later: later ? later.innerText : '' }; });
      check(bottom.bar === 0, '360 floating phone bar removed (add/morrow moved to header)', bottom);
      check(bottom.lastBottom <= bottom.navTop + 1, '360 end of list clear of site nav when scrolled', bottom);
      check(bottom.addH >= 28 && bottom.addH <= 46, '360 add-homework button in header chips (>=44 hit row)', bottom);
      check(/明天 \d+/.test(bottom.later), '360 tomorrow count in header', bottom);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(200);
      void lastCard;
    }
    const rowCount = await page.locator('#task-groups article.grove-row').count();
    const todayRowCount = m.rowTitles ? m.rowTitles.filter(x => todayTitles.includes(norm(x[1]))).length : rowCount;
    report.__todo = report.__todo || [];
    check(todayRowCount === 5, width + ' DOM today rows', todayRowCount + '/' + rowCount);
    // detail
    const detail = {};
    if (width >= 1200) {
      await page.locator('#task-groups article.grove-row [data-grove-open]').first().click();
      await page.waitForTimeout(350);
      detail.info = await page.evaluate(() => {
        const d = document.querySelector('#groveDetail');
        const lis = [...d.querySelectorAll('.grove-steps ul.grove-standards li')];
        const first = lis[0];
        const before = first ? getComputedStyle(first, '::before') : null;
        const facts = [...d.querySelectorAll('.grove-facts .grove-fact')].map(f => { const cs = getComputedStyle(f); return { text: f.innerText.replace(/\s+/g, ' ').trim(), bg: cs.backgroundColor, border: cs.borderTopWidth, radius: cs.borderRadius }; });
        return {
          visible: !!d && d.getBoundingClientRect().height > 200,
          heading: d.querySelector('h2.grove-h')?.innerText.trim(),
          liTexts: lis.map(l => l.innerText.trim()),
          pseudo: before ? { content: before.content, position: before.position, width: before.width } : null,
          facts,
          hasPlanSection: !!d.querySelector('[data-grove-plan-lines]'),
          hasMore: !!d.querySelector('details.grove-more'),
          sections: [...d.querySelectorAll('.grove-card')].map(s => (s.querySelector('h3,h6') || {}).innerText || ''),
        };
      });
      const di = detail.info;
      check(di.visible, '1440 detail visible', di.visible);
      check(di.liTexts.length > 0 && di.liTexts.every(t => !/^[：:，,。；;、]/.test(t)), '1440 detail steps no leading punctuation', di.liTexts);
      check(di.pseudo && di.pseudo.position === 'static', '1440 steps pseudo static', di.pseudo);
      check(di.facts.every(f => f.bg === 'rgba(0, 0, 0, 0)' && f.border === '0px'), '1440 fact cells no input box', di.facts);
      await page.screenshot({ path: path.join(OUT, 'w' + width + '-detail.png') });
    } else {
      await page.locator('#task-groups article.grove-row [data-grove-open]').first().click();
      await page.waitForTimeout(400);
      detail.info = await page.evaluate(() => {
        const d = document.querySelector('#groveDetail');
        const r = d.getBoundingClientRect();
        const back = document.querySelector('[data-grove-back]');
        return { rect: { y: Math.round(r.top), h: Math.round(r.height) }, view: document.querySelector('.grove').getAttribute('data-view'), backVisible: !!back && back.getBoundingClientRect().width > 0, heading: d.querySelector('h2.grove-h')?.innerText.trim(), bodyScrollable: (d.querySelector('.grove-detail-body')?.scrollHeight || 0) > (d.querySelector('.grove-detail-body')?.clientHeight || 0) };
      });
      check(detail.info.view === 'detail', width + ' detail sheet open', detail.info);
      if (width <= 899) {
        const above = await page.evaluate(() => { const sh = document.querySelector('#groveDetail').getBoundingClientRect().top; const cards = [...document.querySelectorAll('#task-groups article.grove-row')]; return { sheetTop: Math.round(sh), cardsAbove: cards.filter(c => { const r = c.getBoundingClientRect(); return r.top < sh - 20 && r.bottom > 0; }).length }; });
        check(above.cardsAbove >= 1, width + ' >=2 cards visible above sheet', above);
      }
      check(detail.info.backVisible, width + ' detail back visible', detail.info);
      await page.screenshot({ path: path.join(OUT, 'w' + width + '-sheet.png') });
      const back = page.locator('[data-grove-back]').first();
      if (await back.isVisible().catch(() => false)) await back.click();
    }
    check(errors.length === 0, width + ' no pageerror', errors);
    check(requests.length === 0, width + ' no non-GET request', requests);
    report.widths.push({ width, height, ...m, detail, errors, nonGet: requests });
    await page.close();
  }
  fs.writeFileSync(path.join(OUT, 'metrics.json'), JSON.stringify(report, null, 1));
  fs.writeFileSync(path.join(OUT, 'assertions.json'), JSON.stringify({ base: BASE, failures }, null, 1));
  console.log('FAILURES', failures.length);
  if (failures.length) console.log(JSON.stringify(failures, null, 1));
  await browser.close();
  process.exit(failures.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
