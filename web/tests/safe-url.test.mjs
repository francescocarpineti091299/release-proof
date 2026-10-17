import assert from "node:assert/strict";
import test from "node:test";
import { safeArtifactUrl } from "../lib/safe-url.ts";

test("artifact URLs allow API paths and HTTP(S) storage URLs", () => {
  for (const url of ["/api/assessments/RP-1/artifacts/a", "https://storage.example/a?signature=abc%20def", "http://localhost:8000/a"]) assert.equal(safeArtifactUrl(url), url);
});

test("artifact URLs reject active schemes, protocol-relative URLs and obfuscation", () => {
  for (const url of [null, undefined, 1, "", "javascript:alert(1)", "java\nscript:alert(1)", "data:text/html,<script>", "file:///secret", "//evil.test/a", "/\\evil.test/a", " https://example.test/a", "https://user:secret@example.test/a", "not-a-url"]) assert.equal(safeArtifactUrl(url), undefined);
});
