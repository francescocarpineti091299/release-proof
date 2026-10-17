/** Decode plain text or SSE without depending on transport chunk boundaries. */
export async function consumeAssistantStream(response: Response, onChunk: (text: string) => void): Promise<void> {
  if (!response.body) {
    onChunk(await response.text());
    return;
  }
  const sse = (response.headers.get("content-type") ?? "").includes("text/event-stream");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let data: string[] = [];
  let frameSize = 0;
  const emit = () => {
    const text = data.join("\n");
    data = [];
    frameSize = 0;
    if (!text || text === "[DONE]") return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      onChunk(text);
      return;
    }
    if (typeof parsed === "string") onChunk(parsed);
    else if (parsed && typeof parsed === "object" && "text" in parsed && typeof parsed.text === "string") onChunk(parsed.text);
  };
  const line = (text: string) => {
    if (!text) emit();
    else if (text === "data" || text.startsWith("data:")) {
      const value = text.slice(5).replace(/^ /, "");
      frameSize += value.length;
      if (frameSize > 1_000_000) throw new Error("Assistant SSE frame is too large");
      data.push(value);
    }
  };
  const process = (text: string, eof = false) => {
    if (!sse) {
      if (text) onChunk(text);
      return;
    }
    buffer += text;
    for (;;) {
      const match = /\r\n|\r|\n/.exec(buffer);
      if (!match || (!eof && match[0] === "\r" && match.index === buffer.length - 1)) break;
      line(buffer.slice(0, match.index));
      buffer = buffer.slice(match.index + match[0].length);
    }
    if (buffer.length > 1_000_000) throw new Error("Assistant SSE line is too large");
    if (eof) {
      if (buffer) line(buffer);
      buffer = "";
      emit();
    }
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      process(decoder.decode(value, { stream: true }));
    }
    process(decoder.decode(), true);
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
