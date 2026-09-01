/*
 * stage.js - backgrounds, captions, banners, confetti. The "set" the animals
 * perform on. All deterministic functions of time.
 */
(function (global) {
  'use strict';
  var K = global.K, TAU = K.TAU;
  var W = 1920, H = 1080, GROUND = 812;
  var TITLE_FONT = 'Baloo2', BODY_FONT = 'Fredoka';

  // ---------------------------------------------------------------- text ---
  // Shrink-to-fit with optional wrap to two lines, so no caption can ever
  // overflow the bar however long the line is.
  function fitLines(ctx, text, font, weight, maxW, maxSize, minSize) {
    var size = maxSize;
    while (size > minSize) {
      ctx.font = weight + ' ' + size + 'px ' + font;
      if (ctx.measureText(text).width <= maxW) return { size: size, lines: [text] };
      size -= 2;
    }
    var words = text.split(' '), best = null;
    for (var i = 1; i < words.length; i++) {
      var a = words.slice(0, i).join(' '), b = words.slice(i).join(' ');
      var d = Math.abs(a.length - b.length);
      if (!best || d < best.d) best = { a: a, b: b, d: d };
    }
    if (!best) return { size: minSize, lines: [text] };
    size = maxSize;
    while (size > 22) {
      ctx.font = weight + ' ' + size + 'px ' + font;
      if (Math.max(ctx.measureText(best.a).width, ctx.measureText(best.b).width) <= maxW) break;
      size -= 2;
    }
    return { size: size, lines: [best.a, best.b] };
  }

  // Outlined text is what keeps captions legible over any background colour.
  function strokeFill(ctx, text, x, y, fill, ink, lw) {
    ctx.lineJoin = 'round'; ctx.miterLimit = 2;
    ctx.lineWidth = lw; ctx.strokeStyle = ink;
    ctx.strokeText(text, x, y);
    ctx.fillStyle = fill; ctx.fillText(text, x, y);
  }

  // ------------------------------------------------------------ backdrop ---
  function sky(ctx, bg) {
    var g = ctx.createLinearGradient(0, 0, 0, GROUND);
    g.addColorStop(0, bg.sky[0]); g.addColorStop(1, bg.sky[1]);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, GROUND + 4);
  }

  function sun(ctx, t, color) {
    color = '#ffd83f';                     // warm yellow reads on every sky
    ctx.save(); ctx.translate(1660, 176);
    ctx.rotate(t * 0.18);
    for (var i = 0; i < 12; i++) {
      ctx.rotate(TAU / 12);
      var len = 128 + Math.sin(t * 2 + i) * 12;
      K.roundRect(ctx, -11, -len, 22, 46, 11);
      ctx.fillStyle = K.rgba(color, 0.75); ctx.fill();
    }
    ctx.restore();
    K.circle(ctx, 1660, 176, 86, K.rgba(color, 0.35));
    K.circle(ctx, 1660, 176, 70, color);
  }

  function cloud(ctx, x, y, s, alpha) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.fillStyle = 'rgba(255,255,255,' + alpha + ')';
    ctx.beginPath();
    ctx.arc(-58, 8, 44, 0, TAU); ctx.arc(-8, -18, 60, 0, TAU);
    ctx.arc(52, 6, 46, 0, TAU); ctx.arc(8, 26, 44, 0, TAU);
    ctx.fill();
    ctx.restore();
  }

  function clouds(ctx, t) {
    for (var i = 0; i < 6; i++) {
      var speed = 12 + K.hash(i * 3 + 1) * 16;
      var x = ((K.hash(i) * W + t * speed) % (W + 460)) - 230;
      var y = 70 + K.hash(i + 40) * 300;
      var s = 0.55 + K.hash(i + 9) * 0.7;
      cloud(ctx, x, y, s, 0.62 + K.hash(i + 17) * 0.3);
    }
  }

  function hills(ctx, bg, t) {
    var cols = bg.hills;
    for (var layer = 0; layer < 3; layer++) {
      var base = GROUND - 118 + layer * 62;
      var amp = 74 - layer * 16;
      ctx.beginPath();
      ctx.moveTo(-40, H);
      ctx.lineTo(-40, base);
      for (var x = -40; x <= W + 40; x += 40) {
        var y = base - Math.sin(x * 0.0032 + layer * 2.1) * amp
                     - Math.sin(x * 0.0071 + layer) * amp * 0.35;
        ctx.lineTo(x, y);
      }
      ctx.lineTo(W + 40, H); ctx.closePath();
      ctx.fillStyle = cols[layer]; ctx.fill();
    }
    ctx.fillStyle = cols[2]; ctx.fillRect(0, GROUND, W, H - GROUND);
  }

  function meadow(ctx, bg, t) {
    // grass tufts and flowers along the ground, gently swaying
    for (var i = 0; i < 34; i++) {
      var x = K.hash(i * 7 + 2) * W;
      var y = GROUND + 22 + K.hash(i * 5) * (H - GROUND - 40);
      var s = 0.6 + (y - GROUND) / (H - GROUND) * 1.1;
      var sw = Math.sin(t * 1.6 + i) * 0.12;
      ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rotate(sw);
      if (i % 4 === 0) {
        var pc = ['#ffd23f', '#ff8fa3', '#ffffff', '#c9a3ff'][i % 4];
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.quadraticCurveTo(4, -22, 0, -40);
        ctx.lineWidth = 5; ctx.strokeStyle = '#2f8c49'; ctx.stroke();
        for (var pdx = 0; pdx < 5; pdx++) {
          var a = (pdx / 5) * TAU;
          K.circle(ctx, Math.cos(a) * 12, -40 + Math.sin(a) * 12, 9, pc);
        }
        K.circle(ctx, 0, -40, 7, '#ffe98a');
      } else {
        ctx.strokeStyle = K.shade(bg.hills[2], 0.25);
        ctx.lineWidth = 6; ctx.lineCap = 'round';
        for (var b = -1; b <= 1; b++) {
          ctx.beginPath(); ctx.moveTo(b * 7, 0);
          ctx.quadraticCurveTo(b * 16, -18, b * 24, -34);
          ctx.stroke();
        }
      }
      ctx.restore();
    }
  }

  function pond(ctx, t) {
    ctx.save();
    K.ell(ctx, 960, GROUND + 74, 880, 116, 0);
    ctx.fillStyle = 'rgba(70,180,235,0.85)'; ctx.fill();
    K.outline(ctx, 10, 'rgba(40,130,190,0.7)');
    ctx.clip();
    for (var i = 0; i < 7; i++) {
      var y = GROUND + 12 + i * 24;
      ctx.beginPath();
      for (var x = 200; x < 1720; x += 24) {
        var yy = y + Math.sin(x * 0.02 + t * 2.2 + i) * 6;
        ctx[x === 200 ? 'moveTo' : 'lineTo'](x, yy);
      }
      ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.stroke();
    }
    ctx.restore();
    // lily pads
    for (var p = 0; p < 2; p++) {
      var lx = 250 + p * 1420, ly = GROUND + 52 + p * 20;
      ctx.save(); ctx.translate(lx, ly + Math.sin(t * 1.5 + p) * 5);
      ctx.beginPath(); ctx.arc(0, 0, 70, 0.42, TAU + 0.1); ctx.lineTo(0, 0);
      ctx.closePath(); K.shapeOL(ctx, '#4fb84f', 8);
      ctx.restore();
    }
  }

  function jungle(ctx, t) {
    var lanes = [70, 250, 430, 1490, 1670, 1850];
    for (var i = 0; i < lanes.length; i++) {
      var x = lanes[i] + Math.sin(t * 0.9 + i) * 14;
      var len = 150 + K.hash(i + 5) * 240;
      ctx.beginPath(); ctx.moveTo(x, -10);
      ctx.quadraticCurveTo(x + 30, len * 0.5, x + Math.sin(t + i) * 22, len);
      ctx.lineWidth = 12; ctx.strokeStyle = '#2f8c49'; ctx.lineCap = 'round'; ctx.stroke();
      for (var l = 1; l <= 3; l++) {
        var ly = len * (l / 3.4);
        K.ell(ctx, x + 26, ly, 40, 18, 0.5 + l); K.shapeOL(ctx, '#3fae5f', 6);
      }
    }
  }

  function floaties(ctx, t, accent) {
    for (var i = 0; i < 16; i++) {
      var x = (K.hash(i * 11) * W + Math.sin(t * 0.6 + i) * 60) % W;
      var y = ((K.hash(i * 3 + 7) * H) - t * (18 + K.hash(i) * 26)) % (H + 200);
      if (y < -100) y += H + 200;
      var r = 10 + K.hash(i + 21) * 16;
      K.twinkle(ctx, x, y < 0 ? y + H + 200 : y, r, K.rgba(accent, 0.55), t * 0.8 + i);
    }
  }

  // Floating quaver notes - fills the empty band above the cast in the chorus.
  function musicNotes(ctx, t, color) {
    for (var i = 0; i < 12; i++) {
      var span = 520;
      var y = 640 - ((t * (46 + K.hash(i) * 40) + K.hash(i * 5) * span) % span);
      var x = 110 + K.hash(i * 3) * (W - 220) + Math.sin(t * 1.2 + i) * 46;
      var sc = 0.7 + K.hash(i + 3) * 0.7;
      ctx.save();
      ctx.translate(x, y); ctx.scale(sc, sc); ctx.rotate(Math.sin(t + i) * 0.25);
      ctx.globalAlpha = 0.9;
      var col = ['#ffffff', color, '#ff8fb0', '#8fd6ff'][i % 4];
      K.ell(ctx, -16, 26, 22, 16, -0.3); ctx.fillStyle = col; ctx.fill();
      K.outline(ctx, 6, 'rgba(70,50,100,0.55)');
      K.roundRect(ctx, 0, -52, 9, 82, 4); ctx.fillStyle = col; ctx.fill();
      K.outline(ctx, 6, 'rgba(70,50,100,0.55)');
      if (i % 2) {
        ctx.beginPath(); ctx.moveTo(9, -52);
        ctx.quadraticCurveTo(46, -40, 34, -2);
        ctx.lineWidth = 12; ctx.strokeStyle = col; ctx.lineCap = 'round'; ctx.stroke();
        ctx.lineWidth = 5; ctx.strokeStyle = 'rgba(70,50,100,0.4)'; ctx.stroke();
      }
      ctx.restore();
    }
    ctx.globalAlpha = 1;
  }

  // ---------------------------------------------------------- confetti -----
  // One burst = 46 particles that fly out, spin, and fall under gravity.
  function burst(ctx, t, t0, cx, cy, seed, power) {
    var age = t - t0;
    if (age < 0 || age > 2.6) return;
    var cols = ['#ff5f8f', '#ffd23f', '#4ad6ff', '#7ef07e', '#c48bff', '#ff9d4d'];
    for (var i = 0; i < 46; i++) {
      var a = (i / 46) * TAU + K.hash(seed + i) * 0.6;
      var sp = (280 + K.hash(seed + i * 3) * 520) * (power || 1);
      var x = cx + Math.cos(a) * sp * age;
      var y = cy + Math.sin(a) * sp * age + 620 * age * age;
      var fade = K.sat(1 - age / 2.6);
      if (y > H + 60) continue;
      ctx.save(); ctx.translate(x, y);
      ctx.rotate(age * (4 + K.hash(seed + i * 7) * 8) * (i % 2 ? 1 : -1));
      ctx.globalAlpha = fade;
      var c = cols[i % cols.length];
      if (i % 3 === 0) K.circle(ctx, 0, 0, 11, c);
      else if (i % 3 === 1) { K.roundRect(ctx, -11, -7, 22, 15, 4); ctx.fillStyle = c; ctx.fill(); }
      else { K.star(ctx, 0, 0, 15, 5, 0.45, 0); ctx.fillStyle = c; ctx.fill(); }
      ctx.restore();
    }
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------- caption ---
  function caption(ctx, text, alpha, rise, frameColor) {
    if (alpha <= 0.01) return;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    var maxW = 1460;
    var f = fitLines(ctx, text, BODY_FONT, '700', maxW, 82, 54);
    ctx.font = '700 ' + f.size + 'px ' + BODY_FONT;
    var tw = 0;
    for (var i = 0; i < f.lines.length; i++) tw = Math.max(tw, ctx.measureText(f.lines[i]).width);
    var bw = Math.min(W - 120, tw + 130);
    var bh = f.lines.length > 1 ? 210 : 148;
    var cy = 964 - (f.lines.length > 1 ? 34 : 0) + (1 - rise) * 46;

    ctx.shadowColor = 'rgba(40,25,60,0.3)'; ctx.shadowBlur = 26; ctx.shadowOffsetY = 12;
    K.roundRect(ctx, 960 - bw / 2, cy - bh / 2, bw, bh, 44);
    ctx.fillStyle = 'rgba(255,255,255,0.96)'; ctx.fill();
    ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
    ctx.lineWidth = 12; ctx.strokeStyle = frameColor; ctx.stroke();

    ctx.font = '700 ' + f.size + 'px ' + BODY_FONT;
    var lh = f.size * 1.12;
    var y0 = cy - (f.lines.length - 1) * lh / 2;
    for (var j = 0; j < f.lines.length; j++) {
      ctx.fillStyle = '#33305c';
      ctx.fillText(f.lines[j], 960, y0 + j * lh);
    }
    ctx.restore();
  }

  // Bouncing karaoke star that hops on the beat above the caption bar.
  function karaokeStar(ctx, t, alpha, color) {
    if (alpha <= 0.01) return;
    var beat = t * 2, hop = Math.abs(Math.sin(beat * Math.PI));
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.translate(228, 918 - hop * 46);
    ctx.rotate(Math.sin(beat * Math.PI) * 0.25);
    K.star(ctx, 0, 0, 34, 5, 0.46, 0);
    ctx.fillStyle = color; ctx.fill();
    K.outline(ctx, 8, '#ffffff');
    ctx.restore();
  }

  // ------------------------------------------------------------- banner ----
  function banner(ctx, text, appear, color, t) {
    if (appear <= 0.01) return;
    var s = K.pop(appear);
    ctx.save();
    ctx.translate(960, 128);
    ctx.rotate(Math.sin(t * 1.6) * 0.018);
    ctx.scale(s, s);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '800 108px ' + TITLE_FONT;
    var tw = ctx.measureText(text).width;
    var bw = tw + 190, bh = 150;
    // ribbon tails
    for (var d = -1; d <= 1; d += 2) {
      ctx.beginPath();
      ctx.moveTo(d * (bw / 2 - 6), -46);
      ctx.lineTo(d * (bw / 2 + 78), -70);
      ctx.lineTo(d * (bw / 2 + 60), 0);
      ctx.lineTo(d * (bw / 2 + 78), 70);
      ctx.lineTo(d * (bw / 2 - 6), 46);
      ctx.closePath();
      ctx.fillStyle = K.shade(color, -0.28); ctx.fill();
      K.outline(ctx, 8, 'rgba(255,255,255,0.9)');
    }
    K.roundRect(ctx, -bw / 2, -bh / 2, bw, bh, 42);
    ctx.fillStyle = color; ctx.fill();
    K.outline(ctx, 10, '#ffffff');
    strokeFill(ctx, text, 0, 6, '#ffffff', 'rgba(60,40,90,0.55)', 12);
    ctx.restore();
  }

  // Speech bubble carrying the animal's sound, pops out on the beat.
  function soundBubble(ctx, text, x, y, amt, color) {
    if (amt <= 0.01) return;
    var s = K.pop(K.sat(amt * 1.6)) * (0.9 + 0.1 * amt);
    ctx.save();
    ctx.globalAlpha = K.sat(amt * 2.2);
    ctx.translate(x, y); ctx.scale(s, s); ctx.rotate(-0.06);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '800 92px ' + TITLE_FONT;
    var tw = ctx.measureText(text).width;
    var bw = Math.max(tw + 96, 210), bh = 156;
    ctx.restore();                                    // re-anchor once we know the width
    ctx.save();
    ctx.globalAlpha = K.sat(amt * 2.2);
    ctx.translate(K.clamp(x, bw / 2 * s + 40, W - bw / 2 * s - 40), y);
    ctx.scale(s, s); ctx.rotate(-0.06);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '800 92px ' + TITLE_FONT;
    ctx.beginPath();                                  // bubble tail
    ctx.moveTo(-46, bh / 2 - 10); ctx.lineTo(-14, bh / 2 + 74); ctx.lineTo(34, bh / 2 - 10);
    ctx.closePath(); ctx.fillStyle = '#ffffff'; ctx.fill();
    K.roundRect(ctx, -bw / 2, -bh / 2, bw, bh, 46);
    ctx.fillStyle = '#ffffff'; ctx.fill();
    K.outline(ctx, 11, color);
    strokeFill(ctx, text, 0, 4, color, 'rgba(255,255,255,0)', 0);
    ctx.restore();
  }

  global.STAGE = {
    W: W, H: H, GROUND: GROUND, TITLE_FONT: TITLE_FONT, BODY_FONT: BODY_FONT,
    sky: sky, sun: sun, clouds: clouds, hills: hills, meadow: meadow,
    pond: pond, jungle: jungle, floaties: floaties, burst: burst,
    musicNotes: musicNotes,
    caption: caption, banner: banner, soundBubble: soundBubble,
    karaokeStar: karaokeStar, fitLines: fitLines, strokeFill: strokeFill
  };
})(typeof window !== 'undefined' ? window : this);
