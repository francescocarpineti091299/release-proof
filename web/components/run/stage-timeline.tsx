"use client";

import { useNow } from "@/lib/hooks";
import { formatDuration } from "@/lib/format";
import { STAGE_HELP, STAGE_LABEL } from "@/lib/semantics";
import { STAGE_ORDER, type StageView } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Hint } from "@/components/ui/hint";
import { StageStatusIcon } from "@/components/ui/status";

const STATUS_TEXT: Record<StageView["status"], string> = {
  QUEUED: "Waiting",
  RUNNING: "Running",
  SUCCEEDED: "Done",
  FAILED: "Failed",
  INCONCLUSIVE: "Inconclusive",
  SKIPPED: "Skipped",
};

export function StageTimeline({ stages }: { stages: StageView[] }) {
  const running = stages.some((s) => s.status === "RUNNING");
  const now = useNow(1000, running);
  const ordered = STAGE_ORDER.map((st) => stages.find((s) => s.stage === st) ?? { stage: st, status: "QUEUED" as const, message: "" });

  return (
    <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-7" aria-label="Pipeline stages">
      {ordered.map((s, i) => {
        const elapsed =
          s.status === "RUNNING" && s.started_at && now ? now - new Date(s.started_at).getTime() : (s.duration_ms ?? null);
        return (
          <li
            key={s.stage}
            className={cn(
              "relative flex gap-3 rounded-lg border bg-white p-3 lg:flex-col lg:gap-2",
              s.status === "RUNNING" && "border-blue-500 ring-2 ring-blue-100",
              s.status === "FAILED" && "border-red-500 bg-red-50",
              s.status === "INCONCLUSIVE" && "border-amber-400 bg-amber-50",
              s.status === "SUCCEEDED" && "border-emerald-300",
              (s.status === "QUEUED" || s.status === "SKIPPED") && "border-border",
              s.status === "SKIPPED" && "bg-slate-50",
            )}
          >
            <div className="flex items-center gap-2">
              <StageStatusIcon status={s.status} />
              <span className="text-xs font-bold text-slate-400 lg:hidden">{i + 1}</span>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-start gap-1">
                <span className={cn("text-sm font-bold leading-tight", s.status === "SKIPPED" || s.status === "QUEUED" ? "text-slate-500" : "text-slate-950")}>
                  {STAGE_LABEL[s.stage]}
                </span>
                <Hint text={STAGE_HELP[s.stage]} className="-mt-0.5" />
              </div>
              <div className="mt-1 flex flex-wrap items-baseline gap-x-2 text-xs">
                <span
                  className={cn(
                    "font-semibold",
                    s.status === "RUNNING" && "text-blue-700",
                    s.status === "FAILED" && "text-red-700",
                    s.status === "INCONCLUSIVE" && "text-amber-800",
                    s.status === "SUCCEEDED" && "text-emerald-700",
                    (s.status === "QUEUED" || s.status === "SKIPPED") && "text-slate-500",
                  )}
                >
                  {STATUS_TEXT[s.status]}
                </span>
                {elapsed !== null && s.status !== "QUEUED" && s.status !== "SKIPPED" ? (
                  <span className="font-mono-id tabular-nums text-slate-600">{formatDuration(elapsed)}</span>
                ) : null}
              </div>
              {s.message ? (
                <p className="mt-1 break-words text-xs text-slate-600" title={s.message}>
                  {s.message === "AI_UNAVAILABLE" ? "AI unavailable, deterministic fallback" : s.message}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
