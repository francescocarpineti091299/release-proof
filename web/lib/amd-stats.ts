import type { AITraceView, AmdDashboard, AmdModuleStats, AmdView } from "@/lib/types";
import { isRecord } from "@/lib/utils";

/** Accepts `[...]` or `{items|<key>: [...]}`. */
export function unwrapList<T>(raw: unknown, ...keys: string[]): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (isRecord(raw)) {
    for (const k of [...keys, "items", "data", "results"]) {
      const v = raw[k];
      if (Array.isArray(v)) return v as T[];
    }
  }
  return [];
}

function percentile(sorted: number[], p: number): number | null {
  if (!sorted.length) return null;
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[idx];
}

const MODULE_ORDER = ["planner", "explainer", "alternatives", "assistant", "smoke"];
const rank = (m: string) => (MODULE_ORDER.includes(m) ? MODULE_ORDER.indexOf(m) : 99);

/** Combine GET /api/amd with traces collected from recent runs into per-module rows. */
export function buildAmdDashboard(view: AmdView, traces: AITraceView[]): AmdDashboard {
  const groups = new Map<string, AITraceView[]>();
  for (const t of traces) groups.set(t.module, [...(groups.get(t.module) ?? []), t]);
  const modules = new Set<string>([
    ...Object.keys(view.provider.models ?? {}),
    ...Object.keys(view.traces.by_module ?? {}),
    ...groups.keys(),
  ]);
  const per_module: AmdModuleStats[] = Array.from(modules)
    .sort((a, b) => rank(a) - rank(b))
    .map((module) => {
      const list = groups.get(module) ?? [];
      const ok = list.filter((t) => t.status === "OK");
      const lat = ok
        .map((t) => t.latency_ms)
        .filter((v): v is number => typeof v === "number")
        .sort((a, b) => a - b);
      return {
        module,
        model: view.provider.models?.[module] ?? list.find((t) => t.model)?.model ?? null,
        calls: view.traces.by_module?.[module] ?? list.length,
        ok_rate: list.length ? ok.length / list.length : null,
        latency_p50_ms: percentile(lat, 50),
        latency_p95_ms: percentile(lat, 95),
      };
    });
  const recent_traces = [...traces].sort((a, b) => b.started_at.localeCompare(a.started_at));
  return { view, per_module, recent_traces };
}
