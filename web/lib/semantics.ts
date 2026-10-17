import type {
  EvaluationRow,
  EvidenceGap,
  ResultView,
  RunMode,
  RunStatus,
  Stage,
  StageStatus,
  TestOutcome,
  TestResultView,
} from "@/lib/types";
import { uniq } from "@/lib/utils";

export type Tone = "green" | "amber" | "slate" | "red" | "blue" | "neutral";

export interface VerdictMeta {
  label: string;
  short: string;
  tone: Tone;
  /** Plain-language answer to "Can this migration proceed as planned?" */
  answer: string;
  explain: string;
}

export const VERDICT_META: Record<string, VerdictMeta> = {
  COMPATIBLE: {
    label: "Compatible",
    short: "Compatible",
    tone: "green",
    answer: "Yes, within the verified scope.",
    explain: "Every critical requirement was satisfied by evidence collected for this plan.",
  },
  CONDITIONAL: {
    label: "Conditional",
    short: "Conditional",
    tone: "amber",
    answer: "Only if the open conditions below are met.",
    explain: "No blocker was found, but the plan depends on conditions that must hold in the field.",
  },
  INDETERMINATE: {
    label: "Indeterminate",
    short: "Not proven",
    tone: "slate",
    answer: "Not proven yet. Critical facts are still unknown.",
    explain: "Indeterminate is not a pass: some critical facts could not be observed, so compatibility is not proven.",
  },
  INCOMPATIBLE: {
    label: "Incompatible",
    short: "Engineering blocker",
    tone: "red",
    answer: "No. An engineering blocker was found.",
    explain: "At least one critical requirement was violated by observed evidence. This blocks the plan as designed. It is not a claim that the firmware is insecure.",
  },
};

export function verdictMeta(v: string | null | undefined): VerdictMeta {
  if (v && VERDICT_META[v]) return VERDICT_META[v];
  return {
    label: v ?? "No verdict",
    short: v ?? "No verdict",
    tone: "neutral",
    answer: "No verdict was issued.",
    explain: "The deterministic engine has not produced a verdict for this run.",
  };
}

export const SCOPE_HELP = {
  migration:
    "Overall Migration: the combined decision for the whole plan. Candidate and Transition must both hold.",
  candidate:
    "Candidate: the new firmware state on its own. Does the post-quantum bootloader and image build, boot, verify and fit?",
  transition:
    "Transition: the path from what is deployed in the field today to the candidate. Can existing devices actually get there?",
};

export const STAGE_LABEL: Record<Stage, string> = {
  PREPARING: "Preparing configuration",
  AI_PLAN: "AI verification plan",
  DISCOVERY: "Discovering firmware facts",
  BUILD_SIGN: "Building & signing",
  EMULATION_TESTS: "Running emulator tests",
  EVALUATION: "Evaluating evidence",
  NEXT_STEPS: "Drafting next steps",
};

export const STAGE_HELP: Record<Stage, string> = {
  PREPARING: "Pinned profile, toolchain and isolated workspace are prepared.",
  AI_PLAN: "The AMD-hosted model selects optional registered tests. Required tests always run.",
  DISCOVERY: "Source pins, partition layout and capabilities are read from the pinned sources.",
  BUILD_SIGN: "Bootloader and images are built and signed with the pinned tools.",
  EMULATION_TESTS: "Images are booted and updated in Renode; UART output is parsed.",
  EVALUATION: "The deterministic V1.2 engine evaluates the evidence and issues the verdict.",
  NEXT_STEPS: "AI explains the result and proposes alternative plans (never verdicts).",
};

export const STAGE_STATUS_TONE: Record<StageStatus, Tone> = {
  QUEUED: "neutral",
  RUNNING: "blue",
  SUCCEEDED: "green",
  FAILED: "red",
  INCONCLUSIVE: "amber",
  SKIPPED: "neutral",
};

