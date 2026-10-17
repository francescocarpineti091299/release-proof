import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:net";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const reservation = createServer();
reservation.listen(0, "127.0.0.1");
await once(reservation, "listening");
const port = reservation.address().port;
await new Promise((done) => reservation.close(done));
const server = spawn(process.execPath, [resolve(".next/standalone/server.js")], {
  env: { ...process.env, HOSTNAME: "127.0.0.1", PORT: String(port), NODE_ENV: "production" },
  stdio: ["ignore", "pipe", "pipe"],
});
let logs = "";
server.stdout.on("data", (chunk) => { logs += chunk; });
server.stderr.on("data", (chunk) => { logs += chunk; });
const base = `http://127.0.0.1:${port}`;
try {
  let ready = false;
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(logs);
    try {
      const response = await fetch(base, { signal: AbortSignal.timeout(2000) });
      assert.equal(response.status, 200);
      const home = await response.text();
      assert.ok(home.includes("A preflight check for long-lived industrial sensors"));
      assert.ok(home.includes("not support for NI firmware or a customer relationship"));
      ready = true;
      break;
    } catch {
      await delay(100);
    }
  }
  assert.ok(ready, logs);
  for (const path of ["/reference", "/amd", "/runs/RP-smoke", "/runs/RP-percent%25", "/runs/RP-literal%252F"]) {
    const response = await fetch(`${base}${path}`, { signal: AbortSignal.timeout(5000) });
    assert.equal(response.status, 200, `${path}: ${await response.text()}`);
  }
  console.log("Standalone HTTP smoke passed: 6 pages, including literal % run IDs; no backend executions.");
} finally {
  if (server.exitCode === null) {
    server.kill();
    await once(server, "exit");
  }
}
