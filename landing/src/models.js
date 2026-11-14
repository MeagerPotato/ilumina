// Props: furniture, the philosopher's rock, the oversized gun, missiles, the
// wearable, and the small bits used by effects.
import { Vox, roundBox, hash3 } from './voxel.js';

export const GLOW = 2;

export const PAL = {
  desk: 0xbb7c4b,
  deskEdge: 0x9b6237,
  deskLeg: 0x8a5530,
  deskPanel: 0xa26a3d,
  knob: 0xe0b95e,
  chair: 0xa96f40,
  chairDk: 0x8c5833,
  paper: 0xf6f3ea,
  print: 0x8b8f9c,
  pencilMark: 0x5d6270,
  stone: 0x8e939c,
  stoneDk: 0x777c86,
  stoneLt: 0xa7acb4,
  moss: 0x6e8f4c,
  metal: 0x5a606c,
  metalDk: 0x40454f,
  metalLt: 0x767d8b,
  poly: 0x30333b,
  wood: 0x7b4c2b,
  hazard: 0xf2c230,
  black: 0x25272c,
  blade: 0xd3dae2,
  bladeDk: 0x9ba4ae,
  tape: 0xa3a7ad,
  olive: 0x66713f,
  oliveDk: 0x535d33,
  red: 0xd33b35,
  white: 0xeeeeee,
  lens: 0x6fe3ff,
  band: 0x2c3038,
  module: 0x1f2329,
  led: 0x52f7e6,
  bin: 0x9aa4ae,
  binDk: 0x7d8792,
};

export function buildDesk() {
  const g = new Vox();
  g.box(-32, 37, -15, 31, 39, 14, (x, y, z) =>
    y === 37 || x === -32 || x === 31 || z === -15 || z === 14 ? PAL.deskEdge : PAL.desk,
  );
  for (const [x, z] of [[-31, -14], [28, -14], [-31, 11], [28, 11]]) g.box(x, 0, z, x + 2, 36, z + 2, PAL.deskLeg);
  g.box(-29, 14, 12, 27, 36, 13, PAL.deskPanel);
  g.box(-30, 31, -12, -30, 36, 11, PAL.deskPanel);
  g.box(12, 3, -12, 28, 36, 13, PAL.deskPanel);
  // drawer fronts on the cabinet, facing the viewer
  const drawer = (y0, y1) => {
    g.box(13, y0, 14, 27, y1, 14, (x, y) => (x === 13 || x === 27 || y === y0 || y === y1 ? PAL.deskEdge : PAL.deskPanel));
    g.box(19, Math.round((y0 + y1) / 2), 15, 21, Math.round((y0 + y1) / 2), 15, PAL.knob);
  };
  drawer(25, 35);
  drawer(13, 23);
  drawer(4, 11);
  return g;
}

export function buildDeskStuff() {
  const g = new Vox();
  // stack of books, far left
  const book = (x0, y0, z0, w, h, d, cover) => {
    g.box(x0, y0, z0, x0 + w - 1, y0 + h - 1, z0 + d - 1, (x, y, z) => {
      const edgeY = y === y0 || y === y0 + h - 1;
      const spine = x === x0;
      if (!edgeY && !spine) return 0xefe6cf;
      return cover;
    });
  };
  book(-29, 40, 2, 17, 4, 12, 0xc0463c);
  book(-28, 44, 3, 15, 3, 10, 0x2f8f88);
  book(-29, 47, 2, 16, 4, 12, 0xd9a441);
  // mug with pencils, right side
  g.cyl('y', 22, 6, 3.6, 40, 47, (x, y, z) => (y === 47 ? 0x6b5a4a : y === 43 ? 0xd9473d : 0xeae5db));
  g.box(26, 42, 5, 26, 45, 7, 0xeae5db);
  g.box(27, 42, 5, 27, 45, 5, 0xeae5db);
  g.box(27, 45, 5, 27, 45, 7, 0xeae5db);
  g.box(21, 48, 5, 21, 53, 5, 0xf2c94c);
  g.set(21, 54, 5, 0x3a3a3a);
  g.box(23, 48, 7, 23, 51, 7, 0x5b8de0);
  g.set(23, 52, 7, 0x3a3a3a);
  g.box(22, 48, 6, 22, 52, 6, 0xd9473d);
  // eraser
  g.box(10, 40, 3, 13, 41, 6, 0xf2a0b0);
  // lamp, back left
  g.cyl('y', -24, -10, 4.5, 40, 40, 0x3a5a48);
  g.box(-25, 41, -11, -24, 52, -10, 0x40624f);
  g.box(-24, 52, -10, -16, 53, -9, 0x40624f);
  g.fill(roundBox(-20, -12, 47, 55, -14, -5, 2.5), -20, 47, -14, -12, 55, -5, (x, y) => (y <= 47 ? 0xfff2b0 : 0x3f7d5a), 0);
  g.set(-16, 47, -10, 0xfff2b0, GLOW);
  return g;
}

