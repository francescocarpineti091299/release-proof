"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Terminal } from "lucide-react";
import type { ConnectionState } from "@/lib/api";
import type { LogStream } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Collapsible } from "@/components/ui/card";
import type { LiveLog } from "./use-live-run";

const STREAMS: LogStream[] = ["runner", "build", "sign", "renode", "uart", "tool"];

const STREAM_COLOR: Record<LogStream, string> = {
  runner: "text-sky-300",
  build: "text-slate-300",
  sign: "text-amber-300",
  renode: "text-violet-300",
  uart: "text-emerald-300",
  tool: "text-cyan-300",
};

const CONN_LABEL: Record<ConnectionState, string> = {
  connecting: "connecting…",
  open: "live",
  reconnecting: "reconnecting…",
  closed: "stream closed",
};

export function LogTail({ logs, conn, limit = 200 }: { logs: LiveLog[]; conn: ConnectionState; limit?: number }) {
  const [filter, setFilter] = useState<LogStream | "all">("all");
  const [stick, setStick] = useState(true);
  const box = useRef<HTMLPreElement>(null);

  const shown = useMemo(() => {
    const list = filter === "all" ? logs : logs.filter((l) => l.stream === filter);
    return list.slice(-limit);
  }, [logs, filter, limit]);

  useEffect(() => {
    if (stick && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [shown, stick]);

  return (
    <Collapsible
      id="logs"
      summary={
        <span className="flex items-center gap-2">
          <Terminal className="h-4 w-4" aria-hidden /> Live log tail
          <span className="text-sm font-normal text-slate-500">
            last {Math.min(limit, shown.length)} of {logs.length} lines
          </span>
        </span>
      }
      right={
        <span className={cn("flex items-center gap-1.5 text-xs font-semibold", conn === "open" ? "text-emerald-700" : "text-slate-500")}>
          <span className={cn("h-2 w-2 rounded-full", conn === "open" ? "rp-pulse bg-emerald-500" : conn === "reconnecting" ? "bg-amber-500" : "bg-slate-400")} />
          {CONN_LABEL[conn]}
        </span>
      }
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by stream">
        {(["all", ...STREAMS] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setFilter(s)}
            aria-pressed={filter === s}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-xs font-semibold",
              filter === s ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-700 hover:border-slate-500",
            )}
          >
            {s}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" checked={stick} onChange={(e) => setStick(e.target.checked)} /> Follow
        </label>
      </div>
      <pre
        ref={box}
        className="max-h-96 min-h-32 overflow-auto rounded-md bg-slate-950 p-3 font-mono text-[12px] leading-relaxed text-slate-200"
        aria-live="off"
      >
        {shown.length === 0 ? (
          <span className="text-slate-500">No log lines yet.</span>
        ) : (
          shown.map((l) => (
            <div key={l.key} className="whitespace-pre-wrap break-all">
              <span className={cn("inline-block w-14 select-none", STREAM_COLOR[l.stream] ?? "text-slate-400")}>{l.stream}</span>
              {l.test_id ? <span className="select-none text-slate-500">[{l.test_id}] </span> : null}
              {l.line}
            </div>
          ))
        )}
      </pre>
    </Collapsible>
  );
}
