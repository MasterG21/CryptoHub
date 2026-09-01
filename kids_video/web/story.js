/*
 * story.js - the director. Turns script.json + a timestamp into one frame.
 *
 * AnimalVideo.drawFrame(ctx, t) is a pure function of t, which is what lets the
 * offline renderer and the in-browser preview produce identical pictures.
 */
(function (global) {
  'use strict';
  var K = global.K, S = global.STAGE, ANIMALS = global.ANIMALS;
  var W = S.W, H = S.H, GROUND = S.GROUND;
  var WIPE = 0.28;                       // seconds per half of the circle wipe

  var script = null, scenes = [], total = 0;

  function setScript(s) {
    script = s; scenes = []; total = 0;
    for (var i = 0; i < s.scenes.length; i++) {
      var sc = s.scenes[i];
      scenes.push({ def: sc, start: total, end: total + sc.dur });
      total += sc.dur;
    }
    return total;
  }

  // ------------------------------------------------------------ helpers ---
  // Triangular pulse: 1 at each time in `times`, falling to 0 over `w` seconds.
  function pulse(lt, times, w) {
    var m = 0;
    for (var i = 0; i < times.length; i++) {
      var d = lt - times[i];
      if (d >= 0 && d < w) m = Math.max(m, Math.sin((d / w) * Math.PI));
    }
    return m;
  }
  function blinkAt(t) {
    var cycle = 3.6, ph = t % cycle;
    return ph > cycle - 0.26 ? Math.sin(((ph - (cycle - 0.26)) / 0.26) * Math.PI) : 0;
  }
  function hopAt(t) { return Math.abs(Math.sin(t * Math.PI)); }   // 2 hops/sec @120bpm

  function activeCaption(def, lt) {
    for (var i = 0; i < def.captions.length; i++) {
      var c = def.captions[i];
      if (lt >= c.t - 0.25 && lt <= c.t + c.d + 0.25) {
        var a = K.sat((lt - (c.t - 0.25)) / 0.3) * K.sat(((c.t + c.d + 0.25) - lt) / 0.3);
        return { text: c.text, alpha: a, rise: K.sat((lt - c.t + 0.25) / 0.45) };
      }
    }
    return null;
  }

  function backdrop(ctx, def, t) {
    var bg = def.bg;
    S.sky(ctx, bg);
    S.sun(ctx, t, bg.accent);
    S.clouds(ctx, t);
    S.hills(ctx, bg, t);
    if (bg.water) S.pond(ctx, t); else S.meadow(ctx, bg, t);
    if (bg.jungle) S.jungle(ctx, t);
    S.floaties(ctx, t, bg.accent);
  }

  // Draw one animal upright on the ground with squash-and-stretch.
  function place(ctx, key, x, y, scale, p, hop) {
    var a = ANIMALS[key];
    if (!a) return;
    var sq = 1 + hop * 0.09, sw = 1 - hop * 0.07;   // stretch up, thin sideways
    ctx.save();
    ctx.translate(x, y - hop * 60);
    ctx.scale(scale * sw, scale * sq);
    a.draw(ctx, p);
    ctx.restore();
  }

  function shadow(ctx, x, y, w, hop) {
    ctx.save();
    ctx.globalAlpha = 0.20 - hop * 0.09;
    K.ell(ctx, x, y + 6, w * (1 - hop * 0.18), w * 0.19, 0);
    ctx.fillStyle = '#1b2a1b'; ctx.fill();
    ctx.restore();
  }

  // ------------------------------------------------------------- scenes ---
  function drawIntro(ctx, def, lt, t) {
    backdrop(ctx, def, t);
    // the whole cast pops up from behind the hill, one after another
    var order = global.ANIMAL_ORDER;
    for (var i = 0; i < order.length; i++) {
      var appear = K.sat((lt - (1.0 + i * 0.28)) / 0.5);
      if (appear <= 0) continue;
      var up = K.pop(appear) * 300;
      var x = 150 + i * 232;
      var hop = hopAt(t + i * 0.3) * 0.35;
      ctx.save();
      ctx.beginPath(); ctx.rect(0, 0, W, GROUND + 46); ctx.clip();
      place(ctx, order[i], x, GROUND + 330 - up, 0.42,
            { t: t + i, mouth: pulse(lt, [2.0 + i * 0.28], 0.5) * 0.7,
              blink: blinkAt(t + i * 0.7), look: 0, wave: 0.4 }, hop);
      ctx.restore();
    }
    // title
    var title = script.meta.title.toUpperCase();
    var app = K.sat(lt / 0.7);
    ctx.save();
    ctx.translate(960, 330);
    ctx.scale(K.pop(app), K.pop(app));
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '800 168px ' + S.TITLE_FONT;
    // per-letter wave so the title never feels static
    var letters = title.split(''), widths = [], totalW = 0;
    for (var L = 0; L < letters.length; L++) {
      var w = ctx.measureText(letters[L]).width; widths.push(w); totalW += w;
    }
    var cx = -totalW / 2;
    for (var m = 0; m < letters.length; m++) {
      var dy = Math.sin(t * 3.4 - m * 0.5) * 16;
      var hue = (m * 26 + t * 40) % 360;
      ctx.save(); ctx.translate(cx + widths[m] / 2, dy); ctx.rotate(Math.sin(t * 2 - m) * 0.03);
      S.strokeFill(ctx, letters[m], 0, 0, 'hsl(' + hue + ',95%,66%)', '#40275e', 22);
      ctx.restore();
      cx += widths[m];
    }
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = K.sat((lt - 0.6) / 0.6);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '700 62px ' + S.BODY_FONT;
    S.strokeFill(ctx, script.meta.subtitle, 960, 452 + Math.sin(t * 2) * 5,
                 '#ffffff', '#40275e', 14);
    ctx.restore();
    S.burst(ctx, lt, 0.35, 960, 420, 3, 1.0);
    S.burst(ctx, lt, 8.6, 960, 460, 11, 1.0);
  }

  function drawVerse(ctx, def, lt, t) {
    backdrop(ctx, def, t);
    var sound = def.sound.toUpperCase();
    // four beats of story: arrive / sing / ask / celebrate
    var singT = [3.35, 4.15, 4.95], celT = [9.35, 10.15, 10.95];
    var enter = K.sat(lt / 0.95);
    var x = K.lerp(2320, 960, K.easeOutBack(enter));
    var hop = hopAt(t) * (lt > 9 ? 1 : 0.62) * (enter > 0.98 ? 1 : 0.3);
    var mouth = Math.max(pulse(lt, singT, 0.55), pulse(lt, celT, 0.55));
    var wave = K.sat(1 - Math.abs(lt - 1.6) / 1.2) * 0.8 + (lt > 9 ? 0.6 : 0);
    var tilt = lt >= 6 && lt < 9 ? Math.sin((lt - 6) * 2.2) * 0.09 : 0;

    var p = { t: t, mouth: mouth, blink: blinkAt(t), look: Math.sin(t * 0.9) * 0.5, wave: wave };
    shadow(ctx, x, GROUND + 18, 210, hop);
    ctx.save();
    ctx.translate(x, GROUND + 20);
    ctx.rotate(tilt);
    ctx.translate(-x, -(GROUND + 20));
    place(ctx, def.animal, x, GROUND + 20, 1.02, p, hop);
    ctx.restore();

    // sound bubbles on the beat
    var bub = Math.max(pulse(lt, singT, 0.75), pulse(lt, celT, 0.75));
    S.soundBubble(ctx, sound + '!', 1450, 320 - bub * 24, bub, def.bg.frame);
    // question marks while asking the child to join in
    if (lt >= 6.1 && lt < 9.1) {
      for (var q = 0; q < 3; q++) {
        var qa = K.sat((lt - 6.2 - q * 0.3) / 0.4) * K.sat((9.05 - lt) / 0.4);
        if (qa <= 0) continue;
        ctx.save();
        ctx.globalAlpha = qa;
        ctx.translate(1330 + q * 130, 300 - Math.sin(t * 2.6 + q) * 26);
        ctx.rotate(Math.sin(t * 2 + q) * 0.18);
        ctx.scale(K.pop(qa), K.pop(qa));
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.font = '800 132px ' + S.TITLE_FONT;
        S.strokeFill(ctx, '?', 0, 0, def.bg.accent, '#40275e', 18);
        ctx.restore();
      }
    }
    for (var c = 0; c < celT.length; c++) S.burst(ctx, lt, celT[c], 960, 420, 40 + c * 13, 0.9);
    S.banner(ctx, ANIMALS[def.animal].label, K.sat((lt - 0.3) / 0.5), def.bg.frame, t);
    S.karaokeStar(ctx, t, K.sat((lt - 3.1) / 0.4) * K.sat((11.9 - lt) / 0.4), def.bg.accent);
  }

  function drawGuess(ctx, def, lt, t) {
    backdrop(ctx, def, t);
    var revealed = lt >= 3.9;
    var rev = K.sat((lt - 3.9) / 0.55);
    var jump = revealed ? K.pop(rev) : 0;
    var hop = hopAt(t) * (revealed ? 1 : 0.25);
    var y = GROUND + 20 + (1 - jump) * 300;              // hidden below the bush
    var mouth = revealed ? pulse(lt, [4.5, 5.3, 6.1, 6.9], 0.5) : 0;

    ctx.save();
    if (!revealed) { ctx.beginPath(); ctx.rect(0, 0, W, GROUND + 150); ctx.clip(); }
    shadow(ctx, 960, GROUND + 18, 210, hop);
    place(ctx, def.animal, 960, y, 1.02,
          { t: t, mouth: mouth, blink: blinkAt(t), look: 0, wave: revealed ? 0.8 : 0 }, hop);
    ctx.restore();

    // the bush that hides them
    ctx.save();
    ctx.translate(0, jump * 210);
    for (var i = 0; i < 16; i++) {
      var bx = 620 + i * 46 + Math.sin(t * 1.4 + i) * 5;
      var by = GROUND + 78 + Math.sin(i * 1.7) * 34;
      K.circle(ctx, bx, by, 74 + K.hash(i) * 22, i % 2 ? '#3fae5f' : '#2f8c49');
    }
    ctx.fillStyle = '#2f8c49'; ctx.fillRect(560, GROUND + 96, 800, H - GROUND);
    ctx.restore();

    if (!revealed) {
      for (var q = 0; q < 3; q++) {
        var qa = K.sat((lt - 0.4 - q * 0.28) / 0.4) * K.sat((3.85 - lt) / 0.3);
        if (qa <= 0) continue;
        ctx.save();
        ctx.globalAlpha = qa;
        ctx.translate(760 + q * 200, 360 - Math.sin(t * 3 + q * 1.1) * 34);
        ctx.rotate(Math.sin(t * 2.4 + q) * 0.2);
        ctx.scale(K.pop(qa), K.pop(qa));
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.font = '800 176px ' + S.TITLE_FONT;
        S.strokeFill(ctx, '?', 0, 0, def.bg.accent, '#40275e', 22);
        ctx.restore();
      }
    } else {
      S.soundBubble(ctx, def.sound.toUpperCase() + '!', 1430, 300,
                    pulse(lt, [4.5, 5.4, 6.3, 7.1], 0.8), def.bg.frame);
      S.burst(ctx, lt, 3.95, 960, 430, 77, 1.1);
      S.burst(ctx, lt, 5.6, 960, 400, 91, 0.8);
    }
    S.banner(ctx, revealed ? ANIMALS[def.animal].label : 'GUESS WHO?',
             revealed ? K.sat((lt - 3.95) / 0.4) : K.sat((lt - 0.2) / 0.5), def.bg.frame, t);
  }

  function drawChorus(ctx, def, lt, t) {
    // rainbow sky that keeps cycling through the whole section
    var hue = (t * 26) % 360;
    var bg = {
      sky: ['hsl(' + hue + ',85%,72%)', 'hsl(' + ((hue + 50) % 360) + ',95%,88%)'],
      hills: def.bg.hills, accent: def.bg.accent, frame: def.bg.frame
    };
    S.sky(ctx, bg); S.sun(ctx, t, def.bg.accent); S.clouds(ctx, t);
    S.hills(ctx, bg, t); S.meadow(ctx, bg, t); S.floaties(ctx, t, def.bg.accent);
    S.musicNotes(ctx, t, def.bg.accent);

    var order = global.ANIMAL_ORDER;
    for (var i = 0; i < order.length; i++) {
      var appear = K.sat((lt - i * 0.16) / 0.5);
      if (appear <= 0) continue;
      var x = 168 + i * 228;
      var hop = hopAt(t + i * 0.25) * 0.9 * appear;
      var mouth = pulse((lt + i * 0.06) % 2, [0.0, 0.5, 1.0, 1.5], 0.34) * 0.9;
      shadow(ctx, x, GROUND + 24, 132, hop);
      ctx.save();
      ctx.globalAlpha = appear;
      place(ctx, order[i], x, GROUND + 26, 0.42 * (0.6 + 0.4 * K.pop(appear)),
            { t: t + i * 0.4, mouth: mouth, blink: blinkAt(t + i * 0.9),
              look: Math.sin(t + i) * 0.6, wave: 0.7 }, hop);
      ctx.restore();
    }
    S.burst(ctx, lt, 0.3, 960, 380, 5, 1.1);
    S.burst(ctx, lt, 4.2, 460, 400, 23, 0.9);
    S.burst(ctx, lt, 8.2, 1460, 400, 61, 0.9);
    S.burst(ctx, lt, 12.2, 960, 360, 87, 1.2);
    S.banner(ctx, 'SING ALONG!', K.sat(lt / 0.6), def.bg.frame, t);
    S.karaokeStar(ctx, t, K.sat((lt - 0.4) / 0.5) * K.sat((15.7 - lt) / 0.5), def.bg.accent);
  }

  function drawOutro(ctx, def, lt, t) {
    backdrop(ctx, def, t);
    // floating hearts sit behind the cast
    for (var hI = 0; hI < 14; hI++) {
      var hy = H - ((t * (60 + K.hash(hI) * 60) + K.hash(hI * 3) * H) % (H + 200));
      var hx = 120 + K.hash(hI * 7) * (W - 240) + Math.sin(t * 1.4 + hI) * 40;
      ctx.save(); ctx.globalAlpha = 0.75;
      K.heart(ctx, hx, hy, 26 + K.hash(hI + 5) * 20,
              ['#ff5f8f', '#ffd23f', '#ff9d4d', '#c48bff'][hI % 4]);
      ctx.restore();
    }
    var cast = ['cow', 'lion', 'monkey', 'elephant'];
    for (var i = 0; i < cast.length; i++) {
      var appear = K.sat((lt - i * 0.2) / 0.5);
      var x = 380 + i * 400;
      var hop = hopAt(t + i * 0.4) * 0.75;
      shadow(ctx, x, GROUND + 22, 180, hop);
      place(ctx, cast[i], x, GROUND + 24, 0.68,
            { t: t + i * 0.5, mouth: pulse(t % 2, [0, 1], 0.5) * 0.6,
              blink: blinkAt(t + i), look: 0,
              wave: 0.5 + 0.5 * Math.sin(t * 5 + i) }, hop * appear);
    }
    S.burst(ctx, lt, 0.4, 960, 420, 7, 1.1);
    S.burst(ctx, lt, 8.4, 960, 400, 29, 1.1);
    S.banner(ctx, 'THANK YOU!', K.sat(lt / 0.6), def.bg.frame, t);
  }

  var DRAW = { intro: drawIntro, verse: drawVerse, guess: drawGuess,
               chorus: drawChorus, outro: drawOutro };

  // ------------------------------------------------------------- frame ----
  function drawFrame(ctx, t) {
    t = K.clamp(t, 0, total - 0.0001);
    var idx = 0;
    for (var i = 0; i < scenes.length; i++) if (t >= scenes[i].start) idx = i;
    var sc = scenes[idx], def = sc.def, lt = t - sc.start;

    ctx.save();
    (DRAW[def.type] || drawVerse)(ctx, def, lt, t);
    ctx.restore();

    var cap = activeCaption(def, lt);
    if (cap) S.caption(ctx, cap.text, cap.alpha, cap.rise, def.bg.frame);

    // circle wipe across the scene boundary, coloured by the incoming scene
    var R = 1180;
    if (idx + 1 < scenes.length && lt > def.dur - WIPE) {
      var g = (lt - (def.dur - WIPE)) / WIPE;
      K.circle(ctx, 960, 540, K.easeInCubic(g) * R, scenes[idx + 1].def.bg.frame);
    } else if (idx > 0 && lt < WIPE) {
      var g2 = 1 - lt / WIPE;
      K.circle(ctx, 960, 540, K.easeOutCubic(g2) * R, def.bg.frame);
    }
  }

  global.AnimalVideo = {
    setScript: setScript,
    drawFrame: drawFrame,
    duration: function () { return total; },
    sceneList: function () { return scenes; }
  };
})(typeof window !== 'undefined' ? window : this);
