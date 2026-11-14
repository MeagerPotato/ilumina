// The two actors: a student in a hoodie and a bearded philosopher in a toga.
// Each is a set of voxel parts hung on a simple joint hierarchy.
import * as THREE from 'three';
import { Vox, roundBox, hash3 } from './voxel.js';
import { pixelMat } from './engine.js';
import { twoBone, ARM_U, ARM_V, LEG_U, LEG_V } from './ik.js';

const SKIN = 1;

export const SP = {
  skin: 0xf0b78f,
  hair: 0x3b2a24,
  hairHi: 0x5a4034,
  hood: 0x4b7bd2,
  hoodDk: 0x3c66b3,
  hoodRib: 0x35599e,
  string: 0xe9e6f2,
  pants: 0x3a3f59,
  shoe: 0xf1efe9,
  shoeRed: 0xd9473d,
  sole: 0x2b2b33,
  eye: 0x1b1820,
  brow: 0x3b2a24,
  mouth: 0x7a2e2e,
  teeth: 0xffffff,
  tongue: 0xd85c5c,
  blush: 0xf2877f,
  white: 0xffffff,
};

export const PP = {
  skin: 0xd9a37b,
  skinHi: 0xe9bd96,
  beard: 0xf3f1ec,
  beardDk: 0xd6d2c9,
  toga: 0xf4ead3,
  togaDk: 0xe0d0aa,
  trim: 0xa8382f,
  rope: 0x8a5a33,
  sandal: 0x7a4b2a,
  eye: 0x1b1820,
  mouth: 0x5e2626,
  tongue: 0xc9525a,
  brow: 0xf3f1ec,
  white: 0xffffff,
};

function joint(parent, x, y, z) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  parent.add(g);
  return g;
}

// Joint layout shared by both characters (voxel units).
const DIMS = {
  spineY: 3,
  neckY: 24,
  shoulderX: 12.5,
  shoulderY: 20,
  upper: 13,
  fore: 16,
  hipX: 5.5,
  hipY: -1,
  thigh: 17,
  shin: 15,
};

export class Rig {
  constructor() {
    const d = DIMS;
    this.d = d;
    this.root = new THREE.Group();
    this.hips = joint(this.root, 0, 25, 0);
    this.spine = joint(this.hips, 0, d.spineY, 0);
    this.neck = joint(this.spine, 0, d.neckY, 0);
    this.shL = joint(this.spine, d.shoulderX, d.shoulderY, 0);
    this.shR = joint(this.spine, -d.shoulderX, d.shoulderY, 0);
    this.elL = joint(this.shL, 0, -d.upper, 0);
    this.elR = joint(this.shR, 0, -d.upper, 0);
    this.hipL = joint(this.hips, d.hipX, d.hipY, 0);
    this.hipR = joint(this.hips, -d.hipX, d.hipY, 0);
    this.knL = joint(this.hipL, 0, -d.thigh, 0);
    this.knR = joint(this.hipR, 0, -d.thigh, 0);
    this._t = new THREE.Vector3();
    this._p = new THREE.Vector3();
  }

  // Body pose: root on the floor (x, z, yaw) plus hip height and joint angles.
  setBody(p) {
    this.root.position.set(p.root[0], p.rootY || 0, p.root[1]);
    this.root.rotation.set(0, p.root[2], 0);
    this.hips.position.set(p.hipsX || 0, p.hipsY, p.hipsZ || 0);
    this.hips.rotation.set(p.hips[0], p.hips[1], p.hips[2], 'YXZ');
    this.spine.rotation.set(p.spine[0], p.spine[1], p.spine[2], 'YXZ');
    this.neck.rotation.set(p.head[0], p.head[1], p.head[2], 'YXZ');
    this.root.updateMatrixWorld(true);
  }

  // World-space point from coordinates in the root frame (character facing +z).
  rootPoint(x, y, z, out = new THREE.Vector3()) {
    return out.set(x, y, z).applyMatrix4(this.root.matrixWorld);
  }
  headPoint(x, y, z, out = new THREE.Vector3()) {
    this.neck.updateWorldMatrix(true, false);
    return out.set(x, y, z).applyMatrix4(this.neck.matrixWorld);
  }
  jointPoint(j, x, y, z, out = new THREE.Vector3()) {
    j.updateWorldMatrix(true, false);
    return out.set(x, y, z).applyMatrix4(j.matrixWorld);
  }

