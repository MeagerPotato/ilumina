// Pooled effect meshes. Every effect is placed from scratch each frame from
// the story clock, so any moment of the loop can be rendered on its own.
import * as THREE from 'three';
import { pixelMat, withPixAttrs } from './engine.js';
import { buildPuff, buildChunk } from './models.js';

class Pool {
  constructor(scene, n, make) {
    this.items = [];
    for (let i = 0; i < n; i++) {
      const m = make(i);
      m.visible = false;
      m.castShadow = false;
      m.receiveShadow = false;
      m.frustumCulled = false;
      scene.add(m);
      this.items.push(m);
    }
    this.n = 0;
  }
  next() {
    if (this.n >= this.items.length) return null;
    const m = this.items[this.n++];
    m.visible = true;
    return m;
  }
  end() {
    for (let i = this.n; i < this.items.length; i++) this.items[i].visible = false;
    this.n = 0;
  }
}

const _up = new THREE.Vector3(0, 1, 0);
const _dir = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _fwd = new THREE.Vector3(0, 0, 1);

export class FX {
  constructor(scene) {
    const puffGeo = buildPuff().geometry(0.5, 0.5, 0.5);
    const chunkGeo = buildChunk().geometry(0.5, 0.5, 0.5);
    this.smoke = new Pool(scene, 110, () => new THREE.Mesh(puffGeo, pixelMat({ vertexColors: false, color: 0xbdbdbd, occ: 0.35 })));
    this.fire = new Pool(scene, 60, () => new THREE.Mesh(puffGeo, pixelMat({ vertexColors: false, color: 0xffb03b, unlit: true })));
    this.chunks = new Pool(scene, 40, () => new THREE.Mesh(chunkGeo, pixelMat({ vertexColors: false, color: 0x8f9298 })));
    const bulletGeo = withPixAttrs(new THREE.BoxGeometry(1.4, 1.4, 11));
    const bulletMat = pixelMat({ vertexColors: false, color: 0xffe36b, unlit: true });
    this.bullets = new Pool(scene, 30, () => new THREE.Mesh(bulletGeo, bulletMat));
    const casingGeo = withPixAttrs(new THREE.BoxGeometry(1.2, 1.2, 2.6));
    const casingMat = pixelMat({ vertexColors: false, color: 0xe0ac3c });
    this.casings = new Pool(scene, 48, () => new THREE.Mesh(casingGeo, casingMat));
  }

  begin() {}

  puff(pos, radius, alpha, color, fire = false) {
    const m = (fire ? this.fire : this.smoke).next();
    if (!m) return;
    m.position.copy(pos);
    m.scale.setScalar(Math.max(0.05, radius / 4.6));
    m.rotation.set(0, (pos.x * 13.1 + pos.z * 7.3) % 6.28, 0);
    m.material.userData.u.uAlpha.value = alpha;
    m.material.color.setHex(color);
  }

  chunk(pos, size, color, rot = 0) {
    const m = this.chunks.next();
    if (!m) return;
    m.position.copy(pos);
    m.scale.setScalar(size);
    m.rotation.set(rot, rot * 1.3, rot * 0.7);
    m.material.color.setHex(color);
    m.material.userData.u.uAlpha.value = 1;
  }

  bullet(pos, dir) {
    const m = this.bullets.next();
    if (!m) return;
    m.position.copy(pos);
    _dir.copy(dir).normalize();
    _q.setFromUnitVectors(_fwd, _dir);
    m.quaternion.copy(_q);
  }

  casing(pos, rot) {
    const m = this.casings.next();
    if (!m) return;
    m.position.copy(pos);
    m.rotation.set(rot, rot * 0.6, rot * 1.7);
  }

  end() {
    this.smoke.end();
    this.fire.end();
    this.chunks.end();
    this.bullets.end();
    this.casings.end();
  }
}

// Ballistic flight with a couple of bounces on the floor (y = floorY).
export function ballistic(p0, v0, t, out, { g = -260, floorY = 0, rest = 0.38, fric = 0.55, bounces = 2 } = {}) {
  let px = p0.x, py = p0.y, pz = p0.z;
  let vx = v0.x, vy = v0.y, vz = v0.z;
  let tl = t;
  let landed = false;
  for (let b = 0; b <= bounces; b++) {
    // time until y hits floor: py + vy*s + g/2 s^2 = floorY
    const A = g / 2, B = vy, C = py - floorY;
    const disc = B * B - 4 * A * C;
    const s = disc < 0 ? Infinity : (-B - Math.sqrt(disc)) / (2 * A);
    if (tl <= s) {
      out.set(px + vx * tl, py + vy * tl + A * tl * tl, pz + vz * tl);
      return { landed, settled: false };
    }
    px += vx * s;
    pz += vz * s;
    py = floorY;
    vy = -(vy + g * s) * rest;
    vx *= fric;
    vz *= fric;
    tl -= s;
    landed = true;
  }
  out.set(px, floorY, pz);
  return { landed: true, settled: true };
}

export { _up };
