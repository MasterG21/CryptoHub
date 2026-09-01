// shot.mjs - grab single frames for visual review.
// usage: node render/shot.mjs <outdir> t1 t2 ...
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { serve } from './serve.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const { srv, port } = await serve(ROOT);
const outDir = process.argv[2];
const times = process.argv.slice(3).map(Number);
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ args: [
  '--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', e => console.error('PAGE ERROR:', e.message));
page.on('console', m => { if (m.type() === 'error') console.error('CONSOLE:', m.text()); });
const Q = process.env.SHOT_Q || 'mat=phong&aa=1&shadow=pcf&smap=1024&seg=14';
await page.goto(`http://127.0.0.1:${port}/web/index.html?${Q}`);
await page.waitForFunction('window.__ready !== undefined', null, { timeout: 90000 });
await page.evaluate(() => window.__ready);
for (const t of times) {
  const data = await page.evaluate(tt => {
    window.__drawAt(tt);
    return document.querySelector('canvas').toDataURL('image/png');
  }, t);
  const f = `${outDir}/t${String(t).padStart(6, '0')}.png`;
  writeFileSync(f, Buffer.from(data.slice(data.indexOf(',') + 1), 'base64'));
  console.log('wrote', f);
}
await browser.close();
srv.close();
