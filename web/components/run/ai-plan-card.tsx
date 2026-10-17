import { Ban, CheckCircle2, Lightbulb, MinusCircle, Sparkles } from "lucide-react";
import type { AIPlanView, TestCatalog, TestResultView } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";

const AI_STATUS_TONE = { OK: "green", SCHEMA_INVALID: "red", REJECTED_BY_GUARDRAIL: "red", AI_UNAVAILABLE: "amber", NOT_REQUESTED: "neutral" } as const;

export function AIPlanCard({
  plan,
  tests,
  catalog,
  pending,
  waiting = false,
  skippedStage,
}: {
  plan: AIPlanView | null | undefined;
  tests: TestResultView[];
  catalog: TestCatalog | null;
  pending: boolean;
  waiting?: boolean;
  skippedStage: boolean;
}) {
  const title = (id: string) => catalog?.templates.find((t) => t.template_id === id)?.title ?? tests.find((t) => t.template_id === id)?.title ?? id;
  const executed = new Set(tests.map((t) => t.template_id));

  return (
    <Card className="border-violet-200">
      <div className="flex items-center justify-between gap-2 border-b border-violet-100 bg-violet-50/60 px-4 py-3">
        <h3 className="flex items-center gap-2 font-bold text-violet-950">
          <Sparkles className="h-4 w-4" aria-hidden /> AI verification plan
        </h3>
        {plan ? (
          <Chip tone={AI_STATUS_TONE[plan.status]} size="xs">
            {plan.status}
          </Chip>
        ) : null}
      </div>
      <div className="space-y-4 p-4 text-sm">
        {!plan ? (
          <p className="text-slate-600">
            {skippedStage
              ? "No AI planning for this run: it reuses evidence that was already collected."
              : pending
                ? "The AMD-hosted planner is choosing which optional registered tests to run…"
                : waiting
                  ? "Planning starts when the run leaves the queue."
                  : "No AI plan was recorded for this run."}
          </p>
        ) : plan.status !== "OK" || !plan.proposal ? (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-950">
            <p className="font-semibold">AI planner unavailable: deterministic fallback</p>
            <p className="mt-1">
              {plan.message ? `${plan.message.replace(/[.\s]+$/, "")}. ` : "The model did not return a valid plan. "}All required tests and every optional registered test were run instead (marked “Profile optional”).
            </p>
          </div>
        ) : (
          <>
            <p className="text-slate-800">{plan.proposal.summary}</p>
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">Selected ({plan.proposal.selected.length})</h4>
              <ol className="mt-1.5 space-y-2">
                {[...plan.proposal.selected]
                  .sort((a, b) => a.priority - b.priority)
                  .map((s) => (
                    <li key={s.template_id} className="flex gap-2">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-700 text-[11px] font-bold text-white">{s.priority}</span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5 font-semibold text-slate-900">
                          {title(s.template_id)}
                          {executed.has(s.template_id) ? (
                            <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-emerald-700">
                              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> in plan
                            </span>
                          ) : null}
                        </div>
                        <p className="text-slate-600">{s.rationale}</p>
                      </div>
                    </li>
                  ))}
              </ol>
            </div>
            {plan.proposal.skipped.length ? (
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">Skipped ({plan.proposal.skipped.length})</h4>
                <ul className="mt-1.5 space-y-1.5">
                  {plan.proposal.skipped.map((s) => (
                    <li key={s.template_id} className="flex gap-2">
                      <MinusCircle className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden />
                      <span>
                        <span className="font-semibold text-slate-800">{title(s.template_id)}</span>
                        <span className="text-slate-600">: {s.reason}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {plan.proposal.suggested_new_tests.length ? (
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">Ideas for new tests (not executed)</h4>
                <ul className="mt-1.5 space-y-1.5">
                  {plan.proposal.suggested_new_tests.map((s) => (
                    <li key={s.title} className="flex gap-2">
                      <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden />
                      <span>
                        <span className="font-semibold text-slate-800">{s.title}</span>
                        <span className="text-slate-600">: {s.purpose}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
        {plan?.blocked_templates.length ? (
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wide text-red-700">Guardrail</h4>
            <ul className="mt-1.5 space-y-1">
              {plan.blocked_templates.map((b) => (
                <li key={b} className="flex items-center gap-2 text-red-900">
                  <Ban className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="font-mono-id">{b}</span>
                  <span className="text-xs">blocked: not a registered test</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="border-t border-border pt-3 text-xs text-slate-500">The AI can only choose among registered tests. Required tests always run, and the verdict is never generated by the model.</p>
      </div>
    </Card>
  );
}
