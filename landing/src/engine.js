// Rendering core: an orthographic isometric camera, a renderer that draws at
// "art" resolution (one canvas pixel = one pixel-art pixel), and a material
// that turns lighting into a few hand-picked tones with ordered dithering.
import * as THREE from 'three';

// Colors are authored as plain sRGB hex values and should come out unchanged.
THREE.ColorManagement.enabled = false;

export const PX = Math.SQRT1_2; // world units per art pixel on the camera plane
export const YAW = Math.PI / 4; // classic isometric rotation
export const PITCH = Math.PI / 6; // 30 degrees down gives clean 2:1 pixel lines

// Uniforms shared by every material in the scene.
export const shared = {
  uDissolve: { value: 0 }, // 0 = scene visible, 1 = dissolved to white
  uFade: { value: new THREE.Vector4(4, -4, 96, 114) }, // island center xz, inner and outer fade radius
  uFadeNoise: { value: 26 },
  uRug: { value: new THREE.Vector4(-8, 8, 54, 44) }, // rug center xz and radii
  uImpact: { value: 0 }, // 1 = one-bit "impact frame": ink silhouettes on white
  uFlashAll: { value: 0 }, // extra light on everything, for big explosions
};

const COMMON = /* glsl */ `
float pixBayer(vec2 p) {
  int x = int(mod(p.x, 4.0));
  int y = int(mod(p.y, 4.0));
  float m[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
  return (m[x + y * 4] + 0.5) / 16.0;
}
float pixHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float pixNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(pixHash(i), pixHash(i + vec2(1.0, 0.0)), u.x),
             mix(pixHash(i + vec2(0.0, 1.0)), pixHash(i + vec2(1.0, 1.0)), u.x), u.y);
}
`;

const VERT_PARS = /* glsl */ `
#include <common>
attribute float aOcc;
attribute float aKind;
attribute float aReveal;
varying float vOcc;
varying float vKind;
varying float vReveal;
varying float vLocalY;
varying vec3 vPixWorld;
`;

const VERT_BEGIN = /* glsl */ `
#include <begin_vertex>
vOcc = aOcc;
vKind = aKind;
vReveal = aReveal;
vLocalY = position.y;
`;

const VERT_PROJECT = /* glsl */ `
#include <project_vertex>
{
  vec4 pw = vec4(transformed, 1.0);
  #ifdef USE_INSTANCING
  pw = instanceMatrix * pw;
  #endif
  vPixWorld = (modelMatrix * pw).xyz;
}
`;

const FRAG_PARS = /* glsl */ `
#include <common>
uniform float uDissolve;
uniform vec4 uFade;
uniform float uFadeNoise;
uniform vec4 uRug;
uniform float uImpact;
uniform float uFlashAll;
uniform float uReveal;
uniform float uFlush;
uniform float uFlushLevel;
uniform vec3 uFlushColor;
uniform float uGlow;
uniform float uAlpha;
uniform float uOccStr;
uniform float uDither;
uniform vec4 uTint;
uniform float uBright;
varying float vOcc;
varying float vKind;
varying float vReveal;
varying float vLocalY;
varying vec3 vPixWorld;
${COMMON}

// Five tones per base color. Shadows lean cool, highlights lean warm.
vec3 pixRamp(vec3 c, float lv) {
  if (lv < 0.5) return c * vec3(0.29, 0.30, 0.40) + vec3(0.012, 0.012, 0.03);
  if (lv < 1.5) return c * vec3(0.59, 0.59, 0.69);
  if (lv < 2.5) return c * vec3(0.83, 0.82, 0.87);
  if (lv < 3.5) return c;
  return mix(c, vec3(1.0, 0.98, 0.9), 0.35);
}

#ifdef PIX_FLOOR
vec3 floorColor(vec2 p) {
  float pw = 11.0;
  float row = floor(p.y / pw);
  float wy = p.y - row * pw;
  float plen = 54.0;
  float off = pixHash(vec2(row, 7.0)) * plen;
  float seg = floor((p.x + off) / plen);
  float wx = (p.x + off) - seg * plen;
  float h = pixHash(vec2(row * 1.7, seg * 3.1));
  vec3 c = mix(vec3(0.70, 0.49, 0.31), vec3(0.80, 0.585, 0.375), h);
  float g = pixNoise(vec2(p.x * 0.06 + h * 13.0, p.y * 0.5));
  if (g > 0.68) c *= 0.92;
  else if (g < 0.2) c *= 1.05;
  if (wy < 2.0) c = vec3(0.47, 0.30, 0.19);
  else if (wx < 1.0) c = vec3(0.52, 0.34, 0.21);
  vec2 q = (p - uRug.xy) / uRug.zw;
  float d = length(q);
  if (d < 1.0) {
    vec3 rc = vec3(0.25, 0.37, 0.57);
    if (d > 0.88) rc = vec3(0.58, 0.23, 0.22);
    else if (d > 0.83) rc = vec3(0.86, 0.67, 0.31);
    else if (d > 0.79) rc = vec3(0.58, 0.23, 0.22);
    else {
      vec2 m = abs(fract(p * 0.085) - 0.5);
      if (abs(m.x + m.y - 0.3) < 0.06) rc = vec3(0.33, 0.48, 0.69);
      if (d < 0.16) rc = vec3(0.86, 0.67, 0.31);
      else if (d < 0.22) rc = vec3(0.58, 0.23, 0.22);
    }
    c = rc;
  }
  return c;
}
#endif
`;

