"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ConnectionState, type StreamEvent } from "@/lib/api";
import { isTerminal } from "@/lib/semantics";
import type { AIAlternativesView, AIPlanView, AIReportView, AITraceView, ArtifactView, LogStream, PlannedTestView, ResultView, RunView, StageView, TestResultView } from "@/lib/types";
import { isRecord } from "@/lib/utils";

export interface LiveLog {
  key: string;
  stream: LogStream;
  line: string;
  test_id: string | null;
  ts: string | null;
}

export interface StreamError {
  failure_class: string;
  message: string;
  test_id?: string | null;
}

const MAX_LOGS = 2000;

function asStageView(d: Record<string, unknown>): Partial<StageView> & { stage: StageView["stage"] } {
  return d as unknown as StageView;
}

export function useLiveRun(runId: string) {
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [logs, setLogs] = useState<LiveLog[]>([]);
  const [observations, setObservations] = useState(0);
  const [conn, setConn] = useState<ConnectionState>("connecting");
  const [result, setResult] = useState<ResultView | null>(null);
  const [traces, setTraces] = useState<AITraceView[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactView[]>([]);
  const [streamErrors, setStreamErrors] = useState<StreamError[]>([]);
  const [plan, setPlan] = useState<PlannedTestView[]>([]);
  const resultLoaded = useRef(false);
  const planLoaded = useRef(false);
  const generation = useRef(0);
  const refreshSequence = useRef(0);

  const refresh = useCallback(async (): Promise<RunView | null> => {
    const current = generation.current;
    const sequence = ++refreshSequence.current;
    const active = () => generation.current === current;
    try {
      const r = await api.getRun(runId);
      if (!active() || sequence !== refreshSequence.current) return null;
      setRun(r);
      setError(null);
      const done = isTerminal(r.status);
      if ((r.verdict || done) && !resultLoaded.current) {
        api
          .getResult(runId)
          .then((res) => {
            if (active() && res) {
              resultLoaded.current = true;
              setResult(res);
            }
          })
          .catch(() => undefined);
      }
      api.getTraces(runId).then((t) => active() && setTraces(t)).catch(() => undefined);
      const planReady = r.stages.some((s) => s.stage === "AI_PLAN" && s.status !== "QUEUED" && s.status !== "RUNNING");
      if (planReady && !planLoaded.current) {
        api
          .getPlan(runId)
          .then((p) => {
            if (active() && p.length) {
              planLoaded.current = true;
              setPlan(p);
            }
          })
          .catch(() => undefined);
      }
      if (done) api.getArtifacts(runId).then((a) => active() && setArtifacts(a)).catch(() => undefined);
      return r;
    } catch (e) {
      if (!active() || sequence !== refreshSequence.current) return null;
      setError(e instanceof Error ? e : new Error(String(e)));
      return null;
    }
  }, [runId]);

  const hasRun = Boolean(run);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let closeTimer: ReturnType<typeof setTimeout> | null = null;
    let replayingTerminal = false;
    const seen = new Set<number>();
    let unsubscribe: () => void = () => undefined;

    const schedule = (ms = 500) => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        void refresh().then((r) => {
          if (alive && r && isTerminal(r.status) && !replayingTerminal && !closeTimer) {
            // Let the final persisted events arrive before closing the stream.
            closeTimer = setTimeout(() => unsubscribe(), 1500);
          }
        });
      }, ms);
    };

    const onEvent = (ev: StreamEvent) => {
      if (!alive) return;
      if (ev.id !== null) {
        if (seen.has(ev.id)) return;
        seen.add(ev.id);
        if (seen.size > 10_000) seen.delete(seen.values().next().value!);
      }
      const d = ev.data;
      switch (ev.type) {
        case "log": {
          const entry: LiveLog = {
            key: `${ev.id ?? ""}-${String(d.seq ?? "")}-${Math.random().toString(36).slice(2, 7)}`,
            stream: (d.stream as LogStream) ?? "runner",
            line: String(d.line ?? ""),
            test_id: (d.test_id as string | null) ?? null,
            ts: (d.ts as string | null) ?? null,
          };
          setLogs((prev) => (prev.length >= MAX_LOGS ? [...prev.slice(-MAX_LOGS + 1), entry] : [...prev, entry]));
          break;
        }
        case "observation":
          setObservations((n) => n + 1);
          break;
        case "artifact": {
          if (typeof d.artifact_id === "string" && typeof d.sha256 === "string") {
            const a: ArtifactView = {
              artifact_id: d.artifact_id,
              name: String(d.name ?? d.path ?? d.artifact_id),
              kind: String(d.kind ?? "other"),
              sha256: d.sha256,
              size_bytes: Number(d.size_bytes ?? 0),
              test_id: (d.test_id as string | null) ?? null,
              url: typeof d.url === "string" ? d.url : `/api/assessments/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(d.artifact_id)}`,
            };
            setArtifacts((prev) => (prev.some((x) => x.artifact_id === a.artifact_id) ? prev : [...prev, a]));
          }
          break;
        }
        case "stage": {
          const s = asStageView(d);
          if (s.stage) {
            const ts = typeof d.ts === "string" ? d.ts : null;
            const final = s.status && s.status !== "RUNNING" && s.status !== "QUEUED";
            const full = "started_at" in d || "duration_ms" in d;
            setRun((prev) =>
              prev
                ? {
                    ...prev,
                    stages: prev.stages.map((x) => {
                      if (x.stage !== s.stage) return x;
                      if (full) {
                        return {
                          stage: x.stage,
                          status: s.status ?? x.status,
                          started_at: s.started_at ?? x.started_at ?? null,
                          finished_at: s.finished_at ?? null,
                          duration_ms: s.duration_ms ?? null,
                          message: s.message ?? x.message,
                        };
                      }
                      const started_at = x.started_at ?? (s.status === "RUNNING" ? ts : null);
                      const duration =
                        final && ts && started_at ? Math.max(0, new Date(ts).getTime() - new Date(started_at).getTime()) : x.duration_ms;
                      return {
                        ...x,
                        status: s.status ?? x.status,
                        message: s.message ?? x.message,
                        started_at,
                        finished_at: final ? (ts ?? x.finished_at) : x.finished_at,
                        duration_ms: duration ?? null,
                      };
                    }),
                  }
                : prev,
            );
          }
          schedule();
          break;
        }
        case "test_result": {
          const t = d as unknown as Partial<TestResultView>;
          if (t.template_id) {
            setRun((prev) =>
              prev
                ? {
                    ...prev,
                    tests: prev.tests.some((x) => x.template_id === t.template_id)
                      ? prev.tests.map((x) =>
                          x.template_id === t.template_id
                            ? { ...x, ...t, planned_by: t.planned_by ?? x.planned_by, title: t.title ?? x.title, negative: t.negative ?? x.negative }
                            : x,
                        )
                      : t.title && t.planned_by
                        ? [...prev.tests, t as TestResultView]
                        : prev.tests,
                  }
                : prev,
            );
          }
          schedule();
          break;
        }
        case "run": {
          if (isRecord(d) && typeof d.run_id === "string" && Array.isArray(d.stages)) {
            const r = d as unknown as RunView;
            setRun(r);
            if (r.verdict || isTerminal(r.status)) schedule(100);
          } else schedule();
          break;
        }
        case "error":
          setStreamErrors((prev) => [...prev.slice(-99), { failure_class: String(d.failure_class ?? "ERROR"), message: String(d.message ?? ""), test_id: (d.test_id as string | null) ?? null }]);
          schedule();
          break;
        case "ai": {
          // {kind: "trace", module, trace} | {kind: "result", module, status, view}
          if (d.kind === "trace" && isRecord(d.trace) && typeof d.trace.trace_id === "string") {
            const tr = d.trace as unknown as AITraceView;
            setTraces((prev) => (prev.some((x) => x.trace_id === tr.trace_id) ? prev : [...prev, tr]));
          } else if (d.kind === "result" && isRecord(d.view)) {
            const view = d.view;
            setRun((prev) => {
              if (!prev) return prev;
              if (d.module === "planner") return { ...prev, ai_plan: view as unknown as AIPlanView };
              if (d.module === "explainer") return { ...prev, ai_report: view as unknown as AIReportView };
              if (d.module === "alternatives") return { ...prev, ai_alternatives: view as unknown as AIAlternativesView };
              return prev;
            });
          }
          schedule(300);
          break;
        }
        case "done":
          schedule(200);
          break;
      }
    };

    void Promise.resolve()
      .then(() => alive ? refresh() : null)
      .then((r) => {
        if (!alive || !r || !hasRun) return;
        // Even for finished runs, replay the stored stream once so logs are visible.
        unsubscribe = api.subscribe(runId, { onEvent, onState: (s) => alive && setConn(s) });
        if (isTerminal(r.status)) {
          replayingTerminal = true;
          // Close a little later: replay of persisted events arrives first.
          const t = setTimeout(() => unsubscribe(), 8000);
          const prev = unsubscribe;
          unsubscribe = () => {
            clearTimeout(t);
            prev();
          };
        }
      });

    return () => {
      alive = false;
      generation.current += 1;
      if (timer) clearTimeout(timer);
      if (closeTimer) clearTimeout(closeTimer);
      unsubscribe();
    };
  }, [runId, refresh, hasRun]);

  // Polling fallback while the stream is not connected.
  const status = run?.status;
  useEffect(() => {
    if ((status && isTerminal(status)) || conn === "open") return;
    const id = setInterval(() => void refresh(), 5000);
    return () => clearInterval(id);
  }, [status, conn, refresh]);

  return { run, error, logs, observations, conn, result, traces, artifacts, streamErrors, plan, refresh };
}
