// The whole 53-second skit as a pure function of time: poses, props,
// effects and dialogue are all derived from the clock, so the loop can be
// scrubbed to any moment.
import * as THREE from 'three';
import { project, shared } from './engine.js';
import { ballistic } from './fx.js';
import { LAYOUT } from './scene.js';
import { hash3 } from './voxel.js';

export const DURATION = 53.6;

// ---------------------------------------------------------------- helpers

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const seg = (t, a, b) => clamp01((t - a) / (b - a));
const lerp = (a, b, u) => a + (b - a) * u;
const E = {
  lin: (u) => u,
  inOut: (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2),
  out: (u) => 1 - Math.pow(1 - u, 3),
  in: (u) => u * u * u,
  back: (u) => {
    const c1 = 2.2, c3 = c1 + 1;
    return 1 + c3 * Math.pow(u - 1, 3) + c1 * Math.pow(u - 1, 2);
  },
  elastic: (u) => (u <= 0 ? 0 : u >= 1 ? 1 : Math.pow(2, -10 * u) * Math.sin((u * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1),
};
const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const lerpArr = (a, b, u) => a.map((v, i) => lerp(v, b[i], u));
const angLerp = (a, b, u) => {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return a + d * u;
};
const jit = (t, i, amp) => (hash3(Math.floor(t * 15), i, 7) - 0.5) * 2 * amp;

function blendBody(a, b, u) {
  return {
    root: [lerp(a.root[0], b.root[0], u), lerp(a.root[1], b.root[1], u), angLerp(a.root[2], b.root[2], u)],
    rootY: lerp(a.rootY || 0, b.rootY || 0, u),
    hipsY: lerp(a.hipsY, b.hipsY, u),
    hipsX: lerp(a.hipsX || 0, b.hipsX || 0, u),
    hipsZ: lerp(a.hipsZ || 0, b.hipsZ || 0, u),
    hips: lerpArr(a.hips, b.hips, u),
    spine: lerpArr(a.spine, b.spine, u),
    head: lerpArr(a.head, b.head, u),
  };
}

class Track {
  constructor(keys) {
    this.keys = keys;
  }
  at(t) {
    const k = this.keys;
    let i = 0;
    while (i + 1 < k.length && k[i + 1][0] <= t) i++;
    const [t0, dur, f, e] = k[i];
    const cur = f(t);
    if (i === 0 || !dur || t >= t0 + dur) return [cur, null, 1];
    const prev = k[i - 1][2](t);
    return [prev, cur, (e || E.inOut)(clamp01((t - t0) / dur))];
  }
}

function stepAt(keys, t) {
  let v = keys[0][1];
  for (const [k, val] of keys) if (k <= t) v = val;
  return v;
}

function resolve(rig, spec, out) {
  if (typeof spec === 'function') return out.copy(spec(rig));
  return rig.rootPoint(spec[0], spec[1], spec[2], out);
}

const _lim = { a: [V(), V(), V(), V()], b: [V(), V(), V(), V()] };
function applyActor(actor, track, t) {
  const [a, b, u] = track.at(t);
  actor.rig.setBody(b ? blendBody(a, b, u) : a);
  const names = ['hL', 'hR', 'fL', 'fR'];
  names.forEach((n, i) => resolve(actor.rig, a[n], _lim.a[i]));
  if (b) names.forEach((n, i) => _lim.a[i].lerp(resolve(actor.rig, b[n], _lim.b[i]), u));
  const dom = b && u >= 0.5 ? b : a;
  actor.rig.setLimbs(_lim.a[0], _lim.a[1], _lim.a[2], _lim.a[3], dom.poles || {});
  return dom;
}

// ---------------------------------------------------------------- student poses

const SEAT = [-10, -6, 0];
const STAND = [-10, -13, 0];
const S = (o) => ({
  root: SEAT,
  hipsY: 25,
  hips: [0.06, 0, 0],
  spine: [0.24, 0, 0],
  head: [0.24, 0, 0],
  fL: [6, 6, 15],
  fR: [-6, 6, 14],
  hL: [10, 43.5, 13],
  hR: [-4, 43.5, 18],
  poles: { armR: [-10, -9, -6], armL: [10, -9, -6] },
  ...o,
});
const STANDING = (o) =>
  S({
    root: STAND,
    hipsY: 38,
    hips: [0, 0, 0],
    spine: [0.04, 0, 0],
    head: [0.02, 0, 0],
    fL: [6, 6, 2],
    fR: [-6, 6, 0],
    hL: [15, 33, 2],
    hR: [-15, 33, 2],
    poles: {},
    ...o,
  });

const writeHand = (t, speed = 1, amp = 1) => {
  const line = (t * 0.45 * speed) % 1;
  return [-1 - line * 7 + Math.sin(t * 11 * speed) * 1.4 * amp, 43 + Math.max(0, Math.sin(t * 7 * speed)) * 0.8, 18 + Math.sin(t * 23 * speed) * 0.8 * amp];
};

// ---------------------------------------------------------------- philosopher poses

const ROCK_SEAT = [46, -9, 0.55];
const P = (o) => ({
  root: ROCK_SEAT,
  hipsY: 28,
  hips: [0.12, 0, 0],
  spine: [0.42, 0.15, 0.05],
  head: [-0.12, -0.05, 0.08],
  fL: [6, 6, 16],
  fR: [-8, 6, 12],
  hL: [9, 30, 19],
  hR: (rig) => rig.headPoint(-1, 1, 12),
  poles: { armR: [6, -10, 6], armL: [10, -4, -4] },
  ...o,
});

const PHIL_PATH = [
  [46, -9],
  [58, -20],
  [72, -34],
  [88, -50],
  [108, -70],
];
function philRunPos(u) {
  const n = PHIL_PATH.length - 1;
  const f = clamp01(u) * n;
  const i = Math.min(n - 1, Math.floor(f));
  const w = f - i;
  const a = PHIL_PATH[i], b = PHIL_PATH[i + 1];
  return [lerp(a[0], b[0], w), lerp(a[1], b[1], w)];
}

const runPose = (t, root, rootY, speed = 3.4, flail = true) => {
  const ph = t * Math.PI * 2 * speed;
  const s = Math.sin(ph), c = Math.cos(ph);
  return {
    root,
    rootY,
    hipsY: 35 + Math.abs(s) * 2.5,
    hips: [0.12, 0, 0],
    spine: [0.32, s * 0.12, 0],
    head: [-0.25, 0, 0],
    fL: [5, 6 + Math.max(0, s) * 11, -13 * c],
    fR: [-5, 6 + Math.max(0, -s) * 11, 13 * c],
    hL: flail ? [17, 72 + Math.sin(ph * 1.5) * 5, 6 + c * 3] : [14, 44, -12 * c],
    hR: flail ? [-17, 72 + Math.cos(ph * 1.5) * 5, 6 - c * 3] : [-14, 44, 12 * c],
    poles: { armL: [10, 4, -6], armR: [-10, 4, -6] },
  };
};

// ---------------------------------------------------------------- dialogue

const LINES = [
  ['s', 2.4, 5.0, 'UM... HOW DO I DO NUMBER 4?'],
  ['p', 5.2, 7.9, 'WHAT IS A NUMBER, TRULY?'],
  ['s', 8.0, 10.6, "I'M STUCK ON THE CHAIN RULE."],
  ['p', 10.8, 13.6, 'ALL OF US ARE BOUND BY CHAINS.'],
  ['p', 16.0, 19.0, 'THE ANSWER WAS INSIDE YOU ALL ALONG.'],
  ['s', 19.2, 20.8, 'IT WAS NOT.'],
  ['p', 21.6, 24.8, 'THE UNEXAMINED HOMEWORK IS NOT WORTH DOING.'],
  ['p', 28.3, 30.4, 'I THINK, THEREFORE I RUN!'],
  ['t', 37.6, 40.6, "YOU SOUND FRUSTRATED. LET'S SLOW DOWN."],
  ['t', 40.8, 43.6, "WHAT'S THE DERIVATIVE OF JUST X²?"],
  ['s', 43.8, 46.4, '...2X? OH! I GET IT!'],
  ['t', 46.6, 49.2, "EXACTLY. YOU'VE GOT THIS."],
  ['p', 49.6, 51.3, 'IS IT SAFE TO PONDER YET?'],
];
const TYPE_RATE = 30;
const talking = (who, t) =>
  LINES.some(([w, a, b, txt]) => w === who && t >= a && t < Math.min(b, a + txt.length / TYPE_RATE + 0.35));

// ---------------------------------------------------------------- key times

const FIRE_START = 29.0;
const FIRE_END = 31.6;
const MISSILES = [
  { launch: 29.55, dur: 0.75, target: [46, 0, -12], side: 1 },
  { launch: 29.95, dur: 0.8, target: [64, 0, -26], side: -1 },
  { launch: 30.35, dur: 0.85, target: [76, 0, -36], side: 1 },
  { launch: 30.75, dur: 0.85, target: [56, 0, -42], side: -1 },
];
const ROCK_BOOM = MISSILES[0].launch + MISSILES[0].dur;

// scratch objects for the gun and root frames
const _Y = new THREE.Vector3(0, 1, 0);
const _ONE = new THREE.Vector3(1, 1, 1);
const _rp = new THREE.Vector3();
const _rq = new THREE.Quaternion();
const _hp = new THREE.Vector3();
const _hq = new THREE.Quaternion();
const _hq2 = new THREE.Quaternion();
const _he = new THREE.Euler();
const _gl = new THREE.Matrix4();
const _gr = new THREE.Matrix4();
const _mz = new THREE.Matrix4();
const _X = new THREE.Vector3(1, 0, 0);
const _BEHIND_P = new THREE.Vector3(-3, 56, -12);
const _BEHIND_Q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-1.45, 0.2, 0.3, 'YXZ'));
const _TOSS_P = new THREE.Vector3(-12, 66, -10);
const _TOSS_Q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-1.9, 0.15, 0, 'YXZ'));
const GUN_CM = new THREE.Vector3(0, 6, 30); // rough center of mass in gun space
const GUN_TOSS = 33.2; // swing the gun up over the shoulder
const GUN_RELEASE = 33.45; // let go of it
const GUN_FLIGHT = 0.85; // it sails off the edge of the world
const GUN_LAND = GUN_RELEASE + GUN_FLIGHT;
const GUN_LAND_AT = new THREE.Vector3(-112, 0, -30);

