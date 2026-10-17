import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function Card({ children, className, id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <div id={id} className={cn("rounded-lg border border-border bg-card shadow-sm", className)}>
      {children}
    </div>
  );
}

export function Section({
  id,
  title,
  eyebrow,
  description,
  actions,
  children,
  className,
}: {
  id?: string;
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cn("scroll-mt-24", className)}>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          {eyebrow ? <div className="mb-0.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{eyebrow}</div> : null}
          <h2 className="text-xl font-bold tracking-tight text-slate-950">{title}</h2>
          {description ? <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function Collapsible({
  summary,
  children,
  defaultOpen = false,
  className,
  id,
  right,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  id?: string;
  right?: ReactNode;
}) {
  return (
    <details id={id} open={defaultOpen} className={cn("group/col rounded-lg border border-border bg-card shadow-sm", className)}>
      <summary className="flex items-center gap-2 px-4 py-3 font-semibold text-slate-900 hover:bg-slate-50">
        <ChevronRight className="rp-chevron h-4 w-4 shrink-0 transition-transform" aria-hidden />
        <span className="min-w-0 flex-1">{summary}</span>
        {right}
      </summary>
      <div className="border-t border-border px-4 py-4">{children}</div>
    </details>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-dashed border-border bg-muted/50 px-4 py-6 text-center text-sm text-muted-foreground">{children}</p>;
}

export function KeyValue({ rows, mono = true }: { rows: [ReactNode, ReactNode][]; mono?: boolean }) {
  if (!rows.length) return <Empty>Nothing recorded.</Empty>;
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[minmax(10rem,max-content)_1fr]">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="font-medium text-slate-600">{k}</dt>
          <dd className={cn("min-w-0 break-all text-slate-900", mono && "font-mono-id")}>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
