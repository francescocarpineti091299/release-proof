"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bot, Clock, Cpu, History, Plus, RotateCcw } from "lucide-react";
import { api, type ConnectionState } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatDuration, formatTimestamp } from "@/lib/format";
import { citationIndex, isTerminal } from "@/lib/semantics";
import type { AITraceView, ArtifactView, PlannedTestView, ResultView, RunView, TestResultView } from "@/lib/types";
import { buttonClass } from "@/components/ui/button";
import { Card, Section } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { ModeChip, RunStatusChip } from "@/components/ui/status";
import { describeRun } from "@/components/home/recent-runs";
import { AIPlanCard } from "./ai-plan-card";
import { Alternatives } from "./alternatives";
import { AssistantDrawer } from "./assistant-drawer";
import { DecisionPanel, FailureBanner, MainCauses, VerifiedAndUnknown } from "./decision";
import { EvidenceExplorer } from "./evidence";
import { LogTail } from "./log-tail";
import { RequirementsTable } from "./requirements-table";
import { StageTimeline } from "./stage-timeline";
import { TechnicalDetails } from "./technical-details";
import { TestsTable } from "./tests-table";
import { TracesTable } from "./traces-table";
import type { LiveLog, StreamError } from "./use-live-run";

export interface RunReportProps {
  run: RunView;
  result: ResultView | null;
  traces: AITraceView[];
  artifacts: ArtifactView[];
  logs?: LiveLog[];
  conn?: ConnectionState;
  observations?: number;
  streamErrors?: StreamError[];
  plan?: PlannedTestView[];
  /** Hide live-only UI (reference page). */
  recorded?: boolean;
  recordedNote?: string;
}

