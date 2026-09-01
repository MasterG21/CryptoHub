// shot.mjs - grab individual frames as PNGs for visual review.
// usage: node shot.mjs out/dir t1 t2 t3 ...
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGE = 'file://' + resolve(HERE, '../web/index.html');
const outDir = process.argv[2];
const times = process.argv.slice(3).map(Number);
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ args: ['--no-sandbox', '--allow-file-access-from-files'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', e => console.error('PAGE ERROR:', e.message));
await page.goto(PAGE);
await page.waitForFunction('window.__ready !== undefined');
await page.evaluate(() => window.__ready);

for (const t of times) {
  const data = await page.evaluate(tt => {
    window.__drawAt(tt);
    return document.getElementById('c').toDataURL('image/png');
  }, t);
  const f = `${outDir}/t${String(t).padStart(6, '0')}.png`;
  writeFileSync(f, Buffer.from(data.slice('data:image/png;base64,'.length), 'base64'));
  console.log('wrote', f);
}
await browser.close();
