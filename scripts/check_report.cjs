const { chromium } = require('playwright');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');

(async () => {
  const target = path.resolve(process.argv[2]);
  const output = path.resolve(process.argv[3]);
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
  const results = [];
  try {
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
      const errors = [];
      page.on('pageerror', err => errors.push(String(err)));
      await page.goto(pathToFileURL(target).href);
      await page.locator('h1').waitFor();
      const measurements = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > window.innerWidth,
        axes: document.querySelectorAll('.summary svg text').length,
        cases: document.querySelectorAll('details').length,
        bodyTextLength: document.body.innerText.length,
      }));
      await page.selectOption('#filter', 'fail');
      const filtered = await page.locator('details:not([hidden])').count();
      await page.selectOption('#filter', 'all');
      await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: false });
      await page.locator('details').first().locator('summary').click();
      const expanded = await page.locator('details').first().getAttribute('open');
      const ok = !measurements.overflow && measurements.axes >= 11 && measurements.cases > 0 && errors.length === 0 && expanded !== null;
      results.push({ name, ...measurements, filtered, errors, expanded: expanded !== null, ok });
      await page.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(output, 'report-qa.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
  if (results.some(x => !x.ok)) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
