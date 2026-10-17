/** Reproducible pitch exports with source/output hashes and layout checks. No npm dependencies. */
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const browser = process.env.RELEASEPROOF_BROWSER || [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/chromium", "/usr/bin/google-chrome",
].find(existsSync);
if (!browser) throw new Error("Set RELEASEPROOF_BROWSER to an installed Chromium browser.");
const tempRoot = process.platform === "win32"
  ? path.join(process.env.LOCALAPPDATA, "Temp", "opencode")
  : process.env.TMPDIR || "/tmp";
await mkdir(tempRoot, { recursive: true });
const profile = await mkdtemp(path.join(tempRoot, "releaseproof-pitch-"));
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
  async function page(source) {
    const { targetId } = await call("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await call("Target.attachToTarget", { targetId, flatten: true });
    await call("Page.enable", {}, sessionId);
    await call("Emulation.setDeviceMetricsOverride", {
      width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false,
    }, sessionId);
    await call("Page.navigate", { url: pathToFileURL(path.join(root, source)).href }, sessionId);
    const ready = await call("Runtime.evaluate", { expression: `new Promise(resolve => {
      const ready = async () => {
        await document.fonts.ready;
        await Promise.all([...document.images].map(image => image.decode()));
        resolve(true);
      };
      if(document.readyState === 'complete') ready();
      else window.addEventListener('load', ready, {once:true});
    })`, awaitPromise: true, returnByValue: true }, sessionId);
    if (ready.exceptionDetails) throw new Error("Pitch assets failed to load.");
    return sessionId;
  }
  const slides = await page("pitch/slides.html");
  const audit = await call("Runtime.evaluate", { expression: `(() => {
    const slides = [...document.querySelectorAll('.slide')];
    return {pages: slides.length, placeholders: document.body.innerText.includes('[['),
      overflow: slides.flatMap(slide => {
        const boundary = slide.getBoundingClientRect();
        const footer = slide.querySelector('.foot').getBoundingClientRect();
        return [...slide.querySelectorAll('*')].filter(el => {
          const r = el.getBoundingClientRect();
          return r.width && r.height && (r.bottom > boundary.bottom + 1 || r.right > boundary.right + 1
            || el.closest('.body') && r.bottom > footer.top + 1);
        }).map(el => slide.id + ':' + el.tagName + ':' + el.textContent.slice(0,60));
      })};
  })()`, returnByValue: true }, slides);
  const layout = audit.result.value;
  if (layout.pages !== 8 || layout.placeholders || layout.overflow.length) {
    throw new Error(`Pitch layout check failed: ${JSON.stringify(layout)}`);
  }
  const pdf = await call("Page.printToPDF", {
    printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false,
  }, slides);
  await writeFile(path.join(root, "pitch/slides.pdf"), Buffer.from(pdf.data, "base64"));
  for (let index = 0; index < layout.pages; index++) {
    const box = await call("Runtime.evaluate", { expression:
      `JSON.stringify(document.querySelectorAll('.slide')[${index}].getBoundingClientRect())`,
    returnByValue: true }, slides);
    const r = JSON.parse(box.result.value);
    const shot = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: r.x, y: r.y, width: r.width, height: r.height, scale: 0.5 } }, slides);
    await writeFile(path.join(profile, `slide-${index + 1}.png`), Buffer.from(shot.data, "base64"));
  }
  const cover = await page("pitch/cover.html");
  const png = await call("Page.captureScreenshot", { format: "png" }, cover);
  await writeFile(path.join(root, "pitch/cover.png"), Buffer.from(png.data, "base64"));
  const hashes = {};
  for (const name of ["slides.html", "slides.pdf", "cover.html", "cover.png"]) {
    hashes[name] = createHash("sha256").update(await readFile(path.join(root, "pitch", name))).digest("hex");
  }
  const report = { exported_at: new Date().toISOString(), browser: (await call("Browser.getVersion")).product,
    ...layout, sha256: hashes };
  await writeFile(path.join(root, "pitch/export-manifest.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({ ...report, preview_directory: profile }, null, 2));
} finally {
  clearTimeout(timer);
  socket?.close();
  child.kill();
}
