// make_thumbnail.mjs - exports the YouTube thumbnail at 1280x720.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
mkdirSync(resolve(ROOT, 'out'), { recursive: true });
const browser = await chromium.launch({ args: ['--no-sandbox', '--allow-file-access-from-files'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
page.on('pageerror', e => { console.error('PAGE ERROR:', e.message); process.exit(1); });
await page.goto('file://' + resolve(ROOT, 'web/thumbnail.html'));
await page.waitForFunction('window.__ready !== undefined');
await page.evaluate(() => window.__ready);
for (const [fmt, q] of [['png', undefined], ['jpeg', 0.92]]) {
  const data = await page.evaluate(([m, qq]) =>
    document.getElementById('c').toDataURL(m, qq), ['image/' + fmt, q]);
  const file = resolve(ROOT, 'out/thumbnail.' + (fmt === 'jpeg' ? 'jpg' : 'png'));
  writeFileSync(file, Buffer.from(data.slice(data.indexOf(',') + 1), 'base64'));
  console.log('wrote', file);
}
await browser.close();
