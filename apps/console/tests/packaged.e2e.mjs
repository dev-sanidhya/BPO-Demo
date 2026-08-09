import { _electron as electron } from "playwright";
import path from "node:path";

const appDir = path.resolve(import.meta.dirname, "..");
const executablePath = path.join(appDir, "release", "win-unpacked", "Aperture CX Agent.exe");
const password = process.env.PILOT_PASSWORD || "PilotTest123!";
const failures = [];
const electronApp = await electron.launch({ executablePath });
const window = await electronApp.firstWindow();

window.on("console", (message) => {
  if (["error", "warning"].includes(message.type())) failures.push(`console ${message.type()}: ${message.text()}`);
});
window.on("requestfailed", (request) => failures.push(`network: ${request.method()} ${request.url()} ${request.failure()?.errorText}`));

try {
  await window.getByLabel("Work email").fill("agent1@pilot.example");
  await window.getByLabel("Password").fill(password);
  await window.getByRole("button", { name: /Enter workspace/ }).click();
  await window.getByText("AGENT WORKSPACE").waitFor();
  await window.getByText("Start AI sample").waitFor();
  await window.getByText("Configured AI route", { exact: true }).waitFor();
  const fit = await window.evaluate(() => ({ width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight }));
  if (fit.scrollWidth > fit.width || fit.scrollHeight > fit.height) throw new Error(`Packaged shell overflowed: ${JSON.stringify(fit)}`);
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(JSON.stringify({ ok: true, executablePath, title: await window.title(), fit }));
} finally {
  await electronApp.close();
}
