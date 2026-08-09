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

  const client = await desktop.newPage();
  watch(client, "client");
  await client.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await client.getByLabel("Work email").fill("client@pilot.example");
  await client.getByLabel("Password").fill(password);
  await client.getByRole("button", { name: /Enter workspace/ }).click();
  await client.getByText("OPERATIONS COMMAND").waitFor();

  const mobile = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const widget = await mobile.newPage();
  watch(widget, "widget");
  await widget.goto(`${baseUrl}/?widget=1`, { waitUntil: "domcontentloaded" });
  await widget.getByLabel("Your name").fill("Mobile Customer");
  await widget.getByLabel("Preferred language").selectOption("mr");
  await widget.getByLabel("Initial message").fill("माझ्या ऑर्डरची स्थिती काय आहे?");
  await widget.getByRole("button", { name: /Start conversation/ }).click();
  await widget.getByText("Connected to support").waitFor();
  await widget.screenshot({ path: path.join(evidenceDir, "mobile-customer-widget.png") });
  const mobileFit = await widget.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (mobileFit.scrollWidth > mobileFit.width) throw new Error(`Mobile widget overflow: ${JSON.stringify(mobileFit)}`);

  await new Promise((resolve) => setTimeout(resolve, 2500));
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({ ok: true, desktopFit, mobileFit, pages: [await portal.title(), await widget.title()] }));
  await mobile.close();
  await desktop.close();
} finally {
  await browser.close();
}
