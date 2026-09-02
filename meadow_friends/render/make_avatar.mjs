/*
 * make_avatar.mjs - the channel profile picture.
 *
 * YouTube crops avatars to a circle and shows them as small as 98 px, so this
 * frames one face tight, centred, with nothing important near the corners, and
 * no text (which would be illegible at that size).
 *
 *   node render/make_avatar.mjs [size]
 */
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { serve } from './serve.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SIZE = +(process.argv[2] || 800);
mkdirSync(resolve(ROOT, 'out'), { recursive: true });
const { srv, port } = await serve(ROOT);
const browser = await chromium.launch({ args: [
  '--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: SIZE, height: SIZE } });
page.on('pageerror', e => { console.error('PAGE ERROR:', e.message); process.exit(1); });
await page.goto(`http://127.0.0.1:${port}/web/index.html?mat=phong&aa=1&shadow=pcf&smap=1024&seg=20`);
await page.waitForFunction('window.__ready !== undefined', null, { timeout: 180000 });
await page.evaluate(() => window.__ready);
await page.evaluate(s => window.__resize(s, s), SIZE);

// Ellie has the most distinctive silhouette at thumbnail size - big round ears
// plus a trunk - so she carries the mark. Milo and the pair are rendered too,
// as alternates.
const shots = [
  ['milo-a', 14.0, 'milo', { open: 0.4, dist: 7.6, side: 0.30 }],
  ['milo-b', 14.0, 'milo', { open: 0.4, dist: 7.6, side: -0.34 }],
  ['milo-c', 124.0, 'milo', { open: 0.4, dist: 7.6, side: 0.26 }],
  ['ellie-a', 124.0, 'ellie', { open: 0.4, dist: 8.6, side: 0.34 }],
];
for (const [name, t, who, opt] of shots) {
  const [square, circle] = await page.evaluate(([tt, w, o]) => {
    window.__avatarOf(tt, w, o);
    const sq = document.querySelector('canvas').toDataURL('image/png');
    return [sq, window.__circleCrop()];
  }, [t, who, opt]);
  for (const [suffix, data] of [['', square], ['-circle', circle]]) {
    const f = resolve(ROOT, `out/avatar-${name}${suffix}.png`);
    writeFileSync(f, Buffer.from(data.slice(data.indexOf(',') + 1), 'base64'));
  }
  console.log('wrote avatar-' + name + ' (square + circle)');
}
await browser.close();
srv.close();
