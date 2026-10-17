"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, Square, X } from "lucide-react";
import { api } from "@/lib/api";
import type { AssistantMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/ui/markdown";

const SUGGESTIONS = [
  "Why is this the verdict?",
  "What blocks the transition?",
  "What evidence shows the candidate boots?",
  "What would make this migration compatible?",
];

export function AssistantDrawer({ runId, open, onClose, citations }: { runId: string; open: boolean; onClose: () => void; citations: Set<string> }) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => () => {
    abort.current?.abort();
    abort.current = null;
  }, []);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || abort.current) return;
    const history: AssistantMessage[] = [...messages, { role: "user" as const, content }].slice(-24);
    setMessages([...history, { role: "assistant", content: "" }]);
    setDraft("");
    setBusy(true);
    setError(null);
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      await api.assistant(
        { run_id: runId, messages: history },
        (chunk) => {
          if (abort.current !== ctrl || ctrl.signal.aborted) return;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + chunk };
            return next;
          });
        },
        ctrl.signal,
      );
    } catch (e) {
      if (abort.current !== ctrl) return;
      if (!(e instanceof DOMException && e.name === "AbortError")) setError(e instanceof Error ? e.message : String(e));
      setMessages((prev) => (prev[prev.length - 1]?.content ? prev : prev.slice(0, -1)));
    } finally {
      if (abort.current === ctrl) {
        setMessages((prev) => (prev.at(-1)?.content ? prev : prev.slice(0, -1)));
        setBusy(false);
        abort.current = null;
      }
    }
  };

  return (
    <aside
      aria-label="Run assistant"
      inert={!open}
      className={cn(
        "fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-slate-300 bg-white shadow-2xl transition-transform duration-200",
        open ? "translate-x-0" : "pointer-events-none translate-x-full",
      )}
    >
      <div className="flex items-center gap-2 border-b border-border bg-slate-950 px-4 py-3 text-white">
        <Bot className="h-5 w-5 text-violet-300" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="font-bold">Ask about this run</div>
          <div className="truncate font-mono-id text-xs text-slate-400">{runId} · AMD-hosted assistant</div>
        </div>
        <button type="button" onClick={onClose} className="rounded p-1 hover:bg-slate-800" aria-label="Close assistant" tabIndex={open ? 0 : -1}>
          <X className="h-5 w-5" aria-hidden />
        </button>
      </div>
      <p className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-950">
        Answers cite this run&apos;s evidence; the verdict comes from the deterministic engine.
      </p>
      <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="space-y-2">
            <p className="text-sm text-slate-600">Ask a question about this run. For example:</p>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                tabIndex={open ? 0 : -1}
                onClick={() => void send(s)}
                className="block w-full rounded-md border border-slate-300 px-3 py-2 text-left text-sm hover:border-slate-500 hover:bg-slate-50"
              >
                {s}
              </button>
            ))}
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cn("max-w-[90%] rounded-lg px-3 py-2", m.role === "user" ? "bg-slate-900 text-white" : "border border-border bg-slate-50 text-slate-900")}>
                {m.role === "user" ? (
                  <p className="whitespace-pre-wrap text-sm">{m.content}</p>
                ) : m.content ? (
                  <Markdown content={m.content} citations={citations} />
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin text-slate-500" aria-label="Thinking" />
                )}
              </div>
            </div>
          ))
        )}
        {error ? (
          <p className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
            Assistant unavailable: {error}
          </p>
        ) : null}
      </div>
      <form
        className="flex items-end gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <textarea
          ref={input}
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, 4000))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send(draft);
            }
          }}
          rows={2}
          tabIndex={open ? 0 : -1}
          placeholder="Ask about evidence, blockers, unknowns…"
          className="min-h-[2.75rem] flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-600"
          aria-label="Your question"
        />
        {busy ? (
          <button type="button" onClick={() => abort.current?.abort()} className="flex h-11 w-11 items-center justify-center rounded-md bg-slate-200 hover:bg-slate-300" aria-label="Stop">
            <Square className="h-4 w-4" aria-hidden />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!draft.trim()}
            tabIndex={open ? 0 : -1}
            className="flex h-11 w-11 items-center justify-center rounded-md bg-slate-950 text-white hover:bg-slate-800 disabled:bg-slate-300"
            aria-label="Send"
          >
            <Send className="h-4 w-4" aria-hidden />
          </button>
        )}
      </form>
    </aside>
  );
}