  // Hands and feet are world-space targets. Poles are offsets in the root frame.
  setLimbs(handL, handR, footL, footR, poles = {}) {
    const d = this.d;
    const sh = (j, side, off) => {
      j.updateWorldMatrix(true, false);
      const s = new THREE.Vector3().setFromMatrixPosition(j.matrixWorld);
      const o = off || [side * 9, -8, -14];
      const dir = new THREE.Vector3(o[0], o[1], o[2]).transformDirection(this.root.matrixWorld).multiplyScalar(20);
      return s.add(dir);
    };
    twoBone(this.shL, this.elL, d.upper, d.fore, handL, sh(this.shL, 1, poles.armL), ARM_U, ARM_V, -1);
    twoBone(this.shR, this.elR, d.upper, d.fore, handR, sh(this.shR, -1, poles.armR), ARM_U, ARM_V, -1);
    const kn = (j, side, off) => {
      j.updateWorldMatrix(true, false);
      const s = new THREE.Vector3().setFromMatrixPosition(j.matrixWorld);
      const o = off || [side * 2, 0, 30];
      return s.add(new THREE.Vector3(o[0], o[1], o[2]).transformDirection(this.root.matrixWorld).multiplyScalar(30));
    };
    twoBone(this.hipL, this.knL, d.thigh, d.shin, footL, kn(this.hipL, 1, poles.legL), LEG_U, LEG_V, 1);
    twoBone(this.hipR, this.knR, d.thigh, d.shin, footR, kn(this.hipR, -1, poles.legR), LEG_U, LEG_V, 1);
  }
}

// ---------------------------------------------------------------- faces

// A face plate is one slab of voxels on the front of the head. Swapping
// plates changes the expression without any z-fighting.
function plate(x0, x1, y0, y1, z, base, kind, feats) {
  const g = new Vox();
  g.box(x0, y0, z, x1, y1, z, base, kind);
  for (const [x, y, c] of feats) g.set(x, y, z, c, c === base ? kind : 0);
  return g;
}

const mirrorPts = (pts) => pts.flatMap(([x, y]) => [[x, y], [-1 - x, y]]);

const STUDENT_BROWS = {
  flat: [[1, 15], [2, 15], [3, 15], [4, 15]],
  up: [[1, 16], [2, 16], [3, 16], [4, 16]],
  angry: [[1, 14], [2, 14], [3, 15], [4, 15]],
  furious: [[1, 13], [2, 14], [3, 15], [4, 16], [1, 14]],
  worried: [[1, 16], [2, 16], [3, 15], [4, 15]],
};
const STUDENT_EYES = {
  open: [[2, 11], [3, 11], [2, 12], [3, 12], [2, 13], [3, 13]],
  focus: [[2, 11], [3, 11], [2, 12], [3, 12]],
  down: [[2, 10], [3, 10], [2, 11], [3, 11]],
  blink: [[2, 11], [3, 11], [1, 11]],
  wide: [[2, 10], [3, 10], [2, 11], [3, 11], [2, 12], [3, 12], [2, 13], [3, 13]],
  happy: [[1, 11], [2, 12], [3, 12], [4, 11]],
  shut: [[1, 12], [2, 11], [3, 11], [4, 12]],
};
const STUDENT_MOUTHS = {
  line: { d: [[-2, 8], [-1, 8], [0, 8], [1, 8]] },
  small: { d: [[-1, 8], [0, 8]] },
  frown: { d: [[-1, 8], [0, 8], [-2, 7], [1, 7]] },
  smile: { d: [[-1, 7], [0, 7], [-2, 8], [1, 8]] },
  wavy: { d: [[-2, 8], [-1, 7], [0, 8], [1, 7]] },
  talk: { d: [[-1, 7], [0, 7], [-1, 8], [0, 8], [-2, 8], [1, 8]] },
  shout: { d: [[-2, 6], [1, 6], [-2, 7], [-1, 7], [0, 7], [1, 7], [-2, 8], [-1, 8], [0, 8], [1, 8]], t: [[-1, 6], [0, 6]] },
  grin: { d: [[-3, 8], [2, 8], [-2, 7], [-1, 7], [0, 7], [1, 7]], w: [[-2, 8], [-1, 8], [0, 8], [1, 8]] },
  grit: {
    d: [[-3, 9], [-2, 9], [-1, 9], [0, 9], [1, 9], [2, 9], [-3, 6], [-2, 6], [-1, 6], [0, 6], [1, 6], [2, 6], [-3, 7], [-3, 8], [2, 7], [2, 8], [-1, 7], [-1, 8], [1, 7], [1, 8]],
    w: [[-2, 7], [-2, 8], [0, 7], [0, 8]],
  },
};

