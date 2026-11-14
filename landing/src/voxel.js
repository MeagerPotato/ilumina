// A tiny voxel modeling kit. Models are filled procedurally and turned into
// meshes with hidden faces removed and per-corner ambient occlusion baked in.
import * as THREE from 'three';

const key = (x, y, z) => (x + 512) | ((y + 512) << 10) | ((z + 512) << 20);

// Each face: outward normal n, in-plane axes u and v with u x v = n,
// and the offset of the face's first corner from the voxel's min corner.
const FACES = [
  { n: [1, 0, 0], u: [0, 1, 0], v: [0, 0, 1], o: [1, 0, 0] },
  { n: [-1, 0, 0], u: [0, 0, 1], v: [0, 1, 0], o: [0, 0, 0] },
  { n: [0, 1, 0], u: [0, 0, 1], v: [1, 0, 0], o: [0, 1, 0] },
  { n: [0, -1, 0], u: [1, 0, 0], v: [0, 0, 1], o: [0, 0, 0] },
  { n: [0, 0, 1], u: [1, 0, 0], v: [0, 1, 0], o: [0, 0, 1] },
  { n: [0, 0, -1], u: [0, 1, 0], v: [1, 0, 0], o: [0, 0, 0] },
];
const CORNERS = [
  [0, 0],
  [1, 0],
  [1, 1],
  [0, 1],
];

