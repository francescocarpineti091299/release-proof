import type { ReactNode } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

export function Hint({ text, className, label = "More information" }: { text: string; className?: string; label?: string }) {
  return (
    <span className={cn("group relative inline-flex align-middle", className)}>
      <button
        type="button"
        aria-label={`${label}: ${text}`}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full text-slate-500 hover:text-slate-900 focus-visible:text-slate-900"
      >
        <Info className="h-4 w-4" aria-hidden />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-1/2 z-40 mb-2 w-64 -translate-x-1/2 rounded-md bg-slate-900 px-3 py-2 text-left text-xs font-normal normal-case leading-snug tracking-normal text-white opacity-0 shadow-lg transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

export function WithHint({ children, text }: { children: ReactNode; text: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      {children}
      <Hint text={text} />
    </span>
  );
}