const PHIL_BROWS = {
  calm: [[1, 14], [2, 14], [3, 14], [4, 14], [1, 15], [2, 15], [3, 15], [4, 15], [5, 14]],
  raised: [[1, 16], [2, 16], [3, 16], [4, 16], [1, 17], [2, 17], [3, 17], [4, 17], [5, 16]],
  stern: [[1, 13], [2, 14], [3, 14], [4, 15], [1, 14], [2, 15], [3, 15], [4, 16], [5, 16]],
};
const PHIL_EYES = {
  closed: { d: [[1, 11], [2, 11], [3, 11], [4, 12]] },
  open: { d: [[2, 11], [3, 11], [2, 12], [3, 12]] },
  wide: { w: [[1, 10], [2, 10], [3, 10], [1, 11], [3, 11], [1, 12], [2, 12], [3, 12]], d: [[2, 11]] },
  glance: { d: [[3, 11], [4, 11], [3, 12], [4, 12]] },
};
const PHIL_MOUTHS = {
  closed: {},
  talk: { d: [[-1, 6], [0, 6], [-1, 7], [0, 7]] },
  smile: { d: [[-2, 7], [-1, 6], [0, 6], [1, 7]] },
  open: { d: [[-2, 6], [-1, 6], [0, 6], [1, 6], [-2, 7], [-1, 7], [0, 7], [1, 7]], t: [[-1, 6], [0, 6]] },
};

// ---------------------------------------------------------------- student

// A head is a rounded block for the face with an egg-shaped dome on top.
function domedHead(cy = 15, top = 9.5) {
  const box = roundBox(-10, 9, 3, 22, -9, 8, 3.2);
  return (x, y, z) =>
    y <= 17 ? box(x, y, z) : ((x + 0.5) / 9.6) ** 2 + ((y - cy) / top) ** 2 + ((z + 0.5) / 8.7) ** 2 <= 1;
}
const HAIR_DOME = { cy: 14, rx: 11.2, ry: 12.2, rz: 10.2 };
const inHairDome = (x, y, z) =>
  ((x + 0.5) / HAIR_DOME.rx) ** 2 + ((y - HAIR_DOME.cy) / HAIR_DOME.ry) ** 2 + ((z + 0.5) / HAIR_DOME.rz) ** 2 <= 1;
const hairTop = (x, z) => {
  const q = 1 - ((x + 0.5) / HAIR_DOME.rx) ** 2 - ((z + 0.5) / HAIR_DOME.rz) ** 2;
  return q <= 0 ? -1 : Math.floor(HAIR_DOME.cy + HAIR_DOME.ry * Math.sqrt(q));
};

function studentHead() {
  const g = new Vox();
  const inHead = domedHead();
  g.box(-3, 0, -3, 2, 3, 2, SP.skin, SKIN);
  g.fill(inHead, -10, 3, -9, 9, 25, 8, SP.skin, SKIN);
  for (let x = -7; x <= 6; x++) for (let y = 6; y <= 17; y++) g.del(x, y, 8);
  g.box(-1, 10, 9, 0, 11, 9, SP.skin, SKIN);
  g.box(-11, 9, -2, -11, 13, 1, SP.skin, SKIN);
  g.box(10, 9, -2, 10, 13, 1, SP.skin, SKIN);
  g.set(-11, 11, 0, 0xd99a74, SKIN);
  g.set(10, 11, 0, 0xd99a74, SKIN);

  // hair
  const inShell = roundBox(-11, 10, 2, 23, -10, 9, 3.6);
  const fringe = [0, 1, 2, 1, 0, 1, 2, 2, 1, 0, 1, 2, 1, 0, 0, 1, 2, 1, 0, 1, 2, 1];
  for (let x = -12; x <= 11; x++)
    for (let y = 6; y <= 27; y++)
      for (let z = -11; z <= 10; z++) {
        const back = z <= -6 && y >= 7 && y <= 17 && inShell(x, y, z);
        const cap = inHairDome(x, y, z) && y >= 16;
        if (!back && !cap) continue;
        if (z >= 6 && y < 20 - fringe[Math.min(21, Math.max(0, x + 11))]) continue;
        if (!back && y < 17 && z > -6) continue;
        // a few lighter strands sweep across the top
        const strand = y >= hairTop(x, z) - 1 && (x * 2 + z * 3 + 40) % 7 === 0;
        g.set(x, y, z, strand || hash3(x, y, z) > 0.93 ? SP.hairHi : SP.hair);
      }
  // sideburns
  g.box(-11, 14, -3, -11, 17, 3, SP.hair);
  g.box(10, 14, -3, 10, 17, 3, SP.hair);
  // messy tufts
  const tufts = [
    [-7, 26, -3, 2], [-6, 26, -2, 1], [-2, 26, -1, 3], [-1, 26, 0, 2], [3, 26, -4, 2],
    [4, 26, -3, 1], [7, 25, 1, 2], [-4, 26, -6, 1], [1, 26, 3, 1], [-9, 24, 2, 1],
  ];
  for (const [x, , z, h] of tufts) {
    const y0 = hairTop(x, z) + 1;
    if (y0 > 0) g.box(x, y0, z, x, y0 + h - 1, z, SP.hair);
  }
  // the one strand that never lies flat
  const cy = hairTop(0, -6) + 1;
  g.box(0, cy, -6, 0, cy + 1, -6, SP.hair);
  g.set(1, cy + 2, -6, SP.hair);
  return g;
}

