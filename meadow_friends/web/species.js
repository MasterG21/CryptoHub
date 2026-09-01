/*
 * species.js - the six characters, built from primitives.
 *
 * Proportions are deliberately toy-like: big head, short limbs, wide-set eyes
 * with a strong catch-light. Everything is rounded, nothing is realistic -
 * that is what keeps them friendly rather than uncanny.
 */
import * as THREE from 'three';
import { ball, blob, mat, sphere, capsule, cone, cyl, torus,
         makeEye, makeMouth } from './rig.js';

// A bendable chain (trunk, tail): each link parents the next, so rotating a
// joint bends everything downstream for free.
function chain(parent, { n, r0, r1, len, color, pos, rough = 0.7 }) {
  const joints = [];
  let node = parent;
  for (let i = 0; i < n; i++) {
    const g = new THREE.Group();
    if (i === 0 && pos) g.position.set(pos[0], pos[1], pos[2]);
    else g.position.set(0, -len / n, 0);
    const r = r0 + (r1 - r0) * (i / Math.max(1, n - 1));
    const seg = ball(color, r, [0, 0, 0], { rough, seg: 18 });
    g.add(seg);
    node.add(g);
    joints.push(g);
    node = g;
  }
  return joints;
}

function legs(group, { color, xs, y, r, len }) {
  for (const x of xs) {
    const m = new THREE.Mesh(capsule(0.5, 1), mat(color));
    m.scale.set(r * 2, len, r * 2);
    m.position.set(x[0], y, x[1]);
    m.castShadow = true; m.receiveShadow = true;
    group.add(m);
  }
}

function arm(group, side, { color, x, y, z, r, len }) {
  const pivot = new THREE.Group();
  pivot.position.set(side * x, y, z);
  const m = new THREE.Mesh(capsule(0.5, 1), mat(color));
  m.scale.set(r * 2, len, r * 2);
  m.position.y = -len * 0.42;
  m.castShadow = true;
  const hand = ball(color, r * 1.18, [0, -len * 0.82, 0], { seg: 16 });
  pivot.add(m, hand);
  group.add(pivot);
  return pivot;
}

function whiskers(head, { y, z, color }) {
  for (const side of [-1, 1]) {
    for (let i = 0; i < 3; i++) {
      const w = new THREE.Mesh(cyl(6), mat(color, { rough: 0.9 }));
      w.scale.set(0.004, 0.115, 0.004);
      w.position.set(side * 0.12, y - i * 0.018, z);
      w.rotation.z = side * (1.15 + i * 0.16);
      w.rotation.x = -0.3;
      head.add(w);
    }
  }
}

