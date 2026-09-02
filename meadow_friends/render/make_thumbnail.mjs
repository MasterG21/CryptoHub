// make_thumbnail.mjs - a hero frame from the real 3D scene, with the title on top.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { serve } from './serve.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
mkdirSync(resolve(ROOT, 'out'), { recursive: true });
const { srv, port } = await serve(ROOT);
const browser = await chromium.launch({ args: [
  '--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', e => { console.error('PAGE ERROR:', e.message); process.exit(1); });
await page.goto(`http://127.0.0.1:${port}/web/index.html?mat=phong&aa=1&shadow=pcf&smap=1024&seg=20`);
await page.waitForFunction('window.__ready !== undefined', null, { timeout: 180000 });
await page.evaluate(() => window.__ready);

// the finale, framed low and wide so the whole cast is in shot
const T = +(process.argv[2] || 124);
// draw and capture in ONE evaluate: a WebGL canvas without preserveDrawingBuffer
// is cleared once the frame is presented, so a separate read comes back black
const data = await page.evaluate(([t]) => {
  window.__thumbAt(t, 'Meadow Friends', 'Animal Sounds!',
    { pos: [0.4, 1.62, 8.4], at: [0.4, 0.95, 0.2], fov: 40 });
  return document.querySelector('canvas').toDataURL('image/jpeg', 0.94);
}, [T]);
const buf = Buffer.from(data.slice(data.indexOf(',') + 1), 'base64');
writeFileSync(resolve(ROOT, 'out/thumbnail-1920.jpg'), buf);
console.log('wrote out/thumbnail-1920.jpg', (buf.length / 1024).toFixed(0), 'KB');
await browser.close();
srv.close();
