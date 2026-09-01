/*
 * animals.js - the eight characters, all original vector artwork.
 *
 * Every animal draws in its own local space: feet on y = 0, centred on x = 0,
 * roughly 470 units tall. The caller translates/scales. Params:
 *   p.t      absolute seconds (idle wiggles)
 *   p.mouth  0..1 how wide the mouth is open
 *   p.blink  0..1 (1 = eyes shut)
 *   p.look   -1..1 pupil offset
 *   p.wave   0..1 raises a wing / paw / trunk
 */
(function (global) {
  'use strict';
  var K = global.K, TAU = K.TAU;
  var INK = '#3f3050';

  // -------------------------------------------------------- shared parts ---
  function eye(ctx, x, y, r, p, sx) {
    var blink = p.blink || 0, look = (p.look || 0) * r * 0.28;
    if (blink > 0.55) {                       // shut: a happy downward lash
      ctx.beginPath();
      ctx.arc(x, y, r * 0.9, Math.PI * 1.15, Math.PI * 1.85);
      ctx.lineWidth = r * 0.34; ctx.strokeStyle = INK; ctx.lineCap = 'round';
      ctx.stroke();
      return;
    }
    var sq = 1 - blink * 1.2;                 // squash while closing
    ctx.save(); ctx.translate(x, y); ctx.scale(sx || 1, Math.max(0.04, sq));
    K.ell(ctx, 0, 0, r, r * 1.06, 0); K.shapeOL(ctx, '#ffffff', r * 0.2);
    K.circle(ctx, look, r * 0.08, r * 0.55, INK);
    K.circle(ctx, look - r * 0.2, -r * 0.22, r * 0.2, 'rgba(255,255,255,0.95)');
    K.circle(ctx, look + r * 0.22, r * 0.26, r * 0.09, 'rgba(255,255,255,0.7)');
    ctx.restore();
  }

  function cheeks(ctx, x, y, r, color) {
    K.circle(ctx, -x, y, r, color); K.circle(ctx, x, y, r, color);
  }

  // Smile when shut, rounded open mouth with a tongue when singing.
  function mouth(ctx, x, y, w, open, lip, clip) {
    var h = w * (0.10 + open * 0.85);
    if (clip) { ctx.save(); clip(ctx); ctx.clip(); }
    if (open < 0.06) {
      ctx.beginPath();
      ctx.moveTo(x - w * 0.5, y - w * 0.06);
      ctx.quadraticCurveTo(x, y + w * 0.34, x + w * 0.5, y - w * 0.06);
      ctx.lineWidth = w * 0.13; ctx.strokeStyle = lip || INK;
      ctx.lineCap = 'round'; ctx.stroke();
      if (clip) ctx.restore();
      return;
    }
    ctx.save();
    K.ell(ctx, x, y + h * 0.32, w * 0.5, h * 0.62, 0);
    ctx.fillStyle = '#8c3b52'; ctx.fill();
    K.outline(ctx, w * 0.11, lip || INK);
    ctx.clip();
    K.fillEll(ctx, x, y + h * 0.95, w * 0.32, h * 0.42, '#ff8fa3');   // tongue
    ctx.restore();
    if (clip) ctx.restore();
  }

  function legs(ctx, y0, h, color, xs, w, footColor) {
    for (var i = 0; i < xs.length; i++) {
      K.roundRect(ctx, xs[i] - w / 2, y0 - h, w, h + w * 0.3, w * 0.45);
      K.shapeOL(ctx, color, 9);
    }
    if (footColor) {
      for (var j = 0; j < xs.length; j++) {
        K.ell(ctx, xs[j], -w * 0.16, w * 0.6, w * 0.34, 0);
        K.shapeOL(ctx, footColor, 8);
      }
    }
  }

  function tailCurl(ctx, x0, y0, x1, y1, cx, cy, w, color) {
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.quadraticCurveTo(cx, cy, x1, y1);
    ctx.lineWidth = w; ctx.strokeStyle = color; ctx.lineCap = 'round'; ctx.stroke();
  }

  var A = {};

  // ------------------------------------------------------------------ cow --
  A.cow = { tint: '#ffffff', label: 'COW', draw: function (ctx, p) {
    var t = p.t, sway = Math.sin(t * 2.1) * 0.03;
    ctx.save(); ctx.rotate(sway);
    legs(ctx, 0, 120, '#f6f2ef', [-96, -36, 36, 96], 50, '#4c4256');
    // tail
    var ty = -118 + Math.sin(t * 3) * 16;
    tailCurl(ctx, 148, -252, 214, ty, 224, -206, 26, INK);
    tailCurl(ctx, 148, -252, 214, ty, 224, -206, 16, '#f6f2ef');
    K.ell(ctx, 214, ty - 4, 24, 30, 0); K.shapeOL(ctx, '#4c4256', 8);
    // body
    K.ell(ctx, 0, -195, 158, 122, 0); K.shapeOL(ctx, '#fbf7f4', 10);
    ctx.save(); K.ell(ctx, 0, -195, 158, 122, 0); ctx.clip();
    K.fillEll(ctx, 0, -118, 118, 62, '#ffe1e8');                 // belly first
    K.fillEll(ctx, -86, -168, 58, 44, '#4c4256', 0.4);
    K.fillEll(ctx, 78, -240, 50, 40, '#4c4256', -0.3);
    K.fillEll(ctx, 46, -196, 34, 26, '#4c4256', 0.2);
    ctx.restore();
    // ears + horns
    K.ell(ctx, -142, -372, 52, 33, -0.45); K.shapeOL(ctx, '#f6f2ef', 9);
    K.fillEll(ctx, -142, -372, 28, 16, '#ffb4c6', -0.45);
    K.ell(ctx, 142, -372, 52, 33, 0.45); K.shapeOL(ctx, '#f6f2ef', 9);
    K.fillEll(ctx, 142, -372, 28, 16, '#ffb4c6', 0.45);
    for (var hs = -1; hs <= 1; hs += 2) {                        // horns, clear of the head
      ctx.save(); ctx.translate(hs * 74, -452); ctx.rotate(hs * 0.5);
      K.ell(ctx, 0, -22, 21, 34, 0); K.shapeOL(ctx, '#f7e2b6', 8);
      ctx.restore();
    }
    // head
    K.ell(ctx, 0, -352, 128, 116, 0); K.shapeOL(ctx, '#fbf7f4', 10);
    ctx.save(); K.ell(ctx, 0, -352, 128, 116, 0); ctx.clip();
    K.fillEll(ctx, -72, -404, 52, 44, '#4c4256', 0.3);   // eye patch
    ctx.restore();
    K.ell(ctx, 0, -300, 92, 64, 0); K.shapeOL(ctx, '#ffc2d1', 9);
    K.fillEll(ctx, -34, -318, 12, 9, '#e07f9c');
    K.fillEll(ctx, 34, -318, 12, 9, '#e07f9c');
    mouth(ctx, 0, -294, 76, p.mouth, '#e07f9c',
          function (c) { K.ell(c, 0, -300, 92, 64, 0); });
    eye(ctx, -54, -388, 30, p); eye(ctx, 54, -388, 30, p);
    ctx.restore();
  }};

  // ----------------------------------------------------------------- duck --
  A.duck = { tint: '#ffd23f', label: 'DUCK', draw: function (ctx, p) {
    var t = p.t, flap = Math.sin(t * 7) * 0.5 * (0.35 + p.wave), bob = Math.sin(t * 2.4) * 6;
    ctx.save(); ctx.translate(0, bob);
    // feet
    for (var s = -1; s <= 1; s += 2) {
      ctx.save(); ctx.translate(s * 52, -6);
      ctx.beginPath(); ctx.moveTo(-34, 0); ctx.lineTo(34, 0);
      ctx.lineTo(26, -26); ctx.lineTo(0, -14); ctx.lineTo(-26, -26); ctx.closePath();
      K.shapeOL(ctx, '#ff9b21', 8); ctx.restore();
    }
    K.ell(ctx, 0, -160, 138, 122, 0); K.shapeOL(ctx, '#ffd23f', 10);   // body
    K.fillEll(ctx, 0, -128, 92, 62, '#ffe58a');
    // tail
    ctx.beginPath(); ctx.moveTo(120, -215); ctx.lineTo(196, -252);
    ctx.lineTo(178, -186); ctx.closePath(); K.shapeOL(ctx, '#ffc21f', 9);
    // wing
    ctx.save(); ctx.translate(-58, -196); ctx.rotate(flap);
    K.ell(ctx, -18, 6, 76, 54, -0.25); K.shapeOL(ctx, '#ffe58a', 9);
    ctx.beginPath(); ctx.moveTo(-70, 20); ctx.quadraticCurveTo(-30, 34, 12, 22);
    ctx.lineWidth = 7; ctx.strokeStyle = '#e8a81a'; ctx.stroke();
    ctx.restore();
    // head
    K.ell(ctx, 0, -318, 100, 98, 0); K.shapeOL(ctx, '#ffd23f', 10);
    for (var i = 0; i < 3; i++) {          // head tuft
      ctx.save(); ctx.translate(-16 + i * 18, -404);
      ctx.rotate(Math.sin(t * 4 + i) * 0.2 - 0.2 + i * 0.2);
      K.ell(ctx, 0, -18, 11, 26, 0); K.shapeOL(ctx, '#ffc21f', 7); ctx.restore();
    }
    // beak - upper and lower halves hinge apart when quacking
    var o = p.mouth;
    ctx.save(); ctx.translate(0, -286);
    ctx.save(); ctx.rotate(-o * 0.3);
    K.ell(ctx, 0, -8, 74, 30, 0); K.shapeOL(ctx, '#ff9b21', 9); ctx.restore();
    ctx.save(); ctx.rotate(o * 0.42);
    K.ell(ctx, 0, 10, 62, 22, 0); K.shapeOL(ctx, '#f08517', 9); ctx.restore();
    ctx.restore();
    eye(ctx, -42, -344, 27, p); eye(ctx, 42, -344, 27, p);
    cheeks(ctx, 82, -318, 20, 'rgba(255,140,150,0.4)');
    ctx.restore();
  }};

  // ------------------------------------------------------------------ cat --
  A.cat = { tint: '#ff9d4d', label: 'CAT', draw: function (ctx, p) {
    var t = p.t, wag = Math.sin(t * 3.2) * 0.5;
    // tail
    ctx.save(); ctx.translate(128, -190); ctx.rotate(wag * 0.5);
    ctx.beginPath(); ctx.moveTo(0, 0);
    ctx.bezierCurveTo(90, -10, 130, -90, 86, -158);
    ctx.lineCap = 'round';
    ctx.lineWidth = 48; ctx.strokeStyle = INK; ctx.stroke();      // outline pass
    ctx.lineWidth = 34; ctx.strokeStyle = '#ff9d4d'; ctx.stroke();
    for (var s = 0; s < 3; s++) {
      K.fillEll(ctx, 60 + s * 22, -34 - s * 40, 9, 15, '#e07a2c', 0.5 + s * 0.3);
    }
    ctx.restore();
    legs(ctx, 0, 96, '#ff9d4d', [-88, -30, 30, 88], 46, '#ffd9b3');
    K.ell(ctx, 0, -178, 128, 126, 0); K.shapeOL(ctx, '#ff9d4d', 10);   // body
    ctx.save(); K.ell(ctx, 0, -178, 128, 126, 0); ctx.clip();
    for (var i = 0; i < 3; i++) K.fillEll(ctx, -100 + i * 12, -230 + i * 52, 22, 10, '#e07a2c', 0.6);
    K.fillEll(ctx, 0, -128, 78, 62, '#ffd9b3');
    ctx.restore();
    // ears
    for (var e = -1; e <= 1; e += 2) {
      ctx.save(); ctx.translate(e * 88, -404); ctx.rotate(e * 0.2 + Math.sin(t * 5) * 0.04);
      ctx.beginPath(); ctx.moveTo(-46, 48); ctx.lineTo(4, -52); ctx.lineTo(52, 40);
      ctx.closePath(); K.shapeOL(ctx, '#ff9d4d', 9);
      ctx.beginPath(); ctx.moveTo(-24, 34); ctx.lineTo(4, -20); ctx.lineTo(30, 30);
      ctx.closePath(); ctx.fillStyle = '#ffb4c6'; ctx.fill();
      ctx.restore();
    }
    K.ell(ctx, 0, -338, 122, 112, 0); K.shapeOL(ctx, '#ff9d4d', 10);   // head
    K.fillEll(ctx, -46, -404, 26, 10, '#e07a2c', -0.35);
    K.fillEll(ctx, 46, -404, 26, 10, '#e07a2c', 0.35);
    // whiskers
    ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(80,60,40,0.65)'; ctx.lineCap = 'round';
    for (var w = 0; w < 3; w++) {
      for (var d = -1; d <= 1; d += 2) {
        ctx.beginPath(); ctx.moveTo(d * 60, -308 + w * 16);
        ctx.quadraticCurveTo(d * 120, -318 + w * 22, d * 168, -304 + w * 30);
        ctx.stroke();
      }
    }
    K.ell(ctx, -32, -296, 44, 34, 0); K.shapeOL(ctx, '#fff3e3', 8);
    K.ell(ctx, 32, -296, 44, 34, 0); K.shapeOL(ctx, '#fff3e3', 8);
    mouth(ctx, 0, -292, 62, p.mouth, INK,
          function (c) { K.ell(c, 0, -338, 122, 112, 0); });
    ctx.beginPath(); ctx.moveTo(-16, -322); ctx.lineTo(16, -322); ctx.lineTo(0, -304);
    ctx.closePath(); K.shapeOL(ctx, '#ff8fa3', 6);
    eye(ctx, -52, -368, 30, p); eye(ctx, 52, -368, 30, p);
    cheeks(ctx, 92, -324, 20, 'rgba(255,120,140,0.35)');
  }};

  // ------------------------------------------------------------------ dog --
  A.dog = { tint: '#d9a066', label: 'DOG', draw: function (ctx, p) {
    var t = p.t, wag = Math.sin(t * 11) * 0.6, ear = Math.sin(t * 3.4) * 0.14;
    ctx.save(); ctx.translate(150, -246); ctx.rotate(wag - 0.5);   // tail
    K.roundRect(ctx, -8, -112, 34, 126, 17); K.shapeOL(ctx, '#c98d51', 9); ctx.restore();
    legs(ctx, 0, 104, '#d9a066', [-92, -32, 32, 92], 48, '#f2d3a8');
    K.ell(ctx, 0, -186, 138, 124, 0); K.shapeOL(ctx, '#d9a066', 10);   // body
    K.fillEll(ctx, 0, -136, 82, 64, '#f2d3a8');
    // floppy ears behind head
    for (var e = -1; e <= 1; e += 2) {
      ctx.save(); ctx.translate(e * 118, -392); ctx.rotate(e * (0.42 + ear));
      K.ell(ctx, e * 16, 78, 58, 104, 0); K.shapeOL(ctx, '#8f5f33', 9); ctx.restore();
    }
    K.ell(ctx, 0, -344, 124, 116, 0); K.shapeOL(ctx, '#d9a066', 10);   // head
    ctx.save(); K.ell(ctx, 0, -344, 124, 116, 0); ctx.clip();
    K.fillEll(ctx, 62, -398, 50, 44, '#8f5f33', -0.3);                 // eye patch
    ctx.restore();
    K.ell(ctx, 0, -296, 86, 62, 0); K.shapeOL(ctx, '#f7e4c9', 9);      // muzzle
    mouth(ctx, 0, -290, 70, p.mouth, INK,
          function (c) { K.ell(c, 0, -296, 86, 62, 0); });
    if (p.mouth < 0.25) {                                              // tongue out
      ctx.save(); ctx.translate(0, -268); ctx.rotate(Math.sin(t * 6) * 0.12);
      K.roundRect(ctx, -20, 0, 40, 46, 18); K.shapeOL(ctx, '#ff8fa3', 7); ctx.restore();
    }
    K.ell(ctx, 0, -332, 34, 26, 0); K.shapeOL(ctx, '#4c4256', 7);      // nose
    K.fillEll(ctx, -10, -340, 9, 6, 'rgba(255,255,255,0.6)');
    eye(ctx, -52, -378, 29, p); eye(ctx, 58, -378, 29, p);
    cheeks(ctx, 96, -318, 19, 'rgba(255,120,120,0.3)');
  }};

  global.ANIMALS = A;
  global.ANIMAL_PARTS = { eye: eye, mouth: mouth, legs: legs, cheeks: cheeks, INK: INK };
})(typeof window !== 'undefined' ? window : this);
