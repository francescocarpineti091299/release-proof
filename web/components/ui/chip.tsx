import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/semantics";

const TONE_CLASSES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 border-emerald-300",
  amber: "bg-amber-50 text-amber-900 border-amber-300",
  slate: "bg-slate-100 text-slate-800 border-slate-300",
  red: "bg-red-50 text-red-800 border-red-300",
  blue: "bg-blue-50 text-blue-800 border-blue-300",
  neutral: "bg-white text-slate-700 border-slate-300",
};

export const TONE_SOLID: Record<Tone, string> = {
  green: "bg-emerald-700 text-white",
  amber: "bg-amber-500 text-black",
  slate: "bg-slate-600 text-white",
  red: "bg-red-700 text-white",
  blue: "bg-blue-700 text-white",
  neutral: "bg-slate-200 text-slate-900",
};

export const TONE_BORDER: Record<Tone, string> = {
  green: "border-emerald-600",
  amber: "border-amber-500",
  slate: "border-slate-500",
  red: "border-red-600",
  blue: "border-blue-600",
  neutral: "border-slate-300",
};

export function Chip({
  tone = "neutral",
  children,
  className,
  title,
  solid = false,
  size = "sm",
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
  solid?: boolean;
  size?: "xs" | "sm" | "md";
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border font-semibold",
        size === "xs" && "px-1.5 py-0 text-[11px] leading-5",
        size === "sm" && "px-2 py-0.5 text-xs",
        size === "md" && "px-3 py-1 text-sm",
        solid ? cn(TONE_SOLID[tone], "border-transparent") : TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Badge({ children, className, title }: { children: ReactNode; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded border border-slate-300 bg-white px-1.5 py-px text-[11px] font-semibold uppercase tracking-wide text-slate-700",
        className,
      )}
    >
      {children}
    </span>
  );
}
