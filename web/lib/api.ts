import type {
  AITraceView,
  AmdDashboard,
  AmdView,
  ArtifactView,
  AssistantRequest,
  ConfigurationView,
  PlannedTestView,
  ReferenceView,
  ResultView,
  RunCreate,
  RunView,
  SSEType,
  TestCatalog,
} from "@/lib/types";
import { buildAmdDashboard, unwrapList } from "@/lib/amd-stats";
import { ApiError } from "@/lib/errors";
import { isRecord } from "@/lib/utils";
import { mockClient } from "@/lib/mock/client";

export { ApiError };

export const MOCK_MODE = process.env.NEXT_PUBLIC_MOCK === "1";

export const SSE_TYPES: SSEType[] = [
  "stage",
  "log",
  "artifact",
  "observation",
  "test_result",
  "error",
  "done",
  "run",
  "ai",
];

export interface StreamEvent {
  id: number | null;
  type: SSEType;
  data: Record<string, unknown>;
}

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export interface SubscribeHandlers {
  onEvent: (event: StreamEvent) => void;
  onState?: (state: ConnectionState) => void;
}

export interface ApiClient {
  listConfigurations(): Promise<ConfigurationView[]>;
  getCatalog(): Promise<TestCatalog | null>;
  listRuns(limit?: number): Promise<RunView[]>;
  createRun(body: RunCreate): Promise<RunView>;
  getRun(runId: string): Promise<RunView>;
  /** Resolves to null while the result is not available yet (404/409). */
  getResult(runId: string): Promise<ResultView | null>;
  getArtifacts(runId: string): Promise<ArtifactView[]>;
  getTraces(runId: string): Promise<AITraceView[]>;
  /** Planned tests (required + AI/optional selection) as soon as AI_PLAN is done. */
  getPlan(runId: string): Promise<PlannedTestView[]>;
  evaluateAlternative(runId: string, planId: string, idempotencyKey: string): Promise<RunView>;
  getReference(): Promise<ReferenceView>;
  getAmd(): Promise<AmdDashboard>;
  /** Streams assistant text. Resolves when the stream ends. */
  assistant(body: AssistantRequest, onChunk: (text: string) => void, signal?: AbortSignal): Promise<void>;
  subscribe(runId: string, handlers: SubscribeHandlers): () => void;
}



const BASE = "/api";

function enc(s: string): string {
  return encodeURIComponent(s);
}

async function errorFrom(res: Response): Promise<ApiError> {
  let detail: unknown = undefined;
  let message = `${res.status} ${res.statusText}`.trim();
  try {
    const text = await res.text();
    try {
      detail = JSON.parse(text);
      if (isRecord(detail)) {
        const d = detail.detail ?? detail.message ?? detail.error;
        if (typeof d === "string") message = d;
        else if (d !== undefined) message = JSON.stringify(d);
      }
    } catch {
      if (text) message = text.slice(0, 300);
    }
  } catch {
    // ignore body read errors
  }
  return new ApiError(message, res.status, detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()) as T;
}

function parseStreamEvent(type: SSEType | null, e: MessageEvent<string>): StreamEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(e.data);
  } catch {
    return null;
  }
  if (!isRecord(parsed)) return null;
  const lastId = e.lastEventId ? Number(e.lastEventId) : null;
  // Envelope form: {id, type, data} (contracts/api.py SSEEvent) — or the bare data dict.
  if (typeof parsed.type === "string" && isRecord(parsed.data) && SSE_TYPES.includes(parsed.type as SSEType)) {
    return {
      id: typeof parsed.id === "number" ? parsed.id : lastId,
      type: parsed.type as SSEType,
      data: parsed.data,
    };
  }
  const t = type ?? (typeof parsed.type === "string" ? (parsed.type as SSEType) : null);
  if (!t || !SSE_TYPES.includes(t)) return null;
  return { id: lastId, type: t, data: parsed };
}

