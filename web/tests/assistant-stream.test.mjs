import assert from "node:assert/strict";
import test from "node:test";
import { consumeAssistantStream } from "../lib/assistant-stream.ts";

function response(text, type = "text/event-stream") {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({
    start(controller) {
      // Every byte in its own chunk, including UTF-8 and CRLF boundaries.
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  }), { headers: { "Content-Type": type } });
}

test("decodes fragmented UTF-8 plain text", async () => {
  let output = "";
  const res = response("Caffè 🔐", "text/plain");
  await consumeAssistantStream(res, (text) => { output += text; });
  assert.equal(output, "Caffè 🔐");
  assert.equal(res.body.locked, false);
});

test("SSE handles CRLF, comments, multiple data lines, DONE and final frame at EOF", async () => {
  let output = "";
  const res = response(': ping\r\nevent: token\r\ndata: {"text":"è"}\r\n\r\ndata: first\ndata: second\n\ndata: [DONE]\n\ndata: "tail"');
  await consumeAssistantStream(res, (text) => { output += text; });
  assert.equal(output, "èfirst\nsecondtail");
  assert.equal(res.body.locked, false);
});

test("callback exceptions propagate once, cancelling and releasing the reader", async () => {
  let calls = 0;
  let cancelled = false;
  const res = new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('data: "x"\n\n')); },
    cancel() { cancelled = true; },
  }), { headers: { "Content-Type": "text/event-stream" } });
  await assert.rejects(consumeAssistantStream(res, () => { calls++; throw new Error("render failed"); }), /render failed/);
  assert.equal(calls, 1);
  assert.equal(cancelled, true);
  assert.equal(res.body.locked, false);
});

test("rejects unbounded SSE frames", async () => {
  await assert.rejects(consumeAssistantStream(new Response(`data: ${"x".repeat(1_000_001)}`, { headers: { "Content-Type": "text/event-stream" } }), () => {}), /too large/);
});
