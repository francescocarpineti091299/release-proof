import type { SSEType } from "@/lib/types";

export const SSE_TYPES: SSEType[] = ["stage", "log", "artifact", "observation", "test_result", "error", "done", "run", "ai"];

export interface StreamEvent {
  id: number | null;
  type: SSEType;
  data: Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function cursor(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function parseStreamEvent(type: SSEType | null, event: Pick<MessageEvent<string>, "data" | "lastEventId">): StreamEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(event.data);
  } catch {
    return null;
  }
  if (!isRecord(parsed)) return null;
  const lastId = event.lastEventId ? cursor(Number(event.lastEventId)) : null;
  if (typeof parsed.type === "string" && isRecord(parsed.data) && SSE_TYPES.includes(parsed.type as SSEType)) {
    return { id: cursor(parsed.id) ?? lastId, type: parsed.type as SSEType, data: parsed.data };
  }
  const t = type ?? (typeof parsed.type === "string" ? parsed.type as SSEType : null);
  if (!t || !SSE_TYPES.includes(t)) return null;
  return { id: lastId, type: t, data: parsed };
}
