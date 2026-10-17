/** Export pitch/final/slides_final.html to PDF + per-slide PNG previews, with an overflow check.
 *  Usage (from the repository root): node pitch/final/export_final.mjs
 *  No npm dependencies; set RELEASEPROOF_BROWSER if Chrome/Edge are not in the default paths. */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const browser = process.env.RELEASEPROOF_BROWSER || [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/chromium", "/usr/bin/google-chrome",
].find(existsSync);
if (!browser) throw new Error("Set RELEASEPROOF_BROWSER to an installed Chromium browser.");
const tempRoot = os.tmpdir();
await mkdir(tempRoot, { recursive: true });
const profile = await mkdtemp(path.join(tempRoot, "releaseproof-final-"));
const previews = path.join(here, "previews");
await mkdir(previews, { recursive: true });
const child = spawn(browser, ["--headless=new", "--no-first-run", "--no-default-browser-check",
  "--allow-file-access-from-files", "--remote-debugging-port=0", `--user-data-dir=${profile}`],
{ stdio: ["ignore", "ignore", "pipe"] });

let socket;
let sequence = 0;
const pending = new Map();
const timer = setTimeout(() => {
  child.kill();
  process.exitCode = 1;
  for (const entry of pending.values()) entry.reject(new Error("Browser export timeout"));
  socket?.close();
}, 60000);

function call(method, params = {}, sessionId) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
}

try {
  const endpoint = await new Promise((resolve, reject) => {
    let log = "";
    child.on("error", reject);
    child.on("exit", () => reject(new Error("Browser exited before debugging endpoint")));
    child.stderr.on("data", chunk => {
      log += chunk;
      const match = /DevTools listening on (ws:\/\/\S+)/.exec(log);
      if (match) resolve(match[1]);
    });
  });
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    const entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    if (message.error) entry.reject(new Error(message.error.message));
    else entry.resolve(message.result);
  });
  const { targetId } = await call("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await call("Target.attachToTarget", { targetId, flatten: true });
  await call("Page.enable", {}, sessionId);
  await call("Emulation.setDeviceMetricsOverride",
    { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false }, sessionId);
  await call("Page.navigate",
    { url: pathToFileURL(path.join(here, "slides_final.html")).href }, sessionId);
  await call("Runtime.evaluate", { expression: `new Promise(resolve => {
    const ready = async () => { await document.fonts.ready;
      await Promise.all([...document.images].map(i => i.decode())); resolve(true); };
    if (document.readyState === 'complete') ready(); else addEventListener('load', ready, {once:true});
  })`, awaitPromise: true, returnByValue: true }, sessionId);
  const audit = await call("Runtime.evaluate", { expression: `(() => {
    const slides = [...document.querySelectorAll('.slide')];
    return { pages: slides.length, placeholders: document.body.innerText.includes('[['),
      overflow: slides.flatMap(slide => {
        const b = slide.getBoundingClientRect();
        const f = slide.querySelector('.foot').getBoundingClientRect();
        return [...slide.querySelectorAll('*')].filter(el => {
          const r = el.getBoundingClientRect();
          return r.width && r.height && (r.bottom > b.bottom + 1 || r.right > b.right + 1
            || (!el.closest('.foot') && r.bottom > f.top + 1));
        }).map(el => slide.id + ':' + el.tagName + ':' + el.textContent.trim().slice(0, 50));
      }) };
  })()`, returnByValue: true }, sessionId);
  const layout = audit.result.value;
  const pdf = await call("Page.printToPDF",
    { printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false }, sessionId);
  await writeFile(path.join(here, "slides_final.pdf"), Buffer.from(pdf.data, "base64"));
  for (let index = 0; index < layout.pages; index++) {
    const box = await call("Runtime.evaluate", { expression:
      `JSON.stringify(document.querySelectorAll('.slide')[${index}].getBoundingClientRect())`,
    returnByValue: true }, sessionId);
    const r = JSON.parse(box.result.value);
    const shot = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: r.x, y: r.y, width: r.width, height: r.height, scale: 0.5 } }, sessionId);
    await writeFile(path.join(previews, `slide-${String(index + 1).padStart(2, "0")}.png`),
      Buffer.from(shot.data, "base64"));
  }
  console.log(JSON.stringify(layout, null, 2));
  if (layout.placeholders || layout.overflow.length) process.exitCode = 1;
} finally {
  clearTimeout(timer);
  socket?.close();
  child.kill();
}