export class Story {
  constructor(stage, camera, overlay) {
    this.st = stage;
    this.cam = camera;
    this.ov = overlay;
    this.W = 1;
    this.H = 1;
    this.reduceMotion = false;
    this._v = V();
    this._w = V();
    this._p = { x: 0, y: 0 };
    this._q = new THREE.Quaternion();
    this._m = new THREE.Matrix4();
    this.buildTracks();
  }

  resize(W, H) {
    this.W = W;
    this.H = H;
  }

  // ------------------------------------------------------------ tracks

  buildTracks() {
    const st = this.st;
    const gunGrip = (side) => (rig) => {
      st.gun.updateMatrixWorld(true);
      return side === 'R' ? V(-0.5, -9, 4).applyMatrix4(st.gun.matrixWorld) : V(-0.5, 15, 5).applyMatrix4(st.gun.matrixWorld);
    };
    const devSide = (sx) => () => {
      st.device.updateMatrixWorld(true);
      return V(sx, 18, -1).applyMatrix4(st.device.matrixWorld);
    };
    const aimYaw = (t) => {
      const lagT = Math.max(0, t - 0.3);
      const pp = this.philRootAt(lagT);
      return Math.atan2(pp[0] - STAND[0] + 2, pp[1] - STAND[1] + 1);
    };
    const firing = (t) => {
      const yaw = Math.min(2.2, Math.max(1.45, aimYaw(t)));
      const shake = t > FIRE_START && t < FIRE_END ? 1 : 0;
      return STANDING({
        root: [-12 + jit(t, 1, 0.5 * shake), -14 + jit(t, 2, 0.5 * shake), yaw],
        hipsY: 35.5,
        hips: [0.08, 0, 0],
        spine: [0.16, -0.3, jit(t, 3, 0.03 * shake)],
        head: [0.08, 0.12, 0],
        fL: [9, 6, 7],
        fR: [-8, 6, -5],
        hL: gunGrip('L'),
        hR: gunGrip('R'),
        poles: { armL: [6, -8, -6], armR: [-10, -6, -8] },
      });
    };

    this.studentTrack = new Track([
      [0, 0, (t) => S({ hR: writeHand(t), head: [0.3, 0, 0] })],
      [1.6, 0.35, (t) => S({ hR: (rig) => rig.headPoint(-7, 6, 11), head: [0.05, 0.15, 0.1], spine: [0.18, 0, 0] })],
      [2.4, 0.35, (t) => S({ spine: [0.12, 0.42, 0], head: [0.02, 0.95, 0], hL: [17, 50 + Math.sin(t * 6) * 1.5, 9], hR: [-6, 43.5, 15] })],
      [5.0, 0.4, () => S({ spine: [0.14, 0.36, 0], head: [0.06, 0.9, 0.08], hL: [10, 43.5, 12], hR: [-6, 43.5, 15] })],
      [8.0, 0.3, (t) => S({ spine: [0.14, 0.4, 0], head: [0.04, 0.95, -0.05], hL: [16, 47 + Math.abs(Math.sin(t * 5)) * 3, 12], hR: [-4, 44, 18] })],
      [10.6, 0.35, () => S({ spine: [0.2, 0.3, 0], head: [0.12, 0.85, 0], hL: [9, 43.5, 12], hR: [-6, 43.5, 14] })],
      [13.6, 0.3, (t) => S({ spine: [0.34, 0, 0], head: [0.42, 0, 0], hR: writeHand(t, 2.6, 2.2) })],
      [14.3, 0.15, (t) => S({ spine: [0.34, 0, 0], head: [0.42, 0, 0], hR: [-3 + Math.sin(t * 34) * 4.5, 43.3, 18] })],
      [14.7, 0.2, (t) => S({ spine: [0.26, 0, 0], head: [0.3, 0, 0], hL: [3 + jit(t, 4, 0.8), 49 + jit(t, 5, 0.8), 15], hR: [-4 + jit(t, 6, 0.8), 49, 15] })],
      [14.98, 0.18, () => S({ spine: [0.05, -0.25, 0], head: [0.05, -0.2, 0], hR: [-16, 68, -2], poles: { armR: [-10, -2, -10] } })],
      [15.2, 0.12, () => S({ spine: [0.2, 0.15, 0], head: [0.12, -0.3, 0], hR: [-22, 52, 14] }), E.out],
      [15.7, 0.4, () => S({ spine: [0.2, 0.3, 0], head: [0.15, 0.7, 0] })],
      [16.0, 0.4, (t) => S({ spine: [0.2, 0.32, 0], head: [0.1 + jit(t, 7, 0.01), 0.85, 0], hL: [10, 43.5, 12], hR: [-8, 43.5, 13] })],
      [19.2, 0.2, (t) => S({ spine: [0.12, 0.42, 0], head: [-0.02, 1.0, 0], hL: [12, 44, 11], hR: [-8, 43.5, 13] })],
      [20.9, 0.25, () => S({ spine: [0.75, 0, 0], head: [0.45, 0, 0], hL: [13, 43.5, 20], hR: [-13, 43.5, 20] }), E.in],
      [22.9, 1.2, (t) => S({ spine: [0.16 + jit(t, 8, 0.015), 0.28, jit(t, 9, 0.02)], head: [0.05, 0.75, 0], hL: [10, 44, 13], hR: [-8, 44, 13] }), E.inOut],
      [25.2, 0.35, (t) => STANDING({ head: [0.0, 0.7, 0], hL: [16, 40, 4], hR: [-16, 40, 4] }), E.back],
      [25.7, 0.3, () => STANDING({ root: [-11, -14, 1.5], head: [0.0, 0.0, 0] })],
      [26.0, 0.4, () => STANDING({ root: [-11, -14, 1.5], spine: [-0.08, 0, 0], hL: [7, 44, -9], hR: [-7, 44, -9], poles: { armL: [10, -4, 6], armR: [-10, -4, 6] } })],
      [26.5, 0.45, (t) => firing(t), E.back],
      [GUN_TOSS, 0.2, () => STANDING({ root: [-12, -14, 1.85], hipsY: 36.5, spine: [-0.16, -0.25, 0], head: [-0.2, 0, 0], hL: gunGrip('L'), hR: gunGrip('R'), poles: { armL: [8, -2, -6], armR: [-10, -2, -6] } })],
      [GUN_RELEASE, 0.15, () => STANDING({ root: [-12, -14, 1.85], spine: [-0.12, -0.25, 0], head: [-0.35, -0.3, 0], hL: [8, 76, -6], hR: [-12, 74, -8] }), E.out],
      [33.8, 0.5, (t) => STANDING({ root: [-12, -14, 1.6], spine: [-0.08, 0, 0], head: [-0.35 + seg(t, 34, 34.9) * 0.4, -0.75, 0] })],
      [35.0, 0.4, () => STANDING({ root: [-10, -13, 0.25], spine: [0.15, 0, 0], head: [0.3, 0.05, 0] })],
      [35.4, 0.4, () => STANDING({ root: [-10, -13, 0.25], hipsY: 35, spine: [0.55, 0, 0], head: [0.35, 0, 0], hL: devSide(13), hR: devSide(-14) })],
      [35.9, 0.3, () => STANDING({ root: [-10, -13, 0.1], spine: [0.05, 0, 0], head: [0.05, 0, 0], hL: devSide(13), hR: devSide(-14) })],
      [36.6, 0.2, () => STANDING({ root: [-10, -13, 0.05], spine: [0.05, 0, 0], head: [0.0, 0, 0], hL: (rig) => rig.headPoint(13, 15, 2), hR: (rig) => rig.headPoint(-14, 15, 2) })],
      [36.8, 0.5, () => S({ hL: [10, 43.5, 13], hR: [-6, 43.5, 16], head: [0.1, 0, 0] })],
      [37.4, 0.4, (t) => S({ spine: [0.18, 0, 0], head: [0.06 + Math.max(0, Math.sin(t * 3)) * 0.06, 0, 0.08], hL: [10, 43.5, 13], hR: [-6, 43.5, 16] })],
      [43.8, 0.2, (t) => S({ spine: [0.0, 0, 0], head: [-0.12, 0, 0], hL: [16, 60 + Math.sin(t * 9) * 2, 10], hR: [-16, 60 + Math.cos(t * 9) * 2, 10] }), E.back],
      [44.6, 0.3, (t) => S({ hR: writeHand(t, 1.7, 1.2), head: [0.32, 0, 0] })],
      [49.6, 0.3, (t) => S({ spine: [0.16, 0.3, 0], head: [0.05, 0.95, 0], hR: [-4, 43.5, 17] })],
      [51.0, 0.4, (t) => S({ hR: writeHand(t, 1.7, 1.2), head: [0.32, 0, 0] })],
    ]);

    this.studentFace = [
      [0, { brow: 'flat', eyes: 'down', mouth: 'line' }],
      [1.6, { brow: 'up', eyes: 'open', mouth: 'small' }],
      [2.4, { brow: 'worried', eyes: 'open', mouth: 'small' }],
      [5.0, { brow: 'worried', eyes: 'open', mouth: 'wavy' }],
      [8.0, { brow: 'angry', eyes: 'focus', mouth: 'line' }],
      [10.6, { brow: 'angry', eyes: 'focus', mouth: 'frown' }],
      [13.6, { brow: 'furious', eyes: 'focus', mouth: 'grit' }],
      [16.0, { brow: 'angry', eyes: 'focus', mouth: 'frown' }],
      [19.2, { brow: 'furious', eyes: 'focus', mouth: 'frown' }],
      [22.9, { brow: 'furious', eyes: 'focus', mouth: 'grit' }],
      [26.4, { brow: 'furious', eyes: 'focus', mouth: 'grin' }],
      [FIRE_START, { brow: 'furious', eyes: 'focus', mouth: 'shout' }],
      [FIRE_END, { brow: 'flat', eyes: 'open', mouth: 'talk' }],
      [33.8, { brow: 'up', eyes: 'wide', mouth: 'small' }],
      [35.4, { brow: 'flat', eyes: 'open', mouth: 'small' }],
      [37.6, { brow: 'flat', eyes: 'open', mouth: 'line' }],
      [41.2, { brow: 'worried', eyes: 'open', mouth: 'small' }],
      [43.8, { brow: 'up', eyes: 'wide', mouth: 'grin' }],
      [44.6, { brow: 'flat', eyes: 'down', mouth: 'smile+b' }],
      [46.6, { brow: 'up', eyes: 'happy', mouth: 'grin' }],
      [47.6, { brow: 'flat', eyes: 'down', mouth: 'smile' }],
      [49.6, { brow: 'angry', eyes: 'focus', mouth: 'frown' }],
      [51.0, { brow: 'flat', eyes: 'down', mouth: 'smile' }],
    ];

    const thinkerTalk = (t) => P({ head: [0.16, 0.12, 0.04 + Math.sin(t * 2.2) * 0.03] });
    this.philTrack = new Track([
      [0, 0, (t) => P({ spine: [0.42 + Math.sin(t * 1.8) * 0.012, -0.1, 0.06] })],
      [27.7, 0.25, () => P({ spine: [0.1, -0.2, 0], head: [-0.15, -0.9, 0], hR: [-14, 46, 10], hL: [12, 40, 12], poles: {} }), E.out],
      [28.3, 0.3, (t) => ({ ...runPose(t, [ROCK_SEAT[0], ROCK_SEAT[1], 1.9], 22 - seg(t, 28.3, 28.95) * 8, 5.5), head: [-0.3, -1.0, 0] }), E.out],
      [28.95, 0.15, (t) => {
        const u = E.in(seg(t, 28.95, 30.4));
        const [x, z] = philRunPos(u);
        const [x2, z2] = philRunPos(u + 0.02);
        return runPose(t, [x, z, Math.atan2(x2 - x, z2 - z)], Math.max(0, 14 - seg(t, 28.95, 29.15) * 14), 4.2);
      }],
      [49.4, 0, (t) => {
        const u = E.out(seg(t, 49.4, 50.2));
        return {
          ...P({}),
          root: [lerp(102, 78, u), lerp(-40, -22, u), -0.4],
          hipsY: 37.5,
          hips: [0, 0, 0],
          spine: [0.12, 0.15, 0.08],
          head: [0.1, 0.25, 0.15],
          fL: [5, 6 + Math.max(0, Math.sin(t * 9)) * 5 * (1 - u), 3],
          fR: [-5, 6 + Math.max(0, -Math.sin(t * 9)) * 5 * (1 - u), 0],
          hL: [10, 34, 8],
          hR: [-17 + Math.sin(t * 7) * 3, 78, 8],
          poles: { armR: [-10, -2, -2] },
        };
      }],
      [51.2, 0.15, (t) => {
        const u = E.in(seg(t, 51.25, 52.3));
        return runPose(t, [lerp(78, 120, u), lerp(-22, -62, u), 2.3], 0, 4.4);
      }],
    ]);
    this.philFace = [
      [0, { brow: 'calm', eyes: 'closed', mouth: 'closed' }],
      [27.7, { brow: 'raised', eyes: 'wide', mouth: 'closed' }],
      [28.3, { brow: 'raised', eyes: 'wide', mouth: 'open' }],
      [49.4, { brow: 'raised', eyes: 'glance', mouth: 'smile' }],
      [51.0, { brow: 'raised', eyes: 'wide', mouth: 'open' }],
    ];
    this.thinkerTalk = thinkerTalk;
  }