export const RUN_STATUS_TONE: Record<RunStatus, Tone> = {
  QUEUED: "neutral",
  RUNNING: "blue",
  SUCCEEDED: "green",
  FAILED: "red",
  CANCELLED: "neutral",
};

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  QUEUED: "Queued",
  RUNNING: "Running",
  SUCCEEDED: "Pipeline completed",
  FAILED: "Pipeline failed",
  CANCELLED: "Cancelled",
};

export const MODE_LABEL: Record<RunMode, string> = {
  LIVE: "LIVE",
  REEVALUATION: "RE-EVALUATION",
  REFERENCE: "RECORDED",
};

export const OUTCOME_TONE: Record<TestOutcome, Tone> = {
  PASS: "green",
  FAIL: "red",
  INCONCLUSIVE: "amber",
  NOT_EXECUTED: "neutral",
  ERROR: "red",
};

export const OUTCOME_LABEL: Record<TestOutcome, string> = {
  PASS: "Pass",
  FAIL: "Fail",
  INCONCLUSIVE: "Inconclusive",
  NOT_EXECUTED: "Not executed",
  ERROR: "Could not run",
};

export const PLANNED_BY_LABEL: Record<TestResultView["planned_by"], string> = {
  POLICY_REQUIRED: "Required",
  AI_PLANNER: "AI planner",
  PROFILE_OPTIONAL: "Profile optional",
};

export const PLANNED_BY_HELP: Record<TestResultView["planned_by"], string> = {
  POLICY_REQUIRED: "Required by the profile policy. Always runs, whatever the AI says.",
  AI_PLANNER: "Optional registered test selected by the AMD-hosted planner.",
  PROFILE_OPTIONAL: "Optional registered test run by default because the AI planner was unavailable.",
};

export const ORIGIN_META: Record<string, { label: string; tone: Tone; help: string }> = {
  MEASURED_TOOL: { label: "Measured (tool)", tone: "green", help: "Measured by a pinned build, sign or inspection tool in this run." },
  OBSERVED_EMULATION: { label: "Observed (emulation)", tone: "blue", help: "Observed while running the firmware in Renode." },
  DECLARED: { label: "Declared", tone: "amber", help: "Declared by the profile or operator; not measured." },
  AI_PROPOSAL: { label: "AI proposal", tone: "neutral", help: "Proposed by AI. Never counts as measured evidence." },
  NOT_OBSERVED: { label: "Not observed", tone: "slate", help: "The fact was not observed in this run; it stays UNKNOWN and is never counted as a pass." },
  RECORDED_WP0_FREEZE: { label: "Recorded (WP0 freeze)", tone: "slate", help: "Measured on 2026-10-01 during the WP0 freeze and re-evaluated by the current engine. Not executed live." },
};

export function originMeta(origin: string): { label: string; tone: Tone; help: string } {
  return ORIGIN_META[origin] ?? { label: origin.replace(/_/g, " ").toLowerCase(), tone: "neutral", help: "" };
}

export const STATE_TONE: Record<string, Tone> = {
  SATISFIED: "green",
  VIOLATED: "red",
  UNKNOWN: "slate",
  OPEN_CONDITION: "amber",
};

export const STATE_LABEL: Record<string, string> = {
  SATISFIED: "Satisfied",
  VIOLATED: "Violated",
  UNKNOWN: "Unknown",
  OPEN_CONDITION: "Open condition",
};

export const FAILURE_HELP: Record<string, string> = {
  ENVIRONMENT_SETUP: "The runner environment could not be prepared.",
  BUILD_FAILED: "A pinned build step failed. This is a tool failure, not a firmware result.",
  TOOL_FAILURE: "A pinned tool crashed or returned an unexpected error.",
  TIMEOUT: "A step exceeded its time budget and was stopped.",
  INCONCLUSIVE: "The run completed but observations were not decisive.",
  INTERNAL: "Internal error in the orchestrator.",
  AI_UNAVAILABLE: "The AMD-hosted model could not be reached.",
};

