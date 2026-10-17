"use client";

import Link from "next/link";
import { ArrowRight, History, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { useApi, useNow } from "@/lib/hooks";
import { formatRelative } from "@/lib/format";
import { isTerminal } from "@/lib/semantics";
import type { ConfigurationView, RunView } from "@/lib/types";
import { Card, Empty } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { ModeChip, RunStatusChip, VerdictChip } from "@/components/ui/status";
import { useEffect } from "react";

export function describeRun(run: RunView, profiles: ConfigurationView[] | undefined) {
  const p = profiles?.find((x) => x.id === run.configuration_id);
  const c = p?.changes.find((x) => x.change_id === run.change_id);
  const plan =
    c && run.plan_id === c.default_plan_id ? c.default_plan_title : c?.alternatives.find((a) => a.plan_id === run.plan_id)?.title;
  return { config: p?.title ?? run.configuration_id, change: c?.title ?? run.change_id, plan: plan ?? run.plan_id, profile: p, scenario: c };
}

export function RecentRuns() {
  const runs = useApi("runs", () => api.listRuns(12));
  const profiles = useApi("configurations", () => api.listConfigurations());
  const anyActive = (runs.data ?? []).some((r) => !isTerminal(r.status));
  const now = useNow(15000);
  const { reload } = runs;

  useEffect(() => {
    if (!anyActive) return;
    const id = setInterval(reload, 4000);
    return () => clearInterval(id);
  }, [anyActive, reload]);

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="flex items-center gap-2 text-base font-bold">
          <History className="h-5 w-5" aria-hidden /> Recent runs
        </h2>
        <button type="button" onClick={reload} className="inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-950">
          <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
        </button>
      </div>
      {runs.loading && !runs.data ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded bg-slate-100" />
          ))}
        </div>
      ) : runs.error ? (
        <div className="p-4">
          <Empty>Could not load runs: {runs.error.message}</Empty>
        </div>
      ) : !runs.data?.length ? (
        <div className="p-4">
          <Empty>No runs yet. Start one above.</Empty>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {runs.data.map((run) => {
            const d = describeRun(run, profiles.data);
            return (
              <li key={run.run_id}>
                <Link href={`/runs/${encodeURIComponent(run.run_id)}`} className="flex flex-col gap-2 px-4 py-3 hover:bg-slate-50 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <ModeChip mode={run.mode} />
                      <span className="font-semibold text-slate-950">{d.config}</span>
                      <span className="font-mono-id text-slate-500">{run.run_id}</span>
                    </div>
                    <div className="mt-0.5 truncate text-sm text-slate-600">
                      {d.change} · plan: {d.plan}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    {run.verdict?.migration ? <VerdictChip verdict={run.verdict.migration} /> : run.status === "FAILED" ? <Chip tone="neutral">No verdict</Chip> : null}
                    <RunStatusChip status={run.status} />
                    <span className="w-24 text-right text-xs text-slate-500">{now ? formatRelative(run.created_at, now) : ""}</span>
                    <ArrowRight className="hidden h-4 w-4 text-slate-400 sm:block" aria-hidden />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function ReferenceCard() {
  return (
    <Link href="/reference" className="block rounded-lg border-2 border-dashed border-slate-400 bg-white p-5 shadow-sm transition-colors hover:border-slate-700">
      <div className="flex items-center gap-2">
        <Chip tone="slate" solid size="xs" className="tracking-wider">
          RECORDED
        </Chip>
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Not a live run</span>
      </div>
      <h3 className="mt-2 text-lg font-bold">Reference run (recorded 2026-10-01)</h3>
      <p className="mt-1 text-sm text-slate-600">
        The recorded WP0 freeze from the wolfBoot proof of concept, re-evaluated by the current engine. Use it as a baseline to compare against live runs.
      </p>
      <span className="mt-3 inline-flex items-center gap-1 text-sm font-semibold">
        Open the recorded reference <ArrowRight className="h-4 w-4" aria-hidden />
      </span>
    </Link>
  );
}
