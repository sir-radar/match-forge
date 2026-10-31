"use client";

import { useEffect, useRef } from "react";

// Single and batch forms share one operation lifecycle. Only reads are cancellable.
export function useResolutionOperation() {
  const operationRef = useRef({ pending: false, mounted: true, controller: null as AbortController | null });
  useEffect(() => {
    const operation = operationRef.current;
    operation.mounted = true;
    return () => { operation.mounted = false; operation.controller?.abort(); };
  }, []);
  const begin = () => {
    if (operationRef.current.pending) return false;
    operationRef.current.pending = true;
    return true;
  };
  const finish = () => { operationRef.current.pending = false; };
  const cancelRead = () => operationRef.current.controller?.abort();
  const newRead = () => {
    cancelRead();
    const controller = new AbortController();
    operationRef.current.controller = controller;
    return controller;
  };
  const isMounted = () => operationRef.current.mounted;
  return { begin, finish, cancelRead, newRead, isMounted };
}