const FRAG_MAIN = /* glsl */ `
#include <opaque_fragment>
{
  float bay = pixBayer(gl_FragCoord.xy);
  #ifndef PIX_NOFADE
  {
    vec2 dxz = vPixWorld.xz - uFade.xy;
    float ang = atan(dxz.y, dxz.x);
    // a blobby, uneven shoreline like a vignette painted by hand
    float rr = length(dxz)
      + (pixNoise(vPixWorld.xz * 0.022 + 3.7) - 0.5) * uFadeNoise
      + (pixNoise(vPixWorld.xz * 0.09) - 0.5) * 7.0
      + sin(ang * 3.0 + 1.3) * 4.0 + sin(ang * 5.0 + 0.4) * 2.5;
    float fa = 1.0 - smoothstep(uFade.z, uFade.w, rr);
    if (fa < bay) discard;
  }
  #endif
  if (uDissolve > bay) discard;
  if (uAlpha < bay) discard;
  if (vReveal > uReveal) discard;

  vec3 base = diffuseColor.rgb;
  #ifdef PIX_FLOOR
  base = floorColor(vPixWorld.xz);
  #endif
  if (vKind > 0.5 && vKind < 1.5) {
    // anger rises from the chin like a thermometer, with a dithered edge
    float edge = clamp((uFlushLevel - vLocalY) / 5.0 + 0.5, 0.0, 1.0);
    base = mix(base, uFlushColor, uFlush * step(bay, edge) * 0.85);
  }
  base = mix(base, uTint.rgb, uTint.a);

  #ifdef PIX_UNLIT
  vec3 col = base;
  if (uImpact > 0.5) col = vec3(1.0);
  #else
  float lumD = max(dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114)), 1e-4);
  float lit = dot(outgoingLight, vec3(0.299, 0.587, 0.114)) / lumD;
  lit *= 1.0 - vOcc * uOccStr;
  lit += uBright + uFlashAll;
  float lv = clamp(floor(lit * 4.0 + (bay - 0.5) * uDither), 0.0, 4.0);
  vec3 col = pixRamp(base, lv);
  if (vKind > 1.5 && vKind < 2.5) col = mix(pixRamp(base * 0.42, lv), base, uGlow);
  if (uImpact > 0.5) col = dot(col, vec3(0.299, 0.587, 0.114)) > 0.42 ? vec3(1.0) : vec3(0.07, 0.065, 0.09);
  #endif
  gl_FragColor = vec4(col, 1.0);
}
`;