/* ------------------------------------------------------------------ mouse -- */
function mouse(C) {
  const g = new THREE.Group();
  const body = blob(C.body, 0.30, 0.33, 0.28, [0, 0.34, 0]);
  const belly = blob(C.belly, 0.21, 0.23, 0.15, [0, 0.30, 0.19], { shadow: false });
  g.add(body, belly);
  legs(g, { color: C.body, xs: [[-0.14, 0.02], [0.14, 0.02]], y: 0.09, r: 0.055, len: 0.1 });
  const armL = arm(g, -1, { color: C.body, x: 0.27, y: 0.44, z: 0.04, r: 0.055, len: 0.2 });
  const armR = arm(g, 1, { color: C.body, x: 0.27, y: 0.44, z: 0.04, r: 0.055, len: 0.2 });

  const head = new THREE.Group();
  head.position.set(0, 0.76, 0);
  g.add(head);
  head.add(ball(C.body, 0.30, [0, 0, 0]));
  const ears = [];
  for (const s of [-1, 1]) {
    const e = new THREE.Group();
    e.position.set(s * 0.24, 0.23, -0.02);
    e.add(blob(C.body, 0.17, 0.17, 0.045, [0, 0, 0]));
    e.add(blob(C.inner, 0.115, 0.115, 0.03, [0, 0, 0.035], { shadow: false }));
    e.rotation.z = s * 0.3;
    head.add(e); ears.push(e);
  }
  head.add(blob(C.belly, 0.15, 0.12, 0.15, [0, -0.05, 0.22], { shadow: false }));
  head.add(ball(C.nose, 0.045, [0, -0.035, 0.35], { rough: 0.35 }));
  whiskers(head, { y: -0.05, z: 0.3, color: '#d8cfe6' });
  const eyes = [
    makeEye(head, { x: -0.115, y: 0.07, z: 0.245, r: 0.075, skin: C.body }),
    makeEye(head, { x: 0.115, y: 0.07, z: 0.245, r: 0.075, skin: C.body }),
  ];
  const mouth = makeMouth(head, { x: 0, y: -0.115, z: 0.30, w: 0.085, h: 0.075, skin: C.body, lip: C.inner });

  const tail = chain(g, { n: 6, r0: 0.035, r1: 0.016, len: 0.5, color: C.inner,
                          pos: [0, 0.32, -0.26] });
  tail[0].rotation.x = -1.1;
  tail.slice(1).forEach((j, i) => { j.rotation.x = 0.28 + i * 0.05; });

  return { group: g, head, body, eyes, mouth, armL, armR, armRest: 0.32,
           bodyScale: body.scale.clone(), height: 1.06, headY: 0.76, headR: 0.30,
           wigglers: [
             { node: ears[0], axis: 'z', base: 0.3, amp: 0.06, speed: 2.4, talk: 0.05 },
             { node: ears[1], axis: 'z', base: -0.3, amp: -0.06, speed: 2.4, talk: -0.05 },
             { node: tail[1], axis: 'z', base: 0, amp: 0.16, speed: 2.9, talk: 0.1 },
             { node: tail[3], axis: 'z', base: 0, amp: 0.2, speed: 3.3, talk: 0.1 },
           ] };
}

/* --------------------------------------------------------------- elephant -- */
function elephant(C) {
  const g = new THREE.Group();
  const body = blob(C.body, 0.52, 0.47, 0.46, [0, 0.62, 0]);
  const belly = blob(C.belly, 0.36, 0.32, 0.22, [0, 0.55, 0.32], { shadow: false });
  g.add(body, belly);
  legs(g, { color: C.body, xs: [[-0.28, 0.2], [0.28, 0.2], [-0.26, -0.2], [0.26, -0.2]],
            y: 0.17, r: 0.115, len: 0.2 });

  const head = new THREE.Group();
  head.position.set(0, 1.14, 0.08);
  g.add(head);
  head.add(ball(C.body, 0.40, [0, 0, 0]));
  const ears = [];
  for (const s of [-1, 1]) {
    const e = new THREE.Group();
    e.position.set(s * 0.36, 0.04, -0.06);
    e.add(blob(C.body, 0.28, 0.32, 0.055, [s * 0.16, 0, 0]));
    e.add(blob(C.inner, 0.19, 0.22, 0.035, [s * 0.16, 0, 0.03], { shadow: false }));
    e.rotation.y = s * 0.35;
    head.add(e); ears.push(e);
  }
  const eyes = [
    makeEye(head, { x: -0.165, y: 0.09, z: 0.315, r: 0.088, skin: C.body }),
    makeEye(head, { x: 0.165, y: 0.09, z: 0.315, r: 0.088, skin: C.body }),
  ];
  // tusks
  for (const s of [-1, 1]) {
    const t = new THREE.Mesh(cone(14), mat('#fffaf0', { rough: 0.4 }));
    t.scale.set(0.045, 0.16, 0.045);
    t.position.set(s * 0.17, -0.24, 0.275);
    t.rotation.x = 0.5; t.rotation.z = s * 0.25;
    t.castShadow = true;
    head.add(t);
  }
  // trunk hangs to the character's left so it never covers the mouth
  const trunk = chain(head, { n: 10, r0: 0.13, r1: 0.045, len: 1.18, color: C.body,
                              pos: [-0.03, -0.05, 0.35] });
  trunk[0].rotation.x = 0.22;
  trunk[0].rotation.z = -0.80;                 // sweep it clear of the mouth
  trunk.forEach((j, i) => { if (i) { j.rotation.x = 0.10; j.rotation.z = -0.10; } });
  const mouth = makeMouth(head, { x: 0.10, y: -0.225, z: 0.30, w: 0.105, h: 0.088, skin: C.body, lip: C.inner });

  const tail = chain(g, { n: 4, r0: 0.028, r1: 0.014, len: 0.34, color: C.body,
                          pos: [0, 0.72, -0.46] });
  tail[0].rotation.x = -0.25;

  return { group: g, head, body, eyes, mouth, armRest: 0,
           bodyScale: body.scale.clone(), height: 1.62, headY: 1.14, headR: 0.40,
           wigglers: [
             { node: ears[0], axis: 'y', base: -0.35, amp: 0.16, speed: 1.7, talk: 0.1 },
             { node: ears[1], axis: 'y', base: 0.35, amp: -0.16, speed: 1.7, talk: -0.1 },
             { node: trunk[2], axis: 'z', base: -0.10, amp: 0.09, speed: 1.5, talk: 0.12 },
             { node: trunk[5], axis: 'z', base: -0.10, amp: 0.13, speed: 1.9, talk: 0.18 },
             { node: tail[1], axis: 'z', base: 0, amp: 0.18, speed: 2.6, talk: 0 },
           ] };
}