  philRootAt(t) {
    if (t < 28.95) return [ROCK_SEAT[0], ROCK_SEAT[1]];
    return philRunPos(E.in(seg(t, 28.95, 30.4)));
  }

  // ------------------------------------------------------------ per-frame update

  update(t) {
    const st = this.st;
    const fx = st.fx;
    const tc = Math.floor(t * 15) / 15; // characters animate on twos
    const shake = { x: 0, y: 0 };

    // loop transitions: dithered dissolve in and out
    shared.uDissolve.value = t < 0.6 ? 1 - seg(t, 0, 0.6) : seg(t, DURATION - 1.0, DURATION - 0.2);

    // ---------------- props state
    // gun placement (must happen before hands are solved)
    this.updateGun(t);
    this.updateDevice(t);

    // chair slides back when the student jumps up, then is pulled back in
    const chairBack = seg(t, 25.2, 25.55) * (1 - seg(t, 36.75, 37.2));
    st.chair.position.set(LAYOUT.chair.x, 0, LAYOUT.chair.z - 12 * E.out(chairBack));
    st.chair.rotation.y = Math.sin(seg(t, 25.2, 26.1) * Math.PI * 3) * 0.12 * (1 - seg(t, 25.2, 26.1));

    // ---------------- student
    const s = st.student;
    applyActor(s, this.studentTrack, tc);
    let face = { ...stepAt(this.studentFace, tc) };
    if (talking('s', t) && Math.floor(t * 8) % 2 === 0) face.mouth = face.mouth.endsWith('+b') ? 'talk+b' : 'talk';
    if ((face.eyes === 'open' || face.eyes === 'focus') && tc % 3.7 < 0.12 && !(tc > 22.9 && tc < 32)) face.eyes = 'blink';
    s.setExpr(face);
    // face turns red from the chin up as frustration builds
    const flush = Math.min(1, seg(t, 15.8, 20.5) * 0.75 + seg(t, 22.9, 24.4) * 0.6) * (1 - seg(t, FIRE_END, 37.4));
    s.headMat.userData.u.uFlush.value = flush > 0.02 ? 1 : 0;
    s.headMat.userData.u.uFlushLevel.value = lerp(-2, 24, flush);

    // pencil in hand
    st.pencil.visible = t < 24.6 || t > 37.4;

    // ---------------- philosopher
    const p = st.phil;
    const visible = t < 30.45 || (t > 49.4 && t < 52.4);
    p.rig.root.visible = visible;
    if (visible) {
      if (t < 27.7 && talking('p', t)) {
        const tt = this.thinkerTalk(tc);
        p.rig.setBody(tt);
        applyActor(p, this.philTrack, tc);
        p.rig.neck.rotation.z = tt.head[2];
      } else applyActor(p, this.philTrack, tc);
      const pf = { ...stepAt(this.philFace, tc) };
      if (talking('p', t) && Math.floor(t * 8) % 2 === 0 && pf.mouth === 'closed') pf.mouth = 'talk';
      p.setExpr(pf);
    }
    st.flag.visible = t > 49.4 && t < 51.25;

    // ---------------- papers
    const u1 = st.paper1Mat.userData.u;
    let rev = lerp(st.p1Start, st.p1Lines, seg(t, 0, 1.6));
    if (t >= 13.6) rev = lerp(99, st.p1Messy, seg(t, 13.6, 14.3));
    if (t >= 14.3) rev = lerp(st.p1Messy, 99, seg(t, 14.3, 14.7));
    u1.uReveal.value = rev;
    st.paper1.visible = t < 14.8;
    st.paper2Mat.userData.u.uReveal.value = lerp(0, st.p2Keys, seg(t, 44.6, 48.6));
    // desk props jump when the student's head hits the desk
    const bonk = Math.sin(Math.PI * seg(t, 21.15, 21.45)) * 2.5;
    st.deskStuff.position.y = bonk;
    st.paper2.position.y = LAYOUT.paper.y - 0.02 + bonk * 0.5;
    st.paper1.position.y = LAYOUT.paper.y + bonk * 0.5;

    // ---------------- rock
    st.rock.visible = t < ROCK_BOOM;
    st.rubble.visible = st.scorch.visible = t >= ROCK_BOOM;

    // ---------------- effects
    this.effects(t, shake);

    if (this.reduceMotion) {
      shake.x = 0;
      shake.y = 0;
    }
    this.lastShake = shake;
    return shake;
  }