export function buildPaper(seed, { problem = true } = {}) {
  const g = new Vox();
  g.box(-7, 0, -9, 6, 0, 8, PAL.paper);
  if (problem) {
    // printed exercise at the top of the page (+z)
    for (let x = 5; x >= -5; x--) if (hash3(x, seed, 1) > 0.25) g.set(x, 0, 7, PAL.print);
    for (let x = 5; x >= -1; x--) if (hash3(x, seed, 2) > 0.3) g.set(x, 0, 5, PAL.print);
    g.set(6, 0, 7, 0x4a4f5c);
    g.set(6, 0, 5, 0x4a4f5c);
  }
  return g;
}

// Handwriting voxels on a sheet. Each mark gets a reveal key so lines appear
// as they are written. Rows run from the top of the page toward the writer.
export function addWriting(g, seed, rows, keyStart = 1, color = PAL.pencilMark, messy = false) {
  let k = keyStart;
  for (const [z, x0, x1] of rows) {
    for (let x = x0; x >= x1; x--) {
      const h = hash3(x, z, seed);
      if (h < (messy ? 0.15 : 0.32)) {
        k += 1;
        continue;
      }
      const dz = messy && hash3(x, z + 7, seed) > 0.6 ? (h > 0.8 ? 1 : -1) : 0;
      g.set(x, 0, z + dz, color, 0, k);
      k += 1;
    }
    k += 4;
  }
  return k;
}

export function buildPencil() {
  const g = new Vox();
  g.box(0, 0, 0, 0, 0, 1, 0xf09aa8);
  g.box(0, 0, 2, 0, 0, 2, 0xc9ccd4);
  g.box(0, 0, 3, 0, 0, 11, 0xf2c94c);
  g.box(0, 0, 12, 0, 0, 12, 0xe8c79a);
  g.box(0, 0, 13, 0, 0, 13, 0x3a3a3a);
  return g;
}

export function buildChair() {
  const g = new Vox();
  g.box(-11, 19, -10, 10, 21, 9, (x, y) => (y === 19 ? PAL.chairDk : PAL.chair));
  for (const [x, z] of [[-11, -10], [9, -10], [-11, 8], [9, 8]]) g.box(x, 0, z, x + 1, 18, z + 1, PAL.chairDk);
  g.box(-11, 22, -10, -10, 52, -9, PAL.chairDk);
  g.box(9, 22, -10, 10, 52, -9, PAL.chairDk);
  g.box(-9, 45, -10, 8, 51, -9, PAL.chair);
  g.box(-9, 34, -10, 8, 37, -9, PAL.chair);
  g.box(-11, 2, -9, 10, 3, -9, PAL.chairDk);
  return g;
}

