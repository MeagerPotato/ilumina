// The whole 53-second skit as a pure function of time: poses, props,
// effects and dialogue are all derived from the clock, so the loop can be
// scrubbed to any moment.
import * as THREE from 'three';
import { project, shared } from './engine.js';
import { ballistic } from './fx.js';
import { LAYOUT } from './scene.js';
import { GUN } from './models.js';
import { hash3 } from './voxel.js';

export const DURATION = 53.6;

// ---------------------------------------------------------------- helpers

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
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
const wrap = (a) => {
  while (a > Math.PI) a -= Math.PI * 2;
  while (a < -Math.PI) a += Math.PI * 2;
  return a;
};
const angLerp = (a, b, u) => a + wrap(b - a) * u;
const jit = (t, i, amp) => (hash3(Math.floor(t * 15), i, 7) - 0.5) * 2 * amp;
// a single bump from 0 up to 1 and back over [a, a + d)
const pulse = (t, a, d) => (t >= a && t < a + d ? Math.sin((Math.PI * (t - a)) / d) : 0);

// Smooth curve through keys [s, v1, v2, ...] (Catmull-Rom tangents).
function spline(keys, s) {
  const n = keys.length;
  let i = 0;
  while (i < n - 2 && s > keys[i + 1][0]) i++;
  const k1 = keys[i], k2 = keys[i + 1];
  const k0 = keys[i > 0 ? i - 1 : i], k3 = keys[i + 2 < n ? i + 2 : i + 1];
  const h = k2[0] - k1[0];
  const u = clamp01((s - k1[0]) / h);
  const u2 = u * u, u3 = u2 * u;
  const h00 = 2 * u3 - 3 * u2 + 1, h10 = u3 - 2 * u2 + u, h01 = -2 * u3 + 3 * u2, h11 = u3 - u2;
  const out = [];
  for (let j = 1; j < k1.length; j++) {
    const m1 = ((k2[j] - k0[j]) / (k2[0] - k0[0])) * h;
    const m2 = ((k3[j] - k1[j]) / (k3[0] - k1[0])) * h;
    out.push(h00 * k1[j] + h10 * m1 + h01 * k2[j] + h11 * m2);
  }
  return out;
}

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

// ---------------------------------------------------------------- gaits

// Feet for a gait in which each foot stays planted for `duty` of the cycle
// while the body passes over it at speed v, so nothing slides. Each foot is
// [y, z] in the root frame; the right foot touches down at phase 0.
const SPRINT_SWING = (A) => [[0, 6, -A], [0.3, 24, -A - 10], [0.68, 19, A + 10], [1, 6, A]];
const WALK_SWING = (A) => [[0, 6, -A], [0.5, 10, 0], [1, 6, A]];
function gait(t, t0, v, T, duty, swing) {
  const ph = ((((t - t0) / T) % 1) + 1) % 1;
  const A = (v * T * duty) / 2;
  const keys = swing(A);
  const foot = (p) => (p < duty ? [6, A - (2 * A * p) / duty] : spline(keys, (p - duty) / (1 - duty)));
  return { ph, R: foot(ph), L: foot((ph + 0.5) % 1) };
}

const RUN_T = 0.4; // one stride: six drawings on twos
// Running flat out: low and leaning, knees driving, arms pumping against the legs.
function sprint(t, t0, v, look = 0) {
  const g = gait(t, t0, v, RUN_T, 0.38, SPRINT_SWING);
  const sw = Math.cos(2 * Math.PI * g.ph); // +1 while the right leg reaches forward
  const step = (2 * g.ph) % 1;
  const aL = 0.5 + 0.5 * sw, aR = 0.5 - 0.5 * sw; // arms swing opposite the legs
  return {
    hipsY: 34 - 2.4 * Math.cos(2 * Math.PI * (step - 0.38)),
    hips: [0.22, 0.12 * sw, 0],
    spine: [0.36, -0.28 * sw, 0],
    head: [-0.44, 0.14 * sw + look, 0],
    fL: [4.5, g.L[0], g.L[1]],
    fR: [-4.5, g.R[0], g.R[1]],
    hL: [13 - 4 * aL, 36 + 18 * aL, -9 + 33 * aL],
    hR: [-13 + 4 * aR, 36 + 18 * aR, -9 + 33 * aR],
    poles: { armL: [10, -6, -12], armR: [-10, -6, -12] },
  };
}

// ---------------------------------------------------------------- dialogue

const LINES = [
  ['s', 2.4, 5.0, 'UM... HOW DO I DO NUMBER 4?'],
  ['p', 5.2, 7.9, 'WHAT IS A NUMBER, TRULY?'],
  ['s', 8.0, 10.6, "I'M STUCK ON THE CHAIN RULE."],
  ['p', 10.8, 13.6, 'ALL OF US ARE BOUND BY CHAINS.'],
  ['p', 16.0, 19.0, 'THE ANSWER WAS INSIDE YOU ALL ALONG.'],
  ['s', 19.2, 20.8, 'IT WAS NOT.'],
  ['p', 21.6, 24.8, 'THE UNEXAMINED HOMEWORK IS NOT WORTH DOING.'],
  // lines over the gun sequence are only dismissed when skipped, so a click
  // never jumps over the action
  ['s', 27.12, 27.85, 'PONDER THIS.', 'hold'],
  ['p', 27.75, 29.0, 'I THINK, THEREFORE I RUN!', 'hold'],
  ['t', 37.6, 40.6, "YOU SOUND FRUSTRATED. LET'S SLOW DOWN."],
  ['t', 40.8, 43.6, "WHAT'S THE DERIVATIVE OF JUST X²?"],
  ['s', 43.8, 46.4, '...2X? OH! I GET IT!'],
  ['t', 46.6, 49.2, "EXACTLY. YOU'VE GOT THIS."],
  ['p', 49.6, 51.3, 'IS IT SAFE TO PONDER YET?'],
];
const TYPE_RATE = 30;
// Lines the viewer clicked to finish early (their mouths stop with the text)
// and lines they dismissed.
const REVEALED = new Set();
const DISMISSED = new Set();
const talking = (who, t) =>
  LINES.some(([w, a, b, txt], i) => w === who && !REVEALED.has(i) && !DISMISSED.has(i) && t >= a && t < Math.min(b, a + txt.length / TYPE_RATE + 0.35));
const onScreen = (i, t) => t >= LINES[i][1] && t < LINES[i][2] && !DISMISSED.has(i);
const typedAll = (i, t) => REVEALED.has(i) || (t - LINES[i][1]) * TYPE_RATE >= LINES[i][3].length;

// ---------------------------------------------------------------- key times

// the student
const T_STAND = 25.2; // jumps up and kicks the chair over
const T_PULL = 25.933; // reaches behind the back
const T_DRAW = 26.0; // the bare receiver comes out
const T_KNIVES = 26.84; // switchblades flip out
const T_LOCK = 26.95; // the last part locks in: impact frame
const T_COVERS = 27.12; // missile pod covers flip open
const T_LEVEL = 27.75; // swings the gun down to the hip
const T_SPIN = 27.85; // barrels spin up
const FIRE_START = 28.1;
const FIRE_END = 29.4;
const T_TURN = 29.45; // turns to the viewer with the gun held up
const T_LOWER = 31.8; // lowers the smoking gun
const GUN_TOSS = 33.2; // swings it up over the shoulder
const GUN_RELEASE = 33.45; // lets go
const GUN_FLIGHT = 0.85; // it sails off the edge of the world
const GUN_LAND = GUN_RELEASE + GUN_FLIGHT;
const GUN_LAND_AT = new THREE.Vector3(-112, 0, -30);
const FIRE_ROOT = [-13, -15];

// the philosopher
const PH_GLANCE = 25.75;
const PH_ALERT = 25.933;
const PH_JUMP = 26.133;
const PH_LAND = 26.333;
const HIDE = [65, -13, 0.95]; // crouched beside his rock
const PH_RUN = 27.933;
// The escape route sweeps to the right across the island's right side, 90
// to 115 units from the student on screen, and ends at the island's right tip
// so he moves across the screen instead of away from the camera.
const ESCAPE = new THREE.SplineCurve(
  [[74, -10], [87, -12], [93, -23], [91, -37], [83, -51]].map(([x, z]) => new THREE.Vector2(x, z)),
);
ESCAPE.arcLengthDivisions = 400;
const ESCAPE_LEN = ESCAPE.getLength();
const ESCAPE_END = ESCAPE.points[ESCAPE.points.length - 1];
const RUN_V = 80;
const RUN_ACC = 0.25;
const runDist = (t, t0, v, acc) => {
  const s = t - t0;
  return s <= 0 ? 0 : s < acc ? (v * s * s) / (2 * acc) : v * (s - acc / 2);
};
const PH_DIVE = PH_RUN + ESCAPE_LEN / RUN_V + RUN_ACC / 2;
const DIVE_DUR = 0.45;
const PH_GONE = PH_DIVE + DIVE_DUR;
const DIVE_DIR = new THREE.Vector2(0.05, -1).normalize(); // off the right tip, into the fade
const RUN_YAW0 = (() => {
  const d = ESCAPE.getTangentAt(0);
  return Math.atan2(d.x, d.y);
})();
const FLEE_FROM = [78, -22];
const FLEE_DIR = new THREE.Vector2(0.7, -0.714).normalize();
const FLEE_START = 51.25;

