/*
 * render_video.mjs - drives the canvas frame by frame and pipes the pictures
 * straight into ffmpeg. Nothing touches the disk between the two, so a full
 * 1080p render needs no scratch space.
 *
 *   node render/render_video.mjs [--fps 30] [--scale 1] [--from 0] [--to 168]
 *                               [--format png|jpeg] [--out out/video.mp4]
 */
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { spawn } from 'child_process';
import { existsSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const FFMPEG = '/usr/local/lib/python3.11/dist-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2';

const arg = (name, def) => {
  const i = process.argv.indexOf('--' + name);
  return i > 0 ? process.argv[i + 1] : def;
};
const FPS = +arg('fps', 30);
const SCALE = +arg('scale', 1);
const FORMAT = arg('format', 'png');
const OUT = resolve(ROOT, arg('out', 'out/animal-sounds-song.mp4'));
const AUDIO = resolve(ROOT, arg('audio', 'out/animal-sounds-song.wav'));
const W = Math.round(1920 * SCALE), H = Math.round(1080 * SCALE);

mkdirSync(dirname(OUT), { recursive: true });
if (!existsSync(AUDIO)) {
  console.error(`missing ${AUDIO} - run: python3 render/make_audio.py`);
  process.exit(1);
}

const browser = await chromium.launch({ args: ['--no-sandbox', '--allow-file-access-from-files'] });
const page = await browser.newPage({ viewport: { width: W, height: H } });
page.on('pageerror', e => { console.error('PAGE ERROR:', e.message); process.exit(1); });
await page.goto('file://' + resolve(ROOT, 'web/index.html'));
await page.waitForFunction('window.__ready !== undefined');
await page.evaluate(() => window.__ready);
if (SCALE !== 1) {
  await page.evaluate(s => {
    const c = document.getElementById('c');
    c.width = Math.round(1920 * s); c.height = Math.round(1080 * s);
    c.getContext('2d').setTransform(s, 0, 0, s, 0, 0);
  }, SCALE);
}

const duration = await page.evaluate(() => window.__duration);
const FROM = +arg('from', 0), TO = Math.min(+arg('to', duration), duration);
const total = Math.round((TO - FROM) * FPS);
console.log(`rendering ${total} frames  ${W}x${H} @ ${FPS}fps  (${(TO - FROM).toFixed(1)}s, ${FORMAT})`);

const ff = spawn(FFMPEG, [
  '-y', '-hide_banner', '-loglevel', 'error',
  '-f', 'image2pipe', '-framerate', String(FPS), '-i', 'pipe:0',
  '-i', AUDIO,
  '-map', '0:v:0', '-map', '1:a:0',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
  '-profile:v', 'high', '-level', '4.2', '-pix_fmt', 'yuv420p',
  '-g', String(FPS * 2), '-bf', '2',
  // make_audio.py already masters to -14 LUFS / -2.2 dBTP, so just resample.
  // (alimiter would *raise* the level here - its `level` option auto-gains.)
  '-af', 'aresample=48000',
  '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
  '-shortest', '-movflags', '+faststart',
  OUT,
]);
ff.stderr.on('data', d => process.stderr.write(d));
const done = new Promise((res, rej) =>
  ff.on('close', c => (c === 0 ? res() : rej(new Error('ffmpeg exited ' + c)))));

const mime = FORMAT === 'png' ? 'image/png' : 'image/jpeg';
const prefix = `data:${mime};base64,`.length;
const write = buf => new Promise(r => (ff.stdin.write(buf) ? r() : ff.stdin.once('drain', r)));

const t0 = Date.now();
for (let i = 0; i < total; i++) {
  const t = FROM + i / FPS;
  const data = await page.evaluate(([tt, m, q]) => {
    window.__drawAt(tt);
    return document.getElementById('c').toDataURL(m, q);
  }, [t, mime, 0.96]);
  await write(Buffer.from(data.slice(prefix), 'base64'));
  if (i % 150 === 0 || i === total - 1) {
    const el = (Date.now() - t0) / 1000, rate = (i + 1) / el;
    process.stdout.write(
      `\r  frame ${i + 1}/${total}  ${rate.toFixed(1)} fps  ` +
      `eta ${Math.round((total - i - 1) / rate)}s      `);
  }
}
ff.stdin.end();
await done;
await browser.close();
console.log(`\ndone -> ${OUT}  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
