/* animals2.js - frog, lion, monkey, elephant. Same local space as animals.js. */
(function (global) {
  'use strict';
  var K = global.K, A = global.ANIMALS, P = global.ANIMAL_PARTS;
  var eye = P.eye, mouth = P.mouth, legs = P.legs, cheeks = P.cheeks, INK = P.INK;

  // ----------------------------------------------------------------- frog --
  A.frog = { tint: '#6dd44f', label: 'FROG', draw: function (ctx, p) {
    var t = p.t, puff = p.mouth;
    // back legs
    for (var s = -1; s <= 1; s += 2) {
      ctx.save(); ctx.translate(s * 150, -70); ctx.scale(s, 1);
      ctx.beginPath();
      ctx.moveTo(-10, -60);
      ctx.quadraticCurveTo(72, -46, 62, 12);
      ctx.quadraticCurveTo(58, 46, 6, 44);
      ctx.quadraticCurveTo(-30, 40, -34, -6);
      ctx.closePath(); K.shapeOL(ctx, '#5cc040', 9);
      for (var f = 0; f < 3; f++) {          // webbed toes
        K.ell(ctx, 22 + f * 26, 48, 15, 11, 0); K.shapeOL(ctx, '#7fe05f', 7);
      }
      ctx.restore();
    }
    // front feet
    for (var s2 = -1; s2 <= 1; s2 += 2) {
      K.ell(ctx, s2 * 74, -18, 40, 20, 0); K.shapeOL(ctx, '#7fe05f', 8);
    }
    K.ell(ctx, 0, -140, 172, 132, 0); K.shapeOL(ctx, '#6dd44f', 10);      // body
    K.fillEll(ctx, 0, -104, 116, 84, '#d6f5a8');                          // belly
    // wide mouth
    ctx.save();
    var mw = 200, mh = 20 + puff * 92;
    K.ell(ctx, 0, -168 + mh * 0.28, mw * 0.5, mh * 0.6, 0);
    ctx.fillStyle = puff > 0.08 ? '#8c3b52' : '#4fae36'; ctx.fill();
    K.outline(ctx, 9, INK);
    if (puff > 0.08) { ctx.clip(); K.fillEll(ctx, 0, -168 + mh, 46, mh * 0.4, '#ff8fa3'); }
    ctx.restore();
    cheeks(ctx, 128, -160, 26 + puff * 14, 'rgba(255,150,175,0.75)');
    // bulging eyes sit on top of the head
    for (var e = -1; e <= 1; e += 2) {
      var ex = e * 78, ey = -284 - Math.sin(t * 2.2) * 4;
      K.ell(ctx, ex, ey, 64, 62, 0); K.shapeOL(ctx, '#7fe05f', 10);
      eye(ctx, ex, ey + 4, 38, p);
    }
    // nostrils
    K.fillEll(ctx, -26, -212, 8, 6, '#3f8f2c'); K.fillEll(ctx, 26, -212, 8, 6, '#3f8f2c');
  }};

  // ----------------------------------------------------------------- lion --
  A.lion = { tint: '#ffc861', label: 'LION', draw: function (ctx, p) {
    var t = p.t, roar = p.mouth;
    ctx.save(); ctx.translate(140, -210);                        // tail
    ctx.beginPath(); ctx.moveTo(0, 0);
    ctx.quadraticCurveTo(96, -20, 84 + Math.sin(t * 3) * 14, -128);
    ctx.lineCap = 'round';
    ctx.lineWidth = 30; ctx.strokeStyle = INK; ctx.stroke();
    ctx.lineWidth = 18; ctx.strokeStyle = '#e8a83c'; ctx.stroke();
    K.ell(ctx, 84 + Math.sin(t * 3) * 14, -142, 24, 28, 0); K.shapeOL(ctx, '#c96f2a', 8);
    ctx.restore();
    legs(ctx, 0, 104, '#ffc861', [-92, -32, 32, 92], 48, '#f2a94e');
    K.ell(ctx, 0, -182, 134, 122, 0); K.shapeOL(ctx, '#ffc861', 10);      // body
    K.fillEll(ctx, 0, -132, 80, 62, '#ffe0a8');
    // mane: two rings of lobes, counter-rotating very slowly
    var cx = 0, cy = -348;
    for (var ring = 0; ring < 2; ring++) {
      var n = ring ? 13 : 11, rad = ring ? 172 : 142;
      var spin = (ring ? 1 : -1) * Math.sin(t * 0.8) * 0.06 + (roar * 0.06);
      for (var i = 0; i < n; i++) {
        var a = (i / n) * K.TAU + spin + ring * 0.24;
        var wob = 1 + Math.sin(t * 3 + i * 1.3) * 0.05 + roar * 0.07;
        K.ell(ctx, cx + Math.cos(a) * rad * wob, cy + Math.sin(a) * rad * wob,
              48, 44, a);
        K.shapeOL(ctx, ring ? '#e07a2c' : '#f2903c', 9);
      }
    }
    for (var e2 = -1; e2 <= 1; e2 += 2) {                                  // ears
      K.ell(ctx, e2 * 96, -428, 32, 30, 0); K.shapeOL(ctx, '#ffc861', 8);
      K.fillEll(ctx, e2 * 96, -426, 16, 15, '#ff9b9b');
    }
    K.ell(ctx, cx, cy, 118, 112, 0); K.shapeOL(ctx, '#ffd98c', 10);        // face
    K.ell(ctx, -36, -306, 46, 34, 0); K.shapeOL(ctx, '#fff0d1', 8);
    K.ell(ctx, 36, -306, 46, 34, 0); K.shapeOL(ctx, '#fff0d1', 8);
    mouth(ctx, 0, -300, 68 + roar * 34, roar, INK,
          function (c) { K.ell(c, cx, cy, 118, 112, 0); });
    ctx.beginPath(); ctx.moveTo(-20, -334); ctx.lineTo(20, -334); ctx.lineTo(0, -314);
    ctx.closePath(); K.shapeOL(ctx, '#c96f2a', 7);
    eye(ctx, -54, -382, 30, p); eye(ctx, 54, -382, 30, p);
  }};

  // --------------------------------------------------------------- monkey --
  A.monkey = { tint: '#a4703f', label: 'MONKEY', draw: function (ctx, p) {
    var t = p.t, swing = Math.sin(t * 3.6);
    // curly tail
    ctx.save(); ctx.translate(112, -196);
    ctx.beginPath(); ctx.moveTo(0, 0);
    ctx.bezierCurveTo(120, 10, 150, -110, 74, -120);
    ctx.bezierCurveTo(34, -126, 42, -74, 84, -76);
    ctx.lineCap = 'round';
    ctx.lineWidth = 30; ctx.strokeStyle = INK; ctx.stroke();
    ctx.lineWidth = 18; ctx.strokeStyle = '#a4703f'; ctx.stroke();
    ctx.restore();
    legs(ctx, 0, 92, '#a4703f', [-76, 76], 50, '#f0c896');
    K.ell(ctx, 0, -178, 124, 116, 0); K.shapeOL(ctx, '#a4703f', 10);      // body
    K.fillEll(ctx, 0, -164, 78, 82, '#f0c896');                           // belly
    // arms: one waves, one holds a banana
    ctx.save(); ctx.translate(-118, -246); ctx.rotate(-0.5 - swing * 0.45 - p.wave * 0.7);
    K.roundRect(ctx, -26, -6, 52, 132, 26); K.shapeOL(ctx, '#a4703f', 9);
    K.ell(ctx, 0, 128, 30, 26, 0); K.shapeOL(ctx, '#f0c896', 8);
    ctx.restore();
    ctx.save(); ctx.translate(118, -246); ctx.rotate(0.4 + swing * 0.2);
    K.roundRect(ctx, -26, -6, 52, 132, 26); K.shapeOL(ctx, '#a4703f', 9);
    ctx.save(); ctx.translate(30, 150); ctx.rotate(-0.85);                // banana
    ctx.beginPath(); ctx.moveTo(-58, -34);
    ctx.quadraticCurveTo(2, 56, 72, -8);
    ctx.quadraticCurveTo(54, 22, 34, 26);
    ctx.quadraticCurveTo(-6, 34, -40, -30);
    ctx.closePath(); K.shapeOL(ctx, '#ffd23f', 8);
    K.roundRect(ctx, -66, -46, 22, 22, 8); K.shapeOL(ctx, '#8f5f33', 7);
    ctx.restore();
    K.ell(ctx, 0, 128, 30, 26, 0); K.shapeOL(ctx, '#f0c896', 8);
    ctx.restore();
    for (var e = -1; e <= 1; e += 2) {                                     // ears
      K.ell(ctx, e * 122, -322, 44, 46, 0); K.shapeOL(ctx, '#a4703f', 9);
      K.fillEll(ctx, e * 122, -322, 24, 26, '#f0c896');
    }
    K.ell(ctx, 0, -330, 116, 110, 0); K.shapeOL(ctx, '#a4703f', 10);       // head
    K.ell(ctx, 0, -312, 90, 84, 0); K.shapeOL(ctx, '#f0c896', 8);          // face
    K.fillEll(ctx, 0, -400, 54, 26, '#8f5f33');                            // fringe
    K.fillEll(ctx, -26, -300, 9, 7, '#8f5f33');
    K.fillEll(ctx, 26, -300, 9, 7, '#8f5f33');
    mouth(ctx, 0, -288, 60, p.mouth, INK,
          function (c) { K.ell(c, 0, -312, 90, 84, 0); });
    eye(ctx, -40, -350, 27, p); eye(ctx, 40, -350, 27, p);
    cheeks(ctx, 78, -318, 18, 'rgba(255,120,120,0.32)');
  }};

  // ------------------------------------------------------------- elephant --
  A.elephant = { tint: '#b9a7d9', label: 'ELEPHANT', draw: function (ctx, p) {
    var t = p.t, flap = Math.sin(t * 2.6) * 0.16, lift = p.mouth;
    ctx.save(); ctx.translate(160, -250);                                  // tail
    ctx.beginPath(); ctx.moveTo(0, 0);
    ctx.quadraticCurveTo(52, 20, 44 + Math.sin(t * 4) * 10, 96);
    ctx.lineCap = 'round';
    ctx.lineWidth = 24; ctx.strokeStyle = INK; ctx.stroke();
    ctx.lineWidth = 14; ctx.strokeStyle = '#a794c9'; ctx.stroke();
    ctx.restore();
    legs(ctx, 0, 118, '#b9a7d9', [-104, -38, 38, 104], 58, '#d6c9ee');
    K.ell(ctx, 0, -210, 168, 142, 0); K.shapeOL(ctx, '#c4b3e0', 10);       // body
    K.fillEll(ctx, 0, -150, 96, 66, '#ddd2f2');
    // ears flap behind the head
    for (var e = -1; e <= 1; e += 2) {
      ctx.save(); ctx.translate(e * 118, -352); ctx.rotate(e * (0.1 + flap));
      K.ell(ctx, e * 62, 6, 88, 104, 0); K.shapeOL(ctx, '#b9a7d9', 10);
      K.fillEll(ctx, e * 62, 10, 54, 68, '#d6c9ee');
      ctx.restore();
    }
    // trunk: the upper curve stays put, only the lower half swings up to toot
    var relaxed = [[40, -122], [-16, -44]], up = [[96, -156], [140, -214]];
    var c2 = [K.lerp(relaxed[0][0], up[0][0], lift), K.lerp(relaxed[0][1], up[0][1], lift)];
    var c3 = [K.lerp(relaxed[1][0], up[1][0], lift), K.lerp(relaxed[1][1], up[1][1], lift)];
    var tr = K.taper(ctx, [0, -300], [48, -238], c2, c3, 44, 15, 30);
    K.shapeOL(ctx, '#b3a0d6', 10);
    K.ell(ctx, tr.tip[0], tr.tip[1], 15, 15, 0); K.shapeOL(ctx, '#b3a0d6', 10);
    for (var r = 5; r < 28; r += 5) {                                      // trunk rings
      ctx.beginPath();
      ctx.moveTo(tr.L[r][0], tr.L[r][1]); ctx.lineTo(tr.R[r][0], tr.R[r][1]);
      ctx.lineWidth = 5; ctx.strokeStyle = 'rgba(90,70,120,0.28)'; ctx.stroke();
    }
    if (lift > 0.3) {                                                      // toot puffs
      for (var pf = 0; pf < 3; pf++) {
        var g = K.sat((lift - 0.3) / 0.7);
        ctx.globalAlpha = K.sat(1 - g * 0.5) * 0.8;
        K.circle(ctx, tr.tip[0] + 24 + g * 50 * (pf + 1), tr.tip[1] - 16 - pf * 24 - g * 18,
                 11 + g * 14 + pf * 4, '#ffffff');
      }
      ctx.globalAlpha = 1;
    }
    K.ell(ctx, 0, -356, 126, 120, 0); K.shapeOL(ctx, '#c4b3e0', 10);       // head
    for (var s = -1; s <= 1; s += 2) {                                     // tusks
      ctx.save(); ctx.translate(s * 74, -286); ctx.rotate(s * 0.34);
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.quadraticCurveTo(s * 10, 34, s * 2, 56);
      ctx.lineCap = 'round'; ctx.lineWidth = 22; ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = 13; ctx.strokeStyle = '#fffdf5'; ctx.stroke();
      ctx.restore();
    }
    eye(ctx, -54, -388, 28, p); eye(ctx, 54, -388, 28, p);
    cheeks(ctx, 98, -336, 20, 'rgba(255,120,150,0.3)');
  }};

  global.ANIMAL_ORDER = ['cow', 'duck', 'cat', 'dog', 'frog', 'lion', 'monkey', 'elephant'];
})(typeof window !== 'undefined' ? window : this);
