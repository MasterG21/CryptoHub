/*
 * rig.js - shared character machinery: materials, the parts every animal has
 * (eyes that blink, a mouth that actually forms vowels), and the per-frame
 * update that turns lip-sync curves and moods into pose.
 */
import * as THREE from 'three';

export const TAU = Math.PI * 2;

// One cache so six characters do not build sixty materials.
const matCache = new Map();
// Phong is several times cheaper to shade than Standard on a software
// rasteriser and, for flat toy colours, looks all but identical.
export const QUALITY = {
  phong: true, seg: 20,
  read() {
    const q = new URLSearchParams(location.search);
    if (q.has('mat')) this.phong = q.get('mat') !== 'standard';
    if (q.has('seg')) this.seg = +q.get('seg');
    return this;
  },
};
export function mat(color, opts = {}) {
  const key = color + JSON.stringify(opts);
  if (!matCache.has(key)) {
    const rough = opts.rough ?? 0.72;
    matCache.set(key, QUALITY.phong
      ? new THREE.MeshPhongMaterial({
          color: new THREE.Color(color),
          shininess: Math.max(2, (1 - rough) * 70),
          specular: new THREE.Color(0x111111).multiplyScalar(1 - rough),
          ...opts.extra,
        })
      : new THREE.MeshStandardMaterial({
          color: new THREE.Color(color), roughness: rough, metalness: 0, ...opts.extra,
        }));
  }
  return matCache.get(key);
}

const geoCache = new Map();
function geo(key, make) {
  if (!geoCache.has(key)) geoCache.set(key, make());
  return geoCache.get(key);
}
export const sphere = (seg = QUALITY.seg) => geo('s' + seg, () => new THREE.SphereGeometry(1, seg, Math.round(seg * 0.75)));
export const capsule = (r = 0.5, l = 1) => geo(`c${r}_${l}`, () => new THREE.CapsuleGeometry(r, l, 8, 20));
export const cone = (seg = 20) => geo('co' + seg, () => new THREE.ConeGeometry(1, 1, seg));
export const torus = (tube = 0.28) => geo('t' + tube, () => new THREE.TorusGeometry(1, tube, 12, 28));
export const cyl = (seg = 18) => geo('cy' + seg, () => new THREE.CylinderGeometry(1, 1, 1, seg));

export function ball(color, r, pos, opts = {}) {
  const m = new THREE.Mesh(sphere(opts.seg ?? QUALITY.seg), mat(color, opts));
  m.scale.setScalar(r);
  if (pos) m.position.set(pos[0], pos[1], pos[2]);
  m.castShadow = opts.shadow !== false;
  m.receiveShadow = opts.shadow !== false;
  return m;
}

export function blob(color, sx, sy, sz, pos, opts = {}) {
  const m = ball(color, 1, pos, opts);
  m.scale.set(sx, sy, sz);
  return m;
}

/* ---------------------------------------------------------------- eyes ---
 * An eyeball, a dark iris with a bright catch-light, and a lid in the body
 * colour that slides down to blink. Dead unblinking eyes are what makes a
 * cartoon face unsettling, so every character blinks on its own cadence.
 */
export function makeEye(parent, { x, y, z, r, skin, tilt = 0 }) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  g.rotation.z = tilt;
  const white = ball('#ffffff', r, [0, 0, 0], { rough: 0.35 });
  const iris = ball('#2b2333', r * 0.52, [0, 0, r * 0.62], { rough: 0.22 });
  const spark = ball('#ffffff', r * 0.2, [-r * 0.2, r * 0.26, r * 0.92], { rough: 0.1 });
  const spark2 = ball('#ffffff', r * 0.1, [r * 0.22, -r * 0.2, r * 0.9], { rough: 0.1 });
  const lid = ball(skin, r * 1.07, [0, r * 1.6, -r * 1.3], { rough: 0.8, shadow: false });
  const brow = blob(skin, r * 0.74, r * 0.10, r * 0.30, [0, r * 1.78, r * 0.46], { rough: 0.8, shadow: false });
  g.add(white, iris, spark, spark2, lid, brow);
  parent.add(g);
  return { group: g, white, iris, spark, lid, brow, r };
}

/* ---------------------------------------------------------------- mouth ---
 * A dark cavity that scales open, a tongue, and a separate smile arc that
 * takes over when the mouth is shut, so a silent character still looks warm.
 */
function lipTone(skin) {
  const c = new THREE.Color(skin);
  c.offsetHSL(0, 0.05, -0.14);
  return '#' + c.getHexString();
}

export function makeMouth(parent, { x, y, z, w, h, skin, lip }) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  const cavity = new THREE.Mesh(sphere(22), mat('#5d2436', { rough: 0.85 }));
  cavity.scale.set(w, h, w * 0.6);
  const tongue = new THREE.Mesh(sphere(16), mat('#ff8fa3', { rough: 0.6 }));
  tongue.scale.set(w * 0.62, h * 0.42, w * 0.42);
  tongue.position.set(0, -h * 0.42, w * 0.16);
  const smile = new THREE.Mesh(torus(0.16), mat('#5d2436', { rough: 0.8 }));
  smile.scale.set(w * 0.92, w * 0.92, w * 0.92);
  smile.rotation.x = Math.PI * 0.5;
  smile.position.z = w * 0.1;
  const lips = new THREE.Mesh(torus(0.15), mat(lip || lipTone(skin), { rough: 0.62 }));
  lips.rotation.x = Math.PI * 0.5;
  g.add(cavity, tongue, smile, lips);
  parent.add(g);
  return { group: g, cavity, tongue, smile, lips, w, h };
}