export function buildRock() {
  const g = new Vox();
  const inside = roundBox(-14, 13, 0, 21, -13, 12, 4.5);
  for (let x = -14; x <= 13; x++)
    for (let y = 0; y <= 21; y++)
      for (let z = -13; z <= 12; z++) {
        if (!inside(x, y, z)) continue;
        const edge = x <= -12 || x >= 11 || z <= -11 || z >= 10 || y >= 19;
        if (edge && hash3(x, y, z) > 0.7 && y > 2) continue;
        let c = PAL.stone;
        const h = hash3(x * 3, y * 5, z * 7);
        if (h > 0.82) c = PAL.stoneDk;
        else if (h < 0.12) c = PAL.stoneLt;
        if ((x + 2 * y) % 13 === 0 && z > 4) c = PAL.stoneDk;
        if (y >= 18 && (x < -8 || z > 7) && hash3(x, y, z + 3) > 0.45) c = PAL.moss;
        g.set(x, y, z, c);
      }
  return g;
}

export function buildRubble() {
  const g = new Vox();
  const stones = [
    [-6, 3, -4, 6, 4, 5], [5, 2, 3, 5, 3, 4], [-2, 2, 7, 4, 3, 4], [8, 2, -7, 4, 3, 4],
    [-11, 1, 5, 3, 2, 3], [1, 5, -2, 4, 4, 4], [12, 1, 6, 3, 2, 2], [-13, 1, -8, 3, 2, 3],
  ];
  for (const [cx, cy, cz, rx, ry, rz] of stones)
    g.ell(cx, cy, cz, rx, ry, rz, (x, y, z) => {
      const h = hash3(x, y, z);
      if (y >= cy + ry - 1 && h > 0.5) return PAL.moss;
      return h > 0.8 ? PAL.stoneDk : h < 0.15 ? PAL.stoneLt : PAL.stone;
    });
  return g;
}

export function buildScorch() {
  const g = new Vox();
  for (let x = -24; x <= 24; x++)
    for (let z = -22; z <= 22; z++) {
      const r = Math.hypot(x, z * 1.1) + (hash3(x, 0, z) - 0.5) * 7;
      if (r > 21) continue;
      g.set(x, 0, z, r < 13 ? 0x2d2a2a : 0x4a4442);
    }
  return g;
}

export function buildBin() {
  const g = new Vox();
  g.cyl('y', 0, 0, 7.2, 0, 15, (x, y, z) => {
    if (y >= 14) return PAL.binDk;
    return (Math.round(Math.atan2(z, x) * 4) % 2 === 0 ? PAL.bin : PAL.binDk);
  });
  g.carve((x, y, z) => y >= 2 && x * x + z * z < 5.5 * 5.5);
  g.cyl('y', 0, 0, 5.4, 1, 1, 0x5b636d);
  g.ell(-1, 14, 1, 3, 2.6, 3, 0xf3f1ea);
  g.ell(2, 13, -2, 2.6, 2.4, 2.6, 0xe6e3d8);
  return g;
}

export function buildPaperBall() {
  const g = new Vox();
  g.ell(0, 0, 0, 2.7, 2.5, 2.7, (x, y, z) => (hash3(x, y, z) > 0.55 ? 0xdedbd1 : 0xf6f3ea));
  return g;
}

export function buildPuff() {
  const g = new Vox();
  g.ell(0, 0, 0, 4.6, 4.2, 4.6, 0xffffff);
  return g;
}

export function buildChunk() {
  const g = new Vox();
  g.box(-1, -1, -1, 1, 1, 0, 0xffffff);
  g.set(0, 1, 1, 0xffffff);
  return g;
}

// ---------------------------------------------------------------- the gun

// Local frame: origin at the top of the pistol grip, +z toward the muzzle,
// +y up, +x is the holder's left. The gun is built as separate parts so it
// can fly together piece by piece in the student's hands.
export const GUN = {
  muzzle: [0, 5.5, 64], // front of the rotating barrels
  gripR: [0, -9, 2.5], // right hand on the pistol grip
  gripL: [13, 1, 14], // left hand on the side handle
  port: [-9, 8.5, 14], // ejection port, right side
  podL: [10, 20.5, 25.5], // front of the left missile pod
  podR: [-10, 20.5, 25.5],
  cm: [0, 4, 20], // rough center of mass
};

