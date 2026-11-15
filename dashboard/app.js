// Ilumina dashboard. Everything drawn here comes from messages the bot sends.
// Nothing is simulated: with no messages, the page stays empty.
import { PipecatClient, SmallWebRTCTransport, WavMediaManager, WebSocketTransport } from "./vendor/pipecat.js";

// Two ways to reach the bot. Locally (uv run bot.py, page at /dashboard/) the browser
// talks to the bot over WebRTC. Hosted (page at /app/ behind the landing page) the bot
// runs in a Vercel Function and the browser reaches it over a WebSocket, voice only.
// That function has a time limit, so the bot says how long a session may last.
const HOSTED = location.pathname.startsWith("/app");
let sessionTimer, timeUp = false;
function startSessionClock(seconds) {
  clearInterval(sessionTimer);
  if (!seconds) return;
  const ends = Date.now() + seconds * 1000;
  sessionTimer = setInterval(() => {
    const left = Math.round((ends - Date.now()) / 1000);
    if (left <= 0) { clearInterval(sessionTimer); timeUp = true; client?.disconnect(); return; }
    if (left <= 60) $("status").textContent = `Session ends in ${left}s`;
  }, 1000);
}

const DIMS = ["confusion", "frustration", "confidence", "engagement"];
const STATUS_TEXT = { steady: "steady", blip: "blip, ignored", trend: "changed" };
const MOVE_TEXT = {
  continue: "Keep going",
  smaller_hint: "Smaller hint",
  new_explanation: "Explain it differently",
  worked_example: "Worked example",
  harder_problem: "Raise the difficulty",
  check_in: "Check in",
};
// Short names for the timeline, where a column is narrow.
const MOVE_SHORT = {
  continue: "Go on", smaller_hint: "Hint", new_explanation: "Re-explain",
  worked_example: "Example", harder_problem: "Harder", check_in: "Check in",
};
// The overall learning state, when the bot sends one. Fixed colours: the three that match a
// reading share its colour, bored is amber, and neutral is grey on purpose.
const STATES = ["engaged", "frustrated", "confused", "bored", "neutral"];
const STATE_COLOR = { engaged: "var(--engagement)", frustrated: "var(--frustration)", confused: "var(--confusion)", bored: "var(--bored)", neutral: "var(--neutral)" };
const stateColor = (st) => STATE_COLOR[st] ?? "var(--muted)";
const history = []; // one snapshot per scored turn
// Teaching moves, each with how many readings the dashboard had when the move arrived.
// The bot sends each reading here as it gives it to the tutor, and the move comes back
// with the reply, so this is the newest reading the tutor could have used.
const moves = [];

const $ = (id) => document.getElementById(id);
const clamp = (v) => Math.max(0, Math.min(1, v));
const pct = (v) => `${clamp(v) * 100}%`;
const color = (dim) => `var(--${dim})`;
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const dimsOf = (snapshot) => [...DIMS, ...Object.keys(snapshot.dimensions).filter((d) => !DIMS.includes(d))]
  .filter((d) => snapshot.dimensions[d]);
const colorOf = (dim) => (DIMS.includes(dim) ? color(dim) : "var(--muted)");

