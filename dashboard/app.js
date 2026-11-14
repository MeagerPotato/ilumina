// Ilumina dashboard. Everything drawn here comes from messages the bot sends.
// Nothing is simulated: with no messages, the page stays empty.
import { PipecatClient, SmallWebRTCTransport } from "./vendor/pipecat.js";

const DIMS = ["confusion", "frustration", "confidence", "engagement"];
const STATUS_TEXT = { steady: "steady", blip: "blip, ignored", trend: "changed" };
const MOVE_TEXT = {
  continue: "Keep going",
  smaller_hint: "Smaller hint",
  new_explanation: "Explain it a different way",
  worked_example: "Worked example",
  harder_problem: "Raise the difficulty",
  check_in: "Check in with the student",
};
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
    // The percentage is about this turn's reading, which on a blip is not the level shown.
    const sure = `${Math.round(d.confidence * 100)}% sure`;
    const read = d.seen === d.level ? sure : `this turn read ${d.seen}, ${sure}`;
    return `<div class="dim">
      <div class="name">${dim}<small>${d.level}, ${read}</small></div>
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

// Deepgram's word timings for the turn, as measured. A wait is only there when one was measured.
function renderEvidence(e) {
  $("measured").hidden = e.words == null; // a turn with nothing measured shows nothing
  if (e.words == null) return;
  const seconds = (v) => `${v.toFixed(1)} s`;
  const cells = [
    e.words_per_minute == null
      ? [e.words, e.words === 1 ? "word, too few for a pace" : "words, too few for a pace"]
      : [e.words_per_minute, "words a minute"],
    [seconds(e.longest_pause), "longest pause"],
    [e.fillers, e.fillers === 1 ? "um or uh" : "ums and uhs"],
  ];
  if (e.waited != null) cells.push([seconds(e.waited), "before you answered"]);
  $("evidence").innerHTML = cells.map(([value, label]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join("");
}

// Memory: the classes the tutor was told about, and the study plan, as the bot sent them.
// The text was written by a model from the student's own class, so it is escaped.
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

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

function renderMemory(m) {
  const classes = (m.lectures ?? []).map((c) => {
    const stuck = (c.sticking_points ?? []).length ? `<span>Likely sticking points: ${withMath(c.sticking_points.join("; "))}</span>` : "";
    return `<p class="class"><b>${withMath(c.title)}</b>
      <span>${withMath([c.subject, (c.concepts ?? []).join(", ")].filter(Boolean).join(": "))}</span>${stuck}</p>`;
  }).join("");
  const moments = m.hard_moments
    ? `<p class="class"><b>Earlier sessions</b><span>${Number(m.hard_moments)} ${m.hard_moments === 1 ? "moment" : "moments"} where you sounded stuck</span></p>`
    : "";
  if (!classes && !moments && !m.plan) {
    $("memory").innerHTML = `<p class="empty">Nothing saved yet. Record a class and Ilumina opens the next session from it.</p>`;
    return;
  }
  $("memory").innerHTML = classes + moments
    + (m.plan ? `<h3>Study plan</h3><div class="plan" tabindex="0">${planHtml(m.plan)}</div>` : "")
    + `<p class="kept">Saved on this computer. Ilumina is told about the classes and where you got stuck, not the plan.</p>`;
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
    $("note").classList.remove("stale");
    $("note").textContent = msg.note ?? "";
    if (msg.scored_ms != null) {
      $("scored").hidden = false;
      $("scored").textContent = `This turn was scored from your voice and your words in ${(msg.scored_ms / 1000).toFixed(2)} seconds.`;
    }
  } else if (msg?.type === "mic_level") {
    // How loud the bot hears the microphone, from 60 dB below full scale up to full scale.
    $("mic").hidden = false;
    const paused = micPaused || Date.now() < micGraceUntil;
    $("mic").classList.toggle("silent", msg.silent && !paused);
    $("mic-fill").style.width = pct((msg.dbfs + 60) / 60);
    $("mic-text").textContent = paused ? "Mic is paused" : msg.silent ? "Mic is silent" : "Mic is live";
    // Levels come once a second. If they stop, no sound is reaching the bot at all.
    clearTimeout(micTimer);
    micTimer = setTimeout(() => {
      $("mic").classList.add("silent");
      $("mic-fill").style.width = "0";
      $("mic-text").textContent = "No sound is arriving";
    }, 3000);
  } else if (msg?.type === "voice_evidence") {
    renderEvidence(msg);
  } else if (msg?.type === "memory") {
    renderMemory(msg);
  } else if (msg?.type === "teaching_move") {
    $("move").hidden = false;
    $("move-name").textContent = MOVE_TEXT[msg.move] ?? msg.move;
  } else if (msg?.type === "board") {
    // The math the tutor is talking about. It stays up until the tutor writes something new.
    $("board").hidden = false;
    $("board-math").innerHTML = tex(msg.latex, true);
  } else if (msg?.type === "student_state_error") {
    $("note").classList.add("stale");
    const reason = msg.error ? ` Reason: ${String(msg.error).slice(0, 200)}` : "";
    $("note").textContent =
      "The reading for this turn failed. Ilumina is using the last state it had." + reason;
  } else if (msg?.type === "session_info") {
    $("running").hidden = false;
    $("running").textContent =
      `This session runs on Pipecat. Deepgram Flux hears you and Deepgram Aura-2 speaks. ` +
      `${msg.tutor_model} does the teaching, and ${msg.emotion_model} reads how you sound and what you say.`;
    headcam = msg.camera === "gopro";
    if (headcam) $("cam-hint").textContent = "Wear the GoPro and look at your page so Ilumina can read the problem and your working.";
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
window.ilumina = { receive, showCamera, setHeadcam, stageEvents, hearing }; // lets checks feed recorded messages and a camera track