function subscribeReal(runId: string, { onEvent, onState }: SubscribeHandlers): () => void {
  let source: EventSource | null = null;
  let closed = false;
  let lastId: string | null = null;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const handle = (type: SSEType | null) => (e: MessageEvent<string>) => {
    if (e.lastEventId) lastId = e.lastEventId;
    const ev = parseStreamEvent(type, e);
    if (ev) onEvent(ev);
  };

  const open = () => {
    if (closed) return;
    onState?.(attempt === 0 ? "connecting" : "reconnecting");
    // EventSource resends Last-Event-ID itself on automatic reconnects; when we have to
    // recreate it after a hard close, pass the cursor as a query parameter as well.
    const qs = lastId ? `?after=${enc(lastId)}` : "";
    const es = new EventSource(`${BASE}/assessments/${enc(runId)}/events${qs}`);
    source = es;
    es.onopen = () => {
      attempt = 0;
      onState?.("open");
    };
    for (const t of SSE_TYPES) es.addEventListener(t, handle(t) as EventListener);
    es.onmessage = handle(null);
    es.onerror = () => {
      if (closed) return;
      if (es.readyState === EventSource.CLOSED) {
        attempt += 1;
        onState?.("reconnecting");
        const delay = Math.min(15000, 1000 * 2 ** Math.min(attempt, 4));
        timer = setTimeout(open, delay);
      } else {
        onState?.("reconnecting");
      }
    };
  };

  open();
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    source?.close();
    onState?.("closed");
  };
}

const realClient: ApiClient = {
  async listConfigurations() {
    return unwrapList<ConfigurationView>(await request<unknown>("/configurations"), "configurations");
  },
  async getCatalog() {
    try {
      return await request<TestCatalog>("/catalog/tests");
    } catch {
      return null;
    }
  },
  async listRuns(limit = 20) {
    return unwrapList<RunView>(await request<unknown>(`/assessments?limit=${limit}`), "runs", "assessments");
  },
  createRun(body) {
    return request<RunView>("/assessments", {
      method: "POST",
      body: JSON.stringify(body),
      headers: body.idempotency_key ? { "Idempotency-Key": body.idempotency_key } : undefined,
    });
  },
  getRun(runId) {
    return request<RunView>(`/assessments/${enc(runId)}`);
  },
  async getResult(runId) {
    try {
      return await request<ResultView>(`/assessments/${enc(runId)}/result`);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 409 || err.status === 425)) return null;
      throw err;
    }
  },
  async getArtifacts(runId) {
    return unwrapList<ArtifactView>(await request<unknown>(`/assessments/${enc(runId)}/artifacts`), "artifacts");
  },
  async getTraces(runId) {
    try {
      return unwrapList<AITraceView>(await request<unknown>(`/assessments/${enc(runId)}/ai-traces`), "traces");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return [];
      throw err;
    }
  },
  async getPlan(runId) {
    try {
      return unwrapList<PlannedTestView>(await request<unknown>(`/assessments/${enc(runId)}/plan`), "plan", "tests");
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 409)) return [];
      throw err;
    }
  },
  evaluateAlternative(runId, planId, idempotencyKey) {
    return request<RunView>(`/assessments/${enc(runId)}/alternatives/${enc(planId)}/evaluate`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  async getReference() {
    const raw = await request<unknown>("/reference");
    if (!isRecord(raw) || !isRecord(raw.run)) throw new ApiError("Unexpected /api/reference payload", 500, raw);
    const ref = raw as unknown as ReferenceView;
    return { ...ref, result: ref.result ?? null, notice: ref.notice ?? "", recorded_at: ref.recorded_at ?? ref.run.created_at };
  },
  async getAmd() {
    const view = await request<AmdView>("/amd");
    // /api/amd has aggregates only; collect recent traces from recent runs for the table.
    const runs = await realClient.listRuns(12).catch(() => [] as RunView[]);
    const lists = await Promise.all(runs.map((r) => realClient.getTraces(r.run_id).catch(() => [] as AITraceView[])));
    return buildAmdDashboard(view, lists.flat());
  },
  async assistant(body, onChunk, signal) {
    const res = await fetch(`${BASE}/assistant`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/plain, text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok) throw await errorFrom(res);
    const isSse = (res.headers.get("content-type") ?? "").includes("text/event-stream");
    if (!res.body) {
      onChunk(await res.text());
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const text = decoder.decode(value, { stream: true });
      if (!isSse) {
        onChunk(text);
        continue;
      }
      buffer += text;
      const frames = buffer.split(/\n\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const data = frame
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).replace(/^ /, ""))
          .join("\n");
        if (!data || data === "[DONE]") continue;
        try {
          const parsed: unknown = JSON.parse(data);
          if (isRecord(parsed) && typeof parsed.text === "string") onChunk(parsed.text);
          else if (typeof parsed === "string") onChunk(parsed);
        } catch {
          onChunk(data);
        }
      }
    }
  },
  subscribe: subscribeReal,
};

export const api: ApiClient = MOCK_MODE ? mockClient : realClient;