/** Contract V1.2 invariants (ruleset RULESET-V1.2). Generic meaning, not per-assessment text. */
export const INVARIANT_MEANING: Record<string, string> = {
  "INV-I1": "A bootable, correctly signed image exists at every state of the transition",
  "INV-I2": "Recovery from a failed step uses an acceptable recovery mode",
  "INV-I3": "No critical authorization path stays classical-only at the target",
  "INV-I4": "The non-atomic update window is handled (interrupted update recovers)",
};

export function rowId(row: EvaluationRow): string {
  return row.requirement_id ?? row.invariant_id ?? "?";
}

export function criterionIndex(result: ResultView | null): Record<string, string> {
  const out: Record<string, string> = { ...INVARIANT_MEANING };
  for (const req of result?.assessment.profile?.requirements ?? []) {
    if (req.id && req.criterion) out[req.id] = req.criterion;
  }
  return out;
}

export function allRows(result: ResultView | null): EvaluationRow[] {
  if (!result) return [];
  return [
    ...(result.result.requirement_evaluation_results ?? []),
    ...(result.result.invariant_evaluation_results ?? []),
  ];
}

export interface DerivedCause {
  id: string;
  state: string;
  text: string;
  citations: string[];
  phases: string[];
}

const STATE_RANK: Record<string, number> = { VIOLATED: 0, UNKNOWN: 1, OPEN_CONDITION: 2 };

/** Critical unmet checks, grouped by requirement or invariant ID. */
export function deterministicCauses(result: ResultView | null, limit = 3): DerivedCause[] {
  const criteria = criterionIndex(result);
  const groups = new Map<string, EvaluationRow[]>();
  for (const row of allRows(result)) {
    if (!row.critical_for_verdict || !(row.state in STATE_RANK)) continue;
    const id = rowId(row);
    groups.set(id, [...(groups.get(id) ?? []), row]);
  }
  const causes = Array.from(groups.entries()).map(([id, rows]) => {
    const worst = rows.reduce((a, b) => (STATE_RANK[b.state] < STATE_RANK[a.state] ? b : a));
    const phases = uniq(rows.map((r) => r.phase));
    const criterion = criteria[id]?.trim().replace(/[.;:]+$/, "");
    const stateText = STATE_LABEL[worst.state]?.toLowerCase() ?? worst.state;
    return {
      id,
      state: worst.state,
      phases,
      text: criterion ? `${criterion}.` : `${id} is ${stateText}.`,
      citations: uniq([id, ...rows.flatMap((r) => [...r.evidence_refs, ...r.gap_refs])]),
    };
  });
  causes.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state]);
  return causes.slice(0, limit);
}

export interface UnknownItem {
  id: string;
  state: string;
  criterion: string | null;
  phases: string[];
  critical: boolean;
  gapRefs: string[];
}

export function unknownRows(result: ResultView | null): UnknownItem[] {
  const criteria = criterionIndex(result);
  const groups = new Map<string, EvaluationRow[]>();
  for (const row of allRows(result)) {
    if (row.state !== "UNKNOWN" && row.state !== "OPEN_CONDITION") continue;
    const id = rowId(row);
    groups.set(id, [...(groups.get(id) ?? []), row]);
  }
  return Array.from(groups.entries()).map(([id, rows]) => ({
    id,
    state: rows[0].state,
    criterion: criteria[id] ?? null,
    phases: uniq(rows.map((r) => r.phase)),
    critical: rows.some((r) => r.critical_for_verdict),
    gapRefs: uniq(rows.flatMap((r) => r.gap_refs)),
  }));
}

export function evidenceGaps(result: ResultView | null): EvidenceGap[] {
  return result?.assessment.evidence_gaps ?? [];
}

/** Every ID a citation may legitimately point at in this run. */
export function citationIndex(result: ResultView | null): Set<string> {
  const ids = new Set<string>();
  for (const e of result?.evidence ?? []) ids.add(e.id);
  for (const row of allRows(result)) ids.add(rowId(row));
  for (const g of evidenceGaps(result)) ids.add(g.gap_id);
  return ids;
}

export function isTerminal(status: RunStatus | undefined): boolean {
  return status === "SUCCEEDED" || status === "FAILED" || status === "CANCELLED";
}
