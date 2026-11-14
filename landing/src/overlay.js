// 2D layer drawn at the same pixel grid as the 3D scene: speech bubbles,
// cartoon symbols and sound-effect lettering.
import { glyph, textWidth, wrap, GLYPH_H, LINE_H } from './font.js';

export const STYLES = {
  student: { fill: '#ffffff', line: '#1f2230', text: '#1f2230', shadow: '#d3d9e6' },
  phil: { fill: '#f8efd8', line: '#6b5236', text: '#3b2d1e', shadow: '#e6d9b9' },
  tutor: { fill: '#eafffb', line: '#13867d', text: '#0c4e48', shadow: '#c3ece6', icon: true },
};

const SPRITES = {
  vein: {
    pal: { r: '#e2343e' },
    rows: ['.rr...rr.', 'r..r.r..r', 'r.......r', '.r.....r.', '.........', '.r.....r.', 'r.......r', 'r..r.r..r', '.rr...rr.'],
  },
  sweat: {
    pal: { b: '#59b4ff', w: '#e6f6ff', k: '#2d6fae' },
    rows: ['..k..', '.kbk.', '.kbk.', 'kbwbk', 'kbbbk', 'kbbbk', '.kkk.'],
  },
  bang: {
    pal: { y: '#ffd23f', k: '#1f2230' },
    rows: ['.kkk.', 'kyyyk', 'kyyyk', 'kyyyk', 'kyyyk', '.kyk.', '.kyk.', '..k..', '.....', '.kkk.', 'kyyyk', '.kkk.'],
  },
  bulb: {
    pal: { y: '#ffe066', w: '#ffffff', g: '#9aa3ad', G: '#6f7883', k: '#1f2230' },
    rows: [
      '...kkkkk...', '..kyyyyyk..', '.kyywwyyyk.', 'kyyywyyyyyk', 'kyyyyyyyyyk', 'kyyyyyyyyyk', '.kyyyyyyyk.',
      '..kyyyyyk..', '...kyyyk...', '...kgggk...', '...kGGGk...', '...kgggk...', '....kkk....',
    ],
  },
  sparkle: {
    pal: { y: '#ffd84d', w: '#ffffff', o: '#fff3b0' },
    rows: ['..o..', '..y..', 'oywyo', '..y..', '..o..'],
  },
  sparkleS: { pal: { y: '#ffd84d', w: '#ffffff' }, rows: ['.y.', 'yww', '.y.'] },
  glint: {
    pal: { w: '#ffffff', b: '#9fd8ff' },
    rows: ['...w...', '...w...', '..bwb..', 'wwwwwww', '..bwb..', '...w...', '...w...'],
  },
  check: {
    pal: { g: '#2fae5b', k: '#14552c' },
    rows: ['.......kk', '......kgk', 'kk...kgk.', 'kgk.kgk..', '.kgkgk...', '..kgk....', '...k.....'],
  },
  burst: {
    pal: { y: '#ffe14d', w: '#ffffff', k: '#1f2230' },
    rows: [
      '.....k.....', '....kyk..k.', '.k..kyk.kyk', 'kyk.kykkyk.', '.kykkwwyk..', '..kywwwyk..', '.kkywwyykk.',
      'kyyyyyyyyyk', '.kkyywkykk.', '..kyk.kyk..', '..kk...kk..',
    ],
  },
  question: {
    pal: { k: '#1f2230', w: '#ffffff', q: '#4b7bd2' },
    rows: [
      '..kkkkkkk..', '.kwwwwwwwk.', 'kwwqqqqwwwk', 'kwqwwwwqwwk', 'kwwwwwwqwwk', 'kwwwwwqwwwk', 'kwwwwqwwwwk',
      'kwwwwwwwwwk', 'kwwwwqwwwwk', '.kwwwwwwwk.', '..kkkkkkk..', '...kk......', '..k........',
    ],
  },
};

const hash = (a, b, c) => {
  const h = Math.sin(a * 127.1 + b * 311.7 + c * 74.7) * 43758.5453;
  return h - Math.floor(h);
};

export class Overlay {
  constructor(canvas) {
    this.c = canvas;
    this.g = canvas.getContext('2d');
    this.W = 0;
    this.H = 0;
    this.s = 1;
  }

  resize(W, H, scale) {
    this.c.width = W;
    this.c.height = H;
    this.W = W;
    this.H = H;
    this.s = scale;
    this.g.imageSmoothingEnabled = false;
  }

  clear() {
    this.g.clearRect(0, 0, this.W, this.H);
  }

