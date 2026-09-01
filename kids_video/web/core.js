/*
 * core.js - drawing primitives, easing, deterministic noise, backgrounds.
 * Everything here is a pure function of time, so an offline render at frame N
 * produces exactly the same pixels as the live preview at t = N / fps.
 */
(function (global) {
  'use strict';

  var TAU = Math.PI * 2;

  // ---------------------------------------------------------------- math ---
  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function sat(v) { return clamp(v, 0, 1); }

  // Normalised progress of `t` across the window [from, from + len].
  function prog(t, from, len) { return sat((t - from) / len); }

  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  function easeInCubic(t) { return t * t * t; }
  function easeInOutSine(t) { return 0.5 - 0.5 * Math.cos(Math.PI * t); }
  function easeOutBack(t) {
    var c = 1.70158, c3 = c + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
  }
  // Springy pop: overshoots then settles. Used for anything that "appears".
  function pop(t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    return 1 - Math.pow(2, -9 * t) * Math.cos(t * 12);
  }

  // Deterministic pseudo-random in [0,1) from an integer seed. No Math.random
  // anywhere in the render path - reruns must be byte-identical.
  function hash(n) {
    var x = Math.sin(n * 127.1 + 311.7) * 43758.5453123;
    return x - Math.floor(x);
  }
  function hrange(n, lo, hi) { return lo + hash(n) * (hi - lo); }

  // -------------------------------------------------------------- colour ---
  function hex2rgb(h) {
    h = h.replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  function rgba(hexColor, a) {
    var c = hex2rgb(hexColor);
    return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')';
  }
  function shade(hexColor, amt) { // amt < 0 darker, > 0 lighter
    var c = hex2rgb(hexColor);
    for (var i = 0; i < 3; i++) {
      c[i] = Math.round(amt < 0 ? c[i] * (1 + amt) : c[i] + (255 - c[i]) * amt);
    }
    return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
  }

  // ------------------------------------------------------------- shapes ---
  function ell(ctx, x, y, rx, ry, rot) {
    ctx.beginPath();
    ctx.ellipse(x, y, Math.abs(rx), Math.abs(ry), rot || 0, 0, TAU);
  }
  function fillEll(ctx, x, y, rx, ry, color, rot) {
    ell(ctx, x, y, rx, ry, rot); ctx.fillStyle = color; ctx.fill();
  }
  function circle(ctx, x, y, r, color) {
    ctx.beginPath(); ctx.arc(x, y, Math.abs(r), 0, TAU); ctx.fillStyle = color; ctx.fill();
  }
  function roundRect(ctx, x, y, w, h, r) {
    r = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  // Chunky outline every character shares - it is what makes the art read as
  // one set rather than eight unrelated drawings.
  function outline(ctx, w, color) {
    ctx.lineWidth = w || 9;
    ctx.strokeStyle = color || '#3a2c4a';
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();
  }
  function shapeOL(ctx, color, lw) { // fill + outline the current path
    ctx.fillStyle = color; ctx.fill(); outline(ctx, lw);
  }
  function star(ctx, x, y, r, points, inner, rot) {
    ctx.beginPath();
    for (var i = 0; i < points * 2; i++) {
      var a = (i / (points * 2)) * TAU + (rot || 0) - Math.PI / 2;
      var rad = i % 2 ? r * inner : r;
      ctx[i ? 'lineTo' : 'moveTo'](x + Math.cos(a) * rad, y + Math.sin(a) * rad);
    }
    ctx.closePath();
  }
  // Four-point sparkle, the "twinkle" used all over the backgrounds.
  function twinkle(ctx, x, y, r, color, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0);
    ctx.beginPath();
    ctx.moveTo(0, -r);
    ctx.quadraticCurveTo(r * 0.16, -r * 0.16, r, 0);
    ctx.quadraticCurveTo(r * 0.16, r * 0.16, 0, r);
    ctx.quadraticCurveTo(-r * 0.16, r * 0.16, -r, 0);
    ctx.quadraticCurveTo(-r * 0.16, -r * 0.16, 0, -r);
    ctx.fillStyle = color; ctx.fill();
    ctx.restore();
  }
  // Tapering ribbon along a cubic bezier - the elephant's trunk. Returns the
  // two edge point lists so callers can draw rings across it.
  function taper(ctx, p0, p1, p2, p3, w0, w1, steps) {
    var L = [], R = [];
    for (var i = 0; i <= steps; i++) {
      var t = i / steps, mt = 1 - t;
      var x = mt * mt * mt * p0[0] + 3 * mt * mt * t * p1[0]
            + 3 * mt * t * t * p2[0] + t * t * t * p3[0];
      var y = mt * mt * mt * p0[1] + 3 * mt * mt * t * p1[1]
            + 3 * mt * t * t * p2[1] + t * t * t * p3[1];
      var dx = 3 * mt * mt * (p1[0] - p0[0]) + 6 * mt * t * (p2[0] - p1[0])
             + 3 * t * t * (p3[0] - p2[0]);
      var dy = 3 * mt * mt * (p1[1] - p0[1]) + 6 * mt * t * (p2[1] - p1[1])
             + 3 * t * t * (p3[1] - p2[1]);
      var len = Math.hypot(dx, dy) || 1;
      var nx = -dy / len, ny = dx / len, w = w0 + (w1 - w0) * t;
      L.push([x + nx * w, y + ny * w]); R.push([x - nx * w, y - ny * w]);
    }
    var n = L.length - 1;
    ctx.beginPath();
    ctx.moveTo(L[0][0], L[0][1]);
    for (var a = 1; a <= n; a++) ctx.lineTo(L[a][0], L[a][1]);
    for (var b = n; b >= 0; b--) ctx.lineTo(R[b][0], R[b][1]);
    ctx.closePath();
    return { L: L, R: R, tip: [(L[n][0] + R[n][0]) / 2, (L[n][1] + R[n][1]) / 2] };
  }

  function heart(ctx, x, y, r, color) {
    ctx.save(); ctx.translate(x, y); ctx.scale(r / 16, r / 16);
    ctx.beginPath();
    ctx.moveTo(0, 6);
    ctx.bezierCurveTo(-14, -4, -9, -16, 0, -8);
    ctx.bezierCurveTo(9, -16, 14, -4, 0, 6);
    ctx.closePath();
    ctx.fillStyle = color; ctx.fill();
    ctx.restore();
  }

  global.K = {
    TAU: TAU, lerp: lerp, clamp: clamp, sat: sat, prog: prog,
    easeOutCubic: easeOutCubic, easeInCubic: easeInCubic,
    easeInOutSine: easeInOutSine, easeOutBack: easeOutBack, pop: pop,
    hash: hash, hrange: hrange,
    rgba: rgba, shade: shade, hex2rgb: hex2rgb,
    ell: ell, fillEll: fillEll, circle: circle, roundRect: roundRect,
    outline: outline, shapeOL: shapeOL, star: star, twinkle: twinkle, heart: heart,
    taper: taper
  };
})(typeof window !== 'undefined' ? window : this);