  updateGun(t) {
    const st = this.st;
    const gun = st.gun;
    gun.visible = t >= 26.5 && t < GUN_LAND;
    if (!gun.visible) return;
    gun.scale.setScalar(t < 27.0 ? 0.7 + 0.3 * E.back(seg(t, 26.5, 26.8)) : 1);
    if (t < GUN_RELEASE) {
      this.gunMatrixAt(t, this._m).decompose(gun.position, gun.quaternion, this._v);
    } else {
      // tossed over the shoulder: it tumbles end over end and sails off the island
      const toss = this.gunToss || (this.gunToss = (() => {
        const m = this.gunMatrixAt(GUN_RELEASE - 1e-4);
        const p = V(), q = new THREE.Quaternion();
        m.decompose(p, q, V());
        const cm = GUN_CM.clone().applyMatrix4(m);
        const T = GUN_FLIGHT, g = 260;
        const vel = V((GUN_LAND_AT.x - cm.x) / T, (GUN_LAND_AT.y + 8 - cm.y + 0.5 * g * T * T) / T, (GUN_LAND_AT.z - cm.z) / T);
        return { q, cm, vel, g };
      })());
      const tau = t - GUN_RELEASE;
      gun.quaternion.copy(toss.q).multiply(this._q.setFromAxisAngle(_X, -tau * 9));
      const c = V(toss.cm.x + toss.vel.x * tau, toss.cm.y + toss.vel.y * tau - 0.5 * toss.g * tau * tau, toss.cm.z + toss.vel.z * tau);
      gun.position.copy(c).sub(GUN_CM.clone().applyQuaternion(gun.quaternion));
    }
    // attachments
    const pods = E.back(seg(t, 27.25, 27.6));
    st.podL.position.y = 13 - 11 * (1 - pods);
    st.podR.position.y = 13 - 11 * (1 - pods);
    st.podL.rotation.z = (1 - pods) * -0.8;
    st.podR.rotation.z = (1 - pods) * 0.8;
    const kl = E.back(seg(t, 27.55, 27.8));
    const kr = E.back(seg(t, 27.75, 28.0));
    st.knifeL.rotation.y = (1 - kl) * 2.9 + 0.12;
    st.knifeR.rotation.y = -(1 - kr) * 2.9 - 0.12;
    const spin = t < 28.6 ? 0 : t < FIRE_END ? (t - 28.6) * (t - 28.6) * 9 + (t - 28.6) * 4 : 0;
    st.barrelPivot.rotation.z = spin;
    st.flash.visible = t > FIRE_START && t < FIRE_END && Math.floor(t * 30) % 2 === 0;
  }

