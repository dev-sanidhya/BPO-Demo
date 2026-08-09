import { _electron as electron, chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const appDir = path.resolve(import.meta.dirname, "..");
const repoDir = path.resolve(appDir, "..", "..");
const apiBase = process.env.PLATFORM_API_URL || "http://127.0.0.1:18080";
const customerUrl = process.env.SIP_CUSTOMER_URL || "http://127.0.0.1:18082/?ext=1003&pass=changeme1003&assist=0";
const password = process.env.PILOT_PASSWORD || "PilotTest123!";
const evidenceDir = path.join(repoDir, "artifacts", "ui");
await mkdir(evidenceDir, { recursive: true });

const login = await fetch(`${apiBase}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "agent1@pilot.example", password }) });
if (!login.ok) throw new Error(`Agent preflight login failed: ${login.status}`);
const { access_token: token } = await login.json();
const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
for (const conversation of await fetch(`${apiBase}/conversations`, { headers }).then((response) => response.json())) {
  if (!["active", "wrap_up"].includes(conversation.status)) continue;
  if (conversation.channel === "voice") {
    const session = await fetch(`${apiBase}/voice/calls/${conversation.id}`, { headers }).then((response) => response.json());
    if (session.session.state !== "ended") await fetch(`${apiBase}/voice/calls/${conversation.id}/control`, { method: "POST", headers, body: JSON.stringify({ action: "hangup" }) });
  }
  await fetch(`${apiBase}/conversations/${conversation.id}/wrap-up`, { method: "POST", headers, body: JSON.stringify({ disposition: "sip_e2e_preflight", summary: "Closed before carrier-free SIP verification." }) });
}

const mediaArgs = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"];
const browser = await chromium.launch({ channel: "chrome", headless: true, args: mediaArgs });
const customerContext = await browser.newContext({ permissions: ["microphone"] });
const customer = await customerContext.newPage();
const failures = [];
customer.on("console", (message) => { if (["error", "warning"].includes(message.type())) failures.push(`customer console ${message.type()}: ${message.text()}`); });
customer.on("requestfailed", (request) => failures.push(`customer network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`));
const electronApp = await electron.launch({
  args: [".", ...mediaArgs],
  cwd: appDir,
  env: { ...process.env, PLATFORM_SIP_ENABLED: "true", PLATFORM_SIP_WS_URL: "ws://127.0.0.1:8088/ws", PLATFORM_SIP_HOST: "127.0.0.1", PLATFORM_SIP_EXTENSION: "1001", PLATFORM_SIP_PASSWORD: "changeme1001" },
});
const agent = await electronApp.firstWindow();
agent.on("console", (message) => { if (["error", "warning"].includes(message.type())) failures.push(`console ${message.type()}: ${message.text()}`); });
agent.on("requestfailed", (request) => { if (!request.url().startsWith("blob:")) failures.push(`network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`); });

try {
  await customer.goto(customerUrl, { waitUntil: "domcontentloaded" });
  await customer.getByText("SIP: registered as 1003").waitFor({ timeout: 20_000 });
  await agent.getByLabel("Work email").fill("agent1@pilot.example");
  await agent.getByLabel("Password").fill(password);
  await agent.getByRole("button", { name: /Enter workspace/ }).click();
  await agent.getByText("SIP 1001").waitFor({ timeout: 20_000 });
  await agent.getByText("Start a voice interaction").waitFor();
  await agent.getByLabel("Customer phone").fill("2003");
  await agent.getByLabel("Start call").click();
  await agent.getByText("Two-party media").waitFor({ timeout: 20_000 });
  const channels = execFileSync("docker", ["exec", "bpo-demo-asterisk-1", "asterisk", "-rx", "core show channels concise"], { encoding: "utf8" });
  if (!channels.includes("PJSIP/1003")) throw new Error(`Asterisk did not expose the live 1003 channel:\n${channels}`);
  await agent.getByRole("button", { name: "Mute" }).click();
  await agent.getByRole("button", { name: "Unmute" }).waitFor();
  await agent.getByRole("button", { name: "Hold" }).click();
  await agent.getByText("On hold", { exact: true }).waitFor();
  await agent.getByRole("button", { name: "Resume" }).click();
  await agent.getByRole("button", { name: "Hang up" }).click();
  await agent.getByText("Call complete", { exact: true }).waitFor({ timeout: 30_000 });
  await customer.getByText("SIP: registered as 1003").waitFor();
  await agent.screenshot({ path: path.join(evidenceDir, "electron-live-sip-call.png") });
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({ ok: true, registered: ["1001", "1003"], dialed: "2003", asteriskMediaChannel: "PJSIP/1003", callState: "ended" }));
} catch (error) {
  console.error(JSON.stringify({ agentSip: await agent.locator("#sip-status").textContent().catch(() => null), customerSip: await customer.locator("#sip-status").textContent().catch(() => null), failures }, null, 2));
  throw error;
} finally {
  await electronApp.close();
  await customerContext.close();
  await browser.close();
}