// Deterministic random numbers so every load looks the same.
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hash3(x, y, z) {
  let h = Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(z | 0, 2147483647);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

// Inside test for a box with rounded edges (inclusive integer bounds).
export function roundBox(x0, x1, y0, y1, z0, z1, r) {
  const ax = x0 + r, bx = x1 - r, ay = y0 + r, by = y1 - r, az = z0 + r, bz = z1 - r;
  return (x, y, z) => {
    if (x < x0 || x > x1 || y < y0 || y > y1 || z < z0 || z > z1) return false;
    const dx = Math.max(ax - x, 0, x - bx);
    const dy = Math.max(ay - y, 0, y - by);
    const dz = Math.max(az - z, 0, z - bz);
    return dx * dx + dy * dy + dz * dz <= r * r + 0.5;
  };
}

export class Vox {
  constructor() {
    this.m = new Map();
  }
  set(x, y, z, c, k = 0, r = 0) {
    if (c === null || c === undefined || c === false) return this;
    this.m.set(key(x, y, z), [x, y, z, c, k, r]);
    return this;
  }
  get(x, y, z) {
    return this.m.get(key(x, y, z));
  }
  has(x, y, z) {
    return this.m.has(key(x, y, z));
  }
  del(x, y, z) {
    this.m.delete(key(x, y, z));
    return this;
  }
  box(x0, y0, z0, x1, y1, z1, c, k = 0, r = 0) {
    const fx = Math.min(x0, x1), tx = Math.max(x0, x1);
    const fy = Math.min(y0, y1), ty = Math.max(y0, y1);
    const fz = Math.min(z0, z1), tz = Math.max(z0, z1);
    for (let x = fx; x <= tx; x++)
      for (let y = fy; y <= ty; y++)
        for (let z = fz; z <= tz; z++) this.set(x, y, z, typeof c === 'function' ? c(x, y, z) : c, k, r);
    return this;
  }
  fill(test, bx0, by0, bz0, bx1, by1, bz1, c, k = 0, r = 0) {
    for (let x = bx0; x <= bx1; x++)
      for (let y = by0; y <= by1; y++)
        for (let z = bz0; z <= bz1; z++)
          if (test(x, y, z)) this.set(x, y, z, typeof c === 'function' ? c(x, y, z) : c, k, r);
    return this;
  }
  ell(cx, cy, cz, rx, ry, rz, c, k = 0, r = 0) {
    for (let x = Math.floor(cx - rx); x <= Math.ceil(cx + rx); x++)
      for (let y = Math.floor(cy - ry); y <= Math.ceil(cy + ry); y++)
        for (let z = Math.floor(cz - rz); z <= Math.ceil(cz + rz); z++) {
          const d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 + ((z - cz) / rz) ** 2;
          if (d <= 1) this.set(x, y, z, typeof c === 'function' ? c(x, y, z) : c, k, r);
        }
    return this;
  }
  // Cylinder along an axis: 'x', 'y' or 'z'. (a, b) is the center in the other two axes.
  cyl(axis, a, b, rad, from, to, c, k = 0, r = 0) {
    const R = Math.ceil(rad);
    for (let s = from; s <= to; s++)
      for (let i = Math.floor(a - R); i <= Math.ceil(a + R); i++)
        for (let j = Math.floor(b - R); j <= Math.ceil(b + R); j++) {
          if ((i - a) ** 2 + (j - b) ** 2 > rad * rad) continue;
          const col = typeof c === 'function' ? null : c;
          if (axis === 'x') this.set(s, i, j, col ?? c(s, i, j), k, r);
          else if (axis === 'y') this.set(i, s, j, col ?? c(i, s, j), k, r);
          else this.set(i, j, s, col ?? c(i, j, s), k, r);
        }
    return this;
  }
  carve(fn) {
    for (const [k, v] of this.m) if (fn(v[0], v[1], v[2], v)) this.m.delete(k);
    return this;
  }
  paint(fn) {
    for (const v of this.m.values()) {
      const c = fn(v[0], v[1], v[2], v[3], v);
      if (c !== undefined && c !== null) v[3] = c;
    }
    return this;
  }
  get size() {
    return this.m.size;
  }

  // Build a BufferGeometry. (px, py, pz) is the pivot, in voxel coordinates.
  geometry(px = 0, py = 0, pz = 0) {
    const pos = [], nor = [], col = [], occ = [], kind = [], rev = [], idx = [];
    const solid = (x, y, z) => this.m.has(key(x, y, z));
    let vi = 0;
    const ao = [0, 0, 0, 0];
    for (const v of this.m.values()) {
      const [x, y, z, c, k, r] = v;
      const cr = ((c >> 16) & 255) / 255, cg = ((c >> 8) & 255) / 255, cb = (c & 255) / 255;
      for (const f of FACES) {
        const nx = x + f.n[0], ny = y + f.n[1], nz = z + f.n[2];
        if (solid(nx, ny, nz)) continue;
        for (let ci = 0; ci < 4; ci++) {
          const [a, b] = CORNERS[ci];
          pos.push(
            x + f.o[0] + f.u[0] * a + f.v[0] * b - px,
            y + f.o[1] + f.u[1] * a + f.v[1] * b - py,
            z + f.o[2] + f.u[2] * a + f.v[2] * b - pz,
          );
          nor.push(f.n[0], f.n[1], f.n[2]);
          col.push(cr, cg, cb);
          const su = a ? 1 : -1, sv = b ? 1 : -1;
          const s1 = solid(nx + f.u[0] * su, ny + f.u[1] * su, nz + f.u[2] * su);
          const s2 = solid(nx + f.v[0] * sv, ny + f.v[1] * sv, nz + f.v[2] * sv);
          const s3 = solid(nx + f.u[0] * su + f.v[0] * sv, ny + f.u[1] * su + f.v[1] * sv, nz + f.u[2] * su + f.v[2] * sv);
          const o = s1 && s2 ? 3 : s1 + s2 + s3;
          ao[ci] = o;
          occ.push(o / 3);
          kind.push(k);
          rev.push(r);
        }
        if (ao[0] + ao[2] > ao[1] + ao[3]) idx.push(vi + 1, vi + 2, vi + 3, vi + 1, vi + 3, vi);
        else idx.push(vi, vi + 1, vi + 2, vi, vi + 2, vi + 3);
        vi += 4;
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.setAttribute('aOcc', new THREE.Float32BufferAttribute(occ, 1));
    g.setAttribute('aKind', new THREE.Float32BufferAttribute(kind, 1));
    g.setAttribute('aReveal', new THREE.Float32BufferAttribute(rev, 1));
    g.setIndex(vi > 65535 ? new THREE.Uint32BufferAttribute(idx, 1) : new THREE.Uint16BufferAttribute(idx, 1));
    g.computeBoundingSphere();
    return g;
  }

  mesh(material, px = 0, py = 0, pz = 0, { cast = true, receive = true } = {}) {
    const m = new THREE.Mesh(this.geometry(px, py, pz), material);
    m.castShadow = cast;
    m.receiveShadow = receive;
    return m;
  }
}
