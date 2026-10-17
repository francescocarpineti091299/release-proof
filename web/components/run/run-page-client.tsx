"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { buttonClass } from "@/components/ui/button";
import { RunReport } from "./run-report";
import { useLiveRun } from "./use-live-run";

export function RunPageClient({ runId }: { runId: string }) {
  const live = useLiveRun(runId);

  if (!live.run) {
    if (live.error) {
      const notFound = "status" in live.error && (live.error as { status?: number }).status === 404;
      return (
        <div className="mx-auto max-w-2xl px-6 py-20 text-center">
          <h1 className="text-2xl font-bold">{notFound ? "Run not found" : "Could not load this run"}</h1>
          <p className="mt-2 font-mono-id text-slate-600">{runId}</p>
          <p className="mt-2 text-slate-600">{live.error.message}</p>
          <div className="mt-6 flex justify-center gap-2">
            <button type="button" className={buttonClass("secondary")} onClick={() => void live.refresh()}>
              Retry
            </button>
            <Link href="/" className={buttonClass("primary")}>
              New assessment
            </Link>
          </div>
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center gap-3 px-6 py-24 text-slate-600">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> Loading run <span className="font-mono-id">{runId}</span>…
      </div>
    );
  }

  return (
    <RunReport
      run={live.run}
      result={live.result}
      traces={live.traces}
      artifacts={live.artifacts}
      logs={live.logs}
      conn={live.conn}
      observations={live.observations}
      streamErrors={live.streamErrors}
      plan={live.plan}
    />
  );
}
