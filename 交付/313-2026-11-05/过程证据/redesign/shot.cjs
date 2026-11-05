const path = require('path');
const MOD = '/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const { chromium } = require(MOD);
(async () => {
  const dir = __dirname;
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1000, height: 2000 } });
  await page.goto('file://' + path.join(dir, 'mockup.html'));
  await page.waitForTimeout(300);
  for (const [sel, name] of [['#list', 'mock-list-360.png'], ['#detail', 'mock-detail-900.png']]) {
    const el = await page.$(sel);
    await el.screenshot({ path: path.join(dir, name) });
    const box = await el.boundingBox();
    console.log(name, Math.round(box.width) + 'x' + Math.round(box.height));
  }
  await browser.close();
})();