/* -------------------------------------------------------------------- cow -- */
function cow(C) {
  const g = new THREE.Group();
  const body = blob(C.body, 0.46, 0.40, 0.42, [0, 0.60, 0]);
  g.add(body, blob(C.belly, 0.32, 0.26, 0.20, [0, 0.52, 0.30], { shadow: false }));
  for (const p of [[-0.30, 0.66, 0.24, 0.15], [0.28, 0.74, -0.10, 0.13], [0.16, 0.44, 0.30, 0.10]]) {
    const s = blob('#4c4256', p[3], p[3] * 0.85, p[3] * 0.8, [p[0], p[1], p[2]], { shadow: false });
    g.add(s);
  }
  legs(g, { color: C.body, xs: [[-0.24, 0.18], [0.24, 0.18], [-0.22, -0.18], [0.22, -0.18]],
            y: 0.17, r: 0.085, len: 0.2 });

  const head = new THREE.Group();
  head.position.set(0, 1.06, 0.1);
  g.add(head);
  head.add(ball(C.body, 0.33, [0, 0, 0]));
  head.add(blob('#4c4256', 0.15, 0.13, 0.10, [-0.16, 0.10, 0.24], { shadow: false }));
  const ears = [];
  for (const s of [-1, 1]) {
    const e = new THREE.Group();
    e.position.set(s * 0.31, 0.04, -0.02);
    e.add(blob(C.body, 0.13, 0.075, 0.07, [s * 0.06, 0, 0]));
    e.rotation.z = s * 0.4;
    head.add(e); ears.push(e);
  }
  for (const s of [-1, 1]) {                                   // horns
    const h = new THREE.Mesh(capsule(0.5, 1), mat('#f7e2b6', { rough: 0.5 }));
    h.scale.set(0.05, 0.09, 0.05);
    h.position.set(s * 0.17, 0.29, -0.02);
    h.rotation.z = s * 0.55;
    h.castShadow = true;
    head.add(h);
  }
  head.add(blob(C.inner, 0.20, 0.155, 0.15, [0, -0.13, 0.23], { shadow: false }));
  for (const s of [-1, 1]) head.add(ball('#e07f9c', 0.028, [s * 0.07, -0.09, 0.35], { shadow: false }));
  const eyes = [
    makeEye(head, { x: -0.145, y: 0.10, z: 0.255, r: 0.082, skin: C.body }),
    makeEye(head, { x: 0.145, y: 0.10, z: 0.255, r: 0.082, skin: C.body }),
  ];
  const mouth = makeMouth(head, { x: 0, y: -0.20, z: 0.30, w: 0.095, h: 0.075, skin: C.inner, lip: '#e07f9c' });
  const tail = chain(g, { n: 5, r0: 0.024, r1: 0.014, len: 0.46, color: C.body,
                          pos: [0, 0.74, -0.42] });
  tail[4].add(ball('#4c4256', 0.05, [0, -0.05, 0]));

  return { group: g, head, body, eyes, mouth, armRest: 0,
           bodyScale: body.scale.clone(), height: 1.44, headY: 1.06, headR: 0.33,
           wigglers: [
             { node: ears[0], axis: 'z', base: 0.4, amp: 0.12, speed: 2.2, talk: 0.08 },
             { node: ears[1], axis: 'z', base: -0.4, amp: -0.12, speed: 2.2, talk: -0.08 },
             { node: tail[1], axis: 'z', base: 0, amp: 0.22, speed: 2.4, talk: 0 },
           ] };
}

