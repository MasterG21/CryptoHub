/*
 * director.js - reads the timeline and decides, for any timestamp, where the
 * camera is, who is talking, where everyone is looking, and what the caption
 * says. Pure function of t, so the render is reproducible.
 */
import * as THREE from 'three';
import { buildCharacter } from './species.js';
import { updateCharacter } from './rig.js';

const CAPTION_COLOR = {
  milo: '#b98cf0', ellie: '#4aa3e0', bella: '#f26c6c',
  pip: '#f2a03c', hop: '#4cb85c', leo: '#e8873a',
};

export function buildDirector(scene, script, timeline, world) {
  const cast = {};
  Object.keys(script.cast).forEach((key, i) => {
    const c = buildCharacter(key, script.cast[key], i);
    c.root.visible = false;
    scene.add(c.root);
    cast[key] = c;
  });

  const scenes = {};
  for (const s of script.scenes) scenes[s.id] = s;

  const events = timeline.events;
  const cues = timeline.cues;
  const fps = timeline.meta.fps;

  // Where each shot puts the camera.
  //
  // A close-up is placed along the character's own facing vector, so we are
  // always looking at a face rather than the back of a head, and the distance
  // is derived from head size so a mouse and an elephant frame the same.
  const ASPECT = 16 / 9;
  function distForSpan(span, fovDeg, fill) {
    const halfH = Math.tan((fovDeg * Math.PI) / 360);
    return (span / 2) / (halfH * ASPECT * fill);
  }

  function frameFor(shot, sceneDef, present, t, shotT, shotLen) {
    const stage = sceneDef.stage;
    const drift = Math.sin(shotT * 0.42 + 1.2) * 0.045;
    const push = Math.min(1, shotT / Math.max(shotLen, 0.001));

    if (shot.startsWith('close:')) {
      const who = shot.split(':')[1];
      if (!stage[who]) return frameFor('wide', sceneDef, present, t, shotT, shotLen);
      const c = cast[who];
      const st = stage[who];
      const fov = 34;
      // follow the character's real gaze (body yaw + head turn) so a close-up
      // always lands on the face, never the back of the head
      const facing = c._gazeYaw ?? (st.face || 0) * 0.5;
      const angle = facing + 0.34 + drift;                // three-quarter view
      const dist = 5.9 * c.headR + 0.52 - push * 0.09;
      const target = new THREE.Vector3(st.x, c.headY - c.headR * 0.30, st.z);
      const pos = new THREE.Vector3(
        st.x + Math.sin(angle) * dist,
        c.headY + c.headR * 0.34 + Math.sin(shotT * 0.5) * 0.012,
        st.z + Math.cos(angle) * dist);
      return { pos, target, fov };
    }

    const keys = shot === 'two'
      ? present.filter(k => k === 'ellie' || k === 'milo')
      : present;
    const use = keys.length >= 2 ? keys : present;
    let minX = Infinity, maxX = -Infinity, maxY = 0, sumZ = 0;
    for (const k of use) {
      const st = stage[k];
      minX = Math.min(minX, st.x - 0.75);
      maxX = Math.max(maxX, st.x + 0.75);
      maxY = Math.max(maxY, cast[k].height);
      sumZ += st.z;
    }
    const cx = (minX + maxX) / 2;
    const cz = sumZ / use.length;
    const span = Math.max(maxX - minX, 2.0);
    const fov = shot === 'wide' ? 40 : 36;
    const fill = shot === 'wide' ? 0.78 : shot === 'group' ? 0.88 : 0.86;
    const back = distForSpan(span, fov, fill) - push * 0.22;
    const target = new THREE.Vector3(cx, maxY * 0.56, cz);
    const pos = new THREE.Vector3(
      cx + Math.sin(drift) * 0.9,
      maxY * (shot === 'wide' ? 0.86 : 0.72) + 0.30,
      cz + back);
    return { pos, target, fov };
  }

  // index of the event covering t
  function eventAt(t) {
    let lo = 0, hi = events.length - 1, idx = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (events[mid].start <= t) { idx = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return idx;
  }

  // how long the current camera setup has been held (so pushes feel continuous)
  function shotSpan(idx) {
    const shot = events[idx].shot;
    let a = idx, b = idx;
    while (a > 0 && events[a - 1].shot === shot &&
           events[a - 1].scene === events[idx].scene) a--;
    while (b < events.length - 1 && events[b + 1].shot === shot &&
           events[b + 1].scene === events[idx].scene) b++;
    return { start: events[a].start, end: events[b].end };
  }

  const camera = new THREE.PerspectiveCamera(38, 16 / 9, 0.1, 120);
  let lastScene = null;
  let lastDbg = {};

  function update(t) {
    const idx = eventAt(t);
    const ev = events[idx];
    lastDbg = { shot: ev.shot, kind: ev.kind, who: ev.who || null, scene: ev.scene };
    const sceneDef = scenes[ev.scene];
    const present = Object.keys(sceneDef.stage);

    if (ev.scene !== lastScene) {
      lastScene = ev.scene;
      world.showSet(ev.set);
      world.applySky(ev.sky);
      for (const key of Object.keys(cast)) {
        const c = cast[key];
        const st = sceneDef.stage[key];
        c.root.visible = !!st;
        if (st) {
          c.root.position.set(st.x, 0, st.z);
          c.root.rotation.y = (st.face || 0) * 0.5;
        }
      }
    }
    world.tick(t);

    const speaking = (ev.kind === 'line' || ev.kind === 'chorus');
    const speakerKey = speaking ? ev.who : null;
    const inSpeech = speaking && t >= ev.start && t < ev.start + ev.dur;
    const f = inSpeech ? Math.min(ev.open.length - 1,
                                  Math.floor((t - ev.start) * fps)) : -1;

    for (const key of present) {
      const c = cast[key];
      const isSpeaker = key === speakerKey ||
        (ev.kind === 'chorus' && (ev.all || []).includes(key));
      const talking = isSpeaker && inSpeech;

      // everyone looks at whoever is talking; the talker looks at the listener
      let lookKey = speakerKey;
      if (isSpeaker) {
        lookKey = present.find(k => k !== key && (k === 'milo' || k === 'ellie')) ||
                  present.find(k => k !== key);
        // when a character asks the audience a question, they look at camera
        if (ev.mood === 'ask') lookKey = null;
      }
      let look = { x: 0, y: 0 };
      if (lookKey && sceneDef.stage[lookKey]) {
        const a = sceneDef.stage[key], b = sceneDef.stage[lookKey];
        const dx = b.x - a.x, dz = b.z - a.z;
        const yaw = Math.atan2(dx, dz) - c.root.rotation.y;
        look.x = Math.max(-0.62, Math.min(0.62, Math.sin(yaw) * 0.95));
        const dh = (cast[lookKey].height - c.height) * 0.5;
        look.y = Math.max(-0.6, Math.min(0.6, dh));
      }

      const hop = talking && ev.mood === 'happy'
        ? Math.max(0, Math.sin((t - ev.start) * 5.2)) * 0.02 : 0;

      updateCharacter(c, {
        t,
        open: talking ? ev.open[f] : 0,
        wide: talking ? ev.wide[f] : 0.5,
        talking,
        mood: talking ? (ev.mood || 'neutral') : (isSpeaker ? 'neutral' : 'happy'),
        look,
        hop,
        gesture: talking ? Math.max(0, ev.open[f] - 0.55) * 0.7 : 0,
      });
      if (c.beak) {
        const open = talking ? ev.open[f] : 0;
        c.beak.lowerPivot.rotation.x = open * 0.55;
      }
      c._gazeYaw = c.root.rotation.y + c.head.rotation.y;
    }

    // camera
    const span = shotSpan(idx);
    const frame = frameFor(ev.shot, sceneDef, present, t, t - span.start,
                           Math.max(0.4, span.end - span.start));
    camera.position.copy(frame.pos);
    camera.lookAt(frame.target);
    if (camera.fov !== frame.fov) { camera.fov = frame.fov; camera.updateProjectionMatrix(); }

    // caption / title
    if (ev.kind === 'title') {
      const a = Math.min(1, (t - ev.start) / 0.6) * Math.min(1, (ev.start + ev.dur - t) / 0.6);
      return { title: script.meta.title, subtitle: script.meta.episode, alpha: Math.max(0, a) };
    }
    let cue = null;
    for (const c of cues) {
      if (t >= c.a - 0.12 && t <= c.b + 0.22) { cue = c; break; }
    }
    if (!cue) return { text: '' };
    const idxColon = cue.text.indexOf(': ');
    const text = idxColon > 0 && idxColon < 12 ? cue.text.slice(idxColon + 2) : cue.text;
    return { text, color: CAPTION_COLOR[speakerKey] || '#ff6b9d' };
  }

  const _u = update;
  function updateWrapped(t) {
    const r = _u(t);
    lastDbg.caption = r.text || r.title || '';
    return r;
  }
  return {
    camera, cast, update: updateWrapped,
    debug: () => ({
      ...lastDbg,
      cam: camera.position.toArray().map(v => +v.toFixed(2)),
      fov: camera.fov,
      chars: Object.fromEntries(Object.entries(cast)
        .filter(([, c]) => c.root.visible)
        .map(([k, c]) => [k, { pos: c.root.position.toArray().map(v => +v.toFixed(2)),
                               ry: +c.root.rotation.y.toFixed(2),
                               headY: c.headY, headR: c.headR }])),
    }),
  };
}
