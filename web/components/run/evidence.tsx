"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Download, FileText, Search } from "lucide-react";
import { formatBytes, formatValue, shortHash } from "@/lib/format";
import { originMeta } from "@/lib/semantics";
import type { ArtifactView, EvidenceView } from "@/lib/types";
import { citationAnchor, cn } from "@/lib/utils";
import { safeArtifactUrl } from "@/lib/safe-url";
import { Chip } from "@/components/ui/chip";
import { Empty } from "@/components/ui/card";

export function ArtifactLink({ a }: { a: ArtifactView }) {
  const href = safeArtifactUrl(a.url);
  return (
    <a
      href={href}
      aria-disabled={!href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex max-w-full items-center gap-1 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs hover:border-slate-400"
      title={`${a.name}\nsha256 ${a.sha256}\n${formatBytes(a.size_bytes)}`}
    >
      <FileText className="h-3 w-3 shrink-0 text-slate-500" aria-hidden />
      <span className="truncate font-medium text-link">{a.name}</span>
      <span className="font-mono-id shrink-0 text-[11px] text-slate-500">{a.sha256.slice(0, 10)}</span>
    </a>
  );
}

function OriginBadge({ origin }: { origin: string }) {
  const meta = originMeta(origin);
  return (
    <Chip tone={meta.tone} size="xs" title={meta.help}>
      {meta.label}
    </Chip>
  );
}

function ValueCell({ value }: { value: unknown }) {
  const text = formatValue(value);
  const unknown = text === "UNKNOWN" || value === null;
  if (typeof value === "object" && value !== null) {
    const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v] as const) : Object.entries(value as Record<string, unknown>);
    return (
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-xs">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-slate-500">{Array.isArray(value) ? "•" : k}</dt>
            <dd className="font-mono-id break-all text-slate-900">{formatValue(v)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className={cn("font-mono-id break-all", unknown ? "text-slate-500" : "font-semibold text-slate-950")}>{unknown ? "not observed" : text}</span>;
}

export function EvidenceExplorer({ evidence }: { evidence: EvidenceView[] }) {
  const [filter, setFilter] = useState<string>("all");
  const filters = useMemo(() => ["all", ...Array.from(new Set(evidence.map((e) => e.origin)))], [evidence]);
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return evidence.filter(
      (e) =>
        (filter === "all" || e.origin === filter) &&
        (!needle || [e.id, e.test_id, e.acquisition_mode, formatValue(e.value), ...e.artifacts.map((a) => a.name)].join(" ").toLowerCase().includes(needle)),
    );
  }, [evidence, filter, q]);

  if (!evidence.length) return <Empty>No evidence rows yet. They appear after evaluation.</Empty>;

  return (
    <div className="rounded-lg border border-border bg-white">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        {filters.map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-xs font-semibold",
              filter === f ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 text-slate-700 hover:border-slate-500",
            )}
          >
            {f === "all" ? `All (${evidence.length})` : `${originMeta(f).label} (${evidence.filter((e) => e.origin === f).length})`}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1.5 rounded-md border border-slate-300 px-2 py-1 text-sm">
          <Search className="h-4 w-4 text-slate-400" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search evidence" className="w-40 bg-transparent outline-none" aria-label="Search evidence" />
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[56rem] text-sm">
          <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-4 py-2">Evidence</th>
              <th className="px-2 py-2">Test</th>
              <th className="px-2 py-2">Value</th>
              <th className="px-2 py-2">Origin</th>
              <th className="px-2 py-2">Run</th>
              <th className="px-4 py-2">Artifacts</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((e) => (
              <tr key={e.id} id={citationAnchor(e.id)} className="align-top">
                <td className="px-4 py-2.5">
                  <div className="font-mono-id font-semibold text-slate-950">{e.id}</div>
                  <div className="text-xs text-slate-500">
                    {e.evidence_kind} · {e.acquisition_mode}
                  </div>
                </td>
                <td className="px-2 py-2.5 font-mono-id">{e.test_id ?? "—"}</td>
                <td className="max-w-xs px-2 py-2.5">
                  <ValueCell value={e.value} />
                  {e.locator ? <div className="mt-0.5 font-mono-id text-[11px] text-slate-500">at {e.locator}</div> : null}
                </td>
                <td className="px-2 py-2.5">
                  <OriginBadge origin={e.origin} />
                </td>
                <td className="px-2 py-2.5">
                  {e.run_id ? (
                    e.run_id.startsWith("RP-") ? (
                      <Link href={`/runs/${encodeURIComponent(e.run_id)}`} className="whitespace-nowrap font-mono-id text-[12px] text-link underline-offset-2 hover:underline">
                        {e.run_id}
                      </Link>
                    ) : (
                      <span className="whitespace-nowrap font-mono-id text-[12px] text-slate-700">{e.run_id}</span>
                    )
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex flex-col items-start gap-1">
                    {e.artifacts.length ? e.artifacts.map((a) => <ArtifactLink key={a.artifact_id + a.name} a={a} />) : <span className="text-slate-400">—</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length ? <p className="px-4 py-6 text-center text-sm text-slate-500">No evidence matches the filter.</p> : null}
      </div>
    </div>
  );
}

export function ArtifactsTable({ artifacts }: { artifacts: ArtifactView[] }) {
  if (!artifacts.length) return <Empty>No artifacts recorded.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-sm">
        <thead className="text-left text-xs font-bold uppercase tracking-wide text-slate-600">
          <tr>
            <th className="py-1.5 pr-3">Name</th>
            <th className="py-1.5 pr-3">Kind</th>
            <th className="py-1.5 pr-3">Test</th>
            <th className="py-1.5 pr-3">Size</th>
            <th className="py-1.5 pr-3">sha256</th>
            <th className="py-1.5" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {artifacts.map((a) => (
            <tr key={a.artifact_id}>
              <td className="py-1.5 pr-3 font-medium">{a.name}</td>
              <td className="py-1.5 pr-3 text-slate-600">{a.kind}</td>
              <td className="py-1.5 pr-3 font-mono-id">{a.test_id ?? "—"}</td>
              <td className="py-1.5 pr-3 tabular-nums text-slate-600">{formatBytes(a.size_bytes)}</td>
              <td className="py-1.5 pr-3 font-mono-id text-slate-600" title={a.sha256}>
                {shortHash(a.sha256, 16)}
              </td>
              <td className="py-1.5 text-right">
                <a
                  href={safeArtifactUrl(a.url)}
                  aria-disabled={!safeArtifactUrl(a.url)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-link hover:underline"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden /> Open
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