function studentFaces() {
  const P = { brow: {}, eyes: {}, mouth: {} };
  for (const [k, pts] of Object.entries(STUDENT_BROWS))
    P.brow[k] = plate(-7, 6, 14, 17, 8, SP.skin, SKIN, mirrorPts(pts).map(([x, y]) => [x, y, SP.brow]));
  for (const [k, pts] of Object.entries(STUDENT_EYES)) {
    const f = mirrorPts(pts).map(([x, y]) => [x, y, SP.eye]);
    if (k === 'wide' || k === 'open') f.push([2, 13, SP.white], [-4, 13, SP.white]);
    P.eyes[k] = plate(-7, 6, 10, 13, 8, SP.skin, SKIN, f);
  }
  for (const blush of [false, true])
    for (const [k, m] of Object.entries(STUDENT_MOUTHS)) {
      const f = [];
      for (const [x, y] of m.d || []) f.push([x, y, SP.mouth]);
      for (const [x, y] of m.w || []) f.push([x, y, SP.teeth]);
      for (const [x, y] of m.t || []) f.push([x, y, SP.tongue]);
      if (blush) f.push([-6, 8, SP.blush], [-5, 8, SP.blush], [4, 8, SP.blush], [5, 8, SP.blush], [-6, 9, SP.blush], [5, 9, SP.blush]);
      P.mouth[k + (blush ? '+b' : '')] = plate(-7, 6, 6, 9, 8, SP.skin, SKIN, f);
    }
  return P;
}

