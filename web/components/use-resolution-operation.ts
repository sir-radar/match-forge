"use client";

import { useEffect, useRef } from "react";

// Shared by single and batch approval forms: cancel reads, never abort approved writes.
export function useResolutionOperation() {
  const pending = useRef(false), mounted = useRef(true), controller = useRef<AbortController | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; controller.current?.abort(); }; }, []);
  return { pending, mounted, controller };
}
