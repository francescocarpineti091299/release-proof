/* In-browser mock API (NEXT_PUBLIC_MOCK=1). Created runs persist in localStorage. */
import type { ApiClient, StreamEvent } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { buildAmdDashboard } from "@/lib/amd-stats";
import type { AITraceView, AmdDashboard, ReferenceView, RunCreate, RunView } from "@/lib/types";
import { MOCK_CATALOG, MOCK_CONFIGS } from "./profiles";
import {
  artifactsAt,
  eventsFor,
  fakeSha,
  MOCK_PROVIDER,
  planAt,
  resultAt,
  runViewAt,
  totalDuration,
  tracesAt,
  type RunRecord,
} from "./sim";
import type { ScenarioKey } from "./scenarios";

const STORE_KEY = "releaseproof.mock.runs.v1";
const IDEM_KEY = "releaseproof.mock.idem.v1";

const WOLF_SEED = "RP-20261017T091502Z-4f1a2c";

const SEEDED: RunRecord[] = [
  { run_id: WOLF_SEED, scenario: "wolfboot", created_ms: Date.parse("2026-10-17T09:15:02Z"), scale: 17 },
  {
    run_id: "RP-20261017T093844Z-b7e0d1",
    scenario: "reeval-reflash",
    created_ms: Date.parse("2026-10-17T09:38:44Z"),
    scale: 4,
    parent_run_id: WOLF_SEED,
  },
  { run_id: "RP-20261017T102530Z-e21f08", scenario: "mcuboot-failed", created_ms: Date.parse("2026-10-17T10:25:30Z"), scale: 17 },
  { run_id: "RP-20261017T104211Z-9c3e5a", scenario: "mcuboot", created_ms: Date.parse("2026-10-17T10:42:11Z"), scale: 19 },
];

const REFERENCE: RunRecord = {
  run_id: "WP0-FREEZE-20261001",
  scenario: "reference",
  created_ms: Date.parse("2026-10-01T09:08:19Z"),
  scale: 15,
};

const assistantTraces: AITraceView[] = [];

function readCreated(): RunRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as RunRecord[]) : [];
  } catch {
    return [];
  }
}

function writeCreated(list: RunRecord[]) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(list.slice(-30)));
  } catch {
    // storage full or disabled: runs stay in memory for this page only
  }
}