function studentBody() {
  const parts = {};
  const hips = new Vox();
  hips.fill(roundBox(-11, 10, -5, 4, -6, 5, 1.6), -11, -5, -6, 10, 4, 5, SP.pants);
  parts.hips = hips;

  const torso = new Vox();
  torso.fill(roundBox(-11, 10, 0, 23, -6, 5, 2.2), -11, 0, -6, 10, 23, 5, (x, y) => (y <= 1 ? SP.hoodRib : SP.hood));
  torso.box(-7, 3, 6, 6, 8, 6, SP.hoodDk);
  torso.box(-7, 8, 6, 6, 8, 6, SP.hoodRib);
  torso.box(-7, 3, 6, -7, 7, 6, SP.hoodRib);
  torso.box(6, 3, 6, 6, 7, 6, SP.hoodRib);
  torso.box(-3, 14, 6, -3, 19, 6, SP.string);
  torso.box(2, 14, 6, 2, 19, 6, SP.string);
  torso.set(-3, 13, 6, 0xc9c6d6);
  torso.set(2, 13, 6, 0xc9c6d6);
  torso.fill(roundBox(-9, 8, 20, 26, -9, -2, 2.6), -9, 20, -9, 8, 26, -2, SP.hoodDk);
  torso.box(-9, 22, -2, -6, 24, 3, SP.hoodDk);
  torso.box(5, 22, -2, 8, 24, 3, SP.hoodDk);
  torso.box(-5, 23, 3, 4, 23, 4, SP.hoodDk);
  parts.torso = torso;

  const upper = new Vox();
  upper.fill(roundBox(-3, 3, -14, 2, -3, 3, 1.6), -3, -14, -3, 3, 2, 3, SP.hood);
  parts.upperL = upper;
  parts.upperR = upper;

  const fore = new Vox();
  fore.fill(roundBox(-3, 3, -11, 2, -3, 3, 1.6), -3, -11, -3, 3, 2, 3, SP.hood);
  fore.box(-3, -13, -3, 3, -12, 3, SP.hoodRib);
  fore.fill(roundBox(-2, 2, -19, -13, -2, 2, 1.1), -2, -19, -2, 2, -13, 2, SP.skin);
  fore.box(-1, -17, 3, 0, -15, 3, SP.skin);
  parts.fore = fore;

  const thigh = new Vox();
  thigh.fill(roundBox(-4, 4, -18, 2, -4, 4, 1.6), -4, -18, -4, 4, 2, 4, SP.pants);
  parts.thigh = thigh;

  const shin = new Vox();
  shin.fill(roundBox(-3, 3, -15, 1, -3, 3, 1.2), -3, -15, -3, 3, 1, 3, SP.pants);
  const shoeC = (x, y, z) => {
    if (y === -21) return SP.sole;
    if ((x === -4 || x === 4) && y >= -19 && y <= -18 && z >= -2 && z <= 6) return SP.shoeRed;
    if (y === -17 && z >= 4 && z <= 7 && z % 2 === 0 && x > -3 && x < 3) return 0xb9b5c6;
    return SP.shoe;
  };
  shin.fill(roundBox(-4, 4, -21, -15, -4, 4, 1.6), -4, -21, -4, 4, -15, 4, shoeC);
  shin.fill(roundBox(-4, 4, -21, -17, -4, 9, 1.4), -4, -21, -4, 4, -17, 9, shoeC);
  parts.shin = shin;
  return parts;
}

// ---------------------------------------------------------------- philosopher

function philHead() {
  const g = new Vox();
  const inHead = domedHead(16, 10.5);
  g.box(-3, -2, -3, 2, 3, 2, PP.skin);
  g.fill(inHead, -10, 3, -9, 9, 27, 8, (x, y, z) => {
    if (y >= 23 && z >= -1 && z <= 4 && x >= -4 && x <= 1) return PP.skinHi;
    return PP.skin;
  });
  for (let x = -7; x <= 6; x++) for (let y = 9; y <= 17; y++) g.del(x, y, 8);
  for (let x = -3; x <= 2; x++) for (let y = 6; y <= 8; y++) g.del(x, y, 8);
  // big nose
  g.box(-1, 9, 9, 0, 12, 9, PP.skin);
  g.box(-1, 9, 10, 0, 10, 10, PP.skin);
  g.set(-2, 9, 9, PP.skin);
  g.set(1, 9, 9, PP.skin);
  // ears
  g.box(-11, 9, -2, -11, 13, 1, PP.skin);
  g.box(10, 9, -2, 10, 13, 1, PP.skin);

  const beardC = (x, y, z) => ((x * 3 + y + z * 7) % 9 === 0 || hash3(x, y, z) > 0.84 ? PP.beardDk : PP.beard);
  // white hair ring around the back and sides
  const inShell = roundBox(-11, 10, 2, 23, -10, 9, 3.6);
  for (let x = -11; x <= 10; x++)
    for (let y = 8; y <= 17; y++)
      for (let z = -10; z <= 3; z++) {
        if (!inShell(x, y, z) || inHead(x, y, z)) continue;
        if (y >= 16 && Math.abs(x + 0.5) < 6 && z > -6) continue;
        if (Math.abs(x + 0.5) >= 9.5 && y >= 9 && y <= 13 && z >= -2 && z <= 1) continue;
        g.set(x, y, z, beardC(x, y, z));
      }
  // cheeks and jaw
  const inJaw = roundBox(-11, 10, -1, 11, -2, 10, 3);
  for (let x = -11; x <= 10; x++)
    for (let y = -1; y <= 11; y++)
      for (let z = -2; z <= 10; z++) {
        if (!inJaw(x, y, z) || inHead(x, y, z)) continue;
        const side = Math.abs(x + 0.5) >= 8.5;
        if (!side && y > 7) continue;
        if (side && y > 11) continue;
        if (x >= -3 && x <= 2 && y >= 6 && y <= 8 && z >= 9) continue;
        g.set(x, y, z, beardC(x, y, z));
      }
  // long beard hanging below the chin
  for (let y = -12; y <= 4; y++) {
    const t = (4 - y) / 16;
    const half = 9.5 - t * t * 7.5;
    const zf = 10 - Math.round(t * 2);
    const zb = Math.round(-1 + t * 6);
    for (let x = Math.ceil(-0.5 - half); x <= Math.floor(-0.5 + half); x++)
      for (let z = zb; z <= zf; z++) g.set(x, y, z, beardC(x, y, z));
  }
  g.set(-1, -13, 7, PP.beard);
  g.set(0, -13, 7, PP.beard);
  // moustache
  g.box(-6, 8, 9, 5, 9, 10, PP.beard);
  g.box(-7, 6, 9, -6, 7, 10, PP.beard);
  g.box(5, 6, 9, 6, 7, 10, PP.beard);
  for (let x = -3; x <= 2; x++) g.del(x, 8, 9);
  g.box(-2, 9, 9, 1, 9, 11, PP.beardDk);
  return g;
}

