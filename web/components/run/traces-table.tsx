import Link from "next/link";
import { formatDuration, formatNumber, formatTimestamp } from "@/lib/format";
import type { AITraceView } from "@/lib/types";
import { Chip } from "@/components/ui/chip";
import { Empty } from "@/components/ui/card";

const STATUS_TONE = { OK: "green", SCHEMA_INVALID: "red", REJECTED_BY_GUARDRAIL: "red", AI_UNAVAILABLE: "amber", NOT_REQUESTED: "neutral" } as const;

export function TracesTable({ traces, showRun = false, empty }: { traces: AITraceView[]; showRun?: boolean; empty?: string }) {
  if (!traces.length) return <Empty>{empty ?? "No AI calls recorded."}</Empty>;
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-white">
      <table className="w-full min-w-[60rem] text-sm">
        <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-wide text-slate-600">
          <tr>
            <th className="px-4 py-2">Module</th>
            {showRun ? <th className="px-2 py-2">Run</th> : null}
            <th className="px-2 py-2">Model</th>
            <th className="px-2 py-2">Hardware</th>
            <th className="px-2 py-2">Endpoint</th>
            <th className="px-2 py-2 text-right">Latency</th>
            <th className="px-2 py-2 text-right">Tokens in / out</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-4 py-2">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {traces.map((t) => (
            <tr key={t.trace_id} className="align-top">
              <td className="px-4 py-2">
                <div className="font-semibold capitalize">{t.module}</div>
                <div className="font-mono-id text-[11px] text-slate-500" title={t.request_id ?? undefined}>
                  {t.trace_id}
                </div>
              </td>
              {showRun ? (
                <td className="px-2 py-2">
                  {t.run_id ? (
                    <Link className="font-mono-id text-[12px] text-link hover:underline" href={`/runs/${encodeURIComponent(t.run_id)}`}>
                      {t.run_id}
                    </Link>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
              ) : null}
              <td className="px-2 py-2 font-mono-id">{t.model || <span className="text-slate-400">not configured</span>}</td>
              <td className="px-2 py-2">{t.hardware_label}</td>
              <td className="px-2 py-2 font-mono-id text-[12px]">{t.endpoint_host || "—"}</td>
              <td className="px-2 py-2 text-right tabular-nums">{t.status === "OK" || t.latency_ms ? formatDuration(t.latency_ms) : "—"}</td>
              <td className="px-2 py-2 text-right tabular-nums">
                {formatNumber(t.prompt_tokens)} / {formatNumber(t.completion_tokens)}
              </td>
              <td className="px-2 py-2">
                <Chip tone={STATUS_TONE[t.status]} size="xs" title={t.error ?? undefined}>
                  {t.status}
                </Chip>
                {t.error ? <div className="mt-0.5 max-w-[14rem] text-xs text-red-700">{t.error}</div> : null}
              </td>
              <td className="px-4 py-2 text-xs text-slate-600">{formatTimestamp(t.started_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
