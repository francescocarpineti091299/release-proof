import assert from "node:assert/strict";
import test from "node:test";
import { parseStreamEvent } from "../lib/run-events.ts";

test("run SSE accepts envelopes and bare payloads with validated cursors", () => {
  assert.deepEqual(parseStreamEvent(null, { lastEventId: "", data: '{"id":42,"type":"log","data":{"line":"x"}}' }), { id: 42, type: "log", data: { line: "x" } });
  assert.deepEqual(parseStreamEvent("log", { lastEventId: "9", data: '{"line":"x"}' }), { id: 9, type: "log", data: { line: "x" } });
  for (const lastEventId of ["NaN", "-1", "1.2", "9007199254740992"]) assert.equal(parseStreamEvent("log", { lastEventId, data: "{}" }).id, null);
  assert.equal(parseStreamEvent(null, { lastEventId: "10", data: '{"id":-1,"type":"log","data":{}}' }).id, 10);
});

test("run SSE rejects malformed JSON, arrays and unknown event types", () => {
  for (const data of ["{", "null", "[]", '"x"', '{"type":"unknown","data":{}}']) assert.equal(parseStreamEvent(null, { lastEventId: "", data }), null);
});
