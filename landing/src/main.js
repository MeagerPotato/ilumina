import { createRenderer, configureRenderer, createCamera, setFrustum, shared } from './engine.js';
import { buildStage } from './scene.js';
import { Overlay } from './overlay.js';
import { Story, DURATION } from './story.js';

const glCanvas = document.getElementById('scene');
const ovCanvas = document.getElementById('overlay');
const params = new URLSearchParams(location.search);

// The essential part of the scene, in art pixels. The canvas covers the whole
// window; the scale is a whole number of device pixels per art pixel, so the
// pixels stay perfectly square, chosen so the scene fills about 70% of what
// would fit and has white space around it.
const NEED_W = 316;
const NEED_H = 256;
const NARROW_W = 230;
const FILL = 0.7;
const FILL_PORTRAIT = 0.85;
// where the world origin sits relative to the canvas center, so the island
// and the space above it for heads and speech bubbles are centered together
const ORIGIN_X = -8;
const ORIGIN_Y = 36;

// Device pixels per art pixel for the current window. `limitW` and `limitH`
// are art sizes that must still fit whole (the still image is wider than the
// part of the live scene that has to fit).
function pixelScale(limitW = 0, limitH = 0) {
  const dpr = Math.min(window.devicePixelRatio || 1, 4);
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const dw = Math.max(1, Math.round(vw * dpr));
  const dh = Math.max(1, Math.round(vh * dpr));
  const portrait = vw < vh;
  const needW = Math.max(portrait ? NARROW_W : NEED_W, limitW);
  const needH = Math.max(NEED_H, limitH);
  const fit = Math.min(dw / needW, dh / needH);
  const want = Math.round(Math.min(dw / (portrait ? NARROW_W : NEED_W), dh / NEED_H) * (portrait ? FILL_PORTRAIT : FILL));
  const k = Math.max(1, Math.min(Math.floor(fit), want));
  return { dpr, dw, dh, k };
}

function computeLayout() {
  const { dpr, dw, dh, k } = pixelScale();
  const W = Math.ceil(dw / k);
  const H = Math.ceil(dh / k);
  const cssPerArt = k / dpr;
  return { dpr, k, W, H, cssW: (W * k) / dpr, cssH: (H * k) / dpr, fontScale: cssPerArt < 1.5 ? 2 : 1 };
}

// Without WebGL (graphics acceleration turned off, or the GPU process gave
// up) three.js can't draw anything, so show one frame of the skit instead,
// at the same crisp whole-number pixel scale, with a short note.
const STILL = { src: '/still.png', w: 405, h: 212 };
let still = null;

function placeStill() {
  if (!still || still.el.hidden) return;
  const { dpr, dw, dh, k } = pixelScale(STILL.w, STILL.h + 24);
  const w = STILL.w * k;
  const h = STILL.h * k;
  const left = Math.floor((dw - w) / 2);
  const top = Math.max(0, Math.floor((dh - h) / 2) - Math.round(12 * dpr));
  Object.assign(still.img.style, {
    width: w / dpr + 'px',
    height: h / dpr + 'px',
    left: left / dpr + 'px',
    top: top / dpr + 'px',
  });
  still.note.style.top = (top + h) / dpr + 12 + 'px';
}

function showStill() {
  glCanvas.style.display = 'none';
  ovCanvas.style.display = 'none';
  document.body.style.cursor = '';
  if (!still) {
    const el = document.createElement('figure');
    el.className = 'still';
    const img = document.createElement('img');
    img.src = STILL.src;
    img.width = STILL.w;
    img.height = STILL.h;
    img.alt =
      'Pixel-art scene: a student at a desk fires an absurdly large cartoon gun while a philosopher runs off shouting, "I think, therefore I run!"';
    const note = document.createElement('figcaption');
    note.textContent = 'This scene is animated. Turn on graphics acceleration in your browser to watch it play.';
    el.append(img, note);
    document.body.append(el);
    still = { el, img, note };
    window.addEventListener('resize', placeStill);
  }
  still.el.hidden = false;
  placeStill();
}

function hideStill() {
  if (still) still.el.hidden = true;
  glCanvas.style.display = '';
  ovCanvas.style.display = '';
}

function start(renderer) {
  const camera = createCamera();
  const stage = buildStage();
  const overlay = new Overlay(ovCanvas);
  const story = new Story(stage, camera, overlay);
  story.reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let layout = null;

  function applyLayout() {
    layout = computeLayout();
    const { W, H, cssW, cssH } = layout;
    renderer.setSize(W, H, false);
    for (const c of [glCanvas, ovCanvas]) {
      c.style.width = cssW + 'px';
      c.style.height = cssH + 'px';
      c.style.left = Math.floor((window.innerWidth - cssW) / 2) + 'px';
      c.style.top = Math.floor((window.innerHeight - cssH) / 2) + 'px';
    }
    overlay.resize(W, H, layout.fontScale);
    story.resize(W, H);
    dirty = true;
  }

  let dirty = true;
  let clock = 0;
  let last = performance.now();
  let lastFrame = -1;
  const speed = parseFloat(params.get('speed') || '1');
  let frozen = params.has('t') ? parseFloat(params.get('t')) : null;
  let shownT = 0; // the moment on screen, which clicks act on

  function renderAt(t) {
    shownT = t;
    const shake = story.update(t);
    setFrustum(camera, layout.W, layout.H, ORIGIN_X + shake.x, ORIGIN_Y + shake.y);
    story.drawOverlay(t, shake);
    renderer.render(stage.scene, camera);
    document.body.style.cursor = story.hasLine(t) ? 'pointer' : '';
  }

  function tick(now) {
    requestAnimationFrame(tick);
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (frozen === null) clock = (clock + dt * speed) % DURATION;
    const t = frozen === null ? clock : frozen;
    const frame = Math.floor(t * 30);
    if (frame === lastFrame && !dirty) return;
    lastFrame = frame;
    dirty = false;
    renderAt(frame / 30);
  }

  // Dialogue works like a game: click, tap, Space or Enter finishes the line
  // being typed, and the next press skips to the end of it.
  function advance() {
    const to = story.advance(shownT);
    if (to === null) return;
    dirty = true;
    if (to === shownT) return; // finished the typing, or dismissed a line
    if (frozen === null) clock = to % DURATION;
    else frozen = to;
  }
  window.addEventListener('pointerdown', (e) => {
    if (e.button === 0) advance();
  });
  window.addEventListener('keydown', (e) => {
    if (e.repeat || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      advance();
    }
  });

  window.addEventListener('resize', applyLayout);
  applyLayout();
  requestAnimationFrame(tick);

  // Hooks for automated frame checks.
  window.__scene = {
    setTime(t) {
      frozen = t;
      renderAt(Math.floor(t * 30) / 30);
    },
    play() {
      if (frozen !== null) clock = frozen;
      frozen = null;
    },
    duration: DURATION,
    shared,
    stage,
    story,
    camera,
    renderer,
  };

  // If the GPU drops out while the page is open, show the still until the
  // browser hands the context back (three.js rebuilds its state on restore).
  glCanvas.addEventListener('webglcontextlost', showStill);
  glCanvas.addEventListener('webglcontextrestored', () => {
    configureRenderer(renderer);
    hideStill();
    applyLayout();
  });
}

let renderer = null;
if (!params.has('still')) {
  try {
    renderer = createRenderer(glCanvas);
  } catch (err) {
    console.warn('WebGL is unavailable, so a still image is shown instead.', err);
  }
}
if (renderer) start(renderer);
else showStill();
