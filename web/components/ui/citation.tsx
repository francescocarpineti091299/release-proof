"use client";

import { Link2 } from "lucide-react";
import { cn, scrollToCitation } from "@/lib/utils";

/** A cited evidence / requirement / invariant / gap ID. Unknown IDs render as not-found. */
export function CitationChip({ id, known }: { id: string; known?: Set<string> }) {
  const valid = !known || known.has(id);
  return (
    <button
      type="button"
      disabled={!valid}
      onClick={() => scrollToCitation(id)}
      title={valid ? `Go to ${id}` : `${id} is not part of this run's evidence (citation rejected)`}
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-px font-mono-id text-[12px]",
        valid
          ? "border-blue-200 bg-blue-50 text-blue-800 hover:border-blue-400 hover:bg-blue-100"
          : "cursor-not-allowed border-slate-200 bg-slate-50 text-slate-400 line-through",
      )}
    >
      <Link2 className="h-3 w-3" aria-hidden />
      {id}
    </button>
  );
}

export function Citations({ ids, known }: { ids: string[]; known?: Set<string> }) {
  if (!ids.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {ids.map((id) => (
        <CitationChip key={id} id={id} known={known} />
      ))}
    </span>
  );
}
