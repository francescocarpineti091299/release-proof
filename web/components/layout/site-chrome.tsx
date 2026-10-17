"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Cpu, FlaskConical, History, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "New assessment", icon: FlaskConical },
  { href: "/reference", label: "Reference run", icon: History },
  { href: "/amd", label: "AMD AI", icon: Cpu },
];

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950 text-white">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-bold tracking-tight">
          <ShieldCheck className="h-6 w-6 text-emerald-400" aria-hidden />
          <span className="text-lg">ReleaseProof</span>
        </Link>
        <nav aria-label="Main" className="ml-auto flex items-center gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex h-9 items-center gap-2 rounded-md px-2.5 text-sm font-semibold text-slate-300 hover:bg-slate-800 hover:text-white sm:px-3",
                  active && "bg-slate-800 text-white",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                <span className="hidden sm:inline">{label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
      {pathname.startsWith("/reference") ? (
        <div className="border-b-2 border-slate-700 bg-slate-200 text-slate-950">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 sm:px-6">
            <span className="inline-flex items-center gap-1.5 rounded bg-slate-900 px-2 py-0.5 text-xs font-black tracking-widest text-white">
              <History className="h-3.5 w-3.5" aria-hidden /> RECORDED
            </span>
            <span className="text-sm font-semibold">Reference run recorded on 2026-10-01. Not a live run; nothing here was executed in this session.</span>
          </div>
        </div>
      ) : null}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-5 text-sm text-slate-600 sm:px-6">
        <span className="font-semibold text-slate-800">Runs on AMD-hosted AI · Renode emulation · contract V1.2</span>
        <span>Non-official engineering assessments. The verdict comes from a deterministic engine, never from the AI.</span>
      </div>
    </footer>
  );
}
