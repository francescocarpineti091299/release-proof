"use client";

import { useMemo, useState } from "react";
import { criterionIndex, rowId } from "@/lib/semantics";
import type { EvaluationRow, ResultView } from "@/lib/types";
import { citationAnchor } from "@/lib/utils";
import { Empty } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { Citations } from "@/components/ui/citation";
import { StateChip } from "@/components/ui/status";

export function RequirementsTable({ result, known }: { result: ResultView | null; known: Set<string> }) {
  const [criticalOnly, setCriticalOnly] = useState(false);
  const criteria = useMemo(() => criterionIndex(result), [result]);

  const groups = useMemo(() => {
    const out: { kind: "Requirement" | "Invariant"; id: string; rows: EvaluationRow[] }[] = [];
    const push = (kind: "Requirement" | "Invariant", rows: EvaluationRow[]) => {
      const map = new Map<string, EvaluationRow[]>();
      for (const r of rows) {
        if (criticalOnly && !r.critical_for_verdict) continue;
        const id = rowId(r);
        map.set(id, [...(map.get(id) ?? []), r]);
      }
      for (const [id, list] of map) out.push({ kind, id, rows: list });
    };
    push("Requirement", result?.result.requirement_evaluation_results ?? []);
    push("Invariant", result?.result.invariant_evaluation_results ?? []);
    return out;
  }, [result, criticalOnly]);

  if (!result) return <Empty>Requirement and invariant results appear after evaluation.</Empty>;

  return (
    <div className="rounded-lg border border-border bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5 text-sm">
        <span className="text-slate-600">
          {groups.length} items from <span className="font-mono-id">SemanticAssessmentResult</span> (contract V1.2)
        </span>
        <label className="flex items-center gap-1.5 text-slate-700">
          <input type="checkbox" checked={criticalOnly} onChange={(e) => setCriticalOnly(e.target.checked)} /> Critical only
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[56rem] text-sm">
          <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-4 py-2">Requirement / invariant</th>
              <th className="px-2 py-2">Phase · subject</th>
              <th className="px-2 py-2">State</th>
              <th className="px-2 py-2">Evidence</th>
              <th className="px-4 py-2">Gaps</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) =>
              g.rows.map((r, i) => (
                <tr key={`${g.id}-${i}`} id={i === 0 ? citationAnchor(g.id) : undefined} className={i === 0 ? "border-t border-border align-top" : "align-top"}>
                  {i === 0 ? (
                    <td className="px-4 py-2" rowSpan={g.rows.length}>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono-id font-bold text-slate-950">{g.id}</span>
                        <span className="text-[11px] font-semibold uppercase text-slate-500">{g.kind}</span>
                        {g.rows.some((x) => x.critical_for_verdict) ? (
                          <Chip tone="neutral" size="xs" title="Critical for the verdict">
                            critical
                          </Chip>
                        ) : null}
                      </div>
                      {criteria[g.id] ? <p className="mt-0.5 max-w-sm text-slate-700">{criteria[g.id]}</p> : null}
                    </td>
                  ) : null}
                  <td className="px-2 py-1.5 text-xs">
                    <span className="font-semibold">{r.phase}</span> · <span className="font-mono-id">{r.subject_ref}</span>
                  </td>
                  <td className="px-2 py-1.5">
                    <StateChip state={r.state} />
                  </td>
                  <td className="px-2 py-1.5">{r.evidence_refs.length ? <Citations ids={r.evidence_refs} known={known} /> : <span className="text-slate-400">—</span>}</td>
                  <td className="px-4 py-1.5">{r.gap_refs.length ? <Citations ids={r.gap_refs} known={known} /> : <span className="text-slate-400">—</span>}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