function idemMap(): Record<string, string> {
  try {
    return JSON.parse(window.localStorage.getItem(IDEM_KEY) ?? "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

function allRecords(): RunRecord[] {
  return [...SEEDED, ...readCreated(), REFERENCE];
}

function find(runId: string): RunRecord {
  const rec = allRecords().find((r) => r.run_id === runId);
  if (!rec) throw new ApiError(`Unknown run ${runId}`, 404);
  return rec;
}

function elapsed(rec: RunRecord): number {
  return (Date.now() - rec.created_ms) / rec.scale;
}

function newRunId(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}T${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`;
  return `RP-${stamp}-${fakeSha(`${Date.now()}-${Math.random()}`).slice(0, 6)}`;
}

function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function createRecord(scenario: ScenarioKey, opts: Partial<RunRecord> = {}): RunRecord {
  const rec: RunRecord = { run_id: newRunId(), scenario, created_ms: Date.now(), scale: 1, ...opts };
  writeCreated([...readCreated(), rec]);
  return rec;
}

function assistantAnswer(run: RunView, question: string): string {
  const res = (() => {
    try {
      return resultAt(find(run.run_id), elapsed(find(run.run_id)));
    } catch {
      return null;
    }
  })();
  const v = run.verdict;
  if (!v) {
    return `This run has **no verdict yet** (status ${run.status}). ${
      run.failure ? `It failed with \`${run.failure.failure_class}\`: ${run.failure.message} No verdict was issued.` : "The deterministic engine issues the verdict after the evaluation stage."
    }`;
  }
  const causes = run.ai_report?.report?.main_causes ?? [];
  const q = question.toLowerCase();
  const lines: string[] = [];
  if (q.includes("candidate")) {
    lines.push(`The **candidate** verdict is **${v.candidate}**. It covers the new firmware state on its own.`);
  } else if (q.includes("transition") || q.includes("block")) {
    lines.push(`The **transition** verdict is **${v.transition}**. It covers getting deployed devices from today's state to the candidate.`);
  } else {
    lines.push(`The deterministic engine's verdict for this run is **${v.migration}** for the overall migration (candidate **${v.candidate}**, transition **${v.transition}**).`);
  }
  if (causes.length) {
    lines.push("", "Main reasons, with the evidence in this run:");
    for (const c of causes) lines.push(`- ${c.text} (${c.citations.join(", ")})`);
  }
  const gaps = res?.assessment.evidence_gaps ?? [];
  if (gaps.length && (q.includes("unknown") || q.includes("compatible") || q.includes("missing") || q.includes("make"))) {
    lines.push("", "Still not observed:");
    for (const g of gaps.slice(0, 3)) lines.push(`- ${g.gap_id}: ${g.reason}`);
  }
  lines.push("", "_I can explain the evidence. I cannot change the verdict._");
  return lines.join("\n");
}

export const mockClient: ApiClient = {
  listConfigurations: () => delay(MOCK_CONFIGS),
  getCatalog: () => delay(MOCK_CATALOG),
  async listRuns(limit = 20) {
    const runs = [...SEEDED, ...readCreated()]
      .sort((a, b) => b.created_ms - a.created_ms)
      .slice(0, limit)
      .map((r) => runViewAt(r, elapsed(r)));
    return delay(runs);
  },
  async createRun(body: RunCreate) {
    const profile = MOCK_CONFIGS.find((p) => p.id === body.configuration_id);
    const change = profile?.changes.find((c) => c.change_id === body.change_id);
    if (!profile || !change) throw new ApiError("Unknown configuration or change", 422);
    if (profile.status === "UNAVAILABLE") throw new ApiError("Configuration unavailable", 409);
    if (body.idempotency_key) {
      const existing = idemMap()[body.idempotency_key];
      if (existing) return delay(runViewAt(find(existing), elapsed(find(existing))));
    }
    const rec = createRecord(profile.bootloader.family === "wolfboot" ? "wolfboot" : "mcuboot", {
      plan_id: body.plan_id ?? undefined,
    });
    if (body.idempotency_key) {
      window.localStorage.setItem(IDEM_KEY, JSON.stringify({ ...idemMap(), [body.idempotency_key]: rec.run_id }));
    }
    return delay(runViewAt(rec, 0), 350);
  },
  async getRun(runId) {
    const rec = find(runId);
    return delay(runViewAt(rec, elapsed(rec)), 60);
  },
  async getResult(runId) {
    const rec = find(runId);
    return delay(resultAt(rec, elapsed(rec)), 80);
  },
  async getArtifacts(runId) {
    const rec = find(runId);
    return delay(artifactsAt(rec, elapsed(rec)), 60);
  },
  async getTraces(runId) {
    const rec = find(runId);
    return delay([...tracesAt(rec, elapsed(rec)), ...assistantTraces.filter((t) => t.run_id === runId)], 60);
  },
  async getPlan(runId) {
    const rec = find(runId);
    return delay(planAt(rec, elapsed(rec)), 60);
  },
  async evaluateAlternative(runId, planId, idempotencyKey) {
    const parent = find(runId);
    const parentView = runViewAt(parent, elapsed(parent));
    const profile = MOCK_CONFIGS.find((p) => p.id === parentView.configuration_id);
    const plan = profile?.changes.find((c) => c.change_id === parentView.change_id)?.alternatives.find((a) => a.plan_id === planId);
    if (!plan) throw new ApiError(`Plan ${planId} is not an allowed alternative`, 422);
    if (plan.status === "REQUIRES_EXTERNAL_VALIDATION") throw new ApiError("This plan requires external validation", 409);
    const existing = idemMap()[idempotencyKey];
    if (existing) return delay(runViewAt(find(existing), elapsed(find(existing))));
    const wolf = profile?.bootloader.family === "wolfboot";
    const rec = plan.requires_rerun_tests
      ? createRecord(wolf ? "wolfboot-hybrid" : "mcuboot", { plan_id: planId, parent_run_id: runId })
      : createRecord(wolf ? "reeval-reflash" : "reeval-mcuboot", { plan_id: planId, parent_run_id: runId });
    window.localStorage.setItem(IDEM_KEY, JSON.stringify({ ...idemMap(), [idempotencyKey]: rec.run_id }));
    return delay(runViewAt(rec, 0), 300);
  },
  async getReference(): Promise<ReferenceView> {
    const t = Number.MAX_SAFE_INTEGER;
    const result = resultAt(REFERENCE, t);
    return delay({
      recorded: true as const,
      run: runViewAt(REFERENCE, t),
      result,
      recorded_at: "2026-10-01",
      notice:
        "Recorded WP0 freeze of 2026-10-01 (nRF52840 + wolfBoot, ECDSA P-256 -> ML-DSA-87). These facts were measured on 2026-10-01 and are re-evaluated here by the current engine; this is not a live execution.",
      canonical_hash: result?.result.canonical_hash ?? null,
    });
  },
  async getAmd(): Promise<AmdDashboard> {
    const traces = [...SEEDED, ...readCreated()].flatMap((r) => tracesAt(r, elapsed(r))).concat(assistantTraces);
    const ok = traces.filter((x) => x.status === "OK");
    const lat = ok.map((x) => x.latency_ms ?? 0).sort((a, b) => a - b);
    const pct = (p: number) => (lat.length ? lat[Math.min(lat.length - 1, Math.ceil((p / 100) * lat.length) - 1)] : null);
    const byModule: Record<string, number> = {};
    for (const x of traces) byModule[x.module] = (byModule[x.module] ?? 0) + 1;
    return delay(
      buildAmdDashboard(
        {
          provider: {
            provider: MOCK_PROVIDER.provider,
            hardware: MOCK_PROVIDER.hardware_label,
            endpoint_host: MOCK_PROVIDER.endpoint_host,
            configured: true,
            unavailable_reason: null,
            models: { planner: MOCK_PROVIDER.model, explainer: MOCK_PROVIDER.model, alternatives: MOCK_PROVIDER.model, assistant: MOCK_PROVIDER.model },
            prompt_templates: { planner: "planner@1", explainer: "explainer@1", alternatives: "alternatives@1", assistant: "assistant@1" },
            allowed_hosts: [MOCK_PROVIDER.endpoint_host],
            response_format: "json_schema",
            fallback_provider: null,
          },
          traces: {
            count: traces.length,
            ok: ok.length,
            ok_rate: traces.length ? ok.length / traces.length : null,
            latency_ms_p50: pct(50),
            latency_ms_p95: pct(95),
            prompt_tokens: traces.reduce((a, x) => a + (x.prompt_tokens ?? 0), 0),
            completion_tokens: traces.reduce((a, x) => a + (x.completion_tokens ?? 0), 0),
            by_module: byModule,
          },
        },
        traces,
      ),
    );
  },
  async assistant(body, onChunk, signal) {
    const run = await mockClient.getRun(body.run_id);
    const question = body.messages[body.messages.length - 1]?.content ?? "";
    const answer = assistantAnswer(run, question);
    const started = Date.now();
    await new Promise((r) => setTimeout(r, 450));
    for (let i = 0; i < answer.length; ) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      const n = 3 + Math.floor(Math.random() * 6);
      onChunk(answer.slice(i, i + n));
      i += n;
      await new Promise((r) => setTimeout(r, 16));
    }
    assistantTraces.push({
      trace_id: `tr-${body.run_id.slice(-6)}-assistant-${assistantTraces.length + 1}`,
      run_id: body.run_id,
      module: "assistant",
      provider: MOCK_PROVIDER.provider,
      model: MOCK_PROVIDER.model,
      endpoint_host: MOCK_PROVIDER.endpoint_host,
      hardware_label: MOCK_PROVIDER.hardware_label,
      request_id: `chatcmpl-${fakeSha(String(started)).slice(0, 20)}`,
      prompt_template: "assistant/v1",
      started_at: new Date(started).toISOString(),
      latency_ms: Date.now() - started,
      prompt_tokens: 4100 + question.length,
      completion_tokens: Math.round(answer.length / 4),
      status: "OK",
    });
  },
  subscribe(runId, { onEvent, onState }) {
    let rec: RunRecord;
    try {
      rec = find(runId);
    } catch {
      onState?.("closed");
      return () => undefined;
    }
    const timers: ReturnType<typeof setTimeout>[] = [];
    let closed = false;
    onState?.("connecting");
    const events = eventsFor(rec);
    const now = elapsed(rec);
    events.forEach((e, i) => {
      const dispatch = () => {
        if (closed) return;
        const data = e.data ?? (runViewAt(rec, e.t) as unknown as Record<string, unknown>);
        const ev: StreamEvent = { id: i + 1, type: e.type, data };
        onEvent(ev);
      };
      const wait = Math.max(0, (e.t - now) * rec.scale);
      timers.push(setTimeout(dispatch, e.t <= now ? 30 : wait));
    });
    timers.push(setTimeout(() => !closed && onState?.("open"), 20));
    timers.push(setTimeout(() => !closed && onState?.("closed"), Math.max(60, (totalDuration(rec) - now) * rec.scale + 100)));
    return () => {
      closed = true;
      timers.forEach(clearTimeout);
      onState?.("closed");
    };
  },
};