// A Lambert material whose output is replaced by the pixel-art ramp above.
export function pixelMat({
  color = 0xffffff,
  vertexColors = true,
  unlit = false,
  floor = false,
  fade = true,
  occ = 0.6,
  dither = 1.0,
  flushColor = 0xd8463c,
  side = THREE.FrontSide,
} = {}) {
  const mat = new THREE.MeshLambertMaterial({ color, vertexColors, side });
  const u = {
    uReveal: { value: 1e6 },
    uFlush: { value: 0 },
    uFlushLevel: { value: -1000 },
    uFlushColor: { value: new THREE.Color(flushColor) },
    uGlow: { value: 0 },
    uAlpha: { value: 1 },
    uOccStr: { value: occ },
    uDither: { value: dither },
    uTint: { value: new THREE.Vector4(0, 0, 0, 0) },
    uBright: { value: 0 },
  };
  const defs = {};
  if (unlit) defs.PIX_UNLIT = '';
  if (floor) defs.PIX_FLOOR = '';
  if (!fade) defs.PIX_NOFADE = '';
  mat.defines = defs;
  mat.userData.u = u;
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, shared, u);
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', VERT_PARS)
      .replace('#include <begin_vertex>', VERT_BEGIN)
      .replace('#include <project_vertex>', VERT_PROJECT);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', FRAG_PARS)
      .replace('#include <opaque_fragment>', FRAG_MAIN);
  };
  mat.customProgramCacheKey = () => 'pix:' + Object.keys(defs).join(',');
  return mat;
}

// Geometries that are not voxel meshes still need the extra attributes.
export function withPixAttrs(geo) {
  const n = geo.attributes.position.count;
  for (const name of ['aOcc', 'aKind', 'aReveal']) {
    if (!geo.attributes[name]) geo.setAttribute(name, new THREE.Float32BufferAttribute(new Float32Array(n), 1));
  }
  if (!geo.attributes.color) {
    geo.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(n * 3).fill(1), 3));
  }
  return geo;
}

export function createRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: false,
    alpha: false,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(1);
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.BasicShadowMap;
  renderer.setClearColor(0xffffff, 1);
  return renderer;
}

export function createCamera() {
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, -1200, 2400);
  const d = 700;
  cam.position.set(
    d * Math.cos(PITCH) * Math.sin(YAW),
    d * Math.sin(PITCH),
    d * Math.cos(PITCH) * Math.cos(YAW),
  );
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld();
  return cam;
}

// Place the world origin at a whole pixel so the art never shifts by half a pixel.
export function setFrustum(cam, W, H, offX = 0, offY = 0) {
  const ox = Math.floor(W / 2) + offX;
  const oy = Math.floor(H / 2) + offY;
  cam.left = -ox * PX;
  cam.right = (W - ox) * PX;
  cam.top = oy * PX;
  cam.bottom = -(H - oy) * PX;
  cam.updateProjectionMatrix();
}

// Light chosen so that top faces land on the base tone, faces toward the
// viewer's left one tone darker, and faces toward the right two tones darker.
export function createLights(scene) {
  const AMB = 0.375;
  const DIR = 0.571;
  const ambient = new THREE.AmbientLight(0xffffff, AMB * Math.PI);
  scene.add(ambient);
  const sun = new THREE.DirectionalLight(0xffffff, DIR * Math.PI);
  const L = new THREE.Vector3(-0.2, 0.876, 0.438).normalize();
  sun.position.copy(L).multiplyScalar(400);
  sun.target.position.set(0, 0, 0);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const s = sun.shadow.camera;
  s.left = -190;
  s.right = 190;
  s.top = 190;
  s.bottom = -190;
  s.near = 1;
  s.far = 900;
  sun.shadow.bias = -0.0006;
  sun.shadow.normalBias = 0.35;
  scene.add(sun, sun.target);
  return { ambient, sun };
}

const _v = new THREE.Vector3();
export function project(cam, W, H, p, out = { x: 0, y: 0 }) {
  _v.copy(p).project(cam);
  out.x = ((_v.x + 1) / 2) * W;
  out.y = ((1 - _v.y) / 2) * H;
  return out;
}