  // The student's root frame at time t, taken from the pose track alone so
  // that effects can ask about other moments without disturbing the rig.
  studentRootAt(t, out = new THREE.Matrix4()) {
    const [a, b, u] = this.studentTrack.at(Math.floor(t * 15) / 15);
    const body = b ? blendBody(a, b, u) : a;
    _rq.setFromAxisAngle(_Y, body.root[2]);
    return out.compose(_rp.set(body.root[0], body.rootY || 0, body.root[1]), _rq, _ONE);
  }

  // Where the gun is at time t while the student holds it: swung out from
  // behind the back, then held at the hip with recoil, then lowered.
  gunMatrixAt(t, out = new THREE.Matrix4()) {
    _hp.set(-16, 42, 4);
    if (t > FIRE_START && t < FIRE_END) _hp.z -= (Math.floor(t * 30) % 2) * 1.6;
    _he.set(0.42 * E.inOut(seg(t, FIRE_END + 0.1, FIRE_END + 0.8)) + 0.04, -0.02, 0, 'YXZ');
    _hq.setFromEuler(_he);
    if (t < 27.0) {
      const w = E.back(seg(t, 26.5, 27.0));
      _hp.lerpVectors(_BEHIND_P, _hp, w);
      _hq.copy(_hq2.slerpQuaternions(_BEHIND_Q, _hq, clamp01(w)));
    }
    if (t > GUN_TOSS) {
      const w = E.inOut(seg(t, GUN_TOSS, GUN_RELEASE));
      _hp.lerpVectors(_hp, _TOSS_P, w);
      _hq.copy(_hq2.slerpQuaternions(_hq, _TOSS_Q, w));
    }
    _gl.compose(_hp, _hq, _ONE);
    return out.multiplyMatrices(this.studentRootAt(t, _gr), _gl);
  }

  updateDevice(t) {
    const st = this.st;
    const d = st.device;
    const s = st.student.rig;
    d.visible = t >= 33.6;
    const glow = t >= 36.6 ? 1 : 0;
    st.deviceMat.userData.u.uGlow.value = glow || (t > 33.6 && t < 34.95 && Math.floor(t * 6) % 2 === 0 ? 1 : 0);
    if (!d.visible) return;
    const rest = new THREE.Object3D();
    rest.position.set(LAYOUT.deviceDesk.x, 26, LAYOUT.deviceDesk.z);
    rest.rotation.set(0, 0.55, 0);
    rest.updateMatrix();
    if (t < 35.9) {
      const f = E.out(seg(t, 33.6, 34.9));
      const bounce = Math.sin(Math.PI * seg(t, 34.9, 35.15)) * 3;
      d.position.set(rest.position.x, lerp(150, 26, f) + bounce, rest.position.z);
      d.rotation.set(Math.sin(t * 5) * 0.15 * (1 - f), 0.55 + (1 - f) * 2.5, 0);
      return;
    }
    // lifted from the desk, raised above the head, then lowered on
    const [a, b, u] = this.studentTrack.at(Math.floor(t * 15) / 15);
    s.setBody(b ? blendBody(a, b, u) : a);
    s.neck.updateWorldMatrix(true, false);
    const headM = s.neck.matrixWorld;
    // held up just clear of the hair, then lowered into place
    const above = new THREE.Matrix4().multiplyMatrices(headM, new THREE.Matrix4().makeTranslation(0, 9, 1));
    const p0 = new THREE.Vector3(), q0 = new THREE.Quaternion(), sc = new THREE.Vector3();
    const p1 = new THREE.Vector3(), q1 = new THREE.Quaternion();
    const p2 = new THREE.Vector3(), q2 = new THREE.Quaternion();
    rest.matrix.decompose(p0, q0, sc);
    above.decompose(p1, q1, sc);
    headM.decompose(p2, q2, sc);
    if (t < 36.3) {
      const f = E.inOut(seg(t, 35.9, 36.3));
      d.position.lerpVectors(p0, p1, f);
      d.quaternion.slerpQuaternions(q0, q1, f);
    } else {
      const f = E.inOut(seg(t, 36.3, 36.6));
      d.position.lerpVectors(p1, p2, f);
      d.quaternion.slerpQuaternions(q1, q2, f);
    }
  }