// The gun parts fly in from the edge of the world, one after another, and
// lock onto the receiver. `from` is the direction they come from in the
// gun's frame, `pt` where they land (used for sparks and lettering).
const FLY_T = 0.3;
const FLY_D = 180;
const ASSEMBLY = [
  { part: 'stock', at: 26.1, from: [-0.55, 0.3, -0.78], spin: [1, 0, 0], pt: [0, 3, -12], sfx: 'CLICK', col: '#ffffff' },
  { part: 'drum', at: 26.22, from: [-0.8, -0.45, 0.4], spin: [1, 0, 0], pt: [0, -12, 22], sfx: 'CLUNK', col: '#ffd23f' },
  { part: 'shroud', at: 26.34, from: [0.85, 0.35, 0.4], spin: [0, 0, 1], pt: [0, 5.5, 36], sfx: 'KLANG', col: '#ff9a3c' },
  { part: 'scope', at: 26.46, from: [0.1, 1, 0.1], spin: [0, 1, 0], pt: [0, 19, 14], sfx: 'TINK', col: '#e8f4ff' },
  { part: 'podL', at: 26.56, from: [0.9, 0.4, -0.2], spin: [0, 1, 0], pt: [10, 20, 10], sfx: 'THUNK', col: '#ffd23f' },
  { part: 'podR', at: 26.64, from: [-0.9, 0.4, 0.2], spin: [0, 1, 0], pt: [-10, 20, 10], sfx: 'THUNK', col: '#ffd23f' },
  { part: 'cleaver', at: 26.74, from: [-0.25, -0.2, 0.95], spin: [1, 0, 0], pt: [0, -9, 52], sfx: 'CHAK', col: '#ffffff' },
].map((a) => ({ ...a, dir: V(...a.from).normalize() }));

// Missiles: one for the rock, six chasing the philosopher, and the big one.
const TUBES = {
  L: [[7.5, 17.5], [12.5, 23.5], [12.5, 17.5], [7.5, 23.5]],
  R: [[-7.5, 17.5], [-12.5, 23.5], [-12.5, 17.5], [-7.5, 23.5]],
};
const MISSILES = [
  { launch: 27.3, dur: 0.4, from: 'L', tube: 0, size: 1.3, kind: 'rock' },
  { launch: 28.15, dur: 0.46, from: 'L', tube: 1, size: 1, kind: 'small' },
  { launch: 28.27, dur: 0.5, from: 'R', tube: 0, size: 1, kind: 'small' },
  { launch: 28.39, dur: 0.46, from: 'L', tube: 2, size: 1, kind: 'small' },
  { launch: 28.51, dur: 0.5, from: 'R', tube: 1, size: 1, kind: 'small' },
  { launch: 28.63, dur: 0.46, from: 'L', tube: 3, size: 1, kind: 'small' },
  { launch: 28.75, dur: 0.5, from: 'R', tube: 2, size: 1, kind: 'small' },
  { launch: 28.95, dur: 1.0, from: 'top', size: 2.4, kind: 'mega' },
];
const ROCK_BOOM = MISSILES[0].launch + MISSILES[0].dur;
const PH_BLAST = ROCK_BOOM;
const MEGA = MISSILES[7].launch + MISSILES[7].dur;
const MEGA_AT = new THREE.Vector3(74, 0, -52); // where he went over the edge
const BLAST = {
  rock: { n: 10, r: 10, puff: 7.5, rise: 34, shake: 3, life: 0.85, debris: 16, dsp: 70, dup: 95, dsize: 1.6, embers: 8, ring: 42 },
  small: { n: 6, r: 6, puff: 5, rise: 16, shake: 1.5, life: 1.2, debris: 6, dsp: 45, dup: 70, dsize: 1, embers: 4, ring: 22 },
  mega: { n: 14, r: 22, puff: 11, rise: 26, shake: 5, life: 2.4, debris: 24, dsp: 90, dup: 130, dsize: 1.8, embers: 16, ring: 125 },
};
const BULLET_V = 650;
const SPIN_W = 42; // barrel speed while firing, radians per second

// barrel angle: spun up, held while firing, then winding down
function barrelAngle(t) {
  const up = FIRE_START - T_SPIN, down = 1.6;
  if (t < T_SPIN) return 0;
  if (t < FIRE_START) {
    const s = t - T_SPIN;
    return (SPIN_W * s * s) / (2 * up);
  }
  const a1 = (SPIN_W * up) / 2;
  if (t < FIRE_END) return a1 + SPIN_W * (t - FIRE_START);
  const a2 = a1 + SPIN_W * (FIRE_END - FIRE_START);
  const s = Math.min(t - FIRE_END, down);
  return a2 + SPIN_W * (s - (s * s) / (2 * down));
}

// How the student holds the gun, in their root frame (facing +z).
const HOLD = {
  side: { p: [-14, 52, -8], e: [1.3, 0.3, 0] }, // just pulled out, on the way up
  present: { p: [-11, 37, 9], e: [-0.5, 0.15, 0] }, // held up while the parts arrive
  up: { p: [-22, 50, 6], e: [-1.35, 0.08, 0.1] }, // pointed at the sky
  low: { p: [-15, 40, 8], e: [0.62, 0.05, 0] }, // lowered, still smoking
  toss: { p: [-12, 66, -10], e: [-1.9, 0.15, 0] }, // swung up over the shoulder
};
const GUN_HULL = [];
for (const x of [-16, 16]) for (const y of [-21, 28]) for (const z of [-22, 68]) GUN_HULL.push([x, y, z]);