const GC = {
  gun: 0x4a5263,
  gunDk: 0x353b48,
  gunLt: 0x6d7689,
  poly: 0x2a2d34,
  black: 0x1f2126,
  accent: 0xff3b30,
};

export function buildGun() {
  // receiver, pistol grip, trigger and a side handle for the second hand
  const core = new Vox();
  core.fill(roundBox(-7, 6, -3, 13, -8, 32, 2), -7, -3, -8, 6, 13, 32, (x, y, z) => {
    if (y >= 12 && z % 4 === 0) return GC.gunDk;
    if (y <= -2) return GC.gunDk;
    if (z === 0 || z === 22) return GC.gunDk;
    return GC.gun;
  });
  core.box(-2, 14, -6, 1, 14, 30, (x, y, z) => (z % 3 === 0 ? GC.black : GC.gunDk));
  for (let z = -5; z <= 30; z++) {
    core.set(-8, 5, z, GC.accent, GLOW);
    core.set(7, 5, z, GC.accent, GLOW);
  }
  core.box(-8, 7, 9, -8, 10, 18, GC.black);
  core.box(-8, 8, 10, -8, 9, 17, 0xb08a3a);
  for (let y = -17; y <= -3; y++) {
    const off = Math.round((y + 3) * 0.35);
    core.box(-3, y, -1 + off, 2, y, 5 + off, (x, yy, z) => ((z + yy + x) % 3 === 0 ? 0x5e3a20 : PAL.wood));
  }
  core.box(-1, -9, 5, 0, -9, 10, GC.gunDk);
  core.box(-1, -8, 10, 0, -3, 10, GC.gunDk);
  core.box(-1, -7, 7, 0, -4, 7, GC.black);
  core.box(7, 4, 12, 12, 6, 15, GC.poly);
  core.box(11, -4, 12, 14, 4, 15, (x, y) => (y % 3 === 0 ? GC.black : GC.poly));
  // a sticker, for personality
  core.box(7, 8, 0, 7, 12, 5, 0xff7eb6);
  core.set(7, 11, 1, GC.black);
  core.set(7, 11, 4, GC.black);
  core.box(7, 9, 1, 7, 9, 4, GC.black);

  // skeleton stock
  const stock = new Vox();
  stock.box(-5, -3, -22, 4, 9, -9, (x, y, z) => (z <= -21 ? GC.black : GC.poly));
  stock.carve((x, y, z) => y >= 1 && y <= 5 && z >= -19 && z <= -13);
  stock.box(-4, -7, -20, 3, -4, -14, GC.poly);
  stock.box(-5, 9, -16, 4, 10, -10, GC.black);

  // drum magazine with hazard stripes
  const drum = new Vox();
  drum.cyl('x', -12, 21.5, 9.5, -6, 5, (x, y, z) => {
    if (x === -6 || x === 5) {
      const r = Math.hypot(y + 12, z - 21.5);
      if (r < 2.6) return GC.gunLt;
      const a = Math.atan2(y + 12, z - 21.5);
      return Math.floor((a / Math.PI) * 6 + 12) % 2 === 0 ? PAL.hazard : GC.black;
    }
    return GC.gunDk;
  });
  drum.box(-3, -3, 17, 2, -2, 26, GC.gunDk);

  // barrel shroud with vents and hinge blocks for the knives
  const shroud = new Vox();
  shroud.cyl('z', -0.5, 5, 7.5, 32, 46, (x, y, z) => {
    const a = Math.atan2(y - 5, x + 0.5);
    if (z % 4 === 2 && z > 33 && z < 45 && Math.floor((a / Math.PI) * 5 + 10) % 2 === 0) return GC.black;
    return z <= 33 || z >= 45 ? GC.gunDk : GC.gun;
  });
  shroud.box(-4, 13, 34, 3, 13, 44, GC.gunLt);
  shroud.box(7, 3, 36, 9, 7, 39, GC.gunDk);
  shroud.box(-10, 3, 36, -8, 7, 39, GC.gunDk);

  // six rotating barrels, pivot on the shroud axis at its front
  const barrels = new Vox();
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    barrels.cyl('z', Math.cos(a) * 4.2, Math.sin(a) * 4.2, 1.7, 0, 17, (x, y, z) => (z >= 17 ? GC.black : GC.gunDk));
  }
  barrels.cyl('z', 0, 0, 7, 6, 7, GC.gun);
  barrels.cyl('z', 0, 0, 7.3, 13, 14, GC.gunDk);
  barrels.cyl('z', 0, 0, 1.5, 0, 15, GC.gunLt);

  // red-eyed scope on the top rail
  const scope = new Vox();
  scope.box(-2, 15, 8, 1, 16, 9, GC.gunDk);
  scope.box(-2, 15, 19, 1, 16, 20, GC.gunDk);
  scope.cyl('z', -0.5, 19.5, 3.3, 4, 24, (x, y, z) => (z >= 22 || z <= 5 ? GC.gunDk : GC.poly));
  scope.cyl('z', -0.5, 19.5, 2.4, 25, 25, 0xff4a3d, GLOW);

  // missile pods (four tubes each) and their flip-up front covers
  const pod = (sign) => {
    const g = new Vox();
    const x0 = sign > 0 ? 0 : -11, x1 = x0 + 11;
    g.fill(roundBox(x0, x1, 0, 12, -10, 14, 1.2), x0, 0, -10, x1, 12, 14, (x, y, z) => {
      if (z >= 2 && z <= 4) return (x + y + z) % 4 < 2 ? PAL.hazard : GC.black;
      if (y === 6 && z % 4 === 0) return PAL.oliveDk;
      return PAL.olive;
    });
    const cx = sign > 0 ? [3, 8] : [-8, -3];
    for (const tx of cx)
      for (const ty of [3, 9]) {
        g.box(tx - 1, ty - 1, 14, tx + 1, ty + 1, 14, GC.black);
        g.set(tx, ty, 14, PAL.red);
      }
    g.box(sign > 0 ? 2 : -3, -2, -6, sign > 0 ? 3 : -2, -1, 6, GC.gunDk);
    g.set(sign > 0 ? x1 : x0, 10, 9, 0x7dff8a, GLOW);
    g.set(sign > 0 ? x1 : x0, 10, 7, GC.accent, GLOW);
    return g;
  };
  const cover = (sign) => {
    const g = new Vox();
    const x0 = sign > 0 ? 0 : -11, x1 = x0 + 11;
    g.box(x0, -13, 0, x1, -1, 0, (x, y) => (y === -7 || y === -2 ? PAL.oliveDk : PAL.olive));
    return g;
  };

  // chef's knives on hinges either side of the shroud
  const knife = () => {
    const g = new Vox();
    g.box(0, -1, -12, 1, 1, -2, (x, y, z) => (y === 0 && (z === -10 || z === -6) ? GC.gunLt : GC.black));
    g.box(-1, -2, -1, 2, 2, 0, GC.gunLt);
    for (let z = 1; z <= 28; z++) {
      const t = z / 28;
      const top = Math.round(2 - t * t * 4.5);
      const bot = Math.round(-5 + t * 4.4 + Math.max(0, t - 0.65) * 7);
      if (bot > top) continue;
      g.box(0, bot, z, 1, top, z, (x, y) => (y === bot ? PAL.bladeDk : y === top ? 0xb9c2cc : PAL.blade));
    }
    return g;
  };

  // a meat cleaver taped under the barrels
  const cleaver = new Vox();
  cleaver.box(-1, 0, -10, 0, 2, 0, PAL.wood);
  for (const z of [-8, -3]) cleaver.box(-2, -1, z, 1, 3, z + 1, PAL.tape);
  cleaver.box(-1, -13, 1, 0, 2, 22, (x, y) => (y === -13 ? PAL.bladeDk : y === 2 ? 0x8f98a3 : PAL.blade));
  cleaver.carve((x, y, z) => y >= -2 && y <= 0 && z >= 3 && z <= 5);

  // muzzle flash star
  const flash = new Vox();
  const star = [
    [0, 0, 0, 5], [0, 0, 6, 3], [0, 0, 11, 2], [5, 0, 3, 2], [-5, 0, 3, 2], [0, 5, 3, 2], [0, -5, 3, 2],
    [4, 4, 5, 1.5], [-4, 4, 5, 1.5], [4, -4, 5, 1.5], [-4, -4, 5, 1.5],
  ];
  for (const [x, y, z, r] of star) flash.ell(x, y, z, r, r, r * 1.2, (xx, yy, zz) => (Math.hypot(xx, yy, zz - 2) < 3 ? 0xffffff : 0xffd34d));

  return {
    core, stock, drum, shroud, barrels, scope, cleaver, flash,
    podL: pod(1), podR: pod(-1), coverL: cover(1), coverR: cover(-1), knifeL: knife(), knifeR: knife(),
  };
}

