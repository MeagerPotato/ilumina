// Ilumina dashboard. Everything drawn here comes from messages the bot sends.
// Nothing is simulated: with no messages, the page stays empty.
import { PipecatClient, SmallWebRTCTransport } from "./vendor/pipecat.js";

const DIMS = ["confusion", "frustration", "confidence", "engagement"];
const STATUS_TEXT = { steady: "steady", blip: "blip, ignored", trend: "changed" };
const history = []; // one snapshot per scored turn

const $ = (id) => document.getElementById(id);
const pct = (v) => `${Math.max(0, Math.min(1, v)) * 100}%`;
const color = (dim) => `var(--${dim})`;

function renderNow(snapshot) {
  $("key").hidden = false;
  $("dims").innerHTML = DIMS.filter((d) => snapshot.dimensions[d]).map((dim) => {
    const d = snapshot.dimensions[dim];
    // Band half-width grows as the model gets less sure of its reading.
    const half = 0.04 + (1 - d.confidence) * 0.22;
    const left = Math.max(0, d.reading - half), right = Math.min(1, d.reading + half);
    return `<div class="dim">
      <div class="name">${dim}<small>${d.level}, ${Math.round(d.confidence * 100)}% sure</small></div>
      <div class="track" role="img" aria-label="${dim}: ${d.level}, estimate ${d.estimate}, reading ${d.reading}">
        <span class="zone" style="left:35%"></span><span class="zone" style="left:65%"></span>
        <span class="band" style="left:${pct(left)};width:${pct(right - left)};background:${color(dim)}"></span>
        <span class="reading" style="left:${pct(d.reading)};border-color:${color(dim)}"></span>
        <span class="estimate" style="left:${pct(d.estimate)};background:${color(dim)}"></span>
      </div>
      <span class="chip ${d.status}">${STATUS_TEXT[d.status] ?? d.status}</span>
    </div>`;
  }).join("");
}

function renderTrace() {
  const W = 1100, rowH = 84, padL = 110, padR = 20, top = 8;
  const n = Math.max(history.length, 8);
  const x = (i) => padL + (i + 0.5) * ((W - padL - padR) / n);
  const rows = DIMS.map((dim, r) => {
    const y0 = top + r * rowH, y = (v) => y0 + rowH - 12 - v * (rowH - 24);
    const pts = history.map((s, i) => ({ i, d: s.dimensions[dim] })).filter((p) => p.d);
    const line = pts.map((p) => `${x(p.i)},${y(p.d.estimate)}`).join(" ");
    const dots = pts.map((p) => {
      const blip = p.d.status === "blip";
      return `<circle cx="${x(p.i)}" cy="${y(p.d.reading)}" r="${p.d.status === "trend" ? 6 : 4.5}"
        fill="${blip ? "var(--panel)" : color(dim)}" stroke="${color(dim)}" stroke-width="2">
        <title>Turn ${history[p.i].turn}: read ${p.d.reading}, ${STATUS_TEXT[p.d.status] ?? p.d.status}</title></circle>`;
    }).join("");
    return `<line x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}" stroke="var(--grid)"/>
      <text class="dimname" x="0" y="${y0 + rowH / 2 + 5}">${dim}</text>
      <polyline points="${line}" fill="none" stroke="${color(dim)}" stroke-width="2.5" stroke-linejoin="round"/>${dots}`;
  }).join("");
  const ticks = history.map((s, i) => `<text x="${x(i)}" y="${top + DIMS.length * rowH + 14}" text-anchor="middle">${s.turn}</text>`).join("");
  $("trace").innerHTML = `<svg viewBox="0 0 ${W} ${top + DIMS.length * rowH + 22}" role="img"
    aria-label="Smoothed estimate and per-turn readings for each dimension, by turn">${rows}${ticks}</svg>`;
}

function addLine(who, text) {
  const li = document.createElement("li");
  const b = document.createElement("b");
  b.textContent = `${who}: `;
  li.append(b, text);
  $("lines").append(li);
  $("lines").scrollTop = $("lines").scrollHeight;
}

// The single entry point for bot data.
function receive(msg) {
  if (msg?.type === "student_state") {
    history.push(msg);
    renderNow(msg);
    renderTrace();
    $("note").classList.remove("stale");
    $("note").textContent = msg.note ?? "";
  } else if (msg?.type === "student_state_error") {
    $("note").classList.add("stale");
    const reason = msg.error ? ` Reason: ${String(msg.error).slice(0, 200)}` : "";
    $("note").textContent =
      "The reading for this turn failed. Ilumina is using the last state it had." + reason;
  }
}

let client;
const shownSegments = new Set();
async function toggle() {
  const button = $("connect");
  if (client) {
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
      onConnected: () => { $("status").textContent = "Connected"; button.textContent = "End session"; button.disabled = false; $("problem").hidden = true; },
      onDisconnected: () => { $("status").textContent = "Not connected"; button.textContent = "Start session"; button.disabled = false; client = undefined; },
      onServerMessage: receive,
      onUserTranscript: (t) => { if (t.final) addLine("You", t.text); },
      onBotOutput: (o) => {
        // Each spoken sentence arrives twice (announced, then completed). Show it once.
        if (o.output_type !== "sentence") return;
        if (o.segment_id == null ? o.spoken_status === "new" : shownSegments.has(o.segment_id)) return;
        shownSegments.add(o.segment_id);
        addLine("Ilumina", o.text);
      },
      onTrackStarted: (track, participant) => {
        if (track.kind !== "audio" || participant?.local) return;
        if ($("bot-audio").srcObject?.getAudioTracks()[0] === track) return;
        $("bot-audio").srcObject = new MediaStream([track]);
      },
      onError: (e) => {
        console.error(e);
        // Show the bot's own error text so the cause is visible without the terminal.
        const detail = e?.data?.message ?? e?.data?.error ?? (typeof e?.data === "string" ? e.data : "");
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
window.ilumina = { receive }; // lets tests feed recorded messages
