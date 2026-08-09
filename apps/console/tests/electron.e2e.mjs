import { _electron as electron } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const appDir = path.resolve(import.meta.dirname, "..");
const evidenceDir = path.resolve(appDir, "..", "..", "artifacts", "ui");
const apiBase = process.env.PLATFORM_API_URL || "http://127.0.0.1:18080";
const password = process.env.PILOT_PASSWORD || "PilotTest123!";
const failures = [];

await mkdir(evidenceDir, { recursive: true });

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

const electronApp = await electron.launch({ args: ["."], cwd: appDir });
const window = await electronApp.firstWindow();
window.on("console", (message) => {
  if (message.type() === "error" || message.type() === "warning") failures.push(`console ${message.type()}: ${message.text()}`);
});
window.on("requestfailed", (request) => failures.push(`network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`));

try {
  await window.getByLabel("Work email").fill("agent1@pilot.example");
  await window.getByLabel("Password").fill(password);
  await window.getByRole("button", { name: /Enter workspace/ }).click();
  await window.getByText("AGENT WORKSPACE").waitFor();
  await window.screenshot({ path: path.join(evidenceDir, "electron-agent-workspace.png") });

  await window.getByRole("button", { name: "Accept" }).first().click();
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

  await window.getByRole("button", { name: /Resolve/ }).click();
  await window.getByText("Ready for the next conversation").waitFor();

  const fit = await window.evaluate(() => ({
    width: innerWidth,
    height: innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    scrollHeight: document.documentElement.scrollHeight,
  }));
  if (fit.scrollWidth > fit.width || fit.scrollHeight > fit.height) throw new Error(`Electron shell overflowed: ${JSON.stringify(fit)}`);
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({ ok: true, title: await window.title(), fit, conversationId: chat.conversation_id }));
} finally {
  await electronApp.close();
}