  // ------------------------------------------------------------ effects

  effects(t, shake) {
    const st = this.st;
    const fx = st.fx;
    const v = this._v;
    const s = st.student.rig;
    const p = st.phil.rig;

    // eraser crumbs
    if (t > 14.3 && t < 16) {
      for (let i = 0; i < 8; i++) {
        const t0 = 14.3 + i * 0.05;
        if (t < t0) continue;
        const p0 = V(LAYOUT.paper.x + (hash3(i, 1, 2) - 0.5) * 8, 41, LAYOUT.paper.z + (hash3(i, 2, 3) - 0.5) * 6);
        const v0 = V((hash3(i, 3, 4) - 0.5) * 40, 25 + hash3(i, 4, 5) * 20, (hash3(i, 5, 6) - 0.5) * 30);
        ballistic(p0, v0, t - t0, v, { floorY: 40.5, bounces: 1 });
        fx.chunk(v, 0.45, 0xf2a0b0, i);
      }
    }

    // crumpled paper ball: in the hands, then thrown at the bin (and missing)
    const ball = st.paperBall;
    ball.visible = t > 14.75;
    if (ball.visible) {
      const throwT = 15.27;
      if (t < throwT) {
        s.elR.updateWorldMatrix(true, false);
        V(0, -16, 2).applyMatrix4(s.elR.matrixWorld);
        ball.position.copy(V(0, -16, 3).applyMatrix4(s.elR.matrixWorld));
        ball.scale.setScalar(t < 15.0 ? 0.6 + 0.4 * seg(t, 14.75, 15.0) : 1);
      } else {
        const p0 = this.ballStart || (this.ballStart = V(-34, 58, -2));
        const v0 = V(-26, 52, 36);
        ballistic(p0, v0, t - throwT, v, { floorY: 2.4, rest: 0.42, fric: 0.6, bounces: 3 });
        ball.position.copy(v);
        ball.rotation.set(t * 9, t * 7, 0);
        ball.scale.setScalar(1);
      }
    }

    // steam from the ears
    if (t > 22.95 && t < 26.2) {
      for (let i = 0; i < 16; i++) {
        const t0 = 22.95 + i * 0.2;
        const age = t - t0;
        if (age < 0 || age > 0.9) continue;
        const side = i % 2 ? 1 : -1;
        const base = s.headPoint(side * 12, 12, 0, V());
        base.y += age * 26;
        base.x += side * age * 6;
        fx.puff(base, 1.6 + age * 3.5, 1 - seg(age, 0.4, 0.9), 0xf4f4f4);
      }
    }

    // pencil snaps
    const snapT = 24.6;
    for (let i = 0; i < 2; i++) {
      const m = st.pencilBits[i];
      m.visible = t >= snapT;
      if (!m.visible) continue;
      const p0 = this.snapPos || (this.snapPos = V(-14, 46, 12));
      const v0 = V(i ? 18 : -14, 48 + i * 10, i ? 6 : -4);
      ballistic(p0, v0, t - snapT, v, { floorY: 40.6, rest: 0.3, bounces: 2 });
      m.position.copy(v);
      const settle = Math.min(t - snapT, 0.9);
      m.rotation.set(Math.PI / 2 + settle * 9 * (i ? 1 : -1), settle * 4, Math.PI / 2);
      if (t - snapT > 0.9) m.rotation.set(Math.PI / 2, i ? 0.6 : -0.9, Math.PI / 2);
    }

    // dust when the student jumps up and when the philosopher leaps
    const dustBurst = (t0, center, n, spread, color = 0xd9c4a2) => {
      const age = t - t0;
      if (age < 0 || age > 0.8) return;
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2 + t0;
        const r = spread * (0.4 + age * 1.6);
        fx.puff(V(center.x + Math.cos(a) * r, center.y + 1.5 + age * 6, center.z + Math.sin(a) * r), 2.2 + age * 3, 1 - seg(age, 0.3, 0.8), color);
      }
    };
    dustBurst(25.3, V(-10, 0, -16), 6, 10);
    dustBurst(28.32, V(ROCK_SEAT[0], 22, ROCK_SEAT[1]), 6, 9);

    // philosopher's running feet kick up dust
    if (t > 28.95 && t < 30.6) {
      for (let i = 0; i < 18; i++) {
        const t0 = 28.95 + i * 0.08;
        const age = t - t0;
        if (age < 0 || age > 0.55) continue;
        const [x, z] = this.philRootAt(t0);
        fx.puff(V(x - 3, 2 + age * 6, z + 3), 2 + age * 5, 1 - seg(age, 0.2, 0.55), 0xd9c4a2);
      }
    }

    // gunfire
    if (st.gun.visible && t > FIRE_START && t < FIRE_END + 0.6) {
      const muzzleAt = (tt) => {
        const m = this.gunMatrixAt(tt, _mz);
        return {
          pos: V(-0.5, 6, 94).applyMatrix4(m),
          dir: V(0, 0, 1).transformDirection(m),
          side: V(-1, 0.6, -0.2).transformDirection(m),
          port: V(-7, 8, 17).applyMatrix4(m),
        };
      };
      // bullets
      for (let i = 0; i < 80; i++) {
        const t0 = FIRE_START + i / 30;
        if (t0 >= FIRE_END) break;
        const age = t - t0;
        if (age < 0 || age > 0.4) continue;
        const mz = muzzleAt(t0);
        const d = mz.dir.clone();
        d.x += (hash3(i, 9, 1) - 0.5) * 0.12;
        d.y += (hash3(i, 9, 2) - 0.5) * 0.05 - 0.02;
        d.z += (hash3(i, 9, 3) - 0.5) * 0.12;
        d.normalize();
        fx.bullet(mz.pos.clone().addScaledVector(d, age * 430 + 6), d);
      }
      // shell casings eject and stay where they land
      for (let i = 0; i < 40; i++) {
        const t0 = FIRE_START + i / 15;
        if (t0 >= FIRE_END) break;
        const age = t - t0;
        if (age < 0) continue;
        const mz = this.casingFrom?.[i] || ((this.casingFrom ||= [])[i] = muzzleAt(t0));
        const v0 = mz.side.clone().multiplyScalar(38 + hash3(i, 3, 3) * 18);
        v0.y = 40 + hash3(i, 4, 4) * 25;
        ballistic(mz.port, v0, age, v, { floorY: 0.6, rest: 0.35, fric: 0.5, bounces: 2 });
        fx.casing(v, age < 0.7 ? age * 22 + i : i * 1.3);
      }
      // muzzle smoke
      for (let i = 0; i < 20; i++) {
        const t0 = FIRE_START + i * 0.13;
        if (t0 >= FIRE_END) break;
        const age = t - t0;
        if (age < 0 || age > 0.6) continue;
        const mz = muzzleAt(t0);
        const pos = mz.pos.clone().addScaledVector(mz.dir, 4 + age * 10);
        pos.y += age * 12;
        fx.puff(pos, 2 + age * 6, 1 - seg(age, 0.25, 0.6), 0xd8d8d8);
      }
    }
    // spent casings stay on the floor
    if (t >= FIRE_END + 0.6 && this.casingFrom) {
      for (let i = 0; i < this.casingFrom.length; i++) {
        const mz = this.casingFrom[i];
        if (!mz) continue;
        const v0 = mz.side.clone().multiplyScalar(38 + hash3(i, 3, 3) * 18);
        v0.y = 40 + hash3(i, 4, 4) * 25;
        ballistic(mz.port, v0, 5, v, { floorY: 0.6, rest: 0.35, fric: 0.5, bounces: 2 });
        fx.casing(v, i * 1.3);
      }
    }