// ---- Motion. Every animation here follows a real message; none of it makes data up. ----
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
// Restart a one-shot CSS animation on an element.
function replay(el, cls) {
  if (!el) return;
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
}
// Count a number from what it showed to its new value.
function tween(el, to, digits = 0) {
  const from = el.dataset.v == null ? to : Number(el.dataset.v);
  el.dataset.v = to;
  const token = (el._t = (el._t ?? 0) + 1);
  if (REDUCED || from === to) { el.textContent = to.toFixed(digits); return; }
  const t0 = performance.now(), dur = 750;
  const step = (t) => {
    if (el._t !== token) return;
    const k = Math.min(1, (t - t0) / dur), e = 1 - (1 - k) ** 3;
    el.textContent = (from + (to - from) * e).toFixed(digits);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
// A square travels along the arrow between two cards when data moves along it.
const flow = (id) => replay($(id), "go");
const freshen = (id) => replay($(id), "fresh");
// The page's ambient colour follows the live reading.
const setMood = (c) => document.documentElement.style.setProperty("--mood", c);

const RING = 2 * Math.PI * 50; // the live ring's circumference, r = 50

// The live headline: the overall state this turn alone sounded like, and how sure the
// model was of it. The tracker's smoothed state is shown underneath as the trend.
// A turn with no overall answer keeps the last one, marked as from that turn.
let lastLive;
function renderLive(snapshot) {
  const ls = snapshot.learning_state;
  if (ls?.reading) lastLive = { ...ls, turn: snapshot.turn };
  $("live").hidden = !lastLive;
  if (!lastLive) return;
  const fresh = lastLive.turn === snapshot.turn;
  const st = lastLive.reading, sure = clamp(lastLive.reading_confidence ?? 0);
  $("live").classList.toggle("stale", !fresh);
  const word = $("live-word");
  if (word.textContent !== st) { word.textContent = st; replay(word, "swap"); }
  $("live-turn").textContent = fresh ? `Live · turn ${lastLive.turn}` : `Turn ${lastLive.turn} · no overall read on turn ${snapshot.turn}`;
  $("live-arc").style.strokeDashoffset = String(RING * (1 - sure));
  tween($("live-pct"), Math.round(sure * 100));
  $("live-trend").innerHTML = lastLive.state
    ? `Trend <b style="--c:${stateColor(lastLive.state)}">${esc(lastLive.state)}</b> · ${lastLive.turns === 1 ? "new" : `${lastLive.turns} turns`}`
    : "";
  if (fresh) setMood(stateColor(st));
  $("live").setAttribute("aria-label", `This turn sounded ${st}, ${Math.round(sure * 100)}% sure. Trend ${lastLive.state ?? "unknown"}.`);
}

// How this turn differs from the student's own usual, and how much it counted.
function renderUsual(snapshot) {
  const chips = Object.entries(snapshot.vs_usual ?? {}).map(([what, how]) => `<span>${esc(what)} <b>${esc(how)}</b></span>`);
  if (snapshot.weight != null && snapshot.weight < 1) chips.push(`<span class="soft">short turn, counted ${snapshot.weight === 0.5 ? "half" : `×${snapshot.weight}`}</span>`);
  $("usual").hidden = !chips.length;
  $("usual-chips").innerHTML = chips.join("");
  const v = snapshot.voice;
  $("pitch").hidden = !(v && v.pitch_hz);
  if (v?.pitch_hz) $("pitch").textContent = `pitch ${v.pitch_hz} Hz` + (v.loudness != null ? ` · ${v.loudness} dBFS` : "");
}

// One row per reading. The bar is this turn's reading; the thin mark is the trend
// (the tracker's smoothed estimate). Rows are kept, so bars glide to new values.
function dimRow(dim) {
  let row = $("dims").querySelector(`[data-dim="${dim}"]`);
  if (row) return row;
  $("dims-empty")?.remove();
  row = document.createElement("div");
  row.className = "dim";
  row.dataset.dim = dim;
  row.style.setProperty("--c", colorOf(dim));
  row.innerHTML = `<div class="name"><i></i>${esc(dim)}</div>
    <div class="track" role="img"><span class="fill"></span><span class="trend"></span></div>
    <div class="level"><span class="delta"></span><b></b><small></small></div>`;
  $("dims").append(row);
  return row;
}

function renderNow(snapshot) {
  $("key").hidden = $("scale").hidden = false;
  renderLive(snapshot);
  renderUsual(snapshot);
  const before = history.at(-2);
  for (const dim of dimsOf(snapshot)) {
    const d = snapshot.dimensions[dim], row = dimRow(dim);
    row.querySelector(".fill").style.width = pct(d.reading);
    row.querySelector(".trend").style.left = pct(d.estimate);
    const level = row.querySelector(".level b");
    if (level.textContent !== d.seen) { level.textContent = d.seen; replay(level, "swap"); }
    row.querySelector(".level small").textContent = `${Math.round(d.confidence * 100)}%`;
    // Up or down from the last turn's reading, when the change is clear.
    const prev = before?.dimensions[dim]?.reading, change = prev == null ? 0 : d.reading - prev;
    const delta = row.querySelector(".delta");
    delta.textContent = change >= 0.1 ? "▲" : change <= -0.1 ? "▼" : "";
    delta.title = prev == null ? "" : `${change >= 0 ? "up" : "down"} ${Math.abs(change).toFixed(2)} from last turn`;
    if (delta.textContent) replay(delta, "swap");
    row.querySelector(".track").setAttribute("aria-label",
      `${dim}: this turn ${d.seen} (${d.reading}), ${Math.round(d.confidence * 100)}% sure. Trend ${d.level} (${d.estimate}).`);
    row.title = `${dim}: this turn ${d.reading}, ${Math.round(d.confidence * 100)}% sure. Trend ${d.level}, ${STATUS_TEXT[d.status] ?? d.status}.`;
  }
}

// Deepgram's word timings for the turn, as measured. Anything not measured shows a dash.
function setStat(key, value, digits, label) {
  const dd = $(`ev-${key}`), num = dd.querySelector("span");
  $(`ev-${key}-l`).textContent = label;
  dd.classList.toggle("none", value == null);
  if (value == null) { num.textContent = "–"; delete num.dataset.v; return; }
  tween(num, value, digits);
}

function renderEvidence(e) {
  const tooFew = e.words != null && e.words_per_minute == null;
  if (tooFew) setStat("wpm", e.words, 0, e.words === 1 ? "word, too few for a pace" : "words, too few for a pace");
  else setStat("wpm", e.words_per_minute, 0, "words a minute");
  setStat("pause", e.longest_pause, 1, "longest pause");
  setStat("fillers", e.fillers, 0, e.fillers === 1 ? "um or uh" : "ums and uhs");
  setStat("wait", e.waited, 1, "wait before answering");
  $("spoke").hidden = e.words == null;
  if (e.words != null) $("spoke").textContent = `${e.words} ${e.words === 1 ? "word" : "words"} in ${e.seconds.toFixed(1)} s`
    + (e.hedges ? ` · ${e.hedges} ${e.hedges === 1 ? "hedge" : "hedges"}` : "");
  if (e.words != null) freshen("heard");
}

// The student's microphone, drawn live in the browser from the same track the bot hears.
// Only shown while a session's microphone track is available.
let wave;
function startWave(track) {
  if (!track || wave?.track === track || REDUCED) return;
  stopWave();
  try {
    const ctx = new AudioContext();
    ctx.resume?.();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(new MediaStream([track])).connect(analyser);
    const buf = new Float32Array(analyser.fftSize), bars = new Array(56).fill(0);
    const cv = $("wave"), g = cv.getContext("2d");
    let last = 0;
    const me = { track, ctx };
    const draw = (t) => {
      if (wave !== me) return;
      if (track.readyState === "ended") return stopWave();
      if (t - last > 60) {
        last = t;
        analyser.getFloatTimeDomainData(buf);
        const rms = Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length);
        bars.push(track.enabled ? clamp((20 * Math.log10(rms || 1e-6) + 60) / 50) : 0);
        bars.shift();
      }
      const dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
      if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const bw = w / bars.length, block = 3;
      bars.forEach((v, i) => {
        const n = Math.max(1, Math.round((v * h) / (block + 1)));
        g.fillStyle = i > bars.length - 4 ? "#13867d" : `rgba(19,134,125,${0.25 + 0.6 * (i / bars.length)})`;
        for (let k = 0; k < n; k++) g.fillRect(i * bw, h - (k + 1) * (block + 1), Math.max(1, bw - 2), block);
      });
      me.raf = requestAnimationFrame(draw);
    };
    wave = me;
    $("wave-box").hidden = false;
    me.raf = requestAnimationFrame(draw);
  } catch (e) {
    console.error(e);
  }
}
function stopWave() {
  if (!wave) return;
  cancelAnimationFrame(wave.raf);
  wave.ctx.close?.().catch(() => {});
  wave = undefined;
  $("wave-box").hidden = true;
}

// Math: text between dollar signs is LaTeX, drawn by KaTeX. If KaTeX did not load,
// or cannot read it, the math is shown as it was written.
function tex(latex, display = false) {
  try {
    return window.katex.renderToString(latex, { displayMode: display, throwOnError: false });
  } catch {
    return esc(latex);
  }
}
const withMath = (text) => String(text).split(/(\$\$[^$]+\$\$|\$[^$\n]+\$)/).map((part, i) =>
  i % 2 ? tex(part.replace(/^\$+|\$+$/g, ""), part.startsWith("$$")) : esc(part)).join("");

function planHtml(markdown) {
  const inline = (t) => withMath(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  let html = "", inList = false;
  for (const raw of markdown.split("\n")) {
    const line = raw.trim();
    const item = line.match(/^(?:[-*]|\d+\.)\s+(.*)/);
    if (item) {
      html += `${inList ? "" : "<ul>"}<li>${inline(item[1])}</li>`;
      inList = true;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    const heading = line.match(/^#+\s+(.*)/);
    if (heading) html += `<h4>${inline(heading[1])}</h4>`;
    else if (line) html += `<p>${inline(line)}</p>`;
  }
  return html + (inList ? "</ul>" : "");
}

// Memory: the classes the tutor was told about, and the study plan, as the bot sent them.
// The text was written by a model from the student's own class, so it is escaped.
function renderMemory(m) {
  const classes = (m.lectures ?? []).map((c) => {
    const stuck = (c.sticking_points ?? []).length ? `<span>Sticking points: ${withMath(c.sticking_points.join("; "))}</span>` : "";
    return `<p class="class"><b>${withMath(c.title)}</b>
      <span>${withMath([c.subject, (c.concepts ?? []).join(", ")].filter(Boolean).join(": "))}</span>${stuck}</p>`;
  }).join("");
  const moments = m.hard_moments
    ? `<p class="class"><b>Earlier sessions</b><span>${Number(m.hard_moments)} ${m.hard_moments === 1 ? "moment" : "moments"} where the student sounded stuck</span></p>`
    : "";
  if (!classes && !moments && !m.plan) {
    $("memory").innerHTML = `<p class="empty">Nothing saved yet.</p>`;
    return;
  }
  $("memory").innerHTML = classes + moments
    + (m.plan ? `<h3>Study plan</h3><div class="plan" tabindex="0">${planHtml(m.plan)}</div>` : "");
}

// Over the session: one row per reading, plus rows for the overall state and the tutor's moves.
// The solid line joins each turn's reading; the faint dashed line is the trend.
// The newest column draws itself in.
let drawnTurns = 0, drawnMoves = 0;
function renderTrace() {
  const W = 1160, rowH = 56, padL = 104, padR = 12, top = 6, moveH = 34;
  const dims = [...new Set(history.flatMap(dimsOf))];
  const n = Math.max(history.length, 12);
  const colW = (W - padL - padR) / n;
  const x = (i) => padL + (i + 0.5) * colW;
  const hasState = history.some((s) => s.learning_state?.reading);
  const stateH = hasState ? 34 : 0;
  const rowsTop = top + stateH;
  const rowsBottom = rowsTop + dims.length * rowH;
  const H = rowsBottom + moveH + 18;
  const newest = history.length > drawnTurns ? history.length - 1 : -1;
  const isNew = (i) => (i === newest ? " new" : "");
  const cols = history.map((s, i) =>
    `<rect class="col" data-i="${i}" x="${padL + i * colW}" y="0" width="${colW}" height="${rowsBottom + moveH}"/>`).join("");
  const rows = dims.map((dim, r) => {
    const y0 = rowsTop + r * rowH, y = (v) => y0 + rowH - 8 - clamp(v) * (rowH - 16);
    const pts = history.map((s, i) => ({ i, d: s.dimensions[dim] })).filter((p) => p.d);
    const trend = pts.map((p) => `${x(p.i)},${y(p.d.estimate)}`).join(" ");
    const segs = pts.slice(1).map((p, k) => {
      const a = pts[k];
      return `<line class="seg${isNew(p.i)}" x1="${x(a.i)}" y1="${y(a.d.reading)}" x2="${x(p.i)}" y2="${y(p.d.reading)}" stroke="${colorOf(dim)}" pathLength="1"/>`;
    }).join("");
    const marks = pts.map((p) =>
      `<rect class="mark${isNew(p.i)}" x="${x(p.i) - 4.5}" y="${y(p.d.reading) - 4.5}" width="9" height="9" fill="${colorOf(dim)}"/>`).join("");
    return `<line x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)"/>
      <line x1="${padL}" x2="${W - padR}" y1="${y(0.65)}" y2="${y(0.65)}" stroke="var(--line)" stroke-dasharray="2 4"/>
      <rect x="0" y="${y0 + rowH / 2 - 9}" width="8" height="8" fill="${colorOf(dim)}"/>
      <text class="row" x="14" y="${y0 + rowH / 2}">${esc(dim)}</text>
      <polyline points="${trend}" fill="none" stroke="${colorOf(dim)}" stroke-width="1.5" stroke-dasharray="3 4" opacity=".45"/>${segs}${marks}`;
  }).join("");
  const pill = (cx, cy, w, fill, label, cls = "") => `<g class="pill${cls}" style="transform-origin:${cx}px ${cy + 9}px">
    <rect x="${cx - w / 2}" y="${cy}" width="${w}" height="18" rx="4" fill="${fill}"/>
    <text x="${cx}" y="${cy + 13}" text-anchor="middle" style="fill:#fff;font-size:11px;font-weight:600">${esc(label)}</text></g>`;
  const pillW = Math.min(colW - 6, 74);
  // A move belongs to the column of the newest reading the tutor could have had.
  const byCol = new Map();
  for (const m of moves) if (m.after > 0) byCol.set(m.after - 1, m.move);
  const newMoveCol = moves.length > drawnMoves ? moves.at(-1).after - 1 : -1;
  const moveRow = `<line x1="${padL}" x2="${W - padR}" y1="${rowsBottom + 4}" y2="${rowsBottom + 4}" stroke="var(--line)" stroke-width="1.5"/>
    <text class="row" x="0" y="${rowsBottom + 24}">Tutor</text>` +
    [...byCol].map(([i, move]) => {
      const label = MOVE_SHORT[move] ?? move;
      return pill(x(i), rowsBottom + 11, pillW, "var(--ink)", colW < 60 ? label.slice(0, 6) : label, i === newMoveCol ? " new" : "");
    }).join("");
  const stateRow = !hasState ? "" : `<text class="row" x="0" y="${top + 17}">Sounded</text>` +
    history.map((s, i) => s.learning_state?.reading
      ? pill(x(i), top + 4, pillW, stateColor(s.learning_state.reading), colW < 60 ? s.learning_state.reading.slice(0, 5) : s.learning_state.reading, isNew(i))
      : "").join("");
  const ticks = history.map((s, i) => `<text x="${x(i)}" y="${H - 2}" text-anchor="middle">${s.turn}</text>`).join("");
  const sweep = newest >= 0 ? `<rect class="sweep" x="${padL + newest * colW}" y="0" width="${colW}" height="${rowsBottom + moveH}"/>` : "";
  $("trace").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img"
    aria-label="Each turn's reading and the trend for each dimension, what the turn sounded like overall, and the tutor's move, by turn">${sweep}${cols}${stateRow}${rows}${moveRow}${ticks}</svg>`;
  $("trace").querySelectorAll(".col").forEach((col) => {
    col.addEventListener("mouseenter", () => showTip(col));
    col.addEventListener("mouseleave", () => { $("tip").hidden = true; col.classList.remove("on"); });
  });
  drawnTurns = history.length;
  drawnMoves = moves.length;
}

function showTip(col) {
  const i = Number(col.dataset.i), s = history[i];
  col.classList.add("on");
  const rows = dimsOf(s).map((dim) => {
    const d = s.dimensions[dim];
    return `<div><span>${esc(dim)}</span><span>${d.seen} <i>· trend ${d.level}</i></span></div>`;
  }).join("");
  const turnMoves = moves.filter((m) => m.after === i + 1).map((m) => MOVE_TEXT[m.move] ?? m.move);
  const tip = $("tip");
  const ls = s.learning_state;
  const stateLine = ls?.reading
    ? `<div><span>sounded</span><span>${esc(ls.reading)} ${Math.round((ls.reading_confidence ?? 0) * 100)}% <i>· trend ${esc(ls.state)}</i></span></div>`
    : "";
  tip.innerHTML = `<b>Turn ${s.turn}</b>${stateLine}${rows}${turnMoves.length ? `<div><span>tutor</span><span>${esc(turnMoves.join(", "))}</span></div>` : ""}`;
  tip.hidden = false;
  const box = $("trace").getBoundingClientRect(), r = col.getBoundingClientRect(), host = tip.parentElement.getBoundingClientRect();
  const left = r.right - host.left + 8;
  tip.style.left = `${left + tip.offsetWidth > host.width ? r.left - host.left - tip.offsetWidth - 8 : left}px`;
  tip.style.top = `${box.top - host.top + 8}px`;
}

function addLine(who, text) {
  $("lines-empty")?.remove();
  const li = document.createElement("li");
  if (who === "You") li.className = "me";
  const b = document.createElement("b");
  b.textContent = who;
  li.append(b, text);
  $("lines").append(li);
  $("lines").scrollTop = $("lines").scrollHeight;
}

function renderMic(level, cls) {
  // How loud the bot hears the microphone, from 60 dB below full scale up to full scale, in ten steps.
  const lit = Math.round(clamp(level) * 10);
  const cells = $("mic-level").children.length === 10 ? [...$("mic-level").children]
    : ($("mic-level").innerHTML = "<i></i>".repeat(10), [...$("mic-level").children]);
  cells.forEach((c, i) => { c.className = i < lit ? (cls ?? "") : ""; });
}
let micTimer;

// Where the conversation is, from the bot's own events, so the student never has to
// guess whether they were heard. Each stage is a name and what to do meanwhile.
const STAGES = {
  starting: ["Getting ready", "Ilumina is about to say hello."],
  listening: ["Your turn", "Ilumina is listening."],
  hearing: ["Hearing you", "Press Done talking to send it now."],
  thinking: ["Heard you", "Ilumina is thinking."],
  speaking: ["Ilumina is speaking", "Talk over it to interrupt."],
};
const NO_ANSWER_AFTER_MS = 12000;
let stageNow = null, heardText = "", userSpeaking = false;
let micPaused = false, turnEnded = false, micGraceUntil = 0, quietTimer, thinkTimer;

// `quiet` keeps a hint out of the screen reader's ear: the words heard so far change
// several times a second.
function setStage(stage, hint, quiet = false) {
  clearTimeout(quietTimer);
  clearTimeout(thinkTimer);
  stageNow = stage;
  $("stage").hidden = !stage;
  if (!stage) return;
  if (stage !== "hearing") heardText = "";
  const [name, usual] = STAGES[stage];
  $("stage").dataset.stage = stage;
  $("stage-name").textContent = name;
  $("stage-hint").textContent = hint ?? usual;
  $("done").setAttribute("aria-disabled", String(stage !== "hearing"));
  const say = quiet ? name : `${name}. ${hint ?? usual}`;
  if ($("stage-say").textContent !== say) $("stage-say").textContent = say;
  // A reply that never comes must not leave the student waiting on "Heard you".
  if (stage === "thinking") thinkTimer = setTimeout(noAnswer, NO_ANSWER_AFTER_MS);
}

// Pipecat's browser audio player files every chunk of the bot's voice under one track
// id, "default", and on an interruption it blocks that id for good. After the first
// time the student talked over Ilumina, every later reply was dropped: the bot said it
// was speaking and nothing played. Each stretch between interruptions gets its own id,
// so only the audio that was actually interrupted is dropped.
function keepBotAudioAfterInterruptions(transport) {
  const media = transport?._mediaManager;
  if (typeof media?.bufferBotAudio !== "function" || typeof media?.interruptBotAudio !== "function") {
    console.warn("Bot audio player not found; replies after an interruption may be silent.");
    return;
  }
  let stretch = 0;
  const buffer = media.bufferBotAudio.bind(media);
  const interrupt = media.interruptBotAudio.bind(media);
  media.bufferBotAudio = (audio) => buffer(audio, `bot-${stretch}`);
  media.interruptBotAudio = async () => {
    const result = await interrupt(); // blocks the current id, so late chunks of it drop
    stretch += 1;
    return result;
  };
}

function noAnswer() {
  const caught = !micPaused || turnEnded; // did the bot get the end of the turn?
  resumeMic();
  setStage("listening", caught
    ? "No answer came. You can speak again."
    : "Ilumina did not catch the end of that. Your microphone is back on, so say it again.");
}

// The words Flux has so far for this turn. Seeing them is the proof of being heard.
function hearing(text) {
  if (micPaused) return; // the turn was already sent with Done talking
  userSpeaking = true;
  const words = text?.trim() || (stageNow === "hearing" ? heardText : "");
  // Flux repeats the same words while it holds a turn open. Only new words count.
  if (stageNow === "hearing" && words === heardText) return;
  heardText = words;
  setStage("hearing", words ? `Heard so far: "${words.length > 70 ? "…" + words.slice(-70) : words}"` : undefined, Boolean(words));
  // In a loud room Flux can wait a long time to be sure the turn is over. Say so.
  quietTimer = setTimeout(() => {
    setStage("hearing", "No new words. Waiting to be sure you have finished, or press Done talking.");
  }, 2500);
}

function setMic(on) {
  const track = client?.tracks()?.local?.audio;
  if (track) track.enabled = on; // a switched-off track sends silence, so the bot still gets audio
}

// A silent microphone is the clearest end of a turn there is, even in a loud room.
function doneTalking() {
  if (micPaused || stageNow !== "hearing") return;
  micPaused = true;
  turnEnded = false;
  setMic(false);
  setStage("thinking", "Sent. Your microphone is paused until Ilumina answers.");
}

function resumeMic() {
  userSpeaking = false;
  if (!micPaused) return;
  micPaused = false;
  micGraceUntil = Date.now() + 1500; // the next level report still covers the pause
  setMic(true);
}

const stageEvents = {
  onBotReady: () => setStage("starting"),
  onUserStartedSpeaking: () => hearing(""),
  onUserStoppedSpeaking: () => { userSpeaking = false; turnEnded = true; if (!micPaused) setStage("thinking"); },
  // The bot speaking settles it: whatever came before, the turn has passed to Ilumina.
  onBotStartedSpeaking: () => { resumeMic(); setStage("speaking"); },
  // After an interruption the student is still talking, so the stage stays on them.
  onBotStoppedSpeaking: () => { if (!userSpeaking && !micPaused) setStage("listening"); },
};


// The single entry point for bot data.
function receive(msg) {
  if (msg?.type === "student_state") {
    history.push(msg);
    flow("flow1");
    renderNow(msg);
    renderTrace();
    freshen("read");
    $("note-box").hidden = false;
    $("note").classList.remove("stale");
    $("note").textContent = msg.note ?? "";
    $("scored").textContent = msg.scored_ms != null
      ? `turn ${msg.turn} · scored in ${(msg.scored_ms / 1000).toFixed(2)} s`
      : `turn ${msg.turn}`;
  } else if (msg?.type === "mic_level") {
    $("mic").hidden = false;
    const paused = micPaused || Date.now() < micGraceUntil;
    $("mic").classList.toggle("silent", msg.silent && !paused);
    renderMic((msg.dbfs + 60) / 60, "on");
    if (!wave) startWave(client?.tracks?.()?.local?.audio);
    $("mic-text").textContent = paused ? "Mic paused" : msg.silent ? "Mic is silent" : "Mic live";
    // Levels come once a second. If they stop, no sound is reaching the bot at all.
    clearTimeout(micTimer);
    micTimer = setTimeout(() => {
      $("mic").classList.add("silent");
      renderMic(0);
      $("mic-text").textContent = "No sound arriving";
    }, 3000);
  } else if (msg?.type === "voice_evidence") {
    renderEvidence(msg);
  } else if (msg?.type === "memory") {
    renderMemory(msg);
  } else if (msg?.type === "teaching_move") {
    moves.push({ move: msg.move, after: history.length });
    $("move").classList.remove("none");
    $("move").textContent = MOVE_TEXT[msg.move] ?? msg.move;
    replay($("move"), "swap");
    flow("flow2");
    freshen("adapt");
    $("why").hidden = !history.length;
    $("why").textContent = history.length ? `after the turn ${history.at(-1).turn} reading` : "";
    if (history.length) renderTrace();
  } else if (msg?.type === "board") {
    // The math the tutor is talking about. It stays up until the tutor writes something new.
    $("board").hidden = false;
    $("board-math").innerHTML = tex(msg.latex, true);
    replay($("board"), "swap");
  } else if (msg?.type === "student_state_error") {
    $("note-box").hidden = false;
    $("note").classList.add("stale");
    const reason = msg.error ? ` Reason: ${String(msg.error).slice(0, 200)}` : "";
    $("note").textContent =
      "The reading for this turn failed. Ilumina is using the last state it had." + reason;
    $("scored").textContent = "last reading failed";
  } else if (msg?.type === "session_info") {
    $("running").textContent = `Pipecat · Deepgram Flux + Aura-2 · ${msg.tutor_model} teaches · ${msg.emotion_model} reads`;
    headcam = msg.camera === "gopro";
    if (headcam) $("cam-hint").textContent = "head-worn GoPro";
    startSessionClock(msg.limit_seconds);
  } else if (msg?.type === "camera_view" && (client?.isCamEnabled || headcamTimer || hostedCam)) {
    $("cam-seen").textContent = msg.seen
      ? "Ilumina got a picture with your last turn."
      : "Ilumina did not get a picture with your last turn.";
  }
}

// Camera controls. The camera is optional and never blocks the voice session.
function showCamera(track) {
  $("cam-video").srcObject = track ? new MediaStream([track]) : null;
  $("cam-video").hidden = !track;
  $("cam-off").hidden = Boolean(track);
  $("cam-toggle").textContent = track ? "Turn camera off" : "Turn camera on";
  if (!track) $("cam-pick").hidden = true;
}

function listCameras(cams) {
  const pick = $("cam-pick");
  pick.replaceChildren(...cams.map((cam, i) => new Option(cam.label || `Camera ${i + 1}`, cam.deviceId)));
  const current = client?.selectedCam?.deviceId;
  if (current) pick.value = current;
  pick.hidden = $("cam-video").hidden || cams.length < 2;
}

function resetCamera(message) {
  showCamera(null);
  $("cam-toggle").disabled = !client;
  $("cam-seen").textContent = message;
}

// Hosted camera. The WebSocket to the bot carries no video, so the page shows the
// camera itself and sends the tutor one JPEG still a second as a message.
const MAX_STILL_CHARS = 60000; // the client refuses messages over 64 KiB
let hostedCam, stillTimer;
const stillCanvas = document.createElement("canvas");
function sendStill() {
  const video = $("cam-video");
  if (!client || !hostedCam || !video.videoWidth) return;
  for (const [width, quality] of [[768, 0.6], [640, 0.5], [480, 0.5]]) {
    stillCanvas.width = width;
    stillCanvas.height = Math.round(width * video.videoHeight / video.videoWidth);
    stillCanvas.getContext("2d").drawImage(video, 0, 0, stillCanvas.width, stillCanvas.height);
    const jpeg = stillCanvas.toDataURL("image/jpeg", quality).split(",")[1];
    if (jpeg.length <= MAX_STILL_CHARS) {
      try { client.sendClientMessage("camera_frame", { jpeg }); } catch (e) { console.error(e); }
      return;
    }
  }
}
async function setHostedCam(on, deviceId) {
  clearInterval(stillTimer);
  hostedCam?.getTracks().forEach((t) => t.stop());
  hostedCam = undefined;
  if (!on) return resetCamera("Camera is off. Ilumina hears you but sees nothing.");
  $("cam-toggle").textContent = "Turn camera off";
  $("cam-seen").textContent = "Starting the camera. Allow it if the browser asks.";
  try {
    hostedCam = await navigator.mediaDevices.getUserMedia({ video: deviceId ? { deviceId: { exact: deviceId } } : { width: { ideal: 1280 } } });
  } catch (e) {
    console.error(e);
    return resetCamera(e?.name === "NotAllowedError"
      ? "The browser blocked the camera. Allow it in the address bar, then try again."
      : "The camera could not be turned on. Ilumina carries on by voice.");
  }
  if (!client) { hostedCam.getTracks().forEach((t) => t.stop()); hostedCam = undefined; return; }
  showCamera(hostedCam.getVideoTracks()[0]);
  $("cam-seen").textContent = "Camera is on. Ilumina gets a picture when you next speak.";
  stillTimer = setInterval(sendStill, 1000);
  const cams = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
  listCameras(cams);
  const current = hostedCam.getVideoTracks()[0]?.getSettings().deviceId;
  if (current) $("cam-pick").value = current;
}

// Head camera (GoPro). The bot says in session_info when it is the camera in use.
// The bot owns the feed; the dashboard switches it and shows the newest frame.
let headcam = false, headcamTimer;
async function showHeadcamFrame() {
  const r = await fetch("/headcam/frame.jpg", { cache: "no-store" }).catch(() => null);
  if (!headcamTimer) return; // turned off while this was on its way
  const img = $("cam-img");
  if (r?.status === 200) {
    const old = img.src;
    img.src = URL.createObjectURL(await r.blob());
    if (old) URL.revokeObjectURL(old);
    if (img.hidden) $("cam-seen").textContent = "Head camera is on. Ilumina gets a picture when you next speak.";
    img.hidden = false;
    $("cam-off").hidden = true;
  } else {
    img.hidden = true;
    $("cam-off").hidden = false;
    const status = r?.headers.get("X-Headcam-Status");
    $("cam-off").textContent = status ? `Waiting for the GoPro (${status})` : "Waiting for the GoPro";
  }
}

function setHeadcam(on) {
  clearInterval(headcamTimer);
  headcamTimer = on ? setInterval(showHeadcamFrame, 500) : undefined;
  fetch(`/headcam/${on ? "on" : "off"}`, { method: "POST" }).catch(console.error);
  $("cam-toggle").textContent = on ? "Turn camera off" : "Turn camera on";
  $("cam-img").hidden = true;
  $("cam-off").hidden = false;
  $("cam-off").textContent = on ? "Waiting for the GoPro" : "Camera is off";
  $("cam-seen").textContent = on
    ? "Starting the head camera."
    : "Camera is off. Ilumina hears you but sees nothing.";
}

function toggleCamera() {
  if (!client) return;
  if (headcam) return setHeadcam(!headcamTimer);
  if (HOSTED) return setHostedCam(!hostedCam);
  const on = !client.isCamEnabled;
  client.enableCam(on);
  if (on) {
    // The button now says what a click does while the camera is still starting.
    $("cam-toggle").textContent = "Turn camera off";
    $("cam-seen").textContent = "Starting the camera. Allow it if the browser asks.";
  } else {
    resetCamera("Camera is off. Ilumina hears you but sees nothing.");
  }
}

let client;
const shownSegments = new Set();
async function toggle() {
  const button = $("connect");
  if (client) {
    resumeMic(); // never leave the microphone track switched off for the next session
    await client.disconnect();
    return;
  }
  const passcode = $("passcode").value.trim();
  if (HOSTED && !passcode) {
    $("status").textContent = "Enter the passcode first";
    $("passcode").focus();
    return;
  }
  button.disabled = true;
  $("status").textContent = "Connecting";
  client = new PipecatClient({
    transport: HOSTED
      // By default the browser side uses Daily's audio handling (echo cancellation),
      // loaded from Daily's CDN. ?media=wav uses plain Web Audio instead, for checks offline.
      ? new WebSocketTransport({
        recorderSampleRate: 16000,
        playerSampleRate: 24000,
        ...(new URLSearchParams(location.search).get("media") === "wav" ? { mediaManager: new WavMediaManager(512, 16000) } : {}),
      })
      : new SmallWebRTCTransport(),
    enableMic: true,
    enableCam: false,
    callbacks: {
      onConnected: () => { $("passcode").hidden = true; $("status").textContent = "Connected"; button.textContent = "End session"; button.disabled = false; $("problem").hidden = true; resetCamera("Camera is off. Ilumina hears you but sees nothing."); },
      onDisconnected: () => { $("passcode").hidden = !HOSTED; clearTimeout(micTimer); stopWave(); resumeMic(); setStage(null); $("mic").hidden = true; clearInterval(sessionTimer); $("status").textContent = timeUp ? "Time is up. Start a new session to keep going." : "Not connected"; timeUp = false; button.textContent = "Start session"; button.disabled = false; client = undefined; if (headcamTimer) setHeadcam(false); if (hostedCam) setHostedCam(false); resetCamera("Start a session to use the camera."); },
      onServerMessage: receive,
      ...stageEvents,
      onUserTranscript: (t) => { if (t.final) addLine("You", t.text); else hearing(t.text); },
      onBotOutput: (o) => {
        // Each spoken sentence arrives twice (announced, then completed). Show it once.
        if (o.output_type !== "sentence") return;
        if (o.segment_id == null ? o.spoken_status === "new" : shownSegments.has(o.segment_id)) return;
        shownSegments.add(o.segment_id);
        addLine("Ilumina", o.text);
      },
      onTrackStarted: (track, participant) => {
        if (track.kind === "video" && participant?.local) {
          showCamera(track);
          $("cam-seen").textContent = "Camera is on. Ilumina gets a picture when you next speak.";
          client.getAllCams().then(listCameras).catch(console.error);
          return;
        }
        if (track.kind !== "audio" || participant?.local) return;
        if ($("bot-audio").srcObject?.getAudioTracks()[0] === track) return;
        $("bot-audio").srcObject = new MediaStream([track]);
      },
      onTrackStopped: (track, participant) => {
        if (track.kind === "video" && participant?.local) showCamera(null);
      },
      onAvailableCamsUpdated: listCameras,
      onCamUpdated: (cam) => { if (cam?.deviceId) $("cam-pick").value = cam.deviceId; },
      onDeviceError: (e) => {
        // Only a camera the student asked for counts; a microphone fault is not a camera problem.
        if (!client?.isCamEnabled || !e?.devices?.includes("cam")) return;
        client.enableCam(false);
        resetCamera(e.type === "permissions"
          ? "The browser blocked the camera. Allow it in the address bar, then try again."
          : "The camera could not be turned on. Ilumina carries on by voice.");
      },
      onError: (e) => {
        console.error(e);
        // Show the bot's own error text so the cause is visible without the terminal.
        const detail = e?.data?.message ?? e?.data?.error ?? (typeof e?.data === "string" ? e.data : "");
        if (stageNow === "thinking") { resumeMic(); setStage("listening", "That reply failed. You can speak again."); }
        $("status").textContent = "Connected, with an error";
        $("problem").hidden = false;
        $("problem").textContent = `The bot reported a problem: ${detail || "no details sent. Check the bot's terminal."}`;
      },
    },
  });
  try {
    if (HOSTED) {
      // Check the passcode first: a refused WebSocket gives the browser no reason.
      const check = await fetch("/api/bot", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ passcode }) });
      if (!check.ok) throw Object.assign(new Error("passcode"), { status: check.status });
      try { sessionStorage.setItem("ilumina-passcode", passcode); } catch {}
      const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/bot?passcode=${encodeURIComponent(passcode)}`;
      keepBotAudioAfterInterruptions(client._transport ?? client.transport);
      await client.connect({ wsUrl });
    } else {
      await client.connect({ webrtcRequestParams: { endpoint: "/api/offer" } });
    }
  } catch (e) {
    console.error(e);
    $("status").textContent = HOSTED
      ? (e?.status === 401 ? "Wrong passcode" : e?.status === 503 ? "The tutor is not set up yet" : "Could not start the tutor. Try again in a minute.")
      : "Could not connect. Is the bot running?";
    button.disabled = false;
    client = undefined;
  }
}

if (HOSTED) {
  // A cold bot function takes several seconds to start (it unpacks its packages first).
  // Wake it while the page loads, so Start session connects quickly. The GET is refused
  // with 405 and starts nothing.
  const wake = () => fetch("/api/bot", { cache: "no-store" }).catch(() => {});
  wake();
  $("passcode").addEventListener("focus", wake, { once: true });
  $("passcode").hidden = false;
  try { $("passcode").value = sessionStorage.getItem("ilumina-passcode") ?? ""; } catch {}
  $("passcode").addEventListener("keydown", (e) => { if (e.key === "Enter" && !client) toggle(); });
}
$("connect").addEventListener("click", toggle);
$("done").addEventListener("click", doneTalking);
$("cam-toggle").addEventListener("click", toggleCamera);
// A closed or reloaded page cannot click "off", so say it on the way out.
window.addEventListener("pagehide", () => { if (headcamTimer) navigator.sendBeacon("/headcam/off"); });
$("cam-pick").addEventListener("change", (e) => HOSTED ? setHostedCam(true, e.target.value) : client?.updateCam(e.target.value));
window.ilumina = { receive, showCamera, setHeadcam, stageEvents, hearing, addLine, startWave }; // lets checks feed recorded messages and a camera track
