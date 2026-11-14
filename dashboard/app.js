// Ilumina dashboard. Everything drawn here comes from messages the bot sends.
// Nothing is simulated: with no messages, the page stays empty.
import { PipecatClient, SmallWebRTCTransport } from "./vendor/pipecat.js";

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

// One headline for the turn: the learning state the tracker settled on, how sure it is,
// and how that belief is spread over all five states. Absent when the bot sent none.
function renderHeadline(ls) {
  $("headline").hidden = !ls;
  if (!ls) return;
  const name = $("state-name");
  name.textContent = ls.state;
  name.style.setProperty("--c", stateColor(ls.state));
  const bits = [`${Math.round(ls.certainty * 100)}% sure`, ls.turns === 1 ? "new this turn" : `${ls.turns} turns`];
  if (ls.reading && ls.reading !== ls.state) bits.push(`this turn looked ${ls.reading}`);
  $("state-meta").textContent = bits.join(" · ");
  const dist = ls.distribution ?? {};
  const order = [...STATES, ...Object.keys(dist).filter((st) => !STATES.includes(st))];
  $("state-dist").innerHTML = order.filter((st) => dist[st] > 0.005).map((st) =>
    `<i style="flex:${dist[st]};background:${stateColor(st)}" title="${esc(st)} ${Math.round(dist[st] * 100)}%"></i>`).join("");
  $("state-dist").setAttribute("aria-label", order.filter((st) => dist[st] != null).map((st) => `${st} ${Math.round(dist[st] * 100)}%`).join(", "));
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

function renderNow(snapshot) {
  $("key").hidden = $("scale").hidden = false;
  renderHeadline(snapshot.learning_state);
  renderUsual(snapshot);
  $("dims").innerHTML = dimsOf(snapshot).map((dim) => {
    const d = snapshot.dimensions[dim];
    // The band grows as the model gets less sure of this turn's reading.
    const half = 0.04 + (1 - d.confidence) * 0.22;
    const left = clamp(d.reading - half), right = clamp(d.reading + half);
    const sure = `${Math.round(d.confidence * 100)}% sure`;
    const read = d.seen === d.level ? sure : `this turn read ${d.seen}, ${sure}`;
    const badge = d.status === "trend" ? `<em class="trend">new</em>` : d.status === "blip" ? `<em class="blip">blip</em>` : "";
    return `<div class="dim ${d.status}" title="${esc(dim)}: ${d.level}. Smoothed ${d.estimate}, this turn ${d.reading} (${read}). ${STATUS_TEXT[d.status] ?? d.status}.">
      <div class="name"><i style="background:${colorOf(dim)}"></i>${esc(dim)}</div>
      <div class="track" role="img" aria-label="${esc(dim)}: ${d.level}, smoothed ${d.estimate}, this turn ${d.reading}, ${read}">
        <span class="band" style="left:${pct(left)};width:${pct(right - left)};background:${colorOf(dim)}"></span>
        <span class="fill" style="width:${pct(d.estimate)};background:${colorOf(dim)}"></span>
        <span class="zone" style="left:35%"></span><span class="zone" style="left:65%"></span>
        <span class="reading" style="left:${pct(d.reading)};border-color:${colorOf(dim)}"></span>
      </div>
      <div class="level">${badge}${d.level}</div>
    </div>`;
  }).join("");
}

// Deepgram's word timings for the turn, as measured. Anything not measured shows a dash.
function renderEvidence(e) {
  const cell = (value, unit, label) => value == null
    ? `<div><dt>${label}</dt><dd class="none">–</dd></div>`
    : `<div><dt>${label}</dt><dd>${value}${unit ? `<small>${unit}</small>` : ""}</dd></div>`;
  const tooFew = e.words != null && e.words_per_minute == null;
  $("evidence").innerHTML = [
    tooFew
      ? cell(e.words, "", e.words === 1 ? "word, too few for a pace" : "words, too few for a pace")
      : cell(e.words_per_minute, "", "words a minute"),
    cell(e.longest_pause?.toFixed(1), "s", "longest pause"),
    cell(e.fillers, "", e.fillers === 1 ? "um or uh" : "ums and uhs"),
    cell(e.waited?.toFixed(1), "s", "wait before answering"),
  ].join("");
  $("spoke").hidden = e.words == null;
  if (e.words != null) $("spoke").textContent = `${e.words} ${e.words === 1 ? "word" : "words"} in ${e.seconds.toFixed(1)} s`
    + (e.hedges ? ` · ${e.hedges} ${e.hedges === 1 ? "hedge" : "hedges"}` : "");
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

// Over the session: one row per reading, plus a row for the tutor's moves.
// The line is the smoothed estimate; squares are each turn's reading, hollow when ignored as a blip.
function renderTrace() {
  const W = 1160, rowH = 56, padL = 104, padR = 12, top = 6, moveH = 34;
  const dims = [...new Set(history.flatMap(dimsOf))];
  const n = Math.max(history.length, 12);
  const colW = (W - padL - padR) / n;
  const x = (i) => padL + (i + 0.5) * colW;
  const hasState = history.some((s) => s.learning_state);
  const stateH = hasState ? 34 : 0;
  const rowsTop = top + stateH;
  const rowsBottom = rowsTop + dims.length * rowH;
  const H = rowsBottom + moveH + 18;
  const cols = history.map((s, i) =>
    `<rect class="col" data-i="${i}" x="${padL + i * colW}" y="0" width="${colW}" height="${rowsBottom + moveH}"/>`).join("");
  const rows = dims.map((dim, r) => {
    const y0 = rowsTop + r * rowH, y = (v) => y0 + rowH - 8 - clamp(v) * (rowH - 16);
    const pts = history.map((s, i) => ({ i, d: s.dimensions[dim] })).filter((p) => p.d);
    const line = pts.map((p) => `${x(p.i)},${y(p.d.estimate)}`).join(" ");
    const marks = pts.map((p) => {
      const blip = p.d.status === "blip", s = p.d.status === "trend" ? 10 : 8;
      return `<rect x="${x(p.i) - s / 2}" y="${y(p.d.reading) - s / 2}" width="${s}" height="${s}"
        fill="${blip ? "var(--bg)" : colorOf(dim)}" stroke="${colorOf(dim)}" stroke-width="2" ${blip ? 'stroke-dasharray="2 1.5"' : ""}/>`;
    }).join("");
    return `<line x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)"/>
      <line x1="${padL}" x2="${W - padR}" y1="${y(0.65)}" y2="${y(0.65)}" stroke="var(--line)" stroke-dasharray="2 4"/>
      <rect x="0" y="${y0 + rowH / 2 - 9}" width="8" height="8" fill="${colorOf(dim)}"/>
      <text class="row" x="14" y="${y0 + rowH / 2}">${esc(dim)}</text>
      <polyline points="${line}" fill="none" stroke="${colorOf(dim)}" stroke-width="2" stroke-linejoin="round" opacity=".55"/>${marks}`;
  }).join("");
  const pill = (cx, cy, w, fill, label) => `<rect x="${cx - w / 2}" y="${cy}" width="${w}" height="18" fill="${fill}"/>
    <text x="${cx}" y="${cy + 13}" text-anchor="middle" style="fill:#fff;font-size:11px;font-weight:600">${esc(label)}</text>`;
  const pillW = Math.min(colW - 6, 74);
  // A move belongs to the column of the newest reading the tutor could have had.
  const byCol = new Map();
  for (const m of moves) if (m.after > 0) byCol.set(m.after - 1, m.move);
  const moveRow = `<line x1="${padL}" x2="${W - padR}" y1="${rowsBottom + 4}" y2="${rowsBottom + 4}" stroke="var(--ink)" stroke-width="2"/>
    <text class="row" x="0" y="${rowsBottom + 24}">Tutor</text>` +
    [...byCol].map(([i, move]) => {
      const label = MOVE_SHORT[move] ?? move;
      return pill(x(i), rowsBottom + 11, pillW, "var(--ink)", colW < 60 ? label.slice(0, 6) : label);
    }).join("");
  const stateRow = !hasState ? "" : `<text class="row" x="0" y="${top + 17}">State</text>` +
    history.map((s, i) => s.learning_state
      ? pill(x(i), top + 4, pillW, stateColor(s.learning_state.state), colW < 60 ? s.learning_state.state.slice(0, 5) : s.learning_state.state)
      : "").join("");
  const ticks = history.map((s, i) => `<text x="${x(i)}" y="${H - 2}" text-anchor="middle">${s.turn}</text>`).join("");
  $("trace").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img"
    aria-label="Smoothed estimate and per-turn readings for each dimension, with the tutor's move, by turn">${cols}${stateRow}${rows}${moveRow}${ticks}</svg>`;
  $("trace").querySelectorAll(".col").forEach((col) => {
    col.addEventListener("mouseenter", () => showTip(col));
    col.addEventListener("mouseleave", () => { $("tip").hidden = true; col.classList.remove("on"); });
  });
}

function showTip(col) {
  const i = Number(col.dataset.i), s = history[i];
  col.classList.add("on");
  const rows = dimsOf(s).map((dim) => {
    const d = s.dimensions[dim];
    return `<div><span>${esc(dim)}</span><span>${d.level}${d.status === "blip" ? " (blip)" : d.status === "trend" ? " (new)" : ""}</span></div>`;
  }).join("");
  const turnMoves = moves.filter((m) => m.after === i + 1).map((m) => MOVE_TEXT[m.move] ?? m.move);
  const tip = $("tip");
  const ls = s.learning_state;
  const stateLine = ls ? `<div><span>state</span><span>${esc(ls.state)} (${Math.round(ls.certainty * 100)}%)</span></div>` : "";
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
  $("mic-level").innerHTML = Array.from({ length: 10 }, (_, i) => `<i class="${i < lit ? cls : ""}"></i>`).join("");
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
    renderNow(msg);
    renderTrace();
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
    $("why").hidden = !history.length;
    $("why").textContent = history.length ? `after the turn ${history.at(-1).turn} reading` : "";
    if (history.length) renderTrace();
  } else if (msg?.type === "board") {
    // The math the tutor is talking about. It stays up until the tutor writes something new.
    $("board").hidden = false;
    $("board-math").innerHTML = tex(msg.latex, true);
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
  } else if (msg?.type === "camera_view" && (client?.isCamEnabled || headcamTimer)) {
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
  button.disabled = true;
  $("status").textContent = "Connecting";
  client = new PipecatClient({
    transport: new SmallWebRTCTransport(),
    enableMic: true,
    enableCam: false,
    callbacks: {
      onConnected: () => { $("status").textContent = "Connected"; button.textContent = "End session"; button.disabled = false; $("problem").hidden = true; resetCamera("Camera is off. Ilumina hears you but sees nothing."); },
      onDisconnected: () => { clearTimeout(micTimer); resumeMic(); setStage(null); $("mic").hidden = true; $("status").textContent = "Not connected"; button.textContent = "Start session"; button.disabled = false; client = undefined; if (headcamTimer) setHeadcam(false); resetCamera("Start a session to use the camera."); },
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
    await client.connect({ webrtcRequestParams: { endpoint: "/api/offer" } });
  } catch (e) {
    console.error(e);
    $("status").textContent = "Could not connect. Is the bot running?";
    button.disabled = false;
    client = undefined;
  }
}

$("connect").addEventListener("click", toggle);
$("done").addEventListener("click", doneTalking);
$("cam-toggle").addEventListener("click", toggleCamera);
// A closed or reloaded page cannot click "off", so say it on the way out.
window.addEventListener("pagehide", () => { if (headcamTimer) navigator.sendBeacon("/headcam/off"); });
$("cam-pick").addEventListener("change", (e) => client?.updateCam(e.target.value));
window.ilumina = { receive, showCamera, setHeadcam, stageEvents, hearing, addLine }; // lets checks feed recorded messages and a camera track
