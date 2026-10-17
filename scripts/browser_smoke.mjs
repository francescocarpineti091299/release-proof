/** Real anonymous browser journeys. No mocked API, insecure TLS flags or assessment creation. */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import path from "node:path";

const base = process.argv[2]?.replace(/\/$/, "");
const parsed = base && new URL(base);
if (!parsed || parsed.protocol !== "https:" || parsed.username || parsed.password) {
  throw new Error("Supply the public HTTPS viewer URL without credentials.");
}
const output = path.resolve(process.argv[3] || "docs/browser-smoke");
const browser = process.env.RELEASEPROOF_BROWSER || [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/chromium", "/usr/bin/google-chrome",
].find(existsSync);
if (!browser) throw new Error("Set RELEASEPROOF_BROWSER to an installed Chromium browser.");
const temp = process.platform === "win32"
  ? path.join(process.env.LOCALAPPDATA, "Temp", "opencode") : process.env.TMPDIR || "/tmp";
await mkdir(output, { recursive: true });
const profile = await mkdtemp(path.join(temp, "releaseproof-browser-"));
const child = spawn(browser, ["--headless=new", "--no-first-run", "--no-default-browser-check",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`], { stdio: ["ignore", "ignore", "pipe"] });
const pending = new Map();
const problems = [];
const requests = [];
let socket;
let nextId = 0;
const deadline = setTimeout(() => {
  for (const p of pending.values()) p.reject(new Error("Browser smoke timeout"));
  child.kill(); socket?.close();
}, 120000);
const call = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const id = ++nextId;
  pending.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
});

try {
  const endpoint = await new Promise((resolve, reject) => {
    let log = "";
    child.on("error", reject);
    child.on("exit", () => reject(new Error("Browser exited before debugging endpoint")));
    child.stderr.on("data", chunk => {
      log += chunk;
      const found = /DevTools listening on (ws:\/\/\S+)/.exec(log);
      if (found) resolve(found[1]);
    });
  });
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.method === "Network.loadingFailed") problems.push(message.params.errorText);
    if (message.method === "Runtime.exceptionThrown") {
      problems.push(message.params.exceptionDetails.text);
    }
    if (message.method === "Network.requestWillBeSent") {
      const request = message.params.request;
      if (request.url.startsWith(base)) requests.push({ url: request.url, method: request.method });
    }
    if (message.method === "Network.responseReceived") {
      const response = message.params.response;
      if (response.url.startsWith(base) && response.status >= 400) {
        problems.push(`${response.status} ${response.url}`);
      }
    }
    const p = pending.get(message.id);
    if (!p) return;
    pending.delete(message.id);
    if (message.error) p.reject(new Error(message.error.message)); else p.resolve(message.result);
  });
  const { targetId } = await call("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await call("Target.attachToTarget", { targetId, flatten: true });
  for (const method of ["Page.enable", "Runtime.enable", "Network.enable"]) await call(method, {}, sessionId);
  await call("Emulation.setDeviceMetricsOverride", {
    width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false,
  }, sessionId);
  const evaluate = async expression => {
    const result = await call("Runtime.evaluate", {
      expression, returnByValue: true, awaitPromise: true,
    }, sessionId);
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  };
  const ready = expression => evaluate(`new Promise((resolve,reject) => {
    const start=Date.now(); const timer=setInterval(() => {
      if (${expression}) { clearInterval(timer); resolve(true); }
      else if(Date.now()-start>30000) { clearInterval(timer); reject(new Error('UI not ready')); }
    },100);
  })`);
  const checks = [];
  for (const family of ["MCUboot", "wolfBoot"]) {
    await call("Page.navigate", { url: base + "/" }, sessionId);
    await ready(`document.body?.innerText.includes('SUPPORTED') &&
      [...document.querySelectorAll('button')].some(b=>b.innerText.includes(${JSON.stringify(family)}))`);
    const password = await evaluate("!!document.querySelector('input[type=password]')");
    if (password) throw new Error("Judging demo unexpectedly asks for a password");
    await evaluate(`[...document.querySelectorAll('button')].find(b=>
      b.innerText.includes(${JSON.stringify(family)}) && b.innerText.includes('SUPPORTED')).click()`);
    await ready("document.body.innerText.includes('What change do you want to ship?')");
    await evaluate("[...document.querySelectorAll('button')].find(b=>b.innerText.includes('Choose')).click()");
    await ready("document.body.innerText.includes('Review the planned checks')");
    const canRun = await evaluate("[...document.querySelectorAll('button')].some(b=>b.innerText.includes('Run assessment')&&!b.disabled)");
    if (!canRun) throw new Error("Run button unavailable for " + family);
    await evaluate("document.querySelector('h3').scrollIntoView({block:'start',behavior:'instant'})");
    const shot = await call("Page.captureScreenshot", { format: "png" }, sessionId);
    await writeFile(path.join(output, `${family.toLowerCase()}-review.png`), Buffer.from(shot.data, "base64"));
    checks.push({ family, anonymous: true, steps: 3, run_button_enabled: true });
  }
  const mutations = requests.filter(r => r.method !== "GET" && r.method !== "HEAD");
  if (problems.length || mutations.length) throw new Error(JSON.stringify({ problems, mutations }));
  const report = { base, checked_at: new Date().toISOString(),
    browser: (await call("Browser.getVersion")).product, checks,
    network_errors: problems, mutation_count: mutations.length, passed: true };
  await writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
} finally {
  clearTimeout(deadline); socket?.close(); child.kill();
}