/* --------------------------------------------------------------- update --- */
const MOODS = {
  neutral:  { brow: 0.0,  squint: 0.0,  tilt: 0.0,  lift: 0.0 },
  happy:    { brow: 0.12, squint: 0.30, tilt: 0.04, lift: 0.03 },
  surprise: { brow: 0.34, squint: -0.2, tilt: -0.05, lift: 0.06 },
  ask:      { brow: 0.20, squint: 0.05, tilt: 0.16, lift: 0.02 },
  think:    { brow: 0.10, squint: 0.15, tilt: 0.12, lift: 0.0 },
};

// Deterministic per-character blink cadence - no Math.random in the draw path.
function blinkAmount(t, seed) {
  const period = 3.1 + (seed % 7) * 0.31;
  const ph = (t + seed * 1.7) % period;
  const d = 0.16;
  if (ph > period - d) return Math.sin(((ph - (period - d)) / d) * Math.PI);
  const half = (t + seed * 1.7 + period * 0.5) % (period * 2.2);
  if (half < d * 0.9) return Math.sin((half / (d * 0.9)) * Math.PI) * 0.8;
  return 0;
}

export function updateCharacter(c, s) {
  const t = s.t;
  const mood = MOODS[s.mood] || MOODS.neutral;
  const talk = s.open || 0;

  // breathing, and a livelier bounce while speaking
  const breath = Math.sin(t * 1.9 + c.seed) * 0.014;
  const bounce = s.talking ? Math.abs(Math.sin(t * 6.2 + c.seed)) * 0.02 * (0.4 + talk) : 0;
  c.body.scale.set(
    c.bodyScale.x * (1 - breath * 0.5),
    c.bodyScale.y * (1 + breath + bounce),
    c.bodyScale.z * (1 - breath * 0.5));
  c.root.position.y = c.baseY + (s.hop || 0) + bounce * 0.6;

  // head: turn toward whoever is being addressed, plus talk bob and mood tilt
  const look = s.look || { x: 0, y: 0 };
  const bob = s.talking ? Math.sin(t * 9.4 + c.seed) * 0.03 * talk : 0;
  c.head.rotation.y = look.x * 0.55 + Math.sin(t * 0.7 + c.seed) * 0.03;
  c.head.rotation.x = -look.y * 0.4 + bob + mood.lift + Math.sin(t * 1.1 + c.seed) * 0.02;
  c.head.rotation.z = mood.tilt + Math.sin(t * 0.53 + c.seed * 2) * 0.02;

  // eyes
  const blink = Math.max(blinkAmount(t, c.seed), s.forceBlink || 0);
  for (const e of c.eyes) {
    const closed = Math.min(1, blink + mood.squint * 0.55);
    // parked behind the eyeball (inside the head) when open, concentric when shut
    e.lid.position.y = e.r * 1.6 * (1 - closed);
    e.lid.position.z = -e.r * 1.3 * (1 - closed);
    e.brow.position.y = e.r * (1.78 + mood.brow);
    e.brow.rotation.z = (e.group.position.x > 0 ? -1 : 1) * mood.brow * 0.5;
    e.iris.position.x = look.x * e.r * 0.3;
    e.iris.position.y = look.y * e.r * 0.22;
    e.spark.position.x = -e.r * 0.2 + look.x * e.r * 0.3;
    e.spark.position.y = e.r * 0.26 + look.y * e.r * 0.22;
  }

  // mouth: `open` drops the jaw, `wide` chooses between an "ee" and an "oo"
  if (c.mouth) {
    const m = c.mouth;
    const wide = s.wide ?? 0.5;
    const open = Math.max(0.02, talk);
    const sx = m.w * (0.72 + wide * 0.55) * (1 + open * 0.18);
    const sy = m.h * (0.06 + open * 1.05) * (1.25 - wide * 0.35);
    m.cavity.scale.set(sx, sy, m.w * 0.55);
    m.tongue.visible = open > 0.22;
    m.tongue.scale.set(sx * 0.6, sy * 0.36, m.w * 0.4);
    m.tongue.position.y = -sy * 0.42;
    m.smile.visible = open < 0.16;
    const sm = m.w * (0.9 + mood.squint * 0.3);
    m.smile.scale.set(sm, sm * 0.8, sm);
    if (m.lips) {
      m.lips.scale.set(sx * 1.16, sy * 1.5 + m.h * 0.30, m.w * 0.5);
      m.lips.visible = open >= 0.16;
    }
  }

  // ears, tails and arms keep a little life going at all times
  c.wigglers.forEach((w, i) => {
    const a = Math.sin(t * w.speed + c.seed + i) * w.amp;
    w.node.rotation[w.axis] = w.base + a + (s.talking ? talk * w.talk : 0);
  });

  if (c.armL && c.armR) {
    const g = s.gesture || 0;
    const sw = Math.sin(t * 2.2 + c.seed) * 0.09;
    c.armL.rotation.z = c.armRest + sw + g * 0.5;
    c.armR.rotation.z = -c.armRest - sw - g * 0.5;
    c.armL.rotation.x = -g * 0.7 - talk * 0.12 * (s.talking ? 1 : 0);
    c.armR.rotation.x = -g * 0.7 - talk * 0.12 * (s.talking ? 1 : 0);
  }
}
