import { _electron as electron, chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const appDir = path.resolve(import.meta.dirname, "..");
const repoDir = path.resolve(appDir, "..", "..");
const apiBase = process.env.PLATFORM_API_URL || "http://127.0.0.1:18080";
const customerUrl = process.env.SIP_CUSTOMER_URL || "http://127.0.0.1:18082/?ext=1003&pass=changeme1003&assist=0&target=2101";
const password = process.env.PILOT_PASSWORD || "PilotTest123!";
const evidenceSid = "eb82ec7b5f0944ca";
const agentAudio = path.join(repoDir, "demo-data", "harper-valley", "audio", "agent", `${evidenceSid}.wav`);
const callerAudio = path.join(repoDir, "demo-data", "harper-valley", "audio", "caller", `${evidenceSid}.wav`);
const evidenceDir = path.join(repoDir, "artifacts", "ui");
await mkdir(evidenceDir, { recursive: true });

const login = await fetch(`${apiBase}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "agent1@pilot.example", password }) });
if (!login.ok) throw new Error(`Agent preflight login failed: ${login.status}`);
const { access_token: token } = await login.json();
const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
const supervisorLogin = await fetch(`${apiBase}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "supervisor@pilot.example", password }) });
if (!supervisorLogin.ok) throw new Error(`Supervisor preflight login failed: ${supervisorLogin.status}`);
const { access_token: supervisorToken } = await supervisorLogin.json();
const supervisorHeaders = { "Content-Type": "application/json", Authorization: `Bearer ${supervisorToken}` };

async function api(pathname, options = {}) {
  const response = await fetch(`${apiBase}${pathname}`, { ...options, headers: { ...headers, ...options.headers } });
  if (!response.ok) throw new Error(`${options.method || "GET"} ${pathname} failed: ${response.status} ${await response.text()}`);
  return response;
}

async function supervisorApi(pathname) {
  const response = await fetch(`${apiBase}${pathname}`, { headers: supervisorHeaders });
  if (!response.ok) throw new Error(`GET ${pathname} failed: ${response.status} ${await response.text()}`);
  return response;
}

for (const queued of await api("/work/queued").then((response) => response.json())) {
  if (queued.channel === "voice") await api(`/voice/calls/${queued.id}/reject`, { method: "POST" });
}

for (const conversation of await api("/conversations").then((response) => response.json())) {
  if (!["active", "wrap_up"].includes(conversation.status)) continue;
  if (conversation.channel === "voice") {
    const call = await api(`/voice/calls/${conversation.id}`).then((response) => response.json());
    if (call.session.state !== "ended") await api(`/voice/calls/${conversation.id}/control`, { method: "POST", body: JSON.stringify({ action: "hangup" }) });
  }
  await api(`/conversations/${conversation.id}/wrap-up`, { method: "POST", body: JSON.stringify({ disposition: "sip_e2e_preflight", summary: "Closed before two-way SIP verification." }) });
}

async function activeVoice(direction) {
  const conversations = await api("/conversations").then((response) => response.json());
  const found = conversations.find((item) => item.channel === "voice" && item.direction === direction && item.status === "active");
  if (!found) throw new Error(`No active ${direction} voice conversation was found`);
  return found;
}

async function waitForNewQueuedVoice(existingIds, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const queued = await api("/work/queued").then((response) => response.json());
    const found = queued.find((item) => item.channel === "voice" && !existingIds.has(item.id));
    if (found) return found;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("The inbound SIP call did not create a new queued voice interaction");
}

async function waitForLiveTranscript(conversationId, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const transcript = await api(`/conversations/${conversationId}/transcript`).then((response) => response.json());
    const roles = new Set(transcript.map((item) => item.speaker));
    if (roles.has("agent") && roles.has("customer")) return transcript;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error(`Speaker-correct Groq transcript did not appear for ${conversationId}`);
}