    // missiles
    MISSILES.forEach((ms, i) => {
      const g = st.missiles[i];
      const age = t - ms.launch;
      g.visible = age >= 0 && age < ms.dur;
      const path = (u) => this.missilePath(ms, i, u);
      if (g.visible) {
        const u = age / ms.dur;
        const pos = path(u);
        const ahead = path(Math.min(1, u + 0.02));
        g.position.copy(pos);
        g.lookAt(ahead);
      }
      // smoke trail
      if (age > 0 && age < ms.dur + 0.9) {
        for (let k = 0; k < 20; k++) {
          const tk = k * 0.04;
          if (tk > Math.min(age, ms.dur)) break;
          const pa = age - tk;
          if (pa > 0.9) continue;
          const pos = path(tk / ms.dur);
          pos.y += pa * 5;
          fx.puff(pos, 1.6 + pa * 4.5, 1 - seg(pa, 0.35, 0.9), 0xe6e6e6);
        }
      }
      // explosion
      const ea = age - ms.dur;
      if (ea >= 0 && ea < 1.6) this.explosion(V(...ms.target), ea, i, shake, i === 0);
    });

    // head bonk
    if (t > 21.15 && t < 21.25) shake.y += 1;

    // philosopher's dust when fleeing again at the end
    if (t > 51.25 && t < 52.4) {
      for (let i = 0; i < 12; i++) {
        const t0 = 51.25 + i * 0.09;
        const age = t - t0;
        if (age < 0 || age > 0.5) continue;
        const u = E.in(seg(t0, 51.25, 52.3));
        fx.puff(V(lerp(78, 120, u) - 3, 2 + age * 6, lerp(-22, -62, u) + 3), 2 + age * 5, 1 - seg(age, 0.2, 0.5), 0xd9c4a2);
      }
    }