export function RunReport({ run, result, traces, artifacts, logs = [], conn = "closed", observations = 0, streamErrors = [], plan = [], recorded = false, recordedNote }: RunReportProps) {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const profiles = useApi("configurations", () => api.listConfigurations());
  const catalog = useApi("catalog", () => api.getCatalog());
  const d = describeRun(run, profiles.data);
  const known = useMemo(() => citationIndex(result), [result]);
  const live = !isTerminal(run.status);
  const done = isTerminal(run.status);
  const aiPlanStage = run.stages.find((s) => s.stage === "AI_PLAN");
  const total = run.started_at && run.finished_at ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime() : null;
  const showDecisionFirst = done || !!run.verdict;
  const amdTraceCount = traces.length;
  const tests = useMemo(() => mergePlan(run.tests, plan), [run.tests, plan]);
  const estimates = useMemo(() => Object.fromEntries(plan.map((p) => [p.template_id, p.est_seconds])), [plan]);

  const decision = (
    <Section id="decision" eyebrow="Decision" title="Can this migration proceed as planned?">
      <div className="space-y-4">
        <DecisionPanel run={run} />
        {run.verdict ? (
          <>
            <MainCauses run={run} result={result} known={known} />
            <VerifiedAndUnknown run={run} result={result} known={known} />
          </>
        ) : null}
      </div>
    </Section>
  );

  const progress = (
    <Section
      id="progress"
      eyebrow={recorded ? "Recorded pipeline" : "How it was checked"}
      title={live ? "Live progress" : "Pipeline"}
      description={
        live
          ? "Every stage reports real status and duration as the runner streams events. No simulated percentages."
          : run.mode === "REEVALUATION"
            ? "Re-evaluation: build and emulation stages are skipped; the parent run's evidence is evaluated under a different plan."
            : undefined
      }
      actions={
        <span className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
          {observations ? <span>{observations} observations</span> : null}
          {total !== null ? (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-4 w-4" aria-hidden /> total {formatDuration(total)}
            </span>
          ) : null}
        </span>
      }
    >
      <div className="space-y-4">
        <StageTimeline stages={run.stages} />
        {streamErrors.length && !run.failure ? (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-950">
            {streamErrors.map((e, i) => (
              <div key={i}>
                <span className="font-semibold">{e.failure_class}</span>
                {e.test_id ? ` (${e.test_id})` : ""}: {e.message}
              </div>
            ))}
          </div>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <div id="tests" className="scroll-mt-24 space-y-2">
            <h3 className="text-base font-bold">Tests ({tests.length})</h3>
            {run.mode === "REEVALUATION" && !tests.length ? (
              <Card className="p-4 text-sm text-slate-700">
                No tests were re-executed. Evidence comes from{" "}
                {run.parent_run_id ? (
                  <Link href={`/runs/${encodeURIComponent(run.parent_run_id)}`} className="font-mono-id font-semibold text-link hover:underline">
                    {run.parent_run_id}
                  </Link>
                ) : (
                  "the parent run"
                )}
                .
              </Card>
            ) : (
              <TestsTable tests={tests} live={live} estimates={estimates} recorded={recorded} />
            )}
          </div>
          <div className="space-y-2">
            <h3 className="text-base font-bold">Plan</h3>
            <AIPlanCard
              plan={run.ai_plan}
              tests={tests}
              catalog={catalog.data ?? null}
              pending={live && aiPlanStage?.status === "RUNNING"}
              waiting={live && (!aiPlanStage || aiPlanStage.status === "QUEUED")}
              skippedStage={aiPlanStage?.status === "SKIPPED"}
            />
          </div>
        </div>
        {!recorded ? <LogTail logs={logs} conn={conn} /> : null}
      </div>
    </Section>
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="mb-4">
        <Link href="/" className="inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-950">
          <ArrowLeft className="h-4 w-4" aria-hidden /> All assessments
        </Link>
      </div>

      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <ModeChip mode={run.mode} />
            <RunStatusChip status={run.status} />
            <span className="font-mono-id text-slate-600">{run.run_id}</span>
          </div>
          <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-slate-950 sm:text-3xl">{d.config}</h1>
          <p className="mt-1 text-base text-slate-700">
            {d.change} <span className="text-slate-400">·</span> plan: <span className="font-semibold">{d.plan}</span>
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Created {formatTimestamp(run.created_at)}
            {run.finished_at ? ` · finished ${formatTimestamp(run.finished_at)}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {!recorded ? (
            <button type="button" className={buttonClass("primary")} onClick={() => setAssistantOpen(true)}>
              <Bot className="h-4 w-4" aria-hidden /> Ask about this run
            </button>
          ) : null}
          <Link href="/" className={buttonClass("secondary")}>
            <Plus className="h-4 w-4" aria-hidden /> New assessment
          </Link>
        </div>
      </header>

      <nav aria-label="On this page" className="mb-6 flex flex-wrap gap-x-4 gap-y-1 border-b border-border pb-3 text-sm font-semibold text-slate-600">
        {(
          [
            ["#decision", "Decision", true],
            ["#suggestions", "Alternatives", showDecisionFirst && !!run.verdict && !recorded],
            ["#progress", "Pipeline", true],
            ["#evidence", "Evidence", true],
            ["#requirements", "Requirements", true],
            ["#amd", `AMD AI (${amdTraceCount})`, true],
            ["#technical", "Technical details", true],
          ] as const
        )
          .filter(([, , show]) => show)
          .map(([href, label]) => (
            <a key={href} href={href} className="hover:text-slate-950">
              {label}
            </a>
          ))}
      </nav>

      <div className="space-y-4">
        {run.mode === "REFERENCE" ? (
          <div className="flex items-start gap-3 rounded-lg border-2 border-slate-500 bg-slate-100 p-4">
            <History className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
            <p className="text-sm text-slate-900">
              <span className="font-bold">RECORDED.</span> This run was recorded during the WP0 freeze and is not live. Nothing on this page was executed in this session.
              {recordedNote ? <span className="mt-1 block text-slate-700">{recordedNote}</span> : null}
            </p>
          </div>
        ) : null}
        {run.mode === "REEVALUATION" ? (
          <div className="flex items-start gap-3 rounded-lg border-2 border-amber-400 bg-amber-50 p-4">
            <RotateCcw className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" aria-hidden />
            <p className="text-sm text-amber-950">
              <span className="font-bold">
                Re-evaluation of plan <span className="font-mono-id">{run.plan_id}</span> on evidence from run{" "}
                {run.parent_run_id ? (
                  <Link href={`/runs/${encodeURIComponent(run.parent_run_id)}`} className="font-mono-id underline">
                    {run.parent_run_id}
                  </Link>
                ) : (
                  "(unknown)"
                )}
              </span>{" "}
              (no new emulation). The parent run and its verdict are unchanged.
            </p>
          </div>
        ) : null}
        {run.status === "QUEUED" ? (
          <div className="flex items-center gap-3 rounded-lg border-2 border-blue-300 bg-blue-50 p-4 text-blue-950">
            <Cpu className="h-5 w-5 shrink-0" aria-hidden />
            <p className="text-sm">
              <span className="font-bold">Queued{run.queue_position ? `: position ${run.queue_position}` : ""}.</span> Emulation workers are limited, so runs start in order. This page updates automatically.
            </p>
          </div>
        ) : null}
        <FailureBanner run={run} />
        {run.ai_plan && run.ai_plan.status === "AI_UNAVAILABLE" ? (
          <p className="text-sm">
            <Chip tone="amber" size="xs">
              AI_UNAVAILABLE
            </Chip>{" "}
            <span className="text-slate-700">The AMD-hosted planner was unavailable. The run used the deterministic fallback plan; no non-AMD model was used.</span>
          </p>
        ) : null}
      </div>

      <div className="mt-6 space-y-10">
        {showDecisionFirst ? decision : progress}
        {showDecisionFirst ? (
          run.verdict && !recorded ? (
            <Section
              id="suggestions"
              eyebrow="Next steps"
              title="What AI suggests"
              description={
                run.ai_alternatives?.status === "OK"
                  ? "Alternative plans drafted by the AMD-hosted model, restricted to plans registered for this configuration."
                  : "The AMD-hosted model did not draft proposals for this run. Registered alternative plans are listed instead."
              }
            >
              <Alternatives run={run} scenario={d.scenario} known={known} />
            </Section>
          ) : null
        ) : (
          decision
        )}
        {showDecisionFirst ? progress : null}

        <Section id="evidence" eyebrow="Explore evidence" title="Evidence explorer" description="Every V1.2 evidence row used by the engine, with where it came from and the artifacts behind it.">
          <EvidenceExplorer evidence={result?.evidence ?? []} />
        </Section>

        <Section id="requirements" eyebrow="Engine result" title="Requirements and invariants">
          <RequirementsTable result={result} known={known} />
        </Section>

        <Section
          id="amd"
          eyebrow="AMD AI"
          title="AI calls for this run"
          description="Every model call is traced: module, model, AMD hardware, endpoint, latency and tokens."
          actions={
            <Link href="/amd" className="text-sm font-semibold text-link hover:underline">
              All AMD AI evidence →
            </Link>
          }
        >
          <TracesTable traces={traces} empty={recorded ? "The recorded reference predates the AI integration: no AI calls." : "No AI calls recorded for this run yet."} />
        </Section>

        <Section id="technical" eyebrow="For engineers" title="Technical details">
          <TechnicalDetails run={run} result={result} artifacts={artifacts} />
        </Section>
      </div>

      {!recorded ? (
        <>
          {!assistantOpen ? (
            <button
              type="button"
              onClick={() => setAssistantOpen(true)}
              className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-lg hover:bg-slate-800"
            >
              <Bot className="h-5 w-5 text-violet-300" aria-hidden /> Ask about this run
            </button>
          ) : null}
          <AssistantDrawer key={run.run_id} runId={run.run_id} open={assistantOpen} onClose={() => setAssistantOpen(false)} citations={known} />
        </>
      ) : null}
    </div>
  );
}

/** Planned tests first (in plan order), overlaid with results as they arrive. */
function mergePlan(tests: TestResultView[], plan: PlannedTestView[]): TestResultView[] {
  if (!plan.length) return tests;
  const byId = new Map(tests.map((t) => [t.template_id, t]));
  const rows: TestResultView[] = plan.map(
    (p) =>
      byId.get(p.template_id) ?? {
        test_id: p.test_id,
        template_id: p.template_id,
        title: p.title,
        negative: p.negative,
        outcome: "NOT_EXECUTED",
        expected: "",
        observed: "",
        duration_ms: 0,
        observation_ids: [],
        failure_class: null,
        planned_by: p.planned_by,
      },
  );
  const planned = new Set(plan.map((p) => p.template_id));
  return [...rows, ...tests.filter((t) => !planned.has(t.template_id))];
}
