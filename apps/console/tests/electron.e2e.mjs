import { _electron as electron } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const appDir = path.resolve(import.meta.dirname, "..");
const evidenceDir = path.resolve(appDir, "..", "..", "artifacts", "ui");
const apiBase = process.env.PLATFORM_API_URL || "http://127.0.0.1:18080";
const password = process.env.PILOT_PASSWORD || "PilotTest123!";
const failures = [];

await mkdir(evidenceDir, { recursive: true });

const agentLoginResponse = await fetch(`${apiBase}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "agent1@pilot.example", password }) });
if (!agentLoginResponse.ok) throw new Error(`Agent preflight login failed: ${agentLoginResponse.status}`);
const agentLogin = await agentLoginResponse.json();
const agentHeaders = { "Content-Type": "application/json", Authorization: `Bearer ${agentLogin.access_token}` };
const assignedResponse = await fetch(`${apiBase}/conversations`, { headers: agentHeaders });
if (!assignedResponse.ok) throw new Error(`Agent preflight work lookup failed: ${assignedResponse.status}`);
for (const conversation of await assignedResponse.json()) {
  if (!["active", "wrap_up"].includes(conversation.status)) continue;
  if (conversation.channel === "voice") {
    const callResponse = await fetch(`${apiBase}/voice/calls/${conversation.id}`, { headers: agentHeaders });
    if (callResponse.ok && (await callResponse.json()).session.state !== "ended") {
      await fetch(`${apiBase}/voice/calls/${conversation.id}/control`, { method: "POST", headers: agentHeaders, body: JSON.stringify({ action: "hangup" }) });
    }
  }
  const cleanupResponse = await fetch(`${apiBase}/conversations/${conversation.id}/wrap-up`, { method: "POST", headers: agentHeaders, body: JSON.stringify({ disposition: "e2e_preflight", summary: "Closed by repeatable Electron test preflight." }) });
  if (!cleanupResponse.ok) throw new Error(`Could not close stale interaction ${conversation.id}: ${cleanupResponse.status}`);
}

const chatStart = await fetch(`${apiBase}/public/chat/start`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    tenant_slug: "aperture-pilot",
    widget_key: "pilot-widget-key-change-me",
    customer_name: "Electron E2E Customer",
    language: "hi-en",
    initial_message: "Mera order delayed hai, please check.",
  }),
});
if (!chatStart.ok) throw new Error(`Could not create E2E chat: ${chatStart.status}`);
const chat = await chatStart.json();
const supervisorLogin = await fetch(`${apiBase}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "supervisor@pilot.example", password }) }).then((response) => response.json());
const createInbound = (name, phone) => fetch(`${apiBase}/voice/calls/simulate-inbound`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${supervisorLogin.access_token}` }, body: JSON.stringify({ phone, customer_name: name, language: "en" }) }).then((response) => response.json());
const rejectedInbound = await createInbound("Reject control test", "+919100000001");
const acceptedInbound = await createInbound("Accept control test", "+919100000002");

const electronApp = await electron.launch({ args: ["."], cwd: appDir });
const window = await electronApp.firstWindow();
window.on("console", (message) => {
  if (message.type() === "error" || message.type() === "warning") failures.push(`console ${message.type()}: ${message.text()}`);
});
window.on("requestfailed", (request) => {
  if (request.url().startsWith("blob:") && request.failure()?.errorText === "net::ERR_ABORTED") return;
  failures.push(`network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`);
});

try {
  await window.getByLabel("Work email").fill("agent1@pilot.example");
  await window.getByLabel("Password").fill(password);
  await window.getByRole("button", { name: /Enter workspace/ }).click();
  await window.getByText("AGENT WORKSPACE").waitFor();
  await window.screenshot({ path: path.join(evidenceDir, "electron-agent-workspace.png") });

  await window.locator(`[data-conversation-id="${chat.conversation_id}"]`).getByRole("button", { name: "Accept" }).click();
  await window.getByText("Mera order delayed hai, please check.").waitFor();
  await window.getByLabel("Message customer").fill("I can help. I am checking the order reference now.");
  await window.getByRole("button", { name: "Send message" }).click();
  await window.getByText("I can help. I am checking the order reference now.").waitFor();
  await window.screenshot({ path: path.join(evidenceDir, "electron-active-conversation.png") });

  const customerMessages = await fetch(`${apiBase}/public/chat/${chat.conversation_id}/messages`, {
    headers: { "X-Chat-Session": chat.session_token },
  }).then((response) => response.json());
  if (!customerMessages.some((message) => message.content === "I can help. I am checking the order reference now.")) {
    throw new Error("Agent reply was not visible to the customer session");
  }

  await window.getByRole("button", { name: /Complete wrap-up/ }).click();
  await window.getByText("Start a voice interaction").waitFor();

  const rejectedQueueItem = window.locator(`[data-conversation-id="${rejectedInbound.conversation.id}"]`);
  await rejectedQueueItem.getByText("Inbound voice call").waitFor();
  await rejectedQueueItem.getByRole("button", { name: "Reject" }).click();
  await rejectedQueueItem.waitFor({ state: "detached" });
  await window.locator(`[data-conversation-id="${acceptedInbound.conversation.id}"]`).getByRole("button", { name: "Accept" }).click();
  await window.getByText("Connected", { exact: true }).waitFor();
  await window.getByRole("button", { name: "Mute" }).click();
  await window.getByRole("button", { name: "Unmute" }).waitFor();
  await window.getByRole("button", { name: "Hold" }).click();
  await window.getByText("On hold", { exact: true }).waitFor();
  await window.getByRole("button", { name: "Resume" }).click();
  await window.getByText("Connected", { exact: true }).waitFor();
  await Promise.all([
    window.waitForResponse((response) => response.url().endsWith(`/voice/calls/${acceptedInbound.conversation.id}/control`) && response.request().postData()?.includes('"action":"transfer"')),
    window.getByRole("button", { name: "Transfer" }).click(),
  ]);
  await window.getByRole("button", { name: "Hang up" }).click();
  await window.getByText("Call complete", { exact: true }).waitFor();
  // A queue-only simulated call has no media and must not fabricate a
  // transcript, recording, guidance, or QA. The strict SIP test owns those
  // evidence assertions with two real human speech tracks.
  await window.screenshot({ path: path.join(evidenceDir, "electron-voice-evidence.png") });
  await window.getByRole("button", { name: /Complete wrap-up/ }).click();
  await window.getByText("Start a voice interaction").waitFor();

  await window.getByLabel("Customer phone").fill("+919999999999");
  await window.getByLabel("Call language").selectOption("en");
  await window.getByRole("button", { name: "Start call" }).click();
  await window.getByText("Connected", { exact: true }).waitFor();
  await window.getByRole("button", { name: "Hang up" }).click();
  await window.getByText("Call complete", { exact: true }).waitFor();
  await window.getByRole("button", { name: /Complete wrap-up/ }).click();
  await window.getByText("Start a voice interaction").waitFor();

  const fit = await window.evaluate(() => ({
    width: innerWidth,
    height: innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    scrollHeight: document.documentElement.scrollHeight,
  }));
  if (fit.scrollWidth > fit.width || fit.scrollHeight > fit.height) throw new Error(`Electron shell overflowed: ${JSON.stringify(fit)}`);
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({ ok: true, title: await window.title(), fit, chatId: chat.conversation_id, rejectedInboundId: rejectedInbound.conversation.id, acceptedInboundId: acceptedInbound.conversation.id }));
} finally {
  await electronApp.close();
}