    fx.end();
  }

  missilePath(ms, i, u) {
    const st = this.st;
    if (!this.missileStart) this.missileStart = [];
    if (!this.missileStart[i]) {
      const m = this.gunMatrixAt(ms.launch);
      this.missileStart[i] = {
        p0: V(ms.side > 0 ? 10 : -11, 24, 32).applyMatrix4(m),
        up: V(0, 1, 0),
        fwd: V(0, 0, 1).transformDirection(m),
      };
    }
    const { p0, fwd } = this.missileStart[i];
    const tgt = V(...ms.target);
    const p1 = p0.clone().addScaledVector(fwd, 30).add(V(0, 70, 0));
    const p2 = tgt.clone().add(V(0, 90, 0));
    const a = 1 - u;
    return V(
      a * a * a * p0.x + 3 * a * a * u * p1.x + 3 * a * u * u * p2.x + u * u * u * tgt.x,
      a * a * a * p0.y + 3 * a * a * u * p1.y + 3 * a * u * u * p2.y + u * u * u * tgt.y,
      a * a * a * p0.z + 3 * a * a * u * p1.z + 3 * a * u * u * p2.z + u * u * u * tgt.z,
    );
  }

  explosion(c, age, seed, shake, big) {
    const fx = this.st.fx;
    if (age < 0.25) {
      const amp = (big ? 3 : 2) * (1 - age / 0.25);
      shake.x += Math.round(jit(age * 60, seed, amp));
      shake.y += Math.round(jit(age * 60, seed + 9, amp));
    }
    // fireball
    const n = big ? 9 : 7;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + seed;
      const r = (big ? 9 : 7) * E.out(clamp01(age / 0.35)) * (0.5 + hash3(i, seed, 1) * 0.6);
      const pos = V(c.x + Math.cos(a) * r, c.y + 5 + hash3(i, seed, 2) * 10 + age * 18, c.z + Math.sin(a) * r);
      if (age < 0.5) {
        const col = age < 0.07 ? 0xffffff : age < 0.18 ? 0xffe066 : age < 0.32 ? 0xff9a3c : 0xe0512f;
        fx.puff(pos, (big ? 7 : 5.5) * (0.6 + E.out(clamp01(age / 0.3)) * 0.8), 1 - seg(age, 0.32, 0.5), col, true);
      }
      if (age > 0.25) {
        const sa = age - 0.25;
        const sp = pos.clone();
        sp.y += sa * 14;
        fx.puff(sp, (big ? 7 : 5.5) * (0.9 + sa * 0.7), 1 - seg(sa, 0.5, 1.3), i % 2 ? 0x77716e : 0x958f8a);
      }
    }
    if (age < 0.06) fx.puff(V(c.x, c.y + 8, c.z), big ? 16 : 12, 1, 0xffffff, true);
    // rock debris
    if (big) {
      for (let i = 0; i < 16; i++) {
        const a = (i / 16) * Math.PI * 2;
        const sp = 40 + hash3(i, 2, 2) * 50;
        const p0 = V(c.x + Math.cos(a) * 4, 10 + hash3(i, 3, 1) * 8, c.z + Math.sin(a) * 4);
        const v0 = V(Math.cos(a) * sp, 60 + hash3(i, 4, 1) * 70, Math.sin(a) * sp);
        const out = V();
        const r = ballistic(p0, v0, age, out, { floorY: 1, rest: 0.3, fric: 0.5, bounces: 1 });
        const col = hash3(i, 5, 1) > 0.7 ? 0x6e8f4c : hash3(i, 6, 1) > 0.5 ? 0x7a7d84 : 0x8f9298;
        fx.chunk(out, 1.2 + hash3(i, 7, 1) * 1.4, col, r.settled ? i : age * 10 + i);
      }
    }
  }

  // ------------------------------------------------------------ overlay

  drawOverlay(t, shake) {
    const ov = this.ov;
    ov.clear();
    if (shared.uDissolve.value > 0.35) return;
    const st = this.st;
    const s = st.student.rig;
    const p = st.phil.rig;
    const W = this.W, H = this.H;
    const sc = ov.s;
    const proj = (vec) => {
      const o = project(this.cam, W, H, vec, { x: 0, y: 0 });
      return o;
    };

    // speech
    for (const [who, a, b, text] of LINES) {
      if (t < a || t >= b) continue;
      let anchor;
      if (who === 's') anchor = s.headPoint(0, 30, 2, V());
      else if (who === 'p') anchor = p.headPoint(0, 27, 0, V());
      else anchor = s.headPoint(0, 27, 12, V());
      const pt = proj(anchor);
      const style = who === 's' ? 'student' : who === 'p' ? 'phil' : 'tutor';
      const lean = who === 's' ? -0.18 : who === 'p' ? 0.2 : -0.3;
      ov.bubble({ text, ax: pt.x, ay: pt.y, style, shown: Math.floor((t - a) * TYPE_RATE), lean });
    }

    const at = (rig, x, y, z) => proj(rig.headPoint(x, y, z, V()));
    // question mark
    if (t > 1.6 && t < 2.4) {
      const q = at(s, 12, 30, 0);
      ov.sprite('question', q.x, q.y - Math.round(seg(t, 1.6, 1.8) * 3) * sc);
    }
    // sweat drop
    if (t > 11.8 && t < 13.6) {
      const q = at(s, -11, 21, 7);
      ov.sprite('sweat', q.x, q.y + Math.round(seg(t, 11.8, 13.6) * 5) * sc);
    }
    // anger veins
    if ((t > 19.2 && t < 20.9) || (t > 22.9 && t < 26.3)) {
      const q = at(s, 9, 25, 4);
      const big = Math.floor(t * 6) % 2 === 0;
      ov.sprite('vein', q.x, q.y, big ? sc : sc);
      if (big) ov.sprite('vein', q.x, q.y, sc);
    }
    // bonk
    if (t > 21.15 && t < 21.7) {
      const q = at(s, 0, 24, 10);
      ov.sprite('burst', q.x + 8 * sc, q.y - 4 * sc);
      ov.sfx('BONK!', q.x + 22 * sc, q.y - 14 * sc, '#ffd23f');
    }
    // gun sound effects
    if (t > 27.3 && t < 27.75) {
      const g = proj(V(5, 30, 10).applyMatrix4(st.gun.matrixWorld));
      ov.sfx('CHK!', g.x, g.y - 6 * sc, '#ffffff');
    }
    if (t > 27.6 && t < 28.2) {
      const g = proj(V(8, 6, 70).applyMatrix4(st.gun.matrixWorld));
      ov.sfx('SHING!', g.x, g.y + 10 * sc, '#e8f4ff');
    }
    if (t > FIRE_START + 0.1 && t < FIRE_END) {
      const g = proj(V(0, 30, 70).applyMatrix4(st.gun.matrixWorld));
      const wob = Math.floor(t * 15) % 2;
      ov.sfx('BRRRRRT!', g.x + wob * sc, g.y - 8 * sc - wob * sc, '#ffd23f');
    }
    if (t > ROCK_BOOM && t < ROCK_BOOM + 0.7) {
      const g = proj(V(LAYOUT.rock.x, 44, LAYOUT.rock.z));
      ov.sfx('KA-BOOM!', g.x, g.y - Math.round(seg(t, ROCK_BOOM, ROCK_BOOM + 0.7) * 6) * sc, '#ff9a3c');
    }
    if (t > GUN_LAND && t < GUN_LAND + 0.7) {
      const g = proj(V(GUN_LAND_AT.x, 6, GUN_LAND_AT.z));
      ov.sfx('CLANK.', g.x, g.y - Math.round(seg(t, GUN_LAND, GUN_LAND + 0.7) * 4) * sc, '#dfe3ea');
    }
    // philosopher notices
    if (t > 27.7 && t < 28.45) {
      const q = at(p, 2, 33, 0);
      ov.sprite('bang', q.x, q.y - Math.round(E.back(seg(t, 27.7, 27.9)) * 4) * sc, sc * 2);
    }
    // wearable descending: sparkles
    if (t > 33.6 && t < 35.3) {
      const c = proj(V(st.device.position.x, st.device.position.y + 20, st.device.position.z));
      for (let i = 0; i < 5; i++) {
        const a = t * 3 + i * 1.256;
        const r = 16 + Math.sin(t * 4 + i) * 3;
        if (Math.floor(t * 10 + i) % 3 === 0) continue;
        ov.sprite(i % 2 ? 'sparkle' : 'sparkleS', c.x + Math.cos(a) * r * sc, c.y + Math.sin(a) * r * 0.7 * sc);
      }
    }
    // the wearable switches on
    if (t > 36.6 && t < 37.5) {
      const c = at(s, 0, 20, 10);
      const u = seg(t, 36.6, 37.5);
      ov.ring(c.x, c.y, (8 + u * 30) * sc, '#52f7e6', 1 - u);
      ov.ring(c.x, c.y, (4 + u * 18) * sc, '#b8fff7', 1 - u);
      if (t < 37.1) ov.sfx('PING!', c.x + 26 * sc, c.y - 18 * sc, '#52f7e6');
    }
    // light bulb moment
    if (t > 43.9 && t < 46.3) {
      const q = at(s, 20, 30, 0);
      const by = q.y - 2 * sc;
      ov.sprite('bulb', q.x, by);
      if (Math.floor(t * 6) % 2 === 0) {
        for (const [dx, dy] of [[-11, -4], [11, -4], [-8, -11], [8, -11], [0, -14]]) ov.rect(q.x + dx * sc, by + dy * sc, sc, sc, '#ffd84d');
      }
    }
    // check marks appear on the new sheet
    const checks = [[45.8, -4, 6], [46.6, -4, 3], [47.4, -4, 0], [48.2, -4, -3]];
    for (const [t0, x, z] of checks) {
      if (t < t0) continue;
      const q = proj(V(LAYOUT.paper.x + x + 9, LAYOUT.paper.y + 1, LAYOUT.paper.z + z));
      ov.sprite('check', q.x, q.y - Math.round((1 - seg(t, t0, t0 + 0.15)) * 3) * sc);
    }
    if (t > 46.6 && t < 47.8) {
      const q = at(s, 0, 16, 6);
      for (let i = 0; i < 4; i++) {
        const a = i * 1.57 + t * 2;
        if (Math.floor(t * 8 + i) % 2) continue;
        ov.sprite('sparkle', q.x + Math.cos(a) * 22 * sc, q.y + Math.sin(a) * 16 * sc);
      }
    }
  }
}
