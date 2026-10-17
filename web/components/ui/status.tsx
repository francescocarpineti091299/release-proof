import { AlertTriangle, CheckCircle2, CircleDashed, HelpCircle, Loader2, MinusCircle, XCircle, OctagonX } from "lucide-react";
import type { RunMode, RunStatus, StageStatus, TestOutcome } from "@/lib/types";
import {
  MODE_LABEL,
  OUTCOME_LABEL,
  OUTCOME_TONE,
  RUN_STATUS_LABEL,
  RUN_STATUS_TONE,
  STAGE_STATUS_TONE,
  STATE_LABEL,
  STATE_TONE,
  verdictMeta,
} from "@/lib/semantics";
import { Chip } from "./chip";

export function VerdictIcon({ verdict, className }: { verdict: string | null | undefined; className?: string }) {
  switch (verdict) {
    case "COMPATIBLE":
      return <CheckCircle2 className={className} aria-hidden />;
    case "CONDITIONAL":
      return <AlertTriangle className={className} aria-hidden />;
    case "INDETERMINATE":
      return <HelpCircle className={className} aria-hidden />;
    case "INCOMPATIBLE":
      return <OctagonX className={className} aria-hidden />;
    default:
      return <MinusCircle className={className} aria-hidden />;
  }
}

export function VerdictChip({ verdict, size = "sm", withWord = false }: { verdict: string | null | undefined; size?: "xs" | "sm" | "md"; withWord?: boolean }) {
  const meta = verdictMeta(verdict);
  return (
    <Chip tone={meta.tone} size={size} title={meta.explain}>
      <VerdictIcon verdict={verdict} className="h-3.5 w-3.5" />
      {withWord ? `${meta.label} · ${meta.short}` : meta.label}
    </Chip>
  );
}

export function StageStatusIcon({ status, className = "h-5 w-5" }: { status: StageStatus; className?: string }) {
  switch (status) {
    case "SUCCEEDED":
      return <CheckCircle2 className={`${className} text-emerald-700`} aria-hidden />;
    case "FAILED":
      return <XCircle className={`${className} text-red-700`} aria-hidden />;
    case "INCONCLUSIVE":
      return <AlertTriangle className={`${className} text-amber-600`} aria-hidden />;
    case "RUNNING":
      return <Loader2 className={`${className} animate-spin text-blue-700`} aria-hidden />;
    case "SKIPPED":
      return <MinusCircle className={`${className} text-slate-400`} aria-hidden />;
    default:
      return <CircleDashed className={`${className} text-slate-400`} aria-hidden />;
  }
}

export function StageStatusChip({ status }: { status: StageStatus }) {
  return (
    <Chip tone={STAGE_STATUS_TONE[status]} size="xs">
      {status}
    </Chip>
  );
}

export function RunStatusChip({ status }: { status: RunStatus }) {
  return (
    <Chip tone={RUN_STATUS_TONE[status]} title={status === "SUCCEEDED" ? "The pipeline finished. This says nothing about the migration verdict." : undefined}>
      {status === "RUNNING" ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : null}
      {RUN_STATUS_LABEL[status]}
    </Chip>
  );
}

export function ModeChip({ mode }: { mode: RunMode }) {
  const tone = mode === "LIVE" ? "blue" : mode === "REEVALUATION" ? "amber" : "slate";
  return (
    <Chip tone={tone} solid size="xs" className="tracking-wider">
      {mode === "LIVE" ? <span className="h-1.5 w-1.5 rounded-full bg-white" aria-hidden /> : null}
      {MODE_LABEL[mode]}
    </Chip>
  );
}

export function OutcomeChip({ outcome, pending }: { outcome: TestOutcome; pending?: boolean }) {
  if (pending && outcome === "NOT_EXECUTED") {
    return (
      <Chip tone="neutral" size="xs" className="text-slate-500">
        Pending
      </Chip>
    );
  }
  return (
    <Chip tone={OUTCOME_TONE[outcome]} size="xs">
      {OUTCOME_LABEL[outcome]}
    </Chip>
  );
}

export function StateChip({ state }: { state: string }) {
  return (
    <Chip tone={STATE_TONE[state] ?? "neutral"} size="xs">
      {STATE_LABEL[state] ?? state}
    </Chip>
  );
}