  rect(x, y, w, h, col) {
    this.g.fillStyle = col;
    this.g.fillRect(Math.round(x), Math.round(y), w, h);
  }

  text(str, x, y, col, limit = Infinity, s = this.s) {
    const g = this.g;
    g.fillStyle = col;
    let cx = Math.round(x);
    let n = 0;
    for (const ch of str) {
      if (n >= limit) break;
      const gl = glyph(ch);
      for (let r = 0; r < GLYPH_H; r++)
        for (let c = 0; c < gl[r].length; c++) if (gl[r][c] === '#') g.fillRect(cx + c * s, Math.round(y) + r * s, s, s);
      cx += (gl[0].length + 1) * s;
      n++;
    }
  }

  // Sound-effect lettering with a dark outline.
  sfx(str, cx, cy, fill = '#ffd23f', outline = '#1f2230', s = this.s) {
    const w = textWidth(str) * s;
    // kept on the canvas: a sound effect cut off at the edge reads as a glitch
    const x = Math.max(2 * s, Math.min(this.W - w - 3 * s, Math.round(cx - w / 2)));
    const y = Math.round(cy - (GLYPH_H * s) / 2);
    for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, 1], [-1, 1], [1, -1], [2, 2], [1, 2], [2, 1]])
      this.text(str, x + dx * s, y + dy * s, outline, Infinity, s);
    this.text(str, x, y, fill, Infinity, s);
  }

  sprite(name, cx, cy, s = this.s) {
    const sp = SPRITES[name];
    const h = sp.rows.length;
    const w = sp.rows[0].length;
    const x0 = Math.round(cx - (w * s) / 2);
    const y0 = Math.round(cy - (h * s) / 2);
    for (let r = 0; r < h; r++)
      for (let c = 0; c < w; c++) {
        const ch = sp.rows[r][c];
        const col = sp.pal[ch];
        if (!col) continue;
        this.g.fillStyle = col;
        this.g.fillRect(x0 + c * s, y0 + r * s, s, s);
      }
    return { w: w * s, h: h * s };
  }

  // Dithered ring, used for the wearable lighting up and for shockwaves on the
  // floor (a circle on the floor is twice as wide as it is tall on screen).
  ring(cx, cy, r, col, density = 1, ratio = 0.62) {
    const g = this.g;
    g.fillStyle = col;
    const steps = Math.max(24, Math.round(r * 7));
    const bayer = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
    for (let i = 0; i < steps; i++) {
      const a = (i / steps) * Math.PI * 2;
      const x = Math.round(cx + Math.cos(a) * r);
      const y = Math.round(cy + Math.sin(a) * r * ratio);
      const th = (bayer[(x & 3) + (y & 3) * 4] + 0.5) / 16;
      if (th > density) continue;
      g.fillRect(x, y, this.s, this.s);
    }
  }

  // Manga focus lines: streaks running in from the edges of the canvas toward
  // (fx, fy). `skip(x, y)` keeps them off whatever should stay clear.
  focusLines(fx, fy, seed, { n = 56, col = '#d6dae3', reach = [0.35, 0.65], thick = 1, skip = null } = {}) {
    const g = this.g;
    const W = this.W, H = this.H;
    g.fillStyle = col;
    for (let i = 0; i < n; i++) {
      const a = ((i + hash(i, seed, 1) * 0.9) / n) * Math.PI * 2;
      const ca = Math.cos(a), sa = Math.sin(a);
      // distance from the focus to the canvas edge along this ray
      const tx = ca > 0 ? (W - fx) / ca : ca < 0 ? -fx / ca : Infinity;
      const ty = sa > 0 ? (H - fy) / sa : sa < 0 ? -fy / sa : Infinity;
      const edge = Math.min(tx, ty);
      if (!(edge > 0)) continue;
      const r0 = edge * (1 - (reach[0] + hash(i, seed, 2) * (reach[1] - reach[0])));
      for (let r = edge; r >= r0; r -= 1) {
        const x = Math.round(fx + ca * r), y = Math.round(fy + sa * r);
        if (skip && skip(x, y)) continue;
        const w = r > r0 + (edge - r0) * 0.55 ? thick + 1 : thick;
        g.fillRect(x, y, w, w);
      }
    }
  }

  // Lock-on brackets around (cx, cy), `size` art pixels from the center.
  reticle(cx, cy, size, col = '#ff3b30', ink = '#1f2230') {
    const g = this.g;
    const s = this.s;
    const arm = Math.max(3 * s, Math.round(size * 0.5));
    const bars = [];
    for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      const x = Math.round(cx + sx * size), y = Math.round(cy + sy * size);
      bars.push([sx < 0 ? x : x - arm + s, y, arm, s]);
      bars.push([x, sy < 0 ? y : y - arm + s, s, arm]);
    }
    bars.push([Math.round(cx) - s, Math.round(cy), 3 * s, s], [Math.round(cx), Math.round(cy) - s, s, 3 * s]);
    g.fillStyle = ink;
    for (const [x, y, w, h] of bars) g.fillRect(x - 1, y - 1, w + 2, h + 2);
    g.fillStyle = col;
    for (const [x, y, w, h] of bars) g.fillRect(x, y, w, h);
  }

  // Speech bubble pointing at (ax, ay). `shown` is how many characters are typed so far.
  bubble({ text, ax, ay, style = 'student', shown = Infinity, lean = 0, maxW = 112, next = false }) {
    const st = STYLES[style];
    const s = this.s;
    // never wider than the canvas, even with doubled lettering on a phone
    maxW = Math.min(maxW, Math.floor(this.W / s) - 34);
    const lines = wrap(text, maxW);
    const tw = Math.max(...lines.map(textWidth));
    const padX = 6, padY = 5;
    const iconW = st.icon ? 11 : 0;
    const bw = (tw + padX * 2 + iconW) * s;
    const bh = (lines.length * LINE_H - (LINE_H - GLYPH_H) + padY * 2) * s;
    const gap = 9 * s;
    let bx = Math.round(ax - bw / 2 + lean * bw);
    bx = Math.max(3 * s, Math.min(this.W - bw - 3 * s, bx));
    let by = Math.round(ay - gap - bh);
    by = Math.max(3 * s, by);
    const g = this.g;

    // shadow, outline and fill with clipped corners
    const shape = (x, y, w, h, col) => {
      g.fillStyle = col;
      g.fillRect(x + s, y, w - 2 * s, h);
      g.fillRect(x, y + s, w, h - 2 * s);
    };
    shape(bx + s, by + s, bw, bh, st.shadow);
    shape(bx, by, bw, bh, st.line);
    shape(bx + s, by + s, bw - 2 * s, bh - 2 * s, st.fill);

    // tail
    const tailH = Math.min(gap - s, 7 * s);
    const tx0 = Math.max(bx + 5 * s, Math.min(bx + bw - 6 * s, Math.round(ax + (bx + bw / 2 - ax) * 0.25)));
    const steps = Math.round(tailH / s);
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const cx = Math.round((tx0 + (ax - tx0) * t) / s) * s;
      const half = Math.max(0, Math.round((1 - t) * 3)) * s;
      const y = by + bh - s + i * s;
      g.fillStyle = st.line;
      g.fillRect(cx - half - s, y, half * 2 + 2 * s + s, s);
      if (half > 0 || i === 0) {
        g.fillStyle = st.fill;
        g.fillRect(cx - half, y, half * 2 + s, s);
      }
    }

    // tutor voice icon: speaker with waves
    let x0 = bx + padX * s + iconW * s;
    if (st.icon) {
      const ix = bx + padX * s;
      const iy = by + padY * s + s;
      g.fillStyle = st.line;
      const ico = ['..#....#.', '.##..#..#', '###.#.#.#', '###.#.#.#', '.##..#..#', '..#....#.'];
      for (let r = 0; r < ico.length; r++)
        for (let c = 0; c < ico[r].length; c++) if (ico[r][c] === '#') g.fillRect(ix + c * s, iy + r * s, s, s);
    }

    let left = shown;
    for (let i = 0; i < lines.length; i++) {
      if (left <= 0) break;
      const lw = textWidth(lines[i]) * s;
      const lx = st.icon ? x0 : Math.round(bx + (bw - lw) / 2);
      const ly = by + (padY + i * LINE_H) * s;
      this.text(lines[i], lx, ly, st.text, left);
      left -= lines[i].length + 1;
    }
    // the "click to continue" arrow in the bottom right corner
    if (next) {
      g.fillStyle = st.text;
      const nx = bx + bw - 10 * s, ny = by + bh - 4 * s;
      g.fillRect(nx, ny, 5 * s, s);
      g.fillRect(nx + s, ny + s, 3 * s, s);
      g.fillRect(nx + 2 * s, ny + 2 * s, s, s);
    }
    return { x: bx, y: by, w: bw, h: bh };
  }
}
