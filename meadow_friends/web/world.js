/*
 * world.js - the set. One meadow, with prop groups that switch on per scene,
 * plus sky and lighting presets so morning, midday and golden hour feel
 * different without rebuilding anything.
 */
import * as THREE from 'three';
import { ball, blob, mat, sphere, cyl, cone, QUALITY } from './rig.js';

export const SKIES = {
  morning: { top: '#7ec8f0', bot: '#ffe9c9', sun: '#fff2d0', key: 2.05, amb: 1.05,
             keyPos: [-6, 8, 5], fog: '#cfe9f7' },
  day:     { top: '#5ab8f2', bot: '#d8f2ff', sun: '#fff8e8', key: 2.25, amb: 1.15,
             keyPos: [5, 10, 6], fog: '#d6eefb' },
  warm:    { top: '#6fc6ea', bot: '#ffe4bd', sun: '#ffeccf', key: 2.15, amb: 1.1,
             keyPos: [7, 7, 4], fog: '#f0e6d8' },
  golden:  { top: '#7fb8e8', bot: '#ffd9a0', sun: '#ffdda8', key: 2.3, amb: 1.0,
             keyPos: [-7, 5.5, 3], fog: '#f6e0c4' },
};

function gradientTexture(top, bottom) {
  const c = document.createElement('canvas');
  c.width = 8; c.height = 256;
  const g = c.getContext('2d');
  const grd = g.createLinearGradient(0, 0, 0, 256);
  grd.addColorStop(0, top);
  grd.addColorStop(0.62, bottom);
  grd.addColorStop(1, bottom);
  g.fillStyle = grd; g.fillRect(0, 0, 8, 256);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function tree(x, z, scale, tone) {
  const g = new THREE.Group();
  const trunk = new THREE.Mesh(cyl(8), mat('#8a5a3b'));
  trunk.scale.set(0.16, 1.1, 0.16);
  trunk.position.y = 0.55;
  g.add(trunk);
  const tones = ['#4fae5f', '#3f9c52', '#63c06d'];
  for (let i = 0; i < 4; i++) {
    const r = 0.62 - i * 0.07;
    const b = ball(tones[(i + tone) % 3], r,
                   [Math.cos(i * 2.3) * 0.26, 1.15 + i * 0.30, Math.sin(i * 2.3) * 0.26],
                   { seg: 12, rough: 0.9, shadow: false });
    g.add(b);
  }
  g.position.set(x, 0, z);
  g.scale.setScalar(scale);
  return g;
}

function bush(x, z, s, color = '#4aa757') {
  const g = new THREE.Group();
  for (let i = 0; i < 4; i++) {
    g.add(ball(color, 0.34 - i * 0.03,
               [Math.cos(i * 1.9) * 0.28, 0.24 + (i % 2) * 0.1, Math.sin(i * 1.9) * 0.22],
               { seg: 10, rough: 0.95, shadow: false }));
  }
  g.position.set(x, 0, z);
  g.scale.setScalar(s);
  return g;
}

// Flowers and grass tufts are instanced - there are hundreds of them.
function scatter(scene, count, geoMaker, material, place, seed) {
  const mesh = new THREE.InstancedMesh(geoMaker(), material, count);
  const m = new THREE.Matrix4();
  let s = seed;
  const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
  for (let i = 0; i < count; i++) {
    const p = place(rnd, i);
    m.compose(new THREE.Vector3(p.x, p.y, p.z),
              new THREE.Quaternion().setFromEuler(new THREE.Euler(p.rx || 0, p.ry || 0, p.rz || 0)),
              new THREE.Vector3(p.s, p.sy || p.s, p.s));
    mesh.setMatrixAt(i, m);
  }
  mesh.instanceMatrix.needsUpdate = true;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  scene.add(mesh);
  return mesh;
}

export function buildWorld(scene, renderer, shadowSize = 1024) {
  const world = { sets: {}, sky: null, lights: {}, clouds: [] };

  // ---- ground: a big disc with gentle rolling hills behind ----
  const groundGeo = new THREE.CircleGeometry(90, 64);
  groundGeo.rotateX(-Math.PI / 2);
  const ground = new THREE.Mesh(groundGeo, mat('#6cc25c', { rough: 1 }));
  ground.receiveShadow = true;
  scene.add(ground);

  const hills = new THREE.Group();
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * Math.PI * 2 + 0.3;
    const d = 26 + (i % 3) * 7;
    const h = blob(i % 2 ? '#5cb04f' : '#69bd58',
                   8 + (i % 4) * 2.4, 3.4 + (i % 3) * 1.1, 8 + (i % 4) * 2.4,
                   [Math.cos(a) * d, -0.6, Math.sin(a) * d], { seg: 12, shadow: false });
    hills.add(h);
  }
  scene.add(hills);

  // ---- clouds ----
  for (let i = 0; i < 5; i++) {
    const g = new THREE.Group();
    for (let j = 0; j < 3; j++) {
      g.add(ball('#ffffff', 1.1 + (j % 3) * 0.4,
                 [(j - 1) * 1.35, (j % 2) * 0.45, (j % 3) * 0.5 - 0.5],
                 { seg: 10, rough: 1, shadow: false }));
    }
    g.position.set(Math.cos(i * 1.4) * (22 + i), 11 + (i % 4) * 2.4, Math.sin(i * 1.4) * (22 + i));
    g.scale.setScalar(0.9 + (i % 3) * 0.35);
    scene.add(g);
    world.clouds.push(g);
  }

  // ---- always-on dressing ----
  const base = new THREE.Group();
  [[-7.5, -6, 1.15, 0], [7.8, -7, 1.3, 1], [-11, -2, 1.0, 2], [11.5, -3.5, 1.1, 1],
   [-5.5, -12, 1.4, 2], [6.0, -13, 1.25, 0]].forEach(t => base.add(tree(t[0], t[1], t[2], t[3])));
  [[-4.2, -3.2, 1.0], [4.6, -3.6, 1.1], [-8.5, -1.2, 0.8], [8.2, -1.6, 0.9]]
    .forEach(b => base.add(bush(b[0], b[1], b[2])));
  scene.add(base);

  const flowerMat = [mat('#ffd84a', { rough: 0.85 }), mat('#ff7fa8', { rough: 0.85 }),
                     mat('#ffffff', { rough: 0.85 }), mat('#b98cf0', { rough: 0.85 })];
  flowerMat.forEach((mt, k) => scatter(scene, 54, () => new THREE.SphereGeometry(1, 7, 5), mt,
    rnd => {
      const a = rnd() * Math.PI * 2, d = 3.2 + rnd() * 12;
      return { x: Math.cos(a) * d, y: 0.10, z: Math.sin(a) * d - 1,
               s: 0.030 + rnd() * 0.016, sy: 0.026 + rnd() * 0.014 };
    }, 7 + k * 13));

  scatter(scene, 520, () => new THREE.ConeGeometry(1, 1, 5), mat('#5cb551', { rough: 1 }),
    rnd => {
      const a = rnd() * Math.PI * 2, d = 2.0 + rnd() * 15;
      return { x: Math.cos(a) * d, y: 0.05, z: Math.sin(a) * d - 1,
               s: 0.035 + rnd() * 0.025, sy: 0.10 + rnd() * 0.09, rz: (rnd() - 0.5) * 0.35 };
    }, 991);

  // ---- per-scene prop groups ----
  const field = new THREE.Group();          // cow: a low fence and a hay bale
  for (let i = -5; i <= 5; i++) {
    const post = new THREE.Mesh(cyl(8), mat('#c39a6b'));
    post.scale.set(0.06, 0.62, 0.06);
    post.position.set(i * 1.15, 0.31, -3.6);
    field.add(post);
  }
  for (const y of [0.32, 0.5]) {
    const rail = new THREE.Mesh(cyl(8), mat('#d3ab7c'));
    rail.scale.set(0.045, 11.5, 0.045);
    rail.rotation.z = Math.PI / 2;
    rail.position.set(0, y, -3.6);
    field.add(rail);
  }
  const hay = new THREE.Mesh(cyl(16), mat('#e8c56b', { rough: 1 }));
  hay.scale.set(0.62, 0.75, 0.62);
  hay.rotation.z = Math.PI / 2;
  hay.position.set(5.4, 0.62, -3.2);
  hay.receiveShadow = true;
  field.add(hay);
  scene.add(field);
  world.sets.field = field;

  // ---- pond ----
  const pond = new THREE.Group();
  const water = new THREE.Mesh(new THREE.CircleGeometry(3.9, 48),
    mat('#4fb8e8', { rough: 0.2, extra: { transparent: true, opacity: 0.93 } }));
  water.rotation.x = -Math.PI / 2;
  water.position.set(0, 0.035, -1.6);
  water.receiveShadow = true;
  pond.add(water);
  const bank = new THREE.Mesh(new THREE.TorusGeometry(3.9, 0.16, 8, 48), mat('#8a7a52', { rough: 1 }));
  bank.rotation.x = -Math.PI / 2;
  bank.position.set(0, 0.05, -1.6);
  pond.add(bank);
  for (let i = 0; i < 5; i++) {
    const a = i * 1.25 + 0.4;
    const pad = new THREE.Mesh(new THREE.CircleGeometry(0.44, 20), mat('#54b84c', { rough: 0.9 }));
    pad.rotation.x = -Math.PI / 2;
    pad.position.set(Math.cos(a) * 2.3, 0.06, Math.sin(a) * 1.7 - 1.6);
    pond.add(pad);
  }
  for (let i = 0; i < 26; i++) {                       // reeds
    const r = new THREE.Mesh(cyl(6), mat('#3f9c52', { rough: 1 }));
    const a = (i / 26) * Math.PI * 2;
    r.scale.set(0.022, 0.5 + (i % 4) * 0.16, 0.022);
    r.position.set(Math.cos(a) * 4.25, 0.3, Math.sin(a) * 4.25 - 1.6);
    r.rotation.z = Math.sin(i) * 0.13;
    pond.add(r);
  }
  scene.add(pond);
  world.sets.pond = pond;

  // ---- tall grass for the lion ----
  const tall = new THREE.Group();
  const tallMesh = new THREE.InstancedMesh(new THREE.ConeGeometry(1, 1, 5),
                                           mat('#c9a94e', { rough: 1 }), 260);
  {
    const m = new THREE.Matrix4();
    let s = 4242;
    const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
    for (let i = 0; i < 260; i++) {
      const a = rnd() * Math.PI * 2, d = 3.4 + rnd() * 9;
      m.compose(new THREE.Vector3(Math.cos(a) * d, 0.38, Math.sin(a) * d - 2),
                new THREE.Quaternion().setFromEuler(new THREE.Euler(0, rnd() * 3, (rnd() - 0.5) * 0.3)),
                new THREE.Vector3(0.11, 0.78 + rnd() * 0.5, 0.11));
      tallMesh.setMatrixAt(i, m);
    }
    tallMesh.instanceMatrix.needsUpdate = true;
  }
  tallMesh.receiveShadow = false;
  tall.add(tallMesh);
  scene.add(tall);
  world.sets.grass = tall;

  world.sets.meadow = new THREE.Group();
  scene.add(world.sets.meadow);

  // ---- lighting ----
  const hemi = new THREE.HemisphereLight('#cfeaff', '#6aa85c', 1.1);
  scene.add(hemi);
  const key = new THREE.DirectionalLight('#fff6e0', 2.2);
  key.position.set(5, 10, 6);
  key.castShadow = true;
  key.shadow.mapSize.set(shadowSize, shadowSize);
  key.shadow.camera.left = -7; key.shadow.camera.right = 7;
  key.shadow.camera.top = 7; key.shadow.camera.bottom = -5;
  key.shadow.camera.near = 2; key.shadow.camera.far = 26;
  key.shadow.bias = -0.0012;
  key.shadow.normalBias = 0.02;
  scene.add(key);
  // gentle fill from the front so faces never fall into shadow - a dark face
  // is most of what makes a cartoon character look sinister
  const fill = new THREE.DirectionalLight('#dceeff', 0.55);
  fill.position.set(-4, 3.4, 7);
  scene.add(fill);
  const rim = new THREE.DirectionalLight('#ffe3b0', 0.5);
  rim.position.set(0, 4, -8);
  scene.add(rim);
  world.lights = { hemi, key, fill, rim };

  world.skyTex = {};
  for (const k of Object.keys(SKIES)) world.skyTex[k] = gradientTexture(SKIES[k].top, SKIES[k].bot);

  world.applySky = (name) => {
    const s = SKIES[name] || SKIES.day;
    scene.background = world.skyTex[name] || world.skyTex.day;
    scene.fog = new THREE.Fog(new THREE.Color(s.fog), 26, 74);
    key.color.set(s.sun);
    key.intensity = s.key;
    key.position.set(s.keyPos[0], s.keyPos[1], s.keyPos[2]);
    hemi.intensity = s.amb;
  };
  world.showSet = (name) => {
    for (const [k, g] of Object.entries(world.sets)) g.visible = (k === name);
    field.visible = name === 'field';
    pond.visible = name === 'pond';
    tall.visible = name === 'grass';
  };
  world.tick = (t) => {
    world.clouds.forEach((c, i) => {
      c.position.x += 0.0016 * (1 + (i % 3) * 0.4);
      if (c.position.x > 42) c.position.x = -42;
      c.position.y += Math.sin(t * 0.4 + i) * 0.0012;
    });
  };
  return world;
}
