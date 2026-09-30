// ORDER_013 receipts: full-page screenshots of wknipe.com pages in light and dark mode at 1280px and 390px, via headless
// Chrome and the DevTools protocol (no npm deps). Charts render lazily on scroll, so each page is scrolled through first.
//   node scripts/site/screenshots.mjs [--base https://wknipe.com] [--out handoffs/screens_013]
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const BASE = arg("--base", "https://wknipe.com"), OUT = arg("--out", "handoffs/screens_013");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PAGES = (arg("--pages", "home=/,market=/x402/,prices=/x402/prices/,seller=/x402/sellers/0xffde1acbac169f822dabc3d97d6d7127dcae6003,design=/design/")).split(",").map((s) => s.split("="));
const MODES = ["light", "dark"], WIDTHS = [1280, 390];
mkdirSync(OUT, { recursive: true });
const port = 9333, prof = mkdtempSync(join(tmpdir(), "wkshot-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, "--hide-scrollbars", "--no-first-run", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let list;
for (let i = 0; i < 50 && !list; i++) { try { list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); } catch { await sleep(200); } }
const ws = new WebSocket(list.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(), waiters = [];
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } else if (d.method) waiters.forEach((w) => w(d)); };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const once = (name) => new Promise((r) => { const w = (d) => { if (d.method === name) { waiters.splice(waiters.indexOf(w), 1); r(d); } }; waiters.push(w); });
await send("Page.enable");
const eval_ = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const shots = [];
for (const [name, path] of PAGES) for (const mode of MODES) for (const width of WIDTHS) {
  await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 500 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: mode }] });
  const loaded = once("Page.loadEventFired");
  await send("Page.navigate", { url: BASE + path });
  await loaded; await sleep(1500);
  await eval_(`(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise(r => setTimeout(r, 250)); } scrollTo(0, 0); await new Promise(r => setTimeout(r, 1200)); return 1; })()`);
  const h = Math.min(await eval_("document.documentElement.scrollHeight"), 9000);
  await send("Emulation.setDeviceMetricsOverride", { width, height: h, deviceScaleFactor: 1, mobile: width < 500 });
  await sleep(700);
  const overflow = await eval_("document.documentElement.scrollWidth > window.innerWidth");
  const shot = await send("Page.captureScreenshot", { format: "jpeg", quality: 70, captureBeyondViewport: false });
  const f = join(OUT, `${name}_${mode}_${width}.jpg`);
  writeFileSync(f, Buffer.from(shot.result.data, "base64"));
  shots.push({ page: name, mode, width, file: f, height: h, horizontal_overflow: overflow });
  console.log(f, h + "px", overflow ? "HORIZONTAL OVERFLOW" : "");
}
writeFileSync(join(OUT, "index.json"), JSON.stringify(shots, null, 1));
ws.close(); chrome.kill();