/* ------------------------------------------------------------------- duck -- */
function duck(C) {
  const g = new THREE.Group();
  const body = blob(C.body, 0.30, 0.29, 0.27, [0, 0.34, 0]);
  g.add(body, blob(C.belly, 0.21, 0.19, 0.14, [0, 0.29, 0.19], { shadow: false }));
  const wings = [];
  for (const s of [-1, 1]) {
    const w = new THREE.Group();
    w.position.set(s * 0.27, 0.37, 0);
    w.add(blob(C.belly, 0.09, 0.17, 0.15, [0, 0, 0]));
    head_tilt(w, s);
    g.add(w); wings.push(w);
  }
  function head_tilt(node, s) { node.rotation.z = s * 0.12; }
  for (const s of [-1, 1]) {                                     // webbed feet
    g.add(blob(C.inner, 0.09, 0.03, 0.12, [s * 0.11, 0.03, 0.05], { shadow: false }));
  }
  const head = new THREE.Group();
  head.position.set(0, 0.66, 0.02);
  g.add(head);
  head.add(ball(C.body, 0.235, [0, 0, 0]));
  const eyes = [
    makeEye(head, { x: -0.10, y: 0.06, z: 0.185, r: 0.062, skin: C.body }),
    makeEye(head, { x: 0.10, y: 0.06, z: 0.185, r: 0.062, skin: C.body }),
  ];
  // the beak *is* the mouth: the lower half hinges open
  const beak = new THREE.Group();
  beak.position.set(0, -0.055, 0.16);
  const upper = blob(C.inner, 0.115, 0.045, 0.15, [0, 0.02, 0.06]);
  const lowerPivot = new THREE.Group();
  const lower = blob('#f08517', 0.10, 0.035, 0.13, [0, -0.025, 0.06]);
  lowerPivot.add(lower);
  beak.add(upper, lowerPivot);
  head.add(beak);
  const tail = blob(C.body, 0.10, 0.08, 0.13, [0, 0.46, -0.28]);
  tail.rotation.x = -0.5; g.add(tail);

  return { group: g, head, body, eyes, beak: { lowerPivot }, armRest: 0,
           bodyScale: body.scale.clone(), height: 0.95, headY: 0.66, headR: 0.25,
           wigglers: [
             { node: wings[0], axis: 'z', base: 0.12, amp: 0.14, speed: 3.0, talk: 0.12 },
             { node: wings[1], axis: 'z', base: -0.12, amp: -0.14, speed: 3.0, talk: -0.12 },
           ] };
}

/* ------------------------------------------------------------------- frog -- */
function frog(C) {
  const g = new THREE.Group();
  const body = blob(C.body, 0.36, 0.25, 0.32, [0, 0.26, 0]);
  g.add(body, blob(C.belly, 0.25, 0.16, 0.20, [0, 0.20, 0.18], { shadow: false }));
  for (const s of [-1, 1]) {                                   // folded back legs
    const l = blob(C.body, 0.13, 0.11, 0.20, [s * 0.32, 0.16, -0.04]);
    g.add(l);
    g.add(blob(C.belly, 0.11, 0.035, 0.10, [s * 0.34, 0.04, 0.15], { shadow: false }));
    g.add(blob(C.belly, 0.07, 0.03, 0.08, [s * 0.16, 0.04, 0.24], { shadow: false }));
  }
  const head = new THREE.Group();
  head.position.set(0, 0.40, 0.02);
  g.add(head);
  head.add(blob(C.body, 0.31, 0.22, 0.26, [0, 0, 0]));
  const eyes = [];
  const lids = [];
  for (const s of [-1, 1]) {
    const socket = ball(C.body, 0.135, [s * 0.165, 0.15, 0.02], { seg: 20 });
    head.add(socket);
    eyes.push(makeEye(head, { x: s * 0.165, y: 0.175, z: 0.06, r: 0.105, skin: C.body }));
  }
  const mouth = makeMouth(head, { x: 0, y: -0.10, z: 0.20, w: 0.19, h: 0.075, skin: C.body, lip: C.inner });
  for (const s of [-1, 1]) head.add(ball('#4f9a35', 0.02, [s * 0.05, 0.02, 0.245], { shadow: false }));

  return { group: g, head, body, eyes, mouth, armRest: 0,
           bodyScale: body.scale.clone(), height: 0.7, headY: 0.44, headR: 0.30,
           wigglers: [] };
}

