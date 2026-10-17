import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function uniq<T>(items: T[]): T[] {
  return Array.from(new Set(items));
}

export function randomKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Scroll to an element rendered with `id="cite-<id>"`, opening collapsed sections first. */
export function scrollToCitation(id: string): boolean {
  if (typeof document === "undefined") return false;
  const el = document.getElementById(citationAnchor(id));
  if (!el) return false;
  let parent: HTMLElement | null = el.parentElement;
  while (parent) {
    if (parent instanceof HTMLDetailsElement && !parent.open) parent.open = true;
    parent = parent.parentElement;
  }
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("cite-flash");
  window.setTimeout(() => el.classList.remove("cite-flash"), 1800);
  return true;
}

export function citationAnchor(id: string): string {
  return `cite-${id.replace(/[^A-Za-z0-9_.:-]/g, "_")}`;
}
