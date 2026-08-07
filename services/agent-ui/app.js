// --- Config -----------------------------------------------------------
// Defaults assume agent-ui, asterisk, and realtime-assist are reachable at
// the same host the browser loaded this page from (typical docker-compose
// host-port-mapped setup). Override via query string for other layouts,
// e.g. ?host=192.168.1.50
const params = new URLSearchParams(window.location.search);
const HOST = params.get("host") || window.location.hostname;
// Plain ws, not wss: the Asterisk transport (asterisk/conf/pjsip.conf) is
// deliberately protocol=ws for this pilot — no TLS cert configured. Browsers
// only allow microphone access on secure origins OR localhost, so this
// works for same-machine testing via http://localhost but needs a
// TLS-terminating proxy in front for a second physical device on the LAN.
//
// Port is 8088, not 8089: confirmed live that Asterisk's actual SIP
// WebSocket upgrade is served on the shared HTTP/ARI port (8088, from
// http.conf) at the /ws path — a raw WebSocket handshake against 8089 (the
// port pjsip.conf's transport-ws section binds) gets no response at all,
// while 8088/ws completes the upgrade correctly (verified with curl,
// Sec-WebSocket-Protocol: sip echoed back). The transport-ws declaration in
// pjsip.conf is still what makes chan_pjsip accept WebSocket registrations
// in the first place — clients just connect via 8088 to reach it.
const SIP_WS_URL = `ws://${HOST}:8088/ws`;
const SIP_EXTENSION = params.get("ext") || "1001";
const SIP_PASSWORD = params.get("pass") || "changeme1001";
const REALTIME_WS_URL = `ws://${HOST}:8765`;

// --- Elements -----------------------------------------------------------
const sipStatusEl = document.getElementById("sip-status");
const wsStatusEl = document.getElementById("ws-status");
const dialTargetEl = document.getElementById("dial-target");
const callBtn = document.getElementById("call-btn");
const hangupBtn = document.getElementById("hangup-btn");
const remoteAudioEl = document.getElementById("remote-audio");
const promptsEl = document.getElementById("prompts");

// --- SIP (JsSIP) ----------------------------------------------------------
// JsSIP is loaded via a plain <script> tag (vendor/jssip.bundle.js, bundled
// at Docker build time — see index.html + package.json) rather than a
// dynamic CDN import. Still guarded with a runtime check: if the bundle
// somehow failed to load, the SIP/dialer panel should degrade gracefully
// rather than take down the unrelated live-assist websocket panel below.
let ua = null;

function setSipStatus(text, cls) {
  sipStatusEl.textContent = `SIP: ${text}`;
  sipStatusEl.className = `status ${cls || ""}`;
}

function initSip() {
  if (typeof JsSIP === "undefined") {
    setSipStatus("SIP library failed to load (dialer unavailable)", "error");
    console.error("window.JsSIP is undefined — vendor/jssip.bundle.js did not load");
    return;
  }

  const socket = new JsSIP.WebSocketInterface(SIP_WS_URL);
  ua = new JsSIP.UA({
    sockets: [socket],
    uri: `sip:${SIP_EXTENSION}@${HOST}`,
    password: SIP_PASSWORD,
    register: true,
  });

  ua.on("connected", () => setSipStatus("connected to Asterisk", "connected"));
  ua.on("disconnected", () => setSipStatus("disconnected, retrying…", "error"));
  ua.on("registered", () => setSipStatus(`registered as ${SIP_EXTENSION}`, "connected"));
  ua.on("registrationFailed", (e) => setSipStatus(`registration failed: ${e.cause}`, "error"));

  ua.on("newRTCSession", ({ session }) => {
    currentSession = session;
    hangupBtn.disabled = false;

    session.connection.addEventListener("track", (event) => {
      remoteAudioEl.srcObject = event.streams[0];
    });

    session.on("ended", resetCallUI);
    session.on("failed", resetCallUI);
  });

  ua.start();
}

let currentSession = null;

function resetCallUI() {
  currentSession = null;
  hangupBtn.disabled = true;
  callBtn.disabled = false;
}

callBtn.addEventListener("click", () => {
  if (!ua) {
    setSipStatus("SIP library not loaded, cannot place calls", "error");
    return;
  }
  const target = dialTargetEl.value.trim();
  if (!target) return;
  currentSession = ua.call(`sip:${target}@${HOST}`, {
    mediaConstraints: { audio: true, video: false },
  });
  callBtn.disabled = true;
  hangupBtn.disabled = false;
});

hangupBtn.addEventListener("click", () => {
  if (currentSession) currentSession.terminate();
  resetCallUI();
});

// --- Live assist websocket ------------------------------------------------
// Deliberately independent of the SIP init above — this panel should keep
// working even if the dialer failed to load.
function setWsStatus(text, cls) {
  wsStatusEl.textContent = `Live assist: ${text}`;
  wsStatusEl.className = `status ${cls || ""}`;
}

function connectRealtimeAssist() {
  const ws = new WebSocket(REALTIME_WS_URL);

  ws.onopen = () => setWsStatus("connected", "connected");
  ws.onclose = () => {
    setWsStatus("disconnected, retrying in 3s…", "error");
    setTimeout(connectRealtimeAssist, 3000);
  };
  ws.onerror = () => setWsStatus("connection error", "error");

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      addPrompt(msg);
    } catch {
      // ignore malformed messages
    }
  };
}

function addPrompt({ call_id, chunk_index, prompt_text }) {
  const li = document.createElement("li");
  const time = new Date().toLocaleTimeString();
  li.innerHTML = `${escapeHtml(prompt_text)}<span class="meta">call ${escapeHtml(call_id)} · chunk ${chunk_index} · ${time}</span>`;
  promptsEl.prepend(li);
  while (promptsEl.children.length > 20) {
    promptsEl.removeChild(promptsEl.lastChild);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

initSip();
connectRealtimeAssist();