async function waitForFinalEvidence(conversationId, timeoutMs = 240_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const [call, evaluations] = await Promise.all([
      api(`/voice/calls/${conversationId}`).then((response) => response.json()),
      supervisorApi("/qa/evaluations").then((response) => response.json()),
    ]);
    const evaluation = evaluations.find((item) => item.conversation_id === conversationId);
    if (call.session.state === "ended" && evaluation?.provider === "groq") {
      const recording = await api(`/conversations/${conversationId}/recording`);
      const transcript = await api(`/conversations/${conversationId}/transcript`).then((response) => response.json());
      const roles = new Set(transcript.map((item) => item.speaker));
      if (!roles.has("agent") || !roles.has("customer")) throw new Error(`Final transcript lost speaker attribution for ${conversationId}`);
      if (!(Number(recording.headers.get("content-length")) > 1_000)) throw new Error(`Recording is empty for ${conversationId}`);
      return { evaluation, transcriptSegments: transcript.length };
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error(`Groq QA/recording evidence did not finalize for ${conversationId}`);
}

const baseMediaArgs = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"];
const browser = await chromium.launch({ channel: "chrome", headless: true, args: [...baseMediaArgs, `--use-file-for-fake-audio-capture=${callerAudio}`] });
const customerContext = await browser.newContext({ permissions: ["microphone"] });
const customer = await customerContext.newPage();
const failures = [];
customer.on("console", (message) => { if (["error", "warning"].includes(message.type())) failures.push(`customer console ${message.type()}: ${message.text()}`); });
customer.on("requestfailed", (request) => failures.push(`customer network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`));
const electronApp = await electron.launch({
  args: [".", ...baseMediaArgs, `--use-file-for-fake-audio-capture=${agentAudio}`],
  cwd: appDir,
  env: { ...process.env, PLATFORM_SIP_ENABLED: "true", PLATFORM_SIP_WS_URL: "ws://127.0.0.1:8088/ws", PLATFORM_SIP_HOST: "127.0.0.1", PLATFORM_SIP_EXTENSION: "1001", PLATFORM_SIP_PASSWORD: "changeme1001" },
});
const agent = await electronApp.firstWindow();
agent.on("console", (message) => { if (["error", "warning"].includes(message.type())) failures.push(`agent console ${message.type()}: ${message.text()}`); });
agent.on("requestfailed", (request) => { if (!request.url().startsWith("blob:")) failures.push(`agent network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`); });

try {
  await customer.goto(customerUrl, { waitUntil: "domcontentloaded" });
  await customer.getByText("SIP: registered as 1003").waitFor({ timeout: 20_000 });
  await agent.getByLabel("Work email").fill("agent1@pilot.example");
  await agent.getByLabel("Password").fill(password);
  await agent.getByRole("button", { name: /Enter workspace/ }).click();
  await agent.getByText("SIP 1001").waitFor({ timeout: 20_000 });

  // Outbound: Electron agent 1001 -> Asterisk 2003 -> browser customer 1003.
  await agent.getByLabel("Customer phone").fill("2003");
  await agent.getByLabel("Start call").click();
  await agent.getByText("Two-party media").waitFor({ timeout: 20_000 });
  const outbound = await activeVoice("outbound");
  const channels = execFileSync("docker", ["exec", "bpo-demo-asterisk-1", "asterisk", "-rx", "core show channels concise"], { encoding: "utf8" });
  if (!channels.includes("PJSIP/1003")) throw new Error(`Asterisk did not expose the live 1003 channel:\n${channels}`);
  await waitForLiveTranscript(outbound.id);
  await agent.getByRole("button", { name: "Mute" }).click();
  await agent.getByRole("button", { name: "Unmute" }).waitFor();
  await agent.getByRole("button", { name: "Hold" }).click();
  await agent.getByText("On hold", { exact: true }).waitFor();
  await agent.getByRole("button", { name: "Resume" }).click();
  await agent.getByRole("button", { name: "Hang up" }).click();
  await agent.getByText("Call complete", { exact: true }).waitFor({ timeout: 30_000 });
  const outboundEvidence = await waitForFinalEvidence(outbound.id);
  await agent.screenshot({ path: path.join(evidenceDir, "electron-real-outbound-sip.png") });
  await agent.getByRole("button", { name: /Complete wrap-up/ }).click();
  await agent.getByText("Start a voice interaction").waitFor();

  // Inbound: browser customer 1003 -> Asterisk 2101 -> ringing Electron agent 1001.
  const existingQueueIds = new Set((await api("/work/queued").then((response) => response.json())).map((item) => item.id));
  await customer.getByRole("button", { name: "Call" }).click();
  const queuedInbound = await waitForNewQueuedVoice(existingQueueIds);
  const inboundQueue = agent.locator(`.queue-item[data-conversation-id="${queuedInbound.id}"]`);
  await inboundQueue.getByRole("button", { name: "Accept" }).waitFor({ timeout: 20_000 });
  const inboundId = await inboundQueue.getAttribute("data-conversation-id");
  if (!inboundId) throw new Error("Inbound queue item did not expose its conversation ID");
  await inboundQueue.getByRole("button", { name: "Accept" }).click();
  await agent.getByText("Two-party media").waitFor({ timeout: 20_000 });
  const inbound = await activeVoice("inbound");
  if (inbound.id !== inboundId) throw new Error(`Accepted inbound ${inbound.id}, expected ${inboundId}`);
  await waitForLiveTranscript(inbound.id);
  await agent.getByRole("button", { name: "Hang up" }).click();
  await agent.getByText("Call complete", { exact: true }).waitFor({ timeout: 30_000 });
  const inboundEvidence = await waitForFinalEvidence(inbound.id);
  await agent.screenshot({ path: path.join(evidenceDir, "electron-real-inbound-sip.png") });

  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({
    ok: true,
    evidenceSource: `HarperValleyBank:${evidenceSid}`,
    registered: ["1001", "1003"],
    outbound: { conversationId: outbound.id, route: "1001->2003->1003", ...outboundEvidence },
    inbound: { conversationId: inbound.id, route: "1003->2101->1001", ...inboundEvidence },
  }));
} catch (error) {
  console.error(JSON.stringify({ agentSip: await agent.locator(".sip-indicator").textContent().catch(() => null), customerSip: await customer.locator("#sip-status").textContent().catch(() => null), failures }, null, 2));
  throw error;
} finally {
  await electronApp.close();
  await customerContext.close();
  await browser.close();
}
