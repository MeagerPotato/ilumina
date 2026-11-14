// Two-bone inverse kinematics for arms and legs.
import * as THREE from 'three';

const _S = new THREE.Vector3();
const _d = new THREE.Vector3();
const _p = new THREE.Vector3();
const _E = new THREE.Vector3();
const _T = new THREE.Vector3();
const _u = new THREE.Vector3();
const _v = new THREE.Vector3();
const _w = new THREE.Vector3();
const _h = new THREE.Vector3();
const _h0 = new THREE.Vector3();
const _m1 = new THREE.Matrix4();
const _m2 = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _pq = new THREE.Quaternion();

// j1 is the root joint (shoulder or hip), j2 the middle joint (elbow or knee),
// a and b the two bone lengths. restU is the bone direction in the rest pose,
// restV the direction the second bone swings toward when the joint bends.
// The middle joint is a hinge around its local x axis.
export function twoBone(j1, j2, a, b, target, pole, restU, restV, hingeSign) {
  j1.parent.updateWorldMatrix(true, false);
  _S.copy(j1.position).applyMatrix4(j1.parent.matrixWorld);
  _d.subVectors(target, _S);
  let dist = _d.length();
  dist = Math.min(Math.max(dist, Math.abs(a - b) + 0.05), a + b - 0.05);
  if (_d.lengthSq() < 1e-8) _d.set(0, -1, 0);
  _d.normalize();

  _p.subVectors(pole, _S);
  _p.addScaledVector(_d, -_p.dot(_d));
  if (_p.lengthSq() < 1e-8) {
    _p.set(0, 0, 1).addScaledVector(_d, -_d.z);
    if (_p.lengthSq() < 1e-8) _p.set(1, 0, 0);
  }
  _p.normalize();

  const cosA = THREE.MathUtils.clamp((a * a + dist * dist - b * b) / (2 * a * dist), -1, 1);
  const sinA = Math.sqrt(1 - cosA * cosA);
  _E.copy(_S).addScaledVector(_d, a * cosA).addScaledVector(_p, a * sinA);
  _T.copy(_S).addScaledVector(_d, dist);

  _u.subVectors(_E, _S).normalize();
  _w.subVectors(_T, _E).normalize();
  _v.copy(_w).addScaledVector(_u, -_w.dot(_u));
  if (_v.lengthSq() < 1e-8) _v.copy(_p).addScaledVector(_u, -_p.dot(_u));
  _v.normalize();

  _h.crossVectors(_u, _v);
  _h0.crossVectors(restU, restV);
  _m1.makeBasis(_u, _v, _h);
  _m2.makeBasis(restU, restV, _h0).transpose();
  _m1.multiply(_m2);
  _q.setFromRotationMatrix(_m1);
  j1.parent.getWorldQuaternion(_pq);
  j1.quaternion.copy(_pq.invert().multiply(_q));

  const theta = Math.acos(THREE.MathUtils.clamp(_u.dot(_w), -1, 1));
  j2.rotation.set(hingeSign * theta, 0, 0);
  j1.updateMatrixWorld(true);
}

export const ARM_U = new THREE.Vector3(0, -1, 0);
export const ARM_V = new THREE.Vector3(0, 0, 1);
export const LEG_U = new THREE.Vector3(0, -1, 0);
export const LEG_V = new THREE.Vector3(0, 0, -1);
