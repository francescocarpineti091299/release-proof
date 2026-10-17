/* Time-driven mock run simulator: the state of a run is a pure function of elapsed time. */
import type {
  AITraceView,
  ArtifactView,
  EvidenceView,
  PlannedTestView,
  ResultView,
  RunView,
  SSEType,
  Stage,
  StageStatus,
  StageView,
  TestResultView,
} from "@/lib/types";
import { STAGE_ORDER } from "@/lib/types";
import { mockTemplate } from "./profiles";
import { scenario, type MockTest, type ScenarioKey, type ScenarioSpec } from "./scenarios";

export interface RunRecord {
  run_id: string;
  scenario: ScenarioKey;
  created_ms: number;
  /** Multiplier from simulated time to displayed time (1 = real time). */
  scale: number;
  plan_id?: string;
  parent_run_id?: string | null;
}

export const MOCK_PROVIDER = {
  provider: "AMD Developer Cloud (vLLM)",
  hardware_label: "AMD Instinct MI300X",
  endpoint_host: "mi300x.devcloud.amd.example",
  model: "Qwen/Qwen3-32B",
};

const LIVE_DURATIONS: Record<Stage, number> = {
  PREPARING: 1000,
  AI_PLAN: 2400,
  DISCOVERY: 1600,
  BUILD_SIGN: 4200,
  EMULATION_TESTS: 6000,
  EVALUATION: 1200,
  NEXT_STEPS: 3200,
};

interface Segment {
  stage: Stage;
  start: number;
  end: number;
  status: StageStatus;
  message: string;
}

export interface TimedEvent {
  t: number;
  type: SSEType;
  data: Record<string, unknown> | null; // null = run snapshot computed at dispatch time
}

interface Timeline {
  spec: ScenarioSpec;
  queueEnd: number;
  segments: Partial<Record<Stage, Segment>>;
  skipped: Set<Stage>;
  failTime: number | null;
  total: number;
  testDone: Map<string, { t: number; duration: number }>;
  events: TimedEvent[];
}

const cache = new Map<string, Timeline>();

export function specFor(rec: RunRecord): ScenarioSpec {
  return scenario(rec.scenario, rec.plan_id);
}