/* ------------------------------------------------------------------- lion -- */
function lion(C) {
  const g = new THREE.Group();
  const body = blob(C.body, 0.42, 0.37, 0.37, [0, 0.56, 0]);
  g.add(body, blob(C.belly, 0.29, 0.24, 0.18, [0, 0.49, 0.27], { shadow: false }));
  legs(g, { color: C.body, xs: [[-0.22, 0.17], [0.22, 0.17], [-0.20, -0.17], [0.20, -0.17]],
            y: 0.16, r: 0.08, len: 0.19 });

  const head = new THREE.Group();
  head.position.set(0, 1.0, 0.06);
  g.add(head);
  // mane first so the face sits proud of it
  const mane = new THREE.Group();
  for (let i = 0; i < 15; i++) {
    const a = (i / 15) * Math.PI * 2;
    const r = 0.30;
    const lobe = ball(i % 2 ? C.mane : '#e07a2c', 0.135,
                      [Math.cos(a) * r, Math.sin(a) * r, -0.06], { seg: 18 });
    mane.add(lobe);
  }
  head.add(mane);
  head.add(ball(C.body, 0.285, [0, 0, 0.05]));
  for (const s of [-1, 1]) {
    head.add(ball(C.body, 0.075, [s * 0.20, 0.26, 0.0]));
    head.add(ball(C.inner, 0.045, [s * 0.20, 0.265, 0.04], { shadow: false }));
  }
  for (const s of [-1, 1]) head.add(blob(C.belly, 0.11, 0.085, 0.09, [s * 0.075, -0.11, 0.26], { shadow: false }));
  head.add(ball(C.nose, 0.045, [0, -0.03, 0.31], { rough: 0.4 }));
  const eyes = [
    makeEye(head, { x: -0.125, y: 0.08, z: 0.245, r: 0.077, skin: C.body }),
    makeEye(head, { x: 0.125, y: 0.08, z: 0.245, r: 0.077, skin: C.body }),
  ];
  const mouth = makeMouth(head, { x: 0, y: -0.165, z: 0.29, w: 0.10, h: 0.085, skin: C.body, lip: C.inner });
  const tail = chain(g, { n: 5, r0: 0.026, r1: 0.016, len: 0.42, color: C.body,
                          pos: [0, 0.68, -0.38] });
  tail[4].add(ball(C.mane, 0.055, [0, -0.05, 0]));

  return { group: g, head, body, eyes, mouth, armRest: 0, mane,
           bodyScale: body.scale.clone(), height: 1.38, headY: 1.0, headR: 0.42,
           wigglers: [
             { node: mane, axis: 'z', base: 0, amp: 0.035, speed: 1.3, talk: 0.03 },
             { node: tail[1], axis: 'z', base: 0, amp: 0.2, speed: 2.5, talk: 0 },
           ] };
}

const BUILDERS = { mouse, elephant, cow, duck, frog, lion };

export function buildCharacter(key, spec, index) {
  const c = BUILDERS[spec.species](spec);
  c.key = key;
  c.seed = index * 2.7 + 1.3;
  c.root = new THREE.Group();
  c.root.add(c.group);
  c.baseY = 0;
  c.eyes = c.eyes || [];
  c.wigglers = c.wigglers || [];
  return c;
}
