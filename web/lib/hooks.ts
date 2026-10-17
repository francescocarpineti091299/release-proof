"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => void;
}

export function useApi<T>(key: string | null, load: () => Promise<T>): AsyncState<T> {
  const loadRef = useRef(load);
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<{ key: string | null; nonce: number; data?: T; error?: Error; done: boolean }>({ key: null, nonce: -1, done: false });

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    if (key === null) return;
    let alive = true;
    Promise.resolve().then(() => loadRef.current()).then(
      (data) => alive && setState({ key, nonce, data, done: true }),
      (error: unknown) => alive && setState({ key, nonce, error: error instanceof Error ? error : new Error(String(error)), done: true }),
    );
    return () => {
      alive = false;
    };
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const fresh = state.key === key && state.nonce === nonce;
  return {
    data: fresh ? state.data : undefined,
    error: fresh ? state.error : undefined,
    loading: key !== null && (!fresh || !state.done),
    reload,
  };
}

/** Current time, updated every `ms` while `active`. Returns 0 before mount (SSR-safe). */
export function useNow(ms = 1000, active = true): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    if (!active) return () => clearTimeout(first);
    const id = setInterval(tick, ms);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [ms, active]);
  return now;
}
