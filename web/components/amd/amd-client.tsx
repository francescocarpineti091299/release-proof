"use client";

import { Activity, AlertTriangle, CheckCircle2, Cpu, Gauge, Loader2, RefreshCw, Server, ShieldCheck, Sigma } from "lucide-react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { Card, Empty, KeyValue, Section } from "@/components/ui/card";
import { TracesTable } from "@/components/run/traces-table";

function Stat({ icon, label, value, sub }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 break-words text-2xl font-extrabold tracking-tight text-slate-950">{value}</div>
      {sub ? <div className="mt-0.5 text-sm text-slate-600">{sub}</div> : null}
    </Card>
  );
}

const MODULE_HELP: Record<string, string> = {
  planner: "Chooses which registered optional tests to run, and why.",
  explainer: "Explains the deterministic result with citations to evidence.",
  alternatives: "Proposes alternative plans from the allowed list.",
  assistant: "Answers questions about a run, grounded in its evidence.",
  smoke: "Connectivity check of the AMD endpoint.",
};

export function AmdClient() {
  const amd = useApi("amd", () => api.getAmd());
  const d = amd.data;
  const p = d?.view.provider;
  const s = d?.view.traces;
  const anyOk = (s?.ok ?? 0) > 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-widest text-red-700">AMD AI evidence</p>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight">Every AI step runs on AMD-hosted inference</h1>
          <p className="mt-2 max-w-3xl text-slate-700">
            Test planning, explanations, alternative plans and the assistant all call one AMD-hosted endpoint, and every call is traced. The model proposes and explains;{" "}
            <strong>it never issues the verdict</strong>. If the endpoint is down, ReleaseProof falls back to deterministic behaviour. It never switches to another provider.
          </p>
        </div>
        <button type="button" onClick={amd.reload} className="inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-950">
          <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
        </button>
      </div>

      {amd.loading && !d ? (
        <div className="flex items-center justify-center gap-3 py-24 text-slate-600">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> Loading AMD evidence…
        </div>
      ) : amd.error || !d || !p || !s ? (
        <div className="mt-8">
          <Empty>AMD evidence is not available: {amd.error?.message ?? "no data"}.</Empty>
        </div>
      ) : (
        <div className="mt-8 space-y-10">
          {p.configured ? (
            <div className="flex items-start gap-3 rounded-lg border-2 border-emerald-500 bg-emerald-50 p-4 text-emerald-950">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
              <p className="text-sm">
                <span className="font-bold">AMD endpoint configured.</span> Calls go to <span className="font-mono-id">{p.endpoint_host || "—"}</span>
                {p.allowed_hosts.length ? <> (allow-list: <span className="font-mono-id">{p.allowed_hosts.join(", ")}</span>)</> : null}.
              </p>
            </div>
          ) : (
            <div role="status" className="flex items-start gap-3 rounded-lg border-2 border-amber-400 bg-amber-50 p-4 text-amber-950">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
              <p className="text-sm">
                <span className="font-bold">AMD endpoint not configured</span>
                {p.unavailable_reason ? <>: {p.unavailable_reason}</> : null}. AI steps are recorded as <span className="font-mono-id">AI_UNAVAILABLE</span> and runs use the
                deterministic fallback. No other provider is used.
              </p>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Stat icon={<Server className="h-4 w-4" aria-hidden />} label="Provider" value={p.provider} sub={<span className="font-mono-id">{p.endpoint_host || "endpoint not set"}</span>} />
            <Stat icon={<Cpu className="h-4 w-4" aria-hidden />} label="Hardware" value={p.hardware} />
            <Stat
              icon={<Activity className="h-4 w-4" aria-hidden />}
              label="AI calls"
              value={formatNumber(s.count)}
              sub={`${formatNumber(s.ok)} OK · OK rate ${formatPercent(s.ok_rate)}`}
            />
            <Stat
              icon={<Gauge className="h-4 w-4" aria-hidden />}
              label="Latency (OK calls)"
              value={
                anyOk ? (
                  <span>
                    {formatDuration(s.latency_ms_p50)} <span className="text-base font-semibold text-slate-500">p50</span>
                  </span>
                ) : (
                  "—"
                )
              }
              sub={anyOk ? `p95 ${formatDuration(s.latency_ms_p95)}` : "No successful call yet"}
            />
            <Stat
              icon={<Sigma className="h-4 w-4" aria-hidden />}
              label="Tokens"
              value={formatNumber((s.prompt_tokens ?? 0) + (s.completion_tokens ?? 0))}
              sub={`${formatNumber(s.prompt_tokens)} prompt · ${formatNumber(s.completion_tokens)} completion`}
            />
            <Stat
              icon={<ShieldCheck className="h-4 w-4" aria-hidden />}
              label="Fallback provider"
              value={p.fallback_provider ?? "None"}
              sub={`Structured output: ${p.response_format ?? "—"}. Unregistered tests and plans are blocked.`}
            />
          </div>

          <Section title="Models per module">
            <div className="overflow-x-auto rounded-lg border border-border bg-white">
              <table className="w-full min-w-[48rem] text-sm">
                <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-wide text-slate-600">
                  <tr>
                    <th className="px-4 py-2">Module</th>
                    <th className="px-2 py-2">Model</th>
                    <th className="px-2 py-2">Prompt template</th>
                    <th className="px-2 py-2 text-right">Calls</th>
                    <th className="px-2 py-2 text-right">OK rate</th>
                    <th className="px-2 py-2 text-right">p50</th>
                    <th className="px-4 py-2 text-right">p95</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {d.per_module.map((m) => (
                    <tr key={m.module}>
                      <td className="px-4 py-2">
                        <div className="font-semibold capitalize">{m.module}</div>
                        <div className="text-xs text-slate-500">{MODULE_HELP[m.module] ?? ""}</div>
                      </td>
                      <td className="px-2 py-2 font-mono-id">{m.model || <span className="text-slate-400">not configured</span>}</td>
                      <td className="px-2 py-2 font-mono-id text-slate-600">{p.prompt_templates?.[m.module] ?? "—"}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{formatNumber(m.calls)}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{formatPercent(m.ok_rate)}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{formatDuration(m.latency_p50_ms)}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{formatDuration(m.latency_p95_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section title="Recent traces" description="Collected from the most recent runs and linked to the run that triggered them. Request ids come from the AMD endpoint.">
            <TracesTable traces={d.recent_traces.slice(0, 50)} showRun empty="No AI calls recorded yet." />
          </Section>

          <Section title="Endpoint policy">
            <Card className="p-4">
              <KeyValue
                rows={[
                  ["Configured", p.configured ? "yes" : "no"],
                  ["Endpoint host", p.endpoint_host || "—"],
                  ["Allowed hosts", p.allowed_hosts.join(", ") || "—"],
                  ["Response format", p.response_format ?? "—"],
                  ["Fallback provider", p.fallback_provider ?? "none (deterministic fallback only)"],
                ]}
              />
            </Card>
          </Section>
        </div>
      )}
    </div>
  );
}
