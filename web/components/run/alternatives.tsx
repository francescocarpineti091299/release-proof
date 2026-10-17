"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Ban, FlaskConical, Loader2, Lock, RotateCcw, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { AlternativePlan, ChangeProposal, ChangeView, RunView } from "@/lib/types";
import { randomKey } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, Empty } from "@/components/ui/card";
import { Badge, Chip } from "@/components/ui/chip";
import { Citations } from "@/components/ui/citation";

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</div>
      <ul className="mt-0.5 list-disc pl-5 text-sm text-slate-700">
        {items.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

function EvaluateButton({ run, plan, allowed }: { run: RunView; plan: string; allowed: AlternativePlan | undefined }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [key] = useState(() => randomKey());

  if (!allowed) {
    return (
      <p className="flex items-center gap-1.5 text-sm font-semibold text-red-800">
        <Ban className="h-4 w-4" aria-hidden /> Blocked: not an allowed plan for this configuration
      </p>
    );
  }
  if (allowed.status === "REQUIRES_EXTERNAL_VALIDATION") {
    return (
      <div className="space-y-1">
        <Button variant="secondary" disabled size="sm">
          <Lock className="h-4 w-4" aria-hidden /> Requires external validation
        </Button>
        <p className="text-xs text-slate-600">{allowed.description}</p>
      </div>
    );
  }
  const go = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      const created = await api.evaluateAlternative(run.run_id, plan, key);
      router.push(`/runs/${encodeURIComponent(created.run_id)}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <div className="space-y-1">
      <Button size="sm" onClick={go} disabled={busy}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : allowed.requires_rerun_tests ? <FlaskConical className="h-4 w-4" aria-hidden /> : <RotateCcw className="h-4 w-4" aria-hidden />}
        Evaluate this plan
      </Button>
      <p className="text-xs text-slate-600">
        {allowed.requires_rerun_tests ? "Starts a new LIVE run: this plan needs tests that were not executed here." : "Re-evaluates this run's evidence under the new plan. No new emulation."}
      </p>
      {err ? (
        <p className="text-xs font-semibold text-red-700" role="alert">
          {err}
        </p>
      ) : null}
    </div>
  );
}

function ProposalCard({ run, p, allowed, known }: { run: RunView; p: ChangeProposal; allowed: AlternativePlan | undefined; known: Set<string> }) {
  return (
    <Card className="flex flex-col p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="border-violet-400 bg-violet-50 text-violet-800">Proposal</Badge>
        <span className="font-mono-id text-xs text-slate-500">{p.plan_id}</span>
      </div>
      <h4 className="mt-1.5 text-base font-bold text-slate-950">{p.title}</h4>
      <p className="mt-1 text-sm text-slate-700">{p.rationale}</p>
      {p.addresses.length ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="font-bold uppercase tracking-wide text-slate-500">Addresses</span>
          <Citations ids={p.addresses} known={known} />
        </div>
      ) : null}
      <div className="mt-3 grid gap-2 sm:grid-cols-3 sm:gap-4">
        <List title="Preconditions" items={p.preconditions} />
        <List title="Trade-offs" items={p.tradeoffs} />
        <List title="Evidence still needed" items={p.evidence_still_needed} />
      </div>
      <div className="mt-auto pt-4">
        <EvaluateButton run={run} plan={p.plan_id} allowed={allowed} />
      </div>
    </Card>
  );
}

export function Alternatives({ run, scenario, known }: { run: RunView; scenario: ChangeView | undefined; known: Set<string> }) {
  const view = run.ai_alternatives;
  const allowed = new Map((scenario?.alternatives ?? []).map((a) => [a.plan_id, a]));
  const ok = view?.status === "OK" && view.alternatives;

  if (run.verdict?.migration === "COMPATIBLE") {
    return <Empty>The migration is compatible as planned, so no alternatives are needed.</Empty>;
  }
  if (run.mode === "REEVALUATION" && !ok) {
    return (
      <Empty>
        Alternatives are drafted for the original LIVE run only. Open the parent run
        {run.parent_run_id ? ` (${run.parent_run_id})` : ""} to explore other plans.
      </Empty>
    );
  }

  return (
    <div className="space-y-3">
      <p className="flex items-start gap-2 rounded-md border border-violet-200 bg-violet-50/60 px-3 py-2 text-sm text-violet-950">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        These are proposals. They do not change the current result. Evaluating one creates a new, independent run; history is never modified.
      </p>
      {ok ? (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            {view.alternatives!.proposals.map((p) => (
              <ProposalCard key={p.plan_id} run={run} p={p} allowed={allowed.get(p.plan_id)} known={known} />
            ))}
          </div>
          {view.alternatives!.not_addressable.length ? (
            <Card className="p-4">
              <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Not addressable by any allowed plan</div>
              <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
                {view.alternatives!.not_addressable.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </Card>
          ) : null}
        </>
      ) : scenario?.alternatives.length ? (
        <>
          <p className="text-sm text-slate-600">
            {view && view.status !== "NOT_REQUESTED" ? (
              <>
                <Chip tone="amber" size="xs">
                  {view.status}
                </Chip>{" "}
                AI proposals are unavailable{view.message ? ` (${view.message})` : ""}. These are the alternative plans registered for this configuration; each can still be evaluated deterministically:
              </>
            ) : run.status === "SUCCEEDED" ? (
              "Alternative plans registered in the profile:"
            ) : (
              "Alternatives are drafted after the evaluation. Registered plans:"
            )}
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {scenario.alternatives.map((a) => (
              <Card key={a.plan_id} className="flex flex-col p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>Registered plan</Badge>
                  <span className="font-mono-id text-xs text-slate-500">{a.plan_id}</span>
                </div>
                <h4 className="mt-1.5 text-base font-bold">{a.title}</h4>
                <p className="mt-1 text-sm text-slate-700">{a.description}</p>
                <div className="mt-auto pt-4">{run.status === "SUCCEEDED" ? <EvaluateButton run={run} plan={a.plan_id} allowed={a} /> : null}</div>
              </Card>
            ))}
          </div>
        </>
      ) : (
        <Empty>No alternative plans are registered for this change.</Empty>
      )}
    </div>
  );
}