export function buildMissile() {
  const g = new Vox();
  g.cyl('z', 0, 0, 2.2, 0, 13, (x, y, z) => (z === 4 || z === 9 ? PAL.red : PAL.white));
  g.cyl('z', 0, 0, 1.6, 14, 15, PAL.red);
  g.cyl('z', 0, 0, 1.0, 16, 17, PAL.red);
  for (const [x, y] of [[3, 0], [-3, 0], [0, 3], [0, -3]]) g.box(x, y, 0, x, y, 3, 0x8b8f99);
  return g;
}

export function buildFlame() {
  const g = new Vox();
  g.ell(0, 0, -3, 1.8, 1.8, 3.6, (x, y, z) => (z > -3 ? 0xffffff : z > -5 ? 0xffd34d : 0xff8a3d));
  return g;
}

// ---------------------------------------------------------------- the wearable

// Built in the head frame of the student so it sits right when worn.
export function buildDevice() {
  const g = new Vox();
  const inCap = roundBox(-11, 10, 14, 25, -10, 9, 4);
  const outer = roundBox(-12, 11, 17, 21, -11, 10, 4.5);
  for (let x = -12; x <= 11; x++)
    for (let z = -11; z <= 10; z++)
      for (let y = 18; y <= 19; y++) {
        if (!outer(x, y, z) || inCap(x, y, z)) continue;
        const front = z >= 8 && x >= -8 && x <= 7;
        g.set(x, y, z, front && y === 18 ? PAL.led : PAL.band, front && y === 18 ? GLOW : 0);
      }
  // camera module on the forehead
  g.fill(roundBox(-4, 3, 17, 23, 9, 14, 1), -4, 17, 9, 3, 23, 14, PAL.module);
  g.cyl('z', -0.5, 20, 2.2, 15, 15, 0x0b0d10);
  g.set(-1, 21, 15, 0x9ff6ff);
  g.box(-3, 24, 10, 2, 24, 13, PAL.led, GLOW);
  // battery pod on the left side
  g.fill(roundBox(11, 14, 14, 21, -5, 2, 1), 11, 14, -5, 14, 21, 2, PAL.module);
  g.set(14, 19, 1, 0x7dff8a, GLOW);
  g.set(14, 19, -1, PAL.led, GLOW);
  return g;
}

export function buildFlag() {
  const g = new Vox();
  g.box(0, 0, 0, 0, 30, 0, PAL.wood);
  g.set(0, 31, 0, PAL.knob);
  // a white flag with a grey hem so it still reads against the white page
  for (let x = 1; x <= 13; x++) {
    const dz = Math.round(Math.sin(x * 0.8) * 1.2);
    for (let y = 19; y <= 29; y++) {
      const hem = x === 13 || y === 19 || y === 29;
      g.set(x, y, dz, hem ? 0xaeb3bd : 0xf6f5f1);
    }
  }
  return g;
}