// scratch objects for the gun and root frames
const _Y = new THREE.Vector3(0, 1, 0);
const _ONE = new THREE.Vector3(1, 1, 1);
const GUN_SCALE = 0.8; // still absurd, but leaves room between the barrels and the philosopher
const _GS = new THREE.Vector3(GUN_SCALE, GUN_SCALE, GUN_SCALE);
const _rp = new THREE.Vector3();
const _rq = new THREE.Quaternion();
const _hp = new THREE.Vector3();
const _hv = new THREE.Vector3();
const _hq = new THREE.Quaternion();
const _qa = new THREE.Quaternion();
const _qb = new THREE.Quaternion();
const _he = new THREE.Euler();
const _gl = new THREE.Matrix4();
const _gj = new THREE.Matrix4();
const _gr = new THREE.Matrix4();
const _gr2 = new THREE.Matrix4();
const _inv = new THREE.Matrix4();
const _X = new THREE.Vector3(1, 0, 0);
const GUN_CM = new THREE.Vector3(...GUN.cm);
const holdQ = (h, out) => (h.q ? out.copy(h.q) : out.setFromEuler(_he.set(h.e[0], h.e[1], h.e[2], 'YXZ')));

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
    this._w2 = V();
    this._aim = V();
    this._q = new THREE.Quaternion();
    this._m = new THREE.Matrix4();
    this._mz = new THREE.Matrix4();
    // per-shot data, filled in the first time each is needed
    this._mc = [];
    this._bullets = [];
    this._casings = [];
    this._smoke = [];
    this._cool = [];
    // The philosopher's escape runs along the rim, where the island's ragged
    // shoreline would eat into him; he gets his own, wider fade while he runs.
    for (const m of [stage.phil.headMat, stage.phil.bodyMat]) m.userData.u.uFade = { value: shared.uFade.value.clone() };
    this.buildTracks();
  }

  resize(W, H) {
    this.W = W;
    this.H = H;
  }

  // ------------------------------------------------------------ tracks

  buildTracks() {
    const st = this.st;
    const gunGrip = (side) => () => {
      st.gun.updateMatrixWorld(true);
      const g = side === 'R' ? GUN.gripR : GUN.gripL;
      return V(g[0], g[1], g[2]).applyMatrix4(st.gun.matrixWorld);
    };
    const holding = (o) => STANDING({ hL: gunGrip('L'), hR: gunGrip('R'), ...o });
    const devSide = (sx) => () => {
      st.device.updateMatrixWorld(true);
      return V(sx, 18, -1).applyMatrix4(st.device.matrixWorld);
    };
    // braced, both hands on the gun while the parts slam home
    const present = (t) =>
      holding({
        root: [-12, -15, 1.45],
        hipsY: 36 - 2.5 * pulse(t, T_LOCK, 0.2),
        hips: [0.02, 0.12, 0],
        spine: [0.04, -0.22, 0],
        head: [0.04, 0.12, 0],
        fL: [9, 6, 7],
        fR: [-9, 6, -6],
        poles: { armL: [8, -8, -6], armR: [-10, -8, -6] },
      });
    // hip fire, turning to follow the philosopher
    const firing = (t) => {
      const sh = t > FIRE_START && t < FIRE_END ? 1 : 0;
      return holding({
        root: [FIRE_ROOT[0] + jit(t, 1, 0.45 * sh), FIRE_ROOT[1] + jit(t, 2, 0.45 * sh), this.fireYaw(t)],
        hipsY: 35,
        hips: [0.05, 0.12, 0],
        spine: [0.1, -0.32, jit(t, 3, 0.025 * sh)],
        head: [0.06, 0.22, 0],
        fL: [10, 6, 9],
        fR: [-10, 6, -7],
        poles: { armL: [6, -8, -6], armR: [-10, -6, -8] },
      });
    };
    // facing the viewer, gun pointed at the sky, hand on hip
    const posing = () =>
      STANDING({
        root: [FIRE_ROOT[0], FIRE_ROOT[1], 0.72],
        hipsY: 37.5,
        hips: [0, 0.05, 0],
        spine: [-0.05, 0.1, 0.02],
        head: [-0.08, 0.05, 0.1],
        fL: [8, 6, 3],
        fR: [-8, 6, -2],
        hL: [15, 38, -2],
        hR: gunGrip('R'),
        poles: { armL: [16, 2, 6], armR: [-12, -6, 2] },
      });
    const lowered = () =>
      holding({
        root: [FIRE_ROOT[0], FIRE_ROOT[1], 0.95],
        hipsY: 37,
        spine: [0.1, 0.05, 0],
        head: [0.36, 0.3, 0],
        fL: [7, 6, 2],
        fR: [-7, 6, -1],
        poles: { armL: [8, -8, -6], armR: [-10, -8, -6] },
      });

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
      [T_STAND, 0.35, () => STANDING({ head: [0.0, 0.7, 0], hL: [16, 40, 4], hR: [-16, 40, 4] }), E.back],
      [25.6, 0.25, () => STANDING({ root: [-11, -14, 1.45], head: [0.04, 0.05, 0], spine: [0.06, 0, 0] })],
      [T_PULL, 0.067, () => STANDING({ root: [-11, -14, 1.45], spine: [0.12, 0.4, 0], head: [0.06, -0.25, 0], hR: [-9, 47, -15], hL: [15, 36, 3], poles: { armR: [-14, -2, 6] } })],
      [T_DRAW, 0.067, (t) => present(t)],
      [T_LEVEL, 0.2, (t) => firing(t), E.out],
      [T_TURN, 0.3, () => posing(), E.inOut],
      [T_LOWER, 0.5, () => lowered()],
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
      [T_PULL, { brow: 'furious', eyes: 'focus', mouth: 'grin' }],
      [FIRE_START, { brow: 'furious', eyes: 'focus', mouth: 'shout' }],
      [FIRE_END, { brow: 'angry', eyes: 'focus', mouth: 'grin' }],
      [T_TURN + 0.15, { brow: 'flat', eyes: 'shut', mouth: 'smile' }],
      [T_LOWER, { brow: 'flat', eyes: 'down', mouth: 'small' }],
      [GUN_TOSS, { brow: 'flat', eyes: 'open', mouth: 'line' }],
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

    this.philTrack = new Track([
      [0, 0, (t) => P({ spine: [0.42 + Math.sin(t * 1.8) * 0.012, -0.1, 0.06] })],
      // one eye opens at the noise, then he sees what is in the student's hands
      [PH_GLANCE, 0.15, () => P({ head: [-0.1, -0.45, 0.05] })],
      [PH_ALERT, 0.1, () => P({ spine: [0.08, -0.25, 0], head: [-0.1, -0.85, 0], hR: [-14, 46, 10], hL: [12, 40, 12], poles: {} }), E.out],
      [PH_JUMP, 0.067, (t) => this.philJump(t)],
      [PH_LAND, 0.1, (t) => this.philCower(t), E.out],
      [PH_BLAST, 0.05, (t) => this.philBlown(t)],
      [PH_RUN, 0.067, (t) => this.philRun(t)],
      [PH_DIVE, 0.1, (t) => this.philDive(t)],
      // back much later with a white flag
      [49.4, 0, (t) => this.philCreep(t)],
      [51.2, 0.15, (t) => this.philFlee(t)],
    ]);
    this.philFace = [
      [0, { brow: 'calm', eyes: 'closed', mouth: 'closed' }],
      [PH_GLANCE, { brow: 'calm', eyes: 'glance', mouth: 'closed' }],
      [PH_ALERT, { brow: 'raised', eyes: 'wide', mouth: 'closed' }],
      [PH_JUMP, { brow: 'raised', eyes: 'wide', mouth: 'open' }],
      [PH_LAND, { brow: 'raised', eyes: 'wide', mouth: 'closed' }],
      [PH_BLAST, { brow: 'raised', eyes: 'wide', mouth: 'open' }],
      [49.4, { brow: 'raised', eyes: 'glance', mouth: 'smile' }],
      [51.0, { brow: 'raised', eyes: 'wide', mouth: 'open' }],
    ];

    // where the gun sits relative to the student's root
    this.gunHolds = new Track([
      [0, 0, () => HOLD.side],
      [T_DRAW + 0.02, 0.08, () => HOLD.present],
      [T_LEVEL, 0.2, (t) => this.aimHold(t)],
      [T_TURN, 0.3, () => HOLD.up],
      [T_LOWER, 0.5, () => HOLD.low],
      [GUN_TOSS, 0.25, () => HOLD.toss],
    ]);
  }

  // ------------------------------------------------------------ the philosopher's escape

  // His position on the floor at time t, independent of the rig.
  philGround(t) {
    if (t < PH_JUMP) return [ROCK_SEAT[0], ROCK_SEAT[1]];
    if (t < PH_LAND) {
      const u = seg(t, PH_JUMP, PH_LAND);
      return [lerp(ROCK_SEAT[0], HIDE[0], u), lerp(ROCK_SEAT[1], HIDE[1], u)];
    }
    if (t < PH_BLAST) return [HIDE[0], HIDE[1]];
    if (t < PH_RUN) {
      const u = E.out(seg(t, PH_BLAST, PH_RUN));
      const s = ESCAPE.points[0];
      return [lerp(HIDE[0], s.x, u), lerp(HIDE[1], s.y, u)];
    }
    if (t < PH_DIVE) {
      const p = ESCAPE.getPointAt(clamp01(runDist(t, PH_RUN, RUN_V, RUN_ACC) / ESCAPE_LEN));
      return [p.x, p.y];
    }
    const d = Math.min(t - PH_DIVE, DIVE_DUR) * 80;
    return [ESCAPE_END.x + DIVE_DIR.x * d, ESCAPE_END.y + DIVE_DIR.y * d];
  }

  philJump(t) {
    const u = seg(t, PH_JUMP, PH_LAND);
    const [x, z] = this.philGround(t);
    return {
      root: [x, z, angLerp(1.78, HIDE[2], E.in(u))],
      rootY: lerp(20, 0, u) + 14 * Math.sin(Math.PI * u),
      hipsY: 33,
      hips: [0.1, 0, 0],
      spine: [0.05, 0, 0],
      head: [-0.2, 0, 0],
      fL: [5, 12, 6],
      fR: [-5, 9, -3],
      hL: [16, 74, 4],
      hR: [-16, 72, 4],
      poles: { armL: [10, 4, -6], armR: [-10, 4, -6] },
    };
  }

  // hunched beside the rock with his hands over his head, trembling
  philCower(t) {
    const tr = Math.floor(t * 15) % 2 ? 1 : -1;
    return {
      root: [HIDE[0] + tr * 0.3, HIDE[1], HIDE[2]],
      rootY: 0,
      hipsY: 19,
      hips: [0.25, 0, 0],
      spine: [0.5, 0, tr * 0.03],
      head: [-0.3, 0.1, 0],
      fL: [6, 6, 9],
      fR: [-6, 6, 8],
      hL: (rig) => rig.headPoint(7, 22, 3),
      hR: (rig) => rig.headPoint(-7, 22, 3),
      poles: { armL: [14, 2, 4], armR: [-14, 2, 4] },
    };
  }

  // thrown clear when the rock goes up, spinning, landing on his feet
  philBlown(t) {
    const u = seg(t, PH_BLAST, PH_RUN);
    const [x, z] = this.philGround(t);
    return {
      root: [x, z, HIDE[2] + E.out(u) * (Math.PI * 2 + wrap(RUN_YAW0 - HIDE[2]))],
      rootY: 22 * Math.sin(Math.PI * u),
      hipsY: 35,
      hips: [-0.15, 0, 0],
      spine: [-0.25, 0, 0.15],
      head: [0.25, 0, 0],
      fL: [13, 9, -7],
      fR: [-12, 12, 5],
      hL: [27, 62, 0],
      hR: [-27, 64, -2],
      poles: {},
    };
  }

  philRun(t) {
    const d = runDist(t, PH_RUN, RUN_V, RUN_ACC);
    const u = clamp01(d / ESCAPE_LEN);
    const p = ESCAPE.getPointAt(u), tan = ESCAPE.getTangentAt(u);
    const yaw = Math.atan2(tan.x, tan.y);
    const v = RUN_V * Math.min(1, (t - PH_RUN) / RUN_ACC);
    // one terrified glance back over his shoulder
    const back = E.inOut(seg(t, 28.38, 28.48)) * (1 - E.inOut(seg(t, 28.62, 28.72)));
    const toS = Math.atan2(FIRE_ROOT[0] - p.x, FIRE_ROOT[1] - p.y);
    const look = clamp(wrap(toS - yaw), -1.2, 1.2) * back;
    return { root: [p.x, p.y, yaw], rootY: 0, ...sprint(t, PH_RUN, v, look) };
  }

  // a flat-out dive off the edge of the world
  philDive(t) {
    const u = seg(t, PH_DIVE, PH_GONE);
    const [x, z] = this.philGround(t);
    return {
      root: [x, z, Math.atan2(DIVE_DIR.x, DIVE_DIR.y)],
      rootY: 3 + 70 * u - 130 * u * u, // up, then down past the edge of the world
      hipsY: 24,
      hips: [1.3, 0, 0],
      spine: [0.12, 0, 0],
      head: [-0.95, 0, 0],
      fL: [5, 22, -31],
      fR: [-5, 25, -29],
      hL: [7, 31, 50],
      hR: [-7, 31, 50],
      poles: { armL: [10, -6, -4], armR: [-10, -6, -4], legL: [2, -30, 0], legR: [-2, -30, 0] },
    };
  }

  // creeping back in from the edge, white flag up
  philCreep(t) {
    const u = seg(t, 49.4, 50.2);
    const g = gait(t, 49.4, 30 / 0.8, 0.8, 0.62, WALK_SWING);
    const rest = seg(t, 50.2, 50.33);
    const foot = (f, z0) => [lerp(f[0], 6, rest), lerp(f[1], z0, rest)];
    const L = foot(g.L, 3), R = foot(g.R, 0);
    return {
      ...P({}),
      root: [lerp(102, 78, u), lerp(-40, -22, u), -0.93],
      hipsY: 37.5,
      hips: [0, 0, 0],
      spine: [0.12, 0.15, 0.08],
      head: [0.1, 0.25, 0.15],
      fL: [5, L[0], L[1]],
      fR: [-5, R[0], R[1]],
      hL: [10, 34, 8],
      hR: [-17 + Math.sin(t * 7) * 3, 78, 8],
      poles: { armR: [-10, -2, -2] },
    };
  }

  philFlee(t) {
    const d = runDist(t, FLEE_START, 85, 0.3);
    const v = 85 * clamp01((t - FLEE_START) / 0.3);
    return {
      root: [FLEE_FROM[0] + FLEE_DIR.x * d, FLEE_FROM[1] + FLEE_DIR.y * d, Math.atan2(FLEE_DIR.x, FLEE_DIR.y)],
      rootY: 0,
      ...sprint(t, FLEE_START, v),
    };
  }

  // ------------------------------------------------------------ aiming

  // The gun trails a little behind the philosopher, at his heels.
  aimPoint(t, out = V()) {
    const [x, z] = this.philGround(clamp(t - 0.16, PH_BLAST, PH_DIVE + 0.12));
    return out.set(x, 3, z);
  }

  fireYaw(t) {
    const a = this.aimPoint(t, this._aim);
    return clamp(Math.atan2(a.x - FIRE_ROOT[0], a.z - FIRE_ROOT[1]), 1.45, 2.6);
  }

  // hip hold, pointed straight at the aim point
  aimHold(t) {
    const root = this.studentRootAt(t, _gr2);
    const a = this.aimPoint(t, V()).applyMatrix4(_inv.copy(root).invert());
    const o = [-13, 41, 8];
    const dx = a.x - o[0], dy = a.y - o[1] - 5.5, dz = a.z - o[2];
    const yaw = clamp(Math.atan2(dx, dz), -0.4, 0.5);
    const pitch = clamp(Math.atan2(-dy, Math.hypot(dx, dz)), -0.1, 0.55);
    return { p: o, q: new THREE.Quaternion().setFromEuler(_he.set(pitch, yaw, 0, 'YXZ')) };
  }

  // ------------------------------------------------------------ per-frame update

  update(t) {
    const st = this.st;
    const tc = Math.floor(t * 15) / 15; // characters animate on twos
    const shake = { x: 0, y: 0 };
    const rm = this.reduceMotion;
    // a line only stays finished while it is on screen (the loop and skips move past it)
    for (const set of [REVEALED, DISMISSED]) for (const i of set) if (t < LINES[i][1] || t >= LINES[i][2]) set.delete(i);

    // loop transitions: dithered dissolve in and out
    shared.uDissolve.value = t < 0.6 ? 1 - seg(t, 0, 0.6) : seg(t, DURATION - 1.0, DURATION - 0.2);
    // one-bit impact frames when the gun locks and when the big one lands, then a flash
    const impact = (t >= T_LOCK && t < T_LOCK + 0.067) || (t >= MEGA && t < MEGA + 0.1);
    shared.uImpact.value = !rm && impact ? 1 : 0;
    const flash = (t >= MEGA + 0.1 ? 0.38 * (1 - seg(t, MEGA + 0.1, MEGA + 0.55)) : 0) + (t >= ROCK_BOOM && t < ROCK_BOOM + 0.1 ? 0.18 : 0);
    shared.uFlashAll.value = rm ? 0 : flash;

    // ---------------- props state
    // gun placement (must happen before hands are solved)
    this.updateGun(t);
    this.updateDevice(t);
    this.updateChair(t);

    // ---------------- student
    const s = st.student;
    applyActor(s, this.studentTrack, tc);
    let face = { ...stepAt(this.studentFace, tc) };
    if (talking('s', t) && Math.floor(t * 8) % 2 === 0) face.mouth = face.mouth.endsWith('+b') ? 'talk+b' : 'talk';
    if ((face.eyes === 'open' || face.eyes === 'focus') && tc % 3.7 < 0.12 && !(tc > 22.9 && tc < 34)) face.eyes = 'blink';
    s.setExpr(face);
    // face turns red from the chin up as frustration builds
    const flush = Math.min(1, seg(t, 15.8, 20.5) * 0.75 + seg(t, 22.9, 24.4) * 0.6) * (1 - seg(t, FIRE_END, 37.4));
    s.headMat.userData.u.uFlush.value = flush > 0.02 ? 1 : 0;
    s.headMat.userData.u.uFlushLevel.value = lerp(-2, 24, flush);

    // pencil in hand
    st.pencil.visible = t < 24.6 || t > 37.4;

    // ---------------- philosopher
    const p = st.phil;
    const visible = t < PH_GONE || (t > 49.4 && t < 52.4);
    p.rig.root.visible = visible;
    {
      const onRim = t > PH_BLAST - 0.05 && t < PH_GONE;
      const alpha = 1 - E.in(seg(t, PH_DIVE + 0.22, PH_GONE));
      for (const m of [p.headMat, p.bodyMat]) {
        m.userData.u.uFade.value.copy(shared.uFade.value);
        if (onRim) m.userData.u.uFade.value.setZ(400).setW(420);
        m.userData.u.uAlpha.value = onRim ? alpha : 1;
      }
    }
    if (visible) {
      applyActor(p, this.philTrack, tc);
      // a slow sway of the head while he holds forth
      if (t < PH_GLANCE && talking('p', t)) p.rig.neck.rotation.z = 0.04 + Math.sin(tc * 2.2) * 0.03;
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

    // ---------------- rock and burn marks
    st.rock.visible = t < ROCK_BOOM;
    st.rubble.visible = st.scorch.visible = t >= ROCK_BOOM;
    for (let i = 1; i < MISSILES.length; i++) {
      const m = st.scorches[i - 1];
      m.visible = t >= MISSILES[i].launch + MISSILES[i].dur;
      if (!m.visible) continue;
      const c = this.missileInfo(i).p3;
      const sc = MISSILES[i].kind === 'mega' ? 1.5 : 0.55;
      m.position.set(c.x, -0.6, c.z);
      m.scale.set(sc, 1, sc);
    }

    // ---------------- effects
    this.effects(t, shake);

    if (rm) {
      shake.x = 0;
      shake.y = 0;
    }
    // On a narrow (portrait) screen the escape and the big blast happen past
    // the right edge, so the view pans right to follow them and back again,
    // in whole pixels.
    const narrow = Math.min(26, 330 - this.W);
    if (narrow > 0) shake.x -= Math.round(narrow * E.inOut(seg(t, 27.5, 28.3)) * (1 - E.inOut(seg(t, 31.4, 32.4))));
    this.lastShake = shake;
    return shake;
  }

  // kicked over backwards when the student jumps up, set right much later
  updateChair(t) {
    const st = this.st;
    const kick = E.out(seg(t, T_STAND, T_STAND + 0.4));
    const tip = t < 36.55 ? E.out(seg(t, T_STAND + 0.02, T_STAND + 0.3)) : 1 - E.back(seg(t, 36.55, 36.85));
    const back = kick * (1 - E.inOut(seg(t, 36.6, 37.1)));
    const bounce = Math.sin(Math.PI * seg(t, T_STAND + 0.3, T_STAND + 0.46)) * 0.12;
    st.chair.position.set(LAYOUT.chair.x, 0, LAYOUT.chair.z - 10 - 10 * back);
    st.chair.rotation.set(-(Math.PI / 2) * tip + bounce, 0, 0);
  }

  updateGun(t) {
    const st = this.st;
    const gun = st.gun;
    const parts = st.gunParts;
    gun.visible = t >= T_DRAW && t < GUN_LAND;
    if (!gun.visible) return;
    if (t < GUN_RELEASE) {
      this.gunMatrixAt(t, this._m).decompose(gun.position, gun.quaternion, gun.scale);
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
      gun.scale.copy(_GS);
      gun.position.copy(c).sub(GUN_CM.clone().multiplyScalar(GUN_SCALE).applyQuaternion(gun.quaternion));
    }

    // parts fly in from far away, spinning, and slam home
    for (const a of ASSEMBLY) {
      const h = parts[a.part];
      const t0 = a.at - FLY_T;
      h.visible = t >= t0;
      if (!h.visible) continue;
      const u = seg(t, t0, a.at);
      const off = Math.pow(1 - u, 1.25) * FLY_D - 2.5 * pulse(t, a.at, 0.08);
      h.position.copy(h.userData.home).addScaledVector(a.dir, off);
      const sp = (1 - u) * (1 - u) * Math.PI * 3;
      h.rotation.set(a.spin[0] * sp, a.spin[1] * sp, a.spin[2] * sp);
    }
    // switchblades flip out from along the shroud
    const kf = E.back(seg(t, T_KNIVES, T_KNIVES + 0.1));
    st.knifeL.rotation.set(-(Math.PI / 2) * (1 - kf), 0.16 * kf, 0, 'YXZ');
    st.knifeR.rotation.set(-(Math.PI / 2) * (1 - kf), -0.16 * kf, 0, 'YXZ');
    // pod covers flip up
    st.coverL.rotation.x = -1.9 * E.back(seg(t, T_COVERS, T_COVERS + 0.18));
    st.coverR.rotation.x = -1.9 * E.back(seg(t, T_COVERS + 0.06, T_COVERS + 0.24));
    st.barrelPivot.rotation.z = barrelAngle(t);
    const f = Math.floor(t * 30);
    st.flash.visible = t > FIRE_START && t < FIRE_END && f % 2 === 0;
    st.flash.rotation.z = f * 0.7;
    // red strips and the scope light up as it locks
    st.gunMat.userData.u.uGlow.value = t < T_LOCK ? 0 : t < T_LOCK + 0.13 ? f % 2 : 1;
  }

  // The student's root frame at time t, taken from the pose track alone so
  // that effects can ask about other moments without disturbing the rig.
  studentRootAt(t, out = new THREE.Matrix4()) {
    const [a, b, u] = this.studentTrack.at(Math.floor(t * 15) / 15);
    const body = b ? blendBody(a, b, u) : a;
    _rq.setFromAxisAngle(_Y, body.root[2]);
    return out.compose(_rp.set(body.root[0], body.rootY || 0, body.root[1]), _rq, _ONE);
  }

  // Where the gun is at time t while the student holds it, including the
  // knocks of parts slamming home and the recoil.
  gunMatrixAt(t, out = new THREE.Matrix4()) {
    const [a, b, u] = this.gunHolds.at(t);
    _hp.set(a.p[0], a.p[1], a.p[2]);
    holdQ(a, _hq);
    if (b) {
      _hp.lerp(_hv.set(b.p[0], b.p[1], b.p[2]), u);
      _hq.slerp(holdQ(b, _qb), u);
    }
    let jx = 0, jy = 0, jz = 0, jr = 0;
    for (const p of ASSEMBLY) {
      const k = pulse(t, p.at, 0.12);
      if (!k) continue;
      jx -= p.dir.x * 1.8 * k;
      jy -= p.dir.y * 1.8 * k;
      jz -= p.dir.z * 1.8 * k;
      jr -= 0.05 * k;
    }
    const lk = pulse(t, T_LOCK, 0.16);
    jy -= 2.4 * lk;
    jr += 0.06 * lk;
    if (t > FIRE_START && t < FIRE_END) {
      const f = Math.floor(t * 30) % 2;
      jz -= 1.8 * f;
      jr -= 0.03 * f;
    }
    for (const m of MISSILES) {
      const k = pulse(t, m.launch, 0.1);
      if (!k) continue;
      jz -= 1.5 * k * m.size;
      jr -= 0.04 * k;
    }
    _gl.compose(_hp, _hq, _GS);
    _gj.makeRotationX(jr).setPosition(jx, jy, jz);
    _gl.multiply(_gj);
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

  // ------------------------------------------------------------ shot data

  // muzzle and barrel direction at time t
  muzzleAt(t) {
    const m = this.gunMatrixAt(t, this._mz);
    return {
      pos: V(...GUN.muzzle).applyMatrix4(m),
      dir: V(0, 0, 1).transformDirection(m),
    };
  }

  bulletInfo(i) {
    if (this._bullets[i]) return this._bullets[i];
    const t0 = FIRE_START + i / 30;
    const mz = this.muzzleAt(t0);
    const aim = this.aimPoint(t0);
    const I = V(aim.x + (hash3(i, 9, 1) - 0.5) * 11, 0.5, aim.z + (hash3(i, 9, 2) - 0.5) * 11);
    const d = I.clone().sub(mz.pos);
    const len = d.length();
    return (this._bullets[i] = { t0, M: mz.pos, I, dir: d.normalize(), len });
  }

  casingInfo(i) {
    if (this._casings[i]) return this._casings[i];
    const t0 = FIRE_START + i / 15;
    const m = this.gunMatrixAt(t0, this._mz);
    const port = V(...GUN.port).applyMatrix4(m);
    const v0 = V(-1, 0.4, -0.3).transformDirection(m).multiplyScalar(30 + hash3(i, 3, 3) * 14);
    v0.y = 34 + hash3(i, 4, 4) * 20;
    return (this._casings[i] = { t0, port, v0 });
  }

  missileInfo(i) {
    if (this._mc[i]) return this._mc[i];
    const m = MISSILES[i];
    const gm = this.gunMatrixAt(m.launch);
    const loc = m.from === 'top' ? [0, 28, 22] : [...TUBES[m.from][m.tube], 26];
    const p0 = V(loc[0], loc[1], loc[2]).applyMatrix4(gm);
    const fwd = V(0, 0, 1).transformDirection(gm);
    let p3;
    if (m.kind === 'rock') p3 = V(LAYOUT.rock.x, 14, LAYOUT.rock.z);
    else if (m.kind === 'mega') p3 = MEGA_AT.clone();
    else {
      // land just behind him, on the island side of his path
      const [x, z] = this.philGround(Math.min(m.launch + m.dur, PH_DIVE) - 0.22);
      const ix = 4 - x, iz = -4 - z, n = Math.hypot(ix, iz) || 1;
      const k = 5 + (i % 3) * 3;
      p3 = V(x + (ix / n) * k, 0, z + (iz / n) * k);
    }
    let p1, p2;
    if (m.kind === 'mega') {
      p1 = p0.clone().addScaledVector(fwd, 20).add(V(0, 190, 0));
      p2 = p3.clone().add(V(0, 240, 0));
    } else {
      p1 = p0.clone().addScaledVector(fwd, 36).add(V(0, m.kind === 'rock' ? 28 : 34, 0));
      p2 = p3.clone().add(V(0, m.kind === 'rock' ? 46 : 58, 0));
    }
    const ch = p3.clone().sub(p0).normalize();
    const n1 = V().crossVectors(ch, _Y).normalize();
    const n2 = V().crossVectors(n1, ch).normalize();
    return (this._mc[i] = { p0, p1, p2, p3, n1, n2, wob: m.kind === 'small' ? 5 : 0 });
  }

  // a cubic arc from the pod to the target, corkscrewing on the way
  missilePath(i, u, out) {
    const c = this.missileInfo(i);
    const a = 1 - u;
    const b0 = a * a * a, b1 = 3 * a * a * u, b2 = 3 * a * u * u, b3 = u * u * u;
    out.set(
      b0 * c.p0.x + b1 * c.p1.x + b2 * c.p2.x + b3 * c.p3.x,
      b0 * c.p0.y + b1 * c.p1.y + b2 * c.p2.y + b3 * c.p3.y,
      b0 * c.p0.z + b1 * c.p1.z + b2 * c.p2.z + b3 * c.p3.z,
    );
    if (c.wob) {
      const w = c.wob * Math.sin(Math.PI * u);
      const ang = u * Math.PI * 3 + i;
      out.addScaledVector(c.n1, Math.cos(ang) * w).addScaledVector(c.n2, Math.sin(ang) * w);
    }
    return out;
  }

  // ------------------------------------------------------------ effects

  effects(t, shake) {
    const st = this.st;
    const fx = st.fx;
    const v = this._v;
    const w = this._w;
    const s = st.student.rig;

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

    // dust: the student jumping up, the chair landing, the philosopher's leaps and dive
    const dustBurst = (t0, cx, cy, cz, n, spread, color = 0xd9c4a2) => {
      const age = t - t0;
      if (age < 0 || age > 0.8) return;
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2 + t0;
        const r = spread * (0.4 + age * 1.6);
        fx.puff(w.set(cx + Math.cos(a) * r, cy + 1.5 + age * 6, cz + Math.sin(a) * r), 2.2 + age * 3, 1 - seg(age, 0.3, 0.8), color);
      }
    };
    dustBurst(25.3, -10, 0, -16, 6, 10);
    dustBurst(T_STAND + 0.3, -10, 0, -58, 6, 9);
    dustBurst(PH_JUMP + 0.02, ROCK_SEAT[0], 21, ROCK_SEAT[1], 5, 7);
    dustBurst(PH_LAND, HIDE[0], 0, HIDE[1], 6, 8);
    dustBurst(PH_RUN, ESCAPE.points[0].x, 0, ESCAPE.points[0].y, 5, 7);
    dustBurst(PH_DIVE, ESCAPE_END.x, 0, ESCAPE_END.y, 6, 8);

    // sparks where each gun part slams home
    if (st.gun.visible && t < T_LOCK + 0.3) {
      st.gun.updateMatrixWorld(true);
      for (const a of ASSEMBLY) {
        const age = t - a.at;
        if (age < 0 || age > 0.22) continue;
        const c = V(...a.pt).applyMatrix4(st.gun.matrixWorld);
        for (let k = 0; k < 7; k++) {
          const th = hash3(k, a.at * 10, 1) * Math.PI * 2;
          const ph = (hash3(k, a.at * 10, 2) - 0.3) * 1.6;
          const sp = 70 + hash3(k, a.at * 10, 3) * 70;
          fx.spark(
            w.set(c.x + Math.cos(th) * Math.cos(ph) * sp * age, c.y + Math.sin(ph) * sp * age - 150 * age * age, c.z + Math.sin(th) * Math.cos(ph) * sp * age),
            k % 2 ? 0xffffff : 0xffe066,
            age < 0.1 ? 1.2 : 0.8,
          );
        }
      }
      // the lock: a ring of sparks off the whole gun
      const la = t - T_LOCK;
      if (la >= 0 && la < 0.25) {
        const c = GUN_CM.clone().applyMatrix4(st.gun.matrixWorld);
        for (let k = 0; k < 12; k++) {
          const th = (k / 12) * Math.PI * 2;
          const sp = 120 + hash3(k, 5, 5) * 60;
          fx.spark(w.set(c.x + Math.cos(th) * sp * la, c.y + Math.sin(th) * sp * la * 0.7 - 120 * la * la, c.z + Math.sin(th * 1.3) * sp * la * 0.6), k % 3 ? 0xffe066 : 0xffffff, 1.1);
        }
      }
    }

    // the philosopher's feet kick up dust as he runs
    if (t > PH_RUN && t < PH_DIVE + 0.5) {
      for (let k = 0; k < 24; k++) {
        const tk = PH_RUN + k * 0.07;
        if (tk > Math.min(t, PH_DIVE)) break;
        const age = t - tk;
        if (age > 0.45) continue;
        const [x, z] = this.philGround(tk);
        fx.puff(w.set(x, 1.5 + age * 6, z), 1.8 + age * 5, 1 - seg(age, 0.18, 0.45), 0xd9c4a2);
      }
    }

    // minigun: tracers, hits walking along behind him, casings, smoke
    if (st.gun.visible && t > FIRE_START) {
      const nB = Math.floor((FIRE_END - FIRE_START) * 30);
      if (t < FIRE_END + 0.6) {
        for (let i = 0; i < nB; i++) {
          const b = this.bulletInfo(i);
          if (b.t0 > t) break;
          const age = t - b.t0;
          const fly = b.len / BULLET_V;
          if (age < fly) {
            fx.bullet(w.copy(b.M).addScaledVector(b.dir, Math.min(b.len - 4, age * BULLET_V + 6)), b.dir);
            continue;
          }
          const a = age - fly;
          if (a > 0.35) continue;
          fx.puff(w.set(b.I.x, 1.5 + a * 9, b.I.z), 1.6 + a * 7, 1 - seg(a, 0.12, 0.35), 0xd9c4a2);
          if (a < 0.12) {
            for (let k = 0; k < 2; k++) {
              const ang = hash3(i, k, 5) * Math.PI * 2;
              const sp = 40 + hash3(i, k, 6) * 50;
              fx.spark(w.set(b.I.x + Math.cos(ang) * sp * a, 1 + a * 60 - a * a * 260, b.I.z + Math.sin(ang) * sp * a), k ? 0xffffff : 0xffe066);
            }
          }
        }
        // muzzle smoke
        for (let i = 0; i < 20; i++) {
          const t0 = FIRE_START + i * 0.065;
          if (t0 >= FIRE_END || t0 > t) break;
          const age = t - t0;
          if (age > 0.5) continue;
          const mz = this._smoke[i] || (this._smoke[i] = this.muzzleAt(t0));
          w.copy(mz.pos).addScaledVector(mz.dir, 4 + age * 14);
          w.y += age * 12;
          fx.puff(w, 2 + age * 6, 1 - seg(age, 0.2, 0.5), 0xd8d8d8);
        }
      }
    }
    // spent casings: ejected while firing, then left lying on the floor
    if (t > FIRE_START) {
      const nC = Math.floor((FIRE_END - FIRE_START) * 15);
      for (let i = 0; i < nC; i++) {
        const c = this.casingInfo(i);
        if (c.t0 > t) break;
        const age = t - c.t0;
        ballistic(c.port, c.v0, Math.min(age, 5), v, { floorY: 0.6, rest: 0.35, fric: 0.5, bounces: 2 });
        fx.casing(v, age < 0.7 ? age * 22 + i : i * 1.3);
      }
    }
    // the barrels smoke while they cool
    if (st.gun.visible && t > FIRE_END && t < GUN_RELEASE + 0.2) {
      for (let k = 0; k < 40; k++) {
        const tk = FIRE_END + k * 0.11;
        if (tk > t || tk > GUN_TOSS) break;
        const age = t - tk;
        if (age > 1.1) continue;
        const m = this._cool[k] || (this._cool[k] = this.muzzleAt(tk).pos);
        fx.puff(w.set(m.x + Math.sin(age * 5 + k) * 2, m.y + 3 + age * 16, m.z), 1.4 + age * 3.2, 1 - seg(age, 0.4, 1.1), k % 3 ? 0xdedede : 0xf4f4f4);
      }
    }

    // missiles, their smoke trails and what they hit
    MISSILES.forEach((ms, i) => {
      const g = st.missiles[i];
      const age = t - ms.launch;
      g.visible = age >= 0 && age < ms.dur;
      if (g.visible) {
        const u = age / ms.dur;
        this.missilePath(i, u, g.position);
        g.lookAt(this.missilePath(i, Math.min(1, u + 0.02), this._w2));
        const grow = ms.kind === 'mega' ? 0.45 + 0.55 * E.out(seg(age, 0, 0.15)) : 1;
        g.scale.setScalar(ms.size * grow * GUN_SCALE);
      }
      const life = ms.kind === 'mega' ? 1.4 : 0.8;
      if (age > 0 && age < ms.dur + life) {
        const step = ms.kind === 'mega' ? 0.025 : 0.03;
        const big = ms.kind === 'mega' ? 2.2 : 1;
        for (let k = 0; k * step <= Math.min(age, ms.dur); k++) {
          const tk = k * step;
          const pa = age - tk;
          if (pa > life) continue;
          const pos = this.missilePath(i, tk / ms.dur, w);
          pos.y += pa * 6;
          fx.puff(pos, (1.4 + pa * 4.5) * big, 1 - seg(pa, life * 0.4, life), 0xe6e6e6);
        }
      }
      const ea = age - ms.dur;
      if (ea >= 0 && ea < BLAST[ms.kind].life + 1.2) this.explosion(this.missileInfo(i).p3, ea, i, shake, ms.kind);
    });

    // firing shakes the view a little
    if (t > FIRE_START && t < FIRE_END) shake.x += Math.floor(t * 30) % 2;
    // head bonk
    if (t > 21.15 && t < 21.25) shake.y += 1;

    // dust as the philosopher bolts again at the very end
    if (t > FLEE_START && t < 52.4) {
      for (let k = 0; k < 14; k++) {
        const t0 = FLEE_START + k * 0.08;
        const age = t - t0;
        if (age < 0 || age > 0.5) continue;
        const d = runDist(t0, FLEE_START, 85, 0.3);
        fx.puff(w.set(FLEE_FROM[0] + FLEE_DIR.x * d, 2 + age * 6, FLEE_FROM[1] + FLEE_DIR.y * d), 2 + age * 5, 1 - seg(age, 0.2, 0.5), 0xd9c4a2);
      }
    }

    fx.end();
  }

  explosion(c, age, seed, shake, kind) {
    const fx = this.st.fx;
    const K = BLAST[kind];
    const w = this._w2;
    if (age < 0.35) {
      const amp = K.shake * (1 - age / 0.35);
      shake.x += Math.round(jit(age * 60, seed, amp));
      shake.y += Math.round(jit(age * 60, seed + 9, amp));
    }
    // white-hot core, fireball, then smoke
    if (age < 0.07) fx.puff(w.set(c.x, c.y + K.puff, c.z), K.puff * 2.4, 1, 0xffffff, true);
    for (let i = 0; i < K.n; i++) {
      const a = (i / K.n) * Math.PI * 2 + seed;
      const r = K.r * E.out(clamp01(age / 0.35)) * (0.45 + hash3(i, seed, 1) * 0.7);
      const hy = c.y + 4 + hash3(i, seed, 2) * K.r * 0.9 + age * K.rise;
      if (age < 0.55) {
        const col = age < 0.07 ? 0xffffff : age < 0.18 ? 0xffe066 : age < 0.32 ? 0xff9a3c : 0xe0512f;
        fx.puff(w.set(c.x + Math.cos(a) * r, hy, c.z + Math.sin(a) * r), K.puff * (0.6 + E.out(clamp01(age / 0.3)) * 0.8), 1 - seg(age, 0.32, 0.55), col, true);
      }
      if (age > 0.22) {
        const sa = age - 0.22;
        const spread = 1 + sa * 0.4;
        fx.puff(
          w.set(c.x + Math.cos(a) * r * spread, hy + sa * K.rise * 0.6, c.z + Math.sin(a) * r * spread),
          K.puff * (0.9 + sa * 0.6),
          1 - seg(sa, K.life * 0.45, K.life),
          i % 2 ? 0x77716e : 0x958f8a,
        );
      }
    }
    // debris
    for (let i = 0; i < K.debris; i++) {
      const a = (i / K.debris) * Math.PI * 2 + seed * 0.7;
      const sp = K.dsp * (0.5 + hash3(i, seed, 3) * 0.9);
      const p0 = V(c.x + Math.cos(a) * 3, c.y + 4 + hash3(i, seed, 4) * 6, c.z + Math.sin(a) * 3);
      const v0 = V(Math.cos(a) * sp, K.dup * (0.6 + hash3(i, seed, 5) * 0.8), Math.sin(a) * sp);
      const r = ballistic(p0, v0, age, w, { floorY: 1, rest: 0.3, fric: 0.5, bounces: 1 });
      const h = hash3(i, seed, 6);
      const col = kind === 'rock' ? (h > 0.7 ? 0x6e8f4c : h > 0.35 ? 0x7a7d84 : 0x8f9298) : h > 0.5 ? 0x8a6a4a : 0x6e5238;
      fx.chunk(w, K.dsize * (0.7 + hash3(i, seed, 7) * 0.8), col, r.settled ? i : age * 10 + i);
    }
    // embers
    if (age < 0.8) {
      for (let i = 0; i < K.embers; i++) {
        const a = hash3(i, seed, 8) * Math.PI * 2;
        const r = K.r * (0.3 + hash3(i, seed, 9)) * (0.5 + age);
        fx.spark(w.set(c.x + Math.cos(a) * r, c.y + 6 + age * (40 + hash3(i, seed, 10) * 50), c.z + Math.sin(a) * r), i % 2 ? 0xffe066 : 0xff9a3c, 0.8);
      }
    }
    // the big one rises into a mushroom cloud
    if (kind === 'mega') {
      const top = 18 + 95 * E.out(seg(age, 0.05, 1.9));
      const fade = 1 - seg(age, 1.9, 3.4);
      const hot = age < 0.45;
      for (let k = 0; k < 7; k++) {
        const h = (k / 6) * top;
        fx.puff(w.set(c.x + Math.sin(k * 1.7 + age * 2) * 2, c.y + h, c.z), 7 + k * 0.8 + age * 2, fade, hot ? 0xff9a3c : k % 2 ? 0x77716e : 0x8a8480, hot);
      }
      for (let k = 0; k < 11; k++) {
        const a = (k / 11) * Math.PI * 2;
        const rr = 12 + age * 9;
        fx.puff(w.set(c.x + Math.cos(a) * rr, c.y + top + Math.sin(a * 2) * 3, c.z + Math.sin(a) * rr), 10 + age * 4, fade, age < 0.5 ? 0xffb03b : k % 2 ? 0x6e6866 : 0x8f8985, age < 0.5);
      }
    }
  }

  // ------------------------------------------------------------ overlay

  // Screen areas the focus lines stay out of: the island and the actors.
  lineSkip(proj) {
    const st = this.st;
    const c = proj(V(4, 0, -4));
    const ax = 1.414 * 122, ay = 0.707 * 122;
    const boxes = [];
    const rigBox = (rig) => {
      const a = proj(rig.rootPoint(0, 0, 0, V()));
      boxes.push([a.x - 40, a.y - 132, a.x + 40, a.y + 10]);
    };
    rigBox(st.student.rig);
    if (st.phil.rig.root.visible) rigBox(st.phil.rig);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y, z] of GUN_HULL) {
      const q = proj(V(x, y, z).applyMatrix4(st.gun.matrixWorld));
      x0 = Math.min(x0, q.x);
      y0 = Math.min(y0, q.y);
      x1 = Math.max(x1, q.x);
      y1 = Math.max(y1, q.y);
    }
    boxes.push([x0 - 8, y0 - 8, x1 + 8, y1 + 8]);
    return (x, y) => {
      const dx = (x - c.x) / ax, dy = (y - c.y) / ay;
      if (dx * dx + dy * dy < 1) return true;
      for (const b of boxes) if (x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3]) return true;
      return false;
    };
  }

  // Game-style dialogue. With a line on screen, the first click finishes
  // typing it and the next one skips to where it ends. Returns the time to
  // jump to, or null when there is no line to act on.
  advance(t) {
    const on = LINES.map((_, i) => i).filter((i) => onScreen(i, t));
    if (!on.length) return null;
    const typing = on.filter((i) => !typedAll(i, t));
    if (typing.length) {
      for (const i of typing) REVEALED.add(i);
      return t;
    }
    const jump = on.filter((i) => LINES[i][4] !== 'hold');
    for (const i of on) if (LINES[i][4] === 'hold') DISMISSED.add(i);
    if (!jump.length) return t;
    // land on the first whole frame after the line, so it is gone at once
    return Math.ceil(Math.max(...jump.map((i) => LINES[i][2])) * 30 + 1e-6) / 30;
  }

  hasLine(t) {
    return LINES.some((_, i) => onScreen(i, t));
  }

  drawOverlay(t, shake) {
    const ov = this.ov;
    ov.clear();
    if (shared.uDissolve.value > 0.35) return;
    const st = this.st;
    const s = st.student.rig;
    const p = st.phil.rig;
    const W = this.W, H = this.H;
    const sc = ov.s;
    const big = sc + 1;
    const proj = (vec) => project(this.cam, W, H, vec, { x: 0, y: 0 });
    const at = (rig, x, y, z) => proj(rig.headPoint(x, y, z, V()));
    if (st.gun.visible) st.gun.updateMatrixWorld(true);
    const gunPt = (x, y, z) => proj(V(x, y, z).applyMatrix4(st.gun.matrixWorld));
    const impact = shared.uImpact.value > 0.5;

    // manga focus lines while the gun comes together, ink at the lock
    if (!this.reduceMotion && st.gun.visible && t > T_DRAW && t < T_LOCK + 0.1) {
      const f = gunPt(...GUN.cm);
      const strong = t >= T_LOCK;
      ov.focusLines(f.x, f.y, Math.floor(t * 15), {
        n: strong ? 64 : 44,
        col: strong || impact ? '#1f2230' : '#d6dae3',
        reach: strong ? [0.5, 0.85] : [0.28, 0.58],
        skip: this.lineSkip(proj),
      });
    }

    // speech
    LINES.forEach(([who, a, b, text], i) => {
      if (!onScreen(i, t)) return;
      let anchor;
      if (who === 's') anchor = s.headPoint(0, 30, 2, V());
      else if (who === 'p') anchor = p.headPoint(0, 27, 0, V());
      else anchor = s.headPoint(0, 27, 12, V());
      const pt = proj(anchor);
      const style = who === 's' ? 'student' : who === 'p' ? 'phil' : 'tutor';
      const lean = who === 's' ? -0.18 : who === 'p' ? 0.2 : -0.3;
      const full = typedAll(i, t);
      ov.bubble({ text, ax: pt.x, ay: pt.y, style, shown: full ? Infinity : Math.floor((t - a) * TYPE_RATE), lean, next: full && Math.floor(t * 2.5) % 2 === 0 });
    });

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
      ov.sprite('vein', q.x, q.y, sc);
    }
    // bonk
    if (t > 21.15 && t < 21.7) {
      const q = at(s, 0, 24, 10);
      ov.sprite('burst', q.x + 8 * sc, q.y - 4 * sc);
      ov.sfx('BONK!', q.x + 22 * sc, q.y - 14 * sc, '#ffd23f');
    }

    // the philosopher sees the gun
    if (t > PH_ALERT && t < PH_ALERT + 0.5) {
      const q = at(p, 2, 33, 0);
      ov.sprite('bang', q.x, q.y - Math.round(E.back(seg(t, PH_ALERT, PH_ALERT + 0.2)) * 4) * sc, sc * 2);
    }
    // and sweats behind his rock
    if (t > PH_LAND + 0.1 && t < PH_BLAST) {
      const q = at(p, -12, 20, 6);
      ov.sprite('sweat', q.x, q.y + (Math.floor(t * 6) % 3) * sc);
    }

    // lettering for each part as it slams home
    for (const a of ASSEMBLY) {
      if (t < a.at || t > a.at + 0.3) continue;
      const q = gunPt(...a.pt);
      const d = a.dir.clone().transformDirection(st.gun.matrixWorld);
      let dx = d.x - d.z, dy = 0.5 * (d.x + d.z) - 1.22 * d.y;
      const n = Math.hypot(dx, dy) || 1;
      dx /= n;
      dy /= n;
      const rise = Math.round(seg(t, a.at, a.at + 0.3) * 4) * sc;
      ov.sfx(a.sfx, q.x + dx * 22 * sc, q.y + dy * 16 * sc - rise, a.col);
    }
    // the knives catch the light
    if (t > T_KNIVES + 0.04 && t < T_KNIVES + 0.22) {
      for (const k of [st.knifeL, st.knifeR]) {
        k.updateWorldMatrix(true, false);
        const q = proj(V(0.5, 0, 27).applyMatrix4(k.matrixWorld));
        ov.sprite('glint', q.x, q.y);
      }
      const q = gunPt(10, 6, 62);
      ov.sfx('SHING!', q.x + 10 * sc, q.y + 12 * sc, '#e8f4ff');
    }
    // locked and loaded
    if (t > T_LOCK && t < T_LOCK + 0.32) {
      const q = gunPt(0, 30, 20);
      ov.sfx('KA-CHUNK!', q.x - 22 * sc, q.y - 6 * sc - Math.round(seg(t, T_LOCK, T_LOCK + 0.32) * 4) * sc, '#ff9a3c', '#1f2230', big);
    }
    if (t > T_LOCK + 0.1 && t < T_LOCK + 0.3) {
      const q = gunPt(-0.5, 19.5, 26);
      ov.sprite('glint', q.x, q.y);
    }
    // lock-on brackets over the philosopher behind his rock
    if (t > 27.0 && t < ROCK_BOOM && p.root.visible) {
      const q = at(p, 0, 10, 2);
      const u = E.out(seg(t, 27.0, 27.3));
      if (t < 27.3 || Math.floor(t * 10) % 2 === 0) ov.reticle(q.x, q.y, Math.round(lerp(36, 14, u)));
      if (t > 27.3) ov.sfx('LOCKED', q.x, q.y + 24 * sc, '#ff3b30');
    }
    // spin-up and firing
    if (st.gun.visible && t > T_SPIN && t < FIRE_START + 0.1) {
      const q = gunPt(0, 22, 50);
      ov.sfx('WHIRRR', q.x, q.y - 6 * sc, '#e8f4ff');
    }
    if (st.gun.visible && t > FIRE_START + 0.05 && t < FIRE_END) {
      const q = gunPt(0, 34, 18);
      const wob = Math.floor(t * 15) % 2;
      ov.sfx('BRRRRRT!', q.x + wob * sc, q.y - 10 * sc - wob * sc, '#ffd23f', '#1f2230', big);
    }
    // shockwaves on the floor and the big lettering
    MISSILES.forEach((ms, i) => {
      const ea = t - ms.launch - ms.dur;
      if (ea < 0 || ea > 0.5) return;
      const c = proj(this.missileInfo(i).p3);
      const K = BLAST[ms.kind];
      const u = ea / 0.5;
      ov.ring(c.x, c.y, 1.414 * K.ring * E.out(u), '#fff3b0', 1 - u, 0.5);
      ov.ring(c.x, c.y, 1.414 * K.ring * 0.7 * E.out(u), '#ffffff', 1 - u, 0.5);
    });
    if (t > ROCK_BOOM && t < ROCK_BOOM + 0.42) {
      const q = proj(V(LAYOUT.rock.x, 44, LAYOUT.rock.z));
      ov.sfx('KA-BOOM!', q.x, q.y - Math.round(seg(t, ROCK_BOOM, ROCK_BOOM + 0.42) * 6) * sc, '#ff9a3c', '#1f2230', big);
    }
    if (t > MEGA && t < MEGA + 1.0) {
      const q = proj(V(MEGA_AT.x, 70, MEGA_AT.z));
      const pop = t < MEGA + 0.1 ? 1 : 0;
      ov.sfx('KA-BOOOOM!', q.x, q.y - Math.round(seg(t, MEGA, MEGA + 1.0) * 8) * sc, '#ff9a3c', '#1f2230', big + pop);
    }
    if (t > GUN_LAND && t < GUN_LAND + 0.7) {
      const g = proj(V(GUN_LAND_AT.x, 6, GUN_LAND_AT.z));
      ov.sfx('CLANK.', g.x, g.y - Math.round(seg(t, GUN_LAND, GUN_LAND + 0.7) * 4) * sc, '#dfe3ea');
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
      const q = proj(s.rootPoint(17, 90, 4, V()));
      const by = q.y;
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

// exported for frame checks
export const TIMES = { T_STAND, T_PULL, T_LOCK, T_LEVEL, FIRE_START, FIRE_END, T_TURN, T_LOWER, GUN_TOSS, PH_JUMP, PH_RUN, PH_DIVE, PH_GONE, ROCK_BOOM, MEGA };
