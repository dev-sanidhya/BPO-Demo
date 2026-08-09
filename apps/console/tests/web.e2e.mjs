import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.CONSOLE_URL || "http://127.0.0.1:18081";
const password = process.env.PILOT_PASSWORD || "PilotTest123!";
const evidenceDir = path.resolve(import.meta.dirname, "..", "..", "..", "artifacts", "ui");
await mkdir(evidenceDir, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: false });
const failures = [];
const watch = (page, label) => {
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) failures.push(`${label} console ${message.type()}: ${message.text()}`);
  });
  page.on("requestfailed", (request) => failures.push(`${label} network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`));
};

try {
  const desktop = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const portal = await desktop.newPage();
  await portal.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await portal.getByLabel("Password").fill("wrong-password");
  await portal.getByRole("button", { name: /Enter workspace/ }).click();
  await portal.getByText("Invalid email or password").waitFor();
  watch(portal, "portal");
  await portal.getByLabel("Password").fill(password);
  await portal.getByRole("button", { name: /Enter workspace/ }).click();
  await portal.getByText("OPERATIONS COMMAND").waitFor();
  await portal.screenshot({ path: path.join(evidenceDir, "web-supervisor-dashboard.png") });
  const desktopFit = await portal.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (desktopFit.scrollWidth > desktopFit.width) throw new Error(`Desktop portal overflow: ${JSON.stringify(desktopFit)}`);
  await portal.getByRole("button", { name: /Conversations/ }).click();
  await portal.getByRole("heading", { name: "Conversations" }).waitFor();
  await portal.getByRole("button", { name: /Quality/ }).click();
  await portal.getByRole("heading", { name: "Quality review" }).waitFor();
  await portal.getByRole("button", { name: "Save review" }).waitFor();
  await portal.getByText("Professional greeting").waitFor();
  await portal.getByLabel("Reviewed score").fill("91");
  await portal.getByLabel("Review reason").fill("Confirmed against the synchronized recording and evidence spans.");
  await portal.getByRole("button", { name: "Save review" }).click();
  await portal.getByText("Human reviewed").first().waitFor();
  await portal.getByText(/Original automatic score: \d+/).waitFor();
  await portal.screenshot({ path: path.join(evidenceDir, "web-quality-review.png") });
  await portal.getByRole("button", { name: /Reports/ }).click();
  await portal.getByRole("heading", { name: "Reports & economics" }).waitFor();
  const [csvDownload] = await Promise.all([portal.waitForEvent("download"), portal.getByRole("button", { name: /CSV/ }).click()]);
  const [pdfDownload] = await Promise.all([portal.waitForEvent("download"), portal.getByRole("button", { name: /PDF/ }).click()]);
  if (!csvDownload.suggestedFilename().endsWith(".csv") || !pdfDownload.suggestedFilename().endsWith(".pdf")) throw new Error("Report downloads used incorrect file types");
  await portal.screenshot({ path: path.join(evidenceDir, "web-reports-costs.png") });

  const admin = await desktop.newPage();
  watch(admin, "admin");
  await admin.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await admin.getByLabel("Work email").fill("admin@pilot.example");
  await admin.getByLabel("Password").fill(password);
  await admin.getByRole("button", { name: /Enter workspace/ }).click();
  await admin.getByRole("button", { name: /Settings/ }).click();
  await admin.getByRole("heading", { name: "Platform configuration" }).waitFor();
  await admin.getByText(/Customer content stays inside/).waitFor();
  await admin.getByLabel("Campaign name").waitFor();
  await admin.getByRole("button", { name: "Save operating model" }).click();
  await admin.getByText("Pilot configuration saved and audited.").waitFor();
  await admin.getByLabel("New user name").fill("E2E Provisioned Agent");
  await admin.getByLabel("New user email").fill(`e2e.agent.${Date.now()}@pilot.example`);
  await admin.getByRole("button", { name: "Create user" }).click();
  await admin.getByText("User created and assigned to the pilot queue.").waitFor();
  await admin.screenshot({ path: path.join(evidenceDir, "web-admin-configuration.png") });

  const client = await desktop.newPage();
  watch(client, "client");
  await client.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await client.getByLabel("Work email").fill("client@pilot.example");
  await client.getByLabel("Password").fill(password);
  await client.getByRole("button", { name: /Enter workspace/ }).click();
  await client.getByText("OPERATIONS COMMAND").waitFor();
  await client.getByRole("button", { name: /Quality/ }).click();
  await client.getByRole("heading", { name: "Quality review" }).waitFor();
  if (await client.getByRole("button", { name: "Save review" }).count()) throw new Error("Client viewer received QA override controls");

  const mobile = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const widget = await mobile.newPage();
  watch(widget, "widget");
  await widget.goto(`${baseUrl}/?widget=1`, { waitUntil: "domcontentloaded" });
  await widget.getByLabel("Your name").fill("Mobile Customer");
  await widget.getByLabel("Preferred language").selectOption("mr");
  await widget.getByLabel("Initial message").fill("माझ्या ऑर्डरची स्थिती काय आहे?");
  const [chatStartResponse] = await Promise.all([
    widget.waitForResponse((response) => response.url().includes("/api/public/chat/start") && response.request().method() === "POST"),
    widget.getByRole("button", { name: /Start conversation/ }).click(),
  ]);
  const chatStart = await chatStartResponse.json();
  await widget.getByText("Connected to support").waitFor();
  await widget.screenshot({ path: path.join(evidenceDir, "mobile-customer-widget.png") });
  const mobileFit = await widget.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (mobileFit.scrollWidth > mobileFit.width) throw new Error(`Mobile widget overflow: ${JSON.stringify(mobileFit)}`);

  const loginResponse = await fetch(`${baseUrl}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "agent1@pilot.example", password }) });
  if (!loginResponse.ok) throw new Error(`Agent API login failed: ${loginResponse.status}`);
  const { access_token: agentToken } = await loginResponse.json();
  const agentHeaders = { Authorization: `Bearer ${agentToken}`, "Content-Type": "application/json" };
  for (const [pathSuffix, body] of [
    [`conversations/${chatStart.conversation_id}/claim`, undefined],
    [`conversations/${chatStart.conversation_id}/messages`, { content: "तुमची ऑर्डर उद्या पोहोचेल. मी पुष्टी पाठवली आहे." }],
    [`conversations/${chatStart.conversation_id}/wrap-up`, { disposition: "resolved", summary: "Delivery date confirmed in Marathi." }],
  ]) {
    const response = await fetch(`${baseUrl}/api/${pathSuffix}`, { method: "POST", headers: agentHeaders, body: body ? JSON.stringify(body) : undefined });
    if (!response.ok) throw new Error(`Agent API step ${pathSuffix} failed: ${response.status} ${await response.text()}`);
  }
  await widget.getByText("Conversation resolved").waitFor({ timeout: 8_000 });
  await widget.getByRole("button", { name: "Rate 5" }).click();
  await widget.getByText("Your recorded CSAT is 5/5.").waitFor();
  await widget.screenshot({ path: path.join(evidenceDir, "mobile-customer-survey.png") });

  await new Promise((resolve) => setTimeout(resolve, 2500));
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({ ok: true, desktopFit, mobileFit, pages: [await portal.title(), await widget.title()] }));
  await mobile.close();
  await desktop.close();
} finally {
  await browser.close();
}