function iso(ms: number): string {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** Deterministic 64-hex pseudo hash for mock artifacts. */
export function fakeSha(input: string): string {
  let out = "";
  for (let seed = 1; out.length < 64; seed++) {
    let h1 = 0xdeadbeef ^ seed;
    let h2 = 0x41c6ce57 ^ seed;
    for (let i = 0; i < input.length; i++) {
      const ch = input.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    out += (h2 >>> 0).toString(16).padStart(8, "0") + (h1 >>> 0).toString(16).padStart(8, "0");
  }
  return out.slice(0, 64);
}

function timeline(rec: RunRecord): Timeline {
  const key = `${rec.run_id}|${rec.scenario}|${rec.plan_id ?? ""}`;
  const hit = cache.get(key);
  if (hit) return hit;

  const spec = specFor(rec);
  const reeval = spec.mode === "REEVALUATION";
  const queueEnd = reeval ? 500 : 1200;
  const skipped = new Set<Stage>(spec.skipped);
  const segments: Partial<Record<Stage, Segment>> = {};
  let cursor = queueEnd;
  let failTime: number | null = null;
  for (const stage of STAGE_ORDER) {
    if (skipped.has(stage)) continue;
    if (failTime !== null) {
      skipped.add(stage);
      continue;
    }
    let dur = LIVE_DURATIONS[stage];
    if (reeval && stage === "NEXT_STEPS") dur = 2200;
    const final = spec.stageFinal[stage];
    const seg: Segment = {
      stage,
      start: cursor,
      end: cursor + dur,
      status: final?.status ?? "SUCCEEDED",
      message: final?.message ?? "",
    };
    if (spec.failAt === stage) {
      seg.end = cursor + Math.round(dur * 0.6);
      seg.status = "FAILED";
      seg.message = spec.failure?.failure_class ?? "FAILED";
      failTime = seg.end;
    }
    segments[stage] = seg;
    cursor = seg.end;
  }
  const total = cursor;

  // Test completion times: spread evenly inside their stage segment.
  const testDone = new Map<string, { t: number; duration: number }>();
  const byStage = new Map<Stage, MockTest[]>();
  for (const test of spec.tests) byStage.set(test.stage, [...(byStage.get(test.stage) ?? []), test]);
  for (const [stage, tests] of byStage) {
    const seg = segments[stage];
    if (!seg) continue;
    const span = seg.end - seg.start;
    const from = seg.start + span * 0.3;
    const to = seg.end - span * 0.03;
    const weights = tests.reduce((acc, x) => acc + Math.max(1, x.duration_ms), 0);
    let prev = from;
    let cum = 0;
    tests.forEach((test) => {
      cum += Math.max(1, test.duration_ms);
      const t = Math.round(from + ((to - from) * cum) / weights);
      if (failTime !== null && t > failTime) return;
      testDone.set(test.template_id, { t, duration: (t - prev) * rec.scale });
      prev = t;
    });
    if (seg.status === "FAILED") {
      const failing = tests.find((x) => x.outcome === "ERROR");
      if (failing) testDone.set(failing.template_id, { t: seg.end, duration: (seg.end - seg.start) * rec.scale * 0.8 });
    }
  }

  const tl: Timeline = { spec, queueEnd, segments, skipped, failTime, total, testDone, events: [] };
  tl.events = buildEvents(rec, tl);
  cache.set(key, tl);
  return tl;
}

function aiAt(tl: Timeline, which: "plan" | "report" | "alternatives"): number | null {
  if (which === "plan") return tl.segments.AI_PLAN?.end ?? null;
  const seg = tl.segments.NEXT_STEPS;
  if (!seg) return null;
  return which === "report" ? seg.start + Math.round((seg.end - seg.start) * 0.55) : seg.end;
}

function traceTime(tl: Timeline, module: string): number | null {
  if (module === "planner") return aiAt(tl, "plan");
  if (module === "explainer") return aiAt(tl, "report");
  if (module === "alternatives") return aiAt(tl, "alternatives");
  return null;
}

function traceId(rec: RunRecord, module: string): string {
  return `tr-${rec.run_id.slice(-6)}-${module}`;
}

export function tracesAt(rec: RunRecord, t: number, given?: Timeline): AITraceView[] {
  const tl = given ?? timeline(rec);
  const out: AITraceView[] = [];
  for (const tr of tl.spec.traces) {
    const at = traceTime(tl, tr.module);
    if (at === null || at > t) continue;
    const started = rec.created_ms + (at * rec.scale - tr.latency_ms);
    out.push({
      trace_id: traceId(rec, tr.module),
      run_id: rec.run_id,
      module: tr.module,
      provider: MOCK_PROVIDER.provider,
      model: MOCK_PROVIDER.model,
      endpoint_host: MOCK_PROVIDER.endpoint_host,
      hardware_label: MOCK_PROVIDER.hardware_label,
      request_id: tr.status === "OK" ? `chatcmpl-${fakeSha(rec.run_id + tr.module).slice(0, 20)}` : null,
      prompt_template: tr.prompt_template,
      started_at: iso(started),
      latency_ms: tr.latency_ms,
      prompt_tokens: tr.status === "OK" ? tr.prompt_tokens : null,
      completion_tokens: tr.status === "OK" ? tr.completion_tokens : null,
      status: tr.status,
      error: tr.error ?? null,
    });
  }
  return out;
}

function stageViews(rec: RunRecord, tl: Timeline, t: number): StageView[] {
  return STAGE_ORDER.map((stage): StageView => {
    const seg = tl.segments[stage];
    if (!seg) {
      const knownSkip = tl.spec.skipped.includes(stage) || (tl.failTime !== null && t >= tl.failTime);
      const reason = tl.spec.mode === "REEVALUATION" ? "Evidence reused from the parent run" : tl.failTime !== null ? "Run failed earlier" : "Not part of this run";
      return { stage, status: knownSkip ? "SKIPPED" : "QUEUED", message: knownSkip ? reason : "" };
    }
    if (t < seg.start) return { stage, status: "QUEUED", message: "" };
    const started_at = iso(rec.created_ms + seg.start * rec.scale);
    if (t < seg.end) return { stage, status: "RUNNING", started_at, message: "" };
    return {
      stage,
      status: seg.status,
      started_at,
      finished_at: iso(rec.created_ms + seg.end * rec.scale),
      duration_ms: Math.round((seg.end - seg.start) * rec.scale),
      message: seg.message,
    };
  });
}

function testViews(tl: Timeline, t: number): TestResultView[] {
  const planReady = tl.segments.AI_PLAN ? t >= tl.segments.AI_PLAN.end : t >= (tl.segments.PREPARING?.end ?? 0);
  if (!planReady) return [];
  return tl.spec.tests.map((test): TestResultView => {
    const tpl = mockTemplate(test.template_id);
    const done = tl.testDone.get(test.template_id);
    const finished = done && done.t <= t;
    return {
      test_id: test.test_id,
      template_id: test.template_id,
      title: tpl?.title ?? test.template_id,
      negative: tpl?.negative ?? false,
      outcome: finished ? test.outcome : "NOT_EXECUTED",
      expected: tpl?.expected ?? "",
      observed: finished ? test.observed : "",
      duration_ms: finished ? Math.round(done.duration) : 0,
      observation_ids: finished ? test.observation_ids : [],
      failure_class: finished ? (test.failure_class ?? null) : null,
      planned_by: test.planned_by,
    };
  });
}

export function runViewAt(rec: RunRecord, t: number): RunView {
  const tl = timeline(rec);
  const spec = tl.spec;
  const ended = t >= tl.total;
  const failed = tl.failTime !== null && t >= tl.failTime;
  const evalEnd = tl.segments.EVALUATION?.end ?? null;
  const discoveryEnd = tl.segments.DISCOVERY?.end ?? tl.segments.PREPARING?.end ?? 0;
  const tid = (m: string) => (tracesAt(rec, t).some((x) => x.module === m) ? [traceId(rec, m)] : []);
  const planAt = aiAt(tl, "plan");
  const reportAt = aiAt(tl, "report");
  const altAt = aiAt(tl, "alternatives");

  return {
    run_id: rec.run_id,
    mode: spec.mode,
    status: failed ? "FAILED" : ended ? "SUCCEEDED" : t < tl.queueEnd ? "QUEUED" : "RUNNING",
    configuration_id: spec.configuration_id,
    configuration_version: spec.configuration_version,
    change_id: spec.change_id,
    plan_id: spec.plan_id,
    parent_run_id: rec.parent_run_id ?? null,
    created_at: iso(rec.created_ms),
    started_at: t >= tl.queueEnd ? iso(rec.created_ms + tl.queueEnd * rec.scale) : null,
    finished_at: ended || failed ? iso(rec.created_ms + (tl.failTime ?? tl.total) * rec.scale) : null,
    queue_position: t < tl.queueEnd ? 1 : null,
    stages: stageViews(rec, tl, t),
    tests: testViews(tl, t),
    verdict:
      spec.doc && evalEnd !== null && t >= evalEnd && !failed
        ? {
            lifecycle: spec.doc.result.lifecycle,
            migration: spec.doc.result.migration_verdict,
            candidate: spec.doc.result.candidate_verdict,
            transition: spec.doc.result.transition_verdict,
            canonical_hash: spec.doc.result.canonical_hash,
            official: false,
          }
        : null,
    failure: failed ? (spec.failure ?? null) : null,
    ai_plan: spec.aiPlan && planAt !== null && t >= planAt ? { ...spec.aiPlan, trace_ids: tid("planner") } : null,
    ai_report: spec.aiReport && reportAt !== null && t >= reportAt ? { ...spec.aiReport, trace_ids: tid("explainer") } : null,
    ai_alternatives:
      spec.aiAlternatives && altAt !== null && t >= altAt ? { ...spec.aiAlternatives, trace_ids: tid("alternatives") } : null,
    source_pins: t >= discoveryEnd ? spec.source_pins : {},
    tool_versions: t >= discoveryEnd ? spec.tool_versions : {},
  };
}

function artifactUrl(name: string, sha: string): string {
  return `data:text/plain;charset=utf-8,${encodeURIComponent(
    `ReleaseProof mock artifact\nname: ${name}\nsha256: ${sha}\n\n(Mock mode: the real API serves the stored file.)\n`,
  )}`;
}

export function artifactsAt(rec: RunRecord, t: number): ArtifactView[] {
  return artifactsOf(rec, timeline(rec), t);
}

function artifactsOf(rec: RunRecord, tl: Timeline, t: number): ArtifactView[] {
  return tl.spec.artifacts
    .filter((a) => {
      const seg = tl.segments[a.stage];
      return tl.spec.mode === "REFERENCE" || (seg ? t >= seg.end || (seg.status === "FAILED" && t >= seg.end) : false);
    })
    .map((a) => {
      const sha = fakeSha(`${rec.run_id}:${a.name}`);
      return {
        artifact_id: a.artifact_id,
        name: a.name,
        kind: a.kind,
        sha256: sha,
        size_bytes: a.size_bytes,
        test_id: a.test_id,
        url: artifactUrl(a.name, sha),
      };
    });
}

function originFor(e: Record<string, unknown>): string {
  const kind = String(e.evidence_kind ?? "");
  const mode = String(e.acquisition_mode ?? "");
  if (kind === "DECLARATION" || e.source_role === "OPERATOR") return "DECLARED";
  if (mode === "EMULATED") return "OBSERVED_EMULATION";
  return "MEASURED_TOOL";
}

export function resultAt(rec: RunRecord, t: number): ResultView | null {
  const tl = timeline(rec);
  const spec = tl.spec;
  const evalEnd = tl.segments.EVALUATION?.end;
  if (!spec.doc || evalEnd === undefined || t < evalEnd) return null;
  const doc = JSON.parse(JSON.stringify(spec.doc)) as NonNullable<ScenarioSpec["doc"]>;
  if (spec.mode !== "REFERENCE") {
    doc.result.assessment_id = rec.run_id;
    doc.assessment.assessment_id = rec.run_id;
  }
  const evidenceRun =
    spec.evidenceRun === "self" ? rec.run_id : spec.evidenceRun === "parent" ? (rec.parent_run_id ?? null) : null;
  const artifactRec = spec.evidenceRun === "parent" && rec.parent_run_id ? { ...rec, run_id: rec.parent_run_id } : rec;
  const arts = artifactsAt(artifactRec, Number.MAX_SAFE_INTEGER);
  const evidence: EvidenceView[] = (doc.assessment.evidence ?? []).map((e) => {
    const refs = Array.isArray(e.artifact_refs) ? (e.artifact_refs as string[]) : [];
    const artifacts = refs.map((ref) => {
      const found = arts.find((a) => a.name === ref) ?? arts.find((a) => a.name.endsWith(`/${ref}`));
      if (found) return found;
      const sha = fakeSha(`${artifactRec.run_id}:${ref}`);
      return { artifact_id: `art-${ref}`, name: ref, kind: "other", sha256: sha, size_bytes: 0, test_id: (e.test_id as string) ?? null, url: artifactUrl(ref, sha) };
    });
    return {
      id: String(e.id),
      test_id: (e.test_id as string | undefined) ?? null,
      value: e.value ?? null,
      evidence_kind: String(e.evidence_kind ?? ""),
      acquisition_mode: String(e.acquisition_mode ?? ""),
      origin: originFor(e),
      run_id: evidenceRun ?? ((e.run_id as string | undefined) ?? null),
      artifacts,
      locator: e.acquisition_mode !== "EMULATED" ? null : e.test_id === "E03" ? "uart.log:L3-L4" : e.test_id === "X01" ? "uart.log:L2-L5" : null,
    };
  });
  return {
    run_id: rec.run_id,
    assessment: doc.assessment,
    result: doc.result,
    gap_plan: null,
    dossier_markdown: renderDossier(rec, spec, doc),
    evidence,
    manifest_sha256: fakeSha(`${rec.run_id}:manifest.json`),
  };
}

function renderDossier(rec: RunRecord, spec: ScenarioSpec, doc: NonNullable<ScenarioSpec["doc"]>): string {
  const r = doc.result;
  const lines = [
    "# Assessment dossier",
    "",
    "> **official=false**: automatic engineering assessment, not an official dossier.",
    "",
    "## 1. Identity",
    "",
    `- **run_id**: \`${rec.run_id}\` (${spec.mode})`,
    `- **assessment_id**: \`${r.assessment_id}\``,
    `- **contract_version**: ${doc.assessment.contract_version ?? "1.2"}`,
    `- **lifecycle**: ${r.lifecycle}`,
    `- **canonical_hash**: \`${r.canonical_hash ?? "—"}\``,
    "",
    "## 2. Executive verdict",
    "",
    "| Scope | Verdict |",
    "|---|---|",
    `| Overall migration | **${r.migration_verdict ?? "—"}** |`,
    `| Candidate | ${r.candidate_verdict ?? "—"} |`,
    `| Transition | ${r.transition_verdict ?? "—"} |`,
    "",
    "## 3. Critical requirements and invariants",
    "",
  ];
  for (const row of [...r.requirement_evaluation_results, ...r.invariant_evaluation_results]) {
    if (!row.critical_for_verdict) continue;
    lines.push(`- \`${row.requirement_id ?? row.invariant_id}\` (${row.phase} · ${row.subject_ref}) → **${row.state}**`);
  }
  lines.push("", "## 4. Open gaps", "");
  for (const g of doc.assessment.evidence_gaps ?? []) lines.push(`- \`${g.gap_id}\` → ${g.requirement_id}: ${g.reason}`);
  lines.push("", "## 5. Reproduction", "", "```text", `profile ${spec.configuration_id}@${spec.configuration_version}`, ...Object.entries(spec.source_pins).map(([k, v]) => `${k} ${v}`), "```", "");
  return lines.join("\n");
}

// ------------------------------------------------------------------ events

function buildEvents(rec: RunRecord, tl: Timeline): TimedEvent[] {
  const ev: TimedEvent[] = [];
  const spec = tl.spec;
  const base = (t: number) => ({ ts: iso(rec.created_ms + t * rec.scale), run_id: rec.run_id });
  const log = (t: number, stream: string, line: string, test_id: string | null = null) =>
    ev.push({ t, type: "log", data: { ...base(t), type: "log", stream, line: line.replace("<run>", rec.run_id), test_id } });

  ev.push({ t: 0, type: "run", data: null });
  ev.push({ t: tl.queueEnd, type: "run", data: null });

  for (const stage of STAGE_ORDER) {
    const seg = tl.segments[stage];
    if (!seg) continue;
    const startedIso = iso(rec.created_ms + seg.start * rec.scale);
    const source = stage === "AI_PLAN" || stage === "EVALUATION" || stage === "NEXT_STEPS" ? "orchestrator" : "runner";
    ev.push({ t: seg.start, type: "stage", data: { stage, status: "RUNNING", started_at: startedIso, finished_at: null, duration_ms: null, message: "", source } });
    const lines = spec.stageLogs[stage] ?? [];
    const span = seg.end - seg.start;
    const stageTests = spec.tests.filter((x) => x.stage === stage);
    lines.forEach(([stream, line], i) => {
      const at = seg.start + Math.round(((i + 1) / (lines.length + 1)) * span * (stageTests.length ? 0.28 : 0.95));
      if (tl.failTime === null || at <= tl.failTime) log(at, stream, line);
    });
    ev.push({
      t: seg.end,
      type: "stage",
      data: {
        stage: seg.stage,
        status: seg.status,
        started_at: startedIso,
        finished_at: iso(rec.created_ms + seg.end * rec.scale),
        duration_ms: Math.round((seg.end - seg.start) * rec.scale),
        message: seg.message,
        source,
      },
    });
  }

  let prev = new Map<Stage, number>();
  for (const test of spec.tests) {
    const done = tl.testDone.get(test.template_id);
    if (!done) continue;
    const seg = tl.segments[test.stage];
    const from = prev.get(test.stage) ?? (seg ? seg.start + (seg.end - seg.start) * 0.3 : done.t - 500);
    test.logs.forEach(([stream, line], i) => {
      log(from + Math.round(((i + 1) / (test.logs.length + 1)) * (done.t - from)), stream, line, test.test_id);
    });
    prev = new Map(prev).set(test.stage, done.t);
    for (const oid of test.observation_ids) {
      ev.push({
        t: done.t,
        type: "observation",
        data: { ...base(done.t), type: "observation", observation: { observation_id: oid, test_id: test.test_id, fact: oid.split("-").slice(2).join("-") } },
      });
    }
    ev.push({
      t: done.t,
      type: "test_result",
      data: {
        ...base(done.t),
        type: "test_result",
        test_id: test.test_id,
        template_id: test.template_id,
        outcome: test.outcome,
        expected: mockTemplate(test.template_id)?.expected ?? "",
        observed: test.observed,
        duration_ms: Math.round(done.duration),
        observation_ids: test.observation_ids,
        failure_class: test.failure_class ?? null,
        title: mockTemplate(test.template_id)?.title ?? test.template_id,
        negative: mockTemplate(test.template_id)?.negative ?? false,
        planned_by: test.planned_by,
      },
    });
  }

  for (const a of artifactsOf(rec, tl, Number.MAX_SAFE_INTEGER)) {
    const spec_a = spec.artifacts.find((x) => x.artifact_id === a.artifact_id);
    const seg = spec_a ? tl.segments[spec_a.stage] : undefined;
    if (!seg) continue;
    ev.push({ t: seg.end, type: "artifact", data: { ...base(seg.end), type: "artifact", ...a, path: a.name } });
  }

  const traceList = tracesAt(rec, Number.MAX_SAFE_INTEGER, tl);
  for (const which of ["plan", "report", "alternatives"] as const) {
    const at = aiAt(tl, which);
    const aiModule = which === "plan" ? "planner" : which === "report" ? "explainer" : "alternatives";
    const view = which === "plan" ? spec.aiPlan : which === "report" ? spec.aiReport : spec.aiAlternatives;
    const trace = traceList.find((x) => x.module === aiModule);
    if (at === null) continue;
    if (trace) ev.push({ t: at, type: "ai", data: { kind: "trace", module: aiModule, trace } });
    if (view) ev.push({ t: at, type: "ai", data: { kind: "result", module: aiModule, status: view.status, view: { ...view, trace_ids: trace ? [trace.trace_id] : [] } } });
  }

  const runnerEnd = tl.failTime ?? tl.segments.EMULATION_TESTS?.end;
  if (runnerEnd !== undefined) {
    if (tl.failTime !== null && spec.failure) {
      ev.push({ t: tl.failTime, type: "error", data: { ...base(tl.failTime), type: "error", ...spec.failure } });
    }
    ev.push({
      t: runnerEnd,
      type: "done",
      data: { ...base(runnerEnd), type: "done", status: tl.failTime !== null ? "FAILED" : "SUCCEEDED", summary: "", tool_versions: spec.tool_versions, source_pins: spec.source_pins },
    });
  }
  if (tl.segments.EVALUATION) ev.push({ t: tl.segments.EVALUATION.end, type: "run", data: null });
  ev.push({ t: tl.failTime ?? tl.total, type: "run", data: null });

  ev.sort((a, b) => a.t - b.t);
  return ev;
}

export function eventsFor(rec: RunRecord): TimedEvent[] {
  return timeline(rec).events;
}

export function totalDuration(rec: RunRecord): number {
  const tl = timeline(rec);
  return tl.failTime ?? tl.total;
}

export function planAt(rec: RunRecord, t: number): PlannedTestView[] {
  const tl = timeline(rec);
  const ready = tl.segments.AI_PLAN ? t >= tl.segments.AI_PLAN.end : t >= (tl.segments.PREPARING?.end ?? 0);
  if (!ready) return [];
  return tl.spec.tests.map((x) => {
    const tpl = mockTemplate(x.template_id);
    return {
      template_id: x.template_id,
      test_id: x.test_id,
      planned_by: x.planned_by,
      title: tpl?.title ?? x.template_id,
      negative: tpl?.negative ?? false,
      est_seconds: tpl?.est_seconds ?? 0,
      params: {},
    };
  });
}