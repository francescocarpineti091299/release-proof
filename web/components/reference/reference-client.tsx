"use client";

import { useMemo } from "react";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { ArtifactView } from "@/lib/types";
import { Empty } from "@/components/ui/card";
import { RunReport } from "@/components/run/run-report";

export function ReferenceClient() {
  const ref = useApi("reference", () => api.getReference());
  const artifacts = useMemo(() => {
    const seen = new Map<string, ArtifactView>();
    for (const e of ref.data?.result?.evidence ?? []) for (const a of e.artifacts) if (!seen.has(a.artifact_id)) seen.set(a.artifact_id, a);
    return Array.from(seen.values());
  }, [ref.data]);

  if (ref.loading) {
    return (
      <div className="flex items-center justify-center gap-3 py-24 text-slate-600">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> Loading the recorded reference…
      </div>
    );
  }
  if (ref.error || !ref.data) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16">
        <Empty>The recorded reference is not available: {ref.error?.message ?? "no data"}.</Empty>
      </div>
    );
  }
  return <RunReport run={ref.data.run} result={ref.data.result} traces={[]} artifacts={artifacts} recorded recordedNote={ref.data.notice} />;
}
