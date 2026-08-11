import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.CONSOLE_URL || "http://127.0.0.1:18081";
const password = process.env.PILOT_PASSWORD || "PilotTest123!";
const evidenceDir = path.resolve(import.meta.dirname, "..", "..", "..", "artifacts", "ui");
await mkdir(evidenceDir, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const failures = [];
const watch = (page, label) => {
  page.on("console", (message) => { if (["error", "warning"].includes(message.type())) failures.push(`${label} console ${message.type()}: ${message.text()}`); });
  page.on("requestfailed", (request) => failures.push(`${label} network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`));
};

async function signIn(page, email) {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /Enter workspace/ }).click();
  await page.getByText("OPERATIONS COMMAND").waitFor();
}

try {
  const desktop = await browser.newContext({ viewport: { width: 1600, height: 900 }, acceptDownloads: true });
  const portal = await desktop.newPage();
  watch(portal, "supervisor");
  await signIn(portal, "supervisor@pilot.example");
  await portal.getByRole("heading", { name: /Welcome, Demo/ }).waitFor();
  await portal.getByText("Recent interactions").waitFor();
  await portal.screenshot({ path: path.join(evidenceDir, "evidence-supervisor-overview.png") });
  const desktopFit = await portal.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (desktopFit.scrollWidth > desktopFit.width) throw new Error(`Desktop portal overflow: ${JSON.stringify(desktopFit)}`);

  await portal.getByRole("button", { name: /Conversations/ }).click();
  await portal.getByRole("heading", { name: "Conversations" }).waitFor();
  await portal.locator(".conversation-index > button").filter({ hasText: "voice" }).first().click();
  await portal.getByText("Published human-recorded simulated call").waitFor();
  await portal.getByText("CC BY 4.0").waitFor();
  const sourceLink = portal.getByRole("link", { name: /Stanford\/Gridspace HarperValleyBank/ });
  if (!(await sourceLink.getAttribute("href"))?.includes("gridspace-stanford-harper-valley")) throw new Error("Conversation provenance link is incorrect");
  await portal.screenshot({ path: path.join(evidenceDir, "evidence-conversation-provenance.png") });

  await portal.getByRole("button", { name: /Quality/ }).click();
  await portal.getByRole("heading", { name: "Quality review" }).waitFor();
  await portal.locator(".score-list > button").first().waitFor();
  const evaluationCount = await portal.locator(".score-list > button").count();
  if (evaluationCount < 8) throw new Error(`Expected a varied Groq voice corpus, found ${evaluationCount} evaluations`);
  await portal.getByText("Professional greeting and identification").waitFor();
  await portal.getByRole("button", { name: "Save review" }).waitFor();
  await portal.screenshot({ path: path.join(evidenceDir, "evidence-groq-quality.png") });

  await portal.getByRole("button", { name: /Reports/ }).click();
  await portal.getByRole("heading", { name: "Reports & economics" }).waitFor();
  await portal.getByRole("heading", { name: "Agent comparison", exact: true }).waitFor();
  await portal.getByRole("heading", { name: "Quality & risk", exact: true }).waitFor();
  await portal.getByRole("heading", { name: "Usage-based cost estimate", exact: true }).waitFor();
  await portal.getByText("this is not an invoice", { exact: false }).waitFor();
  const [csvDownload] = await Promise.all([portal.waitForEvent("download"), portal.getByRole("button", { name: /CSV/ }).click()]);
  const [pdfDownload] = await Promise.all([portal.waitForEvent("download"), portal.getByRole("button", { name: /PDF/ }).click()]);
  if (!csvDownload.suggestedFilename().endsWith(".csv") || !pdfDownload.suggestedFilename().endsWith(".pdf")) throw new Error("Report downloads used incorrect file types");
  await portal.screenshot({ path: path.join(evidenceDir, "evidence-reports-costs.png") });

  const admin = await desktop.newPage();
  watch(admin, "admin");
  await signIn(admin, "admin@pilot.example");
  await admin.getByRole("button", { name: /Settings/ }).click();
  await admin.getByRole("heading", { name: "Platform configuration" }).waitFor();
  await admin.getByLabel("Campaign name").waitFor();
  if ((await admin.getByLabel("Campaign name").inputValue()) !== "HarperValleyBank Evidence Demo") throw new Error("Evidence campaign was not loaded in configuration");
  await admin.getByText("External AI mode is enabled.").waitFor();
  await admin.screenshot({ path: path.join(evidenceDir, "evidence-admin-configuration.png") });

  const client = await desktop.newPage();
  watch(client, "client");
  await signIn(client, "client@pilot.example");
  await client.getByRole("button", { name: /Quality/ }).click();
  await client.getByRole("heading", { name: "Quality review" }).waitFor();
  if (await client.getByRole("button", { name: "Save review" }).count()) throw new Error("Client viewer received QA override controls");

  const mobile = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const mobilePortal = await mobile.newPage();
  watch(mobilePortal, "mobile portal");
  await signIn(mobilePortal, "supervisor@pilot.example");
  await mobilePortal.screenshot({ path: path.join(evidenceDir, "mobile-evidence-overview.png"), fullPage: true });
  const mobilePortalFit = await mobilePortal.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (mobilePortalFit.scrollWidth > mobilePortalFit.width) throw new Error(`Mobile portal overflow: ${JSON.stringify(mobilePortalFit)}`);

  const widget = await mobile.newPage();
  watch(widget, "widget");
  await widget.goto(`${baseUrl}/?widget=1`, { waitUntil: "domcontentloaded" });
  await widget.getByText("Support channel ready").waitFor();
  await widget.getByRole("button", { name: /Start conversation/ }).waitFor();
  await widget.screenshot({ path: path.join(evidenceDir, "mobile-customer-widget-ready.png") });
  const widgetFit = await widget.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (widgetFit.scrollWidth > widgetFit.width) throw new Error(`Mobile widget overflow: ${JSON.stringify(widgetFit)}`);

  await new Promise((resolve) => setTimeout(resolve, 1000));
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({ ok: true, desktopFit, mobilePortalFit, widgetFit, groqEvaluations: evaluationCount }));
  await mobile.close();
  await desktop.close();
} finally {
  await browser.close();
}
