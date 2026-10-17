"use client";

import { useState } from "react";
import { ShieldAlert, Sparkles } from "lucide-react";
import { formatDuration } from "@/lib/format";
import { PLANNED_BY_HELP, PLANNED_BY_LABEL } from "@/lib/semantics";
import type { TestResultView } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/ui/chip";
import { Empty } from "@/components/ui/card";
import { Hint } from "@/components/ui/hint";
import { OutcomeChip } from "@/components/ui/status";

/** Long tool output is clamped to a few lines with a toggle. */
function ObservedText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 220;
  return (
    <>
      <span className={cn(long && !open && "line-clamp-4")} title={long && !open ? text : undefined}>
        {text}
      </span>
      {long ? (
        <button type="button" onClick={() => setOpen((v) => !v)} className="mt-0.5 block text-xs font-semibold text-link hover:underline">
          {open ? "Show less" : "Show full output"}
        </button>
      ) : null}
    </>
  );
}

export function TestsTable({
  tests,
  live,
  estimates = {},
  recorded = false,
}: {
  tests: TestResultView[];
  live: boolean;
  estimates?: Record<string, number>;
  recorded?: boolean;
}) {
  if (!tests.length) {
    return (
      <Empty>
        {recorded
          ? "Recorded facts only: no test was executed in this view. The evidence explorer below lists what was measured on the recording date."
          : live
            ? "The test plan appears here once the AI planning stage completes."
            : "No tests were executed in this run."}
      </Empty>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-white">
      <div className="hidden grid-cols-[minmax(0,2.2fr)_7.5rem_6.5rem_minmax(0,1.4fr)_minmax(0,1.8fr)_4.5rem] gap-3 border-b border-border bg-slate-50 px-4 py-2 text-xs font-bold uppercase tracking-wide text-slate-600 lg:grid">
        <span>Test</span>
        <span className="flex items-center gap-1">
          Planned by <Hint text="Required tests come from the profile policy. The AI planner can only add registered optional tests." />
        </span>
        <span className="flex items-center gap-1">
          Outcome <Hint text="PASS means the test observed what it was designed to check. For a negative test, PASS means the expected rejection was observed. Not a migration verdict." />
        </span>
        <span>Expected</span>
        <span>Observed</span>
        <span className="text-right">Time</span>
      </div>
      <ul className="divide-y divide-border">
        {tests.map((t) => {
          const pending = live && t.outcome === "NOT_EXECUTED";
          return (
            <li
              key={t.template_id}
              className={cn(
                "grid gap-x-3 gap-y-1 px-4 py-3 lg:grid-cols-[minmax(0,2.2fr)_7.5rem_6.5rem_minmax(0,1.4fr)_minmax(0,1.8fr)_4.5rem] lg:items-start",
                pending && "bg-slate-50/60",
              )}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono-id rounded bg-slate-100 px-1 text-slate-700">{t.test_id}</span>
                  <span className={cn("font-semibold", pending ? "text-slate-600" : "text-slate-950")}>{t.title}</span>
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                  <span className="font-mono-id text-[11px] text-slate-500">{t.template_id}</span>
                  {t.negative ? (
                    <Chip tone="slate" size="xs" title="Negative test: passes when the bootloader refuses what it must refuse.">
                      <ShieldAlert className="h-3 w-3" aria-hidden /> Negative
                    </Chip>
                  ) : null}
                </div>
              </div>
              <div>
                <Chip
                  size="xs"
                  tone={t.planned_by === "AI_PLANNER" ? "blue" : t.planned_by === "PROFILE_OPTIONAL" ? "amber" : "neutral"}
                  title={PLANNED_BY_HELP[t.planned_by]}
                  className={t.planned_by === "AI_PLANNER" ? "border-violet-300 bg-violet-50 text-violet-800" : undefined}
                >
                  {t.planned_by === "AI_PLANNER" ? <Sparkles className="h-3 w-3" aria-hidden /> : null}
                  {PLANNED_BY_LABEL[t.planned_by]}
                </Chip>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <OutcomeChip outcome={t.outcome} pending={live} />
                {t.failure_class ? (
                  <Chip tone="red" size="xs">
                    {t.failure_class}
                  </Chip>
                ) : null}
              </div>
              <p className="min-w-0 text-sm text-slate-600 [overflow-wrap:anywhere]">
                <span className="font-semibold text-slate-500 lg:hidden">Expected: </span>
                {t.expected || "—"}
              </p>
              <p className={cn("min-w-0 text-sm [overflow-wrap:anywhere]", t.outcome === "FAIL" || t.outcome === "ERROR" ? "text-red-800" : "text-slate-900")}>
                <span className="font-semibold text-slate-500 lg:hidden">Observed: </span>
                {t.observed ? <ObservedText text={t.observed} /> : pending ? "…" : "—"}
              </p>
              <span className="font-mono-id tabular-nums text-slate-600 lg:text-right">
                {t.duration_ms ? (
                  formatDuration(t.duration_ms)
                ) : pending && estimates[t.template_id] ? (
                  <span className="text-slate-400">~{formatDuration(estimates[t.template_id] * 1000)}</span>
                ) : (
                  "—"
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