function philFaces() {
  const P = { brow: {}, eyes: {}, mouth: {} };
  for (const [k, pts] of Object.entries(PHIL_BROWS))
    P.brow[k] = plate(-7, 6, 14, 17, 8, PP.skin, 0, mirrorPts(pts).map(([x, y]) => [x, y, PP.brow]));
  for (const [k, m] of Object.entries(PHIL_EYES)) {
    const f = [];
    for (const [x, y] of mirrorPts(m.w || [])) f.push([x, y, PP.white]);
    for (const [x, y] of mirrorPts(m.d || [])) f.push([x, y, PP.eye]);
    P.eyes[k] = plate(-7, 6, 9, 13, 8, PP.skin, 0, f);
  }
  for (const [k, m] of Object.entries(PHIL_MOUTHS)) {
    const f = [];
    for (const [x, y] of m.d || []) f.push([x, y, PP.mouth]);
    for (const [x, y] of m.t || []) f.push([x, y, PP.tongue]);
    P.mouth[k] = plate(-3, 2, 6, 8, 8, PP.beard, 0, f);
  }
  return P;
}

function togaColor(x, y) {
  const s = (x + 12) / 23;
  const h = (y - 4) / 20;
  const e = h - s - 0.12;
  if (e > 0.06) return PP.skin;
  if (e > -0.04) return PP.trim;
  return ((Math.round((h - s) * 18) % 3) + 3) % 3 === 0 ? PP.togaDk : PP.toga;
}

function philBody() {
  const parts = {};
  const hips = new Vox();
  hips.fill(roundBox(-13, 12, -8, 5, -7, 6, 2.2), -13, -8, -7, 12, 5, 6, (x, y) => {
    if (y <= -7) return PP.trim;
    return (x + 40) % 5 === 0 ? PP.togaDk : PP.toga;
  });
  parts.hips = hips;

  const torso = new Vox();
  torso.fill(roundBox(-12, 11, 0, 24, -6, 6, 2.4), -12, 0, -6, 11, 24, 6, (x, y) => togaColor(x, y));
  torso.box(-12, 1, -6, 11, 2, 6, (x, y, z) => (torso.has(x, y, z) ? PP.rope : null));
  parts.torso = torso;

  const upperL = new Vox();
  upperL.fill(roundBox(-3, 3, -14, 2, -3, 3, 1.6), -3, -14, -3, 3, 2, 3, (x, y) => (y >= -6 ? (y === -6 ? PP.trim : PP.toga) : PP.skin));
  parts.upperL = upperL;
  const upperR = new Vox();
  upperR.fill(roundBox(-3, 3, -14, 2, -3, 3, 1.6), -3, -14, -3, 3, 2, 3, PP.skin);
  parts.upperR = upperR;

  const fore = new Vox();
  fore.fill(roundBox(-3, 3, -12, 2, -3, 3, 1.6), -3, -12, -3, 3, 2, 3, PP.skin);
  fore.fill(roundBox(-2, 2, -19, -12, -2, 2, 1.1), -2, -19, -2, 2, -12, 2, PP.skin);
  fore.box(-1, -17, 3, 0, -15, 3, PP.skin);
  fore.box(-3, -11, -3, 3, -11, 3, (x, y, z) => (Math.abs(x) === 3 || Math.abs(z) === 3 ? 0xc8a24a : null));
  parts.fore = fore;

  const thigh = new Vox();
  thigh.fill(roundBox(-5, 5, -19, 2, -5, 5, 1.8), -5, -19, -5, 5, 2, 5, (x, y, z) => {
    if (y <= -18) return PP.trim;
    return (x + z + 40) % 4 === 0 ? PP.togaDk : PP.toga;
  });
  parts.thigh = thigh;

  const shin = new Vox();
  shin.fill(roundBox(-3, 3, -15, 1, -3, 3, 1.2), -3, -15, -3, 3, 1, 3, PP.skin);
  shin.fill(roundBox(-3, 3, -21, -15, -3, 3, 1.2), -3, -21, -3, 3, -15, 3, PP.skin);
  shin.fill(roundBox(-3, 3, -21, -18, -3, 8, 1), -3, -21, -3, 3, -18, 8, PP.skin);
  shin.box(-4, -21, -4, 4, -21, 9, PP.sandal);
  shin.box(-3, -18, 5, 3, -18, 6, PP.sandal);
  shin.box(-4, -16, -4, 4, -16, 4, (x, y, z) => (Math.abs(x) === 4 || Math.abs(z) === 4 ? PP.sandal : null));
  parts.shin = shin;
  return parts;
}

