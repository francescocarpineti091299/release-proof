"use client";

import { Fragment, useMemo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn, scrollToCitation } from "@/lib/utils";

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function linkify(children: ReactNode, re: RegExp | null, known: Set<string>): ReactNode {
  if (!re) return children;
  if (typeof children === "string") {
    const parts = children.split(re);
    if (parts.length === 1) return children;
    return parts.map((part, i) =>
      known.has(part) ? (
        <button
          key={`${part}-${i}`}
          type="button"
          onClick={() => scrollToCitation(part)}
          className="rounded bg-blue-50 px-1 font-mono-id text-blue-800 underline decoration-blue-300 underline-offset-2 hover:bg-blue-100"
        >
          {part}
        </button>
      ) : (
        <Fragment key={i}>{part}</Fragment>
      ),
    );
  }
  if (Array.isArray(children)) return children.map((c, i) => <Fragment key={i}>{linkify(c, re, known)}</Fragment>);
  return children;
}

/** Markdown renderer. IDs found in `citations` become buttons that scroll to the cited row. */
export function Markdown({ content, citations, className }: { content: string; citations?: Set<string>; className?: string }) {
  const components = useMemo<Components>(() => {
    const known = citations ?? new Set<string>();
    const ids = Array.from(known).sort((a, b) => b.length - a.length);
    const re = ids.length ? new RegExp(`(${ids.map(escapeRe).join("|")})`, "g") : null;
    const L = (c: ReactNode) => linkify(c, re, known);
    return {
      p: ({ children }) => <p className="mb-2 last:mb-0">{L(children)}</p>,
      li: ({ children }) => <li className="mb-0.5">{L(children)}</li>,
      ul: ({ children }) => <ul className="mb-2 list-disc pl-5 last:mb-0">{children}</ul>,
      ol: ({ children }) => <ol className="mb-2 list-decimal pl-5 last:mb-0">{children}</ol>,
      strong: ({ children }) => <strong className="font-semibold">{L(children)}</strong>,
      em: ({ children }) => <em>{L(children)}</em>,
      h1: ({ children }) => <h3 className="mb-2 mt-4 text-lg font-bold first:mt-0">{children}</h3>,
      h2: ({ children }) => <h4 className="mb-1.5 mt-4 text-base font-bold first:mt-0">{children}</h4>,
      h3: ({ children }) => <h5 className="mb-1 mt-3 text-sm font-bold first:mt-0">{children}</h5>,
      blockquote: ({ children }) => <blockquote className="mb-2 border-l-4 border-slate-300 pl-3 text-slate-600">{children}</blockquote>,
      a: ({ href, children }) => (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-link underline underline-offset-2">
          {children}
        </a>
      ),
      code: ({ className: cls, children }) =>
        cls?.includes("language-") ? (
          <code className={cn("font-mono text-[0.85em]", cls)}>{children}</code>
        ) : (
          <code className="rounded bg-slate-100 px-1 py-px font-mono text-[0.85em]">{L(children)}</code>
        ),
      pre: ({ children }) => <pre className="mb-2 overflow-x-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">{children}</pre>,
      table: ({ children }) => (
        <div className="mb-2 overflow-x-auto">
          <table className="w-full border-collapse text-sm">{children}</table>
        </div>
      ),
      th: ({ children }) => <th className="border border-slate-300 bg-slate-50 px-2 py-1 text-left font-semibold">{children}</th>,
      td: ({ children }) => <td className="border border-slate-300 px-2 py-1 align-top">{L(children)}</td>,
      hr: () => <hr className="my-3 border-slate-200" />,
    };
  }, [citations]);

  if (!content.trim()) return null;
  return (
    <div className={cn("min-w-0 break-words text-sm leading-relaxed", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
