/*
 * render_video.mjs - renders the 3D scene to an MP4.
 *
 * WebGL runs on SwiftShader here, and the dominant per-frame cost is not the
 * rasteriser but the readback out of the GL context (~0.6 s a frame, whatever
 * the resolution). That cost parallelises, so the work is sharded across
 * several browsers, each writing its own segment, and the segments are
 * concatenated at the end.
 *
 *   node render/render_video.mjs [--workers 3] [--fps 30] [--scale 1]
 *                               [--from 0] [--to N] [--out out/video.mp4]
 */
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { spawn } from 'child_process';
import { existsSync, mkdirSync, writeFileSync, rmSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { serve } from './serve.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const FFMPEG = '/usr/local/lib/python3.11/dist-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2';
const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > 0 ? process.argv[i + 1] : d; };

const FPS = +arg('fps', 30);
const SCALE = +arg('scale', 1);
const WORKERS = +arg('workers', 3);
const QUALITY = arg('quality', 'mat=phong&aa=1&shadow=pcf&smap=1024');
const OUT = resolve(ROOT, arg('out', 'out/meadow-friends.mp4'));
const AUDIO = resolve(ROOT, arg('audio', 'out/audio.wav'));
const TMP = resolve(ROOT, 'out/_segments');
const W = Math.round(1920 * SCALE), H = Math.round(1080 * SCALE);

mkdirSync(dirname(OUT), { recursive: true });
rmSync(TMP, { recursive: true, force: true });
mkdirSync(TMP, { recursive: true });
if (!existsSync(AUDIO)) { console.error(`missing ${AUDIO} - run make_audio.py`); process.exit(1); }

const { srv, port } = await serve(ROOT);

async function openPage() {
  const browser = await chromium.launch({ args: [
    '--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(`http://127.0.0.1:${port}/web/index.html?${QUALITY}`);
  await page.waitForFunction('window.__ready !== undefined', null, { timeout: 180000 });
  await page.evaluate(() => window.__ready);
  if (SCALE !== 1) await page.evaluate(([w, h]) => window.__resize(w, h), [W, H]);
  return { browser, page, errs };
}

const probe = await openPage();
const duration = await probe.page.evaluate(() => window.__duration);
await probe.browser.close();

const FROM = +arg('from', 0), TO = Math.min(+arg('to', duration), duration);
const total = Math.round((TO - FROM) * FPS);
console.log(`rendering ${total} frames  ${W}x${H} @ ${FPS}fps  (${(TO - FROM).toFixed(1)}s) ` +
            `across ${WORKERS} worker(s)`);

const per = Math.ceil(total / WORKERS);
const ranges = [];
for (let i = 0; i < WORKERS; i++) {
  const a = i * per, b = Math.min(total, a + per);
  if (b > a) ranges.push([a, b]);
}

const t0 = Date.now();
const progress = ranges.map(() => 0);
function report() {
  const done = progress.reduce((a, b) => a + b, 0);
  const el = (Date.now() - t0) / 1000;
  const rate = done / Math.max(el, 0.001);
  process.stdout.write(`\r  ${done}/${total} frames  ${rate.toFixed(2)} fps  ` +
    `elapsed ${(el / 60).toFixed(1)} min  eta ${((total - done) / Math.max(rate, 1e-6) / 60).toFixed(1)} min   `);
}

async function runWorker(idx) {
  const [a, b] = ranges[idx];
  const seg = resolve(TMP, `seg${String(idx).padStart(2, '0')}.mp4`);
  const { browser, page, errs } = await openPage();
  const ff = spawn(FFMPEG, [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(FPS), '-i', 'pipe:0',
    '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19',
    '-profile:v', 'high', '-level', '4.2', '-pix_fmt', 'yuv420p',
    '-g', String(FPS * 2), '-bf', '2', '-force_key_frames', 'expr:eq(n,0)',
    seg]);
  ff.stderr.on('data', d => process.stderr.write(d));
  const closed = new Promise((res, rej) =>
    ff.on('close', c => (c === 0 ? res() : rej(new Error(`worker ${idx} ffmpeg exited ${c}`)))));
  const prefix = 'data:image/jpeg;base64,'.length;
  const write = buf => new Promise(r => (ff.stdin.write(buf) ? r() : ff.stdin.once('drain', r)));

  for (let i = a; i < b; i++) {
    const t = FROM + i / FPS;
    const data = await page.evaluate(tt => {
      window.__drawAt(tt);
      return document.querySelector('canvas').toDataURL('image/jpeg', 0.94);
    }, t);
    if (errs.length) throw new Error(`worker ${idx} page error: ${errs[0]}`);
    await write(Buffer.from(data.slice(prefix), 'base64'));
    progress[idx] = i - a + 1;
    if (i % 20 === 0) report();
  }
  ff.stdin.end();
  await closed;
  await browser.close();
  return seg;
}

const segs = await Promise.all(ranges.map((_, i) => runWorker(i)));
report();
console.log(`\nencoding done in ${((Date.now() - t0) / 60000).toFixed(1)} min - joining segments`);

const listFile = resolve(TMP, 'list.txt');
writeFileSync(listFile, segs.map(s => `file '${s}'`).join('\n') + '\n');
const run = (args) => new Promise((res, rej) => {
  const p = spawn(FFMPEG, args, { stdio: ['ignore', 'inherit', 'inherit'] });
  p.on('close', c => (c === 0 ? res() : rej(new Error('ffmpeg ' + c))));
});
const joined = resolve(TMP, 'joined.mp4');
await run(['-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
           '-i', listFile, '-c', 'copy', joined]);
await run(['-y', '-hide_banner', '-loglevel', 'error', '-i', joined, '-i', AUDIO,
           '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
           '-af', 'aresample=48000', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
           '-shortest', '-movflags', '+faststart', OUT]);
rmSync(TMP, { recursive: true, force: true });
srv.close();
console.log(`done -> ${OUT}  (${((Date.now() - t0) / 60000).toFixed(1)} min total)`);