// ---------------------------------------------------------------- assembly

function assemble(rig, body, headGrid, faces, headMat, bodyMat, torsoPz = 0) {
  const add = (parent, grid, mat, px = 0.5, py = 0, pz = 0.5) => {
    const m = grid.mesh(mat, px, py, pz);
    parent.add(m);
    return m;
  };
  add(rig.hips, body.hips, bodyMat, 0, 0, 0);
  add(rig.spine, body.torso, bodyMat, 0, 0, torsoPz);
  add(rig.shL, body.upperL, bodyMat);
  add(rig.shR, body.upperR, bodyMat);
  add(rig.elL, body.fore, bodyMat);
  add(rig.elR, body.fore, bodyMat);
  add(rig.hipL, body.thigh, bodyMat);
  add(rig.hipR, body.thigh, bodyMat);
  add(rig.knL, body.shin, bodyMat);
  add(rig.knR, body.shin, bodyMat);
  const head = headGrid.mesh(headMat, 0, 0, 0);
  rig.neck.add(head);
  const plates = { brow: {}, eyes: {}, mouth: {} };
  for (const region of ['brow', 'eyes', 'mouth'])
    for (const [k, grid] of Object.entries(faces[region])) {
      const m = grid.mesh(headMat, 0, 0, 0);
      m.visible = false;
      rig.neck.add(m);
      plates[region][k] = m;
    }
  const cur = { brow: null, eyes: null, mouth: null };
  const setExpr = (e) => {
    for (const region of ['brow', 'eyes', 'mouth']) {
      const k = e[region];
      if (cur[region] === k) continue;
      if (cur[region]) plates[region][cur[region]].visible = false;
      const m = plates[region][k];
      if (!m) throw new Error(`missing ${region} plate ${k}`);
      m.visible = true;
      cur[region] = k;
    }
  };
  return { head, plates, setExpr };
}

const ACTOR_SHADING = { dither: 0.4, occ: 0.45 };

export function createStudent() {
  const rig = new Rig();
  const headMat = pixelMat({ flushColor: 0xe0453b, ...ACTOR_SHADING });
  const bodyMat = pixelMat(ACTOR_SHADING);
  const { setExpr } = assemble(rig, studentBody(), studentHead(), studentFaces(), headMat, bodyMat);
  setExpr({ brow: 'flat', eyes: 'open', mouth: 'line' });
  return { rig, headMat, bodyMat, setExpr };
}

export function createPhilosopher() {
  const rig = new Rig();
  const headMat = pixelMat(ACTOR_SHADING);
  const bodyMat = pixelMat(ACTOR_SHADING);
  // white cloth goes muddy grey in shade, so his robe is lit a little extra
  bodyMat.userData.u.uBright.value = 0.16;
  headMat.userData.u.uBright.value = 0.06;
  const { setExpr } = assemble(rig, philBody(), philHead(), philFaces(), headMat, bodyMat, 0.5);
  setExpr({ brow: 'calm', eyes: 'closed', mouth: 'closed' });
  return { rig, headMat, bodyMat, setExpr };
}
