"use client";

import { BadgeInfo, Bot, CheckCircle2, CircleHelp, Cog, Fingerprint, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { formatValue, shortHash } from "@/lib/format";
import {
  deterministicCauses,
  evidenceGaps,
  FAILURE_HELP,
  SCOPE_HELP,
  unknownRows,
  verdictMeta,
} from "@/lib/semantics";
import type { ResultView, RunView } from "@/lib/types";
import { citationAnchor, cn } from "@/lib/utils";
import { Card, Empty } from "@/components/ui/card";
import { Chip, TONE_BORDER } from "@/components/ui/chip";
import { Citations } from "@/components/ui/citation";
import { Hint } from "@/components/ui/hint";
import { OutcomeChip, StateChip, VerdictChip, VerdictIcon } from "@/components/ui/status";

const BIG_TEXT = {
  green: "text-emerald-800",
  amber: "text-amber-700",
  slate: "text-slate-700",
  red: "text-red-700",
  blue: "text-blue-800",
  neutral: "text-slate-600",
} as const;

const BIG_BG = {
  green: "bg-emerald-50",
  amber: "bg-amber-50",
  slate: "bg-slate-100",
  red: "bg-red-50",
  blue: "bg-blue-50",
  neutral: "bg-slate-50",
} as const;

export function DecisionPanel({ run }: { run: RunView }) {
  const v = run.verdict;
  if (!v) {
    if (run.status === "FAILED" || run.status === "CANCELLED") {
      return (
        <Card className="border-l-8 border-l-slate-400 p-5">
          <div className="flex items-start gap-3">
            <XCircle className="h-8 w-8 shrink-0 text-slate-500" aria-hidden />
            <div>
              <div className="text-2xl font-extrabold text-slate-800">No verdict was issued</div>
              <p className="mt-1 text-slate-600">
                The pipeline {run.status === "FAILED" ? "failed" : "was cancelled"} before evaluation. A tool failure is not a firmware result, so the engine did not judge the migration.
              </p>
            </div>
          </div>
        </Card>
      );
    }
    return (
      <Card className="border-l-8 border-l-blue-400 p-5">
        <div className="flex items-start gap-3">
          <Loader2 className="h-7 w-7 shrink-0 animate-spin text-blue-600" aria-hidden />
          <div>
            <div className="text-xl font-bold text-slate-900">Verdict pending</div>
            <p className="mt-1 text-slate-600">The deterministic V1.2 engine issues the verdict after every test has reported. No result is predicted in advance.</p>
          </div>
        </div>
      </Card>
    );
  }

  const meta = verdictMeta(v.migration);
  return (
    <Card className={cn("overflow-hidden border-l-8", TONE_BORDER[meta.tone])}>
      <div className="grid lg:grid-cols-[1fr_minmax(18rem,26rem)]">
        <div className={cn("p-5 sm:p-6", BIG_BG[meta.tone])}>
          <div className="flex items-center gap-1 text-xs font-bold uppercase tracking-widest text-slate-600">
            Overall migration <Hint text={SCOPE_HELP.migration} />
          </div>
          <div className={cn("mt-1 flex items-center gap-3", BIG_TEXT[meta.tone])}>
            <VerdictIcon verdict={v.migration} className="h-10 w-10 shrink-0 sm:h-12 sm:w-12" />
            <div>
              <div className="text-3xl font-black tracking-tight sm:text-5xl">{v.migration ?? "—"}</div>
              <div className="text-base font-bold sm:text-lg">{meta.short}</div>
            </div>
          </div>
          <p className="mt-3 text-lg font-semibold text-slate-950">{meta.answer}</p>
          <p className="mt-1 max-w-2xl text-sm text-slate-700">{meta.explain}</p>
        </div>
        <div className="flex flex-col gap-3 border-t border-border p-5 lg:border-l lg:border-t-0">
          <ScopeTile label="Candidate" help={SCOPE_HELP.candidate} verdict={v.candidate} subtitle="Is the new firmware state itself sound?" />
          <ScopeTile label="Transition" help={SCOPE_HELP.transition} verdict={v.transition} subtitle="Can deployed devices get there?" />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-border bg-white px-5 py-3 text-xs">
        <Chip tone="neutral" title="official=false. An engineering assessment, not a certification.">
          <BadgeInfo className="h-3.5 w-3.5" aria-hidden /> Non-official engineering assessment
        </Chip>
        <Chip tone="neutral" title="The verdict is computed by the deterministic V1.2 rule engine. AI output never changes it.">
          <Cog className="h-3.5 w-3.5" aria-hidden /> Deterministic engine · contract V1.2
        </Chip>
        {v.canonical_hash ? (
          <span className="inline-flex items-center gap-1 font-mono-id text-slate-600" title={v.canonical_hash}>
            <Fingerprint className="h-3.5 w-3.5" aria-hidden /> {shortHash(v.canonical_hash)}
          </span>
        ) : null}
        <span className="ml-auto text-slate-500">Lifecycle {v.lifecycle}</span>
      </div>
    </Card>
  );
}

function ScopeTile({ label, help, verdict, subtitle }: { label: string; help: string; verdict: string | null; subtitle: string }) {
  const meta = verdictMeta(verdict);
  return (
    <div className={cn("rounded-lg border-2 p-3", TONE_BORDER[meta.tone])}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1 text-sm font-bold text-slate-900">
          {label} <Hint text={help} />
        </span>
        <VerdictChip verdict={verdict} size="sm" />
      </div>
      <p className="mt-1 text-xs text-slate-600">
        {subtitle} <span className="font-semibold">{meta.short}.</span>
      </p>
    </div>
  );
}

export function MainCauses({ run, result, known }: { run: RunView; result: ResultView | null; known: Set<string> }) {
  const report = run.ai_report?.status === "OK" ? run.ai_report.report : null;
  const det = deterministicCauses(result);
  const aiState = run.ai_report?.status;

  if (report) {
    return (
      <Card className="p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="text-lg font-bold">Main causes</h3>
          <Chip tone="blue" size="xs" className="border-violet-300 bg-violet-50 text-violet-800" title="Written by the AMD-hosted explainer from this run's evidence. Citations are checked against the run.">
            <Bot className="h-3 w-3" aria-hidden /> AI explanation · AMD-hosted
          </Chip>
        </div>
        <p className="text-base font-semibold text-slate-950">{report.headline}</p>
        <ol className="mt-3 space-y-3">
          {report.main_causes.map((c, i) => (
            <li key={i} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">{i + 1}</span>
              <div className="min-w-0">
                <p className="text-slate-900">{c.text}</p>
                <div className="mt-1">
                  <Citations ids={c.citations} known={known} />
                </div>
              </div>
            </li>
          ))}
        </ol>
        {report.executive_summary ? <p className="mt-4 border-t border-border pt-3 text-sm text-slate-700">{report.executive_summary}</p> : null}
        <p className="mt-3 text-xs text-slate-500">The explanation is written by AI from the cited evidence. The verdict above comes from the deterministic engine.</p>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-bold">Main causes</h3>
        <Chip tone="neutral" size="xs">
          <Cog className="h-3 w-3" aria-hidden /> From the engine result
        </Chip>
        {aiState && aiState !== "OK" && aiState !== "NOT_REQUESTED" ? (
          <Chip tone="amber" size="xs" title={run.ai_report?.message}>
            AI explanation unavailable · {aiState}
          </Chip>
        ) : null}
      </div>
      {aiState && aiState !== "OK" && aiState !== "NOT_REQUESTED" ? (
        <p className="mb-3 text-sm text-slate-600">
          The AMD-hosted explainer did not produce a report{run.ai_report?.message ? ` (${run.ai_report.message})` : ""}. These causes are the critical violated or unknown
          requirements and invariants, taken directly from the deterministic engine result.
        </p>
      ) : null}
      {!result ? (
        <Empty>Loading the engine result…</Empty>
      ) : det.length === 0 ? (
        <p className="text-slate-700">No critical requirement or invariant is violated or unknown.</p>
      ) : (
        <ol className="space-y-3">
          {det.map((c, i) => (
            <li key={c.id} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">{i + 1}</span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono-id font-semibold">{c.id}</span>
                  <StateChip state={c.state} />
                  <span className="text-xs text-slate-500">in {c.phases.map((p) => p.toLowerCase()).join(", ")}</span>
                </div>
                <p className="mt-0.5 text-slate-900">{c.text}</p>
                <div className="mt-1">
                  <Citations ids={c.citations.filter((x) => x !== c.id)} known={known} />
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

export function VerifiedAndUnknown({ run, result, known }: { run: RunView; result: ResultView | null; known: Set<string> }) {
  const passed = run.tests.filter((t) => t.outcome === "PASS");
  const notDecisive = run.tests.filter((t) => t.outcome !== "PASS");
  const measured = (result?.evidence ?? []).filter(
    (e) => e.evidence_kind === "MEASUREMENT" && e.origin !== "NOT_OBSERVED" && e.value !== "UNKNOWN" && e.value !== null,
  );
  const unknowns = unknownRows(result);
  const gaps = evidenceGaps(result);
  const reeval = run.mode === "REEVALUATION";

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-5">
        <h3 className="flex items-center gap-2 text-lg font-bold">
          <CheckCircle2 className="h-5 w-5 text-emerald-700" aria-hidden /> What we verified
        </h3>
        <p className="mt-1 text-sm text-slate-600">
          {reeval
            ? "Observed in the parent run and reused here."
            : run.mode === "REFERENCE"
              ? "Measured during the recorded WP0 freeze (2026-10-01); not executed in this view."
              : "Observed live in this run by build tools and Renode."}
        </p>
        {passed.length ? (
          <ul className="mt-3 space-y-2">
            {passed.map((t) => (
              <li key={t.template_id} className="flex items-start gap-2 text-sm">
                <OutcomeChip outcome={t.outcome} />
                <span className="min-w-0">
                  <span className="font-semibold text-slate-900">{t.title}</span>
                  {t.negative ? (
                    <span className="ml-1 inline-flex items-center gap-0.5 text-xs font-semibold text-slate-600">
                      <ShieldAlert className="h-3 w-3" aria-hidden /> negative
                    </span>
                  ) : null}
                  <span className="block text-slate-600 line-clamp-2 [overflow-wrap:anywhere]" title={t.observed}>
                    {t.observed}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-slate-600">
            {reeval ? "No tests were re-executed." : run.mode === "REFERENCE" ? "No tests in this view; see the measured evidence below." : "No test passed in this run."}
          </p>
        )}
        {measured.length ? (
          <div className="mt-4 border-t border-border pt-3">
            <div className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">Measured evidence ({measured.length})</div>
            <Citations ids={measured.map((e) => e.id)} known={known} />
          </div>
        ) : null}
      </Card>

      <Card className="p-5">
        <h3 className="flex items-center gap-2 text-lg font-bold">
          <CircleHelp className="h-5 w-5 text-slate-600" aria-hidden /> What remains unknown
        </h3>
        <p className="mt-1 text-sm text-slate-600">Not observed, so never counted as a pass. These keep a verdict from being fully proven.</p>
        {!result ? (
          <p className="mt-3 text-sm text-slate-500">Available after evaluation.</p>
        ) : (
          <>
            {unknowns.length ? (
              <ul className="mt-3 space-y-2">
                {unknowns.map((u) => (
                  <li key={u.id} className="text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <StateChip state={u.state} />
                      <span className="font-mono-id font-semibold">{u.id}</span>
                      {u.critical ? (
                        <Chip tone="neutral" size="xs">
                          critical
                        </Chip>
                      ) : null}
                    </div>
                    {u.criterion ? <p className="mt-0.5 text-slate-800">{u.criterion}</p> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-slate-700">No requirement or invariant is unknown.</p>
            )}
            {gaps.length ? (
              <div className="mt-4 border-t border-border pt-3">
                <div className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">Evidence gaps ({gaps.length})</div>
                <ul className="space-y-2">
                  {gaps.map((g) => (
                    <li key={g.gap_id} id={citationAnchor(g.gap_id)} className="rounded-md border border-border p-2 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono-id font-semibold">{g.gap_id}</span>
                        {g.requirement_id ? <span className="text-xs text-slate-500">→ {g.requirement_id}</span> : null}
                        {g.critical ? (
                          <Chip tone="slate" size="xs">
                            critical
                          </Chip>
                        ) : null}
                        {g.gap_type ? <span className="text-xs text-slate-500">{g.gap_type}</span> : null}
                      </div>
                      {g.reason ? <p className="mt-0.5 text-slate-800">{g.reason}</p> : null}
                      {g.requested_evidence ? <p className="text-xs text-slate-600">Needed: {g.requested_evidence}</p> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {result.result.conditions?.length ? (
              <div className="mt-4 border-t border-border pt-3">
                <div className="mb-1.5 text-xs font-bold uppercase tracking-wide text-amber-700">Open conditions</div>
                <ul className="space-y-1 text-sm">
                  {result.result.conditions.map((c, i) => (
                    <li key={c.condition_id ?? i}>
                      <span className="font-mono-id font-semibold">{c.condition_id}</span>
                      <span className="text-slate-600">
                        {" "}
                        on {c.requirement_id} at {c.step_id}
                        {c.allowed_by_profile ? " (allowed by the profile)" : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
        {notDecisive.length ? (
          <div className="mt-4 border-t border-border pt-3">
            <div className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">Tests without a pass</div>
            <ul className="space-y-1.5 text-sm">
              {notDecisive.map((t) => (
                <li key={t.template_id} className="flex items-start gap-2">
                  <OutcomeChip outcome={t.outcome} />
                  <span className="min-w-0 [overflow-wrap:anywhere]">
                    <span className="font-semibold">{t.title}</span>
                    {t.observed ? (
                      <span className="block text-slate-600 line-clamp-3" title={formatValue(t.observed)}>
                        {formatValue(t.observed)}
                      </span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

export function FailureBanner({ run }: { run: RunView }) {
  if (run.status !== "FAILED") return null;
  const f = run.failure;
  return (
    <div role="alert" className="rounded-lg border-2 border-red-600 bg-red-50 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <XCircle className="h-7 w-7 shrink-0 text-red-700" aria-hidden />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-extrabold text-red-900">Run failed: no verdict issued</span>
            {f ? (
              <Chip tone="red" solid size="sm">
                {f.failure_class}
              </Chip>
            ) : null}
          </div>
          <p className="mt-1 text-red-950">{f?.message ?? "The pipeline stopped before evaluation."}</p>
          {f ? <p className="mt-1 text-sm text-red-800">{FAILURE_HELP[f.failure_class] ?? ""}</p> : null}
          <p className="mt-2 text-sm text-slate-700">
            This is a job failure (a tool did not complete). It is different from a negative test that passes, and from a migration verdict.
          </p>
        </div>
      </div>
    </div>
  );
}
