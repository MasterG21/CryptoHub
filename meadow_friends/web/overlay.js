/*
 * overlay.js - subtitles and the title card, drawn on a 2D canvas and mapped
 * onto a full-screen quad in an orthographic pass. The texture is only redrawn
 * when the words change, so it costs nothing per frame.
 */
import * as THREE from 'three';

const W = 1920, H = 1080;

export function buildOverlay() {
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.minFilter = THREE.LinearFilter;

  const scene = new THREE.Scene();
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const quad = new THREE.Mesh(
    new THREE.PlaneGeometry(2, 2),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthTest: false }));
  scene.add(quad);

  let last = '';

  function fit(text, font, maxW, maxSize, minSize) {
    let size = maxSize;
    while (size > minSize) {
      ctx.font = `700 ${size}px ${font}`;
      if (ctx.measureText(text).width <= maxW) return { size, lines: [text] };
      size -= 2;
    }
    const words = text.split(' ');
    let best = null;
    for (let i = 1; i < words.length; i++) {
      const a = words.slice(0, i).join(' '), b = words.slice(i).join(' ');
      const d = Math.abs(a.length - b.length);
      if (!best || d < best.d) best = { a, b, d };
    }
    if (!best) return { size: minSize, lines: [text] };
    size = maxSize;
    while (size > 26) {
      ctx.font = `700 ${size}px ${font}`;
      if (Math.max(ctx.measureText(best.a).width, ctx.measureText(best.b).width) <= maxW) break;
      size -= 2;
    }
    return { size, lines: [best.a, best.b] };
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawCaption(text, speaker) {
    ctx.clearRect(0, 0, W, H);
    if (!text) return;
    const f = fit(text, 'Fredoka', 1420, 74, 46);
    ctx.font = `700 ${f.size}px Fredoka`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    let tw = 0;
    for (const l of f.lines) tw = Math.max(tw, ctx.measureText(l).width);
    const bw = Math.min(W - 160, tw + 120);
    const bh = f.lines.length > 1 ? 194 : 136;
    const cy = 962 - (f.lines.length > 1 ? 30 : 0);

    ctx.save();
    ctx.shadowColor = 'rgba(20,14,40,0.36)';
    ctx.shadowBlur = 30; ctx.shadowOffsetY = 12;
    roundRect(960 - bw / 2, cy - bh / 2, bw, bh, 40);
    ctx.fillStyle = 'rgba(255,255,255,0.95)';
    ctx.fill();
    ctx.restore();
    ctx.lineWidth = 10;
    ctx.strokeStyle = speaker || '#ff6b9d';
    roundRect(960 - bw / 2, cy - bh / 2, bw, bh, 40);
    ctx.stroke();

    const lh = f.size * 1.14;
    const y0 = cy - (f.lines.length - 1) * lh / 2;
    ctx.fillStyle = '#2f2b52';
    f.lines.forEach((l, i) => ctx.fillText(l, 960, y0 + i * lh));
  }

  function drawTitle(title, subtitle, alpha) {
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '800 168px Baloo2';
    const cols = ['#ff5f8f', '#ff9d3f', '#ffd23f', '#5fd97a', '#3fc0f5', '#a86bf0'];
    const letters = [...title];
    const widths = letters.map(c => ctx.measureText(c).width);
    const total = widths.reduce((a, b) => a + b, 0);
    let x = 960 - total / 2;
    letters.forEach((c, i) => {
      ctx.save();
      ctx.translate(x + widths[i] / 2, 300 + (i % 2 ? 8 : -8));
      ctx.rotate((i % 2 ? 1 : -1) * 0.03);
      ctx.lineJoin = 'round';
      ctx.lineWidth = 26; ctx.strokeStyle = '#ffffff';
      ctx.strokeText(c, 0, 0);
      ctx.lineWidth = 12; ctx.strokeStyle = '#3b2358';
      ctx.strokeText(c, 0, 0);
      ctx.fillStyle = cols[i % cols.length];
      ctx.fillText(c, 0, 0);
      ctx.restore();
      x += widths[i];
    });
    if (subtitle) {
      ctx.font = '700 62px Fredoka';
      ctx.lineJoin = 'round';
      ctx.lineWidth = 16; ctx.strokeStyle = '#3b2358';
      ctx.strokeText(subtitle, 960, 420);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(subtitle, 960, 420);
    }
    ctx.restore();
  }

  // Thumbnail treatment: big rainbow title, a badge, and a soft gradient
  // scrim so the type stays readable over the meadow.
  function drawThumb(title, sub) {
    ctx.clearRect(0, 0, W, H);
    const g = ctx.createLinearGradient(0, 0, 0, 470);
    g.addColorStop(0, 'rgba(20,16,50,0.42)');
    g.addColorStop(1, 'rgba(20,16,50,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, 470);

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '800 210px Baloo2';
    const cols = ['#ff5f8f', '#ffb03f', '#ffe23f', '#5fd97a', '#3fc0f5', '#a86bf0'];
    const letters = [...title];
    const widths = letters.map(c => ctx.measureText(c).width);
    const total = widths.reduce((a, b) => a + b, 0);
    let x = 960 - total / 2;
    letters.forEach((c, i) => {
      ctx.save();
      ctx.translate(x + widths[i] / 2, 172 + (i % 2 ? 10 : -10));
      ctx.rotate((i % 2 ? 1 : -1) * 0.035);
      ctx.lineJoin = 'round';
      ctx.shadowColor = 'rgba(30,16,60,0.5)'; ctx.shadowBlur = 22; ctx.shadowOffsetY = 12;
      ctx.lineWidth = 34; ctx.strokeStyle = '#ffffff'; ctx.strokeText(c, 0, 0);
      ctx.shadowColor = 'transparent';
      ctx.lineWidth = 14; ctx.strokeStyle = '#3b2358'; ctx.strokeText(c, 0, 0);
      ctx.fillStyle = cols[i % cols.length]; ctx.fillText(c, 0, 0);
      ctx.restore();
      x += widths[i];
    });

    ctx.save();
    ctx.translate(960, 336);
    ctx.font = '800 84px Baloo2';
    const bw = ctx.measureText(sub).width + 110;
    roundRect(-bw / 2, -58, bw, 116, 40);
    ctx.fillStyle = '#ff3d77'; ctx.fill();
    ctx.lineWidth = 12; ctx.strokeStyle = '#ffffff'; ctx.stroke();
    ctx.lineJoin = 'round';
    ctx.lineWidth = 10; ctx.strokeStyle = 'rgba(60,20,60,0.45)'; ctx.strokeText(sub, 0, 4);
    ctx.fillStyle = '#ffffff'; ctx.fillText(sub, 0, 4);
    ctx.restore();
  }

  return {
    scene, cam, quad,
    thumb(title, sub) { drawThumb(title, sub); tex.needsUpdate = true; last = '__thumb'; },
    set(state) {
      const key = JSON.stringify(state);
      if (key === last) return;
      last = key;
      if (state.title) drawTitle(state.title, state.subtitle, state.alpha ?? 1);
      else drawCaption(state.text, state.color);
      tex.needsUpdate = true;
    },
  };
}
